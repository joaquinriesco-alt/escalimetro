"""E07 — SpatialGraph: intención espacial ANTES de resolver coordenadas.

Nodos = piezas del programa (agregadas por tipo, más los barrios de trabajo declarados por la alternativa).
Aristas = relaciones tipadas entre nodos o entre un nodo y un ancla del shell (entrance, facade, core).
El grafo NO contiene coordenadas: es lo que el motor traduce después en dominios, restricciones duras y
términos de objetivo. Dos alternativas distintas tienen grafos distintos; ese es el origen real de la
diferencia geométrica entre A, B y C."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

RELATIONS = ["must_connect", "prefer_near", "prefer_far", "client_route", "staff_route", "privacy_gradient",
             "daylight_preference", "shared_support", "acoustic_separation", "entrance_priority"]

ANCHORS = ["entrance", "facade_premium", "core", "circulation"]


@dataclass
class GraphNode:
    id: str                       # reception | boardroom | meeting_8 | meeting_4 | private_office |
                                  # open_work_neighborhood_1..n | phone_booth | kitchenette | dining | lounge
    kind: str                     # room | work | support | anchor
    count: int = 1
    seats: int = 0
    zone: str = ""                # PUBLIC | SEMI_PUBLIC | WORK | SUPPORT
    notes: str = ""


@dataclass
class GraphEdge:
    a: str
    b: str
    relation: str
    weight: float = 1.0
    hard: bool = False            # true = el motor lo traduce en restricción dura
    note: str = ""


@dataclass
class SpatialGraph:
    graph_id: str
    intent: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    priorities: Dict[str, float] = field(default_factory=dict)   # objetivos de space planning ponderados

    def to_dict(self) -> Dict:
        return {"graph_id": self.graph_id, "intent": self.intent,
                "nodes": [asdict(n) for n in self.nodes], "edges": [asdict(e) for e in self.edges],
                "priorities": self.priorities}

    @classmethod
    def from_dict(cls, d: Dict) -> "SpatialGraph":
        return cls(d["graph_id"], d["intent"], [GraphNode(**n) for n in d["nodes"]],
                   [GraphEdge(**e) for e in d["edges"]], d.get("priorities", {}))

    def save(self, path: str) -> None:
        json.dump(self.to_dict(), open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    def node(self, nid: str) -> Optional[GraphNode]:
        return next((n for n in self.nodes if n.id == nid), None)

    def edges_of(self, relation: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.relation == relation]

    def signature(self) -> Dict:
        """Huella comparable entre alternativas (para probar que A/B/C son conceptualmente distintas)."""
        return {"neighborhoods": sum(1 for n in self.nodes if n.kind == "work"),
                "edges": sorted(f"{e.a}|{e.relation}|{e.b}" for e in self.edges),
                "priorities": {k: round(v, 3) for k, v in sorted(self.priorities.items())}}


SCHEMA = {
    "type": "object",
    "required": ["graph_id", "intent", "nodes", "edges", "priorities"],
    "properties": {
        "graph_id": {"type": "string"}, "intent": {"type": "string"},
        "nodes": {"type": "array", "minItems": 8, "items": {
            "type": "object", "required": ["id", "kind"],
            "properties": {"id": {"type": "string"}, "kind": {"type": "string", "enum": ["room", "work", "support", "anchor"]},
                           "count": {"type": "integer", "minimum": 0}, "seats": {"type": "integer", "minimum": 0},
                           "zone": {"type": "string"}, "notes": {"type": "string"}}}},
        "edges": {"type": "array", "minItems": 6, "items": {
            "type": "object", "required": ["a", "b", "relation"],
            "properties": {"a": {"type": "string"}, "b": {"type": "string"},
                           "relation": {"type": "string", "enum": RELATIONS},
                           "weight": {"type": "number"}, "hard": {"type": "boolean"}, "note": {"type": "string"}}}},
        "priorities": {"type": "object"},
    },
    "additionalProperties": False,
}


def program_nodes(program: Dict, neighborhoods: int, seats_split: List[int]) -> List[GraphNode]:
    """Nodos del programa: un nodo por tipo de recinto (con su count) + n barrios de trabajo."""
    counts = {e["module"]: e["count"] for e in program["program"]}
    zone = {"reception": "PUBLIC", "boardroom_12": "SEMI_PUBLIC", "meeting_8": "SEMI_PUBLIC", "meeting_4": "SEMI_PUBLIC",
            "lounge": "SEMI_PUBLIC", "private_office": "WORK", "phone_booth": "SUPPORT", "kitchenette": "SUPPORT",
            "dining": "SUPPORT"}
    order = ["reception", "boardroom_12", "meeting_8", "meeting_4", "private_office", "phone_booth", "kitchenette",
             "dining", "lounge"]
    nodes = [GraphNode(m, "support" if zone.get(m) == "SUPPORT" else "room", counts.get(m, 0), 0, zone.get(m, ""))
             for m in order if counts.get(m, 0) > 0]
    for k, s in enumerate(seats_split[:neighborhoods]):
        nodes.append(GraphNode(f"open_work_neighborhood_{k + 1}", "work", 1, s, "WORK"))
    nodes += [GraphNode(a, "anchor", 1, 0, "", "ancla del shell") for a in ANCHORS]
    return nodes
