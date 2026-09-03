"""E05 — Espina de circulación y bandas, conscientes de pilares, derivadas de la SpatialStrategy.

Para cada región, el patrón de la estrategia (p. ej. work | corr | mixed) se instancia en bandas con
profundidades reales: los pasillos se DESPLAZAN hasta quedar libres de pilares (la banda anterior absorbe
la holgura), y cada banda calcula sus SLOTS (intervalos a lo largo del eje) libres de pilares no
embebibles y dentro del usable real (no sólo del rectángulo de la región: recupera, p. ej., el fondo del ala
oeste que la bahía recorta por una muesca). Entre regiones se crean conectores sólo donde hace falta.
La espina se verifica por raster antes de resolver nada: si el acceso no llega a todos los pasillos, la
estrategia se declara inviable sin gastar solver."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from shapely.geometry import Point as ShPoint, box
from shapely.ops import unary_union
from shapely.prepared import prep

from ..grid import Grid
from ..model import ShellM
from .features import Region, ShellFeatures
from .strategy import PATTERNS, SpatialStrategy

WORK_DEPTHS = (3.2, 1.6)
ROOM_DEPTHS = (5.0, 4.0, 3.5, 3.0)
MIXED_DEPTHS = (5.0, 4.0, 3.5, 3.2, 3.0, 1.6)
EMBED_M = 0.6          # pilar con centro a ≤ 0.6 m del borde de una banda de recintos: va en el tabique


@dataclass
class Band:
    id: str
    region: str
    kind: str                       # work | rooms | mixed | support | corridor
    rect: Tuple[float, float, float, float]
    axis: str                       # 'h': la banda corre en x (apilada en y); 'v': corre en y
    depth: float
    facade: bool = False            # toca la fachada con luz
    door_side: str = ""             # lado de la banda que toca un pasillo (N/S/E/W)
    slots_rooms: List[Tuple[float, float]] = field(default_factory=list)   # intervalos a lo largo (coord absoluta)
    slots_desks: List[Tuple[float, float]] = field(default_factory=list)
    embedded_columns: List[List[float]] = field(default_factory=list)
    width_kind: str = ""            # corridor: primary | secondary

    @property
    def poly(self):
        return box(*self.rect)

    @property
    def along(self) -> Tuple[float, float]:
        return (self.rect[0], self.rect[2]) if self.axis == "h" else (self.rect[1], self.rect[3])

    def to_dict(self):
        return {"id": self.id, "region": self.region, "kind": self.kind, "rect": [round(v, 2) for v in self.rect],
                "axis": self.axis, "depth": round(self.depth, 2), "facade": self.facade, "door_side": self.door_side,
                "slots_rooms": [[round(a, 2), round(b, 2)] for a, b in self.slots_rooms],
                "slots_desks": [[round(a, 2), round(b, 2)] for a, b in self.slots_desks], "width_kind": self.width_kind}


@dataclass
class SpinePlan:
    bands: List[Band]
    corridors: List[Band]
    connectors: List[Tuple[float, float, float, float]]
    entrance_stub: Optional[Tuple[float, float, float, float]]
    feasible: bool
    notes: List[str]
    corridor_area_m2: float = 0.0

    def all_corridor_polys(self):
        return [b.poly for b in self.corridors] + [box(*c) for c in self.connectors] + ([box(*self.entrance_stub)] if self.entrance_stub else [])

    def to_dict(self):
        return {"bands": [b.to_dict() for b in self.bands], "corridors": [b.to_dict() for b in self.corridors],
                "connectors": [[round(v, 2) for v in c] for c in self.connectors],
                "entrance_stub": [round(v, 2) for v in self.entrance_stub] if self.entrance_stub else None,
                "feasible": self.feasible, "notes": self.notes, "corridor_area_m2": round(self.corridor_area_m2, 1)}


def _ref_side(r: Region, pattern: str, entrance: Tuple[float, float]) -> str:
    """Lado desde el que se apilan las bandas."""
    if pattern == "corr_first" and r.facade_side and r.length_m >= 0.7 * r.depth_m:
        return r.facade_side                           # pasillo perimetral: se apila desde la fachada
    if pattern == "corr_first" or not r.facade_side or r.length_m < 0.7 * r.depth_m:
        # región angosta: bandas a lo largo del lado largo; referencia = lado largo más cercano al acceso
        long_sides = ("N", "S") if (r.x1 - r.x0) >= (r.y1 - r.y0) else ("W", "E")
        if r.entrance_side in long_sides:
            return r.entrance_side
        ex, ey = entrance
        d = {"S": abs(ey - r.y0), "N": abs(ey - r.y1), "W": abs(ex - r.x0), "E": abs(ex - r.x1)}
        return min(long_sides, key=lambda s: d[s])
    return r.facade_side


def _stack_rect(r: Region, side: str, off: float, dd: float) -> Tuple[float, float, float, float]:
    if side == "S":
        return (r.x0, r.y0 + off, r.x1, r.y0 + off + dd)
    if side == "N":
        return (r.x0, r.y1 - off - dd, r.x1, r.y1 - off)
    if side == "W":
        return (r.x0 + off, r.y0, r.x0 + off + dd, r.y1)
    return (r.x1 - off - dd, r.y0, r.x1 - off, r.y1)


def _corridor_clear(rect, columns, width: float) -> float:
    """Intrusión máxima de pilares en el pasillo (0 = libre) medida perpendicular al eje."""
    b = box(*rect)
    axis_h = (rect[2] - rect[0]) >= (rect[3] - rect[1])
    worst = 0.0
    for c in columns:
        inter = c.intersection(b)
        if inter.is_empty or inter.area < 1e-3:
            continue
        bb = inter.bounds
        worst = max(worst, (bb[3] - bb[1]) if axis_h else (bb[2] - bb[0]))
    return worst


def _snap_shift(rect, side: str, origin: Tuple[float, float], cell: float) -> float:
    """Desplazamiento extra (≥ 0) para que el borde del pasillo caiga sobre una línea de la rejilla raster:
    un pasillo de 1.2 m alineado a la rejilla de 0.4 contiene exactamente 3 centros de celda; desalineado,
    puede contener 2 y el validador lo declara no transitable. Se ajusta aquí, no en el validador."""
    if side == "S":
        v, o = rect[1], origin[1]
    elif side == "N":
        v, o = rect[3], origin[1]
    elif side == "W":
        v, o = rect[0], origin[0]
    else:
        v, o = rect[2], origin[0]
    k = (v - o) / cell
    frac = k - np.floor(k + 1e-9)
    if frac < 1e-6 or frac > 1 - 1e-6:
        return 0.0
    # S/W: subir al siguiente múltiplo; N/E: bajar al anterior (ambos = alejarse del lado de referencia)
    return (1 - frac) * cell if side in ("S", "W") else frac * cell


def _instantiate(r: Region, pattern: List[str], side: str, columns, prim_w: float, sec_w: float,
                 primary: bool, want_deep_room: bool = False, origin: Tuple[float, float] = (0.0, 0.0),
                 cell: float = 0.4) -> Optional[List[Tuple[str, float]]]:
    """Elige profundidades para el patrón (búsqueda exhaustiva pequeña) y desplaza pasillos fuera de pilares.
    Devuelve [(kind, depth)] o None si no cabe."""
    D = r.depth_m if side == r.facade_side or side in ("S", "N") and (r.y1 - r.y0) <= (r.x1 - r.x0) else None
    D = (r.y1 - r.y0) if side in ("S", "N") else (r.x1 - r.x0)
    choices = []
    for k in pattern:
        if k == "work":
            choices.append([("work", d) for d in WORK_DEPTHS])
        elif k == "rooms":
            choices.append([("rooms", d) for d in ROOM_DEPTHS])
        elif k == "mixed":
            choices.append([("mixed", d) for d in MIXED_DEPTHS])
        elif k == "support":
            choices.append([("support", d) for d in (3.0, 1.6, 1.4)])
        else:
            choices.append([("corridor", prim_w), ("corridor", sec_w)] if primary else [("corridor", sec_w)])
    best, best_score = None, -1.0
    for combo in itertools.product(*choices):
        combo = list(combo)
        # desplazar pasillos fuera de pilares: cada pasillo empieza donde su ancho queda libre
        off, out, ok = 0.0, [], True
        for idx, (k, d) in enumerate(combo):
            if k == "corridor":
                shift = 0.0
                for _ in range(40):
                    rect = _stack_rect(r, side, off + shift, d)
                    extra = _snap_shift(rect, side, origin, cell)
                    if extra > 1e-6:
                        shift += extra; continue
                    intr = _corridor_clear(rect, columns, d)
                    if intr <= 0.08:          # ≤ 8 cm de intrusión: el raster (centros de celda) sigue transitable
                        break
                    shift += 0.1
                else:
                    ok = False; break
                if shift > 0:
                    if not out:
                        out.append(("dead", shift))     # pilares en el muro de referencia: banda muerta (tabique/pilares)
                    else:
                        pk, pd = out[-1]
                        out[-1] = (pk, pd + shift)      # la banda anterior absorbe la holgura
                    off += shift
                out.append((k, d)); off += d
            else:
                out.append((k, d)); off += d
            if off > D + 1e-6:
                ok = False; break
        if not ok:
            continue
        slack = D - off
        # holgura: a la última banda no pasillo (recinto más profundo o puestos con paso)
        for j in range(len(out) - 1, -1, -1):
            if out[j][0] != "corridor":
                out[j] = (out[j][0], out[j][1] + slack); break
        # puntuación: profundidad útil (bandas ≥ 3.0 cuentan entero; filas 1.6 medio) + preferencia por 1ª banda honda
        useful = sum(d if d >= 2.95 else 0.5 * d for k, d in out if k not in ("corridor", "dead"))
        first = next(((k, d) for k, d in out if k != "dead"), ("", 0.0))
        # la intención de la estrategia manda en la 1ª banda: benches (≥ 3.2) si es 'work', recinto (≥ 3.0) si es 'rooms'
        intent = 2.5 if ((first[0] == "work" and first[1] >= 3.2 - 1e-6) or (first[0] in ("rooms", "mixed") and first[1] >= 2.95)) else 0.0
        deep_bonus = 1.5 if (want_deep_room and any(k in ("rooms", "mixed") and d >= 5.0 for k, d in out)) else 0.0
        wide = 0.3 if any(k == "corridor" and d >= prim_w - 1e-6 for k, d in out) else 0.0
        score = useful + intent + deep_bonus + wide - 0.05 * slack
        if score > best_score:
            best, best_score = out, score
    return best


def _slots(band_rect, axis: str, kind: str, usable_p, columns, blockers, step: float = 0.1,
           extend: float = 4.0) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]], List[List[float]]]:
    """Intervalos a lo largo de la banda donde TODA la profundidad está dentro del usable y libre de
    bloqueadores. Extiende más allá del rectángulo de la región mientras el usable lo permita."""
    x0, y0, x1, y1 = band_rect
    if axis == "h":
        a0, a1 = x0 - extend, x1 + extend
    else:
        a0, a1 = y0 - extend, y1 + extend
    n = int(round((a1 - a0) / step))
    ok_rooms = np.zeros(n, bool); ok_desks = np.zeros(n, bool)
    embedded = []
    for i in range(n):
        t = a0 + i * step
        cell = box(t + 0.01, y0 + 0.01, t + step - 0.01, y1 - 0.01) if axis == "h" else box(x0 + 0.01, t + 0.01, x1 - 0.01, t + step - 0.01)
        if not usable_p.contains(cell):
            continue
        r_ok = d_ok = True
        for c in columns:
            if not c.intersects(cell) or c.intersection(cell).area < 1e-6:
                continue
            d_ok = False
            cx, cy = c.centroid.x, c.centroid.y
            near = min(abs(cy - y0), abs(y1 - cy)) if axis == "h" else min(abs(cx - x0), abs(x1 - cx))
            if near > EMBED_M:
                r_ok = False
            elif list(c.bounds) not in embedded:
                embedded.append(list(c.bounds))
        for b in blockers:
            if b.intersects(cell) and b.intersection(cell).area > 1e-6:
                r_ok = d_ok = False
        ok_rooms[i] = r_ok; ok_desks[i] = d_ok

    def runs(mask):
        out, start = [], None
        for i, v in enumerate(mask):
            if v and start is None:
                start = i
            if (not v or i == n - 1) and start is not None:
                end = i if not v else i + 1
                L = (end - start) * step
                if L >= 1.2:
                    out.append((round(a0 + start * step, 2), round(a0 + end * step, 2)))
                start = None
        return out
    return runs(ok_rooms), runs(ok_desks), embedded


def build_spine(shell: ShellM, feats: ShellFeatures, strat: SpatialStrategy, grid: Optional[Grid] = None) -> SpinePlan:
    grid = grid or Grid(shell)
    usable_p = prep(shell.usable.buffer(0.005))
    cols = shell.columns
    prim_w = float(strat.circulation_spine.get("primary_width_m", 1.5))
    sec_w = float(strat.circulation_spine.get("secondary_width_m", 1.2))
    bands: List[Band] = []; corridors: List[Band] = []; notes: List[str] = []
    ex, ey = shell.entrance
    ent_zone = ShPoint(ex, ey).buffer(1.5)
    for r in feats.regions:
        pat_name = strat.circulation_spine["pattern_by_region"].get(r.id, "work_first")
        pattern = PATTERNS[pat_name]
        side = _ref_side(r, pat_name, shell.entrance)
        forced = strat.preflight.get("deep_room_region")
        want_deep = (r.id == forced) if forced else (r.id in strat.client_meeting_zone.get("regions", []) and r.depth_m >= 11.0)
        if want_deep and r.id in strat.circulation_spine["pattern_by_region"] and pat_name in ("work_first", "rooms_first") and forced == r.id:
            pattern = PATTERNS["rooms_first"]     # el directorio pide una banda de recintos honda desde la referencia
        inst = _instantiate(r, pattern, side, cols, prim_w, sec_w, primary=r.has_entrance, want_deep_room=want_deep,
                            origin=(grid.x0, grid.y0), cell=grid.cell)
        if inst is None:
            notes.append(f"región {r.id}: el patrón {pat_name} no cabe en {r.depth_m} m")
            return SpinePlan(bands, corridors, [], None, False, notes)
        axis = "h" if side in ("S", "N") else "v"
        off = 0.0
        made = []
        for k, d in inst:
            rect = _stack_rect(r, side, off, d)
            b = Band(f"{r.id}:{len(made)}:{k}", r.id, k, rect, axis, d, facade=(off < 0.05 and side == r.facade_side and r.facade_len_m > 0))
            if k == "corridor":
                b.width_kind = "primary" if r.has_entrance else "secondary"
                corridors.append(b)
            made.append(b)
            off += d
        # lado de puerta = lado que toca un pasillo dentro de la región
        for i, b in enumerate(made):
            if b.kind == "corridor":
                continue
            nb = [made[j] for j in (i - 1, i + 1) if 0 <= j < len(made) and made[j].kind == "corridor"]
            if nb:
                c = nb[0]
                if axis == "h":
                    b.door_side = "N" if c.rect[1] >= b.rect[3] - 1e-6 else "S"
                else:
                    b.door_side = "E" if c.rect[0] >= b.rect[2] - 1e-6 else "W"
            bands.append(b)
    # ---- conectores: sólo donde la conectividad lo exige ---------------------------------------------
    # Regla 1 (extremos): un pasillo cuyo extremo toca el borde de otra región se prolonga, con su mismo
    #   ancho y sobre su mismo eje, hasta el pasillo más cercano de esa región (si no lo toca ya).
    # Regla 2 (paralelos en el borde): dos pasillos paralelos al borde compartido, uno a cada lado, que se
    #   solapan menos que sec_w se unen con un tramo a lo largo del borde.
    # Regla 3 (paralelos internos): dos pasillos paralelos de una misma región que no quedaron unidos por 1/2
    #   se unen con un pasillo transversal en el extremo más cercano al acceso.
    connectors: List[Tuple[float, float, float, float]] = []
    regs = feats.regions
    reg_of = {r.id: r for r in regs}

    def touches(c: Band, other: Band) -> bool:
        inter = c.poly.buffer(0.05).intersection(other.poly.buffer(0.05))
        if inter.is_empty:
            return False
        bb = inter.bounds
        return min(bb[2] - bb[0], bb[3] - bb[1]) >= sec_w - 0.15

    for c in corridors:
        r = reg_of[c.region]
        ends = [(c.rect[0], "W"), (c.rect[2], "E")] if c.axis == "h" else [(c.rect[1], "S"), (c.rect[3], "N")]
        for coord, side in ends:
            for nb in regs:
                if nb.id == r.id:
                    continue
                edge = {"W": abs(nb.x1 - coord) < 0.05 and abs(r.x0 - coord) < 0.05,
                        "E": abs(nb.x0 - coord) < 0.05 and abs(r.x1 - coord) < 0.05,
                        "S": abs(nb.y1 - coord) < 0.05 and abs(r.y0 - coord) < 0.05,
                        "N": abs(nb.y0 - coord) < 0.05 and abs(r.y1 - coord) < 0.05}[side]
                if not edge:
                    continue
                # ¿el pasillo cae dentro del rango del vecino en su eje transversal?
                if c.axis == "h" and not (nb.y0 - 0.05 <= c.rect[1] and c.rect[3] <= nb.y1 + 0.05):
                    continue
                if c.axis == "v" and not (nb.x0 - 0.05 <= c.rect[0] and c.rect[2] <= nb.x1 + 0.05):
                    continue
                ncs = [o for o in corridors if o.region == nb.id]
                if any(touches(c, o) for o in ncs):
                    continue
                # prolongar hasta el pasillo más cercano del vecino (perpendicular al nuestro)
                best = None
                for o in ncs:
                    if o.axis == c.axis:
                        continue
                    if c.axis == "h":
                        d = (o.rect[0] - coord) if side == "E" else (coord - o.rect[2])
                    else:
                        d = (o.rect[1] - coord) if side == "N" else (coord - o.rect[3])
                    if d >= -0.05 and (best is None or d < best[0]):
                        best = (d, o)
                if best is None:
                    continue
                d, o = best
                if c.axis == "h":
                    x0, x1 = (coord, o.rect[0]) if side == "E" else (o.rect[2], coord)
                    connectors.append((x0, c.rect[1], x1, c.rect[3]))
                else:
                    y0, y1 = (coord, o.rect[1]) if side == "N" else (o.rect[3], coord)
                    connectors.append((c.rect[0], y0, c.rect[2], y1))
    # regla 2
    for i in range(len(regs)):
        for j in range(i + 1, len(regs)):
            a, b = regs[i], regs[j]
            ca = [c for c in corridors if c.region == a.id]; cb = [c for c in corridors if c.region == b.id]
            for pa in ca:
                for pb in cb:
                    if pa.axis != pb.axis:
                        continue
                    if pa.axis == "h" and abs(pa.rect[2] - pb.rect[0]) < 0.05 or pa.axis == "h" and abs(pb.rect[2] - pa.rect[0]) < 0.05:
                        ov = min(pa.rect[3], pb.rect[3]) - max(pa.rect[1], pb.rect[1])
                        if 0 < ov < sec_w - 0.05 or (ov <= 0 and abs(ov) < 8.0):
                            xe = pa.rect[2] if abs(pa.rect[2] - pb.rect[0]) < 0.05 else pa.rect[0]
                            connectors.append((xe - sec_w / 2, min(pa.rect[1], pb.rect[1]), xe + sec_w / 2, max(pa.rect[3], pb.rect[3])))
                    if pa.axis == "v" and abs(pa.rect[3] - pb.rect[1]) < 0.05 or pa.axis == "v" and abs(pb.rect[3] - pa.rect[1]) < 0.05:
                        ov = min(pa.rect[2], pb.rect[2]) - max(pa.rect[0], pb.rect[0])
                        if 0 < ov < sec_w - 0.05 or (ov <= 0 and abs(ov) < 8.0):
                            ye = pa.rect[3] if abs(pa.rect[3] - pb.rect[1]) < 0.05 else pa.rect[1]
                            connectors.append((min(pa.rect[0], pb.rect[0]), ye - sec_w / 2, max(pa.rect[2], pb.rect[2]), ye + sec_w / 2))
    # regla 2b: pasillos paralelos al borde compartido, uno a cada lado, separados por bandas → travesaño
    # perpendicular en la coordenada más cercana al acceso (dentro del tramo compartido)
    for i in range(len(regs)):
        for j in range(i + 1, len(regs)):
            a, b = regs[i], regs[j]
            ca = [c for c in corridors if c.region == a.id]; cb = [c for c in corridors if c.region == b.id]
            if not ca or not cb:
                continue
            if abs(a.y1 - b.y0) < 0.05 or abs(b.y1 - a.y0) < 0.05:
                ye = a.y1 if abs(a.y1 - b.y0) < 0.05 else a.y0
                lo, hi = max(a.x0, b.x0), min(a.x1, b.x1)
                if hi - lo < sec_w:
                    continue
                pa = [c for c in ca if c.axis == "h"]; pb = [c for c in cb if c.axis == "h"]
                if not pa or not pb:
                    continue
                pa = min(pa, key=lambda c: min(abs(c.rect[1] - ye), abs(c.rect[3] - ye)))
                pb = min(pb, key=lambda c: min(abs(c.rect[1] - ye), abs(c.rect[3] - ye)))
                if touches(pa, pb):
                    continue
                already = any(box(*cc).intersects(pa.poly) and box(*cc).intersects(pb.poly) for cc in connectors)
                if already:
                    continue
                xc = min(max(ex, lo + sec_w / 2), hi - sec_w / 2)
                y0 = min(pa.rect[3], pb.rect[3]); y1 = max(pa.rect[1], pb.rect[1])
                connectors.append((xc - sec_w / 2, y0, xc + sec_w / 2, y1))
            elif abs(a.x1 - b.x0) < 0.05 or abs(b.x1 - a.x0) < 0.05:
                xe = a.x1 if abs(a.x1 - b.x0) < 0.05 else a.x0
                lo, hi = max(a.y0, b.y0), min(a.y1, b.y1)
                if hi - lo < sec_w:
                    continue
                pa = [c for c in ca if c.axis == "v"]; pb = [c for c in cb if c.axis == "v"]
                if not pa or not pb:
                    continue
                pa = min(pa, key=lambda c: min(abs(c.rect[0] - xe), abs(c.rect[2] - xe)))
                pb = min(pb, key=lambda c: min(abs(c.rect[0] - xe), abs(c.rect[2] - xe)))
                if touches(pa, pb):
                    continue
                already = any(box(*cc).intersects(pa.poly) and box(*cc).intersects(pb.poly) for cc in connectors)
                if already:
                    continue
                yc = min(max(ey, lo + sec_w / 2), hi - sec_w / 2)
                x0 = min(pa.rect[2], pb.rect[2]); x1 = max(pa.rect[0], pb.rect[0])
                connectors.append((x0, yc - sec_w / 2, x1, yc + sec_w / 2))
    # regla 3: paralelos internos no unidos → transversal en el extremo más cercano al acceso
    allc_tmp = unary_union([c.poly for c in corridors] + [box(*c) for c in connectors])
    comps = list(allc_tmp.geoms) if allc_tmp.geom_type == "MultiPolygon" else [allc_tmp]
    for r in regs:
        cs = [c for c in corridors if c.region == r.id]
        if len(cs) < 2:
            continue
        for k in range(len(cs) - 1):
            c1, c2 = cs[k], cs[k + 1]
            same = any(g.intersects(c1.poly) and g.intersects(c2.poly) for g in comps)
            if same:
                continue
            if c1.axis == "h":
                xe = r.x0 if abs(ex - r.x0) <= abs(ex - r.x1) else r.x1 - sec_w
                connectors.append((xe, min(c1.rect[1], c2.rect[1]), xe + sec_w, max(c1.rect[3], c2.rect[3])))
            else:
                ye = r.y0 if abs(ey - r.y0) <= abs(ey - r.y1) else r.y1 - sec_w
                connectors.append((min(c1.rect[0], c2.rect[0]), ye, max(c1.rect[2], c2.rect[2]), ye + sec_w))
    # alinear conectores a la rejilla (ancho múltiplo de la celda, bordes sobre líneas)
    def snap_conn(c):
        """Alinear a la rejilla si el resultado sigue dentro del usable y libre de pilares; si no, dejar el
        conector tal cual (un tramo de 1.2 m contiene 3 centros de celda en cualquier posición)."""
        x0, y0, x1, y1 = c
        vertical = (x1 - x0) < (y1 - y0)
        cands = []
        for fn in (np.floor, np.ceil):
            if vertical:
                k0 = fn((x0 - grid.x0) / grid.cell + (1e-6 if fn is np.floor else -1e-6)); n = max(3, int(np.ceil((x1 - x0) / grid.cell - 1e-6)))
                cands.append((grid.x0 + k0 * grid.cell, y0, grid.x0 + k0 * grid.cell + n * grid.cell, y1))
            else:
                k0 = fn((y0 - grid.y0) / grid.cell + (1e-6 if fn is np.floor else -1e-6)); n = max(3, int(np.ceil((y1 - y0) / grid.cell - 1e-6)))
                cands.append((x0, grid.y0 + k0 * grid.cell, x1, grid.y0 + k0 * grid.cell + n * grid.cell))
        for cc in cands:
            if usable_p.contains(box(*cc)) and _corridor_clear(cc, cols, 0) <= 0.08:
                return cc
        return c
    connectors = [snap_conn(c) for c in connectors]
    # conectores que cruzan pilares: desplazar 0.4 m a cada lado hasta liberar
    fixed = []
    for c in connectors:
        cand = [c]
        for s in (0.4, -0.4, 0.8, -0.8, 1.2, -1.2):
            if (c[2] - c[0]) < (c[3] - c[1]):
                cand.append((c[0] + s, c[1], c[2] + s, c[3]))
            else:
                cand.append((c[0], c[1] + s, c[2], c[3] + s))
        for cc in cand:
            if _corridor_clear(cc, cols, 0) <= 0.08 and usable_p.contains(box(*cc)):
                fixed.append(cc); break
        else:
            notes.append(f"conector {tuple(round(v, 1) for v in c)} no puede evitar pilares")
            fixed.append(c)
    connectors = fixed
    # ---- acceso: zócalo hasta el pasillo más cercano si el acceso no cae en uno --------------------
    stub = None
    allc = unary_union([c.poly for c in corridors] + [box(*c) for c in connectors])
    if not allc.buffer(0.3).contains(ShPoint(ex, ey)):
        near = allc.boundary.interpolate(allc.boundary.project(ShPoint(ex, ey)))
        x0, x1 = sorted([ex, near.x]); y0, y1 = sorted([ey, near.y])
        if x1 - x0 < prim_w:
            m = (x0 + x1) / 2; x0, x1 = m - prim_w / 2, m + prim_w / 2
        if y1 - y0 < prim_w:
            m = (y0 + y1) / 2; y0, y1 = m - prim_w / 2, m + prim_w / 2
        stub = (x0, y0, x1, y1)
    # ---- slots por banda (bloqueadores = conectores + zócalo + zona del acceso) ----------------------
    blockers = [box(*c) for c in connectors] + ([box(*stub)] if stub else []) + [ent_zone]
    for b in bands:
        others = [rr.poly for rr in feats.regions if rr.id != b.region]
        sr, sd, emb = _slots(b.rect, b.axis, b.kind, usable_p, cols, blockers + others)
        b.slots_rooms, b.slots_desks, b.embedded_columns = sr, sd, emb
    plan = SpinePlan(bands, corridors, connectors, stub, True, notes)
    # ---- verificación raster de la espina (sin mobiliario: sólo pasillos + conectores + zócalo) ------
    free = np.zeros_like(grid.free_base)
    for p in plan.all_corridor_polys() + [ent_zone]:
        grid.paint(p, free, True)
    free &= grid.free_base
    r_cells = max(1, int(round((sec_w / grid.cell - 1) / 2)))
    passable = grid.erode(free, r_cells)
    ent = grid.nearest_free(shell.entrance, passable)
    reach = grid.geodesic(passable, [ent]) if ent is not None else np.full(free.shape, np.inf)
    for c in corridors:
        m = np.zeros_like(free); grid.paint(c.poly, m, True)
        if not np.isfinite(reach[m & passable]).any():
            notes.append(f"pasillo {c.id} no alcanzable desde el acceso por la espina")
            plan.feasible = False
    plan.corridor_area_m2 = float(unary_union(plan.all_corridor_polys()).area)
    return plan
