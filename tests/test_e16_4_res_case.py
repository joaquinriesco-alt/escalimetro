"""E16.4 — el segundo dibujo real (RES) y el registro honesto de su examen.

Estos tests NO afirman que el caso 003 deba dar FIT ni NO_FIT. El resultado del examen se descubre,
no se impone. Lo que fijan es el contrato del experimento: que el input es independiente, que el caso
respeta el contrato de entrada vigente, que no hereda identidad ni resultados de 403/401, que el
motor no cambió, y que un caso sin evidencia computada declara `NOT_EVALUATED` en vez de inventar."""
import hashlib
import json
import os

import pytest

from escalimetro import fit_evidence as FE
from escalimetro.case_context import from_case_dir, validate_case_input
from escalimetro.generalization import freeze

ROOT = os.path.dirname(os.path.dirname(__file__))
C403 = os.path.join(ROOT, "cases", "001_gps_403")
C401 = os.path.join(ROOT, "cases", "002_gps_401")
CRES = os.path.join(ROOT, "cases", "003_res_unknown")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")

RES_SHA = "9c5429109cc0073b71bb46780489d0061c9cf0e3726a84d54b90ade1c286c916"
GPS_SHA = "89546a14dd941bd7c17e985bf316b43141583f51cf7cff74d4b45c4525cabb02"
PROG_SHA = "6f21f50330110b7c4d43b5c0cfe7d6587f7ee0827482d76e00df26a382f56107"
ENGINE_E16_1 = "a6ee3213b6994897aaa16c0852e2079a5eab0b1750f55db4b1d670a39d3c07fa"


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _j(p):
    return json.load(open(p, encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------
# procedencia e independencia del input
# ---------------------------------------------------------------------------------------------------
def test_el_original_de_res_es_el_archivo_congelado():
    assert _sha(os.path.join(CRES, "original.png")) == RES_SHA


def test_res_no_es_el_mismo_dibujo_que_gps():
    """El hallazgo de E16 fue que 403 y 401 comparten archivo. Este es el primero que no."""
    assert _sha(os.path.join(CRES, "original.png")) != _sha(os.path.join(C403, "original.png"))
    assert _sha(os.path.join(C403, "original.png")) == _sha(os.path.join(C401, "original.png"))


def test_el_programa_sigue_congelado():
    assert _sha(PROG) == PROG_SHA


# ---------------------------------------------------------------------------------------------------
# contrato de entrada
# ---------------------------------------------------------------------------------------------------
def test_el_caso_res_pasa_el_contrato_de_entrada_vigente():
    validate_case_input(_j(os.path.join(CRES, "case.json")), "cases/003_res_unknown/case.json")


def test_no_se_introdujo_ningun_campo_de_entrada_nuevo():
    """§12 de E16.3: private_offices y bathrooms son hechos del plano, no del contrato."""
    from escalimetro.case_context import CASE_INPUT_FIELDS
    d = _j(os.path.join(CRES, "case.json"))
    declarados = {k for k in d if not k.startswith("_")}
    assert declarados <= CASE_INPUT_FIELDS
    assert "private_offices" not in declarados and "bathrooms" not in declarados


def test_los_hechos_de_origen_son_los_declarados():
    ctx = from_case_dir(CRES)
    assert ctx.source_name == "RES Real Estate Services"
    assert ctx.published_area_m2 == 608.12
    assert ctx.published_area_kind == "useful"
    assert ctx.unit_label == "UNKNOWN"


def test_unit_label_unknown_no_inventa_una_unidad():
    """UNKNOWN es declarar ignorancia. Ningún rótulo comercial fabricado."""
    ctx = from_case_dir(CRES)
    assert ctx.slug == "UNKNOWN"
    for inventado in ("Oficina 608", "Oficina 003", "Unidad RES", "Piso"):
        assert inventado not in json.dumps(_j(os.path.join(CRES, "case.json")), ensure_ascii=False)


# ---------------------------------------------------------------------------------------------------
# estado del resultado: ausencia declarada, no resultado inventado
# ---------------------------------------------------------------------------------------------------
def test_el_caso_res_no_declara_un_veredicto_que_no_produjo():
    ev = FE.load(CRES, PROG)
    assert ev.technical == FE.TECHNICAL_NOT_EVALUATED
    assert ev.robustness == FE.ROBUSTNESS_NOT_EVALUATED
    assert ev.source_artifacts == []
    assert ev.evaluated is False and ev.presentable is False


def test_la_frescura_no_es_legacy_verified():
    """§32 — LEGACY_VERIFIED es para evidencia histórica. Aquí no hay evidencia, punto."""
    assert FE.load(CRES, PROG).freshness != FE.LEGACY_VERIFIED
    assert FE.load(CRES, PROG).freshness == FE.FRESHNESS_NOT_EVALUATED


def test_el_registro_del_run_documenta_el_fallo_sin_maquillarlo():
    r = _j(os.path.join(CRES, "outputs", "RUN_001_FAILURE.json"))
    assert r["runs_total"] == 1, "una sola corrida: no hubo best-of-N"
    assert r["outcome"] == "C_GENERALIZATION_FAILURE"
    assert r["root_failure_stage"] == "STAGE_1_2_LOCALIZATION"
    assert r["frozen"]["engine_hash"] == ENGINE_E16_1
    assert r["frozen"]["input_image_sha256"] == RES_SHA
    assert r["frozen"]["program_sha256"] == PROG_SHA
    assert all(v is False for v in r["human_intervention"].values())
    for etapa, estado in r["downstream"].items():
        assert estado in ("NOT_RUN", "NOT_EVALUATED"), (etapa, estado)


# ---------------------------------------------------------------------------------------------------
# aislación
# ---------------------------------------------------------------------------------------------------
def test_el_caso_res_no_hereda_identidad_ni_resultados_de_gps():
    ctx = from_case_dir(CRES)
    from escalimetro.fit_evidence import PresentationFit
    p = PresentationFit.from_evidence(ctx, FE.load(CRES, PROG))
    blob = json.dumps(p.to_dict(), ensure_ascii=False)
    for t in ("403", "401", "543", "252", "GPS Property", "ROBUST_FIT", "ROBUST_NO_FIT",
              "ROBUST WITHIN", "NO_FIT"):
        assert t not in blob, t
    assert "608.12" in blob or "608" in blob
    assert "RES Real Estate Services" in blob


def test_los_outputs_de_res_solo_mencionan_gps_en_el_bloque_de_comparacion():
    r = _j(os.path.join(CRES, "outputs", "RUN_001_FAILURE.json"))
    assert r["comparison_drawing_1"]["case"] == "001_gps_403"
    del r["comparison_drawing_1"]
    blob = json.dumps(r, ensure_ascii=False)
    for t in ("001_gps_403", "002_gps_401", "GPS Property", "df6b86058ebb"):
        assert t not in blob, t


# ---------------------------------------------------------------------------------------------------
# el motor no cambió, y los casos anteriores tampoco
# ---------------------------------------------------------------------------------------------------
def test_el_motor_coincide_con_el_baseline_vigente_declarado():
    """E16.5 — CAMBIO INTENCIONAL. Este test pinchaba el hash de E16.1, y E16.5 cambia el motor a
    propósito (la localización pasó a soportar dibujos de planta completa). Pincharlo a un literal
    obligaría a editarlo cada ciclo y dejaría de detectar lo que importa: que alguien toque el motor
    SIN declarar un baseline nuevo. Ahora compara contra el baseline vigente en disco."""
    import glob
    baselines = sorted(glob.glob(os.path.join(ROOT, "cases", "generalization", "*",
                                              "GENERIC_ENGINE_BASELINE.json")),
                       key=os.path.getmtime)
    vigente = _j(baselines[-1])
    assert freeze.manifest()["engine_hash"] == vigente["engine_hash"], \
        "el motor cambió sin crear un baseline nuevo"
    assert vigente["engine_hash"] != ENGINE_E16_1, "E16.5 debe haber avanzado el baseline"


def test_403_sigue_intacta():
    ev = FE.load(C403, PROG)
    assert (ev.technical, ev.robustness, ev.freshness) == (FE.FIT, FE.ROBUST_FIT, FE.LEGACY_VERIFIED)
    g = _j(os.path.join(C403, "ai", "E09", "geometry_hash_check.json"))
    assert g["geometry_hash_before"]["A"] == \
        "df6b86058ebb093f449e1054a0c65a902b7492f7986f4b8395489d63d46d7b99"
    assert all(g["geometry_hash_before"][a] == g["geometry_hash_after"][a] for a in "ABC")


def test_401_sigue_intacta():
    ev = FE.load(C401, PROG)
    assert (ev.technical, ev.robustness, ev.freshness) == (FE.NO_FIT, FE.ROBUST_NO_FIT,
                                                           FE.LEGACY_VERIFIED)
    ctx = from_case_dir(C401)
    assert (ctx.unit_label, ctx.source_name, ctx.published_area_m2) == \
           ("Oficina 401", "GPS Property", 252.0)
