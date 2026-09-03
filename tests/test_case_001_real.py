"""Regresión sobre el plano REAL (Caso 001, GPS 403). Requiere tesseract instalado (pase automático).
Si no hay tesseract, se salta el test automático y se prueba sólo la segmentación por color."""
import json
import os
import shutil

import cv2
import pytest

from escalimetro.pipeline import PipelineConfig, run
from escalimetro.segmentation import REGISTRY as SEG, SegmentationRequest
from run_benchmark import run_benchmark

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
HAS_TESS = shutil.which("tesseract") is not None


def _cfg(tmp, overrides=None):
    c = json.load(open(os.path.join(CASE, "case.json")))
    return PipelineConfig(c["case_id"], os.path.join(CASE, c["image"]), c["unit_label"], c["known_area_m2"],
                          c["known_area_kind"], "ocr", "auto", os.path.join(CASE, overrides) if overrides else None,
                          str(tmp), mask_open_px=c.get("mask_open_px", 3))


@pytest.mark.skipif(not HAS_TESS, reason="tesseract no instalado")
def test_pass_a_automatic_localization(tmp_path):
    fp = run(_cfg(tmp_path))
    assert fp.target_localization == "automatic"
    assert fp.pipeline["segmentation"] == "opencv_color"
    rep = run_benchmark(CASE, str(tmp_path / "bench.json"), str(tmp_path))
    assert rep["perimeter_iou"] >= 0.95
    assert abs(rep["area_error_pct_vs_gt_px"]) <= 3.0
    assert rep["core_iou"] >= 0.8
    assert rep["human_correction_burden"]["total_clicks"] == 0
    assert fp.scale.method == "published_area_inferred"
    assert fp.published_area_m2 == 543
    assert any(u.element.startswith("windows") for u in fp.unknowns)


@pytest.mark.skipif(not HAS_TESS, reason="tesseract no instalado")
def test_pass_b_assisted_reaches_gate(tmp_path):
    fp = run(_cfg(tmp_path, "overrides_assisted.json"))
    assert fp.target_localization == "automatic"          # los overrides no tocan la localización
    rep = run_benchmark(CASE, str(tmp_path / "bench.json"), str(tmp_path))
    assert rep["gate_e0"] == "PASS"
    assert rep["columns"]["f1"] == 1.0
    assert rep["human_correction_burden"]["estimated_seconds"] < 120


def test_color_segmentation_from_label_seed():
    img = cv2.imread(os.path.join(CASE, "original.png"))
    r = SEG["opencv_color"]().segment(SegmentationRequest(img, seed_points=[(494.5, 373.5)]))
    gt = json.load(open(os.path.join(CASE, "ground_truth", "floorplate_gt.json")))
    from metrics import polygon_iou
    import numpy as np
    cnts, _ = cv2.findContours(r.mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ring = [tuple(map(float, p)) for p in max(cnts, key=cv2.contourArea).reshape(-1, 2)]
    assert polygon_iou(ring, gt["perimeter"]["ring"]) >= 0.95
    assert r.mask[280, 500] == 0          # el núcleo no se fuga
    assert r.mask[300, 350] == 255        # brazo oeste de la 403 incluido
