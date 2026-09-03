"""Los adapters remotos deben fallar limpio sin API key y no ser requeridos por la geometría."""
import os

import numpy as np
import pytest

from escalimetro.segmentation import REGISTRY as SEG, SegmentationRequest
from escalimetro.vision import REGISTRY as VIS, ManualVisionInterpreter

IMG = np.full((50, 50, 3), 255, np.uint8)


@pytest.mark.parametrize("name", ["openai", "anthropic", "gemini"])
def test_remote_vlm_requires_key(name, monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="falta"):
        VIS[name]().interpret(IMG, "Oficina 403")


def test_manual_vlm_parses_hints():
    r = ManualVisionInterpreter([{"kind": "unit_region", "confidence": 0.9, "point": [10, 10]}]).interpret(IMG, "U")
    assert r.best("unit_region").point == (10, 10)


def test_sam2_requires_checkpoint(monkeypatch):
    monkeypatch.delenv("ESCALIMETRO_SAM2_CKPT", raising=False)
    with pytest.raises(RuntimeError):
        SEG["sam2"]().segment(SegmentationRequest(IMG, seed_points=[(5, 5)]))


def test_geometry_has_no_provider_imports():
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "escalimetro", "geometry", "extractor.py")).read()
    for bad in ("openai", "anthropic", "google", "sam2", "vision", "segmentation"):
        assert bad not in src
