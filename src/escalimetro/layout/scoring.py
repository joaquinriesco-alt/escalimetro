"""Scoring explícito. Cada objetivo ∈ [0,1]; total = Σ w_i · s_i con pesos del program template
(objectives_weights). Ningún peso vive en el código."""
from __future__ import annotations

from typing import Dict, List

import numpy as np
from shapely.geometry import LineString, Point as ShPoint

from .grid import Grid
from .model import Layout, Placement, ShellM
from .zoning import ZONE_OF_MODULE


def _clamp(x, lo=0.0, hi=1.0):
    return float(max(lo, min(hi, x)))


def _by(layout: Layout, module: str) -> List[Placement]:
    return [p for p in layout.placements if p.module == module]


def _geo(grid: Grid, reach: np.ndarray, p: Placement) -> float:
    if p.door is None:
        return float("inf")
    i, j = grid.cell_of(p.door)
    i, j = min(max(i, 0), grid.nx - 1), min(max(j, 0), grid.ny - 1)
    # celda de puerta puede no ser transitable: buscar mínimo en vecindario
    sub = reach[max(0, j - 2):j + 3, max(0, i - 2):i + 3]
    return float(np.min(sub)) if sub.size else float("inf")


def score(layout: Layout, shell: ShellM, grid: Grid, circ: Dict, zones: Dict, weights: Dict[str, float]) -> Dict:
    s: Dict[str, float] = {}
    detail: Dict[str, str] = {}
    reach = circ["reach"]
    # 1. daylight utilization: puestos open a < 7 m de fachada con luz, ponderado por prioridad
    vals = []
    for p in _by(layout, "workstation_cluster"):
        for (x, y, w, d) in p.desks:
            i, j = grid.cell_of((x + w / 2, y + d / 2))
            i, j = min(max(i, 0), grid.nx - 1), min(max(j, 0), grid.ny - 1)
            dd, wgt = grid.d_daylight[j, i], grid.daylight_w[j, i]
            vals.append(_clamp(1 - dd / 7.0) * (wgt / 0.75 if wgt else 0))
    s["daylight_utilization"] = float(np.mean(vals)) if vals else 0.0
    detail["daylight_utilization"] = f"{len(vals)} puestos; media de (1−d/7)·prioridad"
    # 2. circulation efficiency: área de pasillos usados / usable; 1 a ≤ 18 %, 0 a ≥ 40 %
    usable = float(grid.free_base.sum()) * grid.cell ** 2
    circ_area = float(circ["used_corridors"].sum()) * grid.cell ** 2
    ratio = circ_area / usable if usable else 1
    s["circulation_efficiency"] = _clamp(1 - (ratio - 0.18) / 0.22)
    detail["circulation_efficiency"] = f"pasillos usados {circ_area:.0f} m² = {ratio:.0%} del usable"
    # 3. entrance logic: recepción a ≤ 3 m del acceso (1) … 12 m (0)
    rec = _by(layout, "reception")
    dr = _geo(grid, reach, rec[0]) if rec else float("inf")
    s["entrance_logic"] = _clamp(1 - (dr - 3) / 9) if np.isfinite(dr) else 0.0
    detail["entrance_logic"] = f"recepción a {dr:.1f} m geodésicos del acceso"
    # 4. adjacency
    subs = []
    meets = _by(layout, "meeting_4") + _by(layout, "meeting_8") + _by(layout, "boardroom_12")
    if rec and meets:
        dm = np.mean([rec[0].poly.distance(m.poly) for m in meets])
        subs.append(("salas cerca de recepción", _clamp(1 - (dm - 4) / 16)))
    k, dn = _by(layout, "kitchenette"), _by(layout, "dining")
    if k and dn:
        subs.append(("kitchenette adyacente a comedor", 1.0 if k[0].poly.distance(dn[0].poly) < 0.6 else _clamp(1 - k[0].poly.distance(dn[0].poly) / 10)))
    if k and rec:
        subs.append(("kitchenette lejos de recepción", _clamp((k[0].poly.distance(rec[0].poly) - 4) / 12)))
    clusters = _by(layout, "workstation_cluster")
    for pb in _by(layout, "phone_booth"):
        if clusters:
            subs.append(("cabina cerca de puestos", _clamp(1 - (min(pb.poly.distance(c.poly) for c in clusters) - 1) / 8)))
    lg = _by(layout, "lounge")
    if lg:
        i, j = grid.cell_of(lg[0].center); i, j = min(max(i, 0), grid.nx - 1), min(max(j, 0), grid.ny - 1)
        subs.append(("lounge con luz", _clamp(1 - grid.d_daylight[j, i] / 8)))
    s["adjacency_quality"] = float(np.mean([v for _, v in subs])) if subs else 0.0
    detail["adjacency_quality"] = "; ".join(f"{n}={v:.2f}" for n, v in subs)
    # 5. compactness: recintos apoyados en muro/núcleo o en otro recinto
    rooms = [p for p in layout.placements if p.module != "workstation_cluster"]
    bnd = shell.usable.boundary
    touch = 0
    for p in rooms:
        if bnd.distance(p.poly) < 0.15 or any(q is not p and p.poly.distance(q.poly) < 0.15 for q in rooms):
            touch += 1
    s["compactness"] = touch / len(rooms) if rooms else 0.0
    detail["compactness"] = f"{touch}/{len(rooms)} recintos apoyados en muro o en otro recinto"
    # 6. privacy gradient: trabajo/privados más profundos que la recepción
    if rec:
        deeper = [p for p in _by(layout, "private_office") + clusters if _geo(grid, reach, p) > dr + 2]
        n = len(_by(layout, "private_office") + clusters)
        s["privacy_gradient"] = len(deeper) / n if n else 0.0
        detail["privacy_gradient"] = f"{len(deeper)}/{n} módulos de trabajo a > 2 m más profundos que recepción"
    else:
        s["privacy_gradient"] = 0.0
    # 7. meeting accessibility: la ruta acceso→sala no cruza junto a puestos (celdas de ruta a < 1 m de un cluster)
    if meets and clusters:
        fr = []
        for m in meets:
            path = circ["paths"].get(m.id, [])
            if not path:
                fr.append(1.0); continue
            near = 0
            for (i, j) in path:
                pt = ShPoint(grid.center(i, j))
                if any(c.poly.distance(pt) < 1.0 for c in clusters):
                    near += 1
            fr.append(near / len(path))
        s["meeting_accessibility"] = _clamp(1 - float(np.mean(fr)) * 1.5)
        detail["meeting_accessibility"] = f"fracción media de ruta junto a puestos = {np.mean(fr):.2f}"
    else:
        s["meeting_accessibility"] = 0.0
    # 8. facade preservation: % de fachada likely_glazing frente a recintos cerrados (a < 1 m)
    total = consumed = 0.0
    for e in shell.daylight:
        if e.classification not in ("likely_glazing", "confirmed_glazing"):
            continue
        ln = LineString([e.start, e.end]); total += ln.length
        for p in rooms:
            if p.module in ("lounge", "dining", "reception"):
                continue                                          # abiertos: no bloquean la luz
            if ln.distance(p.poly) < 1.0:
                consumed += ln.intersection(p.poly.buffer(1.0)).length
    frac = consumed / total if total else 0.0
    s["facade_preservation"] = _clamp(1 - max(0.0, frac - 0.30) / 0.5)
    detail["facade_preservation"] = f"{frac:.0%} de la fachada con luz frente a recintos cerrados (tolerancia 30 %)"
    # 9. wasted space: bolsillos libres no transitables ni alcanzables
    free = circ["free"]
    waste_cells = free & ~circ["circulation"] & ~np.isfinite(reach)
    # excluir celdas a ≤ 1 celda de una transitable alcanzable (borde de pasillo, no bolsillo)
    reachable = circ["circulation"]
    near = np.zeros_like(reachable)
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            near |= np.roll(np.roll(reachable, dj, 0), di, 1)
    waste = float((waste_cells & ~near).sum()) * grid.cell ** 2
    s["wasted_space"] = _clamp(1 - waste / (0.10 * usable))
    detail["wasted_space"] = f"{waste:.0f} m² en bolsillos no alcanzables ({waste / usable:.1%} del usable)"
    total_score = float(sum(weights[k] * s[k] for k in weights))
    return {"objectives": {k: round(v, 3) for k, v in s.items()}, "weights": weights, "total": round(total_score, 4), "detail": detail,
            "areas": {"usable_m2": round(usable, 1), "circulation_used_m2": round(circ_area, 1), "wasted_m2": round(waste, 1)}}
