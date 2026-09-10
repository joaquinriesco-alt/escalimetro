"""E25 §10 — experimentos diagnósticos OFFLINE, registrados en E25_EXPERIMENTOS_REGISTRADOS.md.

NO son configuración productiva. Corren con 1 worker, seed fija y límites largos para responder una
pregunta que el presupuesto de producto no puede responder: ¿existe solución?
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from escalimetro.brief import compile_program, load_brief                      # noqa: E402
from escalimetro.case_context import from_case_dir                             # noqa: E402
from escalimetro.layout.e05.bands import build_spine                           # noqa: E402
from escalimetro.layout.e05.features import extract_features                   # noqa: E402
from escalimetro.layout.e05.strategy import generate_strategies                # noqa: E402
from escalimetro.layout.e06 import freeplace as F                              # noqa: E402
from escalimetro.layout.e06.scale import scaled_shell                          # noqa: E402
from escalimetro.layout.e07.strategies import build_alternatives               # noqa: E402
from escalimetro.layout.model import load_modules                              # noqa: E402
from escalimetro.layout.solver import Solver                                   # noqa: E402
from escalimetro.schemas.floorplate import Floorplate                          # noqa: E402

CASE = os.path.join(ROOT, "cases", "001_gps_403")
MODS = os.path.join(ROOT, "program_templates", "modules_office.json")
SEED, WORKERS = 1, 1                       # determinista para diagnóstico
CAP_E24, STEP_E24 = 200, 1.0
CAP_AMPLIO, STEP_FINO = 10 ** 9, 0.8


def contexto(brief_id):
    ctx = from_case_dir(CASE)
    shell = scaled_shell(Floorplate.load(ctx.require_floorplate()), 1.0)
    mods, clr = load_modules(MODS)
    brief = load_brief(os.path.join(ROOT, "briefs", f"BRIEF_{brief_id}.json"))
    prog = compile_program(brief, modules=mods)
    S = Solver(shell, mods, prog, clr)
    feats = extract_features(shell, S.grid)
    e05 = {s.strategy_id: s for s in generate_strategies(feats, brief.open_workstations)}
    return shell, S.grid, feats, mods, brief, prog, e05, build_alternatives(prog)


def geometria(shell, grid, feats, mods, prog, spec, e05, step, cap):
    strat = e05[spec.spine_strategy]
    plan = build_spine(shell, feats, strat, grid)
    els = F.spine_elements(plan)
    brs = F.branch_candidates(shell, feats, els, grid=grid)
    gs, ps = {}, {}
    raw, _ = F.generate_candidates(shell, grid, feats, els + brs, mods, prog, spec.bench_cfgs,
                                   step=step, stats=gs)
    dem = {q["module"]: int(q["count"]) for q in prog["program"]}
    cands = raw if cap >= 10 ** 8 else F.prune(raw, per_module_cap=cap, stats=ps, demand=dem)
    return strat, els + brs, cands, gs, ps


def correr(exp, brief_id, alt, step, cap, tl, modo, feasibility_only):
    shell, grid, feats, mods, brief, prog, e05, specs = contexto(brief_id)
    spec = next(s for s in specs if s.alt == alt)
    t0 = time.time()
    strat, els, cands, gs, ps = geometria(shell, grid, feats, mods, prog, spec, e05, step, cap)
    t_gen = round(time.time() - t0, 2)
    weights = dict(prog["objectives_weights"]); weights.update(spec.weights)
    st = {}
    res = F.solve_free(shell, grid, feats, strat, els, cands, mods, prog, weights,
                       seats_mode=modo, seed=SEED, time_limit_s=tl, workers=WORKERS,
                       feasibility_only=feasibility_only, extra=dict(spec.solver_extra), stats=st)
    return {
        "experimento": exp, "brief": brief_id, "alt": alt,
        "config": {"step": step, "cap": None if cap >= 10 ** 8 else cap, "poda": cap < 10 ** 8,
                   "seats_mode": modo, "feasibility_only": feasibility_only,
                   "time_limit_s": tl, "workers": WORKERS, "seed": SEED},
        "puestos_solicitados": brief.open_workstations,
        "candidatos_brutos": gs.get("brutos_total"),
        "candidatos_al_solver": len(cands),
        "candidatos_por_modulo": st.get("candidatos_por_modulo_en_modelo"),
        "generacion_runtime_s": t_gen,
        "status": res.get("status"),
        "pre_solver_reject": res.get("pre_solver_reject"),
        "reason": res.get("reason"),
        "seats_alcanzados": res.get("seats"),
        "best_objective": st.get("best_objective"),
        "best_bound": st.get("best_bound"),
        "n_variables": st.get("n_variables"), "n_constraints": st.get("n_constraints"),
        "wall_time_s": st.get("wall_time_s"), "deterministic_time": st.get("deterministic_time"),
        "num_branches_explorados": st.get("num_branches_explorados"),
        "num_conflicts": st.get("num_conflicts"),
        "runtime_total_s": round(time.time() - t0, 2),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, choices=["EXP1", "EXP2", "EXP3"])
    ap.add_argument("--tag", default="", help="sufijo del archivo de salida (PRE/POST)")
    ap.add_argument("--briefs", default="DENSO,EJECUTIVO")
    ap.add_argument("--alts", default="A,B,C")
    ap.add_argument("--tl", type=float, default=600.0)
    args = ap.parse_args(argv)
    cfg = {"EXP1": (STEP_E24, CAP_E24, "max", False),
           "EXP2": (STEP_FINO, CAP_AMPLIO, "max", False),
           "EXP3": (STEP_FINO, CAP_AMPLIO, "exact", True)}[args.exp]
    filas = []
    for b in args.briefs.split(","):
        for a in args.alts.split(","):
            print(f"\n##### {args.exp} · {b} / {a} #####", flush=True)
            f = correr(args.exp, b, a, cfg[0], cfg[1], args.tl, cfg[2], cfg[3])
            filas.append(f)
            print(f"  cand {f['candidatos_brutos']} → {f['candidatos_al_solver']} · "
                  f"status={f['status']} · seats={f['seats_alcanzados']} · "
                  f"obj={f['best_objective']} bound={f['best_bound']} · {f['runtime_total_s']} s",
                  flush=True)
            d = os.path.join(ROOT, "cases", "E25")
            os.makedirs(d, exist_ok=True)
            json.dump(filas, open(os.path.join(d, f"E25_{args.exp}{args.tag}.json"), "w", encoding="utf-8"),
                      indent=2, ensure_ascii=False)
    print(f"\nescrito cases/E25/E25_{args.exp}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
