"""E24 §17 — tabla de 18 columnas por combinación brief × alternativa, PEDIDO vs ENTREGADO."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
FILAS = ["DENSO", "EQUILIBRADO", "EJECUTIVO"]
COLS = ["A", "B", "C"]

COLUMNAS = ["brief", "alt", "estado", "puestos_ped", "puestos_ent", "privados_ped", "privados_ent",
            "recintos_ped", "recintos_ent", "programa_completo", "violaciones", "colisiones",
            "circulacion_ok", "util_m2", "programado_m2", "circulacion_m2", "desperdicio_m2",
            "runtime_s"]


def _j(p):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def filas():
    out = []
    for b in FILAS:
        base = os.path.join(CASE, "layouts", f"E24_{b}")
        prog = _j(os.path.join(base, "program_compiled.json")) or {}
        sem = prog.get("brief_semantics", {})
        ped_ws = sem.get("open_workstations")
        ped_pri = (sem.get("rooms") or {}).get("private_office", 0)
        ped_rec = sum((sem.get("rooms") or {}).values())
        perf = _j(os.path.join(base, "performance_profile.json")) or {}
        for a in COLS:
            d = os.path.join(base, "alternatives", a)
            met = _j(os.path.join(d, "metrics.json"))
            nf = _j(os.path.join(d, "no_fit.json"))
            if met is None:
                est = {"NO_FIT_INFEASIBLE": "NO_FIT", "NO_RESULT_TIMEOUT": "SIN_RESULTADO"}.get(
                    (nf or {}).get("status"), "NO_EJECUTADO")
                out.append({"brief": b, "alt": a, "estado": est,
                            "puestos_ped": ped_ws, "puestos_ent": 0,
                            "privados_ped": ped_pri, "privados_ent": 0,
                            "recintos_ped": ped_rec, "recintos_ent": 0,
                            "programa_completo": False, "violaciones": None, "colisiones": None,
                            "circulacion_ok": None, "util_m2": None, "programado_m2": None,
                            "circulacion_m2": None, "desperdicio_m2": None,
                            "runtime_s": (nf or {}).get("runtime_s")})
                continue
            pc = met["program_completeness"]
            rooms = {k: v for k, v in (pc["rooms"] or {}).items()
                     if k not in ("workstation_cluster", "workstation_row")}
            out.append({
                "brief": b, "alt": a, "estado": "FIT",
                "puestos_ped": ped_ws, "puestos_ent": int(str(pc["open_seats"]).split("/")[0]),
                "privados_ped": ped_pri, "privados_ent": rooms.get("private_office", 0),
                "recintos_ped": ped_rec, "recintos_ent": sum(rooms.values()),
                "programa_completo": bool(pc["complete"]),
                "violaciones": met["hard_constraint_violations"], "colisiones": met["collisions"],
                "circulacion_ok": bool(met["circulation_connectivity"]),
                "util_m2": met["usable_area_m2"], "programado_m2": met["net_programmed_area_m2"],
                "circulacion_m2": met["circulation_area_m2"], "desperdicio_m2": met["wasted_area_m2"],
                "runtime_s": (perf.get(a) or {}).get("total_s"),
            })
    return out


def md(rows):
    an = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in COLUMNAS}
    o = ["| " + " | ".join(c.ljust(an[c]) for c in COLUMNAS) + " |",
         "|" + "|".join("-" * (an[c] + 2) for c in COLUMNAS) + "|"]
    for r in rows:
        o.append("| " + " | ".join(str(r[c]).ljust(an[c]) for c in COLUMNAS) + " |")
    return "\n".join(o)


def main():
    rows = filas()
    os.makedirs(os.path.join(ROOT, "cases", "E24"), exist_ok=True)
    json.dump({"columnas": COLUMNAS, "filas": rows},
              open(os.path.join(ROOT, "cases", "E24", "E24_TABLA_18_COLUMNAS.json"), "w",
                   encoding="utf-8"), indent=2, ensure_ascii=False)
    t = md(rows)
    open(os.path.join(ROOT, "cases", "E24", "E24_TABLA_18_COLUMNAS.md"), "w", encoding="utf-8").write(t + "\n")
    print(t)
    print(f"\ncolumnas = {len(COLUMNAS)}  ·  filas = {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
