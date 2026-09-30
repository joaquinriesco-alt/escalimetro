"""E37 §Registro de motores — lo que todo adaptador cumple, y lo único que recibe.

**Lo que recibe un motor es `EngineRequest`, y nada más.** Imágenes en memoria con un id opaco,
los datos que el operador declaró y, si es una corrección, el plano anterior y la instrucción. No
recibe rutas, ni el nombre del proyecto, ni nombres de archivo, ni el id del proyecto: nada que
permita volver al disco. Por eso el ground truth no le puede llegar por accidente: no existe un
camino desde este objeto hacia él (E37 §4, y lo prueban los tests adversariales).

**Lo que devuelve es `EngineResult`**, con la representación v1 cruda —la valida `runs`, no el
adaptador, para que ningún motor se juzgue a sí mismo— más costo, latencia y lo que se mandó.

Un motor que falla lanza `EngineError`: la corrida queda FAILED con el mensaje saneado. Un motor
que no sabe NO falla: devuelve `INSUFFICIENT_EVIDENCE` o `CLARIFICATION_REQUIRED`, que son
resultados válidos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
MISSING_CREDENTIAL = "MISSING_CREDENTIAL"
DISABLED = "DISABLED"

INITIAL = "INITIAL"
CORRECTION = "CORRECTION"


@dataclass(frozen=True)
class InputImage:
    asset_id: str                 # opaco: rca_ + hex. No dice nada del archivo ni del proyecto.
    mime_type: str
    data: bytes = field(repr=False)
    width_px: Optional[int] = None
    height_px: Optional[int] = None


@dataclass(frozen=True)
class InputVideo:
    asset_id: str
    mime_type: str
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class EngineRequest:
    mode: str                                 # INITIAL | CORRECTION
    images: Tuple[InputImage, ...]
    declared: Dict[str, Any]                  # lo que el operador declaró, tal cual
    params: Dict[str, Any]                    # congelados al crear la corrida
    previous: Optional[Dict[str, Any]] = None  # la representación v1 que se corrige
    instruction: Optional[str] = None          # la corrección en lenguaje natural
    clarification_context: Optional[str] = None  # la pregunta que el motor hizo antes, si la hubo
    ignored_inputs: Tuple[str, ...] = ()       # p. ej. "2 documentos": el motor no los consume
    videos: Tuple[InputVideo, ...] = ()        # sólo si el motor declara la capacidad "video"


@dataclass
class EngineResult:
    output: Dict[str, Any]                    # la representación v1, SIN validar todavía
    model: str
    latency_ms: Optional[int]
    prompt_version: str
    prompt_sha256: str
    request_summary: Dict[str, Any]           # saneado y sin imágenes: qué se mandó
    raw: Dict[str, Any] = field(default_factory=dict)  # respuesta del proveedor, saneada
    usage: Dict[str, Any] = field(default_factory=dict)
    cost_usd: Optional[float] = None
    cost_basis: str = "unknown"               # measured | list_price | unknown


@dataclass(frozen=True)
class Availability:
    status: str                               # AVAILABLE | UNAVAILABLE
    reason: Optional[str] = None              # MISSING_CREDENTIAL | DISABLED | …
    detail: str = ""                          # para la UI; nunca un valor de credencial


class EngineError(RuntimeError):
    """Falla técnica del motor: red, proveedor, entrada ilegible, respuesta cortada.

    `partial` lleva lo que ya se sabe cuando la falla ocurre DESPUÉS de hablar con el proveedor
    —latencia, tokens, versión del prompt, qué se mandó, la respuesta cruda—: esa llamada se pagó,
    y una corrida fallida tiene que dejar registrado cuánto costó y qué devolvió (E37 §5)."""

    def __init__(self, kind: str, message: str, partial: Optional[Dict[str, Any]] = None):
        self.kind = kind
        self.partial = dict(partial or {})
        super().__init__(f"{kind}: {message}")


class EngineAdapter:
    """Base de todo adaptador. Agregar un motor es subclasear esto y registrarlo; ni la UI ni el
    modelo de datos cambian (E37 §6)."""

    engine_id: str = ""
    name: str = ""
    version: str = "1"
    provider: str = ""
    pipeline: str = ""
    #: Qué consume: photos, video, declared_data, correction, clarification.
    capabilities: Tuple[str, ...] = ()
    #: True si una corrida gasta dinero. La UI exige confirmación explícita antes de cada una.
    paid: bool = False
    #: Aviso visible en la UI cuando el motor NO es una reconstrucción real (p. ej. el fixture).
    notice: str = ""

    def enabled(self) -> bool:
        """Si aparece en el catálogo. Se evalúa en cada consulta, no al importar."""
        return True

    def model(self) -> str:
        return ""

    def default_params(self) -> Dict[str, Any]:
        return {}

    def availability(self) -> Availability:
        return Availability(AVAILABLE)

    def reconstruct(self, request: EngineRequest) -> EngineResult:     # pragma: no cover
        raise NotImplementedError

    def describe(self) -> Dict[str, Any]:
        disp = self.availability()
        return {"engine_id": self.engine_id, "name": self.name, "version": self.version,
                "provider": self.provider, "model": self.model(), "pipeline": self.pipeline,
                "capabilities": list(self.capabilities), "paid": self.paid, "notice": self.notice,
                "params": self.default_params(), "status": disp.status, "reason": disp.reason,
                "detail": disp.detail}
