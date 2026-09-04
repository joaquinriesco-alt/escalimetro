"""E06 — Orquestador. Etapas (independientes, reanudables):

    python3 -m escalimetro.layout.e06.run sweep   --case cases/001_gps_403 [--factors 0.95,...] [--strategy B_CLIENT_FRONT]
    python3 -m escalimetro.layout.e06.run qa      --case cases/001_gps_403 --ops cases/001_gps_403/layouts/E06/qa_ops.json
    python3 -m escalimetro.layout.e06.run report  --case cases/001_gps_403

Salidas en cases/<id>/layouts/E06/."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

from ...schemas.floorplate import Floorplate
from ..model import Layout, load_modules, load_program
from ..run import compute_metrics
from ..scoring import score as score_layout
from ..solver import Solver
from ..e05.critic import RuleBasedCritic
from ..e05.features import extract_features
from ..e05.strategy import generate_strategies
from ...case_context import from_case_dir
from .scale import DEFAULT_FACTORS, make_scenario, scaled_shell
from .sweep import robustness, run_scenario


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if hasattr(o, "to_dict"):
        return o.to_dict()
    return str(o)


def dump(obj, path):
    json.dump(obj, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=_default)


def cmd_sweep(args):
    out = os.path.join(args.case, "layouts", "E06")
    os.makedirs(out, exist_ok=True)
    fp = Floorplate.load(os.path.join(args.case, "outputs", "floorplate.json"))
    factors = [float(x) for x in args.factors.split(",")] if args.factors else list(DEFAULT_FACTORS)
    path = os.path.join(out, "scale_scenarios.json")
    done = {}
    if os.path.exists(path) and not args.fresh:
        for d in json.load(open(path)):
            done[round(d["scale_factor"], 4)] = d
    t0 = time.time()
    for f in factors:
        if round(f, 4) in done:
            print(f"[sweep] x{f}: ya calculado"); continue
        sc = run_scenario(fp, f, args.strategy, args.modules, args.program, os.path.join(out, "scenarios"),
                          tl_exact=args.tl_exact, tl_probe=args.tl_probe, seed=args.seed)
        done[round(f, 4)] = sc.to_dict()
        dump([done[k] for k in sorted(done)], path)
    scenarios = [done[k] for k in sorted(done)]
    from .scale import ScaleScenario
    rep = robustness([ScaleScenario(**{k: v for k, v in d.items()}) for d in scenarios])
    dump(rep.to_dict(), os.path.join(out, "fit_robustness_report.json"))
    print(f"[sweep] {rep.classification} · exact fit en {rep.exact_fit_factors} · min {rep.min_scale_factor_exact_fit} · {round(time.time() - t0, 1)} s")
    return 0


def cmd_solve(args):
    """Re-resuelve UN escenario (modo exacto) con más tiempo, usando como pista la solución guardada (sonda o exacta)."""
    from .sweep import run_scenario
    from .scale import ScaleScenario
    from ..e05.bands import build_spine
    from . import freeplace as F
    out = os.path.join(args.case, "layouts", "E06")
    factor = args.factor
    fp, shell, mods, prog, S04, strat = _ctx(args, factor)
    hint = _load_scenario_layout(args.case, factor, "exact") or _load_scenario_layout(args.case, factor, "probe")
    feats = extract_features(shell, S04.grid)
    plan = build_spine(shell, feats, strat, S04.grid)
    els = F.spine_elements(plan); brs = F.branch_candidates(shell, feats, els)
    cands, _ = F.generate_candidates(shell, S04.grid, feats, els + brs, mods, prog, strat.bench_preference)
    res = F.solve_free(shell, S04.grid, feats, strat, els + brs, cands, mods, prog, prog["objectives_weights"], seats_mode="exact",
                       seed=args.seed, time_limit_s=args.tl_exact * 0.6, hint=hint, feasibility_only=True)
    print(f"[solve] fase factibilidad: {res['status']} {res['runtime_s']} s")
    if "layout" in res:
        res2 = F.solve_free(shell, S04.grid, feats, strat, els + brs, cands, mods, prog, prog["objectives_weights"], seats_mode="exact",
                            seed=args.seed, time_limit_s=args.tl_exact * 0.4, hint=res["layout"])
        if "layout" in res2:
            res2["runtime_s"] = round(res["runtime_s"] + res2["runtime_s"], 2); res = res2
    print(f"[solve] x{factor}: {res['status']} {res['runtime_s']} s seats={res.get('seats')}")
    path = os.path.join(out, "scale_scenarios.json")
    scen = json.load(open(path))
    rec = next((x for x in scen if abs(x["scale_factor"] - factor) < 1e-6), None)
    if rec is None:
        rec = make_scenario(fp, factor).to_dict(); rec["layout_result"] = {"strategy_id": args.strategy}; scen.append(rec)
    lr = rec["layout_result"]
    lr.setdefault("exact", {})
    lr["exact"].update({"status": res["status"], "runtime_s": res["runtime_s"], "reason": res.get("reason"), "time_limit_s": args.tl_exact})
    if "layout" in res:
        lay = res["layout"]; lay.layout_id = f"x{factor}_exact"
        ok, viol, crit = _evaluate(lay, shell, S04, prog, strat)
        d = os.path.join(out, "scenarios", f"x{factor:.3f}"); os.makedirs(d, exist_ok=True)
        lay.save(os.path.join(d, "layout_exact.json")); dump(lay.metrics, os.path.join(d, "metrics_exact.json")); dump(crit.to_dict(), os.path.join(d, "critique_exact.json"))
        lr["exact"].update({"mode": "exact", "hard_valid": ok, "violations": viol, "seats": sum(p.seats for p in lay.placements),
                            "geometric_score": (lay.scores or {}).get("total"), "architectural_score": crit.architectural_score,
                            "broker_showable": crit.broker_showable, "active_branches": res.get("active_branches"),
                            "daylight": (lay.scores or {}).get("objectives", {}).get("daylight_utilization"), "circulation_m2": lay.metrics.get("circulation_area_m2")})
        lr["exact_fit"] = ok
        if ok:
            lr["max_seats"] = 40
        print(f"[solve] válido={ok} viol={viol[:3]} arq={crit.architectural_score}")
    scen.sort(key=lambda x: x["scale_factor"])
    dump(scen, path)
    rep = robustness([ScaleScenario(**x) for x in scen])
    dump(rep.to_dict(), os.path.join(out, "fit_robustness_report.json"))
    print(f"[solve] {rep.classification} · exact fit {rep.exact_fit_factors}")
    return 0


def _load_scenario_layout(case, factor, mode):
    d = os.path.join(case, "layouts", "E06", "scenarios", f"x{factor:.3f}")
    path = os.path.join(d, f"layout_{mode}.json")
    return Layout.load(path) if os.path.exists(path) else None


def _ctx(args, factor):
    fp = Floorplate.load(os.path.join(args.case, "outputs", "floorplate.json"))
    shell = scaled_shell(fp, factor)
    mods, clr = load_modules(args.modules)
    prog = load_program(args.program)
    S04 = Solver(shell, mods, prog, clr)
    feats = extract_features(shell, S04.grid)
    strat = {s.strategy_id: s for s in generate_strategies(feats)}[args.strategy]
    return fp, shell, mods, prog, S04, strat


def _evaluate(lay, shell, S04, prog, strat):
    ok, viol, circ = S04.validate(lay)
    lay.hard_violations = viol
    lay.circulation_cells = []
    if circ.get("ok"):
        lay.circulation_graph = circ["graph"]
        lay.circulation_cells = [(int(i), int(j)) for j, i in zip(*np.where(circ["used_corridors"]))]
        lay.scores = score_layout(lay, shell, S04.grid, circ, S04.zones, prog["objectives_weights"])
    lay.metrics = compute_metrics(lay, S04, circ if circ else None)
    crit = RuleBasedCritic().critique(lay, lay.metrics, strat.to_dict())
    return ok, viol, crit


def cmd_qa(args):
    """Aplica operaciones de QA (JSON) sobre el layout automático del escenario indicado y re-valida."""
    ctx = from_case_dir(args.case)                      # E15: identidad y rutas del caso
    from ..render import render_png, triptych
    from .qa import HumanCorrectionOperation, apply_operations, burden, qa_gate
    import cv2
    out = os.path.join(args.case, "layouts", "E06")
    factor = args.factor
    fp, shell, mods, prog, S04, strat = _ctx(args, factor)
    before = _load_scenario_layout(args.case, factor, "exact") or _load_scenario_layout(args.case, factor, "probe")
    assert before is not None, "no hay layout automático para ese escenario"
    ok0, viol0, crit0 = _evaluate(before, shell, S04, prog, strat)
    ops = [HumanCorrectionOperation(**o) for o in json.load(open(args.ops))]
    after, log, locked = apply_operations(before, ops, mods)
    ok1, viol1, crit1 = _evaluate(after, shell, S04, prog, strat)
    b = burden(before, after, ops, {"hard_valid": ok1, "violations": viol1, "geometric_score": (after.scores or {}).get("total"),
                                    "architectural_score": crit1.architectural_score, "broker_showable": crit1.broker_showable})
    gate = qa_gate(ok0, crit0.broker_showable, b, ok1, crit1.broker_showable)
    changed = [e["target"] for e in log if e["op"] in ("MOVE", "ROTATE", "SWAP", "RESIZE_TO_VALID_VARIANT")] + \
              [e["args"].get("other") for e in log if e["op"] == "SWAP"] + [p.id for p in after.placements if p.meta.get("qa_added")]
    d = os.path.join(out, "qa"); os.makedirs(d, exist_ok=True)
    before.layout_id = f"AUTO x{factor}"; after.layout_id = f"AFTER QA x{factor}"
    after.save(os.path.join(d, "layout_after_qa.json"))
    dump({"before": {"hard_valid": ok0, "violations": viol0, "geometric_score": (before.scores or {}).get("total"),
                     "architectural_score": crit0.architectural_score, "broker_showable": crit0.broker_showable, "critique": crit0.to_dict()},
          "operations": [o.to_dict() for o in ops], "log": log, "locked": locked, "burden": b.to_dict(),
          "after": {"hard_valid": ok1, "violations": viol1, "geometric_score": (after.scores or {}).get("total"),
                    "architectural_score": crit1.architectural_score, "broker_showable": crit1.broker_showable, "critique": crit1.to_dict()},
          "qa_gate": gate, "scale_factor": factor, "minutes_are_estimated": True}, os.path.join(d, "qa_result.json"))
    g0 = render_png(before, shell, "geometry", os.path.join(d, "auto_geometry.png"), grid_cell=S04.grid.cell,
                    circulation_cells=before.circulation_cells, title=before.layout_id)
    g1 = render_png(after, shell, "geometry", os.path.join(d, "after_qa_geometry.png"), grid_cell=S04.grid.cell,
                    circulation_cells=after.circulation_cells, title=after.layout_id, highlight_ids=changed)
    cv2.imwrite(os.path.join(out, "before_after_qa.png"), triptych([(g0, "AUTO"), (g1, "AFTER QA (rojo = cambiado)")]))
    if ok1:
        render_png(after, shell, "geometry", os.path.join(out, "best_assisted_layout.png"), grid_cell=S04.grid.cell,
                   circulation_cells=after.circulation_cells, title="best_assisted_layout")
        render_png(after, shell, "commercial", os.path.join(out, "best_assisted_layout_commercial.png"),
                   title=f"OFFICE {ctx.slug} · assisted")
    print(f"[qa] antes válido={ok0} arq={crit0.architectural_score} · después válido={ok1} arq={crit1.architectural_score} viol={viol1[:3]} · "
          f"{b.operation_count} ops · {b.estimated_minutes} min est. · {b.automatic_geometry_preserved_pct} % preservado · gate {gate}")
    return 0


def cmd_report(args):
    """Visuales y veredicto a partir de scale_scenarios.json (+ qa_result.json si existe)."""
    ctx = from_case_dir(args.case)                      # E15: identidad y rutas del caso
    from ..render import render_png, triptych
    from .evidence import collect
    from .verdict import build
    from .qa import qa_gate
    import cv2
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = os.path.join(args.case, "layouts", "E06")
    scen = json.load(open(os.path.join(out, "scale_scenarios.json")))
    rob = json.load(open(os.path.join(out, "fit_robustness_report.json")))
    fp = Floorplate.load(os.path.join(args.case, "outputs", "floorplate.json"))
    # E15 (OF02) — las unidades hermanas de la lámina son DATO DEL CASO (case.json → sibling_units),
    # no conocimiento del motor. Un caso que no las declare no obtiene esta evidencia secundaria;
    # no hereda la de otro caso.
    sib = ctx.sibling_units or {}
    published = {k: float(v) for k, v in (sib.get("published_m2") or {}).items()} or None
    samples = {k: tuple(v) for k, v in (sib.get("sample_px") or {}).items()} or None
    if published is None:
        print(f"[e06] sin sibling_units declaradas en {args.case}/case.json: "
              f"la evidencia secundaria por unidades hermanas no se calcula")
    ev = collect(fp, ctx.artifacts.source_image, published, samples)
    dump(ev.to_dict(), os.path.join(out, "secondary_scale_evidence.json"))
    # ---- fit_robustness.png (E15: nombre neutral, antes fit_robustness_403.png) ----
    fs = [s["scale_factor"] for s in scen]
    raw = [s["layout_result"].get("max_seats") for s in scen]
    seats = [v if v is not None else 0 for v in raw]
    fit = [bool(s["layout_result"].get("exact_fit")) for s in scen]
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=130)
    xs_l = [f for f, v in zip(fs, raw) if v is not None]; ys_l = [v for v in raw if v is not None]
    ax.plot(xs_l, ys_l, "-", color="#4c72b0", lw=1.5, zorder=1)
    for f, sc_, ok, v in zip(fs, seats, fit, raw):
        ax.scatter([f], [sc_], s=110, color="#2ca02c" if ok else "#d62728", marker="o" if ok else "X", zorder=3)
        lab = f"{sc_}" if v is not None else "sin anclaje\npara directorio"
        ax.annotate(lab, (f, sc_), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=8 if v is None else 9)
    ax.axhline(40, color="#555", ls="--", lw=1); ax.text(fs[0], 40.4, "brief: 40 puestos", fontsize=9, color="#555")
    ax.axvline(1.0, color="#999", ls=":", lw=1); ax.text(1.001, min(seats) - 1.5, "escala nominal (LOW)", fontsize=8, color="#777")
    ax.set_xlabel(f"factor de escala respecto de {ctx.scale_px_per_m:.2f} px/m (published_area_inferred)")
    ax.set_ylabel("puestos open máximos con recintos completos")
    ax.set_title(f"{ctx.display_name or ctx.unit_label} · fit robustness · verde = exact fit validado · "
                 f"rojo = FAIL · clasificación {rob['classification']}", fontsize=10)
    ax.set_ylim(min(seats) - 3, 43); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(ctx.artifacts.robustness_png); plt.close(fig)
    # ---- scale_sensitivity_layouts.png: conservador, nominal, primer exact fit, optimista ----
    picks = []
    exact = rob.get("exact_fit_factors", [])
    from ..e05.run import mosaic, label as label_img
    seen_f = set()
    for lab, f in (("conservador", min(fs)), ("nominal", 1.0), ("primer exact fit", min(exact) if exact else None), ("optimista", max(fs))):
        if f is None or f in seen_f:
            continue
        seen_f.add(f)
        s = next((x for x in scen if abs(x["scale_factor"] - f) < 1e-6), None)
        if not s:
            continue
        mode = "exact" if s["layout_result"].get("exact_fit") else ("probe" if "probe" in s["layout_result"] and s["layout_result"]["probe"].get("layout_path") else "exact")
        lay = _load_scenario_layout(args.case, f, mode)
        if lay is None:
            blank = np.full((1000, 1800, 3), 245, np.uint8)
            reason = s["layout_result"].get("exact", {}).get("reason") or "sin layout"
            cv2.putText(blank, f"x{f:.3f} {lab}: SIN LAYOUT", (80, 420), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (30, 30, 160), 3)
            cv2.putText(blank, reason[:90], (80, 500), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 60, 60), 2)
            cv2.putText(blank, f"usable {s['layout_result'].get('usable_m2')} m2", (80, 560), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 60, 60), 2)
            picks.append((blank, f"x{f:.3f} {lab} - SIN LAYOUT"))
            continue
        fp_, shell, mods, prog, S04, strat = _ctx(args, f)
        ok, viol, crit = _evaluate(lay, shell, S04, prog, strat)
        lay.layout_id = f"x{f:.3f} {lab} · {'VALIDO' if ok else 'INVALIDO'} · {sum(p.seats for p in lay.placements)} puestos"
        img = render_png(lay, shell, "geometry", os.path.join(out, "scenarios", f"x{f:.3f}", "render.png"), grid_cell=S04.grid.cell,
                         circulation_cells=lay.circulation_cells, title=lay.layout_id)
        picks.append((img, f"x{f:.3f} {lab} - {'VALIDO' if ok else 'INVALIDO'} - {sum(p.seats for p in lay.placements)} puestos"))
    if picks:
        tiles = []
        for img, t in picks:
            im = cv2.resize(img, (900, int(img.shape[0] * 900 / img.shape[1])))
            tiles.append(label_img(im, t, (0, 120, 0) if "VALIDO" in t and "INVALIDO" not in t else (0, 0, 180)))
        cv2.imwrite(os.path.join(out, "scale_sensitivity_layouts.png"), mosaic(tiles, 2))
    # ---- best_autonomous_layout.png (mejor válido automático; preferir nominal) ----
    valid = [s for s in scen if s["layout_result"].get("exact_fit")]
    auto = None
    if valid:
        valid.sort(key=lambda s: (abs(s["scale_factor"] - 1.0), -(s["layout_result"]["exact"].get("architectural_score") or 0)))
        auto = valid[0]
        f = auto["scale_factor"]
        fp_, shell, mods, prog, S04, strat = _ctx(args, f)
        lay = _load_scenario_layout(args.case, f, "exact")
        ok, viol, crit = _evaluate(lay, shell, S04, prog, strat)
        lay.layout_id = f"OFFICE_BALANCED_001_E06_AUTO x{f:.3f}"
        d = os.path.join(out, "OFFICE_BALANCED_001_E06_AUTO"); os.makedirs(d, exist_ok=True)
        lay.save(os.path.join(d, "layout.json")); dump(lay.metrics, os.path.join(d, "metrics.json")); dump(crit.to_dict(), os.path.join(d, "critique.json"))
        render_png(lay, shell, "geometry", os.path.join(out, "best_autonomous_layout.png"), grid_cell=S04.grid.cell,
                   circulation_cells=lay.circulation_cells, title=lay.layout_id)
        render_png(lay, shell, "commercial", os.path.join(out, "best_autonomous_layout_commercial.png"),
                   title=f"OFFICE {ctx.slug} · autonomous")
        auto_gate = "PASS" if (ok and crit.broker_showable) else "FAIL"
        auto_info = {"scale_factor": f, "hard_valid": ok, "architectural_score": crit.architectural_score, "broker_showable": crit.broker_showable,
                     "geometric_score": (lay.scores or {}).get("total"), "seats": sum(p.seats for p in lay.placements), "critique": crit.to_dict(),
                     "metrics": lay.metrics}
    else:
        auto_gate, auto_info = "FAIL", None
    qa_path = os.path.join(out, "qa", "qa_result.json")
    qa = json.load(open(qa_path)) if os.path.exists(qa_path) else None
    assisted_gate = "PASS" if (qa and qa["after"]["hard_valid"] and qa["after"]["broker_showable"]) else "FAIL"
    qa_g = qa["qa_gate"] if qa else ("AUTONOMOUS_PASS" if auto_gate == "PASS" else "FAIL")
    unit_full = f"{ctx.unit_label} ({ctx.source_name})" if ctx.source_name else ctx.unit_label
    v = build(unit_full, "OFFICE_BALANCED_48", 48, rob, ev.to_dict(), auto_gate, assisted_gate, qa_g,
              published_area_m2=ctx.published_area_m2)
    dump(v.to_dict(), os.path.join(out, "fit_verdict.json"))
    open(os.path.join(out, "fit_verdict.txt"), "w", encoding="utf-8").write(v.text())
    dump({"robustness": rob, "evidence": ev.to_dict(), "autonomous": auto_info and {k: v_ for k, v_ in auto_info.items() if k not in ("critique", "metrics")},
          "gate_e1_autonomous": auto_gate, "gate_e1_assisted": assisted_gate, "qa_gate": qa_g, "verdict": v.to_dict()},
         os.path.join(out, "summary.json"))
    print(v.text())
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sweep")
    s.add_argument("--case", required=True)
    s.add_argument("--program", default="program_templates/office_balanced_48.json")
    s.add_argument("--modules", default="program_templates/modules_office.json")
    s.add_argument("--strategy", default="B_CLIENT_FRONT")
    s.add_argument("--factors", default="")
    s.add_argument("--tl-exact", type=float, default=240.0)
    s.add_argument("--tl-probe", type=float, default=90.0)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--fresh", action="store_true")
    s.set_defaults(fn=cmd_sweep)
    for name, fn in (("qa", cmd_qa), ("report", cmd_report), ("solve", cmd_solve)):
        q = sub.add_parser(name)
        q.add_argument("--case", required=True)
        q.add_argument("--program", default="program_templates/office_balanced_48.json")
        q.add_argument("--modules", default="program_templates/modules_office.json")
        q.add_argument("--strategy", default="B_CLIENT_FRONT")
        q.add_argument("--factor", type=float, default=1.0)
        q.add_argument("--ops", default="")
        q.add_argument("--tl-exact", type=float, default=900.0)
        q.add_argument("--seed", type=int, default=1)
        q.set_defaults(fn=fn)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
