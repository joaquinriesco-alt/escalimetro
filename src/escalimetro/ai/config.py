"""E08 — configuración de proveedores de IA.

Ningún proveedor ni modelo está escrito en la lógica de negocio. Todo viene de variables de entorno y se
resuelve en `AIProviderConfig`. Cambiar de modelo es cambiar una variable, no tocar el pipeline.

Las API keys se leen del entorno y NO se serializan nunca: `to_dict()` sólo expone `has_key` (bool)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

PURPOSES = ["spatial_review", "visual_review", "presentation"]
PROVIDERS = ["anthropic", "openai", "deterministic"]

DEFAULTS = {
    "OPENAI_MODEL_VISION": "gpt-5",
    "OPENAI_MODEL_PRESENTATION": "gpt-5",
    "ANTHROPIC_MODEL_REVIEWER": "claude-sonnet-4-5",
    "AI_PROVIDER_TIMEOUT": "60",
    "AI_PROVIDER_MAX_RETRIES": "2",
}

_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "deterministic": None}


@dataclass
class AIProviderConfig:
    provider: str                 # anthropic | openai | deterministic
    model: str
    purpose: str                  # spatial_review | visual_review | presentation
    timeout: float = 60.0
    max_retries: int = 2
    enabled: bool = True
    api_key_env: Optional[str] = None
    _api_key: Optional[str] = field(default=None, repr=False)

    @property
    def has_key(self) -> bool:
        return self.provider == "deterministic" or bool(self._api_key)

    @property
    def available(self) -> bool:
        return self.enabled and self.has_key

    def api_key(self) -> Optional[str]:
        """Único punto de acceso a la credencial. No pasa por `to_dict()` ni por ningún log."""
        return self._api_key

    def to_dict(self) -> Dict:
        """Serialización SEGURA: nunca incluye la clave, sólo si existe."""
        return {"provider": self.provider, "model": self.model, "purpose": self.purpose,
                "timeout": self.timeout, "max_retries": self.max_retries, "enabled": self.enabled,
                "api_key_env": self.api_key_env, "has_key": self.has_key, "available": self.available}


def _env(name: str, env: Optional[Dict[str, str]] = None) -> Optional[str]:
    src = env if env is not None else os.environ
    v = src.get(name)
    return v if v not in (None, "") else None


def _num(name: str, env, cast, default):
    v = _env(name, env)
    try:
        return cast(v) if v is not None else cast(DEFAULTS[name])
    except (TypeError, ValueError):
        return cast(DEFAULTS[name]) if name in DEFAULTS else default


def load_configs(env: Optional[Dict[str, str]] = None) -> Dict[str, AIProviderConfig]:
    """Un config por propósito. `env` explícito permite tests sin tocar el entorno del proceso."""
    timeout = _num("AI_PROVIDER_TIMEOUT", env, float, 60.0)
    retries = _num("AI_PROVIDER_MAX_RETRIES", env, int, 2)
    spec = [
        ("spatial_review", "anthropic", _env("ANTHROPIC_MODEL_REVIEWER", env) or DEFAULTS["ANTHROPIC_MODEL_REVIEWER"]),
        ("visual_review", "openai", _env("OPENAI_MODEL_VISION", env) or DEFAULTS["OPENAI_MODEL_VISION"]),
        ("presentation", "openai", _env("OPENAI_MODEL_PRESENTATION", env) or DEFAULTS["OPENAI_MODEL_PRESENTATION"]),
    ]
    out = {}
    for purpose, provider, model in spec:
        key_env = _KEY_ENV[provider]
        out[purpose] = AIProviderConfig(
            provider=provider, model=model, purpose=purpose, timeout=timeout, max_retries=retries,
            enabled=_env(f"AI_DISABLE_{purpose.upper()}", env) is None,
            api_key_env=key_env, _api_key=_env(key_env, env) if key_env else None)
    return out


def missing_keys(cfgs: Dict[str, AIProviderConfig]) -> List[str]:
    return sorted({c.api_key_env for c in cfgs.values() if c.api_key_env and not c.has_key})
