"""E25 §17 — tabla final 3×3 con la semántica de estados de §8."""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
FILAS = ["DENSO", "EQUILIBRADO", "EJECUTIVO"]
COLS = ["A", "B", "C"]

COLUMNAS = ["brief", "strategy", "status", "solver_status",
            "req_workstations", "del_workstations", "req_privates", "del_privates",
            "req_rooms", "del_rooms", "program_complete", "hard_violations", "collisions",
            "circulation_connected", "cand_raw", "cand_final", "cand_pruning_pct",
            "solver_runtime_s", "total_runtime_s", "geometry_hash"]


def _j(p):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def filas():
    out = []
    for b in FILAS:
        base = os.path.join(CASE, "layouts", f"E25_{b}")
        prog = _j(os.path.join(base, "program_compiled.json")) or {}
        sem = prog.get("brief_semantics", {})
        req_ws = sem.get("open_workstations")
        req_pri = (sem.get("rooms") or {}).get("private_office", 0)
        req_rooms = sum((sem.get("rooms") or {}).values())
        perf = _j(os.path.join(base, "performance_profile.json")) or {}
        cand = _j(os.path.join(base, "candidate_stats.json")) or {}
        for a in COLS:
            d = os.path.join(base, "alternatives", a)
            met = _j(os.path.join(d, "metrics.json"))
            nf = _j(os.path.join(d, "no_fit.json"))
            cs = cand.get(a, {})
            fila = {c: None for c in COLUMNAS}
            fila.update({"brief": b, "strategy": a,
                         "req_workstations": req_ws, "req_privates": req_pri, "req_rooms": req_rooms,
                         "cand_raw": cs.get("brutos"), "cand_final": cs.get("finales"),
                         "cand_pruning_pct": cs.get("descartados_pct")})
            if met is None:
                fila.update({"status": (nf or {}).get("status", "NO_EJECUTADO"),
                             "solver_status": (nf or {}).get("solver_status"),
                             "del_workstations": 0, "del_privates": 0, "del_rooms": 0,
                             "program_complete": False,
                             "total_runtime_s": (nf or {}).get("runtime_s")})
                out.append(fila); continue
            pc = met["program_completeness"]
            rooms = {k: v for k, v in (pc["rooms"] or {}).items()
                     if k not in ("workstation_cluster", "workstation_row")}
            lay = os.path.join(d, "layout.json")
            gh = hashlib.sha256(open(lay, "rb").read()).hexdigest()[:16] if os.path.exists(lay) else None
            fila.update({
                "status": "FIT", "solver_status": (perf.get(a) or {}).get("status_feasibility"),
                "del_workstations": int(str(pc["open_seats"]).split("/")[0]),
                "del_privates": rooms.get("private_office", 0), "del_rooms": sum(rooms.values()),
                "program_complete": bool(pc["complete"]),
                "hard_violations": met["hard_constraint_violations"], "collisions": met["collisions"],
                "circulation_connected": bool(met["circulation_connectivity"]),
                "solver_runtime_s": round((perf.get(a) or {}).get("solver_feasibility_s", 0)
                                          + (perf.get(a) or {}).get("solver_optimization_s", 0), 2),
                "total_runtime_s": (perf.get(a) or {}).get("total_s"),
                "geometry_hash": gh,
            })
            out.append(fila)
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
    d = os.path.join(ROOT, "cases", "E25"); os.makedirs(d, exist_ok=True)
    json.dump({"columnas": COLUMNAS, "filas": rows},
              open(os.path.join(d, "E25_TABLA_FINAL.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    t = md(rows)
    open(os.path.join(d, "E25_TABLA_FINAL.md"), "w", encoding="utf-8").write(t + "\n")
    print(t)
    print(f"\ncolumnas = {len(COLUMNAS)} · filas = {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
