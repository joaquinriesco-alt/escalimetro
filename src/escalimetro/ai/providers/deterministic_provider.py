"""E08 — proveedor determinista (fallback que nunca se cae).

No llama a nada. Deriva sus salidas del crítico por reglas de E05/E07 y de las métricas del layout, y las
emite en los MISMOS schemas que Anthropic y OpenAI. Esto es lo que permite que el producto funcione con
ambos proveedores, con uno, o con ninguno.

No es un mock de un LLM: es el tercer crítico del sistema, y su opinión cuenta igual que la de los otros
dos en el agregador. Cuando produce una revisión que sustituye a un proveedor caído lo declara con
`provider = "deterministic"`, nunca con el nombre del proveedor ausente."""
from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

from .base import AIProvider, ProviderError

PROMPT_VERSION = "deterministic_v1"

# rule-based (E07) → vocabulario común de 13 aspectos de E08
SPATIAL_MAP = {
    "arrival_sequence": "arrival_sequence",
    "reception": "reception",
    "client_access_to_rooms": "client_route",
    "privacy": "privacy_gradient",
    "open_office_quality": "open_work_neighborhoods",
    "kitchenette_dining": "kitchenette_dining",
    "lounge_location": "lounge",
    "circulation": "circulation_logic",
    "fragmentation": "program_coherence",
    "facade_use": "adjacency",
}


def _clamp(v) -> float:
    return max(0.0, min(1.0, round(float(v), 3)))


def _issues(scores: Dict[str, float], verdicts: Dict[str, str], crit_at=0.2, warn_at=0.5) -> tuple:
    crit, warn = [], []
    for k, v in sorted(scores.items()):
        text = verdicts.get(k) or f"aspecto {k} en {v:.2f}"
        if v <= crit_at:
            crit.append({"aspect": k, "severity": "critical", "text": text})
        elif v < warn_at:
            warn.append({"aspect": k, "severity": "warning", "text": text})
    return crit, warn


def spatial_review(ctx: Dict) -> Dict:
    c = ctx["rule_based_critique"]
    rs, rv = c["scores"], c.get("verdicts", {})
    scores = {dst: _clamp(rs[src]) for src, dst in SPATIAL_MAP.items() if src in rs}
    scores["boardroom_location"] = _clamp(1.0 - min(ctx["metrics_summary"].get("boardroom_path_m", 0.0), 30.0) / 30.0)
    scores["meeting_accessibility"] = _clamp(rs.get("client_access_to_rooms", 0.5))
    align = _clamp(ctx.get("strategy_signal", 0.5))
    scores["strategy_alignment"] = align
    crit, warn = _issues(scores, {SPATIAL_MAP.get(k, k): v for k, v in rv.items()})
    strengths = [rv[k] for k, v in sorted(rs.items(), key=lambda kv: -kv[1])[:4]
                 if k in rv and v >= 0.9][:4]
    return {
        "provider": "deterministic", "model": "rule_based_v1", "alternative_id": ctx["alternative_id"],
        "prompt_version": PROMPT_VERSION, "scores": scores,
        "critical_issues": crit, "warnings": warn, "strengths": strengths or ["programa completo y validado"],
        "strategy_alignment": align,
        "architectural_plausibility": _clamp(c["architectural_score"]),
        "confidence": 0.55,
        "summary": (f'{ctx["alternative_id"]}: revisión estructurada derivada del crítico por reglas '
                    f'(sin LLM). Plausibilidad {c["architectural_score"]:.2f}.'),
    }


def visual_review(ctx: Dict) -> Dict:
    m, c = ctx["metrics_summary"], ctx["rule_based_critique"]
    rs = c["scores"]
    frag = _clamp(rs.get("fragmentation", 0.5))
    resid_pen = _clamp(1.0 - min(m.get("residual_m2", 0.0), 120.0) / 120.0)
    scores = {
        "arrival_reads_naturally": _clamp(rs.get("arrival_sequence", 0.5)),
        "reception_convincing": _clamp(rs.get("reception", 0.5)),
        "client_circulation_sense": _clamp(rs.get("client_access_to_rooms", 0.5)),
        "room_proportions": _clamp(ctx.get("proportion_signal", 0.7)),
        "workspace_fragmentation": frag,
        "furniture_believable": 0.8,
        "wasted_zones": resid_pen,
        "meeting_clusters": _clamp(rs.get("client_access_to_rooms", 0.5)),
        "neighborhood_usability": _clamp(rs.get("open_office_quality", 0.5)),
        "credible_test_fit": _clamp((frag + resid_pen + rs.get("circulation", 0.5)) / 3.0),
        "strategy_expression": _clamp(ctx.get("strategy_signal", 0.5)),
    }
    crit, warn = _issues(scores, {})
    vis = _clamp(sum(scores.values()) / len(scores))
    return {
        "provider": "deterministic", "model": "geometry_heuristics_v1", "alternative_id": ctx["alternative_id"],
        "prompt_version": PROMPT_VERSION, "scores": scores,
        "critical_issues": crit, "warnings": warn,
        "strengths": ["circulación conectada y legible", "programa completo sin colisiones"],
        "visual_plausibility": vis, "strategy_readability": _clamp(ctx.get("strategy_signal", 0.5)),
        "ready_for_external_review": bool(vis >= 0.6 and not crit),
        "confidence": 0.4,
        "summary": (f'{ctx["alternative_id"]}: sustituto determinista de la crítica visual. NO vio la '
                    f'planta: deriva de métricas geométricas. Confianza deliberadamente baja.'),
    }


def _subtitle(ctx: Dict) -> str:
    """E24 §6 — el subtítulo decía '48 personas' para cualquier cliente."""
    hc = ctx.get("target_headcount")
    return (f"Mismo programa para {hc} personas, mismo piso. Cambia la prioridad." if hc
            else "El mismo programa, el mismo piso. Cambia la prioridad.")


def presentation_spec(ctx: Dict) -> Dict:
    """Dirección de lámina de respaldo. Copy corto, tomado de la intención declarada de cada alternativa."""
    alts = ctx["alternatives"]
    order = ctx.get("order") or [a["alt"] for a in alts]
    by = {a["alt"]: a for a in alts}
    copy = {k: {"label": by[k]["name"], "one_liner": by[k]["copy_short"],
                "priority": by[k]["priority"], "ideal_for": by[k]["ideal_for"]} for k in order}
    return {
        "alternative_order": order,
        "headline": "Tres formas de ocupar la misma oficina",
        "subtitle": _subtitle(ctx),
        "alternative_copy": copy,
        "strengths": {k: by[k]["strengths"][:4] for k in order},
        "metric_priority": ["puestos", "salas", "luz en puestos", "circulación"],
        "callouts": [{"alternative_id": k, "text": by[k]["callout"]} for k in order if by[k].get("callout")],
        "typography_direction": "una sola familia sans; jerarquía por tamaño y peso, no por color",
        "visual_hierarchy": ["veredicto", "nombre de alternativa", "planta", "KPIs", "detalle"],
        "spacing_guidance": "aire generoso entre bloques; la planta manda, el texto acompaña",
        "color_roles": {"A": "acento frío", "B": "acento cálido", "C": "acento verde",
                        "texto": "tinta neutra", "advertencia": "rojo tierra"},
        "disclaimer_copy": ("Test-fit conceptual para evaluación de espacio. No constituye proyecto de "
                            "arquitectura. Dimensiones sujetas a confirmación de escala."),
        "fit_verdict_copy": ctx.get("fit_copy", "El programa completo cabe en el rango de escala asumido."),
        "provider": "deterministic", "model": "template_v1", "prompt_version": PROMPT_VERSION,
    }


BUILDERS = {"spatial_review": spatial_review, "visual_review": visual_review, "presentation": presentation_spec}


class DeterministicProvider(AIProvider):
    """Siempre disponible. Ignora `prompt` y trabaja sobre `context`."""

    name = "deterministic"

    @property
    def available(self) -> bool:
        return self.cfg.enabled

    def _call(self, prompt, images, system):                 # pragma: no cover - no se usa
        raise ProviderError("provider_error", "el proveedor determinista no usa prompts de texto")

    def complete_json(self, prompt: str, schema_name: str, system: str = "", images=None,
                      purpose: Optional[str] = None, alternative_id: Optional[str] = None,
                      project: Optional[str] = None, context: Optional[Dict] = None):
        from ..schemas import validate
        from .base import AIUsageRecord, ProviderResponse
        p = purpose or self.cfg.purpose
        usage = AIUsageRecord(provider="deterministic", model=self.cfg.model, purpose=p, project=project,
                              alternative_id=alternative_id, attempts=1, cost_status="reported",
                              estimated_cost=0.0, request_id=None)
        t0 = time.time()
        if p not in BUILDERS:
            usage.error = "provider_error"
            raise ProviderError("provider_error", f"propósito no soportado: {p}")
        data = BUILDERS[p](context or {})
        validate(data, schema_name)
        usage.success = True
        usage.latency_ms = round((time.time() - t0) * 1000, 2)
        return ProviderResponse(data=data, usage=usage, raw_text=json.dumps(data, ensure_ascii=False))
