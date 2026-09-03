"""E06 — Human QA loop: operaciones de corrección estructuradas (JSON), re-validación determinista y
medición del HUMAN CORRECTION BURDEN. No es CAD: cada operación es un cambio discreto sobre `layout.json`
que el validador de E04 vuelve a comprobar entero.

Tiempos: si no hay un humano real, los minutos son ESTIMADOS (supuestos por operación declarados en
OP_MINUTES), nunca "medidos"."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from ..model import Layout, Module, Placement
from ..zoning import ZONE_OF_MODULE

OPS = ["ACCEPT", "MOVE", "ROTATE", "SWAP", "RESIZE_TO_VALID_VARIANT", "DELETE", "ADD", "LOCK"]
# supuestos de tiempo por operación en una UI estructurada (minutos) — hipótesis de producto
OP_MINUTES = {"ACCEPT": 0.1, "MOVE": 0.5, "ROTATE": 0.3, "SWAP": 0.5, "RESIZE_TO_VALID_VARIANT": 0.5, "DELETE": 0.2,
              "ADD": 1.0, "LOCK": 0.1}
REVIEW_MINUTES = 1.0          # lectura inicial de la planta antes de operar

OP_SCHEMA = {
    "type": "object", "required": ["op"],
    "properties": {"op": {"type": "string", "enum": OPS}, "target": {"type": "string"},
                   "args": {"type": "object"}, "note": {"type": "string"}},
}


@dataclass
class HumanCorrectionOperation:
    op: str
    target: str = ""
    args: Dict = field(default_factory=dict)
    note: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class HumanCorrectionBurden:
    operation_count: int
    move_count: int
    rotation_count: int
    swap_count: int
    resize_count: int
    add_count: int
    delete_count: int
    locked_elements: int
    accepted_elements: int
    automatic_geometry_preserved_pct: float
    estimated_minutes: float
    minutes_are_estimated: bool
    revalidation_result: Dict
    assumptions: Dict = field(default_factory=lambda: {"op_minutes": dict(OP_MINUTES), "review_minutes": REVIEW_MINUTES})

    def to_dict(self):
        return asdict(self)


def _find(lay: Layout, pid: str) -> Placement:
    p = next((p for p in lay.placements if p.id == pid), None)
    if p is None:
        raise KeyError(f"placement {pid} no existe")
    return p


def _desks_for(p: Placement, rows: int, cols: int, unit: float = 1.6):
    if p.w >= p.d:
        nc, nr = cols, rows
    else:
        nc, nr = rows, cols
    return [(p.x + i * unit, p.y + j * unit, unit, unit) for j in range(nr) for i in range(nc)][:p.seats]


def apply_operations(lay: Layout, ops: List[HumanCorrectionOperation], modules: Dict[str, Module]) -> Tuple[Layout, List[Dict], List[str]]:
    """Aplica operaciones en orden. Devuelve (layout nuevo, log, ids bloqueados). Nunca recalcula nada
    'inteligente': lo que el humano no toca queda exactamente igual."""
    out = copy.deepcopy(lay)
    log, locked = [], []
    for k, o in enumerate(ops):
        entry = {"k": k, "op": o.op, "target": o.target, "args": o.args, "note": o.note}
        if o.op == "ACCEPT":
            _find(out, o.target)
        elif o.op == "LOCK":
            _find(out, o.target); locked.append(o.target)
        elif o.op == "MOVE":
            p = _find(out, o.target)
            before = (p.x, p.y)
            if "x" in o.args and "y" in o.args:
                p.x, p.y = float(o.args["x"]), float(o.args["y"])
            else:
                p.x += float(o.args.get("dx", 0.0)); p.y += float(o.args.get("dy", 0.0))
            if p.desks:
                dx, dy = p.x - before[0], p.y - before[1]
                p.desks = [(x + dx, y + dy, w, d) for (x, y, w, d) in p.desks]
            p.door = None
            entry["from"] = before; entry["to"] = (p.x, p.y)
        elif o.op == "ROTATE":
            p = _find(out, o.target)
            p.w, p.d = p.d, p.w
            p.rot = 90 - p.rot if p.rot in (0, 90) else 0
            if p.desks:
                cols_ = len({round(x, 3) for x, _, _, _ in p.desks}); rows_ = len({round(y, 3) for _, y, _, _ in p.desks})
                p.desks = _desks_for(p, rows_, cols_)
            p.door = None
        elif o.op == "SWAP":
            a, b = _find(out, o.target), _find(out, o.args["other"])
            (a.x, a.y), (b.x, b.y) = (b.x, b.y), (a.x, a.y)
            for p in (a, b):
                p.door = None
                if p.desks:
                    cols_ = len({round(x, 3) for x, _, _, _ in p.desks}); rows_ = len({round(y, 3) for _, y, _, _ in p.desks})
                    p.desks = _desks_for(p, rows_, cols_)
        elif o.op == "RESIZE_TO_VALID_VARIANT":
            p = _find(out, o.target)
            v = o.args["variant"]                    # p. ej. "bench 2x4" | "row 1x3" | "module:<nombre>"
            if v.startswith("bench") or v.startswith("row"):
                rows_, cols_ = [int(t) for t in v.split()[1].split("x")]
                along, deep = 1.6 * cols_, 1.6 * rows_
                if p.w >= p.d:
                    p.w, p.d = along, deep
                else:
                    p.w, p.d = deep, along
                p.seats = rows_ * cols_
                p.module = "workstation_cluster" if rows_ == 2 else "workstation_row"
                p.desks = _desks_for(p, rows_, cols_)
                p.meta["config"] = v
            elif v.startswith("module:"):
                mod = modules[v.split(":", 1)[1]]
                p.module = mod.name; p.w, p.d = (mod.w, mod.d) if p.rot == 0 else (mod.d, mod.w)
                p.zone = ZONE_OF_MODULE.get(mod.name, "")
            p.door = None
        elif o.op == "DELETE":
            p = _find(out, o.target)
            out.placements = [q for q in out.placements if q.id != p.id]
        elif o.op == "ADD":
            a = o.args
            name = a["module"]
            if name in ("workstation_cluster", "workstation_row"):
                rows_, cols_ = a["rows"], a["cols"]
                w, d = (1.6 * cols_, 1.6 * rows_) if a.get("rot", 0) == 0 else (1.6 * rows_, 1.6 * cols_)
                p = Placement(a.get("id", f"{name}_qa{k}"), name, float(a["x"]), float(a["y"]), w, d, a.get("rot", 0), "WORK",
                              seats=rows_ * cols_, meta={"qa_added": True, "config": f"{'bench' if rows_ == 2 else 'row'} {rows_}x{cols_}"})
                p.desks = _desks_for(p, rows_, cols_)
            else:
                mod = modules[name]
                w, d = (mod.w, mod.d) if a.get("rot", 0) == 0 else (mod.d, mod.w)
                p = Placement(a.get("id", f"{name}_qa{k}"), name, float(a["x"]), float(a["y"]), w, d, a.get("rot", 0),
                              ZONE_OF_MODULE.get(name, ""), meta={"qa_added": True})
            out.placements.append(p)
        else:
            raise ValueError(f"operación desconocida {o.op}")
        log.append(entry)
    return out, log, locked


def preserved_pct(before: Layout, after: Layout) -> float:
    """% de placements automáticos que siguen exactamente igual (mismo id, módulo y rectángulo)."""
    if not before.placements:
        return 0.0
    aft = {p.id: (p.module, round(p.x, 3), round(p.y, 3), round(p.w, 3), round(p.d, 3)) for p in after.placements}
    keep = sum(1 for p in before.placements if aft.get(p.id) == (p.module, round(p.x, 3), round(p.y, 3), round(p.w, 3), round(p.d, 3)))
    return round(100.0 * keep / len(before.placements), 1)


def burden(before: Layout, after: Layout, ops: List[HumanCorrectionOperation], revalidation: Dict) -> HumanCorrectionBurden:
    cnt = {o: 0 for o in OPS}
    for o in ops:
        cnt[o.op] += 1
    minutes = REVIEW_MINUTES + sum(OP_MINUTES[o.op] for o in ops)
    return HumanCorrectionBurden(len(ops), cnt["MOVE"], cnt["ROTATE"], cnt["SWAP"], cnt["RESIZE_TO_VALID_VARIANT"], cnt["ADD"],
                                 cnt["DELETE"], cnt["LOCK"], cnt["ACCEPT"], preserved_pct(before, after), round(minutes, 1), True,
                                 revalidation)


# Hipótesis iniciales de producto para el gate asistido (no atribuidas a terceros)
QA_GATES = {"STRONG_ASSISTED_PASS": {"max_minutes": 2.0, "min_preserved_pct": 90.0},
            "ASSISTED_PASS": {"max_minutes": 5.0, "min_preserved_pct": 80.0},
            "WEAK_ASSISTED_PASS": {"max_minutes": 10.0, "min_preserved_pct": 60.0}}


def qa_gate(auto_valid: bool, auto_showable: bool, b: Optional[HumanCorrectionBurden], after_valid: bool, after_showable: bool) -> str:
    if auto_valid and auto_showable:
        return "AUTONOMOUS_PASS"
    if b is None or not after_valid or not after_showable:
        return "FAIL"
    m, p = b.estimated_minutes, b.automatic_geometry_preserved_pct
    for name, th in QA_GATES.items():
        if m <= th["max_minutes"] and p >= th["min_preserved_pct"]:
            return name
    return "FAIL"
