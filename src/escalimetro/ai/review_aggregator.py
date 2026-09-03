"""E08 — agregador de revisiones.

Regla central: **no promediar a ciegas.** Si el crítico por reglas dice que la recepción está bien y el
crítico visual dice que es absurda, el promedio (0.7) esconde exactamente la información que importa. El
agregador guarda el desacuerdo como un hecho de primera clase y deja que el gate decida.

Estados posibles (`AI_REVIEW_STATUS`):

    CONSENSUS_GOOD          — dos o más fuentes, sin desacuerdos fuertes, consenso alto.
    CONSENSUS_WEAK          — de acuerdo, pero con puntajes bajos: coinciden en que no es bueno.
    DISAGREEMENT            — diferencias moderadas en aspectos no críticos.
    CRITICAL_DISAGREEMENT   — una fuente ve un aspecto como crítico y otra lo ve bien. No pasa sola.
    PROVIDER_UNAVAILABLE    — falta al menos un proveedor de IA; el rule-based sostiene el producto."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .schemas import validate

# Un desacuerdo por encima de esto se registra; por encima del segundo umbral y con una fuente en zona
# crítica, se marca como crítico. Umbrales = hipótesis de producto documentadas, como en E07.
DISAGREEMENT_DELTA = 0.30
CRITICAL_DELTA = 0.45
CRITICAL_LOW = 0.35
CONSENSUS_GOOD_MIN = 0.62
AGREEMENT_DELTA = 0.12

# Aspectos equivalentes entre el vocabulario espacial y el visual: comparar "reception" con
# "reception_convincing" es legítimo; comparar "reception" con "wasted_zones" no lo es.
BRIDGE = {
    "arrival_sequence": "arrival_reads_naturally",
    "reception": "reception_convincing",
    "client_route": "client_circulation_sense",
    "meeting_accessibility": "meeting_clusters",
    "open_work_neighborhoods": "neighborhood_usability",
    "program_coherence": "workspace_fragmentation",
    "strategy_alignment": "strategy_expression",
}
STATUSES = ["CONSENSUS_GOOD", "CONSENSUS_WEAK", "DISAGREEMENT", "CRITICAL_DISAGREEMENT", "PROVIDER_UNAVAILABLE"]

# Dos fuentes de la MISMA familia no son evidencia independiente: el crítico visual determinista deriva
# del mismo crítico por reglas, así que "coincidir" con él no significa nada. Sólo se comparan familias
# distintas — de lo contrario el agregador fabricaría consenso.
FAMILY = {"rule_based": "deterministic", "deterministic_visual": "deterministic",
          "deterministic_spatial": "deterministic", "anthropic": "anthropic", "openai_vision": "openai"}


def _families(bysrc: Dict[str, float]) -> int:
    return len({FAMILY.get(s, s) for s in bysrc})


@dataclass
class AggregatedReview:
    data: Dict

    def to_dict(self) -> Dict:
        return validate(self.data, "AggregatedReview")


def _aspect_views(reviews: Dict[str, Dict]) -> Dict[str, Dict[str, float]]:
    """aspecto → {fuente: score}, uniendo los vocabularios espacial y visual por el puente."""
    out: Dict[str, Dict[str, float]] = {}
    inv = {v: k for k, v in BRIDGE.items()}
    for source, rv in reviews.items():
        for k, v in (rv.get("scores") or {}).items():
            key = inv.get(k, k)
            out.setdefault(key, {})[source] = float(v)
    return out


def aggregate(alternative_id: str, reviews: Dict[str, Optional[Dict]],
              provider_status: Dict[str, str]) -> AggregatedReview:
    """`reviews`: {"rule_based": {...}|None, "anthropic": {...}|None, "openai_vision": {...}|None}."""
    present = {k: v for k, v in reviews.items() if v}
    missing = [k for k, v in reviews.items() if not v]
    views = _aspect_views(present)

    agreements, disagreements, critical = [], [], []
    consensus: Dict[str, float] = {}
    for aspect, bysrc in sorted(views.items()):
        # el consenso promedia una vez por familia, no una vez por fuente
        byfam: Dict[str, List[float]] = {}
        for s_, v_ in bysrc.items():
            byfam.setdefault(FAMILY.get(s_, s_), []).append(float(v_))
        fam_mean = {f: sum(v) / len(v) for f, v in byfam.items()}
        consensus[aspect] = round(sum(fam_mean.values()) / len(fam_mean), 3)
        if _families(bysrc) < 2:
            continue
        lo_src = min(bysrc, key=bysrc.get)
        hi_src = max(bysrc, key=bysrc.get)
        delta = round(bysrc[hi_src] - bysrc[lo_src], 3)
        row = {"aspect": aspect, "delta": delta, "scores": {k: round(v, 3) for k, v in bysrc.items()},
               "lowest": lo_src, "highest": hi_src}
        if delta >= CRITICAL_DELTA and bysrc[lo_src] <= CRITICAL_LOW:
            critical.append(row)
        elif delta >= DISAGREEMENT_DELTA:
            disagreements.append(row)
        elif delta <= AGREEMENT_DELTA:
            agreements.append(row)

    # Un aspecto marcado "critical" por una fuente y sano por otra también es desacuerdo crítico,
    # aunque los puntajes numéricos no se separen tanto.
    flagged = {}
    for source, rv in present.items():
        for iss in rv.get("critical_issues") or []:
            flagged.setdefault(iss["aspect"], []).append(source)
    for aspect, srcs in flagged.items():
        fams = {FAMILY.get(s, s) for s in srcs}
        others = [s for s in present if FAMILY.get(s, s) not in fams]
        key = {v: k for k, v in BRIDGE.items()}.get(aspect, aspect)
        byv = views.get(key, {})
        if others and any(byv.get(o, 0.0) >= 0.6 for o in others) and \
                not any(c["aspect"] == key for c in critical):
            critical.append({"aspect": key, "delta": None, "scores": {k: round(v, 3) for k, v in byv.items()},
                             "flagged_critical_by": srcs, "considered_fine_by": others})

    n_ai = sum(1 for k in ("anthropic", "openai_vision") if reviews.get(k))
    mean = round(sum(consensus.values()) / len(consensus), 3) if consensus else 0.0
    if critical:
        status = "CRITICAL_DISAGREEMENT"
        reason = (f"{len(critical)} aspecto(s) donde una fuente ve un problema grave y otra no: "
                  f"{', '.join(c['aspect'] for c in critical[:3])}. No se promedia.")
    elif n_ai < 2:
        status = "PROVIDER_UNAVAILABLE"
        reason = (f"faltan proveedores de IA ({', '.join(missing) or 'ninguno'}); el consenso se apoya en "
                  f"{', '.join(sorted(present))}.")
    elif disagreements:
        status = "DISAGREEMENT"
        reason = (f"{len(disagreements)} aspecto(s) con diferencia ≥ {DISAGREEMENT_DELTA:.2f} entre fuentes: "
                  f"{', '.join(d['aspect'] for d in disagreements[:3])}.")
    elif mean >= CONSENSUS_GOOD_MIN:
        status = "CONSENSUS_GOOD"
        reason = f"las fuentes coinciden y el consenso es alto ({mean:.2f})."
    else:
        status = "CONSENSUS_WEAK"
        reason = f"las fuentes coinciden, pero en que la planta es floja ({mean:.2f})."

    readiness = ("READY_FOR_EXTERNAL_REVIEW" if status == "CONSENSUS_GOOD"
                 else "INTERNAL_REVIEW" if status in ("DISAGREEMENT", "CRITICAL_DISAGREEMENT",
                                                      "PROVIDER_UNAVAILABLE", "CONSENSUS_WEAK")
                 else "NOT_READY")
    confs = [float(r.get("confidence", 0.5)) for r in present.values()]
    confidence = round((sum(confs) / len(confs)) * (0.6 if status == "PROVIDER_UNAVAILABLE" else 1.0), 3) if confs else 0.0

    return AggregatedReview({
        "alternative_id": alternative_id,
        "consensus_scores": consensus,
        "agreements": agreements, "disagreements": disagreements, "critical_disagreements": critical,
        "confidence": min(1.0, confidence),
        "external_review_readiness": readiness,
        "reason": reason, "status": status,
        "sources": {k: ("present" if reviews.get(k) else provider_status.get(k, "unavailable"))
                    for k in reviews},
    })


def requires_internal_review(agg: Dict) -> bool:
    """Una alternativa con CRITICAL_DISAGREEMENT no pasa sola a presentación final."""
    return agg["status"] == "CRITICAL_DISAGREEMENT" or agg["external_review_readiness"] == "INTERNAL_REVIEW"
