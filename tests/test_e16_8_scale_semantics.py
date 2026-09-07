"""E16.8 — una cifra de superficie no es una escala hasta que se sabe qué región mide.

Hasta E16.7 el motor dividía un área en píxeles por un área en metros sin preguntar nunca si las dos
hablaban de la misma región del espacio. El tipo de área publicada sólo movía un número de
confianza: no tenía poder de veto. El resultado es la falla más cara que puede tener este motor,
porque no se ve: metros plausibles calculados sobre una base equivocada.

Estos tests fijan: que las dos regiones son explícitas, que la inferencia exige compatibilidad, que
`useful` no escala en silencio una huella completa, que `unknown` no se convierte en confirmado, que
un detector que falló no se convierte en "cero área excluida", que la incertidumbre semántica no se
cura con un barrido numérico ni con una confirmación humana genérica, y que el solver y la
presentación no consumen como verdad una escala que el motor rechazó."""
import ast
import json
import os
import re

import pytest

from escalimetro import area_semantics as A
from escalimetro.area_semantics import (AreaObservation, ExclusionsNotAvailable, FULL_FOOTPRINT,
                                        TARGET_UNIT, UNKNOWN_REGION, USEFUL_REGION,
                                        region_compatibility, useful_pixel_region_area)
from escalimetro.geometry import scale_from_known_area, scale_manual, scale_unknown

ROOT = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(ROOT, "src", "escalimetro")
C403 = os.path.join(ROOT, "cases", "001_gps_403")
CRES = os.path.join(ROOT, "cases", "003_res_unknown")

# Superficie y área de un caso INVENTADO para los tests del contrato: ningún número de un caso real
# entra aquí. El contrato se prueba con el contrato, no con la respuesta que queremos.
PX2 = 1_000_000.0
M2 = 500.0


def _codigo(path):
    """Fuente sin comentarios ni docstrings: lo que el motor EJECUTA."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def _j(p):
    return json.load(open(p, encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------
# 1-4 · la inferencia exige compatibilidad de regiones
# ---------------------------------------------------------------------------------------------------
def test_la_escala_registra_las_dos_regiones_de_las_que_habla():
    s = scale_from_known_area(PX2, M2, A.K_UNKNOWN, pixel_region=TARGET_UNIT)
    assert s.pixel_region == TARGET_UNIT and s.area_kind == A.K_UNKNOWN
    assert s.semantic_validity and s.semantic_reason


def test_area_de_huella_completa_puede_escalar_una_huella_completa():
    s = scale_from_known_area(PX2, M2, A.K_FULL_FOOTPRINT, pixel_region=FULL_FOOTPRINT)
    assert s.px_per_m is not None
    assert s.semantic_validity == A.SCALE_MATCHED_REGION
    assert s.rejected_px_per_m is None


def test_area_util_no_escala_en_silencio_una_huella_completa():
    s = scale_from_known_area(PX2, M2, A.K_USEFUL, pixel_region=FULL_FOOTPRINT)
    assert s.px_per_m is None, "una región útil y una huella completa no son la misma superficie"
    assert s.semantic_validity == A.SCALE_INCOMPATIBLE_REGION
    assert s.rejected_px_per_m == pytest.approx((PX2 / M2) ** 0.5)
    assert "rejected_px_per_m" in s.meta.notes, "el valor descartado tiene que quedar rastreable"


def test_region_util_con_area_util_si_es_compatible():
    """El contrato se prueba aunque el pipeline todavía no sepa producir una región útil en píxeles:
    son cosas distintas, y confundirlas sería testear la capacidad en vez del contrato."""
    s = scale_from_known_area(PX2, M2, A.K_USEFUL, pixel_region=USEFUL_REGION)
    assert s.px_per_m is not None and s.semantic_validity == A.SCALE_MATCHED_REGION


def test_la_matriz_cubre_todas_las_combinaciones_y_no_tiene_comodines():
    for r in A.PIXEL_REGIONS:
        for k in A.AREA_KINDS:
            assert (r, k) in A.COMPATIBILITY, f"celda sin decidir: {r} × {k}"
    assert A.COMPATIBILITY[(TARGET_UNIT, A.K_USEFUL)] == A.UNKNOWN, \
        "que una unidad SE PAREZCA a su superficie útil no es una definición"


# ---------------------------------------------------------------------------------------------------
# 5 · unknown no asciende a confirmado
# ---------------------------------------------------------------------------------------------------
def test_area_de_tipo_desconocido_no_se_vuelve_confirmada():
    s = scale_from_known_area(PX2, M2, A.K_UNKNOWN, pixel_region=FULL_FOOTPRINT)
    assert s.px_per_m is not None, "sigue habiendo una estimación histórica utilizable como supuesto"
    assert s.semantic_validity == A.SCALE_UNCONFIRMED_REGION
    assert s.meta.status != "confirmed" and s.meta.confidence < 0.75


def test_solo_una_escala_humana_es_confirmada():
    assert scale_manual(10.0).semantic_validity == A.SCALE_CONFIRMED
    assert scale_unknown().semantic_validity == A.SCALE_NOT_EVALUATED


# ---------------------------------------------------------------------------------------------------
# 6 · equivalencia declarada por la fuente
# ---------------------------------------------------------------------------------------------------
def test_una_equivalencia_declarada_por_la_fuente_autoriza_la_inferencia():
    s = scale_from_known_area(PX2, M2, A.K_USEFUL, pixel_region=FULL_FOOTPRINT,
                              declared_region=FULL_FOOTPRINT)
    assert s.px_per_m is not None and s.semantic_validity == A.SCALE_MATCHED_REGION
    m = region_compatibility(FULL_FOOTPRINT, AreaObservation(M2, A.K_USEFUL,
                                                             declared_region=FULL_FOOTPRINT))
    assert m.by_declaration is True, "tiene que quedar registrado que fue una declaración, no la matriz"


def test_una_equivalencia_declarada_que_no_corresponde_bloquea():
    s = scale_from_known_area(PX2, M2, A.K_USEFUL, pixel_region=FULL_FOOTPRINT,
                              declared_region=USEFUL_REGION)
    assert s.px_per_m is None and s.semantic_validity == A.SCALE_INCOMPATIBLE_REGION


# ---------------------------------------------------------------------------------------------------
# 7 · un detector que falló no prueba que no haya nada que excluir
# ---------------------------------------------------------------------------------------------------
def test_deteccion_fallida_no_es_ausencia_de_area_excluida():
    with pytest.raises(ExclusionsNotAvailable):
        useful_pixel_region_area(PX2, exclusions_px2=None, exclusions_evaluated=False)
    with pytest.raises(ExclusionsNotAvailable):
        # el caso peligroso: el detector devolvió lista vacía y alguien la lee como "0 px de núcleo"
        useful_pixel_region_area(PX2, exclusions_px2=0.0, exclusions_evaluated=False)
    assert useful_pixel_region_area(PX2, exclusions_px2=200_000.0,
                                    exclusions_evaluated=True) == PX2 - 200_000.0


# ---------------------------------------------------------------------------------------------------
# 8-9 · incertidumbre numérica ≠ incertidumbre semántica
# ---------------------------------------------------------------------------------------------------
def test_un_barrido_de_robustez_no_cura_una_incompatibilidad_semantica():
    """Un barrido responde '¿y si la escala fuera 10 % distinta?'. La pregunta abierta aquí es otra:
    '¿de qué superficie hablamos?'. Escalar una base equivocada por 0,9 y 1,1 da tres respuestas
    equivocadas con aspecto de rango."""
    base = scale_from_known_area(PX2, M2, A.K_USEFUL, pixel_region=FULL_FOOTPRINT)
    assert base.px_per_m is None
    for factor in (0.9, 1.0, 1.1):
        s = scale_from_known_area(PX2, M2 * factor, A.K_USEFUL, pixel_region=FULL_FOOTPRINT)
        assert s.px_per_m is None and s.semantic_validity == A.SCALE_INCOMPATIBLE_REGION


def test_la_confirmacion_humana_generica_no_cura_una_region_equivocada():
    """`confirm: ["scale_assumption"]` acepta incertidumbre NUMÉRICA. No puede declarar que dos
    regiones distintas son la misma: para eso está `known_area_region`, que es un hecho de origen."""
    src = _codigo(os.path.join(SRC, "semantics", "shell.py"))
    assert "SCALE_INCOMPATIBLE_REGION" in src
    i = src.index("scale_ok")
    assert "scale_incompatible" in src[max(0, i - 400):i + 200]


# ---------------------------------------------------------------------------------------------------
# 10 · el caso real no se valida a sí mismo, y el motor no lo conoce
# ---------------------------------------------------------------------------------------------------
def test_el_caso_de_planta_completa_con_area_util_no_se_valida_solo():
    """Sin usar la cifra del caso: la combinación (huella completa × útil) es la que no autoriza."""
    caso = _j(os.path.join(CRES, "case.json"))
    assert caso["known_area_kind"] == A.K_USEFUL and caso["drawing_scope"] == "whole_shell"
    assert caso.get("known_area_region") is None, "el caso no declara equivalencia de región"
    m = region_compatibility(FULL_FOOTPRINT, AreaObservation(float(caso["known_area_m2"]),
                                                             caso["known_area_kind"]))
    assert m.compatibility == A.INCOMPATIBLE


def test_ninguna_constante_de_caso_en_el_contrato_de_escala():
    for f in (os.path.join(SRC, "area_semantics.py"), os.path.join(SRC, "geometry", "scale.py")):
        txt = open(f, encoding="utf-8").read()
        for t in ("608.12", "608", "543", "252", "557", "44.542", "1206527", "RES",
                  "003_res_unknown", "GPS"):
            assert not re.search(r"(?<![A-Za-z0-9_.])" + re.escape(t) + r"(?![A-Za-z0-9_.])", txt), (f, t)


# ---------------------------------------------------------------------------------------------------
# 11-12 · el downstream no consume una escala rechazada
# ---------------------------------------------------------------------------------------------------
def test_el_solver_se_niega_a_correr_con_una_escala_no_validada():
    from escalimetro.layout.shell_adapter import ScaleNotValidated, shell_from_floorplate
    from escalimetro.schemas.floorplate import Floorplate
    fp = Floorplate.load(os.path.join(C403, "outputs", "floorplate.json"))
    fp.scale.semantic_validity = A.SCALE_INCOMPATIBLE_REGION
    fp.scale.semantic_reason = "regiones distintas (simulado)"
    fp.scale.rejected_px_per_m = fp.scale.px_per_m
    with pytest.raises(ScaleNotValidated):
        shell_from_floorplate(fp)


def test_la_presentacion_no_etiqueta_como_verdad_una_escala_rechazada():
    from escalimetro.case_context import _confidence_label
    rechazada = {"method": "published_area_rejected", "semantic_validity": A.SCALE_INCOMPATIBLE_REGION,
                 "meta": {"status": "unknown"}}
    assert _confidence_label(rechazada) is None, \
        "una escala que no se calculó no tiene grado de confianza que mostrar"
    inferida = {"method": "published_area_inferred", "meta": {"status": "inferred"}}
    assert _confidence_label(inferida) == "LOW", "la regla histórica no se movió"


def test_el_artefacto_historico_de_la_corrida_anterior_se_conserva():
    """E16.8 §14 — lo que el motor computó entonces sigue existiendo tal cual; lo que cambia es su
    interpretación de hoy, que vive en otro archivo."""
    r = _j(os.path.join(CRES, "outputs", "RUN_004_E16_7.json"))
    assert r["run"] == 4 and r["scale"]["px_per_m"] == 44.54242492168967
    assert r["frozen_before_run"]["engine_baseline"] == "E16.7"
