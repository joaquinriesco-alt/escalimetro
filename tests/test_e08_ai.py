"""E08 — tests de la capa de IA.

Ninguno de estos tests gasta dinero: los proveedores se inyectan como dobles. Los tests de integración
real están marcados `@pytest.mark.integration` y se saltan solos si no hay API keys."""
import base64
import json
import os
import time

import jsonschema
import pytest

from escalimetro.ai import prompts
from escalimetro.ai.config import AIProviderConfig, load_configs, missing_keys
from escalimetro.ai.costs import estimate_cost, pricing_snapshot
from escalimetro.ai.geometry_guard import GeometryGuard, GeometryMutated, canonical_geometry, geometry_hash
from escalimetro.ai.orchestrator import AIOrchestrator
from escalimetro.ai.providers.anthropic_provider import AnthropicProvider
from escalimetro.ai.providers.base import AIProvider, ProviderError, ProviderUnavailable, extract_json
from escalimetro.ai.providers.deterministic_provider import DeterministicProvider
from escalimetro.ai.providers.openai_provider import OpenAIProvider
from escalimetro.ai.review_aggregator import aggregate, requires_internal_review
from escalimetro.ai.reviewers import build_payload
from escalimetro.ai.schemas import (SCHEMAS, SchemaFailure, assert_no_coordinates, find_coordinates,
                                    validate)
from escalimetro.ai.telemetry import UsageLedger, contains_secret, scrub
from escalimetro.layout.model import Layout

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
E07 = os.path.join(CASE, "layouts", "E07")
E08 = os.path.join(CASE, "ai", "E08")
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "ai")
ALTS = ["A", "B", "C"]
# Cadena opaca a propósito: NO imita el formato de una credencial real, para que ningún escáner
# de secretos (el de E11 o el de GitHub) marque el repo por un valor de test.
FAKE_KEY = "DUMMY-KEY-FOR-TESTS-NOT-A-CREDENTIAL"


# ---------------------------------------------------------------------------------------------------
# dobles
# ---------------------------------------------------------------------------------------------------
class ScriptedProvider(AIProvider):
    """Devuelve, en orden, lo que se le pase: str (texto crudo) o Exception (a lanzar)."""
    name = "scripted"

    def __init__(self, cfg, script, sleep=lambda s: None):
        super().__init__(cfg, sleep=sleep)
        self.script = list(script)
        self.calls = 0

    def _call(self, prompt, images, system):
        self.calls += 1
        item = self.script.pop(0) if self.script else '{"x": 1}'
        if isinstance(item, Exception):
            raise item
        return {"text": item, "input_tokens": 1200, "output_tokens": 300, "request_id": f"req_{self.calls}"}


def _cfg(provider="anthropic", purpose="spatial_review", retries=2, key=FAKE_KEY):
    return AIProviderConfig(provider=provider, model="test-model", purpose=purpose, timeout=5.0,
                            max_retries=retries, enabled=True, api_key_env="X", _api_key=key)


def _review(alt="A", provider="anthropic", **over):
    base = {
        "provider": provider, "model": "test-model", "alternative_id": alt,
        "prompt_version": "anthropic_spatial_review_v1",
        "scores": {k: 0.7 for k in ["arrival_sequence", "reception", "client_route", "boardroom_location",
                                    "meeting_accessibility", "privacy_gradient", "open_work_neighborhoods",
                                    "adjacency", "kitchenette_dining", "lounge"]},
        "critical_issues": [], "warnings": [], "strengths": ["ok"],
        "strategy_alignment": 0.7, "architectural_plausibility": 0.7, "confidence": 0.7,
        "summary": "test",
    }
    base.update(over)
    return base


@pytest.fixture(scope="module")
def shell():
    from escalimetro.layout.e06.scale import scaled_shell
    from escalimetro.schemas.floorplate import Floorplate
    return scaled_shell(Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json")), 1.0)


@pytest.fixture(scope="module")
def art():
    if not os.path.isdir(os.path.join(E07, "alternatives")):
        pytest.skip("requiere la corrida E07")
    return {a: Layout.load(os.path.join(E07, "alternatives", a, "layout.json")) for a in ALTS}


# ---------------------------------------------------------------------------------------------------
# configuración
# ---------------------------------------------------------------------------------------------------
def test_config_desde_env_sin_hardcode():
    cfgs = load_configs({"ANTHROPIC_MODEL_REVIEWER": "modelo-x", "OPENAI_MODEL_VISION": "modelo-y",
                         "OPENAI_MODEL_PRESENTATION": "modelo-z", "AI_PROVIDER_TIMEOUT": "12",
                         "AI_PROVIDER_MAX_RETRIES": "4"})
    assert cfgs["spatial_review"].model == "modelo-x"
    assert cfgs["visual_review"].model == "modelo-y"
    assert cfgs["presentation"].model == "modelo-z"
    assert all(c.timeout == 12.0 and c.max_retries == 4 for c in cfgs.values())


def test_config_registra_los_campos_pedidos():
    d = _cfg().to_dict()
    for k in ("provider", "model", "purpose", "timeout", "max_retries", "enabled"):
        assert k in d


def test_config_nunca_serializa_la_clave():
    d = _cfg().to_dict()
    assert FAKE_KEY not in json.dumps(d)
    assert d["has_key"] is True


def test_falta_de_api_key_deja_el_proveedor_no_disponible():
    cfgs = load_configs({})
    assert missing_keys(cfgs) == ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
    assert not cfgs["spatial_review"].available


def test_proveedor_sin_clave_falla_limpio():
    p = ScriptedProvider(_cfg(key=None), ['{"a":1}'])
    with pytest.raises(ProviderUnavailable):
        p.complete_json("x", "StructuredSpatialReview")
    assert p.calls == 0                                    # ni siquiera se intenta la llamada


def test_purpose_se_puede_deshabilitar_sin_quitar_la_clave():
    cfgs = load_configs({"ANTHROPIC_API_KEY": FAKE_KEY, "AI_DISABLE_SPATIAL_REVIEW": "1"})
    assert cfgs["spatial_review"].has_key and not cfgs["spatial_review"].available


# ---------------------------------------------------------------------------------------------------
# errores, retries, schemas
# ---------------------------------------------------------------------------------------------------
def test_timeout_reintenta_y_luego_falla():
    p = ScriptedProvider(_cfg(retries=2), [ProviderError("timeout", "t", True)] * 3)
    with pytest.raises(ProviderError) as e:
        p.complete_json("x", "StructuredSpatialReview")
    assert e.value.kind == "timeout" and p.calls == 3      # 1 intento + 2 reintentos, sin loop infinito


def test_rate_limit_reintenta_y_puede_recuperarse():
    p = ScriptedProvider(_cfg(), [ProviderError("rate_limit", "429", True),
                                  json.dumps(_review())])
    r = p.complete_json("x", "StructuredSpatialReview")
    assert r.usage.success and r.usage.attempts == 2


def test_respuesta_vacia_es_error_reintentable():
    p = ScriptedProvider(_cfg(retries=0), [""])
    with pytest.raises(ProviderError) as e:
        p.complete_json("x", "StructuredSpatialReview")
    assert e.value.kind == "empty_response"


def test_json_malformado_falla_como_tal():
    p = ScriptedProvider(_cfg(retries=0), ["esto no es json {"])
    with pytest.raises(ProviderError) as e:
        p.complete_json("x", "StructuredSpatialReview")
    assert e.value.kind == "malformed_json"


def test_json_envuelto_en_prosa_o_bloque_se_extrae():
    assert extract_json('bla ```json\n{"a": 1}\n``` fin')["a"] == 1
    assert extract_json('Aquí va: {"a": {"b": 2}} listo')["a"]["b"] == 2


def test_schema_invalido_reintenta_una_vez_y_marca_provider_failed_schema():
    bad = json.dumps({"provider": "anthropic"})
    p = ScriptedProvider(_cfg(retries=1), [bad, bad])
    with pytest.raises(ProviderError) as e:
        p.complete_json("x", "StructuredSpatialReview")
    assert e.value.kind == "provider_failed_schema" and p.calls == 2


def test_json_parcialmente_valido_no_se_acepta_en_silencio():
    r = _review()
    del r["confidence"]
    with pytest.raises(SchemaFailure):
        validate(r, "StructuredSpatialReview")


def test_todos_los_schemas_son_json_schema_validos():
    for name, sch in SCHEMAS.items():
        jsonschema.Draft202012Validator.check_schema(sch)


# ---------------------------------------------------------------------------------------------------
# prohibición de geometría en outputs de IA
# ---------------------------------------------------------------------------------------------------
def test_output_de_ia_no_puede_traer_coordenadas():
    r = _review()
    r["strengths"] = [{"x": 3.2, "y": 1.0}]
    assert find_coordinates(r)
    with pytest.raises(SchemaFailure):
        assert_no_coordinates(r)


def test_outputs_reales_no_traen_coordenadas():
    if not os.path.exists(os.path.join(E08, "reviews_abc.json")):
        pytest.skip("requiere la corrida E08")
    data = json.load(open(os.path.join(E08, "reviews_abc.json"), encoding="utf-8"))
    for alt in ALTS:
        for name, rv in data[alt]["reviews"].items():
            if rv:
                assert_no_coordinates(rv, name)
    assert_no_coordinates(json.load(open(os.path.join(E08, "presentation_spec.json"), encoding="utf-8")))


# ---------------------------------------------------------------------------------------------------
# geometría inmutable
# ---------------------------------------------------------------------------------------------------
def test_geometry_hash_es_estable_y_canonico(art, shell):
    a = art["A"]
    assert geometry_hash(a, shell) == geometry_hash(a, shell)
    g = canonical_geometry(a, shell)
    assert g["placements"] and g["circulation_nodes"] and g["shell_usable_wkt"]


def test_el_hash_cubre_el_shell_ademas_del_layout(art, shell):
    """El shell es común a las tres, pero sigue siendo geometría: entra al hash."""
    assert geometry_hash(art["A"], shell) != geometry_hash(art["A"], None)


def test_geometry_hash_distingue_alternativas(art):
    assert len({geometry_hash(art[a]) for a in ALTS}) == 3


def test_guard_detecta_mutacion(art):
    import copy
    lay = copy.deepcopy(art["A"])
    with pytest.raises(GeometryMutated):
        with GeometryGuard(lay, what="test"):
            lay.placements[0].x += 0.5


def test_guard_pasa_si_no_hay_mutacion(art):
    with GeometryGuard(art["B"], what="test") as g:
        pass
    assert g.to_dict()["identical"] is True


def test_la_capa_de_ia_no_muta_geometria(art):
    o = AIOrchestrator("test_project", env={})
    lay = art["A"]
    before = geometry_hash(lay)
    r = o.review_alternative("A", lay, _payload("A"))
    assert r.geometry_hash_before == before == geometry_hash(lay) == r.geometry_hash_after
    assert r.geometry_intact


def test_run_real_reporta_geometria_intacta():
    if not os.path.exists(os.path.join(E08, "summary.json")):
        pytest.skip("requiere la corrida E08")
    s = json.load(open(os.path.join(E08, "summary.json"), encoding="utf-8"))
    assert s["geometry_locked"] is True
    assert s["geometry_hashes_before"] == s["geometry_hashes_after"]
    assert all(v["geometry_intact"] for v in s["alternatives"].values())


# ---------------------------------------------------------------------------------------------------
# payload y revisores
# ---------------------------------------------------------------------------------------------------
def _payload(alt):
    d = os.path.join(E07, "alternatives", alt)
    from escalimetro.layout.e07.strategies import build_alternatives
    from escalimetro.layout.model import load_program
    prog = load_program(os.path.join(ROOT, "program_templates", "office_balanced_48.json"))
    spec = {s.alt: s for s in build_alternatives(prog)}[alt]
    comp = json.load(open(os.path.join(E07, "alternative_comparison.json"), encoding="utf-8"))
    row = [r for r in comp["rows"] if r["alt"] == alt][0]
    return build_payload(alt, spec.to_dict(),
                         Layout.load(os.path.join(d, "layout.json")).to_dict(),
                         json.load(open(os.path.join(d, "metrics.json"), encoding="utf-8")),
                         json.load(open(os.path.join(d, "critique.json"), encoding="utf-8")),
                         spec.graph.to_dict(),
                         json.load(open(os.path.join(E07, "fit_verdict.json"), encoding="utf-8")), row)


def test_payload_solo_lleva_alternativas_validadas(art):
    p = _payload("A")
    assert p["metrics_summary"]["seats"] == "40/40"
    assert p["metrics_summary"]["rooms_complete"] is True


def test_fallback_rule_based_siempre_produce_revision():
    p = DeterministicProvider(AIProviderConfig("deterministic", "rule_based_v1", "spatial_review"))
    r = p.complete_json("", "StructuredSpatialReview", purpose="spatial_review", context=_payload("A"))
    assert r.data["provider"] == "deterministic"
    validate(r.data, "StructuredSpatialReview")


def test_revision_anthropic_valida_su_schema():
    from escalimetro.ai.reviewers import AnthropicSpatialReviewer
    p = ScriptedProvider(_cfg(), [json.dumps(_review())])
    r = AnthropicSpatialReviewer(p, "anthropic").review(_payload("A"))
    assert r.ok and r.review["provider"] == "anthropic"


def test_revision_visual_openai_valida_su_schema():
    from escalimetro.ai.reviewers import OpenAIVisualArchitecturalCritic
    vis = {"provider": "openai", "model": "m", "alternative_id": "A",
           "prompt_version": "openai_visual_critic_v1",
           "scores": {k: 0.6 for k in ["arrival_reads_naturally", "reception_convincing",
                                       "client_circulation_sense", "room_proportions",
                                       "workspace_fragmentation", "wasted_zones"]},
           "critical_issues": [], "warnings": [], "strengths": ["ok"], "visual_plausibility": 0.6,
           "strategy_readability": 0.6, "ready_for_external_review": True, "confidence": 0.6,
           "summary": "t"}
    p = ScriptedProvider(_cfg(provider="openai", purpose="visual_review"), [json.dumps(vis)])
    r = OpenAIVisualArchitecturalCritic(p, "openai_vision").review(_payload("A"))
    assert r.ok and r.review["visual_plausibility"] == 0.6


def test_revisor_devuelve_error_sin_romper_el_pipeline():
    from escalimetro.ai.reviewers import AnthropicSpatialReviewer
    p = ScriptedProvider(_cfg(retries=0), [ProviderError("provider_unavailable", "caído")])
    r = AnthropicSpatialReviewer(p, "anthropic").review(_payload("A"))
    assert not r.ok and r.review is None and r.error == "provider_unavailable"


# ---------------------------------------------------------------------------------------------------
# prompts versionados
# ---------------------------------------------------------------------------------------------------
def test_prompts_existen_y_estan_versionados():
    for purpose, version in prompts.REGISTRY.items():
        assert version.endswith("_v1")
        assert prompts.load(version).strip()


def test_prompt_render_sustituye_payload_y_modelo():
    txt = prompts.render(prompts.REGISTRY["spatial_review"], {"k": "v"}, "modelo-x", "A")
    assert "modelo-x" in txt and '"k": "v"' in txt and "<PAYLOAD>" not in txt


def test_cada_output_registra_prompt_version():
    p = ScriptedProvider(_cfg(), [json.dumps(_review())])
    r = p.complete_json("x", "StructuredSpatialReview")
    assert r.data["prompt_version"] == "anthropic_spatial_review_v1"


# ---------------------------------------------------------------------------------------------------
# agregador
# ---------------------------------------------------------------------------------------------------
def _fixtures():
    return json.load(open(os.path.join(FIXTURES, "mock_reviews.json"), encoding="utf-8"))


def test_agregador_consenso_bueno():
    agg = aggregate("A", _fixtures()["A"], {}).to_dict()
    assert agg["status"] == "CONSENSUS_GOOD"
    assert agg["external_review_readiness"] == "READY_FOR_EXTERNAL_REVIEW"
    assert not requires_internal_review(agg)


def test_agregador_registra_desacuerdo_sin_promediarlo():
    agg = aggregate("B", _fixtures()["B"], {}).to_dict()
    assert agg["status"] == "DISAGREEMENT"
    assert agg["disagreements"]
    d = agg["disagreements"][0]
    assert d["delta"] >= 0.30 and len(d["scores"]) >= 2      # los valores originales siguen visibles
    assert requires_internal_review(agg)


def test_desacuerdo_critico_no_pasa_a_presentacion_final():
    agg = aggregate("C", _fixtures()["C"], {}).to_dict()
    assert agg["status"] == "CRITICAL_DISAGREEMENT"
    assert agg["critical_disagreements"]
    assert agg["external_review_readiness"] == "INTERNAL_REVIEW"
    assert requires_internal_review(agg)


def test_estado_provider_unavailable_cuando_falta_ia():
    rv = _fixtures()["A"]
    agg = aggregate("A", {"rule_based": rv["rule_based"], "anthropic": None, "openai_vision": None},
                    {"anthropic": "unavailable", "openai_vision": "unavailable"}).to_dict()
    assert agg["status"] == "PROVIDER_UNAVAILABLE"
    assert agg["sources"]["anthropic"] == "unavailable"


def test_fuentes_de_la_misma_familia_no_fabrican_consenso():
    """El visual determinista deriva del mismo crítico por reglas: coincidir con él no es evidencia."""
    rv = _fixtures()["A"]
    agg = aggregate("A", {"rule_based": rv["rule_based"], "deterministic_visual": rv["rule_based"]},
                    {}).to_dict()
    assert agg["agreements"] == []


def test_agregador_valida_su_schema():
    for a in ALTS:
        validate(aggregate(a, _fixtures()[a], {}).to_dict(), "AggregatedReview")


# ---------------------------------------------------------------------------------------------------
# telemetría de uso, costo y latencia
# ---------------------------------------------------------------------------------------------------
def test_usage_record_valida_schema():
    p = ScriptedProvider(_cfg(), [json.dumps(_review())])
    r = p.complete_json("x", "StructuredSpatialReview", alternative_id="A", project="p")
    d = r.usage.to_dict()
    assert d["input_tokens"] == 1200 and d["success"] is True and d["latency_ms"] >= 0


def test_costo_separa_estimado_reportado_y_desconocido():
    assert estimate_cost("openai", "gpt-5", 1000, 1000)[1] == "estimated"
    assert estimate_cost("openai", "modelo-inventado", 1000, 1000) == (None, "unknown")
    assert estimate_cost("anthropic", "claude-sonnet-4-5", None, None)[1] == "unknown"
    assert estimate_cost("deterministic", "rule_based_v1", None, None) == (0.0, "reported")
    assert "USD" in pricing_snapshot()["unit"]


def test_ledger_agrupa_por_proveedor_alternativa_y_proposito():
    led = UsageLedger("proj")
    for alt in ALTS:
        led.add({"provider": "anthropic", "model": "m", "purpose": "spatial_review", "input_tokens": 100,
                 "output_tokens": 50, "latency_ms": 10.0, "estimated_cost": 0.001,
                 "cost_status": "estimated", "request_id": "r", "success": True, "alternative_id": alt})
    s = led.summary()
    assert set(s["by_alternative"]) == set(ALTS)
    assert s["by_provider"]["anthropic"]["calls"] == 3
    assert s["total_cost"]["status"] == "estimated"


def test_latencias_se_registran_por_revisor(art):
    o = AIOrchestrator("test_project", env={})
    r = o.review_alternative("A", art["A"], _payload("A"))
    assert set(r.latencies_ms) == {"rule_based", "anthropic", "openai_vision"}
    assert all(v >= 0 for v in r.latencies_ms.values())


def test_ejecucion_paralela_no_es_secuencial():
    """Tres revisores de 0.35 s en paralelo deben tardar mucho menos que 1.05 s."""
    class Slow(DeterministicProvider):
        def complete_json(self, *a, **k):
            time.sleep(0.35)
            return super().complete_json(*a, **k)
    cfgS = AIProviderConfig("deterministic", "m", "spatial_review")
    cfgV = AIProviderConfig("deterministic", "m", "visual_review")
    o = AIOrchestrator("test_project", env={}, providers={"spatial_review": Slow(cfgS), "visual_review": Slow(cfgV),
                                          "presentation": Slow(AIProviderConfig("deterministic", "m", "presentation")),
                                          "deterministic_spatial": Slow(cfgS),
                                          "deterministic_visual": Slow(cfgV)})
    lay = Layout.load(os.path.join(E07, "alternatives", "A", "layout.json"))
    t0 = time.time()
    o.review_alternative("A", lay, _payload("A"))
    assert time.time() - t0 < 0.95


# ---------------------------------------------------------------------------------------------------
# secretos
# ---------------------------------------------------------------------------------------------------
def test_scrub_elimina_claves_y_formas_de_credencial():
    """Dos caminos: por NOMBRE de campo y por FORMA del valor.

    La cadena con forma de credencial se construye en tiempo de ejecución, nunca como literal en el
    archivo, para que ningún escáner de secretos marque este test."""
    shaped = "sk-" + "ant-" + "z" * 28          # forma de credencial, valor inventado
    d = scrub({"api_key": FAKE_KEY,             # por nombre de campo
               "nota": f"usa {shaped} aquí",    # por forma del valor
               "n": [{"authorization": "Bearer " + "a" * 30}]})
    blob = json.dumps(d)
    assert FAKE_KEY not in blob                 # el campo api_key fue redactado
    assert shaped not in blob                   # la forma fue redactada dentro de texto libre
    assert blob.count("REDACTED") >= 3


def test_ningun_output_del_repo_contiene_api_keys():
    roots = [os.path.join(CASE, "ai"), os.path.join(ROOT, "docs"), FIXTURES]
    checked = 0
    for root in roots:
        for dirpath, _, files in os.walk(root):
            for f in files:
                if not f.endswith((".json", ".md", ".txt", ".svg")):
                    continue
                txt = open(os.path.join(dirpath, f), encoding="utf-8", errors="ignore").read()
                assert not contains_secret(txt), os.path.join(dirpath, f)
                checked += 1
    assert checked > 0


def test_env_example_solo_tiene_nombres():
    p = os.path.join(ROOT, ".env.example")
    assert os.path.exists(p)
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert line.endswith("="), line                     # nombre, sin valor


def test_env_esta_en_gitignore():
    assert ".env" in open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()


def test_codigo_fuente_no_contiene_credenciales():
    src = os.path.join(ROOT, "src")
    for dirpath, _, files in os.walk(src):
        for f in files:
            if f.endswith(".py"):
                txt = open(os.path.join(dirpath, f), encoding="utf-8").read()
                assert not contains_secret(txt), f


# ---------------------------------------------------------------------------------------------------
# PresentationSpec y renderer determinista
# ---------------------------------------------------------------------------------------------------
def test_presentation_spec_valida_y_no_trae_geometria():
    if not os.path.exists(os.path.join(E08, "presentation_spec.json")):
        pytest.skip("requiere la corrida E08")
    spec = json.load(open(os.path.join(E08, "presentation_spec.json"), encoding="utf-8"))
    validate(spec, "PresentationSpec")
    assert_no_coordinates(spec)
    assert set(spec["alternative_order"]) == set(ALTS)


def test_el_renderer_de_lamina_no_toca_la_geometria(art):
    """La lámina 02 se compone a partir del MISMO SVG del renderer; el hash no se mueve."""
    from escalimetro.ai.board02 import build_board02
    from escalimetro.layout.e06.scale import scaled_shell
    from escalimetro.schemas.floorplate import Floorplate
    if not os.path.exists(os.path.join(E08, "presentation_spec.json")):
        pytest.skip("requiere la corrida E08")
    spec = json.load(open(os.path.join(E08, "presentation_spec.json"), encoding="utf-8"))
    # E16.1: la lámina 02 ya no recibe el dict de fit_verdict.json — recibe hechos del caso y
    # evidencia computada, igual que la Standard 01.
    from escalimetro.case_context import from_case_dir
    from escalimetro.fit_evidence import load as load_fit_evidence
    ctx = from_case_dir(CASE)
    evidence = load_fit_evidence(CASE)
    comp = json.load(open(os.path.join(E07, "alternative_comparison.json"), encoding="utf-8"))
    rows = {r["alt"]: r for r in comp["rows"]}
    shell = scaled_shell(Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json")), 1.0)
    alts = [{"alt": a, "layout": art[a], "row": rows[a],
             "metrics": json.load(open(os.path.join(E07, "alternatives", a, "metrics.json"), encoding="utf-8")),
             "critique": {}} for a in ALTS]
    before = {a: geometry_hash(art[a]) for a in ALTS}
    from escalimetro.layout.model import load_program as _lp
    svg = build_board02(alts, shell, spec, ctx, evidence,
                        program=_lp(os.path.join(ROOT, "program_templates", "office_balanced_48.json")))
    assert svg.startswith("<svg") and "STANDARD 02" in svg
    assert {a: geometry_hash(art[a]) for a in ALTS} == before


def test_lamina_02_incrusta_las_mismas_coordenadas_que_el_layout(art):
    """Identidad de renderer: los rectángulos de los 16 recintos de la lámina son los del layout."""
    from escalimetro.ai.board02 import _plan
    from escalimetro.layout.e06.scale import scaled_shell
    from escalimetro.layout.render import _Tf
    from escalimetro.schemas.floorplate import Floorplate
    shell = scaled_shell(Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json")), 1.0)
    for a in ALTS:
        body, wv, hv = _plan(art[a], shell, width_px=1500)
        tf = _Tf(shell, 1500, 10, extra_bottom=0)
        n = 0
        for p in art[a].placements:
            if p.module.startswith("workstation"):
                continue
            X, Y, W, D = tf.rect(p.x, p.y, p.w, p.d)
            assert f'x="{X:.1f}" y="{Y:.1f}" width="{W:.1f}" height="{D:.1f}"' in body
            n += 1
        assert n == 16


def test_outputs_e08_existen():
    if not os.path.isdir(E08):
        pytest.skip("requiere la corrida E08")
    for f in ("provider_architecture.png", "ai_workflow.png", "reviews_abc.json",
              "review_disagreements.png", "ai_usage_summary.json", "ai_latency_profile.png",
              "presentation_spec.json", "ESCALIMETRO_PRESENTATION_STANDARD_02.png",
              "presentation_standard_01_vs_02.png", "provider_decision_log.json"):
        p = os.path.join(E08, f)
        assert os.path.exists(p) and os.path.getsize(p) > 500, f


def test_decision_log_registra_que_vio_cada_proveedor():
    if not os.path.exists(os.path.join(E08, "provider_decision_log.json")):
        pytest.skip("requiere la corrida E08")
    log = json.load(open(os.path.join(E08, "provider_decision_log.json"), encoding="utf-8"))
    for a in ALTS:
        assert "render" in log[a]["seen_by"]["openai_vision"]
        assert set(log[a]) >= {"reviews", "agreements", "disagreements", "critical_disagreements",
                               "status", "geometry_hash"}


# ---------------------------------------------------------------------------------------------------
# integración real — sólo con API keys, y sólo bajo petición explícita
# ---------------------------------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="sin ANTHROPIC_API_KEY")
def test_integration_anthropic_review_real():
    o = AIOrchestrator("test_project")
    lay = Layout.load(os.path.join(E07, "alternatives", "A", "layout.json"))
    r = o.review_alternative("A", lay, _payload("A"))
    assert r.reviews["anthropic"], r.errors
    validate(r.reviews["anthropic"], "StructuredSpatialReview")
    assert r.geometry_intact


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="sin OPENAI_API_KEY")
def test_integration_openai_visual_review_real():
    o = AIOrchestrator("test_project")
    lay = Layout.load(os.path.join(E07, "alternatives", "A", "layout.json"))
    img = os.path.join(E07, "alternatives", "A", "layout_commercial.png")
    r = o.review_alternative("A", lay, _payload("A"), image_paths=[img])
    assert r.reviews["openai_vision"], r.errors
    validate(r.reviews["openai_vision"], "VisualArchitecturalReview")
    assert r.geometry_intact
