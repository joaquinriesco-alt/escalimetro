"""E05 — Rasgos del shell para razonamiento espacial (sin coordenadas de mobiliario).

Regiones = bahías rectangulares del usable (E04 `decompose_bays`), etiquetadas por su posición respecto al
centro del núcleo (S / N / W / E) y enriquecidas con: fachada con luz, distancia geodésica al acceso,
si contienen el acceso, rectángulo máximo libre de pilares. Todo derivado de ShellM: nada del caso."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import numpy as np
from shapely.geometry import LineString, Point as ShPoint, box

from ..grid import Grid
from ..model import ShellM
from ..strips import Bay, decompose_bays


@dataclass
class Region:
    id: str                      # "S", "W", "E", "S2"…
    x0: float
    y0: float
    x1: float
    y1: float
    facade_side: str             # lado del rectángulo con fachada de luz ('' si no)
    facade_len_m: float          # metros de fachada likely_glazing en ese lado
    depth_m: float               # profundidad perpendicular a la fachada
    length_m: float              # largo paralelo a la fachada
    area_m2: float
    has_entrance: bool
    entrance_side: str           # lado sobre el que cae el acceso (si has_entrance)
    entrance_path_m: float       # distancia geodésica del acceso al centro de la región
    columns: List[List[float]] = field(default_factory=list)   # bounds de pilares que tocan la región

    @property
    def rect(self):
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def poly(self):
        return box(self.x0, self.y0, self.x1, self.y1)

    def to_dict(self):
        return asdict(self)


@dataclass
class DaylightEdgeF:
    id: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    length_m: float
    priority: float
    region_id: str


@dataclass
class ShellFeatures:
    regions: List[Region]
    daylight_edges: List[DaylightEdgeF]
    entrance: Tuple[float, float]
    entrance_region: str
    usable_area_m2: float
    core_center: Tuple[float, float]

    def region(self, rid: str) -> Region:
        return next(r for r in self.regions if r.id == rid)

    def to_dict(self):
        return {"regions": [r.to_dict() for r in self.regions],
                "daylight_edges": [asdict(e) for e in self.daylight_edges],
                "entrance": list(self.entrance), "entrance_region": self.entrance_region,
                "usable_area_m2": self.usable_area_m2, "core_center": list(self.core_center)}


def _compass(cx: float, cy: float, ox: float, oy: float) -> str:
    dx, dy = cx - ox, cy - oy
    if abs(dx) >= abs(dy):
        return "E" if dx > 0 else "W"
    return "N" if dy > 0 else "S"


def extract_features(shell: ShellM, grid: Optional[Grid] = None) -> ShellFeatures:
    grid = grid or Grid(shell)
    bays = decompose_bays(grid, shell)
    core = shell.core[0] if shell.core else shell.perimeter
    ocx, ocy = core.centroid.x, core.centroid.y
    ex, ey = shell.entrance
    regions: List[Region] = []
    labs = []
    for b in bays:
        cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
        # fachada: metros de likely_glazing (prioridad ≥ 0.75) sobre cada lado
        sides = {"S": LineString([(b.x0, b.y0), (b.x1, b.y0)]), "N": LineString([(b.x0, b.y1), (b.x1, b.y1)]),
                 "W": LineString([(b.x0, b.y0), (b.x0, b.y1)]), "E": LineString([(b.x1, b.y0), (b.x1, b.y1)])}
        best, best_len = "", 0.0
        for s, seg in sides.items():
            L = 0.0
            for d in shell.daylight:
                if d.priority >= 0.75:
                    e = LineString([d.start, d.end])
                    if e.distance(seg) < 0.9:
                        L += e.intersection(seg.buffer(0.9)).length
            if L > best_len:
                best, best_len = s, L
        horiz = best in ("S", "N")
        depth = b.h if horiz else b.w
        length = b.w if horiz else b.h
        has_ent = (b.x0 - 0.6 <= ex <= b.x1 + 0.6) and (b.y0 - 0.6 <= ey <= b.y1 + 0.6)
        ent_side = ""
        if has_ent:
            d = {"S": abs(ey - b.y0), "N": abs(ey - b.y1), "W": abs(ex - b.x0), "E": abs(ex - b.x1)}
            ent_side = min(d, key=d.get)
        i, j = grid.cell_of((cx, cy))
        i, j = min(max(i, 0), grid.nx - 1), min(max(j, 0), grid.ny - 1)
        sub = grid.d_entrance[max(0, j - 3):j + 4, max(0, i - 3):i + 4]
        fin = sub[np.isfinite(sub)]
        path = float(fin.min()) if fin.size else float("inf")
        cols = [list(c.bounds) for c in shell.columns if c.intersects(b.poly.buffer(0.1))]
        labs.append(best or _compass(cx, cy, ocx, ocy))
        regions.append(Region("", b.x0, b.y0, b.x1, b.y1, best, round(best_len, 2), round(depth, 2), round(length, 2),
                              round(b.area, 1), has_ent, ent_side, round(path, 1), cols))
    # etiqueta = lado de fachada (o rumbo respecto al núcleo); repetidas → sufijo por posición (oeste→este, sur→norte)
    for lab in set(labs):
        idx = [k for k, l in enumerate(labs) if l == lab]
        idx.sort(key=lambda k: (regions[k].x0 + regions[k].x1, regions[k].y0 + regions[k].y1))
        for n, k in enumerate(idx):
            regions[k].id = lab if len(idx) == 1 else f"{lab}{n + 1}"
    edges = []
    for k, d in enumerate(shell.daylight):
        if d.priority < 0.75:
            continue
        e = LineString([d.start, d.end])
        rid = ""
        for r in regions:
            if r.poly.buffer(0.9).intersects(e):
                rid = r.id
                break
        edges.append(DaylightEdgeF(f"dl{k}", tuple(d.start), tuple(d.end), round(e.length, 2), d.priority, rid))
    ent_region = next((r.id for r in regions if r.has_entrance), regions[0].id)
    return ShellFeatures(regions, edges, (ex, ey), ent_region, round(shell.usable.area, 1), (ocx, ocy))
