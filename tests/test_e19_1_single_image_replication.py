"""E19.1 — guardas de INTEGRIDAD de la replicacion.

E19.1 no crea banco: reusa el de E19 sin tocar un byte. Estos tests prueban exactamente eso —
que el banco, el prompt, las imagenes y el ground truth son los mismos, y que el motor no se movio.
No prueban al evaluador, que no es determinista.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tests" / "fixtures" / "semantic_context"))
import context_bench_scene as B  # noqa: E402

import engine_baseline  # noqa: E402
from escalimetro.generalization import freeze, producer_freeze, scope_guard  # noqa: E402

BENCH_E19 = "2b3e2eb06248f3897b4bf663ce39930fc111b59560ccffd7cac8478141be6f81"
PROMPT_E19 = "2ac0dac653c8755fde3548ba2831a18908bb9db8c2588d731c4e48549cc0656d"
ENGINE = "779a1eee6d3d2f2ce4fcc185dbf08da8890768e49a64211770eb1ee800a8105c"
PRODUCER = "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
SCOPE = {
    "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
    "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
    "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
    "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f",
}
MAN = json.loads((RAIZ / "cases/generalization/E19_1/eval_manifest.json").read_text())


def _sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_el_banco_es_byte_identico_al_de_e19():
    """§2/§3 — si esto falla, E19.1 no es replicacion y el veredicto es D."""
    assert _sha_file(RAIZ / "tests/fixtures/semantic_context/context_bench_scene.py") == BENCH_E19


def test_el_prompt_es_byte_identico_al_de_e19():
    assert _sha_file(RAIZ / "cases/generalization/E19/prompt_congelado.txt") == PROMPT_E19


def test_el_manifiesto_declara_el_mismo_banco_y_prompt():
    assert MAN["bench_sha256"] == BENCH_E19
    assert MAN["prompt_sha256"] == PROMPT_E19


def test_el_manifiesto_tiene_las_108_imagenes_y_el_mismo_mapping():
    items = MAN["items"]
    assert len(items) == 108
    assert len({i["id"] for i in items}) == 108
    assert sum(1 for i in items if i["brazo"] == "FULL_CONTEXT") == 72
    assert sum(1 for i in items if i["brazo"] == "TARGET_ONLY") == 36
    pares = {p[0] for p in B.pares()}
    assert {i["pid"] for i in items} == pares
    for cl in B.CLASES:
        assert sum(1 for i in items if i["verdad"] == cl) == 36


@pytest.mark.parametrize("pid", [p[0] for p in B.pares()])
def test_las_imagenes_se_regeneran_con_el_mismo_sha(pid):
    """Las 108 imagenes no se versionan: se regeneran byte-exactas desde el generador congelado."""
    por = {(i["pid"], i["brazo"], i.get("verdad")): i for i in MAN["items"]}
    with tempfile.TemporaryDirectory() as d:
        for cl in B.CLASES:
            img, caja, leak = B.render(pid, cl)
            assert leak == 0
            p = Path(d) / "x.png"
            cv2.imwrite(str(p), img)
            assert _sha_file(p) == por[(pid, "FULL_CONTEXT", cl)]["sha_img"], (pid, cl)
        img, caja, _ = B.render(pid, "ARCHITECTURAL_ENCLOSURE")
        p = Path(d) / "c.png"
        cv2.imwrite(str(p), B.crop(img, caja))
        assert _sha_file(p) == por[(pid, "TARGET_ONLY", "PAR")]["sha_img"], pid


@pytest.mark.parametrize("pid", [p[0] for p in B.pares()])
def test_el_target_sigue_siendo_byte_identico_dentro_del_par(pid):
    a, ca, _ = B.render(pid, "ARCHITECTURAL_ENCLOSURE")
    b, cb, _ = B.render(pid, "FURNITURE_OBJECT")
    assert ca == cb
    ha = hashlib.sha256(np.ascontiguousarray(B.crop(a, ca)).tobytes()).hexdigest()
    hb = hashlib.sha256(np.ascontiguousarray(B.crop(b, cb)).tobytes()).hexdigest()
    assert ha == hb == MAN["crops_sha256"][pid]


def test_e19_1_no_toca_el_motor():
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
    d = RAIZ / "cases/generalization/E19_1"
    assert d.exists()
    assert not list(d.glob("*.py")), "los scripts del spike deben guardarse como .txt"


def test_el_artefacto_declara_el_veredicto_y_la_variable_unica():
    a = json.loads((RAIZ / "cases/generalization/E19_1/"
                    "SINGLE_IMAGE_BLIND_CONTEXT_REPLICATION.json").read_text())
    assert a["variable_unica"] == "BATCH_SIZE"
    assert a["batch_size"] == {"E19": 6, "E19_1": 1}
    assert a["protocolo"]["evaluaciones_independientes"] == 108
    assert a["protocolo"]["una_imagen_por_evaluador"] is True
    assert a["casos_reales"] == {"GPS": "NOT_OPENED", "RES": "NOT_OPENED", "tercer_plano": "CLOSED"}
    assert a["provider"]["PROVIDER_IDENTITY"] == "UNKNOWN"
    assert a["provider"]["PRODUCTION_REPRODUCIBILITY"] == "NOT_PROVEN"
    assert a["verdict"].startswith("B - SINGLE-IMAGE CONTEXT REPLICATION PARTIAL")
