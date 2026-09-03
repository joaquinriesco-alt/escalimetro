"""Compara cases/<id>/outputs/floorplate.json contra cases/<id>/ground_truth/floorplate_gt.json.

Umbrales Gate E0 (docs/BENCHMARK.md):
  iou >= 0.95 · |area_err| <= 3% · core_centroid_err <= 1.0 m · entrance_err <= 1.5 m
  columnas f1 >= 0.8 (o corregibles) · semántica de lados >= 0.8
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from escalimetro.schemas.floorplate import Floorplate  # noqa: E402
from metrics import (area_error_pct, centroid_error_px, entrance_error_px, hausdorff_px,  # noqa: E402
                     mean_boundary_distance_px, point_set_pr, polygon_iou, segment_kind_accuracy)

GATE = {"iou_min": 0.95, "area_err_pct_max": 3.0, "core_err_m_max": 1.0, "entrance_err_m_max": 1.5,
        "column_f1_min": 0.8, "segment_acc_min": 0.8}


def human_burden(pred: Floorplate, case_dir: str) -> dict:
    """HUMAN CORRECTION BURDEN a partir del overrides usado por la predicción. Un click por punto,
    un click por confirmación; polígonos = un click por vértice. Tiempo estimado a 4 s/click
    (supuesto, no medido con UI)."""
    name = pred.pipeline.get("overrides")
    ov = {}
    if name and os.path.exists(os.path.join(case_dir, name)):
        ov = json.load(open(os.path.join(case_dir, name), encoding="utf-8"))
    b = {"seed_clicks": len(ov.get("seed_points", [])) + (1 if ov.get("bbox") else 0),
         "confirm_clicks": len(ov.get("confirm", [])),
         "entrance_clicks": len(ov.get("entrances", [])) + (1 if ov.get("entrance_choice") else 0),
         "daylight_relabels": len(ov.get("daylight_confirm") or {}),
         "north_declared": 1 if ov.get("north_angle_deg") is not None else 0,
         "column_added": len((ov.get("columns") or {}).get("add", [])),
         "column_removed": len((ov.get("columns") or {}).get("remove_near", [])),
         "window_points": 2 * len(ov.get("windows", [])),
         "facade_relabels": len(ov.get("facade_kinds") or {}),
         "perimeter_vertices_drawn": len((ov.get("perimeter") or {}).get("ring", [])),
         "core_vertices_drawn": sum(len(c.get("ring", [])) for c in ov.get("core", [])),
         "points_moved": 0}
    clicks = sum(v for k, v in b.items())
    b["total_clicks"] = clicks
    b["estimated_seconds"] = clicks * 4
    b["target_localization"] = pred.target_localization
    return b


def shell_metrics(pred: Floorplate, gt: Floorplate, ppm: float | None) -> dict:
    """Métricas E03: accesos por candidatos, pilares v2, luz natural vs GT."""
    import numpy as np
    tol = (1.5 * ppm) if ppm else 12
    gt_ent = [e.point for e in gt.entrances]
    cands = [c.point for c in pred.entrance_candidates]
    prim = pred.primary_entrance
    d_prim = min(float(np.hypot(prim.point[0] - g[0], prim.point[1] - g[1])) for g in gt_ent) if (prim and gt_ent) else None
    cand_pr = point_set_pr(cands, gt_ent, tol)
    # luz: por lado GT, el lado pred más cercano (punto medio)
    def mid(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    agree = miss = false_claim = n = 0
    for g in gt.daylight_segments:
        if g.classification == "opaque" or "exterior_unknown" == g.classification:
            continue                                        # sólo lados GT con glazing observado
        gm = mid(g.start, g.end)
        best = min(pred.daylight_segments, key=lambda p: np.hypot(mid(p.start, p.end)[0] - gm[0], mid(p.start, p.end)[1] - gm[1]),
                   default=None)
        if best is None:
            continue
        n += 1
        if best.classification in ("likely_glazing", "confirmed_glazing"):
            agree += 1
        elif best.classification == "exterior_unknown":
            miss += 1
        else:
            false_claim += 1
    # falsos claims inversos: pred dice glazing donde GT dice opaque
    fc2 = 0
    for p in pred.daylight_segments:
        if p.classification in ("likely_glazing", "confirmed_glazing"):
            pm = mid(p.start, p.end)
            g = min(gt.daylight_segments, key=lambda g: np.hypot(mid(g.start, g.end)[0] - pm[0], mid(g.start, g.end)[1] - pm[1]), default=None)
            if g is not None and g.classification == "opaque":
                fc2 += 1
    exterior_kinds = [s.kind for s in pred.facade_segments]
    return {
        "primary_entrance": prim and {"point": prim.point, "status": prim.status, "confidence": prim.confidence,
                                      "error_px": d_prim and round(d_prim, 1), "error_m": (d_prim and ppm) and round(d_prim / ppm, 2)},
        "entrance_candidates": {"n": len(cands), "recall_of_gt": cand_pr["recall"], "precision": cand_pr["precision"], "tol_px": round(tol, 1)},
        "daylight": {"gt_glazing_sides": n, "agree_likely_or_confirmed": agree, "conservative_unknown": miss,
                     "false_claims_on_glazing": false_claim, "false_glazing_on_opaque": fc2,
                     "accuracy": (agree / n) if n else None},
        "exterior_facade_classified": sum(1 for k in exterior_kinds if k == "facade") > 0 and all(k != "unknown" for k in exterior_kinds),
        "readiness": pred.shell_readiness.__dict__ if pred.shell_readiness else None,
    }


def run_benchmark(case_dir: str, out_path: str | None = None, pred_dir: str | None = None) -> dict:
    pred_dir = pred_dir or os.path.join(case_dir, "outputs")
    pred = Floorplate.load(os.path.join(pred_dir, "floorplate.json"))
    gt = Floorplate.load(os.path.join(case_dir, "ground_truth", "floorplate_gt.json"))
    ppm = gt.scale.px_per_m or pred.scale.px_per_m
    scale_note = "GT" if gt.scale.px_per_m else f"pred ({pred.scale.method}) — conversión a m NO independiente"
    to_m = (lambda px: px / ppm) if ppm else (lambda px: None)

    iou = polygon_iou(pred.perimeter.ring, gt.perimeter.ring)
    # área: contra GT en px² (independiente de la escala inyectada por known_area) y en m² si GT trae área
    area_px_err = area_error_pct(pred.area_px2, gt.area_px2) if gt.area_px2 else None
    area_m_err = area_error_pct(pred.area_m2, gt.area_m2) if (gt.area_m2 and pred.area_m2) else None
    haus = hausdorff_px(pred.perimeter.ring, gt.perimeter.ring)
    mbd = mean_boundary_distance_px(pred.perimeter.ring, gt.perimeter.ring)
    core_err = centroid_error_px(pred.core[0].ring, gt.core[0].ring) if (gt.core and pred.core) else None
    core_iou = polygon_iou(pred.core[0].ring, gt.core[0].ring) if (gt.core and pred.core) else None
    col_tol = 0.6 * ppm if ppm else 10
    cols = point_set_pr([c.center for c in pred.columns], [c.center for c in gt.columns], col_tol)
    ent = entrance_error_px([e.point for e in pred.entrances], [e.point for e in gt.entrances])
    sem = segment_kind_accuracy(pred.facade_segments, gt.facade_segments)

    rep = {
        "case_id": pred.case_id, "px_per_m_used": ppm, "px_per_m_source": scale_note,
        "vertices_gt": len(gt.perimeter.ring), "vertices_pred": len(pred.perimeter.ring),
        "core_iou": core_iou and round(core_iou, 3),
        "perimeter_iou": round(iou, 4),
        "area_error_pct_vs_gt_px": None if area_px_err is None else round(area_px_err, 2),
        "area_error_pct_vs_gt_m2": None if area_m_err is None else round(area_m_err, 2),
        "hausdorff_px": round(haus, 1), "hausdorff_m": to_m(haus) and round(to_m(haus), 2),
        "mean_boundary_dist_px": round(mbd, 1), "mean_boundary_dist_m": to_m(mbd) and round(to_m(mbd), 3),
        "core_centroid_err_px": core_err and round(core_err, 1), "core_centroid_err_m": core_err and to_m(core_err) and round(to_m(core_err), 2),
        "columns": cols, "column_tol_px": round(col_tol, 1),
        "entrance_err_px": ent and round(ent, 1), "entrance_err_m": ent and to_m(ent) and round(to_m(ent), 2),
        "segment_semantic": sem,
        "pred_unknowns": [u.element for u in pred.unknowns],
        "human_correction_burden": human_burden(pred, case_dir),
    }
    checks = {
        "iou": iou >= GATE["iou_min"],
        "area": area_px_err is not None and abs(area_px_err) <= GATE["area_err_pct_max"],
        "core": core_err is not None and ppm and to_m(core_err) <= GATE["core_err_m_max"],
        "entrance": ent is not None and ppm and to_m(ent) <= GATE["entrance_err_m_max"],
        "columns": cols["f1"] >= GATE["column_f1_min"],
        "segments": (sem["accuracy"] or 0) >= GATE["segment_acc_min"],
    }
    rep["gate_checks"] = {k: bool(v) for k, v in checks.items()}
    rep["gate_e0"] = "PASS" if all(checks.values()) else "FAIL"
    # ---- E03: shell semántico y Gate E0.5 ----
    if pred.shell_readiness is not None and pred.daylight_segments:
        sm = shell_metrics(pred, gt, ppm)
        rep["shell"] = sm
        burden = rep["human_correction_burden"]
        r = pred.shell_readiness
        prim_ok = bool(sm["primary_entrance"] and sm["primary_entrance"]["status"] == "confirmed"
                       and sm["primary_entrance"]["error_px"] is not None and sm["primary_entrance"]["error_px"] <= sm["entrance_candidates"]["tol_px"])
        checks05 = {
            "iou": iou >= GATE["iou_min"],
            "core": core_err is not None and ppm and to_m(core_err) <= GATE["core_err_m_max"],
            "primary_entrance_confirmed_and_correct": prim_ok,
            "columns_100pct": cols["recall"] >= 1.0 and cols["precision"] >= 0.9,
            "exterior_facade_classified": bool(sm["exterior_facade_classified"]),
            "daylight_available": sm["daylight"]["agree_likely_or_confirmed"] > 0,
            "no_false_claims": sm["daylight"]["false_claims_on_glazing"] == 0 and sm["daylight"]["false_glazing_on_opaque"] == 0 and cols["fp"] == 0,
            "burden_under_60s": burden["estimated_seconds"] < 60,
            "ready_for_layout": bool(r.ready_for_layout),
        }
        rep["gate_e05_checks"] = checks05
        rep["gate_e05"] = "PASS" if all(checks05.values()) else "FAIL"
    out_path = out_path or os.path.join(pred_dir, "benchmark.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    return rep


if __name__ == "__main__":
    print(json.dumps(run_benchmark(sys.argv[1]), indent=2, ensure_ascii=False))
