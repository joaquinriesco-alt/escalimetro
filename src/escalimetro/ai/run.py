"""E08 — orquestación real sobre las tres alternativas de E07.

    PYTHONPATH=src python -m escalimetro.ai.run --case cases/001_gps_403

No regenera layouts. No toca el solver. Lee A/B/C de E07, los somete a los tres críticos, agrega, dirige
la lámina y renderiza de forma determinista. Salidas en cases/<id>/ai/E08/."""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Dict, List

import cv2

from ..layout.e06.scale import scaled_shell
from ..layout.e07.strategies import build_alternatives
from ..layout.model import Layout, load_program
from ..renderer.side_by_side import _svg_to_bgr
from ..schemas.floorplate import Floorplate
from .board02 import build_board02
from .config import load_configs, missing_keys
from .geometry_guard import geometry_hash
from .orchestrator import AIOrchestrator
from .reviewers import build_payload
from .telemetry import scrub
from .visuals import (ai_workflow_svg, latency_png, provider_architecture_svg, standard_compare_png,
                      disagreements_png)

ALTS = ["A", "B", "C"]
PRIORITY = {"A": "Prioriza eficiencia", "B": "Prioriza equilibrio", "C": "Prioriza colaboración"}


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(scrub(obj), open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=str)


def _callout(alt: str, row: Dict) -> str:
    if alt == "A":
        return f'Menos circulación y menos fragmentación: {row["work_blocks"]} bloques de trabajo.'
    if alt == "B":
        return f'La mejor luz en puestos de las tres y el directorio junto al acceso.'
    return f'Cuatro barrios de trabajo y {row["circulation_m2"]:.0f} m² de circulación, la menor de las tres.'


def presentation_context(specs, rows, fit) -> Dict:
    by = {r["alt"]: r for r in rows}
    return {
        "order": ALTS,
        "fit_copy": "El programa completo cabe en el rango de escala asumido.",
        "alternatives": [{
            "alt": s.alt, "name": s.name, "copy_short": s.copy_short, "priority": PRIORITY[s.alt],
            "ideal_for": s.ideal_for, "strengths": s.strengths, "callout": _callout(s.alt, by[s.alt]),
        } for s in specs],
        "metrics_by_alternative": {k: {m: by[k][m] for m in
                                       ("circulation_m2", "residual_m2", "daylight", "client_route",
                                        "work_blocks", "architectural_score")} for k in ALTS},
        "presentation_standard": "ESCALIMETRO_PRESENTATION_STANDARD_02",
        "audience": "broker, gerente general, real estate manager, gerente de administración",
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--program", default="program_templates/office_balanced_48.json")
    ap.add_argument("--mock-disagreement", default="", help="fixtures JSON para el panel de demostración")
    args = ap.parse_args(argv)
    t0 = time.time()
    e07 = os.path.join(args.case, "layouts", "E07")
    out = os.path.join(args.case, "ai", "E08")
    os.makedirs(out, exist_ok=True)

    fp = Floorplate.load(os.path.join(args.case, "outputs", "floorplate.json"))
    shell = scaled_shell(fp, 1.0)
    prog = load_program(args.program)
    specs = {s.alt: s for s in build_alternatives(prog)}
    comp = json.load(open(os.path.join(e07, "alternative_comparison.json"), encoding="utf-8"))
    rows = {r["alt"]: r for r in comp["rows"]}
    fit = json.load(open(os.path.join(e07, "fit_verdict.json"), encoding="utf-8"))

    cfgs = load_configs()
    miss = missing_keys(cfgs)
    orch = AIOrchestrator(project=os.path.basename(args.case), shell=shell)
    status = orch.provider_status()
    print(f"[e08] proveedores: " + " · ".join(f'{k}={v["status"]}' for k, v in status.items()))
    if miss:
        print(f"[e08] NOT EXECUTED — API KEY MISSING: {', '.join(miss)} · el pipeline continúa con el "
              f"crítico determinista (fail-clean)")

    results, decision_log = {}, {}
    for alt in ALTS:
        d = os.path.join(e07, "alternatives", alt)
        layout = Layout.load(os.path.join(d, "layout.json"))
        metrics = json.load(open(os.path.join(d, "metrics.json"), encoding="utf-8"))
        critique = json.load(open(os.path.join(d, "critique.json"), encoding="utf-8"))
        graph = json.load(open(os.path.join(e07, "alternatives", f"spatial_graph_{alt}.json"), encoding="utf-8"))
        payload = build_payload(alt, specs[alt].to_dict(), layout.to_dict(), metrics, critique, graph,
                               fit, rows[alt])
        h_before = geometry_hash(layout, shell)
        r = orch.review_alternative(alt, layout, payload,
                                    image_paths=[os.path.join(d, "layout_commercial.png")])
        assert geometry_hash(layout, shell) == h_before, "la geometría cambió alrededor de la capa de IA"
        results[alt] = r
        decision_log[alt] = {
            "geometry_hash": h_before,
            "seen_by": {k: ("structured payload + render" if k == "openai_vision" else "structured payload")
                        for k in r.reviews},
            "reviews": {k: (None if v is None else {"provider": v["provider"], "model": v["model"],
                                                    "prompt_version": v["prompt_version"],
                                                    "summary": v["summary"], "scores": v["scores"]})
                        for k, v in r.reviews.items()},
            "agreements": r.aggregated["agreements"],
            "disagreements": r.aggregated["disagreements"],
            "critical_disagreements": r.aggregated["critical_disagreements"],
            "status": r.aggregated["status"],
            "external_review_readiness": r.aggregated["external_review_readiness"],
            "errors": r.errors,
        }
        print(f'[e08] {alt}: {r.aggregated["status"]} · {r.aggregated["external_review_readiness"]} · '
              f'geometría intacta={r.geometry_intact} · errores={r.errors or "ninguno"}')

    dump({k: v.to_dict() for k, v in results.items()}, os.path.join(out, "reviews_abc.json"))
    dump(decision_log, os.path.join(out, "provider_decision_log.json"))

    # ---- dirección de lámina + render determinista ------------------------------------------------
    ctx = presentation_context([specs[a] for a in ALTS], list(rows.values()), fit)
    spec = orch.presentation_spec(ctx)
    dump(spec, os.path.join(out, "presentation_spec.json"))
    print(f'[e08] presentation spec: provider={spec["provider"]} model={spec["model"]} '
          f'prompt={spec["prompt_version"]}')

    board_alts, hashes_before = [], {}
    for alt in ALTS:
        d = os.path.join(e07, "alternatives", alt)
        lay = Layout.load(os.path.join(d, "layout.json"))
        hashes_before[alt] = geometry_hash(lay, shell)
        board_alts.append({"alt": alt, "layout": lay,
                           "metrics": json.load(open(os.path.join(d, "metrics.json"), encoding="utf-8")),
                           "critique": json.load(open(os.path.join(d, "critique.json"), encoding="utf-8")),
                           "row": rows[alt]})
    svg = build_board02(board_alts, shell, spec, fit)
    open(os.path.join(out, "ESCALIMETRO_PRESENTATION_STANDARD_02.svg"), "w", encoding="utf-8").write(svg)
    cv2.imwrite(os.path.join(out, "ESCALIMETRO_PRESENTATION_STANDARD_02.png"), _svg_to_bgr(svg, 3600))
    hashes_after = {a["alt"]: geometry_hash(a["layout"], shell) for a in board_alts}
    assert hashes_before == hashes_after, "el renderer de presentación mutó geometría"

    # ---- visuales ---------------------------------------------------------------------------------
    cv2.imwrite(os.path.join(out, "provider_architecture.png"),
                _svg_to_bgr(provider_architecture_svg(status), 2200))
    cv2.imwrite(os.path.join(out, "ai_workflow.png"), _svg_to_bgr(ai_workflow_svg(), 2200))
    mock = None
    if args.mock_disagreement:
        # Dry-run: fixtures MOCK pasadas por el agregador REAL. Sirven para ver la maquinaria de
        # desacuerdo funcionando; no son opiniones de ningún proveedor y están rotuladas como tales.
        from .review_aggregator import aggregate as _agg
        fx = json.load(open(args.mock_disagreement, encoding="utf-8"))
        mock = {k: _agg(k, v, {}).to_dict() for k, v in fx.items()}
        dump({"note": "FIXTURES MOCK — no son opiniones reales de ningún proveedor",
              "source_file": args.mock_disagreement, "aggregated": mock},
             os.path.join(out, "mock_dry_run.json"))
    disagreements_png({k: v.aggregated for k, v in results.items()}, mock,
                      os.path.join(out, "review_disagreements.png"))
    latency_png({k: v.latencies_ms for k, v in results.items()}, status,
                os.path.join(out, "ai_latency_profile.png"))
    standard_compare_png(os.path.join(args.case, "layouts", "E07",
                                      "ESCALIMETRO_PRESENTATION_STANDARD_01.png"),
                         os.path.join(out, "ESCALIMETRO_PRESENTATION_STANDARD_02.png"),
                         os.path.join(out, "presentation_standard_01_vs_02.png"))

    usage = orch.ledger.summary()
    dump(usage, os.path.join(out, "ai_usage_summary.json"))
    summary = {
        "runtime_s": round(time.time() - t0, 1),
        "api_execution_status": ("EXECUTED" if not miss else "NOT EXECUTED — API KEY MISSING"),
        "missing_keys": miss,
        "provider_status": {k: v["status"] for k, v in status.items()},
        "alternatives": {k: {"status": v.aggregated["status"],
                             "readiness": v.aggregated["external_review_readiness"],
                             "geometry_intact": v.geometry_intact,
                             "geometry_hash": v.geometry_hash_before}
                         for k, v in results.items()},
        "presentation_spec_provider": spec["provider"],
        "ai_calls": usage["calls"], "ai_cost": usage["total_cost"],
        "geometry_hashes_before": hashes_before, "geometry_hashes_after": hashes_after,
        "geometry_locked": hashes_before == hashes_after,
    }
    dump(summary, os.path.join(out, "summary.json"))
    print(f'[e08] listo en {summary["runtime_s"]} s · {summary["api_execution_status"]} · '
          f'geometry_locked={summary["geometry_locked"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
