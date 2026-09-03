"""E07 — Motor de generación por alternativa, con profiling por etapa.

Pipeline (idéntico en A/B/C, sólo cambian grafo/espina/objetivos):

    spine (E05)  →  ramales  →  candidatos (E06 + poda)  →  CP-SAT factibilidad (warm start)
                 →  CP-SAT optimización (early stop)     →  validación determinista (E04)
                 →  crítico (E05)                        →  métricas

KPI E07: < 120 s por alternativa. Se consigue con poda de candidatos dominados, pista (hint) de la fase de
factibilidad, corte anticipado de la optimización y reutilización de la geometría común entre alternativas.
Ninguna de esas medidas relaja una restricción dura: la validación final es la misma de E04."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..grid import Grid
from ..model import Layout, Module, ShellM
from ..run import compute_metrics
from ..scoring import score as score_layout
from ..solver import Solver
from ..e05.bands import build_spine
from ..e05.critic import RuleBasedCritic
from ..e05.features import ShellFeatures, extract_features
from ..e05.strategy import generate_strategies
from ..e06 import freeplace as F
from .strategies import AlternativeSpec


@dataclass
class Profile:
    alternative: str
    candidate_generation_s: float = 0.0
    warm_start_s: float = 0.0
    warm_start_seats: Optional[int] = None
    solver_feasibility_s: float = 0.0
    solver_optimization_s: float = 0.0
    validation_s: float = 0.0
    critic_s: float = 0.0
    render_s: float = 0.0
    spine_s: float = 0.0
    total_s: float = 0.0
    n_candidates_raw: int = 0
    n_candidates_pruned: int = 0
    n_branches: int = 0
    reused_geometry: bool = False
    solutions_found: Optional[int] = None
    candidate_count: int = 0
    valid_candidate_count: int = 0
    chosen_candidate: str = ""
    feasibility_retry: bool = False
    status_feasibility: str = ""
    status_optimization: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class AlternativeResult:
    alt: str
    name: str
    layout: Layout
    hard_valid: bool
    violations: List[str]
    metrics: Dict
    critique: Dict
    profile: Profile
    spine_strategy: str

    def to_dict(self):
        return {"alt": self.alt, "name": self.name, "hard_valid": self.hard_valid, "violations": self.violations,
                "metrics": self.metrics, "critique": self.critique, "profile": self.profile.to_dict(),
                "spine_strategy": self.spine_strategy, "layout_id": self.layout.layout_id}


class Engine:
    """Mantiene el shell, la rejilla y una caché de geometría de candidatos por espina, para que dos
    alternativas que comparten estrategia de circulación no repitan la generación."""

    def __init__(self, shell: ShellM, modules: Dict[str, Module], program: Dict, clearances: Dict, seed: int = 1):
        self.shell, self.modules, self.program, self.seed = shell, modules, program, seed
        self.validator = Solver(shell, modules, program, clearances)     # validador + scoring + raster de E04
        self.grid: Grid = self.validator.grid
        self.feats: ShellFeatures = extract_features(shell, self.grid)
        self.e05_strategies = {s.strategy_id: s for s in generate_strategies(self.feats)}
        self.critic = RuleBasedCritic()
        self._geom_cache: Dict[Tuple[str, tuple], Tuple[list, list, float]] = {}

    # ---------- geometría común (espina + ramales + candidatos podados) ----------------------------
    def geometry_for(self, spec: AlternativeSpec, cap: int = 200, log=None):
        key = (spec.spine_strategy, tuple(spec.bench_cfgs))
        if key in self._geom_cache:
            els, cands, gen_s = self._geom_cache[key]
            return els, cands, gen_s, True
        t0 = time.time()
        strat = self.e05_strategies[spec.spine_strategy]
        plan = build_spine(self.shell, self.feats, strat, self.grid)
        els = F.spine_elements(plan)
        brs = F.branch_candidates(self.shell, self.feats, els, grid=self.grid)
        raw, _ = F.generate_candidates(self.shell, self.grid, self.feats, els + brs, self.modules, self.program,
                                       spec.bench_cfgs, step=1.0)
        cands = F.prune(raw, per_module_cap=cap, log=log)
        gen_s = round(time.time() - t0, 2)
        self._geom_cache[key] = (els + brs, cands, gen_s)
        return els + brs, cands, gen_s, False, len(raw), len(brs)

    def run(self, spec: AlternativeSpec, tl_feas: float = 30.0, tl_opt: float = 40.0, early_stop_s: float = 20.0,
            tl_warm: float = 20.0, cap: int = 200, log=print) -> AlternativeResult:
        t_all = time.time()
        prof = Profile(alternative=spec.alt)
        got = self.geometry_for(spec, cap=cap, log=None)
        if len(got) == 4:
            els, cands, gen_s, reused = got
            raw_n, n_br = len(cands), sum(1 for e in els if not e.fixed)
        else:
            els, cands, gen_s, reused, raw_n, n_br = got
        prof.candidate_generation_s, prof.reused_geometry = (0.0 if reused else gen_s), reused
        prof.n_candidates_raw, prof.n_candidates_pruned, prof.n_branches = raw_n, len(cands), n_br
        strat = self.e05_strategies[spec.spine_strategy]
        weights = dict(self.program["objectives_weights"]); weights.update(spec.weights)
        extra = dict(spec.solver_extra)
        # 1a) warm start: relajación de capacidad (Σ puestos ≤ 40, resto del programa completo). Es sólo una
        #     PISTA para CP-SAT; nunca se devuelve como resultado.
        t = time.time()
        warm = F.solve_free(self.shell, self.grid, self.feats, strat, els, cands, self.modules, self.program, weights,
                            seats_mode="max", seed=self.seed, time_limit_s=tl_warm, extra=extra)
        prof.warm_start_s = round(time.time() - t, 2)
        prof.warm_start_seats = warm.get("seats")
        # 1b) factibilidad exacta (Σ = 40 duro) con esa pista
        t = time.time()
        res = F.solve_free(self.shell, self.grid, self.feats, strat, els, cands, self.modules, self.program, weights,
                           seats_mode="exact", seed=self.seed, time_limit_s=tl_feas, feasibility_only=True, extra=extra,
                           hint=warm.get("layout"))
        if "layout" not in res and res["status"] == "UNKNOWN":
            # reintento adaptativo: el límite de tiempo, no la geometría, agotó la fase (se registra)
            res = F.solve_free(self.shell, self.grid, self.feats, strat, els, cands, self.modules, self.program,
                               weights, seats_mode="exact", seed=self.seed, time_limit_s=tl_feas * 2,
                               feasibility_only=True, extra=extra, hint=warm.get("layout"))
            prof.feasibility_retry = True
        prof.solver_feasibility_s = round(time.time() - t, 2)
        prof.status_feasibility = res["status"]
        if "layout" not in res:
            prof.total_s = round(time.time() - t_all, 2)
            raise RuntimeError(f"{spec.alt}: sin solución factible ({res['status']}: {res.get('reason')})")
        # 2) optimización con la solución factible como pista y corte anticipado
        t = time.time()
        extra_opt = dict(extra); extra_opt["early_stop_after_s"] = early_stop_s
        res2 = F.solve_free(self.shell, self.grid, self.feats, strat, els, cands, self.modules, self.program, weights,
                            seats_mode="exact", seed=self.seed, time_limit_s=tl_opt, hint=res["layout"], extra=extra_opt)
        prof.solver_optimization_s = round(time.time() - t, 2)
        prof.status_optimization = res2.get("status", "")
        prof.solutions_found = res2.get("solutions_found")
        # 3) DOS candidatos por alternativa (factibilidad y optimizado): se validan los dos y gana el mejor
        #    VÁLIDO por score arquitectónico. Un candidato inválido nunca puede ganar.
        t = time.time()
        cands_out = []
        for tag, rr in (("feasibility", res), ("optimized", res2)):
            if "layout" not in rr:
                continue
            lay_c: Layout = rr["layout"]
            lay_c.layout_id = f"OFFICE_403_{spec.alt}_{spec.name}_{tag}"
            lay_c.template_id = self.program.get("template_id", "")
            ok_c, viol_c, circ_c = self.validator.validate(lay_c)
            lay_c.hard_violations = viol_c
            lay_c.circulation_cells = []
            if circ_c.get("ok"):
                lay_c.circulation_graph = circ_c["graph"]
                lay_c.circulation_cells = [(int(i), int(j)) for j, i in zip(*np.where(circ_c["used_corridors"]))]
                lay_c.scores = score_layout(lay_c, self.shell, self.grid, circ_c, self.validator.zones, weights)
            lay_c.metrics = compute_metrics(lay_c, self.validator, circ_c if circ_c else None)
            crit_c = self.critic.critique(lay_c, lay_c.metrics, strat.to_dict())
            cands_out.append({"tag": tag, "ok": ok_c, "viol": viol_c, "layout": lay_c, "crit": crit_c,
                              "geo": (lay_c.scores or {}).get("total") or 0.0})
        prof.validation_s = round(time.time() - t, 2)
        prof.candidate_count = len(cands_out)
        prof.valid_candidate_count = sum(1 for c in cands_out if c["ok"])
        if not cands_out:
            prof.total_s = round(time.time() - t_all, 2)
            raise RuntimeError(f"{spec.alt}: sin candidato")
        cands_out.sort(key=lambda c: (c["ok"], c["crit"].architectural_score, c["geo"]), reverse=True)
        chosen = cands_out[0]
        prof.chosen_candidate = chosen["tag"]
        lay, ok, viol, crit = chosen["layout"], chosen["ok"], chosen["viol"], chosen["crit"]
        lay.layout_id = f"OFFICE_403_{spec.alt}_{spec.name}"
        prof.critic_s = 0.0
        lay.zones = dict(lay.zones or {}); lay.zones["alternative"] = {"alt": spec.alt, "name": spec.name,
                                                                      "graph_id": spec.graph.graph_id,
                                                                      "spine_strategy": spec.spine_strategy}
        prof.total_s = round(time.time() - t_all, 2)
        if log:
            log(f"[e07] {spec.alt} {spec.name}: válido={ok} puestos={sum(p.seats for p in lay.placements)} "
                f"arq={crit.architectural_score} geo={(lay.scores or {}).get('total')} · {prof.total_s} s "
                f"(cand {prof.candidate_generation_s}{' reuso' if reused else ''} · warm {prof.warm_start_s} · "
                f"feas {prof.solver_feasibility_s} · opt {prof.solver_optimization_s})")
        return AlternativeResult(spec.alt, spec.name, lay, ok, viol, lay.metrics, crit.to_dict(), prof, spec.spine_strategy)


def geometric_difference(a: Layout, b: Layout, tol: float = 0.5) -> Dict:
    """Fracción de colocaciones que NO coinciden entre dos alternativas (misma posición ± tol)."""
    A = [(p.module, p.x, p.y, p.w, p.d) for p in a.placements]
    B = [(p.module, p.x, p.y, p.w, p.d) for p in b.placements]
    same = 0
    used = set()
    for m, x, y, w, d in A:
        for k, (m2, x2, y2, w2, d2) in enumerate(B):
            if k in used or m2 != m:
                continue
            if abs(x - x2) <= tol and abs(y - y2) <= tol and abs(w - w2) <= tol and abs(d - d2) <= tol:
                used.add(k); same += 1; break
    n = max(len(A), len(B))
    return {"identical_placements": same, "n": n, "different_pct": round(100.0 * (n - same) / n, 1)}
