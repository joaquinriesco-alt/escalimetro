"""E16.13 — un núcleo es UNA entidad semántica que puede ocupar VARIAS regiones.

E16.12 midió el costo de la afirmación contraria. `components_max = 1` decía "un núcleo correcto es
una sola pieza conectada", y con esa regla puesta el motor sólo podía hacer dos cosas frente a un
conjunto de servicio distribuido: rechazarlo, o fabricar una franja de unión por espacio abierto. Los
tests de este módulo fijan las tres cosas que reemplazan a esa regla:

  * la REPRESENTACIÓN admite 1..N piezas y normaliza las formas sucias con una política declarada;
  * el CONTRATO pregunta propiedades —construcción, forma, invasión y relación con el alcance
    semántico POR PIEZA; tamaño y coherencia con la pista SOBRE LA UNIÓN— y no cuenta piezas;
  * la fabricación se MIDE y todavía no veta, porque su umbral no está calibrado.
"""
import json
import os
import re

import cv2
import numpy as np
import pytest

from escalimetro.geometry import core_geometry as CG
from escalimetro.geometry import core_components as CCOMP
from escalimetro.geometry.core_components import InvalidCoreGeometry

ROOT = os.path.dirname(os.path.dirname(__file__))
FX = os.path.join(ROOT, "tests", "fixtures", "core_components")
SRC = os.path.join(ROOT, "src", "escalimetro")

ACEPTAN = {"A_SINGLE_COMPONENT_LEGACY": 1, "B_TWO_LEGITIMATE_COMPONENTS": 2,
           "C_THREE_LEGITIMATE_COMPONENTS": 3}
RECHAZAN = ["E_SPURIOUS_COMPONENT", "J_OPEN_FLOOR_COMPONENT"]


def _fx(n):
    img = cv2.imread(os.path.join(FX, n + ".png"))
    meta = json.load(open(os.path.join(FX, n + ".json"), encoding="utf-8"))
    fp = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(fp, [np.array(meta["footprint_ring"], np.int32)], 255)
    return img, fp, meta


def _eval(n, rings_key="candidate_rings", **kw):
    img, fp, meta = _fx(n)
    if rings_key in meta:
        return CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta[rings_key], **kw)
    return CG.core_from_hint(img, fp, tuple(meta["hint_region"]), **kw)


# ---------------------------------------------------------------------------------------------------
# 1 · representación canónica: 1..N piezas, política declarada para las formas sucias
# ---------------------------------------------------------------------------------------------------
def test_la_version_del_contrato_geometrico_cambia_de_mayor():
    """1.x era single-ring. Un lector antiguo tiene que poder detectar que la geometría que recibe ya
    no cumple la propiedad que él daba por cierta."""
    assert CCOMP.CONTRACT_VERSION.startswith("core-geometry/2.")


def test_una_pieza_es_el_caso_degenerado_y_no_un_camino_aparte():
    c = _eval("A_SINGLE_COMPONENT_LEGACY")
    assert c.metrics["components"] == 1
    assert len(c.components) == 1 and c.ring == c.components[0]


@pytest.mark.parametrize("nombre,piezas", sorted(ACEPTAN.items()))
def test_las_piezas_legitimas_se_representan_y_se_aceptan(nombre, piezas):
    c = _eval(nombre)
    assert c.metrics["components"] == piezas, (nombre, c.metrics)
    assert len(c.components) == piezas
    assert c.accepted, (nombre, c.reasons)
    assert c.status == "CORE_ACCEPTED", (nombre, c.notes)


def test_la_esquirla_de_ruido_se_descarta_en_la_normalizacion_y_se_cuenta():
    """No se ignora en silencio ni hunde el candidato entero: se descarta y queda contada."""
    img, fp, meta = _fx("F_TINY_NOISE_COMPONENT")
    c = CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["candidate_rings"])
    assert len(meta["candidate_rings"]) == 3
    assert c.metrics["components"] == meta["expected_components"] == 2
    assert c.metrics["normalized_away"] == meta["expected_normalized_away"] == 1


def test_las_piezas_que_se_solapan_se_fusionan_y_se_cuentan():
    """Geometría doble no puede existir: dos anillos solapados describen una sola región."""
    img, fp, meta = _fx("G_OVERLAPPING_COMPONENTS")
    c = CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["candidate_rings"])
    assert c.metrics["components"] == 1 and c.metrics["merged_overlaps"] == 1
    union = float((c.mask > 0).sum())
    suma = 0.0
    for r in meta["candidate_rings"]:
        m = np.zeros(fp.shape[:2], np.uint8)
        cv2.fillPoly(m, [np.array(r, np.int32)], 255)
        suma += float((m > 0).sum())
    assert union < suma, "la fusión tiene que quitar el área contada dos veces"


def test_una_pieza_fuera_de_la_huella_no_se_normaliza_sino_que_es_invalida():
    img, fp, meta = _fx("H_COMPONENT_OUTSIDE_FOOTPRINT")
    with pytest.raises(InvalidCoreGeometry):
        CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["candidate_rings"])


def test_el_orden_de_las_piezas_es_canonico_y_estable():
    img, fp, meta = _fx("C_THREE_LEGITIMATE_COMPONENTS")
    a = CG.core_from_hint(img, fp, tuple(meta["hint_region"]))
    b = CG.core_from_hint(img, fp, tuple(meta["hint_region"]))
    assert a.components == b.components, "dos corridas iguales serializan igual"
    areas = [cv2.contourArea(np.array(r, np.float32)) for r in a.components]
    assert areas == sorted(areas, reverse=True), "orden canónico: área descendente"


def test_ring_sigue_existiendo_como_vista_de_compatibilidad():
    """Un lector de la era single-ring no se rompe: recibe la pieza MAYOR, y eso es explícitamente
    una vista parcial, no el núcleo."""
    c = _eval("C_THREE_LEGITIMATE_COMPONENTS")
    assert c.ring == c.components[0] and len(c.ring) >= 4
    assert len(c.components) > 1, "el fixture existe justamente para que la vista sea parcial"


# ---------------------------------------------------------------------------------------------------
# 2 · el contrato pregunta propiedades, no cantidad de piezas
# ---------------------------------------------------------------------------------------------------
def test_el_contrato_no_tiene_ninguna_clave_que_cuente_piezas():
    for k in CG.CORE_ACCEPTANCE:
        assert "components_max" != k and "count" not in k, k


@pytest.mark.parametrize("nombre", RECHAZAN)
def test_una_pieza_que_no_es_nucleo_veta_el_candidato(nombre):
    """El motor no recorta en silencio lo que no puede justificar: si una pieza del candidato no está
    construida o es piso ocupable, el candidato NO es un núcleo validado. Descartarla calladamente
    sería la misma clase de error que E16.11 detectó al dejar fuera un bloque sin decirlo."""
    c = _eval(nombre)
    assert not c.accepted and c.reasons
    assert any("componente" in r for r in c.reasons), c.reasons


def test_la_invasion_por_pieza_ve_lo_que_el_promedio_de_la_union_esconde():
    """Es la prueba directa de por qué `open_floor_invasion` es PER-COMPONENT: sobre la unión, una
    pieza ocupable queda diluida por las piezas buenas y el contrato la deja pasar."""
    c = _eval("J_OPEN_FLOOR_COMPONENT")
    assert c.metrics["open_floor_invasion"] < CG.CORE_ACCEPTANCE["open_floor_invasion_max"], \
        "sobre la unión, este candidato pasaría"
    peor = max(m["open_floor_invasion"] for m in c.component_metrics)
    assert peor > CG.CORE_ACCEPTANCE["open_floor_invasion_max"]
    ok_union, _ = CG.accept_core(c.metrics)                       # lectura histórica: sólo unión
    ok_piezas, fails = CG.accept_core(c.metrics, None, c.component_metrics)
    assert ok_union and not ok_piezas and fails


def test_la_solidez_de_la_union_mide_el_reparto_de_la_planta_y_no_la_forma_del_objeto():
    """Por eso `solidity` es PER-COMPONENT. La envolvente convexa de la unión atraviesa la
    circulación que separa los bloques, así que su solidez baja cuanto más repartido está el núcleo,
    aunque cada pieza sea un rectángulo."""
    c = _eval("C_THREE_LEGITIMATE_COMPONENTS")
    assert min(m["solidity"] for m in c.component_metrics) > 0.9
    assert c.metrics["solidity"] < 0.75
    duro = {"solidity_min": 0.8}
    assert not CG.accept_core(c.metrics, duro)[0], "leída sobre la unión, la exigencia rechazaría"
    assert CG.accept_core(c.metrics, duro, c.component_metrics)[0], "leída por pieza, acepta"


def test_cada_invariante_por_pieza_veta_cuando_se_endurece():
    c = _eval("B_TWO_LEGITIMATE_COMPONENTS")
    assert c.accepted
    peor = c.component_metrics
    for k, v in (("wall_fraction_min", max(m["wall_fraction"] for m in peor) + 0.1),
                 ("solidity_min", max(m["solidity"] for m in peor) + 0.05),
                 ("open_floor_invasion_max", 0.0),
                 ("component_scope_overlap_min", 1.01)):
        ok, fails = CG.accept_core(c.metrics, {k: v}, peor)
        assert not ok and fails, f"{k} no está vetando por pieza"


def test_cada_invariante_de_union_veta_cuando_se_endurece():
    c = _eval("B_TWO_LEGITIMATE_COMPONENTS")
    m = c.metrics
    for k, v in (("hint_iou_min", m["hint_iou"] + 0.1),
                 ("footprint_frac_min", m["footprint_frac"] + 0.05),
                 ("footprint_frac_max", m["footprint_frac"] - 0.01)):
        ok, fails = CG.accept_core(m, {k: v}, c.component_metrics)
        assert not ok and fails, f"{k} no está vetando sobre la unión"


# ---------------------------------------------------------------------------------------------------
# 3 · fabricación: se mide, no veta, y no hay umbral inventado
# ---------------------------------------------------------------------------------------------------
def test_el_puente_por_piso_abierto_se_mide_y_se_distingue_del_candidato_honesto():
    """MISMO dibujo, MISMA pista, dos geometrías: la que cruza el piso abierto para tener una sola
    pieza, y la que respeta las dos piezas que el dibujo tiene."""
    img, fp, meta = _fx("D_FABRICATED_BRIDGE")
    puente = CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["candidate_rings"])
    honesto = CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["honest_rings"])
    assert puente.metrics["components"] == 1 and honesto.metrics["components"] == 2
    assert puente.metrics["fabricated_fraction"] > 10 * honesto.metrics["fabricated_fraction"]


def test_la_fabricacion_no_veta_y_lo_dice():
    """E16.13 §11: el banco disponible no basta para separar un puente de un recinto interior grande
    sin inventar un número. El estado honesto es decir que no está calibrado, no poner 5 %."""
    c = _eval("D_FABRICATED_BRIDGE")
    assert c.metrics["fabricated_fraction"] > 0.1
    assert c.metrics["bridge_validation"] == "NOT_CALIBRATED"
    assert c.accepted, "mientras no esté calibrado, la métrica informa y no decide"
    assert not any("fabric" in r for r in c.reasons)
    for k in CG.CORE_ACCEPTANCE:
        assert "fabricated" not in k and "bridge" not in k, k


def test_la_fabricacion_se_reporta_tambien_por_pieza():
    c = _eval("E_SPURIOUS_COMPONENT")
    assert max(m["fabricated_fraction"] for m in c.component_metrics) > 0.9, \
        "una pieza sobre papel en blanco es fabricación pura"
    assert min(m["fabricated_fraction"] for m in c.component_metrics) < 0.05


# ---------------------------------------------------------------------------------------------------
# 4 · la completitud se evalúa sobre la UNIÓN
# ---------------------------------------------------------------------------------------------------
def test_la_completitud_mira_la_union_de_piezas():
    """Con las anclas repartidas entre dos bloques, el candidato de dos piezas está completo y el de
    una sola no. Si la completitud mirara sólo la pieza mayor, los dos darían lo mismo."""
    completo = _eval("I_DISTRIBUTED_ANCHOR_COVERAGE")
    parcial = _eval("I_DISTRIBUTED_ANCHOR_COVERAGE", rings_key="partial_rings")
    assert completo.completeness_status == "COMPLETE" and completo.status == "CORE_ACCEPTED"
    assert parcial.completeness_status == "INCOMPLETE"
    assert parcial.status == "CORE_REJECTED_INCOMPLETE"
    assert parcial.completeness_metrics["mass_coverage"] < completo.completeness_metrics["mass_coverage"]


# ---------------------------------------------------------------------------------------------------
# 5 · sin acoplamiento de caso
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("archivo", ["core_components.py", "core_geometry.py"])
def test_ninguna_constante_de_caso_en_los_modulos_de_geometria(archivo):
    txt = open(os.path.join(SRC, "geometry", archivo), encoding="utf-8").read()
    for t in ("RES", "Real Estate Services", "608.12", "003_res_unknown", "1788", "1070",
              "645", "1300", "835", "GPS", "403", "543", "7395", "6342"):
        assert not re.search(r"(?<![A-Za-z0-9_.])" + re.escape(t) + r"(?![A-Za-z0-9_.])", txt), t


# ---------------------------------------------------------------------------------------------------
# 6 · contrato de salida: una entidad semántica, N entradas del esquema, con procedencia
# ---------------------------------------------------------------------------------------------------
def test_una_entidad_semantica_produce_n_entradas_core_con_procedencia():
    c = _eval("C_THREE_LEGITIMATE_COMPONENTS")
    cores = CG.cores_from_candidate(c)
    assert len(cores) == c.metrics["components"] == 3
    assert [k.ring for k in cores] == c.components
    for i, k in enumerate(cores):
        assert k.meta.provenance != "unknown"
        assert f"core {i + 1}/3" in k.meta.notes
        assert c.contract_version in k.meta.notes
        assert "fabricated_fraction" in k.meta.notes and "bridge_validation" in k.meta.notes


def test_las_entradas_de_salida_no_afirman_que_haya_tres_nucleos():
    """N regiones de UN núcleo no son N núcleos. La nota lo dice explícitamente y el estado del
    conjunto es el mismo para todas las entradas."""
    c = _eval("B_TWO_LEGITIMATE_COMPONENTS")
    cores = CG.cores_from_candidate(c)
    assert {k.meta.status for k in cores} == {cores[0].meta.status}
    assert all(k.kind == "core" for k in cores)
