"""E16.5 — LOCALIZACIÓN: qué región de la lámina es el espacio a evaluar.

E16.4 descubrió que el pipeline asumía una sola forma de responder esa pregunta: *buscar por OCR el
número de la unidad impreso sobre el dibujo*. Eso es cierto en un aviso que publica varias unidades
rotuladas —la lámina de GPS Property con 401, 402 y 403— y es falso en un plano de planta completa,
que no tiene ningún número interno que localizar. Preguntar "¿dónde está la unidad tal?" a un dibujo
que **es** la unidad no es una pregunta difícil: es una pregunta mal formulada.

Hay entonces dos clases de dibujo, y el motor tiene que saber cuál está mirando:

    MULTI_UNIT     varias unidades en una lámina, cada una identificada.
                   Localizar la unidad objetivo por su rótulo. Camino histórico, sin cambios.

    WHOLE_SHELL    el dibujo completo es el espacio a evaluar.
                   No hay unidad interna que encontrar; la región de interés es el dibujo mismo.

**Localización no es geometría.** Este módulo NO decide dónde están los muros, ni el núcleo, ni
qué píxeles son shell. Sólo responde *por dónde empezar a mirar*, que es lo que la segmentación
necesita para arrancar. En modo WHOLE_SHELL la región de interés es la **extensión de lo dibujado**,
no el rectángulo del archivo: una lámina trae márgenes blancos, un título y a veces una marca de
agua, y ninguno de ellos es parte del inmueble. Confundir "el dibujo completo" con "todos los píxeles
de la imagen" sería reemplazar un supuesto no genérico por otro.

Qué NO decide el modo:
- que `unit_label` sea desconocido NO implica WHOLE_SHELL. Hay láminas multiunidad cuyo rótulo
  objetivo falta en la metadata y donde igual hay que localizar una unidad concreta. La ausencia de
  un dato no es evidencia sobre la naturaleza del dibujo.
- el modo es un HECHO DE LA FUENTE (`case.json → drawing_scope`), declarado por quien conoce el
  aviso, con la misma categoría que la superficie publicada o el nombre del broker."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

#: modos de localización. El valor por defecto preserva el comportamiento histórico.
MULTI_UNIT = "multi_unit"
WHOLE_SHELL = "whole_shell"
DRAWING_SCOPES = (MULTI_UNIT, WHOLE_SHELL)
DEFAULT_SCOPE = MULTI_UNIT

#: cómo se resolvió la localización, para que aguas abajo se sepa de dónde vino.
TARGET_UNIT_BY_LABEL = "TARGET_UNIT_BY_LABEL"      # hint de OCR/VLM sobre el rótulo de la unidad
WHOLE_DRAWING_TARGET = "WHOLE_DRAWING_TARGET"      # el dibujo entero es el objetivo
ASSISTED = "ASSISTED"                              # seed_points/bbox humanos en overrides
MANUAL = "MANUAL"                                  # perímetro humano en overrides

#: procedencia de la decisión. No es lo mismo haberlo leído que haberlo declarado.
PROV_OCR_HINT = "OCR_HINT"
PROV_SOURCE_FACT = "SOURCE_FACT_WHOLE_DRAWING"
PROV_MANUAL = "MANUAL_OVERRIDE"

UNKNOWN_SCOPE = "UNKNOWN_DRAWING_SCOPE"


class LocalizationError(RuntimeError):
    """No se pudo determinar qué región de la lámina evaluar."""


@dataclass(frozen=True)
class Localization:
    """Dónde empezar a mirar, y por qué se cree eso."""
    method: str                                   # TARGET_UNIT_BY_LABEL | WHOLE_DRAWING_TARGET | ...
    provenance: str                               # OCR_HINT | SOURCE_FACT_WHOLE_DRAWING | MANUAL_OVERRIDE
    seeds: Tuple[Tuple[float, float], ...] = ()
    roi: Optional[Tuple[int, int, int, int]] = None   # x0, y0, x1, y1
    notes: str = ""

    def to_dict(self) -> dict:
        return {"method": self.method, "provenance": self.provenance,
                "seeds": [list(s) for s in self.seeds], "roi": list(self.roi) if self.roi else None,
                "notes": self.notes}


def validate_scope(scope: Optional[str]) -> str:
    s = (scope or DEFAULT_SCOPE).strip()
    if s not in DRAWING_SCOPES:
        raise LocalizationError(
            f"{UNKNOWN_SCOPE}: '{scope}'. Valores admitidos: {', '.join(DRAWING_SCOPES)}. "
            f"Es un hecho de la fuente: '{MULTI_UNIT}' si la lámina publica varias unidades "
            f"identificadas, '{WHOLE_SHELL}' si el dibujo completo es el espacio a evaluar.")
    return s


def drawing_bounds(image_bgr: np.ndarray, ink_threshold: int = 245,
                   min_ink_frac: float = 0.0005) -> Optional[Tuple[int, int, int, int]]:
    """Extensión de lo dibujado sobre la lámina, en píxeles.

    NO es geometría del inmueble: es dónde hay tinta y dónde hay papel. Se descartan las filas y
    columnas cuya proporción de píxeles no blancos es despreciable, de modo que los márgenes blancos
    queden fuera y un título suelto en una esquina no arrastre el recuadro a toda la hoja."""
    if image_bgr is None or image_bgr.size == 0:
        return None
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    ink = (gray < ink_threshold).astype(np.uint8)
    h, w = ink.shape
    rows = ink.sum(axis=1) / float(w)
    cols = ink.sum(axis=0) / float(h)
    ys = np.where(rows > min_ink_frac)[0]
    xs = np.where(cols > min_ink_frac)[0]
    if not len(ys) or not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def whole_drawing_localization(image_bgr: np.ndarray) -> Localization:
    """El dibujo completo es el objetivo: la región de interés es la extensión de lo dibujado.

    La semilla es el centro de esa región. Es la definición más simple que se sostiene sin mirar
    ningún caso concreto; si el centro cae sobre un núcleo o un vacío, eso lo descubrirá la
    segmentación y será información sobre la segmentación, no sobre la localización."""
    roi = drawing_bounds(image_bgr)
    if roi is None:
        raise LocalizationError("la lámina no contiene contenido dibujado detectable")
    x0, y0, x1, y1 = roi
    return Localization(method=WHOLE_DRAWING_TARGET, provenance=PROV_SOURCE_FACT,
                        seeds=(((x0 + x1) / 2.0, (y0 + y1) / 2.0),), roi=roi,
                        notes="el caso declara drawing_scope=whole_shell: el dibujo completo es el "
                              "espacio a evaluar, así que no se busca ningún rótulo de unidad")
