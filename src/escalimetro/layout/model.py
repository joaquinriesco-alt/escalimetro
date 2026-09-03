"""Modelo del motor de layout. Agnóstico a vertical: SHELL + PROGRAM + MODULES + CONSTRAINTS + OBJECTIVES.
Todo en metros, origen abajo-izquierda del bbox del perímetro (Floorplate.to_m)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from shapely.geometry import Polygon, box

Point = Tuple[float, float]


@dataclass
class DaylightEdge:
    start: Point
    end: Point
    classification: str
    priority: float


@dataclass
class ShellM:
    """Shell en metros."""
    perimeter: Polygon
    usable: Polygon                 # perímetro − core − (nada más: pilares son obstáculos aparte)
    core: List[Polygon]
    columns: List[Polygon]          # cuadrados en m
    entrance: Point
    daylight: List[DaylightEdge]
    px_per_m: float
    scale_confidence: str           # LOW | MEDIUM | HIGH
    source: Dict = field(default_factory=dict)

    def obstacles(self) -> List[Polygon]:
        return list(self.core) + list(self.columns)


@dataclass
class Module:
    name: str
    kind: str                       # room | furniture
    w: float
    d: float
    occupancy: int
    spec: Dict = field(default_factory=dict)

    @property
    def area(self) -> float:
        return self.w * self.d


@dataclass
class Placement:
    id: str
    module: str
    x: float                        # esquina inferior-izquierda (m)
    y: float
    w: float                        # dimensiones YA rotadas
    d: float
    rot: int = 0                    # 0 | 90
    zone: str = ""
    seats: int = 0
    door: Optional[Point] = None    # punto de acceso al recinto (m)
    desks: List[Tuple[float, float, float, float]] = field(default_factory=list)   # (x, y, w, d) puestos individuales
    meta: Dict = field(default_factory=dict)

    @property
    def poly(self) -> Polygon:
        return box(self.x, self.y, self.x + self.w, self.y + self.d)

    @property
    def center(self) -> Point:
        return (self.x + self.w / 2, self.y + self.d / 2)


@dataclass
class Layout:
    layout_id: str
    template_id: str
    seed: int
    placements: List[Placement]
    circulation_cells: List[Tuple[int, int]] = field(default_factory=list)
    circulation_graph: Dict = field(default_factory=dict)      # {"nodes": [...], "edges": [...]}
    zones: Dict = field(default_factory=dict)
    scores: Dict = field(default_factory=dict)
    hard_violations: List[str] = field(default_factory=list)
    metrics: Dict = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d

    def save(self, path: str) -> None:
        def _default(o):
            try:
                import numpy as np
                if isinstance(o, (np.integer,)):
                    return int(o)
                if isinstance(o, (np.bool_,)):
                    return bool(o)
                if isinstance(o, (np.floating,)):
                    return float(o)
                if isinstance(o, np.ndarray):
                    return o.tolist()
            except ImportError:
                pass
            raise TypeError(f"no serializable: {type(o)}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=_default)

    @classmethod
    def load(cls, path: str) -> "Layout":
        d = json.load(open(path, encoding="utf-8"))
        pl = [Placement(**{**p, "door": tuple(p["door"]) if p.get("door") else None,
                           "desks": [tuple(x) for x in p.get("desks", [])]}) for p in d["placements"]]
        return cls(d["layout_id"], d["template_id"], d["seed"], pl, [tuple(c) for c in d.get("circulation_cells", [])],
                   d.get("circulation_graph", {}), d.get("zones", {}), d.get("scores", {}), d.get("hard_violations", []),
                   d.get("metrics", {}), d.get("notes", []))


def load_modules(path: str) -> Tuple[Dict[str, Module], Dict]:
    d = json.load(open(path, encoding="utf-8"))
    mods = {}
    for name, spec in d["modules"].items():
        mods[name] = Module(name, spec["kind"], float(spec["w"]), float(spec["d"]), int(spec.get("occupancy", 0)), spec)
    return mods, d.get("clearances", {})


def load_program(path: str) -> Dict:
    return json.load(open(path, encoding="utf-8"))
