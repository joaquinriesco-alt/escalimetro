from metrics import area_error_pct, hausdorff_px, point_set_pr, polygon_iou

SQ = [(0, 0), (100, 0), (100, 100), (0, 100)]


def test_iou_identity_and_half():
    assert polygon_iou(SQ, SQ) == 1.0
    assert abs(polygon_iou(SQ, [(0, 0), (50, 0), (50, 100), (0, 100)]) - 0.5) < 1e-9


def test_area_error_sign():
    assert area_error_pct(103, 100) == 3.0
    assert area_error_pct(97, 100) == -3.0


def test_hausdorff():
    assert hausdorff_px(SQ, [(0, 0), (110, 0), (110, 100), (0, 100)]) == 10.0


def test_point_set_pr():
    r = point_set_pr([(0, 0), (50, 50), (999, 999)], [(1, 1), (50, 50)], tol_px=5)
    assert (r["tp"], r["fp"], r["fn"]) == (2, 1, 0)
    assert r["recall"] == 1.0 and abs(r["precision"] - 2 / 3) < 1e-9
