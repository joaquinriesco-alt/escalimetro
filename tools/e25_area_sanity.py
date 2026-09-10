"""E25 §6 — SANITY CHECK GEOMÉTRICO SIN CP-SAT.

Suma de áreas. NO decide factibilidad: un programa puede sumar poco y no caber (geometría), o sumar
mucho y caber (holgura de circulación real). Sólo produce una SEÑAL para leer el diagnóstico.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from escalimetro.brief import compile_program, load_brief                      # noqa: E402
from escalimetro.case_context import from_case_dir                             # noqa: E402
from escalimetro.layout.e05.preflight import CIRC_FACTOR                       # noqa: E402
from escalimetro.layout.e06.scale import scaled_shell                          # noqa: E402
from escalimetro.layout.model import load_modules                              # noqa: E402
from escalimetro.schemas.floorplate import Floorplate                          # noqa: E402

CASE = os.path.join(ROOT, "cases", "001_gps_403")
MODS = os.path.join(ROOT, "program_templates", "modules_office.json")
BRIEFS = ["DENSO", "EQUILIBRADO", "EJECUTIVO"]

GRUPO = {"private_office": "privados",
         "meeting_4": "salas", "meeting_8": "salas", "boardroom_12": "salas",
         "reception": "apoyo", "kitchenette": "apoyo", "dining": "apoyo",
         "lounge": "apoyo", "phone_booth": "apoyo",
         "workstation_cluster": "puestos", "workstation_row": "puestos"}

#: umbrales de SEÑAL, declarados antes de mirar ningún número
PLAUSIBLE_MAX = 0.80          # ≤ 80 % del área disponible → CLEARLY_PLAUSIBLE
TIGHT_MAX = 1.00              # 80–100 % → TIGHT; > 100 % → CLEARLY_OVER_CAPACITY


def main():
    ctx = from_case_dir(CASE)
    fp = Floorplate.load(ctx.require_floorplate())
    shell = scaled_shell(fp, 1.0)
    mods, _ = load_modules(MODS)
    raw = json.load(open(MODS, encoding="utf-8"))["modules"]
    perimetro = shell.perimeter.area
    core = sum(c.area for c in shell.core)
    cols = sum(c.area for c in shell.columns)
    usable = shell.usable.area                 # perímetro − core (en 403 el núcleo es CONTIGUO, no interior)
    # lo que el solver realmente ve: celdas libres de la rejilla (descuenta pilares y bordes)
    from escalimetro.layout.grid import Grid
    g = Grid(shell)
    disponible = float(g.free_base.sum()) * g.cell ** 2
    out = {"case": "001_gps_403",
           "shell": {"perimetro_m2": round(perimetro, 1), "core_m2": round(core, 1),
                     "core_es_interior": bool(shell.perimeter.intersection(
                         __import__("shapely.ops", fromlist=["unary_union"]).unary_union(shell.core)).area > 1.0)
                     if shell.core else False,
                     "usable_m2": round(usable, 1), "pilares_m2": round(cols, 2),
                     "n_pilares": len(shell.columns),
                     "disponible_m2": round(disponible, 1),
                     "disponible_fuente": "Grid.free_base (celdas libres que ve el solver)"},
           "circulacion_factor": CIRC_FACTOR,
           "umbrales": {"CLEARLY_PLAUSIBLE": f"ratio <= {PLAUSIBLE_MAX}",
                        "TIGHT": f"{PLAUSIBLE_MAX} < ratio <= {TIGHT_MAX}",
                        "CLEARLY_OVER_CAPACITY": f"ratio > {TIGHT_MAX}"},
           "briefs": {}}
    for b in BRIEFS:
        brief = load_brief(os.path.join(ROOT, "briefs", f"BRIEF_{b}.json"))
        prog = compile_program(brief, modules=mods)
        g = {"puestos": 0.0, "privados": 0.0, "salas": 0.0, "apoyo": 0.0}
        # puestos: huella real del asiento (1.6 × (0.8 + 0.8)), no la del cluster con su pasillo
        ws = raw["workstation"]
        g["puestos"] = brief.open_workstations * ws["w"] * (ws["d"] + ws.get("chair_zone_d", 0.8))
        for p in prog["program"]:
            m = p["module"]
            if m in ("workstation_cluster", "workstation_row"):
                continue
            g[GRUPO[m]] += p["count"] * raw[m]["w"] * raw[m]["d"]
        neto = sum(g.values())
        circ = neto * CIRC_FACTOR / (1 - CIRC_FACTOR)      # circulación como 20 % del total ocupado
        total = neto + circ
        ratio = total / disponible
        senal = ("CLEARLY_PLAUSIBLE" if ratio <= PLAUSIBLE_MAX else
                 "TIGHT" if ratio <= TIGHT_MAX else "CLEARLY_OVER_CAPACITY")
        out["briefs"][b] = {
            "puestos": brief.open_workstations,
            "privados": brief.room_count("private_office"),
            "recintos": sum(p["count"] for p in prog["program"]
                            if p["module"] not in ("workstation_cluster", "workstation_row")),
            "area_min_puestos_m2": round(g["puestos"], 1),
            "area_min_privados_m2": round(g["privados"], 1),
            "area_min_salas_m2": round(g["salas"], 1),
            "area_min_apoyo_m2": round(g["apoyo"], 1),
            "area_min_neta_m2": round(neto, 1),
            "circulacion_min_estimada_m2": round(circ, 1),
            "area_min_total_m2": round(total, 1),
            "disponible_m2": round(disponible, 1),
            "ratio": round(ratio, 3),
            "holgura_m2": round(disponible - total, 1),
            "senal": senal,
        }
    d = os.path.join(ROOT, "cases", "E25")
    os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, "E25_AREA_SANITY.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
