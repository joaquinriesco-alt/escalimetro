"""E16.13.1 — un núcleo es UNA entidad semántica que puede ocupar VARIAS regiones.

TRES CONCEPTOS QUE NO SON EL MISMO

    CORE SEMANTIC ENTITY       el conjunto de infraestructura permanente que constituye el núcleo
    CORE GEOMETRIC COMPONENT   una región espacial individual de ese conjunto
    CORE CANDIDATE             el conjunto de 1..N componentes propuesto para esa entidad

"Multi-componente" NO significa "varios núcleos". Significa UN núcleo representado por varias
regiones, porque un edificio puede repartir ascensores, escaleras, baños y shafts en bloques
separados por circulación.

POR QUÉ EXISTE ESTE MÓDULO

E16.12 midió que `components_max = 1` hacía irrepresentable la respuesta correcta. Este módulo aporta
SÓLO la representación y su validación; NO produce geometría y NO toca el productor. Recibe anillos
—vengan del productor histórico, de una anotación o de otro productor futuro— y responde una sola
pregunta: ¿esta colección de regiones es una geometría de núcleo válida, y cuál es su forma canónica?

CANONICALIZACIÓN GEOMÉTRICA vs REPARACIÓN SEMÁNTICA — LA DISTINCIÓN QUE ORDENA TODO

Una operación es CANONICALIZACIÓN GEOMÉTRICA si dos entradas que describen el mismo conjunto de
regiones producen la misma salida y NINGUNA afirmación cambia: ordenar las piezas, cerrar el anillo,
rasterizar la máscara de unión. Eso es contract-safe.

Una operación es REPARACIÓN SEMÁNTICA si cambia lo que la evidencia afirmaba: descartar una pieza,
fusionar dos piezas en una, recortar una pieza que se sale. Eso NO es contract-safe, porque el
defecto que arregla vive aguas arriba y taparlo lo vuelve invisible.

    NO SE ARREGLA EVIDENCIA DEFECTUOSA PARA HACERLA ACEPTABLE.

Por eso aquí sólo hay canonicalización, y todo lo demás es un rechazo explícito
(`InvalidCoreGeometry`) o un estado de geometría que el contrato puede leer.

QUÉ NO HACE

No agrupa componentes por cercanía: dos piezas no pertenecen al mismo núcleo por estar juntas. Esa
relación la establece la evidencia semántica aguas arriba.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from shapely.geometry import Polygon as ShPolygon

Point = Tuple[float, float]
Ring = List[Point]

#: 1.x era single-ring (E16.10/E16.11). El salto de mayor existe para que un consumidor que daba por
#: cierto "un núcleo es una sola región" pueda DETECTARLO en vez de descubrirlo.
CONTRACT_VERSION = "core-geometry/2.0.0"

#: NO hay piso de ruido. Una constante universal de tamaño mínimo de pieza no está calibrada: el
#: banco disponible son fixtures sintéticos, y no distinguen una esquirla de rasterización de un
#: shaft chico. Descartar piezas por tamaño sería además REPARACIÓN SEMÁNTICA —tapa un defecto del
#: productor—, así que las piezas pequeñas se CONSERVAN, se miden (`min_component_frac`) y las juzga
#: el contrato por sus propiedades, como a cualquier otra.
NOISE_POLICY = "NOT_CALIBRATED_KEEP_AND_REPORT"


class InvalidCoreGeometry(ValueError):
    """La colección de regiones no puede representar un núcleo. No es un veto del contrato —eso
    significaría 'esto no parece un núcleo'— sino que el objeto no es una geometría válida."""


@dataclass
class CoreComponentSet:
    """Representación canónica de un candidato: 1..N anillos + su máscara de unión."""
    components: List[Ring]
    mask: np.ndarray
    areas_px: List[int] = field(default_factory=list)
    notes: str = ""

    def __len__(self) -> int:
        return len(self.components)

    @property
    def is_multi(self) -> bool:
        return len(self.components) > 1

    def single_ring(self) -> Ring:
        """Vista de UNA región, y sólo si el candidato tiene UNA región.

        E16.13 (inválido) resolvió esto con una propiedad `ring` que devolvía calladamente la pieza
        MAYOR. Un consumidor de la era single-ring habría seguido leyendo `.ring` y creyendo que
        tenía el núcleo completo mientras recibía una parte: pérdida de geometría SIN señal. Aquí la
        compatibilidad hacia atrás no puede costar silencio."""
        if len(self.components) != 1:
            raise MultiComponentCoreError(
                f"este candidato tiene {len(self.components)} regiones: no existe 'el' anillo del "
                f"núcleo. Usa `components` (todas) o `largest_ring_view()` si de verdad quieres una "
                f"parte, que lo dice en el nombre")
        return self.components[0]

    def largest_ring_view(self) -> Ring:
        """La región MAYOR, explícitamente como vista PARCIAL. El nombre es la señal."""
        return self.components[0] if self.components else []


class MultiComponentCoreError(RuntimeError):
    """Un lector pidió 'el anillo' de un núcleo que ocupa varias regiones."""


def _ring_polygon(ring: Sequence[Point]) -> ShPolygon:
    p = ShPolygon(ring)
    if not p.is_valid:
        p = p.buffer(0)
    return p


def normalize_components(rings: Sequence[Ring], footprint: np.ndarray) -> CoreComponentSet:
    """Lleva una colección de anillos a su forma canónica, o falla explicando por qué.

    LO QUE HACE (canonicalización geométrica, sin cambiar ninguna afirmación):
      * ordena las piezas: área descendente y, a igualdad, esquina superior izquierda, de modo que
        dos candidatos iguales serialicen igual;
      * rasteriza la máscara de unión.

    LO QUE NO HACE, Y POR QUÉ (E16.13.1 §7):
      * no descarta piezas chicas — sería reparación semántica y no hay umbral calibrado;
      * no fusiona piezas que se solapan — dos regiones que reclaman los mismos píxeles son un
        defecto aguas arriba, no una forma que canonicalizar: `InvalidCoreGeometry`;
      * no recorta una pieza que se sale de la huella: `InvalidCoreGeometry`.

    La tolerancia de las dos últimas es CERO por diseño. Un umbral de "cuánto solape se perdona" o
    "cuánto puede salirse" sería otra constante sin calibrar, y el error caro aquí es el silencioso."""
    h, w = footprint.shape[:2]
    fp = footprint > 0
    area_fp = float(fp.sum())
    if not rings:
        raise InvalidCoreGeometry("un candidato geométrico necesita al menos una componente")

    polys: List[ShPolygon] = []
    for r in rings:
        if len(r) < 3:
            raise InvalidCoreGeometry(f"anillo degenerado con {len(r)} vértices")
        p = _ring_polygon(r)
        if p.is_empty or p.area <= 0:
            raise InvalidCoreGeometry("anillo de área nula")
        polys.append(p)

    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            if polys[i].intersection(polys[j]).area > 0:
                raise InvalidCoreGeometry(
                    f"las componentes {i} y {j} se solapan: dos regiones no pueden reclamar los "
                    f"mismos píxeles. Fusionarlas taparía un defecto del productor")

    masks, fuera = [], []
    for i, p in enumerate(polys):
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.array(list(p.exterior.coords)[:-1], np.int32)], 255)
        mb = m > 0
        n_out = int((mb & ~fp).sum())
        if n_out:
            fuera.append((i, n_out))
        masks.append(mb)
    if fuera:
        det = ", ".join(f"{i} ({n} px)" for i, n in fuera)
        raise InvalidCoreGeometry(f"componente(s) fuera de la huella del piso: {det}")

    orden = sorted(range(len(polys)),
                   key=lambda i: (-polys[i].area, polys[i].bounds[1], polys[i].bounds[0]))
    comps = [[(float(x), float(y)) for x, y in list(polys[i].exterior.coords)[:-1]] for i in orden]
    areas = [int(masks[i].sum()) for i in orden]
    mask = np.zeros((h, w), np.uint8)
    for i in orden:
        mask[masks[i]] = 255
    menor = min(areas) / area_fp if area_fp else 0.0
    return CoreComponentSet(components=comps, mask=mask, areas_px=areas,
                            notes=(f"{len(comps)} componente(s); menor = {menor:.5f} de la huella; "
                                   f"política de piezas chicas: {NOISE_POLICY}"))


def components_from_mask(mask: np.ndarray, footprint: np.ndarray) -> CoreComponentSet:
    """Deriva la representación canónica de una máscara ya producida.

    Es el ADAPTADOR MECÁNICO entre el productor histórico —que entrega una máscara— y la
    representación. No decide nada: las piezas son las componentes conectadas que la máscara ya
    tiene. Un candidato de una sola pieza es el caso degenerado natural."""
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
    return normalize_components(rings, footprint)
