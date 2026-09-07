"""E16.5 — la localización deja de asumir que el dibujo rotula su unidad.

E16.4 encontró el primer supuesto no genérico del motor: para saber qué región evaluar, el pipeline
buscaba por OCR el número de la unidad impreso sobre el dibujo. Eso vale en un aviso multiunidad y no
vale en un plano de planta completa, que no tiene ningún número interno que localizar.

Estos tests fijan el contrato nuevo: que existen dos modos, que el modo es un hecho de la fuente y no
una inferencia sobre la ausencia de datos, que una lámina multiunidad sin hint NO se traga el dibujo
entero en silencio, y que el camino histórico de 403/401 no cambió."""
import hashlib
import json
import os

import cv2
import numpy as np
import pytest

from escalimetro import localization as L
from escalimetro.pipeline import PipelineConfig
from escalimetro.vision import REGISTRY as VIS

ROOT = os.path.dirname(os.path.dirname(__file__))
C403 = os.path.join(ROOT, "cases", "001_gps_403")
CRES = os.path.join(ROOT, "cases", "003_res_unknown")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "localization", "whole_shell_example.png")


def _j(p):
    return json.load(open(p, encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------
# 1-3 · el modo whole-drawing existe, es semántica de dominio, y declara su procedencia
# ---------------------------------------------------------------------------------------------------
def test_el_alcance_del_dibujo_es_un_hecho_de_dominio():
    """§12 — semántica de dominio, no un switch técnico. No hay force_full_image ni skip_localization."""
    from escalimetro.case_context import CASE_INPUT_FIELDS
    assert "drawing_scope" in CASE_INPUT_FIELDS
    assert L.DRAWING_SCOPES == (L.MULTI_UNIT, L.WHOLE_SHELL)
    src = open(os.path.join(ROOT, "src", "escalimetro", "localization.py"), encoding="utf-8").read()
    for hack in ("force_full_image", "use_entire_image", "skip_localization"):
        assert hack not in src


def test_whole_shell_no_necesita_localizar_ningun_rotulo():
    """§31.2 — sin OCR, sin número de unidad, sin hint."""
    loc = L.whole_drawing_localization(cv2.imread(FIXTURE))
    assert loc.method == L.WHOLE_DRAWING_TARGET
    assert loc.seeds and loc.roi


def test_la_procedencia_de_whole_shell_es_explicita_y_no_finge_ser_ocr():
    """§17, §18 — aguas abajo debe saberse que esto NO vino del OCR."""
    loc = L.whole_drawing_localization(cv2.imread(FIXTURE))
    assert loc.provenance == L.PROV_SOURCE_FACT == "SOURCE_FACT_WHOLE_DRAWING"
    assert loc.provenance != L.PROV_OCR_HINT
    assert loc.provenance != L.PROV_MANUAL


# ---------------------------------------------------------------------------------------------------
# 4-5 · lo que NO debe activar el modo
# ---------------------------------------------------------------------------------------------------
def test_un_unit_label_desconocido_no_activa_whole_shell_por_si_solo():
    """§11 — la ausencia de un dato no es evidencia sobre la naturaleza del dibujo."""
    src = open(os.path.join(ROOT, "src", "escalimetro", "pipeline.py"), encoding="utf-8").read()
    assert "if not digits(unit_label)" not in src
    assert 'unit_label == "UNKNOWN"' not in src
    # el modo por defecto de un caso que no lo declara es multi_unit, diga lo que diga su rótulo
    assert PipelineConfig("x", "y", "UNKNOWN").drawing_scope == L.MULTI_UNIT
    assert L.validate_scope(None) == L.MULTI_UNIT


def test_una_lamina_multiunidad_sin_hint_no_se_traga_el_dibujo_entero(tmp_path):
    """§16 — el negativo que impide que la ruta nueva 'arregle' todo consumiendo la lámina completa."""
    caso = tmp_path / "caso"
    (caso / "outputs").mkdir(parents=True)
    img = cv2.imread(FIXTURE)
    cv2.imwrite(str(caso / "original.png"), img)
    from escalimetro.pipeline import run
    cfg = PipelineConfig(case_id="X", image_path=str(caso / "original.png"), unit_label="UNKNOWN",
                         known_area_m2=500.0, out_dir=str(caso / "outputs"),
                         drawing_scope=L.MULTI_UNIT)          # multiunidad declarado
    with pytest.raises(RuntimeError) as e:
        run(cfg)
    assert "Sin localización" in str(e.value)


def test_un_alcance_desconocido_se_rechaza_en_vez_de_asumir():
    for malo in ("full_image", "whatever", "WHOLE"):
        with pytest.raises(L.LocalizationError):
            L.validate_scope(malo)


# ---------------------------------------------------------------------------------------------------
# 6 · el modo funciona sin RES
# ---------------------------------------------------------------------------------------------------
def test_un_caso_generico_no_res_recorre_el_mismo_camino():
    """§15 — el único test del modo nuevo no puede ser RES."""
    img = cv2.imread(FIXTURE)
    loc = L.whole_drawing_localization(img)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = loc.roi
    assert (x0, y0) != (0, 0) or (x1, y1) != (w, h), "la ROI no debe ser el rectángulo del archivo"
    assert x0 > 0 and y0 > 0, "los márgenes blancos deben quedar fuera"
    blob = open(os.path.join(ROOT, "src", "escalimetro", "localization.py"), encoding="utf-8").read()
    for t in ("RES", "608", "003_res_unknown", "Real Estate"):
        assert t not in blob, t


def test_la_roi_es_lo_dibujado_y_no_todos_los_pixeles(tmp_path):
    """§9 — whole drawing NO significa mask = rectángulo de la imagen."""
    lienzo = np.full((400, 600, 3), 255, np.uint8)
    cv2.rectangle(lienzo, (200, 150), (400, 300), (0, 0, 0), 3)
    p = tmp_path / "m.png"
    cv2.imwrite(str(p), lienzo)
    x0, y0, x1, y1 = L.drawing_bounds(cv2.imread(str(p)))
    assert 190 <= x0 <= 205 and 140 <= y0 <= 155
    assert 395 <= x1 <= 410 and 295 <= y1 <= 310


# ---------------------------------------------------------------------------------------------------
# 7 · RES llega a segmentación sin ayuda humana
# ---------------------------------------------------------------------------------------------------
def test_res_declara_whole_shell_como_hecho_de_la_fuente():
    d = _j(os.path.join(CRES, "case.json"))
    assert d["drawing_scope"] == "whole_shell"
    assert "_drawing_scope_note" in d


def test_res_supera_la_localizacion_sin_semilla_manual():
    loc = _j(os.path.join(CRES, "outputs", "localization.json"))
    assert loc["method"] == "WHOLE_DRAWING_TARGET"
    assert loc["provenance"] == "SOURCE_FACT_WHOLE_DRAWING"
    assert loc["roi"] is not None
    assert not os.path.exists(os.path.join(CRES, "overrides.json")), \
        "el caso no debe tener overrides: ni seed_points, ni bbox, ni perímetro"


def test_el_run_postfix_se_detuvo_en_la_primera_frontera_nueva():
    r = _j(os.path.join(CRES, "outputs", "RUN_002_POSTFIX.json"))
    assert r["runs_post_fix"] == 1
    assert r["localization"]["status"] == "PASS"
    assert r["next_pipeline_state"] == "B_SEGMENTATION_FAILURE"
    assert all(v is False for v in r["human_intervention"].values())


# ---------------------------------------------------------------------------------------------------
# 8-9 · sin acoplamiento, y el camino histórico intacto
# ---------------------------------------------------------------------------------------------------
def test_el_motor_generico_no_conoce_a_res():
    from escalimetro.generalization import freeze
    for f in freeze.engine_files():
        txt = open(os.path.join(ROOT, f), encoding="utf-8").read()
        for t in ("003_res_unknown", "608.12", "Real Estate Services", "RES_608_12"):
            assert t not in txt, f"{f}: {t}"


def test_la_localizacion_de_403_por_ocr_no_cambio():
    """§13, §31.9 — el camino histórico sigue siendo rótulo → OCR → hint."""
    img = cv2.imread(os.path.join(C403, "original.png"))
    res = VIS["ocr"]().interpret(img, "Oficina 403", 543.0)
    region = res.best("unit_region")
    assert region is not None, "403 debe seguir localizándose por su rótulo impreso"
    assert region.text == "403"
    assert region.point is not None
    fp = _j(os.path.join(C403, "outputs", "floorplate.json"))
    assert fp["target_localization"] == "automatic"
