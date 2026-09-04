"""E14 — tests del gate de generalización.

Sólo lo necesario (§30): el manifiesto congelado, el chequeo de cero tuning, el esquema del segundo
shell, que no haya mutación específica de caso, la scorecard, y la distinción entre NO_FIT y
SOLVER_FAILURE. Ningún test del motor se toca."""
import json
import os

import pytest

from escalimetro.generalization.freeze import compare, engine_files, manifest
from escalimetro.generalization.scorecard import RESULTS, build

ROOT = os.path.dirname(os.path.dirname(__file__))
E14 = os.path.join(ROOT, "cases", "generalization", "E14")
BEFORE = "FROZEN_ENGINE_MANIFEST_BEFORE.json"
AFTER = "FROZEN_ENGINE_MANIFEST_AFTER.json"
SHELL2 = os.path.join(ROOT, "cases", "002_gps_401")
EXPECTED_403 = {"A": "df6b86058ebb", "B": "5c5c276923dd", "C": "e12cc722485b"}


def _j(*p):
    return json.load(open(os.path.join(*p), encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------
# freeze manifest
# ---------------------------------------------------------------------------------------------------
def test_el_manifiesto_cubre_el_motor_y_excluye_las_herramientas_de_e14():
    files = engine_files(ROOT)
    assert any(f.endswith(os.path.join("layout", "solver.py")) for f in files)
    assert any("strategies.py" in f for f in files)
    assert any(f.endswith("modules_office.json") for f in files)
    assert not any(os.path.join("escalimetro", "generalization") in f for f in files)


def test_el_manifiesto_no_contiene_secretos():
    m = _j(E14, BEFORE)
    blob = json.dumps(m).lower()
    for bad in ("api_key", "sk-", "token", "password", "secret"):
        assert bad not in blob


def test_el_manifiesto_es_reproducible():
    a = manifest(ROOT, "x", "")
    b = manifest(ROOT, "y", "")
    assert a["engine_hash"] == b["engine_hash"]
    assert a["file_hashes"] == b["file_hashes"]


def test_compare_detecta_cualquier_cambio():
    a = manifest(ROOT, "", "")
    b = json.loads(json.dumps(a))
    k = sorted(b["file_hashes"])[0]
    b["file_hashes"][k] = "0" * 64
    c = compare(a, b)
    assert c["identical"] is False and c["changed"] == [k]


# ---------------------------------------------------------------------------------------------------
# zero tuning — el chequeo que decide si E14 es válido
# ---------------------------------------------------------------------------------------------------
def test_el_motor_no_cambio_durante_e14():
    """Hecho HISTÓRICO: durante E14, sobre el commit 85c8cb1, el motor entró y salió idéntico."""
    before, after = _j(E14, BEFORE), _j(E14, AFTER)
    c = compare(before, after)
    assert c["identical"] is True, f"E14 INVALID: {c['changed']}"
    assert c["engine_hash_before"] == c["engine_hash_after"]


def test_el_chequeo_guardado_dice_identical():
    assert _j(E14, "engine_freeze_check.json")["identical"] is True


def test_el_freeze_de_e14_no_congela_el_desarrollo_futuro():
    """E15 — corrección de semántica del freeze.

    El test anterior comparaba EL MOTOR DE HOY contra el hash congelado en E14. Eso convertía un
    experimento histórico en una cárcel permanente: cualquier cambio legítimo posterior rompía la
    suite y obligaba a elegir entre evolucionar el producto o mantener E14 "válido".

    Lo que E14 debía probar es un hecho del pasado —motor antes == motor después, DURANTE el
    experimento— y eso lo prueba `test_el_motor_no_cambio_durante_e14`, que sigue verde y seguirá
    verde para siempre porque compara dos manifiestos guardados, no el código de hoy.

    Este test afirma explícitamente lo contrario del anterior: que el motor de hoy PUEDE diferir del
    de E14 sin que eso invalide nada. Si algún día vuelven a coincidir tampoco pasa nada; lo que no
    puede volver a existir es una aserción que exija la igualdad."""
    hist = _j(E14, BEFORE)
    now = manifest(ROOT, "", "")
    c = compare(hist, now)
    assert isinstance(c["identical"], bool)          # la herramienta funciona
    assert _j(E14, "engine_freeze_check.json")["identical"] is True   # el hecho histórico sigue en pie


def test_la_herramienta_freeze_detecta_una_mutacion_simulada():
    """§5 — lo que el test histórico sí debe seguir demostrando: que el instrumento sirve."""
    a = manifest(ROOT, "", "")
    b = json.loads(json.dumps(a))
    k = sorted(b["file_hashes"])[0]
    b["file_hashes"][k] = "f" * 64
    c = compare(a, b)
    assert c["identical"] is False and k in c["changed"]


# ---------------------------------------------------------------------------------------------------
# segundo shell — esquema y ausencia de trampa
# ---------------------------------------------------------------------------------------------------
def test_el_segundo_shell_usa_el_mismo_contrato_floorplate():
    a = _j(ROOT, "cases", "001_gps_403", "outputs", "floorplate.json")
    b = _j(SHELL2, "outputs", "floorplate.json")
    assert a["schema_version"] == b["schema_version"]
    assert set(a.keys()) == set(b.keys()), "E14 no puede inventar un esquema propio"


def test_el_segundo_shell_es_la_misma_imagen_fuente():
    a = _j(ROOT, "cases", "001_gps_403", "outputs", "floorplate.json")["source_image"]
    b = _j(SHELL2, "outputs", "floorplate.json")["source_image"]
    assert a["sha256"] == b["sha256"], "la lámina debe ser idéntica: es generalización INTRA-DRAWING"


def test_el_case_json_solo_cambia_la_identidad_del_inmueble():
    """E14 cambió tres campos de identidad más la nota de imagen. E15 agregó metadatos de caso
    (source_name, sibling_units, fit_verdict), que son datos del inmueble y no parámetros del motor:
    se listan aparte para que la aserción siga diciendo lo que decía."""
    a = _j(ROOT, "cases", "001_gps_403", "case.json")
    b = _j(SHELL2, "case.json")
    E15_METADATA = {"source_name", "sibling_units", "fit_verdict", "display_name"}
    diff = {k for k in set(a) | set(b) if a.get(k) != b.get(k)} - E15_METADATA
    assert diff == {"case_id", "unit_label", "known_area_m2", "image_note"}, diff
    # los parámetros del pipeline siguen idénticos entre los dos casos: una sola variable
    for k in ("vision", "segmentation", "simplify_eps_frac", "mask_open_px"):
        assert a[k] == b[k], k


def test_no_se_transfirio_geometria_de_403():
    """§7: ni perímetro, ni columnas, ni accesos copiados. Ninguna coordenada puede coincidir."""
    a = _j(ROOT, "cases", "001_gps_403", "outputs", "floorplate.json")
    b = _j(SHELL2, "outputs", "floorplate.json")
    ra = {tuple(p) for p in a["perimeter"]["ring"]}
    rb = {tuple(p) for p in b["perimeter"]["ring"]}
    assert not (ra & rb), "vértices compartidos: hubo transferencia"
    ea = {tuple(e["point"]) for e in a["entrances"]}
    eb = {tuple(e["point"]) for e in b["entrances"]}
    assert not (ea & eb), "accesos compartidos: hubo transferencia"


def test_el_segundo_shell_no_reutiliza_los_overrides_de_403():
    o = _j(SHELL2, "overrides_assisted.json")
    o403 = _j(ROOT, "cases", "001_gps_403", "overrides_assisted.json")
    pts = {tuple(c["center"]) for c in o.get("columns", {}).get("add", [])}
    pts403 = {tuple(c["center"]) for c in o403.get("columns", {}).get("add", [])}
    assert not (pts & pts403)


def test_hitl_dentro_del_maximo():
    o = _j(SHELL2, "overrides_assisted.json")
    assert o["_hitl_total_ops"] == len(o["_hitl_log"]) <= 10
    kinds = {op["kind"] for op in o["_hitl_log"]}
    prohibidas = {"draw_layout", "move_room", "place_room", "edit_solver", "manual_fit"}
    assert not (kinds & prohibidas)


# ---------------------------------------------------------------------------------------------------
# NO_FIT vs SOLVER_FAILURE — la distinción crítica (§16)
# ---------------------------------------------------------------------------------------------------
def test_el_resultado_es_no_fit_y_no_un_crash():
    s = _j(E14, "solver_result.json")
    assert s["result"] == "TECHNICAL_NO_FIT"
    m = s["metrics"]
    assert m["collisions"] == 0                       # geometría válida: no es representación rota
    assert m["circulation_connectivity"] is True
    assert m["candidate_count"] == 12                 # el catálogo no quedó vacío
    assert m["valid_candidate_count"] == 0            # ninguno cumple: eso es NO_FIT
    assert m["hard_constraint_violations"] > 0


def test_el_diagnostico_separa_evidencia_de_inferencia():
    d = _j(E14, "no_fit_diagnostic.json")
    assert d["evidence"] and d["inference"]
    for i in d["inference"]:
        assert i["confidence"] in ("ALTA", "MEDIA", "BAJA", "NO VERIFICADA")


def test_el_sweep_uso_los_rangos_de_e06_sin_modificar():
    from escalimetro.layout.e06.scale import DEFAULT_FACTORS
    r = _j(E14, "robustness.json")
    assert r["factors_tested"] == list(DEFAULT_FACTORS)
    assert r["exact_fit_factors"] == []


def test_no_se_generaron_alternativas_abc():
    """§29: sin FIT no hay A/B/C, y no se fabrica ninguna planta para llenar el hueco."""
    assert not os.path.isdir(os.path.join(SHELL2, "layouts", "E07"))
    assert os.path.exists(os.path.join(E14, "visuals", "07b_abc_not_generated.png"))


# ---------------------------------------------------------------------------------------------------
# scorecard
# ---------------------------------------------------------------------------------------------------
def _args(**kw):
    base = dict(shell_available=True, localization="assisted", shell_ready="ASSISTED_READY",
                hitl_ops=10, solver_ran=True, solver_result="TECHNICAL_NO_FIT", collisions=0,
                circulation_ok=True, hard_violations_coherent=True, semantics_ok=True,
                engine_identical=True, runtime={"solver": 166.0})
    base.update(kw)
    return base


def test_no_fit_no_penaliza_el_gate():
    """§22 — se valida el motor, no la capacidad del inmueble."""
    fit = build(**_args(solver_result="TECHNICAL_FIT"))
    nofit = build(**_args(solver_result="TECHNICAL_NO_FIT"))
    assert fit["result"] == nofit["result"] == "ASSISTED_GENERALIZATION_PASS"


def test_un_crash_si_penaliza():
    assert build(**_args(solver_result="SOLVER_FAILURE"))["result"] == "GENERALIZATION_FAIL"


def test_tuning_invalida_el_pass():
    assert build(**_args(engine_identical=False))["result"] == "GENERALIZATION_FAIL"


def test_sin_hitl_seria_pass_completo():
    assert build(**_args(localization="auto", shell_ready="AUTO_READY",
                         hitl_ops=0))["result"] == "GENERALIZATION_PASS"


def test_sin_shell_es_insufficient_input():
    assert build(**_args(shell_available=False))["result"] == "INSUFFICIENT_INPUT"


def test_no_existe_una_quinta_categoria():
    assert len(RESULTS) == 4
    for kw in ({}, {"solver_result": "SOLVER_FAILURE"}, {"engine_identical": False},
               {"shell_available": False}, {"localization": "auto", "shell_ready": "AUTO_READY"}):
        assert build(**_args(**kw))["result"] in RESULTS


def test_el_resultado_guardado_es_el_esperado():
    sc = _j(E14, "scorecard.json")
    assert sc["result"] == "ASSISTED_GENERALIZATION_PASS"
    assert sc["generalization_level"] == "INTRA-DRAWING"
    assert {c["id"] for c in sc["checks"]} == {f"G{i}" for i in range(8)}


# ---------------------------------------------------------------------------------------------------
# regresión del caso 403
# ---------------------------------------------------------------------------------------------------
def test_la_geometria_de_403_no_cambio():
    g = _j(ROOT, "cases", "001_gps_403", "ai", "E09", "geometry_hash_check.json")
    assert g["identical"] is True
    for a, pref in EXPECTED_403.items():
        assert g["geometry_hash_before"][a].startswith(pref)
        assert g["geometry_hash_before"][a] == g["geometry_hash_after"][a]


# ---------------------------------------------------------------------------------------------------
# auditoría de acoplamiento — se reporta, no se corrige
# ---------------------------------------------------------------------------------------------------
def test_la_auditoria_de_overfitting_clasifica_todo():
    a = _j(E14, "overfitting_audit.json")
    for f in a["findings"]:
        assert f["classification"] in ("BENIGN", "CASE_COUPLING_RISK", "CONFIRMED_CASE_COUPLING")
        assert f["file"] and f["impact"]
    assert a["summary"]["CONFIRMED_CASE_COUPLING"] >= 1


def test_el_acoplamiento_confirmado_de_e14_fue_corregido_en_e15():
    """Este test decía lo contrario hasta E15, y con razón: durante E14 el acoplamiento TENÍA que
    seguir presente, porque corregirlo habría cambiado el motor en mitad del experimento.

    E15 es un ciclo posterior cuyo encargo explícito es eliminarlo. La aserción se invierte, no se
    borra: sigue vigilando la misma línea, ahora en la dirección correcta. El hallazgo de E14 queda
    registrado en `overfitting_audit.json`, que no se toca."""
    src = open(os.path.join(ROOT, "src", "escalimetro", "layout", "run.py"), encoding="utf-8").read()
    assert "shell_semantics_403.png" not in src
    audit = _j(E14, "overfitting_audit.json")
    of01 = next(f for f in audit["findings"] if f["id"] == "OF01")
    assert of01["classification"] == "CONFIRMED_CASE_COUPLING"   # el hallazgo histórico intacto
