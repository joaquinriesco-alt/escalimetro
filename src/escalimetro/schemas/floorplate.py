"""Floorplate JSON schema — versión 0.2.0 (lee 0.1.1).

Principios:
- Toda coordenada se expresa en píxeles de la imagen fuente (origen arriba-izquierda,
  y hacia abajo) Y en metros (origen abajo-izquierda del bbox del perímetro, y hacia arriba).
  Sólo se serializan los píxeles + la escala; los metros se derivan (`to_m`).
- Cada elemento lleva `confidence` (0..1) y `provenance` (de dónde salió).
- Nada se inventa: si un elemento no se pudo inferir, va en `unknowns`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "0.2.0"   # 0.2.0 (E03): shell semántico — entrance_candidates, primary_entrance, daylight_segments,
                           #   exterior_facade_segments, column_candidates, shell_readiness, north_arrow. Lee 0.1.1 con defaults.
COMPATIBLE_VERSIONS = ("0.1.1", "0.2.0")

Point = Tuple[float, float]
Ring = List[Point]


class Provenance(str, Enum):
    """De dónde proviene un elemento. Nunca 'generated'."""
    MANUAL = "manual"                   # anotación / override humano
    KNOWN_AREA = "known_area"           # derivado de superficie publicada
    CV_SEGMENTATION = "cv_segmentation" # OpenCV clásico
    ML_SEGMENTATION = "ml_segmentation" # SAM2 u otro modelo
    VLM = "vlm"                         # modelo de visión-lenguaje
    CV_HEURISTIC = "cv_heuristic"       # heurística geométrica sobre la imagen
    DERIVED = "derived"                 # calculado a partir de otros elementos
    UNKNOWN = "unknown"


class Status(str, Enum):
    CONFIRMED = "confirmed"             # confirmado por humano
    INFERRED = "inferred"               # inferido, no confirmado
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNKNOWN = "unknown"


@dataclass
class Meta:
    confidence: float = 0.0
    provenance: str = Provenance.UNKNOWN.value
    status: str = Status.UNKNOWN.value
    notes: str = ""

    def __post_init__(self):
        assert 0.0 <= self.confidence <= 1.0, "confidence fuera de [0,1]"


@dataclass
class SourceImage:
    path: str
    width_px: int
    height_px: int
    sha256: str = ""
    dpi: Optional[float] = None


@dataclass
class CoordinateSystem:
    """px: origen arriba-izquierda, y hacia abajo (convención imagen).
    m: origen abajo-izquierda del bbox del perímetro, y hacia arriba (convención plano)."""
    units: str = "px"
    origin: str = "top_left"
    y_axis: str = "down"
    note: str = "Convertir a metros con scale.px_per_m; ver Floorplate.to_m()"


@dataclass
class Scale:
    px_per_m: Optional[float]
    method: str                       # published_area_inferred | known_area | scale_bar | dimension_text | manual | unknown
    reference_area_m2: Optional[float] = None
    meta: Meta = field(default_factory=Meta)
    # E16.8 — de qué región del espacio habla cada lado de la división, y si eso autoriza la
    # inferencia. Sin estos tres campos, `px_per_m` es un número sin sujeto.
    pixel_region: str = "unknown_region"      # ver area_semantics.PIXEL_REGIONS
    area_kind: str = "unknown"                # ver area_semantics.AREA_KINDS
    semantic_validity: str = "SCALE_NOT_EVALUATED"   # ver area_semantics
    semantic_reason: str = ""
    # Valor que HABRÍA salido si se ignorara la semántica. Se guarda por trazabilidad —para poder
    # comparar contra corridas históricas— y NO debe consumirse como escala: cuando este campo está
    # poblado, `px_per_m` es None a propósito.
    rejected_px_per_m: Optional[float] = None


@dataclass
class Polygon:
    ring: Ring                        # exterior, cerrado implícitamente
    meta: Meta = field(default_factory=Meta)


@dataclass
class Perimeter:
    ring: Ring
    raw_ring: Ring = field(default_factory=list)   # contorno sin simplificar
    meta: Meta = field(default_factory=Meta)


@dataclass
class CoreGroup:
    """E16.13.1 — identidad semántica de un núcleo repartido en varias regiones.

    Un núcleo puede ocupar N regiones separadas por circulación, y el esquema las guarda como N
    entradas `Core`. Sin este bloque, un consumidor no puede distinguir UN núcleo de tres regiones de
    TRES núcleos independientes: son dos afirmaciones arquitectónicas distintas. El vínculo va en
    campos, no en `meta.notes`, para que sobreviva a la serialización y sea legible por máquina."""
    semantic_core_id: str = ""        # mismo id ⇒ misma entidad semántica
    component_index: int = 0
    component_count: int = 1
    contract_version: str = ""        # bajo qué representación se produjo
    candidate_status: str = ""        # estado del CONJUNTO, no de esta región


@dataclass
class Core:
    ring: Ring                        # polígono de UNA región del núcleo
    kind: str = "core"                # core | shaft | stairs | wc
    meta: Meta = field(default_factory=Meta)
    #: None = registro anterior a E16.13.1, cuando un núcleo era necesariamente una sola región
    group: Optional[CoreGroup] = None


@dataclass
class Column:
    center: Point
    size_px: float                    # lado aproximado
    shape: str = "square"             # square | round | rect | unknown
    meta: Meta = field(default_factory=Meta)


@dataclass
class Entrance:
    point: Point                      # punto sobre el perímetro
    width_px: Optional[float] = None
    kind: str = "main"                # main | secondary | emergency
    meta: Meta = field(default_factory=Meta)


@dataclass
class Window:
    start: Point
    end: Point
    meta: Meta = field(default_factory=Meta)


@dataclass
class FacadeSegment:
    """Un lado del perímetro simplificado, clasificado."""
    index: int
    start: Point
    end: Point
    kind: str                         # facade | party_wall | core_wall | corridor | unknown
    meta: Meta = field(default_factory=Meta)


@dataclass
class FixedElement:
    ring: Ring
    kind: str                         # wc | kitchen | shaft | stairs | other
    label: str = ""
    meta: Meta = field(default_factory=Meta)


@dataclass
class Unknown:
    element: str
    reason: str


# ---- 0.2.0: shell semántico ------------------------------------------------
@dataclass
class EntranceCandidate:
    point: Point
    kind: str                         # primary | secondary | unknown
    confidence: float
    evidence: List[str] = field(default_factory=list)
    width_px: Optional[float] = None
    segment_index: Optional[int] = None
    status: str = Status.NEEDS_CONFIRMATION.value
    provenance: str = Provenance.CV_HEURISTIC.value


@dataclass
class DaylightSegment:
    index: int
    start: Point
    end: Point
    classification: str               # confirmed_glazing | likely_glazing | exterior_unknown | opaque | unknown
    confidence: float
    daylight_priority: float          # 0..1
    evidence: List[str] = field(default_factory=list)
    status: str = Status.NEEDS_CONFIRMATION.value
    provenance: str = Provenance.CV_HEURISTIC.value


@dataclass
class ColumnCandidate:
    center: Point
    size_px: float
    confidence: float
    evidence: List[str] = field(default_factory=list)
    status: str = Status.NEEDS_CONFIRMATION.value
    provenance: str = Provenance.CV_HEURISTIC.value


@dataclass
class NorthArrow:
    detected: bool = False
    angle_deg: Optional[float] = None   # 0 = norte hacia arriba de la imagen, sentido horario
    meta: Meta = field(default_factory=Meta)


@dataclass
class ShellReadiness:
    geometry_ready: bool = False
    entrance_ready: bool = False
    columns_ready: bool = False
    daylight_ready: bool = False
    requires_confirmation: List[str] = field(default_factory=list)
    ready_for_layout: bool = False
    notes: str = ""


@dataclass
class Floorplate:
    schema_version: str
    case_id: str
    unit_label: str                   # ej. "Oficina 403"
    source_image: SourceImage
    coordinate_system: CoordinateSystem
    scale: Scale
    perimeter: Perimeter
    holes: List[Polygon] = field(default_factory=list)
    core: List[Core] = field(default_factory=list)
    columns: List[Column] = field(default_factory=list)
    entrances: List[Entrance] = field(default_factory=list)
    windows: List[Window] = field(default_factory=list)
    facade_segments: List[FacadeSegment] = field(default_factory=list)
    fixed_elements: List[FixedElement] = field(default_factory=list)
    area_m2: Optional[float] = None
    area_px2: Optional[float] = None
    area_meta: Meta = field(default_factory=Meta)
    published_area_m2: Optional[float] = None       # cifra comercial tal como se publicó; NO es área geométrica
    published_area_kind: str = "unknown"            # useful | rentable | total | unknown
    target_localization: str = "unknown"            # automatic | assisted | manual | unknown
    unknowns: List[Unknown] = field(default_factory=list)
    # 0.2.0 shell semántico (todo opcional; ausente en 0.1.1)
    entrance_candidates: List[EntranceCandidate] = field(default_factory=list)
    primary_entrance: Optional[EntranceCandidate] = None
    exterior_facade_segments: List[int] = field(default_factory=list)      # índices de facade_segments con kind=facade
    daylight_segments: List[DaylightSegment] = field(default_factory=list)
    column_candidates: List[ColumnCandidate] = field(default_factory=list)
    north_arrow: NorthArrow = field(default_factory=NorthArrow)
    shell_readiness: ShellReadiness = field(default_factory=ShellReadiness)
    pipeline: Dict[str, Any] = field(default_factory=dict)   # versión, adapters, parámetros

    # ---- serialización ------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Floorplate":
        if d.get("schema_version") not in COMPATIBLE_VERSIONS:
            raise ValueError(f"schema_version {d.get('schema_version')} no compatible con {COMPATIBLE_VERSIONS}")

        def m(x):
            return Meta(**x) if x else Meta()

        def tup(r):
            return [tuple(p) for p in r]

        return cls(
            schema_version=d["schema_version"],
            case_id=d["case_id"],
            unit_label=d["unit_label"],
            source_image=SourceImage(**d["source_image"]),
            coordinate_system=CoordinateSystem(**d["coordinate_system"]),
            scale=Scale(px_per_m=d["scale"]["px_per_m"], method=d["scale"]["method"],
                        reference_area_m2=d["scale"].get("reference_area_m2"), meta=m(d["scale"].get("meta")),
                        pixel_region=d["scale"].get("pixel_region", "unknown_region"),
                        area_kind=d["scale"].get("area_kind", "unknown"),
                        semantic_validity=d["scale"].get("semantic_validity", "SCALE_NOT_EVALUATED"),
                        semantic_reason=d["scale"].get("semantic_reason", ""),
                        rejected_px_per_m=d["scale"].get("rejected_px_per_m")),
            perimeter=Perimeter(ring=tup(d["perimeter"]["ring"]), raw_ring=tup(d["perimeter"].get("raw_ring", [])),
                                meta=m(d["perimeter"].get("meta"))),
            holes=[Polygon(ring=tup(h["ring"]), meta=m(h.get("meta"))) for h in d.get("holes", [])],
            core=[Core(ring=tup(c["ring"]), kind=c.get("kind", "core"), meta=m(c.get("meta")),
                       group=(CoreGroup(**c["group"]) if c.get("group") else None))
                  for c in d.get("core", [])],
            columns=[Column(center=tuple(c["center"]), size_px=c["size_px"], shape=c.get("shape", "unknown"),
                            meta=m(c.get("meta"))) for c in d.get("columns", [])],
            entrances=[Entrance(point=tuple(e["point"]), width_px=e.get("width_px"), kind=e.get("kind", "main"),
                                meta=m(e.get("meta"))) for e in d.get("entrances", [])],
            windows=[Window(start=tuple(w["start"]), end=tuple(w["end"]), meta=m(w.get("meta"))) for w in d.get("windows", [])],
            facade_segments=[FacadeSegment(index=s["index"], start=tuple(s["start"]), end=tuple(s["end"]), kind=s["kind"],
                                           meta=m(s.get("meta"))) for s in d.get("facade_segments", [])],
            fixed_elements=[FixedElement(ring=tup(x["ring"]), kind=x["kind"], label=x.get("label", ""), meta=m(x.get("meta")))
                            for x in d.get("fixed_elements", [])],
            area_m2=d.get("area_m2"), area_px2=d.get("area_px2"), area_meta=m(d.get("area_meta")),
            published_area_m2=d.get("published_area_m2"), published_area_kind=d.get("published_area_kind", "unknown"),
            target_localization=d.get("target_localization", "unknown"),
            unknowns=[Unknown(**u) for u in d.get("unknowns", [])],
            pipeline=d.get("pipeline", {}),
            entrance_candidates=[EntranceCandidate(**{**e, "point": tuple(e["point"])}) for e in d.get("entrance_candidates", [])],
            primary_entrance=EntranceCandidate(**{**d["primary_entrance"], "point": tuple(d["primary_entrance"]["point"])})
            if d.get("primary_entrance") else None,
            exterior_facade_segments=list(d.get("exterior_facade_segments", [])),
            daylight_segments=[DaylightSegment(**{**x, "start": tuple(x["start"]), "end": tuple(x["end"])}) for x in d.get("daylight_segments", [])],
            column_candidates=[ColumnCandidate(**{**c, "center": tuple(c["center"])}) for c in d.get("column_candidates", [])],
            north_arrow=NorthArrow(detected=d.get("north_arrow", {}).get("detected", False), angle_deg=d.get("north_arrow", {}).get("angle_deg"),
                                   meta=m(d.get("north_arrow", {}).get("meta"))),
            shell_readiness=ShellReadiness(**d["shell_readiness"]) if d.get("shell_readiness") else ShellReadiness(),
        )

    @classmethod
    def load(cls, path: str) -> "Floorplate":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    # ---- conversión a metros -----------------------------------------
    def to_m(self, p: Point) -> Point:
        """px (origen arriba-izq, y abajo) → metros (origen abajo-izq del bbox del perímetro, y arriba)."""
        if not self.scale.px_per_m:
            raise ValueError("sin escala")
        xs = [q[0] for q in self.perimeter.ring]
        ys = [q[1] for q in self.perimeter.ring]
        x0, y1 = min(xs), max(ys)
        return ((p[0] - x0) / self.scale.px_per_m, (y1 - p[1]) / self.scale.px_per_m)

    def perimeter_m(self) -> Ring:
        return [self.to_m(p) for p in self.perimeter.ring]


def json_schema() -> Dict[str, Any]:
    """JSON Schema (draft-07) mínimo para validación externa. Se mantiene a mano y se testea
    contra la serialización de un Floorplate real (tests/test_schema.py)."""
    meta = {"type": "object", "required": ["confidence", "provenance", "status"],
            "properties": {"confidence": {"type": "number", "minimum": 0, "maximum": 1},
                           "provenance": {"enum": [p.value for p in Provenance]},
                           "status": {"enum": [s.value for s in Status]},
                           "notes": {"type": "string"}}}
    point = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
    ring = {"type": "array", "items": point, "minItems": 3}
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Escalímetro Floorplate", "version": SCHEMA_VERSION, "type": "object",
        "required": ["schema_version", "case_id", "unit_label", "source_image", "coordinate_system",
                     "scale", "perimeter"],
        "properties": {
            "schema_version": {"enum": list(COMPATIBLE_VERSIONS)},
            "case_id": {"type": "string"}, "unit_label": {"type": "string"},
            "source_image": {"type": "object", "required": ["path", "width_px", "height_px"]},
            "coordinate_system": {"type": "object"},
            "scale": {"type": "object", "required": ["px_per_m", "method"],
                      "properties": {"px_per_m": {"type": ["number", "null"]}, "method": {"type": "string"},
                                     "meta": meta}},
            "perimeter": {"type": "object", "required": ["ring"], "properties": {"ring": ring, "meta": meta}},
            "holes": {"type": "array", "items": {"type": "object", "required": ["ring"]}},
            "core": {"type": "array", "items": {"type": "object", "required": ["ring", "meta"]}},
            "columns": {"type": "array", "items": {"type": "object", "required": ["center", "meta"]}},
            "entrances": {"type": "array", "items": {"type": "object", "required": ["point", "meta"]}},
            "windows": {"type": "array", "items": {"type": "object", "required": ["start", "end", "meta"]}},
            "facade_segments": {"type": "array", "items": {"type": "object", "required": ["start", "end", "kind", "meta"]}},
            "fixed_elements": {"type": "array"},
            "area_m2": {"type": ["number", "null"]},
            "published_area_m2": {"type": ["number", "null"]},
            "target_localization": {"enum": ["automatic", "assisted", "manual", "unknown"]},
            "unknowns": {"type": "array", "items": {"type": "object", "required": ["element", "reason"]}},
            "entrance_candidates": {"type": "array", "items": {"type": "object", "required": ["point", "kind", "confidence", "evidence"]}},
            "primary_entrance": {"type": ["object", "null"]},
            "daylight_segments": {"type": "array", "items": {"type": "object", "required": ["start", "end", "classification", "confidence", "daylight_priority", "evidence"],
                                  "properties": {"classification": {"enum": ["confirmed_glazing", "likely_glazing", "exterior_unknown", "opaque", "unknown"]},
                                                 "daylight_priority": {"type": "number", "minimum": 0, "maximum": 1}}}},
            "column_candidates": {"type": "array"},
            "shell_readiness": {"type": "object", "required": ["geometry_ready", "entrance_ready", "columns_ready", "daylight_ready",
                                                               "requires_confirmation", "ready_for_layout"]},
        },
    }
