"""E24 §6 — filas de programa para láminas, DERIVADAS del brief.

Las etiquetas son taxonomía de módulos (§6 prohíbe borrarlas). Las CANTIDADES ya no: salen del programa
compilado desde BriefV1. Antes, tres láminas distintas escribían `("Puestos open space", "40")`.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..layout.program_access import open_workstations

OPEN_SEATS_LABEL = "Puestos open space"

#: (singular, plural) por módulo. Etiqueta comercial, no dato del cliente.
ROW_LABELS: Dict[str, Tuple[str, str]] = {
    "private_office": ("Oficina privada", "Oficinas privadas"),
    "meeting_4": ("Sala de 4", "Salas de 4"),
    "meeting_8": ("Sala de 8", "Salas de 8"),
    "boardroom_12": ("Directorio de 12", "Directorios de 12"),
    "phone_booth": ("Phone booth", "Phone booths"),
    "reception": ("Recepción", "Recepciones"),
    "kitchenette": ("Kitchenette", "Kitchenettes"),
    "dining": ("Comedor", "Comedores"),
    "lounge": ("Lounge", "Lounges"),
    "workstation_row": ("Fila de puestos", "Filas de puestos"),
}
#: orden de lámina, estable e independiente del orden en que venga el brief
ROW_ORDER = ["private_office", "meeting_4", "meeting_8", "boardroom_12", "phone_booth",
             "reception", "kitchenette", "dining", "lounge", "workstation_row"]

#: módulos cuya cuenta es geometría derivada, no programa que el cliente pidió
DERIVED_IN_DISPLAY = ("workstation_cluster",)


def room_counts(program: Dict) -> Dict[str, int]:
    return {p["module"]: int(p["count"]) for p in program["program"]
            if p["module"] not in DERIVED_IN_DISPLAY and int(p["count"]) > 0}


def total_rooms(program: Dict) -> int:
    """Recintos del programa (sin clusters de puestos). Con el brief histórico da 16."""
    return sum(room_counts(program).values())


def program_rows(program: Dict) -> List[Tuple[str, str]]:
    counts = room_counts(program)
    rows = [(OPEN_SEATS_LABEL, str(open_workstations(program)))]
    for m in ROW_ORDER:
        n = counts.get(m, 0)
        if n <= 0:
            continue
        sing, plur = ROW_LABELS.get(m, (m, m))
        rows.append((sing if n == 1 else plur, str(n)))
    for m in sorted(set(counts) - set(ROW_ORDER)):          # módulo nuevo: no se oculta
        rows.append((m, str(counts[m])))
    return rows


def program_kpis(program: Dict) -> List[Tuple[str, str]]:
    """KPIs cortos de lámina: puestos y recintos, ambos del brief."""
    return [(str(open_workstations(program)), "puestos"), (str(total_rooms(program)), "recintos")]


#: banda compacta de la Standard 02/03: agrupa las salas de reunión, como hacía la lámina histórica.
#: `salas` incluye el directorio y además éste se destaca en su propia entrada: así lo mostraba la
#: lámina histórica (3 salas de 4 + 1 de 8 + 1 directorio = 5). E24 REPRODUCE esa agrupación en vez de
#: corregirla: cambiar lo que dice la lámina no es la variable de este ciclo. Queda anotado como
#: ambigüedad de presentación (el directorio se cuenta dos veces en la banda).
BAND_GROUPS = [("puestos", None),
               ("oficinas privadas", ["private_office"]),
               ("salas", ["meeting_4", "meeting_8", "boardroom_12"]),
               ("directorio de 12", ["boardroom_12"]),
               ("phone booths", ["phone_booth"]),
               ("recepción", ["reception"]),
               ("cocina", ["kitchenette"]),
               ("comedor", ["dining"]),
               ("lounge", ["lounge"])]


def program_band_items(program: Dict) -> List[Tuple[str, str]]:
    """[(cantidad, etiqueta)] para la banda 'EL MISMO PROGRAMA EN LAS TRES'. Todo del brief."""
    counts = room_counts(program)
    out = [(str(open_workstations(program)), "puestos")]
    for label, mods in BAND_GROUPS[1:]:
        n = sum(counts.get(m, 0) for m in mods)
        if n > 0:
            out.append((str(n), label))
    resto = sorted(set(counts) - {m for _, ms in BAND_GROUPS[1:] for m in ms})
    out += [(str(counts[m]), m) for m in resto if counts[m] > 0]
    return out
