"""E31 — adaptador OpenAI Images (`POST /v1/images/edits`).

Codificado contra la referencia del endpoint (developers.openai.com/api/docs/api-reference/images/
createEdit, consultada 2026-09-21): multipart con `image`, `prompt`, `model`, `size`, `quality`,
`input_fidelity`, `output_format`; respuesta `data[0].b64_json` + `usage` con tokens.

`input_fidelity=high` es el único control documentado sobre cuánto se respeta la imagen de entrada,
y es exactamente lo que este producto necesita. No hay `seed`: la repetibilidad se mide, no se
configura. El enmascarado es "prompt-based" según la guía, así que no se usa máscara: la
preservación se pide por contrato de texto, igual que a los demás.

El tamaño se calcula para conservar la proporción de la foto (múltiplos de 16, 1:3–3:1, dentro de
los límites de píxeles publicados); si no se puede, `auto`.

Costo: MEDIDO desde `usage` (tokens × tarifa publicada). Ver docs/E31_PROVIDER_DUE_DILIGENCE.md.
"""
from __future__ import annotations

import base64
import os
import time
from typing import Dict, Optional

from ..domain import visual
from . import base

NAME = "openai"
ENV = "OPENAI_API_KEY"
DEFAULT_MODEL = "gpt-image-2.5-sunburst"
URL = "https://api.openai.com/v1/images/edits"

#: USD por millón de tokens, estándar, 2026-09-21.
PRICE_PER_M = {"gpt-image-2.5-sunburst": {"img_in": 8.0, "txt_in": 5.0, "out": 30.0},
               "gpt-image-2.5-flare": {"img_in": 8.0, "txt_in": 5.0, "out": 30.0},
               "gpt-image-2": {"img_in": 8.0, "txt_in": 5.0, "out": 30.0},
               "gpt-image-1.5": {"img_in": 8.0, "txt_in": 5.0, "out": 32.0},
               "gpt-image-1": {"img_in": 10.0, "txt_in": 5.0, "out": 40.0}}
MIN_PX, MAX_PX, MAX_EDGE = 655_360, 8_294_400, 3840


def size_for(w: int, h: int, long_edge: int = 1536) -> str:
    """Tamaño que conserva la proporción de la foto dentro de las reglas publicadas."""
    r = w / float(h)
    if r > 3 or r < 1 / 3:
        return "auto"
    if w >= h:
        W = long_edge; H = int(round(W / r))
    else:
        H = long_edge; W = int(round(H * r))
    W, H = max(16, (W // 16) * 16), max(16, (H // 16) * 16)
    if W * H < MIN_PX:
        f = (MIN_PX / (W * H)) ** 0.5
        W, H = ((int(W * f) // 16) + 1) * 16, ((int(H * f) // 16) + 1) * 16
    if W * H > MAX_PX or W > MAX_EDGE or H > MAX_EDGE:
        return "auto"
    return f"{W}x{H}"


class OpenAIImagesProvider:
    name = NAME

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("OPENAI_STAGING_MODEL") or DEFAULT_MODEL
        self.quality = os.environ.get("OPENAI_STAGING_QUALITY") or "high"

    def available(self) -> bool:
        return base.env_key(ENV) is not None

    def _fields(self, req: visual.StagingRequest, blob: bytes) -> Dict[str, str]:
        dims = base.image_dims(blob)
        return {"model": self.model, "prompt": req.context["prompt"], "n": "1",
                "size": size_for(*dims) if dims else "auto", "quality": self.quality,
                "input_fidelity": "high", "output_format": "png"}

    def _cost(self, data: Dict):
        uso = data.get("usage") or {}
        tarifa = PRICE_PER_M.get(self.model)
        if uso and tarifa:
            det = uso.get("input_tokens_details") or {}
            img_in = float(det.get("image_tokens") or 0)
            txt_in = float(det.get("text_tokens") or 0)
            if not det:
                img_in = float(uso.get("input_tokens") or 0)
            sal = float(uso.get("output_tokens") or 0)
            return (round(img_in / 1e6 * tarifa["img_in"] + txt_in / 1e6 * tarifa["txt_in"]
                          + sal / 1e6 * tarifa["out"], 6), "measured")
        return None, "unknown"

    def stage_photo(self, request: visual.StagingRequest, image_bytes: bytes = b"",
                    mime_type: str = "image/png") -> visual.ProviderOutput:
        key = base.env_key(ENV)
        if not key:
            raise visual.ProviderNotConfigured(f"falta {ENV} en el entorno")
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime_type, "png")
        ctype, body = base.multipart(self._fields(request, image_bytes),
                                     [("image", f"source.{ext}", image_bytes, mime_type)])
        t0 = time.monotonic()
        data = base.request_json(NAME, "POST", URL,
                                 {"Authorization": f"Bearer {key}", "Content-Type": ctype}, body)
        latencia = int((time.monotonic() - t0) * 1000)
        items = data.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise base.ProviderError(NAME, "la respuesta no contiene ninguna imagen")
        costo, basis = self._cost(data)
        return visual.ProviderOutput(
            image_bytes=base64.b64decode(items[0]["b64_json"]), mime_type="image/png",
            provider=NAME, model=self.model, latency_ms=latencia, cost_usd=costo, cost_basis=basis,
            seed=None, raw=base.sanitize({"usage": data.get("usage"), "size": data.get("size"),
                                          "quality": data.get("quality"),
                                          "input_fidelity": "high"}))
