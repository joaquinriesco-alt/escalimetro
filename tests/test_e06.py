"""E06 — tests: modelo de escala, barrido determinista, FitRobustnessReport, colocación libre ortogonal,
circulación con quiebre, QA humano, burden, re-validación, veredicto de producto."""
import copy
import json
import os

import jsonschema
import pytest
from shapely.geometry import box

from escalimetro.layout import Layout, Placement, Solver, load_modules, load_program
from escalimetro.layout.e05.bands import build_spine
from escalimetro.layout.e05.critic import rank
from escalimetro.layout.e05.features import extract_features
from escalimetro.layout.e05.strategy import generate_strategies
from escalimetro.layout.e06 import freeplace as F
from escalimetro.layout.e06.qa import (OP_SCHEMA, HumanCorrectionOperation, apply_operations, burden, preserved_pct, qa_gate)
from escalimetro.layout.e06.scale import DEFAULT_FACTORS, SCENARIO_SCHEMA, make_scenario, scaled_shell
from escalimetro.layout.e06.sweep import FitRobustnessReport, classify, robustness
from escalimetro.layout.e06.scale import ScaleScenario
from escalimetro.layout.e06.verdict import build
from escalimetro.schemas.floorplate import Floorplate

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
MODS = os.path.join(ROOT, "program_templates", "modules_office.json")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")


@pytest.fixture(scope="module")
def fp():
    return Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json"))


@pytest.fixture(scope="module")
def ctx(fp):
    shell = scaled_shell(fp, 1.0)
    mods, clr = load_modules(MODS)
    prog = load_program(PROG)
    S04 = Solver(shell, mods, prog, clr)
    feats = extract_features(shell, S04.grid)
    strat = {s.strategy_id: s for s in generate_strategies(feats, int(prog["open_workstations_exact"]))}["B_CLIENT_FRONT"]
    plan = build_spine(shell, feats, strat, S04.grid)
    els = F.spine_elements(plan)
    brs = F.branch_candidates(shell, feats, els)
    cands, _ = F.generate_candidates(shell, S04.grid, feats, els + brs, mods, prog, strat.bench_preference, step=1.6)
    return dict(shell=shell, mods=mods, prog=prog, S04=S04, feats=feats, strat=strat, els=els, brs=brs, cands=cands)


@pytest.fixture(scope="module")
def probe(ctx):
    return F.solve_free(ctx["shell"], ctx["S04"].grid, ctx["feats"], ctx["strat"], ctx["els"] + ctx["brs"], ctx["cands"],
                        ctx["mods"], ctx["prog"], ctx["prog"]["objectives_weights"], seats_mode="max", time_limit_s=30.0)


# ---- escala ------------------------------------------------------------------------------------------
def test_scale_scenario_schema(fp):
    for f in DEFAULT_FACTORS:
        sc = make_scenario(fp, f)
        jsonschema.validate(sc.to_dict(), SCENARIO_SCHEMA)
        assert abs(sc.px_per_m * f - fp.scale.px_per_m) < 1e-3          # px_per_m se guarda redondeado a 4 decimales


def test_scaled_shell_area_scales_quadratically(fp):
    a1 = scaled_shell(fp, 1.0).usable.area
    a2 = scaled_shell(fp, 1.05).usable.area
    assert abs(a2 / a1 - 1.05 ** 2) < 1e-3
    assert len(scaled_shell(fp, 1.05).columns) == 10


def test_scale_sweep_is_deterministic(fp):
    a = [make_scenario(fp, f).to_dict() for f in DEFAULT_FACTORS]
    b = [make_scenario(fp, f).to_dict() for f in DEFAULT_FACTORS]
    assert a == b and [x["scale_factor"] for x in a] == DEFAULT_FACTORS


def test_fit_robustness_report_and_classification():
    assert classify([0.95, 1.0, 1.05], []) == "ROBUST_NO_FIT"
    assert classify([0.95, 0.975, 1.0, 1.05], [0.975, 1.0, 1.05]) == "ROBUST_FIT"
    assert classify([0.95, 0.975, 0.99, 1.0, 1.01, 1.025, 1.05], [0.99, 1.0, 1.01, 1.025, 1.05]) == "LIKELY_FIT"
    assert classify([0.95, 0.975, 0.99, 1.0, 1.01, 1.025, 1.05], [1.01, 1.025, 1.05]) == "BORDERLINE"
    assert classify([0.95, 0.975, 0.99, 1.0, 1.01, 1.025, 1.05], [1.05]) == "LIKELY_NO_FIT"
    scen = [ScaleScenario(f, 8.36 / f, 543 * f * f, 543 * f * f, "t", "LOW",
                          {"exact_fit": f >= 1.0, "max_seats": 40 if f >= 1.0 else 34, "exact": {"violations": ["puestos open 34 ≠ 40"]}})
            for f in DEFAULT_FACTORS]
    rep = robustness(scen)
    assert isinstance(rep, FitRobustnessReport)
    assert rep.min_scale_factor_exact_fit == 1.0 and rep.classification == "BORDERLINE"
    assert rep.pct_scenarios_exact_fit == round(100 * 4 / 7, 1)
    assert "puestos open" in rep.primary_constraint


# ---- colocación libre ---------------------------------------------------------------------------------
def test_free_candidates_are_geometrically_valid(ctx):
    shell = ctx["shell"]
    u = shell.usable.buffer(0.01)
    ent = box(shell.entrance[0] - 1.2, shell.entrance[1] - 1.2, shell.entrance[0] + 1.2, shell.entrance[1] + 1.2)
    for c in ctx["cands"]:
        assert u.contains(c.poly)
        for core in shell.core:
            assert core.intersection(c.poly).area < 1e-6
        assert c.touches
        for col in shell.columns:
            inter = col.intersection(c.poly).area
            if c.module.startswith("workstation"):
                assert inter < 1e-4
            elif inter > 1e-4:
                assert c.poly.exterior.distance(col.centroid) <= 0.6


def test_room_orientation_diversity(ctx):
    rots = {c.module: set() for c in ctx["cands"]}
    for c in ctx["cands"]:
        rots[c.module].add(c.rot)
    assert rots["private_office"] == {0, 90} and rots["meeting_4"] == {0, 90}
    # hay candidatos perpendiculares a la fachada sur (profundidad en x) y candidatos contra el núcleo
    priv = [c for c in ctx["cands"] if c.module == "private_office"]
    assert any(c.rect[3] - c.rect[1] > c.rect[2] - c.rect[0] and c.region.startswith("S") for c in priv)
    core = ctx["shell"].core[0]
    # candidatos contra el núcleo: a ≤ 0.5 m del polígono del núcleo (el muro del núcleo segmentado tiene espesor)
    assert any(c.poly.distance(core) <= 0.5 for c in ctx["cands"] if not c.module.startswith("workstation"))


def test_branches_give_bends_and_are_column_free(ctx):
    assert len(ctx["brs"]) >= 5
    axes = {b.axis for b in ctx["brs"]}
    assert axes == {"h", "v"}                       # ramales perpendiculares a pasillos en ambas direcciones
    for b in ctx["brs"]:
        for col in ctx["shell"].columns:
            inter = col.intersection(b.poly)
            if not inter.is_empty:
                bb = inter.bounds
                assert min(bb[2] - bb[0], bb[3] - bb[1]) <= 0.08 + 1e-6


def test_exact_program_and_avoidance_in_free_solution(ctx, probe):
    assert "layout" in probe
    lay = probe["layout"]
    counts = {}
    for p in lay.placements:
        counts[p.module] = counts.get(p.module, 0) + 1
    for e in ctx["prog"]["program"]:
        if e["module"] != "workstation_cluster":
            assert counts.get(e["module"], 0) == e["count"], e["module"]
    ok, viol, circ = ctx["S04"].validate(lay)
    assert not any("núcleo" in v or "intersecta pilar" in v or "colisión" in v or "fuera del shell" in v for v in viol)
    assert circ["ok"]                                # toda zona ocupada conecta a la red de acceso
    assert not any("sin acceso" in v for v in viol)


def test_circulation_with_bend_when_branch_active(ctx, probe):
    lay = probe["layout"]
    net = lay.zones["network"]
    assert net["branches_candidates"] >= 5
    # si hay ramal activo, es perpendicular a la espina (quiebre / T) y algún recinto lo usa como puerta
    for b in net["branches_active"]:
        assert any(b["id"] in p.meta.get("touches", []) for p in lay.placements)


def test_invalid_candidate_cannot_win():
    cands = [{"strategy_id": "bad", "hard_valid": False, "geometric_score": 0.99, "architectural_score": 0.99},
             {"strategy_id": "good", "hard_valid": True, "geometric_score": 0.3, "architectural_score": 0.4}]
    assert [c["strategy_id"] for c in rank(cands)] == ["good"]


# ---- QA humano ------------------------------------------------------------------------------------------
def test_human_correction_operation_schema_and_apply(ctx, probe):
    lay = probe["layout"]
    ops = [HumanCorrectionOperation("ACCEPT", "boardroom_12_1"), HumanCorrectionOperation("LOCK", "reception_1"),
           HumanCorrectionOperation("MOVE", "phone_booth_1", {"dx": 0.4, "dy": 0.0}, "corrida"),
           HumanCorrectionOperation("ROTATE", "phone_booth_2"),
           HumanCorrectionOperation("SWAP", "meeting_4_1", {"other": "meeting_4_2"}),
           HumanCorrectionOperation("DELETE", "phone_booth_3"),
           HumanCorrectionOperation("ADD", "", {"module": "phone_booth", "x": 1.0, "y": 1.0, "id": "phone_booth_qa"})]
    for o in ops:
        jsonschema.validate(o.to_dict(), OP_SCHEMA)
    after, log, locked = apply_operations(lay, ops, ctx["mods"])
    assert len(log) == 7 and locked == ["reception_1"]
    pb = next(p for p in after.placements if p.id == "phone_booth_1"); pb0 = next(p for p in lay.placements if p.id == "phone_booth_1")
    assert abs(pb.x - pb0.x - 0.4) < 1e-9
    assert not any(p.id == "phone_booth_3" for p in after.placements)
    assert any(p.id == "phone_booth_qa" and p.meta.get("qa_added") for p in after.placements)
    assert [(p.id, p.x, p.y) for p in lay.placements] != [(p.id, p.x, p.y) for p in after.placements]
    assert len(lay.placements) == len([p for p in probe["layout"].placements])       # el original no se muta


def test_resize_to_valid_variant_keeps_module_grid(ctx, probe):
    lay = probe["layout"]
    ws = next(p for p in lay.placements if p.module.startswith("workstation"))
    after, _, _ = apply_operations(lay, [HumanCorrectionOperation("RESIZE_TO_VALID_VARIANT", ws.id, {"variant": "bench 2x3"})], ctx["mods"])
    p = next(p for p in after.placements if p.id == ws.id)
    assert p.seats == 6 and {round(p.w, 3), round(p.d, 3)} == {3.2, 4.8} and len(p.desks) == 6


def test_burden_and_geometry_preservation(ctx, probe):
    lay = probe["layout"]
    ops = [HumanCorrectionOperation("MOVE", "phone_booth_1", {"dx": 0.4}), HumanCorrectionOperation("LOCK", "boardroom_12_1"),
           HumanCorrectionOperation("ACCEPT", "reception_1")]
    after, _, _ = apply_operations(lay, ops, ctx["mods"])
    n = len(lay.placements)
    assert preserved_pct(lay, after) == round(100.0 * (n - 1) / n, 1)
    b = burden(lay, after, ops, {"hard_valid": False})
    assert b.operation_count == 3 and b.move_count == 1 and b.locked_elements == 1 and b.accepted_elements == 1
    assert b.minutes_are_estimated is True and abs(b.estimated_minutes - (1.0 + 0.5 + 0.1 + 0.1)) < 1e-6


def test_deterministic_revalidation_after_correction(ctx, probe):
    lay = probe["layout"]
    ok0, viol0, _ = ctx["S04"].validate(lay)
    # mover el directorio encima de la recepción produce colisión detectada por el validador (determinista)
    rec = next(p for p in lay.placements if p.module == "reception")
    after, _, _ = apply_operations(lay, [HumanCorrectionOperation("MOVE", "boardroom_12_1", {"x": rec.x, "y": rec.y})], ctx["mods"])
    ok1, viol1, _ = ctx["S04"].validate(after)
    assert not ok1 and any(v.startswith("colisión") for v in viol1)
    ok2, viol2, _ = ctx["S04"].validate(after)
    assert viol1 == viol2


def test_qa_gates_thresholds():
    class B:  # burden mínimo
        def __init__(self, m, p): self.estimated_minutes, self.automatic_geometry_preserved_pct = m, p
    assert qa_gate(True, True, None, False, False) == "AUTONOMOUS_PASS"
    assert qa_gate(False, False, B(1.5, 95), True, True) == "STRONG_ASSISTED_PASS"
    assert qa_gate(False, False, B(4.0, 85), True, True) == "ASSISTED_PASS"
    assert qa_gate(False, False, B(8.0, 70), True, True) == "WEAK_ASSISTED_PASS"
    assert qa_gate(False, False, B(12.0, 95), True, True) == "FAIL"
    assert qa_gate(False, False, B(1.0, 95), False, True) == "FAIL"     # sin re-validación válida no hay PASS


def test_product_fit_verdict():
    rob = {"classification": "BORDERLINE", "min_scale_factor_exact_fit": 1.0, "pct_scenarios_exact_fit": 57.1,
           "exact_fit_factors": [1.0, 1.01, 1.025, 1.05], "primary_constraint": "puestos open", "confidence": "LOW"}
    ev = {"verdict": "UNKNOWN", "combined_factor_range": None}
    v = build("Oficina 403", "OFFICE_BALANCED_48", 48, rob, ev, "PASS", "FAIL", "AUTONOMOUS_PASS")
    d = v.to_dict()
    for k in ("fit", "reason", "primary_uncertainty", "recommendation", "scale_confidence", "gate_e1_autonomous", "gate_e1_assisted"):
        assert k in d
    assert v.fit == "BORDERLINE" and "1.000" in v.reason and "UNKNOWN" in v.primary_uncertainty
    assert "FIT: BORDERLINE" in v.text()
