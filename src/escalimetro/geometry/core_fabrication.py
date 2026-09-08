"""E16.13.1 §11 — `fabricated_fraction`: DIAGNÓSTICO EXPERIMENTAL, fuera del contrato.

QUÉ MIDE

La fracción de un candidato que no es estructura ni está encerrada por una MISMA pieza de estructura.
Es la medida directa de cuánta superficie afirma el candidato que el dibujo no respalda: una franja de
unión inventada entre dos bloques, o una región dibujada sobre papel en blanco.

POR QUÉ NO ES PARTE DEL CONTRATO VIGENTE

Dos razones, y las dos son de honestidad, no de prudencia:

1. **No está calibrada.** El banco disponible son fixtures sintéticos. Alcanzan para mostrar que la
   métrica SEPARA —dos órdenes de magnitud entre un puente y el candidato honesto del mismo dibujo—
   y no alcanzan para fijar la frontera entre un puente fabricado y un recinto interior grande y
   legítimo. Poner 5 % sería inventar una constante.
2. **Depende de una regla de evidencia que este ciclo no puede tocar.** El enclaustramiento hay que
   evaluarlo pieza por pieza y excluyendo la ENVOLVENTE del piso: si se evalúa sobre la evidencia
   completa, el muro perimetral encierra la planta entera y respalda cualquier cosa dentro del
   edificio —medido: la métrica da 0,0000 incluso para un puente evidente—. Esa exclusión pertenece a
   la capa de evidencia estructural, que en E16.13.1 está congelada. Por eso el módulo vive aparte,
   no entra en `CORE_ACCEPTANCE`, no aparece en ningún camino de veto y su estado declarado es:

    bridge_validation = NOT_CALIBRATED

Lee `wall_map` sin modificarlo. No produce geometría y no participa en ninguna decisión.
"""
from __future__ import annotations

from typing import Dict, Optional

import cv2
import numpy as np

from ..segmentation.structural import stroke_scale_px
from .core_geometry import wall_map

BRIDGE_VALIDATION = "NOT_CALIBRATED"


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Una pieza MÁS los recintos que ella misma encierra. No es rellenar el contorno externo: un
    muro en C no se vuelve bloque macizo, y el espacio abierto que la pieza no encierra queda fuera."""
    h, w = mask.shape[:2]
    ff = np.zeros((h + 2, w + 2), np.uint8)
    fuera = (mask == 0).astype(np.uint8) * 255
    for x in range(0, w, max(1, w // 100)):
        for y in (0, h - 1):
            if fuera[y, x] == 255:
                cv2.floodFill(fuera, ff, (x, y), 128)
    for y in range(0, h, max(1, h // 100)):
        for x in (0, w - 1):
            if fuera[y, x] == 255:
                cv2.floodFill(fuera, ff, (x, y), 128)
    return (mask > 0) | (fuera == 255)


def structural_support(image_bgr: np.ndarray, footprint: np.ndarray,
                       region: Optional[np.ndarray] = None) -> np.ndarray:
    """Píxeles que SON muro o están encerrados por una misma pieza de muro, excluida la envolvente.

    La banda que define "envolvente" es de dos anchos de trazo (`stroke_scale_px`), es decir se deriva
    del tamaño del ráster y no es un número elegido. Aun así, este módulo es experimental: la regla
    pertenece a la capa de evidencia y ahí deberá discutirse."""
    fp = footprint > 0
    walls = wall_map(image_bgr) > 0
    k = stroke_scale_px(footprint.shape[:2])
    interior = cv2.erode((fp * 255).astype(np.uint8),
                         cv2.getStructuringElement(cv2.MORPH_RECT, (2 * k + 1, 2 * k + 1))) > 0
    n, lab, _, _ = cv2.connectedComponentsWithStats(((walls & fp) * 255).astype(np.uint8), 8)
    sup = np.zeros(fp.shape[:2], bool)
    for i in range(1, n):
        pieza = (lab == i)
        if region is not None and not (pieza & region).any():
            continue
        if float((pieza & interior).sum()) / float(pieza.sum()) < 0.5:   # envolvente del piso
            continue
        sup |= fill_holes((pieza * 255).astype(np.uint8))
    return (sup | (walls & fp)) & fp


def fabrication_diagnostics(image_bgr: np.ndarray, footprint: np.ndarray, cand) -> Dict:
    """Diagnóstico del candidato: fabricación de la unión y de cada región. No veta nada."""
    mask = cand.mask > 0
    area = float(mask.sum())
    if area <= 0:
        return {"bridge_validation": BRIDGE_VALIDATION, "fabricated_fraction": None}
    sop = structural_support(image_bgr, footprint, mask)
    h, w = footprint.shape[:2]
    per = []
    for ring in cand.components:
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.array(ring, np.int32)], 255)
        mb = (m > 0) & mask
        per.append(round(float((mb & ~sop).sum()) / max(1.0, float(mb.sum())), 4))
    return {"bridge_validation": BRIDGE_VALIDATION,
            "fabricated_fraction": round(float((mask & ~sop).sum()) / area, 4),
            "fabricated_fraction_per_component": per,
            "status": "EXPERIMENTAL_DIAGNOSTIC_NOT_IN_CONTRACT"}
