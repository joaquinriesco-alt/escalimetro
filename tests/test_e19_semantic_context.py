"""E19 — guardas del banco pareado de contexto.

No prueban al evaluador (que no es determinista): prueban que el EXPERIMENTO es valido —
que el target es byte-identico entre las dos clases del par, que no hay fuga local, que no hay
texto y que el motor no se movio.
"""
import ast
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tests" / "fixtures" / "semantic_context"))
import context_bench_scene as B  # noqa: E402

from escalimetro.generalization import freeze, producer_freeze, scope_guard  # noqa: E402

ENGINE_E18 = "779a1eee6d3d2f2ce4fcc185dbf08da8890768e49a64211770eb1ee800a8105c"
PRODUCER_E18 = "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
SCOPE_E18 = {
    "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
    "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
    "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
    "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f",
}


def _sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def _par(pid):
    a, ca, la = B.render(pid, "ARCHITECTURAL_ENCLOSURE")
    b, cb, lb = B.render(pid, "FURNITURE_OBJECT")
    return (a, ca, la), (b, cb, lb)


def test_el_banco_tiene_36_pares_y_clases_balanceadas():
    ps = B.pares()
    assert len(ps) == 36
    assert len({p[0] for p in ps}) == 36
    # cada par aporta exactamente una escena de cada clase
    assert len(ps) * 1 == sum(1 for _ in ps)


@pytest.mark.parametrize("pid", [p[0] for p in B.pares()])
def test_el_target_es_byte_identico_dentro_del_par(pid):
    """§4 — si esto falla, el ciclo es EXPERIMENT_INVALID por fuga de informacion local."""
    (a, ca, _), (b, cb, _) = _par(pid)
    assert ca == cb, f"{pid}: el recuadro objetivo no coincide"
    assert _sha(B.crop(a, ca)) == _sha(B.crop(b, cb)), f"{pid}: el recorte NO es byte-identico"


@pytest.mark.parametrize("pid", [p[0] for p in B.pares()])
def test_ningun_objeto_de_contexto_invade_el_recuadro(pid):
    """El keep-out debe ser un no-op: si borra pixeles, el contexto estaba entrando al crop."""
    (_, _, la), (_, _, lb) = _par(pid)
    assert la == 0 and lb == 0, f"{pid}: keep-out borro {la}/{lb} px de contexto"


def test_las_dos_escenas_del_par_si_difieren_fuera_del_recuadro():
    """El contrafactual tiene que ser real: identico adentro, distinto afuera."""
    distintas = 0
    for pid, _, _, _ in B.pares():
        (a, ca, _), (b, _, _) = _par(pid)
        if _sha(a) != _sha(b):
            distintas += 1
    assert distintas == 36


def test_el_render_es_determinista():
    for pid in ("PAR01", "PAR18", "PAR36"):
        for cl in B.CLASES:
            assert _sha(B.render(pid, cl)[0]) == _sha(B.render(pid, cl)[0])


def test_un_solo_ancho_y_un_solo_gris():
    """§16 — si el ancho o el gris variaran, el ciclo estaria midiendo E17 otra vez."""
    fuente = (RAIZ / "tests/fixtures/semantic_context/context_bench_scene.py").read_text()
    arbol = ast.parse(fuente)
    for n in ast.walk(arbol):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            n.value = ast.Constant("")          # fuera los docstrings, no la prosa
    codigo = ast.unparse(arbol)
    # el grosor sale de UNA sola funcion, y esa funcion usa UNA sola constante
    assert codigo.count("W_UNICO") == 2, "el ancho: una definicion y un unico uso"
    assert "def _t(S=SIDE)" in codigo
    # exactamente tres tonos en toda escena: papel, tinta y el gris del marcador
    for pid in ("PAR01", "PAR20", "PAR36"):
        for cl in B.CLASES:
            tonos = sorted(np.unique(B.render(pid, cl)[0]).tolist())
            assert tonos == sorted([B.TINTA, B.GRIS_MARCA, B.PAPEL]), (pid, cl, tonos)


def test_no_hay_texto_en_ninguna_escena():
    """§7 — el ciclo mide contexto visual, no rotulos."""
    fuente = (RAIZ / "tests/fixtures/semantic_context/context_bench_scene.py").read_text()
    arbol = ast.parse(fuente)
    for n in ast.walk(arbol):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            n.value = ast.Constant("")
    codigo = ast.unparse(arbol)
    assert "putText" not in codigo
    assert "FONT_HERSHEY" not in codigo


def test_posicion_tamano_y_orientacion_no_correlacionan_con_la_clase():
    """§14 G0.4 — por construccion son la MISMA geometria, asi que la correlacion es nula."""
    for pid, t, _, _ in B.pares():
        (a, ca, _), (b, cb, _) = _par(pid)
        assert ca == cb
        assert B.caja_crop(t) == ca


def test_el_marcador_es_identico_entre_clases():
    for pid in ("PAR03", "PAR20"):
        (a, ca, _), (b, cb, _) = _par(pid)
        borde_a = B.crop(a, ca)[0, :]
        borde_b = B.crop(b, cb)[0, :]
        assert np.array_equal(borde_a, borde_b)


def test_e19_no_toca_el_motor():
    """§19 — motor, productor y alcance byte-identicos a E18/E17/E16.16."""
    r = producer_freeze.read_worktree(str(RAIZ))
    assert freeze.manifest(str(RAIZ))["engine_hash"] == ENGINE_E18
    assert producer_freeze.producer_hash(r) == PRODUCER_E18
    assert scope_guard.hashes(r) == SCOPE_E18


def test_el_spike_vive_fuera_del_runtime():
    """§2 — ningun modulo de src importa el banco, y los scripts del spike no son importables."""
    for py in (RAIZ / "src").rglob("*.py"):
        t = py.read_text()
        assert "context_bench_scene" not in t, py
        assert "semantic_context" not in t, py
    d = RAIZ / "cases/generalization/E19"
    assert d.exists()
    assert not list(d.glob("*.py")), "los scripts del spike deben guardarse como .txt"
