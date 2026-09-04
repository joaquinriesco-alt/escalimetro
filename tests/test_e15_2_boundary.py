"""E15.2 — cierre de las tres fronteras que quedaban abiertas tras E15.1.

A · `scale_confidence` es evidencia derivada y ya no puede declararse como entrada.
B · la evidencia histórica exige compatibilidad explícita de motor, no sólo floorplate y programa.
C · un diccionario con las claves correctas no es evidencia: la presentación exige el tipo."""
import json
import os

import pytest

from escalimetro import fit_evidence as FE
from escalimetro.case_context import (CASE_INPUT_FIELDS, COMPUTED_RESULT_FIELDS,
                                      COMPUTED_RESULT_NOT_ALLOWED, DERIVED_EVIDENCE_FIELDS,
                                      DERIVED_EVIDENCE_NOT_ALLOWED, CaseContext,
                                      MissingCaseMetadata, from_case_dir, validate_case_input)
from escalimetro.fit_evidence import PresentationFit
from escalimetro.layout.e07.board import build_board

ROOT = os.path.dirname(os.path.dirname(__file__))
C403 = os.path.join(ROOT, "cases", "001_gps_403")
C401 = os.path.join(ROOT, "cases", "002_gps_401")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")
GENERIC = os.path.join(ROOT, "tests", "fixtures", "generalization", "TEST_GENERIC_CASE.json")
COMPAT = os.path.join(ROOT, "cases", "generalization", "ENGINE_COMPATIBILITY.json")


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _cases():
    base = os.path.join(ROOT, "cases")
    return [os.path.join(base, d, "case.json") for d in sorted(os.listdir(base))
            if os.path.exists(os.path.join(base, d, "case.json"))]


# ===================================================================================================
# A · scale_confidence fuera de la entrada
# ===================================================================================================
def test_scale_confidence_es_rechazado_como_entrada():
    with pytest.raises(MissingCaseMetadata) as e:
        validate_case_input({"case_id": "X", "unit_label": "Oficina 999",
                             "scale_confidence": "LOW"})
    assert DERIVED_EVIDENCE_NOT_ALLOWED in str(e.value)
    assert "scale_confidence" in str(e.value)


def test_scale_confidence_no_esta_en_la_lista_de_entrada():
    assert "scale_confidence" not in CASE_INPUT_FIELDS
    assert "scale_confidence" in DERIVED_EVIDENCE_FIELDS


@pytest.mark.parametrize("field", sorted(DERIVED_EVIDENCE_FIELDS))
def test_ningun_valor_derivado_se_acepta_como_entrada(field):
    with pytest.raises(MissingCaseMetadata):
        validate_case_input({"case_id": "X", "unit_label": "Y", field: "loquesea"})


@pytest.mark.parametrize("field", sorted(COMPUTED_RESULT_FIELDS))
def test_ningun_resultado_se_acepta_como_entrada(field):
    with pytest.raises(MissingCaseMetadata) as e:
        validate_case_input({"case_id": "X", "unit_label": "Y", field: "loquesea"})
    assert COMPUTED_RESULT_NOT_ALLOWED in str(e.value)


def test_un_campo_desconocido_tambien_se_rechaza():
    """Sin esto, un resultado con nombre nuevo se colaría — que es como entró fit_verdict en E15."""
    with pytest.raises(MissingCaseMetadata):
        validate_case_input({"case_id": "X", "unit_label": "Y", "layout_is_great": True})


def test_los_case_json_reales_pasan_el_validador():
    for p in _cases():
        validate_case_input(_j(p), p)


def test_la_confianza_de_escala_sale_del_floorplate():
    fp = _j(os.path.join(C403, "outputs", "floorplate.json"))
    assert fp["scale"]["meta"]["confidence"] == 0.4
    assert from_case_dir(C403).scale_confidence == "LOW"
    assert "scale_confidence" not in _j(os.path.join(C403, "case.json"))


# ===================================================================================================
# B · procedencia y compatibilidad de motor
# ===================================================================================================
def test_la_declaracion_de_compatibilidad_existe_y_es_explicita():
    # E15.3 — el baseline vigente avanza cada ciclo, así que el test comprueba la FORMA de la
    # declaración y no un valor concreto que habría que editar cada vez.
    d = _j(COMPAT)
    assert {"E14", "E15", "E15.1", "E15.2"} <= set(d["baselines"])
    assert d["current_baseline"] in d["baselines"]
    assert d["current_baseline"] in d["compatible_with_current"]
    assert d["compatible_with_current"][0] == "E14"
    assert set(d["compatible_with_current"]) <= set(d["baselines"])
    assert d["transitions"][-1]["to"] == d["current_baseline"]
    for t in d["transitions"]:
        assert t["kind"] in ("NON_SEMANTIC", "SEMANTIC")
        assert t["evidence"], t
        assert "changed_files" in t, "el diff debe estar calculado, no afirmado"


def test_toda_transicion_que_toca_la_superficie_semantica_muestra_el_diff():
    d = _j(COMPAT)
    surface = set(d["semantic_surface"]["files"])
    for t in d["transitions"]:
        touched = {f for f in t["changed_files"] + t["added_files"] + t["removed_files"]
                   if f in surface}
        assert touched == set(t["semantic_surface_touched"]), t["from"] + "→" + t["to"]
        for f, why in t["semantic_surface_touched"].items():
            assert len(why) > 80, f"{f}: la justificación debe explicar el cambio, no nombrarlo"


def test_el_registro_legado_declara_su_baseline_productor():
    """E15.3 — CAMBIO DE CONTRATO INTENCIONAL. E15.2 escribía `producer_engine_baseline: "E14"` y
    explicaba en una nota que en realidad no sabía quién produjo estos artefactos: un campo de
    procedencia afirmando algo no probado. Ahora el productor es null/UNKNOWN y lo verificable —el
    baseline desde el que se puede comprobar compatibilidad— vive en su propio campo."""
    for case in (C403, C401):
        reg = _j(os.path.join(case, "layouts", FE.LEGACY_REGISTRY))
        assert reg["producer_engine_baseline"] is None
        assert reg["producer_engine_baseline_status"] == "UNKNOWN"
        assert reg["verified_compatible_from_baseline"] == "E14"


def test_la_evidencia_historica_sigue_vigente_bajo_el_baseline_actual():
    for case in (C403, C401):
        ev = FE.load(case, PROG)
        assert ev.freshness == FE.LEGACY_VERIFIED and ev.stale_reasons == []


def test_un_baseline_incompatible_vuelve_la_evidencia_stale(tmp_path):
    """§11 — el test obligatorio: motor futuro no declarado compatible ⇒ STALE."""
    d = _j(COMPAT)
    d["current_baseline"] = "E17_SOLVER_REWRITE"
    d["baselines"]["E17_SOLVER_REWRITE"] = "f" * 64
    d["compatible_with_current"] = ["E17_SOLVER_REWRITE"]          # E14 ya NO es compatible
    d["transitions"].append({"from": "E15.2", "to": "E17_SOLVER_REWRITE", "kind": "SEMANTIC",
                             "summary": "reescritura del solver (simulada)", "changed_files": [],
                             "added_files": [], "removed_files": [],
                             "semantic_surface_touched": {}, "evidence": ["simulación de test"]})
    p = tmp_path / "compat.json"
    json.dump(d, open(p, "w", encoding="utf-8"))
    ok, why = FE.engine_is_compatible("E14", str(p))
    assert ok is False and "no está declarado compatible" in why
    from escalimetro.fit_evidence import _freshness
    st, reasons = _freshness(C403, [], None, PROG, str(p))
    assert st == FE.STALE and any("no está declarado compatible" in r for r in reasons)


def test_un_cambio_no_semantico_declarado_mantiene_la_evidencia_valida(tmp_path):
    """§12 — el caso positivo: metadata/presentación no invalida un resultado geométrico."""
    d = _j(COMPAT)
    d["current_baseline"] = "E16_METADATA_ONLY"
    d["baselines"]["E16_METADATA_ONLY"] = "a" * 64
    d["compatible_with_current"] = ["E14", "E15", "E15.1", "E15.2", "E16_METADATA_ONLY"]
    d["transitions"].append({"from": "E15.2", "to": "E16_METADATA_ONLY", "kind": "NON_SEMANTIC",
                             "summary": "sólo metadatos (simulado)", "changed_files": [],
                             "added_files": [], "removed_files": [],
                             "semantic_surface_touched": {}, "evidence": ["simulación de test"]})
    p = tmp_path / "compat.json"
    json.dump(d, open(p, "w", encoding="utf-8"))
    ok, _ = FE.engine_is_compatible("E14", str(p))
    assert ok is True
    from escalimetro.fit_evidence import _freshness
    st, reasons = _freshness(C403, [os.path.join(C403, a) for a in
                                    [x["path"] for x in _j(os.path.join(C403, "layouts",
                                                                        FE.LEGACY_REGISTRY))["artifacts"]]],
                             None, PROG, str(p))
    assert st == FE.LEGACY_VERIFIED and reasons == []


def test_sin_declaracion_de_compatibilidad_no_se_asume_nada(tmp_path):
    ok, why = FE.engine_is_compatible("E14", str(tmp_path / "no_existe.json"))
    assert ok is False and "no hay declaración" in why


def test_evidencia_sin_baseline_productor_no_es_vigente():
    ok, why = FE.engine_is_compatible(None)
    assert ok is False and "no declara" in why


def test_evidencia_stale_no_puede_mostrar_el_veredicto_actual(tmp_path):
    """§11 — nunca ROBUST WITHIN… en silencio."""
    ev = FE.load(C403, PROG)
    stale = FE.FitEvidence(technical=ev.technical, robustness=ev.robustness, freshness=FE.STALE,
                           stale_reasons=["baseline incompatible"],
                           source_artifacts=ev.source_artifacts)
    assert stale.presentable is False
    p = PresentationFit.from_evidence(from_case_dir(C403), stale)
    assert p.fit_label == FE.STALE_LABEL
    assert "ROBUST WITHIN" not in p.fit_label and p.fit == FE.STALE


# ===================================================================================================
# C · un dict no es evidencia
# ===================================================================================================
FABRICATED = {"technical_fit": "FIT", "fit_label": "ROBUST WITHIN ASSUMED SCALE RANGE"}


def test_la_lamina_rechaza_un_veredicto_fabricado_a_mano():
    """§16 — el test explícito: el dict tiene las claves correctas y aun así se rechaza.

    E15.3 — el mensaje ya no habla de `PresentationFit`: exigir ese tipo era el agujero (se podía
    construir a mano). El board ahora pide la EVIDENCIA."""
    ctx = from_case_dir(C403)
    with pytest.raises(TypeError) as e:
        build_board([], None, FABRICATED, ctx=ctx)
    assert "FitEvidence" in str(e.value)


@pytest.mark.parametrize("fake", [FABRICATED, {}, None, "ROBUST WITHIN", 42,
                                  {"technical_fit": "FIT", "robustness": "ROBUST_FIT",
                                   "freshness": "FRESH", "fit_label": "x", "unit": "y"}])
def test_ninguna_forma_de_dict_pasa_como_evidencia(fake):
    ctx = from_case_dir(C403)
    with pytest.raises((TypeError, ValueError)):
        build_board([], None, fake, ctx=ctx)


def test_presentationfit_solo_se_construye_desde_fitevidence():
    ctx = from_case_dir(C403)
    with pytest.raises(TypeError):
        PresentationFit.from_evidence(ctx, FABRICATED)
    with pytest.raises(TypeError):
        PresentationFit.from_evidence(ctx, None)


def test_presentationfit_lleva_su_procedencia():
    ctx = from_case_dir(C403)
    p = PresentationFit.from_evidence(ctx, FE.load(C403, PROG))
    assert isinstance(p, PresentationFit)
    assert len(p._provenance) == 4
    assert all("layouts/E0" in a for a in p._provenance)
    with pytest.raises(Exception):                     # frozen: no se puede reescribir el veredicto
        p.fit_label = "ROBUST WITHIN ASSUMED SCALE RANGE"


def test_un_caso_sin_evidencia_no_lleva_procedencia():
    ctx = from_case_dir(C403)
    p = PresentationFit.from_evidence(ctx, FE.FitEvidence())
    assert p._provenance == () and p.fit_label == FE.NOT_EVALUATED_LABEL


# ===================================================================================================
# regresiones duras
# ===================================================================================================
def test_403_evidencia_sigue_valida():
    ev = FE.load(C403, PROG)
    assert (ev.technical, ev.robustness, ev.freshness) == (FE.FIT, FE.ROBUST_FIT, FE.LEGACY_VERIFIED)


def test_403_lamina_byte_identica():
    import types
    from escalimetro.schemas.floorplate import Floorplate
    from escalimetro.layout.model import Layout, load_program
    from escalimetro.layout.e06.scale import scaled_shell
    from escalimetro.layout.e07.strategies import build_alternatives
    e07 = os.path.join(C403, "layouts", "E07")
    ctx = from_case_dir(C403)
    evidence = FE.load(C403, PROG)          # E15.3: el board recibe la EVIDENCIA
    shell = scaled_shell(Floorplate.load(os.path.join(C403, "outputs", "floorplate.json")), 1.0)
    specs = {s.alt: s for s in build_alternatives(load_program(PROG))}
    alts = []
    for a in "ABC":
        d = os.path.join(e07, "alternatives", a)
        alts.append({"spec": specs[a], "result": types.SimpleNamespace(
            layout=Layout.load(os.path.join(d, "layout.json")),
            metrics=_j(os.path.join(d, "metrics.json")),
            critique=_j(os.path.join(d, "critique.json")))})
    assert build_board(alts, shell, evidence, ctx=ctx) == open(
        os.path.join(e07, "ESCALIMETRO_PRESENTATION_STANDARD_01.svg"), encoding="utf-8").read()


def test_403_geometria_intacta_hashes_completos():
    g = _j(os.path.join(C403, "ai", "E09", "geometry_hash_check.json"))
    assert g["geometry_hash_before"]["A"] == \
        "df6b86058ebb093f449e1054a0c65a902b7492f7986f4b8395489d63d46d7b99"
    assert g["geometry_hash_before"]["B"] == \
        "5c5c276923dd7da69844ad3d409f4b879ac40c911144e4a11bf3cb4c6d8f066c"
    assert g["geometry_hash_before"]["C"] == \
        "e12cc722485b9c58251621bd6f05e92fdc8633675156e8d26f2a110d6048e4c6"
    assert all(g["geometry_hash_before"][a] == g["geometry_hash_after"][a] for a in "ABC")


def test_401_mantiene_su_evidencia_real():
    ev = FE.load(C401, PROG)
    assert ev.technical == FE.NO_FIT and ev.robustness == FE.ROBUST_NO_FIT
    assert ev.open_seats == "4/40" and ev.hard_violations == 5
    ctx = from_case_dir(C401)
    assert (ctx.unit_label, ctx.source_name, ctx.published_area_m2) == \
        ("Oficina 401", "GPS Property", 252.0)
    p = PresentationFit.from_evidence(ctx, ev)
    assert p.technical_fit == FE.NO_FIT and p.robustness == FE.ROBUST_NO_FIT
    assert "403" not in json.dumps(p.to_dict(), ensure_ascii=False)


def test_caso_generico_sin_resultados():
    d = _j(GENERIC)
    ctx = CaseContext(case_id=d["case_id"], unit_label=d["unit_label"],
                      source_name=d["source_name"], published_area_m2=d["known_area_m2"])
    p = PresentationFit.from_evidence(ctx, FE.FitEvidence())
    assert p.technical_fit == FE.TECHNICAL_NOT_EVALUATED
    assert p.robustness == FE.ROBUSTNESS_NOT_EVALUATED
    blob = json.dumps(p.to_dict(), ensure_ascii=False)
    for t in ("403", "543", "GPS", "ROBUST_FIT", "ROBUST WITHIN", "NO_FIT"):
        assert t not in blob, t
