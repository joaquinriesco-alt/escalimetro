"""E09 — tests de la lógica del experimento.

No se agregan tests "por deporte" (§25). Estos cubren el código NUEVO que va a interpretar las respuestas
reales cuando existan credenciales: el mapeo entre los dos vocabularios, la clasificación del caso de la
recepción, el estado de acuerdo y la ablación. Si esta lógica está mal, el informe de E09 mentirá aunque
las llamadas funcionen.

Se usan las fixtures MOCK de E08 (tres fuentes) para ejercitar el camino "con datos", y la corrida real
bloqueada para el camino "sin datos"."""
import json
import os

import pytest

from escalimetro.ai.e09 import (COMPARABLE, ablation, agreement_matrix, agreement_status,
                                reception_case, score_of, strategy_readability, value_per_provider)

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
E09 = os.path.join(CASE, "ai", "E09")
FIX = os.path.join(ROOT, "tests", "fixtures", "ai", "mock_reviews.json")
ALTS = ["A", "B", "C"]


@pytest.fixture(scope="module")
def mock():
    return json.load(open(FIX, encoding="utf-8"))


@pytest.fixture(scope="module")
def blocked():
    return {a: {"rule_based": {"provider": "deterministic", "scores": {"reception": 0.4},
                               "architectural_plausibility": 0.7, "strategy_alignment": 0.6,
                               "confidence": 0.55, "critical_issues": [], "warnings": []},
                "anthropic": None, "openai_vision": None} for a in ALTS}


# ---------------------------------------------------------------------------------------------------
# mapeo entre vocabularios
# ---------------------------------------------------------------------------------------------------
def test_score_of_traduce_el_vocabulario_visual(mock):
    """`reception` en el schema espacial y `reception_convincing` en el visual son el mismo aspecto."""
    vis = mock["C"]["openai_vision"]
    assert vis["scores"]["reception_convincing"] == score_of(vis, "reception")


def test_score_of_devuelve_none_sin_contraparte(mock):
    vis = mock["A"]["openai_vision"]
    assert score_of(vis, "kitchenette_dining") is None      # no se fuerza equivalencia inexistente
    assert score_of(None, "reception") is None


def test_overall_plausibility_toma_el_campo_de_cada_schema(mock):
    assert score_of(mock["A"]["anthropic"], "overall_plausibility") == \
        mock["A"]["anthropic"]["architectural_plausibility"]
    assert score_of(mock["A"]["openai_vision"], "overall_plausibility") == \
        mock["A"]["openai_vision"]["visual_plausibility"]


# ---------------------------------------------------------------------------------------------------
# estado de acuerdo — mismos umbrales que E08, sin recalibrar
# ---------------------------------------------------------------------------------------------------
def test_agreement_status_usa_los_umbrales_de_e08():
    from escalimetro.ai.review_aggregator import AGREEMENT_DELTA, CRITICAL_DELTA, DISAGREEMENT_DELTA
    assert agreement_status({"a": 0.70, "b": 0.75}) == "AGREEMENT"
    assert agreement_status({"a": 0.40, "b": 0.75}) == "DISAGREEMENT"
    assert agreement_status({"a": 0.18, "b": 0.72}) == "CRITICAL_DISAGREEMENT"
    assert agreement_status({"a": 0.60, "b": 0.80}) == "PARTIAL"
    assert (AGREEMENT_DELTA, DISAGREEMENT_DELTA, CRITICAL_DELTA) == (0.12, 0.30, 0.45)


def test_una_sola_fuente_es_blocked_no_acuerdo():
    assert agreement_status({"rule_based": 0.7}) == "BLOCKED"


def test_matriz_cubre_todas_las_celdas(mock):
    rows = agreement_matrix(mock)
    assert len(rows) == len(ALTS) * len(COMPARABLE)
    crit = [r for r in rows if r["agreement_status"] == "CRITICAL_DISAGREEMENT"]
    assert crit and crit[0]["aspect"] == "reception" and crit[0]["alternative_id"] == "C"


def test_matriz_marca_blocked_sin_proveedores(blocked):
    rows = agreement_matrix(blocked)
    assert all(r["agreement_status"] == "BLOCKED" for r in rows)
    assert all(r["delta_max"] is None for r in rows)


# ---------------------------------------------------------------------------------------------------
# §9 caso de control: la recepción
# ---------------------------------------------------------------------------------------------------
def test_reception_confirmed_defect(mock):
    """En C el crítico visual la ve en 0.18: el defecto queda confirmado por ese lado."""
    c = reception_case(mock)["C"]
    assert c["openai_vision"] < 0.5
    assert c["classification"] in ("CONFIRMED_DEFECT", "AI_DISAGREEMENT")


def test_reception_false_positive_si_ambos_la_ven_bien(mock):
    m = json.loads(json.dumps(mock))
    m["A"]["anthropic"]["scores"]["reception"] = 0.82
    m["A"]["openai_vision"]["scores"]["reception_convincing"] = 0.80
    assert reception_case(m)["A"]["classification"] == "RULE_CRITIC_FALSE_POSITIVE"


def test_reception_ai_disagreement(mock):
    m = json.loads(json.dumps(mock))
    m["B"]["anthropic"]["scores"]["reception"] = 0.85
    m["B"]["openai_vision"]["scores"]["reception_convincing"] = 0.20
    assert reception_case(m)["B"]["classification"] == "AI_DISAGREEMENT"


def test_reception_unclear_y_blocked_sin_modelos(blocked):
    r = reception_case(blocked)
    assert all(r[a]["classification"] == "UNCLEAR" and r[a]["status"] == "BLOCKED" for a in ALTS)


# ---------------------------------------------------------------------------------------------------
# §10 legibilidad de estrategia
# ---------------------------------------------------------------------------------------------------
def test_strategy_readability_reporta_las_tres_fuentes(mock):
    s = strategy_readability(mock)
    assert s["A"]["status"] == "EXECUTED"
    assert s["A"]["openai_visual"] is not None and s["A"]["anthropic_structured"] is not None


def test_strategy_readability_blocked(blocked):
    assert all(strategy_readability(blocked)[a]["status"] == "BLOCKED" for a in ALTS)


# ---------------------------------------------------------------------------------------------------
# §12 ablación
# ---------------------------------------------------------------------------------------------------
def _lat():
    return {a: {"rule_based": 10.0, "anthropic": 900.0, "openai_vision": 1500.0} for a in ALTS}


def test_ablacion_cuatro_configuraciones(mock):
    rows = ablation(mock, _lat(), {})
    assert [r["config"] for r in rows] == ["CONFIG_0", "CONFIG_1", "CONFIG_2", "CONFIG_3"]
    assert all(r["status"] == "EXECUTED" for r in rows)


def test_ablacion_config3_ve_mas_desacuerdos_que_config0(mock):
    rows = {r["config"]: r for r in ablation(mock, _lat(), {})}
    assert rows["CONFIG_0"]["disagreements"] == 0        # una sola fuente: no hay con quién discrepar
    assert rows["CONFIG_3"]["disagreements"] > 0


def test_ablacion_marca_blocked_lo_que_falta(blocked):
    rows = ablation(blocked, _lat(), {})
    assert rows[0]["status"] == "EXECUTED"                # CONFIG_0 sí se puede evaluar
    assert all(r["status"] == "BLOCKED" for r in rows[1:])
    assert "anthropic" in rows[1]["blocked_sources"]
    assert all("issues_detected" not in r for r in rows[1:])   # no se estima nada


# ---------------------------------------------------------------------------------------------------
# §13 valor por proveedor
# ---------------------------------------------------------------------------------------------------
def test_valor_es_insufficient_evidence_sin_contraste(blocked):
    v = {r["provider"]: r for r in value_per_provider(blocked, [], {}, _lat())}
    assert v["anthropic"]["incremental_value"] == "INSUFFICIENT_EVIDENCE"
    assert v["openai_vision"]["status"] == "BLOCKED"
    assert v["rule_based"]["incremental_value"] == "INSUFFICIENT_EVIDENCE"


def test_valor_no_inventa_numeros_para_un_proveedor_ausente(blocked):
    v = {r["provider"]: r for r in value_per_provider(blocked, [], {}, _lat())}
    assert v["anthropic"]["unique_useful_findings"] is None
    assert v["anthropic"]["cost_usd"] is None


# ---------------------------------------------------------------------------------------------------
# corrida real (bloqueada) — los artefactos existen y declaran su estado
# ---------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.isdir(E09), reason="requiere la corrida E09")
def test_corrida_e09_declara_su_bloqueo_sin_inventar():
    s = json.load(open(os.path.join(E09, "summary.json"), encoding="utf-8"))
    if s["api_execution_status"].startswith("BLOCKED"):
        assert s["gate_api"] == "BLOCKED"
        assert s["gate_multi_model_value"] == "INSUFFICIENT_EVIDENCE"
        assert s["standard_03"].startswith("NOT PRODUCED")
        rv = json.load(open(os.path.join(E09, "real_reviews_abc.json"), encoding="utf-8"))
        for a in ALTS:
            assert rv[a]["anthropic"] is None and rv[a]["openai_vision"] is None
    assert s["geometry_locked"] is True


@pytest.mark.skipif(not os.path.isdir(E09), reason="requiere la corrida E09")
def test_geometry_hash_no_cambio_en_e09():
    g = json.load(open(os.path.join(E09, "geometry_hash_check.json"), encoding="utf-8"))
    assert g["identical"] is True
    assert g["geometry_hash_before"] == g["geometry_hash_after"]
    e08 = json.load(open(os.path.join(CASE, "ai", "E08", "summary.json"), encoding="utf-8"))
    assert g["geometry_hash_before"] == e08["geometry_hashes_before"]   # mismo baseline que E08


@pytest.mark.skipif(not os.path.isdir(E09), reason="requiere la corrida E09")
def test_las_nueve_visuales_de_e09_existen():
    for n in ("real_reviews_abc.png", "provider_agreement_matrix.png", "reception_case_study.png",
              "strategy_readability_comparison.png", "provider_ablation.png", "real_cost_latency.png",
              "geometry_hash_check.png", "provider_value_summary.png", "presentation_01_02_03.png"):
        p = os.path.join(E09, n)
        assert os.path.exists(p) and os.path.getsize(p) > 20000, n
