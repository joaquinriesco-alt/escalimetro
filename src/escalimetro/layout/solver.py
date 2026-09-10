"""Solver E04: construcción aleatoria guiada + reinicios + mejora local. Determinista por seed.

Por qué esto y no CP-SAT/annealing puro: el problema tiene ~20 rectángulos con muchas restricciones
geométricas no lineales (polígono en L, pilares, circulación transitable por BFS). Un constructivo con
anclajes en muros produce candidatos "arquitectónicos" (recintos apoyados en muros, pasillos que
emergen entre ellos) y es trivial de explicar y reproducir. Los reinicios aleatorios dan diversidad;
la mejora local (reubicar un recinto si mejora el score y sigue válido) pule al mejor. CP-SAT queda
para cuando haya que garantizar optimalidad sobre una discretización — no es el riesgo de E04.

Pipeline por candidato:
  1. recintos (rooms) en orden de prioridad, cada uno elegido entre posiciones factibles ancladas a
     muros/núcleo por utilidad = afinidad de zona + preferencia de luz + preferencia de acceso + ruido;
  2. clusters de puestos en el espacio restante, priorizando cercanía a fachada con luz;
  3. validación dura (dentro, sin núcleo, sin pilares, sin solapes, programa exacto, circulación);
  4. score.
"""
from __future__ import annotations

import math
import random
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from shapely.geometry import LineString, Point as ShPoint, Polygon, box
from shapely.ops import unary_union
from shapely.prepared import prep

from scipy import ndimage

from .program_access import open_workstations

from .circulation import analyze
from .grid import Grid
from .model import Layout, Module, Placement, ShellM
from .scoring import score as score_layout
from .strips import build_strips, decompose_bays, fill_strip, sections
from .zoning import ZONE_OF_MODULE, compute_zones

ROOM_ORDER = ["reception", "boardroom_12", "meeting_8", "meeting_4", "private_office", "kitchenette", "dining", "lounge", "phone_booth"]


class Solver:
    def __init__(self, shell: ShellM, modules: Dict[str, Module], program: Dict, clearances: Dict, cell_m: float = 0.4):
        self.shell, self.modules, self.program, self.clr = shell, modules, program, clearances
        self.grid = Grid(shell, cell_m)
        self.zones = compute_zones(self.grid, shell)
        self.usable_p = prep(shell.usable.buffer(0.02))
        self.cols = shell.columns
        self.cols_p = [prep(c) for c in self.cols]
        self.anchors = self._wall_anchors()
        self.weights = program["objectives_weights"]
        self.aisle = float(clearances.get("desk_aisle_m", 1.2))
        self.reserve_spine = False
        self.rooms_first = True
        self.strategy = "strips"          # strips | greedy
        self.bays = decompose_bays(self.grid, shell)
        # zona libre obligatoria frente al acceso (radio 1.5 m): nadie la ocupa
        self.entrance_zone = ShPoint(shell.entrance).buffer(1.2)
        self.search_restarts, self.search_iters = 15, 300
        self.usable_pad = shell.usable.buffer(0.02)
        self._sec_cache: Dict[Tuple[float, bool], list] = {}
        # RESERVA DE FACHADA para puestos: celdas a ≤ cluster_depth de fachada con luz probable.
        # Los puestos tienen la primera opción sobre la fachada; los recintos sólo usan el excedente.
        self.cluster_depth = 3.2
        need = open_workstations(program)
        self.desk_demand_m2 = need / 6 * (4.8 * 3.2) * 1.25           # clusters + 25 % de holgura de posición
        self.reserve = self.grid.free_base & (self.grid.d_daylight <= self.cluster_depth) & (self.grid.daylight_w >= 0.75)
        self.reserve_area = float(self.reserve.sum()) * self.grid.cell ** 2
        self.reserve_surplus = max(0.0, self.reserve_area - self.desk_demand_m2)   # el espinazo se calcula para visualizar; los pasillos emergen y se verifican por conectividad
        self.min_corr = float(clearances.get("secondary_circulation_m", 1.2))

    # ---------- geometría de anclajes --------------------------------------------------------
    def _wall_anchors(self) -> List[Tuple[float, float, float, float, str]]:
        """Lados axis-aligned del usable: (x1,y1,x2,y2, 'h'|'v') con normal interior implícita."""
        out = []
        rings = [self.shell.usable.exterior] + list(self.shell.usable.interiors)
        for ring in rings:
            pts = list(ring.coords)
            for a, b in zip(pts[:-1], pts[1:]):
                if abs(a[1] - b[1]) < 0.05 and abs(a[0] - b[0]) > 1.0:
                    out.append((a[0], a[1], b[0], b[1], "h"))
                elif abs(a[0] - b[0]) < 0.05 and abs(a[1] - b[1]) > 1.0:
                    out.append((a[0], a[1], b[0], b[1], "v"))
        return out

    def _inward(self, x: float, y: float, axis: str) -> int:
        """+1 / −1: hacia dónde está el interior del usable desde el punto (x,y) del muro."""
        for sgn in (1, -1):
            q = (x, y + sgn * 0.3) if axis == "h" else (x + sgn * 0.3, y)
            if self.shell.usable.contains(ShPoint(q)):
                return sgn
        return 0

    def _room_candidates(self, mod: Module, step: float = 0.5) -> List[Tuple[float, float, float, float, int]]:
        cands = []
        for (x1, y1, x2, y2, axis) in self.anchors:
            L = abs(x2 - x1) if axis == "h" else abs(y2 - y1)
            for (w, d, rot) in ((mod.w, mod.d, 0), (mod.d, mod.w, 90)) if mod.spec.get("rotation_allowed", True) else ((mod.w, mod.d, 0),):
                along = w if axis == "h" else d
                depth = d if axis == "h" else w
                if along > L + 0.05:
                    continue
                n = int((L - along) / step) + 1
                for k in range(n):
                    t = k * step
                    if axis == "h":
                        x = min(x1, x2) + t
                        sgn = self._inward(x + along / 2, y1, "h")
                        y = y1 if sgn > 0 else y1 - depth
                    else:
                        y = min(y1, y2) + t
                        sgn = self._inward(x1, y + along / 2, "v")
                        x = x1 if sgn > 0 else x1 - depth
                    if sgn == 0:
                        continue
                    cands.append((x, y, w, d, rot))
        return cands

    # ---------- conectividad rápida (numpy/scipy) ----------------------------------------------
    def _occ_mask(self, rects: List[Polygon]) -> np.ndarray:
        """Celdas cuyo CENTRO cae dentro del rectángulo (coherente con Grid.paint)."""
        occ = np.zeros(self.grid.inside.shape, bool)
        c, x0, y0 = self.grid.cell, self.grid.x0, self.grid.y0
        for r in rects:
            if r.is_empty:
                continue
            if r.geom_type != "Polygon" or len(r.exterior.coords) != 5:
                self.grid.paint(r, occ, True); continue
            minx, miny, maxx, maxy = r.bounds
            i0 = int(np.ceil((minx - x0) / c - 0.5)); i1 = int(np.floor((maxx - x0) / c - 0.5))
            j0 = int(np.ceil((miny - y0) / c - 0.5)); j1 = int(np.floor((maxy - y0) / c - 0.5))
            if i1 >= i0 and j1 >= j0:
                occ[max(0, j0):min(self.grid.ny, j1 + 1), max(0, i0):min(self.grid.nx, i1 + 1)] = True
        return occ

    def _connectivity_ok(self, rects: List[Polygon], free_extra: List[Polygon] = ()) -> bool:
        """Todos los rectángulos tienen una celda transitable (pasillo ≥ min_corr) en la componente
        conectada al acceso. Erosión + etiquetado con scipy: ~1 ms. free_extra: zonas que se
        consideran libres aunque las cubra un rectángulo (conectores reservados)."""
        occ = self._occ_mask(rects)
        if free_extra:
            occ &= ~self._occ_mask(list(free_extra))
        free = self.grid.free_base & ~occ
        r = max(1, int(round((self.min_corr / self.grid.cell - 1) / 2)))
        passable = ndimage.binary_erosion(free, structure=np.ones((2 * r + 1, 2 * r + 1)), border_value=0)
        lab, n = ndimage.label(passable, structure=np.ones((3, 3)))
        ei, ej = self.grid.entrance_cell
        # componente del acceso: la celda transitable más cercana al acceso (≤ 2 m), una sola
        js, is_ = np.where(passable)
        if len(is_) == 0:
            return False
        d2 = (is_ - ei) ** 2 + (js - ej) ** 2
        k = int(np.argmin(d2))
        if d2[k] * self.grid.cell ** 2 > 4.0:
            return False
        comp = lab == lab[js[k], is_[k]]
        comp_d = ndimage.binary_dilation(comp, structure=np.ones((5, 5)))
        for rct in rects:
            m = self._occ_mask([rct])
            if not (m & comp_d).any():
                return False
        return True

    # ---------- factibilidad ---------------------------------------------------------------
    def _feasible(self, rect: Polygon, placed: List[Placement], spine: np.ndarray, gap: float = 0.0) -> bool:
        if not self.usable_p.contains(rect):
            return False
        if any(cp.intersects(rect) for cp in self.cols_p):
            return False
        for p in placed:
            if rect.intersection(p.poly).area > 1e-6:
                return False
            if gap > 0 and rect.distance(p.poly) < gap - 0.02:
                return False
        if not self.reserve_spine:
            return True
        # espinazo reservado
        minx, miny, maxx, maxy = rect.bounds
        i0, j0 = self.grid.cell_of((minx + 0.05, miny + 0.05)); i1, j1 = self.grid.cell_of((maxx - 0.05, maxy - 0.05))
        sub = spine[max(0, j0):min(self.grid.ny, j1 + 1), max(0, i0):min(self.grid.nx, i1 + 1)]
        return not sub.any()

    def _utility(self, mod: Module, rect: Polygon, rng: random.Random, temp: float) -> float:
        c = rect.centroid
        i, j = self.grid.cell_of((c.x, c.y)); i, j = min(max(i, 0), self.grid.nx - 1), min(max(j, 0), self.grid.ny - 1)
        z = self.zones["map"]
        # afinidad de zona: fracción de celdas del rectángulo en la zona preferida
        minx, miny, maxx, maxy = rect.bounds
        i0, j0 = self.grid.cell_of((minx, miny)); i1, j1 = self.grid.cell_of((maxx, maxy))
        sub = z[max(0, j0):min(self.grid.ny, j1 + 1), max(0, i0):min(self.grid.nx, i1 + 1)]
        want = ["PUBLIC", "SEMI_PUBLIC", "WORK", "SUPPORT"].index(ZONE_OF_MODULE.get(mod.name, "SEMI_PUBLIC"))
        aff = float((sub == want).mean()) if sub.size else 0.0
        dl = self.grid.d_daylight[j, i]; de = self.grid.d_entrance[j, i]
        dl_s = max(0.0, 1 - dl / 8) if np.isfinite(dl) else 0.0
        de_s = max(0.0, 1 - de / 20) if np.isfinite(de) else 0.0
        dp, ep = float(mod.spec.get("daylight_preference", 0.5)), float(mod.spec.get("entrance_preference", 0.5))
        # preferencia de luz: si el módulo la quiere, premia estar cerca; si no la quiere, premia NO consumir fachada
        light = dp * dl_s + (1 - dp) * (1 - dl_s) * 0.6
        ent = ep * de_s + (1 - ep) * (1 - de_s) * 0.6
        return 1.2 * aff + 1.0 * light + 1.0 * ent + rng.gauss(0, temp)

    # ---------- construcción -----------------------------------------------------------------
    def build(self, seed: int, temp: float = 0.25) -> Tuple[Layout, List[str]]:
        rng = random.Random(seed)
        spine = self.zones["spine"]
        placed: List[Placement] = []
        notes: List[str] = []
        counts = {p["module"]: p["count"] for p in self.program["program"]}
        surplus = {"m2": self.reserve_surplus}

        def place_rooms(names):
            for name in names:
                n = counts.get(name, 0)
                mod = self.modules[name]
                cands = self._room_candidates(mod)
                for k in range(n):
                    scored = []
                    for (x, y, w, d, rot) in cands:
                        rect = box(x, y, x + w, y + d)
                        if name == "reception" and ShPoint(self.shell.entrance).distance(rect) > 8.0:
                            continue
                        if not self._feasible(rect, placed, spine, gap=0.0):
                            continue
                        if any(q.module == "workstation_cluster" and rect.distance(q.poly) < self.aisle - 1e-6 for q in placed):
                            continue
                        # reserva de fachada: sólo módulos con alta preferencia de luz y sólo con excedente
                        res_cells = self._occ_mask([rect]) & self.reserve
                        res_m2 = float(res_cells.sum()) * self.grid.cell ** 2
                        if res_m2 > 0.5:
                            if float(mod.spec.get("daylight_preference", 0.5)) < 0.7 or res_m2 > surplus["m2"]:
                                continue
                        u = self._utility(mod, rect, rng, temp)
                        pref = set(mod.spec.get("preferred_adjacency", [])) | {name}
                        if any(q.module in pref and rect.distance(q.poly) < 0.3 for q in placed):
                            u += 0.5
                        # empaquetado: lados compartidos con otros recintos o con muros (esquinas primero)
                        shared = sum(1 for q in placed if q.module != "workstation_cluster" and rect.distance(q.poly) < 0.05
                                     and rect.buffer(0.05).intersection(q.poly).area > 0.2)
                        wall_touch = self.shell.usable.exterior.intersection(rect.buffer(0.05)).length
                        for ring in self.shell.usable.interiors:
                            wall_touch += ring.intersection(rect.buffer(0.05)).length
                        u += 0.35 * min(shared, 2) + 0.25 * min(wall_touch / (rect.length / 2), 1.0)
                        if float(mod.spec.get("daylight_preference", 0.5)) < 0.7:
                            c = rect.centroid; i, j = self.grid.cell_of((c.x, c.y)); i, j = min(max(i, 0), self.grid.nx - 1), min(max(j, 0), self.grid.ny - 1)
                            if self.zones["map"][j, i] == 2:
                                u -= 0.8
                        scored.append((u, x, y, w, d, rot, rect))
                    scored.sort(key=lambda t: -t[0])
                    best = None
                    for (u, x, y, w, d, rot, rect) in scored[:60]:       # conectividad sólo para los mejores
                        if self._connectivity_ok([q.poly for q in placed] + [rect]):
                            best = (u, x, y, w, d, rot); break
                    if best is None:
                        notes.append(f"sin posición factible para {name} #{k + 1}")
                        break
                    _, x, y, w, d, rot = best
                    surplus["m2"] -= float((self._occ_mask([box(x, y, x + w, y + d)]) & self.reserve).sum()) * self.grid.cell ** 2
                    placed.append(Placement(f"{name}_{k + 1}", name, x, y, w, d, rot, ZONE_OF_MODULE.get(name, ""),
                                            seats=mod.occupancy if mod.kind == "room" else 0))

        # 1. recepción (ancla el acceso) y recintos grandes primero (se empaquetan en las zonas sin luz premium)
        place_rooms(["reception"] + ([n for n in ROOM_ORDER if n != "reception"] if self.rooms_first else []))
        # 2. clusters de puestos: necesitan la fachada y espacio continuo
        need = open_workstations(self.program)
        got = 0; k = 0
        while got < need:
            remaining = need - got
            rows, cols = (2, 3) if remaining >= 6 else (2, max(1, math.ceil(remaining / 2)))
            seats = min(remaining, rows * cols)
            w0, d0 = cols * 1.6, rows * 1.6
            best = None
            xs = np.arange(self.grid.x0, self.grid.x0 + self.grid.nx * self.grid.cell, 0.8)
            ys = np.arange(self.grid.y0, self.grid.y0 + self.grid.ny * self.grid.cell, 0.8)
            others = [q for q in placed if q.module == "workstation_cluster"]
            for x in xs:
                for y in ys:
                    for (w, d, rot) in ((w0, d0, 0), (d0, w0, 90)):
                        rect = box(float(x), float(y), float(x) + w, float(y) + d)
                        if not self._feasible(rect, placed, spine, gap=self.aisle):
                            continue
                        c = rect.centroid; i, j = self.grid.cell_of((c.x, c.y)); i, j = min(max(i, 0), self.grid.nx - 1), min(max(j, 0), self.grid.ny - 1)
                        dl = self.grid.d_daylight[j, i]
                        u = (1 - min(dl, 10) / 10) * self.grid.daylight_w[j, i] / 0.75 + rng.gauss(0, temp * 0.6)
                        if others:
                            dmin = min(rect.distance(q.poly) for q in others)
                            u += 0.35 * max(0.0, 1 - dmin / 6)
                            # alineación en filas: misma y o misma x que algún cluster existente
                            if any(abs(q.y - y) < 0.05 or abs(q.x - x) < 0.05 for q in others):
                                u += 0.25
                        if best is None or u > best[0]:
                            if not self._connectivity_ok([q.poly for q in placed] + [rect]):
                                continue
                            best = (u, float(x), float(y), w, d, rot)
            if best is None:
                notes.append(f"sin posición para cluster #{k + 1} ({seats} puestos)")
                break
            _, x, y, w, d, rot = best
            desks = []
            nr, nc = (rows, cols) if rot == 0 else (cols, rows)
            for r in range(nr):
                for cc in range(nc):
                    if len(desks) < seats:
                        desks.append((x + cc * (w / nc), y + r * (d / nr), w / nc, d / nr))
            placed.append(Placement(f"workstation_cluster_{k + 1}", "workstation_cluster", x, y, w, d, rot, "WORK", seats=seats, desks=desks))
            got += seats; k += 1
        # 3. resto de recintos (si los clusters fueron primero)
        if not self.rooms_first:
            place_rooms([n for n in ROOM_ORDER if n != "reception"])
        layout = Layout(layout_id="candidate", template_id=self.program["template_id"], seed=seed, placements=placed)
        return layout, notes

    # ---------- conectores entre bahías ------------------------------------------------------------
    def junction_connectors(self, sel, rng, width: float = 1.5) -> List[Polygon]:
        """Para cada par de segmentos de bahía que comparten un borde, un CONECTOR de `width` m
        perpendicular al borde que une el pasillo más cercano de un lado con el del otro. Los
        conectores se reservan (nadie los ocupa) → la circulación entre bahías queda garantizada por
        construcción; la validación raster lo confirma después."""
        out = []
        items = [(b, [st for st in strips if st.kind == "corridor"]) for b, _, strips in sel]
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, ca = items[i]; b, cb = items[j]
                if not ca or not cb:
                    continue
                # borde compartido (vertical u horizontal)
                if abs(a.x1 - b.x0) < 0.05 or abs(b.x1 - a.x0) < 0.05:
                    xe = a.x1 if abs(a.x1 - b.x0) < 0.05 else a.x0
                    lo, hi = max(a.y0, b.y0), min(a.y1, b.y1)
                    if hi - lo < width + 0.5:
                        continue
                    yc = (lo + hi) / 2          # determinista: los conectores son bloqueadores del plan
                    # pasillos más cercanos al borde en cada bahía
                    pa = min(ca, key=lambda st: min(abs(st.rect[0] - xe), abs(st.rect[2] - xe)))
                    pb = min(cb, key=lambda st: min(abs(st.rect[0] - xe), abs(st.rect[2] - xe)))
                    xa = pa.rect[2] if pa.rect[2] <= xe + 0.05 else pa.rect[0]
                    xb = pb.rect[0] if pb.rect[0] >= xe - 0.05 else pb.rect[2]
                    # si un pasillo perpendicular al borde (corre en y) lo toca, el conector sale de su eje
                    for pp, xx in ((pa, xa), (pb, xb)):
                        if pp.axis == "h" and abs(xx - xe) < 0.05:     # pasillo que corre en x toca el borde vertical
                            yc = min(max((pp.rect[1] + pp.rect[3]) / 2, lo + width / 2), hi - width / 2)
                    if abs(xa - xe) < 0.05 and abs(xb - xe) < 0.05:
                        # ambos pasillos (horizontales) tocan el borde: si se solapan en y no hace falta nada;
                        # si no, el conector corre A LO LARGO del borde uniendo sus alturas (no perpendicular).
                        ov = min(pa.rect[3], pb.rect[3]) - max(pa.rect[1], pb.rect[1])
                        if ov >= self.min_corr - 0.05:
                            continue
                        ylo, yhi = min(pa.rect[1], pb.rect[1]), max(pa.rect[3], pb.rect[3])
                        out.append(box(xe - width / 2, ylo, xe + width / 2, yhi))
                        continue
                    # si un pasillo ya toca el borde en la altura yc, el tramo es de largo 0 en ese lado
                    if pa.rect[1] <= yc <= pa.rect[3] and abs(xa - xe) < 0.05 and pb.rect[1] <= yc <= pb.rect[3] and abs(xb - xe) < 0.05:
                        continue
                    x0, x1 = min(xa, xb, xe), max(xa, xb, xe)
                    out.append(box(x0, yc - width / 2, x1, yc + width / 2))
                elif abs(a.y1 - b.y0) < 0.05 or abs(b.y1 - a.y0) < 0.05:
                    ye = a.y1 if abs(a.y1 - b.y0) < 0.05 else a.y0
                    lo, hi = max(a.x0, b.x0), min(a.x1, b.x1)
                    if hi - lo < width + 0.5:
                        continue
                    xc = (lo + hi) / 2
                    pa = min(ca, key=lambda st: min(abs(st.rect[1] - ye), abs(st.rect[3] - ye)))
                    pb = min(cb, key=lambda st: min(abs(st.rect[1] - ye), abs(st.rect[3] - ye)))
                    ya = pa.rect[3] if pa.rect[3] <= ye + 0.05 else pa.rect[1]
                    yb = pb.rect[1] if pb.rect[1] >= ye - 0.05 else pb.rect[3]
                    for pp, yy in ((pa, ya), (pb, yb)):
                        if pp.axis == "v" and abs(yy - ye) < 0.05:     # pasillo que corre en y toca el borde horizontal
                            xc = min(max((pp.rect[0] + pp.rect[2]) / 2, lo + width / 2), hi - width / 2)
                    if abs(ya - ye) < 0.05 and abs(yb - ye) < 0.05:
                        ov = min(pa.rect[2], pb.rect[2]) - max(pa.rect[0], pb.rect[0])
                        if ov >= self.min_corr - 0.05:
                            continue
                        xlo, xhi = min(pa.rect[0], pb.rect[0]), max(pa.rect[2], pb.rect[2])
                        out.append(box(xlo, ye - width / 2, xhi, ye + width / 2))
                        continue
                    if pa.rect[0] <= xc <= pa.rect[2] and abs(ya - ye) < 0.05 and pb.rect[0] <= xc <= pb.rect[2] and abs(yb - ye) < 0.05:
                        continue
                    y0, y1 = min(ya, yb, ye), max(ya, yb, ye)
                    out.append(box(xc - width / 2, y0, xc + width / 2, y1))
        return out

    def cross_connectors(self, sel, width: float = 1.5) -> List[Polygon]:
        """Un segmento con ≥ 2 pasillos paralelos necesita un pasillo transversal que los una: se reserva
        una banda de `width` m a través de todas las franjas, en el extremo del segmento más cercano al
        acceso (medido a lo largo del eje de las franjas)."""
        out = []
        ex, ey = self.shell.entrance
        for b, sec, strips in sel:
            corrs = [st for st in strips if st.kind == "corridor"]
            if len(corrs) < 2:
                continue
            axis = corrs[0].axis
            if axis == "h":          # franjas corren en x: banda vertical en el extremo x más cercano al acceso
                x0 = b.x0 if abs(ex - b.x0) <= abs(ex - b.x1) else b.x1 - width
                out.append(box(x0, b.y0, x0 + width, b.y1))
            else:
                y0 = b.y0 if abs(ey - b.y0) <= abs(ey - b.y1) else b.y1 - width
                out.append(box(b.x0, y0, b.x1, y0 + width))
        return out

    # ---------- construcción por bahías y franjas (E04, estrategia principal) ------------------------
    def _corridors_clear(self, strips_all) -> bool:
        """Ningún pilar reduce un pasillo por debajo de min_corr (los pilares de la línea intermedia caen
        dentro del pasillo si la sección no los absorbe en una franja de recintos)."""
        for st in strips_all:
            if st.kind != "corridor":
                continue
            b = box(*st.rect)
            for c in self.cols:
                inter = c.intersection(b)
                if inter.is_empty or inter.area < 1e-3:
                    continue
                bb = inter.bounds
                intrusion = (bb[3] - bb[1]) if st.axis == "h" else (bb[2] - bb[0])
                if st.depth - intrusion < self.min_corr - 0.05:
                    return False
        return True

    def build_strips(self, seed: int) -> Tuple[Layout, List[str]]:
        rng = random.Random(seed)
        notes: List[str] = []
        counts = {p["module"]: p["count"] for p in self.program["program"]}
        need = open_workstations(self.program)
        # 1. elegir una sección por bahía. Se muestrea hasta que la capacidad cubra el programa.
        rooms_items = []
        for name in ROOM_ORDER:
            mod = self.modules[name]
            for k in range(counts.get(name, 0)):
                rooms_items.append((f"{name}_{k + 1}", mod, mod.w, mod.d, mod.occupancy if mod.kind == "room" else 0))
        room_area = sum(w * d for _, _, w, d, _ in rooms_items)
        clusters = []
        got, k = 0, 0
        while got < need:
            seats = min(6, need - got)
            rows, cols = (2, 3) if seats >= 6 else (2, max(1, math.ceil(seats / 2)))
            clusters.append((f"workstation_cluster_{k + 1}", self.modules["workstation_cluster"], cols * 1.6, rows * 1.6, seats))
            got += seats; k += 1
        chosen = None
        from .strips import Bay, split_bay, strip_segments, pack_ffd, place_at
        ent = ShPoint(self.shell.entrance)

        def plan(strips_all):
            return self.plan_strips(strips_all, rooms_items, need, rng)

        # ---- búsqueda local sobre la configuración de bahías (eje, cortes, secciones) --------------
        # fitness = fracción de recintos asignables + fracción de puestos + conectividad + acceso abierto.
        # Mutaciones: cambiar la sección de un segmento / mover un corte / cambiar el eje de una bahía.
        def make_state():
            st = []
            for b0 in self.bays:
                axis = rng.choice(b0.axis_options())
                b0.axis = axis
                segs = split_bay(b0, rng)
                secs = []
                for b in segs:
                    b.axis = axis
                    depth = b.strip_depth()
                    sc = b.entrance_side in (("S", "N") if b.strip_axis() == "h" else ("W", "E"))
                    key = (round(depth, 2), bool(b.facade_side), sc)
                    if key not in self._sec_cache:
                        self._sec_cache[key] = sections(depth, bool(b.facade_side), start_corridor=sc)
                    opts = self._sec_cache[key]
                    if not opts:
                        secs.append(None); continue
                    weights = [3.0 if (b.facade_side and sec[0][0] == "desks") else (0.3 if (b.facade_side and sec[0][0] == "rooms") else 1.0) for sec in opts]
                    secs.append(rng.choices(opts, weights=weights, k=1)[0])
                st.append({"bay": b0, "axis": axis, "segs": segs, "secs": secs})
            return st

        def realize(state):
            sel = []
            for e in state:
                for b, sec in zip(e["segs"], e["secs"]):
                    if sec is None:
                        continue
                    b.axis = e["axis"]
                    sel.append((b, sec, build_strips(b, sec, self.shell.usable)))
            self._connectors = self.junction_connectors(sel, rng) + self.cross_connectors(sel)
            return sel

        def fitness(state):
            sel = realize(state)
            strips_all = [st for _, _, strips in sel for st in strips]
            corr = [box(*st.rect) for st in strips_all if st.kind == "corridor"] + list(self._connectors)
            ent_ok = any(c.distance(self.entrance_zone) < 0.6 for c in corr)
            blocks = [box(*st.rect) for st in strips_all if st.kind != "corridor"]
            conn_ok = self._connectivity_ok(blocks, free_extra=self._connectors) if blocks else False
            corr_ok = self._corridors_clear(strips_all)
            res = self.plan_strips(strips_all, rooms_items, need, rng, partial=True)
            rooms_frac, seats_frac = res["rooms_frac"], res["seats_frac"]
            f = 0.4 * rooms_frac + 0.3 * seats_frac + 0.1 * ent_ok + 0.1 * conn_ok + 0.1 * corr_ok
            if not (ent_ok and conn_ok and corr_ok):
                f *= 0.7          # topología rota = nunca preferible a un programa incompleto con topología sana
            full = rooms_frac >= 1.0 and seats_frac >= 1.0 and ent_ok and conn_ok and corr_ok
            return f, full, sel, strips_all, res

        def mutate(state):
            e = rng.choice(state)
            r = rng.random()
            b0 = e["bay"]
            if r < 0.6 and e["secs"]:
                i = rng.randrange(len(e["secs"]))
                b = e["segs"][i]
                sc = b.entrance_side in (("S", "N") if b.strip_axis() == "h" else ("W", "E"))
                key = (round(b.strip_depth(), 2), bool(b.facade_side), sc)
                if key not in self._sec_cache:
                    self._sec_cache[key] = sections(b.strip_depth(), bool(b.facade_side), start_corridor=sc)
                opts = self._sec_cache.get(key) or []
                if opts:
                    e["secs"][i] = rng.choice(opts)
            elif r < 0.85:
                b0.axis = e["axis"]
                e["segs"] = split_bay(b0, rng)
                e["secs"] = []
                for b in e["segs"]:
                    b.axis = e["axis"]
                    sc = b.entrance_side in (("S", "N") if b.strip_axis() == "h" else ("W", "E"))
                    key = (round(b.strip_depth(), 2), bool(b.facade_side), sc)
                    if key not in self._sec_cache:
                        self._sec_cache[key] = sections(b.strip_depth(), bool(b.facade_side), start_corridor=sc)
                    opts = self._sec_cache[key]
                    e["secs"].append(rng.choice(opts) if opts else None)
            else:
                opts_axis = b0.axis_options()
                if len(opts_axis) > 1:
                    e["axis"] = [a for a in opts_axis if a != e["axis"]][0]
                    b0.axis = e["axis"]
                    e["segs"] = split_bay(b0, rng)
                    e["secs"] = []
                    for b in e["segs"]:
                        b.axis = e["axis"]
                        sc = b.entrance_side in (("S", "N") if b.strip_axis() == "h" else ("W", "E"))
                        key = (round(b.strip_depth(), 2), bool(b.facade_side), sc)
                        if key not in self._sec_cache:
                            self._sec_cache[key] = sections(b.strip_depth(), bool(b.facade_side), start_corridor=sc)
                        opts = self._sec_cache[key]
                        e["secs"].append(rng.choice(opts) if opts else None)
            return state

        import copy
        best_state, best_f = None, -1
        for restart in range(self.search_restarts):
            state = make_state()
            f, full, sel, strips_all, res = fitness(state)
            cur_f = f
            if full:
                chosen = (sel, strips_all, (res["assign"], res["desk_plan"])); break
            for it in range(self.search_iters):
                cand = mutate(copy.deepcopy(state))
                f2, full2, sel2, strips2, res2 = fitness(cand)
                if full2:
                    chosen = (sel2, strips2, (res2["assign"], res2["desk_plan"])); break
                if f2 >= cur_f:
                    state, cur_f = cand, f2
            if chosen is not None:
                break
            if cur_f > best_f:
                best_f, best_state = cur_f, state
        if chosen is None and best_state is not None:
            f, full, sel, strips_all, res = fitness(best_state)
            corr = [box(*st.rect) for st in strips_all if st.kind == "corridor"]
            self.last_search = {"best_fitness": round(best_f, 3), "found": False, "unassigned": res["unassigned"],
                                "seats_frac": round(res["seats_frac"], 2),
                                "entrance_ok": any(c.distance(self.entrance_zone) < 0.6 for c in corr),
                                "conn_ok": self._connectivity_ok([box(*st.rect) for st in strips_all if st.kind != "corridor"]),
                                "strips": [(st.kind, round(st.depth, 1), [round(v, 1) for v in st.rect]) for st in strips_all],
                                "sections": [(b.ref_side, [k for k, _ in sec]) for b, sec, _ in sel]}
        else:
            self.last_search = {"best_fitness": round(best_f, 3), "found": chosen is not None}
        if chosen is None:
            notes.append("ninguna combinación de secciones cubre el programa (capacidad con pilares): se devuelve el mejor parcial")
            if best_state is None:
                return Layout("candidate", self.program["template_id"], seed, []), notes
            f, full, sel, strips_all, res = fitness(best_state)
            chosen = (sel, strips_all, (res["assign"], res["desk_plan"]))
            notes.append(f"parcial: sin asignar {res['unassigned']}, puestos {res['seats_frac']:.0%}")
        sel, strips_all, (assign, desk_plan) = chosen
        placed: List[Placement] = []
        for i, lst in assign.items():
            st = strips_all[i]
            for it, off, along in lst:
                placed.append(place_at(st, it, off, self.cols, along_hint=along))
        for i, it, off in desk_plan:
            placed.append(place_at(strips_all[i], it, off, self.cols))
        chosen = sel
        # recepción debe estar a ≤ 8 m del acceso: si no, intentar reubicarla con anclajes
        rec = [p for p in placed if p.module == "reception"]
        if rec and ent.distance(rec[0].poly) > 8.0:
            others = [p for p in placed if p is not rec[0]]
            mod = self.modules["reception"]
            best = None
            for (x, y, w, d, rot) in self._room_candidates(mod):
                rect = box(x, y, x + w, y + d)
                if ent.distance(rect) > 8.0 or not self._feasible(rect, others, self.zones["spine"]):
                    continue
                if any(q.module == "workstation_cluster" and rect.distance(q.poly) < self.aisle - 0.02 for q in others):
                    continue
                dd = ent.distance(rect)
                if best is None or dd < best[0]:
                    best = (dd, x, y, w, d, rot)
            if best:
                _, x, y, w, d, rot = best
                placed = others + [Placement("reception_1", "reception", x, y, w, d, rot, "PUBLIC", seats=1)]
                notes.append("recepción reubicada por anclaje para cumplir ≤ 8 m del acceso")
        layout = Layout("candidate", self.program["template_id"], seed, placed)
        layout.zones = {"sections": [{"bay": [round(b.x0, 1), round(b.y0, 1), round(b.x1, 1), round(b.y1, 1)], "facade": b.facade_side,
                                      "ref_side": b.ref_side, "section": [(k, d) for k, d in sec]} for b, sec, _ in chosen],
                        "connectors": [[round(v, 2) for v in c.bounds] for c in getattr(self, "_connectors", [])],
                        "strips": [(st.kind, round(st.depth, 2), [round(v, 2) for v in st.rect]) for st in strips_all]}
        return layout, notes

    def plan_strips(self, strips_all, rooms_items, need, rng, partial: bool = False):
        ent = ShPoint(self.shell.entrance)
        unassigned = []
        if True:
            from .strips import strip_segments
            """Asignación 1D con pilares: recintos por clase de profundidad (los más profundos primero) con
            preferencia de cercanía al acceso; puestos por bloques. Devuelve plan o None."""
            blk = tuple([self.entrance_zone] + list(getattr(self, "_connectors", [])))
            room_strips = [(i, st, strip_segments(st, self.cols, "rooms", blockers=blk)) for i, st in enumerate(strips_all) if st.kind == "rooms"]
            desk_strips = [(i, st, strip_segments(st, self.cols, "desks", blockers=blk)) for i, st in enumerate(strips_all) if st.kind == "desks"]
            desk_seg_ref = {i: sg for i, st, sg in desk_strips}
            segs = {i: [[a, b] for a, b in sg] for i, _, sg in room_strips}
            items = sorted(rooms_items, key=lambda it: (-min(it[2], it[3]), -float(it[1].spec.get("entrance_preference", 0.5)) + rng.uniform(-0.1, 0.1)))
            assign: Dict[int, list] = {i: [] for i, _, _ in room_strips}
            for it in items:
                pid, mod, w, d, seats = it
                ep = float(mod.spec.get("entrance_preference", 0.5))
                best = None
                for i, st, _ in room_strips:
                    alongs = sorted([a for a, dd in ((w, d), (d, w)) if dd <= st.depth + 0.05])
                    for along in alongs:
                        hit = None
                        for sg in segs[i]:
                            if sg[1] - sg[0] >= along - 1e-6:
                                hit = sg; break
                        if hit is None:
                            continue
                        de = box(*st.rect).distance(ent)
                        leftover = (hit[1] - hit[0]) - along
                        u = (ep - 0.5) * (-de / 10.0) - 0.15 * (st.depth - min(w, d)) - 0.04 * leftover + rng.uniform(0, 0.25)
                        if best is None or u > best[0]:
                            best = (u, i, hit, along)
                        break
                if best is None:
                    if partial:
                        unassigned.append(pid); continue
                    return None
                _, i, sg, along = best
                assign[i].append((it, sg[0], along))
                sg[0] += along
            # segunda oportunidad para lo no asignado: franjas de puestos (restos) y pasillos con holgura
            # (un pasillo de 2.5 m puede alojar cabinas de 1.2 m dejando 1.3 m de paso)
            if unassigned:
                extra = []
                for i, st in enumerate(strips_all):
                    if st.kind == "desks":
                        extra.append((i, st, st.depth, desk_seg_ref[i]))
                    # (los pasillos ya no reciben holgura: la holgura es franja de recintos al final de la sección)
                still = []
                for pid in unassigned:
                    it = next(x for x in rooms_items if x[0] == pid)
                    _, mod, w, d, seats = it
                    done = False
                    for i, st, avail_depth, sg in extra:
                        alongs = sorted([a for a, dd in ((w, d), (d, w)) if dd <= avail_depth + 0.05])
                        for along in alongs:
                            for seg in sg:
                                if seg[1] - seg[0] >= along - 1e-6:
                                    assign.setdefault(i, []).append((it, seg[0], along))
                                    seg_list = sg
                                    seg_list[seg_list.index(seg)] = (seg[0] + along, seg[1])
                                    done = True; break
                            if done: break
                        if done: break
                    if not done:
                        still.append(pid)
                unassigned = still
            # puestos: bloques en segmentos de franjas de puestos (2 filas primero)
            need_left = need
            desk_plan = []
            k = 0
            for i, st, sg in sorted(desk_strips, key=lambda t: (-t[1].depth, -sum(b - a for a, b in t[2]))):
                single = st.depth < 3.2 - 0.05
                for (a, b) in sg:
                    pos = a
                    while need_left > 0 and b - pos >= 3.2 - 1e-6:
                        room = b - pos
                        if single:
                            cols = min(3, max(2, int(room // 1.6)), math.ceil(need_left / 1)); seats = min(cols, need_left); w, d = cols * 1.6, 1.6; mod = self.modules["workstation_row"]
                        else:
                            # bench 2×c: el más largo que quepa en el segmento y que no sobre puestos (c ≤ 6 → 9.6 m)
                            cols = 2
                            for cc in (6, 5, 4, 3):
                                if need_left >= 2 * cc and room >= cc * 1.6 - 1e-6:
                                    cols = cc; break
                            if cols * 1.6 > room + 1e-6:
                                break
                            seats = min(2 * cols, need_left); w, d = cols * 1.6, 3.2; mod = self.modules["workstation_cluster"]
                        if w > room + 1e-6:
                            break
                        desk_plan.append((i, (f"{mod.name}_{k + 1}", mod, w, d, seats), pos)); k += 1
                        pos += w + self.aisle; need_left -= seats
                if need_left <= 0:
                    break
            if partial:
                tot_a = sum(w * d for _, _, w, d, _ in rooms_items) or 1.0
                un_a = sum(w * d for pid, _, w, d, _ in rooms_items if pid in unassigned)
                return {"assign": assign, "desk_plan": desk_plan, "rooms_frac": 1 - un_a / tot_a,
                        "seats_frac": min(1.0, (need - max(0, need_left)) / need), "unassigned": unassigned}
            if need_left > 0:
                return None
            return assign, desk_plan


    # ---------- validación dura ---------------------------------------------------------------
    def validate(self, layout: Layout) -> Tuple[bool, List[str], Dict]:
        v: List[str] = []
        counts = {p["module"]: p["count"] for p in self.program["program"]}
        for name, n in counts.items():
            if name == "workstation_cluster":
                continue
            have = sum(1 for p in layout.placements if p.module == name)
            if have != n:
                v.append(f"programa incompleto: {name} {have}/{n}")
        seats = sum(p.seats for p in layout.placements if p.module in ("workstation_cluster", "workstation_row"))
        need = open_workstations(self.program)
        if seats != need:
            v.append(f"puestos open {seats} ≠ {need}")
        usable = self.shell.usable.buffer(0.01)
        for p in layout.placements:
            if not usable.contains(p.poly):
                v.append(f"{p.id} fuera del shell usable")
            if p.poly.intersection(self.entrance_zone).area > 0.05:
                v.append(f"{p.id} invade la zona libre del acceso (r=1.5 m)")
            if any(c.intersects(p.poly) and c.intersection(p.poly).area > 1e-4 for c in self.shell.core):
                v.append(f"{p.id} dentro del núcleo")
            for c in self.cols:
                if c.intersects(p.poly) and c.intersection(p.poly).area > 1e-4:
                    if self.modules[p.module].kind == "room" and p.poly.exterior.distance(c.centroid) <= 0.6:
                        # pilar en la línea de tabique de un recinto (centro a ≤ 0.6 m del borde): el tabique se
                        # alinea al pilar. SUPUESTO arquitectónico registrado en meta.embedded_columns; nunca en puestos.
                        p.meta.setdefault("embedded_columns", [])
                        if list(c.bounds) not in p.meta["embedded_columns"]:
                            p.meta["embedded_columns"].append(list(c.bounds))
                        continue
                    v.append(f"{p.id} intersecta pilar")
        for a_i, a in enumerate(layout.placements):
            for b in layout.placements[a_i + 1:]:
                if a.poly.intersection(b.poly).area > 1e-4:
                    v.append(f"colisión {a.id} × {b.id}")
        circ = analyze(self.grid, layout, self.min_corr)
        v += circ["violations"]
        # restricciones duras declaradas por módulo en la biblioteca (hoy: within_8m_of_entrance)
        if "reach" in circ:
            for n in circ.get("graph", {}).get("nodes", []):
                pl = next((p for p in layout.placements if p.id == n["id"]), None)
                if pl is None:
                    continue
                hard = self.modules[pl.module].spec.get("hard", [])
                if "within_8m_of_entrance" in hard and n.get("path_m", 0.0) > 8.0:
                    v.append(f"{pl.id} a {n['path_m']} m geodésicos del acceso (> 8 m, hard within_8m_of_entrance)")
        return (not v), v, circ

    # ---------- búsqueda ---------------------------------------------------------------------
    def solve(self, n_candidates: int = 120, seed: int = 1, improve_rounds: int = 2, log=print) -> Dict:
        t0 = time.time()
        results = []
        invalid = []          # (clave, layout, circ): se conservan para devolver el mejor parcial sin reconstruir
        valid = 0
        for k in range(n_candidates):
            s = seed * 100000 + k
            lay, notes = self.build_strips(s) if self.strategy == "strips" else self.build(s)
            ok, viol, circ = self.validate(lay)
            if ok:
                valid += 1
                sc = score_layout(lay, self.shell, self.grid, circ, self.zones, self.weights)
                lay.scores = sc; lay.notes = notes
                results.append((sc["total"], s, lay))
            else:
                if log and k < 8:
                    log(f"  cand {k}: inválido → {viol[:3]}")
                key = (len([v for v in viol if v.startswith("programa") or v.startswith("puestos")]), len(viol), k)
                lay.hard_violations = viol; lay.notes = notes
                invalid.append((key, lay, circ))
        results.sort(key=lambda r: -r[0])
        best_before = results[0][0] if results else None
        if not results:
            # ningún candidato válido: devolver el mejor parcial (menos faltas de programa, luego menos violaciones)
            invalid.sort(key=lambda r: r[0])
            runtime = time.time() - t0
            lay, circ = invalid[0][1], invalid[0][2]
            try:
                lay.scores = score_layout(lay, self.shell, self.grid, circ, self.zones, self.weights)
            except Exception as e:  # noqa: BLE001
                lay.scores = {"total": None, "error": str(e)}
            return {"candidate_count": n_candidates, "valid_candidate_count": 0, "runtime_s": round(runtime, 1),
                    "best_score_before_improve": None, "best_score": None, "improve_moves_accepted": 0,
                    "best": lay, "top_scores": [], "seed": seed, "status": "FAIL: sin candidato válido",
                    "best_partial_violations": lay.hard_violations,
                    "invalid_summary": [{"seed": r[0][2], "violations": r[1].hard_violations} for r in invalid]}
        improved = 0
        if results:
            top = results[0][2]
            top, improved = self.improve(top, rounds=improve_rounds, seed=seed)
            ok, viol, circ = self.validate(top)
            assert ok, viol
            top.scores = score_layout(top, self.shell, self.grid, circ, self.zones, self.weights)
            top.circulation_graph = circ["graph"]
            top.circulation_cells = [(int(i), int(j)) for j, i in zip(*np.where(circ["used_corridors"]))]
            top.hard_violations = []
            results[0] = (top.scores["total"], results[0][1], top)
        runtime = time.time() - t0
        return {"candidate_count": n_candidates, "valid_candidate_count": valid, "runtime_s": round(runtime, 1),
                "best_score_before_improve": best_before, "best_score": results[0][0] if results else None,
                "improve_moves_accepted": improved, "best": results[0][2] if results else None,
                "top_scores": [round(r[0], 4) for r in results[:5]], "seed": seed, "status": "OK"}

    def improve(self, layout: Layout, rounds: int = 2, seed: int = 1, tries_per_room: int = 25) -> Tuple[Layout, int]:
        """Mejora local: reubicar cada recinto (no clusters) en otra posición factible si el score sube."""
        rng = random.Random(seed + 7)
        accepted = 0
        ok, _, circ = self.validate(layout)
        cur = score_layout(layout, self.shell, self.grid, circ, self.zones, self.weights)["total"]
        for _ in range(rounds):
            for idx, p in enumerate(layout.placements):
                if p.module == "workstation_cluster":
                    continue
                mod = self.modules[p.module]
                cands = self._room_candidates(mod)
                rng.shuffle(cands)
                others = [q for q in layout.placements if q is not p]
                for (x, y, w, d, rot) in cands[:tries_per_room * 8]:
                    rect = box(x, y, x + w, y + d)
                    if p.module == "reception" and ShPoint(self.shell.entrance).distance(rect) > 8.0:
                        continue
                    if not self._feasible(rect, others, self.zones["spine"]):
                        continue
                    trial = Placement(p.id, p.module, x, y, w, d, rot, p.zone, p.seats)
                    lay2 = Layout(layout.layout_id, layout.template_id, layout.seed, others[:idx] + [trial] + others[idx:])
                    ok2, _, circ2 = self.validate(lay2)
                    if not ok2:
                        continue
                    sc2 = score_layout(lay2, self.shell, self.grid, circ2, self.zones, self.weights)["total"]
                    if sc2 > cur + 1e-4:
                        layout = lay2; cur = sc2; accepted += 1
                        break
        return layout, accepted
