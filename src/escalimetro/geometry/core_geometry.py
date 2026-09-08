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
from . import core_completeness as CC
from .core_components import (CONTRACT_VERSION, CoreComponentSet, InvalidCoreGeometry,
                              MultiComponentCoreError, components_from_mask, normalize_components)

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
    # E16.11 — dos preguntas distintas, dos estados distintos. `accepted` sigue significando lo que
    # significaba en E16.10 (plausibilidad) y ya no es el veredicto: el veredicto es `status`.
    plausibility_status: str = ""
    completeness_status: str = ""
    completeness_metrics: Dict = field(default_factory=dict)
    completeness_reasons: List[str] = field(default_factory=list)
    status: str = ""
    # E16.13.1 — la representación. `components` es la verdad geométrica del candidato; `ring` sólo
    # existe cuando esa verdad es UNA región.
    components: List[List[Point]] = field(default_factory=list)
    component_metrics: List[Dict] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION
    geometry_notes: str = ""

    def __post_init__(self):
        # NO se puede construir un candidato de varias regiones que además cargue "el" anillo. Es la
        # regla que impide la pérdida silenciosa que el intento anterior tenía: allí `.ring` devolvía
        # calladamente la pieza mayor y un lector de la era single-ring creía tener el núcleo entero.
        if len(self.components) > 1 and self.ring:
            raise MultiComponentCoreError(
                f"un candidato de {len(self.components)} regiones no tiene un anillo único; "
                f"los consumidores deben leer `components` o pasar por `cores_from_candidate`")

    def single_ring(self) -> List[Point]:
        """El anillo del núcleo, y sólo si el núcleo es UNA región. Si son varias, falla en vez de
        devolver una parte."""
        if len(self.components) > 1:
            raise MultiComponentCoreError(
                f"este candidato ocupa {len(self.components)} regiones: no existe 'el' anillo")
        return self.ring or (self.components[0] if self.components else [])


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


def enclosed_cell_anchors(image_bgr: np.ndarray, footprint: np.ndarray,
                          max_frac: float = ANCHOR_MAX_FRAC) -> Tuple[np.ndarray, int]:
    """Celdas interiores CERRADAS y pequeñas, dentro de la huella.

    NOMBRE CORREGIDO EN E16.11, Y EL CAMBIO IMPORTA. E16.10 llamaba a esto
    `vertical_circulation_anchors` y su docstring decía "cajas de ascensor, ductos, shafts". Eso
    afirmaba algo que el código no mide. Lo que el código mide es exactamente esto: componentes
    conectadas de espacio libre, encerradas por muro dilatado, que no son la dominante y que no
    superan `max_frac` de la huella. Una caja de ascensor produce una de estas celdas; una bodega,
    un cuarto técnico, un baño individual y un hueco de dibujo también. En el plano de desarrollo
    resultó que las mayores eran cabinas de ascensor, pero eso fue una OBSERVACIÓN sobre ese dibujo,
    no una propiedad del detector.

        LA VARIABLE DICE LO QUE SABEMOS, NO LO QUE INFERIMOS.

    Se usan como ANCLA GEOMÉTRICA: dicen "aquí hay un recinto cerrado", que es evidencia de
    construcción permanente, no de circulación vertical."""
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
    anchors, n_anchors = enclosed_cell_anchors(image_bgr, footprint, p["anchor_max_frac"])

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
                              "enclosed_cell_anchors_in_drawing": n_anchors}, False,
                             ["sin estructura permanente donde la pista dice que hay núcleo"])

    # 3. enlazar piezas separadas por vanos y pasillos, y quedarse con el cluster mayor
    r = max(3, int(max(h, w) * p["link_frac"])) | 1
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r))
    cluster = cv2.morphologyEx((seed * 255).astype(np.uint8), cv2.MORPH_CLOSE, ker)
    n, lab, st, _ = cv2.connectedComponentsWithStats((cluster > 0).astype(np.uint8), 8)
    if n <= 1:
        return CoreCandidate(np.zeros((h, w), np.uint8), [], {"enclosed_cell_anchors_in_drawing": n_anchors},
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
        return CoreCandidate(np.zeros((h, w), np.uint8), [], {"enclosed_cell_anchors_in_drawing": n_anchors},
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
        # evidencia, no veto en esta capa: cuántas celdas cerradas quedaron dentro del candidato.
        # E16.11 las usa además para evaluar COMPLETITUD, que es una pregunta distinta.
        "enclosed_cell_anchors_inside": int(cv2.connectedComponents(
            (((anchors > 0) & filled) * 255).astype(np.uint8))[0] - 1),
        "enclosed_cell_anchors_in_drawing": int(n_anchors),
    }
    eps = 0.004 * cv2.arcLength(big, True)
    ring = [(float(a[0][0]), float(a[0][1])) for a in cv2.approxPolyDP(big, eps, True)]
    return CoreCandidate((filled * 255).astype(np.uint8), ring, metrics)


# -----------------------------------------------------------------------------------------------
# CONTRATO DE ACEPTACIÓN DEL NÚCLEO (E16.10 §8, ámbitos migrados en E16.13.1)
#
# Congelado ANTES de mirar ningún caso de desarrollo. NINGÚN VALOR CAMBIA en este ciclo: lo único
# que cambia es DÓNDE se pregunta cada propiedad, y que `components_max` deja de existir.
#
#   MÉTRICA                 ÁMBITO            POR QUÉ
#   wall_fraction           PER-COMPONENT     cada región tiene que estar construida; promediar deja
#                                             que una región maciza tape una vacía
#   solidity                PER-COMPONENT     un bloque es compacto. La envolvente convexa de la
#                                             UNIÓN atraviesa la circulación entre regiones, así que
#                                             a nivel de unión mide el reparto de la planta y no la
#                                             forma del objeto  → OBSOLETA como métrica de unión
#   open_floor_invasion     PER-COMPONENT     una región que es piso ocupable no es núcleo, aunque
#                                             el promedio del conjunto la disimule
#   scope_overlap           PER-COMPONENT     RELACIÓN de cada región con el alcance semántico.
#                                             Sustituye a toda idea de "pertenencia por cercanía"
#   footprint_frac          UNION             el tamaño del núcleo es el del conjunto
#   hint_iou                UNION             la pista describe el conjunto
#   centroid_in_hint        UNION             el centro de UNA región puede caer fuera sin que el
#                                             conjunto esté mal
#   components              OBSOLETA          la cantidad de regiones es una propiedad del DIBUJO,
#                                             no del núcleo: se mide y se reporta, no veta
# -----------------------------------------------------------------------------------------------
CORE_ACCEPTANCE = {
    # --- UNIÓN ---------------------------------------------------------------------------------
    # coherencia con la pista: si la geometría no se solapa con lo que la semántica señaló, o su
    # centro cae fuera, el productor encontró OTRA cosa. Umbral bajo a propósito: la pista es un
    # recuadro grueso y el núcleo es una figura flaca; exigir más obligaría a parecerse al recuadro.
    "hint_iou_min": 0.15,
    "require_centroid_in_hint": True,
    # tamaño plausible respecto de la huella: ni un armario ni media planta
    "footprint_frac_min": 0.02,
    "footprint_frac_max": 0.35,
    # --- POR COMPONENTE ------------------------------------------------------------------------
    # estructura permanente: un núcleo está CONSTRUIDO. Una porción equivalente de piso abierto tiene
    # una fracción de muro cercana a cero.
    "wall_fraction_min": 0.12,
    # compacidad: cada región es un bloque, no una constelación de fragmentos
    "solidity_min": 0.55,
    # invasión del espacio ocupable: si la mayor parte de una región es piso abierto dominante, es
    # oficina con muros alrededor, no núcleo
    "open_floor_invasion_max": 0.30,
    # relación de cada región con el alcance que la semántica señaló
    "component_scope_overlap_min": 0.50,
}


def accept_core(metrics: Dict, contract: Optional[Dict] = None,
                component_metrics: Optional[List[Dict]] = None) -> Tuple[bool, List[str]]:
    """Evalúa el contrato en sus dos ámbitos.

    Sin `component_metrics` —un lector histórico— las invariantes por componente se evalúan sobre la
    UNIÓN, que es exactamente lo que hacía E16.10: nadie cambia de criterio en silencio."""
    c = dict(CORE_ACCEPTANCE, **(contract or {}))
    fails: List[str] = []
    if metrics.get("core_px", 0) <= 0:
        return False, ["candidato vacío"]

    # --- unión ---
    if metrics["hint_iou"] < c["hint_iou_min"]:
        fails.append(f"hint_iou={metrics['hint_iou']:.3f} < {c['hint_iou_min']}")
    if c["require_centroid_in_hint"] and not metrics["centroid_in_hint"]:
        fails.append("el centro del candidato cae fuera de la región señalada")
    f = metrics["footprint_frac"]
    if not (c["footprint_frac_min"] <= f <= c["footprint_frac_max"]):
        fails.append(f"footprint_frac={f:.3f} fuera de [{c['footprint_frac_min']}, {c['footprint_frac_max']}]")

    # --- por componente ---
    piezas = component_metrics if component_metrics else [metrics]
    for i, m in enumerate(piezas):
        et = f"componente {m.get('index', i)}"
        if m["wall_fraction"] < c["wall_fraction_min"]:
            fails.append(f"{et}: wall_fraction={m['wall_fraction']:.3f} < {c['wall_fraction_min']}: "
                         f"no hay estructura permanente suficiente")
        if m["solidity"] < c["solidity_min"]:
            fails.append(f"{et}: solidity={m['solidity']:.3f} < {c['solidity_min']}: región fragmentada")
        if m["open_floor_invasion"] > c["open_floor_invasion_max"]:
            fails.append(f"{et}: open_floor_invasion={m['open_floor_invasion']:.3f} > "
                         f"{c['open_floor_invasion_max']}: la región es mayormente piso ocupable")
        if "scope_overlap" in m and m["scope_overlap"] < c["component_scope_overlap_min"]:
            fails.append(f"{et}: scope_overlap={m['scope_overlap']:.3f} < "
                         f"{c['component_scope_overlap_min']}: la región no está donde la semántica "
                         f"señaló núcleo")
    return (not fails), fails


# -----------------------------------------------------------------------------------------------
# CAPA DE MEDICIÓN DEL CONTRATO
#
# Mide propiedades de UNA GEOMETRÍA DADA. No produce geometría: lee los mapas del productor
# (`wall_map`, `open_floor`) sin modificarlos, y por eso puede evaluar tanto lo que produjo
# `build_core` como una geometría declarada por un fixture, una anotación u otro productor.
# -----------------------------------------------------------------------------------------------
def _scope_mask(shape, footprint: np.ndarray, hint_region, margin_frac: float = SEARCH_MARGIN_FRAC):
    """El alcance semántico con el mismo margen que usa el productor para BUSCAR. Se lee la constante
    congelada; no se redefine."""
    h, w = shape[:2]
    x0, y0, x1, y1 = [int(v) for v in hint_region]
    m = int(max(h, w) * margin_frac)
    z = np.zeros((h, w), np.uint8)
    z[max(0, y0 - m):min(h, y1 + m), max(0, x0 - m):min(w, x1 + m)] = 255
    return (z > 0) & (footprint > 0)


def _geometry_metrics(mask: np.ndarray, hint_box: np.ndarray, walls: np.ndarray, piso: np.ndarray,
                      scope: np.ndarray, area_fp: float, hint) -> Dict:
    x0, y0, x1, y1 = hint
    area = float(mask.sum())
    if area <= 0:
        return {"core_px": 0}
    inter = float((mask & hint_box).sum())
    union = float((mask | hint_box).sum())
    ys, xs = np.where(mask)
    cy, cx = float(ys.mean()), float(xs.mean())
    cnts, _ = cv2.findContours((mask * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    hull = np.zeros(mask.shape[:2], np.uint8)
    cv2.fillPoly(hull, [cv2.convexHull(np.vstack(cnts))], 255)
    # el casco se mide EN PÍXELES, igual que el área: mezclarlo con el área poligonal del casco daba
    # solidez > 1 en piezas chicas
    hull_area = float((hull > 0).sum()) or area
    return {
        "core_px": int(area),
        "footprint_frac": round(area / area_fp, 6) if area_fp else 0.0,
        "hint_iou": round(inter / union, 4) if union else 0.0,
        "centroid_in_hint": bool(x0 <= cx <= x1 and y0 <= cy <= y1),
        "outside_hint_frac": round(float((mask & ~hint_box).sum()) / area, 4),
        "wall_fraction": round(float((mask & walls).sum()) / area, 4),
        "solidity": round(area / hull_area, 4),
        "open_floor_invasion": round(float((mask & piso).sum()) / area, 4),
        "scope_overlap": round(float((mask & scope).sum()) / area, 4),
    }


def component_metrics(cs: CoreComponentSet, image_bgr: np.ndarray, footprint: np.ndarray,
                      hint_region) -> Tuple[Dict, List[Dict]]:
    """Métricas de la UNIÓN y de cada componente, con las mismas fórmulas."""
    h, w = footprint.shape[:2]
    fp = footprint > 0
    area_fp = float(fp.sum())
    x0, y0, x1, y1 = [int(v) for v in hint_region]
    hint_box = np.zeros((h, w), bool)
    hint_box[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
    walls = wall_map(image_bgr) > 0
    piso = open_floor(image_bgr, footprint) > 0
    scope = _scope_mask((h, w), footprint, hint_region)
    hint = (x0, y0, x1, y1)
    union = _geometry_metrics(cs.mask > 0, hint_box, walls, piso, scope, area_fp, hint)
    per = []
    for i, ring in enumerate(cs.components):
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.array(ring, np.int32)], 255)
        d = _geometry_metrics((m > 0) & (cs.mask > 0), hint_box, walls, piso, scope, area_fp, hint)
        d["index"] = i
        per.append(d)
    return union, per


def evaluate_candidate(image_bgr: np.ndarray, footprint: np.ndarray,
                       hint_region: Tuple[float, float, float, float],
                       rings, contract: Optional[Dict] = None,
                       completeness_contract: Optional[Dict] = None,
                       anchor_max_frac: float = ANCHOR_MAX_FRAC) -> CoreCandidate:
    """Somete a las dos preguntas del contrato una geometría DECLARADA, sin pasar por el productor.

    Es la puerta que hace auditable el contrato por sí solo: las clases que interesan en este ciclo
    —dos y tres regiones legítimas, puente falso, región espuria, región diminuta, solape, región
    fuera de la huella— son propiedades de UNA GEOMETRÍA. Hacerlas depender de que el productor las
    genere fue exactamente el error del intento anterior."""
    cs = normalize_components([[(float(x), float(y)) for x, y in r] for r in rings], footprint)
    union, per = component_metrics(cs, image_bgr, footprint, hint_region)
    union.update({"components": len(cs), "component_areas_px": list(cs.areas_px),
                  "min_component_frac": round(min(cs.areas_px) / max(1.0, float((footprint > 0).sum())), 6),
                  "contract_version": CONTRACT_VERSION, "provenance": "declared"})
    cand = CoreCandidate(cs.mask, cs.components[0] if len(cs) == 1 else [], union,
                         components=cs.components, component_metrics=per, geometry_notes=cs.notes)
    ok, fails = accept_core(union, contract, per)
    cand.accepted, cand.reasons = ok, fails
    cand.plausibility_status = CC.PLAUSIBLE if ok else CC.NOT_PLAUSIBLE
    anchors, _ = enclosed_cell_anchors(image_bgr, footprint, anchor_max_frac)
    ev = CC.evaluate_completeness(cand.mask, anchors, hint_region, completeness_contract)
    cand.completeness_status, cand.completeness_metrics = ev.status, ev.metrics
    cand.completeness_reasons = ev.reasons
    cand.status = CC.overall_status(ok, ev.status)
    cand.notes = f"{cand.status} (geometría declarada, {len(cs)} región(es))"
    return cand


def core_from_hint(image_bgr: np.ndarray, footprint: np.ndarray,
                   hint_region: Tuple[float, float, float, float],
                   params: Optional[Dict] = None,
                   contract: Optional[Dict] = None,
                   completeness_contract: Optional[Dict] = None) -> CoreCandidate:
    """Produce el candidato y lo somete a las DOS preguntas: ¿parece un núcleo? ¿es el núcleo
    completo? El estado global sale de `core_completeness.overall_status`, y no hay ningún camino
    por el que "plausible" sola produzca CORE_ACCEPTED."""
    cand = build_core(image_bgr, footprint, hint_region, params)
    if not cand.metrics.get("core_px"):
        cand.plausibility_status = CC.NOT_PLAUSIBLE
        cand.completeness_status = CC.COMPLETENESS_NOT_EVALUATED
        cand.status = CC.CORE_REJECTED_IMPLAUSIBLE
        return cand
    # ADAPTADOR MECÁNICO (E16.13.1 §4): la máscara que el productor ya produjo se lleva a la
    # representación canónica. No decide nada, no reagrupa nada y no puede cambiar la geometría: las
    # regiones son las componentes conectadas que esa máscara YA tenía. El productor histórico
    # devuelve una sola, y eso está bien: lo que este ciclo prueba es que el contrato sabe
    # representar y juzgar 1..N, no que el productor sepa encontrarlas.
    cs = components_from_mask(cand.mask, footprint)
    cand.components = cs.components
    cand.geometry_notes = cs.notes
    if len(cs) > 1:
        cand.ring = []          # ver CoreCandidate.__post_init__: sin anillo único, sin vista parcial
    cand.metrics["component_areas_px"] = list(cs.areas_px)
    cand.metrics["contract_version"] = CONTRACT_VERSION
    cand.metrics["provenance"] = "producer"
    _, per = component_metrics(cs, image_bgr, footprint, hint_region)
    cand.component_metrics = per
    ok, fails = accept_core(cand.metrics, contract, per)
    cand.accepted = ok
    cand.reasons = fails
    cand.plausibility_status = CC.PLAUSIBLE if ok else CC.NOT_PLAUSIBLE

    anchors, _ = enclosed_cell_anchors(image_bgr, footprint,
                                       (params or {}).get("anchor_max_frac", ANCHOR_MAX_FRAC))
    ev = CC.evaluate_completeness(cand.mask, anchors, hint_region, completeness_contract)
    cand.completeness_status = ev.status
    cand.completeness_metrics = ev.metrics
    cand.completeness_reasons = ev.reasons
    cand.status = CC.overall_status(ok, ev.status)
    cand.notes = f"{cand.status}: plausibilidad={cand.plausibility_status}, completitud={ev.status}"
    if fails or ev.reasons:
        cand.notes += " — " + "; ".join(fails + ev.reasons)
    return cand


# -----------------------------------------------------------------------------------------------
# CONTRATO DE SALIDA: UNA entidad semántica → N entradas `Core`, con el vínculo LEGIBLE POR MÁQUINA
# -----------------------------------------------------------------------------------------------
def cores_from_candidate(cand: CoreCandidate, semantic_core_id: str = "") -> List:
    """Convierte el candidato en entradas del esquema sin perder la identidad semántica.

    El intento anterior escribía "core 2/3" en `meta.notes`. Eso es texto libre: un consumidor no
    puede distinguir UN núcleo repartido en tres regiones de TRES núcleos independientes sin parsear
    prosa. Aquí el vínculo va en un campo estructurado (`Core.group`), que sobrevive al `to_dict` y
    al `from_dict` del esquema, y la afirmación arquitectónica —cuántos núcleos hay— la hace el
    `semantic_core_id` compartido, no una nota."""
    from ..schemas.floorplate import Core, CoreGroup, Meta, Provenance, Status
    total = len(cand.components)
    gid = semantic_core_id or f"core-{abs(hash(tuple(map(tuple, cand.components[0])))) % 10**8:08d}"
    out = []
    for i, ring in enumerate(cand.components):
        m = cand.component_metrics[i] if i < len(cand.component_metrics) else {}
        out.append(Core(ring=[(float(x), float(y)) for x, y in ring], kind="core",
                        meta=Meta(confidence=0.0,
                                  provenance=Provenance.CV_HEURISTIC.value,
                                  status=(Status.INFERRED.value if cand.status == CC.CORE_ACCEPTED
                                          else Status.NEEDS_CONFIRMATION.value),
                                  notes=(f"{cand.status} · wall_fraction={m.get('wall_fraction')} · "
                                         f"solidity={m.get('solidity')}")),
                        group=CoreGroup(semantic_core_id=gid, component_index=i,
                                        component_count=total,
                                        contract_version=cand.contract_version,
                                        candidate_status=cand.status)))
    return out
