"""E16.10/E16.13 — geometría de núcleo guiada por semántica, decidida por código determinista.

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
compacta, con circulación vertical adentro cuando el dibujo la deja ver, y que NO es espacio ocupable
normal. Ninguna de esas propiedades es "estar al centro", "ser un rectángulo" NI "ser una sola pieza".

QUÉ CAMBIÓ EN E16.13, Y POR QUÉ

E16.10 codificó "un núcleo es una sola componente conectada" de dos maneras a la vez: el productor
unía piezas con un cierre morfológico de radio fijo y después se quedaba con la mayor, y el contrato
exigía `components == 1`. E16.12 midió el costo de esa afirmación: un conjunto de servicio
distribuido —bloques separados por circulación, que es como se construyen los edificios reales—
producía varias piezas correctas y el contrato las rechazaba, mientras que la única forma de cumplir
la regla era ENGORDAR la geometría hasta cruzar espacio abierto. Sobre el candidato histórico del
caso de desarrollo, el 68 % de sus píxeles no era estructura ni estaba encerrado por estructura.

    UN NÚCLEO ES UNA ENTIDAD SEMÁNTICA QUE PUEDE OCUPAR VARIAS REGIONES.
    NO SE FABRICAN PUENTES PARA SATISFACER UN TIPO DE DATO,
    NI SE RECHAZAN PIEZAS CORRECTAS POR ESTAR SEPARADAS.

El reemplazo NO es `components <= N`: mover el número no arregla nada, porque la cantidad de piezas
no es una propiedad del objeto sino del dibujo. Lo que el contrato pregunta ahora son PROPIEDADES:
cada pieza construida y relacionada con el alcance semántico (PER-COMPONENT), el conjunto plausible
respecto de la huella y de la pista (UNION), y la completitud sobre la UNIÓN (E16.11, sin cambios).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..segmentation.structural import stroke_scale_px, structural_ink
from . import core_completeness as CC
from .core_components import (CONTRACT_VERSION, CoreComponentSet, InvalidCoreGeometry,
                              NOISE_COMPONENT_MIN_FRAC, components_from_mask)

Point = Tuple[float, float]

# --- parámetros de la construcción geométrica ---------------------------------------------------
#: margen con el que se ensancha el recuadro de la pista para BUSCAR. Existe porque una pista es
#: aproximada por definición (E16.9 midió ±15-20 px de borde declarados por el propio intérprete):
#: buscar sólo dentro del recuadro heredaría su error. Fracción del lado mayor de la imagen.
SEARCH_MARGIN_FRAC = 0.03
#: para incorporar una pieza estructural completa hace falta que ESA pieza esté mayormente en la zona
#: de búsqueda. Impide que un muro de fachada —que apenas roza la zona— arrastre la planta.
LINK_MIN_OVERLAP = 0.50
#: una celda interior cerrada más grande que esto no es un ducto ni una caja de ascensor: es una
#: sala. Fracción de la huella.
ANCHOR_MAX_FRAC = 0.02
#: una pieza con menos de esta fracción de la masa estructural de la pieza principal no es un bloque
#: par del conjunto: es un recinto ordinario que la pista abarcó de más. Criterio de MASA, no de
#: distancia — misma razón que en E16.11.
COMPONENT_MIN_MASS_RATIO = 0.15
#: una pieza estructural cuya masa no está mayormente en el INTERIOR de la huella es la envolvente
#: del piso, no una pieza de núcleo. El interior se define descontando una banda de dos anchos de
#: trazo desde el borde: es la escala a la que un muro perimetral está dibujado.
INTERIOR_MIN_FRAC = 0.50

#: parámetro OBSOLETO desde E16.13. Se conserva nombrado, y nombrado como obsoleto, porque su valor
#: (2,5 % del lado mayor) es exactamente lo que fabricaba los puentes que E16.12 midió. Ya no lo lee
#: nadie; está aquí para que quien busque `LINK_FRAC` en el historial encuentre la explicación y no
#: lo reintroduzca.
LINK_FRAC_OBSOLETE_E16_13 = 0.025


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
    # E16.13 — la representación canónica. `components` es la verdad geométrica; `ring` es la vista
    # de compatibilidad (la pieza MAYOR) que conservan los lectores de la era single-ring.
    components: List[List[Point]] = field(default_factory=list)
    component_metrics: List[Dict] = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION


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
    un cuarto técnico, un baño individual y un hueco de dibujo también.

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


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Una pieza estructural MÁS los recintos que ella misma encierra.

    No es un relleno del contorno externo: un hueco se rellena sólo si está efectivamente encerrado
    por la pieza. Un muro en forma de C no se convierte en bloque macizo al pasar por aquí, y el
    espacio abierto que la pieza no encierra queda fuera. Esa diferencia es lo que separa "seguir la
    estructura" de "inflar hasta que quede bonito"."""
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


def build_core(image_bgr: np.ndarray, footprint: np.ndarray,
               hint_region: Tuple[float, float, float, float],
               params: Optional[Dict] = None) -> CoreCandidate:
    """Produce el candidato a núcleo. NO decide si es válido: eso lo hace el contrato.

    CÓMO SE RECORREN LAS PIEZAS, Y POR QUÉ CAMBIÓ EN E16.13.

    El productor de E16.10 unía las piezas con un CIERRE MORFOLÓGICO de radio fijo y después se
    quedaba con la componente conectada MAYOR. Esa combinación tiene dos defectos simétricos:

      * dos bloques de servicio genuinamente pertenecientes al mismo núcleo, pero separados en el
        papel por un pasillo más ancho que ese radio, NO se unen — y el segundo se descarta en
        silencio, que es el falso positivo de completitud que E16.11 detectó;
      * al revés, un radio generoso ENGORDA la estructura hasta cruzar espacio abierto y fabrica una
        franja que el dibujo no tiene.

    El radio decide, y el radio no sabe nada de arquitectura. Se reemplaza por lo único que sí sabe:
    la evidencia. Las piezas se recorren por CONECTIVIDAD ESTRUCTURAL —muros y celdas cerradas
    conectados entre sí— y no por vecindad. Lo único que se cierra es una holgura menor que el ancho
    de trazo del dibujo: un hueco de dos píxeles en una línea de nueve es un artefacto del raster, no
    una separación arquitectónica.

    Y cuando la evidencia dice que hay más de una pieza separada, el productor DEVUELVE más de una
    pieza."""
    p = {"search_margin_frac": SEARCH_MARGIN_FRAC, "link_min_overlap": LINK_MIN_OVERLAP,
         "anchor_max_frac": ANCHOR_MAX_FRAC, "component_min_mass_ratio": COMPONENT_MIN_MASS_RATIO,
         "noise_min_frac": NOISE_COMPONENT_MIN_FRAC, "interior_min_frac": INTERIOR_MIN_FRAC,
         **(params or {})}
    h, w = footprint.shape[:2]
    fp = footprint > 0
    area_fp = float(fp.sum())
    walls = wall_map(image_bgr) > 0
    anchors, n_anchors = enclosed_cell_anchors(image_bgr, footprint, p["anchor_max_frac"])
    vacio = np.zeros((h, w), np.uint8)
    base = {"enclosed_cell_anchors_in_drawing": int(n_anchors)}

    # 1. la pista REDUCE el espacio de búsqueda; no recorta el resultado
    m = int(max(h, w) * p["search_margin_frac"])
    x0, y0, x1, y1 = [int(v) for v in hint_region]
    search = np.zeros((h, w), np.uint8)
    search[max(0, y0 - m):min(h, y1 + m), max(0, x0 - m):min(w, x1 + m)] = 255
    search = (search > 0) & fp

    # 2. evidencia estructural de una PIEZA de núcleo: MURO. Las celdas cerradas siguen siendo
    #    evidencia —de enclaustramiento y de completitud (E16.11)— pero no fundan una pieza por sí
    #    solas: un recinto sin muro propio no es construcción permanente, y una letra de marca de
    #    agua encierra una celda igual que un ducto. Los recintos que un muro encierra se recuperan
    #    igual en el paso 7, porque están dentro de la pieza que los encierra.
    estructura = walls & fp
    if not (estructura & search).any():
        return CoreCandidate(vacio, [], base, False,
                             ["sin estructura permanente donde la pista dice que hay núcleo"])

    # 3. reparación de raster, NO enlace: se cierra una holgura menor que el ancho de trazo
    k = stroke_scale_px(footprint.shape[:2])
    heal = max(3, k // 3) | 1
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (heal, heal))
    sana = cv2.morphologyEx((estructura * 255).astype(np.uint8), cv2.MORPH_CLOSE, ker) > 0

    # 4. piezas = componentes conectadas de la evidencia DENTRO de la zona de búsqueda. Se recorta
    #    antes de etiquetar, no después, y la razón es una falla medida: el mobiliario denso llega a
    #    tocar a la vez el núcleo y la fachada, de modo que sin recortar TODA la planta queda en una
    #    sola pieza que después se descarta entera por no vivir dentro de la zona. Recortar primero
    #    conserva la pieza; el paso 5 le devuelve lo que la zona le cortó.
    n, lab, st, _ = cv2.connectedComponentsWithStats(((sana & search) * 255).astype(np.uint8), 8)
    if n <= 1:
        return CoreCandidate(vacio, [], base, False, ["la evidencia estructural no forma piezas"])

    # 5. cada pieza recupera ENTERAS las componentes estructurales que toca y que viven mayormente
    #    en la zona de búsqueda: así el borde lo pone la estructura y no el recuadro de la pista, y
    #    el resultado puede salirse del recuadro. Dos exclusiones, cada una por su razón:
    #      * un muro de fachada apenas roza la zona de búsqueda y por eso no se incorpora, aunque
    #        toque el núcleo;
    #      * la ENVOLVENTE del piso —el muro perimetral— sí puede vivir entera dentro de una pista
    #        floja, y rellenar los recintos que encierra convertiría la planta completa en núcleo.
    #        El perímetro ya está representado por `Perimeter`; un núcleo es interior por definición.
    interior = cv2.erode((fp * 255).astype(np.uint8),
                         cv2.getStructuringElement(cv2.MORPH_RECT, (2 * k + 1, 2 * k + 1))) > 0
    nf, lf, sf, _ = cv2.connectedComponentsWithStats((sana * 255).astype(np.uint8), 8)
    ampliables, envolventes = {}, 0
    for j in range(1, nf):
        comp = (lf == j)
        m_comp = float(comp.sum())
        if float((comp & search).sum()) / m_comp < p["link_min_overlap"]:
            continue
        if float((comp & interior).sum()) / m_comp < p["interior_min_frac"]:
            envolventes += 1
            continue
        ampliables[j] = comp

    candidatas = []
    for i in range(1, n):
        pieza = (lab == i)
        for j in set(np.unique(lf[pieza])) - {0}:
            if j in ampliables:
                pieza = pieza | ampliables[j]
        candidatas.append((int((pieza & estructura).sum()), pieza))
    if not candidatas:
        return CoreCandidate(vacio, [], base, False,
                             ["ninguna pieza estructural vive dentro de la zona señalada"])

    # 6. filtro por MASA ESTRUCTURAL RELATIVA respecto de la pieza principal
    mayor = max(c[0] for c in candidatas)
    elegidas = [c for c in candidatas if c[0] >= p["component_min_mass_ratio"] * mayor]
    descartadas = len(candidatas) - len(elegidas)

    # 7. cada pieza aporta su propia masa MÁS los recintos que ella misma encierra
    filled = np.zeros((h, w), bool)
    for _, pieza in elegidas:
        filled |= fill_holes((pieza * 255).astype(np.uint8))
    filled &= fp
    if not filled.any():
        return CoreCandidate(vacio, [], base, False,
                             ["el candidato queda vacío al recortarlo a la huella"])

    # 8. REPRESENTACIÓN CANÓNICA: 1..N componentes, ruido descartado y contado, solapes fusionados
    try:
        cs = components_from_mask((filled * 255).astype(np.uint8), footprint, p["noise_min_frac"])
    except InvalidCoreGeometry as e:
        return CoreCandidate(vacio, [], dict(base, invalid_geometry=str(e)), False,
                             [f"geometría no representable: {e}"])
    filled = cs.mask > 0
    area = float(filled.sum())

    # 9. métricas medidas, no estimadas
    hint_box = np.zeros((h, w), bool)
    hint_box[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
    piso = open_floor(image_bgr, footprint) > 0
    metrics = _union_metrics(filled, hint_box, walls, piso, search, area_fp, (x0, y0, x1, y1))
    metrics.update({
        "components": len(cs),
        "discarded_pieces": int(descartadas),
        "envelope_pieces_excluded": int(envolventes),
        "structural_pieces_kept": int(len(cs)),
        "normalized_away": int(cs.normalized_away),
        "merged_overlaps": int(cs.merged_overlaps),
        "enclosed_cell_anchors_inside": int(cv2.connectedComponents(
            (((anchors > 0) & filled) * 255).astype(np.uint8))[0] - 1),
        "enclosed_cell_anchors_in_drawing": int(n_anchors),
        "contract_version": CONTRACT_VERSION,
    })
    per = _component_metrics(cs, hint_box, walls, piso, search, area_fp, (x0, y0, x1, y1))
    soporte = structural_support(image_bgr, footprint, filled)
    metrics["fabricated_fraction"] = round(float((filled & ~soporte).sum()) / area, 4)
    for m, ring in zip(per, cs.components):
        mm = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mm, [np.array(ring, np.int32)], 255)
        mb = (mm > 0) & (cs.mask > 0)
        m["fabricated_fraction"] = round(float((mb & ~soporte).sum()) / max(1.0, float(mb.sum())), 4)
    # `bridge_validation` NO es un veredicto. E16.13 §11: la métrica está medida y su umbral NO está
    # calibrado — el banco disponible tiene ocho fixtures sintéticos y dos dibujos de desarrollo, que
    # no bastan para separar "puente fabricado" de "recinto interior legítimo grande" sin inventar un
    # número. Poner 5 % aquí sería exactamente el tipo de constante que este proyecto persigue.
    metrics["bridge_validation"] = "NOT_CALIBRATED"

    return CoreCandidate(cs.mask, cs.ring, metrics, components=cs.components, component_metrics=per)


def structural_support(image_bgr: np.ndarray, footprint: np.ndarray,
                       region: Optional[np.ndarray] = None) -> np.ndarray:
    """Los píxeles del dibujo que SON estructura o están encerrados POR UNA MISMA PIEZA de estructura.

    Es el referente contra el que se mide `fabricated_fraction`: lo que un candidato ocupe fuera de
    aquí es superficie que el dibujo no respalda.

    El enclaustramiento se evalúa PIEZA POR PIEZA, y esa decisión es la que da sentido a la medida.
    Evaluarlo sobre la evidencia completa haría que el muro perimetral —que encierra la planta
    entera— respaldara cualquier cosa dentro del edificio, y la métrica valdría cero siempre. Se
    midió: con enclaustramiento conjunto, un candidato que cruza piso abierto entre dos bloques da
    fabricación 0,000. Por la misma razón la envolvente del piso no participa: el perímetro ya está
    representado por `Perimeter` y no es evidencia de núcleo."""
    fp = footprint > 0
    walls = wall_map(image_bgr) > 0
    k = stroke_scale_px(footprint.shape[:2])
    heal = max(3, k // 3) | 1
    sana = cv2.morphologyEx(((walls & fp) * 255).astype(np.uint8), cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (heal, heal))) > 0
    interior = cv2.erode((fp * 255).astype(np.uint8),
                         cv2.getStructuringElement(cv2.MORPH_RECT, (2 * k + 1, 2 * k + 1))) > 0
    n, lab, _, _ = cv2.connectedComponentsWithStats((sana * 255).astype(np.uint8), 8)
    sup = np.zeros(fp.shape[:2], bool)
    for i in range(1, n):
        pieza = (lab == i)
        if region is not None and not (pieza & region).any():
            continue
        if float((pieza & interior).sum()) / float(pieza.sum()) < INTERIOR_MIN_FRAC:
            continue
        sup |= fill_holes((pieza * 255).astype(np.uint8))
    return (sup | (walls & fp)) & fp


def _geom(mask: np.ndarray, hint_box: np.ndarray, walls: np.ndarray, piso: np.ndarray,
          search: np.ndarray, area_fp: float, hint: Tuple[int, int, int, int]) -> Dict:
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
    # el casco se mide EN PÍXELES, igual que el área: mezclar el área poligonal del casco con el
    # conteo de píxeles de la máscara daba solidez > 1 en piezas chicas
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
        "scope_overlap": round(float((mask & search).sum()) / area, 4),
    }


def _union_metrics(mask, hint_box, walls, piso, search, area_fp, hint) -> Dict:
    return _geom(mask, hint_box, walls, piso, search, area_fp, hint)


def _component_metrics(cs: CoreComponentSet, hint_box, walls, piso, search, area_fp, hint) -> List[Dict]:
    out = []
    h, w = cs.mask.shape[:2]
    for idx, ring in enumerate(cs.components):
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.array(ring, np.int32)], 255)
        mb = (m > 0) & (cs.mask > 0)
        d = _geom(mb, hint_box, walls, piso, search, area_fp, hint)
        d["index"] = idx
        out.append(d)
    return out


# -----------------------------------------------------------------------------------------------
# CONTRATO DE ACEPTACIÓN DEL NÚCLEO (E16.10 §8, migrado en E16.13 §13)
#
# Cada umbral nombra una propiedad general del objeto "núcleo", y cada uno se prueba por los DOS
# lados con fixtures sintéticos. Lo que E16.13 cambia es DÓNDE se evalúa cada propiedad:
#
#   MÉTRICA                 ÁMBITO E16.13     POR QUÉ
#   wall_fraction           PER-COMPONENT     cada pieza tiene que estar construida; promediar sobre
#                                             la unión deja que una pieza maciza tape una pieza vacía
#   solidity                PER-COMPONENT     un bloque es compacto; la envolvente convexa de la
#                                             UNIÓN atraviesa la circulación entre bloques, así que
#                                             la solidez de la unión mide el reparto de la planta y
#                                             no el objeto  → OBSOLETA a nivel de unión
#   open_floor_invasion     PER-COMPONENT     una pieza que es mayormente piso ocupable no es núcleo,
#                                             aunque el promedio del conjunto la disimule
#   scope_overlap           PER-COMPONENT     RELACIÓN con el alcance semántico: cada pieza tiene que
#                                             estar donde la semántica dijo. Sustituye a la idea de
#                                             "pertenencia por cercanía", que este ciclo prohíbe
#   footprint_frac          UNION             el tamaño del núcleo es el del conjunto, no el de una
#                                             pieza; una pieza chica es legítima
#   hint_iou                UNION             la pista describe el conjunto
#   centroid_in_hint        UNION             ídem; el centro de UNA pieza puede caer fuera sin que
#                                             el conjunto esté mal
#   components              OBSOLETA          la cantidad de piezas es una propiedad del DIBUJO, no
#                                             del núcleo. Se mide y se reporta; no veta
#   fabricated_fraction     MEDIDA, NO VETA   umbral no calibrado (§11): `bridge_validation`
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
    # compacidad: cada pieza es un bloque, no una constelación de fragmentos
    "solidity_min": 0.55,
    # invasión del espacio ocupable: si la mayor parte de una pieza es piso abierto dominante, es
    # oficina con muros alrededor, no núcleo
    "open_floor_invasion_max": 0.30,
    # relación de cada pieza con el alcance que la semántica señaló
    "component_scope_overlap_min": 0.50,
}


def accept_core(metrics: Dict, contract: Optional[Dict] = None,
                component_metrics: Optional[List[Dict]] = None) -> Tuple[bool, List[str]]:
    """Evalúa el contrato en sus dos ámbitos. Sin `component_metrics` —lectores históricos— las
    invariantes por componente se evalúan sobre la unión, que es exactamente lo que hacía E16.10."""
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
            fails.append(f"{et}: solidity={m['solidity']:.3f} < {c['solidity_min']}: pieza fragmentada")
        if m["open_floor_invasion"] > c["open_floor_invasion_max"]:
            fails.append(f"{et}: open_floor_invasion={m['open_floor_invasion']:.3f} > "
                         f"{c['open_floor_invasion_max']}: la pieza es mayormente piso ocupable")
        if "scope_overlap" in m and m["scope_overlap"] < c["component_scope_overlap_min"]:
            fails.append(f"{et}: scope_overlap={m['scope_overlap']:.3f} < "
                         f"{c['component_scope_overlap_min']}: la pieza no está donde la semántica "
                         f"señaló núcleo")
    return (not fails), fails


def core_from_hint(image_bgr: np.ndarray, footprint: np.ndarray,
                   hint_region: Tuple[float, float, float, float],
                   params: Optional[Dict] = None,
                   contract: Optional[Dict] = None,
                   completeness_contract: Optional[Dict] = None) -> CoreCandidate:
    """Produce el candidato y lo somete a las DOS preguntas: ¿parece un núcleo? ¿es el núcleo
    completo? El estado global sale de `core_completeness.overall_status`, y no hay ningún camino
    por el que "plausible" sola produzca CORE_ACCEPTED. La completitud se evalúa sobre la UNIÓN de
    componentes, que es la entidad de la que la pregunta habla."""
    cand = build_core(image_bgr, footprint, hint_region, params)
    if not cand.metrics.get("core_px"):
        cand.plausibility_status = CC.NOT_PLAUSIBLE
        cand.completeness_status = CC.COMPLETENESS_NOT_EVALUATED
        cand.status = CC.CORE_REJECTED_IMPLAUSIBLE
        return cand
    ok, fails = accept_core(cand.metrics, contract, cand.component_metrics)
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
    cand.notes = (f"{cand.status}: plausibilidad={cand.plausibility_status}, completitud={ev.status}, "
                  f"componentes={cand.metrics.get('components')}")
    if fails or ev.reasons:
        cand.notes += " — " + "; ".join(fails + ev.reasons)
    return cand


def evaluate_candidate(image_bgr: np.ndarray, footprint: np.ndarray,
                       hint_region: Tuple[float, float, float, float],
                       rings, params: Optional[Dict] = None,
                       contract: Optional[Dict] = None,
                       completeness_contract: Optional[Dict] = None) -> CoreCandidate:
    """Somete a las mismas dos preguntas un candidato DECLARADO, sin pasar por el productor.

    Existe porque las clases de E16.13 que interesan —el puente fabricado, la pieza espuria, la
    esquirla de ruido, el solape, la pieza fuera de la huella— son propiedades de UNA GEOMETRÍA, y
    hacerlas depender del productor convertiría un fallo de producción en un falso fallo de contrato.
    Es también la puerta por la que entra una geometría de núcleo de otra procedencia (una anotación
    manual, otro productor) sin duplicar el juez."""
    from .core_components import normalize_components
    p = {"search_margin_frac": SEARCH_MARGIN_FRAC, "anchor_max_frac": ANCHOR_MAX_FRAC, **(params or {})}
    h, w = footprint.shape[:2]
    fp = footprint > 0
    area_fp = float(fp.sum())
    cs = normalize_components([[(float(x), float(y)) for x, y in r] for r in rings], footprint,
                              p.get("noise_min_frac", NOISE_COMPONENT_MIN_FRAC))
    x0, y0, x1, y1 = [int(v) for v in hint_region]
    m = int(max(h, w) * p["search_margin_frac"])
    search = np.zeros((h, w), np.uint8)
    search[max(0, y0 - m):min(h, y1 + m), max(0, x0 - m):min(w, x1 + m)] = 255
    search = (search > 0) & fp
    hint_box = np.zeros((h, w), bool)
    hint_box[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True
    walls = wall_map(image_bgr) > 0
    piso = open_floor(image_bgr, footprint) > 0
    anchors, n_anchors = enclosed_cell_anchors(image_bgr, footprint, p["anchor_max_frac"])
    mask = cs.mask > 0
    soporte = structural_support(image_bgr, footprint, mask)
    area = float(mask.sum())

    metrics = _union_metrics(mask, hint_box, walls, piso, search, area_fp, (x0, y0, x1, y1))
    metrics.update({
        "components": len(cs), "normalized_away": int(cs.normalized_away),
        "merged_overlaps": int(cs.merged_overlaps),
        "fabricated_fraction": round(float((mask & ~soporte).sum()) / area, 4) if area else 0.0,
        "bridge_validation": "NOT_CALIBRATED",
        "enclosed_cell_anchors_in_drawing": int(n_anchors),
        "enclosed_cell_anchors_inside": int(cv2.connectedComponents(
            (((anchors > 0) & mask) * 255).astype(np.uint8))[0] - 1),
        "contract_version": CONTRACT_VERSION,
        "provenance": "declared",
    })
    per = _component_metrics(cs, hint_box, walls, piso, search, area_fp, (x0, y0, x1, y1))
    for d, ring in zip(per, cs.components):
        mm = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mm, [np.array(ring, np.int32)], 255)
        mb = (mm > 0) & mask
        d["fabricated_fraction"] = round(float((mb & ~soporte).sum()) / max(1.0, float(mb.sum())), 4)

    cand = CoreCandidate(cs.mask, cs.ring, metrics, components=cs.components, component_metrics=per)
    ok, fails = accept_core(metrics, contract, per)
    cand.accepted, cand.reasons = ok, fails
    cand.plausibility_status = CC.PLAUSIBLE if ok else CC.NOT_PLAUSIBLE
    ev = CC.evaluate_completeness(cand.mask, anchors, hint_region, completeness_contract)
    cand.completeness_status, cand.completeness_metrics = ev.status, ev.metrics
    cand.completeness_reasons = ev.reasons
    cand.status = CC.overall_status(ok, ev.status)
    cand.notes = f"{cand.status} (candidato declarado, {len(cs)} pieza(s))"
    return cand


def cores_from_candidate(cand: CoreCandidate) -> List:
    """UNA entidad semántica de núcleo → N entradas `Core` del esquema de salida (E16.13 §17).

    El esquema ya era `List[Core]` y el solver ya hacía `unary_union`, así que aguas abajo no cambia
    nada; lo que cambiaba era que el productor no podía llenar esa lista con más de una región. Cada
    entrada declara su procedencia y su lugar dentro del conjunto —`core 2/3`— para que un lector no
    confunda N regiones de un núcleo con N núcleos, que es una afirmación arquitectónica distinta y
    que este motor no hace."""
    from ..schemas.floorplate import Core, Meta, Provenance, Status
    total = len(cand.components)
    out = []
    for i, ring in enumerate(cand.components):
        m = cand.component_metrics[i] if i < len(cand.component_metrics) else {}
        out.append(Core(ring=[(float(x), float(y)) for x, y in ring], kind="core",
                        meta=Meta(confidence=0.0,
                                  provenance=Provenance.CV_HEURISTIC.value,
                                  status=(Status.INFERRED.value if cand.status == CC.CORE_ACCEPTED
                                          else Status.NEEDS_CONFIRMATION.value),
                                  notes=(f"core {i + 1}/{total} · {cand.contract_version} · "
                                         f"{cand.status} · wall_fraction="
                                         f"{m.get('wall_fraction')} · fabricated_fraction="
                                         f"{m.get('fabricated_fraction')} · bridge_validation="
                                         f"{cand.metrics.get('bridge_validation')}"))))
    return out
