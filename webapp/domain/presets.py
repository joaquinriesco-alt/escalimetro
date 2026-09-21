"""E30 §5/§6 — PRESETS. El usuario dice cómo quiere que FUNCIONE la oficina; no la dibuja.

Dos familias que no se tocan entre sí, y esa separación es el punto del §6:

    WORKPLACE PRESET   afecta el PROGRAMA  → cuántos puestos, privados y salas. Cambia el layout.
    VISUAL STYLE       afecta la IMAGEN    → mobiliario, materiales, luz decorativa, paleta.
                                             NO cambia geometría, y hay un test que lo verifica.

=================================================================================================
LO QUE UN PRESET DE LUGAR DE TRABAJO PUEDE Y NO PUEDE HACER — leer antes de tocar este archivo
=================================================================================================
Un preset produce un **BriefV1 y nada más**: `target_headcount`, `open_workstations` y `rooms`.
Ésos son los únicos campos que el contrato del cliente admite (E24 §4) y los únicos que el motor
lee de él.

No toca —ni puede tocar— `DesignPolicyV1`: pesos del objetivo, zonificación, adyacencias, barrios,
estrategia geométrica de A/B/C. Eso es política interna de Escalímetro (E24 §5) y es deliberado que
un preset comercial no la mueva.

**La brecha honesta que el §5 pide declarar:** un preset cambia QUÉ se pide, no CÓMO se coloca.
"COLLABORATIVE" pide más salas, más lounge y menos puestos fijos; no le dice al motor que agrupe
distinto ni que privilegie encuentro sobre luz natural, porque hoy no existe ningún campo de
contrato por el que decírselo. La intención se expresa entera en el programa. Si algún día se
quiere que el preset incline también el objetivo, eso es un cambio de contrato del motor y no se
hace a escondidas desde acá.

=================================================================================================
La identidad que ningún preset puede romper (E24, `BriefV1.validate`)
=================================================================================================
    PERMANENT_SEATS = open_workstations + private_office + reception   ≤   target_headcount

`_ajustar` la impone por construcción: antes que fabricar ocupación, un preset entrega menos
puestos. §22: nunca inventar gente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# =================================================================================================
# WORKPLACE PRESETS
# =================================================================================================
DENSE = "DENSE"
BALANCED = "BALANCED"
COLLABORATIVE = "COLLABORATIVE"
EXECUTIVE = "EXECUTIVE"
WORKPLACE_PRESETS = (DENSE, BALANCED, COLLABORATIVE, EXECUTIVE)
DEFAULT_PRESET = BALANCED


@dataclass(frozen=True)
class WorkplacePreset:
    key: str
    label: str
    goal: str                       # qué busca, en lenguaje de cliente
    #: puestos fijos por persona. 1.0 = un puesto para cada uno; <1 = escritorio compartido.
    seat_ratio: float
    #: oficinas privadas por persona.
    private_ratio: float
    min_private: int
    #: una sala de N cada `people_per_*` personas. 0 = no se pide ese tipo.
    people_per_meeting_4: int
    people_per_meeting_8: int
    #: desde cuántas personas tiene sentido un directorio.
    boardroom_from: int
    people_per_booth: int
    min_booth: int
    lounges_from: int
    second_lounge_from: int
    dining_from: int

    def describe(self) -> str:
        comp = "un puesto por persona" if self.seat_ratio >= 1.0 else \
               f"{int(round(self.seat_ratio * 100))} puestos cada 100 personas"
        return f"{self.goal} · {comp}"


CATALOG: Dict[str, WorkplacePreset] = {
    DENSE: WorkplacePreset(
        DENSE, "Densa", "Aprovechar al máximo la superficie",
        seat_ratio=1.0, private_ratio=0.03, min_private=1,
        people_per_meeting_4=25, people_per_meeting_8=60, boardroom_from=40,
        people_per_booth=12, min_booth=2, lounges_from=30, second_lounge_from=0, dining_from=20),
    BALANCED: WorkplacePreset(
        BALANCED, "Equilibrada", "Mezcla razonable de puestos, salas y apoyo",
        seat_ratio=1.0, private_ratio=0.08, min_private=1,
        people_per_meeting_4=12, people_per_meeting_8=30, boardroom_from=25,
        people_per_booth=10, min_booth=2, lounges_from=20, second_lounge_from=0, dining_from=15),
    COLLABORATIVE: WorkplacePreset(
        COLLABORATIVE, "Colaborativa", "Más espacio compartido y de reunión, menos densidad",
        seat_ratio=0.80, private_ratio=0.05, min_private=1,
        people_per_meeting_4=8, people_per_meeting_8=20, boardroom_from=30,
        people_per_booth=8, min_booth=3, lounges_from=1, second_lounge_from=40, dining_from=15),
    EXECUTIVE: WorkplacePreset(
        EXECUTIVE, "Ejecutiva", "Más oficinas privadas y salas formales, menos densidad",
        seat_ratio=1.0, private_ratio=0.25, min_private=2,
        people_per_meeting_4=15, people_per_meeting_8=25, boardroom_from=12,
        people_per_booth=20, min_booth=1, lounges_from=25, second_lounge_from=0, dining_from=20),
}

PRESET_LABEL = {k: v.label for k, v in CATALOG.items()}


class PresetError(ValueError):
    """El preset no puede producir un brief honesto con esos datos."""


def _cada(personas: int, cada: int) -> int:
    return int(math.ceil(personas / float(cada))) if cada and personas > 0 else 0


def _ajustar(personas: int, puestos: int, privados: int, recepcion: int) -> Tuple[int, int, int]:
    """Impone PERMANENT_SEATS ≤ target_headcount cediendo en este orden: recepción, privados,
    puestos. Nunca al revés: antes de inventar una persona, el preset entrega menos programa."""
    while puestos < 1 and privados > 0:
        privados -= 1
        puestos += 1
    if puestos < 1 and recepcion:
        recepcion, puestos = 0, puestos + 1
    puestos = max(1, puestos)
    while puestos + privados + recepcion > personas:
        if recepcion:
            recepcion = 0
        elif privados:
            privados -= 1
        else:
            puestos = max(1, personas - 0)
            break
    return puestos, privados, recepcion


def program_for(preset_key: str, headcount: int,
                target_seats: Optional[int] = None) -> Dict[str, int]:
    """preset + personas → cantidades por módulo. Determinista: mismos datos, mismo programa."""
    if preset_key not in CATALOG:
        raise PresetError(f"preset de lugar de trabajo desconocido: {preset_key}")
    try:
        personas = int(headcount)
    except (TypeError, ValueError):
        raise PresetError("El número de personas tiene que ser un número entero.")
    if personas < 1:
        raise PresetError("El número de personas debe ser al menos 1.")
    if personas > 5000:
        raise PresetError("El número de personas es demasiado alto para esta versión.")
    p = CATALOG[preset_key]

    privados = max(p.min_private, int(round(personas * p.private_ratio)))
    recepcion = 1 if personas >= 3 else 0
    if target_seats is not None:
        try:
            objetivo = int(target_seats)
        except (TypeError, ValueError):
            raise PresetError("Los puestos objetivo tienen que ser un número entero.")
        if objetivo < 1:
            raise PresetError("Los puestos objetivo deben ser al menos 1.")
        if objetivo > personas:
            # §22 — no se fabrica ocupación. Si pide más puestos que personas, se le dice.
            raise PresetError(f"Pediste {objetivo} puestos para {personas} personas. Los puestos "
                              f"fijos no pueden superar a las personas.")
        puestos = objetivo - privados - recepcion
    else:
        puestos = int(round(personas * p.seat_ratio)) - privados - recepcion
    puestos, privados, recepcion = _ajustar(personas, puestos, privados, recepcion)

    return {
        "private_office": privados,
        "reception": recepcion,
        "meeting_4": _cada(personas, p.people_per_meeting_4),
        "meeting_8": _cada(personas, p.people_per_meeting_8),
        "boardroom_12": 1 if personas >= p.boardroom_from else 0,
        "phone_booth": max(p.min_booth, _cada(personas, p.people_per_booth)),
        "kitchenette": 1,
        "dining": 1 if personas >= p.dining_from else 0,
        "lounge": (2 if (p.second_lounge_from and personas >= p.second_lounge_from)
                   else (1 if personas >= p.lounges_from else 0)),
        "_open_workstations": puestos,
    }


def brief_for(preset_key: str, headcount: int, brief_id: str,
              target_seats: Optional[int] = None) -> Dict:
    """preset + personas → dict BriefV1 listo para `webapp.briefs`. El único camino EXPRESS."""
    prog = program_for(preset_key, headcount, target_seats)
    puestos = prog.pop("_open_workstations")
    return {"contract_version": "brief_v1", "brief_id": brief_id,
            "target_headcount": int(headcount), "open_workstations": puestos,
            "rooms": [{"module": m, "count": n} for m, n in prog.items() if n > 0]}


def rooms_for_form(preset_key: str, headcount: int) -> Dict[str, int]:
    """Lo que el preset propone, para precargar el formulario AVANZADO. A partir de ahí el usuario
    edita: el preset es un punto de partida, no una jaula."""
    prog = program_for(preset_key, headcount)
    prog.pop("_open_workstations")
    return prog


def summary(preset_key: str, headcount: int) -> str:
    """Una línea para mostrar ANTES de generar: qué va a pedir este preset."""
    b = brief_for(preset_key, headcount, "PREVIEW")
    rooms = {r["module"]: r["count"] for r in b["rooms"]}
    salas = sum(rooms.get(m, 0) for m in ("meeting_4", "meeting_8", "boardroom_12"))
    bits = [f'{b["open_workstations"]} puestos']
    if rooms.get("private_office"):
        bits.append(f'{rooms["private_office"]} privados')
    if salas:
        bits.append(f"{salas} salas")
    return " · ".join(bits)


# =================================================================================================
# VISUAL STYLES — §6. Afectan la IMAGEN, jamás la geometría.
# =================================================================================================
@dataclass(frozen=True)
class VisualStyle:
    key: str
    label: str
    mood: str
    materials: str


VISUAL_STYLES: Dict[str, VisualStyle] = {
    "CORPORATE": VisualStyle("CORPORATE", "Corporativo", "sobrio, institucional, ordenado",
                             "madera clara, gris, vidrio, textil neutro"),
    "CONTEMPORARY": VisualStyle("CONTEMPORARY", "Contemporáneo", "actual, luminoso, limpio",
                                "roble claro, blanco, verde vegetal, metal fino"),
    "CREATIVE": VisualStyle("CREATIVE", "Creativo", "informal, cálido, con color",
                            "color saturado en puntos, textil, madera, plantas"),
    "INDUSTRIAL": VisualStyle("INDUSTRIAL", "Industrial", "crudo, técnico, de carácter",
                              "metal negro, cielo expuesto, hormigón, cuero"),
    "PREMIUM": VisualStyle("PREMIUM", "Premium", "silencioso, caro, de materiales nobles",
                           "nogal, piedra, latón, textil grueso"),
}
DEFAULT_STYLE = "CONTEMPORARY"
STYLE_LABEL = {k: v.label for k, v in VISUAL_STYLES.items()}


def require_style(key: str) -> str:
    if key not in VISUAL_STYLES:
        raise PresetError(f"estilo visual desconocido: {key}")
    return key


def require_preset(key: str) -> str:
    if key not in CATALOG:
        raise PresetError(f"preset de lugar de trabajo desconocido: {key}")
    return key


def style_brief(key: str) -> Dict:
    """Lo que se le pasa al motor visual. Nótese que NO contiene ni un número de geometría: un
    estilo no sabe cuántos metros mide la planta ni dónde están las ventanas, y por eso no puede
    cambiarlos (§6)."""
    s = VISUAL_STYLES[require_style(key)]
    return {"style": s.key, "label": s.label, "mood": s.mood, "materials": s.materials}
