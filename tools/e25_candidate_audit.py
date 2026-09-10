"""E25 §7 — auditoría del generador de candidatos. Cuenta, no opina."""
from __future__ import annotations
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, os.path.join(ROOT, "tools"))
from e25_offline_experiments import contexto, geometria                        # noqa: E402

BRIEFS = ["DENSO", "EQUILIBRADO", "EJECUTIVO"]
CAP, STEP = 200, 1.0


def main():
    out = []
    for b in BRIEFS:
        shell, grid, feats, mods, brief, prog, e05, specs = contexto(b)
        pedidos = {p["module"]: p["count"] for p in prog["program"]}
        for spec in specs:
            strat, els, cands, gs, ps = geometria(shell, grid, feats, mods, prog, spec, e05, STEP, CAP)
            # filtro de dominio de ruta que aplica solve_free ANTES de construir el modelo
            maxp = {"reception": 8.0 - 0.4}
            maxp.update({k: float(v) for k, v in spec.solver_extra.get("module_max_path", {}).items()})
            por_mod = {}
            for c in cands:
                if c.module in maxp and c.path_m > maxp[c.module]:
                    por_mod.setdefault(c.module, {"filtrados_por_ruta": 0, "en_modelo": 0})
                    por_mod[c.module]["filtrados_por_ruta"] += 1
                    continue
                por_mod.setdefault(c.module, {"filtrados_por_ruta": 0, "en_modelo": 0})
                por_mod[c.module]["en_modelo"] += 1
            filas = {}
            for m, n in sorted(pedidos.items()):
                d = por_mod.get(m, {"filtrados_por_ruta": 0, "en_modelo": 0})
                brutos = gs["brutos_por_modulo"].get(m, 0)
                pod = ps["por_modulo"].get(m, {})
                filas[m] = {"instancias_pedidas": n, "brutos": brutos,
                            "tras_dominancia": pod.get("tras_dominancia"),
                            "tras_cap": pod.get("finales"), "cap_activo": pod.get("cap_activo"),
                            "filtrados_por_ruta": d["filtrados_por_ruta"],
                            "en_modelo": d["en_modelo"],
                            "candidatos_por_instancia": round(d["en_modelo"] / n, 1) if n else None}
            out.append({"brief": b, "alt": spec.alt, "bench_cfgs": list(spec.bench_cfgs),
                        "module_max_path": spec.solver_extra.get("module_max_path", {}),
                        "modulos": filas})
            print(f"\n=== {b} / {spec.alt} ===")
            print(f"{'módulo':<22}{'pide':>5}{'brutos':>8}{'domin':>7}{'cap':>6}{'ruta✗':>7}{'modelo':>8}{'x inst':>8}")
            for m, f in filas.items():
                print(f"{m:<22}{f['instancias_pedidas']:>5}{f['brutos']:>8}{str(f['tras_dominancia']):>7}"
                      f"{str(f['tras_cap']):>6}{f['filtrados_por_ruta']:>7}{f['en_modelo']:>8}"
                      f"{str(f['candidatos_por_instancia']):>8}")
    d = os.path.join(ROOT, "cases", "E25"); os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, "E25_AUDITORIA_CANDIDATOS.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
