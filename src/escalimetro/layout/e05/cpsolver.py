"""E05 — Solver geométrico híbrido: SpatialStrategy + espina + módulos → placements, con OR-Tools CP-SAT.

Modelo: cada banda tiene slots 1D (intervalos libres a lo largo de su eje). Cada recinto elige EXACTAMENTE
una opción (slot, orientación) = intervalo opcional; los puestos son bloques opcionales por slot con
configuración parametrizada (bench 2×2…2×6, filas 1×2…1×6) y suma EXACTA = brief. NoOverlap por slot.

Las restricciones duras están DENTRO de la búsqueda: programa completo y conteos exactos (una opción por
recinto, Σ puestos = open_workstations del brief), dentro del usable / fuera de núcleo y pilares,
recepción a ≤ 8 m de ruta del acceso (dominio de posiciones restringido por la distancia geodésica sobre
la espina), sin colisiones (NoOverlap), acceso a cada recinto (toda opción toca un pasillo por
construcción). El validador determinista de E04 vuelve a comprobar todo después.

MOST CONSTRAINED FIRST: CP-SAT no necesita un orden, pero las decisiones de estrategia (bandas hondas para
el directorio, zona del acceso para recepción) se fijan antes; el orden de ramificación sugiere primero
recepción, directorio, sala 8, salas 4, privados, comedor/kitchenette, lounge, puestos, cabinas."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from ortools.sat.python import cp_model
from shapely.geometry import box, Point as ShPoint

from ..grid import Grid
from ..model import Layout, Module, Placement, ShellM
from ..program_access import open_workstations
from ..zoning import ZONE_OF_MODULE
from .bands import Band, SpinePlan
from .strategy import SpatialStrategy

ORDER = ["reception", "boardroom_12", "meeting_8", "meeting_4", "private_office", "dining", "kitchenette", "lounge",
         "phone_booth"]
SC = 100                       # escala: 1 unidad = 1 cm
AISLE = 0.9                    # pasillo terciario entre benches
RECEPTION_MAX_PATH = 8.0


@dataclass
class RepairConstraints:
    """Restricciones que el crítico devuelve al solver (nunca coordenadas)."""
    forbid_module_in_band: List[Tuple[str, str]] = field(default_factory=list)      # (module, band_id)
    forbid_module_on_facade: List[str] = field(default_factory=list)                # module
    require_same_slot: List[Tuple[str, str]] = field(default_factory=list)          # (pid_a, pid_b)
    require_adjacent: List[Tuple[str, str]] = field(default_factory=list)           # (pid_a, pid_b)
    weight_overrides: Dict[str, float] = field(default_factory=dict)
    min_seats_on_facade: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self):
        return {"forbid_module_in_band": self.forbid_module_in_band, "forbid_module_on_facade": self.forbid_module_on_facade,
                "require_same_slot": self.require_same_slot, "require_adjacent": self.require_adjacent,
                "weight_overrides": self.weight_overrides, "min_seats_on_facade": self.min_seats_on_facade, "notes": self.notes}


def _room_items(modules: Dict[str, Module], program: Dict) -> List[Tuple[str, Module]]:
    items = []
    for name in ORDER:
        n = next((e["count"] for e in program["program"] if e["module"] == name), 0)
        for k in range(n):
            items.append((f"{name}_{k + 1}", modules[name]))
    return items


def _reach_line(grid: Grid, plan: SpinePlan, shell: ShellM) -> np.ndarray:
    """Distancia geodésica desde el acceso sobre la espina (pasillos + conectores + zócalo)."""
    free = np.zeros_like(grid.free_base)
    for p in plan.all_corridor_polys() + [ShPoint(shell.entrance).buffer(1.5)]:
        grid.paint(p, free, True)
    free &= grid.free_base
    ent = grid.nearest_free(shell.entrance, free)
    return grid.geodesic(free, [ent])


def _band_path(grid: Grid, reach: np.ndarray, b: Band, t: float) -> float:
    """Distancia de ruta acceso → punto t (a lo largo) sobre la línea de puerta de la banda."""
    x0, y0, x1, y1 = b.rect
    if b.axis == "h":
        y = y1 + 0.3 if b.door_side == "N" else y0 - 0.3
        p = (t, y)
    else:
        x = x1 + 0.3 if b.door_side == "E" else x0 - 0.3
        p = (x, t)
    i, j = grid.cell_of(p)
    i, j = min(max(i, 0), grid.nx - 1), min(max(j, 0), grid.ny - 1)
    sub = reach[max(0, j - 1):j + 2, max(0, i - 1):i + 2]
    fin = sub[np.isfinite(sub)]
    return float(fin.min()) if fin.size else float("inf")


def solve(shell: ShellM, grid: Grid, plan: SpinePlan, strat: SpatialStrategy, modules: Dict[str, Module],
          program: Dict, weights: Dict[str, float], repair: Optional[RepairConstraints] = None, seed: int = 1,
          time_limit_s: float = 20.0, workers: int = 2, log=None, seats_mode: str = "exact") -> Dict:
    """seats_mode: 'exact' = Σ puestos == open_workstations_exact (el brief; único modo que puede dar PASS);
    'max' = SONDA DE CAPACIDAD: maximiza puestos con el programa de recintos completo. Un resultado 'max'
    nunca es un candidato válido si no llega al brief; se usa para diagnosticar cuántos puestos caben."""
    t0 = time.time()
    repair = repair or RepairConstraints()
    W = dict(weights); W.update(strat.objective_weights); W.update(repair.weight_overrides)
    need = open_workstations(program)
    rooms = _room_items(modules, program)
    reach = _reach_line(grid, plan, shell)
    bands = [b for b in plan.bands if b.kind in ("work", "rooms", "mixed", "support")]
    m = cp_model.CpModel()
    # ---- opciones de recintos --------------------------------------------------------------------
    opts = {}          # pid -> list of dict(lit, start, end, band, slot, along, deep, rot)
    slot_ivs: Dict[Tuple[str, int], list] = {}
    obj = []
    for pid, mod in rooms:
        mods_allowed = strat.module_regions.get(mod.name, [r for r in {b.region for b in bands}])
        lst = []
        for b in bands:
            if b.kind == "work" and mod.name != "phone_booth":
                continue                                   # bandas de puestos: sólo cabinas como excepción de soporte
            if (mod.name, b.id) in repair.forbid_module_in_band:
                continue
            if mod.name in repair.forbid_module_on_facade and b.facade:
                continue
            for si, (a, c) in enumerate(b.slots_rooms):
                for along, deep in ((mod.w, mod.d), (mod.d, mod.w)):
                    if deep > b.depth + 0.05 or along > (c - a) + 1e-6:
                        continue
                    if not mod.spec.get("rotation_allowed", True) and along != mod.w:
                        continue
                    lo, hi = int(round(a * SC)), int(round((c - along) * SC))
                    if hi < lo:
                        continue
                    lit = m.NewBoolVar(f"{pid}|{b.id}|{si}|{int(along * 10)}")
                    if mod.name == "reception":
                        # dominio duro: alguna celda del frente del recinto a ≤ 8 m de ruta del acceso
                        allowed = []
                        for s in range(lo, hi + 1, 10):
                            best = min(_band_path(grid, reach, b, (s + k) / SC) for k in range(0, int(along * SC) + 1, 40))
                            if best <= RECEPTION_MAX_PATH - 0.4:
                                allowed.append(s)
                        if not allowed:
                            continue
                        start = m.NewIntVarFromDomain(cp_model.Domain.FromValues(allowed), f"s_{lit.Name()}")
                    else:
                        start = m.NewIntVar(lo, hi, f"s_{lit.Name()}")
                    size = int(round(along * SC))
                    end = m.NewIntVar(lo, hi + size, f"e_{lit.Name()}")
                    iv = m.NewOptionalIntervalVar(start, size, end, lit, f"iv_{lit.Name()}")
                    slot_ivs.setdefault((b.id, si), []).append(iv)
                    o = {"lit": lit, "start": start, "band": b, "slot": si, "along": along, "deep": deep,
                         "rot": 0 if along == mod.w else 90, "size": size}
                    lst.append(o)
                    # ---- costos/beneficios de la opción (constantes) ----
                    path = _band_path(grid, reach, b, (a + c) / 2)
                    score = 0.0
                    ep = float(mod.spec.get("entrance_preference", 0.5))
                    score += W.get("entrance_logic", 0.12) * (ep - 0.5) * (-min(path, 40.0) / 10.0)
                    dp = float(mod.spec.get("daylight_preference", 0.5))
                    if b.facade:
                        # recinto cerrado consumiendo fachada: castigo proporcional a los metros; el lounge casi no
                        score -= W.get("facade_preservation", 0.08) * (1.0 - dp) * along / 5.0
                        score += W.get("daylight_utilization", 0.2) * (dp - 0.5) * 0.5
                    if b.region not in mods_allowed:
                        score -= 0.6                       # fuera de la zona que pide la estrategia (blando)
                    zone = ZONE_OF_MODULE.get(mod.name, "")
                    if mod.name in strat.support_zone.get("modules", []) and b.region in strat.support_zone.get("regions", []):
                        score += 0.15
                    obj.append((lit, int(round(score * SC))))
        if not lst:
            return {"status": "INFEASIBLE_MODEL", "reason": f"{pid} sin ninguna opción de colocación", "runtime_s": round(time.time() - t0, 2)}
        m.AddExactlyOne([o["lit"] for o in lst])
        opts[pid] = lst
    # ---- bloques de puestos --------------------------------------------------------------------------
    bench_cfgs = list(strat.bench_preference)
    blocks = []        # dict(lits per cfg, start, band, slot, seats per cfg)
    seat_terms = []
    facade_seat_terms = []
    for b in bands:
        if b.kind not in ("work", "mixed"):
            continue
        rows = 2 if b.depth >= 3.2 - 1e-6 else (1 if b.depth >= 1.6 - 1e-6 else 0)
        if rows == 0:
            continue
        for si, (a, c) in enumerate(b.slots_rooms):
            L = c - a
            K = int((L + AISLE) // (1.6 * 2 + AISLE))
            K = max(0, min(K, 8))
            # pilares embebibles en tabique dentro del slot: bloquean puestos (nunca mobiliario sobre pilar)
            col_ivs = []
            for cb in b.embedded_columns:
                ca, cc = (cb[0], cb[2]) if b.axis == "h" else (cb[1], cb[3])
                if cc > a and ca < c:
                    ca2, cc2 = max(a, ca - 0.05), min(c, cc + 0.05)
                    col_ivs.append(m.NewIntervalVar(int(round(ca2 * SC)), int(round((cc2 - ca2) * SC)), int(round(cc2 * SC)), f"col|{b.id}|{si}|{len(col_ivs)}"))
            desk_group = list(col_ivs)
            for k in range(K):
                blk = {"band": b, "slot": si, "cfgs": []}
                lits = []
                for cfg in bench_cfgs:
                    along = 1.6 * cfg
                    if along + 0.0 > L + 1e-6:
                        continue
                    size = int(round((along + AISLE) * SC))
                    lo, hi = int(round(a * SC)), int(round((c + AISLE - along - AISLE) * SC))
                    if hi < lo:
                        continue
                    lit = m.NewBoolVar(f"blk|{b.id}|{si}|{k}|{cfg}")
                    start = m.NewIntVar(lo, hi, f"bs_{lit.Name()}")
                    end = m.NewIntVar(lo, hi + size, f"be_{lit.Name()}")
                    iv = m.NewOptionalIntervalVar(start, size, end, lit, f"biv_{lit.Name()}")
                    slot_ivs.setdefault((b.id, si), []).append(iv)
                    desk_group.append(iv)
                    seats = rows * cfg
                    if b.region not in strat.module_regions.get("workstation", [b.region]):
                        obj.append((lit, -int(round(0.1 * seats * SC))))
                    blk["cfgs"].append({"lit": lit, "start": start, "cfg": cfg, "seats": seats, "along": along, "rows": rows})
                    lits.append(lit)
                    seat_terms.append((lit, seats))
                    if b.facade:
                        facade_seat_terms.append((lit, seats))
                        obj.append((lit, int(round(W.get("daylight_utilization", 0.2) * seats * 0.25 * SC))))
                    else:
                        obj.append((lit, int(round(-W.get("daylight_utilization", 0.2) * seats * 0.05 * SC))))
                    # preferencia de la estrategia por benches largos (menos pasillos terciarios)
                    obj.append((lit, int(round(0.02 * cfg * SC))))
                if lits:
                    m.AddAtMostOne(lits)
                    blocks.append(blk)
            if col_ivs and len(desk_group) > len(col_ivs):
                m.AddNoOverlap(desk_group)

    if seat_terms and seats_mode == "max":
        m.Add(sum(l * s for l, s in seat_terms) <= need)     # sonda: cuántos caben (nunca más del brief)
    elif seat_terms:
        m.Add(sum(l * s for l, s in seat_terms) == need)     # brief exacto: restricción dura EN la búsqueda
    else:
        return {"status": "INFEASIBLE_MODEL", "reason": "sin bandas de puestos", "runtime_s": round(time.time() - t0, 2)}
    if repair.min_seats_on_facade and facade_seat_terms:
        m.Add(sum(l * s for l, s in facade_seat_terms) >= repair.min_seats_on_facade)
    # ---- no solape por slot ----------------------------------------------------------------------
    for key, ivs in slot_ivs.items():
        m.AddNoOverlap(ivs)
    # ---- relaciones: mismo slot (blando) / adyacencia (reparación dura) ---------------------------
    def same_slot_lits(pa, pb):
        out = []
        by_a = {}
        for o in opts.get(pa, []):
            by_a.setdefault((o["band"].id, o["slot"]), []).append(o)
        for o2 in opts.get(pb, []):
            key = (o2["band"].id, o2["slot"])
            for o1 in by_a.get(key, []):
                both = m.NewBoolVar(f"same|{pa}|{pb}|{key[0]}|{key[1]}|{o1['lit'].Index()}|{o2['lit'].Index()}")
                m.AddBoolAnd([o1["lit"], o2["lit"]]).OnlyEnforceIf(both)
                m.AddBoolOr([o1["lit"].Not(), o2["lit"].Not()]).OnlyEnforceIf(both.Not())
                out.append((both, o1, o2))
        return out

    def pids_of(module):
        return [pid for pid, mod in rooms if mod.name == module]

    for cluster in strat.room_clusters:
        if len(cluster) < 2:
            continue
        for pa in pids_of(cluster[0]):
            for pb in pids_of(cluster[1]):
                for both, o1, o2 in same_slot_lits(pa, pb):
                    obj.append((both, int(round(0.4 * W.get("adjacency_quality", 0.14) / 0.14 * SC))))
    for rel in strat.forbidden_relationships:
        if rel.get("relation") != "adjacent":
            continue
        for pa in pids_of(rel["a"]):
            for pb in pids_of(rel["b"]):
                for both, o1, o2 in same_slot_lits(pa, pb):
                    obj.append((both, -int(round(0.5 * SC))))
    for pa, pb in repair.require_same_slot + repair.require_adjacent:
        trip = same_slot_lits(pa, pb)
        if not trip:
            return {"status": "INFEASIBLE_MODEL", "reason": f"{pa} y {pb} no comparten ningún slot", "runtime_s": round(time.time() - t0, 2)}
        m.AddBoolOr([t[0] for t in trip])
        if (pa, pb) in repair.require_adjacent:
            for both, o1, o2 in trip:
                left = m.NewBoolVar(f"adjL|{both.Index()}"); right = m.NewBoolVar(f"adjR|{both.Index()}")
                m.Add(o2["start"] == o1["start"] + o1["size"]).OnlyEnforceIf([both, left])
                m.Add(o1["start"] == o2["start"] + o2["size"]).OnlyEnforceIf([both, right])
                m.AddBoolOr([left, right]).OnlyEnforceIf(both)
    # ---- objetivo y resolución --------------------------------------------------------------------

    if seats_mode == "max":
        # sonda: primero puestos (peso dominante), después la calidad
        m.Maximize(sum(l * s_ * 20 * SC for l, s_ in seat_terms) + sum(l * c for l, c in obj))
    else:
        m.Maximize(sum(l * c for l, c in obj))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    st = solver.Solve(m)
    runtime = round(time.time() - t0, 2)
    status_name = solver.StatusName(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "runtime_s": runtime, "reason": "CP-SAT no encontró asignación que cumpla las restricciones duras"}
    # ---- extraer placements ---------------------------------------------------------------------
    placements: List[Placement] = []

    def rect_in_band(b: Band, s: float, along: float, deep: float):
        x0, y0, x1, y1 = b.rect
        if b.axis == "h":
            if b.door_side == "N":
                return (s, y1 - deep, along, deep)
            return (s, y0, along, deep)
        if b.door_side == "E":
            return (x1 - deep, s, deep, along)
        return (x0, s, deep, along)

    for pid, mod in rooms:
        o = next(o for o in opts[pid] if solver.Value(o["lit"]))
        b = o["band"]
        deep = o["deep"]
        # recinto se estira hasta el fondo de la banda si sobra ≤ 0.6 m (tabique contra el muro)
        if b.depth - deep <= 0.6 + 1e-6:
            deep = b.depth
        x, y, w, d = rect_in_band(b, solver.Value(o["start"]) / SC, o["along"], deep)
        pl = Placement(pid, mod.name, x, y, w, d, o["rot"], ZONE_OF_MODULE.get(mod.name, ""),
                       seats=0, meta={"band": b.id, "strategy": strat.strategy_id})
        placements.append(pl)
    k = 0
    for blk in blocks:
        for cfgo in blk["cfgs"]:
            if not solver.Value(cfgo["lit"]):
                continue
            b = blk["band"]
            rows, cfg = cfgo["rows"], cfgo["cfg"]
            along, deep = cfgo["along"], 1.6 * rows
            x, y, w, d = rect_in_band(b, solver.Value(cfgo["start"]) / SC, along, deep)
            desks = []
            if b.axis == "h":
                nr, nc = rows, cfg
                for r in range(nr):
                    for cc in range(nc):
                        desks.append((x + cc * 1.6, y + r * 1.6, 1.6, 1.6))
            else:
                nr, nc = cfg, rows
                for r in range(nr):
                    for cc in range(nc):
                        desks.append((x + cc * 1.6, y + r * 1.6, 1.6, 1.6))
            k += 1
            name = "workstation_cluster" if rows == 2 else "workstation_row"
            placements.append(Placement(f"{name}_{k}", name, x, y, w, d, 0 if b.axis == "h" else 90, "WORK",
                                        seats=rows * cfg, desks=desks,
                                        meta={"band": b.id, "config": f"bench {rows}x{cfg}" if rows == 2 else f"row 1x{cfg}",
                                              "strategy": strat.strategy_id}))
    lay = Layout(layout_id=f"{strat.strategy_id}", template_id=program.get("template_id", ""), seed=seed, placements=placements)
    lay.zones = {"spine": plan.to_dict()}
    return {"status": status_name, "runtime_s": runtime, "layout": lay, "objective": solver.ObjectiveValue() / SC,
            "seats": sum(p.seats for p in placements),
            "n_room_options": sum(len(v) for v in opts.values()), "n_desk_blocks": len(blocks)}
