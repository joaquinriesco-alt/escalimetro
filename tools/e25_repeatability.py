"""E25 §9 — ¿el modo determinista repite? Misma versión, mismo shell, mismo brief, misma estrategia."""
from __future__ import annotations
import hashlib, json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, os.path.join(ROOT, "tools"))
from e25_offline_experiments import contexto, geometria                        # noqa: E402
from escalimetro.layout.e06 import freeplace as F                              # noqa: E402

CAP, STEP, SEED = 200, 1.0, 1


def una(brief_id, alt, det, budget, tl):
    shell, grid, feats, mods, brief, prog, e05, specs = contexto(brief_id)
    spec = next(s for s in specs if s.alt == alt)
    strat, els, cands, gs, ps = geometria(shell, grid, feats, mods, prog, spec, e05, STEP, CAP)
    w = dict(prog["objectives_weights"]); w.update(spec.weights)
    st = {}; t0 = time.time()
    res = F.solve_free(shell, grid, feats, strat, els, cands, mods, prog, w, seats_mode="exact",
                       seed=SEED, time_limit_s=tl, workers=2, feasibility_only=True,
                       extra=dict(spec.solver_extra), stats=st,
                       deterministic=det, deterministic_budget=budget)
    h = None
    if "layout" in res:
        pl = sorted((p.module, round(p.x, 3), round(p.y, 3), round(p.w, 3), round(p.d, 3))
                    for p in res["layout"].placements)
        h = hashlib.sha256(str(pl).encode()).hexdigest()[:16]
    return {"status": res.get("status"), "seats": res.get("seats"), "geometry_hash": h,
            "wall_time_s": st.get("wall_time_s"), "det_time": st.get("deterministic_time"),
            "runtime_s": round(time.time() - t0, 2), "modo": "DETERMINISTA" if det else "PRODUCTO"}


def main():
    out = {"combinacion": "EQUILIBRADO/B", "corridas": {}}
    for modo, det, budget, tl in (("PRODUCTO", False, 0.0, 25.0),
                                  ("DETERMINISTA", True, 40.0, 0.0)):
        rs = [una("EQUILIBRADO", "B", det, budget, tl) for _ in range(2)]
        igual = (rs[0]["status"] == rs[1]["status"] and rs[0]["seats"] == rs[1]["seats"]
                 and rs[0]["geometry_hash"] == rs[1]["geometry_hash"])
        out["corridas"][modo] = {"runs": rs, "reproducible": igual}
        print(f"\n### {modo}")
        for i, r in enumerate(rs, 1):
            print(f"  run {i}: {r['status']} seats={r['seats']} geom={r['geometry_hash']} "
                  f"wall={r['wall_time_s']}s det_time={r['det_time']} total={r['runtime_s']}s")
        print(f"  reproducible: {igual}")
    d = os.path.join(ROOT, "cases", "E25"); os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, "E25_REPRODUCIBILIDAD.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
