"""E28 §14 — CONTRATO del futuro motor visual. Sin implementación, y a propósito.

Acá no hay ninguna llamada a ningún proveedor, ninguna clave y ninguna imagen generada. Lo único
que existe es la forma de la conversación que E29 va a tener con quien sea que haga el staging, y
el vocabulario para describir qué puede tocarse de una foto y qué no.

Por qué el contrato antes que el proveedor: la pregunta difícil de virtual staging no es "¿qué API
uso?" sino "¿cómo sé que la imagen que me devolvieron sigue siendo ESTA oficina?". Si eso no está
escrito antes de integrar, se termina eligiendo proveedor por la calidad del render y descubriendo
después que mueve las ventanas de lugar.

ADVERTENCIA HONESTA sobre los invariantes: este módulo los DECLARA, no los verifica. Nada en E28
comprueba que una imagen conserve la perspectiva. El día que haya un proveedor real, esa
verificación es trabajo propio y probablemente el más importante de E29.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Protocol

CONTRACT_VERSION = "visual_staging_v1"

#: Lo que NO puede cambiar entre la foto original y la ambientada. Es la definición de "sigue siendo
#: la misma oficina": si esto se mueve, la imagen es una fantasía y no material comercial honesto.
ARCHITECTURAL_INVARIANTS = (
    "perspective",        # el punto de vista y la óptica
    "windows",            # posición, tamaño y forma de las ventanas
    "columns",            # pilares
    "walls",              # muros existentes
    "ceiling",            # cielo y su altura aparente
    "floor",              # plano de piso
    "structure",          # vigas, losas, cualquier elemento portante
    "exterior_views",     # lo que se ve por las ventanas
)

#: Lo que sí puede cambiar: es la propuesta, no el edificio.
EDITABLE_ELEMENTS = (
    "furniture",
    "decoration",
    "decorative_lighting",
    "plants",
    "occupancy",
    "proposed_partitions",   # sólo si la salida las presenta explícitamente como propuesta
)


class VisualStagingError(RuntimeError):
    """Base de los errores del contrato."""


class ProviderNotConfigured(VisualStagingError):
    """No hay proveedor. Es el estado normal en E28 y debe fallar RUIDOSAMENTE.

    Deliberadamente no existe un modo 'degradado' que devuelva la foto original haciéndola pasar
    por ambientada: un pack que miente sobre lo que contiene es peor que un pack incompleto."""


class ProviderDisabled(VisualStagingError):
    """Hay proveedor pero está apagado por configuración."""


class InvariantViolation(VisualStagingError):
    """La imagen devuelta cambió algo que no podía cambiar. Nadie la lanza todavía."""


@dataclass(frozen=True)
class StagingRequest:
    property_id: str
    source_asset_id: str
    style_preset: str = "office_neutral"
    #: Contexto que el proveedor puede usar para no inventar: superficie, tipo de espacio, notas.
    context: Dict = field(default_factory=dict)
    must_preserve: List[str] = field(default_factory=lambda: list(ARCHITECTURAL_INVARIANTS))
    may_edit: List[str] = field(default_factory=lambda: list(EDITABLE_ELEMENTS))
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class StagingResult:
    """Lo que un proveedor tiene que devolver para que el asset derivado sea trazable."""
    derived_asset_id: str
    provider: str
    model: str
    cost_usd: Optional[float]
    latency_s: Optional[float]
    seed: Optional[str]
    request: Dict
    #: Verificación de invariantes: None mientras no exista. NO se rellena con optimismo.
    invariants_verified: Optional[Dict] = None
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> Dict:
        return asdict(self)


class VisualStagingProvider(Protocol):
    """Lo que E29 tendrá que implementar. Una sola operación."""

    name: str

    def available(self) -> bool: ...

    def stage_photo(self, request: StagingRequest) -> StagingResult: ...


class NotConfiguredProvider:
    """El proveedor que hay en E28: ninguno. Existe para que el resto del sistema pueda
    preguntarle si está disponible y recibir un no honesto."""

    name = "not_configured"

    def available(self) -> bool:
        return False

    def stage_photo(self, request: StagingRequest) -> StagingResult:
        raise ProviderNotConfigured(
            "El motor de ambientación todavía no existe. E28 deja el contrato; la integración y "
            "sus compuertas de fidelidad son trabajo de E29.")


def get_provider() -> VisualStagingProvider:
    """Punto único de obtención. Hoy siempre devuelve el no-configurado."""
    return NotConfiguredProvider()


def staging_status() -> Dict:
    """Lo que el manifiesto del pack debe decir sobre las imágenes ambientadas."""
    p = get_provider()
    return {"contract_version": CONTRACT_VERSION, "provider": p.name,
            "available": p.available(), "status": "not_generated",
            "reason": "no hay motor de ambientación integrado en esta versión"}
