"""E16.13.1 — el contrato geométrico admite 1..N regiones, y el PRODUCTOR NO SE MUEVE.

E16.13 se invalidó por mezclar dos variables: contrato y productor. Aquí la única variable es el
contrato, y eso se comprueba, no se afirma: `test_el_productor_no_cambio_respecto_de_la_base_limpia`
hashea el texto exacto de las funciones del productor contra la revisión base.

Los fixtures declaran su geometría. Exigirle al productor congelado que genere dos o tres regiones
sería volver a mezclar las variables."""
import json
import os
import re
import subprocess

import cv2
import numpy as np
import pytest

from escalimetro.generalization import producer_freeze as PF
from escalimetro.geometry import core_components as CCOMP
from escalimetro.geometry import core_fabrication as CF
from escalimetro.geometry import core_geometry as CG
from escalimetro.geometry.core_components import InvalidCoreGeometry, MultiComponentCoreError

ROOT = os.path.dirname(os.path.dirname(__file__))
FX = os.path.join(ROOT, "tests", "fixtures", "core_components")
SRC = os.path.join(ROOT, "src", "escalimetro")
#: revisión con el motor anterior al ciclo: E16.12, que no cambió el motor respecto de E16.11
BASE_LIMPIA = "c6de3f9"

ACEPTAN = {"A_SINGLE_COMPONENT_LEGACY": 1, "B_TWO_LEGITIMATE_COMPONENTS": 2,
           "C_THREE_LEGITIMATE_COMPONENTS": 3}
RECHAZAN = ["E_SPURIOUS_COMPONENT", "F_TINY_COMPONENT", "J_OPEN_FLOOR_COMPONENT"]
INVALIDAS = ["G_OVERLAPPING_COMPONENTS", "H_COMPONENT_OUTSIDE_FOOTPRINT"]


def _fx(n):
    img = cv2.imread(os.path.join(FX, n + ".png"))
    meta = json.load(open(os.path.join(FX, n + ".json"), encoding="utf-8"))
    fp = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(fp, [np.array(meta["footprint_ring"], np.int32)], 255)
    return img, fp, meta


def _eval(n, key="candidate_rings", **kw):
    img, fp, meta = _fx(n)
    return CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta[key], **kw)


def _hay_git():
    return subprocess.run(["git", "-C", ROOT, "cat-file", "-e", BASE_LIMPIA + "^{commit}"],
                          capture_output=True).returncode == 0


# ---------------------------------------------------------------------------------------------------
# 0 · LA FRONTERA DEL EXPERIMENTO — el test que E16.13 no tenía
# ---------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not _hay_git(), reason="la base limpia no está en este clon")
def test_el_productor_no_cambio_entre_la_base_limpia_y_e16_13_1():
    """UNA VARIABLE en E16.13.1: el contrato. La comprobación se hace entre las DOS revisiones
    históricas —la base limpia y el commit de E16.13.1— y no contra el árbol de trabajo, porque
    ciclos posteriores SÍ pueden mover el productor (E16.14 lo hace a propósito). Lo que este test
    protege es el hecho histórico: cuando se migró el contrato, el productor no se tocó."""
    if subprocess.run(["git", "-C", ROOT, "cat-file", "-e", "6c5142d^{commit}"],
                      capture_output=True).returncode != 0:
        pytest.skip("el commit de E16.13.1 no está en este clon")
    a = PF.producer_segments(PF.read_git(BASE_LIMPIA, ROOT))
    b = PF.producer_segments(PF.read_git("6c5142d", ROOT))
    assert set(a) == set(b) and all(a[k] == b[k] for k in a), "E16.13.1 tocó el productor"
    assert PF.producer_hash(PF.read_git(BASE_LIMPIA, ROOT)) == \
        PF.producer_hash(PF.read_git("6c5142d", ROOT))


def test_el_productor_del_experimento_invalido_no_pasaria_esta_frontera():
    """El ciclo anterior habría sido detenido por este test. Se comprueba contra el propio commit
    inválido si está disponible en el clon."""
    if subprocess.run(["git", "-C", ROOT, "cat-file", "-e", "ee4334e^{commit}"],
                      capture_output=True).returncode != 0:
        pytest.skip("el commit del experimento inválido no está en este clon")
    base = PF.producer_segments(PF.read_git(BASE_LIMPIA, ROOT))
    try:
        malo = PF.producer_segments(PF.read_git("ee4334e", ROOT))
    except KeyError as e:
        assert "LINK_FRAC" in str(e)      # allí el parámetro de enlace fue renombrado: ya es cambio
        return
    assert any(base[k] != malo.get(k) for k in base), "debería detectar el cambio de productor"


# ---------------------------------------------------------------------------------------------------
# 1 · representación: 1..N regiones, sin reparación semántica
# ---------------------------------------------------------------------------------------------------
def test_la_version_del_contrato_cambia_de_mayor():
    assert CCOMP.CONTRACT_VERSION.startswith("core-geometry/2.")


@pytest.mark.parametrize("nombre,piezas", sorted(ACEPTAN.items()))
def test_las_regiones_legitimas_se_representan_y_se_aceptan(nombre, piezas):
    c = _eval(nombre)
    assert c.metrics["components"] == piezas and len(c.components) == piezas, (nombre, c.metrics)
    assert c.accepted and c.status == "CORE_ACCEPTED", (nombre, c.reasons)


def test_una_region_es_el_caso_degenerado_y_no_un_camino_aparte():
    c = _eval("A_SINGLE_COMPONENT_LEGACY")
    assert len(c.components) == 1 and c.ring == c.components[0] and c.single_ring() == c.ring


def test_una_region_diminuta_no_se_descarta_sino_que_se_juzga():
    """§7: descartarla sería REPARACIÓN SEMÁNTICA —taparía un defecto de quien la produjo— y no hay
    umbral de tamaño calibrado. Se conserva, se mide y la vetan las mismas invariantes de siempre."""
    img, fp, meta = _fx("F_TINY_COMPONENT")
    c = CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["candidate_rings"])
    assert len(meta["candidate_rings"]) == 3
    assert c.metrics["components"] == meta["expected_components"] == 3, "no se descartó ninguna"
    assert c.metrics["min_component_frac"] < 0.001, "la región diminuta sigue ahí y está medida"
    assert not c.accepted and any("componente 2" in r for r in c.reasons), c.reasons
    assert CCOMP.NOISE_POLICY == "NOT_CALIBRATED_KEEP_AND_REPORT"
    txt = open(os.path.join(SRC, "geometry", "core_components.py"), encoding="utf-8").read()
    assert "NOISE_COMPONENT_MIN_FRAC" not in txt, "no se hereda el umbral del intento inválido"


@pytest.mark.parametrize("nombre", INVALIDAS)
def test_las_geometrias_no_representables_se_rechazan_sin_arreglarlas(nombre):
    """Solape y pieza fuera de la huella no se canonicalizan: se declaran inválidas. Fusionar o
    recortar produciría una geometría aceptable a partir de evidencia defectuosa."""
    img, fp, meta = _fx(nombre)
    with pytest.raises(InvalidCoreGeometry):
        CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["candidate_rings"])


def test_el_solape_no_se_fusiona_en_silencio():
    img, fp, meta = _fx("G_OVERLAPPING_COMPONENTS")
    with pytest.raises(InvalidCoreGeometry) as e:
        CCOMP.normalize_components([[(float(x), float(y)) for x, y in r]
                                    for r in meta["candidate_rings"]], fp)
    assert "solapan" in str(e.value)
    txt = open(os.path.join(SRC, "geometry", "core_components.py"), encoding="utf-8").read()
    assert "unary_union" not in txt, "no hay fusión de piezas en la representación"


def test_el_orden_de_las_regiones_es_canonico_y_estable():
    img, fp, meta = _fx("C_THREE_LEGITIMATE_COMPONENTS")
    r = meta["candidate_rings"]
    a = CCOMP.normalize_components([[(float(x), float(y)) for x, y in q] for q in r], fp)
    b = CCOMP.normalize_components([[(float(x), float(y)) for x, y in q] for q in reversed(r)], fp)
    assert a.components == b.components, "el mismo conjunto serializa igual en cualquier orden"
    assert a.areas_px == sorted(a.areas_px, reverse=True)


# ---------------------------------------------------------------------------------------------------
# 2 · `.ring`: la compatibilidad no puede costar silencio (§14)
# ---------------------------------------------------------------------------------------------------
def test_un_nucleo_de_varias_regiones_no_tiene_anillo_unico():
    c = _eval("C_THREE_LEGITIMATE_COMPONENTS")
    assert c.ring == [], "no hay 'el' anillo: el campo queda vacío, no con una parte"
    with pytest.raises(MultiComponentCoreError):
        c.single_ring()


def test_no_se_puede_construir_un_candidato_multi_region_con_anillo():
    with pytest.raises(MultiComponentCoreError):
        CG.CoreCandidate(np.zeros((4, 4), np.uint8), [(0, 0), (1, 0), (1, 1)], {},
                         components=[[(0, 0), (1, 0), (1, 1)], [(2, 2), (3, 2), (3, 3)]])


def test_la_vista_parcial_existe_pero_lo_dice_en_el_nombre():
    img, fp, meta = _fx("B_TWO_LEGITIMATE_COMPONENTS")
    cs = CCOMP.normalize_components([[(float(x), float(y)) for x, y in r]
                                     for r in meta["candidate_rings"]], fp)
    assert cs.largest_ring_view() == cs.components[0]
    with pytest.raises(MultiComponentCoreError):
        cs.single_ring()
    txt = open(os.path.join(SRC, "geometry", "core_components.py"), encoding="utf-8").read()
    assert not re.search(r"def\s+ring\s*\(", txt), \
        "no puede existir un alias `.ring` que devuelva calladamente una parte"
    assert not hasattr(cs, "ring"), "ni siquiera como atributo"


# ---------------------------------------------------------------------------------------------------
# 3 · el contrato pregunta propiedades, no cantidad de regiones (§9)
# ---------------------------------------------------------------------------------------------------
def test_el_contrato_no_tiene_ninguna_clave_que_cuente_regiones():
    for k in CG.CORE_ACCEPTANCE:
        assert k != "components_max" and "count" not in k, k
    src = open(os.path.join(SRC, "geometry", "core_geometry.py"), encoding="utf-8").read()
    i, j = src.index("def accept_core"), src.index("# ----", src.index("def accept_core"))
    assert "components" not in src[i:j], "el contrato no puede leer la cantidad de regiones"


def test_ningun_umbral_heredado_cambio_de_valor():
    """Este ciclo migra ÁMBITOS, no valores. Cualquier recalibración sería otra variable."""
    base = json_thresholds_from_git()
    for k, v in base.items():
        if k == "components_max":
            assert k not in CG.CORE_ACCEPTANCE
            continue
        assert CG.CORE_ACCEPTANCE[k] == v, (k, v, CG.CORE_ACCEPTANCE.get(k))


def json_thresholds_from_git():
    if not _hay_git():
        pytest.skip("la base limpia no está en este clon")
    txt = PF.read_git(BASE_LIMPIA, ROOT)("src/escalimetro/geometry/core_geometry.py")
    ns = {}
    bloque = txt[txt.index("CORE_ACCEPTANCE = {"):]
    bloque = bloque[:bloque.index("\n}\n") + 3]
    exec(bloque, {}, ns)
    return ns["CORE_ACCEPTANCE"]


@pytest.mark.parametrize("nombre", RECHAZAN)
def test_una_region_que_no_es_nucleo_veta_el_candidato(nombre):
    """El motor no recorta en silencio lo que no puede justificar: quedarse con las regiones buenas y
    tirar la mala sería la misma clase de error que E16.11 detectó."""
    c = _eval(nombre)
    assert not c.accepted and any("componente" in r for r in c.reasons), (nombre, c.reasons)


def test_la_invasion_por_region_ve_lo_que_el_promedio_de_la_union_esconde():
    c = _eval("J_OPEN_FLOOR_COMPONENT")
    assert c.metrics["open_floor_invasion"] < CG.CORE_ACCEPTANCE["open_floor_invasion_max"]
    assert max(m["open_floor_invasion"] for m in c.component_metrics) > \
        CG.CORE_ACCEPTANCE["open_floor_invasion_max"]
    assert CG.accept_core(c.metrics)[0], "lectura histórica (sólo unión): pasaría"
    ok, fails = CG.accept_core(c.metrics, None, c.component_metrics)
    assert not ok and fails


def test_la_solidez_de_la_union_mide_el_reparto_de_la_planta_y_no_la_forma_del_objeto():
    c = _eval("C_THREE_LEGITIMATE_COMPONENTS")
    assert min(m["solidity"] for m in c.component_metrics) > 0.9
    assert c.metrics["solidity"] < 0.75
    duro = {"solidity_min": 0.8}
    assert not CG.accept_core(c.metrics, duro)[0], "sobre la unión rechazaría"
    assert CG.accept_core(c.metrics, duro, c.component_metrics)[0], "por región acepta"


def test_cada_invariante_por_region_veta_cuando_se_endurece():
    c = _eval("B_TWO_LEGITIMATE_COMPONENTS")
    assert c.accepted
    per = c.component_metrics
    for k, v in (("wall_fraction_min", max(m["wall_fraction"] for m in per) + 0.1),
                 ("solidity_min", max(m["solidity"] for m in per) + 0.05),
                 ("open_floor_invasion_max", 0.0),
                 ("component_scope_overlap_min", 1.01)):
        ok, fails = CG.accept_core(c.metrics, {k: v}, per)
        assert not ok and fails, f"{k} no está vetando por región"


def test_cada_invariante_de_union_veta_cuando_se_endurece():
    c = _eval("B_TWO_LEGITIMATE_COMPONENTS")
    m = c.metrics
    for k, v in (("hint_iou_min", m["hint_iou"] + 0.1),
                 ("footprint_frac_min", m["footprint_frac"] + 0.05),
                 ("footprint_frac_max", m["footprint_frac"] - 0.01)):
        ok, fails = CG.accept_core(m, {k: v}, c.component_metrics)
        assert not ok and fails, f"{k} no está vetando sobre la unión"


# ---------------------------------------------------------------------------------------------------
# 4 · completitud sobre la UNIÓN (§10)
# ---------------------------------------------------------------------------------------------------
def test_la_completitud_mira_la_union_de_regiones():
    """Fixture mínimo del §10: una región, un ancla; tres regiones cubren el cluster."""
    completo = _eval("I_DISTRIBUTED_ANCHOR_COVERAGE")
    parcial = _eval("I_DISTRIBUTED_ANCHOR_COVERAGE", key="partial_rings")
    assert completo.metrics["components"] == 3
    assert completo.completeness_status == "COMPLETE" and completo.status == "CORE_ACCEPTED"
    assert parcial.completeness_status == "INCOMPLETE"
    assert parcial.status == "CORE_REJECTED_INCOMPLETE"
    assert parcial.completeness_metrics["mass_coverage"] < \
        completo.completeness_metrics["mass_coverage"]


def test_los_umbrales_de_completitud_de_e16_11_no_se_tocaron():
    from escalimetro.geometry import core_completeness as CC
    assert CC.COMPLETENESS_CONTRACT == {"significant_min_ratio": 0.10, "dominant_min_ratio": 0.25,
                                        "mass_coverage_min": 0.80, "min_significant_anchors": 2}


# ---------------------------------------------------------------------------------------------------
# 5 · fabricación: diagnóstico experimental, FUERA del contrato (§11)
# ---------------------------------------------------------------------------------------------------
def test_el_puente_se_distingue_del_candidato_honesto_del_mismo_dibujo():
    img, fp, meta = _fx("D_FABRICATED_BRIDGE")
    puente = CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["candidate_rings"])
    honesto = CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["honest_rings"])
    a = CF.fabrication_diagnostics(img, fp, puente)["fabricated_fraction"]
    b = CF.fabrication_diagnostics(img, fp, honesto)["fabricated_fraction"]
    assert puente.metrics["components"] == 1 and honesto.metrics["components"] == 2
    assert a > 10 * b


def test_la_fabricacion_no_participa_de_ninguna_decision():
    img, fp, meta = _fx("D_FABRICATED_BRIDGE")
    c = CG.evaluate_candidate(img, fp, tuple(meta["hint_region"]), meta["candidate_rings"])
    d = CF.fabrication_diagnostics(img, fp, c)
    assert d["bridge_validation"] == "NOT_CALIBRATED"
    assert c.accepted and not any("fabric" in r for r in c.reasons)
    assert "fabricated_fraction" not in c.metrics
    for k in CG.CORE_ACCEPTANCE:
        assert "fabric" not in k and "bridge" not in k, k
    src = open(os.path.join(SRC, "geometry", "core_geometry.py"), encoding="utf-8").read()
    assert "core_fabrication" not in src, "el contrato no importa el diagnóstico experimental"


# ---------------------------------------------------------------------------------------------------
# 6 · identidad semántica en la salida (§13)
# ---------------------------------------------------------------------------------------------------
def test_un_consumidor_distingue_un_nucleo_de_tres_regiones_de_tres_nucleos():
    from escalimetro.schemas.floorplate import Core, CoreGroup
    c = _eval("C_THREE_LEGITIMATE_COMPONENTS")
    uno = CG.cores_from_candidate(c, semantic_core_id="sc-1")
    assert len(uno) == 3
    assert {k.group.semantic_core_id for k in uno} == {"sc-1"}
    assert [k.group.component_index for k in uno] == [0, 1, 2]
    assert {k.group.component_count for k in uno} == {3}
    # tres núcleos independientes: tres ids distintos y component_count 1
    tres = [CG.cores_from_candidate(_eval("A_SINGLE_COMPONENT_LEGACY"), semantic_core_id=f"sc-{i}")[0]
            for i in range(3)]
    assert len({k.group.semantic_core_id for k in tres}) == 3
    assert {k.group.component_count for k in tres} == {1}
    assert isinstance(uno[0].group, CoreGroup) and isinstance(uno[0], Core)


def test_el_vinculo_semantico_sobrevive_a_la_serializacion_y_no_vive_en_notes():
    import dataclasses
    from escalimetro.schemas.floorplate import CoreGroup
    c = _eval("B_TWO_LEGITIMATE_COMPONENTS")
    cores = CG.cores_from_candidate(c, semantic_core_id="sc-9")
    d = [dataclasses.asdict(k) for k in cores]
    assert all(x["group"]["semantic_core_id"] == "sc-9" for x in d)
    vuelta = [CoreGroup(**x["group"]) for x in d]
    assert [g.component_index for g in vuelta] == [0, 1] and vuelta[0].component_count == 2
    assert all("2/2" not in k.meta.notes for k in cores), \
        "el vínculo es un campo, no una nota en prosa"


# ---------------------------------------------------------------------------------------------------
# 7 · sin acoplamiento de caso
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("archivo", ["core_components.py", "core_geometry.py", "core_fabrication.py"])
def test_ninguna_constante_de_caso_en_los_modulos_de_geometria(archivo):
    txt = open(os.path.join(SRC, "geometry", archivo), encoding="utf-8").read()
    for t in ("RES", "Real Estate Services", "608.12", "003_res_unknown", "1788", "1070",
              "645", "1300", "835", "GPS", "403", "543", "7395", "6342"):
        assert not re.search(r"(?<![A-Za-z0-9_.])" + re.escape(t) + r"(?![A-Za-z0-9_.])", txt), t
