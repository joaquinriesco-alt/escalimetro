"""CLI: python -m escalimetro.layout.run --case cases/001_gps_403 --program program_templates/office_balanced_48.json
                                         --layout-id OFFICE_BALANCED_001 --candidates 12 --seed 1
Salidas en cases/<id>/layouts/<layout_id>/: layout.json, layout_geometry.png/svg, layout_commercial.png/svg,
metrics.json, comparison_*.png."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

from ..case_context import SEMANTICS_ARTIFACT_MISSING, from_case_dir
from ..schemas.floorplate import Floorplate
from .model import Layout, load_modules, load_program
from .render import render_png, triptych
from .shell_adapter import shell_from_floorplate
from .solver import Solver


def compute_metrics(layout: Layout, solver: Solver, circ) -> dict:
    g = solver.grid
    usable = float(g.free_base.sum()) * g.cell ** 2
    prog_area = sum(p.w * p.d for p in layout.placements)
    circ_area = float(circ["used_corridors"].sum()) * g.cell ** 2 if (circ and "used_corridors" in circ) else None
    free = circ["free"] if circ else None
    unalloc = (float(free.sum()) * g.cell ** 2 - (circ_area or 0)) if (free is not None and circ_area is not None) else None
    counts = {}
    for p in layout.placements:
        counts[p.module] = counts.get(p.module, 0) + 1
    seats = sum(p.seats for p in layout.placements if p.module.startswith("workstation"))
    need = solver.program.get("open_workstations_exact", 40)
    prog = solver.program["program"]
    complete = all(counts.get(pp["module"], 0) == pp["count"] for pp in prog if pp["module"] != "workstation_cluster") and seats == need
    collisions = [v for v in layout.hard_violations if v.startswith("colisión")]
    return {
        "program_completeness": {"complete": complete, "open_seats": f"{seats}/{need}", "rooms": counts},
        "hard_constraint_violations": len(layout.hard_violations), "violations": layout.hard_violations,
        "collisions": len(collisions),
        "circulation_connectivity": bool(circ and circ["ok"]),
        "daylight_score": layout.scores.get("objectives", {}).get("daylight_utilization") if layout.scores else None,
        "adjacency_score": layout.scores.get("objectives", {}).get("adjacency_quality") if layout.scores else None,
        "usable_area_m2": round(usable, 1),
        "net_programmed_area_m2": round(prog_area, 1),
        "circulation_area_m2": circ_area and round(circ_area, 1),
        "unallocated_area_m2": unalloc and round(unalloc, 1),
        "wasted_area_m2": layout.scores.get("areas", {}).get("wasted_m2") if layout.scores else None,
        "embedded_columns": sum(1 for p in layout.placements if p.meta.get("embedded_columns")),
        "scale_note": "Dimensiones sujetas a confirmación de escala (published_area_inferred, confianza LOW).",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--program", default="program_templates/office_balanced_48.json")
    ap.add_argument("--modules", default="program_templates/modules_office.json")
    ap.add_argument("--layout-id", default="OFFICE_BALANCED_001")
    ap.add_argument("--candidates", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--improve-rounds", type=int, default=1)
    args = ap.parse_args(argv)
    ctx = from_case_dir(args.case)                     # E15: identidad y rutas vienen del caso
    fp = Floorplate.load(ctx.require_floorplate())
    shell = shell_from_floorplate(fp)
    mods, clr = load_modules(args.modules)
    prog = load_program(args.program)
    out = os.path.join(args.case, "layouts", args.layout_id)
    os.makedirs(out, exist_ok=True)
    S = Solver(shell, mods, prog, clr)
    print(f"[layout] shell usable {shell.usable.area:.1f} m², pilares {len(shell.columns)}, bahías {len(S.bays)}, escala {shell.scale_confidence}")
    res = S.solve(n_candidates=args.candidates, seed=args.seed, improve_rounds=args.improve_rounds, log=print)
    lay: Layout = res["best"]
    lay.layout_id = args.layout_id
    ok, viol, circ = S.validate(lay)
    lay.hard_violations = viol
    if circ and circ.get("ok"):
        lay.circulation_graph = circ.get("graph", {})
        lay.circulation_cells = [(int(i), int(j)) for j, i in zip(*np.where(circ["used_corridors"]))]
    lay.metrics = compute_metrics(lay, S, circ if circ else None)
    lay.metrics.update({"candidate_count": res["candidate_count"], "valid_candidate_count": res["valid_candidate_count"],
                        "runtime_s": res["runtime_s"], "best_total_score": res["best_score"], "status": res.get("status"),
                        "top_scores": res.get("top_scores"), "improve_moves_accepted": res.get("improve_moves_accepted"),
                        "search": getattr(S, "last_search", {}) and {k: v for k, v in S.last_search.items() if k not in ("strips", "sections")}})
    lay.zones["areas_m2"] = S.zones["areas_m2"]
    lay.save(os.path.join(out, "layout.json"))
    json.dump(lay.metrics, open(os.path.join(out, "metrics.json"), "w"), indent=2, ensure_ascii=False, default=lambda o: int(o) if hasattr(o, "__int__") else str(o))
    geo = render_png(lay, shell, "geometry", os.path.join(out, "layout_001_geometry.png"), grid_cell=S.grid.cell,
                     circulation_cells=lay.circulation_cells, title=args.layout_id)
    com = render_png(lay, shell, "commercial", os.path.join(out, "layout_001_commercial.png"), title=args.layout_id.replace("_", " "))
    cv2.imwrite(os.path.join(out, "geometry_vs_commercial.png"), triptych([(geo, "LAYOUT GEOMETRY"), (com, "LAYOUT COMMERCIAL")]))
    orig = cv2.imread(ctx.artifacts.source_image)
    sem_path = ctx.artifacts.resolve_semantics_png()
    shell_png = cv2.imread(sem_path) if sem_path else None
    if shell_png is None:
        # E15 §14 — antes esto se omitía en silencio. Un artefacto ausente se reporta; no cambia el fit.
        print(f"[layout] {SEMANTICS_ARTIFACT_MISSING}: ninguno de "
              f"{[os.path.basename(p) for p in ctx.artifacts.semantics_png_candidates]} existe en "
              f"{ctx.artifacts.outputs_dir}; el tríptico no se genera (el resultado de fit no cambia)")
    if orig is None:
        print(f"[layout] SOURCE_IMAGE_MISSING: {ctx.artifacts.source_image}")
    if orig is not None and shell_png is not None:
        cv2.imwrite(os.path.join(out, "original_shell_layout.png"),
                    triptych([(orig, f"ORIGINAL {ctx.source_label().upper()}"),
                              (shell_png, "SHELL ESCALIMETRO"), (com, f"LAYOUT {args.layout_id}")]))
    print(f"[layout] {res.get('status')} valid {res['valid_candidate_count']}/{res['candidate_count']} runtime {res['runtime_s']}s score {res['best_score']}")
    print(f"[layout] violaciones: {viol[:6]}")
    print(json.dumps(lay.metrics["program_completeness"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
