"""E31 — adaptador Black Forest Labs (FLUX.1 Kontext [pro] por defecto).

Codificado contra la referencia (docs.bfl.ml, consultada 2026-09-21): `POST /v1/flux-kontext-pro`
con cabecera `x-key`, cuerpo `prompt` + `input_image` (base64, ≤20 MB / 20 MP), `seed` (¡sí hay!),
`output_format`, `safety_tolerance`, `prompt_upsampling`; respuesta `{id, polling_url}`; sondeo GET
a `polling_url` cada 0,5 s hasta `Ready`; la imagen en `result.sample`, una URL firmada válida 10
minutos que se descarga de inmediato y NO se guarda.

Kontext es el modelo de edición con preservación estructural de BFL y tiene precio fijo por imagen
($0.04 pro / $0.08 max): el costo es de lista. Los endpoints FLUX.2 devuelven `cost` en créditos
($0.01) y ahí sí es medido.

ADVERTENCIA DE LICENCIA (docs/E31_PROVIDER_DUE_DILIGENCE.md): los términos del servicio API de BFL
otorgan a BFL una licencia perpetua sobre Inputs y Outputs para mejorar sus productos. Antes de
mandar una foto de un cliente real por este adaptador, eso tiene que estar decidido por Joaquín.
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Dict, Optional

from ..domain import visual
from . import base

NAME = "bfl"
ENV = "BFL_API_KEY"
DEFAULT_MODEL = "flux-kontext-pro"
HOST = "https://api.bfl.ai"
LIST_PRICE = {"flux-kontext-pro": 0.04, "flux-kontext-max": 0.08}
CREDIT_USD = 0.01
POLL_S = float(os.environ.get("BFL_POLL_S", "0.5"))
POLL_MAX_S = int(os.environ.get("BFL_POLL_MAX_S", "180"))
TERMINAL_BAD = ("Error", "Failed", "Content Moderated", "Request Moderated")


class BFLProvider:
    name = NAME

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("BFL_STAGING_MODEL") or DEFAULT_MODEL

    def available(self) -> bool:
        return base.env_key(ENV) is not None

    def _payload(self, req: visual.StagingRequest, blob: bytes) -> Dict:
        p: Dict = {"prompt": req.context["prompt"],
                   "input_image": base64.b64encode(blob).decode("ascii"),
                   "output_format": "png", "safety_tolerance": 2, "prompt_upsampling": False}
        seed = req.context.get("seed")
        if seed is not None:
            p["seed"] = int(seed)
        return p

    def stage_photo(self, request: visual.StagingRequest, image_bytes: bytes = b"",
                    mime_type: str = "image/png") -> visual.ProviderOutput:
        key = base.env_key(ENV)
        if not key:
            raise visual.ProviderNotConfigured(f"falta {ENV} en el entorno")
        cab = {"x-key": key, "Content-Type": "application/json", "accept": "application/json"}
        t0 = time.monotonic()
        creado = base.request_json(NAME, "POST", f"{HOST}/v1/{self.model}", cab,
                                   json.dumps(self._payload(request, image_bytes)).encode("utf-8"))
        polling = creado.get("polling_url")
        if not polling:
            raise base.ProviderError(NAME, "la respuesta de creación no trae polling_url")
        estado, resultado = "Pending", {}
        while time.monotonic() - t0 < POLL_MAX_S:
            resultado = base.request_json(NAME, "GET", polling, {"x-key": key, "accept": "application/json"})
            estado = resultado.get("status", "Pending")
            if estado == "Ready":
                break
            if estado in TERMINAL_BAD:
                raise base.ProviderError(NAME, f"estado terminal del proveedor: {estado}")
            time.sleep(POLL_S)
        if estado != "Ready":
            raise base.ProviderError(NAME, f"tiempo agotado esperando el resultado ({POLL_MAX_S} s)")
        muestra = (resultado.get("result") or {}).get("sample")
        if not muestra:
            raise base.ProviderError(NAME, "resultado Ready sin imagen (result.sample vacío)")
        st, _, blob = base.request("GET", muestra, {}, None)
        if st >= 400 or not blob:
            raise base.ProviderError(NAME, "no se pudo descargar la imagen firmada", st)
        latencia = int((time.monotonic() - t0) * 1000)
        if creado.get("cost") is not None:
            costo, basis = round(float(creado["cost"]) * CREDIT_USD, 6), "measured"
        elif self.model in LIST_PRICE:
            costo, basis = LIST_PRICE[self.model], "list_price"
        else:
            costo, basis = None, "unknown"
        seed = (resultado.get("result") or {}).get("seed")
        return visual.ProviderOutput(
            image_bytes=blob, mime_type="image/png", provider=NAME, model=self.model,
            latency_ms=latencia, cost_usd=costo, cost_basis=basis,
            seed=str(seed) if seed is not None else None,
            # sin polling_url ni sample: son URLs firmadas y no se persisten
            raw=base.sanitize({"id": creado.get("id"), "status": estado,
                               "input_mp": creado.get("input_mp"), "output_mp": creado.get("output_mp"),
                               "credits": creado.get("cost")}))
