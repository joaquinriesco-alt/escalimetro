"""Adapters de VisionInterpreter.

- ManualVisionInterpreter: lee hints desde overrides.json (human-in-the-loop). Sin red.
- OpenAI / Anthropic / Gemini: esqueletos con el contrato completo; hacen la llamada
  sólo si existe la API key. Ningún proveedor se asume permanente: el pipeline recibe
  la instancia por inyección (ver pipeline.py, `--vision`).

Todos comparten `_parse_hints`, así que cambiar de proveedor no toca geometría.
"""
from __future__ import annotations

import base64
import json
import os
from typing import List, Optional

import cv2
import numpy as np

from .base import Hint, PROMPT_TEMPLATE, VisionInterpreter, VisionResult


def _parse_hints(payload: dict) -> List[Hint]:
    out = []
    for h in payload.get("hints", []):
        out.append(Hint(kind=h["kind"], confidence=float(h.get("confidence", 0.0)),
                        point=tuple(h["point"]) if h.get("point") else None,
                        bbox=tuple(h["bbox"]) if h.get("bbox") else None,
                        text=h.get("text", ""), notes=h.get("notes", ""),
                        color_bgr=tuple(h["color_bgr"]) if h.get("color_bgr") else None))
    return out


def _jpeg_b64(image_bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


class ManualVisionInterpreter(VisionInterpreter):
    """Hints escritos a mano en overrides.json → sección "vision_hints"."""
    name = "manual"

    def __init__(self, hints: Optional[list] = None):
        self._hints = hints or []

    def interpret(self, image_bgr, target_unit, known_area_m2=None) -> VisionResult:
        return VisionResult(provider="manual", model="human", hints=_parse_hints({"hints": self._hints}))


class NullVisionInterpreter(VisionInterpreter):
    """No entrega hints. Útil para medir qué hace el pipeline sólo con CV + overrides."""
    name = "null"

    def interpret(self, image_bgr, target_unit, known_area_m2=None) -> VisionResult:
        return VisionResult(provider="null", model="none")


class _RemoteVLM(VisionInterpreter):
    env_key = ""
    model = ""

    def _prompt(self, image_bgr, target_unit):
        h, w = image_bgr.shape[:2]
        return PROMPT_TEMPLATE.format(w=w, h=h, unit=target_unit)

    def _require_key(self):
        key = os.environ.get(self.env_key)
        if not key:
            raise RuntimeError(f"{self.name}: falta {self.env_key}. Usa --vision manual o null.")
        return key


class OpenAIVisionInterpreter(_RemoteVLM):
    name = "openai"
    env_key = "OPENAI_API_KEY"
    model = os.environ.get("ESCALIMETRO_OPENAI_MODEL", "gpt-4o")

    def interpret(self, image_bgr, target_unit, known_area_m2=None) -> VisionResult:
        key = self._require_key()
        from openai import OpenAI  # import perezoso: dependencia opcional
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=self.model, response_format={"type": "json_object"},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": self._prompt(image_bgr, target_unit)},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_jpeg_b64(image_bgr)}"}}]}])
        payload = json.loads(resp.choices[0].message.content)
        return VisionResult(provider=self.name, model=self.model, hints=_parse_hints(payload), raw=payload)


class AnthropicVisionInterpreter(_RemoteVLM):
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"
    model = os.environ.get("ESCALIMETRO_ANTHROPIC_MODEL", "claude-sonnet-4-5")

    def interpret(self, image_bgr, target_unit, known_area_m2=None) -> VisionResult:
        key = self._require_key()
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=self.model, max_tokens=2000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg_b64(image_bgr)}},
                {"type": "text", "text": self._prompt(image_bgr, target_unit)}]}])
        text = msg.content[0].text
        payload = json.loads(text[text.find("{"): text.rfind("}") + 1])
        return VisionResult(provider=self.name, model=self.model, hints=_parse_hints(payload), raw=payload)


class GeminiVisionInterpreter(_RemoteVLM):
    name = "gemini"
    env_key = "GOOGLE_API_KEY"
    model = os.environ.get("ESCALIMETRO_GEMINI_MODEL", "gemini-2.5-pro")

    def interpret(self, image_bgr, target_unit, known_area_m2=None) -> VisionResult:
        key = self._require_key()
        from google import genai
        client = genai.Client(api_key=key)
        ok, buf = cv2.imencode(".jpg", image_bgr)
        resp = client.models.generate_content(
            model=self.model,
            contents=[genai.types.Part.from_bytes(data=buf.tobytes(), mime_type="image/jpeg"),
                      self._prompt(image_bgr, target_unit)],
            config={"response_mime_type": "application/json"})
        payload = json.loads(resp.text)
        return VisionResult(provider=self.name, model=self.model, hints=_parse_hints(payload), raw=payload)


from .ocr_localizer import OCRVisionInterpreter  # noqa: E402

REGISTRY = {
    "ocr": OCRVisionInterpreter,
    "manual": ManualVisionInterpreter,
    "null": NullVisionInterpreter,
    "openai": OpenAIVisionInterpreter,
    "anthropic": AnthropicVisionInterpreter,
    "gemini": GeminiVisionInterpreter,
}
