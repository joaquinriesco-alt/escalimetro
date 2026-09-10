"""E24 — guardas del BRIEF y de la ACEPTACIÓN DE SHELL.

Lo que estos tests prueban, y lo que deliberadamente no:

  SÍ   que el brief GOBIERNA: que quitar los hardcodes no dejó otro camino por donde el 40 vuelva.
  SÍ   que los tres briefs producen tres programas distintos (§18: si los tres resuelven el programa
       histórico, E24 es FAIL).
  SÍ   que `not_layout_dominated` depende ÚNICAMENTE del hecho declarado (§12).
  SÍ   que una escala confirmada por dos puntos se puede REPRODUCIR desde los datos guardados (§14).
  NO   que los layouts sean bonitos. La calidad arquitectónica se CALIFICA en E24 (§19) y se corrige
       en E25; ningún test verde la sustituye.
"""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from escalimetro.brief import (BriefV1, BriefError, apportion, brief_from_legacy_program,   # noqa: E402
                               compile_program, load_brief, program_rows, program_kpis,
                               total_rooms, DEFAULT_POLICY)
from escalimetro.generalization import freeze, producer_freeze, scope_guard                 # noqa: E402
from escalimetro.layout.model import load_modules                                           # noqa: E402
from escalimetro.layout.program_access import ProgramContractError, open_workstations       # noqa: E402
from escalimetro.shell_input import (INPUT_NOT_READY, SHELL_ACCEPTED, ScaleConfirmation,    # noqa: E402
                                     USER_CONFIRMED_DISTANCE, evaluate)

# --- congelados de E24 -----------------------------------------------------------------------------
BRIEF_SHA = {
    "BRIEF_DENSO":       "f4daa2a96c42fc49c72f603fd35d73f5f7d87a8c769b95d3d902ce2af6e1d057",
    "BRIEF_EQUILIBRADO": "f6174547ac8f7dabe3e402a07f653f7644672892354ee083713c72f7a76628af",
    "BRIEF_EJECUTIVO":   "d5a71c337ef9ed2de59e2b353a949bfb88feef91d35a94f7430b62e24841beb6",
}
# E24 TOCA EL MOTOR a propósito (§6): el ENGINE_HASH se mueve y se declara aquí.
ENGINE_E23 = "779a1eee6d3d2f2ce4fcc185dbf08da8890768e49a64211770eb1ee800a8105c"
ENGINE_E24 = "ea55d67374535121306fc201ceccc1d11ec7107ee55b70bec7ebf3b176c1f214"
# El PRODUCTOR semántico y el SCOPE no se tocan: E24 es brief + aceptación, no semántica.
PRODUCER = "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
SCOPE = {
    "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
    "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
    "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
    "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f",
}
BRIEFS = ["BRIEF_DENSO", "BRIEF_EQUILIBRADO", "BRIEF_EJECUTIVO"]
SRC = RAIZ / "src"


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def mods():
    m, _ = load_modules(str(RAIZ / "program_templates/modules_office.json"))
    return m


# ===================================================================================================
# 1 — los briefs están congelados y son consistentes
# ===================================================================================================
@pytest.mark.parametrize("b", BRIEFS)
def test_los_briefs_estan_congelados(b):
    assert _sha(RAIZ / f"briefs/{b}.json") == BRIEF_SHA[b], (
        "los números de los tres briefs se fijaron ANTES de correr layouts (§8). Si este test cae, "
        "alguien los movió después de ver resultados.")


@pytest.mark.parametrize("b", BRIEFS)
def test_cada_brief_es_consistente_consigo_mismo(b, mods):
    br = load_brief(str(RAIZ / f"briefs/{b}.json"))
    assert br.validate(mods) == []
    assert br.target_headcount >= br.permanent_seats(mods)


@pytest.mark.parametrize("b", BRIEFS)
def test_el_brief_no_declara_politica_de_diseno(b):
    """§3/§5 — el cliente no controla pesos, zonificación, adyacencias ni estrategia."""
    d = json.loads((RAIZ / f"briefs/{b}.json").read_text(encoding="utf-8"))
    prohibidos = {"objectives_weights", "objective_weights", "zoning_rules", "solver_extra",
                  "weights", "adjacency", "strategies", "corridor_width_m", "spine_strategy",
                  "room_positions", "bench_cfgs"}
    assert not (set(d) & prohibidos), sorted(set(d) & prohibidos)
    with pytest.raises(BriefError):
        BriefV1.from_dict({**d, "objectives_weights": {"x": 1.0}})


def test_el_brief_no_puede_declarar_clusters_de_puestos():
    """Los clusters son geometría derivada de `open_workstations`, no programa del cliente."""
    d = json.loads((RAIZ / "briefs/BRIEF_EQUILIBRADO.json").read_text(encoding="utf-8"))
    d["rooms"] = d["rooms"] + [{"module": "workstation_cluster", "count": 7}]
    with pytest.raises(BriefError):
        BriefV1.from_dict(d).require_valid()


def test_headcount_menor_que_los_puestos_declarados_es_brief_inconsistente(mods):
    br = BriefV1("X", 10, 40, [{"module": "private_office", "count": 4}])
    errs = br.validate(mods)
    assert any("target_headcount" in e for e in errs), errs
    with pytest.raises(BriefError):
        compile_program(br, modules=mods)


# ===================================================================================================
# 2 — semántica auditada en docs/E24_PROGRAM_SEMANTICS_AUDIT.md
# ===================================================================================================
def test_los_asientos_de_sala_no_son_headcount_permanente(mods):
    """§4 — el error que E24 prohíbe cometer. meeting_8 aporta 8 asientos y CERO puestos."""
    br = load_brief(str(RAIZ / "briefs/BRIEF_EQUILIBRADO.json"))
    s = br.summary(mods)
    assert s["permanent_seats"] == 45          # 40 open + 4 privados + 1 recepción
    assert s["meeting_seats"] == 32            # 3×4 + 8 + 12
    assert s["permanent_seats"] + s["meeting_seats"] != s["permanent_seats"]
    mas_salas = BriefV1(br.brief_id, br.target_headcount, br.open_workstations,
                        [dict(r) for r in br.rooms if r["module"] != "meeting_8"] +
                        [{"module": "meeting_8", "count": 5}])
    assert mas_salas.permanent_seats(mods) == s["permanent_seats"], (
        "agregar salas NO puede cambiar los puestos permanentes")
    assert mas_salas.meeting_seats(mods) > s["meeting_seats"]


def test_target_headcount_no_es_una_restriccion_del_solver(mods):
    """§4 — cambiar el headcount declarado no cambia una sola entrada del motor."""
    br = load_brief(str(RAIZ / "briefs/BRIEF_EQUILIBRADO.json"))
    a = compile_program(br, modules=mods)
    b = compile_program(BriefV1(br.brief_id, br.target_headcount + 20, br.open_workstations, br.rooms),
                        modules=mods)
    for k in ("program", "open_workstations_exact", "objectives_weights"):
        assert a[k] == b[k], k


def test_el_unseated_headcount_se_reporta_y_no_se_rellena(mods):
    br = load_brief(str(RAIZ / "briefs/BRIEF_EQUILIBRADO.json"))
    assert br.unseated_headcount(mods) == 3
    assert compile_program(br, modules=mods)["open_workstations_exact"] == 40


# ===================================================================================================
# 3 — §7 reparto entero, sin tablas por tamaño
# ===================================================================================================
@pytest.mark.parametrize("total", list(range(0, 121)))
@pytest.mark.parametrize("alt", ["A", "B", "C"])
def test_el_reparto_suma_exactamente_el_total(total, alt):
    s = apportion(total, DEFAULT_POLICY.proportions_for(alt))
    assert sum(s) == total
    assert all(x >= 0 for x in s)
    assert len(s) == len(DEFAULT_POLICY.proportions_for(alt))


def test_el_reparto_reproduce_la_intencion_historica():
    """Con 40 puestos, las proporciones dan EXACTAMENTE los splits que estaban escritos a mano."""
    assert apportion(40, DEFAULT_POLICY.proportions_for("A")) == [24, 16]
    assert apportion(40, DEFAULT_POLICY.proportions_for("B")) == [16, 14, 10]
    assert apportion(40, DEFAULT_POLICY.proportions_for("C")) == [12, 10, 10, 8]


def test_el_reparto_conserva_el_orden_relativo_de_la_intencion():
    for alt in "ABC":
        props = DEFAULT_POLICY.proportions_for(alt)
        for n in (24, 40, 56, 80):
            s = apportion(n, props)
            assert sorted(s, reverse=True) == s, (alt, n, s)


def test_el_reparto_es_determinista():
    for n in (23, 41, 57):
        for alt in "ABC":
            p = DEFAULT_POLICY.proportions_for(alt)
            assert apportion(n, p) == apportion(n, p)


# ===================================================================================================
# 4 — §9/§18 el brief histórico no se rompe y los tres briefs NO son el mismo programa
# ===================================================================================================
def test_el_brief_equilibrado_reproduce_el_programa_historico_semanticamente(mods):
    """Adenda §5 — semánticamente, no byte a byte."""
    legacy = json.loads((RAIZ / "program_templates/office_balanced_48.json").read_text(encoding="utf-8"))
    hist = brief_from_legacy_program(legacy, "BRIEF_EQUILIBRADO")
    nuevo = load_brief(str(RAIZ / "briefs/BRIEF_EQUILIBRADO.json"))
    assert hist.to_dict() == nuevo.to_dict()
    p = compile_program(nuevo, modules=mods)
    assert p["open_workstations_exact"] == legacy["open_workstations_exact"] == 40
    assert p["target_headcount"] == legacy["target_headcount"] == 48
    # semánticamente, no byte a byte (adenda §5): el template traía además una `note` en prosa
    assert [(e["module"], e["count"]) for e in p["program"]] == \
           [(e["module"], e["count"]) for e in legacy["program"]]
    assert p["objectives_weights"] == legacy["objectives_weights"]
    assert total_rooms(p) == 16
    assert DEFAULT_POLICY.zoning_rules() == {k: sorted(v) for k, v in legacy["zoning_rules"].items()}


def test_los_tres_briefs_son_tres_programas_distintos(mods):
    """§18 — si los tres terminan resolviendo el mismo programa de 40 puestos, E24 es FAIL."""
    progs = {b: compile_program(load_brief(str(RAIZ / f"briefs/{b}.json")), modules=mods) for b in BRIEFS}
    needs = {b: p["open_workstations_exact"] for b, p in progs.items()}
    assert len(set(needs.values())) == 3, needs
    assert len({total_rooms(p) for p in progs.values()}) == 3
    firmas = {b: hashlib.sha256(json.dumps(p["program"], sort_keys=True).encode()).hexdigest()
              for b, p in progs.items()}
    assert len(set(firmas.values())) == 3, firmas
    splits = {b: [load_brief(str(RAIZ / f"briefs/{b}.json")).neighborhood_seats(a) for a in "ABC"]
              for b in BRIEFS}
    assert len({json.dumps(v) for v in splits.values()}) == 3, splits


# ===================================================================================================
# 5 — §6 los hardcodes del brief histórico ya no están en el runtime
# ===================================================================================================
DEFAULT_40 = re.compile(r"""\.get\(\s*["']open_workstations_exact["']\s*,\s*\d+""")


def test_no_queda_ningun_default_de_40_puestos_en_el_motor():
    """El patrón es la LLAMADA con default, no la palabra: un docstring que explique el problema
    no es el problema."""
    for py in SRC.rglob("*.py"):
        m = DEFAULT_40.search(py.read_text(encoding="utf-8"))
        assert m is None, f"{py}: {m.group(0)}"


def test_el_motor_se_niega_a_correr_sin_puestos_declarados():
    with pytest.raises(ProgramContractError):
        open_workstations({"program": []})
    assert open_workstations({"open_workstations_exact": 56}) == 56


def test_las_laminas_ya_no_escriben_el_programa_a_mano():
    for rel in ("layout/e07/board.py", "validation/boards.py", "ai/board02.py"):
        t = (SRC / "escalimetro" / rel).read_text(encoding="utf-8")
        assert 'PROGRAM_ROWS = [("Puestos open space", "40")' not in t, rel
        assert '("40", "puestos")' not in t, rel
        assert '("16", "recintos")' not in t, rel
        assert '("Puestos open", "40 / 40")' not in t, rel


def test_las_filas_de_programa_se_derivan_del_brief(mods):
    eq = compile_program(load_brief(str(RAIZ / "briefs/BRIEF_EQUILIBRADO.json")), modules=mods)
    ej = compile_program(load_brief(str(RAIZ / "briefs/BRIEF_EJECUTIVO.json")), modules=mods)
    assert program_rows(eq)[0] == ("Puestos open space", "40")
    assert program_rows(ej)[0] == ("Puestos open space", "24")
    assert dict(program_rows(eq))["Oficinas privadas"] == "4"
    assert dict(program_rows(ej))["Oficinas privadas"] == "8"
    assert program_kpis(eq) == [("40", "puestos"), ("16", "recintos")]
    assert program_kpis(ej) == [("24", "puestos"), ("22", "recintos")]


def test_los_splits_de_barrios_ya_no_son_tablas_escritas_a_mano():
    t = (SRC / "escalimetro/layout/e07/strategies.py").read_text(encoding="utf-8")
    for tabla in ("[24, 16]", "[16, 14, 10]", "[12, 10, 10, 8]"):
        assert f"program_nodes(program, {len(tabla)}" not in t
        assert f", {tabla})" not in t, tabla
    assert "seats_total = 40" not in (SRC / "escalimetro/layout/e05/strategy.py").read_text(encoding="utf-8")


def test_lo_que_NO_se_borro_sigue_en_pie():
    """§6 — taxonomía, etiquetas y reglas arquitectónicas NO son hardcodes del brief."""
    from escalimetro.layout.render import LABELS, COMMERCIAL_FILL
    from escalimetro.layout.zoning import ZONE_OF_MODULE
    assert LABELS["private_office"] == "Oficina privada"
    assert COMMERCIAL_FILL["meeting_8"]
    assert ZONE_OF_MODULE["reception"] == "PUBLIC"
    assert DEFAULT_POLICY.zoning_rules()["WORK"] == ["private_office", "workstation_cluster"]


# ===================================================================================================
# 6 — §11-§14 ShellInputV1
# ===================================================================================================
CASOS = {"cases/001_gps_403": SHELL_ACCEPTED,
         "cases/002_gps_401": SHELL_ACCEPTED,
         "cases/003_res_unknown": INPUT_NOT_READY}


@pytest.mark.parametrize("case,esperado", sorted(CASOS.items()))
def test_los_veredictos_de_aceptacion(case, esperado):
    """§15 — expectativas PRE-DECLARADAS en el prompt, antes de implementar."""
    assert evaluate(str(RAIZ / case)).verdict == esperado


def test_el_artefacto_valida_contra_el_contrato_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((RAIZ / "contracts/shell_input_v1.schema.json").read_text(encoding="utf-8"))
    for c in CASOS:
        jsonschema.validate(evaluate(str(RAIZ / c)).to_dict(), schema)


def test_not_layout_dominated_depende_SOLO_del_hecho_declarado():
    """§12 — el mismo dibujo, tres declaraciones, tres respuestas. Nada mira la imagen."""
    case = json.loads((RAIZ / "cases/001_gps_403/case.json").read_text(encoding="utf-8"))
    got = {}
    for v in (True, False, "unknown"):
        r = evaluate(str(RAIZ / "cases/001_gps_403"), case={**case, "shell_declared_clean": v})
        got[str(v)] = (r.status("not_layout_dominated"), r.verdict)
    assert got["True"] == ("PASS", SHELL_ACCEPTED)
    assert got["False"] == ("FAIL", INPUT_NOT_READY)
    assert got["unknown"] == ("NEEDS_HITL", SHELL_ACCEPTED)


def test_la_aceptacion_no_importa_ni_IA_ni_VLM_ni_semantic_hint():
    """La prohibición se prueba leyendo el árbol de imports, no confiando en la prosa."""
    prohibidos = ("semantic_hint", "vlm", "openai", "anthropic", "providers", "reviewers",
                  "orchestrator", "area_semantics", "cv2")
    for py in (SRC / "escalimetro/shell_input").rglob("*.py"):
        arbol = ast.parse(py.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            mods_ = []
            if isinstance(n, ast.Import):
                mods_ = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                mods_ = [n.module or ""]
            for m in mods_:
                assert not any(p in m.lower() for p in prohibidos), (py.name, m)


def test_res_no_esta_listo_por_DOS_razones_independientes():
    r = evaluate(str(RAIZ / "cases/003_res_unknown"))
    assert r.status("not_layout_dominated") == "FAIL"
    assert r.status("scale_consumable") == "FAIL"
    assert r.evidence["px_per_m"] is None
    assert r.evidence["scale_semantic_validity"] == "SCALE_INCOMPATIBLE_REGION"
    assert r.verdict == INPUT_NOT_READY, "INPUT_NOT_READY manda sobre SCALE_UNRESOLVED (precedencia §11)"


def test_needs_hitl_nunca_bloquea():
    r = evaluate(str(RAIZ / "cases/001_gps_403"))
    assert "NEEDS_HITL" in {c["status"] for c in r.checks.values()}
    assert r.verdict == SHELL_ACCEPTED
    assert r.hitl_required and all(h in ("perimeter", "scale", "entrance", "fixed_elements")
                                   for h in r.hitl_required)


# ---- §14 escala confirmada -------------------------------------------------------------------------
def test_la_escala_confirmada_por_dos_puntos_es_reproducible():
    c = ScaleConfirmation.from_two_points([100.0, 100.0], [100.0, 183.5652], 10.0)
    assert c.provenance == USER_CONFIRMED_DISTANCE
    d = c.to_dict()
    import math
    px = math.dist(tuple(d["point_a_px"]), tuple(d["point_b_px"])) / d["real_distance_m"]
    assert abs(px - d["px_per_m"]) < 1e-6, "los datos crudos deben permitir recomputar la escala"


def test_una_escala_confirmada_convierte_el_check_en_PASS():
    case = json.loads((RAIZ / "cases/001_gps_403/case.json").read_text(encoding="utf-8"))
    case["scale_confirmation"] = {"method": "two_point_distance", "point_a_px": [321.0, 238.5],
                                  "point_b_px": [321.0, 378.0], "real_distance_m": 16.7}
    r = evaluate(str(RAIZ / "cases/001_gps_403"), case=case)
    assert r.status("scale_consumable") == "PASS"
    assert r.evidence["scale_provenance"] == USER_CONFIRMED_DISTANCE
    assert "scale" not in r.hitl_required or r.status("area_consistent") == "NEEDS_HITL"


def test_la_via_secundaria_se_distingue_de_la_primaria():
    a = ScaleConfirmation.from_px_per_m(8.3565)
    assert a.provenance == "USER_DECLARED_PX_PER_M" != USER_CONFIRMED_DISTANCE
    assert a.point_a_px is None and "no es reproducible" in a.note


def test_ningun_caso_real_declara_una_escala_confirmada_todavia():
    """E24 implementa el mecanismo; NO inventa una medición que nadie tomó."""
    for c in CASOS:
        case = json.loads((RAIZ / c / "case.json").read_text(encoding="utf-8"))
        assert case.get("scale_confirmation") is None, c


def test_shell_declared_clean_es_campo_de_entrada_del_caso():
    from escalimetro.case_context import CASE_INPUT_FIELDS, DERIVED_EVIDENCE_FIELDS
    assert "shell_declared_clean" in CASE_INPUT_FIELDS
    assert "scale_confirmation" in CASE_INPUT_FIELDS
    assert "shell_declared_clean" not in DERIVED_EVIDENCE_FIELDS


# ===================================================================================================
# 7 — §21 la falsa protección de los hashes A/B/C
# ===================================================================================================
def test_los_hashes_ABC_se_recomputan_desde_la_geometria_guardada():
    """Antes se comparaban DOS JSON congelados entre sí: verde aunque el solver cambiara.
    Ahora el hash se vuelve a calcular desde layout.json + el shell del caso."""
    from escalimetro.ai.geometry_guard import geometry_hash
    from escalimetro.case_context import from_case_dir
    from escalimetro.layout.e06.scale import scaled_shell
    from escalimetro.layout.model import Layout
    from escalimetro.schemas.floorplate import Floorplate
    C = RAIZ / "cases/001_gps_403"
    exp = json.loads((C / "ai/E09/EXPECTED_GEOMETRY_HASHES.json").read_text(encoding="utf-8"))["full_hashes"]
    ctx = from_case_dir(str(C))
    shell = scaled_shell(Floorplate.load(ctx.require_floorplate()), 1.0)
    for a in "ABC":
        lay = Layout.load(str(C / f"layouts/E07/alternatives/{a}/layout.json"))
        assert geometry_hash(lay, shell) == exp[a], a


# ===================================================================================================
# 8 — alcance: qué movió E24 y qué no
# ===================================================================================================
def test_e24_movio_el_motor_a_proposito_y_nada_mas():
    r = producer_freeze.read_worktree(str(RAIZ))
    eng = freeze.manifest(str(RAIZ))["engine_hash"]
    assert eng != ENGINE_E23, "E24 §6 exige tocar el motor: si el hash no se movió, no se quitó nada"
    assert eng == ENGINE_E24
    base = json.loads((RAIZ / "cases/generalization/E24/GENERIC_ENGINE_BASELINE.json").read_text(encoding="utf-8"))
    assert base["engine_hash"] == eng, "el motor cambió sin actualizar el baseline declarado de E24"
    assert base["diff_vs_previous"]["previous_engine_hash"] == ENGINE_E23
    assert producer_freeze.producer_hash(r) == PRODUCER, "E24 no toca el productor semántico"
    assert scope_guard.hashes(r) == SCOPE, "E24 no toca contrato/wall evidence/semantic hint/downstream"


def test_e24_no_toca_la_superficie_semantica():
    """El baseline declara qué archivos cambiaron. Ninguno es de la capa semántica: E24 es brief +
    aceptación, no interpretación de dibujos."""
    base = json.loads((RAIZ / "cases/generalization/E24/GENERIC_ENGINE_BASELINE.json").read_text(encoding="utf-8"))
    d = base["diff_vs_previous"]
    assert d["semantic_surface_touched"] == [], d["semantic_surface_touched"]
    assert d["removed_files"] == []
    assert set(d["added_files"]) >= {"src/escalimetro/brief/brief_v1.py",
                                     "src/escalimetro/shell_input/shell_input_v1.py",
                                     "src/escalimetro/layout/program_access.py"}


def test_e24_no_reabre_la_limpieza_de_planos():
    """§26 — si la aceptación empezara a limpiar planos, sería V1 SCOPE VIOLATION."""
    doc = (RAIZ / "docs/PLAN_CLEANING_DEFERRED.md").read_text(encoding="utf-8")
    assert "DEFERRED AFTER MVP V1" in doc
    txt = "\n".join(p.read_text(encoding="utf-8") for p in (SRC / "escalimetro/shell_input").rglob("*.py"))
    for prohibido in ("inpaint", "erase_furniture", "remove_furniture", "limpiar_mobiliario",
                      "declutter", "cv2."):
        assert prohibido not in txt, prohibido
