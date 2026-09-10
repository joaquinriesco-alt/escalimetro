"""E06 — Barrido de escala: el MISMO brief, los MISMOS módulos y clearances, sobre el shell escalado por
cada factor. Para cada escenario: espina E05 (estrategia dada) + ORTHOGONAL_FREE_PLACEMENT (CP-SAT) en modo
exacto; si no hay solución exacta, sonda de capacidad (máximo de puestos con recintos completos).
Produce ScaleScenario[] + FitRobustnessReport."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import numpy as np

from ...schemas.floorplate import Floorplate
from ..model import Layout, load_modules, load_program
from ..program_access import open_workstations
from ..run import compute_metrics
from ..scoring import score as score_layout
from ..solver import Solver
from ..e05.bands import build_spine
from ..e05.critic import RuleBasedCritic
from ..e05.features import extract_features
from ..e05.strategy import generate_strategies
from . import freeplace as F
from .scale import DEFAULT_FACTORS, ScaleScenario, make_scenario, scaled_shell

# Hipótesis de producto (no son norma ni provienen de terceros): umbrales de clasificación
THRESHOLDS = {"robust_conservative_factor": 0.975, "borderline_band": 0.025, "optimistic_factor": 1.025}


@dataclass
class FitRobustnessReport:
    factors_tested: List[float]
    exact_fit_factors: List[float]
    min_scale_factor_exact_fit: Optional[float]
    pct_scenarios_exact_fit: float
    max_seats_by_factor: Dict[str, int]
    sensitivity: str                      # texto: puestos por 1 % de escala, etc.
    primary_constraint: str
    confidence: str
    classification: str                   # ROBUST_FIT | LIKELY_FIT | BORDERLINE | LIKELY_NO_FIT | ROBUST_NO_FIT
    thresholds: Dict = field(default_factory=lambda: dict(THRESHOLDS))
    notes: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def classify(factors: List[float], exact: List[float], th: Dict = THRESHOLDS) -> str:
    """Clasificación (hipótesis de producto):
    ROBUST_FIT: cabe incluso en escenarios conservadores (factor ≤ 0.975).
    LIKELY_FIT: cabe en el nominal y en ±1 %.
    BORDERLINE: el resultado cambia PASS↔FAIL dentro de ±2.5 % del nominal.
    LIKELY_NO_FIT: sólo cabe con escenarios claramente optimistas (≥ 1.025).
    ROBUST_NO_FIT: no cabe en ningún escenario probado."""
    if not exact:
        return "ROBUST_NO_FIT"
    mn = min(exact)
    if mn <= th["robust_conservative_factor"] + 1e-9:
        return "ROBUST_FIT"
    near = [f for f in factors if abs(f - 1.0) <= 0.01 + 1e-9]
    if all(f in exact for f in near) and 1.0 in exact:
        return "LIKELY_FIT"
    if any(abs(f - 1.0) <= th["borderline_band"] + 1e-9 for f in exact):
        return "BORDERLINE"
    if mn >= th["optimistic_factor"] - 1e-9:
        return "LIKELY_NO_FIT"
    return "BORDERLINE"


def run_scenario(fp: Floorplate, factor: float, strategy_id: str, modules_path: str, program_path: str, out_dir: str,
                 tl_exact: float = 120.0, tl_probe: float = 90.0, seed: int = 1, log=print) -> ScaleScenario:
    t0 = time.time()
    sc = make_scenario(fp, factor)
    shell = scaled_shell(fp, factor)
    mods, clr = load_modules(modules_path)
    prog = load_program(program_path)
    S04 = Solver(shell, mods, prog, clr)
    grid = S04.grid
    feats = extract_features(shell, grid)
    strat = {s.strategy_id: s for s in generate_strategies(feats, int(prog["open_workstations_exact"]))}[strategy_id]
    plan = build_spine(shell, feats, strat, grid)
    els = F.spine_elements(plan)
    brs = F.branch_candidates(shell, feats, els)
    cands, _ = F.generate_candidates(shell, grid, feats, els + brs, mods, prog, strat.bench_preference)
    weights = prog["objectives_weights"]
    critic = RuleBasedCritic()
    result = {"strategy_id": strategy_id, "spine_feasible": plan.feasible, "n_candidates": len(cands), "n_branches": len(brs),
              "usable_m2": round(shell.usable.area, 1)}

    def finish(res, mode):
        lay: Layout = res["layout"]
        lay.layout_id = f"x{factor}_{mode}"
        ok, viol, circ = S04.validate(lay)
        lay.hard_violations = viol
        if circ.get("ok"):
            lay.circulation_graph = circ["graph"]
            lay.circulation_cells = [(int(i), int(j)) for j, i in zip(*np.where(circ["used_corridors"]))]
            lay.scores = score_layout(lay, shell, grid, circ, S04.zones, weights)
        lay.metrics = compute_metrics(lay, S04, circ if circ else None)
        crit = critic.critique(lay, lay.metrics, strat.to_dict())
        d = os.path.join(out_dir, f"x{factor:.3f}")
        os.makedirs(d, exist_ok=True)
        lay.save(os.path.join(d, f"layout_{mode}.json"))
        json.dump(lay.metrics, open(os.path.join(d, f"metrics_{mode}.json"), "w"), indent=2, ensure_ascii=False, default=str)
        json.dump(crit.to_dict(), open(os.path.join(d, f"critique_{mode}.json"), "w"), indent=2, ensure_ascii=False)
        return {"mode": mode, "status": res["status"], "hard_valid": ok, "violations": viol, "seats": res.get("seats"),
                "geometric_score": (lay.scores or {}).get("total"), "architectural_score": crit.architectural_score,
                "broker_showable": crit.broker_showable, "runtime_s": res["runtime_s"], "active_branches": res.get("active_branches"),
                "layout_path": os.path.join(d, f"layout_{mode}.json"), "daylight": (lay.scores or {}).get("objectives", {}).get("daylight_utilization"),
                "circulation_m2": lay.metrics.get("circulation_area_m2")}

    # 1) sonda de capacidad (rápida): cuántos puestos caben con los recintos completos; su solución es la PISTA
    resp = F.solve_free(shell, grid, feats, strat, els + brs, cands, mods, prog, weights, seats_mode="max", seed=seed, time_limit_s=tl_probe)
    result["probe"] = {"status": resp["status"], "runtime_s": resp["runtime_s"]}
    if "layout" in resp:
        result["probe"].update(finish(resp, "probe"))
    probe_seats = resp.get("seats")
    # 2) brief exacto (Σ puestos duro = open_workstations): primero factibilidad pura con la sonda como pista, luego optimización con
    #    la solución factible como pista (dos fases: CP-SAT encuentra antes una solución sin objetivo)
    res = F.solve_free(shell, grid, feats, strat, els + brs, cands, mods, prog, weights, seats_mode="exact", seed=seed,
                       time_limit_s=tl_exact * 0.6, hint=resp.get("layout"), feasibility_only=True)
    result["exact_feasibility_phase"] = {"status": res["status"], "runtime_s": res["runtime_s"]}
    if "layout" in res:
        res2 = F.solve_free(shell, grid, feats, strat, els + brs, cands, mods, prog, weights, seats_mode="exact", seed=seed,
                            time_limit_s=tl_exact * 0.4, hint=res["layout"])
        if "layout" in res2:
            res2["runtime_s"] = round(res["runtime_s"] + res2["runtime_s"], 2)
            res = res2
    result["exact"] = {"status": res["status"], "runtime_s": res["runtime_s"], "reason": res.get("reason")}
    if "layout" in res:
        result["exact"].update(finish(res, "exact"))
        # si CP-SAT halló solución pero el validador la rechaza, no hay fit exacto validado
    exact_valid = bool(result["exact"].get("hard_valid"))
    result["exact_fit"] = exact_valid
    result["max_seats"] = open_workstations(prog) if exact_valid else probe_seats
    result["runtime_total_s"] = round(time.time() - t0, 1)
    sc.layout_result = result
    if log:
        log(f"[sweep] x{factor}: usable {result['usable_m2']} m² · exact {result['exact']['status']} valid={exact_valid} · max_seats {result.get('max_seats')} · {result['runtime_total_s']} s")
    return sc


def robustness(scenarios: List[ScaleScenario]) -> FitRobustnessReport:
    factors = [s.scale_factor for s in scenarios]
    exact = [s.scale_factor for s in scenarios if s.layout_result.get("exact_fit")]
    max_seats = {f"{s.scale_factor:.3f}": int(s.layout_result.get("max_seats") or 0) for s in scenarios}
    # sensibilidad: pendiente de puestos máximos por 1 % de escala (regresión lineal simple)
    xs = np.array(factors); ys = np.array([max_seats[f"{f:.3f}"] for f in factors], float)
    slope = float(np.polyfit(xs, ys, 1)[0]) / 100.0 if len(xs) > 1 else 0.0
    sens = f"≈ {slope:.1f} puestos máximos por cada 1 % de escala (regresión sobre {len(xs)} escenarios)"
    # restricción principal: la violación más frecuente en los escenarios sin fit
    viols = {}
    for s in scenarios:
        if s.layout_result.get("exact_fit"):
            continue
        ex = s.layout_result.get("exact", {})
        items = ex.get("violations") or ([ex["reason"]] if ex.get("reason") else []) or s.layout_result.get("probe", {}).get("violations") or []
        for v in items:
            key = v.split(":")[0] if "candidatos" in v else v.split(" ")[0] + (" open" if v.startswith("puestos") else "")
            if "candidatos" in v:
                key = f"{key}: sin candidato de colocación (rectángulo mayor no cabe junto a la red)"
            viols[key] = viols.get(key, 0) + 1
    primary = max(viols, key=viols.get) if viols else "ninguna"
    cls = classify(factors, exact)
    conf = "LOW" if scenarios and scenarios[0].confidence == "LOW" else "MEDIUM"
    notes = ["Los umbrales de clasificación son hipótesis de producto (THRESHOLDS), no norma ni referencia externa.",
             "Un 'exact fit' es un candidato con hard_valid=true del validador determinista E04 (programa 100 %, los puestos exactos del brief, 0 colisiones, circulación, recepción ≤ 8 m).",
             "max_seats proviene de la sonda de capacidad (recintos completos, maximizar puestos, límite de tiempo): es cota inferior del óptimo si el status no es OPTIMAL."]
    return FitRobustnessReport(factors, exact, min(exact) if exact else None, round(100.0 * len(exact) / max(1, len(factors)), 1),
                               max_seats, sens, primary, conf, cls, notes=notes)
