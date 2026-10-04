"""E45.2 — endurecimiento de la carga móvil del piloto: límites explícitos, lectura acotada y
normalización de HEIC/HEIF.

Es una corrección operacional de la web de E45, no un sistema nuevo: no toca E44 ni E37, sólo
decide qué bytes pueden entrar a `campaign.import_upload`. El motor nunca ve HEIC: una foto de
iPhone se decodifica acá y entra al proyecto como JPG.

Los límites viven en constantes (y se pueden bajar con el entorno en un despliegue chico, nunca
subir por encima del tope del servidor). Valores elegidos para un iPhone típico: HEIC 12 MP ≈ 2–4 MB,
JPG 12 MP ≈ 3–6 MB, 48 MP ≈ 10–15 MB; un caso real tiene 6–15 fotos.
"""
from __future__ import annotations

import io
import os
from typing import IO, List, Tuple

MAX_FOTOS = int(os.environ.get("ESCALIMETRO_PILOT_MAX_FOTOS", "20"))
MAX_FOTO_MB = int(os.environ.get("ESCALIMETRO_PILOT_MAX_FOTO_MB", "15"))
MAX_LOTE_MB = int(os.environ.get("ESCALIMETRO_PILOT_MAX_LOTE_MB", "120"))
MAX_PLANO_REAL_MB = int(os.environ.get("ESCALIMETRO_PILOT_MAX_PLANO_MB", "25"))
# decodificar una imagen cuesta ~4 bytes por píxel: este tope acota la memoria de la conversión
MAX_PIXELES = 80_000_000
MAX_LADO_PX = 12_000
CHUNK = 64 * 1024
# el cuerpo entero de un POST de CREAR (fotos + plano real + campos) no puede pasar de esto
MAX_ENVIO_BYTES = (MAX_LOTE_MB + MAX_PLANO_REAL_MB + 2) * 1024 * 1024

FOTO_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif")
PLANO_EXTS = (".pdf", ".png", ".jpg", ".jpeg")
FORMATOS_FOTO = "JPG, PNG, WEBP, HEIC o HEIF"
FORMATOS_PLANO = "PDF, JPG o PNG"
ACCEPT_FOTOS = "image/png,image/jpeg,image/webp,image/heic,image/heif,.heic,.heif"

_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs",
                b"mif1", b"msf1", b"heif", b"avif"}


class UploadError(ValueError):
    """Mensaje ya redactado para quien sube el material."""


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.0f}"


def _nombre(n: str) -> str:
    return os.path.basename(n or "")[:60]


def leer_limitado(stream: IO[bytes], max_bytes: int, nombre: str, *, presupuesto: List[int]) -> bytes:
    """Lee `stream` en trozos y aborta EN CUANTO se pasa de `max_bytes` (por archivo) o se agota
    el `presupuesto` del lote: nunca se lee un archivo entero para después medirlo. `presupuesto`
    es una lista de un elemento con los bytes que le quedan al lote (se descuenta en el sitio)."""
    out = bytearray()
    while True:
        trozo = stream.read(CHUNK)
        if not trozo:
            break
        out += trozo
        if len(out) > max_bytes:
            raise UploadError(f"«{_nombre(nombre)}» pesa demasiado: el máximo por archivo es "
                              f"{_mb(max_bytes)} MB. Reduce su tamaño o elige otra.")
        presupuesto[0] -= len(trozo)
        if presupuesto[0] < 0:
            raise UploadError(f"El lote de fotos pesa demasiado: el máximo total es "
                              f"{MAX_LOTE_MB} MB. Sube menos fotos o más livianas.")
    return bytes(out)


def leer_fotos(storages) -> List[Tuple[str, bytes]]:
    """Fotos de un envío de CREAR: valida la cantidad ANTES de leer ningún byte."""
    storages = [s for s in storages if s and s.filename]
    if len(storages) > MAX_FOTOS:
        raise UploadError(f"Subiste {len(storages)} fotos; el máximo por propiedad es {MAX_FOTOS}. "
                          "Elige las más representativas.")
    for s in storages:
        if os.path.splitext(s.filename)[1].lower() not in FOTO_EXTS:
            raise UploadError(f"Formato no aceptado: «{_nombre(s.filename)}». "
                              f"Las fotos pueden ser {FORMATOS_FOTO}.")
    presupuesto = [MAX_LOTE_MB * 1024 * 1024]
    return [(s.filename, leer_limitado(s.stream, MAX_FOTO_MB * 1024 * 1024, s.filename,
                                       presupuesto=presupuesto)) for s in storages]


def leer_plano_real(storage) -> Tuple[str, bytes] | None:
    if not storage or not storage.filename:
        return None
    if os.path.splitext(storage.filename)[1].lower() not in PLANO_EXTS:
        raise UploadError(f"Formato no aceptado para el plano real: «{_nombre(storage.filename)}». "
                          f"Puede ser {FORMATOS_PLANO}.")
    presupuesto = [MAX_PLANO_REAL_MB * 1024 * 1024]
    return storage.filename, leer_limitado(storage.stream, MAX_PLANO_REAL_MB * 1024 * 1024,
                                           storage.filename, presupuesto=presupuesto)


# --------------------------------------------------------------------------------------------
# contenido real
# --------------------------------------------------------------------------------------------
def _tipo_por_cabecera(blob: bytes) -> str:
    if blob.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    if blob[4:8] == b"ftyp" and blob[8:12] in _HEIF_BRANDS:
        return "heif"
    if blob.startswith(b"%PDF"):
        return "pdf"
    return ""


def _abrir_imagen(blob: bytes, nombre: str):
    from PIL import Image                                          # noqa: PLC0415
    try:
        import pillow_heif                                         # noqa: PLC0415
        pillow_heif.register_heif_opener()
    except ImportError:                                            # sin la librería no se finge soporte
        pass
    Image.MAX_IMAGE_PIXELS = MAX_PIXELES
    ilegible = UploadError(f"No pudimos leer «{_nombre(nombre)}»: el archivo está dañado o no es "
                           "una imagen válida. Vuelve a exportarlo o elige otro.")
    try:
        im = Image.open(io.BytesIO(blob))
        w, h = im.size
    except Exception:                                              # noqa: BLE001
        raise ilegible from None
    if w * h > MAX_PIXELES or max(w, h) > MAX_LADO_PX:
        raise UploadError(f"«{_nombre(nombre)}» tiene una resolución demasiado alta ({w}×{h} px). "
                          "Expórtala a un tamaño menor.")
    try:
        im.load()
    except Exception:                                              # noqa: BLE001
        raise ilegible from None
    return im


def normalizar_foto(nombre: str, blob: bytes) -> Tuple[str, bytes]:
    """JPG/PNG/WEBP: se verifica que decodifiquen y pasan INTACTOS (el original es evidencia).
    HEIC/HEIF: se decodifican, se aplica la orientación y salen como JPG; el original no se
    conserva, el pipeline ya consume JPG. Un archivo cuyo contenido no corresponde a una imagen
    soportada se rechaza aunque su extensión lo disfrace."""
    ext = os.path.splitext(nombre)[1].lower()
    tipo = _tipo_por_cabecera(blob)
    esperado = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp",
                ".heic": "heif", ".heif": "heif"}.get(ext)
    if tipo not in ("jpeg", "png", "webp", "heif") or tipo != esperado:
        raise UploadError(f"«{_nombre(nombre)}» no es una foto {ext.lstrip('.').upper()} válida: "
                          "su contenido no coincide con su formato.")
    if tipo == "heif":
        try:
            import pillow_heif                                     # noqa: F401, PLC0415
        except ImportError:
            raise UploadError("Este servidor no puede leer fotos HEIC todavía. Expórtalas como "
                              "JPG desde el iPhone (Ajustes › Cámara › Formatos › Más compatible).") from None
    im = _abrir_imagen(blob, nombre)
    if tipo != "heif":
        return nombre, blob
    from PIL import Image, ImageOps                                # noqa: PLC0415
    try:
        # pillow-heif ya aplica la rotación `irot` del contenedor; exif_transpose cubre el EXIF
        # que pudiera quedar (y es no-op si el valor ya es 1, así que no rota dos veces)
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92, optimize=True)
    except Exception:                                              # noqa: BLE001
        raise UploadError(f"No pudimos convertir «{_nombre(nombre)}». Vuelve a exportarla como "
                          "JPG o elige otra.") from None
    return os.path.splitext(nombre)[0] + ".jpg", buf.getvalue()


def validar_plano(nombre: str, blob: bytes) -> None:
    """Contenido real del plano (publicado en MEJORAR o real de CREAR): PDF con páginas, o
    PNG/JPG que decodifiquen. No se acepta por extensión."""
    ext = os.path.splitext(nombre)[1].lower()
    tipo = _tipo_por_cabecera(blob)
    esperado = {".pdf": "pdf", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}.get(ext)
    if tipo != esperado or esperado is None:
        raise UploadError(f"«{_nombre(nombre)}» no es un {ext.lstrip('.').upper()} válido: "
                          "su contenido no coincide con su formato.")
    if tipo == "pdf":
        try:
            import pymupdf                                         # noqa: PLC0415
            with pymupdf.open(stream=blob, filetype="pdf") as doc:
                if doc.page_count < 1:
                    raise ValueError("sin páginas")
        except Exception:                                          # noqa: BLE001
            raise UploadError(f"No pudimos leer «{_nombre(nombre)}»: el PDF está dañado o "
                              "vacío.") from None
        return
    _abrir_imagen(blob, nombre)
