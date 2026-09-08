"""E16.10 — la semántica propone, la geometría determinista dispone, el contrato veta.

E16.9 midió que un modelo general de visión identifica el núcleo en dos familias gráficas distintas
y que el OCR del motor no lo consigue en ninguna. También midió el límite: devuelve un RECUADRO. Este
módulo fija que ese recuadro entra al motor como PISTA —reduce el espacio de búsqueda— y nunca como
geometría, que el polígono lo produce código determinista sobre evidencia estructural, y que una
pista correcta NO garantiza un núcleo aceptado."""
import ast
import json
import os
import re

import cv2
import numpy as np
import pytest

from escalimetro import semantic_hint as SH
from escalimetro.geometry import core_geometry as CG
from escalimetro.semantic_hint import (InvalidSemanticHint, SemanticHint, SemanticHintUnavailable,
                                       cache_key, load_hint)

ROOT = os.path.dirname(os.path.dirname(__file__))
FX = os.path.join(ROOT, "tests", "fixtures", "core")
SRC = os.path.join(ROOT, "src", "escalimetro")

ACEPTAN = ["A_core_compacto", "B_hint_demasiado_grande", "C_bloques_con_circulacion",
           "D_watermark_y_texto", "E_mobiliario_denso"]
RECHAZAN = ["F_hint_equivocada", "G_fragmentada"]


def _fx(n):
    img = cv2.imread(os.path.join(FX, n + ".png"))
    meta = json.load(open(os.path.join(FX, n + ".json"), encoding="utf-8"))
    fp = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(fp, [np.array(meta["footprint_ring"], np.int32)], 255)
    return img, fp, meta


def _core(n, **kw):
    img, fp, meta = _fx(n)
    return CG.core_from_hint(img, fp, tuple(meta["hint_region"]), **kw)


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
# 1 · contrato de la pista: no se puede falsificar con un dict
# ---------------------------------------------------------------------------------------------------
def test_un_dict_arbitrario_no_es_una_pista():
    with pytest.raises(InvalidSemanticHint):
        SemanticHint.from_dict({"kind": "core"})
    base = dict(kind="core", approximate_region=[10, 10, 100, 100], confidence="high",
                semantic_evidence="hay cabinas y escalera", provenance="VLM",
                source_image_sha256="a" * 64)
    SemanticHint.from_dict(base)                       # válida
    for roto in ({"kind": "nucleo"}, {"provenance": "INVENTADA"}, {"confidence": "altísima"},
                 {"semantic_evidence": "   "}, {"approximate_region": [10, 10, 5, 5]},
                 {"source_image_sha256": "corto"}):
        with pytest.raises(InvalidSemanticHint):
            SemanticHint.from_dict({**base, **roto})


def test_la_pista_se_declara_como_aproximada_en_su_propio_artefacto():
    h = SemanticHint.from_dict(dict(kind="core", approximate_region=[10, 10, 100, 100],
                                    confidence="low", semantic_evidence="x", provenance="VLM",
                                    source_image_sha256="b" * 64))
    d = h.to_dict()
    assert "approximate_region" in d and "PISTA" in d["_warning"]
    assert "geometría aceptada" in d["_warning"]


def test_la_procedencia_desconocida_es_preferible_a_una_falsa():
    h = SemanticHint.from_dict(dict(kind="core", approximate_region=[1, 1, 9, 9], confidence="high",
                                    semantic_evidence="x", provenance="VLM",
                                    source_image_sha256="c" * 64))
    assert h.provider == SH.UNKNOWN and h.model == SH.UNKNOWN


# ---------------------------------------------------------------------------------------------------
# 2 · cache y reproducibilidad
# ---------------------------------------------------------------------------------------------------
def test_la_identidad_del_cache_incluye_imagen_proveedor_modelo_y_version():
    a = cache_key("a" * 64, "prov", "modelo")
    assert a != cache_key("b" * 64, "prov", "modelo")
    assert a != cache_key("a" * 64, "otro", "modelo")
    assert a != cache_key("a" * 64, "prov", "otro")
    assert a != cache_key("a" * 64, "prov", "modelo", "9.9.9")


def test_sin_artefacto_no_hay_nucleo_inventado(tmp_path):
    img = tmp_path / "x.png"
    cv2.imwrite(str(img), np.full((20, 20, 3), 255, np.uint8))
    with pytest.raises(SemanticHintUnavailable):
        load_hint(str(tmp_path), str(img))
    (tmp_path / "semantic").mkdir()
    with pytest.raises(SemanticHintUnavailable):
        load_hint(str(tmp_path), str(img))


def test_una_pista_de_otra_imagen_no_sirve(tmp_path):
    img = tmp_path / "x.png"
    cv2.imwrite(str(img), np.full((20, 20, 3), 255, np.uint8))
    h = SemanticHint.from_dict(dict(kind="core", approximate_region=[1, 1, 9, 9], confidence="high",
                                    semantic_evidence="x", provenance="VLM",
                                    source_image_sha256="d" * 64))
    SH.save_hint(str(tmp_path), h)
    with pytest.raises(SemanticHintUnavailable):
        load_hint(str(tmp_path), str(img))


# ---------------------------------------------------------------------------------------------------
# 3 · la geometría NO es el recuadro
# ---------------------------------------------------------------------------------------------------
def test_el_nucleo_no_es_la_pista():
    """El fixture B da una pista deliberadamente enorme. Si el productor copiara el recuadro,
    `hint_iou` sería ~1 y la fracción de huella sería la del recuadro."""
    c = _core("B_hint_demasiado_grande")
    assert c.accepted
    assert c.metrics["hint_iou"] < 0.5, "el polígono se parece demasiado al recuadro de la pista"
    assert c.metrics["footprint_frac"] < 0.25


def test_la_geometria_puede_salirse_del_recuadro_siguiendo_la_estructura():
    c = _core("E_mobiliario_denso")
    assert c.accepted and c.metrics["outside_hint_frac"] > 0.0, \
        "la estructura manda: el borde no está recortado por el recuadro"


def test_el_codigo_no_convierte_la_pista_en_geometria():
    src = _codigo(os.path.join(SRC, "geometry", "core_geometry.py"))
    assert "hint_region" in src
    assert not re.search(r"(mask|core|filled)\s*=\s*[^\n]*hint_box", src), \
        "el recuadro no puede ser la máscara"
    assert "wall_map" in src and "structural_ink" in src, "la geometría sale de evidencia estructural"


# ---------------------------------------------------------------------------------------------------
# 4 · clases gráficas de la familia de fixtures
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", ACEPTAN)
def test_las_clases_con_nucleo_producen_geometria_aceptada(nombre):
    c = _core(nombre)
    assert c.accepted, (nombre, c.reasons, c.metrics)
    assert c.metrics["components"] == 1 and len(c.ring) >= 4


@pytest.mark.parametrize("nombre", RECHAZAN)
def test_las_clases_sin_nucleo_valido_se_rechazan(nombre):
    c = _core(nombre)
    assert not c.accepted and c.reasons, nombre


def test_una_pista_correcta_no_garantiza_un_nucleo_aceptado():
    """El corazón de la arquitectura: en G la pista señala exactamente la zona correcta y la
    estructura no alcanza. La semántica propone; el contrato veta igual."""
    img, fp, meta = _fx("G_fragmentada")
    correcta = _fx("A_core_compacto")[2]["hint_region"]
    assert meta["hint_region"] == correcta, "el fixture G usa la MISMA pista que el fixture bueno"
    c = CG.core_from_hint(img, fp, tuple(correcta))
    assert not c.accepted


def test_sin_pista_no_hay_geometria_de_nucleo():
    assert os.path.exists(os.path.join(FX, "H_sin_pista.png"))
    assert not os.path.exists(os.path.join(FX, "H_sin_pista.json")), \
        "la clase H es justamente la ausencia de pista"


# ---------------------------------------------------------------------------------------------------
# 5 · el contrato de aceptación se prueba por los DOS lados
# ---------------------------------------------------------------------------------------------------
def test_cada_umbral_del_contrato_veta_cuando_se_endurece():
    c = _core("A_core_compacto")
    assert c.accepted
    m = c.metrics
    for k, v in (("hint_iou_min", m["hint_iou"] + 0.1),
                 ("wall_fraction_min", m["wall_fraction"] + 0.1),
                 ("footprint_frac_min", m["footprint_frac"] + 0.05),
                 ("footprint_frac_max", m["footprint_frac"] - 0.01),
                 ("solidity_min", m["solidity"] + 0.05),
                 ("open_floor_invasion_max", max(0.0, m["open_floor_invasion"] - 0.01))):
        ok, fails = CG.accept_core(m, {k: v})
        assert not ok and fails, f"{k} no está vetando"


def test_el_contrato_esta_declarado_como_dato_y_completo():
    for k in ("hint_iou_min", "require_centroid_in_hint", "wall_fraction_min", "footprint_frac_min",
              "footprint_frac_max", "solidity_min", "components_max", "open_floor_invasion_max"):
        assert k in CG.CORE_ACCEPTANCE


def test_las_anclas_se_registran_pero_no_vetan_la_plausibilidad():
    """E16.11 renombró la señal: `enclosed_cell_anchors_*`. Lo que el detector mide son celdas
    cerradas, no ascensores, y el nombre dejó de afirmar lo segundo. En la capa de PLAUSIBILIDAD
    siguen sin vetar; la completitud las usa aparte (ver tests de E16.11)."""
    c = _core("A_core_compacto")
    assert c.metrics["enclosed_cell_anchors_inside"] >= 1
    assert not any("anchor" in r for r in c.reasons)
    src = _codigo(os.path.join(SRC, "geometry", "core_geometry.py"))
    i, j = src.index("def accept_core"), src.index("def core_from_hint")
    assert "anchor" not in src[i:j], "las anclas no vetan la plausibilidad"


# ---------------------------------------------------------------------------------------------------
# 6 · sin acoplamiento de caso
# ---------------------------------------------------------------------------------------------------
def test_ninguna_constante_de_caso_en_el_codigo_nuevo():
    for f in (os.path.join(SRC, "semantic_hint.py"), os.path.join(SRC, "geometry", "core_geometry.py")):
        txt = open(f, encoding="utf-8").read()
        for t in ("RES", "Real Estate Services", "608.12", "9c542910", "1788", "1070",
                  "645", "1300", "835", "425", "570", "333"):
            assert not re.search(r"(?<![A-Za-z0-9_.])" + re.escape(t) + r"(?![A-Za-z0-9_.])", txt), (f, t)
