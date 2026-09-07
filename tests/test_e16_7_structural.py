"""E16.7 — la evidencia estructural deja de ser "gris < 110".

E16.6 generalizó la segmentación whole-shell: sin semilla, por conectividad con el exterior. RES
volvió a fallar, y la causa medida no estaba en la conectividad sino una capa antes: el mapa de
barreras se construía con un umbral global absoluto, y un plano trazado en gris claro no tiene
ningún píxel bajo ese umbral. El detector no veía el muro que un humano ve.

Estos tests fijan: que la evidencia estructural es relativa al fondo local y no a un número absoluto,
que un perímetro claro con mobiliario oscuro produce barreras válidas, que las clases gráficas
antiguas siguen valiendo, que las láminas sin edificio siguen siendo rechazadas —incluidas las
nuevas, más difíciles—, que la aceptación de la barrera y la de la máscara son capas separadas, que
los parámetros efectivamente usados quedan persistidos, y que el camino multiunidad no se movió."""
import ast
import json
import os
import re

import cv2
import numpy as np
import pytest

from escalimetro import localization as L
from escalimetro.segmentation import REGISTRY, strategy_for
from escalimetro.segmentation.base import SegmentationRequest
from escalimetro.segmentation.strategy import SEEDED_COLOR, SEEDED_FLOOD, WHOLE_SHELL_PROVIDER
from escalimetro.segmentation import structural as S

ROOT = os.path.dirname(os.path.dirname(__file__))
FX = os.path.join(ROOT, "tests", "fixtures", "segmentation")
SRC = os.path.join(ROOT, "src", "escalimetro", "segmentation")

# clases gráficas que DEBEN producir una huella
POSITIVOS_E16_6 = ["A_whole_shell_simple", "B_whole_shell_core", "C_whole_shell_clutter"]
POSITIVOS_E16_7 = ["D0_muro_oscuro_mobiliario_claro", "D1_muro_gris_claro_mobiliario_oscuro",
                   "D3_doble_linea", "D4_vanos_de_puerta"]
# clases gráficas que DEBEN ser rechazadas
NEGATIVOS_E16_6 = ["N1_casi_vacia", "N2_sin_planta", "N3_perimetro_abierto"]
NEGATIVOS_E16_7 = ["N4_solo_mobiliario", "N5_solo_grilla", "N6_lamina_de_titulo",
                   "N7_dos_rectangulos", "N8_croquis_abierto"]
# clases gráficas NO RESUELTAS. Se declaran como tales y se MIDEN: D2 se rechaza (rechazo honesto),
# D5 se acepta contaminada y el contrato de aceptación no lo detecta. Ver §6 de
# docs/E16_7_STRUCTURAL_BARRIER_CONTRACT.md.
NO_RESUELTA = ["D2_muro_gris_claro_con_ejes"]


def _img(n):
    return cv2.imread(os.path.join(FX, n + ".png"))


def _seg(img, **params):
    return REGISTRY["whole_shell"]().segment(
        SegmentationRequest(img, bbox=L.drawing_bounds(img), params=params or None))


def _codigo(path):
    """Fuente sin comentarios ni docstrings: lo que el motor EJECUTA."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


# ---------------------------------------------------------------------------------------------------
# 1 · la evidencia estructural es relativa, no un umbral global absoluto
# ---------------------------------------------------------------------------------------------------
def test_la_evidencia_estructural_no_es_un_umbral_global_de_gris():
    codigo = _codigo(os.path.join(SRC, "structural.py"))
    assert "MORPH_CLOSE" in codigo, "el fondo local se estima cerrando la imagen"
    assert not re.search(r"gray\s*<\s*\d", codigo), "quedó una comparación absoluta contra el gris"
    prov = _codigo(os.path.join(SRC, "providers.py"))
    cuerpo = prov[prov.index("class WholeShellProvider"):]
    assert "structural_ink" in cuerpo
    assert "wall_thresh" not in cuerpo, "whole_shell ya no puede depender de un umbral de muro"


def test_el_mismo_dibujo_en_dos_tintas_da_la_misma_evidencia():
    """Un plano trazado claro y el mismo trazado oscuro son el mismo dibujo. Un umbral global los
    separa; la evidencia estructural no."""
    base = _img("D0_muro_oscuro_mobiliario_claro")
    claro = _img("D1_muro_gris_claro_mobiliario_oscuro")
    a, b = _seg(base), _seg(claro)
    assert a.confidence > 0 and b.confidence > 0
    inter = int(((a.mask > 0) & (b.mask > 0)).sum())
    union = int(((a.mask > 0) | (b.mask > 0)).sum())
    assert union and inter / union > 0.98, "la huella no puede depender de con qué tinta se dibujó"


def test_un_umbral_global_no_habria_visto_el_perimetro_claro():
    """Testigo de la causa raíz: sobre D1 la regla de E16.6 no marca un solo píxel del perímetro."""
    g = cv2.cvtColor(_img("D1_muro_gris_claro_mobiliario_oscuro"), cv2.COLOR_BGR2GRAY)
    perimetro = np.zeros_like(g, bool)
    perimetro[104:117, 130:750] = True          # tramo de muro superior, sin mobiliario encima
    assert (g[perimetro] < 110).sum() == 0, "el fixture ya no representa la clase que falla"
    ink = S.structural_ink(_img("D1_muro_gris_claro_mobiliario_oscuro")).ink
    assert (ink[perimetro] > 0).sum() > 0, "la evidencia estructural sí debe verlo"


def test_la_escala_de_trazo_se_deriva_del_tamano_de_la_imagen():
    assert S.stroke_scale_px((700, 1000)) == 11
    assert S.stroke_scale_px((1070, 1788)) == 19
    for k in (S.stroke_scale_px((h, w)) for h, w in ((100, 100), (5000, 9000), (620, 900))):
        assert k % 2 == 1 and S.STROKE_SCALE_MIN <= k <= S.STROKE_SCALE_MAX


# ---------------------------------------------------------------------------------------------------
# 2 · clases gráficas: positivas y negativas
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", POSITIVOS_E16_6 + POSITIVOS_E16_7)
def test_las_clases_con_edificio_producen_huella(nombre):
    r = _seg(_img(nombre))
    assert r.confidence > 0 and (r.mask > 0).sum() > 0, r.notes
    assert r.diagnostics["barrier"]["accepted"] and r.diagnostics["mask"]["accepted"]


@pytest.mark.parametrize("nombre", NEGATIVOS_E16_6 + NEGATIVOS_E16_7)
def test_las_laminas_sin_edificio_son_rechazadas(nombre):
    r = _seg(_img(nombre))
    assert r.confidence == 0.0 and (r.mask > 0).sum() == 0, r.notes


@pytest.mark.parametrize("nombre", NO_RESUELTA)
def test_la_clase_no_resuelta_rechaza_en_vez_de_inventar(nombre):
    """Ejes de replanteo que cruzan la planta: la huella candidata se contamina con las celdas de la
    retícula. E16.7 NO resuelve esta clase; lo que sí exige es que no entregue esa máscara como
    buena. Rechazo honesto > geometría equivocada."""
    r = _seg(_img(nombre))
    assert r.confidence == 0.0 and (r.mask > 0).sum() == 0
    assert r.diagnostics["mask"]["open_ratio"] < 0.10


def test_la_anotacion_pegada_al_muro_contamina_la_huella_y_el_contrato_no_lo_ve():
    """CLASE ABIERTA, MEDIDA. Un rótulo trazado sobre el muro queda conectado al edificio, la huella
    lo absorbe, y ninguna de las métricas declaradas lo detecta: se acepta una máscara equivocada.
    Este test NO afirma que esté bien; fija la magnitud del defecto para que no crezca en silencio y
    para que el próximo ciclo tenga contra qué compararse."""
    limpia = _seg(_img("D1_muro_gris_claro_mobiliario_oscuro"))
    sucia = _seg(_img("D5_rotulo_tocando_el_muro"))
    assert sucia.confidence > 0, "hoy se acepta: eso es exactamente lo que está mal"
    a, b = limpia.mask > 0, sucia.mask > 0
    exceso = float((b & ~a).sum()) / float(b.sum())
    assert 0.005 < exceso < 0.03, f"contaminación medida fuera de lo registrado: {exceso:.4f}"


def test_el_mobiliario_oscuro_no_se_confunde_con_el_edificio():
    """N4: sólo muebles. Hay tinta de sobra y muy oscura; no hay estructura a escala de la lámina."""
    r = _seg(_img("N4_solo_mobiliario"))
    assert r.confidence == 0.0
    assert r.diagnostics["barrier"]["ink_frac_roi"] > 0.02, "el negativo debe tener tinta abundante"


def test_dos_candidatos_grandes_no_se_resuelven_a_dedo():
    r = _seg(_img("N7_dos_rectangulos"))
    assert r.confidence == 0.0
    assert r.diagnostics["mask"]["second_ratio"] >= 0.50, "la lámina es ambigua por construcción"


# ---------------------------------------------------------------------------------------------------
# 3 · las dos aceptaciones son capas distintas
# ---------------------------------------------------------------------------------------------------
def test_barrera_y_mascara_se_aceptan_por_separado():
    vacia = _seg(_img("N1_casi_vacia"))
    assert vacia.diagnostics["barrier"]["accepted"] is False
    assert "mask" not in vacia.diagnostics, "sin barrera válida no se evalúa máscara"
    grilla = _seg(_img("N5_solo_grilla"))
    assert grilla.diagnostics["barrier"]["accepted"] is True, "hay estructura: la barrera es válida"
    assert grilla.diagnostics["mask"]["accepted"] is False, "pero lo que encierra no es un edificio"


def test_el_contrato_de_barrera_esta_declarado_como_dato():
    for k in ("ink_frac_min", "ink_frac_max", "span_ratio_min", "outside_frac_min", "outside_frac_max"):
        assert k in S.BARRIER_ACCEPTANCE
    ok, why = S.barrier_accept(0.0, {"span_ratio": 0.0, "outside_reachable_frac_roi": 1.0,
                                     "outside_reachable_frac_image": 1.0})
    assert not ok and "span_ratio" in why


# ---------------------------------------------------------------------------------------------------
# 4 · procedencia: nada de parámetros ocultos
# ---------------------------------------------------------------------------------------------------
def test_los_parametros_usados_quedan_persistidos():
    d = _seg(_img("C_whole_shell_clutter")).diagnostics
    si = d["structural_ink"]
    assert si["method"] == "local_contrast_blackhat"
    assert si["min_contrast"] == S.MIN_CONTRAST
    assert si["stroke_scale_px"] == S.stroke_scale_px(_img("C_whole_shell_clutter").shape[:2])
    for k in ("barrier_frac_roi", "span_ratio", "outside_reachable_frac_roi",
              "outside_reachable_frac_image"):
        assert k in d["barrier"]
    for k in ("roi_frac", "fill", "second_ratio", "open_ratio", "mask_px"):
        assert k in d["mask"]
    json.dumps(d)          # tiene que ser serializable para el artefacto del run


# ---------------------------------------------------------------------------------------------------
# 5 · sin acoplamiento de caso, y el camino multiunidad intacto
# ---------------------------------------------------------------------------------------------------
def test_ninguna_constante_del_caso_real_en_el_codigo():
    for f in ("structural.py", "providers.py", "strategy.py"):
        src = _codigo(os.path.join(SRC, f))
        for t in ("RES", "608", "910", "542", "1788", "1070", "156", "166", "176", "189", "197"):
            assert not re.search(r"(?<![A-Za-z0-9_.])" + t + r"(?![A-Za-z0-9_.])", src), (f, t)
        for t in ("003_res_unknown", "Real Estate", "watermark"):
            assert t not in src, (f, t)


def test_el_camino_multiunidad_no_se_movio():
    assert strategy_for("multi_unit") == SEEDED_FLOOD
    assert strategy_for("multi_unit", has_color_hint=True) == SEEDED_COLOR
    assert strategy_for("whole_shell") == WHOLE_SHELL_PROVIDER
    flood = _codigo(os.path.join(SRC, "providers.py"))
    cuerpo = flood[flood.index("class OpenCVFloodProvider"):flood.index("class OpenCVColorRangeProvider")]
    assert "wall_thresh" in cuerpo and "structural_ink" not in cuerpo, \
        "opencv_flood es el camino histórico de 403/401: E16.7 no lo toca"
