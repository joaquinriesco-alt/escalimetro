"""E15.1 — evidencia de fit: RESULTADO COMPUTADO, nunca hecho de entrada.

La frontera que este módulo hace explícita:

    case.json           HECHOS DE ENTRADA        quién es el inmueble
    floorplate.json     GEOMETRÍA DERIVADA       qué midió el pipeline
    E04/E06/E07         EVIDENCIA COMPUTADA      qué encontró el motor      ← esto
    presentación        COMBINA los tres         qué se le muestra a alguien

Un veredicto de fit es lo cuarto que puede pasarle a un inmueble, no lo primero. En E15 quedó dentro
de `case.json`, y eso permitía que la lámina mostrara un resultado viejo sólo porque estaba escrito
en los metadatos. Aquí se lee de los artefactos que el motor produjo, y sólo de ahí.

Dos capas separadas a propósito (§22): la factibilidad técnica y la robustez de escala responden
preguntas distintas y pueden discrepar. Colapsarlas en un solo string fue lo que hizo que E15
mostrara `FIT NO EVALUADO` para la Oficina 401 cuando E14 ya había producido un `TECHNICAL_NO_FIT`
perfectamente válido.

La disposición comercial (§23) NO vive aquí: E13 tiene su propia validación con humanos."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

# --- capa 1: factibilidad técnica ---------------------------------------------------------------
FIT = "FIT"
NO_FIT = "NO_FIT"
TECHNICAL_NOT_EVALUATED = "NOT_EVALUATED"
FAILURE = "FAILURE"

# --- capa 2: robustez de escala (vocabulario de E06, sin inventar uno nuevo) ---------------------
ROBUST_FIT = "ROBUST_FIT"
ROBUST_NO_FIT = "ROBUST_NO_FIT"
ROBUSTNESS_NOT_EVALUATED = "NOT_EVALUATED"

# --- frescura -----------------------------------------------------------------------------------
FRESH = "FRESH"
STALE = "STALE"
LEGACY_VERIFIED = "LEGACY_VERIFIED"
FRESHNESS_NOT_EVALUATED = "NOT_EVALUATED"

LEGACY_REGISTRY = "EVIDENCE_LEGACY.json"
COMPATIBILITY_FILE = os.path.join("cases", "generalization", "ENGINE_COMPATIBILITY.json")


def sha256_file(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load(path: str) -> Optional[Dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                      # noqa: BLE001
        return None


@dataclass
class FitEvidence:
    """Lo que el motor encontró. Ningún campo se declara a mano en un archivo de configuración."""
    technical: str = TECHNICAL_NOT_EVALUATED
    robustness: str = ROBUSTNESS_NOT_EVALUATED
    freshness: str = FRESHNESS_NOT_EVALUATED
    program: Optional[str] = None
    headcount: Optional[int] = None
    program_complete: Optional[bool] = None
    open_seats: Optional[str] = None
    hard_violations: Optional[int] = None
    collisions: Optional[int] = None
    min_scale_factor_exact_fit: Optional[float] = None
    pct_scenarios_exact_fit: Optional[float] = None
    scale_confidence: Optional[str] = None
    primary_constraint: Optional[str] = None
    reason: Optional[str] = None
    recommendation: Optional[str] = None
    primary_uncertainty: Optional[str] = None
    source_artifacts: List[str] = field(default_factory=list)
    stale_reasons: List[str] = field(default_factory=list)
    provenance: Dict = field(default_factory=dict)

    # --- lo que la presentación puede preguntar ---------------------------------------------------
    @property
    def evaluated(self) -> bool:
        return self.technical != TECHNICAL_NOT_EVALUATED or self.robustness != ROBUSTNESS_NOT_EVALUATED

    @property
    def presentable(self) -> bool:
        """Evidencia vieja NO se presenta como actual. Si está STALE, la lámina dice que hay que
        recalcular; no muestra el veredicto de antes."""
        return self.evaluated and self.freshness in (FRESH, LEGACY_VERIFIED)

    def to_dict(self) -> Dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["evaluated"] = self.evaluated
        d["presentable"] = self.presentable
        return d


# ---------------------------------------------------------------------------------------------------
# frescura — mínimo viable, sin base de datos (§11)
# ---------------------------------------------------------------------------------------------------
def engine_compatibility(path: str = COMPATIBILITY_FILE) -> Dict:
    """Declaración explícita de qué baselines producen evidencia todavía vigente (§9).

    No es un hash del repositorio ni un comodín: es una lista de TRANSICIONES declaradas, cada una con
    su diff calculado a la vista. Si el archivo no existe, no se asume compatibilidad con nada."""
    d = _load(path) or {}
    return {"current": d.get("current_baseline"),
            "compatible": set(d.get("compatible_with_current") or []),
            "baselines": d.get("baselines") or {}, "transitions": d.get("transitions") or []}


def engine_is_compatible(producer_baseline: Optional[str], path: str = COMPATIBILITY_FILE) -> (bool, str):
    """¿Una evidencia producida bajo `producer_baseline` sigue vigente bajo el baseline actual?"""
    c = engine_compatibility(path)
    if not c["current"]:
        return False, "no hay declaración de compatibilidad de motor"
    if not producer_baseline:
        return False, "la evidencia no declara con qué baseline de motor se produjo"
    if producer_baseline not in c["compatible"]:
        return False, (f"el baseline productor '{producer_baseline}' no está declarado compatible con "
                       f"'{c['current']}'")
    return True, ""


def current_fingerprint(case_dir: str, program_path: str = "") -> Dict[str, Optional[str]]:
    """Las tres cosas que, si cambian, invalidan un veredicto: la geometría, el programa y el motor."""
    fp = os.path.join(case_dir, "outputs", "floorplate.json")
    eng = os.path.join("cases", "generalization", "E15_1", "GENERIC_ENGINE_BASELINE.json")
    baseline = _load(eng) or _load(os.path.join("cases", "generalization", "E15",
                                                "GENERIC_ENGINE_BASELINE.json")) or {}
    return {"floorplate_sha256": sha256_file(fp),
            "program_sha256": sha256_file(program_path) if program_path else None,
            "engine_hash": baseline.get("engine_hash")}


def _freshness(case_dir: str, artifacts: List[str], recorded: Optional[Dict],
               program_path: str, compat_path: str = COMPATIBILITY_FILE) -> (str, List[str]):
    """Tres caminos, en orden:

    1. El artefacto declara su propia procedencia → se compara y sale FRESH o STALE.
    2. No la declara, pero está en el registro legado del caso y las huellas pinchadas ahí siguen
       coincidiendo → LEGACY_VERIFIED.
    3. Ninguna de las dos → STALE. No hay comodín."""
    now = current_fingerprint(case_dir, program_path)
    if recorded:
        bad = [f"{k} cambió" for k in ("floorplate_sha256", "program_sha256")
               if recorded.get(k) and now.get(k) and recorded[k] != now[k]]
        ok, why = engine_is_compatible(recorded.get("producer_engine_baseline"), compat_path)
        if not ok:
            bad.append(why)
        return (STALE, bad) if bad else (FRESH, [])

    reg = _load(os.path.join(case_dir, "layouts", LEGACY_REGISTRY))
    if not reg:
        return STALE, ["el artefacto no declara procedencia y el caso no tiene registro legado"]
    bad = []
    # E15.2 — la evidencia histórica ya no basta con que floorplate y programa sigan iguales: el
    # baseline que la produjo tiene que estar declarado compatible con el vigente.
    ok, why = engine_is_compatible(reg.get("producer_engine_baseline"), compat_path)
    if not ok:
        bad.append(why)
    pinned = reg.get("pinned_fingerprint", {})
    for k in ("floorplate_sha256", "program_sha256"):
        if pinned.get(k) and now.get(k) and pinned[k] != now[k]:
            bad.append(f"{k} cambió respecto del pinchado en {LEGACY_REGISTRY}")
    declared = {a["path"]: a.get("sha256") for a in reg.get("artifacts", [])}
    for a in artifacts:
        rel = os.path.relpath(a, case_dir).replace(os.sep, "/")
        if rel not in declared:
            bad.append(f"{rel} no está declarado en {LEGACY_REGISTRY}")
        elif declared[rel] and declared[rel] != sha256_file(a):
            bad.append(f"{rel} cambió respecto de su sha256 declarado")
    return (STALE, bad) if bad else (LEGACY_VERIFIED, [])


# ---------------------------------------------------------------------------------------------------
# carga desde artefactos computados
# ---------------------------------------------------------------------------------------------------
def _technical_from_gates(gates: Dict) -> Optional[str]:
    """E07 evaluó las tres alternativas: el gate técnico E1-T es el resultado de factibilidad."""
    st = [v.get("E1-T", {}).get("status") for v in gates.values() if isinstance(v, dict)]
    if not st:
        return None
    return FIT if all(s == "PASS" for s in st) else NO_FIT


def _technical_from_metrics(m: Dict) -> Optional[str]:
    """Sin E07, el layout nominal de E04 dice lo mismo: si ningún candidato es válido, NO_FIT."""
    if not m:
        return None
    status = str(m.get("status") or "")
    if "excep" in status.lower() or "traceback" in status.lower():
        return FAILURE
    comp = (m.get("program_completeness") or {}).get("complete")
    viol = m.get("hard_constraint_violations")
    valid = m.get("valid_candidate_count")
    if comp is True and not viol:
        return FIT
    if comp is False or (valid == 0) or (viol or 0) > 0:
        return NO_FIT
    return None


def load(case_dir: str, program_path: str = "program_templates/office_balanced_48.json") -> FitEvidence:
    """Lee la evidencia de los artefactos que el motor dejó. Si no hay artefactos, NOT_EVALUATED —
    nunca un veredicto declarado a mano."""
    ev = FitEvidence()
    arts: List[str] = []

    # --- capa técnica -----------------------------------------------------------------------------
    p_gates = os.path.join(case_dir, "layouts", "E07", "gates.json")
    gates = _load(p_gates)
    tech = None
    if gates:
        tech = _technical_from_gates(gates)
        arts.append(p_gates)
        pm = os.path.join(case_dir, "layouts", "E07", "alternatives", "A", "metrics.json")
        m = _load(pm) or {}
        if m:
            arts.append(pm)
    else:
        pm = os.path.join(case_dir, "layouts", "OFFICE_BALANCED_001", "metrics.json")
        m = _load(pm) or {}
        if m:
            tech = _technical_from_metrics(m)
            arts.append(pm)
    if tech:
        ev.technical = tech
        comp = (m.get("program_completeness") or {})
        ev.program_complete = comp.get("complete")
        ev.open_seats = comp.get("open_seats")
        ev.hard_violations = m.get("hard_constraint_violations")
        ev.collisions = m.get("collisions")

    # --- capa de robustez -------------------------------------------------------------------------
    p_rob = os.path.join(case_dir, "layouts", "E06", "fit_robustness_report.json")
    rob = _load(p_rob)
    if rob:
        ev.robustness = rob.get("classification") or ROBUSTNESS_NOT_EVALUATED
        ev.min_scale_factor_exact_fit = rob.get("min_scale_factor_exact_fit")
        ev.pct_scenarios_exact_fit = rob.get("pct_scenarios_exact_fit")
        ev.scale_confidence = rob.get("confidence")
        ev.primary_constraint = rob.get("primary_constraint")
        arts.append(p_rob)

    # --- narrativa computada por E06 --------------------------------------------------------------
    p_v = os.path.join(case_dir, "layouts", "E06", "fit_verdict.json")
    v = _load(p_v)
    if v:
        ev.program = v.get("program")
        ev.headcount = v.get("headcount")
        ev.reason = v.get("reason")
        ev.recommendation = v.get("recommendation")
        ev.primary_uncertainty = v.get("primary_uncertainty")
        ev.scale_confidence = ev.scale_confidence or v.get("scale_confidence")
        arts.append(p_v)

    if ev.headcount is None and program_path and os.path.exists(program_path):
        prog = _load(program_path) or {}
        ev.program = ev.program or prog.get("template_id") or os.path.basename(program_path)
        ev.headcount = prog.get("headcount") or prog.get("target_headcount")

    ev.source_artifacts = [a.replace(os.sep, "/") for a in arts]
    if not ev.evaluated:
        ev.freshness = FRESHNESS_NOT_EVALUATED
        return ev
    recorded = (v or {}).get("provenance") or (rob or {}).get("provenance")
    ev.freshness, ev.stale_reasons = _freshness(case_dir, arts, recorded, program_path)
    ev.provenance = {"recorded": recorded, "current": current_fingerprint(case_dir, program_path),
                     "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return ev


# ---------------------------------------------------------------------------------------------------
# formateador de presentación — COPY, no dato (§18)
# ---------------------------------------------------------------------------------------------------
#: Etiqueta de lámina por clasificación de robustez. Es texto comercial, no resultado: vive aquí,
#: en la capa de presentación, y NUNCA en los metadatos del caso.
ROBUSTNESS_LABEL = {
    ROBUST_FIT: "ROBUST WITHIN ASSUMED SCALE RANGE",
    "LIKELY_FIT": "LIKELY WITHIN ASSUMED SCALE RANGE",
    "BORDERLINE": "BORDERLINE WITHIN ASSUMED SCALE RANGE",
    ROBUST_NO_FIT: "NO FIT IN ASSUMED SCALE RANGE",
}
TECHNICAL_LABEL = {FIT: "FIT TÉCNICO", NO_FIT: "SIN FIT TÉCNICO", FAILURE: "FALLO DEL MOTOR"}
NOT_EVALUATED_LABEL = "FIT NO EVALUADO"
STALE_LABEL = "REQUIERE RECÁLCULO"

#: Recomendación de lámina: una línea imperativa por clasificación. La recomendación analítica que
#: computa E06 es más larga y vive en la evidencia; ésta es la que cabe en la barra lateral.
RECOMMENDATION_COPY = {
    ROBUST_FIT: "Confirma una dimensión real antes de comprometer capacidad.",
    "LIKELY_FIT": "Confirma una dimensión real antes de comprometer capacidad.",
    "BORDERLINE": "Confirma una dimensión real antes de comprometer capacidad.",
    ROBUST_NO_FIT: "El programa solicitado no cabe en este shell.",
}
DEFAULT_RECOMMENDATION = "Confirma una dimensión real antes de comprometer capacidad."
NOTE = "Test-fit conceptual de space planning. No constituye proyecto de arquitectura."


@dataclass(frozen=True)
class PresentationFit:
    """E15.2 §14 — lo que la lámina consume. Tipado y construible **sólo** desde una `FitEvidence`.

    Un diccionario con las claves correctas ya no sirve: `build_board` exige esta clase, y el único
    constructor público es `from_evidence`. Cerrar esta puerta importa porque un dict como

        {"technical_fit": "FIT", "fit_label": "ROBUST WITHIN ASSUMED SCALE RANGE"}

    tiene la forma de una conclusión técnica sin ninguna procedencia detrás.

    `_provenance` guarda de qué artefactos salió, y es obligatorio: una instancia sin artefactos y sin
    estado NOT_EVALUATED no se puede construir."""
    unit: str
    published_area_m2: Optional[float]
    technical_fit: str
    robustness: str
    freshness: str
    fit: str
    fit_label: str
    scale: str
    scale_confidence: str
    headcount: Optional[int]
    program: Optional[str]
    recommendation: str
    reason: str
    note: str
    source: str
    _provenance: tuple = ()

    @classmethod
    def from_evidence(cls, ctx, ev: "FitEvidence") -> "PresentationFit":
        """CASE FACTS + COMPUTED EVIDENCE -> copy de lámina. Único camino autorizado."""
        if not isinstance(ev, FitEvidence):
            raise TypeError("PresentationFit sólo se construye desde una FitEvidence: un veredicto es "
                            "un RESULTADO COMPUTADO, no un diccionario escrito a mano")
        unit = ctx.display_name or ctx.unit_label
        base = dict(
            unit=f"{unit} ({ctx.source_name})" if ctx.source_name else unit,
            published_area_m2=ctx.published_area_m2,
            technical_fit=ev.technical, robustness=ev.robustness, freshness=ev.freshness,
            scale="UNCONFIRMED",
            scale_confidence=ev.scale_confidence or (ctx.scale_confidence or "UNKNOWN"),
            headcount=ev.headcount, program=ev.program, note=NOTE,
            source=("evidencia computada: " + ", ".join(ev.source_artifacts)
                    if ev.source_artifacts else "sin artefactos de evidencia para este caso"),
            _provenance=tuple(ev.source_artifacts))
        if not ev.evaluated:
            return cls(fit=TECHNICAL_NOT_EVALUATED, fit_label=NOT_EVALUATED_LABEL,
                       recommendation=DEFAULT_RECOMMENDATION,
                       reason="Ninguna etapa del motor produjo evidencia de fit para este caso.", **base)
        if not ev.presentable:
            return cls(fit=STALE, fit_label=STALE_LABEL, recommendation=DEFAULT_RECOMMENDATION,
                       reason="La evidencia guardada no corresponde al floorplate, al programa o a una "
                              "versión compatible del motor: " + "; ".join(ev.stale_reasons), **base)
        return cls(fit=ev.robustness,
                   fit_label=ROBUSTNESS_LABEL.get(ev.robustness,
                                                  TECHNICAL_LABEL.get(ev.technical, NOT_EVALUATED_LABEL)),
                   recommendation=RECOMMENDATION_COPY.get(ev.robustness, DEFAULT_RECOMMENDATION),
                   reason=ev.reason or "", **base)

    def get(self, key, default=None):
        """Acceso de sólo lectura por nombre, para que los consumidores no cambien de forma. NO
        convierte esto en un dict: `build_board` exige el tipo, no la interfaz."""
        return getattr(self, key, default)

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


def presentation_fit(ctx, ev: "FitEvidence") -> PresentationFit:
    """Alias estable del único camino autorizado (se mantiene el nombre que usa E07)."""
    return PresentationFit.from_evidence(ctx, ev)
