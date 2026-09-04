"""E08 — AI ORCHESTRATOR.

Lo que hace:

1. resuelve proveedores desde configuración (nunca hardcode);
2. hashea la geometría ANTES de cualquier llamada;
3. lanza en PARALELO las revisiones independientes (Anthropic no espera a OpenAI);
4. cae al crítico determinista cuando un proveedor no está;
5. agrega las revisiones sin promediar los desacuerdos;
6. hashea la geometría DESPUÉS y falla si cambió;
7. registra uso, latencia y decisiones.

Lo que NO hace: tocar el solver, generar layouts, ni dejar que un modelo decida si una geometría es
válida. La IA sólo recibe A/B/C ya validados — nunca los miles de candidatos internos."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..layout.model import Layout
from .config import AIProviderConfig, load_configs, missing_keys
from .geometry_guard import GeometryGuard, geometry_hash
from .providers.anthropic_provider import AnthropicProvider
from .providers.deterministic_provider import DeterministicProvider
from .providers.openai_provider import OpenAIProvider
from .review_aggregator import aggregate, requires_internal_review
from .reviewers import (AnthropicSpatialReviewer, OpenAIVisualArchitecturalCritic, ReviewResult,
                        RuleBasedReviewer, build_payload)
from .telemetry import UsageLedger

PROVIDER_CLASSES = {"anthropic": AnthropicProvider, "openai": OpenAIProvider,
                    "deterministic": DeterministicProvider}


def _det_cfg(purpose: str) -> AIProviderConfig:
    return AIProviderConfig(provider="deterministic", model="rule_based_v1", purpose=purpose,
                            timeout=1.0, max_retries=0, enabled=True)


@dataclass
class AlternativeAIResult:
    alternative_id: str
    reviews: Dict[str, Optional[Dict]]
    aggregated: Dict
    geometry_hash_before: str
    geometry_hash_after: str
    latencies_ms: Dict[str, float]
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def geometry_intact(self) -> bool:
        return self.geometry_hash_before == self.geometry_hash_after

    def to_dict(self) -> Dict:
        return {"alternative_id": self.alternative_id, "reviews": self.reviews,
                "aggregated": self.aggregated, "geometry_hash_before": self.geometry_hash_before,
                "geometry_hash_after": self.geometry_hash_after, "geometry_intact": self.geometry_intact,
                "latencies_ms": self.latencies_ms, "errors": self.errors,
                "requires_internal_review": requires_internal_review(self.aggregated)}


class AIOrchestrator:
    def __init__(self, project: str, env: Optional[Dict[str, str]] = None,
                 providers: Optional[Dict[str, object]] = None, max_workers: int = 3, shell=None):
        """E16.1 §18 — `project` es OBLIGATORIO. Antes tenía `"001_gps_403"` por defecto: cualquier
        orquestación que no lo declarara quedaba etiquetada como la Oficina 403 en los payloads que
        van a los críticos. Los dos llamadores reales (ai/run.py y ai/e09.py) ya lo pasaban
        explícitamente; el único que dependía del default eran tests que no usan el valor. No se
        sustituye por otro default: un identificador de proyecto que nadie declaró no existe."""
        if not project:
            raise ValueError("AIOrchestrator necesita el proyecto/caso explícitamente: no hay un "
                             "proyecto por defecto")
        self.project = project
        self.shell = shell        # el shell entra al hash: es geometría, aunque sea común a las tres
        self.configs = load_configs(env)
        self.missing_keys = missing_keys(self.configs)
        self.max_workers = max_workers
        self.ledger = UsageLedger(project)
        self.providers: Dict[str, object] = providers or {}
        for purpose, cfg in self.configs.items():
            self.providers.setdefault(purpose, PROVIDER_CLASSES[cfg.provider](cfg))
        self.providers.setdefault("deterministic_spatial", DeterministicProvider(_det_cfg("spatial_review")))
        self.providers.setdefault("deterministic_visual", DeterministicProvider(_det_cfg("visual_review")))
        self.providers.setdefault("deterministic_presentation",
                                  DeterministicProvider(_det_cfg("presentation")))

    # ---------------------------------------------------------------------------------------------
    def provider_status(self) -> Dict[str, Dict]:
        out = {}
        for purpose, cfg in self.configs.items():
            p = self.providers[purpose]
            out[purpose] = {**cfg.to_dict(),
                            "status": "AVAILABLE" if getattr(p, "available", False) else
                                      ("NO_API_KEY" if not cfg.has_key else "DISABLED")}
        out["deterministic"] = {"provider": "deterministic", "model": "rule_based_v1",
                                "purpose": "fallback", "status": "AVAILABLE", "has_key": True}
        return out

    # ---------------------------------------------------------------------------------------------
    def review_alternative(self, alt: str, layout: Layout, payload: Dict,
                           image_paths: Optional[List[str]] = None) -> AlternativeAIResult:
        """Una alternativa, tres revisores, en paralelo. La geometría se hashea alrededor de todo."""
        guard = GeometryGuard(layout, self.shell, what=f"ai_review_{alt}")
        latencies: Dict[str, float] = {}
        errors: Dict[str, str] = {}
        with guard:
            rule = RuleBasedReviewer(self.providers["deterministic_spatial"], "rule_based")
            anth = AnthropicSpatialReviewer(self.providers["spatial_review"], "anthropic")
            oai = OpenAIVisualArchitecturalCritic(self.providers["visual_review"], "openai_vision")

            jobs = {
                "rule_based": lambda: rule.review(payload, self.project),
                "anthropic": lambda: anth.review(payload, self.project),
                "openai_vision": lambda: oai.review(payload, self.project, image_paths=image_paths),
            }
            results: Dict[str, ReviewResult] = {}
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futs = {}
                for name, fn in jobs.items():
                    t0 = time.time()
                    futs[ex.submit(fn)] = (name, t0)
                for fut, (name, t0) in list(futs.items()):
                    results[name] = fut.result()
                    latencies[name] = round((time.time() - t0) * 1000, 1)

        reviews: Dict[str, Optional[Dict]] = {}
        for name, r in results.items():
            reviews[name] = r.review if r.ok else None
            if r.usage:
                self.ledger.add(r.usage)
            if not r.ok:
                errors[name] = r.error or "unknown"

        # Fallback declarado: si el crítico visual no está, el determinista ocupa su lugar y lo dice.
        if reviews.get("openai_vision") is None:
            det = OpenAIVisualArchitecturalCritic(self.providers["deterministic_visual"],
                                                  "deterministic_visual").review(payload, self.project)
            if det.ok:
                reviews["deterministic_visual"] = det.review
                self.ledger.add(det.usage)

        status = {k: ("unavailable" if k in errors else "present") for k in reviews}
        agg = aggregate(alt, reviews, status).to_dict()
        return AlternativeAIResult(alt, reviews, agg, guard.before, guard.after, latencies, errors)

    # ---------------------------------------------------------------------------------------------
    def presentation_spec(self, ctx: Dict) -> Dict:
        """OpenAI dirige la lámina; si no está, dirige la plantilla determinista. En ambos casos el
        RENDER lo hace el código, nunca el modelo."""
        from . import prompts
        from .schemas import assert_no_coordinates, validate
        p = self.providers["presentation"]
        if getattr(p, "available", False):
            try:
                prompt = prompts.render(prompts.REGISTRY["presentation"], ctx, self.configs["presentation"].model)
                r = p.complete_json(prompt, "PresentationSpec", purpose="presentation",
                                    project=self.project, context=ctx)
                self.ledger.add(r.usage.to_dict())
                assert_no_coordinates(r.data, "presentation_spec")
                return validate(r.data, "PresentationSpec")
            except Exception as e:
                self.ledger.add({"provider": "openai", "model": self.configs["presentation"].model,
                                 "purpose": "presentation", "input_tokens": None, "output_tokens": None,
                                 "latency_ms": 0.0, "estimated_cost": None, "cost_status": "unknown",
                                 "request_id": None, "success": False,
                                 "error": str(getattr(e, "kind", type(e).__name__)), "attempts": 1})
        r = self.providers["deterministic_presentation"].complete_json(
            "", "PresentationSpec", purpose="presentation", project=self.project, context=ctx)
        self.ledger.add(r.usage.to_dict())
        assert_no_coordinates(r.data, "presentation_spec")
        return r.data


__all__ = ["AIOrchestrator", "AlternativeAIResult", "build_payload", "geometry_hash"]
