"""E17 — spike de representación de ANCHO. Ninguna de estas representaciones toca el motor.

Los tests fijan lo esencial y barato de reproducir: que el banco es determinista, que el ancho
dibujado y el ancho estimado guardan orden, que la magnitud escala con la resolución —lo contrario
de lo que hace `structural_ink`— y que nada de esto está conectado al runtime.
"""
import json
import os
import sys

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "tests", "fixtures", "structural_width"))
import width_bench_scene as B  # noqa: E402

from escalimetro.segmentation.structural import structural_ink  # noqa: E402

ART = os.path.join(ROOT, "cases", "generalization", "E17")
ESCALERA = ["A_w1", "B_w2", "C_w3", "D_w4", "E_w6", "F_w8"]


def _edge_pair_width(img):
    """La representación mejor puntuada del spike, reproducida aquí en tres líneas para que el test
    no dependa de un artefacto: bordes de Canny y distancia entre ellos."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    e = cv2.Canny(g, 40, 120)
    return 2.0 * cv2.distanceTransform((e == 0).astype(np.uint8), cv2.DIST_L2, 5)


def _mediana_en(mask, w):
    from skimage.morphology import skeletonize
    sk = skeletonize(mask > 0)
    v = w[sk]
    v = v[np.isfinite(v) & (v > 0)]
    return float(np.median(v)) if v.size else 0.0


def test_el_banco_es_determinista():
    a, _ = B.render(800)
    b, _ = B.render(800)
    assert np.array_equal(a, b)
    assert B.GENERATOR_VERSION.startswith("e17-width-bench/")


@pytest.mark.parametrize("side", [800, 1400])
def test_el_ancho_estimado_preserva_el_orden_de_la_escalera(side):
    img, gt = B.render(side)
    w = _edge_pair_width(img)
    est = [_mediana_en(gt[p], w) for p in ESCALERA]
    pares = [(i, j) for i in range(len(est)) for j in range(i + 1, len(est))]
    ok = sum(1 for i, j in pares if est[i] <= est[j])
    assert ok / len(pares) >= 0.9, est


def test_el_ancho_estimado_escala_con_la_resolucion():
    """Lo que `structural_ink` NO hace: si el ancho dibujado se multiplica por 2,4, la estimación
    tiene que acompañar. Es el contraste directo con el hallazgo de E16.16."""
    e = {}
    for side in (1000, 2400):
        img, gt = B.render(side)
        w = _edge_pair_width(img)
        e[side] = _mediana_en(gt["F_w8"], w)
    esperado = B.expected_width_px(8, 2400) / B.expected_width_px(8, 1000)
    medido = e[2400] / max(1e-9, e[1000])
    assert abs(medido - esperado) / esperado < 0.20, (e, medido, esperado)


def test_la_tinta_estructural_vigente_si_se_satura():
    """El contraste que justifica el spike: la representación del motor comprime el ancho."""
    anchos = {}
    for side in (1000, 2400):
        img, gt = B.render(side)
        ink = (structural_ink(img).ink > 0).astype(np.uint8)
        d = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
        anchos[side] = _mediana_en(gt["F_w8"], 2.0 * d)
    razon_ink = anchos[2400] / max(1e-9, anchos[1000])
    razon_real = B.expected_width_px(8, 2400) / B.expected_width_px(8, 1000)
    assert razon_ink < razon_real * 0.8, (anchos, razon_ink, razon_real)


def test_el_ancho_solo_no_separa_muro_fino_de_mobiliario():
    """§10 — resultado central: un muro de 1× y una mesa de 1× miden lo mismo. La representación no
    falla; simplemente el ancho no contiene esa distinción."""
    img, gt = B.render(1400)
    w = _edge_pair_width(img)
    muro_fino = _mediana_en(gt["A_w1"], w)
    mesa = _mediana_en(gt["L_mesa"], w)
    muro_grueso = _mediana_en(gt["C_w3"], w)
    assert abs(muro_fino - mesa) <= 2.0, (muro_fino, mesa)
    assert muro_grueso > mesa + 1.0, (muro_grueso, mesa)


def test_el_spike_no_esta_conectado_al_motor():
    g = os.path.join(ROOT, "src", "escalimetro")
    for prohibido in ("width_representation.py", "core_width.py", "reps.py"):
        assert not os.path.exists(os.path.join(g, "geometry", prohibido))
    for f in ("reps_spike.txt", "score_spike.txt", "separabilidad_spike.txt"):
        assert os.path.exists(os.path.join(ART, f))
    d = json.load(open(os.path.join(ART, "WIDTH_REPRESENTATION_SPIKE.json"), encoding="utf-8"))
    assert d["engine_unchanged"] is True
    assert d["verdict"].startswith("B - WIDTH RECOVERABLE")
    assert set(d["scorecard"]) == {"distance_transform", "ridge_scale_space", "edge_pair",
                                   "morph_scale_space"}
