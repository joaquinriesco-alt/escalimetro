"""E05 — E04 queda congelado como baseline. Este test falla si alguien 'arregla' el resultado histórico."""
import json
import os

from escalimetro.layout import Layout, Solver, load_modules, load_program, shell_from_floorplate
from escalimetro.schemas.floorplate import Floorplate

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
E04 = os.path.join(CASE, "layouts", "OFFICE_BALANCED_001")


def test_e04_baseline_is_still_fail():
    m = json.load(open(os.path.join(E04, "metrics.json")))
    assert m["status"].startswith("FAIL")
    assert m["valid_candidate_count"] == 0 and m["candidate_count"] == 6
    assert m["program_completeness"]["complete"] is False
    assert m["program_completeness"]["open_seats"] == "33/40"
    assert m["best_total_score"] is None


def test_e04_baseline_revalidates_as_invalid():
    fp = Floorplate.load(os.path.join(CASE, "outputs", "floorplate.json"))
    shell = shell_from_floorplate(fp)
    mods, clr = load_modules(os.path.join(ROOT, "program_templates", "modules_office.json"))
    prog = load_program(os.path.join(ROOT, "program_templates", "office_balanced_48.json"))
    S = Solver(shell, mods, prog, clr)
    lay = Layout.load(os.path.join(E04, "layout.json"))
    ok, viol, circ = S.validate(lay)
    assert not ok
    assert "programa incompleto: boardroom_12 0/1" in viol
    assert "puestos open 33 ≠ 40" in viol
    assert any("within_8m_of_entrance" in v for v in viol)
    assert circ["ok"]                       # la circulación del baseline sí estaba conectada
