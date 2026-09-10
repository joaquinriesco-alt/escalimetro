"""E24 §11-§13 — ShellInputV1: implementación en runtime del contrato que E23 sólo especificó.

Siete checks sobre un Floorplate normalizado + los HECHOS DECLARADOS del caso. Cuatro veredictos.
Ningún check limpia el plano, interpreta mobiliario ni redibuja nada: V1 es shell-only
(docs/PRODUCT_V1_SCOPE.md, docs/PLAN_CLEANING_DEFERRED.md).

Resolución del veredicto — determinista, declarada aquí antes de mirar ningún caso:

    INVALID_INPUT     si falla la geometría base (perímetro o ambigüedad geométrica)
    INPUT_NOT_READY   si el plano está DECLARADO dominado por un layout previo
    SCALE_UNRESOLVED  si no hay escala consumible y nadie la confirmó
    SHELL_ACCEPTED    en cualquier otro caso

NEEDS_HITL NUNCA bloquea: agrega una pregunta a `hitl_required` y el shell sigue siendo aceptable.
Un test-fit con la escala por confirmar es exactamente el producto V1; uno sin perímetro, no.
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

CONTRACT_VERSION = "shell_input_v1"

SHELL_ACCEPTED = "SHELL_ACCEPTED"
INPUT_NOT_READY = "INPUT_NOT_READY"
INVALID_INPUT = "INVALID_INPUT"
SCALE_UNRESOLVED = "SCALE_UNRESOLVED"
VERDICTS = (SHELL_ACCEPTED, INPUT_NOT_READY, INVALID_INPUT, SCALE_UNRESOLVED)

PASS, NEEDS_HITL, FAIL, NOT_EVALUATED = "PASS", "NEEDS_HITL", "FAIL", "NOT_EVALUATED"

CHECK_ORDER = ["perimeter_recoverable", "scale_consumable", "area_consistent",
               "obstacles_representable", "entrance_identifiable", "not_layout_dominated",
               "geometry_unambiguous"]

HITL_PERIMETER, HITL_SCALE, HITL_ENTRANCE, HITL_FIXED = "perimeter", "scale", "entrance", "fixed_elements"

#: veredictos semánticos de escala que se pueden CONSUMIR sin confirmación humana
SCALE_OK = ("SCALE_CONFIRMED", "SCALE_INFERRED_MATCHED_REGION")
SCALE_BAD = ("SCALE_INCOMPATIBLE_REGION",)

#: tolerancia de coherencia de área contra la superficie publicada
AREA_TOL = 0.10


@dataclass
class ShellInputV1:
    case_id: str
    verdict: str
    checks: Dict[str, Dict[str, str]]
    evidence: Dict
    hitl_required: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"contract_version": CONTRACT_VERSION, "case_id": self.case_id, "verdict": self.verdict,
                "hitl_required": list(self.hitl_required),
                "checks": {k: self.checks[k] for k in CHECK_ORDER}, "evidence": self.evidence}

    def status(self, name: str) -> str:
        return self.checks[name]["status"]


def _c(status: str, why: str) -> Dict[str, str]:
    return {"status": status, "why": why}


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def find_floorplate(case_dir: str) -> Optional[str]:
    """Ruta canónica primero; si no existe, el floorplate más reciente que haya dejado el pipeline.
    Se REPORTA cuál se usó: dos plantas distintas no se juzgan como si fueran la misma."""
    canon = os.path.join(case_dir, "outputs", "floorplate.json")
    if os.path.exists(canon):
        return canon
    cand = sorted(glob.glob(os.path.join(case_dir, "outputs", "*floorplate*.json")))
    return cand[-1] if cand else None


# ---------------------------------------------------------------------------------------------------
# geometría auxiliar (sin dependencias pesadas: un anillo es una lista de puntos)
# ---------------------------------------------------------------------------------------------------
def _area(ring: List[List[float]]) -> float:
    n = len(ring)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _seg_cross(p, q, r, s) -> bool:
    def d(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = d(r, s, p), d(r, s, q), d(p, q, r), d(p, q, s)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _self_intersects(ring: List[List[float]]) -> bool:
    n = len(ring)
    segs = [(ring[i], ring[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _seg_cross(segs[i][0], segs[i][1], segs[j][0], segs[j][1]):
                return True
    return False


def _degenerate_edges(ring: List[List[float]], min_px: float = 1.0) -> int:
    n = len(ring)
    return sum(1 for i in range(n)
               if math.dist(tuple(ring[i]), tuple(ring[(i + 1) % n])) < min_px)


# ---------------------------------------------------------------------------------------------------
# los siete checks
# ---------------------------------------------------------------------------------------------------
def _check_perimeter(fp: Dict) -> Tuple[Dict, Optional[List]]:
    ring = ((fp.get("perimeter") or {}).get("ring")) or []
    if len(ring) < 4:
        return _c(FAIL, f"el perímetro tiene {len(ring)} vértices: no hay polígono recuperable"), None
    a = _area(ring)
    if a <= 0:
        return _c(FAIL, "el perímetro encierra área nula"), None
    st = ((fp.get("perimeter") or {}).get("meta") or {}).get("status")
    if st == "confirmed":
        return _c(PASS, f"perímetro de {len(ring)} vértices, {a:.0f} px², estado confirmed"), ring
    return _c(NEEDS_HITL, f"perímetro de {len(ring)} vértices recuperado, estado {st!r}: "
                          f"pedir confirmación de una sola pregunta"), ring


def _check_scale(fp: Dict, conf) -> Tuple[Dict, Optional[float], Optional[str], Optional[str]]:
    """→ (check, px_per_m, provenance, semantic_validity)"""
    sc = fp.get("scale") or {}
    sem = sc.get("semantic_validity")
    if conf is not None:
        return (_c(PASS, f"escala confirmada por el usuario ({conf.method}): "
                         f"{conf.px_per_m:.4f} px/m"), conf.px_per_m, conf.provenance, sem)
    px = sc.get("px_per_m")
    prov = sc.get("method")
    if px is None or sem in SCALE_BAD:
        return (_c(FAIL, f"no hay escala consumible: px_per_m={px!r}, validez semántica={sem!r}. "
                         f"Pedir dos puntos y la distancia real entre ellos."), None, prov, sem)
    if sem in SCALE_OK:
        return _c(PASS, f"escala consumible ({sem}): {px:.4f} px/m"), float(px), prov, sem
    return (_c(NEEDS_HITL, f"escala inferida por {prov!r} sin validación semántica ({sem!r}): "
                           f"{px:.4f} px/m. Se puede intentar layout, pero el número es un supuesto."),
            float(px), prov, sem)


def _check_area(fp: Dict, px_per_m: Optional[float], ring) -> Tuple[Dict, Optional[float]]:
    pub = fp.get("published_area_m2")
    if px_per_m is None or ring is None:
        return _c(NOT_EVALUATED, "sin escala consumible no hay área en metros que comparar"), None
    m2 = _area(ring) / (px_per_m ** 2)
    if pub is None:
        return _c(NEEDS_HITL, f"área del modelo {m2:.1f} m²; el caso no declara superficie publicada "
                              f"contra la cual contrastarla"), round(m2, 2)
    err = abs(m2 - float(pub)) / float(pub)
    if err <= AREA_TOL:
        return _c(PASS, f"área del modelo {m2:.1f} m² vs publicada {float(pub):.1f} m² "
                        f"(desvío {err * 100:.1f} % ≤ {AREA_TOL * 100:.0f} %)"), round(m2, 2)
    return _c(NEEDS_HITL, f"área del modelo {m2:.1f} m² vs publicada {float(pub):.1f} m² "
                          f"(desvío {err * 100:.1f} %): confirmar qué región mide la cifra publicada"), round(m2, 2)


def _check_obstacles(fp: Dict) -> Tuple[Dict, int]:
    core = fp.get("core") or []
    cols = fp.get("columns") or []
    n = len(core) + len(cols)
    if core and cols:
        return _c(PASS, f"{len(core)} núcleo(s) y {len(cols)} pilar(es) representables como polígonos"), n
    if not core and not cols:
        return _c(NEEDS_HITL, "no se recuperó ni núcleo ni pilares: confirmar si la planta es diáfana "
                              "o marcar los elementos fijos"), 0
    falta = "núcleo" if not core else "pilares"
    return _c(NEEDS_HITL, f"faltan {falta}: {len(core)} núcleo(s), {len(cols)} pilar(es). "
                          f"Confirmar elementos fijos."), n


def _check_entrance(fp: Dict) -> Dict:
    pe = fp.get("primary_entrance") or {}
    ents = fp.get("entrances") or []
    if pe.get("point") and pe.get("status") == "confirmed":
        return _c(PASS, f"acceso principal confirmado en {pe['point']} "
                        f"(confianza {pe.get('confidence')})")
    if pe.get("point") or ents:
        return _c(NEEDS_HITL, f"hay {len(ents)} candidato(s) de acceso pero ninguno confirmado: "
                              f"pedir cuál es el acceso")
    return _c(NEEDS_HITL, "no se identificó acceso: pedir al usuario que lo señale")


def _check_not_layout_dominated(declared) -> Dict:
    """§12 — SÓLO el hecho declarado. Sin IA, sin VLM, sin SemanticHint, sin contar muebles."""
    if declared is True:
        return _c(PASS, "hecho declarado en el caso: shell_declared_clean = true (planta libre)")
    if declared is False:
        return _c(FAIL, "hecho declarado en el caso: shell_declared_clean = false. El dibujo está "
                        "dominado por un layout existente. V1 no limpia planos: es entrada no lista, "
                        "no un fallo del producto (docs/PLAN_CLEANING_DEFERRED.md).")
    return _c(NEEDS_HITL, "el caso no declara shell_declared_clean: una confirmación simple "
                          "('¿esta planta viene libre?'). No se infiere del dibujo.")


def _check_geometry(fp: Dict, ring) -> Dict:
    if ring is None:
        return _c(NOT_EVALUATED, "sin perímetro recuperado no hay geometría que juzgar")
    holes = fp.get("holes") or []
    if _self_intersects(ring):
        return _c(FAIL, "el perímetro se auto-intersecta: el polígono no es simple")
    deg = _degenerate_edges(ring)
    unk = [u.get("element") for u in (fp.get("unknowns") or [])]
    partes = []
    if deg:
        partes.append(f"{deg} arista(s) degenerada(s) < 1 px")
    if holes:
        partes.append(f"{len(holes)} hueco(s) interior(es)")
    if partes:
        return _c(NEEDS_HITL, "polígono simple, con observaciones: " + "; ".join(partes) +
                              (f"; incógnitas declaradas: {unk}" if unk else ""))
    return _c(PASS, f"polígono simple de {len(ring)} vértices, sin huecos ni aristas degeneradas" +
                    (f"; incógnitas declaradas: {unk}" if unk else ""))


# ---------------------------------------------------------------------------------------------------
def evaluate(case_dir: str, case: Dict = None, floorplate_path: str = None,
             scale_confirmation=None) -> ShellInputV1:
    """`case` es el case.json ya leído (hechos declarados). `scale_confirmation` es una
    ScaleConfirmation ya construida, o None para leerla del propio caso."""
    from .scale_confirmation import ScaleConfirmation

    case = case if case is not None else json.load(open(os.path.join(case_dir, "case.json"), encoding="utf-8"))
    case_id = case.get("case_id") or os.path.basename(case_dir.rstrip("/"))
    fpp = floorplate_path or find_floorplate(case_dir)
    declared_clean = case.get("shell_declared_clean", "unknown")
    conf = scale_confirmation or ScaleConfirmation.from_case(case.get("scale_confirmation"))

    if not fpp or not os.path.exists(fpp):
        checks = {k: _c(NOT_EVALUATED, "no hay floorplate normalizado para este caso") for k in CHECK_ORDER}
        checks["perimeter_recoverable"] = _c(FAIL, "no existe ningún floorplate.json en outputs/")
        checks["not_layout_dominated"] = _check_not_layout_dominated(declared_clean)
        ev = {"floorplate_sha256": "0" * 64, "floorplate_path": "", "scale_semantic_validity": None,
              "px_per_m": None, "usable_area_m2": None, "obstacle_count": 0,
              "shell_declared_clean": declared_clean, "scale_provenance": "NONE",
              "scale_confirmation": None, "notes": "sin geometría normalizada no hay nada que aceptar"}
        return ShellInputV1(case_id, INVALID_INPUT, checks, ev, [HITL_PERIMETER])

    fp = json.load(open(fpp, encoding="utf-8"))
    checks: Dict[str, Dict[str, str]] = {}
    checks["perimeter_recoverable"], ring = _check_perimeter(fp)
    checks["scale_consumable"], px, prov, sem = _check_scale(fp, conf)
    checks["area_consistent"], m2 = _check_area(fp, px, ring)
    checks["obstacles_representable"], nobs = _check_obstacles(fp)
    checks["entrance_identifiable"] = _check_entrance(fp)
    checks["not_layout_dominated"] = _check_not_layout_dominated(declared_clean)
    checks["geometry_unambiguous"] = _check_geometry(fp, ring)

    hitl: List[str] = []
    if checks["perimeter_recoverable"]["status"] == NEEDS_HITL or \
       checks["geometry_unambiguous"]["status"] == NEEDS_HITL:
        hitl.append(HITL_PERIMETER)
    if checks["scale_consumable"]["status"] in (NEEDS_HITL, FAIL) or \
       checks["area_consistent"]["status"] == NEEDS_HITL:
        hitl.append(HITL_SCALE)
    if checks["entrance_identifiable"]["status"] == NEEDS_HITL:
        hitl.append(HITL_ENTRANCE)
    if checks["obstacles_representable"]["status"] == NEEDS_HITL or \
       checks["not_layout_dominated"]["status"] == NEEDS_HITL:
        hitl.append(HITL_FIXED)
    hitl = [h for h in (HITL_PERIMETER, HITL_SCALE, HITL_ENTRANCE, HITL_FIXED) if h in hitl]

    if checks["perimeter_recoverable"]["status"] == FAIL or checks["geometry_unambiguous"]["status"] == FAIL:
        verdict = INVALID_INPUT
    elif checks["not_layout_dominated"]["status"] == FAIL:
        verdict = INPUT_NOT_READY
    elif checks["scale_consumable"]["status"] == FAIL:
        verdict = SCALE_UNRESOLVED
    else:
        verdict = SHELL_ACCEPTED

    ev = {"floorplate_sha256": _sha(fpp), "floorplate_path": os.path.relpath(fpp).replace(os.sep, "/"),
          "scale_semantic_validity": sem, "px_per_m": px,
          "usable_area_m2": m2, "obstacle_count": nobs,
          "shell_declared_clean": declared_clean,
          "scale_provenance": (conf.provenance if conf else (prov or "NONE")),
          "scale_confirmation": conf.to_dict() if conf else None,
          "notes": f"{sum(1 for c in checks.values() if c['status'] == PASS)}/7 checks en PASS"}
    return ShellInputV1(case_id, verdict, checks, ev, hitl)
