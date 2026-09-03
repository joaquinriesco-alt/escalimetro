"""Zonificación previa a la colocación: PUBLIC / SEMI_PUBLIC / WORK / SUPPORT sobre la rejilla,
a partir de dos campos: distancia geodésica al acceso y distancia a fachada con luz probable.

Reglas (m, sujetas a escala):
  PUBLIC       d_entrance ≤ 7
  WORK         d_daylight ≤ 6 y prioridad de luz ≥ 0.4 (y no PUBLIC)
  SUPPORT      interior (d_daylight > 6) y d_entrance > 10
  SEMI_PUBLIC  el resto (borde entre público y trabajo)
Además: el ESPINAZO de circulación primaria = celdas libres a ≤ spine_m del núcleo (y del acceso), reservadas.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
from shapely.geometry import Point as ShPoint
from shapely.ops import unary_union

from .grid import Grid
from .model import ShellM

ZONES = ["PUBLIC", "SEMI_PUBLIC", "WORK", "SUPPORT"]
ZONE_OF_MODULE = {"reception": "PUBLIC", "meeting_4": "SEMI_PUBLIC", "meeting_8": "SEMI_PUBLIC", "boardroom_12": "SEMI_PUBLIC",
                  "lounge": "SEMI_PUBLIC", "workstation_cluster": "WORK", "private_office": "WORK",
                  "phone_booth": "SUPPORT", "kitchenette": "SUPPORT", "dining": "SUPPORT"}


def compute_zones(grid: Grid, shell: ShellM, public_m: float = 7.0, work_m: float = 6.0, support_m: float = 10.0,
                  spine_m: float = 1.5) -> Dict:
    z = np.full(grid.inside.shape, -1, int)
    pub = grid.free_base & (grid.d_entrance <= public_m)
    work = grid.free_base & ~pub & (grid.d_daylight <= work_m) & (grid.daylight_w >= 0.4)
    sup = grid.free_base & ~pub & ~work & (grid.d_daylight > work_m) & (grid.d_entrance > support_m)
    semi = grid.free_base & ~pub & ~work & ~sup
    for k, m in enumerate([pub, semi, work, sup]):
        z[m] = k
    # espinazo: banda de spine_m alrededor del núcleo, dentro del usable, + zona del acceso
    core_u = unary_union(shell.core) if shell.core else None
    spine = np.zeros_like(grid.inside)
    ent = ShPoint(shell.entrance)
    for j in range(grid.ny):
        for i in range(grid.nx):
            if not grid.free_base[j, i]:
                continue
            p = ShPoint(grid.center(i, j))
            if (core_u is not None and core_u.distance(p) <= spine_m) or ent.distance(p) <= spine_m + 0.5:
                spine[j, i] = True
    areas = {name: float((z == k).sum()) * grid.cell ** 2 for k, name in enumerate(ZONES)}
    return {"map": z, "spine": spine, "areas_m2": {k: round(v, 1) for k, v in areas.items()},
            "params": {"public_m": public_m, "work_m": work_m, "support_m": support_m, "spine_m": spine_m}}
