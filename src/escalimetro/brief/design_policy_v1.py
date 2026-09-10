"""E24 §5 — DesignPolicyV1: CÓMO ESCALÍMETRO DISEÑA. Interno. No se expone en BriefV1.

El cliente pide programa (puestos, privados, salas). No elige pesos del objetivo, ni zonificación, ni
adyacencias, ni la partición del open space en barrios, ni la estrategia geométrica de A/B/C. Convertir
el brief en una interfaz de CAD es exactamente lo que E24 §3 prohíbe.

La zonificación viva del runtime es `layout.zoning.ZONE_OF_MODULE`; aquí se DERIVA de ella para que no
existan dos verdades. El `zoning_rules` que traían las plantillas de programa era una copia muerta:
nunca se leyó (auditado en docs/E24_PROGRAM_SEMANTICS_AUDIT.md §6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..layout.zoning import ZONE_OF_MODULE

#: Pesos por defecto del objetivo (los que traía office_balanced_48.json). Cada alternativa los
#: sobrescribe con los suyos en e07/strategies.py; esto es la base común.
DEFAULT_OBJECTIVE_WEIGHTS: Dict[str, float] = {
    "daylight_utilization": 0.20,
    "circulation_efficiency": 0.12,
    "entrance_logic": 0.12,
    "adjacency_quality": 0.14,
    "compactness": 0.08,
    "privacy_gradient": 0.08,
    "meeting_accessibility": 0.10,
    "facade_preservation": 0.08,
    "wasted_space": 0.08,
}

#: §7 — partición del open space en barrios, POR ALTERNATIVA, como proporciones.
#: Reproducen exactamente la intención histórica con 40 puestos:
#:   A [0.60, 0.40]              · 40 → [24, 16]
#:   B [0.40, 0.35, 0.25]        · 40 → [16, 14, 10]
#:   C [0.30, 0.25, 0.25, 0.20]  · 40 → [12, 10, 10, 8]
#: y siguen funcionando con cualquier otro total sin tablas nuevas.
NEIGHBORHOOD_PROPORTIONS: Dict[str, List[float]] = {
    "A": [0.60, 0.40],
    "B": [0.40, 0.35, 0.25],
    "C": [0.30, 0.25, 0.25, 0.20],
}

#: Asientos por bench estándar. Define cuántos clusters pide un total de puestos.
SEATS_PER_CLUSTER = 6

#: Módulos cuyo `occupancy` ES headcount permanente (docs/E24_PROGRAM_SEMANTICS_AUDIT.md §4-§5).
PERMANENT_SEAT_MODULES = ("private_office", "reception")
#: Módulos cuyo `occupancy` son asientos de reunión: NUNCA headcount permanente.
MEETING_SEAT_MODULES = ("meeting_4", "meeting_8", "boardroom_12")
#: Módulos de soporte cuya ocupación es capacidad por turno, no puesto.
SUPPORT_CAPACITY_MODULES = ("dining", "lounge")


@dataclass(frozen=True)
class DesignPolicyV1:
    policy_id: str = "design_policy_v1"
    objective_weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_OBJECTIVE_WEIGHTS))
    neighborhood_proportions: Dict[str, List[float]] = field(
        default_factory=lambda: {k: list(v) for k, v in NEIGHBORHOOD_PROPORTIONS.items()})
    seats_per_cluster: int = SEATS_PER_CLUSTER

    def zoning_rules(self) -> Dict[str, List[str]]:
        """Derivado de la zonificación viva del runtime; no una segunda copia editable."""
        out: Dict[str, List[str]] = {}
        for mod, zone in ZONE_OF_MODULE.items():
            out.setdefault(zone, []).append(mod)
        return {z: sorted(ms) for z, ms in sorted(out.items())}

    def proportions_for(self, alt: str) -> List[float]:
        if alt not in self.neighborhood_proportions:
            raise KeyError(f"alternativa sin proporciones de barrio declaradas: {alt}")
        return list(self.neighborhood_proportions[alt])

    def to_dict(self) -> Dict:
        return {"policy_id": self.policy_id, "objective_weights": dict(self.objective_weights),
                "neighborhood_proportions": {k: list(v) for k, v in self.neighborhood_proportions.items()},
                "seats_per_cluster": self.seats_per_cluster, "zoning_rules": self.zoning_rules()}


DEFAULT_POLICY = DesignPolicyV1()
