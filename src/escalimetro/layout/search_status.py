"""E25 §8 — SEMÁNTICA DE ESTADOS DE BÚSQUEDA.

El error que E25 corrige: E24 llamaba `NO_FIT` a dos cosas distintas y una tercera se llamaba igual.
CP-SAT `INFEASIBLE` prueba que no hay solución **en el modelo que se le entregó**. Si el conjunto de
candidatos que construyó ese modelo fue muestreado o podado, no dice nada sobre el problema real.

    FIT                       existe una solución que cumple todas las restricciones duras.
    PROVEN_INFEASIBLE         no existe solución. Sólo se puede afirmar si el espacio considerado es
                              COMPLETO respecto del modelo V1.
    SEARCH_EXHAUSTED          el solver probó infactibilidad DENTRO de un espacio incompleto.
                              Significa "no encontramos solución con esta búsqueda".
                              NO significa "no cabe".
    TIMEOUT_NO_SOLUTION       se agotó el presupuesto sin ninguna solución válida.
    TIMEOUT_WITH_INCUMBENT    hay solución válida; no se terminó de optimizar.

Regla de producto, no negociable:

    PROVEN_INFEASIBLE  →  se puede decir "este programa no cabe bajo estas restricciones".
    SEARCH_EXHAUSTED   →  JAMÁS se puede decir eso.
    TIMEOUT_*          →  JAMÁS se puede decir eso.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

FIT = "FIT"
PROVEN_INFEASIBLE = "PROVEN_INFEASIBLE"
SEARCH_EXHAUSTED = "SEARCH_EXHAUSTED"
TIMEOUT_NO_SOLUTION = "TIMEOUT_NO_SOLUTION"
TIMEOUT_WITH_INCUMBENT = "TIMEOUT_WITH_INCUMBENT"

STATUSES = (FIT, PROVEN_INFEASIBLE, SEARCH_EXHAUSTED, TIMEOUT_NO_SOLUTION, TIMEOUT_WITH_INCUMBENT)

#: los únicos estados que autorizan decirle al cliente "no cabe"
PUEDE_DECIR_NO_CABE = (PROVEN_INFEASIBLE,)


@dataclass(frozen=True)
class CandidateSpace:
    """Descriptor de COMPLETITUD del espacio de candidatos que se le entregó al solver.

    `complete` sólo puede ser True si NADA descartó candidatos que pudieran formar parte de una
    solución válida. En V1 eso nunca ocurre: los rectángulos se muestrean en posiciones discretas a lo
    largo de los elementos de circulación. Por eso el default es False y hay que argumentar para
    cambiarlo, no al revés."""
    sampled_positions: bool = True        # posiciones discretizadas (step)
    dominance_pruned: bool = False        # se colapsaron candidatos "dominados"
    capped: bool = False                  # se aplicó un tope por módulo
    step_m: Optional[float] = None
    cap: Optional[int] = None
    note: str = ""

    @property
    def complete(self) -> bool:
        return not (self.sampled_positions or self.dominance_pruned or self.capped)

    def por_que_incompleto(self) -> str:
        r = []
        if self.sampled_positions:
            r.append(f"posiciones muestreadas cada {self.step_m} m")
        if self.dominance_pruned:
            r.append("candidatos colapsados por dominancia")
        if self.capped:
            r.append(f"tope de {self.cap} candidatos por módulo" if self.cap
                     else "tope por módulo escalado con la demanda del programa")
        return "; ".join(r) or "espacio completo"

    def to_dict(self) -> Dict:
        return {"complete": self.complete, "sampled_positions": self.sampled_positions,
                "dominance_pruned": self.dominance_pruned, "capped": self.capped,
                "step_m": self.step_m, "cap": self.cap,
                "por_que_incompleto": self.por_que_incompleto(), "note": self.note}


def classify(solver_status: str, has_solution: bool, space: CandidateSpace,
             optimality_proven: bool = False) -> str:
    """Traduce (estado de CP-SAT, hubo solución, completitud del espacio) → estado de producto."""
    if has_solution:
        return FIT if optimality_proven else (TIMEOUT_WITH_INCUMBENT if solver_status == "FEASIBLE" else FIT)
    if solver_status in ("INFEASIBLE", "INFEASIBLE_MODEL"):
        # AQUÍ está la corrección de E25: un espacio incompleto NUNCA produce PROVEN_INFEASIBLE.
        return PROVEN_INFEASIBLE if space.complete else SEARCH_EXHAUSTED
    return TIMEOUT_NO_SOLUTION


def puede_decir_que_no_cabe(status: str) -> bool:
    return status in PUEDE_DECIR_NO_CABE


def explicacion(status: str, space: CandidateSpace) -> str:
    if status == FIT:
        return "existe un layout que cumple todas las restricciones duras"
    if status == PROVEN_INFEASIBLE:
        return "no existe solución en el espacio completo del modelo V1: el programa no cabe bajo estas restricciones"
    if status == SEARCH_EXHAUSTED:
        return ("el solver probó que no hay solución DENTRO del espacio de candidatos considerado, que "
                f"es incompleto ({space.por_que_incompleto()}). No es una demostración de que no quepa.")
    if status == TIMEOUT_NO_SOLUTION:
        return "se agotó el presupuesto de tiempo sin encontrar solución: no dice nada sobre factibilidad"
    if status == TIMEOUT_WITH_INCUMBENT:
        return "hay un layout válido; no se terminó de optimizar dentro del presupuesto"
    raise ValueError(f"estado desconocido: {status!r}")
