"""E15.3 — que la procedencia no finja.

A · un `PresentationFit` construido a mano tiene el tipo correcto y ninguna procedencia: no puede
    llegar al board como veredicto vigente.
B · una `FitEvidence` que AFIRMA un resultado técnico sin artefactos que lo produzcan no es evidencia.
    `NOT_EVALUATED` es la ausencia de un resultado y no necesita procedencia.
C · el registro legado no conoce a su productor. Decir que sí lo conocía era el agujero: ahora
    distingue PRODUCTOR DESCONOCIDO de ANCLA DE COMPATIBILIDAD VERIFICADA.
D · los umbrales numéricos de confianza que E15.2 inventó (0.5 / 0.8) están fuera: la clasificación
    es la del pipeline, que ya existía."""
import json
import os
import tempfile
import types

import pytest

from escalimetro import fit_evidence as FE
from escalimetro.case_context import CaseContext, from_case_dir
from escalimetro.fit_evidence import (EvidenceWithoutProvenance, FitEvidence, PresentationFit,
                                      presentation_fit)
from escalimetro.layout.e06.scale import scaled_shell
from escalimetro.layout.e07.board import build_board
from escalimetro.layout.e07.strategies import build_alternatives
from escalimetro.layout.model import Layout, load_program
from escalimetro.schemas.floorplate import Floorplate

ROOT = os.path.dirname(os.path.dirname(__file__))
C403 = os.path.join(ROOT, "cases", "001_gps_403")
C401 = os.path.join(ROOT, "cases", "002_gps_401")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")
GENERIC = os.path.join(ROOT, "tests", "fixtures", "generalization", "TEST_GENERIC_CASE.json")
LEGACY403 = os.path.join(C403, "layouts", "EVIDENCE_LEGACY.json")
LEGACY401 = os.path.join(C401, "layouts", "EVIDENCE_LEGACY.json")


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _alts_403():
    specs = {s.alt: s for s in build_alternatives(load_program(PROG))}
    out = []
    for a in "ABC":
        d = os.path.join(C403, "layouts", "E07", "alternatives", a)
        out.append({"spec": specs[a], "result": types.SimpleNamespace(
            layout=Layout.load(os.path.join(d, "layout.json")),
            metrics=_j(os.path.join(d, "metrics.json")),
            critique=_j(os.path.join(d, "critique.json")))})
    return out


def _shell_403():
    return scaled_shell(Floorplate.load(os.path.join(C403, "outputs", "floorplate.json")), 1.0)


FORJADO = dict(unit="Oficina 403 (GPS Property)", published_area_m2=543.0, technical_fit="FIT",
               robustness="ROBUST_FIT", freshness="FRESH", fit="ROBUST_FIT",
               fit_label="ROBUST WITHIN ASSUMED SCALE RANGE", scale="UNCONFIRMED",
               scale_confidence="HIGH", headcount=40, program="programa para 48 personas",
               recommendation="—", reason="escrito a mano", note="—", source="ninguna")


def _compat(current, compatible):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    json.dump({"current_baseline": current, "compatible_with_current": list(compatible),
               "baselines": {}, "transitions": []}, open(path, "w", encoding="utf-8"))
    return path


# ---------------------------------------------------------------------------------------------------
# A · un objeto del tipo correcto no es procedencia
# ---------------------------------------------------------------------------------------------------
def test_un_presentationfit_a_mano_no_llega_al_board():
    """El agujero de E15.2: `PresentationFit(...)` es construible —es un dataclass— y tenía el tipo
    que `build_board` exigía. Un type check comprueba la forma del contenedor, no el origen."""
    ctx = from_case_dir(C403)
    forjado = PresentationFit(**FORJADO)
    assert forjado.technical_fit == "FIT" and forjado._provenance == ()   # se construye, sí
    with pytest.raises(TypeError) as e:
        build_board(_alts_403(), _shell_403(), forjado, ctx=ctx)          # pero no entra
    assert "EVIDENCIA" in str(e.value)


@pytest.mark.parametrize("falso", [
    PresentationFit(**FORJADO),
    {"technical_fit": "FIT", "fit_label": "ROBUST WITHIN ASSUMED SCALE RANGE"},
    None, "FIT", 42, types.SimpleNamespace(technical="FIT", robustness="ROBUST_FIT"),
])
def test_ninguna_forma_falsa_entra_al_board(falso):
    with pytest.raises(TypeError):
        build_board(_alts_403(), _shell_403(), falso, ctx=from_case_dir(C403))


def test_el_board_deriva_la_copy_desde_la_evidencia():
    """La copy ya no llega hecha: se construye dentro del boundary controlado."""
    ctx = from_case_dir(C403)
    svg = build_board(_alts_403(), _shell_403(), FE.load(C403, PROG), ctx=ctx)
    assert "ROBUST WITHIN" in svg and "ASSUMED SCALE RANGE" in svg


# ---------------------------------------------------------------------------------------------------
# B · una afirmación necesita evidencia; una ausencia, no
# ---------------------------------------------------------------------------------------------------
def test_fitevidence_que_afirma_fit_sin_artefactos_es_rechazada():
    ev = FitEvidence(technical=FE.FIT, robustness=FE.ROBUST_FIT, freshness=FE.FRESH,
                     source_artifacts=[])
    assert ev.has_provenance is False
    assert ev.presentable is False
    with pytest.raises(EvidenceWithoutProvenance):
        PresentationFit.from_evidence(from_case_dir(C403), ev)


@pytest.mark.parametrize("tech,rob", [(FE.FIT, FE.ROBUSTNESS_NOT_EVALUATED),
                                      (FE.NO_FIT, FE.ROBUSTNESS_NOT_EVALUATED),
                                      (FE.TECHNICAL_NOT_EVALUATED, FE.ROBUST_FIT),
                                      (FE.TECHNICAL_NOT_EVALUATED, FE.ROBUST_NO_FIT)])
def test_cualquier_afirmacion_parcial_tambien_exige_procedencia(tech, rob):
    ev = FitEvidence(technical=tech, robustness=rob, freshness=FE.FRESH, source_artifacts=[])
    assert ev.has_provenance is False
    with pytest.raises(EvidenceWithoutProvenance):
        PresentationFit.from_evidence(from_case_dir(C403), ev)


def test_not_evaluated_sin_artefactos_sigue_siendo_legitimo():
    """NOT_EVALUATED es la AUSENCIA de un resultado. Exigirle artefactos sería exigir procedencia de
    la nada, y dejaría al caso genérico sin poder decir 'no lo he evaluado'."""
    ev = FitEvidence()
    assert ev.has_provenance is True and ev.evaluated is False
    d = _j(GENERIC)
    ctx = CaseContext(case_id=d["case_id"], unit_label=d["unit_label"],
                      source_name=d["source_name"], published_area_m2=d["known_area_m2"])
    p = PresentationFit.from_evidence(ctx, ev)
    assert p.technical_fit == FE.TECHNICAL_NOT_EVALUATED
    assert p.robustness == FE.ROBUSTNESS_NOT_EVALUATED
    assert p.fit_label == FE.NOT_EVALUATED_LABEL
    blob = json.dumps(p.to_dict(), ensure_ascii=False)
    for t in ("403", "543", "GPS", "ROBUST_FIT", "ROBUST WITHIN", "NO_FIT"):
        assert t not in blob, t


def test_la_403_real_si_produce_su_veredicto():
    p = presentation_fit(from_case_dir(C403), FE.load(C403, PROG))
    assert p.technical_fit == FE.FIT and p.robustness == FE.ROBUST_FIT
    assert p.fit_label == "ROBUST WITHIN ASSUMED SCALE RANGE"
    assert len(p._provenance) == 4


def test_la_401_real_si_produce_su_veredicto():
    p = presentation_fit(from_case_dir(C401), FE.load(C401, PROG))
    assert p.technical_fit == FE.NO_FIT and p.robustness == FE.ROBUST_NO_FIT
    assert p.freshness == FE.LEGACY_VERIFIED
    assert p._provenance and "403" not in json.dumps(p.to_dict(), ensure_ascii=False)


# ---------------------------------------------------------------------------------------------------
# C · productor desconocido != ancla de compatibilidad verificada
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("path", [LEGACY403, LEGACY401])
def test_el_registro_legado_no_finge_conocer_a_su_productor(path):
    reg = _j(path)
    assert reg["producer_engine_baseline"] is None
    assert reg["producer_engine_baseline_status"] == "UNKNOWN"
    assert reg["verified_compatible_from_baseline"] == "E14"
    assert "provenance_note" in reg


@pytest.mark.parametrize("path", [LEGACY403, LEGACY401])
def test_productor_desconocido_con_ancla_valida_conserva_la_evidencia(path):
    c = _compat("E15.3", ["E14", "E15", "E15.1", "E15.2", "E15.3"])
    try:
        ok, why = FE._legacy_engine_ok(_j(path), c)
        assert ok and why == ""
    finally:
        os.unlink(c)


@pytest.mark.parametrize("path", [LEGACY403, LEGACY401])
def test_un_ancla_incompatible_vuelve_la_evidencia_stale(path):
    c = _compat("E99", ["E99"])
    try:
        ok, why = FE._legacy_engine_ok(_j(path), c)
        assert not ok and "ancla" in why
        case_dir = os.path.dirname(os.path.dirname(path))
        art = os.path.join(case_dir, "layouts", "E06", "fit_verdict.json")
        estado, razones = FE._freshness(case_dir, [art], None, PROG, c)
        assert estado == FE.STALE and razones
    finally:
        os.unlink(c)


def test_sin_productor_y_sin_ancla_no_se_asume_nada():
    reg = _j(LEGACY403)
    reg.pop("verified_compatible_from_baseline")
    c = _compat("E15.3", ["E14", "E15.3"])
    try:
        ok, why = FE._legacy_engine_ok(reg, c)
        assert not ok and "ancla" in why
    finally:
        os.unlink(c)


def test_un_productor_real_declarado_no_usa_el_ancla():
    """Los dos contratos no se colapsan: si un artefacto SÍ sabe quién lo produjo, manda eso."""
    reg = dict(_j(LEGACY403), producer_engine_baseline="E15",
               producer_engine_baseline_status="KNOWN",
               verified_compatible_from_baseline="ANCLA_QUE_NO_EXISTE")
    c = _compat("E15.3", ["E15", "E15.3"])
    try:
        assert FE._legacy_engine_ok(reg, c)[0] is True          # gana el productor real
        c2 = _compat("E15.3", ["E14", "E15.3"])                 # productor real NO compatible
        assert FE._legacy_engine_ok(reg, c2)[0] is False        # y el ancla no lo rescata
        os.unlink(c2)
    finally:
        os.unlink(c)


def test_403_y_401_siguen_legacy_verified_bajo_la_declaracion_real():
    for cd in (C403, C401):
        assert FE.load(cd, PROG).freshness == FE.LEGACY_VERIFIED


# ---------------------------------------------------------------------------------------------------
# D · los umbrales inventados salieron
# ---------------------------------------------------------------------------------------------------
def test_los_umbrales_numericos_inventados_ya_no_existen():
    """E15.2 introdujo `<0.5 LOW`, `<0.8 MEDIUM`, `HIGH`. No existían en ninguna parte del motor: un
    ciclo que no debía tocar la lógica de escala no puede definir cuándo algo pasa a MEDIUM o HIGH."""
    import ast
    from escalimetro import case_context
    src = open(os.path.join(ROOT, "src", "escalimetro", "case_context.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "_confidence_label")
    numeros = {n.value for n in ast.walk(fn)
               if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
               and not isinstance(n.value, bool)}
    assert numeros == set(), f"_confidence_label no debe tener umbrales numéricos: {numeros}"
    # y no acepta ya un número suelto: la clasificación necesita método y estado
    assert case_context._confidence_label(0.4) is None


def test_la_clasificacion_es_la_del_pipeline():
    """Misma regla que `layout/shell_adapter.py`: método y estado de la escala, no un umbral."""
    from escalimetro.case_context import _confidence_label
    assert _confidence_label({"method": "published_area_inferred",
                              "meta": {"status": "inferred"}}) == "LOW"
    assert _confidence_label({"method": "manual", "meta": {"status": "confirmed"}}) == "HIGH"
    assert _confidence_label({"method": "manual", "meta": {"status": "inferred"}}) == "MEDIUM"
    assert _confidence_label({}) is None


@pytest.mark.parametrize("case_dir", [C403, C401])
def test_la_confianza_real_sigue_siendo_low(case_dir):
    fp = _j(os.path.join(case_dir, "outputs", "floorplate.json"))
    assert fp["scale"]["method"] == "published_area_inferred"
    assert from_case_dir(case_dir).scale_confidence == "LOW"


def test_el_vocabulario_lo_fija_el_esquema_existente():
    from escalimetro.layout.e06.scale import SCENARIO_SCHEMA
    assert SCENARIO_SCHEMA["properties"]["confidence"]["enum"] == ["LOW", "MEDIUM", "HIGH"]


# ---------------------------------------------------------------------------------------------------
# regresiones duras
# ---------------------------------------------------------------------------------------------------
def test_403_lamina_byte_identica():
    svg = build_board(_alts_403(), _shell_403(), FE.load(C403, PROG), ctx=from_case_dir(C403))
    assert svg == open(os.path.join(C403, "layouts", "E07",
                                    "ESCALIMETRO_PRESENTATION_STANDARD_01.svg"),
                       encoding="utf-8").read()


def test_403_geometria_intacta_hashes_completos():
    g = _j(os.path.join(C403, "ai", "E09", "geometry_hash_check.json"))
    assert g["geometry_hash_before"]["A"] == \
        "df6b86058ebb093f449e1054a0c65a902b7492f7986f4b8395489d63d46d7b99"
    assert g["geometry_hash_before"]["B"] == \
        "5c5c276923dd7da69844ad3d409f4b879ac40c911144e4a11bf3cb4c6d8f066c"
    assert g["geometry_hash_before"]["C"] == \
        "e12cc722485b9c58251621bd6f05e92fdc8633675156e8d26f2a110d6048e4c6"
    assert all(g["geometry_hash_before"][a] == g["geometry_hash_after"][a] for a in "ABC")


def test_401_conserva_sus_hechos_y_su_evidencia():
    ctx = from_case_dir(C401)
    assert (ctx.unit_label, ctx.source_name, ctx.published_area_m2) == \
           ("Oficina 401", "GPS Property", 252.0)
    ev = FE.load(C401, PROG)
    assert (ev.technical, ev.robustness, ev.freshness) == (FE.NO_FIT, FE.ROBUST_NO_FIT,
                                                           FE.LEGACY_VERIFIED)
    assert ev.open_seats == "4/40" and ev.hard_violations == 5
