"""E25 §5 — DIAGNÓSTICO PRE. Instrumenta el pipeline TAL CUAL quedó en E24, sin cambiar una decisión.

Reproduce exactamente la secuencia de Engine.run (E24): espina → ramales → candidatos (step=1.0) →
poda (cap 200) → warm start (seats<=need, tl 22 s) → factibilidad exacta (tl 25 s, reintento ×2 si
UNKNOWN). Lo único que agrega son contadores.
"""
from __future__ import annotations

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
BRIEFS = ["DENSO", "EQUILIBRADO", "EJECUTIVO"]

# parámetros EXACTOS de E24 (e07/run.py defaults)
CAP, STEP, TL_WARM, TL_FEAS, SEED, WORKERS = 200, 1.0, 22.0, 25.0, 1, 2


def area_modulo(raw, m):
    d = raw["modules"][m]
    return d["w"] * d["d"]


def main():
    ctx = from_case_dir(CASE)
    fp = Floorplate.load(ctx.require_floorplate())
    shell = scaled_shell(fp, 1.0)
    mods, clr = load_modules(MODS)
    raw_mods = json.load(open(MODS, encoding="utf-8"))
    out = {"case": "001_gps_403", "parametros": {"cap": CAP, "step": STEP, "tl_warm": TL_WARM,
                                                 "tl_feas": TL_FEAS, "seed": SEED, "workers": WORKERS},
           "combinaciones": []}
    for b in BRIEFS:
        brief = load_brief(os.path.join(ROOT, "briefs", f"BRIEF_{b}.json"))
        prog = compile_program(brief, modules=mods)
        S = Solver(shell, mods, prog, clr)
        grid = S.grid
        feats = extract_features(shell, grid)
        e05 = {s.strategy_id: s for s in generate_strategies(feats, brief.open_workstations)}
        specs = build_alternatives(prog)
        area_min = {p["module"]: round(p["count"] * area_modulo(raw_mods, p["module"]), 2)
                    for p in prog["program"]}
        for spec in specs:
            t0 = time.time()
            print(f"\n===== {b} / {spec.alt} =====", flush=True)
            strat = e05[spec.spine_strategy]
            plan = build_spine(shell, feats, strat, grid)
            els = F.spine_elements(plan)
            brs = F.branch_candidates(shell, feats, els, grid=grid)
            gen_stats, prune_stats = {}, {}
            t_gen = time.time()
            raw, _ = F.generate_candidates(shell, grid, feats, els + brs, mods, prog, spec.bench_cfgs,
                                           step=STEP, stats=gen_stats)
            cands = F.prune(raw, per_module_cap=CAP, stats=prune_stats)
            t_gen = round(time.time() - t_gen, 2)
            weights = dict(prog["objectives_weights"]); weights.update(spec.weights)
            extra = dict(spec.solver_extra)

            warm_stats, feas_stats, feas2_stats = {}, {}, {}
            warm = F.solve_free(shell, grid, feats, strat, els + brs, cands, mods, prog, weights,
                                seats_mode="max", seed=SEED, time_limit_s=TL_WARM, workers=WORKERS,
                                extra=extra, stats=warm_stats)
            res = F.solve_free(shell, grid, feats, strat, els + brs, cands, mods, prog, weights,
                               seats_mode="exact", seed=SEED, time_limit_s=TL_FEAS, workers=WORKERS,
                               feasibility_only=True, extra=extra, hint=warm.get("layout"),
                               stats=feas_stats)
            retry = False
            if "layout" not in res and res["status"] == "UNKNOWN":
                retry = True
                res = F.solve_free(shell, grid, feats, strat, els + brs, cands, mods, prog, weights,
                                   seats_mode="exact", seed=SEED, time_limit_s=TL_FEAS * 2,
                                   workers=WORKERS, feasibility_only=True, extra=extra,
                                   hint=warm.get("layout"), stats=feas2_stats)
            fila = {
                "brief": b, "alt": spec.alt, "nombre": spec.name,
                "solicitud": {
                    "puestos": brief.open_workstations,
                    "privados": brief.room_count("private_office"),
                    "modulos": {p["module"]: p["count"] for p in prog["program"]},
                    "area_nominal_por_modulo_m2": area_min,
                    "area_nominal_programa_m2": round(sum(area_min.values()), 2),
                },
                "estrategia": {"spine": spec.spine_strategy, "bench_cfgs": list(spec.bench_cfgs),
                               "solver_extra": {k: v for k, v in spec.solver_extra.items()
                                                if k in ("max_bench_blocks", "min_bench_blocks",
                                                         "max_facade_closed_rooms", "module_max_path")}},
                "generacion": gen_stats, "poda": prune_stats,
                "generacion_runtime_s": t_gen,
                "n_elementos_circulacion": len(els), "n_ramales_candidatos": len(brs),
                "warm": warm_stats or {"status": warm.get("status"),
                                       "pre_solver_reject": warm.get("pre_solver_reject")},
                "warm_seats": warm.get("seats"),
                "feasibility": feas_stats or {"status": res.get("status"),
                                              "pre_solver_reject": res.get("pre_solver_reject")},
                "feasibility_retry": retry,
                "feasibility_retry_stats": feas2_stats or None,
                "resultado_e24": {"status": res.get("status"), "tiene_layout": "layout" in res,
                                  "reason": res.get("reason"),
                                  "pre_solver_reject": res.get("pre_solver_reject")},
                "runtime_total_s": round(time.time() - t0, 2),
            }
            out["combinaciones"].append(fila)
            print(f"  candidatos {gen_stats.get('brutos_total')} → {prune_stats.get('finales')} "
                  f"(cap activo en {prune_stats.get('modulos_con_cap_activo')})", flush=True)
            print(f"  warm={warm.get('status')} seats={warm.get('seats')} · "
                  f"feas={res.get('status')} retry={retry} · {fila['runtime_total_s']} s", flush=True)
    d = os.path.join(ROOT, "cases", "E25")
    os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, "E25_DIAGNOSTICO_PRE_3x3.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print("\nescrito cases/E25/E25_DIAGNOSTICO_PRE_3x3.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
