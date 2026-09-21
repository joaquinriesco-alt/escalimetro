"""E31 — registro de proveedores de ambientación. La raíz de composición y nada más.

Un proveedor se usa en el PRODUCTO sólo si una PERSONA lo aprobó tras ver las tasas del bake-off
(`domain/pilot.approve`). E32 §H: "Key presence must NEVER select the provider". Tener tres claves
en el entorno no convierte a ninguno en el elegido, y `ESCALIMETRO_STAGING_PROVIDER` ya no elige
nada — se conserva sólo para poder decir en la consola que está puesta y que no manda.

Jamás se cae a otro proveedor si el aprobado no responde: comparar proveedores exige saber
exactamente cuál respondió (§16 de E31: "no silent fallback").

El bake-off y los smoke tests nombran a cada proveedor explícitamente y no pasan por la aprobación:
son experimentos, y lo que producen no puede llegar a un cliente.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from ..domain import visual
from . import bfl, gemini, openai_images

ENV_SELECT = "ESCALIMETRO_STAGING_PROVIDER"

_FACTORIES = {gemini.NAME: gemini.GeminiProvider,
              openai_images.NAME: openai_images.OpenAIImagesProvider,
              bfl.NAME: bfl.BFLProvider}
NAMES = tuple(_FACTORIES)
ENV_OF = {gemini.NAME: gemini.ENV, openai_images.NAME: openai_images.ENV, bfl.NAME: bfl.ENV}


def resolve(name: Optional[str] = None) -> visual.VisualStagingProvider:
    """Sin `name`, devuelve el proveedor APROBADO (y sólo si además tiene credencial). Con `name`,
    ese proveedor: es el camino de los experimentos, que nombran a quién le preguntan."""
    if name:
        elegido = name.strip().lower()
    else:
        from ..domain import pilot                            # noqa: PLC0415
        elegido = (pilot.approved_provider_name() or "").lower()
    if not elegido or elegido == visual.NotConfiguredProvider.name:
        return visual.NotConfiguredProvider()
    fab = _FACTORIES.get(elegido)
    if fab is None:
        raise visual.ProviderNotConfigured(
            f"proveedor de ambientación desconocido: {elegido!r} (válidos: {', '.join(NAMES)})")
    return fab()


def known(name: str) -> bool:
    """¿Existe un adaptador con ese nombre? Se consulta el registro VIVO, no la lista congelada al
    importar: así un adaptador añadido en caliente (los tests lo hacen) también se reconoce."""
    return (name or "").strip().lower() in _FACTORIES


def estimate_usd(name: str) -> Optional[float]:
    """Cuánto costaría UNA generación con este proveedor, según precio de lista. Sirve para pedir
    confirmación antes de gastar; el costo real se mide después, intento por intento."""
    mod = {gemini.NAME: gemini, openai_images.NAME: openai_images, bfl.NAME: bfl}.get(name)
    if mod is None:
        return None
    p = _FACTORIES[name]()
    return getattr(mod, "ESTIMATE_USD", {}).get(p.model)


def catalog() -> List[Dict]:
    """Para la pantalla interna: qué proveedores existen y cuáles tienen credencial. Sin valores."""
    from ..domain import pilot                                # noqa: PLC0415
    aprobado = pilot.approved_provider_name()
    out = []
    for n in NAMES:
        p = _FACTORIES[n]()
        out.append({"name": n, "model": p.model, "env": ENV_OF[n], "available": p.available(),
                    "selected": aprobado == n})
    return out
