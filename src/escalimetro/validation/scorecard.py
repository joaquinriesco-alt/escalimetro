"""E13 — scorecard y gates. Cálculo, no juicio: los umbrales están fijados antes de ver datos (§27, §55).

Dos gates independientes (§29):

    LAYOUT QUALITY GATE  — ¿el material sirve para mandárselo a un cliente?
    PRODUCT VALUE GATE   — ¿alguien necesita esto?

Ambos deben pasar para que el producto avance. Que uno pase y el otro no también es información:
layouts buenos sin dolor = solución sin problema; dolor grande con layouts flojos = arreglar el motor.

Regla anti-autoengaño: todas las métricas duras se calculan sobre la ALTERNATIVA PREFERIDA de cada
evaluador, no sobre 'al menos una de las tres'. Con tres opciones independientes al 40% de send rate,
'al menos una' da 78% y el gate pasaría sin que ninguna alternativa sea enviable. Ese agujero está
cerrado a propósito."""
from __future__ import annotations

import csv
import io
from typing import Dict, List, Optional

from .schema import (CHANGE_OK, COMMERCIAL_ROLES, FREQUENT, INTENDED_TAG, SHARE_MEANINGFUL,
                     SLOW_TURNAROUND, preferred_real, validate_rows)

# ---------------------------------------------------------------------------------------------------
# UMBRALES FIJADOS — no se tocan después de ver resultados (§27)
# ---------------------------------------------------------------------------------------------------
THRESHOLDS = {
    "MIN_RESPONDENTS": 5,
    "MIN_COMMERCIAL": 4,          # de los 5, al menos 4 deben ser del segmento comercial
    "G1_SEND_PREFERRED": 0.70,    # send rate sobre la alternativa preferida
    "G2_CONF4_PREFERRED": 0.60,   # confianza >= 4 sobre la preferida
    "G3_SHARED_BLOCKER": 0.30,    # ningún defecto bloqueante compartido llega a este %
    "G4_CHANGE_OK": 0.70,         # NO_CHANGE o MINOR sobre la preferida
    "P1_PAIN": 0.60,              # turnaround lento o no hace test-fit
    "P2_FREQUENCY": 0.50,         # al menos mensual
    "P3_WOULD_USE": 0.70,
    "P4_SHARE": 0.50,             # >=26% de sus búsquedas
}


def _pct(n: int, d: int) -> Optional[float]:
    return None if not d else round(100.0 * n / d, 1)


def load_csv(text: str) -> List[Dict[str, str]]:
    return [dict(r) for r in csv.DictReader(io.StringIO(text))]


def by_respondent(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        out.setdefault(r["respondent_id"], []).append(r)
    return out


def _split(v: str) -> List[str]:
    return [x.strip() for x in (v or "").split("|") if x.strip()]


# ---------------------------------------------------------------------------------------------------
def compute(rows: List[Dict[str, str]], segment: str = "COMMERCIAL") -> Dict:
    """`segment`: COMMERCIAL (brokers y afines), ARCHITECT, o ALL. Nunca se mezclan sin segmentar (§2)."""
    errors = validate_rows(rows) if rows else ["dataset vacío"]
    people = by_respondent(rows)
    if segment == "COMMERCIAL":
        people = {k: v for k, v in people.items() if v[0].get("role") in COMMERCIAL_ROLES}
    elif segment == "ARCHITECT":
        people = {k: v for k, v in people.items() if v[0].get("role") == "ARCHITECT"}

    n = len(people)
    n_comm = len([v for v in by_respondent(rows).values() if v[0].get("role") in COMMERCIAL_ROLES])

    pref_rows, send_pref, conf4_pref, change_ok = [], 0, 0, 0
    blockers: Dict[str, int] = {}
    for rid, rs in people.items():
        alt = preferred_real(rs)
        row = next((r for r in rs if r["option_real"] == alt), None)
        if row is None:                               # eligió NINGUNA: cuenta como no enviable
            pref_rows.append(None)
            continue
        pref_rows.append(row)
        if row.get("send_to_client") == "YES":
            send_pref += 1
        if (row.get("confidence") or "").isdigit() and int(row["confidence"]) >= 4:
            conf4_pref += 1
        if row.get("change_magnitude") in CHANGE_OK:
            change_ok += 1
        if row.get("blocking_error") == "YES":
            for d in _split(row.get("defect_categories", "")):
                blockers[d] = blockers.get(d, 0) + 1

    worst_blocker, worst_n = (max(blockers.items(), key=lambda kv: kv[1]) if blockers else ("", 0))

    # --- por alternativa (§28) ---------------------------------------------------------------------
    per_alt: Dict[str, Dict] = {}
    for a in ("A", "B", "C"):
        rs = [r for rid, v in people.items() for r in v if r["option_real"] == a]
        yes = sum(1 for r in rs if r.get("send_to_client") == "YES")
        confs = [int(r["confidence"]) for r in rs if (r.get("confidence") or "").isdigit()]
        blk = sum(1 for r in rs if r.get("blocking_error") == "YES")
        prefs = sum(1 for rid, v in people.items() if preferred_real(v) == a)
        tags = [t for r in rs for t in _split(r.get("strategy_tags", ""))]
        recognised = sum(1 for r in rs if INTENDED_TAG[a] in _split(r.get("strategy_tags", "")))
        rec_ok = sum(1 for r in rs if r.get("reception_ok") == "YES")
        mv = sum(1 for r in rs if r.get("move_reception") == "YES")
        sr, cr, br = _pct(yes, len(rs)), _pct(sum(1 for c in confs if c >= 4), len(confs)), _pct(blk, len(rs))
        per_alt[a] = {
            "n": len(rs), "send_rate": sr, "preferred_n": prefs,
            "mean_confidence": (round(sum(confs) / len(confs), 2) if confs else None),
            "conf4_rate": cr, "blocking_error_rate": br,
            "strategy_recognition": _pct(recognised, len(rs)), "strategy_tags": tags,
            "reception_acceptance": _pct(rec_ok, len(rs)), "move_reception_rate": _pct(mv, len(rs)),
            "classification": _classify(sr, cr, br),
        }

    # --- producto (§18, §19, §20) ------------------------------------------------------------------
    firsts = [v[0] for v in people.values()]
    pain = sum(1 for r in firsts if r.get("current_turnaround") in SLOW_TURNAROUND
               or r.get("current_testfit_method") == "NO_TESTFIT")
    freq = sum(1 for r in firsts if r.get("frequency") in FREQUENT)
    use = sum(1 for r in firsts if r.get("would_use_under_2min") == "YES")
    share = sum(1 for r in firsts if r.get("share_of_searches") in SHARE_MEANINGFUL)
    distinct = sum(1 for r in firsts if r.get("options_distinct") == "YES")
    qa = {k: sum(1 for r in firsts if r.get("human_qa_need") == k)
          for k in ("ALWAYS", "SOMETIMES", "IMPORTANT_CLIENTS_ONLY", "NO")}

    m = {
        "segment": segment, "n_respondents": n, "n_commercial_total": n_comm,
        "errors": errors if rows else ["dataset vacío — aún no hay entrevistas"],
        "send_rate_preferred": _pct(send_pref, n),
        "conf4_rate_preferred": _pct(conf4_pref, n),
        "change_ok_rate_preferred": _pct(change_ok, n),
        "worst_shared_blocker": worst_blocker,
        "worst_shared_blocker_rate": _pct(worst_n, n),
        "distinctness_rate": _pct(distinct, n),
        "pain_rate": _pct(pain, n), "frequency_rate": _pct(freq, n),
        "would_use_rate": _pct(use, n), "share_rate": _pct(share, n),
        "qa_requirement": qa,
        "per_alternative": per_alt,
    }
    m["layout_gate"] = _layout_gate(m, n_comm)
    m["product_gate"] = _product_gate(m)
    m["gate_result"] = ("PASS" if m["layout_gate"]["result"] == "PASS"
                        and m["product_gate"]["result"] == "PASS" else
                        ("INSUFFICIENT_DATA" if n < THRESHOLDS["MIN_RESPONDENTS"] else "FAIL"))
    return m


def _classify(send_rate, conf4_rate, blocking_rate) -> str:
    """§28 — clasificación por alternativa, sin usar ningún score de IA."""
    if send_rate is None:
        return "NO_DATA"
    if send_rate >= 70 and (conf4_rate or 0) >= 60 and (blocking_rate or 0) < 30:
        return "BROKER_READY"
    if send_rate < 50:
        return "REJECTED"
    return "BORDERLINE"


def _chk(name: str, value, threshold, ok: bool, detail: str) -> Dict:
    return {"check": name, "value": value, "threshold": threshold,
            "status": ("PASS" if ok else "FAIL"), "detail": detail}


def _layout_gate(m: Dict, n_comm: int) -> Dict:
    T, n = THRESHOLDS, m["n_respondents"]
    if n < T["MIN_RESPONDENTS"]:
        return {"result": "INSUFFICIENT_DATA", "checks": [],
                "detail": f"{n} evaluadores; el protocolo exige {T['MIN_RESPONDENTS']}"}
    c = [
        _chk("G0 muestra", f"{n} evaluadores · {n_comm} comerciales",
             f">= {T['MIN_RESPONDENTS']} y >= {T['MIN_COMMERCIAL']} comerciales",
             n >= T["MIN_RESPONDENTS"] and n_comm >= T["MIN_COMMERCIAL"],
             "sin masa comercial mínima el gate no mide lo que dice medir"),
        _chk("G1 send rate sobre la preferida", m["send_rate_preferred"],
             f">= {T['G1_SEND_PREFERRED']*100:.0f}%",
             (m["send_rate_preferred"] or 0) >= T["G1_SEND_PREFERRED"] * 100,
             "la métrica central; NINGUNA cuenta como no enviable"),
        _chk("G2 confianza >= 4 sobre la preferida", m["conf4_rate_preferred"],
             f">= {T['G2_CONF4_PREFERRED']*100:.0f}%",
             (m["conf4_rate_preferred"] or 0) >= T["G2_CONF4_PREFERRED"] * 100,
             "endurece G1; está correlacionada con ella, no es evidencia independiente"),
        _chk("G3 defecto bloqueante compartido",
             f"{m['worst_shared_blocker'] or '—'} {m['worst_shared_blocker_rate'] or 0}%",
             f"< {T['G3_SHARED_BLOCKER']*100:.0f}%",
             (m["worst_shared_blocker_rate"] or 0) < T["G3_SHARED_BLOCKER"] * 100,
             "si varios ven el mismo bloqueo, el bloqueo es real"),
        _chk("G4 cambio requerido NO_CHANGE o MINOR", m["change_ok_rate_preferred"],
             f">= {T['G4_CHANGE_OK']*100:.0f}%",
             (m["change_ok_rate_preferred"] or 0) >= T["G4_CHANGE_OK"] * 100,
             "el chequeo menos amable: 'sí lo mandaría' + 'movería el directorio' es MATERIAL"),
    ]
    return {"result": "PASS" if all(x["status"] == "PASS" for x in c) else "FAIL", "checks": c,
            "detail": ""}


def _product_gate(m: Dict) -> Dict:
    T, n = THRESHOLDS, m["n_respondents"]
    if n < T["MIN_RESPONDENTS"]:
        return {"result": "INSUFFICIENT_DATA", "checks": [], "detail": f"{n} evaluadores"}
    c = [
        _chk("P1 dolor real", m["pain_rate"], f">= {T['P1_PAIN']*100:.0f}%",
             (m["pain_rate"] or 0) >= T["P1_PAIN"] * 100,
             "turnaround de 1-2 días o más, o directamente no hacen test-fit"),
        _chk("P2 frecuencia", m["frequency_rate"], f">= {T['P2_FREQUENCY']*100:.0f}%",
             (m["frequency_rate"] or 0) >= T["P2_FREQUENCY"] * 100, "al menos mensual"),
        _chk("P3 lo usaría en < 2 min", m["would_use_rate"], f">= {T['P3_WOULD_USE']*100:.0f}%",
             (m["would_use_rate"] or 0) >= T["P3_WOULD_USE"] * 100, "declarado, nivel 1"),
        _chk("P4 cubre parte real de sus búsquedas", m["share_rate"], f">= {T['P4_SHARE']*100:.0f}%",
             (m["share_rate"] or 0) >= T["P4_SHARE"] * 100, ">= 26% de sus búsquedas"),
    ]
    return {"result": "PASS" if all(x["status"] == "PASS" for x in c) else "FAIL", "checks": c,
            "detail": "la necesidad de QA humana se reporta pero NO es gate: un modelo con QA "
                      "puede ser un negocio perfectamente viable"}
