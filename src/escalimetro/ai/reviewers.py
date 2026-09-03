"""E08 — los tres revisores.

    AnthropicSpatialReviewer          — lógica espacial estructurada. No necesita imagen.
    OpenAIVisualArchitecturalCritic   — mira la planta renderizada. Juzga lo que un validador no puede.
    RuleBasedReviewer                 — el crítico determinista de E05/E07, intacto, emitido en el mismo schema.

Los tres consumen el MISMO payload de producto y emiten el MISMO vocabulario de aspectos, que es lo que
después permite decir si están de acuerdo o no. Ninguno recibe objetos mutables: el payload es un dict
construido a partir de copias."""
from __future__ import annotations

import base64
import copy
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import prompts
from .providers.base import AIProvider, ProviderResponse
from .providers.deterministic_provider import DeterministicProvider
from .schemas import assert_no_coordinates, validate

MAX_IMAGE_BYTES = 4_000_000


def _b64(path: str) -> Dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"imagen demasiado grande para la API: {path} ({len(data)} bytes)")
    ext = os.path.splitext(path)[1].lower()
    media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "image/png")
    return {"media_type": media, "data": base64.b64encode(data).decode("ascii")}


def strategy_signal(alt: str, metrics_summary: Dict) -> float:
    """Señal determinista de "¿la planta hace lo que la estrategia dice?", usada por el proveedor
    determinista y como referencia de comparación. A = eficiencia, B = equilibrio, C = colaboración."""
    m = metrics_summary
    if alt == "A":
        return max(0.0, min(1.0, (1 - min(m.get("circulation_m2", 90) / 120.0, 1.0)) * 0.5
                            + min(m.get("fragmentation", 0.5), 1.0) * 0.5))
    if alt == "B":
        return max(0.0, min(1.0, m.get("daylight", 0.5) * 0.5 + m.get("client_route", 0.5) * 0.5))
    return max(0.0, min(1.0, min(m.get("work_blocks", 7) / 10.0, 1.0) * 0.6 + m.get("client_route", 0.5) * 0.4))


def build_payload(alt: str, spec: Dict, layout: Dict, metrics: Dict, critique: Dict, graph: Dict,
                  fit: Dict, comparison_row: Dict) -> Dict:
    """Payload común. Se pasa a los LLM como JSON dentro del prompt y al determinista como `context`."""
    ms = {
        "seats": metrics["program_completeness"]["open_seats"],
        "rooms_complete": bool(metrics["program_completeness"]["complete"]),
        "usable_m2": metrics["usable_area_m2"], "circulation_m2": metrics["circulation_area_m2"],
        "residual_m2": metrics["wasted_area_m2"], "net_programmed_m2": metrics["net_programmed_area_m2"],
        "daylight": comparison_row.get("daylight"), "client_route": comparison_row.get("client_route"),
        "facade_consumption_pct": comparison_row.get("facade_consumption_pct"),
        "boardroom_path_m": comparison_row.get("boardroom_path_m"),
        "reception_path_m": comparison_row.get("reception_path_m"),
        "work_blocks": comparison_row.get("work_blocks"),
        "fragmentation": comparison_row.get("fragmentation"),
        "compactness": comparison_row.get("compactness"),
    }
    rooms = [{"id": p["id"], "module": p["module"], "seats": p.get("seats", 0),
              "area_m2": round(p["w"] * p["d"], 1), "ratio": round(max(p["w"], p["d"]) / max(min(p["w"], p["d"]), 0.1), 2)}
             for p in layout["placements"]]
    prop = sum(1 for r in rooms if r["ratio"] <= 2.6) / max(len(rooms), 1)
    return {
        "alternative_id": alt,
        "strategy": {"name": spec["name"], "intent": spec["intent"], "spine": spec["spine_strategy"],
                     "neighborhoods": len([n for n in graph["nodes"] if n["kind"] == "work"])},
        "program": {"open_seats": 40, "private_office": 4, "meeting_4": 3, "meeting_8": 1, "boardroom_12": 1,
                    "phone_booth": 3, "reception": 1, "kitchenette": 1, "dining": 1, "lounge": 1},
        "spatial_graph": {"graph_id": graph["graph_id"], "intent": graph["intent"],
                          "edges": [f'{e["a"]} -{e["relation"]}-> {e["b"]}' + (" [DURA]" if e.get("hard") else "")
                                    for e in graph["edges"]],
                          "priorities": graph.get("priorities", {})},
        "rooms": rooms,
        "metrics_summary": ms,
        "rule_based_critique": {"scores": critique["scores"], "verdicts": critique.get("verdicts", {}),
                                "architectural_score": critique["architectural_score"]},
        "fit_verdict": {"fit": fit["fit"], "reason": fit["reason"]},
        "scale_status": {"scale": fit["scale"], "confidence": fit["scale_confidence"],
                         "disclaimer": "Dimensiones sujetas a confirmación de escala."},
        "strategy_signal": round(strategy_signal(alt, ms), 3),
        "proportion_signal": round(prop, 3),
    }


@dataclass
class ReviewResult:
    kind: str                     # spatial | visual
    source: str                   # anthropic | openai | rule_based | deterministic
    ok: bool
    review: Optional[Dict] = None
    error: Optional[str] = None
    usage: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {"kind": self.kind, "source": self.source, "ok": self.ok, "review": self.review,
                "error": self.error, "usage": self.usage}


class _Reviewer:
    kind = "spatial"
    schema = "StructuredSpatialReview"
    purpose = "spatial_review"

    def __init__(self, provider: AIProvider, source: str):
        self.provider, self.source = provider, source

    def _images(self, ctx) -> Optional[List[Dict]]:
        return None

    def review(self, payload: Dict, project: str = "", image_paths: Optional[List[str]] = None) -> ReviewResult:
        pay = copy.deepcopy(payload)                       # el proveedor nunca ve objetos del motor
        alt = pay["alternative_id"]
        version = prompts.REGISTRY[self.purpose]
        try:
            imgs = [_b64(p) for p in (image_paths or [])] if not isinstance(self.provider, DeterministicProvider) else None
            prompt = "" if isinstance(self.provider, DeterministicProvider) else \
                prompts.render(version, pay, self.provider.cfg.model, alt)
            r: ProviderResponse = self.provider.complete_json(
                prompt, self.schema, purpose=self.purpose, alternative_id=alt, project=project,
                images=imgs, context=pay)
            data = r.data
            assert_no_coordinates(data, f"{self.source}/{self.purpose}")
            validate(data, self.schema)
            data["provider"] = self.provider.cfg.provider if not isinstance(self.provider, DeterministicProvider) \
                else "deterministic"
            return ReviewResult(self.kind, self.source, True, data, None, r.usage.to_dict())
        except Exception as e:
            kind = getattr(e, "kind", type(e).__name__)
            return ReviewResult(self.kind, self.source, False, None, str(kind))


class AnthropicSpatialReviewer(_Reviewer):
    """Revisión estructurada. Deliberadamente SIN imagen: juzga la lógica, no el dibujo."""
    kind, schema, purpose = "spatial", "StructuredSpatialReview", "spatial_review"


class OpenAIVisualArchitecturalCritic(_Reviewer):
    """Crítica visual. Recibe el render de la planta; sin imagen no tiene nada que aportar."""
    kind, schema, purpose = "visual", "VisualArchitecturalReview", "visual_review"


class RuleBasedReviewer(_Reviewer):
    """El crítico determinista de E07, sin tocar, emitido en el schema común de E08."""
    kind, schema, purpose = "spatial", "StructuredSpatialReview", "spatial_review"
