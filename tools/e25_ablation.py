"""E25 §10 / EXP-4 — ABLACIÓN: ¿qué restricción exacta ata a EJECUTIVO?

Sobre el modelo WARM (el relajado: Σ puestos ≤ N), quitando UNA restricción por vez. Diagnóstico puro:
identifica la restricción que ata. NO autoriza relajar nada por sí solo."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from e25_offline_experiments import contexto, geometria                        # noqa: E402
from escalimetro.layout.e06 import freeplace as F                              # noqa: E402

CAP, STEP, SEED, WORKERS = 200, 1.0, 1, 1

ABLACIONES = [
    ("BASELINE", lambda e: e),
    ("sin_max_facade_closed_rooms", lambda e: {k: v for k, v in e.items() if k != "max_facade_closed_rooms"}),
    ("sin_module_max_path", lambda e: {k: v for k, v in e.items() if k != "module_max_path"}),
    ("sin_hard_adjacent_pairs", lambda e: {k: v for k, v in e.items() if k != "hard_adjacent_pairs"}),
    ("sin_bench_blocks", lambda e: {k: v for k, v in e.items() if k not in ("min_bench_blocks", "max_bench_blocks")}),
    ("solo_geometria", lambda e: {k: v for k, v in e.items()
                                  if k not in ("max_facade_closed_rooms", "module_max_path",
                                               "hard_adjacent_pairs", "min_bench_blocks",
                                               "max_bench_blocks")}),
]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", default="EJECUTIVO")
    ap.add_argument("--alts", default="A,B")
    ap.add_argument("--tl", type=float, default=60.0)
    ap.add_argument("--reception-max-path", type=float, default=8.0)
    args = ap.parse_args(argv)
    filas = []
    for alt in args.alts.split(","):
        shell, grid, feats, mods, brief, prog, e05, specs = contexto(args.brief)
        spec = next(s for s in specs if s.alt == alt)
        strat, els, cands, gs, ps = geometria(shell, grid, feats, mods, prog, spec, e05, STEP, CAP)
        weights = dict(prog["objectives_weights"]); weights.update(spec.weights)
        for nombre, quitar in ABLACIONES:
            extra = quitar(dict(spec.solver_extra))
            st = {}
            t0 = time.time()
            res = F.solve_free(shell, grid, feats, strat, els, cands, mods, prog, weights,
                               seats_mode="max", seed=SEED, time_limit_s=args.tl, workers=WORKERS,
                               reception_max_path=args.reception_max_path, extra=extra, stats=st)
            fila = {"brief": args.brief, "alt": alt, "ablacion": nombre,
                    "reception_max_path": args.reception_max_path,
                    "status": res.get("status"), "seats": res.get("seats"),
                    "pre_solver_reject": res.get("pre_solver_reject"),
                    "reason": res.get("reason"),
                    "wall_time_s": st.get("wall_time_s"), "runtime_s": round(time.time() - t0, 2)}
            filas.append(fila)
            print(f"{args.brief}/{alt:<2} {nombre:<32} {str(res.get('status')):<12} "
                  f"seats={res.get('seats')} · {fila['runtime_s']} s", flush=True)
    d = os.path.join(ROOT, "cases", "E25")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"E25_EXP4_ABLACION_{args.brief}.json")
    json.dump(filas, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("\nescrito", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
