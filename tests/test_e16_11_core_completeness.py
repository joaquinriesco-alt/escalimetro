"""E16.11 — el contrato deja de confundir "plausible" con "completo".

E16.10 aceptó sobre el plano de desarrollo un candidato que pasaba sus siete criterios y dejaba fuera
el banco principal de ascensores. Ninguno de esos criterios preguntaba si el candidato contiene la
evidencia estructural que la propia semántica señaló, o sólo una parte. Estos tests fijan la
separación entre las dos preguntas, la métrica de completitud y —sobre todo— que la métrica NO exige
cubrir todas las celdas cerradas que caigan dentro del recuadro."""
import ast
import json
import os
import re

import cv2
import numpy as np
import pytest

from escalimetro.geometry import core_completeness as CC
from escalimetro.geometry import core_geometry as CG

ROOT = os.path.dirname(os.path.dirname(__file__))
FX = os.path.join(ROOT, "tests", "fixtures", "core_completeness")
FX10 = os.path.join(ROOT, "tests", "fixtures", "core")
SRC = os.path.join(ROOT, "src", "escalimetro")

ESPERADO = {
    "A_COMPLETE_CLUSTER": CC.COMPLETE,
    "B_PARTIAL_CLUSTER": CC.INCOMPLETE,
    "C_UNRELATED_CLOSED_ROOM": CC.COMPLETE,
    "D_TINY_NOISE_ANCHORS": CC.COMPLETE,
    "E_DISTRIBUTED_SERVICE_BLOCKS": CC.COMPLETE,
    "F_COMPACT_FALSE_COMPLETE": CC.INCOMPLETE,
    "G_NO_RELIABLE_ANCHORS": CC.COMPLETENESS_NOT_EVALUATED,
}


def _fx(n):
    img = cv2.imread(os.path.join(FX, n + ".png"))
    meta = json.load(open(os.path.join(FX, n + ".json"), encoding="utf-8"))
    fp = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(fp, [np.array(meta["footprint_ring"], np.int32)], 255)
    cand = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(cand, [np.array(meta["candidate_ring"], np.int32)], 255)
    anchors, _ = CG.enclosed_cell_anchors(img, fp)
    return img, fp, cand, anchors, meta


def _ev(n, **kw):
    _, _, cand, anchors, meta = _fx(n)
    return CC.evaluate_completeness(cand, anchors, tuple(meta["hint_region"]), kw or None)


def _codigo(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


# ---------------------------------------------------------------------------------------------------
# 1 · la señal dice lo que sabemos
# ---------------------------------------------------------------------------------------------------
def test_las_anclas_no_se_llaman_circulacion_vertical():
    """Lo que el detector mide son celdas cerradas. Una caja de ascensor produce una; una bodega, un
    cuarto técnico y un hueco de dibujo también. El nombre dejó de afirmar lo que no se mide."""
    assert hasattr(CG, "enclosed_cell_anchors")
    assert not hasattr(CG, "enclosed_cells"), "el nombre viejo no puede seguir disponible"
    src = _codigo(os.path.join(SRC, "geometry", "core_geometry.py"))
    assert "vertical_circulation" not in src
    src2 = _codigo(os.path.join(SRC, "geometry", "core_completeness.py"))
    assert "vertical_circulation" not in src2 and "ascensor" not in src2.lower()


# ---------------------------------------------------------------------------------------------------
# 2 · plausibilidad y completitud son dos preguntas
# ---------------------------------------------------------------------------------------------------
def test_plausible_ya_no_significa_aceptado():
    assert CC.overall_status(True, CC.COMPLETE) == CC.CORE_ACCEPTED
    assert CC.overall_status(True, CC.INCOMPLETE) == CC.CORE_REJECTED_INCOMPLETE
    assert CC.overall_status(True, CC.COMPLETENESS_NOT_EVALUATED) == \
        CC.CORE_UNVALIDATED_NO_COMPLETENESS_EVIDENCE
    assert CC.overall_status(False, CC.COMPLETE) == CC.CORE_REJECTED_IMPLAUSIBLE


def test_la_ausencia_de_evidencia_no_produce_un_pase():
    ev = _ev("G_NO_RELIABLE_ANCHORS")
    assert ev.status == CC.COMPLETENESS_NOT_EVALUATED and ev.reasons
    assert CC.overall_status(True, ev.status) != CC.CORE_ACCEPTED


def test_con_una_sola_ancla_significativa_no_hay_cluster_que_evaluar():
    img, fp, cand, anchors, meta = _fx("A_COMPLETE_CLUSTER")
    ev = CC.evaluate_completeness(cand, anchors, tuple(meta["hint_region"]),
                                  {"min_significant_anchors": 99})
    assert ev.status == CC.COMPLETENESS_NOT_EVALUATED


# ---------------------------------------------------------------------------------------------------
# 3 · la familia de fixtures, clase por clase
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", sorted(ESPERADO))
def test_cada_clase_grafica_da_el_estado_declarado(nombre):
    ev = _ev(nombre)
    assert ev.status == ESPERADO[nombre], (nombre, ev.metrics, ev.reasons)


def test_el_par_central_comparte_dibujo_y_pista_y_solo_cambia_el_candidato():
    """A y B son el mismo dibujo y la misma pista. Lo único distinto es hasta dónde llega el
    candidato, y eso basta para que uno sea COMPLETE y el otro INCOMPLETE."""
    a = json.load(open(os.path.join(FX, "A_COMPLETE_CLUSTER.json"), encoding="utf-8"))
    b = json.load(open(os.path.join(FX, "B_PARTIAL_CLUSTER.json"), encoding="utf-8"))
    ia = cv2.imread(os.path.join(FX, "A_COMPLETE_CLUSTER.png"))
    ib = cv2.imread(os.path.join(FX, "B_PARTIAL_CLUSTER.png"))
    assert np.array_equal(ia, ib), "los dos fixtures deben ser el MISMO dibujo"
    assert a["hint_region"] == b["hint_region"] and a["candidate_ring"] != b["candidate_ring"]
    assert _ev("A_COMPLETE_CLUSTER").status == CC.COMPLETE
    assert _ev("B_PARTIAL_CLUSTER").status == CC.INCOMPLETE


# ---------------------------------------------------------------------------------------------------
# 4 · NO se exige cubrir todas las celdas cerradas
# ---------------------------------------------------------------------------------------------------
def test_un_recinto_cerrado_ajeno_no_obliga_a_incluirlo():
    ev = _ev("C_UNRELATED_CLOSED_ROOM")
    assert ev.status == CC.COMPLETE
    assert ev.metrics["mass_coverage"] < 1.0, \
        "el fixture debe dejar masa fuera: si no, no prueba nada"


def test_el_ruido_pequeno_no_domina_la_cobertura():
    ev = _ev("D_TINY_NOISE_ANCHORS")
    assert ev.status == CC.COMPLETE
    assert ev.metrics["anchors_in_scope"] > ev.metrics["significant_anchors"], \
        "el piso de significancia tiene que estar descartando ruido"


def test_la_metrica_es_de_masa_y_no_de_conteo():
    src = _codigo(os.path.join(SRC, "geometry", "core_completeness.py"))
    assert "mass_coverage" in src
    assert not re.search(r"len\(\s*dentro\s*\)\s*/\s*len\(", src), "no puede ser un conteo"
    img, fp, cand, anchors, meta = _fx("A_COMPLETE_CLUSTER")
    ev = CC.evaluate_completeness(cand, anchors, tuple(meta["hint_region"]))
    assert ev.metrics["significant_mass_px"] > ev.metrics["significant_anchors"]


def test_el_contrato_no_tiene_ningun_parametro_de_distancia():
    """Un primer borrador agrupaba anclas con una distancia proporcional a la diagonal de la PISTA:
    una pista más floja producía un cluster más glotón y el recinto vecino entraba. Un criterio cuya
    severidad depende de lo prolijo que fue el intérprete semántico no es un criterio."""
    for k in CC.COMPLETENESS_CONTRACT:
        assert "link" not in k and "dist" not in k, k


# ---------------------------------------------------------------------------------------------------
# 5 · el contrato se prueba por los dos lados
# ---------------------------------------------------------------------------------------------------
def test_cada_umbral_de_completitud_cambia_el_veredicto():
    assert _ev("A_COMPLETE_CLUSTER").status == CC.COMPLETE
    assert _ev("A_COMPLETE_CLUSTER", mass_coverage_min=1.01).status == CC.INCOMPLETE
    assert _ev("A_COMPLETE_CLUSTER", min_significant_anchors=99).status == \
        CC.COMPLETENESS_NOT_EVALUATED
    assert _ev("B_PARTIAL_CLUSTER", mass_coverage_min=0.30).status == CC.COMPLETE, \
        "bajar el umbral tiene que dejar pasar lo parcial: el criterio es el umbral, no el azar"


def test_el_contrato_esta_declarado_como_dato():
    for k in ("significant_min_ratio", "dominant_min_ratio", "mass_coverage_min",
              "min_significant_anchors"):
        assert k in CC.COMPLETENESS_CONTRACT


# ---------------------------------------------------------------------------------------------------
# 6 · el productor de E16.10 no se tocó, y no hay acoplamiento de caso
# ---------------------------------------------------------------------------------------------------
def test_el_productor_geometrico_sigue_produciendo_lo_mismo():
    """La familia de E16.10 se conserva como regresión del productor: mismas máscaras, mismas
    métricas de plausibilidad."""
    for n in ("A_core_compacto", "C_bloques_con_circulacion", "E_mobiliario_denso"):
        img = cv2.imread(os.path.join(FX10, n + ".png"))
        meta = json.load(open(os.path.join(FX10, n + ".json"), encoding="utf-8"))
        fp = np.zeros(img.shape[:2], np.uint8)
        cv2.fillPoly(fp, [np.array(meta["footprint_ring"], np.int32)], 255)
        c = CG.build_core(img, fp, tuple(meta["hint_region"]))
        assert c.metrics["components"] == 1 and c.metrics["core_px"] > 0
        ok, _ = CG.accept_core(c.metrics)
        assert ok, n


def test_ninguna_constante_de_caso_en_el_contrato_de_completitud():
    txt = open(os.path.join(SRC, "geometry", "core_completeness.py"), encoding="utf-8").read()
    for t in ("RES", "Real Estate Services", "608.12", "003_res_unknown", "1788", "1070",
              "645", "1300", "835", "GPS", "403", "543", "7395", "6342", "13", "20"):
        assert not re.search(r"(?<![A-Za-z0-9_.])" + re.escape(t) + r"(?![A-Za-z0-9_.])", txt), t
