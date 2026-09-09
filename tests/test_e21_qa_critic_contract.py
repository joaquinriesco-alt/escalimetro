"""E21 — guardas de INTEGRIDAD del contrato QA-critic.

E21 no crea banco ni toca el motor: reusa el banco de E19 byte a byte y cambia UNA cosa,
la PREGUNTA que se le hace al evaluador (de "clasifica" a "juzga esta afirmacion").
Estos tests prueban la integridad del experimento y que el motor no se movio.
NO prueban al evaluador, que no es determinista.

El scorecard NO se afirma en prosa: se RECALCULA aqui desde respuestas_e21.txt + ground truth
y se compara contra score_e21.txt. Si alguien edita el scorecard, estos tests fallan.
"""
import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tests" / "fixtures" / "semantic_context"))
import context_bench_scene as B  # noqa: E402

from escalimetro.generalization import freeze, producer_freeze, scope_guard  # noqa: E402

BENCH_E19 = "2b3e2eb06248f3897b4bf663ce39930fc111b59560ccffd7cac8478141be6f81"
PROMPT_E21 = "ab58d99ebe98923dff4cb2d1af43866630c954574b18a4db6c6ef920ca36170d"
PREREG_E21 = "abfac27d46b78d400c4a6cd55be1626c0a7f46ec5851caa671d8296d40ad4181"
RESPUESTAS = "312ee30c106711c7aa845181fdb176a0cf4409e994d72463993e752853f17f5f"
ENGINE = "779a1eee6d3d2f2ce4fcc185dbf08da8890768e49a64211770eb1ee800a8105c"
PRODUCER = "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
SCOPE = {
    "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
    "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
    "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
    "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f",
}
D = RAIZ / "cases/generalization/E21"
MAN = json.loads((D / "manifest.json").read_text())
E19_1 = json.loads((RAIZ / "cases/generalization/E19_1/eval_manifest.json").read_text())
A, F = "ARCHITECTURAL_ENCLOSURE", "FURNITURE_OBJECT"
VEREDICTOS = ("CONSISTENT", "REVIEW", "INSUFFICIENT_EVIDENCE")


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _asserts():
    return {a["call_id"]: a for a in MAN["manifest"]}


def _respuestas():
    r, orden = {}, []
    for L in (D / "respuestas_e21.txt").read_text().splitlines():
        L = L.strip()
        if not L:
            continue
        _ola, cid, v = L.split()
        r[cid] = v
        orden.append(cid)
    return r, orden


def _score_txt():
    return (D / "score_e21.txt").read_text()


# ---------------------------------------------------------------- banco y motor

def test_el_banco_sigue_siendo_el_de_e19():
    """§3 — si el banco cambio, E21 no es comparable con E19/E19.1/E20."""
    assert _sha(RAIZ / "tests/fixtures/semantic_context/context_bench_scene.py") == BENCH_E19


def test_las_72_imagenes_son_las_mismas_de_e19_1():
    """§3 — cada sha_img del manifest E21 debe coincidir con el manifest de E19.1."""
    por_id = {e["id"]: e for e in E19_1["items"] if e.get("brazo") == "FULL_CONTEXT"}
    assert len(por_id) == 72
    for a in MAN["manifest"]:
        assert a["img"] in por_id, a["img"]
        assert a["sha_img"] == por_id[a["img"]]["sha_img"], a["img"]


def test_el_ground_truth_coincide_con_e19_1():
    por_id = {e["id"]: e for e in E19_1["items"] if e.get("brazo") == "FULL_CONTEXT"}
    for a in MAN["manifest"]:
        assert a["gt"] == por_id[a["img"]]["verdad"], a["call_id"]


def test_el_banco_declarado_en_e19_1_es_el_mismo_bench():
    assert E19_1["bench_sha256"] == BENCH_E19


def test_el_motor_no_se_movio():
    """E21 es un spike de evaluacion: no puede tocar el motor."""
    r = producer_freeze.read_worktree(str(RAIZ))
    assert freeze.manifest(str(RAIZ))["engine_hash"] == ENGINE
    assert producer_freeze.producer_hash(r) == PRODUCER


def test_el_scope_guard_no_se_movio():
    r = producer_freeze.read_worktree(str(RAIZ))
    assert scope_guard.hashes(r) == SCOPE


def test_el_generador_conserva_un_solo_ancho_y_tres_tonos():
    """El ancho unico impide que E17 (ancho) se cuele como pista."""
    fuente = Path(B.__file__).read_text()
    arbol = ast.parse(fuente)
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (n.body and isinstance(n.body[0], ast.Expr)
                    and isinstance(n.body[0].value, ast.Constant)
                    and isinstance(n.body[0].value.value, str)):
                n.body.pop(0)
    codigo = ast.unparse(arbol)
    assert codigo.count("W_UNICO") == 2
    assert B.W_UNICO == 0.0035
    assert sorted({B.PAPEL, B.TINTA, B.GRIS_MARCA}) == [35, 130, 255]


# ---------------------------------------------------------------- prompt

def test_el_prompt_esta_congelado_y_hasheado():
    assert _sha(D / "prompt_qa_congelado.txt") == PROMPT_E21


def test_el_prompt_tiene_exactamente_un_marcador_de_rol():
    """§9 — el ASSERTED_ROLE es la UNICA variable entre las dos llamadas de una imagen."""
    t = (D / "prompt_qa_congelado.txt").read_text()
    assert t.count("{ASSERTED_ROLE}") == 1


def test_el_prompt_pide_los_tres_veredictos_y_solo_esos():
    t = (D / "prompt_qa_congelado.txt").read_text()
    for v in VEREDICTOS:
        assert v in t, v
    assert "qa_verdict" in t


def test_el_prompt_no_pide_clasificar():
    """§5 — el critic juzga una afirmacion; no produce una clasificacion propia."""
    t = (D / "prompt_qa_congelado.txt").read_text()
    assert "not to produce a classification of" in t


def test_el_prompt_no_menciona_ciclos_ni_resultados_anteriores():
    t = (D / "prompt_qa_congelado.txt").read_text().lower()
    for prohibido in ("e19", "e20", "e18", "e17", "recall", "pod_aislado", "poche",
                      "gate", "previous", "earlier", "benchmark"):
        assert prohibido not in t, prohibido


def test_el_prompt_no_sugiere_una_distribucion_de_respuestas():
    """§10 — un critic que conoce la tasa de error base no es un critic."""
    t = (D / "prompt_qa_congelado.txt").read_text()
    assert "Do not assume any particular distribution of answers." in t


def test_el_prompt_restringe_las_herramientas():
    t = (D / "prompt_qa_congelado.txt").read_text()
    assert "ONLY on the exact file path" in t
    for h in ("Glob", "Grep", "Bash", "WebSearch"):
        assert h in t, h


def test_el_preregistro_esta_congelado_y_hasheado():
    assert _sha(D / "preregistro.md") == PREREG_E21


# ---------------------------------------------------------------- diseno contrafactual

def test_hay_exactamente_144_assertions():
    assert len(MAN["manifest"]) == 144
    assert MAN["n"] == 144


def test_los_call_id_son_unicos_y_bien_formados():
    ids = [a["call_id"] for a in MAN["manifest"]]
    assert len(set(ids)) == 144
    for a in MAN["manifest"]:
        sufijo = "_T" if a["arm"] == "TRUE" else "_F"
        assert a["call_id"] == a["img"] + sufijo


def test_cada_imagen_aporta_exactamente_dos_brazos():
    por_img = {}
    for a in MAN["manifest"]:
        por_img.setdefault(a["img"], []).append(a["arm"])
    assert len(por_img) == 72
    for img, brazos in por_img.items():
        assert sorted(brazos) == ["FALSE", "TRUE"], img


def test_los_dos_brazos_de_una_imagen_usan_LA_MISMA_imagen():
    """§11 — el contrafactual solo es valido si el pixel no cambia entre brazos."""
    por_img = {}
    for a in MAN["manifest"]:
        por_img.setdefault(a["img"], set()).add(a["sha_img"])
    for img, shas in por_img.items():
        assert len(shas) == 1, img


def test_el_brazo_true_afirma_el_rol_verdadero():
    for a in MAN["manifest"]:
        if a["arm"] == "TRUE":
            assert a["asserted"] == a["gt"], a["call_id"]


def test_el_brazo_false_afirma_el_rol_invertido():
    for a in MAN["manifest"]:
        if a["arm"] == "FALSE":
            assert a["asserted"] != a["gt"], a["call_id"]
            assert {a["asserted"], a["gt"]} == {A, F}, a["call_id"]


def test_el_balance_de_las_cuatro_celdas_es_36_36_36_36():
    """§12 — sin balance, cualquier asimetria medida seria del banco, no del critic."""
    celdas = {}
    for a in MAN["manifest"]:
        celdas[(a["arm"], a["asserted"])] = celdas.get((a["arm"], a["asserted"]), 0) + 1
    assert celdas[("TRUE", A)] == 36
    assert celdas[("TRUE", F)] == 36
    assert celdas[("FALSE", A)] == 36
    assert celdas[("FALSE", F)] == 36


def test_el_banco_esta_balanceado_36_recintos_36_muebles():
    gts = [a["gt"] for a in MAN["manifest"] if a["arm"] == "TRUE"]
    assert gts.count(A) == 36
    assert gts.count(F) == 36


def test_solo_hay_dos_roles_posibles():
    assert {a["asserted"] for a in MAN["manifest"]} == {A, F}
    assert {a["gt"] for a in MAN["manifest"]} == {A, F}


# ---------------------------------------------------------------- orden y olas

def test_la_semilla_esta_declarada():
    assert MAN["semilla"] == 2101


def test_hay_12_olas_de_12():
    assert len(MAN["olas"]) == 12
    for ola in MAN["olas"]:
        assert len(ola) == 12


def test_las_olas_son_una_reparticion_exacta_del_orden_pre_registrado():
    plano = [c for ola in MAN["olas"] for c in ola]
    assert len(plano) == 144
    assert sorted(plano) == sorted(MAN["orden"])


def test_las_olas_se_reproducen_desde_el_orden_sin_ninguna_eleccion_libre():
    """§12 — el agrupamiento es un barrido greedy determinista sobre el orden de la semilla:
    cada llamada cae en la primera ola con hueco que no contenga ya el otro brazo de su imagen.
    Reproducible sin ver ningun resultado. Si el agrupamiento hubiera sido a mano, esto falla."""
    olas = [[] for _ in range(12)]
    for cid in MAN["orden"]:
        img = cid.rsplit("_", 1)[0]
        for o in olas:
            if len(o) < 12 and all(x.rsplit("_", 1)[0] != img for x in o):
                o.append(cid)
                break
        else:
            pytest.fail(f"sin hueco para {cid}")
    assert olas == MAN["olas"]


def test_ninguna_ola_contiene_los_dos_brazos_de_la_misma_imagen():
    """§12 — declarado ANTES de correr. Dos brazos concurrentes serian una fuga posible."""
    for i, ola in enumerate(MAN["olas"], 1):
        imgs = [c.rsplit("_", 1)[0] for c in ola]
        assert len(set(imgs)) == 12, f"ola {i}"


def test_el_orden_cubre_el_manifest_completo():
    assert set(MAN["orden"]) == {a["call_id"] for a in MAN["manifest"]}


# ---------------------------------------------------------------- respuestas

def test_hay_144_respuestas_y_estan_hasheadas():
    r, orden = _respuestas()
    assert len(r) == 144
    assert len(orden) == 144
    assert _sha(D / "respuestas_e21.txt") == RESPUESTAS


def test_las_respuestas_siguen_el_orden_de_despacho_pre_registrado():
    """Si el orden ejecutado no es el declarado, el pre-registro no gobierna nada.
    El orden de ejecucion es el de las olas, que a su vez se deriva del orden de la semilla."""
    _r, orden = _respuestas()
    assert orden == [c for ola in MAN["olas"] for c in ola]


def test_todo_veredicto_es_uno_de_los_tres_permitidos():
    r, _o = _respuestas()
    for cid, v in r.items():
        assert v in VEREDICTOS, (cid, v)


def test_no_hay_respuesta_sin_assertion_ni_assertion_sin_respuesta():
    r, _o = _respuestas()
    assert set(r) == {a["call_id"] for a in MAN["manifest"]}


def test_la_incidencia_tecnica_esta_registrada_y_no_se_oculta():
    """§48-49 del pre-registro: un solo reintento, registrado, sin elegir por calidad."""
    t = (D / "incidencias_tecnicas.txt").read_text()
    assert "TECHNICAL_RETRY = TRUE" in t
    assert "CRMQAT_T" in t
    r, _o = _respuestas()
    assert r["CRMQAT_T"] == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------- metricas recalculadas

def _metricas():
    r, _o = _respuestas()
    ass = _asserts()

    def sel(arm=None, asserted=None):
        return [c for c, a in ass.items()
                if (arm is None or a["arm"] == arm)
                and (asserted is None or a["asserted"] == asserted)]

    def frac(cids, v):
        return sum(1 for c in cids if r[c] == v) / len(cids)

    return {
        "ERROR_CATCH_RATE": frac(sel("FALSE"), "REVIEW"),
        "ERROR_CATCH_RATE_falsa_ARCH": frac(sel("FALSE", A), "REVIEW"),
        "ERROR_CATCH_RATE_falsa_FURN": frac(sel("FALSE", F), "REVIEW"),
        "CORRECT_PASS_RATE": frac(sel("TRUE"), "CONSISTENT"),
        "CORRECT_PASS_RATE_true_ARCH": frac(sel("TRUE", A), "CONSISTENT"),
        "CORRECT_PASS_RATE_true_FURN": frac(sel("TRUE", F), "CONSISTENT"),
        "TRUE_ASSERTION_REVIEW_RATE": frac(sel("TRUE"), "REVIEW"),
        "FALSE_ASSERTION_CONSISTENT_RATE": frac(sel("FALSE"), "CONSISTENT"),
        "INSUFFICIENT_RATE_total": frac(list(ass), "INSUFFICIENT_EVIDENCE"),
    }


def test_el_scorecard_no_es_prosa_se_recalcula_desde_los_datos():
    """La prueba central: cada numero del scorecard sale de respuestas + ground truth."""
    m = _metricas()
    txt = _score_txt()
    for k, v in m.items():
        assert f"{k:34s} {v:.4f}" in txt, (k, v)


def test_balanced_qa_accuracy_es_el_promedio_de_las_dos_tasas():
    m = _metricas()
    ba = (m["ERROR_CATCH_RATE"] + m["CORRECT_PASS_RATE"]) / 2
    assert f"BALANCED_QA_ACCURACY               {ba:.4f}" in _score_txt()


def test_las_tres_tasas_de_cada_brazo_suman_uno():
    r, _o = _respuestas()
    ass = _asserts()
    for arm in ("TRUE", "FALSE"):
        cids = [c for c, a in ass.items() if a["arm"] == arm]
        total = sum(1 for c in cids if r[c] in VEREDICTOS)
        assert total == len(cids) == 72


def test_error_catch_y_false_consistent_e_insufficient_son_particion():
    m = _metricas()
    r, _o = _respuestas()
    ass = _asserts()
    f_ins = sum(1 for c, a in ass.items()
                if a["arm"] == "FALSE" and r[c] == "INSUFFICIENT_EVIDENCE") / 72
    assert abs(m["ERROR_CATCH_RATE"] + m["FALSE_ASSERTION_CONSISTENT_RATE"] + f_ins - 1) < 1e-12


def test_el_ideal_pair_rate_se_recalcula_por_imagen():
    r, _o = _respuestas()
    imgs = sorted({a["img"] for a in MAN["manifest"]})
    ideal = sum(1 for im in imgs
                if r[im + "_T"] == "CONSISTENT" and r[im + "_F"] == "REVIEW")
    assert f"IDEAL_PAIR_RATE (T=CONSISTENT y F=REVIEW) = {ideal/72:.4f}  ({ideal}/72)" in _score_txt()


def test_la_matriz_3x3_de_pares_suma_72():
    r, _o = _respuestas()
    imgs = sorted({a["img"] for a in MAN["manifest"]})
    d = {}
    for im in imgs:
        k = (r[im + "_T"], r[im + "_F"])
        d[k] = d.get(k, 0) + 1
    assert sum(d.values()) == 72


# ---------------------------------------------------------------- gates

def _gates():
    m = _metricas()
    ba = (m["ERROR_CATCH_RATE"] + m["CORRECT_PASS_RATE"]) / 2
    return [
        m["ERROR_CATCH_RATE"] >= 0.80,
        m["ERROR_CATCH_RATE_falsa_ARCH"] >= 0.70,
        m["ERROR_CATCH_RATE_falsa_FURN"] >= 0.70,
        m["CORRECT_PASS_RATE"] >= 0.75,
        m["CORRECT_PASS_RATE_true_ARCH"] >= 0.65,
        m["CORRECT_PASS_RATE_true_FURN"] >= 0.65,
        m["FALSE_ASSERTION_CONSISTENT_RATE"] <= 0.15,
        m["TRUE_ASSERTION_REVIEW_RATE"] <= 0.25,
        m["INSUFFICIENT_RATE_total"] <= 0.15,
        ba >= 0.775,
    ]


def test_los_umbrales_del_scorecard_son_los_del_preregistro():
    """Blindaje anti p-hacking: los umbrales del scorecard deben estar en el pre-registro."""
    pre = (D / "preregistro.md").read_text()
    for u in ("0.80", "0.70", "0.75", "0.65", "0.15", "0.25", "0.775"):
        assert u in pre, u


def test_e21_a_es_fail_y_no_se_movio_ningun_umbral():
    assert not all(_gates())
    assert "E21-A = FAIL" in _score_txt()


def test_los_gates_que_pasan_son_exactamente_cuatro():
    assert sum(_gates()) == 4
    assert _score_txt().count("[PASS]") == 4
    assert _score_txt().count("[FAIL]") == 6


def test_el_gate_de_deteccion_falla_por_un_margen_que_no_es_de_redondeo():
    m = _metricas()
    assert 0.80 - m["ERROR_CATCH_RATE"] > 0.20


def test_la_asimetria_por_clase_es_real_y_no_ruido_de_una_celda():
    """El hallazgo: el critic favorece la lectura MUEBLE en los DOS brazos."""
    m = _metricas()
    assert m["ERROR_CATCH_RATE_falsa_ARCH"] > m["ERROR_CATCH_RATE_falsa_FURN"]
    assert m["CORRECT_PASS_RATE_true_FURN"] > m["CORRECT_PASS_RATE_true_ARCH"]


def test_la_stop_rule_esta_escrita_y_el_resultado_no_la_habilita():
    """Stop rule: solo E21-A autoriza E22. E21-A fallo, asi que nada se abre."""
    pre = (D / "preregistro.md").read_text()
    assert "Solo E21-A autoriza E22" in pre
    assert "sin abrir el tercer plano" in pre
    assert "E21-A = FAIL" in _score_txt()


def test_el_scorecard_no_declara_ningun_gate_como_pasado_si_su_metrica_no_lo_cumple():
    """Blindaje: cada linea [PASS]/[FAIL] del scorecard debe concordar con el recalculo."""
    lineas = [l for l in _score_txt().splitlines() if l.startswith(("[PASS]", "[FAIL]"))]
    assert len(lineas) == 10
    for linea, ok in zip(lineas, _gates()):
        assert linea.startswith("[PASS]") == ok, linea


# ---------------------------------------------------------------- acoplamiento

def test_e21_no_toca_runtime():
    """E21 es evaluacion: su scoring no puede importar nada del paquete."""
    t = (D / "score_e21_script.txt").read_text()
    assert "escalimetro" not in t
    assert "numpy" in t


def test_el_spike_vive_fuera_del_runtime():
    for py in (RAIZ / "src").rglob("*.py"):
        s = py.read_text()
        assert "context_bench_scene" not in s, py
        assert "semantic_context" not in s, py
    assert not list(D.glob("*.py")), "los scripts del spike se guardan como .txt"


def test_los_artefactos_no_contienen_credenciales():
    for p in sorted(D.glob("*")):
        t = p.read_text(errors="ignore").lower()
        for token in ("api_key", "apikey", "secret", "password", "sk-", "bearer ",
                      "railway_token", "ghp_"):
            assert token not in t, (p.name, token)


def test_el_scorecard_declara_provider_desconocido_en_el_preregistro():
    pre = (D / "preregistro.md").read_text()
    assert "PROVIDER_IDENTITY = UNKNOWN" in pre
    assert "PRODUCTION_REPRODUCIBILITY = NOT_PROVEN" in pre
