"""E08 — proveedor Anthropic (API de runtime del producto).

Ojo con la distinción, que no es cosmética: **Claude Code / Claude Chat se usaron para CONSTRUIR
ESCALÍMETRO. Esta clase es la Anthropic API que ESCALÍMETRO usa en producción.** Son dos cosas
distintas: una es herramienta de desarrollo, la otra es una dependencia del producto con su propia
credencial, su propio costo, su propia latencia y su propio modo de fallo."""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import AIProvider, ProviderError


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, cfg, sleep=None, client=None):
        super().__init__(cfg, sleep=sleep or __import__("time").sleep)
        self._client = client

    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:                          # pragma: no cover
                raise ProviderError("provider_unavailable", "el SDK anthropic no está instalado") from None
            self._client = anthropic.Anthropic(api_key=self.cfg.api_key(), timeout=self.cfg.timeout,
                                               max_retries=0)   # los reintentos los maneja AIProvider
        return self._client

    def _call(self, prompt: str, images: Optional[List[Dict]], system: str) -> Dict:
        content: List[Dict] = []
        for im in images or []:
            content.append({"type": "image", "source": {"type": "base64", "media_type": im["media_type"],
                                                        "data": im["data"]}})
        content.append({"type": "text", "text": prompt})
        try:
            msg = self.client().messages.create(
                model=self.cfg.model, max_tokens=4096, system=system or "",
                messages=[{"role": "user", "content": content}])
        except Exception as e:
            raise _translate(e) from None
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        u = getattr(msg, "usage", None)
        return {"text": text, "input_tokens": getattr(u, "input_tokens", None),
                "output_tokens": getattr(u, "output_tokens", None), "request_id": getattr(msg, "id", None)}


def _translate(e: Exception) -> ProviderError:
    n = type(e).__name__
    if "RateLimit" in n or "429" in str(e):
        return ProviderError("rate_limit", str(e), retryable=True)
    if "Timeout" in n or "timeout" in str(e).lower():
        return ProviderError("timeout", str(e), retryable=True)
    if "Connection" in n or "APIStatus" in n or "Internal" in n:
        return ProviderError("provider_unavailable", str(e), retryable=True)
    if "Authentication" in n or "PermissionDenied" in n:
        return ProviderError("auth_error", "credencial rechazada", retryable=False)
    return ProviderError("provider_error", f"{n}: {e}", retryable=False)
