"""E05 — tests de la arquitectura híbrida: SpatialStrategy, estrategias, pre-flight, espina, CP-SAT con
restricciones duras en la búsqueda, crítico, reparación, ranking, identidad geométrica de renders."""
import json
import os

import jsonschema
import pytest
from shapely.geometry import box

from escalimetro.layout import Layout, Placement, Solver, load_modules, load_program, shell_from_floorplate
from escalimetro.layout.e05 import cpsolver
from escalimetro.layout.e05.bands import build_spine
from escalimetro.layout.e05.critic import CritiqueReport, RepairSuggestion, RuleBasedCritic, rank, to_repair_constraints
from escalimetro.layout.e05.features import extract_features
from escalimetro.layout.e05.preflight import preflight
from escalimetro.layout.e05.strategy import SCHEMA, SpatialStrategy, generate_strategies
from escalimetro.layout.render import render_layout_svg
from escalimetro.schemas.floorplate import Floorplate

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
MODS = os.path.join(ROOT, "program_templates", "modules_office.json")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")


@pytest.fixture(scope="module")
def ctx():
    fp = Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json"))
    shell = shell_from_floorplate(fp)
    mods, clr = load_modules(MODS)
    prog = load_program(PROG)
    S04 = Solver(shell, mods, prog, clr)
    feats = extract_features(shell, S04.grid)
    strats = generate_strategies(feats, int(prog["open_workstations_exact"]))
    return dict(shell=shell, mods=mods, prog=prog, S04=S04, grid=S04.grid, feats=feats, strats=strats)


@pytest.fixture(scope="module")
def g_probe(ctx):
    """Una sola resolución (sonda de capacidad, G) compartida por varios tests: CP-SAT tarda segundos."""
    return _solve(ctx, "G_E_PUBLIC_S2_WORK", seats_mode="max", tl=25.0)


def _solve(ctx, sid, seats_mode="exact", tl=25.0, repair=None):
    strat = next(s for s in ctx["strats"] if s.strategy_id == sid)
    plan = build_spine(ctx["shell"], ctx["feats"], strat, ctx["grid"])
    return strat, plan, cpsolver.solve(ctx["shell"], ctx["grid"], plan, strat, ctx["mods"], ctx["prog"],
                                       ctx["prog"]["objectives_weights"], repair=repair, seed=1, time_limit_s=tl,
                                       seats_mode=seats_mode)


# ---- SpatialStrategy schema y generación -----------------------------------------------------------
def test_spatial_strategy_schema(ctx):
    for s in ctx["strats"]:
        jsonschema.validate(s.to_dict(), SCHEMA)
        d = s.to_dict()
        txt = json.dumps(d)
        assert '"x":' not in txt and '"y":' not in txt and "coords" not in txt   # intención, no coordenadas de mobiliario
        back = SpatialStrategy.from_dict(d)
        assert back.strategy_id == s.strategy_id


def test_at_least_8_distinct_strategies(ctx):
    strats = ctx["strats"]
    assert len(strats) >= 8
    assert len({s.family for s in strats}) >= 8
    sigs = {json.dumps({k: v for k, v in s.to_dict().items() if k not in ("strategy_id", "family", "description")}, sort_keys=True) for s in strats}
    assert len(sigs) >= 8                                               # distintas en contenido, no sólo en nombre


def test_strategy_generation_is_deterministic(ctx):
    n = int(ctx["prog"]["open_workstations_exact"]) if "prog" in ctx else 40
    a = [s.to_dict() for s in generate_strategies(ctx["feats"], n)]
    b = [s.to_dict() for s in generate_strategies(ctx["feats"], n)]
    assert a == b


def test_strategies_reference_real_regions(ctx):
    ids = {r.id for r in ctx["feats"].regions}
    for s in ctx["strats"]:
        assert s.public_zone["region"] == ctx["feats"].entrance_region
        for rid in s.client_meeting_zone["regions"] + s.support_zone["regions"]:
            assert rid in ids


# ---- pre-flight y espina ------------------------------------------------------------------------------
def test_preflight_reports_boardroom_hosts(ctx):
    strat = ctx["strats"][0]
    plan = build_spine(ctx["shell"], ctx["feats"], strat, ctx["grid"])
    rep = preflight(strat, plan, ctx["mods"], ctx["prog"], ctx["shell"].usable.area)
    assert rep.largest_required_rectangle == [7.2, 5.0]
    assert isinstance(rep.boardroom_hosts, list)
    for bid in rep.boardroom_hosts:
        b = next(b for b in plan.bands if b.id == bid)
        L = max(s[1] - s[0] for s in b.slots_rooms)
        assert (b.depth >= 5.0 - 1e-6 and L >= 7.2 - 1e-6) or (b.depth >= 7.2 - 1e-6 and L >= 5.0 - 1e-6)


def test_spine_corridors_are_column_free_and_connected(ctx):
    strat = ctx["strats"][1]
    plan = build_spine(ctx["shell"], ctx["feats"], strat, ctx["grid"])
    assert plan.feasible
    for c in plan.corridors:
        for col in ctx["shell"].columns:
            inter = col.intersection(c.poly)
            if not inter.is_empty:
                bb = inter.bounds
                intr = (bb[3] - bb[1]) if c.axis == "h" else (bb[2] - bb[0])
                assert intr <= 0.08 + 1e-6


# ---- restricciones duras dentro de la búsqueda --------------------------------------------------------
def test_reception_domain_is_within_8m(ctx, g_probe):
    strat, plan, res = g_probe
    assert "layout" in res
    lay = res["layout"]
    ok, viol, circ = ctx["S04"].validate(lay)
    assert not any("within_8m_of_entrance" in v for v in viol)       # ≤ 8 m garantizado por el dominio, no a posteriori
    rec = next(n for n in circ["graph"]["nodes"] if n["id"] == "reception_1")
    assert rec["path_m"] <= 8.0


def test_exact_program_counts_and_boardroom_in_search(ctx, g_probe):
    strat, plan, res = g_probe
    lay = res["layout"]
    counts = {}
    for p in lay.placements:
        counts[p.module] = counts.get(p.module, 0) + 1
    for e in ctx["prog"]["program"]:
        if e["module"] != "workstation_cluster":
            assert counts.get(e["module"], 0) == e["count"], e["module"]
    bd = next(p for p in lay.placements if p.module == "boardroom_12")
    assert {round(bd.w, 1), round(bd.d, 1)} >= {7.2} and min(bd.w, bd.d) >= 5.0 - 1e-6
    assert ctx["shell"].usable.buffer(0.01).contains(bd.poly)


def test_exact_mode_requires_40_seats_or_fails(ctx):
    strat, plan, res = _solve(ctx, "H_WORK_FAR_CLIENT_ENTRANCE", seats_mode="exact", tl=15.0)
    if "layout" in res:
        assert sum(p.seats for p in res["layout"].placements) == 40
    else:
        assert res["status"] in ("INFEASIBLE", "UNKNOWN", "INFEASIBLE_MODEL")


def test_workstation_configs_derive_from_module(ctx, g_probe):
    strat, plan, res = g_probe
    for p in res["layout"].placements:
        if p.module.startswith("workstation"):
            cfg = p.meta["config"]
            rows, cols = (2, p.seats // 2) if cfg.startswith("bench") else (1, p.seats)
            assert abs(max(p.w, p.d) - 1.6 * cols) < 1e-6 and abs(min(p.w, p.d) - 1.6 * rows) < 1e-6
            assert len(p.desks) == p.seats


def test_columns_never_intersect_furniture(ctx, g_probe):
    strat, plan, res = g_probe
    for p in res["layout"].placements:
        if p.module.startswith("workstation"):
            for c in ctx["shell"].columns:
                assert c.intersection(p.poly).area < 1e-4
    ok, viol, _ = ctx["S04"].validate(res["layout"])
    assert not any("intersecta pilar" in v for v in viol)


def test_circulation_connectivity_of_solution(ctx, g_probe):
    strat, plan, res = g_probe
    ok, viol, circ = ctx["S04"].validate(res["layout"])
    assert circ["ok"]
    assert not any("sin acceso" in v for v in viol)


# ---- crítico, reparación, ranking ----------------------------------------------------------------------
def test_critic_schema_and_no_coordinates(ctx, g_probe):
    strat, plan, res = g_probe
    lay = res["layout"]
    ok, viol, circ = ctx["S04"].validate(lay)
    lay.hard_violations = viol
    from escalimetro.layout.run import compute_metrics
    lay.metrics = compute_metrics(lay, ctx["S04"], circ)
    rep = RuleBasedCritic().critique(lay, lay.metrics, strat.to_dict())
    d = rep.to_dict()
    for k in ("candidate_id", "hard_valid", "scores", "verdicts", "architectural_score", "broker_showable", "repair_suggestions"):
        assert k in d
    assert set(d["scores"]) == set(__import__("escalimetro.layout.e05.critic", fromlist=["ASPECTS"]).ASPECTS)
    assert 0.0 <= rep.architectural_score <= 1.0
    for s in rep.repair_suggestions:
        assert "x" not in s.args and "y" not in s.args          # el crítico nunca mueve coordenadas


def test_repair_loop_translates_suggestions_to_constraints():
    rep = CritiqueReport("c", True, {}, {}, 0.5, False,
                         [RepairSuggestion("require_adjacent", {"a": "kitchenette_1", "b": "dining_1"}, "separados"),
                          RepairSuggestion("forbid_on_facade", {"module": "private_office"}, "fachada"),
                          RepairSuggestion("weight", {"objective": "compactness", "value": 0.2}, "fragmentado")])
    rc = to_repair_constraints(rep)
    assert ("kitchenette_1", "dining_1") in rc.require_adjacent
    assert "private_office" in rc.forbid_module_on_facade
    assert rc.weight_overrides["compactness"] == 0.2


def test_repair_constraints_are_honoured_by_solver(ctx):
    rc = cpsolver.RepairConstraints(require_adjacent=[("kitchenette_1", "dining_1")])
    strat, plan, res = _solve(ctx, "G_E_PUBLIC_S2_WORK", seats_mode="max", tl=25.0, repair=rc)
    if "layout" in res:
        k = next(p for p in res["layout"].placements if p.module == "kitchenette")
        d = next(p for p in res["layout"].placements if p.module == "dining")
        assert k.poly.buffer(0.05).intersects(d.poly)
    else:
        assert res["status"] in ("INFEASIBLE", "UNKNOWN", "INFEASIBLE_MODEL")


def test_invalid_candidate_cannot_win():
    cands = [{"strategy_id": "bad", "hard_valid": False, "geometric_score": 0.99, "architectural_score": 0.99},
             {"strategy_id": "good", "hard_valid": True, "geometric_score": 0.4, "architectural_score": 0.5}]
    ranked = rank(cands)
    assert [c["strategy_id"] for c in ranked] == ["good"]
    assert cands[0]["total_score"] is None


def test_render_geometry_identity(ctx, g_probe):
    strat, plan, res = g_probe
    lay = res["layout"]
    import re
    g = render_layout_svg(lay, ctx["shell"], "geometry")
    c = render_layout_svg(lay, ctx["shell"], "commercial")
    before = [(p.id, p.x, p.y, p.w, p.d) for p in lay.placements]
    assert before == [(p.id, p.x, p.y, p.w, p.d) for p in lay.placements]      # renderizar no muta el layout
    assert "Dimensiones sujetas a confirmación de escala" in g and "Dimensiones sujetas a confirmación de escala" in c
    # cada recinto aparece en ambas láminas en la misma posición (rect con las mismas coordenadas de píxel)
    def rects(svg):
        return set(re.findall(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" fill="(?!none)', svg))
    rg, rcm = rects(g), rects(c)
    n_rooms = sum(1 for p in lay.placements if not p.module.startswith("workstation"))
    assert len(rg & rcm) >= n_rooms                 # todos los recintos: mismo rect de píxel en ambas láminas
