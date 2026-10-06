"""E47.7 (cierra E46-H16) — clasificar una foto de CREAR ya no cuesta decenas de segundos, y H01 sigue
cerrado: el plano directo, recodificado JPEG o redimensionado se bloquea antes de crear el proyecto.

Todo sintético, sin red ni gasto. El benchmark completo (12 MP, antes/después) es
`scripts/e47_7_h16_bench.py`; aquí se fijan la equivalencia y una cota holgada de tiempo.
"""
from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from webapp import plan_guard                                       # noqa: E402
from webapp.domain.potential import classify                        # noqa: E402


def _plano(w=1600, h=1200):
    img = np.full((h, w, 3), 250, np.uint8)
    for i in range(1, 8):
        cv2.rectangle(img, (w * i // 10, h // 6), (w * (i + 1) // 10, h * 5 // 6), (40, 40, 40), 6)
    cv2.line(img, (w // 10, h // 2), (w * 9 // 10, h // 2), (30, 30, 30), 5)
    return img


def _foto(w, h, semilla=1):
    rng = np.random.default_rng(semilla)
    base = rng.integers(0, 255, size=(max(2, h // 40), max(2, w // 40), 3), dtype=np.uint8)
    img = cv2.resize(base, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.int16)
    img += rng.integers(-18, 18, size=img.shape, dtype=np.int16)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_colores_empaquetados_igual_a_np_unique():
    """El conteo por entero empaquetado es exactamente el de `np.unique(axis=0)` de antes."""
    for semilla in range(3):
        img = _foto(300, 200, semilla)
        q = (img // 32).reshape(-1, 3)
        esperado = len(np.unique(q, axis=0))
        assert classify.features("", img)["colors"] == esperado


def test_features_mide_reducido_pero_informa_tamano_original():
    img = _foto(3000, 2000)
    f = classify.features("", img)
    assert (f["width"], f["height"], f["short_side"]) == (3000, 2000, 2000)
    assert classify.reducir(img).shape[:2] == (341, 512)


def test_clasifica_con_la_imagen_ya_decodificada_sin_releer(tmp_path, monkeypatch):
    img = _foto(1200, 900)
    llamadas = []
    real = cv2.imread
    monkeypatch.setattr(cv2, "imread", lambda *a, **k: (llamadas.append(a), real(*a, **k))[1])
    assert classify.classify("no-existe.jpg", img=img)["kind"] == classify.PHOTO
    assert llamadas == []


@pytest.mark.parametrize("variante", ["directo", "jpeg", "reducido"])
def test_H01_el_plano_sigue_bloqueado(tmp_path, variante):
    gt = tmp_path / "gt.png"
    cv2.imwrite(str(gt), _plano())
    if variante == "directo":
        p = tmp_path / "f.png"
        cv2.imwrite(str(p), _plano(4000, 3000))
    elif variante == "jpeg":
        p = tmp_path / "f.jpg"
        cv2.imwrite(str(p), _plano(4000, 3000), [cv2.IMWRITE_JPEG_QUALITY, 60])
    else:
        p = tmp_path / "f.png"
        cv2.imwrite(str(p), cv2.resize(_plano(), (800, 600), interpolation=cv2.INTER_AREA))
    assert plan_guard.motivo_de_rechazo(str(p), str(gt))
    with pytest.raises(ValueError):
        plan_guard.revisar_fotos([("f", str(p))], str(gt))


def test_H01_parecido_al_gt_sin_parecer_plano_sigue_bloqueado(tmp_path):
    """Un GT con color (no «tinta sobre papel») sólo lo detiene la comparación perceptual."""
    gt_img = _foto(1600, 1200, 7)
    gt = tmp_path / "gt.png"
    cv2.imwrite(str(gt), gt_img)
    p = tmp_path / "f.jpg"
    cv2.imwrite(str(p), cv2.resize(gt_img, (4000, 3000)), [cv2.IMWRITE_JPEG_QUALITY, 70])
    assert plan_guard.motivo_de_rechazo(str(p), str(gt)) == "es visualmente igual al plano real que cargaste"
    otra = tmp_path / "otra.jpg"
    cv2.imwrite(str(otra), _foto(4000, 3000, 99))
    assert plan_guard.motivo_de_rechazo(str(otra), str(gt)) is None


def test_revisar_fotos_lee_el_gt_una_sola_vez(tmp_path, monkeypatch):
    gt = tmp_path / "gt.png"
    cv2.imwrite(str(gt), _plano())
    fotos = []
    for i in range(3):
        p = tmp_path / ("f%d.jpg" % i)
        cv2.imwrite(str(p), _foto(800, 600, i))
        fotos.append(("f%d" % i, str(p)))
    leidas = []
    real = plan_guard._leer
    monkeypatch.setattr(plan_guard, "_leer", lambda ruta: (leidas.append(ruta), real(ruta))[1])
    plan_guard.revisar_fotos(fotos, str(gt))
    assert leidas.count(str(gt)) == 1


def test_H16_foto_de_12mp_se_clasifica_rapido(tmp_path):
    """Antes ≈ 16 s en el runner de E47.7; ahora < 1 s. Cota holgada (10×) para no ser frágil."""
    p = tmp_path / "grande.jpg"
    cv2.imwrite(str(p), _foto(4000, 3000), [cv2.IMWRITE_JPEG_QUALITY, 90])
    from webapp.domain.reconstruction import projects
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    t = time.perf_counter()
    plano, _ = projects._looks_like_plan(str(p), img)
    assert plano is False
    assert time.perf_counter() - t < 2.0


def test_heic_sigue_aceptandose_en_add_asset():
    """E45.2 (HEIC/HEIF) lo cubre `test_e45_2_mobile_upload.py`; aquí sólo que la ruta de
    clasificación no cambió qué extensiones acepta CREAR."""
    from webapp.domain.reconstruction import projects
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        assert ext in projects._EXT[projects.PHOTO]
