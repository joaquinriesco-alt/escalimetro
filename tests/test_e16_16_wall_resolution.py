"""E16.16 — ¿es `WALL_EVIDENCE` invariante a la resolución del ráster?

Ciclo de EVIDENCIA: el motor no cambia. Estos tests fijan lo que se midió, para que la conclusión sea
auditable y para que un ciclo futuro sepa contra qué compara.

La escena es vectorial y se rasteriza a varias resoluciones desde la MISMA fuente: lo único que
cambia entre corridas es el número de píxeles.
"""
import os
import sys

import cv2
import numpy as np
import pytest

from escalimetro.geometry import core_geometry as CG
from escalimetro.segmentation.structural import stroke_scale_px

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "tests", "fixtures", "wall_resolution"))
import multires_scene as scene  # noqa: E402

RES = (600, 800, 1000, 1400, 1800, 2400)


def _wall_metrics(side):
    img, gt = scene.render(side)
    w = CG.wall_map(img) > 0
    gw = gt["wall"] > 0
    tol = max(1, stroke_scale_px((gt["height"], gt["side"])) // 3)
    gw_tol = cv2.dilate((gw * 255).astype(np.uint8),
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tol | 1, tol | 1))) > 0
    rec = float((w & gw).sum()) / max(1.0, float(gw.sum()))
    fp_mob = float((w & (gt["furniture"] > 0) & ~gw_tol).sum()) / \
        max(1.0, float(((gt["furniture"] > 0) & ~gw_tol).sum()))
    return rec, fp_mob


def test_el_umbral_de_grosor_no_es_una_fraccion_estable_de_la_escala_de_trazo():
    """`max(3, k//4)` cambia de régimen con la resolución: el piso absoluto domina abajo y la división
    entera salta arriba. La proporción umbral/escala oscila más del doble."""
    ratios = []
    for side in RES:
        k = stroke_scale_px((int(side * 0.66), side))
        ratios.append(((max(3, k // 4) | 1) / k))
    assert max(ratios) / min(ratios) > 2.0, ratios
    assert abs(min(ratios) - 0.20) < 0.01 and abs(max(ratios) - 0.43) < 0.01


@pytest.mark.parametrize("side", RES)
def test_la_escala_de_trazo_si_escala_con_el_raster(side):
    """`stroke_scale_px` no es la raíz: se mantiene en ~1 % del lado en todo el rango."""
    k = stroke_scale_px((int(side * 0.66), side))
    assert 0.010 <= k / side <= 0.012


def test_la_misma_escena_cambia_de_clasificacion_solo_por_la_resolucion():
    """El resultado central del ciclo. Misma geometría, mismos anchos relativos, distinto ráster:
    el recall de muro va de 0,28 a 1,00 y los falsos positivos sobre mobiliario de 0,00 a 1,00."""
    rec = {s: _wall_metrics(s) for s in (800, 1400)}
    r800, fp800 = rec[800]
    r1400, fp1400 = rec[1400]
    assert r800 < 0.5, r800            # a 800 px la mayor parte del muro no se reconoce
    assert r1400 > 0.9, r1400          # a 1400 px sí
    assert fp1400 > 0.9, fp1400        # y ahí el mobiliario entra casi entero
    assert (r1400 - r800) > 0.5, "si esto se estabiliza, la evidencia dejó de depender del ráster"


def test_la_respuesta_de_ancho_de_la_tinta_se_satura():
    """Causa medida, distinta del piso de 3 px: el ancho de la tinta no sigue al ancho dibujado, así
    que 'grosor' deja de ser una magnitud comparable entre resoluciones."""
    anchos = {}
    for side in (600, 2400):
        img, gt = scene.render(side)
        from escalimetro.segmentation.structural import structural_ink
        ink = (structural_ink(img).ink > 0).astype(np.uint8)
        d = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
        v = d[(gt["wall"] > 0) & (ink > 0)]
        anchos[side] = float(np.median(v)) * 2
    dibujado = (scene.W_PERIM * 2400) / (scene.W_PERIM * 600)      # 4x
    medido = anchos[2400] / max(0.1, anchos[600])
    assert medido < dibujado / 1.5, (anchos, medido, dibujado)


def test_el_artefacto_del_banco_esta_registrado():
    import json
    p = os.path.join(ROOT, "cases", "generalization", "E16_16", "MULTIRES_WALL_EVIDENCE.json")
    d = json.load(open(p, encoding="utf-8"))
    assert d["engine_unchanged"] is True
    assert len(d["baseline_e16_15"]) == len(RES)
    assert d["verdict"].startswith("D - REPRESENTATION LIMIT")


def test_los_candidatos_no_estan_embarcados():
    g = os.path.join(ROOT, "src", "escalimetro", "geometry")
    assert not os.path.exists(os.path.join(g, "wall_candidate_canonical_scale.py"))
    art = os.path.join(ROOT, "cases", "generalization", "E16_16")
    for f in ("wall_candidate_canonical_scale.txt", "wall_candidate_distance_transform.txt"):
        assert os.path.exists(os.path.join(art, f))
