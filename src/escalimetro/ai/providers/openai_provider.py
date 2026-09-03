"""E08 — proveedor OpenAI (API de runtime del producto).

Misma distinción que en el proveedor Anthropic: **ChatGPT se usó para coordinar el proyecto. Esta clase
es la OpenAI API que ESCALÍMETRO llama en producción.** Se usa para dos propósitos distintos, con dos
modelos configurables por separado: crítica visual de la planta y dirección de la lámina."""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import AIProvider, ProviderError


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, cfg, sleep=None, client=None):
        super().__init__(cfg, sleep=sleep or __import__("time").sleep)
        self._client = client

    def client(self):
        if self._client is None:
            try:
                import openai
            except ImportError:                          # pragma: no cover
                raise ProviderError("provider_unavailable", "el SDK openai no está instalado") from None
            self._client = openai.OpenAI(api_key=self.cfg.api_key(), timeout=self.cfg.timeout, max_retries=0)
        return self._client

    def _call(self, prompt: str, images: Optional[List[Dict]], system: str) -> Dict:
        content: List[Dict] = [{"type": "input_text", "text": prompt}]
        for im in images or []:
            content.append({"type": "input_image",
                            "image_url": f"data:{im['media_type']};base64,{im['data']}"})
        msgs = ([{"role": "system", "content": [{"type": "input_text", "text": system}]}] if system else []) + \
               [{"role": "user", "content": content}]
        try:
            r = self.client().responses.create(model=self.cfg.model, input=msgs, max_output_tokens=4096)
        except Exception as e:
            raise _translate(e) from None
        text = getattr(r, "output_text", "") or ""
        u = getattr(r, "usage", None)
        return {"text": text, "input_tokens": getattr(u, "input_tokens", None),
                "output_tokens": getattr(u, "output_tokens", None), "request_id": getattr(r, "id", None)}


def _translate(e: Exception) -> ProviderError:
    n = type(e).__name__
    s = str(e)
    if "RateLimit" in n or "429" in s:
        return ProviderError("rate_limit", s, retryable=True)
    if "Timeout" in n or "timeout" in s.lower():
        return ProviderError("timeout", s, retryable=True)
    if "Connection" in n or "InternalServer" in n or "APIStatus" in n:
        return ProviderError("provider_unavailable", s, retryable=True)
    if "Authentication" in n or "PermissionDenied" in n:
        return ProviderError("auth_error", "credencial rechazada", retryable=False)
    return ProviderError("provider_error", f"{n}: {e}", retryable=False)
