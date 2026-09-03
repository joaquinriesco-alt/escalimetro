import json

import jsonschema
import pytest

from escalimetro.schemas.floorplate import (SCHEMA_VERSION, Core, CoordinateSystem, Floorplate, Meta, Perimeter,
                                             Provenance, Scale, SourceImage, Status, json_schema)


def _fp():
    return Floorplate(SCHEMA_VERSION, "t", "U", SourceImage("x.jpg", 100, 80), CoordinateSystem(),
                      Scale(10.0, "manual", None, Meta(1, "manual", "confirmed")),
                      Perimeter([(0, 0), (50, 0), (50, 40), (0, 40)], meta=Meta(0.5, "cv_segmentation", "needs_confirmation")),
                      core=[Core([(50, 0), (60, 0), (60, 10), (50, 10)], meta=Meta(1, "manual", "confirmed"))],
                      area_m2=20.0, area_px2=2000.0)


def test_roundtrip_json(tmp_path):
    fp = _fp()
    p = tmp_path / "fp.json"
    fp.save(str(p))
    fp2 = Floorplate.load(str(p))
    assert fp2.perimeter.ring == fp.perimeter.ring
    assert fp2.core[0].meta.provenance == "manual"
    assert fp2.schema_version == SCHEMA_VERSION


def test_validates_against_json_schema():
    jsonschema.validate(json.loads(_fp().to_json()), json_schema())


def test_confidence_range_enforced():
    with pytest.raises(AssertionError):
        Meta(confidence=1.5)


def test_version_mismatch_rejected():
    d = _fp().to_dict(); d["schema_version"] = "9.9.9"
    with pytest.raises(ValueError):
        Floorplate.from_dict(d)


def test_to_m_flips_y_and_scales():
    fp = _fp()
    assert fp.to_m((0, 40)) == (0.0, 0.0)          # esquina inferior-izq en px → origen en m
    assert fp.to_m((50, 0)) == (5.0, 4.0)


def test_provenance_never_generated():
    assert "generated" not in [p.value for p in Provenance]
    assert {"unknown", "needs_confirmation"} <= {s.value for s in Status}
