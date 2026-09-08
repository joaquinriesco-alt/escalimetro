"""E16.13 — un núcleo es UNA entidad semántica que puede ocupar VARIAS regiones.

TRES CONCEPTOS QUE NO SON EL MISMO (E16.13 §3)

    CORE SEMANTIC ENTITY   el conjunto de infraestructura permanente que constituye el núcleo
    CORE GEOMETRIC COMPONENT   una región espacial individual de ese conjunto
    CORE CANDIDATE   el conjunto de 1..N componentes que el productor propone para esa entidad

"Multi-componente" NO significa "varios núcleos". Significa UN núcleo representado por varias
regiones, porque un edificio puede repartir ascensores, escaleras, baños y shafts en bloques
separados por circulación. Que estén separados en el papel no los convierte en cosas distintas.

POR QUÉ CAMBIA EL CONTRATO

E16.12 midió el costo de la regla anterior. `components_max = 1` afirmaba "un núcleo correcto es una
sola pieza conectada", y esa afirmación quedó falsada por el propio banco de fixtures: un conjunto
distribuido legítimo devuelve varias piezas y era rechazado, mientras que la única forma de cumplir
la regla era engordar la geometría hasta cruzar espacio abierto. Sobre el candidato histórico del
caso de desarrollo, el 68 % de sus píxeles no era estructura ni estaba encerrado por estructura.

    NO SE CONECTAN PIEZAS PARA SATISFACER UN TIPO DE DATO,
    NI SE RECHAZAN PIEZAS CORRECTAS POR ESTAR SEPARADAS.

Y el reemplazo no es `components <= N`: mover el número no arregla nada. Lo que se evalúa ahora son
propiedades — cada pieza construida y relacionada con el alcance semántico, el conjunto plausible
dentro de la huella, la completitud sobre la UNIÓN — más una métrica de puente que se MIDE y todavía
no veta (ver `fabricated_fraction`).

LO QUE ESTE MÓDULO NO HACE

No agrupa componentes por cercanía. Dos piezas no pertenecen al mismo núcleo por estar juntas —una
escalera y unos baños pueden estar separados por circulación, y dos recintos sin relación pueden
estar pegados—. La relación entre piezas la establece la evidencia semántica aguas arriba; aquí sólo
se exige que cada pieza tenga relación con el alcance que esa evidencia señaló.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from shapely.geometry import Polygon as ShPolygon
from shapely.ops import unary_union

Point = Tuple[float, float]
Ring = List[Point]

CONTRACT_VERSION = "core-geometry/2.0.0"   # 1.x = single-ring (E16.10/E16.11)

# --- normalización -------------------------------------------------------------------------------
#: una pieza más chica que esto, respecto de la huella, no es una afirmación estructural: es un
#: fragmento de rasterización. Se descarta EN LA NORMALIZACIÓN y queda registrado; no se ignora en
#: silencio ni se usa para rechazar todo el candidato.
NOISE_COMPONENT_MIN_FRAC = 0.002


class InvalidCoreGeometry(ValueError):
    """La geometría propuesta no puede representar un núcleo. No es un rechazo de contrato: es que
    el objeto no es válido."""


@dataclass
class CoreComponentSet:
    """Representación canónica de un candidato: 1..N anillos + su máscara de unión."""
    components: List[Ring]
    mask: np.ndarray
    normalized_away: int = 0        # piezas por debajo del piso de ruido, descartadas y contadas
    merged_overlaps: int = 0        # piezas que se solapaban y se fusionaron
    notes: str = ""

    def __len__(self) -> int:
        return len(self.components)

    @property
    def ring(self) -> Ring:
        """Compatibilidad con lectores de la era single-ring: el anillo de la pieza MAYOR.

        Existe para no romper artefactos y consumidores históricos, y es deliberadamente una vista
        parcial: quien necesite el núcleo completo debe leer `components`."""
        return self.components[0] if self.components else []


def _ring_polygon(ring: Sequence[Point]) -> ShPolygon:
    p = ShPolygon(ring)
    if not p.is_valid:
        p = p.buffer(0)
    return p


def normalize_components(rings: Sequence[Ring], footprint: np.ndarray,
                         noise_min_frac: float = NOISE_COMPONENT_MIN_FRAC) -> CoreComponentSet:
    """Convierte una propuesta cualquiera en la representación canónica, o falla explicando por qué.

    Política declarada y determinista para los tres casos sucios (E16.13 §15 F, G, H):

      * pieza por debajo del piso de ruido  → SE DESCARTA en la normalización y se cuenta;
      * piezas que se solapan               → SE FUSIONAN y se cuenta; nunca geometría doble;
      * pieza fuera de la huella            → NO se normaliza: `InvalidCoreGeometry`.

    Orden canónico: área descendente y, a igualdad, esquina superior izquierda. La serialización de
    dos candidatos iguales es idéntica."""
    h, w = footprint.shape[:2]
    fp = footprint > 0
    area_fp = float(fp.sum())
    if not rings:
        raise InvalidCoreGeometry("un candidato geométrico necesita al menos una componente")
    polys = []
    for r in rings:
        if len(r) < 3:
            raise InvalidCoreGeometry(f"anillo degenerado con {len(r)} vértices")
        p = _ring_polygon(r)
        if p.is_empty or p.area <= 0:
            raise InvalidCoreGeometry("anillo de área nula")
        polys.append(p)
    # fuera de la huella: no es normalizable, es inválido
    fuera = 0
    for p in polys:
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.array(list(p.exterior.coords)[:-1], np.int32)], 255)
        dentro = float(((m > 0) & fp).sum()) / max(1.0, float((m > 0).sum()))
        if dentro < 0.98:
            fuera += 1
    if fuera:
        raise InvalidCoreGeometry(f"{fuera} componente(s) fuera de la huella del piso")
    # solapes: se fusionan
    u = unary_union(polys)
    partes = list(u.geoms) if u.geom_type == "MultiPolygon" else [u]
    merged = max(0, len(polys) - len(partes))
    # ruido: se descarta
    quedan, ruido = [], 0
    for p in partes:
        if p.area < noise_min_frac * area_fp:
            ruido += 1
            continue
        quedan.append(p)
    if not quedan:
        raise InvalidCoreGeometry("todas las componentes están por debajo del piso de ruido")
    quedan.sort(key=lambda p: (-p.area, p.bounds[1], p.bounds[0]))
    comps = [[(float(x), float(y)) for x, y in list(p.exterior.coords)[:-1]] for p in quedan]
    mask = np.zeros((h, w), np.uint8)
    for c in comps:
        cv2.fillPoly(mask, [np.array(c, np.int32)], 255)
    mask = ((mask > 0) & fp).astype(np.uint8) * 255
    return CoreComponentSet(components=comps, mask=mask, normalized_away=ruido,
                            merged_overlaps=merged,
                            notes=f"{len(comps)} componente(s); ruido descartado={ruido}; "
                                  f"solapes fusionados={merged}")


def components_from_mask(mask: np.ndarray, footprint: np.ndarray,
                         noise_min_frac: float = NOISE_COMPONENT_MIN_FRAC) -> CoreComponentSet:
    """Deriva la representación canónica de una máscara. Un candidato de una sola pieza es el caso
    degenerado natural: no hay dos caminos, hay uno."""
    n, lab, st, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    rings: List[Ring] = []
    for i in range(1, n):
        pieza = ((lab == i) * 255).astype(np.uint8)
        cnts, _ = cv2.findContours(pieza, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        eps = 0.004 * cv2.arcLength(c, True)
        ap = cv2.approxPolyDP(c, eps, True)
        if len(ap) < 3:
            continue
        rings.append([(float(a[0][0]), float(a[0][1])) for a in ap])
    return normalize_components(rings, footprint, noise_min_frac)
