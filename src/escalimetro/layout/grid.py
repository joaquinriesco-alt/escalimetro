"""Rejilla métrica sobre el shell: campos escalares (distancia geodésica al acceso, distancia a fachada
con luz) y utilidades raster para circulación. Celda = cell_m (default 0.4 m)."""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Tuple

import numpy as np
from shapely.geometry import LineString, Point as ShPoint, Polygon
from shapely.prepared import prep
from shapely.strtree import STRtree

from .model import ShellM


class Grid:
    def __init__(self, shell: ShellM, cell_m: float = 0.4):
        self.cell = cell_m
        minx, miny, maxx, maxy = shell.perimeter.bounds
        self.x0, self.y0 = minx, miny
        self.nx = int(np.ceil((maxx - minx) / cell_m)) + 1
        self.ny = int(np.ceil((maxy - miny) / cell_m)) + 1
        self.inside = np.zeros((self.ny, self.nx), bool)
        usable = prep(shell.usable)
        for j in range(self.ny):
            for i in range(self.nx):
                cx, cy = self.center(i, j)
                self.inside[j, i] = usable.contains(ShPoint(cx, cy))
        # pilares: celda bloqueada si su centro cae dentro del pilar (o a < 0.1 m): evita que un pilar de
        # 0.8 m bloquee 3 celdas (1.2 m) por cuantización
        self.obstacle = np.zeros_like(self.inside)
        for c in shell.columns:
            self._paint(c, self.obstacle, tol=0.1)
        self.free_base = self.inside & ~self.obstacle
        self.entrance_cell = self.nearest_free(shell.entrance, self.free_base)
        # campos
        self.d_entrance = self.geodesic(self.free_base, [self.entrance_cell])
        self.d_daylight, self.daylight_w = self._daylight_field(shell)

    def center(self, i: int, j: int) -> Tuple[float, float]:
        return (self.x0 + (i + 0.5) * self.cell, self.y0 + (j + 0.5) * self.cell)

    def cell_of(self, p) -> Tuple[int, int]:
        return (int((p[0] - self.x0) / self.cell), int((p[1] - self.y0) / self.cell))

    def _paint(self, poly: Polygon, arr: np.ndarray, value=True, tol: float = None):
        """tol=None: celda pintada si el polígono toca el 90 % de la celda; tol=r: si toca un disco de radio r
        alrededor del centro."""
        minx, miny, maxx, maxy = poly.bounds
        i0, j0 = self.cell_of((minx, miny)); i1, j1 = self.cell_of((maxx, maxy))
        pp = prep(poly)
        r = self.cell * 0.45 if tol is None else tol
        for j in range(max(0, j0), min(self.ny, j1 + 1)):
            for i in range(max(0, i0), min(self.nx, i1 + 1)):
                if pp.intersects(ShPoint(self.center(i, j)).buffer(r, 1)):
                    arr[j, i] = value

    def paint(self, poly: Polygon, arr: np.ndarray, value=True):
        """Ocupación por CENTRO de celda (tol 0.05 m): un pasillo de 1.2 m contiene siempre 3 centros
        de celda (0.4 m) sea cual sea su alineación; pintar celdas parciales exigiría pasillos de
        1.6–2.0 m sólo por cuantización. Las colisiones reales se verifican con geometría exacta."""
        self._paint(poly, arr, value, tol=0.05)

    def nearest_free(self, p, free: np.ndarray) -> Tuple[int, int]:
        i, j = self.cell_of(p)
        best, bd = None, 1e9
        js, is_ = np.where(free)
        for jj, ii in zip(js, is_):
            d = (ii - i) ** 2 + (jj - j) ** 2
            if d < bd:
                bd, best = d, (ii, jj)
        return best

    def geodesic(self, free: np.ndarray, sources: List[Tuple[int, int]]) -> np.ndarray:
        """Distancia geodésica (BFS 8-conexo con pesos 1/√2) en metros; inf donde no llega."""
        dist = np.full(free.shape, np.inf)
        dq = deque()
        for (i, j) in sources:
            if free[j, i]:
                dist[j, i] = 0.0; dq.append((i, j))
        nbrs = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (-1, -1, 1.414)]
        while dq:
            i, j = dq.popleft()
            for di, dj, wgt in nbrs:
                ii, jj = i + di, j + dj
                if 0 <= ii < self.nx and 0 <= jj < self.ny and free[jj, ii]:
                    nd = dist[j, i] + wgt * self.cell
                    if nd < dist[jj, ii] - 1e-9:
                        dist[jj, ii] = nd; dq.append((ii, jj))
        return dist

    def _daylight_field(self, shell: ShellM):
        """Para cada celda: distancia euclídea al lado con luz más cercano (ponderado por prioridad) y
        prioridad de ese lado. Sólo lados likely/confirmed/exterior_unknown (prioridad > 0)."""
        edges = [(LineString([d.start, d.end]), d.priority) for d in shell.daylight if d.priority > 0]
        dist = np.full(self.inside.shape, np.inf); wgt = np.zeros(self.inside.shape)
        for j in range(self.ny):
            for i in range(self.nx):
                if not self.inside[j, i]:
                    continue
                p = ShPoint(self.center(i, j))
                best = (np.inf, 0.0)
                for ln, pr in edges:
                    dd = ln.distance(p)
                    if dd < best[0]:
                        best = (dd, pr)
                dist[j, i], wgt[j, i] = best
        return dist, wgt

    def erode(self, free: np.ndarray, r_cells: int) -> np.ndarray:
        """Celdas cuyo vecindario (2r+1)² está libre: pasillo de ancho ≥ (2r+1)·cell."""
        out = free.copy()
        for dj in range(-r_cells, r_cells + 1):
            for di in range(-r_cells, r_cells + 1):
                sh = np.roll(np.roll(free, dj, 0), di, 1)
                out &= sh
        # bordes: roll envuelve; anular borde
        out[:r_cells, :] = False; out[-r_cells:, :] = False; out[:, :r_cells] = False; out[:, -r_cells:] = False
        return out
