"""E31 — registro de proveedores de ambientación. La raíz de composición y nada más.

Un proveedor se usa en el PRODUCTO sólo si alguien lo decidió: `ESCALIMETRO_STAGING_PROVIDER`
tiene que nombrarlo. Que exista una clave en el entorno no basta —tener tres claves no convierte a
ninguno en el elegido— y jamás se cae a otro proveedor si el nombrado no está: comparar proveedores
exige saber exactamente cuál respondió (§16: "no silent fallback").

El benchmark nombra a cada uno explícitamente y no pasa por la variable de entorno.
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
    elegido = (name or os.environ.get(ENV_SELECT) or "").strip().lower()
    if not elegido or elegido == visual.NotConfiguredProvider.name:
        return visual.NotConfiguredProvider()
    fab = _FACTORIES.get(elegido)
    if fab is None:
        raise visual.ProviderNotConfigured(
            f"proveedor de ambientación desconocido: {elegido!r} (válidos: {', '.join(NAMES)})")
    return fab()


def catalog() -> List[Dict]:
    """Para la pantalla interna: qué proveedores existen y cuáles tienen credencial. Sin valores."""
    out = []
    for n in NAMES:
        p = _FACTORIES[n]()
        out.append({"name": n, "model": p.model, "env": ENV_OF[n], "available": p.available(),
                    "selected": (os.environ.get(ENV_SELECT) or "").strip().lower() == n})
    return out
