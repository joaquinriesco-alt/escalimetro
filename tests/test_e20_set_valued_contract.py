"""E20 — guardas de INTEGRIDAD del contrato set-valued.

E20 no crea banco: reusa el de E19 sin tocar un byte y cambia UNA cosa, el contrato de salida.
Estos tests prueban eso y que el motor no se movio. No prueban al evaluador, que no es determinista.
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

import engine_baseline  # noqa: E402
from escalimetro.generalization import freeze, producer_freeze, scope_guard  # noqa: E402

BENCH_E19 = "2b3e2eb06248f3897b4bf663ce39930fc111b59560ccffd7cac8478141be6f81"
PROMPT_E20 = "80e77c48498a1462653e2c27da565ecff6c5900b6c066ae37be305b0ca25bf30"
ENGINE = "779a1eee6d3d2f2ce4fcc185dbf08da8890768e49a64211770eb1ee800a8105c"
PRODUCER = "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
SCOPE = {
    "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
    "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
    "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
    "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f",
}
D = RAIZ / "cases/generalization/E20"
ART = json.loads((D / "SET_VALUED_SEMANTIC_PROPOSAL_CONTRACT.json").read_text())
MAN = json.loads((RAIZ / "cases/generalization/E19_1/eval_manifest.json").read_text())
A, F = "ARCHITECTURAL_ENCLOSURE", "FURNITURE_OBJECT"


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_el_banco_sigue_siendo_el_de_e19():
    """§3/§6 — si el banco cambio, E20 no es comparable y el veredicto seria E20-E."""
    assert _sha(RAIZ / "tests/fixtures/semantic_context/context_bench_scene.py") == BENCH_E19
    assert ART["identidad_con_e19"]["bench_sha256"] == BENCH_E19


def test_el_prompt_esta_congelado_y_hasheado():
    assert _sha(D / "prompt_e20_congelado.txt") == PROMPT_E20
    assert ART["prompt"]["sha256"] == PROMPT_E20
    assert ART["prompt"]["PROMPT_FROZEN"] is True


def test_el_prompt_no_menciona_ciclos_ni_errores_anteriores():
    """§8 — el prompt debe ser GENERAL."""
    t = (D / "prompt_e20_congelado.txt").read_text().lower()
    for prohibido in ("e19", "e18", "e17", "recall", "pod_aislado", "poche", "poché",
                      "gate", "benchmark result", "previous", "earlier"):
        assert prohibido not in t, prohibido


def test_el_contrato_de_salida_tiene_exactamente_los_cuatro_valores_permitidos():
    """§7 — singleton ARCH, singleton FURN, ambas, o vacio. Nada mas."""
    vistos = set()
    for s in ART["respuestas"].values():
        assert isinstance(s, list)
        assert all(x in (A, F) for x in s), s
        assert len(s) == len(set(s)), s
        assert len(s) <= 2
        vistos.add(tuple(sorted(s)))
    permitidos = {(), (A,), (F,), (A, F)}
    assert vistos <= permitidos, vistos


def test_hay_exactamente_72_respuestas_una_por_imagen_full_context():
    fc = [i for i in MAN["items"] if i["brazo"] == "FULL_CONTEXT"]
    assert len(fc) == 72
    assert set(ART["respuestas"]) == {i["id"] for i in fc}
    assert ART["protocolo"]["evaluaciones_independientes"] == 72
    assert ART["protocolo"]["una_imagen_por_evaluador"] is True
    assert ART["protocolo"]["batching"] == "NONE"


def test_target_only_no_se_uso():
    """§6 — TARGET_ONLY queda fuera del gate principal y no se ejecuto."""
    assert ART["identidad_con_e19"]["target_only"] == "NOT_USED_IN_E20"
    to = {i["id"] for i in MAN["items"] if i["brazo"] == "TARGET_ONLY"}
    assert not (set(ART["respuestas"]) & to)


@pytest.mark.parametrize("pid", [p[0] for p in B.pares()])
def test_el_target_sigue_siendo_byte_identico_dentro_del_par(pid):
    import numpy as np
    a, ca, la = B.render(pid, A)
    b, cb, lb = B.render(pid, F)
    assert ca == cb and la == 0 and lb == 0
    ha = hashlib.sha256(np.ascontiguousarray(B.crop(a, ca)).tobytes()).hexdigest()
    hb = hashlib.sha256(np.ascontiguousarray(B.crop(b, cb)).tobytes()).hexdigest()
    assert ha == hb == MAN["crops_sha256"][pid]


def test_e20_no_toca_el_motor():
    r = producer_freeze.read_worktree(str(RAIZ))
    # E24 — el literal ENGINE es el motor de ESTE ciclo y queda documentado en la cadena de
    # baselines. Lo que se comprueba hoy es que el motor está en el baseline VIGENTE: un ciclo
    # posterior puede moverlo a propósito, pero sólo declarando un baseline nuevo.
    assert engine_baseline.esta_en_la_cadena(ENGINE), "el motor de este ciclo salió de la cadena"
    assert freeze.manifest(str(RAIZ))["engine_hash"] == engine_baseline.engine_hash(), \
        "el motor cambió sin declarar un GENERIC_ENGINE_BASELINE.json nuevo"
    assert producer_freeze.producer_hash(r) == PRODUCER
    assert scope_guard.hashes(r) == SCOPE


def test_el_spike_vive_fuera_del_runtime():
    for py in (RAIZ / "src").rglob("*.py"):
        t = py.read_text()
        assert "context_bench_scene" not in t, py
        assert "semantic_context" not in t, py
    assert not list(D.glob("*.py")), "los scripts del spike deben guardarse como .txt"


def test_el_artefacto_declara_el_veredicto_y_los_gates():
    assert ART["variable_unica"] == "OUTPUT_DECISION_CONTRACT"
    assert ART["casos_reales"] == {"GPS": "NOT_OPENED", "RES": "NOT_OPENED", "tercer_plano": "CLOSED"}
    assert ART["provider"]["PROVIDER_IDENTITY"] == "UNKNOWN"
    assert ART["provider"]["PRODUCTION_REPRODUCIBILITY"] == "NOT_PROVEN"
    assert ART["verdict"].startswith("E20-B")
    g = ART["gates"]
    assert g["SINGLETON_RATE >= 0.60"] is False
    assert g["BOTH_RATE <= 0.40"] is False
    assert g["TRUE_ROLE_COVERAGE overall >= 0.95"] is True


def test_las_metricas_del_artefacto_se_recomputan_desde_las_respuestas():
    """El scoring no es prosa: se recalcula desde possible_roles y el ground truth."""
    por_id = {i["id"]: i for i in MAN["items"] if i["brazo"] == "FULL_CONTEXT"}
    n = len(ART["respuestas"])
    cov = sum(1 for k, s in ART["respuestas"].items() if por_id[k]["verdad"] in s) / n
    both = sum(1 for s in ART["respuestas"].values() if len(s) == 2) / n
    sing = [k for k, s in ART["respuestas"].items() if len(s) == 1]
    prec = sum(1 for k in sing if por_id[k]["verdad"] in ART["respuestas"][k]) / len(sing)
    M = ART["resultados"]["metricas"]
    assert round(cov, 4) == M["TRUE_ROLE_COVERAGE_overall"]
    assert round(both, 4) == M["BOTH_RATE"]
    assert round(len(sing) / n, 4) == M["SINGLETON_RATE"]
    assert round(prec, 4) == M["SINGLETON_PRECISION"]
