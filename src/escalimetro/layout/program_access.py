"""E24 §6 — acceso al programa SIN valores por defecto.

Antes, ocho puntos del motor leían la clave de puestos con un valor por defecto de 40. Ese 40 era el brief
histórico escrito ocho veces: un programa mal compilado seguía corriendo y resolvía 40 puestos en
silencio. Ahora falta el dato → excepción. El brief gobierna o no se corre."""
from __future__ import annotations

from typing import Dict


class ProgramContractError(KeyError):
    pass


def open_workstations(program: Dict) -> int:
    if "open_workstations_exact" not in program:
        raise ProgramContractError(
            "el programa no declara `open_workstations_exact`. E24: los puestos vienen del BriefV1 "
            "(brief.compile_program), no de un valor por defecto del motor.")
    n = int(program["open_workstations_exact"])
    if n < 0:
        raise ProgramContractError(f"open_workstations_exact negativo: {n}")
    return n
