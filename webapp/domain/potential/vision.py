"""E17.0 — LO QUE SE PUEDE MEDIR DE UNA FOTO SIN INVENTAR NADA.

=================================================================================================
Qué hace este módulo y, sobre todo, qué NO hace
=================================================================================================
Mide propiedades **ópticas** de una imagen: cuánta luz tiene, cuán nítida es, cuánto detalle hay,
si las verticales están torcidas, si es igual a otra. Todo eso son magnitudes de la imagen, se
calculan con aritmética sobre píxeles y se pueden volver a calcular para comprobarlas.

NO clasifica escenas. No dice "esto es un living", no dice "esto está vacío", no dice "esto es
bonito". Eso requeriría un modelo que no tenemos y produciría afirmaciones que no podríamos
sostener frente a quien nos pregunte por qué.

Donde hace falta una señal que no es óptica —¿este espacio está vacío?— se usa un **proxy
declarado como tal**: `emptiness_proxy` mide densidad de bordes en la mitad inferior del cuadro,
que baja cuando hay poco mobiliario y sube cuando hay mucho. Es una correlación razonable y no es
un detector de muebles; por eso viaja con ese nombre, nunca alimenta un criterio por sí solo, y la
evidencia que se muestra al usuario es la medición, no una conclusión.

=================================================================================================
De dónde salen los umbrales
=================================================================================================
De propiedades del formato, no de un dataset que no tenemos:

* `brightness` se compara contra una banda centrada porque una imagen de 8 bits con media bajo
  0.25 tiene la mayoría de su información en los primeros niveles, donde el ruido de compresión
  es del mismo orden que la señal;
* `sharpness` usa la varianza del laplaciano normalizada por el tamaño, que es la medida estándar
  de enfoque y no depende de la escena;
* el umbral de duplicado es distancia de Hamming ≤ 5 sobre 64 bits de dHash, que es el valor
  habitual para "la misma foto reencodeada" y deja pasar dos tomas distintas del mismo ambiente.

Ninguno está calibrado sobre avisos reales. Van con nombre y valor visibles para que el día que
haya muestra se puedan discutir con datos, igual que hicimos con los umbrales del motor.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: Banda de luminancia media aceptable (0–1). Fuera de ella la foto se lee oscura o quemada.
BRIGHTNESS_OK = (0.28, 0.72)
BRIGHTNESS_DARK = 0.22
#: Varianza del laplaciano por debajo de la cual una foto se ve blanda en pantalla.
SHARPNESS_MIN = 60.0
#: Lado menor mínimo para que una foto aguante una portada.
MIN_SHORT_SIDE = 800
#: Distancia de Hamming sobre dHash de 64 bits para considerar dos fotos la misma.
DUPLICATE_HAMMING = 5
#: Inclinación de verticales, en grados, a partir de la cual la perspectiva se nota torcida.
TILT_DEGREES = 2.5

ANALYZER_VISION_VERSION = "vision-v0"


def _cv():
    import cv2                                                 # noqa: PLC0415
    import numpy as np                                         # noqa: PLC0415
    return cv2, np


def dhash(gray, size: int = 8) -> Optional[int]:
    """Huella perceptual: compara cada píxel con su vecino derecho sobre una miniatura. Dos
    reencodificaciones de la misma foto dan la misma huella; dos tomas distintas del mismo
    ambiente, no."""
    cv2, np = _cv()
    chico = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = chico[:, 1:] > chico[:, :-1]
    v = 0
    for b in bits.flatten():
        v = (v << 1) | int(b)
    return v


def hamming(a: Optional[int], b: Optional[int]) -> int:
    if a is None or b is None:
        return 64
    return bin(a ^ b).count("1")


def measure(path: str) -> Dict:
    """Todas las mediciones de una imagen. Si no se puede leer, se dice; no se devuelve un cero
    que después parezca una medición."""
    try:
        cv2, np = _cv()
    except ImportError:
        return {"ok": False, "reason": "sin OpenCV disponible"}
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "reason": "no se pudo leer la imagen"}
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = gray.astype("float32") / 255.0

    brillo = float(g.mean())
    contraste = float(g.std())
    nitidez = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    quemados = float((gray >= 250).mean())
    apagados = float((gray <= 5).mean())

    bordes = cv2.Canny(gray, 80, 200)
    densidad = float((bordes > 0).mean())
    # mitad inferior: es donde está el suelo y, si hay, el mobiliario. Ver el encabezado: es un
    # PROXY de ocupación, no un detector de muebles.
    inferior = bordes[h // 2:, :]
    vacio = float((inferior > 0).mean())

    return {
        "ok": True, "version": ANALYZER_VISION_VERSION,
        "width": int(w), "height": int(h), "megapixels": round(w * h / 1e6, 2),
        "short_side": int(min(w, h)),
        "orientation": "landscape" if w > h * 1.05 else ("portrait" if h > w * 1.05 else "square"),
        "brightness": round(brillo, 4),
        "contrast": round(contraste, 4),
        "sharpness": round(nitidez, 2),
        "clipped_highlights": round(quemados, 4),
        "clipped_shadows": round(apagados, 4),
        "edge_density": round(densidad, 4),
        "emptiness_proxy": round(vacio, 4),
        "vertical_tilt_deg": _tilt(img),
        "dhash": dhash(gray),
    }


def _tilt(img) -> Optional[float]:
    """Cuánto se desvían de la vertical las líneas largas y casi verticales del cuadro.

    En una foto de interior esas líneas son jambas, cantos de muro y marcos: si están torcidas, la
    foto se ve caída. Se toma la MEDIANA de las desviaciones para que una diagonal suelta —una
    escalera, un mueble— no arrastre el resultado."""
    cv2, np = _cv()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    lineas = cv2.HoughLinesP(cv2.Canny(gray, 80, 200), 1, np.pi / 360,
                             threshold=80, minLineLength=max(40, h // 6), maxLineGap=8)
    if lineas is None:
        return None
    desv = []
    # HoughLinesP devuelve (N,1,4); reshape explícito en vez de `lineas[:, 0]`, que según la
    # versión de OpenCV devuelve un escalar y revienta al desempaquetar.
    for x1, y1, x2, y2 in lineas.reshape(-1, 4):
        dx, dy = float(x2 - x1), float(y2 - y1)
        if abs(dy) < 1e-6:
            continue
        ang = abs(np.degrees(np.arctan2(dx, dy)))              # 0° = perfectamente vertical
        ang = min(ang, 180.0 - ang)
        if ang <= 20.0:                                        # sólo las que pretenden ser verticales
            desv.append(ang)
    return round(float(np.median(desv)), 2) if len(desv) >= 4 else None


# =================================================================================================
# calidad técnica comparable entre fotos del mismo aviso
# =================================================================================================
#: Los cuatro componentes de la calidad técnica y cuánto pesa cada uno. Están acá, con nombre y
#: valor, porque de esto sale la respuesta a "¿la portada es la mejor foto disponible?" y esa
#: respuesta tiene que poder discutirse sin leer el código.
QUALITY_WEIGHTS = {"exposure": 0.35, "sharpness": 0.30, "resolution": 0.20, "framing": 0.15}


def _banda(v: float, lo: float, hi: float) -> float:
    """1.0 dentro de la banda, cayendo linealmente hasta 0 a una banda de distancia."""
    if v is None:
        return 0.0
    if lo <= v <= hi:
        return 1.0
    ancho = (hi - lo) or 1.0
    d = (lo - v) if v < lo else (v - hi)
    return max(0.0, 1.0 - d / ancho)


def quality(m: Dict) -> Dict:
    """Calidad técnica 0–1 con sus cuatro componentes visibles. No es "qué tan linda es la foto":
    es qué tan bien está tomada, que es lo único que se puede medir."""
    if not m.get("ok"):
        return {"score": 0.0, "components": {}, "reason": m.get("reason")}
    exposicion = _banda(m["brightness"], *BRIGHTNESS_OK) * (
        1.0 - min(1.0, m["clipped_highlights"] * 8 + m["clipped_shadows"] * 8))
    nitidez = min(1.0, (m["sharpness"] or 0.0) / (SHARPNESS_MIN * 3))
    resolucion = min(1.0, (m["short_side"] or 0) / (MIN_SHORT_SIDE * 1.5))
    tilt = m.get("vertical_tilt_deg")
    encuadre = 1.0 if tilt is None else max(0.0, 1.0 - max(0.0, tilt - TILT_DEGREES) / 10.0)
    comps = {"exposure": round(max(0.0, exposicion), 3), "sharpness": round(nitidez, 3),
             "resolution": round(resolucion, 3), "framing": round(encuadre, 3)}
    total = sum(comps[k] * w for k, w in QUALITY_WEIGHTS.items())
    return {"score": round(total, 3), "components": comps, "weights": dict(QUALITY_WEIGHTS)}


def duplicate_groups(medios: List[Dict]) -> List[List[str]]:
    """Grupos de fotos que son la misma imagen. Devuelve ids, no conteos: el informe tiene que
    poder señalar CUÁLES, no sólo cuántas."""
    pendientes = [(m["media_id"], (m.get("analysis_obj") or {}).get("dhash")) for m in medios]
    pendientes = [(i, hsh) for i, hsh in pendientes if hsh is not None]
    grupos: List[List[str]] = []
    usados = set()
    for i, (mid, hsh) in enumerate(pendientes):
        if mid in usados:
            continue
        grupo = [mid]
        for otro, hsh2 in pendientes[i + 1:]:
            if otro not in usados and hamming(hsh, hsh2) <= DUPLICATE_HAMMING:
                grupo.append(otro)
                usados.add(otro)
        if len(grupo) > 1:
            usados.add(mid)
            grupos.append(grupo)
    return grupos
