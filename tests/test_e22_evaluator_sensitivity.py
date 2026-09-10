"""E22 — guardas de INTEGRIDAD de la prueba de sensibilidad al evaluador.

E22 no crea banco, no cambia el prompt y no toca el motor: reusa TODO lo de E21 byte a byte
y cambia UNA cosa, el evaluador. Estos tests prueban esa identidad y que el scorecard no es prosa.
NO prueban al evaluador, que no es determinista.

El scorecard se RECALCULA aqui desde respuestas_e22.txt + ground truth y se compara contra
score_e22.txt. Si alguien edita el scorecard, la suite se pone roja.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tests" / "fixtures" / "semantic_context"))
import context_bench_scene as B  # noqa: E402

import engine_baseline  # noqa: E402
from escalimetro.generalization import freeze, producer_freeze, scope_guard  # noqa: E402

BENCH = "2b3e2eb06248f3897b4bf663ce39930fc111b59560ccffd7cac8478141be6f81"
PROMPT_E21 = "ab58d99ebe98923dff4cb2d1af43866630c954574b18a4db6c6ef920ca36170d"
BASELINE_E21 = "312ee30c106711c7aa845181fdb176a0cf4409e994d72463993e752853f17f5f"
MANIFEST = "43de0430755fccdbc1e182efa1fb1ac28b64a6caa1d04fd14859370d4c4b78f8"
PREREG_E22 = "2332a7d693b706c8985ba7f96c4a3d8e320f84369df5ba288b95d2f8a56d63e1"
INVENTARIO = "c402b6e74babbad0ec490061f866cf0fc538fd50cbed40d7bcd617277af9a7bf"
RESP_E22 = "40436c26202dad83c23c4cdfc7950c500df80761891006d04c3c493514b64a68"
ENGINE = "779a1eee6d3d2f2ce4fcc185dbf08da8890768e49a64211770eb1ee800a8105c"
PRODUCER = "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
SCOPE = {
    "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
    "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
    "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
    "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f",
}
D22 = RAIZ / "cases/generalization/E22"
D21 = RAIZ / "cases/generalization/E21"
MAN = json.loads((D22 / "manifest.json").read_text())
A, F = "ARCHITECTURAL_ENCLOSURE", "FURNITURE_OBJECT"
VEREDICTOS = ("CONSISTENT", "REVIEW", "INSUFFICIENT_EVIDENCE")


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _asserts():
    return {a["call_id"]: a for a in MAN["manifest"]}


def _carga(p):
    r, orden = {}, []
    for L in Path(p).read_text().splitlines():
        L = L.strip()
        if not L:
            continue
        _ola, cid, v = L.split()
        r[cid] = v
        orden.append(cid)
    return r, orden


def _alt():
    return _carga(D22 / "respuestas_e22.txt")


def _base():
    return _carga(D21 / "respuestas_e21.txt")


def _score():
    return (D22 / "score_e22.txt").read_text()


# ------------------------------------------------ identidad congelada respecto de E21

def test_el_banco_es_el_mismo_de_e19_a_e21():
    assert _sha(RAIZ / "tests/fixtures/semantic_context/context_bench_scene.py") == BENCH


def test_el_prompt_es_EL_MISMO_de_e21_sin_una_coma_de_cambio():
    """§6 — si el prompt cambia, E22 no mide el evaluador, mide el prompt."""
    assert _sha(D21 / "prompt_qa_congelado.txt") == PROMPT_E21


def test_e22_no_tiene_prompt_propio():
    """No puede existir un prompt alternativo: E22 reusa el de E21."""
    assert not list(D22.glob("*prompt*"))


def test_el_manifest_es_EL_MISMO_de_e21():
    """§7 — mismos call_id, mismo GT, misma distribucion, mismos asserted roles."""
    assert _sha(D22 / "manifest.json") == MANIFEST
    assert _sha(D21 / "manifest.json") == MANIFEST
    assert json.loads((D21 / "manifest.json").read_text()) == MAN


def test_el_baseline_de_e21_esta_intacto():
    """§7 — el baseline es inmutable y no se re-ejecuto opus."""
    assert _sha(D21 / "respuestas_e21.txt") == BASELINE_E21


def test_el_motor_no_se_movio():
    r = producer_freeze.read_worktree(str(RAIZ))
    # E24 — el literal ENGINE es el motor de ESTE ciclo y queda documentado en la cadena de
    # baselines. Lo que se comprueba hoy es que el motor está en el baseline VIGENTE: un ciclo
    # posterior puede moverlo a propósito, pero sólo declarando un baseline nuevo.
    assert engine_baseline.esta_en_la_cadena(ENGINE), "el motor de este ciclo salió de la cadena"
    assert freeze.manifest(str(RAIZ))["engine_hash"] == engine_baseline.engine_hash(), \
        "el motor cambió sin declarar un GENERIC_ENGINE_BASELINE.json nuevo"
    assert producer_freeze.producer_hash(r) == PRODUCER


def test_el_scope_guard_no_se_movio():
    r = producer_freeze.read_worktree(str(RAIZ))
    assert scope_guard.hashes(r) == SCOPE


def test_el_generador_conserva_un_solo_ancho_y_tres_tonos():
    assert B.W_UNICO == 0.0035
    assert sorted({B.PAPEL, B.TINTA, B.GRIS_MARCA}) == [35, 130, 255]


# ------------------------------------------------ inventario y seleccion (§3, §4)

def test_el_inventario_esta_congelado_y_hasheado():
    assert _sha(D22 / "inventario_modelos.txt") == INVENTARIO


def test_el_inventario_lista_las_cuatro_configuraciones_del_entorno():
    t = (D22 / "inventario_modelos.txt").read_text()
    for p in ("opus", "sonnet", "haiku", "fable"):
        assert p in t, p


def test_se_eligio_UN_SOLO_alternativo():
    """§3/§18 — un solo alternativo, elegido antes de ver resultados."""
    t = (D22 / "inventario_modelos.txt").read_text()
    assert "EVALUADOR ALTERNATIVO = sonnet" in t
    assert "UNO SOLO" in t
    pre = (D22 / "preregistro.md").read_text()
    assert "EVALUADOR ALTERNATIVO CONGELADO = sonnet" in pre


def test_no_hay_rastro_de_un_segundo_alternativo_en_las_respuestas():
    """Blindaje anti model shopping: 144 respuestas, ni una mas."""
    r, orden = _alt()
    assert len(r) == 144 and len(orden) == 144


def test_la_prioridad_usada_esta_declarada_y_es_la_2():
    pre = (D22 / "preregistro.md").read_text()
    assert "SELECTION_PRIORITY_USED = PRIORIDAD 2" in pre
    assert "PRIORIDAD 1" in pre and "NO SATISFACIBLE" in pre


def test_la_verificabilidad_de_identidad_esta_declarada_como_limitada():
    """§4 — no fingir diversidad de proveedor que no se puede verificar."""
    pre = (D22 / "preregistro.md").read_text()
    assert "MODEL_IDENTITY_VERIFIABILITY = CONFIGURATION_LEVEL_ONLY" in pre
    assert "PROVIDER_IDENTITY            = UNKNOWN" in pre
    assert "NO independencia de proveedor" in pre


def test_el_preregistro_esta_congelado_y_hasheado():
    assert _sha(D22 / "preregistro.md") == PREREG_E22


def test_el_preregistro_se_escribio_antes_de_inferir():
    pre = (D22 / "preregistro.md").read_text()
    assert "ANTES de la inferencia #1" in pre
    assert "PREREGISTRATION_FROZEN = TRUE" in pre


# ------------------------------------------------ orden y respuestas

def test_las_respuestas_siguen_el_orden_de_despacho_pre_registrado():
    _r, orden = _alt()
    assert orden == [c for ola in MAN["olas"] for c in ola]


def test_las_respuestas_estan_hasheadas():
    assert _sha(D22 / "respuestas_e22.txt") == RESP_E22


def test_todo_veredicto_es_uno_de_los_tres_permitidos():
    r, _o = _alt()
    for cid, v in r.items():
        assert v in VEREDICTOS, (cid, v)


def test_alternativo_y_baseline_cubren_exactamente_las_mismas_144_assertions():
    ra, _ = _alt()
    rb, _ = _base()
    assert set(ra) == set(rb) == set(_asserts())


def test_el_balance_de_las_cuatro_celdas_sigue_siendo_36_cada_una():
    celdas = {}
    for a in MAN["manifest"]:
        k = (a["arm"], a["asserted"])
        celdas[k] = celdas.get(k, 0) + 1
    assert celdas[("TRUE", A)] == celdas[("TRUE", F)] == 36
    assert celdas[("FALSE", A)] == celdas[("FALSE", F)] == 36


# ------------------------------------------------ metricas recalculadas

def _met(r):
    ass = _asserts()

    def sel(arm=None, asr=None):
        return [c for c, a in ass.items()
                if (arm is None or a["arm"] == arm) and (asr is None or a["asserted"] == asr)]

    def fr(cs, v):
        return sum(1 for c in cs if r[c] == v) / len(cs)

    m = {
        "ERROR_CATCH_RATE": fr(sel("FALSE"), "REVIEW"),
        "ERROR_CATCH_RATE_falsa_ARCH": fr(sel("FALSE", A), "REVIEW"),
        "ERROR_CATCH_RATE_falsa_FURN": fr(sel("FALSE", F), "REVIEW"),
        "CORRECT_PASS_RATE": fr(sel("TRUE"), "CONSISTENT"),
        "CORRECT_PASS_RATE_true_ARCH": fr(sel("TRUE", A), "CONSISTENT"),
        "CORRECT_PASS_RATE_true_FURN": fr(sel("TRUE", F), "CONSISTENT"),
        "TRUE_ASSERTION_REVIEW_RATE": fr(sel("TRUE"), "REVIEW"),
        "FALSE_ASSERTION_CONSISTENT_RATE": fr(sel("FALSE"), "CONSISTENT"),
        "INSUFFICIENT_RATE_total": fr(list(ass), "INSUFFICIENT_EVIDENCE"),
    }
    m["BALANCED_QA_ACCURACY"] = (m["ERROR_CATCH_RATE"] + m["CORRECT_PASS_RATE"]) / 2
    imgs = sorted({a["img"] for a in ass.values()})
    m["IDEAL_PAIR_RATE"] = sum(
        1 for i in imgs if r[i + "_T"] == "CONSISTENT" and r[i + "_F"] == "REVIEW") / len(imgs)
    m["PASS_ASYMMETRY"] = m["CORRECT_PASS_RATE_true_FURN"] - m["CORRECT_PASS_RATE_true_ARCH"]
    m["CATCH_ASYMMETRY"] = m["ERROR_CATCH_RATE_falsa_ARCH"] - m["ERROR_CATCH_RATE_falsa_FURN"]
    return m


def test_el_scorecard_no_es_prosa_se_recalcula_desde_los_datos():
    """La prueba central: cada fila sale de respuestas + ground truth, para ALT y para BASE."""
    ma, mb = _met(_alt()[0]), _met(_base()[0])
    txt = _score()
    for k in ["ERROR_CATCH_RATE", "ERROR_CATCH_RATE_falsa_ARCH", "ERROR_CATCH_RATE_falsa_FURN",
              "CORRECT_PASS_RATE", "CORRECT_PASS_RATE_true_ARCH", "CORRECT_PASS_RATE_true_FURN",
              "TRUE_ASSERTION_REVIEW_RATE", "FALSE_ASSERTION_CONSISTENT_RATE",
              "BALANCED_QA_ACCURACY", "IDEAL_PAIR_RATE"]:
        assert f"{k:34s}{ma[k]:13.4f}{mb[k]:13.4f}{ma[k]-mb[k]:+10.4f}" in txt, k


def test_el_baseline_del_scorecard_coincide_con_e21_publicado():
    """El brazo BASE de E22 debe reproducir exactamente las cifras de E21."""
    mb = _met(_base()[0])
    assert abs(mb["ERROR_CATCH_RATE"] - 0.5694) < 1e-3
    assert abs(mb["CORRECT_PASS_RATE"] - 0.7639) < 1e-3
    assert abs(mb["BALANCED_QA_ACCURACY"] - 0.6667) < 1e-3
    assert abs(mb["PASS_ASYMMETRY"] - 0.4166) < 1e-3
    assert abs(mb["CATCH_ASYMMETRY"] - 0.2500) < 1e-3


def test_los_indices_de_asimetria_se_recalculan():
    ma = _met(_alt()[0])
    txt = _score()
    assert f"{'PASS_ASYMMETRY':26s}{ma['PASS_ASYMMETRY']:10.4f}" in txt
    assert f"{'CATCH_ASYMMETRY':26s}{ma['CATCH_ASYMMETRY']:10.4f}" in txt


def test_el_hallazgo_central_el_alternativo_nunca_marca_una_falsa_FURN():
    """0 de 36. Si esto cambia, el informe esta mal."""
    r, _o = _alt()
    ass = _asserts()
    ff = [c for c, a in ass.items() if a["arm"] == "FALSE" and a["asserted"] == F]
    assert len(ff) == 36
    assert sum(1 for c in ff if r[c] == "REVIEW") == 0


def test_el_alternativo_acepta_todas_las_true_FURN():
    r, _o = _alt()
    ass = _asserts()
    tf = [c for c, a in ass.items() if a["arm"] == "TRUE" and a["asserted"] == F]
    assert sum(1 for c in tf if r[c] == "CONSISTENT") == 36


def test_la_asimetria_no_se_redujo_aumento():
    """La pregunta de E22 era si el sesgo era del evaluador. Empeoro en ambos indices."""
    ma, mb = _met(_alt()[0]), _met(_base()[0])
    assert ma["PASS_ASYMMETRY"] > mb["PASS_ASYMMETRY"]
    assert ma["CATCH_ASYMMETRY"] > mb["CATCH_ASYMMETRY"]


# ------------------------------------------------ gates

def _gates():
    m = _met(_alt()[0])
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
        m["BALANCED_QA_ACCURACY"] >= 0.775,
    ]


def test_los_umbrales_son_los_originales_de_e21_sin_relajar():
    """§11 — el gate absoluto es el de E21-A. Debe estar literal en los dos pre-registros."""
    p22 = (D22 / "preregistro.md").read_text()
    p21 = (D21 / "preregistro.md").read_text()
    for u in ("0.80", "0.70", "0.75", "0.65", "0.15", "0.25", "0.775"):
        assert u in p22 and u in p21, u


def test_el_gate_absoluto_falla():
    assert not all(_gates())
    assert "GATE ABSOLUTO = FAIL" in _score()


def test_cada_linea_pass_fail_concuerda_con_el_recalculo():
    lineas = [l for l in _score().splitlines() if l.startswith(("[PASS]", "[FAIL]"))]
    assert len(lineas) == 10
    for linea, ok in zip(lineas, _gates()):
        assert linea.startswith("[PASS]") == ok, linea


def test_solo_tres_gates_pasan():
    assert sum(_gates()) == 3


def test_el_delta_de_balanced_qa_dispara_el_umbral_de_e22_D():
    """§17 E22-D: DELTA_BALANCED_QA <= -0.10."""
    ma, mb = _met(_alt()[0]), _met(_base()[0])
    assert ma["BALANCED_QA_ACCURACY"] - mb["BALANCED_QA_ACCURACY"] <= -0.10


# ------------------------------------------------ desviaciones declaradas

def test_la_desviacion_de_tool_restriction_esta_declarada_y_cuantificada():
    """No se oculta: 7 de 144 llamadas usaron Bash. Debe estar escrito, con los call_id."""
    t = (D22 / "incidencias_tecnicas.txt").read_text()
    assert "DESVIACION DE TOOL RESTRICTION" in t
    assert "7 de 144" in t
    for cid in ("MJK6F2_T", "TL3PFB_T", "E3M2GB_F", "WLCDKW_T",
                "YAJ5GC_F", "JQ6ZTY_T", "3Y29N4_T"):
        assert cid in t, cid


def test_la_auditoria_descarta_fuga_de_informacion():
    t = (D22 / "incidencias_tecnicas.txt").read_text()
    assert "Cero fuga de informacion hacia el evaluador" in t
    assert "ninguna leyo otra imagen del banco" in t


def test_no_hubo_reintentos_tecnicos():
    t = (D22 / "incidencias_tecnicas.txt").read_text()
    assert "TECHNICAL_RETRY = FALSE" in t


def test_ninguna_llamada_fue_descartada():
    t = (D22 / "incidencias_tecnicas.txt").read_text()
    assert "NO se descarto ninguna" in t


# ------------------------------------------------ stop rules y acoplamiento

def test_la_stop_rule_esta_escrita_y_no_se_abre_nada():
    pre = (D22 / "preregistro.md").read_text()
    assert "Ningun veredicto abre GPS, RES ni el tercer plano" in pre
    assert "Ni siquiera E22-A" in pre


def test_e22_no_toca_runtime():
    t = (D22 / "score_e22_script.txt").read_text()
    assert "escalimetro" not in t
    assert "numpy" in t


def test_el_spike_vive_fuera_del_runtime():
    for py in (RAIZ / "src").rglob("*.py"):
        s = py.read_text()
        assert "context_bench_scene" not in s, py
        assert "semantic_context" not in s, py
    assert not list(D22.glob("*.py")), "los scripts del spike se guardan como .txt"


def test_los_artefactos_no_contienen_credenciales():
    for p in sorted(D22.glob("*")):
        t = p.read_text(errors="ignore").lower()
        for token in ("api_key", "apikey", "secret", "password", "sk-", "bearer ",
                      "railway_token", "ghp_"):
            assert token not in t, (p.name, token)
