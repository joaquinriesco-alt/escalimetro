"""E13 — cegado y randomización.

Regla única: el evaluador ve OPTION X / Y / Z y nunca A / B / C durante la evaluación inicial (§4).
El mapping vive aquí y en `blind_mapping.json`, nunca en el material que se le muestra.

Randomización (§5): el prompt propone cinco órdenes. Se usan las SEIS permutaciones porque con cinco
cada alternativa no aparece el mismo número de veces en cada posición —con ABC/BCA/CAB/ACB/BAC la
alternativa A sale primera dos veces y tercera una— y el sesgo de posición es exactamente lo que la
randomización debe cancelar. Con seis, cada alternativa ocupa cada posición exactamente dos veces."""
from __future__ import annotations

from itertools import permutations
from typing import Dict, List, Tuple

ALTS: Tuple[str, str, str] = ("A", "B", "C")
BLIND: Tuple[str, str, str] = ("X", "Y", "Z")
REAL_NAMES = {"A": "A EFICIENTE", "B": "B BALANCEADO", "C": "C COLABORATIVO"}

#: las seis permutaciones, en orden fijo y reproducible
ORDERS: List[Tuple[str, str, str]] = sorted(permutations(ALTS))


def order_for(respondent_index: int) -> Tuple[str, str, str]:
    """Orden de presentación para el n-ésimo evaluador (0-based). Cicla sobre las seis permutaciones."""
    if respondent_index < 0:
        raise ValueError("respondent_index debe ser >= 0")
    return ORDERS[respondent_index % len(ORDERS)]


def mapping_for(respondent_index: int) -> Dict[str, str]:
    """{'X': 'B', 'Y': 'C', 'Z': 'A'} — qué alternativa real hay detrás de cada etiqueta ciega."""
    return dict(zip(BLIND, order_for(respondent_index)))


def inverse_mapping_for(respondent_index: int) -> Dict[str, str]:
    """{'B': 'X', ...} — para traducir una respuesta ciega a la alternativa real."""
    return {v: k for k, v in mapping_for(respondent_index).items()}


def display_order_label(respondent_index: int) -> str:
    """'SET 3 · B-C-A' — se anota en el CSV para poder auditar el sesgo de posición después."""
    o = order_for(respondent_index)
    return f"SET {respondent_index % len(ORDERS) + 1} · {'-'.join(o)}"


def position_balance(n_respondents: int) -> Dict[str, List[int]]:
    """Cuántas veces cae cada alternativa en cada posición con n evaluadores. Sirve para el informe."""
    out = {a: [0, 0, 0] for a in ALTS}
    for i in range(n_respondents):
        for pos, alt in enumerate(order_for(i)):
            out[alt][pos] += 1
    return out


# ---------------------------------------------------------------------------------------------------
# fuga de información
# ---------------------------------------------------------------------------------------------------
#: términos que NUNCA pueden aparecer en material que ve el evaluador antes de la revelación (§4, §36)
LEAK_TERMS = [
    "EFICIENTE", "BALANCEADO", "COLABORATIVO",
    "OpenAI", "Anthropic", "Claude", "GPT", "LLM", "AI-generated", "inteligencia artificial",
    "solver", "CP-SAT", "OR-Tools", "geometry_hash", "GeometryHash", "IoU",
    "E1-T", "E1-A", "E1-C", "rule_based", "rule-based", "critic", "telemetry", "Railway",
    "score", "puntaje", "0.40", "Qbiq", "Canva", "Runway",
    "optimizado", "inteligente", "premium",
]


def leaks(text: str) -> List[str]:
    """Términos prohibidos presentes en un texto. Case-insensitive. Vacío = limpio."""
    low = (text or "").lower()
    hits = []
    for t in LEAK_TERMS:
        if t.lower() in low:
            hits.append(t)
    return hits
