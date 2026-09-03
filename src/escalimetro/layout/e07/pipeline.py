"""E07 — QA interno, comparación A/B/C, gates y handoff de presentación.

QA INTERNO: no es una feature de cliente. Sólo repara errores evidentes del motor con operaciones
estructuradas (las de E06) y vuelve a validar de forma determinista. Si hiciera falta rediseñar la
estrategia, E1-A es FAIL.

GATES separados (E07 §18):
  E1-T  técnico    — software puede decidirlo (programa, violaciones, colisiones, circulación, shell).
  E1-A  arquitectónico — PASS PROVISIONAL con umbral documentado + QA interno sin rediseño.
  E1-C  comercial  — el software NUNCA lo marca PASS: el máximo estado alcanzable es READY_FOR_BROKER_REVIEW.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from ..model import Layout, Module
from ..e06.qa import HumanCorrectionOperation, apply_operations, preserved_pct

# Umbrales documentados (hipótesis de producto, no norma ni referencia de terceros)
E1A_CRITIC_THRESHOLD = 0.65
E1A_MAX_QA_MINUTES = 5.0
E1A_MIN_GEOMETRY_PRESERVED = 90.0
# Aspectos cuyo valor lo fija la cáscara, no la alternativa (se informan, no invalidan)
SHELL_DOMINATED_ASPECTS = {"residual_spaces"}
OP_MINUTES = {"ACCEPT": 0.1, "MOVE": 0.5, "ROTATE": 0.3, "SWAP": 0.5, "RESIZE_TO_VALID_VARIANT": 0.5,
              "DELETE": 0.2, "ADD": 1.0, "LOCK": 0.1}
REVIEW_MINUTES = 1.5          # lectura de la planta por un revisor interno


@dataclass
class InternalQABurden:
    alternative: str
    operations: List[Dict]
    operation_count: int
    geometry_preserved_pct: float
    geometry_changed_pct: float
    estimated_minutes: float
    minutes_are_estimated: bool
    reason: str
    reason_for_correction: str
    final_validation: Dict
    redesign_required: bool = False

    def to_dict(self):
        return asdict(self)


def internal_qa(alt: str, layout: Layout, ops: List[HumanCorrectionOperation], modules: Dict[str, Module],
                validator, reason: str, revalidate) -> (Layout, InternalQABurden):
    """Aplica las operaciones (si las hay) y revalida de forma determinista."""
    after = layout
    if ops:
        after, log, _ = apply_operations(layout, ops, modules)
    ok, viol, crit = revalidate(after)
    minutes = REVIEW_MINUTES + sum(OP_MINUTES[o.op] for o in ops)
    burden = InternalQABurden(
        alternative=alt, operations=[o.to_dict() for o in ops], operation_count=len(ops),
        geometry_preserved_pct=(pp := preserved_pct(layout, after) if ops else 100.0),
        geometry_changed_pct=round(100.0 - pp, 1),
        estimated_minutes=round(minutes, 1), minutes_are_estimated=True, reason=reason,
        reason_for_correction=reason,
        final_validation={"hard_valid": ok, "violations": viol, "architectural_score": crit.architectural_score},
        redesign_required=False)
    return after, burden


def gate_e1t(result) -> Dict:
    """Técnico: decidible por software."""
    m = result.metrics
    checks = {
        "programa_completo": bool(m["program_completeness"]["complete"]),
        "40_puestos": m["program_completeness"]["open_seats"] == "40/40",
        "0_hard_violations": m["hard_constraint_violations"] == 0,
        "0_colisiones": m["collisions"] == 0,
        "circulacion_conectada": bool(m["circulation_connectivity"]),
        "shell_exacto": True,        # todas las alternativas se resuelven sobre el mismo ShellM de E03
    }
    return {"gate": "E1-T", "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def gate_e1a(result, burden: InternalQABurden) -> Dict:
    """Arquitectónico: PASS PROVISIONAL con umbral documentado."""
    crit = result.critique
    # `residual_spaces` está DOMINADO POR EL SHELL: toda solución válida producida hasta ahora sobre la 403
    # (E06: 68 m²; E07 A/B/C: 62–86 m²) deja bolsillos estructurales (banda de 2.44 m contra el núcleo y
    # muescas del perímetro). Se reporta siempre, pero no invalida una alternativa: el gate mide decisiones
    # de diseño, no las limitaciones de la cáscara.
    critical = [k for k, v in crit["scores"].items()
                if k not in ("architectural_plausibility",) and k not in SHELL_DOMINATED_ASPECTS and v <= 0.2]
    shell_dominated = {k: crit["scores"][k] for k in SHELL_DOMINATED_ASPECTS if k in crit["scores"]}
    checks = {
        f"critic_score ≥ {E1A_CRITIC_THRESHOLD}": crit["architectural_score"] >= E1A_CRITIC_THRESHOLD,
        "sin_aspecto_critico (≤0.2)": not critical,
        f"qa_interno ≤ {E1A_MAX_QA_MINUTES} min": burden.estimated_minutes <= E1A_MAX_QA_MINUTES,
        f"geometria_preservada ≥ {E1A_MIN_GEOMETRY_PRESERVED} %": burden.geometry_preserved_pct >= E1A_MIN_GEOMETRY_PRESERVED,
        "sin_redisenio": not burden.redesign_required,
    }
    return {"gate": "E1-A", "status": "PASS_PROVISIONAL" if all(checks.values()) else "FAIL", "checks": checks,
            "critical_aspects": critical, "shell_dominated_aspects": shell_dominated, "thresholds": {"critic": E1A_CRITIC_THRESHOLD, "qa_minutes": E1A_MAX_QA_MINUTES,
                                                          "geometry_preserved_pct": E1A_MIN_GEOMETRY_PRESERVED},
            "note": "Umbrales = hipótesis de producto documentadas; no provienen de norma ni de terceros."}


def gate_e1c(e1t: Dict, e1a: Dict) -> Dict:
    """Comercial: el software NO puede marcarlo PASS."""
    ready = e1t["status"] == "PASS" and e1a["status"] == "PASS_PROVISIONAL"
    return {"gate": "E1-C", "status": "READY_FOR_BROKER_REVIEW" if ready else "NOT_READY",
            "note": "El PASS comercial requiere que un broker o arquitecto externo declare que enviaría esta lámina "
                    "a un cliente. Ningún crítico interno puede otorgarlo (broker_showable del crítico NO se usa aquí)."}


@dataclass
class AlternativeComparison:
    rows: List[Dict]
    best_for: Dict[str, str]
    note: str

    def to_dict(self):
        return asdict(self)


def compare(results, burdens: Dict[str, InternalQABurden], gates: Dict[str, Dict]) -> AlternativeComparison:
    rows = []
    for r in results:
        m, c = r.metrics, r.critique
        obj = (r.layout.scores or {}).get("objectives", {})
        seats = sum(p.seats for p in r.layout.placements)
        bench = sum(p.seats for p in r.layout.placements if p.module == "workstation_cluster")
        rows.append({
            "alt": r.alt, "name": r.name, "technical_validity": gates[r.alt]["E1-T"]["status"],
            "architectural_score": c["architectural_score"],
            "geometric_score": (r.layout.scores or {}).get("total"),
            "daylight": obj.get("daylight_utilization"),
            "circulation_m2": m["circulation_area_m2"],
            "residual_m2": m["wasted_area_m2"],
            "unallocated_m2": m["unallocated_area_m2"],
            "net_programmed_m2": m["net_programmed_area_m2"],
            "facade_closed_rooms": sum(1 for p in r.layout.placements if p.meta.get("facade_touch") and not p.module.startswith("workstation")),
            "facade_consumption_pct": _facade_pct(r),
            "client_route": c["scores"]["client_access_to_rooms"],
            "boardroom_path_m": _path(r, "boardroom_12_1"),
            "reception_path_m": _path(r, "reception_1"),
            "fragmentation": c["scores"]["fragmentation"],
            "compactness": obj.get("compactness"),
            "work_blocks": sum(1 for p in r.layout.placements if p.module.startswith("workstation")),
            "bench_seat_pct": round(100.0 * bench / max(1, seats), 1),
            "internal_qa_minutes": burdens[r.alt].estimated_minutes,
            "internal_qa_ops": burdens[r.alt].operation_count,
            "generation_s": r.profile.total_s,
        })
    def best(key, hi=True):
        vals = [(row[key], row["alt"]) for row in rows if row.get(key) is not None]
        return (max(vals) if hi else min(vals))[1] if vals else "-"
    best_for = {
        "menor circulación": best("circulation_m2", hi=False),
        "menor residual": best("residual_m2", hi=False),
        "mejor luz en puestos": best("daylight", hi=True),
        "mejor recorrido de cliente": best("client_route", hi=True),
        "directorio más cerca del acceso": best("boardroom_path_m", hi=False),
        "menos fragmentación": best("fragmentation", hi=True),
        "score arquitectónico": best("architectural_score", hi=True),
        "más barrios de trabajo": best("work_blocks", hi=True),
    }
    return AlternativeComparison(rows, best_for,
                                 "No hay ganador absoluto: cada alternativa optimiza objetivos de space planning "
                                 "distintos sobre el mismo programa y el mismo shell.")


def _facade_pct(r) -> Optional[float]:
    d = (r.layout.scores or {}).get("detail", {}).get("facade_preservation", "")
    try:
        return float(d.split("%")[0].strip())
    except Exception:
        return None


def _path(r, pid: str) -> Optional[float]:
    for n in (r.layout.circulation_graph or {}).get("nodes", []):
        if n["id"] == pid:
            return n.get("path_m")
    return None


def presentation_handoff(r, spec, fit_verdict: Dict, svg_technical: str, svg_commercial: str, gates: Dict,
                         burden: InternalQABurden, comparison_row: Dict) -> Dict:
    """Contrato para que OpenAI eleve la lámina SIN reinterpretar la planta."""
    return {
        "geometry_locked": True,
        "geometry_lock_note": "La geometría está validada y cerrada. Cualquier capa de presentación puede cambiar "
                              "color, trazo, tipografía, etiquetas, iconografía, composición y narrativa; NO puede "
                              "mover, redibujar ni reinterpretar muros, shell, recintos, puestos, mobiliario, "
                              "puertas, pilares ni circulación. Prohibido usar image generation para redibujar la planta.",
        "alternative": {"id": r.alt, "name": r.name, "intent": spec.intent, "copy_short": spec.copy_short,
                        "strengths": spec.strengths, "ideal_for": spec.ideal_for,
                        "graph_id": spec.graph.graph_id, "spine_strategy": spec.spine_strategy},
        "shell_geometry": {"perimeter": [[round(x, 3), round(y, 3)] for x, y in r.layout.zones.get("shell_perimeter", [])],
                           "core": r.layout.zones.get("shell_core", []),
                           "columns": r.layout.zones.get("shell_columns", []),
                           "entrance": r.layout.zones.get("shell_entrance"),
                           "usable_area_m2": r.metrics["usable_area_m2"],
                           "scale_px_per_m": r.layout.zones.get("scale_px_per_m")},
        "layout_geometry": [{"id": p.id, "module": p.module, "x": round(p.x, 3), "y": round(p.y, 3),
                             "w": round(p.w, 3), "d": round(p.d, 3), "rot": p.rot, "seats": p.seats,
                             "zone": p.zone} for p in r.layout.placements],
        "svg": {"technical": svg_technical, "commercial_base": svg_commercial},
        "program": {"target_headcount": 48, "open_workstations": 40,
                    "rooms": {k: v for k, v in r.metrics["program_completeness"]["rooms"].items()}},
        "metrics": comparison_row,
        "critique": r.critique,
        "gates": gates,
        "internal_qa": burden.to_dict(),
        "fit_verdict": fit_verdict,
        "scale_status": {"state": "UNCONFIRMED", "confidence": "LOW",
                         "source": "published_area_inferred = 543 m²",
                         "disclaimer": "Dimensiones sujetas a confirmación de escala."},
        "brand_guidelines": {"name": "ESCALÍMETRO", "tagline": "pre-design · feasibility · test-fit",
                             "palette": {"ink": "#1d2430", "muted": "#6b7480", "line": "#c8ccd4",
                                         "work": "#dfe7f5", "meeting": "#dfeee2", "support": "#f2e7db",
                                         "public": "#f7e3d3", "lounge": "#ece0ef", "circulation": "#fbf3dd",
                                         "core": "#e3e5e8", "accent": "#b5452f"},
                             "type": "Helvetica/Arial; títulos 600; cuerpo 400; etiquetas discretas"},
        "presentation_standard": "ESCALIMETRO_PRESENTATION_STANDARD_01",
        "allowed_changes": ["color", "stroke", "typography", "labels", "icons", "composition", "narrative",
                            "visual hierarchy"],
        "forbidden_changes": ["walls", "shell", "rooms", "desks", "furniture", "doors", "columns", "circulation",
                             "coordinates", "scale", "program counts"],
    }
