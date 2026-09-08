"""E18 — spike de representación de TOPOLOGÍA. El motor no cambia y el ANCHO no participa.

Lo que fijan estos tests es el resultado del ciclo, no una capacidad del producto: que el grafo se
reconstruye de forma estable, que texto y grilla sí se distinguen por estructura, y —lo central— que
un recinto y una mesa de la misma geometría son topológicamente idénticos.
"""
import json
import os
import sys

import cv2
import numpy as np
import pytest
from skimage.morphology import skeletonize

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "tests", "fixtures", "structural_topology"))
import topology_bench_scene as T  # noqa: E402

ART = os.path.join(ROOT, "cases", "generalization", "E18")


def _firma(img):
    """Firma topológica mínima, reproducida aquí para que el test no dependa del artefacto:
    componentes, puntas y uniones del esqueleto. NO se usa ancho en ningún paso."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    b = max(3, int(round(0.02 * max(g.shape))) | 1)
    m = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, b, 5) > 0
    sk = skeletonize(m)
    k = np.ones((3, 3), np.uint8); k[1, 1] = 0
    n = cv2.filter2D(sk.astype(np.uint8), -1, k)
    inv = (~m).astype(np.uint8)
    nl, lab = cv2.connectedComponents(inv, 4)
    bordes = set(lab[0].tolist()) | set(lab[-1].tolist()) | set(lab[:, 0].tolist()) | set(lab[:, -1].tolist())
    ciclos = sum(1 for i in range(1, nl) if i not in bordes and (lab == i).sum() > 9)
    return {"components": int(cv2.connectedComponents(sk.astype(np.uint8), 8)[0] - 1),
            "endpoints": int(((n == 1) & sk).sum()),
            "junction_nodes": int(cv2.connectedComponents(((n >= 3) & sk).astype(np.uint8), 8)[0] - 1),
            "cycles": ciclos}


def _ad_hoc(objs, side):
    T.ESCENAS.append(("_t", "tmp", objs, dict(endpoints=None, L=None, T=None, X=None, cycles=None,
                                              closed=None, components=None, long_path=None)))
    try:
        return T.render("_t", side)[0]
    finally:
        T.ESCENAS.pop()


def test_el_banco_es_determinista_y_de_ancho_unico():
    a = T.render("P6_red_ortogonal", 1000)[0]
    b = T.render("P6_red_ortogonal", 1000)[0]
    assert np.array_equal(a, b)
    assert T.GENERATOR_VERSION.startswith("e18-topology-bench/")
    src = open(os.path.join(ROOT, "tests", "fixtures", "structural_topology",
                            "topology_bench_scene.py"), encoding="utf-8").read()
    assert "W_UNICO" in src, "todo el banco se dibuja con un solo ancho: si no, se estaría midiendo width"


def test_el_grafo_reproduce_el_ground_truth_declarado():
    img, meta = T.render("P6_red_ortogonal", 1400)
    f = _firma(img)
    gt = meta["gt"]
    assert f["components"] == gt["components"]
    assert f["endpoints"] == gt["endpoints"]
    assert f["cycles"] == gt["cycles"]
    assert f["junction_nodes"] == gt["T"] + gt["X"]


@pytest.mark.parametrize("side", [800, 1400, 2400])
def test_el_grafo_es_estable_entre_resoluciones(side):
    img, meta = T.render("P6_red_ortogonal", side)
    f = _firma(img)
    assert f["components"] == 1 and f["cycles"] == 4 and f["endpoints"] == 0


def test_un_recinto_y_una_mesa_de_la_misma_geometria_son_indistinguibles():
    """EL RESULTADO DEL CICLO (§13, §20). Mismo ancho, misma forma: toda señal topológica coincide.
    Si algún día esto deja de ser cierto, hay que revisar por qué —probablemente porque se coló una
    señal que no es topología—."""
    recinto = _ad_hoc([T.rect(0.20, 0.22, 0.42, 0.37)], 1400)
    mesa = _ad_hoc([T.rect(0.20, 0.22, 0.42, 0.37)], 1400)
    assert _firma(recinto) == _firma(mesa)
    chica = _firma(_ad_hoc([T.rect(0.30, 0.30, 0.20, 0.14)], 1400))
    assert chica["cycles"] == 1 and chica["endpoints"] == 0, \
        "una mesa más chica sigue siendo un ciclo cerrado sin puntas: sólo cambia el TAMAÑO"


def test_el_texto_si_se_distingue_por_estructura():
    """Texto: muchas puntas y uniones por unidad de estructura; un muro, casi ninguna."""
    muro = _firma(_ad_hoc([T.rect(0.15, 0.22, 0.55, 0.40)], 1400))
    texto = _firma(_ad_hoc([T.texto("SALA DE REUNIONES", 0.15, 0.40)], 1400))
    assert texto["endpoints"] > muro["endpoints"] + 5
    assert texto["components"] > muro["components"]


def test_la_grilla_si_se_distingue_por_puntas_libres():
    """La hipótesis previa era la periodicidad; lo que separa de verdad son las puntas libres y las
    uniones en X. Queda registrado que la señal esperada no fue la que discriminó."""
    red = _firma(_ad_hoc([T.rect(0.12, 0.15, 0.66, 0.60), T.poly([(0.45, 0.15), (0.45, 0.75)]),
                          T.poly([(0.12, 0.45), (0.78, 0.45)])], 1400))
    grilla = _firma(_ad_hoc([T.grilla([0.18, 0.38, 0.58, 0.78], [0.22, 0.50, 0.78])], 1400))
    assert grilla["endpoints"] >= 10 and red["endpoints"] == 0


def test_el_texto_pegado_contamina_el_grafo_de_forma_visible():
    limpio = _firma(_ad_hoc([T.rect(0.15, 0.22, 0.55, 0.40)], 1400))
    tocando = _firma(_ad_hoc([T.rect(0.15, 0.22, 0.55, 0.40),
                              T.texto("SALA 3", 0.30, 0.225, 0.8)], 1400))
    assert tocando["junction_nodes"] > limpio["junction_nodes"]
    assert tocando["cycles"] >= limpio["cycles"], "el recinto no se pierde por la contaminación"


def test_el_spike_no_usa_ancho_ni_toca_el_motor():
    import ast
    tree = ast.parse(open(os.path.join(ART, "topology_reps_spike.txt"), encoding="utf-8").read())
    for node in ast.walk(tree):                      # se audita el CÓDIGO, no la prosa
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    rep = ast.unparse(tree)
    for prohibido in ("edge_pair", "distanceTransform", "width", "thickness", "grosor"):
        assert prohibido not in rep, prohibido
    g = os.path.join(ROOT, "src", "escalimetro", "geometry")
    assert not os.path.exists(os.path.join(g, "topology.py"))
    d = json.load(open(os.path.join(ART, "TOPOLOGY_REPRESENTATION_SPIKE.json"), encoding="utf-8"))
    assert d["engine_unchanged"] is True
    assert d["edge_pair_bounding"] == "NOT_EVALUATED_IN_E18"
    assert d["verdict"].startswith("E - INFORMATION LIMIT")
    assert set(d["scorecard"]["accuracy"]) == {"skeleton_graph", "line_segment_graph", "contour_graph"}
