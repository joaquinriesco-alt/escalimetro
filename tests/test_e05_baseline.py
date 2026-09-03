"""E06 — E05 queda congelado como baseline: Gate E1 FAIL, 34/40 puestos, 17/17 recintos."""
import json
import os

from escalimetro.layout import Layout

ROOT = os.path.dirname(os.path.dirname(__file__))
E05 = os.path.join(ROOT, "cases", "001_gps_403", "layouts", "E05")


def test_e05_baseline_summary_is_fail_34_of_40():
    s = json.load(open(os.path.join(E05, "summary.json")))
    assert s["gate_e1"] == "FAIL"
    assert s["stats"]["hard_valid_count"] == 0 and s["stats"]["strategy_count"] >= 8
    assert s["best_partial"]["seats"] == 34
    assert s["best_partial"]["violations"] == ["puestos open 34 ≠ 40"]


def test_e05_baseline_layout_has_all_16_room_placements():
    """El programa de recintos son 16 colocaciones (4+3+1+1+3+1+1+1+1); el prompt E06 lo cita como '17/17'
    contando también el bloque de puestos como ítem de programa. Se fija el número real."""
    lay = Layout.load(os.path.join(E05, "E05_BEST_PARTIAL_B_CLIENT_FRONT", "layout.json"))
    rooms = [p for p in lay.placements if not p.module.startswith("workstation")]
    assert len(rooms) == 16
    assert sum(p.seats for p in lay.placements) == 34
