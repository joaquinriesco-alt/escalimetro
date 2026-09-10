"""E25 — guardas de HONESTIDAD DEL SEARCH.

Lo que protegen, en una línea: que el motor no vuelva a llamar "no cabe" a "no lo encontré".
"""
import ast
import json
import os
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from escalimetro.brief import compile_program, load_brief, BriefV1                    # noqa: E402
from escalimetro.layout.e06 import freeplace as F                                     # noqa: E402
from escalimetro.layout.search_status import (CandidateSpace, FIT, PROVEN_INFEASIBLE,  # noqa: E402
                                              SEARCH_EXHAUSTED, STATUSES,
                                              TIMEOUT_NO_SOLUTION, TIMEOUT_WITH_INCUMBENT,
                                              classify, explicacion, puede_decir_que_no_cabe)
from escalimetro.layout.model import load_modules                                     # noqa: E402

SRC = RAIZ / "src"
BRIEFS = ["BRIEF_DENSO", "BRIEF_EQUILIBRADO", "BRIEF_EJECUTIVO"]


@pytest.fixture(scope="module")
def mods():
    m, _ = load_modules(str(RAIZ / "program_templates/modules_office.json"))
    return m


# ===================================================================================================
# 1 — §8 semántica de estados
# ===================================================================================================
INCOMPLETO = CandidateSpace(sampled_positions=True, dominance_pruned=True, capped=True, step_m=1.0, cap=200)
COMPLETO = CandidateSpace(sampled_positions=False, dominance_pruned=False, capped=False)


def test_un_espacio_incompleto_NUNCA_produce_proven_infeasible():
    """El error exacto que E25 corrige. CP-SAT dice INFEASIBLE sobre el modelo que recibió; si ese
    modelo se construyó con candidatos podados, no prueba nada sobre el problema real."""
    assert classify("INFEASIBLE", False, INCOMPLETO) == SEARCH_EXHAUSTED
    assert classify("INFEASIBLE_MODEL", False, INCOMPLETO) == SEARCH_EXHAUSTED
    assert classify("INFEASIBLE", False, COMPLETO) == PROVEN_INFEASIBLE


def test_timeout_no_es_infactibilidad():
    assert classify("UNKNOWN", False, INCOMPLETO) == TIMEOUT_NO_SOLUTION
    assert classify("UNKNOWN", False, COMPLETO) == TIMEOUT_NO_SOLUTION
    assert not puede_decir_que_no_cabe(TIMEOUT_NO_SOLUTION)


def test_con_solucion_hay_FIT_o_incumbente():
    assert classify("OPTIMAL", True, INCOMPLETO, optimality_proven=True) == FIT
    assert classify("FEASIBLE", True, INCOMPLETO) == TIMEOUT_WITH_INCUMBENT


def test_solo_proven_infeasible_autoriza_decir_que_no_cabe():
    permitidos = {s for s in STATUSES if puede_decir_que_no_cabe(s)}
    assert permitidos == {PROVEN_INFEASIBLE}


def test_cada_estado_tiene_explicacion_y_ninguna_miente():
    for s in STATUSES:
        t = explicacion(s, INCOMPLETO).lower()
        if not puede_decir_que_no_cabe(s):
            assert "no cabe" not in t or "no es una demostración de que no quepa" in t, (s, t)


def test_el_espacio_de_candidatos_de_v1_es_incompleto_por_construccion():
    """Si algún día alguien marca el espacio como completo, tiene que ser una decisión explícita."""
    from escalimetro.layout.e07.engine import Engine
    src = (SRC / "escalimetro/layout/e07/engine.py").read_text(encoding="utf-8")
    assert "CandidateSpace(sampled_positions=True" in src
    assert "dominance_pruned=True" in src and "capped=True" in src
    assert not INCOMPLETO.complete


# ===================================================================================================
# 2 — §11 la poda ya no destruye la diversidad de tamaños (D1)
# ===================================================================================================
class _C:
    """Candidato mínimo con la interfaz que usa `prune`."""
    def __init__(self, cid, module, rect, rot=0, touches=("e0",), daylight=1.0, path=1.0):
        self.cid, self.module, self.rect, self.rot = cid, module, rect, rot
        self.touches, self.daylight_m, self.path_m = list(touches), daylight, path


def test_la_poda_conserva_tamanos_distintos_en_la_misma_celda():
    """D1 — un bench 2×6 y uno 2×2 anclados en el mismo punto son alternativas DISTINTAS."""
    c = [_C(0, "workstation_cluster", (0.0, 0.0, 9.6, 3.2)),      # 2×6
         _C(1, "workstation_cluster", (0.0, 0.0, 3.2, 3.2)),      # 2×2
         _C(2, "workstation_cluster", (0.0, 0.0, 6.4, 3.2))]      # 2×4
    out = F.prune(c, per_module_cap=1000)
    assert len(out) == 3, "la poda volvió a colapsar tamaños distintos"


def test_la_poda_sigue_colapsando_duplicados_de_la_misma_huella():
    c = [_C(0, "meeting_4", (0.0, 0.0, 3.5, 3.0), daylight=1.0, path=1.0),
         _C(1, "meeting_4", (0.1, 0.1, 3.6, 3.1), daylight=5.0, path=5.0)]
    assert len(F.prune(c, per_module_cap=1000)) == 1


# ===================================================================================================
# 3 — §11 el tope escala con la demanda (D2)
# ===================================================================================================
def test_el_tope_escala_con_las_instancias_pedidas():
    c = [_C(i, "private_office", (i * 3.0, 0.0, i * 3.0 + 4.0, 3.0)) for i in range(600)]
    pocos = F.prune(list(c), per_module_cap=200, demand={"private_office": 1})
    muchos = F.prune(list(c), per_module_cap=200, demand={"private_office": 8})
    assert len(pocos) == 200
    assert len(muchos) > len(pocos), "8 instancias reciben el mismo pool que 1"
    assert len(muchos) == min(600, max(200, 80 * 8))


def test_sin_demanda_el_comportamiento_es_el_tope_base():
    c = [_C(i, "meeting_4", (i * 4.0, 0.0, i * 4.0 + 3.5, 3.0)) for i in range(500)]
    assert len(F.prune(c, per_module_cap=200)) == 200


# ===================================================================================================
# 4 — §11 cobertura mínima por instancia (D3)
# ===================================================================================================
def test_el_generador_declara_su_piso_de_cobertura():
    assert F.MIN_CANDIDATOS_POR_INSTANCIA >= 1
    assert F.MAX_REFINAMIENTOS >= 1
    assert 0 < F.STEP_MINIMO < 1.0


# ===================================================================================================
# 5 — §11 PROHIBIDO: ramas específicas por brief
# ===================================================================================================
LITERALES_DE_BRIEF = [
    re.compile(r'brief_id\s*==\s*["\']'),
    re.compile(r'template_id\s*==\s*["\']'),
    re.compile(r'\bDENSO\b'), re.compile(r'\bEJECUTIVO\b'), re.compile(r'\bEQUILIBRADO\b'),
    re.compile(r'open_workstations\s*==\s*\d+'),
    re.compile(r'private_office_count\s*==\s*\d+'),
    re.compile(r'\bin\s*\(\s*24\s*,\s*40\s*,\s*56\s*\)'),
]


def test_el_runtime_no_tiene_ninguna_rama_ligada_a_los_briefs_de_e24():
    """§11 — la generalidad se comprueba leyendo el código, no confiando en la prosa."""
    ofensas = []
    for py in SRC.rglob("*.py"):
        t = py.read_text(encoding="utf-8")
        for pat in LITERALES_DE_BRIEF:
            for m in pat.finditer(t):
                ofensas.append(f"{py.relative_to(RAIZ)}: {m.group(0)!r}")
    assert not ofensas, ofensas


def test_el_runtime_no_ramifica_por_cantidades_concretas_de_puestos():
    """Un `if` cuyo test compara con 24/40/56 sería un hack disfrazado."""
    sospechosos = []
    for py in SRC.rglob("*.py"):
        arbol = ast.parse(py.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if not isinstance(n, ast.If):
                continue
            for c in ast.walk(n.test):
                if isinstance(c, ast.Constant) and isinstance(c.value, int) and c.value in (24, 40, 56, 8):
                    for name in ast.walk(n.test):
                        if isinstance(name, ast.Name) and "workstation" in name.id.lower():
                            sospechosos.append(f"{py.relative_to(RAIZ)}:{n.lineno}")
    assert not sospechosos, sospechosos


# ===================================================================================================
# 6 — §22 conteos arbitrarios: el brief no tiene que parecerse a ninguno de los tres
# ===================================================================================================
@pytest.mark.parametrize("n", [1, 7, 13, 24, 31, 40, 56, 77, 100])
def test_cualquier_numero_de_puestos_compila_y_reparte_exacto(n, mods):
    b = BriefV1("ARBITRARIO", max(n + 5, n), n, [{"module": "reception", "count": 1}])
    p = compile_program(b, modules=mods)
    assert p["open_workstations_exact"] == n
    for alt in "ABC":
        s = b.neighborhood_seats(alt)
        assert sum(s) == n


@pytest.mark.parametrize("privados", [0, 1, 5, 8, 12, 20])
def test_cualquier_cantidad_de_recintos_compila(privados, mods):
    b = BriefV1("ARBITRARIO", 60, 20,
                [{"module": "private_office", "count": privados}, {"module": "reception", "count": 1}])
    p = compile_program(b, modules=mods)
    got = {q["module"]: q["count"] for q in p["program"]}
    assert got.get("private_office", 0) == privados


# ===================================================================================================
# 7 — §9 DETERMINISTIC_DEV_MODE
# ===================================================================================================
def test_el_modo_determinista_existe_y_declara_lo_que_cambia():
    src = (SRC / "escalimetro/layout/e06/freeplace.py").read_text(encoding="utf-8")
    assert "ESCALIMETRO_DETERMINISTIC" in src
    assert "num_search_workers = 1" in src
    assert "max_deterministic_time" in src
    assert "randomize_search = False" in src


def test_el_modo_determinista_no_es_el_default():
    """§9 — es un modo de desarrollo; no se convierte solo en configuración productiva."""
    src = (SRC / "escalimetro/layout/e06/freeplace.py").read_text(encoding="utf-8")
    assert 'os.environ.get("ESCALIMETRO_DETERMINISTIC", "") == "1"' in src
    assert "deterministic: Optional[bool] = None" in src


def test_el_modo_determinista_apaga_el_corte_por_tiempo_de_pared():
    src = (SRC / "escalimetro/layout/e06/freeplace.py").read_text(encoding="utf-8")
    assert 'early = 0.0 if det else float(extra.get("early_stop_after_s", 0) or 0)' in src


# ===================================================================================================
# 8 — §14 regresión dura del brief base
# ===================================================================================================
BASE = RAIZ / "cases/001_gps_403/layouts/E25_EQUILIBRADO"


@pytest.mark.parametrize("alt", ["A", "B", "C"])
def test_regresion_equilibrado(alt):
    met = BASE / f"alternatives/{alt}/metrics.json"
    if not met.exists():
        pytest.skip("requiere la corrida final de E25")
    m = json.loads(met.read_text(encoding="utf-8"))
    pc = m["program_completeness"]
    assert pc["open_seats"] == "40/40"
    assert pc["complete"] is True
    assert m["hard_constraint_violations"] == 0
    assert m["collisions"] == 0
    assert m["circulation_connectivity"] is True


# ===================================================================================================
# 9 — los artefactos de diagnóstico existen y dicen lo que el informe dice
# ===================================================================================================
def test_el_diagnostico_pre_esta_congelado_y_cubre_las_nueve_combinaciones():
    p = RAIZ / "cases/E25/E25_DIAGNOSTICO_PRE_3x3.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert len(d["combinaciones"]) == 9
    assert {c["brief"] for c in d["combinaciones"]} == {"DENSO", "EQUILIBRADO", "EJECUTIVO"}
    for c in d["combinaciones"]:
        assert "generacion" in c and "poda" in c and "feasibility" in c


def test_los_experimentos_quedaron_registrados_antes_de_correrse():
    t = (RAIZ / "cases/E25/E25_EXPERIMENTOS_REGISTRADOS.md").read_text(encoding="utf-8")
    for x in ("EXP-1", "EXP-2", "EXP-3", "EXP-4", "PROVEN_INFEASIBLE", "SEARCH_EXHAUSTED"):
        assert x in t, x
    assert "parameter fishing" in t


# ===================================================================================================
# 10 — §23 alcance: qué movió E25 y qué no
# ===================================================================================================
def test_e25_movio_el_motor_a_proposito_con_baseline_declarado():
    import engine_baseline
    from escalimetro.generalization import freeze, producer_freeze, scope_guard
    base = json.loads((RAIZ / "cases/generalization/E25/GENERIC_ENGINE_BASELINE.json").read_text(encoding="utf-8"))
    eng = freeze.manifest(str(RAIZ))["engine_hash"]
    # E26 — mismo arreglo que se aplicó a los ciclos anteriores: el baseline de E25 declara el motor
    # DE E25, y lo que se comprueba hoy es que el motor está en el baseline VIGENTE, que un ciclo
    # posterior puede mover declarando baseline nuevo.
    assert engine_baseline.esta_en_la_cadena(base["engine_hash"]), "el motor de E25 salió de la cadena"
    assert eng == engine_baseline.engine_hash(), \
        "el motor cambió sin declarar un GENERIC_ENGINE_BASELINE.json nuevo"
    assert base["diff_vs_previous"]["previous"] == "E24"
    r = producer_freeze.read_worktree(str(RAIZ))
    assert producer_freeze.producer_hash(r) == "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
    assert scope_guard.hashes(r) == {
        "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
        "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
        "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
        "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f"}


def test_e25_no_toco_la_superficie_semantica_ni_borro_nada():
    base = json.loads((RAIZ / "cases/generalization/E25/GENERIC_ENGINE_BASELINE.json").read_text(encoding="utf-8"))
    d = base["diff_vs_previous"]
    assert d["semantic_surface_touched"] == []
    assert d["removed_files"] == []
    assert d["added_files"] == ["src/escalimetro/layout/search_status.py"]


def test_los_briefs_de_e24_no_se_tocaron():
    """§4 — inputs congelados. Si alguien movió un número para conseguir FIT, esto cae."""
    import hashlib
    esperado = {
        "BRIEF_DENSO": "f4daa2a96c42fc49c72f603fd35d73f5f7d87a8c769b95d3d902ce2af6e1d057",
        "BRIEF_EQUILIBRADO": "f6174547ac8f7dabe3e402a07f653f7644672892354ee083713c72f7a76628af",
        "BRIEF_EJECUTIVO": "d5a71c337ef9ed2de59e2b353a949bfb88feef91d35a94f7430b62e24841beb6"}
    for b, sha in esperado.items():
        assert hashlib.sha256((RAIZ / f"briefs/{b}.json").read_bytes()).hexdigest() == sha, b


def test_la_tabla_final_reporta_los_nueve_estados_con_la_semantica_de_e25():
    p = RAIZ / "cases/E25/E25_TABLA_FINAL.json"
    if not p.exists():
        pytest.skip("requiere la corrida final de E25")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert len(d["filas"]) == 9
    for f in d["filas"]:
        assert f["status"] in STATUSES, f
        # ninguna celda puede decir "no cabe": ninguna es PROVEN_INFEASIBLE
        assert f["status"] != PROVEN_INFEASIBLE, (
            "V1 no puede demostrar infactibilidad: el espacio de candidatos es incompleto")
    fits = [f for f in d["filas"] if f["status"] == FIT]
    assert {f["brief"] for f in fits} == {"EQUILIBRADO"}
    assert all(f["del_workstations"] == f["req_workstations"] for f in fits)
