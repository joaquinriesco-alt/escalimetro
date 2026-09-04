"""E07 — Orquestador: tres alternativas, QA interno, gates, comparación, handoff y lámina.

    PYTHONPATH=src python3 -m escalimetro.layout.e07.run --case cases/001_gps_403

Salidas en cases/<id>/layouts/E07/."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List

import cv2
import numpy as np

from ...case_context import CaseContext, from_case_dir
from ...renderer.side_by_side import _svg_to_bgr
from ...schemas.floorplate import Floorplate
from ..model import Layout, load_modules, load_program
from ..render import render_layout_svg, render_png, triptych
from ..e05.run import label as label_img, mosaic
from ..e06.qa import HumanCorrectionOperation
from ..e06.scale import scaled_shell
from .board import build_board
from .engine import Engine, geometric_difference
from .graph import SCHEMA as GRAPH_SCHEMA
from .pipeline import (AlternativeComparison, compare, gate_e1a, gate_e1c, gate_e1t, internal_qa,
                       presentation_handoff)
from .strategies import build_alternatives
from .visuals import comparison_png, performance_png, qa_summary_png, spatial_graph_svg

# E15 — el veredicto de fit es DATO DEL CASO, no conocimiento del motor. Vive en case.json y se
# completa con la identidad del caso (unidad, fuente, superficie publicada). Un caso sin veredicto
# declarado obtiene UNKNOWN: nunca el de otro caso.
DEFAULT_FIT = {
    "program": "OFFICE_BALANCED_48",
    "headcount": 48,
    "fit": "UNKNOWN",
    "fit_label": "FIT NO EVALUADO",
    "scale": "UNCONFIRMED",
    "scale_confidence": "LOW",
    "reason": "Este caso no declara un veredicto de robustez de escala en case.json.",
    "recommendation": "Confirma una dimensión real antes de comprometer capacidad.",
    "note": "Test-fit conceptual de space planning. No constituye proyecto de arquitectura.",
    "source": "sin análisis de robustez declarado para este caso.",
}


def fit_verdict_for(ctx) -> Dict:
    """Veredicto de fit del caso, con la identidad resuelta desde el CaseContext."""
    fit = dict(DEFAULT_FIT)
    fit.update(ctx.fit_verdict or {})
    unit = ctx.display_name or ctx.unit_label
    fit["unit"] = f"{unit} ({ctx.source_name})" if ctx.source_name else unit
    fit["published_area_m2"] = ctx.published_area_m2
    return fit


# QA interno (operaciones mínimas de reparación; el cliente final no ve esta capa)
QA_OPS: Dict[str, List[Dict]] = {}


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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--program", default="program_templates/office_balanced_48.json")
    ap.add_argument("--modules", default="program_templates/modules_office.json")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tl-warm", type=float, default=22.0)
    ap.add_argument("--tl-feas", type=float, default=25.0)
    ap.add_argument("--tl-opt", type=float, default=34.0)
    ap.add_argument("--early-stop", type=float, default=18.0)
    ap.add_argument("--cap", type=int, default=200)
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv)
    t_all = time.time()
    out = os.path.join(args.case, "layouts", "E07")
    os.makedirs(os.path.join(out, "alternatives"), exist_ok=True)
    ctx = from_case_dir(args.case)                     # E15: la identidad del inmueble es dato del caso
    FIT = fit_verdict_for(ctx)
    fp = Floorplate.load(ctx.require_floorplate())
    shell = scaled_shell(fp, 1.0)                      # escala nominal: E07 NO repite el barrido de E06
    mods, clr = load_modules(args.modules)
    prog = load_program(args.program)
    eng = Engine(shell, mods, prog, clr, seed=args.seed, layout_id_prefix=ctx.layout_id())
    specs = [s for s in build_alternatives(prog) if not args.only or s.alt in args.only.split(",")]
    print(f"[e07] {ctx.title()} · {ctx.published_area_label()} publicados · shell {shell.usable.area:.1f} m² · "
          f"{len(specs)} alternativas · escala nominal (UNCONFIRMED)")

    results, burdens, gates, handoffs = [], {}, {}, {}
    for spec in specs:
        spec.graph.save(os.path.join(out, "alternatives", f"spatial_graph_{spec.alt}.json"))
        r = eng.run(spec, tl_feas=args.tl_feas, tl_opt=args.tl_opt, early_stop_s=args.early_stop,
                    tl_warm=args.tl_warm, cap=args.cap)
        # ---- QA interno (revalidación determinista; sin rediseño) ----
        ops = [HumanCorrectionOperation(**o) for o in QA_OPS.get(spec.alt, [])]

        def revalidate(lay, _spec=spec):
            ok, viol, crit = _revalidate(eng, lay, _spec)
            return ok, viol, crit
        reason = ("sin errores evidentes del motor: el revisor sólo acepta la propuesta"
                  if not ops else "reparación de un error evidente del motor")
        lay_after, burden = internal_qa(spec.alt, r.layout, ops, mods, eng.validator, reason, revalidate)
        if ops:
            r.layout = lay_after
            ok, viol, crit = _revalidate(eng, lay_after, spec)
            r.hard_valid, r.violations, r.critique = ok, viol, crit.to_dict()
            r.metrics = lay_after.metrics
        results.append(r); burdens[spec.alt] = burden
        e1t = gate_e1t(r); e1a = gate_e1a(r, burden); e1c = gate_e1c(e1t, e1a)
        gates[spec.alt] = {"E1-T": e1t, "E1-A": e1a, "E1-C": e1c}
        d = os.path.join(out, "alternatives", spec.alt)
        os.makedirs(d, exist_ok=True)
        t = time.time()
        r.layout.save(os.path.join(d, "layout.json"))
        dump(r.metrics, os.path.join(d, "metrics.json"))
        dump(r.critique, os.path.join(d, "critique.json"))
        dump(burden.to_dict(), os.path.join(d, "internal_qa.json"))
        dump(gates[spec.alt], os.path.join(d, "gates.json"))
        render_png(r.layout, shell, "geometry", os.path.join(d, "layout_geometry.png"), grid_cell=eng.grid.cell,
                   circulation_cells=r.layout.circulation_cells, title=f"{spec.alt} — {spec.name}")
        render_png(r.layout, shell, "commercial", os.path.join(d, "layout_commercial.png"),
                   title=f"{ctx.unit_title()} · {spec.alt} {spec.name}")
        r.profile.render_s = round(time.time() - t, 2)
        r.profile.total_s = round(r.profile.total_s + r.profile.render_s, 2)
        print(f"[e07]   {spec.alt}: candidatos {r.profile.candidate_count} (válidos {r.profile.valid_candidate_count}, "
              f"elegido {r.profile.chosen_candidate}) · E1-T {e1t['status']} · E1-A {e1a['status']} · E1-C {e1c['status']} · "
              f"QA {burden.operation_count} ops / {burden.estimated_minutes} min est.")

    # ---- comparación, diferencia geométrica, handoff ------------------------------------------------
    comp = compare(results, burdens, gates)
    diffs = {}
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            diffs[f"{results[i].alt}vs{results[j].alt}"] = geometric_difference(results[i].layout, results[j].layout)
    for spec, r in zip(specs, results):
        row = next(x for x in comp.rows if x["alt"] == spec.alt)
        svg_t = render_layout_svg(r.layout, shell, "geometry", title=f"{spec.alt} — {spec.name}",
                                  grid_cell=eng.grid.cell, circulation_cells=r.layout.circulation_cells)
        svg_c = render_layout_svg(r.layout, shell, "commercial", title=f"{ctx.unit_title()} · {spec.alt} {spec.name}")
        r.layout.zones["shell_perimeter"] = [[round(x, 3), round(y, 3)] for x, y in shell.perimeter.exterior.coords]
        r.layout.zones["shell_core"] = [[[round(x, 3), round(y, 3)] for x, y in c.exterior.coords] for c in shell.core]
        r.layout.zones["shell_columns"] = [[round(v, 3) for v in c.bounds] for c in shell.columns]
        r.layout.zones["shell_entrance"] = [round(v, 3) for v in shell.entrance]
        r.layout.zones["scale_px_per_m"] = round(shell.px_per_m, 4)
        h = presentation_handoff(r, spec, FIT, svg_t, svg_c, gates[spec.alt], burdens[spec.alt], row, ctx=ctx)
        handoffs[spec.alt] = h
        dump(h, os.path.join(out, "alternatives", spec.alt, "presentation_handoff.json"))
        open(os.path.join(out, "alternatives", spec.alt, "layout_technical.svg"), "w", encoding="utf-8").write(svg_t)
        open(os.path.join(out, "alternatives", spec.alt, "layout_commercial.svg"), "w", encoding="utf-8").write(svg_c)
    dump({"geometry_locked": True, "presentation_standard": "ESCALIMETRO_PRESENTATION_STANDARD_01",
          "fit_verdict": FIT, "alternatives": {k: {"handoff": f"alternatives/{k}/presentation_handoff.json"} for k in handoffs},
          "comparison": comp.to_dict(), "geometric_difference": diffs},
         os.path.join(out, "presentation_handoff.json"))
    dump(comp.to_dict(), os.path.join(out, "alternative_comparison.json"))
    dump(FIT, os.path.join(out, "fit_verdict.json"))
    dump({r.alt: r.profile.to_dict() for r in results}, os.path.join(out, "performance_profile.json"))
    dump({k: v.to_dict() for k, v in burdens.items()}, os.path.join(out, "internal_qa.json"))
    dump(gates, os.path.join(out, "gates.json"))

    # ---- visuales ----------------------------------------------------------------------------------
    img = _svg_to_bgr(spatial_graph_svg([s.graph for s in specs]), 2400)
    cv2.imwrite(os.path.join(out, "spatial_graphs_abc.png"), img)
    tiles = []
    for spec, r in zip(specs, results):
        im = cv2.imread(os.path.join(out, "alternatives", spec.alt, "layout_geometry.png"))
        im = cv2.resize(im, (1500, int(im.shape[0] * 1500 / im.shape[1])))
        tiles.append(label_img(im, f"{spec.alt} - {spec.name} - {sum(p.seats for p in r.layout.placements)} puestos - "
                                   f"{'VALIDO' if r.hard_valid else 'INVALIDO'}", (0, 120, 0) if r.hard_valid else (0, 0, 180)))
    cv2.imwrite(os.path.join(out, "layouts_abc_geometry.png"), mosaic(tiles, 1))
    comparison_png(comp.rows, os.path.join(out, "alternative_comparison.png"))
    performance_png([r.profile.to_dict() for r in results], os.path.join(out, "performance_profile.png"))
    qa_summary_png([burdens[r.alt].to_dict() for r in results], os.path.join(out, "internal_qa_summary.png"))
    # lámina: sólo con layouts validados
    valid = [{"spec": s, "result": r} for s, r in zip(specs, results) if r.hard_valid]
    if len(valid) == len(results) and results:
        svg = build_board(valid, shell, FIT, ctx=ctx)
        open(os.path.join(out, "ESCALIMETRO_PRESENTATION_STANDARD_01.svg"), "w", encoding="utf-8").write(svg)
        board = _svg_to_bgr(svg, 3600)
        cv2.imwrite(os.path.join(out, "ESCALIMETRO_PRESENTATION_STANDARD_01.png"), board)
    else:
        print("[e07] lámina NO generada: la Presentation Standard sólo recibe alternativas validadas")
    total = round(time.time() - t_all, 1)
    dump({"total_runtime_s": total, "per_alternative_s": {r.alt: r.profile.total_s for r in results},
          "kpi_target_s": 120.0, "kpi_met": all(r.profile.total_s < 120 for r in results),
          "gates": {k: {g: v[g]["status"] for g in v} for k, v in gates.items()},
          "geometric_difference": diffs, "fit_verdict": FIT},
         os.path.join(out, "summary.json"))
    print(f"[e07] total {total} s · diferencia geométrica {diffs} · KPI<120s "
          f"{all(r.profile.total_s < 120 for r in results)}")
    return 0


def _revalidate(eng: Engine, lay: Layout, spec):
    from ..run import compute_metrics
    from ..scoring import score as score_layout
    weights = dict(eng.program["objectives_weights"]); weights.update(spec.weights)
    ok, viol, circ = eng.validator.validate(lay)
    lay.hard_violations = viol
    lay.circulation_cells = []
    if circ.get("ok"):
        lay.circulation_graph = circ["graph"]
        lay.circulation_cells = [(int(i), int(j)) for j, i in zip(*np.where(circ["used_corridors"]))]
        lay.scores = score_layout(lay, eng.shell, eng.grid, circ, eng.validator.zones, weights)
    lay.metrics = compute_metrics(lay, eng.validator, circ if circ else None)
    crit = eng.critic.critique(lay, lay.metrics, eng.e05_strategies[spec.spine_strategy].to_dict())
    return ok, viol, crit


if __name__ == "__main__":
    sys.exit(main())
