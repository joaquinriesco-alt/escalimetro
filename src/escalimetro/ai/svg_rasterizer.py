"""E12 — rasterización SVG → PNG robusta y portable.

Por qué existe este módulo, en una línea: en Railway `cv2.imwrite` recibió `None` y murió con
`(-215:Assertion failed) !_img.empty()`. El `None` venía de un `except Exception: pass` que se tragaba el
fallo real del rasterizador. Aquí no se traga nada.

Backends, en orden de preferencia:

    1. resvg      — rueda Rust autocontenida (abi3, py3.10+), SIN librerías nativas del sistema.
                    Es la primaria justamente por eso: en una imagen slim de Railway no hay que instalar
                    nada. Renderiza `<svg>` anidado, texto y paths igual que cairo.
    2. cairosvg   — excelente calidad, pero necesita libcairo.so.2 del sistema vía cffi. En Debian slim
                    no está, y ése fue el fallo de la primera corrida. Queda como respaldo.

No hay backend basado en ejecutables externos (Inkscape, rsvg-convert, ImageMagick, Chrome): Railway
podría no tenerlos y el fallo sería el mismo pero más difícil de diagnosticar.

Ninguno de los dos altera el SVG: se rasteriza el string tal cual."""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

MIN_WIDTH, MAX_WIDTH = 16, 20000
BACKENDS = ("resvg", "cairosvg")


class PresentationRasterizationError(RuntimeError):
    """Fallo al convertir un SVG de presentación en un raster utilizable.

    Lleva sólo información diagnóstica no sensible: nunca el SVG completo, nunca credenciales."""

    def __init__(self, reason: str, *, svg_length: int = 0, target_width: int = 0,
                 backend: str = "none", attempts: Optional[List[str]] = None):
        self.reason = reason
        self.svg_length = int(svg_length)
        self.target_width = int(target_width)
        self.backend = backend
        self.attempts = attempts or []
        super().__init__(f"{reason} · svg_length={self.svg_length} · target_width={self.target_width} "
                         f"· backend={self.backend}"
                         + (f" · intentos=[{'; '.join(self.attempts)}]" if self.attempts else ""))

    def to_dict(self) -> dict:
        return {"error": "PresentationRasterizationError", "reason": self.reason,
                "svg_length": self.svg_length, "target_width": self.target_width,
                "backend": self.backend, "attempts": self.attempts}


# ---------------------------------------------------------------------------------------------------
# backends
# ---------------------------------------------------------------------------------------------------
def _resvg(svg: str, width: int) -> bytes:
    import resvg_py                       # rueda autocontenida; sin libs del sistema
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width, background="#ffffff"))


def _cairosvg(svg: str, width: int) -> bytes:
    import cairosvg                       # requiere libcairo.so.2 en el sistema
    return cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=width)


_IMPL = {"resvg": _resvg, "cairosvg": _cairosvg}


def available_backends() -> List[str]:
    """Qué backends se pueden importar aquí y ahora. Útil para el log de arranque en Railway."""
    ok = []
    for name in BACKENDS:
        try:
            if name == "resvg":
                import resvg_py           # noqa: F401
            else:
                import cairosvg           # noqa: F401
            ok.append(name)
        except Exception:
            continue
    return ok


# ---------------------------------------------------------------------------------------------------
def rasterize_svg_to_bgr(svg: str, target_width: int, backends: Optional[Tuple[str, ...]] = None) -> np.ndarray:
    """SVG (string) → ndarray BGR válido. Levanta `PresentationRasterizationError` o devuelve algo usable.

    Nunca devuelve None ni un array vacío: ése era exactamente el contrato que faltaba."""
    n = len(svg or "")
    if not svg or not svg.strip():
        raise PresentationRasterizationError("svg vacío", svg_length=n, target_width=target_width)
    if "<svg" not in svg:
        raise PresentationRasterizationError("el texto no contiene un elemento <svg>", svg_length=n,
                                             target_width=target_width)
    if not isinstance(target_width, (int, np.integer)) or isinstance(target_width, bool):
        raise PresentationRasterizationError("target_width no es un entero", svg_length=n, target_width=0)
    if not (MIN_WIDTH <= int(target_width) <= MAX_WIDTH):
        raise PresentationRasterizationError(
            f"target_width fuera de rango [{MIN_WIDTH}, {MAX_WIDTH}]", svg_length=n, target_width=target_width)

    attempts: List[str] = []
    for name in (backends or BACKENDS):
        impl = _IMPL.get(name)
        if impl is None:
            attempts.append(f"{name}: backend desconocido")
            continue
        try:
            png = impl(svg, int(target_width))
        except ImportError as e:
            attempts.append(f"{name}: no instalado ({type(e).__name__})")
            continue
        except OSError as e:                       # típico: falta libcairo.so.2
            attempts.append(f"{name}: librería del sistema ausente ({type(e).__name__})")
            continue
        except Exception as e:                     # el backend existe pero no pudo con este SVG
            attempts.append(f"{name}: {type(e).__name__}")
            continue
        if not png:
            attempts.append(f"{name}: devolvió 0 bytes")
            continue
        arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if arr is None or arr.size == 0 or arr.ndim != 3 or arr.shape[0] <= 0 or arr.shape[1] <= 0:
            attempts.append(f"{name}: el PNG no decodifica a una imagen válida")
            continue
        return arr

    raise PresentationRasterizationError("ningún backend pudo rasterizar el SVG", svg_length=n,
                                         target_width=target_width, backend="none", attempts=attempts)


# ---------------------------------------------------------------------------------------------------
def validate_bgr(image, *, what: str = "imagen") -> np.ndarray:
    """Comprueba que algo es realmente una imagen antes de escribirla. Nunca más un assert de OpenCV."""
    if image is None:
        raise PresentationRasterizationError(f"{what}: la imagen es None")
    if not isinstance(image, np.ndarray):
        raise PresentationRasterizationError(f"{what}: no es un ndarray ({type(image).__name__})")
    if image.size == 0:
        raise PresentationRasterizationError(f"{what}: array vacío")
    if image.ndim not in (2, 3):
        raise PresentationRasterizationError(f"{what}: ndim inválido ({image.ndim})")
    if image.shape[0] <= 0 or image.shape[1] <= 0:
        raise PresentationRasterizationError(f"{what}: dimensiones inválidas {image.shape[:2]}")
    if image.ndim == 3 and image.shape[2] not in (1, 3, 4):
        raise PresentationRasterizationError(f"{what}: canales inválidos ({image.shape[2]})")
    return image


def imwrite_guarded(path: str, image, *, what: str = "imagen") -> str:
    """`cv2.imwrite` con red de seguridad a los dos lados: valida la entrada y comprueba el retorno.

    `cv2.imwrite` devuelve False sin lanzar cuando no puede escribir (ruta inexistente, permisos,
    extensión desconocida). Eso también es un fallo y aquí se trata como tal."""
    import os
    validate_bgr(image, what=what)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    try:
        ok = cv2.imwrite(path, image)
    except cv2.error as exc:                                   # extensión desconocida, códec ausente
        raise PresentationRasterizationError(
            f"{what}: cv2.imwrite falló para {os.path.basename(path)} ({exc.__class__.__name__})") from exc
    if not ok:
        raise PresentationRasterizationError(f"{what}: cv2.imwrite devolvió False para {os.path.basename(path)}")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise PresentationRasterizationError(f"{what}: el archivo no quedó escrito ({os.path.basename(path)})")
    return path


def rasterize_and_write(svg: str, target_width: int, path: str, *, what: str = "lámina") -> str:
    """El camino completo, sin huecos: SVG → ndarray validado → PNG en disco verificado."""
    return imwrite_guarded(path, rasterize_svg_to_bgr(svg, target_width), what=what)
