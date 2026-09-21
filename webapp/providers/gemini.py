"""E31 — adaptador Google Gemini (edición de imagen con texto + imagen).

Codificado contra la referencia REST de `models/{model}:generateContent`
(https://ai.google.dev/api/generate-content, consultada 2026-09-21): `inline_data` para la foto,
`generationConfig.responseModalities=["IMAGE"]`, `imageConfig.aspectRatio`, `seed`, y la imagen de
vuelta en `candidates[].content.parts[].inlineData.data`.

NOTA DE DILIGENCIA: la guía de generación de imágenes muestra hoy un endpoint más nuevo
(`/v1beta/interactions`). Sin credencial no fue posible verificar en vivo cuál de los dos acepta
`gemini-3.1-flash-image`. Si la primera llamada real devuelve 4xx, el cambio está acotado a
`_payload()` y `_extract()`; nada del dominio se entera.

Costo: MEDIDO desde `usageMetadata` (tokens × tarifa publicada); si el proveedor no lo devuelve,
precio de lista de una imagen 1K. Ver docs/E31_PROVIDER_DUE_DILIGENCE.md.
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Dict, Optional

from ..domain import visual
from . import base

NAME = "gemini"
ENV = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini-3.1-flash-image"
ASPECTS = ("1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")

#: Tarifas publicadas (USD por millón de tokens), estándar, 2026-09-21. Salida 1K ≈ 1120 tokens.
PRICE_PER_M = {"gemini-3.1-flash-image": {"in": 0.50, "out": 60.0},
               "gemini-3.1-flash-lite-image": {"in": 0.25, "out": 30.0},
               "gemini-3-pro-image": {"in": 2.00, "out": 120.0}}
LIST_PRICE_1K = {"gemini-3.1-flash-image": 0.067, "gemini-3.1-flash-lite-image": 0.0336,
                 "gemini-3-pro-image": 0.134}
#: Estimación PREVIA para confirmar un gasto (§D). Es el precio de lista de una imagen 1K más el
#: costo de la foto de entrada; el real se mide después desde `usageMetadata`.
ESTIMATE_USD = {"gemini-3.1-flash-image": 0.07, "gemini-3.1-flash-lite-image": 0.04,
                "gemini-3-pro-image": 0.14}


class GeminiProvider:
    name = NAME

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("GEMINI_STAGING_MODEL") or DEFAULT_MODEL

    def available(self) -> bool:
        return base.env_key(ENV) is not None

    def _payload(self, req: visual.StagingRequest, blob: bytes, mime: str) -> Dict:
        dims = base.image_dims(blob)
        cfg: Dict = {"responseModalities": ["IMAGE"]}
        if dims:
            cfg["imageConfig"] = {"aspectRatio": base.nearest_aspect(dims[0], dims[1], ASPECTS)}
        seed = req.context.get("seed")
        if seed is not None:
            cfg["seed"] = int(seed)
        return {"contents": [{"role": "user", "parts": [
                    {"text": req.context["prompt"]},
                    {"inline_data": {"mime_type": mime,
                                     "data": base64.b64encode(blob).decode("ascii")}}]}],
                "generationConfig": cfg}

    @staticmethod
    def _extract(data: Dict) -> bytes:
        fb = data.get("promptFeedback") or {}
        if fb.get("blockReason"):
            raise base.ProviderError(NAME, f"petición bloqueada: {fb.get('blockReason')}")
        for cand in data.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                inl = part.get("inlineData") or part.get("inline_data")
                if inl and inl.get("data"):
                    return base64.b64decode(inl["data"])
        raise base.ProviderError(NAME, "la respuesta no contiene ninguna imagen")

    def _cost(self, data: Dict):
        uso = data.get("usageMetadata") or {}
        tarifa = PRICE_PER_M.get(self.model)
        if uso and tarifa:
            ent = float(uso.get("promptTokenCount") or 0)
            sal = float(uso.get("candidatesTokenCount") or 0)
            return round(ent / 1e6 * tarifa["in"] + sal / 1e6 * tarifa["out"], 6), "measured"
        if self.model in LIST_PRICE_1K:
            return LIST_PRICE_1K[self.model], "list_price"
        return None, "unknown"

    def stage_photo(self, request: visual.StagingRequest, image_bytes: bytes = b"",
                    mime_type: str = "image/png") -> visual.ProviderOutput:
        key = base.env_key(ENV)
        if not key:
            raise visual.ProviderNotConfigured(f"falta {ENV} en el entorno")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = json.dumps(self._payload(request, image_bytes, mime_type)).encode("utf-8")
        t0 = time.monotonic()
        data = base.request_json(NAME, "POST", url,
                                 {"x-goog-api-key": key, "Content-Type": "application/json"}, body)
        latencia = int((time.monotonic() - t0) * 1000)
        img = self._extract(data)
        costo, basis = self._cost(data)
        mime_out = "image/png"
        for cand in data.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                inl = part.get("inlineData") or part.get("inline_data") or {}
                if inl.get("mimeType") or inl.get("mime_type"):
                    mime_out = inl.get("mimeType") or inl.get("mime_type")
        return visual.ProviderOutput(
            image_bytes=img, mime_type=mime_out, provider=NAME, model=self.model,
            latency_ms=latencia, cost_usd=costo, cost_basis=basis,
            seed=str(request.context["seed"]) if request.context.get("seed") is not None else None,
            raw=base.sanitize({"usageMetadata": data.get("usageMetadata"),
                               "modelVersion": data.get("modelVersion"),
                               "finishReason": ((data.get("candidates") or [{}])[0]).get("finishReason")}))
