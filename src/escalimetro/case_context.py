"""E15 — contrato genérico de caso.

El motor de layouts no debe saber que la oficina es la 403, que mide 543 m² ni que el aviso lo
publicó GPS Property. Eso son **datos del caso**.

E15.1 — este módulo representa **CASE INPUT**, y nada más. Un veredicto de fit es evidencia
computada y vive en `fit_evidence.py`: `CaseContext` no lo transporta ni tiene métodos que devuelvan
factibilidad o robustez como si fueran atributos del inmueble. La escala sí sigue aquí, pero con su
naturaleza declarada: `published_area_m2` es SOURCE FACT, `scale_px_per_m` es DERIVED GEOMETRY y
`scale_confidence` es DERIVED EVIDENCE. Ver docs/E15_1_DATA_LINEAGE.md. Este módulo es el único lugar donde esos datos se
leen, y el único que los reparte al resto del pipeline.

Dirección de datos, en un solo sentido:

    case.json + floorplate.json  →  CaseContext  →  layout / presentation / nombres de artefactos

Ningún módulo aguas abajo —`board.py`, `engine.py`, `run.py`— puede inventar metadatos del inmueble.
Si un dato no existe, el valor es `None` y quien lo necesite decide: omitirlo, mostrarlo como
desconocido, o bloquear esa etapa con un error descriptivo. **Nunca un valor por defecto de otro
caso.**

Campos requeridos y opcionales (§30, auditado):

    REQUERIDOS   case_id, unit_label
    OPCIONALES   source_name, display_name, published_area_m2, published_area_kind,
                 scale_px_per_m, scale_status, scale_confidence, sibling_units

El floorplate NO es requerido para construir un contexto: se puede tener metadatos de un caso antes
de normalizarlo, y los tests de contrato lo necesitan sin geometría. Las etapas que sí lo necesiten
llaman a `require_floorplate()`, que falla con un mensaje concreto. Esa es la corrección al criterio
inicial de §30: exigir el floorplate en la construcción impediría verificar el contrato sin un
inmueble."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class MissingCaseMetadata(Exception):
    """Un dato del caso que esta etapa necesita no existe. Nunca se sustituye por el de otro caso."""


DERIVED_EVIDENCE_NOT_ALLOWED = "DERIVED_EVIDENCE_NOT_ALLOWED"
COMPUTED_RESULT_NOT_ALLOWED = "COMPUTED_RESULT_NOT_ALLOWED"
UNKNOWN_CASE_FIELD = "UNKNOWN_CASE_FIELD"

#: E15.2 — lo único que puede declararse en case.json. Cualquier otra cosa se rechaza al cargar.
from .area_semantics import SCALE_INCOMPATIBLE_REGION

CASE_INPUT_FIELDS = {
    "case_id", "image", "image_note", "unit_label", "display_name", "source_name",
    "known_area_m2", "known_area_kind", "known_area_region", "sibling_units",
    "overrides", "vision", "segmentation", "simplify_eps_frac", "mask_open_px",
    "drawing_scope",          # E16.5 — hecho de la fuente: multi_unit | whole_shell
    # E24 §12 — hecho de INTAKE, no inferencia: ¿el dibujo viene libre de layout previo?
    # true | false | "unknown". Es la ÚNICA fuente de `not_layout_dominated` en ShellInputV1.
    # Prohibido derivarlo de la imagen, de un VLM o de SemanticHint.
    "shell_declared_clean",
    # E24 §14 — confirmación humana de escala: dos puntos + la distancia real entre ellos.
    # {"method": "two_point_distance", "point_a_px": [x,y], "point_b_px": [x,y], "real_distance_m": n}
    # o, vía secundaria, {"method": "px_per_m", "px_per_m": n}. Es un dato declarado por una persona,
    # no evidencia derivada de la geometría: por eso vive aquí y no en DERIVED_EVIDENCE_FIELDS.
    "scale_confirmation",
}
#: valores derivados de la geometría: se leen del floorplate, nunca se declaran a mano
DERIVED_EVIDENCE_FIELDS = {"scale_confidence", "scale_px_per_m", "scale_status", "scale",
                           "scale_semantic_validity",   # E16.8: la valida el motor, no el caso
                           "usable_area_m2", "area_m2"}
#: resultados de ejecución: se leen de los artefactos computados
COMPUTED_RESULT_FIELDS = {"fit_verdict", "fit", "technical_fit", "robustness", "robustness_result",
                          "recommendation", "hard_violations", "program_completeness",
                          "critic_score", "layout_quality", "ai_review", "broker_ready",
                          "commercial_readiness", "gate", "gates", "classification", "verdict",
                          "score", "seats", "collisions"}

MISSING_PUBLISHED_AREA = "MISSING_PUBLISHED_AREA"
MISSING_UNIT_LABEL = "MISSING_UNIT_LABEL"
MISSING_CASE_METADATA = "MISSING_CASE_METADATA"
MISSING_FLOORPLATE = "MISSING_FLOORPLATE"
SEMANTICS_ARTIFACT_MISSING = "SEMANTICS_ARTIFACT_MISSING"

UNKNOWN_AREA_LABEL = "superficie no publicada"
UNKNOWN_SOURCE_LABEL = "fuente no especificada"


def unit_slug(unit_label: str) -> str:
    """Identificador corto y estable derivado del rótulo: 'Oficina 403' → '403'.

    Si el rótulo no tiene dígitos se usa el texto normalizado ('Piso Ejecutivo' → 'PISO_EJECUTIVO'),
    de modo que el resultado siga siendo determinista y legible por un humano."""
    if not unit_label:
        raise MissingCaseMetadata(f"{MISSING_UNIT_LABEL}: no se puede derivar un identificador sin rótulo")
    digits = re.findall(r"\d+", unit_label)
    if digits:
        return digits[-1]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", unit_label.strip()).strip("_").upper()
    return slug or "UNIT"


@dataclass
class CaseArtifacts:
    """Nombres de artefactos derivados del caso (§24). Deja de construirse rutas a mano en ocho archivos.

    Los nombres nuevos son neutrales. Para artefactos históricos existe un fallback explícito: se
    busca primero el nombre genérico, después el que produjo el pipeline de ese caso. El fallback es
    una lista, no una cadena de `try`, para que quede auditable qué se intentó."""
    case_dir: str
    slug: str

    @property
    def outputs_dir(self) -> str:
        return os.path.join(self.case_dir, "outputs")

    @property
    def floorplate(self) -> str:
        return os.path.join(self.outputs_dir, "floorplate.json")

    @property
    def source_image(self) -> str:
        return os.path.join(self.case_dir, "original.png")

    def layouts_dir(self, sub: str = "") -> str:
        return os.path.join(self.case_dir, "layouts", sub) if sub else os.path.join(self.case_dir, "layouts")

    @property
    def semantics_png_candidates(self) -> List[str]:
        """Nombres posibles del render semántico, del genérico al histórico."""
        return [os.path.join(self.outputs_dir, "shell_semantics.png"),
                os.path.join(self.outputs_dir, f"shell_semantics_{self.slug}.png")]

    def resolve_semantics_png(self) -> Optional[str]:
        for p in self.semantics_png_candidates:
            if os.path.exists(p):
                return p
        return None

    @property
    def robustness_png(self) -> str:
        return os.path.join(self.layouts_dir("E06"), "fit_robustness.png")

    @property
    def board_png(self) -> str:
        return os.path.join(self.layouts_dir("E07"), "ESCALIMETRO_PRESENTATION_STANDARD_01.png")


@dataclass
class CaseContext:
    # --- requeridos --------------------------------------------------------------------------------
    case_id: str
    unit_label: str
    # --- opcionales --------------------------------------------------------------------------------
    case_dir: str = ""
    source_name: Optional[str] = None
    display_name: Optional[str] = None
    published_area_m2: Optional[float] = None
    published_area_kind: str = "unknown"
    scale_px_per_m: Optional[float] = None
    scale_status: Optional[str] = None
    scale_confidence: Optional[str] = None
    scale_semantic_validity: Optional[str] = None   # E16.8, DERIVED_EVIDENCE
    sibling_units: Dict = field(default_factory=dict)

    # ----------------------------------------------------------------------------------------------
    def __post_init__(self):
        if not self.case_id:
            raise MissingCaseMetadata(f"{MISSING_CASE_METADATA}: falta case_id")
        if not self.unit_label:
            raise MissingCaseMetadata(f"{MISSING_UNIT_LABEL}: falta unit_label")

    # --- identidad ---------------------------------------------------------------------------------
    @property
    def slug(self) -> str:
        return unit_slug(self.unit_label)

    @property
    def artifacts(self) -> CaseArtifacts:
        return CaseArtifacts(self.case_dir, self.slug)

    def layout_id(self, alt: str = "", name: str = "", suffix: str = "") -> str:
        """'OFFICE_403_A_EFICIENTE'. Determinista, estable y legible; derivado del rótulo, no del
        case_id, que sería innecesariamente largo."""
        parts = ["OFFICE", self.slug] + [p for p in (alt, name, suffix) if p]
        return "_".join(str(p) for p in parts)

    def unit_title(self) -> str:
        """'OFICINA 403' — sólo el rótulo, en mayúsculas. Es lo que va en el pie de cada planta."""
        return (self.display_name or self.unit_label).upper()

    def title(self) -> str:
        """'OFICINA 403 · GPS PROPERTY'. Sin fuente declarada: sólo el rótulo, sin inventar una."""
        head = self.unit_title()
        return f"{head} · {self.source_name.upper()}" if self.source_name else head

    def source_label(self) -> str:
        return self.source_name or UNKNOWN_SOURCE_LABEL

    def published_area_label(self) -> str:
        """'543 m²' o el texto de desconocido. NUNCA el área de otro caso."""
        if self.published_area_m2 is None:
            return UNKNOWN_AREA_LABEL
        v = float(self.published_area_m2)
        return f"{v:.0f} m²" if abs(v - round(v)) < 1e-6 else f"{v:.1f} m²"

    def scale_label(self) -> str:
        # E16.8 — "no validada" y "desconocida" no son lo mismo, y presentarlas igual borra
        # justamente la información que costó un ciclo producir.
        if self.scale_semantic_validity == SCALE_INCOMPATIBLE_REGION:
            return "escala no validada"
        if self.scale_px_per_m is None:
            return "escala desconocida"
        return f"{self.scale_px_per_m:.2f}".replace(".", ",") + " px/m"

    # --- requisitos por etapa ----------------------------------------------------------------------
    def require_published_area(self, what: str = "esta etapa") -> float:
        if self.published_area_m2 is None:
            raise MissingCaseMetadata(
                f"{MISSING_PUBLISHED_AREA}: {what} necesita published_area_m2 y el caso "
                f"'{self.case_id}' no la declara. No se sustituye por el área de otro caso.")
        return float(self.published_area_m2)

    def require_floorplate(self) -> str:
        p = self.artifacts.floorplate
        if not self.case_dir or not os.path.exists(p):
            raise MissingCaseMetadata(f"{MISSING_FLOORPLATE}: no existe {p}")
        return p

    def to_dict(self) -> Dict:
        return {"case_id": self.case_id, "unit_label": self.unit_label, "slug": self.slug,
                "display_name": self.display_name, "source_name": self.source_name,
                "published_area_m2": self.published_area_m2,
                "published_area_kind": self.published_area_kind,
                "scale_px_per_m": self.scale_px_per_m, "scale_status": self.scale_status,
                "scale_confidence": self.scale_confidence,
                "scale_semantic_validity": self.scale_semantic_validity,
                "unit_title": self.unit_title(), "title": self.title(), "published_area_label": self.published_area_label(),
                "layout_id_example": self.layout_id("A", "EJEMPLO")}


# ---------------------------------------------------------------------------------------------------
# constructores — un solo camino de datos
# ---------------------------------------------------------------------------------------------------
def validate_case_input(case: Dict, where: str = "case.json") -> Dict:
    """E15.2 — `case.json` es ENTRADA. Un valor derivado o un resultado se rechazan al cargar, no se
    ignoran en silencio: si alguien los escribe, es que cree que sirven para algo.

    `scale_confidence` está en la lista de derivados. Es una evaluación de la geometría —sale de
    `floorplate.json → scale.meta.confidence`— y declararla a mano permitiría afirmar que la escala
    es fiable sin haberla medido."""
    keys = {k for k in case if not k.startswith("_")}
    bad_derived = sorted(keys & DERIVED_EVIDENCE_FIELDS)
    if bad_derived:
        raise MissingCaseMetadata(
            f"{DERIVED_EVIDENCE_NOT_ALLOWED}: {where} declara {bad_derived}. Son valores DERIVADOS de "
            f"la geometría y se leen de outputs/floorplate.json; no se declaran como entrada.")
    bad_computed = sorted(keys & COMPUTED_RESULT_FIELDS)
    if bad_computed:
        raise MissingCaseMetadata(
            f"{COMPUTED_RESULT_NOT_ALLOWED}: {where} declara {bad_computed}. Son RESULTADOS de "
            f"ejecución y se leen de los artefactos computados; no se declaran como entrada.")
    unknown = sorted(keys - CASE_INPUT_FIELDS)
    if unknown:
        raise MissingCaseMetadata(
            f"{UNKNOWN_CASE_FIELD}: {where} declara {unknown}, que no están en el contrato de "
            f"entrada. Si es un hecho del inmueble, agrégalo a CASE_INPUT_FIELDS; si es un resultado, "
            f"no va aquí.")
    return case


def _confidence_label(scale: Dict) -> Optional[str]:
    """Etiqueta de confianza de escala. Es DERIVED_EVIDENCE: describe cuánto se puede confiar en una
    medición, y por eso no puede declararse como entrada.

    E15.3 — la clasificación NO es de este módulo. Es la del pipeline, que ya existía antes de E15.2
    en `layout/shell_adapter.py` (método y estado de la escala, no un umbral numérico) y cuyo
    vocabulario está fijado por el esquema de `layout/e06/scale.py` (`enum: LOW | MEDIUM | HIGH`).
    Aquí sólo se reusa.

    E15.2 había introducido umbrales numéricos `< 0.5 → LOW`, `< 0.8 → MEDIUM`, `HIGH` en otro caso.
    Eran inventados: no existían en ninguna parte del motor. Un ciclo que no debía cambiar la lógica
    de escala no puede definir cuándo una medición pasa a ser MEDIUM o HIGH. Se eliminaron."""
    if not isinstance(scale, dict) or not scale:
        return None                       # un número suelto ya no clasifica nada: hace falta el método
    # E16.8 — una escala rechazada por semántica no tiene grado de confianza: no hay medición que
    # calificar. Devolver MEDIUM aquí la presentaría como una escala peor en vez de como ninguna.
    if scale.get("semantic_validity") == SCALE_INCOMPATIBLE_REGION:
        return None
    method = scale.get("method")
    status = (scale.get("meta") or {}).get("status")
    if method is None and status is None:
        return None
    if method == "published_area_inferred":                # misma regla que shell_adapter.py:34
        return "LOW"
    return "HIGH" if status == "confirmed" else "MEDIUM"


def _read_json(path: str) -> Optional[Dict]:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def from_case_dir(case_dir: str) -> CaseContext:
    """Fuente de verdad: `case.json` para la identidad, `outputs/floorplate.json` para lo derivado.

    El floorplate manda en área y escala cuando existe, porque es lo que el motor consumió de verdad;
    `case.json` es lo que el humano declaró. Si difieren, gana lo que se usó."""
    case = _read_json(os.path.join(case_dir, "case.json"))
    if case is None:
        raise MissingCaseMetadata(f"{MISSING_CASE_METADATA}: no existe {case_dir}/case.json")
    validate_case_input(case, os.path.join(case_dir, "case.json"))
    fp = _read_json(os.path.join(case_dir, "outputs", "floorplate.json")) or {}
    scale = fp.get("scale") or {}
    meta = scale.get("meta") or {}
    return CaseContext(
        case_id=case.get("case_id") or "",
        unit_label=fp.get("unit_label") or case.get("unit_label") or "",
        case_dir=case_dir,
        source_name=case.get("source_name"),
        display_name=case.get("display_name"),
        published_area_m2=(fp.get("published_area_m2") if fp.get("published_area_m2") is not None
                           else case.get("known_area_m2")),
        published_area_kind=(fp.get("published_area_kind") or case.get("known_area_kind") or "unknown"),
        scale_px_per_m=scale.get("px_per_m"),
        scale_status=meta.get("status"),
        scale_confidence=_confidence_label(scale),         # DERIVED_EVIDENCE: regla del pipeline
        scale_semantic_validity=scale.get("semantic_validity"),
        sibling_units=case.get("sibling_units") or {},
    )


def from_floorplate(fp, case_dir: str = "", source_name: Optional[str] = None) -> CaseContext:
    """Contexto a partir de un Floorplate ya cargado (objeto o dict). Útil cuando el llamador ya lo
    tiene en memoria y no quiere releer el disco."""
    d = fp if isinstance(fp, dict) else {
        "case_id": getattr(fp, "case_id", ""), "unit_label": getattr(fp, "unit_label", ""),
        "published_area_m2": getattr(fp, "published_area_m2", None),
        "published_area_kind": getattr(fp, "published_area_kind", "unknown"),
        "scale": {"px_per_m": getattr(getattr(fp, "scale", None), "px_per_m", None)}}
    if case_dir and os.path.exists(os.path.join(case_dir, "case.json")):
        ctx = from_case_dir(case_dir)
        if source_name:
            ctx.source_name = source_name
        return ctx
    scale = d.get("scale") or {}
    return CaseContext(case_id=d.get("case_id") or "", unit_label=d.get("unit_label") or "",
                       case_dir=case_dir, source_name=source_name,
                       published_area_m2=d.get("published_area_m2"),
                       published_area_kind=d.get("published_area_kind") or "unknown",
                       scale_px_per_m=scale.get("px_per_m") if isinstance(scale, dict) else None)
