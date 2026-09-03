"""Métricas del benchmark ETAPA 1. Todas en px salvo que se indique; el reporte las convierte a m
si hay escala en el ground truth.

Ground truth: cases/<id>/ground_truth/floorplate_gt.json (mismo schema, provenance=manual).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from shapely.geometry import Point as ShPoint, Polygon as ShPolygon
from shapely.ops import unary_union

Point = Tuple[float, float]


def _poly(ring) -> ShPolygon:
    p = ShPolygon(ring)
    return p if p.is_valid else p.buffer(0)


def polygon_iou(a: Sequence[Point], b: Sequence[Point]) -> float:
    pa, pb = _poly(a), _poly(b)
    u = pa.union(pb).area
    return float(pa.intersection(pb).area / u) if u > 0 else 0.0


def area_error_pct(pred_area: float, gt_area: float) -> float:
    return float((pred_area - gt_area) / gt_area * 100.0)


def hausdorff_px(a: Sequence[Point], b: Sequence[Point]) -> float:
    return float(_poly(a).exterior.hausdorff_distance(_poly(b).exterior))


def mean_boundary_distance_px(a: Sequence[Point], b: Sequence[Point], n: int = 400) -> float:
    """Distancia media simétrica entre contornos, muestreando n puntos. Más estable que Hausdorff."""
    ea, eb = _poly(a).exterior, _poly(b).exterior
    da = [eb.distance(ea.interpolate(t, normalized=True)) for t in np.linspace(0, 1, n, endpoint=False)]
    db = [ea.distance(eb.interpolate(t, normalized=True)) for t in np.linspace(0, 1, n, endpoint=False)]
    return float((np.mean(da) + np.mean(db)) / 2)


def centroid_error_px(pred_ring: Optional[Sequence[Point]], gt_ring: Sequence[Point]) -> Optional[float]:
    if not pred_ring:
        return None
    ca, cb = _poly(pred_ring).centroid, _poly(gt_ring).centroid
    return float(ca.distance(cb))


def point_set_pr(pred: Sequence[Point], gt: Sequence[Point], tol_px: float) -> Dict[str, float]:
    """Precision/recall con emparejamiento greedy por distancia (húngaro no hace falta a esta escala)."""
    pred, gt = list(pred), list(gt)
    if not gt and not pred:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0}
    used = set(); tp = 0
    for p in pred:
        best, bi = tol_px, None
        for i, g in enumerate(gt):
            if i in used:
                continue
            d = float(np.hypot(p[0] - g[0], p[1] - g[1]))
            if d <= best:
                best, bi = d, i
        if bi is not None:
            used.add(bi); tp += 1
    fp, fn = len(pred) - tp, len(gt) - tp
    prec = tp / len(pred) if pred else 0.0
    rec = tp / len(gt) if gt else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def entrance_error_px(pred: Sequence[Point], gt: Sequence[Point]) -> Optional[float]:
    """Error del acceso principal: distancia mínima entre el primer pred (main) y cualquier gt
    (si hay accesos simétricos en el GT, acertar cualquiera cuenta)."""
    if not gt or not pred:
        return None
    p = pred[0]
    return float(min(np.hypot(p[0] - g[0], p[1] - g[1]) for g in gt))


def segment_kind_accuracy(pred_segs, gt_segs, tol_px: float = 10.0) -> Dict[str, float]:
    """Accuracy semántica de lados: para cada lado GT, busca el lado pred cuyo punto medio esté
    a < tol y compara kind. Los lados sin match cuentan como error."""
    if not gt_segs:
        return {"accuracy": None, "n": 0}
    ok = 0
    for g in gt_segs:
        gm = ((g.start[0] + g.end[0]) / 2, (g.start[1] + g.end[1]) / 2)
        gl = ShPolygon([g.start, g.end, (g.end[0] + 0.01, g.end[1] + 0.01)]).exterior  # línea como polígono degenerado
        best = None; bd = 1e9
        for p in pred_segs:
            pm = ((p.start[0] + p.end[0]) / 2, (p.start[1] + p.end[1]) / 2)
            d = float(np.hypot(pm[0] - gm[0], pm[1] - gm[1]))
            if d < bd:
                bd, best = d, p
        if best is not None and bd <= tol_px * 4 and best.kind == g.kind:
            ok += 1
    return {"accuracy": ok / len(gt_segs), "n": len(gt_segs)}
