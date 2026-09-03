"""Planificación por BAHÍAS y FRANJAS (strip planning) — la manera en que un arquitecto ordena una planta:

1. El usable ortogonal se descompone en bahías rectangulares (rectángulo máximo iterativo sobre la rejilla).
2. Cada bahía tiene un lado de fachada (con luz probable) y un lado interior (núcleo / medianero).
3. Una SECCIÓN es una secuencia de franjas paralelas a la fachada, de la fachada hacia adentro:
   puestos (3.2 m) · pasillo (1.2–1.5 m) · recintos (3.0 / 3.5 / 4.0 / 5.0 m).
   Reglas: dos franjas de puestos van separadas por un pasillo; toda franja de recintos toca un pasillo;
   la profundidad total ≤ profundidad de la bahía (el sobrante ensancha el último pasillo).
4. Cada franja se rellena en 1D (estantería): recintos uno junto a otro compartiendo muro; clusters con
   pasillo de 1.2 m entre ellos; los pilares se saltan.
5. La circulación se verifica después con el raster (circulation.analyze): nada se da por supuesto.

Generalidad: sólo asume shell ortogonal (o casi) y módulos rectangulares. Ninguna coordenada del caso.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from shapely.geometry import LineString, Point as ShPoint, box

from .grid import Grid
from .model import Module, Placement, ShellM
from .zoning import ZONE_OF_MODULE

DESK_DEPTH = 3.2
ROW_DEPTH = 1.6
CORR = (1.2, 1.5)
ROOM_DEPTHS = (3.0, 3.5, 4.0, 5.0)


@dataclass
class Bay:
    x0: float
    y0: float
    x1: float
    y1: float
    facade_side: str = ""              # 'S' | 'N' | 'W' | 'E' | '' (lado del rectángulo que da a fachada con luz)
    facade_priority: float = 0.0
    axis: str = ""                     # 'h' | 'v' forzado (elección del candidato); '' = por fachada/lado largo
    ref_side: str = ""                 # lado de referencia de las franjas (calculado en build_strips)
    entrance_side: str = ""            # lado de la bahía sobre el que cae el acceso principal ('' si no)

    @property
    def w(self): return self.x1 - self.x0
    @property
    def h(self): return self.y1 - self.y0
    @property
    def area(self): return self.w * self.h
    @property
    def poly(self): return box(self.x0, self.y0, self.x1, self.y1)

    def strip_axis(self) -> str:
        """Las franjas corren paralelas al lado de referencia: eje forzado; si no, la fachada; si no, el lado largo."""
        if self.axis:
            return self.axis
        if self.facade_side in ("S", "N"):
            return "h"
        if self.facade_side in ("W", "E"):
            return "v"
        return "h" if self.w >= self.h else "v"

    def axis_options(self) -> List[str]:
        """Si la fachada está en el lado corto, ambas orientaciones son razonables."""
        fa = self.strip_axis()
        if self.facade_side in ("W", "E") and self.h < 0.7 * self.w:
            return ["v", "h"]
        if self.facade_side in ("S", "N") and self.w < 0.7 * self.h:
            return ["h", "v"]
        return [fa]

    def strip_depth(self) -> float:
        return self.h if self.strip_axis() == "h" else self.w


def split_bay(bay: "Bay", rng: random.Random, min_len: float = 5.0, step: float = 0.4) -> List["Bay"]:
    """Parte la bahía a lo largo de su eje de franjas en 1–3 segmentos (cortes aleatorios múltiplos de step)."""
    axis = bay.strip_axis()
    L = bay.w if axis == "h" else bay.h
    n = 1 if L < 2 * min_len else rng.choice([1, 2, 2, 3] if L >= 3 * min_len else [1, 2])
    cuts = []
    for _ in range(50):
        cs = sorted(rng.choice(np.arange(min_len, L - min_len + 1e-6, step)) for _ in range(n - 1))
        if all(b - a >= min_len for a, b in zip([0.0] + list(cs), list(cs) + [L])):
            cuts = list(cs); break
    edges = [0.0] + cuts + [L]
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if axis == "h":
            nb = Bay(bay.x0 + a, bay.y0, bay.x0 + b, bay.y1, bay.facade_side, bay.facade_priority)
        else:
            nb = Bay(bay.x0, bay.y0 + a, bay.x1, bay.y0 + b, bay.facade_side, bay.facade_priority)
        # el lado del acceso se hereda sólo por el segmento que lo contiene
        if bay.entrance_side:
            nb.entrance_side = bay.entrance_side if (a <= (0.0) or True) else ""
        out.append(nb)
    return out


@dataclass
class Strip:
    kind: str                          # desks | corridor | rooms
    depth: float
    rect: Tuple[float, float, float, float]   # x0,y0,x1,y1 en m
    axis: str                          # 'h': la franja corre en x; 'v': corre en y


def _max_rectangle(mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Rectángulo máximo de True en mask (histograma). Devuelve (i0, j0, i1, j1) exclusivo."""
    ny, nx = mask.shape
    h = np.zeros(nx, int)
    best = (0, None)
    for j in range(ny):
        h = np.where(mask[j], h + 1, 0)
        stack: List[int] = []
        for i in range(nx + 1):
            cur = h[i] if i < nx else 0
            start = i
            while stack and h[stack[-1]] >= cur:
                k = stack.pop()
                height = h[k]
                start = k
                width = i - k
                if height * width > best[0]:
                    best = (height * width, (k, j - height + 1, i, j + 1))
            stack.append(start) if not stack or h[start] < cur or True else None
            h[start] = cur if start < nx else 0
    return best[1]


def _facade_side(b: "Bay", shell: ShellM):
    best = ("", 0.0)
    for side, seg in (("S", LineString([(b.x0, b.y0), (b.x1, b.y0)])), ("N", LineString([(b.x0, b.y1), (b.x1, b.y1)])),
                      ("W", LineString([(b.x0, b.y0), (b.x0, b.y1)])), ("E", LineString([(b.x1, b.y0), (b.x1, b.y1)]))):
        L = 0.0
        for d in shell.daylight:
            if d.priority >= 0.75:
                e = LineString([d.start, d.end])
                if e.distance(seg) < 0.9:
                    L += e.intersection(seg.buffer(0.9)).length
        if L > best[1]:
            best = (side, L)
    b.facade_side, b.facade_priority = best[0], (0.75 if best[0] else 0.0)


def decompose_bays(grid: Grid, shell: ShellM, min_area_m2: float = 15.0, snap_m: float = 0.35, max_bays: int = 8) -> List[Bay]:
    """Partición rectilínea por líneas de vértice + fusión voraz de rectángulos máximos.

    1. Líneas x e y de todos los vértices del usable (líneas a < snap_m se funden: escalones de 10 cm no
       cuentan). 2. Celdas de la retícula marcadas dentro/fuera por su centroide. 3. Iterativamente, el
       rectángulo de celdas interiores de mayor área (búsqueda exhaustiva sobre pares de líneas, con
       sumas acumuladas) se convierte en bahía y se retira. Los escalones ≥ snap_m (p. ej. 0.7 m de
       fachada) SÍ separan bahías: es lo que permite secciones distintas a cada lado del escalón.
    Restos < min_area quedan libres (la validación dura decide todo después)."""
    from shapely.prepared import prep
    polys = [shell.usable] if shell.usable.geom_type == "Polygon" else list(shell.usable.geoms)
    xs, ys = set(), set()
    for poly in polys:
        for ring in [poly.exterior] + list(poly.interiors):
            for (x, y) in ring.coords:
                xs.add(round(x, 3)); ys.add(round(y, 3))

    def snap(vals):
        vals = sorted(vals); out = [vals[0]]
        for v in vals[1:]:
            if v - out[-1] >= snap_m:
                out.append(v)
        return out
    xs, ys = snap(xs), snap(ys)
    nx, ny = len(xs) - 1, len(ys) - 1
    pp = prep(shell.usable)
    inside = np.zeros((ny, nx), bool)
    for j in range(ny):
        for i in range(nx):
            inside[j, i] = pp.contains(ShPoint((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2))
    inside_full = inside.copy()
    bays: List[Bay] = []
    for _ in range(max_bays):
        best = (0.0, None)
        for j0 in range(ny):
            for j1 in range(j0 + 1, ny + 1):
                colok = inside[j0:j1].all(axis=0)
                i = 0
                while i < nx:
                    if not colok[i]:
                        i += 1; continue
                    k = i
                    while k < nx and colok[k]:
                        k += 1
                    area = (xs[k] - xs[i]) * (ys[j1] - ys[j0])
                    if area > best[0]:
                        best = (area, (i, j0, k, j1))
                    i = k
        if best[1] is None or best[0] < min_area_m2:
            break
        i, j0, k, j1 = best[1]
        bays.append(Bay(xs[i], ys[j0], xs[k], ys[j1]))
        inside[j0:j1, i:k] = False
    # refinamiento: si un corte en una línea de vértice interior permite que un lado crezca ≥ grow_m en
    # profundidad (p. ej. la fachada tiene un escalón de 0.7 m), se parte la bahía y cada mitad crece.
    grow_m = 0.5
    refined: List[Bay] = []
    # celdas disponibles para crecer = libres (no asignadas a ninguna bahía) ∪ las de la propia bahía
    for b in bays:
        _facade_side(b, shell)
        if b.strip_axis() != "h":
            refined.append(b); continue   # el corte en x sólo tiene sentido si las franjas corren en x:
                                          # cortar la profundidad de una bahía con fachada W/E la fragmenta
        own = np.zeros_like(inside)
        bi0, bi1 = xs.index(round(b.x0, 3)), xs.index(round(b.x1, 3)); bj0, bj1 = ys.index(round(b.y0, 3)), ys.index(round(b.y1, 3))
        own[bj0:bj1, bi0:bi1] = True
        avail = inside | own
        done = False
        for xl in xs:
            if not (b.x0 + 3.0 < xl < b.x1 - 3.0):
                continue
            halves = []
            for (ax0, ax1) in ((b.x0, xl), (xl, b.x1)):
                i0, i1 = xs.index(round(ax0, 3)) if round(ax0, 3) in xs else None, xs.index(round(ax1, 3)) if round(ax1, 3) in xs else None
                if i0 is None or i1 is None:
                    halves = None; break
                # extender en y mientras todas las celdas de las columnas i0..i1-1 sean interiores
                j0 = ys.index(round(b.y0, 3)); j1 = ys.index(round(b.y1, 3))
                while j0 > 0 and avail[j0 - 1, i0:i1].all():
                    j0 -= 1
                while j1 < ny and avail[j1, i0:i1].all():
                    j1 += 1
                halves.append(Bay(ax0, ys[j0], ax1, ys[j1]))
            if halves and any((h.h - b.h) >= grow_m for h in halves):
                refined += halves; done = True
                for h in halves:
                    hi0, hi1 = xs.index(round(h.x0, 3)), xs.index(round(h.x1, 3)); hj0, hj1 = ys.index(round(h.y0, 3)), ys.index(round(h.y1, 3))
                    inside[hj0:hj1, hi0:hi1] = False
                break
        if not done:
            refined.append(b)
    bays = refined
    for b in bays:
        _facade_side(b, shell)
        ex, ey = shell.entrance
        if b.y0 - 0.5 <= ey <= b.y1 + 0.5 and b.x0 - 0.5 <= ex <= b.x1 + 0.5:
            dists = {"S": abs(ey - b.y0), "N": abs(ey - b.y1), "W": abs(ex - b.x0), "E": abs(ex - b.x1)}
            side = min(dists, key=dists.get)
            if dists[side] <= 0.6:
                b.entrance_side = side
    return bays


def sections(depth: float, has_facade: bool, max_strips: int = 4, start_corridor: bool = False) -> List[List[Tuple[str, float]]]:
    """Secuencias de franjas (kind, depth) válidas para una bahía de `depth` m."""
    kinds = [("desks", DESK_DEPTH), ("desks", ROW_DEPTH)] + [("corridor", c) for c in CORR] + [("rooms", d) for d in ROOM_DEPTHS]
    out = []
    if depth >= 11.0:
        max_strips = max(max_strips, 5)      # bahías profundas (ala oeste 12.7 m): puestos|pasillo|recintos|pasillo|recintos
    for n in range(1, max_strips + 1):
        for seq in itertools.product(kinds, repeat=n):
            tot = sum(d for _, d in seq)
            if tot > depth + 1e-6 or tot < depth - 4.0:
                continue
            ks = [k for k, _ in seq]
            if "corridor" not in ks:
                continue                         # toda sección lleva pasillo: la circulación no es residual
            if start_corridor and ks[0] != "corridor":
                continue
            ok = True
            for a, b in zip(ks, ks[1:]):
                if a == "corridor" and b == "corridor":
                    ok = False
                if a == "desks" and b == "desks":
                    ok = False
            # recintos deben tocar pasillo; puestos también (o el borde de fachada con pasillo al otro lado)
            for idx, k in enumerate(ks):
                if k in ("rooms", "desks"):
                    nb = [ks[i] for i in (idx - 1, idx + 1) if 0 <= i < n]
                    if "corridor" not in nb:
                        ok = False
            if not has_facade and ks[0] == "desks":
                pass   # permitido pero peor; el score lo castiga
            if ok:
                out.append(list(seq))
    # deduplicar
    seen, res = set(), []
    for s in out:
        key = tuple(s)
        if key not in seen:
            seen.add(key); res.append(s)
    return res


def reference_side(bay: Bay, usable=None) -> str:
    """Lado desde el que se apilan las franjas: la fachada si está en el eje; si no, el lado que es borde
    del shell (muro/medianero) y no un lado abierto hacia otra bahía; si ambos o ninguno, el primero."""
    axis = bay.strip_axis()
    cands = ("S", "N") if axis == "h" else ("W", "E")
    if bay.entrance_side in cands:
        return bay.entrance_side          # el acceso manda: las franjas arrancan con pasillo desde ese lado
    if bay.facade_side in cands:
        return bay.facade_side
    if usable is not None:
        bnd = usable.boundary
        segs = {"S": LineString([(bay.x0, bay.y0), (bay.x1, bay.y0)]), "N": LineString([(bay.x0, bay.y1), (bay.x1, bay.y1)]),
                "W": LineString([(bay.x0, bay.y0), (bay.x0, bay.y1)]), "E": LineString([(bay.x1, bay.y0), (bay.x1, bay.y1)])}
        on = {c: bnd.buffer(0.15).intersection(segs[c]).length / max(segs[c].length, 1e-6) for c in cands}
        best = max(cands, key=lambda c: on[c])
        if on[best] > 0.5:
            return best
    return cands[0]


def build_strips(bay: Bay, section: List[Tuple[str, float]], usable=None) -> List[Strip]:
    """Franjas geométricas desde el lado de referencia hacia adentro."""
    side = reference_side(bay, usable)
    bay.ref_side = side
    tot = sum(d for _, d in section)
    depth_axis = bay.h if side in ("S", "N") else bay.w
    slack = depth_axis - tot
    strips = []
    off = 0.0
    section = list(section)
    # holgura: si la sección termina en pasillo y sobra ≥ 1.2 m, la holgura es una franja de recintos al final
    # (cabinas / recintos pequeños); si no, se suma a la última franja NO pasillo (fondo muerto de recinto o
    # puestos). El pasillo mantiene su ancho nominal: los conectores entre bahías dependen de su posición.
    if slack >= 1.2 and section[-1][0] == "corridor":
        section.append(("rooms", slack)); slack = 0.0
    last_corr = max([i for i, (kk, _) in enumerate(section) if kk == "corridor"], default=-1)
    last_non = max([i for i, (kk, _) in enumerate(section) if kk != "corridor"], default=-1)
    slack_idx = last_non if last_non >= 0 else last_corr
    for idx, (k, d) in enumerate(section):
        dd = d + (slack if idx == slack_idx else 0.0)
        if side == "S":
            rect = (bay.x0, bay.y0 + off, bay.x1, bay.y0 + off + dd); axis = "h"
        elif side == "N":
            rect = (bay.x0, bay.y1 - off - dd, bay.x1, bay.y1 - off); axis = "h"
        elif side == "W":
            rect = (bay.x0 + off, bay.y0, bay.x0 + off + dd, bay.y1); axis = "v"
        else:
            rect = (bay.x1 - off - dd, bay.y0, bay.x1 - off, bay.y1); axis = "v"
        strips.append(Strip(k, dd, rect, axis))
        off += dd
    return strips


def fill_strip(strip: Strip, items: List[Tuple[str, Module, float, float, int]], columns, rng: random.Random,
               from_end: bool = False, gap_desks: float = 1.2, usable=None) -> Tuple[List[Placement], List[Tuple]]:
    """Estantería 1D: coloca items (id, module, w, d, seats) a lo largo de la franja. Devuelve
    (colocados, no colocados). Los pilares se saltan avanzando la posición."""
    x0, y0, x1, y1 = strip.rect
    L = (x1 - x0) if strip.axis == "h" else (y1 - y0)
    depth = (y1 - y0) if strip.axis == "h" else (x1 - x0)
    pos = 0.0
    placed, rest = [], []
    order = items[::-1] if from_end else items
    for (pid, mod, w, d, seats) in order:
        along, deep = (w, d)
        if deep > depth + 0.05:
            along, deep = d, w                       # rotar para caber en profundidad
            if deep > depth + 0.05:
                rest.append((pid, mod, w, d, seats)); continue
        gap = gap_desks if mod.name in ("workstation_cluster", "workstation_row") else 0.0
        placed_ok = False
        for _try in range(40):
            if pos + along > L + 1e-6:
                break
            if strip.axis == "h":
                rx0 = (x0 + pos) if not from_end else (x1 - pos - along)
                rect = box(rx0, y0, rx0 + along, y0 + deep)
                # alinear el recinto al lado interior (fondo de franja) — muro compartido con la franja siguiente
            else:
                ry0 = (y0 + pos) if not from_end else (y1 - pos - along)
                rect = box(x0, ry0, x0 + deep, ry0 + along)
            hit = [c for c in columns if c.intersects(rect) and c.intersection(rect).area > 1e-4]
            # un pilar DENTRO de un recinto cerrado es aceptable si queda a ≤ 0.6 m del borde del recinto
            # (esquina/borde); en puestos, nunca. Se registra en meta del Placement.
            embedded = []
            if mod.kind == "room":
                keep = []
                for c in hit:
                    if rect.exterior.distance(c.centroid) <= 0.6:      # misma regla que Solver.validate
                        embedded.append(c)
                    else:
                        keep.append(c)
                hit = keep
            if not hit and usable is not None and not usable.contains(rect):
                pos += 0.4; continue                       # muesca del shell: avanzar
            if not hit:
                rot = 0 if (along, deep) == (w, d) else 90
                rx, ry = rect.bounds[0], rect.bounds[1]
                pw, pd = rect.bounds[2] - rx, rect.bounds[3] - ry
                desks = []
                if mod.name in ("workstation_cluster", "workstation_row"):
                    rows = 1 if abs(min(pw, pd) - 1.6) < 0.05 else 2
                    cols = max(1, -(-seats // rows))
                    nr, nc = (rows, cols) if abs(pw - cols * 1.6) < 0.05 else (cols, rows)
                    for r in range(nr):
                        for cc in range(nc):
                            if len(desks) < seats:
                                desks.append((rx + cc * (pw / nc), ry + r * (pd / nr), pw / nc, pd / nr))
                pl = Placement(pid, mod.name, rx, ry, pw, pd, rot, ZONE_OF_MODULE.get(mod.name, ""), seats=seats, desks=desks)
                if embedded:
                    pl.meta["embedded_columns"] = [list(c.bounds) for c in embedded]
                placed.append(pl)
                pos += along + gap
                placed_ok = True
                break
            # saltar el pilar
            adv = max((c.bounds[2] if strip.axis == "h" else c.bounds[3]) for c in hit) - (x0 if strip.axis == "h" else y0)
            if from_end:
                adv = (x1 if strip.axis == "h" else y1) - min((c.bounds[0] if strip.axis == "h" else c.bounds[1]) for c in hit)
            pos = max(pos + 0.2, adv + 0.05)
        if not placed_ok:
            rest.append((pid, mod, w, d, seats))
    return placed, rest


# ---------------------------------------------------------------------------------------------
# Planificación 1D con pilares: segmentos libres por franja, empaquetado FFD, colocación a offsets
# ---------------------------------------------------------------------------------------------
def strip_segments(strip: Strip, columns, kind: str, embed_m: float = 0.6, blockers=()) -> List[Tuple[float, float]]:
    """Intervalos [a,b) a lo largo de la franja libres de pilares bloqueantes. En franjas de recintos,
    un pilar cuyo CENTRO está a ≤ embed_m del borde interior o exterior de la franja se considera embebible en la
    línea de tabique (no bloquea). Misma regla que Solver.validate."""
    x0, y0, x1, y1 = strip.rect
    L = (x1 - x0) if strip.axis == "h" else (y1 - y0)
    blocks = []
    srect = box(x0, y0, x1, y1)
    for c in list(columns) + list(blockers):
        cb = c.bounds
        if not (cb[2] > x0 + 1e-6 and cb[0] < x1 - 1e-6 and cb[3] > y0 + 1e-6 and cb[1] < y1 - 1e-6):
            continue
        if c.intersection(srect).area < (0.02 if kind == "rooms" else 1e-4):
            continue
        if kind == "rooms" and c not in blockers:
            # distancia del pilar a los bordes largos de la franja
            cx, cy = c.centroid.x, c.centroid.y
            if strip.axis == "h":
                near_edge = min(abs(cy - y0), abs(y1 - cy))
            else:
                near_edge = min(abs(cx - x0), abs(x1 - cx))
            if near_edge <= embed_m:
                continue
        a = (cb[0] - x0) if strip.axis == "h" else (cb[1] - y0)
        b = (cb[2] - x0) if strip.axis == "h" else (cb[3] - y0)
        blocks.append((max(0.0, a - 0.05), min(L, b + 0.05)))
    blocks.sort()
    segs, cur = [], 0.0
    for a, b in blocks:
        if a > cur + 0.3:
            segs.append((cur, a))
        cur = max(cur, b)
    if L > cur + 0.3:
        segs.append((cur, L))
    return segs


def pack_ffd(segments: List[Tuple[float, float]], lengths: List[Tuple[str, float]], gap: float = 0.0):
    """First-fit-decreasing en segmentos 1D. lengths = [(id, along)]. Devuelve ({id: offset}, no_colocados)."""
    segs = [[a, b] for a, b in segments]
    placed, rest = {}, []
    for pid, along in sorted(lengths, key=lambda t: -t[1]):
        ok = False
        for sg in segs:
            if sg[1] - sg[0] >= along - 1e-6:
                placed[pid] = sg[0]
                sg[0] += along + gap
                ok = True
                break
        if not ok:
            rest.append(pid)
    return placed, rest


def place_at(strip: Strip, item, offset: float, columns, along_hint: float = None) -> Placement:
    """Coloca un item (id, module, w, d, seats) en la franja al offset dado (desde el inicio de la franja)."""
    pid, mod, w, d, seats = item
    x0, y0, x1, y1 = strip.rect
    depth = (y1 - y0) if strip.axis == "h" else (x1 - x0)
    along, deep, rot = (w, d, 0)
    if d > depth + 0.05 or (w <= depth + 0.05 and along_hint is not None and abs(along_hint - d) < 1e-6):
        along, deep, rot = d, w, 90
    if strip.axis == "h":
        rect = box(x0 + offset, y0, x0 + offset + along, y0 + deep)
    else:
        rect = box(x0, y0 + offset, x0 + deep, y0 + offset + along)
    rx, ry = rect.bounds[0], rect.bounds[1]
    pw, pd = rect.bounds[2] - rx, rect.bounds[3] - ry
    desks = []
    if mod.name in ("workstation_cluster", "workstation_row"):
        rows = 1 if abs(min(pw, pd) - 1.6) < 0.05 else 2
        cols = max(1, -(-seats // rows))
        nr, nc = (rows, cols) if abs(pw - cols * 1.6) < 0.05 else (cols, rows)
        for r in range(nr):
            for cc in range(nc):
                if len(desks) < seats:
                    desks.append((rx + cc * (pw / nc), ry + r * (pd / nr), pw / nc, pd / nr))
    pl = Placement(pid, mod.name, rx, ry, pw, pd, rot, ZONE_OF_MODULE.get(mod.name, ""), seats=seats, desks=desks)
    emb = [list(c.bounds) for c in columns if c.intersects(rect) and c.intersection(rect).area > 1e-4]
    if emb:
        pl.meta["embedded_columns"] = emb
    return pl
