"""E13 — esquema de captura. Una fila por RESPONDENT × OPTION (§25).

Campos por evaluador (se repiten idénticos en sus tres filas) y campos por opción (cambian fila a
fila). `validate_rows` comprueba las dos cosas: que los valores estén en el vocabulario y que los
campos por evaluador no se contradigan entre sus propias filas — un CSV que dice que el mismo broker
prefiere X en una fila e Y en otra está mal capturado y no debe llegar a la scorecard."""
from __future__ import annotations

from typing import Dict, List, Tuple

YN = ["YES", "NO"]

#: columnas en orden. El CSV vacío se emite con exactamente esta cabecera.
COLUMNS: List[str] = [
    # --- identificación --------------------------------------------------------------------------
    "respondent_id", "role", "years_experience", "session_date",
    # --- cegado ----------------------------------------------------------------------------------
    "option_blind", "option_real", "display_order",
    # --- por opción ------------------------------------------------------------------------------
    "send_to_client", "confidence", "blocking_error", "defect_categories",
    "change_magnitude", "strategy_tags", "reception_ok", "move_reception",
    # --- por evaluador ---------------------------------------------------------------------------
    "preferred_option", "options_distinct", "similar_pair",
    "current_testfit_method", "current_turnaround", "frequency",
    "useful_generated", "would_use_under_2min", "use_case", "share_of_searches", "human_qa_need",
    # --- opcionales ------------------------------------------------------------------------------
    "qa_time_minutes", "time_to_first_decision_s", "observations",
    "level2_done", "comparison_vs_architect", "brand_understood", "notes",
]

#: campos que deben ser idénticos en las tres filas de un mismo evaluador
PER_RESPONDENT = ["role", "years_experience", "session_date", "display_order", "preferred_option",
                  "options_distinct", "similar_pair", "current_testfit_method", "current_turnaround",
                  "frequency", "useful_generated", "would_use_under_2min", "use_case", "share_of_searches",
                  "human_qa_need", "comparison_vs_architect", "brand_understood"]

ROLES = ["BROKER", "LEASING", "COMMERCIAL_AGENT", "REAL_ESTATE_PRO", "ARCHITECT", "OTHER"]
#: sólo estos cuentan en el numerador del gate de layout (§2: los arquitectos son referencia secundaria)
COMMERCIAL_ROLES = ["BROKER", "LEASING", "COMMERCIAL_AGENT", "REAL_ESTATE_PRO"]

DEFECTS = ["ARRIVAL", "RECEPTION", "CLIENT_ROUTE", "BOARDROOM", "MEETING_ROOMS", "PRIVACY",
           "WORKSTATIONS", "DAYLIGHT", "KITCHEN_DINING", "LOUNGE", "CIRCULATION", "ADJACENCY",
           "DENSITY", "READABILITY", "PROGRAM_MISSING", "PROGRAM_EXCESS", "OTHER"]

STRATEGY_TAGS = ["EFFICIENCY", "BALANCE", "COLLABORATION", "FORMAL", "CLIENT_FACING", "DENSE",
                 "OPEN", "PRIVATE", "OTHER"]
#: qué etiqueta corresponde a la intención programada de cada alternativa (§15)
INTENDED_TAG = {"A": "EFFICIENCY", "B": "BALANCE", "C": "COLLABORATION"}

CHANGE_MAGNITUDE = ["NO_CHANGE", "MINOR", "MATERIAL", "REDESIGN"]
#: MINOR o menos = enviable sin rehacer nada de fondo
CHANGE_OK = ["NO_CHANGE", "MINOR"]

TURNAROUND = ["<1H", "SAME_DAY", "1-2D", "3-5D", ">5D", "UNKNOWN"]
SLOW_TURNAROUND = ["1-2D", "3-5D", ">5D"]
FREQUENCY = ["WEEKLY_MULTIPLE", "WEEKLY", "MONTHLY", "FEW_PER_YEAR", "ALMOST_NEVER"]
FREQUENT = ["WEEKLY_MULTIPLE", "WEEKLY", "MONTHLY"]
METHODS = ["I_DO_IT", "ASK_ARCHITECT", "ASK_LANDLORD", "ASK_CLIENT", "NO_TESTFIT", "OTHER"]
USE_CASES = ["BEFORE_SHOWING", "DURING_SEARCH", "IN_PROPOSAL", "COMPARE_BUILDINGS",
             "WIN_LISTING", "WOULD_NOT_USE", "OTHER"]
SHARE = ["0", "1-25", "26-50", "51-75", "76-100"]
SHARE_MEANINGFUL = ["26-50", "51-75", "76-100"]
QA_NEED = ["ALWAYS", "SOMETIMES", "IMPORTANT_CLIENTS_ONLY", "NO"]
QA_TIME = ["0", "<5", "5-15", "15-30", "30-60", ">60"]
COMPARISON = ["MUCH_WORSE", "WORSE", "SIMILAR", "BETTER", "MUCH_BETTER", ""]
SIMILAR_PAIR = ["X-Y", "X-Z", "Y-Z", "ALL_THREE", ""]
PREFERRED = ["X", "Y", "Z", "NONE"]
OBSERVATIONS = ["FIRST_OPTION_LOOKED_AT", "ZOOM_NEEDED", "ASKED_SCALE", "ASKED_WINDOWS",
                "ASKED_ACCESS", "ASKED_COLUMNS", "ASKED_CAPACITY", "ASKED_AI", "ASKED_EDITING"]

ENUMS: Dict[str, List[str]] = {
    "role": ROLES, "option_blind": ["X", "Y", "Z"], "option_real": ["A", "B", "C"],
    "send_to_client": YN, "blocking_error": YN, "change_magnitude": CHANGE_MAGNITUDE,
    "reception_ok": YN, "move_reception": YN, "preferred_option": PREFERRED,
    "options_distinct": YN, "similar_pair": SIMILAR_PAIR, "current_testfit_method": METHODS,
    "current_turnaround": TURNAROUND, "frequency": FREQUENCY,
    "useful_generated": YN + [""], "would_use_under_2min": YN,
    "use_case": USE_CASES, "share_of_searches": SHARE, "human_qa_need": QA_NEED,
    "qa_time_minutes": QA_TIME + [""], "comparison_vs_architect": COMPARISON,
    "brand_understood": YN + [""], "level2_done": YN + [""],
}
MULTI: Dict[str, List[str]] = {"defect_categories": DEFECTS, "strategy_tags": STRATEGY_TAGS,
                               "observations": OBSERVATIONS}

HEADER = ",".join(COLUMNS)


def empty_csv() -> str:
    """CSV de captura vacío: cabecera y nada más. E13 no inventa evaluadores (§52)."""
    return HEADER + "\n"


def _split(v: str) -> List[str]:
    return [x.strip() for x in (v or "").split("|") if x.strip()]


def validate_rows(rows: List[Dict[str, str]]) -> List[str]:
    """Lista de problemas encontrados. Vacía = el dataset es utilizable."""
    err: List[str] = []
    if not rows:
        return ["dataset vacío"]
    for i, r in enumerate(rows, 1):
        missing = [c for c in COLUMNS if c not in r]
        if missing:
            err.append(f"fila {i}: faltan columnas {missing}")
            continue
        for col, allowed in ENUMS.items():
            v = (r.get(col) or "").strip()
            if v and v not in allowed:
                err.append(f"fila {i}: {col}='{v}' fuera del vocabulario")
        for col, allowed in MULTI.items():
            for v in _split(r.get(col, "")):
                # FIRST_OPTION_LOOKED_AT viaja con la etiqueta ciega pegada: 'FIRST_OPTION_LOOKED_AT:X'
                base = v.split(":", 1)[0]
                if base not in allowed:
                    err.append(f"fila {i}: {col} contiene '{v}', fuera del vocabulario")
                elif base == "FIRST_OPTION_LOOKED_AT" and v.split(":", 1)[-1] not in ("X", "Y", "Z", base):
                    err.append(f"fila {i}: observations '{v}' debe apuntar a X, Y o Z")
        c = (r.get("confidence") or "").strip()
        if c and c not in list("12345"):
            err.append(f"fila {i}: confidence='{c}' debe ser 1..5")

    by: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        by.setdefault(r["respondent_id"], []).append(r)
    for rid, rs in by.items():
        if len(rs) != 3:
            err.append(f"{rid}: {len(rs)} filas, se esperan 3 (una por opción)")
        if len({r["option_real"] for r in rs}) != len(rs):
            err.append(f"{rid}: alternativa real repetida")
        if len({r["option_blind"] for r in rs}) != len(rs):
            err.append(f"{rid}: etiqueta ciega repetida")
        for col in PER_RESPONDENT:
            vals = {(r.get(col) or "").strip() for r in rs}
            if len(vals) > 1:
                err.append(f"{rid}: '{col}' inconsistente entre sus filas ({sorted(vals)})")
    return err


def preferred_real(rows_of_respondent: List[Dict[str, str]]) -> str:
    """Traduce la preferencia ciega (X/Y/Z) a la alternativa real (A/B/C). '' si eligió NINGUNA."""
    p = (rows_of_respondent[0].get("preferred_option") or "").strip()
    if p in ("", "NONE"):
        return ""
    for r in rows_of_respondent:
        if r["option_blind"] == p:
            return r["option_real"]
    return ""
