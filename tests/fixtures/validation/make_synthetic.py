"""Genera el CSV SINTÉTICO de prueba. NO son evaluadores reales (§52): cada respondent_id lleva el
prefijo SYNTHETIC_TEST_ONLY y el dataset nunca debe mezclarse con datos de entrevistas.

Está construido para que el gate de layout PASE y el de producto FALLE: así los tests comprueban que
los dos gates son de verdad independientes y que la scorecard sabe decir que no."""
import csv, io, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
from escalimetro.validation.blind import display_order_label, mapping_for          # noqa: E402
from escalimetro.validation.schema import COLUMNS                                  # noqa: E402

# rol, preferida REAL, send por alt, conf por alt, bloqueante, cambio, producto
PEOPLE = [
    ("BROKER",           "B", {"A": "YES", "B": "YES", "C": "NO"},  {"A": 4, "B": 5, "C": 2},
     {"C": "RECEPTION"},   {"A": "MINOR", "B": "NO_CHANGE", "C": "MATERIAL"},
     ("ASK_ARCHITECT", "3-5D", "WEEKLY", "YES", "51-75", "SOMETIMES")),
    ("BROKER",           "C", {"A": "NO", "B": "YES", "C": "YES"},  {"A": 3, "B": 4, "C": 4},
     {"A": "CIRCULATION"}, {"A": "MATERIAL", "B": "MINOR", "C": "MINOR"},
     ("ASK_ARCHITECT", "1-2D", "WEEKLY", "YES", "26-50", "SOMETIMES")),
    ("LEASING",          "C", {"A": "YES", "B": "YES", "C": "YES"}, {"A": 4, "B": 4, "C": 5},
     {},                   {"A": "MINOR", "B": "MINOR", "C": "NO_CHANGE"},
     ("ASK_ARCHITECT", "3-5D", "MONTHLY", "NO", "26-50", "IMPORTANT_CLIENTS_ONLY")),
    ("COMMERCIAL_AGENT", "A", {"A": "YES", "B": "NO", "C": "YES"},  {"A": 5, "B": 2, "C": 4},
     {"B": "BOARDROOM"},   {"A": "NO_CHANGE", "B": "REDESIGN", "C": "MINOR"},
     ("I_DO_IT", "<1H", "MONTHLY", "NO", "1-25", "NO")),
    ("REAL_ESTATE_PRO",  "B", {"A": "NO", "B": "NO", "C": "NO"},    {"A": 2, "B": 3, "C": 3},
     {"B": "RECEPTION"},   {"A": "MATERIAL", "B": "MATERIAL", "C": "MATERIAL"},
     ("ASK_LANDLORD", "SAME_DAY", "FEW_PER_YEAR", "NO", "0", "ALWAYS")),
    ("ARCHITECT",        "A", {"A": "NO", "B": "NO", "C": "NO"},    {"A": 3, "B": 2, "C": 3},
     {"A": "PRIVACY", "B": "PRIVACY", "C": "PRIVACY"},
     {"A": "MATERIAL", "B": "MATERIAL", "C": "MATERIAL"},
     ("I_DO_IT", "<1H", "WEEKLY", "NO", "1-25", "ALWAYS")),
]
TAG = {"A": "EFFICIENCY", "B": "BALANCE", "C": "COLLABORATION"}


def build() -> str:
    rows = []
    for i, (role, pref, send, conf, blk, chg, prod) in enumerate(PEOPLE):
        mp = mapping_for(i)
        inv = {v: k for k, v in mp.items()}
        rid = f"SYNTHETIC_TEST_ONLY_R{i + 1:02d}"
        method, turn, freq, use2, share, qa = prod
        for b in ("X", "Y", "Z"):
            a = mp[b]
            r = {c: "" for c in COLUMNS}
            r.update(respondent_id=rid, role=role, years_experience=str(8 + i),
                     session_date="2026-09-10", option_blind=b, option_real=a,
                     display_order=display_order_label(i), send_to_client=send[a],
                     confidence=str(conf[a]), blocking_error=("YES" if a in blk else "NO"),
                     defect_categories=blk.get(a, ""), change_magnitude=chg[a],
                     strategy_tags=TAG[a], reception_ok=("NO" if a == "C" else "YES"),
                     move_reception=("YES" if a == "C" else "NO"),
                     preferred_option=inv[pref], options_distinct=("YES" if i < 4 else "NO"),
                     similar_pair=("" if i < 4 else "ALL_THREE"),
                     current_testfit_method=method, current_turnaround=turn, frequency=freq,
                     useful_generated="YES", would_use_under_2min=use2,
                     use_case=("DURING_SEARCH" if use2 == "YES" else "WOULD_NOT_USE"),
                     share_of_searches=share, human_qa_need=qa,
                     qa_time_minutes=("15-30" if role == "ARCHITECT" else ""),
                     time_to_first_decision_s=str(20 + 7 * i),
                     observations="FIRST_OPTION_LOOKED_AT:X|ASKED_SCALE",
                     level2_done=("YES" if i < 3 else "NO"), comparison_vs_architect="SIMILAR",
                     brand_understood="YES", notes="SYNTHETIC_TEST_ONLY")
            rows.append(r)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader(); w.writerows(rows)
    return buf.getvalue()


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "SYNTHETIC_TEST_ONLY_responses.csv")
    open(out, "w", encoding="utf-8").write(build())
    print("escrito", out)
