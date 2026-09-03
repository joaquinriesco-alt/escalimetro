"""Circulación explícita: raster de celdas libres → celdas 'transitables' (vecindario de ancho mínimo
libre) → alcanzables desde el acceso → cada recinto necesita una puerta a una celda transitable
alcanzable. Grafo primario = árbol BFS acceso → puertas (nodos = acceso + puertas; aristas = rutas).
Un recinto sin ruta = violación dura (el layout FALLA)."""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

from .grid import Grid
from .model import Layout, Placement


def free_mask(grid: Grid, placements: List[Placement]) -> np.ndarray:
    free = grid.free_base.copy()
    for p in placements:
        grid.paint(p.poly, free, False)
    return free


def door_for(grid: Grid, p: Placement, passable: np.ndarray, reach: np.ndarray) -> Optional[Tuple[Tuple[int, int], Tuple[float, float]]]:
    """Celda transitable y alcanzable adyacente (≤ 1.5 celdas) al borde del recinto. Devuelve
    (celda, punto de puerta sobre el borde del recinto) o None."""
    i0, j0 = grid.cell_of((p.x, p.y)); i1, j1 = grid.cell_of((p.x + p.w, p.y + p.d))
    best = None
    for j in range(max(0, j0 - 2), min(grid.ny, j1 + 3)):
        for i in range(max(0, i0 - 2), min(grid.nx, i1 + 3)):
            if not (passable[j, i] and np.isfinite(reach[j, i])):
                continue
            cx, cy = grid.center(i, j)
            # distancia al rectángulo
            dx = max(p.x - cx, 0, cx - (p.x + p.w)); dy = max(p.y - cy, 0, cy - (p.y + p.d))
            dd = (dx * dx + dy * dy) ** 0.5
            if dd <= grid.cell * 2.3 and (best is None or reach[j, i] < best[0]):
                door = (min(max(cx, p.x), p.x + p.w), min(max(cy, p.y), p.y + p.d))
                best = (reach[j, i], (i, j), door)
    return (best[1], best[2]) if best else None


def analyze(grid: Grid, layout: Layout, min_width_m: float = 1.2) -> Dict:
    free = free_mask(grid, layout.placements)
    r = max(1, int(round((min_width_m / grid.cell - 1) / 2)))     # (2r+1)·cell ≥ min_width
    passable = grid.erode(free, r)
    ent = grid.entrance_cell
    if not passable[ent[1], ent[0]]:
        # buscar la celda transitable más cercana al acceso (≤ 2 m)
        cand = grid.nearest_free(grid.center(*ent), passable)
        if cand is None or np.hypot(cand[0] - ent[0], cand[1] - ent[1]) * grid.cell > 2.0:
            return {"ok": False, "violations": ["acceso bloqueado: sin celda transitable a ≤ 2 m del acceso"],
                    "free": free, "passable": passable, "reach": np.full(free.shape, np.inf)}
        ent = cand
    reach = grid.geodesic(passable, [ent])
    violations, doors, nodes, edges = [], {}, [{"id": "entrance", "cell": ent, "xy": grid.center(*ent)}], []
    for p in layout.placements:
        d = door_for(grid, p, passable, reach)
        if d is None:
            violations.append(f"{p.id} ({p.module}) sin acceso desde circulación")
            continue
        cell, door = d
        p.door = door
        doors[p.id] = cell
        nodes.append({"id": p.id, "cell": cell, "xy": door, "path_m": round(float(reach[cell[1], cell[0]]), 1)})
    # rutas (backtracking por gradiente de reach) para el grafo primario
    paths = {}
    for pid, cell in doors.items():
        path = [cell]; cur = cell
        for _ in range(10000):
            if cur == ent:
                break
            i, j = cur; best = None
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    ii, jj = i + di, j + dj
                    if 0 <= ii < grid.nx and 0 <= jj < grid.ny and passable[jj, ii] and reach[jj, ii] < reach[j, i]:
                        if best is None or reach[jj, ii] < reach[best[1], best[0]]:
                            best = (ii, jj)
            if best is None:
                break
            cur = best; path.append(cur)
        paths[pid] = path
        edges.append({"from": "entrance", "to": pid, "length_m": round(len(path) * grid.cell, 1)})
    circ = passable & np.isfinite(reach)
    # área de circulación = celdas de las rutas dilatadas al ancho mínimo (pasillos efectivamente usados)
    used = np.zeros_like(free)
    for path in paths.values():
        for (i, j) in path:
            used[max(0, j - r):j + r + 1, max(0, i - r):i + r + 1] = True
    used &= free
    dead = free & ~circ & ~np.isfinite(grid.geodesic(free, [ent]))          # bolsillos libres no alcanzables ni por 1 celda
    return {"ok": not violations, "violations": violations, "free": free, "passable": passable, "reach": reach,
            "circulation": circ, "used_corridors": used, "dead": dead, "paths": paths,
            "graph": {"nodes": nodes, "edges": edges}, "entrance_cell": ent, "min_width_m": min_width_m}
