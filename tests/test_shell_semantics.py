"""E03 — shell semántico sobre el Caso 001 real."""
import json
import os
import shutil

import cv2
import numpy as np
import pytest

from escalimetro.pipeline import PipelineConfig, run
from escalimetro.schemas.floorplate import Floorplate, SCHEMA_VERSION
from escalimetro.semantics.columns_v2 import detect_columns_v2
from escalimetro.semantics.daylight import classify_daylight
from escalimetro.semantics.entrance import choose_primary, detect_entrance_candidates
from run_benchmark import run_benchmark

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
HAS_TESS = shutil.which("tesseract") is not None
GT = json.load(open(os.path.join(CASE, "ground_truth", "floorplate_gt.json")))
GT_ENT = [tuple(e["point"]) for e in GT["entrances"]]
GT_COLS = [tuple(c["center"]) for c in GT["columns"]]


@pytest.fixture(scope="module")
def base():
    """Floorplate geométrico del pase A (sin semántica) + máscaras, para probar los detectores aislados."""
    fp = Floorplate.load(os.path.join(CASE, "outputs", "pass_a", "floorplate.json"))
    img = cv2.imread(os.path.join(CASE, "original.png"))
    raw = cv2.imread(os.path.join(CASE, "outputs", "pass_a", "mask.png"), 0)
    opened = cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    return fp, img, raw, opened


def test_entrance_candidates_cover_gt(base):
    fp, img, raw, opened = base
    c = detect_entrance_candidates(img, fp.perimeter.ring, fp.facade_segments, [k.ring for k in fp.core], raw, opened, fp.scale.px_per_m)
    assert c, "sin candidatos"
    for g in GT_ENT:
        assert min(np.hypot(x.point[0] - g[0], x.point[1] - g[1]) for x in c) <= 12.5   # 1.5 m
    best, status, _ = choose_primary(c)
    assert best is not None and min(np.hypot(best.point[0] - g[0], best.point[1] - g[1]) for g in GT_ENT) <= 12.5
    assert all(len(x.evidence) >= 2 for x in c)                 # cada candidato explica por qué
    assert all(x.segment_index is not None for x in c)


def test_columns_v2_precision_recall(base):
    fp, img, raw, _ = base
    boxes = [h["bbox"] for h in fp.pipeline["vision_hints"] if h["bbox"]]
    cs = detect_columns_v2(img, raw, fp.scale.px_per_m, exclude_bboxes=boxes)
    tp = sum(1 for c in cs if min(np.hypot(c.center[0] - g[0], c.center[1] - g[1]) for g in GT_COLS) <= 6)
    assert tp / len(cs) >= 0.9
    assert tp / len(GT_COLS) >= 0.7
    assert any(any(e.startswith("grid:") for e in c.evidence) for c in cs)   # la modulación aportó


def test_daylight_no_false_claims(base):
    fp, img, _, _ = base
    d = classify_daylight(img, fp.perimeter.ring, fp.facade_segments, fp.scale.px_per_m)
    assert all(x.classification != "confirmed_glazing" for x in d)          # sólo el humano confirma
    assert all(x.classification == "opaque" for x in d if x.facade_kind in ("party_wall", "core_wall"))
    assert any(x.classification == "likely_glazing" for x in d)
    for x in d:
        assert 0.0 <= x.daylight_priority <= 1.0 and x.evidence


@pytest.mark.skipif(not HAS_TESS, reason="tesseract no instalado")
def test_auto_shell_not_ready_without_human(tmp_path):
    c = json.load(open(os.path.join(CASE, "case.json")))
    fp = run(PipelineConfig(c["case_id"], os.path.join(CASE, c["image"]), c["unit_label"], c["known_area_m2"], c["known_area_kind"],
                            "ocr", "auto", None, str(tmp_path), mask_open_px=c.get("mask_open_px", 3)))
    assert fp.schema_version == SCHEMA_VERSION == "0.2.0"
    assert fp.shell_readiness.ready_for_layout is False
    assert "primary_entrance" in fp.shell_readiness.requires_confirmation
    assert fp.primary_entrance is not None and fp.primary_entrance.status in ("needs_confirmation", "inferred")
    assert fp.north_arrow.detected is False
    for name in ("shell_semantics_403.png", "shell_comparison_403.png", "shell_semantics.svg"):
        assert os.path.exists(os.path.join(tmp_path, name))


@pytest.mark.skipif(not HAS_TESS, reason="tesseract no instalado")
def test_confirmed_shell_passes_gate_e05(tmp_path):
    c = json.load(open(os.path.join(CASE, "case.json")))
    fp = run(PipelineConfig(c["case_id"], os.path.join(CASE, c["image"]), c["unit_label"], c["known_area_m2"], c["known_area_kind"],
                            "ocr", "auto", os.path.join(CASE, "overrides_shell.json"), str(tmp_path), mask_open_px=c.get("mask_open_px", 3)))
    assert fp.shell_readiness.ready_for_layout is True
    assert fp.target_localization == "automatic"
    rep = run_benchmark(CASE, str(tmp_path / "b.json"), str(tmp_path))
    assert rep["gate_e05"] == "PASS", rep["gate_e05_checks"]
    assert rep["human_correction_burden"]["estimated_seconds"] < 60
    assert rep["shell"]["daylight"]["false_claims_on_glazing"] == 0
    assert rep["columns"]["fp"] == 0


def test_schema_0_1_1_still_loads(tmp_path):
    fp = Floorplate.load(os.path.join(CASE, "outputs", "pass_a", "floorplate.json"))
    d = fp.to_dict(); d["schema_version"] = "0.1.1"
    for k in ("entrance_candidates", "primary_entrance", "daylight_segments", "column_candidates", "shell_readiness", "north_arrow"):
        d.pop(k, None)
    p = tmp_path / "old.json"; p.write_text(json.dumps(d))
    old = Floorplate.load(str(p))
    assert old.entrance_candidates == [] and old.shell_readiness.ready_for_layout is False
