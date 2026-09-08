"""E16.14 — el productor propone 1..N regiones. Descubrir, seleccionar, devolver.

TRES RESPONSABILIDADES QUE NO SE MEZCLAN

    DISCOVERY   qué piezas estructurales existen             (evidencia congelada, sin decidir nada)
    SELECTION   cuáles pertenecen a la entidad semántica     (por evidencia, no por tamaño ni cercanía)
    OUTPUT      devolver esas piezas SIN inventar conexión   (nunca un puente por espacio abierto)

QUÉ SE ELIMINA DEL PRODUCTOR ANTERIOR, Y POR QUÉ

El productor de E16.10 perdía información en tres puntos, todos medidos:

  1. `MORPH_CLOSE` de radio fijo sobre la evidencia: fabrica una franja de unión donde el dibujo
     tiene circulación. Es geometría inventada para satisfacer un tipo de dato.
  2. `cluster = (lab == mayor)`: de N piezas estructurales queda UNA, elegida por tamaño.
  3. `drawContours(max(cnts))` + quedarse otra vez con la pieza mayor: segunda pérdida, y el relleno
     del contorno externo se traga el espacio que ese contorno rodea sin que nadie lo encierre.

Ninguna de las tres sobrevive. "La componente mayor es el núcleo" queda descartado como principio:
una pieza grande puede ser fachada, mobiliario encadenado, perímetro, ruido, o sólo una PARTE del
núcleo. Y el extremo contrario —"tomar todas las piezas del alcance"— es igual de falso: convertiría
la pista en geometría.

EL CRITERIO DE SELECCIÓN: RECINTO CERRADO DENTRO DE LA PIEZA

Una pieza estructural entra al núcleo si cumple las tres a la vez:

    (i)   es INTERIOR: no es la envolvente del piso, que ya representa `Perimeter`;
    (ii)  vive mayormente dentro del ALCANCE que la pista señaló (misma constante que usaba el
          productor anterior para incorporar muros: `LINK_MIN_OVERLAP`);
    (iii) ENCIERRA al menos una celda cerrada SIGNIFICATIVA (`enclosed_cell_anchors`, semántica de
          E16.11: evidencia geométrica de recinto permanente, NO prueba de circulación vertical).

"Significativa" no es un número nuevo: es la definición ya congelada en E16.11 —área de al menos
`significant_min_ratio` veces la mayor celda cerrada DENTRO DEL ALCANCE—. Se reutiliza tal cual, sin
tocarla, porque inventar aquí un tamaño mínimo propio sería agregar una constante sin calibrar. Y
hace falta: a la escala de estas láminas, el mapa de muros congelado admite trazo de mobiliario de
3 px (medido), y un rectángulo de mobiliario ENCIERRA una celda igual que un ducto. Lo que las
separa no es el grosor —esa señal está agotada— sino la masa del recinto respecto del mayor del
alcance.

Por qué (iii) y no otra cosa: es la única señal disponible que distingue "bloque de servicio" de
"tabique, mueble o anotación" sin recurrir a tamaño ni a distancia. Un mueble no encierra un recinto;
una letra de marca de agua no encierra un recinto a escala de celda; un bloque con cabinas, ductos o
baños individuales, sí. La celda ordinaria de una OFICINA queda excluida por la propia definición
congelada de ancla, que descarta las celdas mayores que `ANCHOR_MAX_FRAC` de la huella: una sala no
es un ancla.

    LA PROXIMIDAD NO DEFINE PERTENENCIA. No hay ninguna distancia en este módulo.

LO QUE ESTE PRODUCTOR NO HACE

No itera contra el contrato. Propone una vez y no vuelve a mirar el veredicto: no existe ningún
"agregar piezas hasta que la completitud suba". No mide `fabricated_fraction` ni la optimiza. No toca
la evidencia estructural: `wall_map`, `enclosed_cell_anchors` y `structural_ink` se usan tal como
están congelados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..segmentation.structural import stroke_scale_px
from .core_completeness import COMPLETENESS_CONTRACT

PRODUCER_VERSION = "core-producer/2.0.0"    # 1.x = una sola región por selección de tamaño


@dataclass
class ProducerTrace:
    """Qué se descubrió, qué se seleccionó y POR QUÉ se descartó lo demás. Es la traza que permite
    auditar precisión y recall sin abrir el algoritmo."""
    discovered: int = 0
    selected: int = 0
    rejected: List[Dict] = field(default_factory=list)
    anchors_in_scope: int = 0
    significant_anchors: int = 0
    notes: str = ""


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Una pieza MÁS los recintos que ella misma encierra.

    No es rellenar el contorno externo —ese fue el tercer punto de pérdida del productor anterior—:
    un hueco se rellena sólo si está efectivamente encerrado por la pieza, así que un muro en C sigue
    siendo un muro en C y el espacio abierto que la pieza no encierra queda fuera."""
    h, w = mask.shape[:2]
    ff = np.zeros((h + 2, w + 2), np.uint8)
    fuera = (mask == 0).astype(np.uint8) * 255
    for x in range(0, w, max(1, w // 120)):
        for y in (0, h - 1):
            if fuera[y, x] == 255:
                cv2.floodFill(fuera, ff, (x, y), 128)
    for y in range(0, h, max(1, h // 120)):
        for x in (0, w - 1):
            if fuera[y, x] == 255:
                cv2.floodFill(fuera, ff, (x, y), 128)
    return (mask > 0) | (fuera == 255)


def discover(walls: np.ndarray, footprint: np.ndarray) -> Tuple[int, np.ndarray]:
    """DISCOVERY — las piezas estructurales que el dibujo tiene, sin decidir nada.

    La conectividad la define el dibujo: componentes conectadas del mapa de muros dentro de la huella.

    Con UNA reparación de ráster, y sólo una: el mapa de muros se construye abriendo la tinta con un
    elemento de tamaño `max(3, k//4)` —el criterio de grosor de E16.7/E16.8-CORE—, y esa apertura le
    come las esquinas al trazo, de modo que un rectángulo de muro llega aquí partido en cuatro
    segmentos que no se tocan. Se cierra con EL MISMO elemento: devuelve exactamente lo que la
    apertura quitó y no alcanza más lejos que el propio ancho de trazo. No es enlace —no puede cruzar
    un pasillo, ni un vano, ni acercar dos bloques— y por eso no fabrica geometría. Medido: sin esta
    reparación, un solo bloque de servicio aparece como cuatro piezas y el productor propone cuatro
    regiones donde el dibujo tiene una."""
    k = stroke_scale_px(footprint.shape[:2])
    grosor = max(3, k // 4) | 1
    m = ((walls > 0) & (footprint > 0)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grosor, grosor)))
    return cv2.connectedComponents(((m > 0) & (footprint > 0)).astype(np.uint8), 8)[:2]


def significant_anchor_mask(anchors: np.ndarray, scope: np.ndarray) -> Tuple[np.ndarray, int, int]:
    """Las celdas cerradas SIGNIFICATIVAS del alcance, con la definición congelada de E16.11."""
    n, lab, st, cen = cv2.connectedComponentsWithStats((anchors > 0).astype(np.uint8), 8)
    h, w = anchors.shape[:2]
    en_alcance = []
    for i in range(1, n):
        cx, cy = cen[i]
        if scope[int(min(h - 1, max(0, cy))), int(min(w - 1, max(0, cx)))]:
            en_alcance.append((i, int(st[i, cv2.CC_STAT_AREA])))
    if not en_alcance:
        return np.zeros((h, w), np.uint8), 0, 0
    mayor = max(a for _, a in en_alcance)
    umbral = COMPLETENESS_CONTRACT["significant_min_ratio"] * mayor
    sel = [i for i, a in en_alcance if a >= umbral]
    return np.isin(lab, sel).astype(np.uint8) * 255, len(en_alcance), len(sel)


def select(image_shape, n: int, lab: np.ndarray, footprint: np.ndarray, scope: np.ndarray,
           anchors: np.ndarray, min_scope_overlap: float,
           interior: np.ndarray) -> Tuple[List[np.ndarray], ProducerTrace]:
    """SELECTION — qué piezas pertenecen a la entidad semántica.

    Tres preguntas por pieza, ninguna de tamaño y ninguna de distancia. Cada descarte queda con su
    motivo en la traza, para que se pueda auditar qué se dejó fuera y por qué."""
    tr = ProducerTrace(discovered=max(0, n - 1))
    elegidas: List[np.ndarray] = []
    for i in range(1, n):
        pieza = (lab == i)
        masa = float(pieza.sum())
        if masa <= 0:
            continue
        cerrada = _fill_holes((pieza * 255).astype(np.uint8)) & (footprint > 0)
        dentro_alcance = float((pieza & scope).sum()) / masa
        en_interior = float((pieza & interior).sum()) / masa
        anclas = int(cv2.connectedComponents((((anchors > 0) & cerrada) * 255).astype(np.uint8))[0] - 1)
        info = {"structural_px": int(masa), "scope_overlap": round(dentro_alcance, 3),
                "interior_frac": round(en_interior, 3), "enclosed_cells": anclas}
        if en_interior < 0.50:
            tr.rejected.append({**info, "why": "envolvente del piso: ya la representa el perímetro"})
            continue
        if dentro_alcance < min_scope_overlap:
            tr.rejected.append({**info, "why": "vive fuera del alcance que la semántica señaló"})
            continue
        if anclas < 1:
            tr.rejected.append({**info, "why": "no encierra ninguna celda cerrada significativa: no "
                                              "hay evidencia de recinto permanente"})
            continue
        elegidas.append(cerrada)
    tr.selected = len(elegidas)
    return elegidas, tr


def produce(image_bgr: np.ndarray, footprint: np.ndarray,
            hint_region: Tuple[float, float, float, float],
            walls: np.ndarray, anchors: np.ndarray,
            search_margin_frac: float, min_scope_overlap: float,
            params: Optional[Dict] = None) -> Tuple[List[np.ndarray], ProducerTrace]:
    """DISCOVERY → SELECTION → OUTPUT. Las máscaras salen separadas: la unión nunca se conecta."""
    h, w = footprint.shape[:2]
    fp = footprint > 0
    x0, y0, x1, y1 = [int(v) for v in hint_region]
    m = int(max(h, w) * search_margin_frac)
    scope = np.zeros((h, w), np.uint8)
    scope[max(0, y0 - m):min(h, y1 + m), max(0, x0 - m):min(w, x1 + m)] = 255
    scope = (scope > 0) & fp
    k = stroke_scale_px((h, w))
    interior = cv2.erode((fp * 255).astype(np.uint8),
                         cv2.getStructuringElement(cv2.MORPH_RECT, (2 * k + 1, 2 * k + 1))) > 0
    sig, n_scope, n_sig = significant_anchor_mask(anchors, scope)
    n, lab = discover(walls, footprint)
    piezas, tr = select((h, w), n, lab, footprint, scope, sig, min_scope_overlap, interior)
    tr.anchors_in_scope, tr.significant_anchors = n_scope, n_sig
    tr.notes = (f"{PRODUCER_VERSION}: descubiertas {tr.discovered}, seleccionadas {tr.selected}; "
                f"celdas cerradas en el alcance {n_scope} (significativas {n_sig}); "
                f"criterio = interior + alcance semántico + recinto cerrado significativo propio")
    return piezas, tr
