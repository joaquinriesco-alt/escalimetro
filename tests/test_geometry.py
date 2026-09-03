import cv2
import numpy as np

from escalimetro.geometry import GeometryExtractor, scale_from_known_area, snap_orthogonal, snap_point_to_ring


def _l_mask():
    m = np.zeros((400, 500), np.uint8)
    cv2.fillPoly(m, [np.array([(50, 50), (400, 50), (400, 250), (250, 250), (250, 350), (50, 350)], np.int32)], 255)
    return m


def test_extractor_preserves_l_corner():
    g = GeometryExtractor().extract(_l_mask())
    assert len(g.ring) == 6, g.ring          # 6 vértices: el quiebre de la L se preserva
    assert abs(g.area_px2 - (350 * 200 + 200 * 100)) / (350 * 200 + 200 * 100) < 0.02


def test_extractor_does_not_oversimplify_small_jog():
    m = _l_mask()
    cv2.rectangle(m, (400, 50), (420, 80), 255, -1)  # un quiebre chico de 20x30 px (perímetro ~1300 → eps ~5px)
    g = GeometryExtractor().extract(m)
    assert len(g.ring) >= 8


def test_snap_orthogonal_keeps_diagonals():
    ring = [(0, 0), (100, 1), (100, 100), (50, 150), (0, 100)]   # un chaflán diagonal real
    out = snap_orthogonal(ring)
    assert out[0][1] == out[1][1]                                # lado casi horizontal → horizontal
    assert out[3] == (50, 150)                                   # el chaflán no se toca


def test_scale_from_known_area():
    s = scale_from_known_area(10000.0, 100.0, "useful")
    assert abs(s.px_per_m - 10.0) < 1e-9
    assert s.meta.provenance == "known_area"


def test_snap_point_to_ring():
    p = snap_point_to_ring((120, 40), [(0, 0), (100, 0), (100, 100), (0, 100)])
    assert p == (100.0, 40.0)
