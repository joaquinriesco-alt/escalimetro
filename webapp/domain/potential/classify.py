"""E17.2 §6 — QUÉ ES CADA IMAGEN QUE BAJAMOS.

Una galería trae fotos del inmueble, a veces un plano, a veces un mapa y casi siempre algún logo
de la corredora. Mezclarlos arruina dos cosas a la vez: el logo baja el promedio de calidad
fotográfica, y el plano —que es la imagen más valiosa que puede traer un aviso— se queda sin
usar porque nadie lo reconoció.

=================================================================================================
Heurísticas, no un modelo
=================================================================================================
§6 lo autoriza explícitamente y además es lo correcto: la señal que separa un plano de una foto es
trivial de medir y no necesita aprendizaje. Un plano es tinta sobre papel: casi todo el cuadro es
blanco y casi no hay color. Una foto de interior tiene el cuadro lleno.

Medido sobre el material real de este repositorio:

    imagen                     blanco   saturación
    plano GPS 403               0.688      0.064
    plano RES                   0.772      0.002
    plano sintético             0.649      0.059
    fotos de oficina       0.000–0.243  0.059–0.150

El corte va en 0.45 de blanco con saturación baja: el margen entre 0.243 y 0.649 es amplio y no
hay que afinar nada. Como todo umbral de esta familia, está escrito y visible; si aparece un plano
sobre fondo oscuro, se va a ver en la muestra antes que en un debate.

`MAP` se clasifica **sólo por la URL**. Un mapa estático se parece demasiado a una foto aérea o a
un render como para separarlos con tres estadísticos, y adivinar mal significaría tirar una foto
buena. Lo que no se pueda distinguir queda en `OTHER`, que no se usa para nada y no hace daño.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

PHOTO = "PHOTO"
FLOORPLAN = "FLOORPLAN"
MAP = "MAP"
LOGO = "LOGO"
OTHER = "OTHER"
CLASSES = (PHOTO, FLOORPLAN, MAP, LOGO, OTHER)
CLASS_LABEL = {PHOTO: "foto", FLOORPLAN: "plano", MAP: "mapa", LOGO: "logo", OTHER: "otra"}

#: Fracción del cuadro que es papel. Medido: planos 0.649–0.772, fotos 0.000–0.243.
WHITE_MIN = 0.45
#: Saturación media por encima de la cual deja de parecer tinta sobre papel.
SAT_MAX = 0.20
#: Lado menor por debajo del cual una imagen no es material publicable: es un ícono.
LOGO_SIDE_MAX = 200
#: Un logo tiene pocos colores y mucho fondo. Se piden las dos cosas: una sola sobra.
LOGO_COLORS_MAX = 16
LOGO_WHITE_MIN = 0.55

_MAP_URL = re.compile(r"(staticmap|maps\.google|mapbox|openstreetmap|/mapa|/map[_.-])", re.I)


def features(path: str) -> Optional[Dict]:
    """Los tres estadísticos que deciden, más el tamaño. Se guardan con el medio para que la
    clasificación se pueda revisar después sin volver a abrir el archivo."""
    try:
        import cv2                                             # noqa: PLC0415
        import numpy as np                                     # noqa: PLC0415
    except ImportError:
        return None
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    q = (img // 32).reshape(-1, 3)
    return {"white_fraction": round(float((gray > 235).mean()), 4),
            "saturation": round(float(hsv[..., 1].mean() / 255), 4),
            "edge_density": round(float((cv2.Canny(gray, 80, 200) > 0).mean()), 4),
            "colors": int(len(np.unique(q, axis=0))),
            "width": int(w), "height": int(h), "short_side": int(min(w, h))}


def classify(path: str, url: str = "") -> Dict:
    """Qué es esta imagen, con la evidencia que lo sostiene."""
    if url and _MAP_URL.search(url):
        return {"kind": MAP, "why": "la dirección de la imagen la identifica como mapa",
                "features": {}}
    f = features(path)
    if f is None:
        return {"kind": OTHER, "why": "no se pudo leer la imagen", "features": {}}
    if f["short_side"] < LOGO_SIDE_MAX:
        return {"kind": LOGO, "why": f"lado menor {f['short_side']} px: es un ícono, no material "
                                     f"publicable", "features": f}
    if (f["white_fraction"] >= LOGO_WHITE_MIN and f["colors"] <= LOGO_COLORS_MAX
            and f["edge_density"] < 0.02):
        return {"kind": LOGO, "why": f"fondo plano ({f['white_fraction']}) con "
                                     f"{f['colors']} colores y casi sin trazo", "features": f}
    if f["white_fraction"] >= WHITE_MIN and f["saturation"] <= SAT_MAX:
        return {"kind": FLOORPLAN,
                "why": f"{int(f['white_fraction'] * 100)} % del cuadro es papel y la saturación "
                       f"es {f['saturation']}: es tinta sobre papel, no una foto",
                "features": f}
    return {"kind": PHOTO, "why": "el cuadro está lleno y tiene color", "features": f}
