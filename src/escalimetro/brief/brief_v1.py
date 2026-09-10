"""E24 §4 — BriefV1: lo que pide el cliente. Nada más.

Campos: brief_id, target_headcount, open_workstations, rooms:[{module, count}].

Lo que NO está aquí, a propósito (§3/§5): pesos del objetivo, zonificación, adyacencias, estrategia
geométrica, posición de recintos, ancho de pasillos, número de barrios de trabajo. Eso es DesignPolicyV1.

La semántica de los campos está auditada en docs/E24_PROGRAM_SEMANTICS_AUDIT.md. Resumen operativo:

    open_workstations   puestos fijos de open space, EXACTOS. Única cantidad que es restricción dura.
    target_headcount    población declarada. Dimensiona soporte y relato. NO es restricción.
    rooms               recintos por módulo. `workstation_cluster` NO se declara: se deriva.

y la identidad que E24 exige que nadie confunda:

    PERMANENT_SEATS = open_workstations + Σ count·occupancy sobre {private_office, reception}
    MEETING_SEATS   = Σ count·occupancy sobre {meeting_4, meeting_8, boardroom_12}   ← jamás headcount
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .design_policy_v1 import (DEFAULT_POLICY, MEETING_SEAT_MODULES, PERMANENT_SEAT_MODULES,
                               SUPPORT_CAPACITY_MODULES, DesignPolicyV1)

CONTRACT_VERSION = "brief_v1"

#: Módulos que el brief NO puede declarar porque se derivan de `open_workstations`.
DERIVED_MODULES = ("workstation_cluster", "workstation_row", "workstation")


class BriefError(ValueError):
    """El brief es inconsistente consigo mismo. No se corre geometría: se detiene y se reporta."""


@dataclass
class BriefV1:
    brief_id: str
    target_headcount: int
    open_workstations: int
    rooms: List[Dict] = field(default_factory=list)      # [{"module": str, "count": int}]

    # ---------- lectura ---------------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: Dict) -> "BriefV1":
        cv = d.get("contract_version", CONTRACT_VERSION)
        if cv != CONTRACT_VERSION:
            raise BriefError(f"contract_version desconocido: {cv!r}")
        faltan = [k for k in ("brief_id", "target_headcount", "open_workstations", "rooms") if k not in d]
        if faltan:
            raise BriefError(f"faltan campos obligatorios del brief: {faltan}")
        extra = set(d) - {"contract_version", "brief_id", "target_headcount", "open_workstations",
                          "rooms", "notes"}
        if extra:
            raise BriefError(f"campos no permitidos en BriefV1 (¿política de diseño?): {sorted(extra)}")
        return cls(str(d["brief_id"]), int(d["target_headcount"]), int(d["open_workstations"]),
                   [{"module": str(r["module"]), "count": int(r["count"])} for r in d["rooms"]])

    def to_dict(self) -> Dict:
        return {"contract_version": CONTRACT_VERSION, "brief_id": self.brief_id,
                "target_headcount": self.target_headcount, "open_workstations": self.open_workstations,
                "rooms": [dict(r) for r in self.rooms]}

    # ---------- derivadas -------------------------------------------------------------------------
    def room_count(self, module: str) -> int:
        return sum(int(r["count"]) for r in self.rooms if r["module"] == module)

    def cluster_count(self, policy: DesignPolicyV1 = DEFAULT_POLICY) -> int:
        """Clusters necesarios para cubrir los puestos. 40 → 7, idéntico al template histórico."""
        return int(math.ceil(self.open_workstations / float(policy.seats_per_cluster)))

    def permanent_seats(self, modules: Optional[Dict] = None) -> int:
        return self.open_workstations + self._occ_sum(PERMANENT_SEAT_MODULES, modules)

    def meeting_seats(self, modules: Optional[Dict] = None) -> int:
        return self._occ_sum(MEETING_SEAT_MODULES, modules)

    def support_capacity(self, modules: Optional[Dict] = None) -> int:
        return self._occ_sum(SUPPORT_CAPACITY_MODULES, modules)

    def unseated_headcount(self, modules: Optional[Dict] = None) -> int:
        """Se REPORTA. No se rellena con puestos extra (regla heredada de E05, formalizada en E24)."""
        return self.target_headcount - self.permanent_seats(modules)

    def _occ_sum(self, mods: Sequence[str], modules: Optional[Dict]) -> int:
        occ = _occupancies(modules)
        return sum(self.room_count(m) * int(occ.get(m, 0)) for m in mods)

    def neighborhood_seats(self, alt: str, policy: DesignPolicyV1 = DEFAULT_POLICY) -> List[int]:
        """§7 — reparto entero exacto de `open_workstations` entre los barrios de la alternativa."""
        from .apportion import apportion
        return apportion(self.open_workstations, policy.proportions_for(alt))

    # ---------- validación ------------------------------------------------------------------------
    def validate(self, modules: Optional[Dict] = None) -> List[str]:
        """Consistencia del BRIEF, no de la geometría. Geometría la juzga el solver."""
        errs: List[str] = []
        if not self.brief_id:
            errs.append("brief_id vacío")
        if self.open_workstations < 1:
            errs.append(f"open_workstations debe ser ≥ 1 (es {self.open_workstations})")
        vistos = set()
        for r in self.rooms:
            m = r["module"]
            if m in DERIVED_MODULES:
                errs.append(f"{m} no se declara en el brief: se deriva de open_workstations")
            if int(r["count"]) < 0:
                errs.append(f"count negativo en {m}")
            if m in vistos:
                errs.append(f"módulo duplicado en rooms: {m}")
            vistos.add(m)
        if modules:
            desconocidos = sorted(m for m in vistos if m not in modules)
            if desconocidos:
                errs.append(f"módulos fuera de la biblioteca: {desconocidos}")
        ps = self.permanent_seats(modules)
        if self.target_headcount < ps:
            errs.append(f"target_headcount ({self.target_headcount}) < puestos permanentes ({ps}): "
                        f"el brief pide menos personas que los puestos que declara")
        return errs

    def require_valid(self, modules: Optional[Dict] = None) -> "BriefV1":
        errs = self.validate(modules)
        if errs:
            raise BriefError(f"BRIEF_INCONSISTENT [{self.brief_id}]: " + "; ".join(errs))
        return self

    def summary(self, modules: Optional[Dict] = None) -> Dict:
        return {"brief_id": self.brief_id, "target_headcount": self.target_headcount,
                "open_workstations": self.open_workstations,
                "permanent_seats": self.permanent_seats(modules),
                "meeting_seats": self.meeting_seats(modules),
                "support_capacity": self.support_capacity(modules),
                "unseated_headcount": self.unseated_headcount(modules),
                "cluster_count": self.cluster_count(),
                "rooms": {r["module"]: int(r["count"]) for r in self.rooms}}


def _occupancies(modules: Optional[Dict]) -> Dict[str, int]:
    """`modules` puede ser el dict de `load_modules` (Module con .occupancy) o el JSON crudo."""
    if not modules:
        return {}
    out: Dict[str, int] = {}
    for name, m in modules.items():
        if hasattr(m, "occupancy"):
            out[name] = int(getattr(m, "occupancy") or 0)
        elif isinstance(m, dict):
            out[name] = int(m.get("occupancy") or 0)
    return out


def load_brief(path: str) -> BriefV1:
    with open(path, encoding="utf-8") as fh:
        return BriefV1.from_dict(json.load(fh))


# -------------------------------------------------------------------------------------------------
# compilación brief + política → el `program` que consume el motor
# -------------------------------------------------------------------------------------------------
def compile_program(brief: BriefV1, policy: DesignPolicyV1 = DEFAULT_POLICY,
                    modules: Optional[Dict] = None) -> Dict:
    """BriefV1 (cliente) + DesignPolicyV1 (interno) → dict de programa del motor.

    El motor no cambia de contrato: sigue leyendo `program`, `open_workstations_exact` y
    `objectives_weights`. Lo que cambia es que esos valores YA NO están escritos a mano en ninguna
    parte: salen del brief y de la política."""
    brief.require_valid(modules)
    prog = [{"module": "workstation_cluster", "count": brief.cluster_count(policy)}]
    prog += [{"module": r["module"], "count": int(r["count"])} for r in brief.rooms if int(r["count"]) > 0]
    return {
        "template_id": brief.brief_id,
        "brief": brief.to_dict(),
        "design_policy": policy.to_dict(),
        "vertical": "OFFICE",
        "target_headcount": brief.target_headcount,
        "program": prog,
        "open_workstations_exact": brief.open_workstations,
        "objectives_weights": dict(policy.objective_weights),
        "brief_semantics": brief.summary(modules),
    }


def brief_from_legacy_program(prog: Dict, brief_id: Optional[str] = None) -> BriefV1:
    """Puente de lectura para plantillas antiguas (`office_balanced_48.json`). Sólo se usa para
    demostrar equivalencia semántica; el camino de producción es brief JSON → compile_program."""
    rooms = [{"module": p["module"], "count": int(p["count"])} for p in prog["program"]
             if p["module"] not in DERIVED_MODULES]
    return BriefV1(brief_id or prog.get("template_id", "legacy"), int(prog["target_headcount"]),
                   int(prog["open_workstations_exact"]), rooms)
