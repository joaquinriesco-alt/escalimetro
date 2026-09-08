"""E16.15 — auditoría del criterio de SELECCIÓN del productor. Ciclo de evidencia, sin cambio de motor.

Qué fija este módulo:

1. **El defecto que E16.14 dejó abierto es real y es genérico**: el motor tiene DOS definiciones de
   "encerrado". El detector de celdas cierra los vanos dilatando el muro; el selector del productor
   pregunta el enclaustramiento sobre el muro sin dilatar. Se comprueba sobre un fixture sintético
   —no sobre un caso real— que las dos definiciones dan respuestas distintas sobre el mismo dibujo.

2. **La familia S1–S8** existe, con sus expectativas escritas antes de medir, y el comportamiento del
   motor vigente sobre ella queda registrado como lo que es: fallos conocidos de precisión.

3. **El candidato de E16.15 no está embarcado**: vive como artefacto `.txt` fuera de `src/`, así que
   no es importable y no entra en el hash del motor.
"""
import json
import os

import cv2
import numpy as np
import pytest

from escalimetro.geometry import core_geometry as CG
from escalimetro.geometry import core_producer as CP
from escalimetro.segmentation.structural import stroke_scale_px

ROOT = os.path.dirname(os.path.dirname(__file__))
FX = os.path.join(ROOT, "tests", "fixtures", "core_selection")
ART = os.path.join(ROOT, "cases", "generalization", "E16_15")

#: medido con el motor vigente (E16.14). Son FALLOS CONOCIDOS de precisión del selector, no metas.
S_MEDIDO_E16_14 = {
    "S1_CLOSED_CELL_WITH_DOOR_GAP": (1, 4),
    "S2_SAME_GEOMETRY_WITHOUT_ANCHOR": (0, 2),
    "S3_FURNITURE_ENCLOSURE": (0, 5),
    "S4_WATERMARK_OR_TEXT_CELL": (0, 4),
    "S5_TWO_REAL_COMPONENTS_SEPARATED": (2, 3),
    "S6_SMALL_VALID_ANCHOR": (2, 3),
    "S7_LARGE_UNRELATED_ANCHOR": (1, 4),
    "S8_AMBIGUOUS_STRUCTURAL_CLUSTERS": ("AMBIGUO", 7),
}


def _fx(n):
    img = cv2.imread(os.path.join(FX, n + ".png"))
    meta = json.load(open(os.path.join(FX, n + ".json"), encoding="utf-8"))
    fp = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(fp, [np.array(meta["footprint_ring"], np.int32)], 255)
    return img, fp, meta


def _scope(fp, hint):
    h, w = fp.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in hint]
    m = int(max(h, w) * CG.SEARCH_MARGIN_FRAC)
    z = np.zeros((h, w), np.uint8)
    z[max(0, y0 - m):min(h, y1 + m), max(0, x0 - m):min(w, x1 + m)] = 255
    return (z > 0) & (fp > 0)


# ---------------------------------------------------------------------------------------------------
# 1 · el motor tiene DOS definiciones de "encerrado", y se demuestra sin usar ningún caso real
# ---------------------------------------------------------------------------------------------------
def test_las_dos_definiciones_de_encerrado_no_coinciden():
    """S1 dibuja un recinto con vano de puerta: existe como celda cerrada SÓLO tras la reparación
    canónica que aplica el detector. El selector, que pregunta sobre el muro sin dilatar, no ve
    ninguna pieza responsable de esa celda. Ésa es la inconsistencia que E16.15 audita."""
    img, fp, meta = _fx("S1_CLOSED_CELL_WITH_DOOR_GAP")
    anchors, _ = CG.enclosed_cell_anchors(img, fp)
    scope = _scope(fp, meta["hint_region"])
    assert (anchors > 0).any(), "el detector sí encuentra celdas cerradas en este dibujo"

    walls = CG.wall_map(img) > 0
    k = stroke_scale_px(fp.shape[:2])
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (k | 1, k | 1))
    n, lab = CP.discover(walls, fp)

    na, alab, ast, acen = cv2.connectedComponentsWithStats((anchors > 0).astype(np.uint8), 8)
    celdas = [i for i in range(1, na)
              if scope[int(min(fp.shape[0] - 1, max(0, acen[i][1]))),
                       int(min(fp.shape[1] - 1, max(0, acen[i][0])))]]

    def encierra(region):
        """ENCERRAR es contener la celda entera, no rozarla."""
        return sum(1 for i in celdas
                   if float(((alab == i) & region).sum()) / float((alab == i).sum()) >= 0.99)

    sin_dilatar = con_dilatacion = 0
    for i in range(1, n):
        p = (lab == i)
        if not p.any() or float((p & scope).sum()) / float(p.sum()) < CG.LINK_MIN_OVERLAP:
            continue
        a = CP._fill_holes((p * 255).astype(np.uint8)) & (fp > 0)                    # definición del selector
        b = CP._fill_holes(cv2.dilate((p * 255).astype(np.uint8), ker)) & (fp > 0)   # definición del detector
        sin_dilatar += encierra(a)
        con_dilatacion += encierra(b)
    assert con_dilatacion > sin_dilatar, \
        "si coincidieran, no habría nada que unificar y el diagnóstico de E16.14 sería falso"


def test_la_dilatacion_canonica_es_la_del_detector_de_celdas():
    """La operación que hay que compartir no es 'una dilatación cualquiera': es exactamente la que el
    detector aplica antes de buscar espacio libre. Se comprueba reproduciéndola."""
    img, fp, _ = _fx("S1_CLOSED_CELL_WITH_DOOR_GAP")
    k = stroke_scale_px(fp.shape[:2])
    walls = CG.wall_map(img) > 0
    cerrado = cv2.dilate((walls * 255).astype(np.uint8),
                         cv2.getStructuringElement(cv2.MORPH_RECT, (k | 1, k | 1))) > 0
    libre = ((fp > 0) & ~cerrado).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(libre, 8)
    dominante = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    area_fp = float((fp > 0).sum())
    sel = [i for i in range(1, n)
           if i != dominante and st[i, cv2.CC_STAT_AREA] <= CG.ANCHOR_MAX_FRAC * area_fp]
    esperado = np.isin(lab, sel).astype(np.uint8) * 255 if sel else np.zeros(fp.shape[:2], np.uint8)
    obtenido, _ = CG.enclosed_cell_anchors(img, fp)
    assert np.array_equal(esperado > 0, obtenido > 0), \
        "la reparación canónica reproducida no es idéntica a la del detector"


# ---------------------------------------------------------------------------------------------------
# 2 · la familia S está declarada y su comportamiento actual queda registrado
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", sorted(S_MEDIDO_E16_14))
def test_la_familia_s_esta_declarada_con_su_expectativa(nombre):
    meta = json.load(open(os.path.join(FX, nombre + ".json"), encoding="utf-8"))
    assert "expected_selected" in meta and meta["spec"]
    assert meta["expected_selected"] == S_MEDIDO_E16_14[nombre][0]


@pytest.mark.parametrize("nombre", sorted(S_MEDIDO_E16_14))
def test_el_motor_vigente_sigue_fallando_la_familia_s_como_esta_registrado(nombre):
    """No se maquilla: se fija el número medido. Si cambia, hay que volver a mirarlo, no taparlo."""
    img, fp, meta = _fx(nombre)
    c = CG.core_from_hint(img, fp, tuple(meta["hint_region"]))
    esperado, medido = S_MEDIDO_E16_14[nombre]
    assert c.metrics.get("structural_components_selected", 0) == medido, (nombre, c.metrics)
    if isinstance(esperado, int) and esperado != medido:
        pytest.xfail(f"{nombre}: el selector vigente elige {medido} y el fixture pide {esperado}")


def test_la_relacion_de_pertenencia_no_puede_depender_del_tamano_de_la_celda():
    """S6 existe para probar el DESACOPLE: una celda pequeña debe poder respaldar pertenencia aunque
    el contrato de completitud la considere poco significativa. Hoy el selector vigente usa el umbral
    de significancia como compuerta, que es justamente lo que E16.15 declara incorrecto."""
    img, fp, meta = _fx("S6_SMALL_VALID_ANCHOR")
    x0, y0, x1, y1 = meta["small_anchor_box"]
    anchors, _ = CG.enclosed_cell_anchors(img, fp)
    assert (anchors[y0:y1, x0:x1] > 0).any(), "la celda chica existe como evidencia"
    src = open(os.path.join(ROOT, "src", "escalimetro", "geometry", "core_producer.py"),
               encoding="utf-8").read()
    assert "significant_min_ratio" in src, \
        "si esto deja de estar, el desacople ya se hizo: hay que actualizar este test y el informe"


# ---------------------------------------------------------------------------------------------------
# 3 · el candidato NO está embarcado
# ---------------------------------------------------------------------------------------------------
def test_el_candidato_v3_es_artefacto_y_no_motor():
    p = os.path.join(ART, "core_producer_v3_candidate.txt")
    assert os.path.exists(p), "el candidato medido tiene que quedar registrado"
    assert not os.path.exists(os.path.join(ROOT, "src", "escalimetro", "geometry",
                                           "core_producer_v3_candidate.py"))
    txt = open(p, encoding="utf-8").read()
    assert "responsible_anchors" in txt and "significant_min_ratio" not in txt


def test_las_corridas_del_candidato_estan_registradas():
    d = json.load(open(os.path.join(ART, "CANDIDATE_DEV_RUNS.json"), encoding="utf-8"))
    for caso in ("RES", "GPS"):
        assert d[caso]["discovered"] > d[caso]["selected"] > 0
        assert d[caso]["associations"], "cada pieza seleccionada declara de qué celdas es responsable"
