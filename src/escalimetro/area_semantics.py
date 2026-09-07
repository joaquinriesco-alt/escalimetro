"""E16.8 — qué región del espacio mide una cifra de superficie, y cuándo puede fijar la escala.

EL ERROR DE CONTRATO QUE ESTE MÓDULO CIERRA
-------------------------------------------
Hasta E16.7 la escala se obtenía así:

    px_per_m = sqrt(area_px2 / area_m2)

sin preguntar nunca si `area_px2` y `area_m2` miden **la misma región del espacio**. El tipo de
área declarado (`useful`, `rentable`, `total`, `unknown`) sólo movía un número de confianza: no
tenía poder de veto. El resultado es una escala que siempre existe y que a veces mide otra cosa.

    UNA CIFRA DE SUPERFICIE NO ES UNA ESCALA.
    Es una observación sobre una región del espacio.

Para dividir un área en píxeles por un área en metros hace falta, antes, una correspondencia
declarada entre las dos regiones. Si no la hay, no hay escala; hay una hipótesis.

POR QUÉ IMPORTA MÁS QUE UN DETECTOR ROTO
----------------------------------------
Un detector que no encuentra el núcleo produce un vacío visible: el pipeline se detiene y alguien
lo mira. Una escala tomada de una región equivocada produce metros plausibles, y un px/m equivocado
se ve exactamente igual de bien que el correcto: todo lo que dependa de metros —anchos de
circulación, capacidad, FIT/NO_FIT— queda mal sin que nada lo advierta. El fallo silencioso es el
caro.

DOS INCERTIDUMBRES QUE NO SE MEZCLAN
------------------------------------
* INCERTIDUMBRE NUMÉRICA: "la escala podría ser 43-46 px/m". Se trata con un barrido de robustez.
* INCERTIDUMBRE SEMÁNTICA: "no sé si esa cifra corresponde a esta región". No se trata con un
  barrido: un barrido de ±10 % sobre una base equivocada devuelve un rango equivocado con aspecto
  de rigor. Bloquea o degrada la inferencia; no se promedia.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------------------------
# REGIONES EN PÍXELES — qué recortó el motor. Sale del proveedor de segmentación, no de un caso.
# ---------------------------------------------------------------------------------------------
FULL_FOOTPRINT = "full_footprint"          # todo lo encerrado por el perímetro exterior (whole_shell)
TARGET_UNIT = "target_unit"                # la unidad objetivo dentro de una lámina multiunidad
USEFUL_REGION = "useful_region"            # huella menos exclusiones EFECTIVAMENTE calculadas
UNKNOWN_REGION = "unknown_region"          # hay polígono, no se sabe qué representa
PIXEL_REGIONS = (FULL_FOOTPRINT, TARGET_UNIT, USEFUL_REGION, UNKNOWN_REGION)

# ---------------------------------------------------------------------------------------------
# TIPOS DE ÁREA PUBLICADA — vocabulario del repo, auditado antes de tocarlo (E16.8 §7).
# `useful`, `rentable`, `total` y `unknown` ya existían en case.json, en el esquema y en el
# cálculo de confianza. `full_footprint` es el único añadido, y existe porque faltaba la forma de
# decir la única cosa que autoriza la inferencia sobre una planta completa: "esta cifra es el área
# de lo que encierra el perímetro".
# ---------------------------------------------------------------------------------------------
K_USEFUL = "useful"                # superficie útil según la fuente; excluye al menos comunes/núcleo
K_RENTABLE = "rentable"            # arrendable; puede incorporar prorrateo según mercado
K_TOTAL = "total"                  # AMBIGUO en el vocabulario heredado: ver nota abajo
K_FULL_FOOTPRINT = "full_footprint"  # área de la región encerrada por el perímetro exterior
K_UNKNOWN = "unknown"              # hay cifra, no se sabe qué región mide
AREA_KINDS = (K_USEFUL, K_RENTABLE, K_TOTAL, K_FULL_FOOTPRINT, K_UNKNOWN)

# ---------------------------------------------------------------------------------------------
# ESTADOS DE VALIDEZ SEMÁNTICA DE UNA ESCALA
# ---------------------------------------------------------------------------------------------
SCALE_CONFIRMED = "SCALE_CONFIRMED"                    # medida o declarada por un humano
SCALE_MATCHED_REGION = "SCALE_INFERRED_MATCHED_REGION"  # inferida, con regiones que se corresponden
SCALE_UNCONFIRMED_REGION = "SCALE_UNCONFIRMED_REGION"   # inferida, sin poder demostrar la correspondencia
SCALE_INCOMPATIBLE_REGION = "SCALE_INCOMPATIBLE_REGION"  # las dos regiones son distintas por definición
SCALE_NOT_EVALUATED = "SCALE_NOT_EVALUATED"             # no había con qué

COMPATIBLE, INCOMPATIBLE, UNKNOWN = "COMPATIBLE", "INCOMPATIBLE", "UNKNOWN"

# ---------------------------------------------------------------------------------------------
# MATRIZ DE COMPATIBILIDAD  (región en píxeles × tipo de área publicada)
#
# Criterio, uno solo y aplicado igual a todas las celdas: dos regiones son COMPATIBLES cuando el
# vocabulario las define como la misma región; INCOMPATIBLES cuando el vocabulario las define como
# regiones distintas; UNKNOWN cuando el vocabulario no alcanza para decidirlo. No hay ninguna celda
# resuelta "porque en la práctica suele coincidir": esa es exactamente la puerta que E16.8 cierra.
#
# `total`: en el mercado chileno suele significar útil más prorrateo de comunes —mayor que la
# planta— pero el repo nunca lo definió y también se usa para "superficie total del piso". Ambiguo
# es la clasificación honesta; que lo aclare la fuente o el humano, no una heurística.
# ---------------------------------------------------------------------------------------------
COMPATIBILITY: Dict[Tuple[str, str], str] = {
    (FULL_FOOTPRINT, K_FULL_FOOTPRINT): COMPATIBLE,
    (FULL_FOOTPRINT, K_USEFUL): INCOMPATIBLE,      # útil excluye por definición parte de lo encerrado
    (FULL_FOOTPRINT, K_RENTABLE): INCOMPATIBLE,    # arrendable no es la huella: es una convención comercial
    (FULL_FOOTPRINT, K_TOTAL): UNKNOWN,
    (FULL_FOOTPRINT, K_UNKNOWN): UNKNOWN,

    (USEFUL_REGION, K_USEFUL): COMPATIBLE,
    (USEFUL_REGION, K_FULL_FOOTPRINT): INCOMPATIBLE,
    (USEFUL_REGION, K_RENTABLE): UNKNOWN,
    (USEFUL_REGION, K_TOTAL): UNKNOWN,
    (USEFUL_REGION, K_UNKNOWN): UNKNOWN,

    # Una unidad objetivo recortada de una lámina no está definida como ninguna de las cifras
    # publicadas: se le parece a la útil de esa unidad, y "se le parece" no es una definición.
    (TARGET_UNIT, K_FULL_FOOTPRINT): INCOMPATIBLE,
    (TARGET_UNIT, K_USEFUL): UNKNOWN,
    (TARGET_UNIT, K_RENTABLE): UNKNOWN,
    (TARGET_UNIT, K_TOTAL): UNKNOWN,
    (TARGET_UNIT, K_UNKNOWN): UNKNOWN,

    (UNKNOWN_REGION, K_FULL_FOOTPRINT): UNKNOWN,
    (UNKNOWN_REGION, K_USEFUL): UNKNOWN,
    (UNKNOWN_REGION, K_RENTABLE): UNKNOWN,
    (UNKNOWN_REGION, K_TOTAL): UNKNOWN,
    (UNKNOWN_REGION, K_UNKNOWN): UNKNOWN,
}


@dataclass(frozen=True)
class AreaObservation:
    """Una cifra de superficie CON la región que dice medir. Una superficie publicada deja de ser un
    float y un string sueltos: es una observación con procedencia."""
    value_m2: float
    kind: str = K_UNKNOWN
    source: str = ""                       # quién publica la cifra
    provenance: str = "source_fact"        # source_fact | human_declared | derived
    declared_region: Optional[str] = None  # equivalencia DECLARADA por la fuente (E16.8 §21)

    def __post_init__(self):
        if self.kind not in AREA_KINDS:
            raise ValueError(f"tipo de área desconocido: {self.kind!r}; válidos: {AREA_KINDS}")
        if self.declared_region is not None and self.declared_region not in PIXEL_REGIONS:
            raise ValueError(f"región declarada desconocida: {self.declared_region!r}")
        if self.value_m2 is not None and self.value_m2 <= 0:
            raise ValueError("una superficie publicada debe ser > 0")


@dataclass
class RegionMatch:
    """Resultado de preguntar si una región en píxeles y una cifra publicada hablan de lo mismo."""
    compatibility: str
    state: str
    reason: str
    pixel_region: str
    area_kind: str
    by_declaration: bool = False


def region_compatibility(pixel_region: str, obs: AreaObservation) -> RegionMatch:
    """La única puerta de entrada a la inferencia de escala por superficie publicada."""
    if pixel_region not in PIXEL_REGIONS:
        raise ValueError(f"región en píxeles desconocida: {pixel_region!r}")
    # E16.8 §21 — equivalencia DECLARADA por la fuente. Es un hecho de origen, no una heurística:
    # alguien afirma explícitamente qué región mide su cifra, y se registra como tal.
    if obs.declared_region is not None:
        if obs.declared_region == pixel_region:
            return RegionMatch(COMPATIBLE, SCALE_MATCHED_REGION,
                               f"la fuente declara que {obs.value_m2} m² ({obs.kind}) corresponden a "
                               f"la región '{pixel_region}'", pixel_region, obs.kind, by_declaration=True)
        return RegionMatch(INCOMPATIBLE, SCALE_INCOMPATIBLE_REGION,
                           f"la fuente declara que la cifra corresponde a '{obs.declared_region}', "
                           f"y la región medida es '{pixel_region}'", pixel_region, obs.kind, by_declaration=True)
    comp = COMPATIBILITY.get((pixel_region, obs.kind), UNKNOWN)
    if comp == COMPATIBLE:
        return RegionMatch(comp, SCALE_MATCHED_REGION,
                           f"'{obs.kind}' y '{pixel_region}' nombran la misma región",
                           pixel_region, obs.kind)
    if comp == INCOMPATIBLE:
        return RegionMatch(comp, SCALE_INCOMPATIBLE_REGION,
                           f"'{obs.kind}' y '{pixel_region}' nombran regiones distintas: la cifra "
                           f"publicada no puede fijar la escala de este polígono sin una equivalencia "
                           f"declarada por la fuente", pixel_region, obs.kind)
    return RegionMatch(comp, SCALE_UNCONFIRMED_REGION,
                       f"no se puede demostrar que '{obs.kind}' corresponda a '{pixel_region}': la "
                       f"escala queda como supuesto, no como medida", pixel_region, obs.kind)


# ---------------------------------------------------------------------------------------------
# REGIÓN ÚTIL EN PÍXELES (E16.8 §16, §17)
# ---------------------------------------------------------------------------------------------
class ExclusionsNotAvailable(RuntimeError):
    """No se puede construir una región útil en píxeles porque las exclusiones no están disponibles.

    LA DISTINCIÓN QUE ESTA EXCEPCIÓN PROTEGE:

        AUSENCIA DE DETECCIÓN  !=  DETECCIÓN DE AUSENCIA

    Un detector de núcleo que devuelve una lista vacía porque busca color en un plano en blanco y
    negro NO ha demostrado que no haya núcleo. Restar cero y llamar "útil" al resultado convierte un
    detector roto en evidencia. Mientras las exclusiones no estén EVALUADAS, la región útil no
    existe, y una escala que dependa de ella tampoco."""


def useful_pixel_region_area(footprint_px2: float, exclusions_px2: Optional[float],
                             exclusions_evaluated: bool) -> float:
    """Área útil en píxeles = huella menos exclusiones, sólo si las exclusiones fueron evaluadas."""
    if not exclusions_evaluated or exclusions_px2 is None:
        raise ExclusionsNotAvailable(
            "las exclusiones (núcleo, shafts, comunes) no fueron evaluadas: no hay región útil en "
            "píxeles que medir. Un detector sin resultados no prueba que el área excluida sea 0")
    if exclusions_px2 < 0 or exclusions_px2 >= footprint_px2:
        raise ValueError("exclusiones fuera de rango respecto de la huella")
    return float(footprint_px2 - exclusions_px2)
