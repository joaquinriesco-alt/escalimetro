"""E16.7 — evidencia estructural en un dibujo de arquitectura.

DEFINICIÓN OPERACIONAL
----------------------
Hasta E16.6 el motor identificaba lo dibujado con una sola regla:

    tinta  ==  gris < 110

Esa regla no describe un dibujo: describe una *tinta concreta*. Un plano puede estar trazado en
negro sólido, en gris medio, en gris claro, o impreso con un tóner gastado, y sigue siendo el mismo
dibujo con el mismo contenido. Lo que no cambia entre esas versiones es la RELACIÓN entre el trazo y
el papel sobre el que está: el trazo es **más oscuro que el fondo que lo rodea**. Un umbral global
mide la primera propiedad —contingente— e ignora la segunda, que es la que define un dibujo.

De ahí la definición que este módulo implementa:

    EVIDENCIA ESTRUCTURAL = píxel materialmente más oscuro que el fondo LOCAL del papel,
                            medido a la escala de trazo del dibujo.

"Materialmente" y "escala de trazo" son las dos únicas magnitudes que hay que fijar, y ninguna de
las dos es una propiedad de un caso:

* `min_contrast` — cuánto más oscuro. Es una constante del MEDIO, no del dibujo: en un raster de 8
  bits, el ruido de escaneo, la compresión y el antialias mueven el gris unos pocos niveles; un
  trazo deliberado mueve decenas. 25 niveles ≈ 10 % del rango es el punto donde deja de haber duda.
  No se eligió mirando ningún plano real: se eligió por el rango del formato.
* `stroke_scale_frac` — a qué escala se mide "el fondo local". El fondo se estima cerrando la imagen
  con un elemento cuadrado más ancho que cualquier trazo y más angosto que cualquier recinto: un
  trazo desaparece bajo ese cierre (y por tanto se revela como más oscuro que su fondo), un recinto
  no. 1 % del lado mayor cumple las dos cosas en cualquier dibujo cuya escala de trazo sea la de un
  plano: a 1788 px son 18 px, a 800 px son 8 px.

QUÉ NO ES ESTO
--------------
No es un detector de muros. No distingue muro de mobiliario, de texto ni de marca de agua, y no
tiene por qué: la segmentación whole-shell no pregunta *qué es cada trazo*, pregunta *qué queda
encerrado*. Convertir esto en un clasificador de elementos sería resolver un problema mayor —
parsing CAD— para responder una pregunta menor. Lo que este módulo entrega es la capa que faltaba:
un mapa de barreras que representa lo que hay dibujado, en vez de lo que resulta ser oscuro.

BLACK-HAT Y LOS TRAZOS GRUESOS
------------------------------
`closing(gris) - gris` deja en cero el interior de una mancha oscura más ancha que el elemento
estructurante: de un bloque macizo se marca su borde, no su relleno. Para el propósito de este
módulo eso es irrelevante y conviene decirlo explícitamente: el borde de un bloque macizo es un
anillo cerrado, y la conectividad con el exterior no distingue un anillo de un disco. Lo que el
bloque encierra sigue quedando encerrado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

# Constantes del medio y de la escala de dibujo. No son constantes de ningún caso.
MIN_CONTRAST = 25          # niveles de gris (de 255) que separan trazo de ruido/antialias
STROKE_SCALE_FRAC = 0.01   # ancho del elemento estructurante como fracción del lado mayor
STROKE_SCALE_MIN = 3
STROKE_SCALE_MAX = 51


@dataclass
class StructuralInk:
    """Mapa de evidencia estructural + cómo se obtuvo (E16.7 §18: nada de parámetros ocultos)."""
    ink: np.ndarray                      # uint8 0/255
    params: Dict = field(default_factory=dict)
    diagnostics: Dict = field(default_factory=dict)


def stroke_scale_px(shape: Tuple[int, int], frac: float = STROKE_SCALE_FRAC) -> int:
    """Elemento estructurante impar derivado del tamaño de la imagen, no de un caso."""
    h, w = shape[:2]
    k = int(round(max(h, w) * float(frac)))
    k = max(STROKE_SCALE_MIN, min(STROKE_SCALE_MAX, k))
    return k if k % 2 == 1 else k + 1


def structural_ink(image, min_contrast: int = MIN_CONTRAST,
                   stroke_scale_frac: float = STROKE_SCALE_FRAC,
                   roi: Optional[Tuple[int, int, int, int]] = None) -> StructuralInk:
    """Trazo = más oscuro que el fondo local por al menos `min_contrast` niveles."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    h, w = gray.shape[:2]
    k = stroke_scale_px(gray.shape, stroke_scale_frac)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, ker)     # papel, sin los trazos
    contrast = cv2.subtract(background, gray)                     # cuánto más oscuro que su fondo
    ink = (contrast >= int(min_contrast)).astype(np.uint8) * 255

    if roi:
        x0, y0, x1, y1 = map(int, roi)
        sub = ink[y0:y1, x0:x1]
        area = max(1, (x1 - x0) * (y1 - y0))
    else:
        sub, area = ink, h * w
    diag = {
        "ink_frac_roi": round(float((sub > 0).sum()) / area, 6),
        "contrast_p99": float(np.percentile(contrast, 99)),
        "background_median": float(np.median(background)),
    }
    return StructuralInk(ink=ink,
                         params={"method": "local_contrast_blackhat",
                                 "min_contrast": int(min_contrast),
                                 "stroke_scale_frac": float(stroke_scale_frac),
                                 "stroke_scale_px": int(k)},
                         diagnostics=diag)


# ---------------------------------------------------------------------------------------------
# CONTRATO DE ACEPTACIÓN DEL MAPA DE BARRERAS (E16.7 §16)
#
# Distinto y anterior al contrato de aceptación de la MÁSCARA (E16.6). Aquí no se juzga si la huella
# resultante es plausible: se juzga si el dibujo aporta, en absoluto, una barrera con la que valga la
# pena preguntar por conectividad. Los tres criterios están declarados antes de correr ningún caso.
# ---------------------------------------------------------------------------------------------
BARRIER_ACCEPTANCE = {
    # hay dibujo, y sigue siendo mayormente papel: una hoja casi vacía o casi negra no es un plano
    "ink_frac_min": 0.002,
    "ink_frac_max": 0.60,
    # una barrera perimetral es una estructura A ESCALA DEL DIBUJO: su mayor componente conectada
    # abarca al menos media diagonal de la región de interés. Mobiliario suelto y rótulos no.
    "span_ratio_min": 0.50,
    # ni la barrera tapa la hoja entera ni el exterior alcanza todo: tiene que encerrar algo
    "outside_frac_min": 0.02,
    "outside_frac_max": 0.98,
}


def barrier_diagnostics(barrier: np.ndarray, outside: np.ndarray,
                        roi: Optional[Tuple[int, int, int, int]] = None) -> Dict:
    h, w = barrier.shape[:2]
    if roi:
        x0, y0, x1, y1 = map(int, roi)
    else:
        x0, y0, x1, y1 = 0, 0, w, h
    roi_area = max(1, (x1 - x0) * (y1 - y0))
    roi_diag = float(np.hypot(x1 - x0, y1 - y0)) or 1.0
    b = barrier[y0:y1, x0:x1]
    n, _, stats, _ = cv2.connectedComponentsWithStats((b > 0).astype(np.uint8), 8)
    if n <= 1:
        span = 0.0
    else:
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        span = float(np.hypot(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])) / roi_diag
    return {
        "barrier_frac_roi": round(float((b > 0).sum()) / roi_area, 6),
        "barrier_components": int(n - 1),
        "span_ratio": round(span, 4),
        "outside_reachable_frac_roi": round(float((outside[y0:y1, x0:x1] > 0).sum()) / roi_area, 6),
        "outside_reachable_frac_image": round(float((outside > 0).sum()) / float(h * w), 6),
    }


def barrier_accept(ink_frac: float, diag: Dict, contract: Dict = None) -> Tuple[bool, str]:
    c = dict(BARRIER_ACCEPTANCE, **(contract or {}))
    fails = []
    if not (c["ink_frac_min"] <= ink_frac <= c["ink_frac_max"]):
        fails.append(f"ink_frac={ink_frac:.4f} fuera de [{c['ink_frac_min']}, {c['ink_frac_max']}]")
    if diag["span_ratio"] < c["span_ratio_min"]:
        fails.append(f"span_ratio={diag['span_ratio']:.3f} < {c['span_ratio_min']}")
    o = diag["outside_reachable_frac_image"]
    if not (c["outside_frac_min"] <= o <= c["outside_frac_max"]):
        fails.append(f"outside_frac={o:.4f} fuera de [{c['outside_frac_min']}, {c['outside_frac_max']}]")
    return (not fails), "; ".join(fails)
