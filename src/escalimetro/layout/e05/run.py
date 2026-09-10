"""E05 — Orquestador: SPATIAL STRATEGY → GEOMETRIC SOLVER → DETERMINISTIC VALIDATOR → ARCHITECTURAL CRITIC →
REPAIR / ITERATION. Uso:

    PYTHONPATH=src python3 -m escalimetro.layout.e05.run --case cases/001_gps_403 --time-limit 40 --seed 1

Salidas en cases/<id>/layouts/E05/: strategies/*.json, strategy_feasibility_report.json, iterations.json,
candidates.json, summary.json, strategy_diagrams.png, candidate_matrix.png, layout_e05_geometry.png,
layout_e05_commercial_base.png, e04_vs_e05.png y OFFICE_BALANCED_001_E05/ (si hay ganador válido)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List

import cv2
import numpy as np

from ...renderer.side_by_side import _svg_to_bgr
from ...schemas.floorplate import Floorplate
from ..grid import Grid
from ..model import Layout, load_modules, load_program
from ..render import _Tf, _poly_pts, render_png, triptych
from ..run import compute_metrics
from ..scoring import score as score_layout
from ..shell_adapter import shell_from_floorplate
from ..solver import Solver
from . import cpsolver
from .bands import build_spine
from .critic import RuleBasedCritic, rank, to_repair_constraints
from .features import extract_features
from .preflight import preflight
from .strategy import SpatialStrategy, generate_strategies

ROLE_COLORS = {"public": "#f4c7a1", "client": "#b8d8b8", "work": "#c9d7ee", "support": "#e6d3c0", "mixed": "#dcdcdc"}


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if hasattr(o, "to_dict"):
        return o.to_dict()
    return str(o)


def dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=_json_default)


def strategy_svg(shell, feats, strat: SpatialStrategy, plan, width=700) -> str:
    tf = _Tf(shell, width, 30, extra_bottom=70)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{tf.W}" height="{tf.H:.0f}" font-family="Helvetica,Arial,sans-serif">',
         '<rect width="100%" height="100%" fill="#fff"/>']
    o.append(f'<polygon points="{_poly_pts(tf, shell.perimeter)}" fill="#fafafa" stroke="#222" stroke-width="2"/>')
    for c in shell.core:
        o.append(f'<polygon points="{_poly_pts(tf, c)}" fill="#d9d9d9" stroke="#555"/>')
    roles = {}
    for rid in strat.support_zone.get("regions", []):
        roles[rid] = "support"
    for n in strat.work_neighborhoods:
        for rid in n["regions"]:
            roles[rid] = "work"
    for rid in strat.client_meeting_zone.get("regions", []):
        roles[rid] = "client"
    roles[strat.public_zone["region"]] = "public"
    for r in feats.regions:
        X, Y, Wd, D = tf.rect(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)
        o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{Wd:.1f}" height="{D:.1f}" fill="{ROLE_COLORS.get(roles.get(r.id, "mixed"))}" fill-opacity="0.75" stroke="#888" stroke-dasharray="4,3"/>')
    if plan is not None:
        for b in plan.bands:
            if b.kind in ("corridor", "dead"):
                continue
            X, Y, Wd, D = tf.rect(b.rect[0], b.rect[1], b.rect[2] - b.rect[0], b.rect[3] - b.rect[1])
            col = {"work": "#7f9fd6", "rooms": "#6aa36a", "mixed": "#9a9a9a", "support": "#c09060"}.get(b.kind, "#999")
            o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{Wd:.1f}" height="{D:.1f}" fill="none" stroke="{col}" stroke-width="1.5"/>')
        for p in plan.all_corridor_polys():
            o.append(f'<polygon points="{_poly_pts(tf, p)}" fill="#ffe9a8" stroke="#c9a227" stroke-width="0.8"/>')
    for e in feats.daylight_edges:
        (x1, y1), (x2, y2) = tf(e.start), tf(e.end)
        col = "#1f77b4" if e.id in strat.premium_daylight_edges else "#9ecae1"
        o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="4"/>')
    for c in shell.columns:
        o.append(f'<polygon points="{_poly_pts(tf, c)}" fill="#111"/>')
    ex, ey = tf(shell.entrance)
    o.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="6" fill="none" stroke="#c0392b" stroke-width="2.5"/>')
    for r in feats.regions:
        cx, cy = tf(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
        t = f"{r.id}: {roles.get(r.id, 'mixed')}"
        o.append(f'<rect x="{cx - 34:.0f}" y="{cy - 11:.0f}" width="68" height="15" fill="#fff" fill-opacity="0.85" rx="3"/>')
        o.append(f'<text x="{cx:.0f}" y="{cy:.0f}" font-size="11" text-anchor="middle" fill="#222" font-weight="bold">{t}</text>')
    base = tf.H - 70 + 18
    o.append(f'<text x="30" y="{base:.0f}" font-size="14" font-weight="bold">{strat.strategy_id}</text>')
    desc = strat.description
    o.append(f'<text x="30" y="{base + 18:.0f}" font-size="10" fill="#444">{desc[:110]}</text>')
    o.append(f'<text x="30" y="{base + 32:.0f}" font-size="10" fill="#444">{desc[110:220]}</text>')
    o.append(f'<text x="30" y="{base + 48:.0f}" font-size="10" fill="#666">naranja=público · verde=cliente · azul=trabajo · beige=soporte · amarillo=espina · azul fuerte=fachada premium</text>')
    o.append("</svg>")
    return "\n".join(o)


def mosaic(imgs: List[np.ndarray], cols: int, gap: int = 16) -> np.ndarray:
    w = max(i.shape[1] for i in imgs); h = max(i.shape[0] for i in imgs)
    rows = int(np.ceil(len(imgs) / cols))
    canvas = np.full((rows * h + (rows - 1) * gap, cols * w + (cols - 1) * gap, 3), 255, np.uint8)
    for k, im in enumerate(imgs):
        r, c = divmod(k, cols)
        y, x = r * (h + gap), c * (w + gap)
        canvas[y:y + im.shape[0], x:x + im.shape[1]] = im
    return canvas


def label(img: np.ndarray, text: str, color=(0, 0, 0)) -> np.ndarray:
    out = np.full((img.shape[0] + 34, img.shape[1], 3), 255, np.uint8)
    out[34:] = img
    cv2.putText(out, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--program", default="program_templates/office_balanced_48.json")
    ap.add_argument("--modules", default="program_templates/modules_office.json")
    ap.add_argument("--time-limit", type=float, default=40.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-repair", type=int, default=2)
    ap.add_argument("--no-probe", action="store_true", help="no correr la sonda de capacidad (max puestos)")
    ap.add_argument("--only", default="", help="ids de estrategias separados por coma")
    args = ap.parse_args(argv)
    t_all = time.time()
    out = os.path.join(args.case, "layouts", "E05")
    os.makedirs(os.path.join(out, "strategies"), exist_ok=True)
    fp = Floorplate.load(os.path.join(args.case, "outputs", "floorplate.json"))
    shell = shell_from_floorplate(fp)
    mods, clr = load_modules(args.modules)
    prog = load_program(args.program)
    S04 = Solver(shell, mods, prog, clr)          # validador / scoring / raster de E04 (congelados)
    grid = S04.grid
    feats = extract_features(shell, grid)
    dump(feats.to_dict(), os.path.join(out, "shell_features.json"))
    strategies = generate_strategies(feats, int(prog["open_workstations_exact"]))
    if args.only:
        keep = set(args.only.split(","))
        strategies = [s for s in strategies if s.strategy_id in keep]
    critic = RuleBasedCritic()
    weights = prog["objectives_weights"]
    feas_reports, iterations, candidates, plans = [], [], [], {}
    e04_metrics = None
    e04_path = os.path.join(args.case, "layouts", "OFFICE_BALANCED_001", "metrics.json")
    if os.path.exists(e04_path):
        e04_metrics = json.load(open(e04_path))
    print(f"[e05] shell {shell.usable.area:.1f} m² · regiones {[r.id for r in feats.regions]} · acceso en {feats.entrance_region} · {len(strategies)} estrategias")
    for strat in strategies:
        t_s = time.time()
        plan = build_spine(shell, feats, strat, grid)
        rep = preflight(strat, plan, mods, prog, shell.usable.area)
        # ajuste de pre-flight: si ninguna banda aloja el rectángulo mayor, forzar una banda honda en alguna región
        if not rep.boardroom_hosts:
            for rid in strat.client_meeting_zone.get("regions", []) + [r.id for r in feats.regions]:
                strat.preflight = {"deep_room_region": rid}
                plan2 = build_spine(shell, feats, strat, grid)
                rep2 = preflight(strat, plan2, mods, prog, shell.usable.area)
                if rep2.boardroom_hosts:
                    rep2.obvious_infeasibilities.append(f"ajuste pre-flight: banda honda forzada en {rid} para el directorio")
                    rep2.feasible = plan2.feasible and not [x for x in rep2.obvious_infeasibilities if not x.startswith("ajuste")]
                    plan, rep = plan2, rep2
                    break
            else:
                strat.preflight = {}
        strat.preflight = {**strat.preflight, "report": rep.to_dict(), "spine_feasible": plan.feasible, "spine_notes": plan.notes}
        strat.save(os.path.join(out, "strategies", f"{strat.strategy_id}.json"))
        dump(plan.to_dict(), os.path.join(out, "strategies", f"{strat.strategy_id}_spine.json"))
        feas_reports.append(rep.to_dict())
        plans[strat.strategy_id] = plan
        print(f"[e05] {strat.strategy_id}: pre-flight {'OK' if rep.feasible else 'INVIABLE'} · directorio en {rep.boardroom_hosts} · {rep.obvious_infeasibilities}")
        if not rep.feasible:
            candidates.append({"strategy_id": strat.strategy_id, "mode": "exact", "status": "PREFLIGHT_INFEASIBLE",
                               "hard_valid": False, "violations": rep.obvious_infeasibilities, "runtime_s": round(time.time() - t_s, 1)})
            continue
        # ---- solver exacto (brief) + validación + crítica + reparación -------------------------------
        repair = None
        best_for_strategy = None
        for it in range(args.max_repair + 1):
            res = cpsolver.solve(shell, grid, plan, strat, mods, prog, weights, repair=repair, seed=args.seed,
                                 time_limit_s=args.time_limit)
            rec = {"strategy_id": strat.strategy_id, "iteration": it, "mode": "exact", "status": res["status"],
                   "runtime_s": res["runtime_s"], "repair": repair.to_dict() if repair else None}
            if "layout" not in res:
                rec.update({"hard_valid": False, "violations": [res.get("reason", res["status"])]})
                iterations.append(rec); candidates.append(rec)
                print(f"[e05]   iter {it}: {res['status']} ({res['runtime_s']} s) {res.get('reason', '')}")
                break
            lay: Layout = res["layout"]
            lay.layout_id = f"{strat.strategy_id}_it{it}"
            ok, viol, circ = S04.validate(lay)
            lay.hard_violations = viol
            if circ.get("ok"):
                lay.circulation_graph = circ["graph"]
                lay.circulation_cells = [(int(i), int(j)) for j, i in zip(*np.where(circ["used_corridors"]))]
                lay.scores = score_layout(lay, shell, grid, circ, S04.zones, weights)
            lay.metrics = compute_metrics(lay, S04, circ if circ else None)
            crit = critic.critique(lay, lay.metrics, strat.to_dict())
            rec.update({"hard_valid": ok, "violations": viol, "geometric_score": (lay.scores or {}).get("total"),
                        "architectural_score": crit.architectural_score, "critique": crit.to_dict(), "layout": lay,
                        "seats": sum(p.seats for p in lay.placements)})
            iterations.append({k: v for k, v in rec.items() if k != "layout"})
            print(f"[e05]   iter {it}: {res['status']} ({res['runtime_s']} s) válido={ok} geo={rec['geometric_score']} arq={crit.architectural_score} viol={viol[:3]}")
            if best_for_strategy is None or (ok and not best_for_strategy["hard_valid"]) or \
               (ok == best_for_strategy["hard_valid"] and (crit.architectural_score or 0) > (best_for_strategy.get("architectural_score") or 0)):
                best_for_strategy = rec
            if not ok or not crit.repair_suggestions or crit.architectural_score >= 0.75:
                break
            repair = to_repair_constraints(crit)
        if best_for_strategy:
            candidates.append(best_for_strategy)
        # ---- sonda de capacidad (diagnóstico, nunca candidato) -------------------------------------
        if not args.no_probe and not (best_for_strategy and best_for_strategy.get("hard_valid")):
            resp = cpsolver.solve(shell, grid, plan, strat, mods, prog, weights, seed=args.seed,
                                  time_limit_s=args.time_limit, seats_mode="max")
            recp = {"strategy_id": strat.strategy_id, "mode": "probe_max_seats", "status": resp["status"], "runtime_s": resp["runtime_s"],
                    "hard_valid": False}
            if "layout" in resp:
                lay = resp["layout"]; lay.layout_id = f"{strat.strategy_id}_probe"
                ok, viol, circ = S04.validate(lay)
                lay.hard_violations = viol
                if circ.get("ok"):
                    lay.circulation_graph = circ["graph"]
                    lay.circulation_cells = [(int(i), int(j)) for j, i in zip(*np.where(circ["used_corridors"]))]
                    lay.scores = score_layout(lay, shell, grid, circ, S04.zones, weights)
                lay.metrics = compute_metrics(lay, S04, circ if circ else None)
                crit = critic.critique(lay, lay.metrics, strat.to_dict())
                recp.update({"seats": resp.get("seats"), "violations": viol, "geometric_score": (lay.scores or {}).get("total"),
                             "architectural_score": crit.architectural_score, "critique": crit.to_dict(), "layout": lay,
                             "only_seats_missing": all(v.startswith("puestos open") for v in viol)})
                print(f"[e05]   sonda: {resp['status']} puestos máx {resp.get('seats')} viol={viol[:2]}")
            else:
                recp["violations"] = [resp.get("reason", "")]
                print(f"[e05]   sonda: {resp['status']}")
            candidates.append(recp)
    # ---- ranking ------------------------------------------------------------------------------------
    exact = [c for c in candidates if c.get("mode") == "exact"]
    ranked = rank(exact)
    total_runtime = round(time.time() - t_all, 1)
    stats = {"strategy_count": len(strategies), "candidate_count": len([c for c in candidates if "layout" in c]),
             "exact_attempts": len(exact), "hard_valid_count": len(ranked),
             "architecturally_acceptable_count": len([c for c in ranked if c["critique"]["broker_showable"]]),
             "runtime_total_s": total_runtime, "runtime_per_strategy_s": round(total_runtime / max(1, len(strategies)), 1),
             "seed": args.seed, "time_limit_s": args.time_limit}
    winner = ranked[0] if ranked else None
    probes = [c for c in candidates if c.get("mode") == "probe_max_seats" and "layout" in c]
    best_partial = max(probes, key=lambda c: (c.get("only_seats_missing", False), c.get("seats") or 0, c.get("architectural_score") or 0)) if probes else None
    # ---- salidas del ganador / mejor parcial --------------------------------------------------------
    shown = winner or best_partial
    if shown:
        lay = shown["layout"]
        lid = "OFFICE_BALANCED_001_E05" if winner else f"E05_BEST_PARTIAL_{shown['strategy_id']}"
        lay.layout_id = lid
        d = os.path.join(out, lid); os.makedirs(d, exist_ok=True)
        lay.save(os.path.join(d, "layout.json"))
        dump(lay.metrics, os.path.join(d, "metrics.json"))
        dump(shown["critique"], os.path.join(d, "critique.json"))
        geo = render_png(lay, shell, "geometry", os.path.join(out, "layout_e05_geometry.png"), grid_cell=grid.cell,
                         circulation_cells=lay.circulation_cells, title=lid)
        com = render_png(lay, shell, "commercial", os.path.join(out, "layout_e05_commercial_base.png"), title=lid.replace("_", " "))
        e04_com = cv2.imread(os.path.join(args.case, "layouts", "OFFICE_BALANCED_001", "layout_001_commercial.png"))
        if e04_com is not None:
            cv2.imwrite(os.path.join(out, "e04_vs_e05.png"), triptych([(e04_com, "E04 OFFICE_BALANCED_001 (FAIL)"),
                                                                       (com, f"E05 {lid}" + ("" if winner else " (PARCIAL, INVALIDO)"))]))
    # ---- diagramas de estrategias y matriz de candidatos ---------------------------------------------
    panels = []
    for strat in strategies:
        svg = strategy_svg(shell, feats, strat, plans.get(strat.strategy_id))
        img = _svg_to_bgr(svg, 700)
        if img is not None:
            panels.append(img)
    if panels:
        cv2.imwrite(os.path.join(out, "strategy_diagrams.png"), mosaic(panels, 4))
    thumbs = []
    for strat in strategies:
        cs = [c for c in candidates if c["strategy_id"] == strat.strategy_id and "layout" in c]
        if not cs:
            c0 = next((c for c in candidates if c["strategy_id"] == strat.strategy_id), None)
            blank = np.full((500, 700, 3), 245, np.uint8)
            cv2.putText(blank, "sin candidato", (200, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (60, 60, 60), 2)
            thumbs.append(label(blank, f"{strat.strategy_id}: {c0['status'] if c0 else '-'}", (0, 0, 180)))
            continue
        best = sorted(cs, key=lambda c: (c["hard_valid"], c.get("seats") or 0, c.get("architectural_score") or 0))[-1]
        img = render_png(best["layout"], shell, "geometry", os.path.join(out, "strategies", f"{strat.strategy_id}_best.png"),
                         grid_cell=grid.cell, circulation_cells=best["layout"].circulation_cells, title=best["layout"].layout_id)
        img = cv2.resize(img, (700, int(img.shape[0] * 700 / img.shape[1])))
        tag = f"{strat.strategy_id}: {'VALIDO' if best['hard_valid'] else 'INVALIDO'} - {best.get('mode')} - {best.get('seats')} puestos"
        thumbs.append(label(img, tag, (0, 120, 0) if best["hard_valid"] else (0, 0, 180)))
    if thumbs:
        cv2.imwrite(os.path.join(out, "candidate_matrix.png"), mosaic(thumbs, 2))
    # ---- registros ------------------------------------------------------------------------------------
    dump(feas_reports, os.path.join(out, "strategy_feasibility_report.json"))
    dump(iterations, os.path.join(out, "iterations.json"))
    dump([{k: v for k, v in c.items() if k != "layout"} for c in candidates], os.path.join(out, "candidates.json"))
    summary = {"stats": stats, "gate_e1": "PASS" if (winner and winner["critique"]["broker_showable"]) else "FAIL",
               "winner": winner and {k: v for k, v in winner.items() if k not in ("layout", "critique")},
               "best_partial": best_partial and {k: v for k, v in best_partial.items() if k not in ("layout", "critique")},
               "ranking": [{"strategy_id": c["strategy_id"], "total_score": c["total_score"], "geometric_score": c["geometric_score"],
                            "architectural_score": c["architectural_score"]} for c in ranked],
               "e04_metrics": e04_metrics and {k: e04_metrics.get(k) for k in ("program_completeness", "hard_constraint_violations", "daylight_score",
                                                                                 "circulation_area_m2", "unallocated_area_m2", "valid_candidate_count")}}
    dump(summary, os.path.join(out, "summary.json"))
    print(f"[e05] hard_valid {stats['hard_valid_count']}/{stats['exact_attempts']} · aceptables {stats['architecturally_acceptable_count']} · Gate E1 {summary['gate_e1']} · {total_runtime} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
