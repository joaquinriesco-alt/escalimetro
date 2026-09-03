"""E08 — interfaz común de proveedores.

Un proveedor sabe UNA cosa: recibir un prompt (y opcionalmente imágenes) y devolver un dict JSON más un
registro de uso. No sabe qué es un layout, no sabe qué es una alternativa y no toca geometría.

El manejo de fallos (timeout, 429, respuesta vacía, JSON malformado, schema inválido) vive aquí, con un
máximo de reintentos configurable y sin bucles infinitos."""
from __future__ import annotations

import json
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from ..config import AIProviderConfig
from ..schemas import SchemaFailure, validate


class ProviderError(Exception):
    """Fallo del proveedor. `retryable` decide si tiene sentido reintentar."""

    def __init__(self, kind: str, message: str, retryable: bool = False):
        super().__init__(f"{kind}: {message}")
        self.kind, self.message, self.retryable = kind, message, retryable


class ProviderUnavailable(ProviderError):
    def __init__(self, message: str):
        super().__init__("provider_unavailable", message, retryable=False)


@dataclass
class AIUsageRecord:
    provider: str
    model: str
    purpose: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: float = 0.0
    estimated_cost: Optional[float] = None
    reported_cost: Optional[float] = None
    cost_status: str = "unknown"          # estimated | reported | unknown
    request_id: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    attempts: int = 0
    project: Optional[str] = None
    alternative_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return validate(asdict(self), "AIUsageRecord")


@dataclass
class ProviderResponse:
    data: Dict
    usage: AIUsageRecord
    raw_text: str = ""


def extract_json(text: str) -> Dict:
    """Un modelo puede envolver el JSON en prosa o en un bloque ```json. Se extrae el primer objeto
    balanceado; si no hay ninguno, es `malformed_json` (reintentable una vez)."""
    if not text or not text.strip():
        raise ProviderError("empty_response", "el proveedor devolvió una respuesta vacía", retryable=True)
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    start = t.find("{")
    if start < 0:
        raise ProviderError("malformed_json", "no hay objeto JSON en la respuesta", retryable=True)
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(t[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError as e:
                    raise ProviderError("malformed_json", str(e), retryable=True) from None
    raise ProviderError("malformed_json", "objeto JSON sin cerrar", retryable=True)


class AIProvider(ABC):
    """Contrato. `complete_json` devuelve un dict ya validado contra `schema_name`."""

    name = "base"

    def __init__(self, cfg: AIProviderConfig, sleep=time.sleep):
        self.cfg = cfg
        self._sleep = sleep

    @property
    def available(self) -> bool:
        return self.cfg.available

    @abstractmethod
    def _call(self, prompt: str, images: Optional[List[Dict]], system: str) -> Dict:
        """Devuelve {"text": str, "input_tokens": int|None, "output_tokens": int|None, "request_id": str|None}."""

    def complete_json(self, prompt: str, schema_name: str, system: str = "", images=None,
                      purpose: Optional[str] = None, alternative_id: Optional[str] = None,
                      project: Optional[str] = None, context: Optional[Dict] = None) -> ProviderResponse:
        """`context` es el payload estructurado del producto. Los proveedores LLM lo ignoran (ya viene
        serializado dentro de `prompt`); el proveedor determinista lo usa como su única entrada."""
        from ..costs import estimate_cost
        usage = AIUsageRecord(provider=self.cfg.provider, model=self.cfg.model,
                              purpose=purpose or self.cfg.purpose, project=project,
                              alternative_id=alternative_id, request_id=str(uuid.uuid4()))
        if not self.available:
            usage.error = "provider_unavailable"
            raise ProviderUnavailable(f"{self.cfg.provider}/{self.cfg.purpose}: sin credencial o deshabilitado")
        t0 = time.time()
        last: Optional[ProviderError] = None
        attempts = self.cfg.max_retries + 1
        for attempt in range(1, attempts + 1):
            usage.attempts = attempt
            try:
                raw = self._call(prompt, images, system)
                usage.input_tokens = raw.get("input_tokens")
                usage.output_tokens = raw.get("output_tokens")
                usage.request_id = raw.get("request_id") or usage.request_id
                data = extract_json(raw.get("text", ""))
                validate(data, schema_name)
                usage.success = True
                usage.latency_ms = round((time.time() - t0) * 1000, 1)
                cost, status = estimate_cost(self.cfg.provider, self.cfg.model,
                                             usage.input_tokens, usage.output_tokens)
                usage.estimated_cost, usage.cost_status = cost, status
                return ProviderResponse(data=data, usage=usage, raw_text=raw.get("text", ""))
            except SchemaFailure as e:
                last = ProviderError("provider_failed_schema", str(e), retryable=attempt < attempts)
            except ProviderError as e:
                last = e
            except Exception as e:                                  # error inesperado del SDK
                last = ProviderError("provider_error", f"{type(e).__name__}: {e}", retryable=False)
            if not last.retryable or attempt >= attempts:
                break
            self._sleep(min(2.0 ** (attempt - 1), 8.0))
        usage.latency_ms = round((time.time() - t0) * 1000, 1)
        usage.success = False
        usage.error = last.kind if last else "unknown"
        raise last if last else ProviderError("unknown", "fallo sin diagnóstico")
