"""E24 §11/§15 — evalúa ShellInputV1 sobre los casos y guarda el artefacto por caso."""
from __future__ import annotations
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from escalimetro.shell_input import evaluate            # noqa: E402

CASES = ["cases/001_gps_403", "cases/002_gps_401", "cases/003_res_unknown"]

def main():
    res = {}
    for c in CASES:
        r = evaluate(c)
        d = os.path.join(c, "shell_input")
        os.makedirs(d, exist_ok=True)
        json.dump(r.to_dict(), open(os.path.join(d, "shell_input_v1.json"), "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
        res[os.path.basename(c)] = r.to_dict()
        print(f"{os.path.basename(c):<20} {r.verdict:<18} hitl={r.hitl_required}")
    os.makedirs("cases/E24", exist_ok=True)
    json.dump(res, open("cases/E24/shell_acceptance.json", "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    return 0

if __name__ == "__main__":
    sys.exit(main())
