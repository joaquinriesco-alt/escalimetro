"""E05 — Pre-flight de capacidad por estrategia, ANTES de resolver geometría.

Calcula demanda (áreas, metros de banda por clase de profundidad, fachada) contra la oferta de la espina
(bandas con sus slots), detecta el rectángulo más exigente (directorio 7.2×5.0) y dónde cabe, y marca
inviabilidades obvias para no gastar solver en imposibles."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple

from ..model import Module
from ..program_access import open_workstations
from .bands import SpinePlan, Band
from .strategy import SpatialStrategy

CIRC_FACTOR = 0.20        # estimación de circulación como fracción del usable (E04 real: 21 %)


@dataclass
class FeasibilityReport:
    strategy_id: str
    required_module_area_m2: float
    closed_room_area_m2: float
    open_work_area_m2: float
    estimated_circulation_m2: float
    spine_corridor_area_m2: float
    facade_demand_m: float                 # metros de fachada que pedirían los puestos del brief en bench 2×c
    facade_offer_m: float                  # metros de slots de puestos en bandas de fachada
    largest_required_rectangle: List[float]
    boardroom_hosts: List[str]             # bandas donde cabe el directorio
    room_meters_demand: Dict[str, float]   # por clase de profundidad
    room_meters_offer: Dict[str, float]
    seat_capacity_estimate: int
    obvious_infeasibilities: List[str] = field(default_factory=list)
    feasible: bool = True

    def to_dict(self):
        return asdict(self)


def _room_items(modules: Dict[str, Module], program: Dict) -> List[Tuple[str, Module]]:
    items = []
    for e in program["program"]:
        if e["module"] == "workstation_cluster":
            continue
        for k in range(e["count"]):
            items.append((f"{e['module']}_{k + 1}", modules[e["module"]]))
    return items


def preflight(strat: SpatialStrategy, plan: SpinePlan, modules: Dict[str, Module], program: Dict,
              usable_area: float) -> FeasibilityReport:
    rooms = _room_items(modules, program)
    need_seats = open_workstations(program)
    ws = modules["workstation"]
    closed = sum(m.w * m.d for _, m in rooms)
    open_area = need_seats * ws.w * (ws.d + float(ws.spec.get("chair_zone_d", 0.8)))
    big = max(rooms, key=lambda it: it[1].w * it[1].d)[1]
    largest = [max(big.w, big.d), min(big.w, big.d)]
    # oferta: bandas útiles (no pasillo/dead)
    bands = [b for b in plan.bands if b.kind not in ("corridor", "dead")]
    hosts = []
    for b in bands:
        L = max([s[1] - s[0] for s in b.slots_rooms], default=0.0)
        if (b.depth >= largest[1] - 1e-6 and L >= largest[0] - 1e-6) or (b.depth >= largest[0] - 1e-6 and L >= largest[1] - 1e-6):
            hosts.append(b.id)
    # metros de banda por clase de profundidad (demanda: cada recinto pide su lado corto como profundidad)
    classes = [5.0, 4.0, 3.5, 3.0, 1.2]
    demand = {str(c): 0.0 for c in classes}
    for _, m in rooms:
        dmin = min(m.w, m.d)
        cls = next((c for c in classes if dmin >= c - 1e-6), 1.2)
        demand[str(cls)] += max(m.w, m.d)
    offer = {str(c): 0.0 for c in classes}
    for b in bands:
        if b.kind == "work":
            continue                                   # bandas de puestos no alojan recintos (salvo cabinas)
        cls = next((c for c in classes if b.depth >= c - 1e-6), None)
        if cls is None:
            continue
        offer[str(cls)] += sum(s[1] - s[0] for s in b.slots_rooms)
    # capacidad de puestos: bandas 'work'/'mixed' de fachada y no fachada
    seats = 0; facade_offer = 0.0
    for b in bands:
        if b.kind not in ("work", "mixed"):
            continue
        rows = 2 if b.depth >= 3.2 - 1e-6 else (1 if b.depth >= 1.6 - 1e-6 else 0)
        for a, c in b.slots_desks:
            L = c - a
            n_benches = max(0, int((L + 0.9) // (1.6 * 6 + 0.9)))       # benches 2×6 con pasillo 0.9
            rest = L - n_benches * (1.6 * 6 + 0.9)
            cols_ = n_benches * 6 + max(0, int((rest + 1e-6) // 1.6))
            seats += rows * cols_
            if b.facade:
                facade_offer += L
    facade_demand = need_seats / 2 * 1.6 * 1.1        # 2 filas por bench + 10 % de pasillos terciarios
    problems = []
    if not hosts:
        problems.append(f"ninguna banda aloja el rectángulo mayor {largest[0]}×{largest[1]} (directorio)")
    # oferta acumulada por profundidad decreciente vs demanda acumulada
    acc_o = acc_d = 0.0
    for c in classes:
        acc_o += offer[str(c)]; acc_d += demand[str(c)]
        if acc_d > acc_o + 1e-6:
            problems.append(f"faltan {acc_d - acc_o:.1f} m de banda de profundidad ≥ {c} m para los recintos")
            break
    if seats < need_seats:
        problems.append(f"capacidad estimada de puestos {seats} < {need_seats}")
    if closed + open_area + plan.corridor_area_m2 > usable_area:
        problems.append("área de módulos + espina supera el usable")
    rep = FeasibilityReport(strat.strategy_id, round(closed + open_area, 1), round(closed, 1), round(open_area, 1),
                            round(CIRC_FACTOR * usable_area, 1), round(plan.corridor_area_m2, 1), round(facade_demand, 1),
                            round(facade_offer, 1), largest, hosts, demand, {k: round(v, 1) for k, v in offer.items()},
                            seats, problems, feasible=(plan.feasible and not problems))
    return rep
