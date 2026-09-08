"""E16.10 — geometría de núcleo guiada por semántica, decidida por código determinista.

LA ARQUITECTURA QUE ESTE MÓDULO IMPLEMENTA

    pista semántica  →  reducción del espacio de búsqueda
                     →  GEOMETRÍA DETERMINISTA sobre evidencia estructural
                     →  CONTRATO DE ACEPTACIÓN que puede vetar

La pista dice *dónde mirar*. No dice dónde está el borde. El borde sale de las mismas señales que los
ciclos anteriores dejaron validadas —evidencia estructural (E16.7), muros por grosor y linealidad
(E16.8-CORE), celdas interiores cerradas, conectividad— y el resultado puede quedar FUERA del
recuadro de la pista si la estructura continúa, o MUCHO MÁS CHICO si no la hay. Las dos cosas se
miden y se reportan (`hint_iou`, `outside_hint_frac`): si el polígono coincidiera con el recuadro,
sería una copia disfrazada y el informe lo mostraría.

QUÉ ES UN NÚCLEO, OPERACIONALMENTE

Una región interior de infraestructura permanente: construida (mucho muro por unidad de superficie),
compacta, conectada, con circulación vertical adentro cuando el dibujo la deja ver, y que NO es
espacio ocupable normal. Ninguna de esas propiedades es "estar al centro" ni "ser un rectángulo".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..segmentation.structural import stroke_scale_px, structural_ink

Point = Tuple[float, float]

# --- parámetros de la construcción geométrica ---------------------------------------------------
#: margen con el que se ensancha el recuadro de la pista para BUSCAR. Existe porque una pista es
#: aproximada por definición (E16.9 midió ±15-20 px de borde declarados por el propio intérprete):
#: buscar sólo dentro del recuadro heredaría su error. Fracción del lado mayor de la imagen.
SEARCH_MARGIN_FRAC = 0.03
#: radio con el que se enlazan piezas de estructura separadas por un vano o un pasillo. Es la escala
#: a la que dos bloques de servicio se leen como un mismo núcleo. Fracción del lado mayor.
LINK_FRAC = 0.025
#: para incorporar una componente de muro completa hace falta que ESA componente esté mayormente en
#: la zona de búsqueda. Impide que un muro de fachada —que apenas roza la zona— arrastre la planta.
LINK_MIN_OVERLAP = 0.50
#: una celda interior cerrada más grande que esto no es un ducto ni una caja de ascensor: es una
#: sala. Fracción de la huella.
ANCHOR_MAX_FRAC = 0.02


@dataclass
class CoreCandidate:
    mask: np.ndarray
    ring: List[Point]
    metrics: Dict
    accepted: bool = False
    reasons: List[str] = field(default_factory=list)
    notes: str = ""


def wall_map(image_bgr: np.ndarray) -> np.ndarray:
    """Muro = trazo GRUESO y LINEAL.

    E16.7 estableció que la evidencia estructural no distingue muro de mobiliario, y que para
    preguntar *qué encierra el perímetro* esa distinción no hacía falta. Para un núcleo sí hace
    falta: un muro es un trazo que además es grueso respecto de la escala de trazo del dibujo y que
    se extiende en línea recta a lo largo de varias veces esa escala. Un mueble y una anotación no
    cumplen las dos cosas a la vez. Ambos tamaños se derivan de `stroke_scale_px`, es decir del
    tamaño de la imagen, no de un caso."""
    ink = (structural_ink(image_bgr).ink > 0).astype(np.uint8) * 255
    k = stroke_scale_px(ink.shape[:2])
    grosor = max(3, k // 4) | 1
    grueso = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grosor, grosor)))
    largo = max(9, 2 * k) | 1
    h = cv2.morphologyEx(grueso, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (largo, 1)))
    v = cv2.morphologyEx(grueso, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, largo)))
    return ((h | v) > 0).astype(np.uint8) * 255


def enclosed_cells(image_bgr: np.ndarray, footprint: np.ndarray,
                   max_frac: float = ANCHOR_MAX_FRAC) -> Tuple[np.ndarray, int]:
    """Celdas interiores CERRADAS y pequeñas: cajas de ascensor, ductos, shafts.

    Son la huella gráfica de la circulación vertical: un recinto sin puerta dibujada al piso. E16.8
    las midió y aislaron exactamente las cabinas de ascensor del plano de desarrollo. Se usan como
    ANCLA, no como núcleo: un ancla dice "aquí hay infraestructura permanente"."""
    fp = footprint > 0
    walls = wall_map(image_bgr) > 0
    k = stroke_scale_px(footprint.shape[:2])
    cerrado = cv2.dilate((walls * 255).astype(np.uint8),
                         cv2.getStructuringElement(cv2.MORPH_RECT, (k | 1, k | 1))) > 0
    libre = (fp & ~cerrado).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(libre, 8)
    if n <= 1:
        return np.zeros(footprint.shape[:2], np.uint8), 0
    dominante = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    area_fp = float(fp.sum())
    sel = [i for i in range(1, n)
           if i != dominante and st[i, cv2.CC_STAT_AREA] <= max_frac * area_fp]
    out = np.isin(lab, sel).astype(np.uint8) * 255 if sel else np.zeros(footprint.shape[:2], np.uint8)
    return out, len(sel)


def open_floor(image_bgr: np.ndarray, footprint: np.ndarray) -> np.ndarray:
    """El espacio libre DOMINANTE de la planta: el piso ocupable. Sirve para medir invasión."""
    fp = footprint > 0
    ink = structural_ink(image_bgr).ink > 0
    libre = (fp & ~ink).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(libre, 8)
    if n <= 1:
        return np.zeros(footprint.shape[:2], np.uint8)
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return ((lab == i).astype(np.uint8)) * 255


def build_core(image_bgr: np.ndarray, footprint: np.ndarray,
               hint_region: Tuple[float, float, float, float],
               params: Optional[Dict] = None) -> CoreCandidate:
    """Produce el candidato a núcleo. NO decide si es válido: eso lo hace el contrato."""
    p = {"search_margin_frac": SEARCH_MARGIN_FRAC, "link_frac": LINK_FRAC,
         "link_min_overlap": LINK_MIN_OVERLAP, "anchor_max_frac": ANCHOR_MAX_FRAC,
         **(params or {})}
    h, w = footprint.shape[:2]
    fp = footprint > 0
    area_fp = float(fp.sum())
    walls = wall_map(image_bgr) > 0
    anchors, n_anchors = enclosed_cells(image_bgr, footprint, p["anchor_max_frac"])

    # 1. la pista REDUCE el espacio de búsqueda; no recorta el resultado
    m = int(max(h, w) * p["search_margin_frac"])
    x0, y0, x1, y1 = [int(v) for v in hint_region]
    search = np.zeros((h, w), np.uint8)
    search[max(0, y0 - m):min(h, y1 + m), max(0, x0 - m):min(w, x1 + m)] = 255
    search = (search > 0) & fp

    # 2. semilla: estructura y anclas dentro de la zona de búsqueda
    seed = ((walls & search) | ((anchors > 0) & search))
    if not seed.any():
        return CoreCandidate(np.zeros((h, w), np.uint8), [],
                             {"reason": "sin estructura en la zona de búsqueda",
                              "vertical_circulation_anchors": n_anchors}, False,
                             ["sin estructura permanente donde la pista dice que hay núcleo"])

    # 3. enlazar piezas separadas por vanos y pasillos, y quedarse con el cluster mayor
    r = max(3, int(max(h, w) * p["link_frac"])) | 1
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r))
    cluster = cv2.morphologyEx((seed * 255).astype(np.uint8), cv2.MORPH_CLOSE, ker)
    n, lab, st, _ = cv2.connectedComponentsWithStats((cluster > 0).astype(np.uint8), 8)
    if n <= 1:
        return CoreCandidate(np.zeros((h, w), np.uint8), [], {"vertical_circulation_anchors": n_anchors},
                             False, ["la estructura no forma ningún cluster"])
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    cluster = (lab == i)

    # 4. la geometría SIGUE A LA ESTRUCTURA, no al recuadro: se incorporan enteras las componentes de
    #    muro que el cluster toca Y que viven mayormente en la zona de búsqueda. Un muro de fachada
    #    apenas roza esa zona y por eso no entra.
    nw, lw, sw, _ = cv2.connectedComponentsWithStats((walls * 255).astype(np.uint8), 8)
    add = []
    for c in set(np.unique(lw[cluster & walls])) - {0}:
        comp = (lw == c)
        if comp.sum() and (comp & search).sum() / comp.sum() >= p["link_min_overlap"]:
            add.append(c)
    if add:
        cluster = cluster | np.isin(lw, add)
    cluster = cv2.morphologyEx((cluster * 255).astype(np.uint8), cv2.MORPH_CLOSE, ker) > 0

    # 5. rellenar el contorno externo y devolver la franja que el cierre había engordado
    cnts, _ = cv2.findContours((cluster * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros((h, w), np.uint8)
    cv2.drawContours(filled, [max(cnts, key=cv2.contourArea)], -1, 255, cv2.FILLED)
    filled = cv2.erode(filled, ker)
    filled = (filled > 0) & fp
    # devolver la franja del enlace puede partir una región por su cintura más fina: el núcleo es UNA
    # pieza, así que se conserva la mayor y el resto se descarta explícitamente (queda medido en
    # `discarded_pieces`).
    nf, lf, sf, _ = cv2.connectedComponentsWithStats((filled * 255).astype(np.uint8), 8)
    piezas = max(0, nf - 1)
    if piezas > 1:
        j = 1 + int(np.argmax(sf[1:, cv2.CC_STAT_AREA]))
        filled = (lf == j)
    if not filled.any():
        return CoreCandidate(np.zeros((h, w), np.uint8), [], {"vertical_circulation_anchors": n_anchors},
                             False, ["el candidato desaparece al descontar el enlace morfológico"])

    # 6. métricas medidas, no estimadas
    area = float(filled.sum())
    hint_box = np.zeros((h, w), bool)
    hint_box[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
    inter = float((filled & hint_box).sum())
    union = float((filled | hint_box).sum())
    ys, xs = np.where(filled)
    cy, cx = float(ys.mean()), float(xs.mean())
    cnts2, _ = cv2.findContours((filled * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    big = max(cnts2, key=cv2.contourArea)
    hull = cv2.convexHull(big)
    hull_area = float(cv2.contourArea(hull)) or area
    piso = open_floor(image_bgr, footprint) > 0
    n_cc = cv2.connectedComponentsWithStats((filled * 255).astype(np.uint8), 8)[0] - 1
    metrics = {
        "core_px": int(area),
        "footprint_frac": round(area / area_fp, 6) if area_fp else 0.0,
        "hint_iou": round(inter / union, 4) if union else 0.0,
        "centroid_in_hint": bool(x0 <= cx <= x1 and y0 <= cy <= y1),
        "outside_hint_frac": round(float((filled & ~hint_box).sum()) / area, 4),
        "wall_fraction": round(float((filled & walls).sum()) / area, 4),
        "solidity": round(area / hull_area, 4),
        "open_floor_invasion": round(float((filled & piso).sum()) / area, 4),
        "components": int(n_cc),
        "discarded_pieces": int(piezas - 1) if piezas > 1 else 0,
        # evidencia, no veto: se registra cuántas celdas cerradas quedaron dentro. Hay dibujos que
        # no las hacen visibles, y su ausencia no prueba que no haya circulación vertical.
        "vertical_circulation_anchors": int(cv2.connectedComponents(
            (((anchors > 0) & filled) * 255).astype(np.uint8))[0] - 1),
        "anchors_in_drawing": int(n_anchors),
    }
    eps = 0.004 * cv2.arcLength(big, True)
    ring = [(float(a[0][0]), float(a[0][1])) for a in cv2.approxPolyDP(big, eps, True)]
    return CoreCandidate((filled * 255).astype(np.uint8), ring, metrics)


# -----------------------------------------------------------------------------------------------
# CONTRATO DE ACEPTACIÓN DEL NÚCLEO (E16.10 §8)
#
# Congelado ANTES de mirar ningún caso de desarrollo. Cada umbral nombra una propiedad general del
# objeto "núcleo", y cada uno se prueba por los DOS lados con fixtures sintéticos.
# -----------------------------------------------------------------------------------------------
CORE_ACCEPTANCE = {
    # coherencia con la pista: si la geometría no se solapa con lo que la semántica señaló, o su
    # centro cae fuera, el productor encontró OTRA cosa. Umbral bajo a propósito: la pista es un
    # recuadro grueso y el núcleo es una figura flaca; exigir más obligaría a parecerse al recuadro.
    "hint_iou_min": 0.15,
    "require_centroid_in_hint": True,
    # estructura permanente: un núcleo está CONSTRUIDO. Una porción equivalente de piso abierto tiene
    # una fracción de muro cercana a cero.
    "wall_fraction_min": 0.12,
    # tamaño plausible respecto de la huella: ni un armario ni media planta
    "footprint_frac_min": 0.02,
    "footprint_frac_max": 0.35,
    # compacidad: un núcleo es un bloque, no una constelación de fragmentos
    "solidity_min": 0.55,
    "components_max": 1,
    # invasión del espacio ocupable: si la mayor parte del candidato es piso abierto dominante,
    # es oficina con muros alrededor, no núcleo
    "open_floor_invasion_max": 0.30,
}


def accept_core(metrics: Dict, contract: Optional[Dict] = None) -> Tuple[bool, List[str]]:
    c = dict(CORE_ACCEPTANCE, **(contract or {}))
    fails: List[str] = []
    if metrics.get("core_px", 0) <= 0:
        return False, ["candidato vacío"]
    if metrics["hint_iou"] < c["hint_iou_min"]:
        fails.append(f"hint_iou={metrics['hint_iou']:.3f} < {c['hint_iou_min']}")
    if c["require_centroid_in_hint"] and not metrics["centroid_in_hint"]:
        fails.append("el centro del candidato cae fuera de la región señalada")
    if metrics["wall_fraction"] < c["wall_fraction_min"]:
        fails.append(f"wall_fraction={metrics['wall_fraction']:.3f} < {c['wall_fraction_min']}: "
                     f"no hay estructura permanente suficiente")
    f = metrics["footprint_frac"]
    if not (c["footprint_frac_min"] <= f <= c["footprint_frac_max"]):
        fails.append(f"footprint_frac={f:.3f} fuera de [{c['footprint_frac_min']}, {c['footprint_frac_max']}]")
    if metrics["solidity"] < c["solidity_min"]:
        fails.append(f"solidity={metrics['solidity']:.3f} < {c['solidity_min']}: candidato fragmentado")
    if metrics["components"] > c["components_max"]:
        fails.append(f"components={metrics['components']} > {c['components_max']}")
    if metrics["open_floor_invasion"] > c["open_floor_invasion_max"]:
        fails.append(f"open_floor_invasion={metrics['open_floor_invasion']:.3f} > "
                     f"{c['open_floor_invasion_max']}: el candidato es mayormente piso ocupable")
    return (not fails), fails


def core_from_hint(image_bgr: np.ndarray, footprint: np.ndarray,
                   hint_region: Tuple[float, float, float, float],
                   params: Optional[Dict] = None,
                   contract: Optional[Dict] = None) -> CoreCandidate:
    cand = build_core(image_bgr, footprint, hint_region, params)
    if not cand.metrics.get("core_px"):
        return cand
    ok, fails = accept_core(cand.metrics, contract)
    cand.accepted = ok
    cand.reasons = fails
    cand.notes = ("core aceptado" if ok else "core RECHAZADO: " + "; ".join(fails))
    return cand
