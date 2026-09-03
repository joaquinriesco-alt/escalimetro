"""End-to-end sobre el fixture sintético. Valida MECÁNICA, no fidelidad a planos reales."""
import json
import os

import pytest

from escalimetro.pipeline import PipelineConfig, run
from escalimetro.schemas.floorplate import Floorplate
from run_benchmark import run_benchmark


@pytest.fixture(scope="module")
def result(synthetic_case):
    c = json.load(open(os.path.join(synthetic_case, "case.json")))
    cfg = PipelineConfig(c["case_id"], os.path.join(synthetic_case, "original.jpg"), c["unit_label"],
                         c["known_area_m2"], c["known_area_kind"], "manual", "opencv_flood",
                         os.path.join(synthetic_case, "overrides.json"), os.path.join(synthetic_case, "outputs"))
    fp = run(cfg)
    rep = run_benchmark(synthetic_case)
    return fp, rep, synthetic_case


def test_outputs_exist(result):
    _, _, d = result
    for f in ["floorplate.json", "planta_escalimetro.svg", "planta_escalimetro_px.svg", "side_by_side.png",
              "overlay.png", "mask.png", "original_grid.png", "benchmark.json"]:
        assert os.path.exists(os.path.join(d, "outputs", f)), f


def test_perimeter_fidelity(result):
    fp, rep, _ = result
    assert len(fp.perimeter.ring) == 6
    assert rep["perimeter_iou"] >= 0.98
    assert rep["hausdorff_px"] <= 4


def test_scale_recovered_from_known_area(result):
    fp, rep, _ = result
    assert abs(fp.scale.px_per_m - rep["px_per_m_used"]) / rep["px_per_m_used"] < 0.01
    assert abs(rep["area_error_pct_vs_gt_px"]) <= 3.0


def test_door_does_not_leak_into_corridor(result):
    fp, _, _ = result
    xs = [p[0] for p in fp.perimeter.ring]
    assert max(xs) < 770   # el pasillo empieza en x=560..760; si fugara, max x ≈ 760+ y aparecerían más vértices


def test_columns_entrance_core(result):
    _, rep, _ = result
    assert rep["columns"]["f1"] == 1.0
    assert rep["entrance_err_px"] <= 8
    assert rep["core_centroid_err_px"] <= 1


def test_semantics_and_gate(result):
    fp, rep, _ = result
    assert rep["segment_semantic"]["accuracy"] >= 0.8
    assert rep["gate_e0"] == "PASS"
    assert any(u.element.startswith(("windows", "daylight")) for u in fp.unknowns)   # lo no inferible queda registrado, no inventado


def test_svg_is_valid_xml_and_has_no_raster(result):
    import xml.etree.ElementTree as ET
    _, _, d = result
    svg = open(os.path.join(d, "outputs", "planta_escalimetro.svg")).read()
    ET.fromstring(svg)
    assert "<image" not in svg                                  # geometría, nunca píxeles


def test_provenance_on_every_element(result):
    fp, _, _ = result
    for c in fp.columns + fp.entrances + fp.core + fp.facade_segments:
        assert c.meta.provenance != "unknown" and 0 <= c.meta.confidence <= 1
    assert fp.perimeter.meta.provenance == "cv_segmentation"
    assert fp.entrances[0].meta.provenance == "manual"


def test_manual_perimeter_override(result, tmp_path):
    fp, _, d = result
    ov = {"perimeter": {"ring": [[200, 200], [500, 200], [500, 600], [200, 600]]}, "known_area": {"m2": 100, "kind": "useful"}}
    json.dump(ov, open(tmp_path / "ov.json", "w"))
    c = json.load(open(os.path.join(d, "case.json")))
    fp2 = run(PipelineConfig("t", os.path.join(d, "original.jpg"), "U", None, "unknown", "null", "opencv_flood",
                             str(tmp_path / "ov.json"), str(tmp_path / "out")))
    assert fp2.perimeter.meta.provenance == "manual" and fp2.perimeter.meta.status == "confirmed"
    assert abs(fp2.area_m2 - 100) < 0.5
