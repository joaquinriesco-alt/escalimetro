"""E04 — tests del motor de layout (SHELL + PROGRAM + MODULES + CONSTRAINTS + OBJECTIVES + SCORING).
No dependen de que exista una solución válida para el brief: prueban las reglas, no el resultado."""
import json
import os

import pytest
from shapely.geometry import box

from escalimetro.layout import Layout, Placement, Solver, load_modules, load_program, shell_from_floorplate
from escalimetro.layout.render import render_layout_svg
from escalimetro.layout.strips import sections
from escalimetro.schemas.floorplate import Floorplate

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
MODS = os.path.join(ROOT, "program_templates", "modules_office.json")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")


@pytest.fixture(scope="module")
def shell():
    fp = Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json"))
    return shell_from_floorplate(fp)


@pytest.fixture(scope="module")
def solver(shell):
    mods, clr = load_modules(MODS)
    prog = load_program(PROG)
    return Solver(shell, mods, prog, clr)


def test_program_template_is_the_brief():
    p = json.load(open(PROG))
    counts = {e["module"]: e["count"] for e in p["program"]}
    assert p["open_workstations_exact"] == 40
    assert counts["private_office"] == 4 and counts["meeting_4"] == 3 and counts["meeting_8"] == 1
    assert counts["boardroom_12"] == 1 and counts["phone_booth"] == 3 and counts["reception"] == 1
    assert counts["kitchenette"] == 1 and counts["dining"] == 1 and counts["lounge"] == 1
    w = p["objectives_weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-6
    for k in ("daylight_utilization", "circulation_efficiency", "entrance_logic", "adjacency_quality", "compactness",
              "privacy_gradient", "meeting_accessibility", "facade_preservation", "wasted_space"):
        assert k in w


def test_module_library_fields():
    mods, clr = load_modules(MODS)
    need = {"workstation", "workstation_cluster", "private_office", "meeting_4", "meeting_8", "boardroom_12",
            "phone_booth", "reception", "kitchenette", "dining", "lounge"}
    assert need <= set(mods)
    raw = json.load(open(MODS))["modules"]
    for name in need - {"workstation"}:
        m = raw[name]
        for f in ("w", "d", "occupancy", "daylight_preference", "entrance_preference", "wall_preference",
                  "rotation_allowed", "hard", "soft"):
            assert f in m, (name, f)
    assert clr["secondary_circulation_m"] >= 1.2


def test_shell_adapter_from_case(shell):
    assert shell.scale_confidence == "LOW"                     # published_area_inferred
    assert abs(shell.usable.area - 543.0) < 1.0
    assert len(shell.columns) == 10
    inside = sum(shell.usable.buffer(0.3).contains(c.centroid) for c in shell.columns)
    assert inside >= 9            # el pilar NW cae en una muesca del perímetro segmentado (E03), a < 0.3 m
    assert not any(c.intersects(shell.usable) for c in shell.core) or all(
        shell.usable.intersection(c).area < 1e-6 for c in shell.core)


def test_shell_adapter_requires_ready_shell(shell):
    fp = Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json"))
    fp.shell_readiness.ready_for_layout = False
    with pytest.raises(ValueError):
        shell_from_floorplate(fp)


def test_sections_always_contain_corridor():
    for sec in sections(7.7, True):
        kinds = [k for k, _ in sec]
        assert "corridor" in kinds
        for i, k in enumerate(kinds):
            if k in ("rooms", "desks"):
                nb = [kinds[j] for j in (i - 1, i + 1) if 0 <= j < len(kinds)]
                assert "corridor" in nb, sec
    for sec in sections(5.0, False, start_corridor=True):
        assert sec[0][0] == "corridor"


def test_zoning_has_four_zones(solver):
    z = solver.zones["areas_m2"]
    assert set(z) >= {"PUBLIC", "SEMI_PUBLIC", "WORK", "SUPPORT"}
    assert all(v >= 0 for v in z.values())


def test_validate_rejects_incomplete_program(solver):
    lay = Layout(layout_id="t", template_id="office_balanced_48", seed=0, placements=[])
    ok, viol, _ = solver.validate(lay)
    assert not ok
    assert any(v.startswith("programa incompleto") for v in viol)
    assert any(v.startswith("puestos open") for v in viol)


def test_validate_rejects_column_and_core(solver, shell):
    c = shell.columns[0]
    cx, cy = c.centroid.x, c.centroid.y
    desk = Placement("workstation_cluster_x", "workstation_cluster", cx - 2.4, cy - 1.6, 4.8, 3.2, 0, "WORK", seats=6)
    lay = Layout(layout_id="t", template_id="x", seed=0, placements=[desk])
    ok, viol, _ = solver.validate(lay)
    assert any("intersecta pilar" in v for v in viol)
    core = shell.core[0].centroid
    room = Placement("meeting_4_x", "meeting_4", core.x, core.y, 3.5, 3.0, 0, "SEMI_PUBLIC")
    lay = Layout(layout_id="t", template_id="x", seed=0, placements=[room])
    ok, viol, _ = solver.validate(lay)
    assert any("núcleo" in v or "fuera del shell" in v for v in viol)


def test_validate_detects_collision(solver):
    a = Placement("private_office_1", "private_office", 14.0, 1.0, 4.0, 3.0, 0, "WORK")
    b = Placement("private_office_2", "private_office", 15.0, 1.5, 4.0, 3.0, 0, "WORK")
    lay = Layout(layout_id="t", template_id="x", seed=0, placements=[a, b])
    ok, viol, _ = solver.validate(lay)
    assert any(v.startswith("colisión") for v in viol)


def test_solver_reproducible_and_reports_counts(solver):
    solver.search_restarts, solver.search_iters = 1, 5          # rápido: sólo la mecánica
    r1 = solver.solve(n_candidates=1, seed=7, improve_rounds=0, log=None)
    r2 = solver.solve(n_candidates=1, seed=7, improve_rounds=0, log=None)
    for k in ("candidate_count", "valid_candidate_count", "runtime_s", "best_score", "status"):
        assert k in r1
    p1 = [(p.id, round(p.x, 3), round(p.y, 3)) for p in r1["best"].placements]
    p2 = [(p.id, round(p.x, 3), round(p.y, 3)) for p in r2["best"].placements]
    assert p1 == p2                                             # misma semilla → mismo layout


def test_renders_share_geometry(solver, shell):
    solver.search_restarts, solver.search_iters = 1, 5
    lay = solver.solve(n_candidates=1, seed=3, improve_rounds=0, log=None)["best"]
    g = render_layout_svg(lay, shell, "geometry")
    c = render_layout_svg(lay, shell, "commercial")
    assert "Dimensiones sujetas a confirmación de escala" in g
    assert "Dimensiones sujetas a confirmación de escala" in c
    # la geometría (rectángulos de módulos, mismos ids) es idéntica: se compara el JSON, no el estilo
    ids = sorted(p.id for p in lay.placements if not p.module.startswith("workstation"))
    assert ids == sorted(set(ids)) and len(ids) > 0
    assert all(pid in g for pid in ids)          # la planta técnica etiqueta cada recinto con su id
    assert g != c                                # cambia el estilo, no el Layout (misma lista de Placement)


def test_layout_json_roundtrip(tmp_path, solver):
    solver.search_restarts, solver.search_iters = 1, 3
    lay = solver.solve(n_candidates=1, seed=5, improve_rounds=0, log=None)["best"]
    f = tmp_path / "layout.json"
    lay.save(str(f))
    back = Layout.load(str(f))
    assert [(p.id, p.x, p.y, p.w, p.d) for p in back.placements] == [(p.id, p.x, p.y, p.w, p.d) for p in lay.placements]
