"""E23 — invariantes de PRODUCTO del MVP V1 shell-only.

E23 no cambia runtime: audita y fija contrato. Estos tests no miden salud de ingeniería
(de eso ya hay 1036); miden que las AFIRMACIONES DE PRODUCTO del informe E23 sigan siendo
ciertas contra los artefactos reales. Si alguien cambia el motor y el 403 deja de producir
tres alternativas válidas, esto se pone rojo.
"""
import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import engine_baseline  # noqa: E402
from escalimetro.generalization import freeze, producer_freeze, scope_guard  # noqa: E402

ENGINE = "779a1eee6d3d2f2ce4fcc185dbf08da8890768e49a64211770eb1ee800a8105c"
PRODUCER = "cacc3636ee14928d2eada9c63103081d305511b73b6716cc48ef2fe8fb38a5a3"
SCOPE = {
    "CONTRACT": "031bea3d7b96c2bfa2990160c982a0a8f7448da12f53e0c137977b2e74e550ee",
    "WALL_EVIDENCE": "9c8db1516771271dd25d4f4fb2cf128b978dcc9c2c378c3a7b94d08add1f23fd",
    "SEMANTIC_HINT": "dc8547bc7ad0c3dd05bb926c37d53d2ee156383157be9f2a807799a21870fa13",
    "DOWNSTREAM": "1d6b13664f9c71f79e581915fa24ac620d153541d427eafdc793762a0586507f",
}
C = RAIZ / "contracts"
GPS = RAIZ / "cases/001_gps_403"
G401 = RAIZ / "cases/002_gps_401"
RES = RAIZ / "cases/003_res_unknown"


def _j(p):
    return json.loads(Path(p).read_text())


# ------------------------------------------------ E23 no toca runtime

def test_e23_no_toca_el_motor():
    """§26 — src/escalimetro/** = cero cambios. E23 es auditoría y contrato."""
    r = producer_freeze.read_worktree(str(RAIZ))
    # E24 — el literal ENGINE es el motor de ESTE ciclo y queda documentado en la cadena de
    # baselines. Lo que se comprueba hoy es que el motor está en el baseline VIGENTE: un ciclo
    # posterior puede moverlo a propósito, pero sólo declarando un baseline nuevo.
    assert engine_baseline.esta_en_la_cadena(ENGINE), "el motor de este ciclo salió de la cadena"
    assert freeze.manifest(str(RAIZ))["engine_hash"] == engine_baseline.engine_hash(), \
        "el motor cambió sin declarar un GENERIC_ENGINE_BASELINE.json nuevo"
    assert producer_freeze.producer_hash(r) == PRODUCER
    assert scope_guard.hashes(r) == SCOPE


def test_el_esquema_del_contrato_sigue_viviendo_fuera_del_runtime():
    """E23 dejó los contratos como ESPECIFICACIÓN (JSON Schema), fuera de src/, para no mover el hash
    del motor mientras se decidía el alcance de V1.

    E24 §11 los IMPLEMENTA a propósito: `src/escalimetro/shell_input/` es runtime y el hash del motor
    se mueve, con baseline declarado (cases/generalization/E24/GENERIC_ENGINE_BASELINE.json). Lo que
    sigue en pie —y es lo que este test comprueba— es que el ESQUEMA no se copió dentro del código:
    hay una sola definición del contrato, en contracts/, y el runtime la valida contra ella."""
    assert C.is_dir()
    assert not list(C.glob("*.py")), "el contrato se define en JSON Schema, no en Python"
    esquema = (C / "shell_input_v1.schema.json").read_text(encoding="utf-8")
    for py in (RAIZ / "src").rglob("*.py"):
        t = py.read_text(encoding="utf-8")
        assert '"$id": "escalimetro/contracts/shell_input_v1' not in t, (py, "esquema duplicado en runtime")
        assert esquema[:200] not in t, (py, "el contrato se copió dentro del runtime")
    # y el runtime declara la MISMA versión de contrato que el esquema, sin redefinirlo
    from escalimetro.shell_input import CONTRACT_VERSION, VERDICTS
    esq = _j(C / "shell_input_v1.schema.json")
    assert CONTRACT_VERSION == esq["properties"]["contract_version"]["const"]
    assert set(VERDICTS) == set(esq["properties"]["verdict"]["enum"])


# ------------------------------------------------ contratos V1

def test_el_contrato_de_input_v1_existe_y_es_json_schema_valido():
    s = _j(C / "shell_input_v1.schema.json")
    assert s["$schema"].startswith("http://json-schema.org/draft-07")
    assert s["properties"]["contract_version"]["const"] == "shell_input_v1"


def test_el_contrato_de_input_declara_exactamente_los_cuatro_veredictos():
    """§7 — SHELL_ACCEPTED / INPUT_NOT_READY / INVALID_INPUT / SCALE_UNRESOLVED."""
    s = _j(C / "shell_input_v1.schema.json")
    assert sorted(s["properties"]["verdict"]["enum"]) == sorted(
        ["SHELL_ACCEPTED", "INPUT_NOT_READY", "INVALID_INPUT", "SCALE_UNRESOLVED"])


def test_el_contrato_de_input_cubre_los_siete_criterios_de_aceptacion():
    s = _j(C / "shell_input_v1.schema.json")
    req = set(s["properties"]["checks"]["required"])
    assert req == {"perimeter_recoverable", "scale_consumable", "area_consistent",
                   "obstacles_representable", "entrance_identifiable",
                   "not_layout_dominated", "geometry_unambiguous"}


def test_el_hitl_de_v1_solo_admite_cuatro_preguntas_cerradas():
    """§8 — confirmar hechos, nunca diseñar. Si aparece una quinta, es CAD."""
    s = _j(C / "shell_input_v1.schema.json")
    assert sorted(s["properties"]["hitl_required"]["items"]["enum"]) == \
        sorted(["perimeter", "scale", "entrance", "fixed_elements"])


def test_el_contrato_de_escala_del_input_usa_el_vocabulario_ya_existente():
    """No inventar un vocabulario nuevo: reusar area_semantics."""
    from escalimetro.area_semantics import (SCALE_CONFIRMED, SCALE_INCOMPATIBLE_REGION,
                                            SCALE_MATCHED_REGION, SCALE_NOT_EVALUATED,
                                            SCALE_UNCONFIRMED_REGION)
    s = _j(C / "shell_input_v1.schema.json")
    enum = set(s["properties"]["evidence"]["properties"]["scale_semantic_validity"]["enum"])
    for v in (SCALE_CONFIRMED, SCALE_MATCHED_REGION, SCALE_UNCONFIRMED_REGION,
              SCALE_INCOMPATIBLE_REGION, SCALE_NOT_EVALUATED):
        assert v in enum, v


def test_el_esquema_de_revision_humana_tiene_las_tres_notas():
    """§10 — A GOOD / B CORRECTABLE / C BAD, sin puntaje automático."""
    s = _j(C / "human_review_v1.schema.json")
    assert sorted(s["properties"]["grade"]["enum"]) == ["A_GOOD", "B_CORRECTABLE", "C_BAD"]


def test_el_esquema_de_revision_humana_captura_los_defectos_que_vimos():
    s = _j(C / "human_review_v1.schema.json")
    tags = set(s["properties"]["reason_tags"]["items"]["enum"])
    for t in ("circulacion", "espacio_desperdiciado", "sin_espesor_de_tabique",
              "sin_pasillo_legible", "conflicto_nucleo", "otro"):
        assert t in tags, t


def test_la_revision_humana_no_deriva_ningun_score_automatico():
    """§10 — 'NO construir machine learning todavía'."""
    s = _j(C / "human_review_v1.schema.json")
    for prohibido in ("score", "weight", "label", "prediction", "model"):
        assert prohibido not in s["properties"], prohibido


# ------------------------------------------------ capacidad real del producto

def test_gps_403_produce_TRES_alternativas():
    """El hecho central de producto: el motor sí genera 3 layouts sobre un shell real."""
    for a in "ABC":
        assert (GPS / f"layouts/E07/alternatives/{a}/layout.json").exists()


def test_las_tres_alternativas_de_403_son_VALIDAS():
    """40/40 puestos, programa completo, 0 violaciones duras, 0 colisiones, circulación conectada."""
    for a in "ABC":
        m = _j(GPS / f"layouts/E07/alternatives/{a}/metrics.json")
        pc = m["program_completeness"]
        assert pc["complete"] is True, a
        assert pc["open_seats"] == "40/40", a
        assert m["hard_constraint_violations"] == 0, a
        assert m["collisions"] == 0, a
        assert m["circulation_connectivity"] is True, a


def test_las_tres_alternativas_son_GEOMETRICAMENTE_DISTINTAS():
    """Si A, B y C fueran iguales, 'tres alternativas' sería una etiqueta vacía."""
    firmas = []
    for a in "ABC":
        lay = _j(GPS / f"layouts/E07/alternatives/{a}/layout.json")
        rects = sorted((p["module"], round(p["x"], 2), round(p["y"], 2),
                        round(p["w"], 2), round(p["d"], 2)) for p in lay["placements"])
        firmas.append(hashlib.sha256(str(rects).encode()).hexdigest())
    assert len(set(firmas)) == 3


def test_las_tres_alternativas_difieren_en_circulacion_y_desperdicio():
    """La diversidad es medible, no sólo posicional."""
    circ = {a: _j(GPS / f"layouts/E07/alternatives/{a}/metrics.json")["circulation_area_m2"]
            for a in "ABC"}
    assert len(set(round(v, 1) for v in circ.values())) == 3, circ


def test_el_programa_completo_incluye_recintos_y_puestos():
    """Un layout no es sólo puestos: hay salas, privados, recepción, servicios."""
    rooms = _j(GPS / "layouts/E07/alternatives/A/metrics.json")["program_completeness"]["rooms"]
    for m in ("boardroom_12", "reception", "meeting_8", "private_office", "kitchenette", "dining"):
        assert rooms.get(m, 0) >= 1, m
    assert rooms["private_office"] == 4


def test_existe_la_lamina_de_tres_columnas():
    """§9/§18 — el entregable visual A|B|C existe."""
    assert (GPS / "layouts/E07/ESCALIMETRO_PRESENTATION_STANDARD_01.png").exists()
    assert (GPS / "layouts/E07/layouts_abc_geometry.png").exists()


def test_los_gates_tecnicos_de_403_pasan_en_las_tres():
    g = _j(GPS / "layouts/E07/gates.json")
    for a in "ABC":
        assert g[a]["E1-T"]["status"] == "PASS", a


# ------------------------------------------------ lo que NO funciona, fijado como hecho

def test_401_es_NO_FIT_y_eso_es_una_respuesta_correcta():
    """252 m² no dan para 40 puestos. El motor lo dice sin romperse: no es un bug."""
    m = _j(G401 / "layouts/OFFICE_BALANCED_001/metrics.json")
    assert m["program_completeness"]["complete"] is False
    assert m["collisions"] == 0
    assert m["circulation_connectivity"] is True
    assert not (G401 / "layouts/E07").exists()


def test_res_nunca_llego_a_tener_escala_consumible():
    """RES es el caso que define INPUT_NOT_READY: plano amoblado y escala rechazada."""
    fp = _j(RES / "outputs/E16_8_floorplate.json")
    assert fp["scale"]["px_per_m"] is None
    assert fp["scale"]["semantic_validity"] == "SCALE_INCOMPATIBLE_REGION"
    assert fp["scale"]["method"] == "published_area_rejected"


def test_res_esta_declarado_como_plano_amoblado_en_su_propio_caso():
    t = (RES / "case.json").read_text()
    assert "mobiliario" in t


def test_los_tests_de_layout_parten_de_un_floorplate_YA_COMMITEADO():
    """La costura visión→layout no está cubierta por ningún test: los tests de layout
    cargan un floorplate.json versionado en git, no lo generan desde la imagen.
    Cuando E25 cierre la costura, este test debe ACTUALIZARSE, no borrarse en silencio."""
    fp = GPS / "outputs/floorplate.json"
    assert fp.exists()
    consumidores = []
    for t in (RAIZ / "tests").glob("test_*.py"):
        if t.name == Path(__file__).name:
            continue
        s = t.read_text()
        if "escalimetro.layout" in s and "Floorplate.load" in s:
            consumidores.append(t.name)
    assert consumidores, "nadie carga un floorplate para layout"
    # ninguno de ellos construye ese floorplate: no llaman a pipeline.run
    for nombre in consumidores:
        s = (RAIZ / "tests" / nombre).read_text()
        assert "pipeline.run(" not in s and "from .pipeline import" not in s, nombre


# ------------------------------------------------ documentación de producto

def test_el_alcance_v1_esta_escrito_y_dice_shell_only():
    t = (RAIZ / "docs/PRODUCT_V1_SCOPE.md").read_text()
    assert "planta libre" in t
    assert "INPUT_NOT_READY" in t
    assert "no es un fallo del motor V1" in t


def test_la_limpieza_automatica_esta_declarada_diferida():
    """§20 — nota clara, sin borrar y sin integrar."""
    t = (RAIZ / "docs/PLAN_CLEANING_DEFERRED.md").read_text()
    assert "DEFERRED AFTER MVP V1" in t
    assert "No borrar" in t and "No integrar" in t


def test_la_investigacion_semantica_sigue_desconectada_del_runtime():
    """§1 — no integrar salidas E19–E22 en runtime."""
    for py in (RAIZ / "src").rglob("*.py"):
        s = py.read_text()
        assert "cases/generalization" not in s, py
        assert "context_bench_scene" not in s, py
