"""E26 — guardas de LO QUE UN HUMANO VA A REVISAR.

Protegen cinco cosas y nada más: que el gate sirva para cualquier brief, que una lámina no use
evidencia de otra corrida, que cada layout tenga identidad, que quality.json exista y sea honesto, y
que la revisión humana no venga escrita por un agente.
"""
import json
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from escalimetro import fit_evidence as FE                                     # noqa: E402
from escalimetro.layout.e07.pipeline import gate_e1t                           # noqa: E402
from escalimetro.layout.e07.traceability import quality, traceability          # noqa: E402

R403 = RAIZ / "cases/001_gps_403/layouts/E26_403"
R401 = RAIZ / "cases/002_gps_401/layouts/E26_401"
ALTS = ["A", "B", "C"]


class _R:
    """Result mínimo con lo que el gate consume."""
    def __init__(self, seats, need, completo=True, viol=0, colis=0, circ=True):
        self.metrics = {"program_completeness": {"complete": completo, "open_seats": f"{seats}/{need}",
                                                 "rooms": {}},
                        "hard_constraint_violations": viol, "collisions": colis,
                        "circulation_connectivity": circ}


# ===================================================================================================
# §3 — el gate técnico sirve para CUALQUIER conteo de puestos
# ===================================================================================================
@pytest.mark.parametrize("n", [1, 7, 18, 24, 40, 56, 103])
def test_el_gate_pasa_cuando_se_entrega_exactamente_lo_pedido(n):
    """Ejecuta la función real del gate, no un regex sobre el archivo."""
    prog = {"template_id": "X", "open_workstations_exact": n}
    g = gate_e1t(_R(n, n), prog)
    assert g["status"] == "PASS", g
    assert g["open_workstations_requested"] == n
    assert g["open_workstations_delivered"] == n


@pytest.mark.parametrize("n,entregados", [(18, 17), (24, 23), (56, 48)])
def test_el_gate_falla_cuando_faltan_puestos(n, entregados):
    prog = {"template_id": "X", "open_workstations_exact": n}
    assert gate_e1t(_R(entregados, n), prog)["status"] == "FAIL"


def test_el_gate_no_esta_pinchado_a_40():
    """El brief de la 401 pide 18. Con el gate viejo (`open_seats == "40/40"`) esto era FAIL."""
    prog = {"template_id": "BRIEF_401_V1", "open_workstations_exact": 18}
    g = gate_e1t(_R(18, 18), prog)
    assert g["status"] == "PASS"
    assert not any("40" in k for k in g["checks"]), g["checks"]


# ===================================================================================================
# §4 — la evidencia de una lámina pertenece a su propia corrida
# ===================================================================================================
def test_load_acepta_run_dir_y_lo_usa_como_capa_tecnica():
    import inspect
    assert "run_dir" in inspect.signature(FE.load).parameters


@pytest.mark.parametrize("run", [R403, R401])
def test_la_corrida_declara_su_procedencia(run):
    if not run.exists():
        pytest.skip("requiere la corrida de E26")
    p = run / FE.RUN_PROVENANCE
    assert p.exists(), "sin run_provenance.json la evidencia no puede afirmarse propia"
    d = json.loads(p.read_text(encoding="utf-8"))
    for k in ("case_id", "brief_id", "out_name", "floorplate_sha256", "program_sha256",
              "engine_hash", "engine_commit", "generated_at"):
        assert d.get(k), k


def test_la_evidencia_de_403_es_de_su_corrida_y_no_dice_requiere_recalculo():
    if not R403.exists():
        pytest.skip("requiere la corrida de E26")
    prog = str(R403 / "program_compiled.json")
    ev = FE.load(str(RAIZ / "cases/001_gps_403"), prog, run_dir=str(R403))
    assert ev.freshness == FE.FRESH, (ev.freshness, ev.stale_reasons)
    assert ev.presentable
    assert all(str(R403.name) in a or "run_provenance" in a for a in ev.source_artifacts), ev.source_artifacts
    from escalimetro.case_context import from_case_dir
    fit = FE.presentation_fit(from_case_dir(str(RAIZ / "cases/001_gps_403")), ev)
    assert fit.fit_label != FE.STALE_LABEL, "la lámina no puede decir REQUIERE RECÁLCULO con evidencia propia"


def test_no_se_hereda_la_robustez_de_otra_corrida():
    """§4 — el barrido de escala de E06 se hizo con otro programa: no se adopta en silencio."""
    if not R403.exists():
        pytest.skip("requiere la corrida de E26")
    ev = FE.load(str(RAIZ / "cases/001_gps_403"), str(R403 / "program_compiled.json"), run_dir=str(R403))
    assert ev.robustness == FE.ROBUSTNESS_NOT_EVALUATED
    assert ev.robustness_note, "si no se usa la robustez ajena hay que decir por qué"
    assert not any("/E06/" in a for a in ev.source_artifacts), ev.source_artifacts


def test_sin_run_provenance_la_evidencia_es_stale_y_no_inventa_fit(tmp_path):
    caso = tmp_path / "caso"
    (caso / "outputs").mkdir(parents=True)
    (caso / "outputs" / "floorplate.json").write_text("{}", encoding="utf-8")
    run = caso / "layouts" / "X"
    (run / "alternatives" / "A").mkdir(parents=True)
    (run / "gates.json").write_text(json.dumps({"A": {"E1-T": {"status": "PASS"}}}), encoding="utf-8")
    (run / "alternatives" / "A" / "metrics.json").write_text(
        json.dumps({"program_completeness": {"complete": True, "open_seats": "18/18"}}), encoding="utf-8")
    ev = FE.load(str(caso), "", run_dir=str(run))
    assert ev.freshness == FE.STALE
    assert not ev.presentable


# ===================================================================================================
# §5 — la lámina no publica copy que el layout no demuestra
# ===================================================================================================
def test_la_lamina_no_afirma_fortalezas_estaticas():
    src = (RAIZ / "src/escalimetro/layout/e07/board.py").read_text(encoding="utf-8")
    assert "spec.strengths" not in src, "volvió la copy fija de fortalezas"
    assert "spec.ideal_for" not in src, "volvió el bloque IDEAL PARA"
    assert "MEDIDO EN ESTA PLANTA" in src


def test_el_handoff_marca_las_afirmaciones_de_intencion_como_no_verificadas():
    src = (RAIZ / "src/escalimetro/layout/e07/pipeline.py").read_text(encoding="utf-8")
    assert "strategy_intent_claims" in src
    assert '"strengths": spec.strengths,\n                        "ideal_for"' not in src


@pytest.mark.parametrize("run", [R403, R401])
def test_ninguna_lamina_generada_contiene_la_frase_falsa(run):
    if not run.exists():
        pytest.skip("requiere la corrida de E26")
    for svg in run.glob("*.svg"):
        t = svg.read_text(encoding="utf-8")
        assert "Fachada liberada para puestos" not in t, svg
        assert "IDEAL PARA" not in t, svg


# ===================================================================================================
# §6/§7 — identidad y calidad por layout
# ===================================================================================================
def _fit_alts(run):
    if not run.exists():
        return []
    return [a for a in ALTS if (run / "alternatives" / a / "metrics.json").exists()]


@pytest.mark.parametrize("run", [R403, R401])
def test_cada_layout_fit_tiene_identidad_completa(run):
    alts = _fit_alts(run)
    if not alts:
        pytest.skip("esta corrida no produjo layouts")
    for a in alts:
        t = json.loads((run / "alternatives" / a / "traceability.json").read_text(encoding="utf-8"))
        for k in ("case_id", "brief_id", "strategy", "layout_sha256", "engine_commit",
                  "brief_sha256", "generated_at"):
            assert t.get(k), (run.name, a, k)
        assert len(t["layout_sha256"]) == 64
        assert t["strategy"] == a


@pytest.mark.parametrize("run", [R403, R401])
def test_cada_layout_fit_tiene_quality_json(run):
    alts = _fit_alts(run)
    if not alts:
        pytest.skip("esta corrida no produjo layouts")
    campos = ("layout_sha256", "engine_commit", "brief_sha256", "unallocated_area_m2",
              "unallocated_pct", "residual_spaces_m2", "daylight_score", "fragmentation",
              "facade_use", "architectural_score", "circulation_pct", "waste_pct")
    for a in alts:
        q = json.loads((run / "alternatives" / a / "quality.json").read_text(encoding="utf-8"))
        for k in campos:
            assert k in q, (run.name, a, k)
        assert q["layout_sha256"] == json.loads(
            (run / "alternatives" / a / "traceability.json").read_text(encoding="utf-8"))["layout_sha256"]
        assert "NO es una evaluación arquitectónica" in q["_contract"]


def test_quality_calcula_delta_solo_contra_una_corrida_comparable():
    prov = {"case_id": "c", "brief_id": "b", "engine_commit": "x", "brief_sha256": "y",
            "generated_at": "2026-01-01T00:00:00+00:00"}
    met = {"usable_area_m2": 100.0, "unallocated_area_m2": 20.0, "circulation_area_m2": 10.0,
           "wasted_area_m2": 5.0, "daylight_score": 0.3, "net_programmed_area_m2": 65.0,
           "program_completeness": {"complete": True, "open_seats": "18/18"}}
    crit = {"scores": {"fragmentation": 0.9, "facade_use": 0.4, "residual_spaces": 0.1},
            "verdicts": {"facade_use": "50% de la fachada", "residual_spaces": "5 m²",
                         "fragmentation": "ok"}, "architectural_score": 0.7}
    sin = quality(prov, "A", "", met, crit)
    assert "delta_vs_previous" not in sin
    con = quality(prov, "A", "", met, crit, previous={**sin, "architectural_score": 0.6,
                                                     "layout_sha256": "zz"})
    assert con["delta_vs_previous"]["architectural_score"] == pytest.approx(0.1)
    assert "no dice que una planta sea mejor" in con["_delta_note"]


# ===================================================================================================
# §9 — el brief de la 401 se congeló ANTES de ejecutar
# ===================================================================================================
def test_el_brief_401_se_congelo_antes_del_primer_solve():
    import hashlib
    fr = json.loads((RAIZ / "cases/E26/BRIEF_401_V1_FREEZE.json").read_text(encoding="utf-8"))
    real = hashlib.sha256((RAIZ / "briefs/BRIEF_401_V1.json").read_bytes()).hexdigest()
    assert fr["brief_sha256"] == real, "el brief cambió después de congelarse"
    if R401.exists():
        prov = json.loads((R401 / FE.RUN_PROVENANCE).read_text(encoding="utf-8"))
        assert prov["brief_sha256"] == real
        assert fr["frozen_at"] <= prov["generated_at"], "el congelado tiene que ser anterior a la corrida"


def test_el_brief_401_no_es_el_brief_de_403():
    a = json.loads((RAIZ / "briefs/BRIEF_401_V1.json").read_text(encoding="utf-8"))
    b = json.loads((RAIZ / "briefs/BRIEF_EQUILIBRADO.json").read_text(encoding="utf-8"))
    assert a["open_workstations"] != b["open_workstations"]
    assert {r["module"] for r in a["rooms"]} != {r["module"] for r in b["rooms"]}


# ===================================================================================================
# §8 — el caso base no regresa
# ===================================================================================================
@pytest.mark.parametrize("alt", ALTS)
def test_regresion_403(alt):
    p = R403 / "alternatives" / alt / "metrics.json"
    if not p.exists():
        pytest.skip("requiere la corrida de E26")
    m = json.loads(p.read_text(encoding="utf-8"))
    pc = m["program_completeness"]
    assert pc["open_seats"] == "40/40"
    assert pc["complete"] is True
    assert m["hard_constraint_violations"] == 0
    assert m["collisions"] == 0
    assert m["circulation_connectivity"] is True


# ===================================================================================================
# §12 — NADIE prellenó la revisión humana
# ===================================================================================================
def test_no_existe_ninguna_revision_humana_prellenada_en_e26():
    """La primera revisión la hace Joaquín. Las de ciclos anteriores las escribió un agente y no
    cuentan: no se copian ni se heredan."""
    for d in (RAIZ / "cases/001_gps_403/reviews/E26", RAIZ / "cases/002_gps_401/reviews/E26"):
        if d.exists():
            assert not list(d.glob("*.json")), f"{d} ya trae revisiones: E26 no puede prellenarlas"
    best = RAIZ / "cases/E26/E26_BEST_ALTERNATIVE.json"
    assert not best.exists(), "la mejor alternativa la elige el humano"


def test_el_indice_de_revision_no_trae_grados_ni_tags():
    p = RAIZ / "review/review_index.json"
    if not p.exists():
        pytest.skip("requiere tools/e26_build_review.py")
    t = p.read_text(encoding="utf-8")
    idx = json.loads(t)
    assert idx["reason_tags"], "el índice ofrece el vocabulario de tags, que no es una evaluación"
    for c in idx["casos"]:
        for a in c["alternativas"]:
            assert "grade" not in a and "reason_tags" not in a and "free_note" not in a, a
    assert "A_GOOD" not in t and "B_CORRECTABLE" not in t and "C_BAD" not in t


def test_la_consola_no_preselecciona_ningun_grado():
    h = (RAIZ / "review/index.html").read_text(encoding="utf-8")
    assert "checked" not in h.replace(":checked", ""), "algún control viene marcado por defecto"
    assert 'if(!gsel) return;' in h, "sin grado elegido no puede generarse una revisión"


# ===================================================================================================
# §13 — la hipótesis queda registrada y NO implementada
# ===================================================================================================
def test_la_hipotesis_esta_registrada_sin_implementar():
    t = (RAIZ / "docs/ARCHITECTURAL_HYPOTHESIS_01.md").read_text(encoding="utf-8")
    assert "UNVALIDATED_BY_HUMAN_REVIEW" in t
    assert "Program-independent circulation" in t
    # y el motor sigue construyendo la espina SIN el programa
    src = (RAIZ / "src/escalimetro/layout/e05/bands.py").read_text(encoding="utf-8")
    assert "def build_spine(shell: ShellM, feats: ShellFeatures, strat: SpatialStrategy," in src
    assert "program" not in src.split("def build_spine")[1].split(")")[0], \
        "E26 no debía tocar la circulación"


# ===================================================================================================
# §11 — la consola guarda contra el contrato
# ===================================================================================================
def test_el_servidor_valida_contra_el_contrato_y_no_inventa_campos():
    src = (RAIZ / "tools/e26_review_server.py").read_text(encoding="utf-8")
    assert "human_review_v1.schema.json" in src
    assert "127.0.0.1" in src, "el servidor de revisión no se expone a la red"
    # sin autenticación, sin usuarios, sin base de datos: es una herramienta local de un solo revisor
    import re as _re
    codigo = _re.sub(r'"""[\s\S]*?"""', "", src)
    codigo = "\n".join(l for l in codigo.splitlines() if not l.strip().startswith("#"))
    for prohibido in ("password", "sqlite", "sqlalchemy", "session[", "cookie"):
        assert prohibido not in codigo.lower(), prohibido


def test_una_revision_de_ejemplo_valida_contra_el_esquema():
    jsonschema = pytest.importorskip("jsonschema")
    esquema = json.loads((RAIZ / "contracts/human_review_v1.schema.json").read_text(encoding="utf-8"))
    ejemplo = {"contract_version": "human_layout_review_v1", "case_id": "002_gps_401",
               "brief_id": "BRIEF_401_V1", "alternative": "A", "grade": "B_CORRECTABLE",
               "reason_tags": ["circulacion"], "free_note": "ejemplo de forma, no una evaluación",
               "reviewer": "TEST", "reviewed_at": "2026-09-10T12:00:00+00:00", "minutes_spent": 3}
    jsonschema.validate(ejemplo, esquema)


# ===================================================================================================
# §2 — E26 NO tocó search. Verificable, no prometido.
# ===================================================================================================
def test_e26_no_toco_search():
    """§2 lista qué está prohibido modificar. El baseline declara qué archivos cambiaron; ninguno es
    de la superficie de búsqueda."""
    base = json.loads((RAIZ / "cases/generalization/E26/GENERIC_ENGINE_BASELINE.json").read_text(encoding="utf-8"))
    d = base["diff_vs_previous"]
    assert d["search_surface_touched"] == [], d["search_surface_touched"]
    assert d["semantic_surface_touched"] == []
    assert d["removed_files"] == []
    assert d["added_files"] == ["src/escalimetro/layout/e07/traceability.py"]


def test_e26_movio_el_motor_con_baseline_declarado():
    import engine_baseline
    from escalimetro.generalization import freeze, producer_freeze, scope_guard
    base = json.loads((RAIZ / "cases/generalization/E26/GENERIC_ENGINE_BASELINE.json").read_text(encoding="utf-8"))
    eng = freeze.manifest(str(RAIZ))["engine_hash"]
    assert base["engine_hash"] == eng
    assert engine_baseline.engine_hash() == eng
    assert base["diff_vs_previous"]["previous"] == "E25"
    r = producer_freeze.read_worktree(str(RAIZ))
    assert producer_freeze.producer_hash(r) == \
        "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
    assert scope_guard.hashes(r) == {
        "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
        "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
        "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
        "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f"}
