"""E16.10 — pistas semánticas: qué cree ver un intérprete, y de dónde salió esa creencia.

POR QUÉ EXISTE ESTE TIPO
------------------------
E16.9 midió que un modelo general de visión identifica el núcleo de un plano en dos familias
gráficas distintas, y que el OCR del motor no lo consigue en ninguna de las dos. Pero también midió
el límite: el modelo devuelve un RECUADRO y prosa, no geometría. Un recuadro que ocupa el 28 % de una
planta no es un núcleo; es una pista sobre dónde mirar.

De ahí la regla que este módulo hace estructural:

    SEMANTICS PROPOSES.  DETERMINISTIC GEOMETRY DISPOSES.  ACCEPTANCE CONTRACT VETOES.

Un `SemanticHint` NUNCA es geometría aceptada. Su región se llama `approximate_region` a propósito, y
el productor de geometría la usa para REDUCIR EL ESPACIO DE BÚSQUEDA, no para recortar el resultado.
Si alguien escribe `core_polygon = hint.approximate_region`, el contrato completo se vuelve teatro.

REPRODUCIBILIDAD
----------------
Un intérprete no determinista no puede estar dentro de una corrida reproducible: dos ejecuciones del
mismo motor congelado sobre la misma imagen darían resultados distintos, y el ciclo de congelamiento
que este proyecto sostiene desde E14 dejaría de significar algo. Por eso la pista se CACHEA como
artefacto, con la identidad de lo que la produjo (imagen, proveedor, modelo, versión de prompt), y el
pipeline consume el artefacto, no el proveedor. Sin artefacto y sin proveedor: `SEMANTIC_HINT_UNAVAILABLE`.
Nunca un núcleo inventado por una heurística de reemplazo silenciosa.

PROCEDENCIA HONESTA
-------------------
`provider` y `model` admiten `UNKNOWN`, y eso es preferible a una procedencia falsa: las pistas de
desarrollo de este ciclo salieron de un spike, no del runtime productivo, y su artefacto lo dice.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "1.0.0"

# --- clases de pista ---------------------------------------------------------------------------
KIND_CORE = "core"
KINDS = (KIND_CORE,)

# --- procedencia -------------------------------------------------------------------------------
PROV_VLM = "VLM"
PROV_OCR = "OCR"
PROV_MANUAL_QA = "MANUAL_QA"     # herramienta interna trazable; no es parte del flujo del cliente
PROVENANCES = (PROV_VLM, PROV_OCR, PROV_MANUAL_QA)

UNKNOWN = "UNKNOWN"

# --- estados -----------------------------------------------------------------------------------
HINT_AVAILABLE = "SEMANTIC_HINT_AVAILABLE"
HINT_UNAVAILABLE = "SEMANTIC_HINT_UNAVAILABLE"

CONFIDENCES = ("low", "medium", "high")


class InvalidSemanticHint(ValueError):
    """Un dict cualquiera no puede hacerse pasar por una pista válida."""


class SemanticHintUnavailable(RuntimeError):
    """No hay artefacto cacheado ni proveedor disponible. No se inventa un núcleo."""


@dataclass(frozen=True)
class SemanticHint:
    """Lo que un intérprete CREE ver, dónde aproximadamente, y por qué.

    `approximate_region` es (x0, y0, x1, y1) en píxeles de la imagen fuente, o un polígono
    aproximado. Está marcado como aproximado en el nombre, en el docstring y en el artefacto:
    ninguna capa aguas abajo puede tratarlo como geometría aceptada."""
    kind: str
    approximate_region: Tuple[float, float, float, float]
    confidence: str
    semantic_evidence: str
    provenance: str
    provider: str = UNKNOWN
    model: str = UNKNOWN
    schema_version: str = SCHEMA_VERSION
    source_image_sha256: str = ""
    created_at: str = ""
    raw_response_sha256: str = ""
    approximate_polygon: Optional[List[Tuple[float, float]]] = None
    notes: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise InvalidSemanticHint(f"kind desconocido: {self.kind!r}")
        if self.provenance not in PROVENANCES:
            raise InvalidSemanticHint(f"provenance desconocida: {self.provenance!r}")
        if self.confidence not in CONFIDENCES:
            raise InvalidSemanticHint(f"confidence debe ser {CONFIDENCES}: {self.confidence!r}")
        r = self.approximate_region
        if not (isinstance(r, (tuple, list)) and len(r) == 4):
            raise InvalidSemanticHint("approximate_region debe ser (x0, y0, x1, y1)")
        if not (r[0] < r[2] and r[1] < r[3]):
            raise InvalidSemanticHint("approximate_region degenerada")
        if not self.semantic_evidence.strip():
            raise InvalidSemanticHint("una pista sin evidencia declarada no es auditable")
        if len(self.source_image_sha256) != 64:
            raise InvalidSemanticHint("la pista debe estar atada a la imagen que la produjo")

    # -- serialización ---------------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["approximate_region"] = list(self.approximate_region)
        d["_warning"] = ("approximate_region es una PISTA, no geometría aceptada. El polígono lo "
                         "produce código determinista y lo aprueba el contrato de aceptación.")
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SemanticHint":
        if not isinstance(d, dict):
            raise InvalidSemanticHint("se esperaba un objeto")
        campos = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in d.items() if k in campos}
        faltan = {"kind", "approximate_region", "confidence", "semantic_evidence", "provenance",
                  "source_image_sha256"} - set(data)
        if faltan:
            raise InvalidSemanticHint(f"faltan campos obligatorios: {sorted(faltan)}")
        data["approximate_region"] = tuple(data["approximate_region"])
        if data.get("approximate_polygon"):
            data["approximate_polygon"] = [tuple(p) for p in data["approximate_polygon"]]
        return cls(**data)


def image_sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def cache_key(image_sha: str, provider: str, model: str, schema_version: str = SCHEMA_VERSION) -> str:
    """Identidad de una respuesta semántica. Cambiar de proveedor, de modelo o de versión de
    contrato produce OTRA pista: no se reutiliza una cacheada bajo condiciones distintas."""
    raw = f"{image_sha}|{provider}|{model}|{schema_version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_path(case_dir: str, key: str) -> str:
    return os.path.join(case_dir, "semantic", f"hint_{key}.json")


def save_hint(case_dir: str, hint: SemanticHint) -> str:
    key = cache_key(hint.source_image_sha256, hint.provider, hint.model, hint.schema_version)
    p = cache_path(case_dir, key)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(hint.to_dict(), fh, indent=2, ensure_ascii=False)
    return p


def load_hint(case_dir: str, image_path: str, kind: str = KIND_CORE,
              provider: Optional[str] = None, model: Optional[str] = None) -> SemanticHint:
    """Consume el ARTEFACTO, nunca el proveedor. Sin artefacto: SemanticHintUnavailable."""
    sha = image_sha256(image_path)
    d = os.path.join(case_dir, "semantic")
    if not os.path.isdir(d):
        raise SemanticHintUnavailable(f"{HINT_UNAVAILABLE}: no hay pistas cacheadas para este caso")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(d, fn), encoding="utf-8") as fh:
            raw = json.load(fh)
        try:
            h = SemanticHint.from_dict(raw)
        except InvalidSemanticHint:
            continue
        if h.kind != kind or h.source_image_sha256 != sha:
            continue
        if provider and h.provider != provider:
            continue
        if model and h.model != model:
            continue
        return h
    raise SemanticHintUnavailable(
        f"{HINT_UNAVAILABLE}: ninguna pista '{kind}' cacheada corresponde a esta imagen "
        f"(sha256 {sha[:12]}…). No se infiere un núcleo sin evidencia semántica")
