"""E06 — ORTHOGONAL_FREE_PLACEMENT: segunda representación de colocación, más general que las bandas de E05
y todavía verificable.

Idea: la circulación es una RED = espina fija de E05 (pasillos + conectores) + RAMALES candidatos
(perpendiculares a la espina hacia la fachada o hacia el núcleo, o uniendo pasillos paralelos: quiebres,
T, ramas cortas, lazos). Los recintos y bloques de puestos son RECTÁNGULOS CANDIDATOS finitos, anclados a
cualquier elemento de la red por cualquiera de sus lados y en cualquier orientación (paralelos o
perpendiculares a la fachada, contra el núcleo, a ambos lados de un pasillo). Cada candidato sabe su
polígono, orientación, relación con fachada, distancia al acceso, luz, región, pilares y a qué elementos de
circulación toca. Se descartan ANTES del solver los que cruzan núcleo, pilares (salvo pilar en tabique de
recinto), salen del shell, invaden la zona del acceso o no tocan ningún elemento de circulación.

CP-SAT elige: un candidato por recinto, bloques de puestos con Σ = open_workstations del brief, ramales
activos (bool), NoOverlap2D
entre todos los rectángulos elegidos y los ramales activos; un candidato que sólo toca ramales exige que
alguno esté activo. La red queda conectada por construcción (todo ramal nace en la espina o en otro pasillo
fijo) y el validador determinista de E04 vuelve a verificar puertas y conectividad por raster."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from ortools.sat.python import cp_model
from shapely.geometry import LineString, Point as ShPoint, box
from shapely.ops import unary_union
from shapely.prepared import prep

from ..grid import Grid
from ..model import Layout, Module, Placement, ShellM
from ..program_access import open_workstations
from ..zoning import ZONE_OF_MODULE
from ..e05.bands import SpinePlan, _corridor_clear
from ..e05.features import ShellFeatures
from ..e05.strategy import SpatialStrategy

SC = 100
AISLE = 0.9
EMBED_M = 0.6
ORDER = ["boardroom_12", "reception", "meeting_8", "dining", "private_office", "meeting_4", "lounge", "kitchenette", "phone_booth"]


@dataclass
class Element:
    id: str
    rect: Tuple[float, float, float, float]
    kind: str                # spine | connector | branch
    axis: str                # h | v
    fixed: bool

    @property
    def poly(self):
        return box(*self.rect)


@dataclass
class Candidate:
    cid: int
    module: str
    rect: Tuple[float, float, float, float]
    rot: int
    touches: List[str]                      # ids de elementos de circulación que toca (≥ 0.8 m de contacto)
    touches_fixed: bool
    conflicts: List[str]                    # ramales que cruza
    region: str
    facade_touch: bool
    daylight_m: float                       # distancia a fachada con luz (centro)
    path_m: float                           # distancia de ruta acceso → puerta (sobre espina + ramales, cota inferior)
    embedded_columns: List[List[float]]
    seats: int = 0
    config: str = ""
    rows: int = 0
    cols: int = 0

    @property
    def poly(self):
        return box(*self.rect)

    def to_dict(self):
        return {"cid": self.cid, "module": self.module, "rect": [round(v, 2) for v in self.rect], "rot": self.rot,
                "touches": self.touches, "conflicts": self.conflicts, "region": self.region, "facade_touch": self.facade_touch,
                "daylight_m": round(self.daylight_m, 2), "path_m": round(self.path_m, 1), "embedded_columns": self.embedded_columns,
                "seats": self.seats, "config": self.config}


def spine_elements(plan: SpinePlan) -> List[Element]:
    out = []
    for c in plan.corridors:
        out.append(Element(c.id, c.rect, "spine", c.axis, True))
    for k, c in enumerate(plan.connectors):
        out.append(Element(f"conn{k}", tuple(c), "connector", "v" if (c[2] - c[0]) < (c[3] - c[1]) else "h", True))
    if plan.entrance_stub:
        s = plan.entrance_stub
        out.append(Element("stub", tuple(s), "connector", "v" if (s[2] - s[0]) < (s[3] - s[1]) else "h", True))
    return out


def branch_candidates(shell: ShellM, feats: ShellFeatures, fixed: List[Element], width: float = 1.2,
                      step: float = 2.0, min_len: float = 2.0, grid: Optional[Grid] = None) -> List[Element]:
    """Ramales perpendiculares a cada pasillo fijo, a ambos lados, cada `step` m, hasta el borde del usable o
    hasta otro pasillo fijo (lazo). Libres de pilares (≤ 8 cm), dentro del usable.

    El ancho se ALINEA A LA REJILLA del validador (E07): un pasillo de 1.2 m contiene 3 centros de celda de
    0.4 m sólo si sus bordes caen sobre líneas de la rejilla; desalineado puede contener 2 y el validador lo
    declara no transitable (recinto 'sin acceso'). Alinear aquí evita ese falso negativo."""
    usable_p = prep(shell.usable.buffer(0.005))
    fixed_union = unary_union([e.poly for e in fixed])
    out = []
    k = 0
    cell = grid.cell if grid is not None else 0.4
    gx0, gy0 = (grid.x0, grid.y0) if grid is not None else (0.0, 0.0)
    nw = max(3, int(np.ceil(width / cell - 1e-9)))          # celdas de ancho del ramal

    def snap_lo(v, origin):
        return origin + np.floor((v - origin) / cell + 1e-9) * cell
    for e in fixed:
        if e.kind != "spine":
            continue
        x0, y0, x1, y1 = e.rect
        if e.axis == "h":
            positions = np.arange(x0 + 1.0, x1 - 1.0 - width + 1e-6, step)
            positions = [snap_lo(t, gx0) for t in positions]
            for t in positions:
                for side in (+1, -1):
                    # extender hasta chocar con borde del usable / otro pasillo
                    L = 0.0
                    best = None
                    while L < 20.0:
                        L += 0.4
                        rect = (t, y1, t + nw * cell, y1 + L) if side > 0 else (t, y0 - L, t + nw * cell, y0)
                        if not usable_p.contains(box(*rect)):
                            break
                        if _corridor_clear(rect, shell.columns, width) > 0.08:
                            break
                        best = rect
                        # ¿toca otro pasillo fijo (lazo)? entonces basta
                        probe = box(*rect).buffer(0.05)
                        if probe.intersects(fixed_union.difference(e.poly.buffer(0.05))):
                            break
                    if best and (best[3] - best[1]) >= min_len:
                        out.append(Element(f"br{k}", best, "branch", "v", False)); k += 1
        else:
            positions = np.arange(y0 + 1.0, y1 - 1.0 - width + 1e-6, step)
            positions = [snap_lo(t, gy0) for t in positions]
            for t in positions:
                for side in (+1, -1):
                    L = 0.0
                    best = None
                    while L < 20.0:
                        L += 0.4
                        rect = (x1, t, x1 + L, t + nw * cell) if side > 0 else (x0 - L, t, x0, t + nw * cell)
                        if not usable_p.contains(box(*rect)):
                            break
                        if _corridor_clear(rect, shell.columns, width) > 0.08:
                            break
                        best = rect
                        probe = box(*rect).buffer(0.05)
                        if probe.intersects(fixed_union.difference(e.poly.buffer(0.05))):
                            break
                    if best and (best[2] - best[0]) >= min_len:
                        out.append(Element(f"br{k}", best, "branch", "h", False)); k += 1
    # deduplicar ramales casi iguales
    uniq, seen = [], []
    for b in out:
        key = tuple(round(v, 1) for v in b.rect)
        if key in seen:
            continue
        seen.append(key); uniq.append(b)
    return uniq


def _reach_network(grid: Grid, shell: ShellM, elements: List[Element]) -> np.ndarray:
    free = np.zeros_like(grid.free_base)
    for e in elements:
        grid.paint(e.poly, free, True)
    grid.paint(ShPoint(shell.entrance).buffer(1.5), free, True)
    free &= grid.free_base
    ent = grid.nearest_free(shell.entrance, free)
    return grid.geodesic(free, [ent])


def _contact(a, b) -> float:
    """Largo del contacto entre dos rectángulos (comparten un lado)."""
    inter = box(*a).buffer(0.02).intersection(box(*b).buffer(0.02))
    if inter.is_empty:
        return 0.0
    bb = inter.bounds
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    if min(w, h) > 0.2:
        return 0.0                              # se solapan de verdad, no es contacto
    return max(w, h)


def prune(cands: List[Candidate], per_module_cap: int = 220, log=None) -> List[Candidate]:
    """E07 — poda de candidatos dominados, sin perder diversidad geométrica.

    Un candidato domina a otro del mismo módulo si ocupa CASI la misma posición (misma celda de 1.2 m,
    misma orientación, mismo elemento de circulación principal) y no es mejor en luz ni en ruta. Se
    conserva el mejor de cada celda y, si aún hay más de `per_module_cap`, se muestrea uniformemente el
    resto ordenado por calidad para no sesgar la geometría hacia una sola zona."""
    out: List[Candidate] = []
    for mod in sorted({c.module for c in cands}):
        group = [c for c in cands if c.module == mod]
        best: Dict[tuple, Candidate] = {}
        for c in group:
            key = (round(c.rect[0] / 1.2), round(c.rect[1] / 1.2), c.rot, c.touches[0] if c.touches else "")
            cur = best.get(key)
            if cur is None or (c.daylight_m, c.path_m) < (cur.daylight_m, cur.path_m):
                best[key] = c
        kept = list(best.values())
        if len(kept) > per_module_cap:
            kept.sort(key=lambda c: (c.path_m, c.daylight_m))
            stepk = len(kept) / per_module_cap
            kept = [kept[int(i * stepk)] for i in range(per_module_cap)]
        out += kept
    if log:
        log(f"[free] poda: {len(cands)} → {len(out)} candidatos")
    return out


def generate_candidates(shell: ShellM, grid: Grid, feats: ShellFeatures, elements: List[Element],
                        modules: Dict[str, Module], program: Dict, bench_cfgs: List[int], step: float = 0.8,
                        log=None) -> Tuple[List[Candidate], np.ndarray]:
    usable_p = prep(shell.usable.buffer(0.005))
    fixed = [e for e in elements if e.fixed]
    branches = [e for e in elements if not e.fixed]
    fixed_union = unary_union([e.poly for e in fixed])
    ent_zone = ShPoint(shell.entrance).buffer(1.2)
    reach = _reach_network(grid, shell, elements)
    daylight_edges = [LineString([d.start, d.end]) for d in shell.daylight if d.priority >= 0.75]
    regions = feats.regions

    def region_of(rect):
        c = box(*rect).centroid
        for r in regions:
            if r.poly.buffer(0.3).contains(c):
                return r.id
        return ""

    def path_at(p):
        i, j = grid.cell_of(p)
        i, j = min(max(i, 0), grid.nx - 1), min(max(j, 0), grid.ny - 1)
        sub = reach[max(0, j - 1):j + 2, max(0, i - 1):i + 2]
        fin = sub[np.isfinite(sub)]
        return float(fin.min()) if fin.size else float("inf")

    def daylight_at(rect):
        i, j = grid.cell_of(box(*rect).centroid.coords[0])
        i, j = min(max(i, 0), grid.nx - 1), min(max(j, 0), grid.ny - 1)
        return float(grid.d_daylight[j, i]) if np.isfinite(grid.d_daylight[j, i]) else 99.0

    cands: List[Candidate] = []
    seen = set()

    ubx = shell.usable.bounds

    def try_rect(module: str, rect, rot, is_room: bool, seats=0, config="", rows=0, cols=0):
        # rechazo rápido por caja envolvente antes de cualquier operación de shapely
        if rect[0] < ubx[0] - 0.01 or rect[1] < ubx[1] - 0.01 or rect[2] > ubx[2] + 0.01 or rect[3] > ubx[3] + 0.01:
            return
        key = (module, config, tuple(round(v, 2) for v in rect))
        if key in seen:
            return
        seen.add(key)
        poly = box(*rect)
        if not usable_p.contains(poly):
            return
        if poly.intersects(ent_zone) and poly.intersection(ent_zone).area > 0.05:
            return
        if fixed_union.intersects(poly) and fixed_union.intersection(poly).area > 1e-3:
            return
        emb = []
        for c in shell.columns:
            if c.intersects(poly) and c.intersection(poly).area > 1e-4:
                if is_room and poly.exterior.distance(c.centroid) <= EMBED_M:
                    emb.append([round(v, 2) for v in c.bounds])
                else:
                    return
        touches, tf = [], False
        for e in elements:
            if _contact(rect, e.rect) >= 0.8:
                touches.append(e.id)
                if e.fixed:
                    tf = True
        if not touches:
            return
        conflicts = [b.id for b in branches if b.poly.intersects(poly) and b.poly.intersection(poly).area > 1e-3]
        # puerta = centro del contacto con el elemento fijo más cercano al acceso (o del ramal)
        best_path = float("inf")
        for e in elements:
            if e.id in touches:
                inter = box(*rect).buffer(0.02).intersection(e.poly.buffer(0.02))
                c = inter.centroid
                best_path = min(best_path, path_at((c.x, c.y)))
        ftouch = any(poly.buffer(0.15).intersects(ed) for ed in daylight_edges)
        cands.append(Candidate(len(cands), module, rect, rot, touches, tf, conflicts, region_of(rect), ftouch,
                               daylight_at(rect), best_path, emb, seats, config, rows, cols))

    def positions_along(e: Element, along: float):
        x0, y0, x1, y1 = e.rect
        a0, a1 = (x0, x1) if e.axis == "h" else (y0, y1)
        lo, hi = a0 - along + 1.0, a1 - 1.0
        ts = np.arange(np.floor(lo / 0.4) * 0.4, hi + 1e-6, step)
        return [round(t, 2) for t in ts]

    def anchored_rects(e: Element, along: float, deep: float):
        x0, y0, x1, y1 = e.rect
        for t in positions_along(e, along):
            if e.axis == "h":
                yield (t, y1, t + along, y1 + deep)           # lado N
                yield (t, y0 - deep, t + along, y0)           # lado S
            else:
                yield (x1, t, x1 + deep, t + along)           # lado E
                yield (x0 - deep, t, x0, t + along)           # lado W

    # recintos
    for e in ORDER:
        n = next((p["count"] for p in program["program"] if p["module"] == e), 0)
        if n == 0:
            continue
        mod = modules[e]
        for el in elements:
            for along, deep in ((mod.w, mod.d), (mod.d, mod.w)):
                if not mod.spec.get("rotation_allowed", True) and along != mod.w:
                    continue
                for rect in anchored_rects(el, along, deep):
                    try_rect(e, rect, 0 if along == mod.w else 90, True)
    # puestos: benches 2×c y filas 1×c; el pasillo terciario de 0.9 m se incorpora al rectángulo (a un lado)
    ws = modules["workstation"]
    unit = ws.w
    for el in elements:
        for rows in (2, 1):
            for c in bench_cfgs + [2, 3]:
                if rows == 1 and c > 6:
                    continue
                along, deep = unit * c, (ws.d + float(ws.spec.get("chair_zone_d", 0.8))) * rows
                for rect in anchored_rects(el, along, deep):
                    try_rect("workstation_cluster" if rows == 2 else "workstation_row", rect, 0, False, seats=rows * c,
                             config=f"bench {rows}x{c}" if rows == 2 else f"row 1x{c}", rows=rows, cols=c)
    if log:
        by = {}
        for c in cands:
            by[c.module] = by.get(c.module, 0) + 1
        log(f"[free] candidatos: {len(cands)} · {by}")
    return cands, reach


def solve_free(shell: ShellM, grid: Grid, feats: ShellFeatures, strat: SpatialStrategy, elements: List[Element],
               cands: List[Candidate], modules: Dict[str, Module], program: Dict, weights: Dict[str, float],
               seats_mode: str = "exact", seed: int = 1, time_limit_s: float = 60.0, workers: int = 2,
               reception_max_path: float = 8.0, locks: Optional[List[Dict]] = None, log=None,
               hint: Optional[Layout] = None, feasibility_only: bool = False, extra: Optional[Dict] = None) -> Dict:
    """locks: [{"module","rect"}] rectángulos fijados por QA humano (el solver debe respetarlos).

    extra (E07, opcional): opciones de estrategia que NO relajan ninguna restricción dura —
      max_facade_closed_rooms: nº máximo de recintos cerrados que pueden tocar fachada con luz
      module_max_path: {módulo: metros} cota de ruta acceso→puerta (filtro de dominio, como recepción)
      pair_bonus: [(módulo_a, módulo_b, bonus)] adyacencia premiada/castigada
      row_penalty_per_seat: castigo por asiento en filas 1×c (fomenta benches)
      min_bench_blocks: nº mínimo de bloques de puestos (barrios de trabajo)
      max_bench_blocks: nº máximo de bloques de puestos (compacidad)
      branch_cost_scale: multiplicador del costo de cada ramal de circulación
      stop_after_s_without_improvement: corte anticipado de la fase de optimización"""
    t0 = time.time()
    extra = dict(extra or {})
    W = dict(weights); W.update(strat.objective_weights); W.update(extra.get("weight_overrides", {}))
    need = open_workstations(program)
    m = cp_model.CpModel()
    branches = [e for e in elements if not e.fixed]
    b_lit = {b.id: m.NewBoolVar(f"b_{b.id}") for b in branches}
    lits: Dict[int, cp_model.IntVar] = {}
    xiv, yiv = [], []
    obj = []
    rooms = []
    for name in ORDER:
        n = next((p["count"] for p in program["program"] if p["module"] == name), 0)
        rooms += [(f"{name}_{k + 1}", name) for k in range(n)]
    by_mod: Dict[str, List[Candidate]] = {}
    max_path = {"reception": reception_max_path - 0.4}
    max_path.update({k: float(v) for k, v in extra.get("module_max_path", {}).items()})
    for c in cands:
        if c.module in max_path and c.path_m > max_path[c.module]:
            continue                                            # dominio duro de ruta (recepción y, en E07, otros)
        by_mod.setdefault(c.module, []).append(c)
    # ---- literales y rectángulos --------------------------------------------------------------------
    def add_interval(c: Candidate, lit):
        x0, y0, x1, y1 = [int(round(v * SC)) for v in c.rect]
        xi = m.NewOptionalFixedSizeIntervalVar(x0, x1 - x0, lit, f"x{c.cid}")
        yi = m.NewOptionalFixedSizeIntervalVar(y0, y1 - y0, lit, f"y{c.cid}")
        xiv.append(xi); yiv.append(yi)
        # adyacencia a la red: si no toca elemento fijo, algún ramal tocado debe estar activo
        if not c.touches_fixed:
            m.AddBoolOr([b_lit[t] for t in c.touches if t in b_lit]).OnlyEnforceIf(lit)
        for bid in c.conflicts:
            m.AddImplication(lit, b_lit[bid].Not())

    # recintos: por TIPO de módulo, Σ literales = nº de instancias (sin simetría entre instancias iguales)
    type_lits: Dict[str, List[Tuple[Candidate, object]]] = {}
    counts = {}
    for pid, name in rooms:
        counts[name] = counts.get(name, 0) + 1
    for name, n in counts.items():
        opts = by_mod.get(name, [])
        if len(opts) < n:
            return {"status": "INFEASIBLE_MODEL", "reason": f"{name}: {len(opts)} candidatos para {n} instancias", "runtime_s": round(time.time() - t0, 2)}
        lst = []
        mod = modules[name]
        ep = float(mod.spec.get("entrance_preference", 0.5)); dp = float(mod.spec.get("daylight_preference", 0.5))
        for c in opts:
            lit = m.NewBoolVar(f"{name}|{c.cid}")
            add_interval(c, lit)
            lst.append((c, lit))
            s_ = W.get("entrance_logic", 0.12) * (ep - 0.5) * (-min(c.path_m, 40.0) / 10.0)
            if c.facade_touch:
                s_ -= W.get("facade_preservation", 0.08) * (1.0 - dp) * max(c.rect[2] - c.rect[0], c.rect[3] - c.rect[1]) / 5.0
                s_ += W.get("daylight_utilization", 0.2) * (dp - 0.5) * 0.5
            if c.region and c.region not in strat.module_regions.get(name, [c.region]):
                s_ -= 0.5
            if name in strat.support_zone.get("modules", []) and c.region in strat.support_zone.get("regions", []):
                s_ += 0.15
            obj.append((lit, int(round(s_ * SC))))
        m.Add(sum(l for _, l in lst) == n)
        type_lits[name] = lst
    # puestos
    seat_terms = []
    for c in by_mod.get("workstation_cluster", []) + by_mod.get("workstation_row", []):
        lit = m.NewBoolVar(f"ws|{c.cid}")
        add_interval(c, lit)
        lits[c.cid] = lit
        seat_terms.append((c, lit))
        # luz: cerca de fachada (d < 7 m) bonifica; bench largo bonifica; filas penalizan un poco
        dl = max(0.0, 1.0 - min(c.daylight_m, 7.0) / 7.0)
        row_pen = float(extra.get("row_penalty_per_seat", 0.03))
        s = W.get("daylight_utilization", 0.2) * c.seats * (0.25 * dl - 0.05) + 0.02 * c.cols - (row_pen * c.seats if c.rows == 1 else 0.0)
        if c.region and c.region not in strat.module_regions.get("workstation", [c.region]):
            s -= 0.08 * c.seats
        obj.append((lit, int(round(s * SC))))
    if not seat_terms:
        return {"status": "INFEASIBLE_MODEL", "reason": "sin candidatos de puestos", "runtime_s": round(time.time() - t0, 2)}
    if seats_mode == "max":
        m.Add(sum(l * c.seats for c, l in seat_terms) <= need)
    else:
        m.Add(sum(l * c.seats for c, l in seat_terms) == need)
    # ramales: cuestan área (circulación) → pequeño castigo; ramal activo ocupa espacio (NoOverlap)
    for b in branches:
        x0, y0, x1, y1 = [int(round(v * SC)) for v in b.rect]
        xiv.append(m.NewOptionalFixedSizeIntervalVar(x0, x1 - x0, b_lit[b.id], f"bx{b.id}"))
        yiv.append(m.NewOptionalFixedSizeIntervalVar(y0, y1 - y0, b_lit[b.id], f"by{b.id}"))
        obj.append((b_lit[b.id], -int(round(float(extra.get("branch_cost_scale", 1.0)) * 0.05 * box(*b.rect).area * SC / 5.0))))
    # bloqueos de QA humano: rectángulos ocupados (no candidatos)
    for k, lk in enumerate(locks or []):
        x0, y0, x1, y1 = [int(round(v * SC)) for v in lk["rect"]]
        xiv.append(m.NewFixedSizeIntervalVar(x0, x1 - x0, f"lx{k}")); yiv.append(m.NewFixedSizeIntervalVar(y0, y1 - y0, f"ly{k}"))
    m.AddNoOverlap2D(xiv, yiv)
    # relaciones: clusters (adyacencia = contacto ≥ 0.8) → bonus; prohibidas → castigo
    pair_lits: Dict[Tuple[str, str], list] = {}

    def pair_terms(ma, mb, bonus):
        ca, cb = type_lits.get(ma, []), type_lits.get(mb, [])
        for c1, la in ca:
            for c2, lb in cb:
                if _contact(c1.rect, c2.rect) >= 0.8:
                    both = m.NewBoolVar(f"pair|{ma}|{mb}|{c1.cid}|{c2.cid}")
                    m.AddBoolAnd([la, lb]).OnlyEnforceIf(both)
                    m.AddBoolOr([la.Not(), lb.Not()]).OnlyEnforceIf(both.Not())
                    obj.append((both, int(round(bonus * SC))))
                    pair_lits.setdefault((ma, mb), []).append(both)

    for cl in strat.room_clusters:
        if len(cl) >= 2 and cl[0] in by_mod and cl[1] in by_mod:
            pair_terms(cl[0], cl[1], 0.4)
    for rel in strat.forbidden_relationships:
        if rel.get("relation") == "adjacent" and rel["a"] in by_mod and rel["b"] in by_mod:
            pair_terms(rel["a"], rel["b"], -0.5)
    # ---- opciones E07: restricciones duras adicionales (nunca relajan las del brief) -----------------
    for ma, mb, bonus in extra.get("pair_bonus", []):
        if ma in by_mod and mb in by_mod:
            pair_terms(ma, mb, float(bonus))
    if "max_facade_closed_rooms" in extra:
        fac_lits = [l for name, lst in type_lits.items() if name not in ("reception",)
                    for c, l in lst if c.facade_touch]
        if fac_lits:
            m.Add(sum(fac_lits) <= int(extra["max_facade_closed_rooms"]))
    # adyacencia DURA entre dos módulos (principio común A/B/C: cocina–comedor)
    for ma, mb in extra.get("hard_adjacent_pairs", []):
        if ma not in by_mod or mb not in by_mod:
            continue
        if (ma, mb) not in pair_lits:
            pair_terms(ma, mb, 0.0)
        lst = pair_lits.get((ma, mb), [])
        if not lst:
            return {"status": "INFEASIBLE_MODEL", "reason": f"{ma}+{mb}: ningún par de candidatos es adyacente",
                    "runtime_s": round(time.time() - t0, 2)}
        m.AddBoolOr(lst)
    # luz natural para puestos (principio común): mínimo de asientos a ≤ `facade_seat_dist_m` de fachada con luz
    if "min_facade_seats" in extra:
        dmax = float(extra.get("facade_seat_dist_m", 3.5))
        near = [(c, l) for c, l in seat_terms if c.daylight_m <= dmax]
        if not near:
            return {"status": "INFEASIBLE_MODEL", "reason": "sin candidatos de puestos junto a fachada",
                    "runtime_s": round(time.time() - t0, 2)}
        m.Add(sum(l * c.seats for c, l in near) >= int(extra["min_facade_seats"]))
    blocks_lits = [l for c, l in seat_terms]
    if "min_bench_blocks" in extra and blocks_lits:
        m.Add(sum(blocks_lits) >= int(extra["min_bench_blocks"]))
    if "max_bench_blocks" in extra and blocks_lits:
        m.Add(sum(blocks_lits) <= int(extra["max_bench_blocks"]))
    if seats_mode == "max":
        m.Maximize(sum(l * c.seats * 20 * SC for c, l in seat_terms) + sum(l * v for l, v in obj))
    elif not feasibility_only:
        m.Maximize(sum(l * v for l, v in obj))
    # pista (solución de la sonda u otra corrida): acelera mucho la búsqueda exacta
    if hint is not None:
        hinted = {p.meta.get("cid") for p in hint.placements if p.meta.get("cid") is not None}
        for name, lst in type_lits.items():
            for c, l in lst:
                m.AddHint(l, 1 if c.cid in hinted else 0)
        for c, l in seat_terms:
            m.AddHint(l, 1 if c.cid in hinted else 0)
        act = {b["id"] for b in (hint.zones or {}).get("network", {}).get("branches_active", [])}
        for b in branches:
            m.AddHint(b_lit[b.id], 1 if b.id in act else 0)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    early = float(extra.get("early_stop_after_s", 0) or 0)
    cb = None
    if early > 0:
        class _EarlyStop(cp_model.CpSolverSolutionCallback):
            """Corte anticipado de producto: en cuanto existe una solución y ya se invirtieron `early`
            segundos, se detiene la búsqueda. Se busca un BUEN plan, no el óptimo global demostrado;
            ninguna restricción dura se relaja (toda solución devuelta cumple el modelo completo)."""
            def __init__(self, t_start, budget):
                super().__init__(); self.t0, self.budget, self.n = t_start, budget, 0
            def on_solution_callback(self):
                self.n += 1
                if time.time() - self.t0 >= self.budget:
                    self.StopSearch()
        cb = _EarlyStop(time.time(), early)
    st = solver.Solve(m, cb) if cb else solver.Solve(m)
    runtime = round(time.time() - t0, 2)
    status = solver.StatusName(st)
    n_cands = sum(len(v) for v in by_mod.values())
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status, "runtime_s": runtime, "n_candidates": n_cands, "n_branches": len(branches),
                "reason": "CP-SAT: sin asignación que cumpla las restricciones duras" if status == "INFEASIBLE" else "sin solución en el tiempo"}
    placements: List[Placement] = []
    for name, lst in type_lits.items():
        chosen = [c for c, l in lst if solver.Value(l)]
        for k_, c in enumerate(chosen):
            pid = f"{name}_{k_ + 1}"
            x0, y0, x1, y1 = c.rect
            pl = Placement(pid, name, x0, y0, x1 - x0, y1 - y0, c.rot, ZONE_OF_MODULE.get(name, ""),
                           meta={"cid": c.cid, "touches": c.touches, "region": c.region, "facade_touch": c.facade_touch,
                                 "embedded_columns": c.embedded_columns, "strategy": strat.strategy_id})
            placements.append(pl)
    k = 0
    for c, l in seat_terms:
        if not solver.Value(l):
            continue
        x0, y0, x1, y1 = c.rect
        w, d = x1 - x0, y1 - y0
        # celdas de puesto: filas × columnas según orientación del rectángulo
        unit = 1.6
        nc, nr = int(round(w / unit)), int(round(d / unit))
        desks = [(x0 + i * unit, y0 + j * unit, unit, unit) for j in range(nr) for i in range(nc)][:c.seats]
        k += 1
        placements.append(Placement(f"{c.module}_{k}", c.module, x0, y0, w, d, c.rot, "WORK", seats=c.seats, desks=desks,
                                    meta={"cid": c.cid, "config": c.config, "touches": c.touches, "region": c.region,
                                          "strategy": strat.strategy_id}))
    active = [b for b in branches if solver.Value(b_lit[b.id])]
    lay = Layout(layout_id=f"free_{strat.strategy_id}", template_id=program.get("template_id", ""), seed=seed, placements=placements)
    lay.zones = {"network": {"fixed": [{"id": e.id, "rect": [round(v, 2) for v in e.rect], "kind": e.kind} for e in elements if e.fixed],
                             "branches_active": [{"id": b.id, "rect": [round(v, 2) for v in b.rect]} for b in active],
                             "branches_candidates": len(branches)}}
    return {"status": status, "runtime_s": runtime, "layout": lay,
            "objective": (solver.ObjectiveValue() / SC) if not feasibility_only else None,
            "solutions_found": getattr(cb, "n", None),
            "seats": sum(p.seats for p in placements), "n_candidates": n_cands, "n_branches": len(branches),
            "active_branches": [b.id for b in active]}
