"""E07 — tests: grafo espacial, tres estrategias distintas, validez dura de A/B/C, diferencia geométrica,
gates E1-T / E1-A / E1-C, QA interno, profiling, handoff con geometría bloqueada y lámina.

Los tests de artefactos leen las salidas de `cases/001_gps_403/layouts/E07/` (la corrida real). No vuelven a
ejecutar el solver: el motor ya está cubierto por E04/E05/E06."""
import json
import os
import types

import jsonschema
import pytest

from escalimetro.layout import Layout, Solver, load_modules, load_program
from escalimetro.layout.e06.qa import HumanCorrectionOperation
from escalimetro.layout.e06.scale import scaled_shell
from escalimetro.layout.e07.engine import geometric_difference
from escalimetro.layout.e07.graph import SCHEMA as GRAPH_SCHEMA
from escalimetro.layout.e07.pipeline import (E1A_CRITIC_THRESHOLD, E1A_MAX_QA_MINUTES, InternalQABurden,
                                             gate_e1a, gate_e1c, gate_e1t, internal_qa, presentation_handoff)
from escalimetro.layout.e07.strategies import build_alternatives
from escalimetro.schemas.floorplate import Floorplate

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
OUT = os.path.join(CASE, "layouts", "E07")
MODS = os.path.join(ROOT, "program_templates", "modules_office.json")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")
ALTS = ["A", "B", "C"]

pytestmark = pytest.mark.skipif(not os.path.isdir(os.path.join(OUT, "alternatives")),
                                reason="requiere la corrida E07 (python -m escalimetro.layout.e07.run)")


# ---------------------------------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def prog():
    return load_program(PROG)


@pytest.fixture(scope="module")
def shell():
    return scaled_shell(Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json")), 1.0)


def _read(alt, name):
    return json.load(open(os.path.join(OUT, "alternatives", alt, name), encoding="utf-8"))


@pytest.fixture(scope="module")
def arts():
    out = {}
    for a in ALTS:
        d = os.path.join(OUT, "alternatives", a)
        out[a] = {"layout": Layout.load(os.path.join(d, "layout.json")),
                  "metrics": _read(a, "metrics.json"), "critique": _read(a, "critique.json"),
                  "gates": _read(a, "gates.json"), "qa": _read(a, "internal_qa.json"),
                  "handoff": _read(a, "presentation_handoff.json")}
    return out


def _result(alt, arts):
    a = arts[alt]
    return types.SimpleNamespace(alt=alt, name=alt, layout=a["layout"], metrics=a["metrics"],
                                 critique=a["critique"], hard_valid=True, violations=[])


# ---------------------------------------------------------------------------------------------------
# grafo espacial
# ---------------------------------------------------------------------------------------------------
def test_spatial_graph_valida_contra_schema(prog):
    for spec in build_alternatives(prog):
        jsonschema.validate(spec.graph.to_dict(), GRAPH_SCHEMA)


def test_spatial_graph_persistido_valida(prog):
    for a in ALTS:
        g = json.load(open(os.path.join(OUT, "alternatives", f"spatial_graph_{a}.json"), encoding="utf-8"))
        jsonschema.validate(g, GRAPH_SCHEMA)


def test_grafo_precede_a_las_coordenadas(prog):
    """El grafo se define sobre nodos de programa, no sobre geometría: ningún nodo trae x/y."""
    for spec in build_alternatives(prog):
        for n in spec.graph.to_dict()["nodes"]:
            assert "x" not in n and "y" not in n


# ---------------------------------------------------------------------------------------------------
# estrategias A/B/C
# ---------------------------------------------------------------------------------------------------
def test_tres_alternativas_deterministas(prog):
    a = [s.to_dict() for s in build_alternatives(prog)]
    b = [s.to_dict() for s in build_alternatives(prog)]
    assert a == b
    assert [s["alt"] for s in a] == ALTS


def test_alternativas_conceptualmente_distintas(prog):
    specs = build_alternatives(prog)
    sigs = [s.graph.signature() for s in specs]
    assert len({json.dumps(s, sort_keys=True) for s in sigs}) == 3
    assert len({s.spine_strategy for s in specs}) == 3          # circulación distinta
    assert len({tuple(s.bench_cfgs) for s in specs}) == 3       # granularidad de barrios distinta
    assert len({json.dumps(s.weights, sort_keys=True) for s in specs}) == 3   # objetivos distintos


def test_principios_arquitectonicos_comunes(prog):
    """Los principios del §10 son comunes: cocina+comedor duro, luz al open, recepción en el acceso."""
    for spec in build_alternatives(prog):
        assert ("kitchenette", "dining") in [tuple(p) for p in spec.solver_extra["hard_adjacent_pairs"]]
        rels = {(e.a, e.relation, e.b) for e in spec.graph.edges}
        assert ("open_work_neighborhood_1", "daylight_preference", "facade_premium") in rels
        assert ("reception", "entrance_priority", "entrance") in rels


def test_mismo_programa_en_las_tres(prog):
    counts = {e["module"]: e["count"] for e in prog["program"]}
    for spec in build_alternatives(prog):
        assert sum(n.seats for n in spec.graph.nodes if n.kind == "work") == 40
        for m, c in counts.items():
            n = spec.graph.node(m)
            if n is not None:
                assert n.count == c


# ---------------------------------------------------------------------------------------------------
# validez dura de la geometría producida
# ---------------------------------------------------------------------------------------------------
def test_cuarenta_puestos_en_las_tres(arts):
    for a in ALTS:
        assert arts[a]["metrics"]["program_completeness"]["open_seats"] == "40/40"


def test_programa_completo_en_las_tres(arts):
    for a in ALTS:
        assert arts[a]["metrics"]["program_completeness"]["complete"] is True


def test_sin_violaciones_ni_colisiones(arts):
    for a in ALTS:
        m = arts[a]["metrics"]
        assert m["hard_constraint_violations"] == 0
        assert m["collisions"] == 0


def test_circulacion_conectada(arts):
    for a in ALTS:
        assert arts[a]["metrics"]["circulation_connectivity"] is True


def test_recepcion_dentro_del_limite(arts):
    for a in ALTS:
        nodes = arts[a]["layout"].circulation_graph.get("nodes", [])
        rec = [n for n in nodes if n["id"].startswith("reception")]
        assert rec and rec[0]["path_m"] <= 8.0 + 1e-6


def test_revalidacion_determinista(arts, shell, prog):
    """La validez no es un flag guardado: se vuelve a decidir con el validador de E04."""
    mods, clr = load_modules(MODS)
    val = Solver(shell, mods, prog, clr)
    for a in ALTS:
        ok, viol = val.validate(arts[a]["layout"])[:2]
        assert ok, (a, viol)


def test_mismo_shell_en_las_tres(arts):
    per = [tuple(map(tuple, arts[a]["handoff"]["shell_geometry"]["perimeter"])) for a in ALTS]
    assert per[0] == per[1] == per[2]
    areas = {round(arts[a]["metrics"]["usable_area_m2"], 1) for a in ALTS}
    assert len(areas) == 1


def test_diferencia_geometrica_significativa(arts):
    pairs = [("A", "B"), ("A", "C"), ("B", "C")]
    for x, y in pairs:
        d = geometric_difference(arts[x]["layout"], arts[y]["layout"])
        assert d["different_pct"] >= 30.0, (x, y, d)   # no son tres semillas casi iguales


# ---------------------------------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------------------------------
def test_gate_e1t_pass(arts):
    for a in ALTS:
        assert gate_e1t(_result(a, arts))["status"] == "PASS"
        assert arts[a]["gates"]["E1-T"]["status"] == "PASS"


def test_gate_e1t_detecta_programa_incompleto(arts):
    r = _result("A", arts)
    r.metrics = json.loads(json.dumps(arts["A"]["metrics"]))
    r.metrics["program_completeness"]["open_seats"] = "38/40"
    assert gate_e1t(r)["status"] == "FAIL"


def test_gate_e1a_provisional_con_umbral_documentado(arts):
    b = InternalQABurden(**{k: v for k, v in arts["A"]["qa"].items() if k in InternalQABurden.__dataclass_fields__})
    g = gate_e1a(_result("A", arts), b)
    assert g["status"] == "PASS_PROVISIONAL"
    assert g["thresholds"]["critic"] == E1A_CRITIC_THRESHOLD
    assert "hipótesis de producto" in g["note"]


def test_gate_e1a_falla_bajo_umbral(arts):
    r = _result("A", arts)
    r.critique = json.loads(json.dumps(arts["A"]["critique"]))
    r.critique["architectural_score"] = 0.4
    b = InternalQABurden(**{k: v for k, v in arts["A"]["qa"].items() if k in InternalQABurden.__dataclass_fields__})
    assert gate_e1a(r, b)["status"] == "FAIL"


def test_gate_e1c_nunca_pasa_por_software(arts):
    for a in ALTS:
        g = gate_e1c(arts[a]["gates"]["E1-T"], arts[a]["gates"]["E1-A"])
        assert g["status"] in ("READY_FOR_BROKER_REVIEW", "NOT_READY")
        assert g["status"] != "PASS"
        assert arts[a]["gates"]["E1-C"]["status"] != "PASS"


def test_gate_e1c_no_usa_broker_showable(arts):
    """El crítico interno declara broker_showable=False y aun así E1-C llega a READY: son capas distintas."""
    for a in ALTS:
        assert arts[a]["critique"]["broker_showable"] is False
        assert arts[a]["gates"]["E1-C"]["status"] == "READY_FOR_BROKER_REVIEW"


# ---------------------------------------------------------------------------------------------------
# QA interno
# ---------------------------------------------------------------------------------------------------
def test_qa_interno_es_estimado_no_medido(arts):
    for a in ALTS:
        q = arts[a]["qa"]
        assert "estimated_minutes" in q and "measured_minutes" not in q
        assert q["minutes_are_estimated"] is True
        assert q["estimated_minutes"] <= E1A_MAX_QA_MINUTES
        assert q["redesign_required"] is False
        assert q["operation_count"] == len(q["operations"])
        assert q["reason_for_correction"] and q["geometry_changed_pct"] == 0.0


def test_qa_interno_sin_operaciones_preserva_la_geometria(arts, shell, prog):
    mods, clr = load_modules(MODS)
    val = Solver(shell, mods, prog, clr)
    lay = arts["A"]["layout"]
    crit = types.SimpleNamespace(architectural_score=arts["A"]["critique"]["architectural_score"])
    after, b = internal_qa("A", lay, [], mods, val, "revisión sin cambios", lambda l: (True, [], crit))
    assert b.operation_count == 0
    assert b.geometry_changed_pct == 0.0
    assert [(p.id, p.x, p.y) for p in after.placements] == [(p.id, p.x, p.y) for p in lay.placements]


def test_operacion_de_qa_valida_contra_schema():
    op = HumanCorrectionOperation("move", "meeting_4_1", {"dx": 0.4, "dy": 0.0})
    assert op.to_dict()["op"] == "move" and op.target == "meeting_4_1"


# ---------------------------------------------------------------------------------------------------
# performance
# ---------------------------------------------------------------------------------------------------
def test_profiling_por_etapa_completo():
    s = json.load(open(os.path.join(OUT, "summary.json"), encoding="utf-8"))
    assert set(s["per_alternative_s"]) == set(ALTS)
    prof = json.load(open(os.path.join(OUT, "performance.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(OUT, "performance.json")) else None
    if prof:
        for p in prof:
            for k in ("candidate_generation_s", "solver_feasibility_s", "solver_optimization_s",
                      "validation_s", "critic_s", "render_s", "total_s"):
                assert k in p


def test_kpi_120s_por_alternativa():
    s = json.load(open(os.path.join(OUT, "summary.json"), encoding="utf-8"))
    assert s["kpi_target_s"] == 120.0
    assert all(v < 120.0 for v in s["per_alternative_s"].values()), s["per_alternative_s"]
    assert s["kpi_met"] is True


# ---------------------------------------------------------------------------------------------------
# handoff y presentación
# ---------------------------------------------------------------------------------------------------
def test_handoff_geometry_locked(arts):
    for a in ALTS:
        h = arts[a]["handoff"]
        assert h["geometry_locked"] is True
        assert "image generation" in h["geometry_lock_note"]
        assert h["scale_status"]["state"] == "UNCONFIRMED"
        assert h["fit_verdict"]["fit"] == "ROBUST_WITHIN_ASSUMED_SCALE_RANGE"


def test_handoff_lleva_la_misma_geometria_que_el_layout(arts):
    for a in ALTS:
        h, lay = arts[a]["handoff"], arts[a]["layout"]
        assert len(h["layout_geometry"]) == len(lay.placements)
        for g, p in zip(h["layout_geometry"], lay.placements):
            assert g["id"] == p.id
            assert abs(g["x"] - p.x) < 1e-3 and abs(g["y"] - p.y) < 1e-3


def test_renderers_tecnico_y_comercial_comparten_coordenadas(arts, shell):
    """Regla absoluta §22: técnico y comercial son la MISMA planta con otra piel."""
    from escalimetro.layout.render import render_layout_svg, _Tf
    for a in ALTS:
        lay = arts[a]["layout"]
        t = render_layout_svg(lay, shell, "geometry", width_px=1200)
        c = render_layout_svg(lay, shell, "commercial", width_px=1200)
        tf = _Tf(shell, 1200, 60, extra_bottom=150)
        tfc = _Tf(shell, 1200, 60, extra_bottom=190)
        n = 0
        for p in lay.placements:
            if p.module.startswith("workstation"):
                continue
            X, Y, W, D = tf.rect(p.x, p.y, p.w, p.d)
            X2, Y2, W2, D2 = tfc.rect(p.x, p.y, p.w, p.d)
            assert (X, Y, W, D) == (X2, Y2, W2, D2)          # misma transformación
            key = f'x="{X:.1f}" y="{Y:.1f}" width="{W:.1f}" height="{D:.1f}"'
            assert key in t and key in c, (a, p.id)
            n += 1
        assert n == 16


def test_lamina_solo_recibe_alternativas_validadas(arts):
    png = os.path.join(OUT, "ESCALIMETRO_PRESENTATION_STANDARD_01.png")
    assert os.path.exists(png)
    s = json.load(open(os.path.join(OUT, "summary.json"), encoding="utf-8"))
    assert all(s["gates"][a]["E1-T"] == "PASS" for a in ALTS)


def test_escala_no_confirmada_en_todas_las_salidas(arts):
    for a in ALTS:
        assert "confirmación de escala" in arts[a]["metrics"]["scale_note"]
    fit = json.load(open(os.path.join(OUT, "fit_verdict.json"), encoding="utf-8"))
    assert fit["fit"] == "ROBUST_WITHIN_ASSUMED_SCALE_RANGE"
    assert fit["scale"] == "UNCONFIRMED"


def test_seis_visuales_obligatorias():
    for n in ("spatial_graphs_abc.png", "layouts_abc_geometry.png", "alternative_comparison.png",
              "internal_qa_summary.png", "performance_profile.png", "ESCALIMETRO_PRESENTATION_STANDARD_01.png"):
        p = os.path.join(OUT, n)
        assert os.path.exists(p) and os.path.getsize(p) > 20000, n
