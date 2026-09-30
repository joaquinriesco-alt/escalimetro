"""E37 §Registro de motores. La UI lista lo que hay acá; no conoce ningún motor por su nombre.

Separado a propósito de `webapp.providers`: aquel registro es de ambientación (editar una foto) y
alimenta el panel de preparación, el benchmark y la aprobación del piloto. Mezclar un motor de
reconstrucción ahí cambiaría esos paneles sin que nadie lo pidiera.

Para agregar un motor: escribir un `EngineAdapter` y llamar `register()` —aquí abajo para los que
vienen con la app, o desde un test—. Nada más. Quitarlo es `unregister()`.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import (AVAILABLE, CORRECTION, DISABLED, INITIAL, MISSING_CREDENTIAL, UNAVAILABLE,
                   Availability, EngineAdapter, EngineError, EngineRequest, EngineResult,
                   InputImage, InputVideo)
from . import fixture, openai_direct

__all__ = ["AVAILABLE", "UNAVAILABLE", "MISSING_CREDENTIAL", "DISABLED", "INITIAL", "CORRECTION",
           "Availability", "EngineAdapter", "EngineError", "EngineRequest", "EngineResult",
           "InputImage", "InputVideo", "register", "unregister", "get", "catalog", "adapters"]

_REGISTRY: Dict[str, EngineAdapter] = {}


def register(adapter: EngineAdapter) -> EngineAdapter:
    if not adapter.engine_id:
        raise ValueError("un motor necesita engine_id")
    _REGISTRY[adapter.engine_id] = adapter
    return adapter


def unregister(engine_id: str) -> None:
    _REGISTRY.pop(engine_id, None)


def adapters() -> List[EngineAdapter]:
    """Los motores registrados y habilitados, en orden de registro."""
    return [a for a in _REGISTRY.values() if a.enabled()]


def get(engine_id: str) -> Optional[EngineAdapter]:
    a = _REGISTRY.get(engine_id)
    return a if a is not None and a.enabled() else None


def catalog() -> List[Dict]:
    """Lo que ve la UI: cada motor con su disponibilidad y la razón. Nunca un valor de credencial."""
    return [a.describe() for a in adapters()]


register(openai_direct.OpenAIDirect())
register(fixture.FixtureReplay())
