"""E08 — schemas locales de todo output de IA.

Regla: aunque el proveedor soporte structured output nativo, la validación que decide es ÉSTA, del lado
del cliente. Un JSON parcialmente válido no se acepta en silencio.

Regla dura adicional: ningún output de IA puede contener coordenadas. `assert_no_coordinates` recorre el
objeto completo buscando claves geométricas y falla si aparece alguna."""
from __future__ import annotations

from typing import Dict, List, Tuple

import jsonschema

# Aspectos que los tres críticos puntúan con el mismo vocabulario (permite comparar y agregar).
ASPECTS = ["arrival_sequence", "reception", "client_route", "boardroom_location", "meeting_accessibility",
           "privacy_gradient", "open_work_neighborhoods", "adjacency", "kitchenette_dining", "lounge",
           "circulation_logic", "program_coherence", "strategy_alignment"]

VISUAL_ASPECTS = ["arrival_reads_naturally", "reception_convincing", "client_circulation_sense",
                  "room_proportions", "workspace_fragmentation", "furniture_believable", "wasted_zones",
                  "meeting_clusters", "neighborhood_usability", "credible_test_fit", "strategy_expression"]

# Claves prohibidas en cualquier output de IA: geometría es propiedad del motor determinista.
FORBIDDEN_KEYS = {"x", "y", "w", "d", "cx", "cy", "coords", "coordinates", "geometry", "placements",
                  "perimeter", "polygon", "points", "rect", "bbox", "px_per_m", "walls", "columns", "doors"}

_SCORE = {"type": "number", "minimum": 0.0, "maximum": 1.0}
_ISSUE = {"type": "object", "required": ["aspect", "severity", "text"],
          "properties": {"aspect": {"type": "string"}, "severity": {"enum": ["critical", "warning", "info"]},
                         "text": {"type": "string", "minLength": 3}},
          "additionalProperties": False}
_META = {"provider": {"type": "string"}, "model": {"type": "string"}, "alternative_id": {"type": "string"},
         "prompt_version": {"type": "string"}, "confidence": _SCORE, "summary": {"type": "string"}}

STRUCTURED_SPATIAL_REVIEW = {
    "type": "object",
    "required": ["provider", "model", "alternative_id", "scores", "critical_issues", "warnings", "strengths",
                 "strategy_alignment", "architectural_plausibility", "confidence", "summary", "prompt_version"],
    "properties": {**_META,
                   "scores": {"type": "object", "minProperties": 8,
                              "additionalProperties": _SCORE},
                   "critical_issues": {"type": "array", "items": _ISSUE},
                   "warnings": {"type": "array", "items": _ISSUE},
                   "strengths": {"type": "array", "items": {"type": "string"}},
                   "strategy_alignment": _SCORE,
                   "architectural_plausibility": _SCORE},
    "additionalProperties": False,
}

VISUAL_ARCHITECTURAL_REVIEW = {
    "type": "object",
    "required": ["provider", "model", "alternative_id", "scores", "critical_issues", "warnings", "strengths",
                 "visual_plausibility", "strategy_readability", "ready_for_external_review", "confidence",
                 "summary", "prompt_version"],
    "properties": {**_META,
                   "scores": {"type": "object", "minProperties": 6, "additionalProperties": _SCORE},
                   "critical_issues": {"type": "array", "items": _ISSUE},
                   "warnings": {"type": "array", "items": _ISSUE},
                   "strengths": {"type": "array", "items": {"type": "string"}},
                   "visual_plausibility": _SCORE,
                   "strategy_readability": _SCORE,
                   "ready_for_external_review": {"type": "boolean"}},
    "additionalProperties": False,
}

AGGREGATED_REVIEW = {
    "type": "object",
    "required": ["alternative_id", "consensus_scores", "agreements", "disagreements", "critical_disagreements",
                 "confidence", "external_review_readiness", "reason", "status", "sources"],
    "properties": {
        "alternative_id": {"type": "string"},
        "consensus_scores": {"type": "object", "additionalProperties": _SCORE},
        "agreements": {"type": "array", "items": {"type": "object"}},
        "disagreements": {"type": "array", "items": {"type": "object"}},
        "critical_disagreements": {"type": "array", "items": {"type": "object"}},
        "confidence": _SCORE,
        "external_review_readiness": {"enum": ["READY_FOR_EXTERNAL_REVIEW", "INTERNAL_REVIEW", "NOT_READY"]},
        "reason": {"type": "string"},
        "status": {"enum": ["CONSENSUS_GOOD", "CONSENSUS_WEAK", "DISAGREEMENT", "CRITICAL_DISAGREEMENT",
                            "PROVIDER_UNAVAILABLE"]},
        "sources": {"type": "object"},
    },
    "additionalProperties": False,
}

PRESENTATION_SPEC = {
    "type": "object",
    "required": ["alternative_order", "headline", "subtitle", "alternative_copy", "strengths",
                 "metric_priority", "callouts", "typography_direction", "visual_hierarchy",
                 "spacing_guidance", "color_roles", "disclaimer_copy", "fit_verdict_copy",
                 "provider", "model", "prompt_version"],
    "properties": {
        "alternative_order": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
        "headline": {"type": "string", "minLength": 4, "maxLength": 90},
        "subtitle": {"type": "string", "maxLength": 160},
        "alternative_copy": {"type": "object", "additionalProperties": {
            "type": "object", "required": ["label", "one_liner", "priority"],
            "properties": {"label": {"type": "string", "maxLength": 24},
                           "one_liner": {"type": "string", "maxLength": 130},
                           "priority": {"type": "string", "maxLength": 60},
                           "ideal_for": {"type": "string", "maxLength": 110}},
            "additionalProperties": False}},
        "strengths": {"type": "object", "additionalProperties": {
            "type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 4}},
        "metric_priority": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
        "callouts": {"type": "array", "items": {
            "type": "object", "required": ["alternative_id", "text"],
            "properties": {"alternative_id": {"type": "string"}, "text": {"type": "string", "maxLength": 90}},
            "additionalProperties": False}},
        "typography_direction": {"type": "string"},
        "visual_hierarchy": {"type": "array", "items": {"type": "string"}},
        "spacing_guidance": {"type": "string"},
        "color_roles": {"type": "object", "additionalProperties": {"type": "string"}},
        "disclaimer_copy": {"type": "string"},
        "fit_verdict_copy": {"type": "string", "maxLength": 160},
        "provider": {"type": "string"}, "model": {"type": "string"}, "prompt_version": {"type": "string"},
    },
    "additionalProperties": False,
}

AI_USAGE_RECORD = {
    "type": "object",
    "required": ["provider", "model", "purpose", "input_tokens", "output_tokens", "latency_ms",
                 "estimated_cost", "request_id", "success"],
    "properties": {
        "provider": {"type": "string"}, "model": {"type": "string"}, "purpose": {"type": "string"},
        "project": {"type": ["string", "null"]}, "alternative_id": {"type": ["string", "null"]},
        "input_tokens": {"type": ["integer", "null"]}, "output_tokens": {"type": ["integer", "null"]},
        "latency_ms": {"type": "number"},
        "estimated_cost": {"type": ["number", "null"]}, "reported_cost": {"type": ["number", "null"]},
        "cost_status": {"enum": ["estimated", "reported", "unknown"]},
        "request_id": {"type": ["string", "null"]}, "success": {"type": "boolean"},
        "error": {"type": ["string", "null"]}, "attempts": {"type": "integer"},
    },
    "additionalProperties": False,
}

SCHEMAS = {
    "StructuredSpatialReview": STRUCTURED_SPATIAL_REVIEW,
    "VisualArchitecturalReview": VISUAL_ARCHITECTURAL_REVIEW,
    "AggregatedReview": AGGREGATED_REVIEW,
    "PresentationSpec": PRESENTATION_SPEC,
    "AIUsageRecord": AI_USAGE_RECORD,
}


class SchemaFailure(Exception):
    """El output del proveedor no cumple el schema local."""


def validate(obj: Dict, schema_name: str) -> Dict:
    try:
        jsonschema.validate(obj, SCHEMAS[schema_name])
    except jsonschema.ValidationError as e:
        raise SchemaFailure(f"{schema_name}: {e.message} (en {'/'.join(str(p) for p in e.absolute_path)})") from None
    return obj


def find_coordinates(obj, path: str = "") -> List[str]:
    """Devuelve las rutas donde aparece una clave geométrica prohibida."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if str(k).lower() in FORBIDDEN_KEYS:
                hits.append(p)
            hits += find_coordinates(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += find_coordinates(v, f"{path}[{i}]")
    return hits


def assert_no_coordinates(obj, what: str = "output") -> None:
    hits = find_coordinates(obj)
    if hits:
        raise SchemaFailure(f"{what} contiene geometría prohibida: {', '.join(hits[:6])}")
