"""E30 §9 — FIT REQUEST: "evaluá esta propiedad para este programa".

Es la pieza que convierte a Escalímetro de entregable en flujo. Una propiedad se prepara UNA vez
—geometría, escala, accesos— y a partir de ahí cada prospecto que aparece es un fit request nuevo
sobre la MISMA geometría. Eso es lo que hace que el segundo prospecto sea barato y el décimo
también.

Dos clases de fit, y la diferencia es comercial, no técnica:

    BASE       el de la propiedad. Sale del preset EQUILIBRADO y produce el layout REPRESENTATIVO
               del pack de publicación (§18). Hay exactamente uno por propiedad.
    PROSPECT   uno por prospecto, con su nombre, su marca y su programa. Sólo en Pro (§17).

Reglas que este módulo hace cumplir y que no son negociables:

* **un fit nuevo no destruye los anteriores** (§9). Cada uno guarda sus corridas y su historia; se
  archivan, no se borran. Un prospecto que no arrendó el año pasado sigue siendo evidencia.
* **no se inventa ocupación** (§18/§22). Si no sabemos cuántas personas son, se pide; no hay un
  número por defecto escondido en ninguna parte de este archivo.
* **el motor no se entera de nada de esto.** Un fit produce un BriefV1 y una corrida; el contrato
  con el motor es exactamente el mismo que en E27.
"""
from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional

from .. import briefs as briefmod, engine, store
from . import entitlements, presets, properties

SCHEMA_VERSION = "fit_request_v1"

BASE = "BASE"
PROSPECT = "PROSPECT"
KINDS = (BASE, PROSPECT)

EXPRESS = "EXPRESS"
ADVANCED = "ADVANCED"
BRIEF_MODES = (EXPRESS, ADVANCED)

#: Cómo se eligió el layout representativo. Se guarda en el asset y se muestra: el cliente tiene
#: derecho a saber por qué está viendo ESA lámina y no otra (§22).
SELECTED_BY_LABEL = {
    "human_best_alt": "elegida por nuestro equipo tras revisar las tres",
    "program_complete": "la alternativa que ubica el programa completo",
    "first_fit": "la primera alternativa con layout",
}


class FitError(ValueError):
    """Problema del fit request que el usuario puede corregir."""


def new_id() -> str:
    return "f_" + uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------------------------
# creación
# ---------------------------------------------------------------------------------------------
def _insert(property_id: str, kind: str, label: str, headcount: Optional[int], preset: str,
            style: str, brief_mode: str, prospect_name: str = "", prospect_color: str = "",
            prospect_logo_id: Optional[str] = None, notes: str = "") -> str:
    fid = new_id()
    now = store.now()
    store.ex("INSERT INTO fit_requests(fit_id, property_id, schema_version, kind, label, "
             "prospect_name, prospect_color, prospect_logo_id, headcount, workplace_preset, "
             "visual_style, brief_mode, brief_json, notes, archived, created_at, updated_at) "
             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,0,?,?)",
             (fid, property_id, SCHEMA_VERSION, kind, label.strip()[:120],
              prospect_name.strip()[:120], prospect_color, prospect_logo_id,
              headcount, preset, style, brief_mode, notes.strip()[:2000], now, now))
    return fid


def base_of(property_id: str) -> Optional[Dict]:
    row = store.q1("SELECT * FROM fit_requests WHERE property_id=? AND kind='BASE' "
                   "ORDER BY created_at LIMIT 1", (property_id,))
    return dict(row) if row else None


def ensure_base(property_id: str, headcount: int, preset: str = presets.DEFAULT_PRESET,
                style: str = presets.DEFAULT_STYLE) -> str:
    """El fit BASE de la propiedad: el que produce el layout representativo del pack (§18).

    `headcount` es OBLIGATORIO y no tiene valor por defecto a propósito. §18: "if headcount is
    unknown, request minimum necessary customer input rather than invent it"."""
    properties.require(property_id)
    presets.require_preset(preset)
    presets.require_style(style)
    try:
        h = int(headcount)
    except (TypeError, ValueError):
        raise FitError("Decinos cuántas personas van a trabajar en la oficina.")
    if h < 1:
        raise FitError("El número de personas debe ser al menos 1.")
    existente = base_of(property_id)
    if existente:
        store.ex("UPDATE fit_requests SET headcount=?, workplace_preset=?, visual_style=?, "
                 "updated_at=? WHERE fit_id=?", (h, preset, style, store.now(),
                                                 existente["fit_id"]))
        return existente["fit_id"]
    return _insert(property_id, BASE, "Programa base", h, preset, style, EXPRESS)


def create_prospect(property_id: str, prospect_name: str, headcount: int,
                    preset: str = presets.DEFAULT_PRESET, style: str = presets.DEFAULT_STYLE,
                    prospect_color: str = "", prospect_logo_id: Optional[str] = None,
                    notes: str = "") -> str:
    """Un fit para un prospecto concreto. Sólo Pro (§17) — y la negativa ocurre acá, en el
    dominio, no escondiendo un botón."""
    entitlements.require(property_id, entitlements.PROSPECT_FIT_REQUESTS)
    properties.require(property_id)
    presets.require_preset(preset)
    presets.require_style(style)
    nombre = (prospect_name or "").strip()
    if not nombre:
        raise FitError("Ponle el nombre del prospecto.")
    try:
        h = int(headcount)
    except (TypeError, ValueError):
        raise FitError("Decinos cuántas personas son.")
    if h < 1:
        raise FitError("El número de personas debe ser al menos 1.")
    tope = entitlements.limit(property_id, "fit_requests_per_property")
    if tope is not None and len(list_for(property_id, include_base=False)) >= tope:
        raise entitlements.EntitlementError(entitlements.PROSPECT_FIT_REQUESTS)
    from . import branding                                    # noqa: PLC0415
    color = branding.normalize_color(prospect_color)
    return _insert(property_id, PROSPECT, nombre, h, preset, style, EXPRESS,
                   prospect_name=nombre, prospect_color=color,
                   prospect_logo_id=prospect_logo_id, notes=notes)


# ---------------------------------------------------------------------------------------------
# lectura
# ---------------------------------------------------------------------------------------------
def get(fit_id: str, property_id: Optional[str] = None) -> Optional[Dict]:
    """Con `property_id`, un fit de otra propiedad no existe. Misma barrera que en `assets`."""
    row = store.q1("SELECT * FROM fit_requests WHERE fit_id=?", (fit_id,))
    if row is None:
        return None
    d = dict(row)
    if property_id is not None and d["property_id"] != property_id:
        return None
    d["brief"] = store.js(d["brief_json"], None)
    return d


def require(fit_id: str, property_id: Optional[str] = None) -> Dict:
    f = get(fit_id, property_id)
    if f is None:
        raise LookupError(fit_id)
    return f


def list_for(property_id: str, include_base: bool = True,
             include_archived: bool = False) -> List[Dict]:
    sql = "SELECT * FROM fit_requests WHERE property_id=?"
    if not include_base:
        sql += " AND kind<>'BASE'"
    if not include_archived:
        sql += " AND archived=0"
    sql += " ORDER BY kind DESC, created_at DESC"
    return [get(r["fit_id"]) for r in store.q(sql, (property_id,))]


def archive(fit_id: str) -> None:
    """§9 — no se destruye: se archiva. El material generado sigue existiendo y sigue siendo
    trazable; sólo deja de estar primero en la lista."""
    store.ex("UPDATE fit_requests SET archived=1, updated_at=? WHERE fit_id=?",
             (store.now(), fit_id))


# ---------------------------------------------------------------------------------------------
# programa
# ---------------------------------------------------------------------------------------------
def brief_preview(fit: Dict) -> Optional[Dict]:
    """Qué va a pedir este fit, ANTES de gastar una corrida. Sin efectos."""
    if fit.get("brief"):
        return fit["brief"]
    if not fit.get("headcount"):
        return None
    return presets.brief_for(fit["workplace_preset"], fit["headcount"],
                             _brief_slug(fit), target_seats=None)


def _brief_slug(fit: Dict) -> str:
    base = fit["label"] if fit["kind"] == PROSPECT else "BASE"
    return briefmod.slug(f'{base}_{fit["workplace_preset"]}')


def set_advanced_brief(fit_id: str, brief_dict: Dict) -> None:
    """Modo AVANZADO (§10): el usuario editó el programa módulo por módulo. Se guarda tal cual;
    a partir de acá el preset queda como referencia de dónde salió, no como fuente."""
    f = require(fit_id)
    entitlements.require(f["property_id"], entitlements.ADVANCED_BRIEF)
    store.ex("UPDATE fit_requests SET brief_json=?, brief_mode=?, updated_at=? WHERE fit_id=?",
             (json.dumps(brief_dict, ensure_ascii=False), ADVANCED, store.now(), fit_id))


def set_express(fit_id: str, headcount: int, preset: str, style: str,
                target_seats: Optional[int] = None) -> None:
    """Modo EXPRESS (§10): personas + preset, y opcionalmente puestos objetivo. Nada más."""
    f = require(fit_id)
    presets.require_preset(preset)
    presets.require_style(style)
    b = presets.brief_for(preset, headcount, _brief_slug(dict(f, workplace_preset=preset)),
                          target_seats=target_seats)
    store.ex("UPDATE fit_requests SET headcount=?, workplace_preset=?, visual_style=?, "
             "brief_mode=?, brief_json=?, updated_at=? WHERE fit_id=?",
             (int(headcount), preset, style, EXPRESS,
              json.dumps(b, ensure_ascii=False), store.now(), fit_id))


# ---------------------------------------------------------------------------------------------
# generación
# ---------------------------------------------------------------------------------------------
def generate(fit_id: str) -> str:
    """Compila el brief del fit y lanza UNA corrida del motor. Devuelve el run_id.

    El motor sigue calculando sus tres estrategias A/B/C: eso es cómo está construido y E30 no lo
    toca. Lo que cambia es cuántas de esas tres se ENTREGAN, y eso lo decide el producto
    (`delivered`), no el solver."""
    from . import floorplan                                   # noqa: PLC0415
    f = require(fit_id)
    p = properties.require(f["property_id"])
    case_id = p["floorplan_case_id"]
    if not case_id:
        raise FitError("La propiedad todavía no tiene una planta preparada.")
    t = floorplan.technical_state(f["property_id"])
    if not t["ready"]:
        raise FitError("La planta todavía no está lista para generar alternativas.")
    if runs_for(fit_id) and not entitlements.allows(f["property_id"], entitlements.REGENERATE):
        raise entitlements.EntitlementError(entitlements.REGENERATE)

    b = brief_preview(f)
    if b is None:
        raise FitError("Falta decir cuántas personas van a trabajar en la oficina.")
    briefmod.validate_against_engine(b, briefmod.MODULES_PATH)
    brief_id, _ = briefmod.register(case_id, b, f["label"])
    store.ex("UPDATE fit_requests SET brief_json=?, updated_at=? WHERE fit_id=?",
             (json.dumps(dict(b, brief_id=brief_id), ensure_ascii=False), store.now(), fit_id))
    run_id = engine.launch(case_id, brief_id)
    store.ex("INSERT OR REPLACE INTO fit_runs(fit_id, run_id, created_at) VALUES (?,?,?)",
             (fit_id, run_id, store.now()))
    return run_id


def runs_for(fit_id: str) -> List[Dict]:
    """Corridas de este fit, de la más nueva a la más vieja, con sus alternativas."""
    out = []
    for fr in store.q("SELECT run_id FROM fit_runs WHERE fit_id=? ORDER BY created_at DESC",
                      (fit_id,)):
        r = store.q1("SELECT * FROM runs WHERE run_id=?", (fr["run_id"],))
        if r is None:
            continue
        alts = [dict(a) for a in store.q(
            "SELECT * FROM alternatives WHERE run_id=? ORDER BY alt", (r["run_id"],))]
        out.append({"run": dict(r), "alternatives": alts})
    return out


def latest_run(fit_id: str) -> Optional[Dict]:
    rs = runs_for(fit_id)
    return rs[0] if rs else None


def fit_alternatives(fit_id: str) -> List[Dict]:
    """Las alternativas CON layout de la última corrida. Vacío si el motor no encontró ninguna,
    y eso no se maquilla: SEARCH_EXHAUSTED es un resultado, no un error (§22)."""
    r = latest_run(fit_id)
    if r is None:
        return []
    return [a for a in r["alternatives"] if a["status"] == "FIT"]


# ---------------------------------------------------------------------------------------------
# §18 — el layout REPRESENTATIVO
# ---------------------------------------------------------------------------------------------
def pick_representative(run_row: Dict, alternatives: List[Dict]) -> Optional[Dict]:
    """El criterio del §18, aislado de dónde vengan la corrida y las alternativas: lo usan tanto
    un fit request como una propiedad vinculada a mano a un caso que ya existía."""
    fits_ = [a for a in alternatives if a["status"] == "FIT"]
    if not fits_:
        return None
    best = run_row.get("best_alt")
    if best in ("A", "B", "C"):
        elegida = next((a for a in fits_ if a["alt"] == best), None)
        if elegida:
            return {"alt": elegida, "run": run_row, "selected_by": "human_best_alt"}
    completa = next((a for a in fits_
                     if (store.js(a["quality"], {}) or {}).get("program_complete")), None)
    if completa:
        return {"alt": completa, "run": run_row, "selected_by": "program_complete"}
    return {"alt": fits_[0], "run": run_row, "selected_by": "first_fit"}


def representative(fit_id: str) -> Optional[Dict]:
    """La ÚNICA alternativa que entra en el pack de publicación.

    §18 es explícito: "Do not just publish 'latest layout'". El criterio, en orden y declarado:

      1. si una persona de nuestro equipo marcó la mejor de la corrida, ésa. El juicio humano
         gana siempre: es literalmente el producto que E26 construyó para medir;
      2. si no, la que ubica el programa completo (`program_complete` del motor);
      3. si ninguna lo ubica entero, la primera con layout, en orden A, B, C.

    Lo que este criterio NO es: una puntuación de calidad arquitectónica. `architectural_score`
    existe en quality.json y dice de sí mismo que es instrumentación y que ningún umbral suyo
    decide si una planta sirve. Usarlo acá para coronar "la mejor" sería exactamente la clase de
    afirmación que §22 prohíbe. Por eso se devuelve también `selected_by`: quien mira la lámina
    puede saber por qué es ésa."""
    r = latest_run(fit_id)
    return pick_representative(r["run"], r["alternatives"]) if r else None


def delivered(fit_id: str) -> List[Dict]:
    """Qué alternativas ENTREGA el producto de ESTA propiedad: el Pack entrega una representativa;
    Pro entrega las tres. Se pregunta por la propiedad, no por la cuenta."""
    f = require(fit_id)
    if entitlements.allows(f["property_id"], entitlements.ABC_ALTERNATIVES):
        return fit_alternatives(fit_id)
    rep = representative(fit_id)
    return [rep["alt"]] if rep else []


def view(fit_id: str, property_id: Optional[str] = None) -> Dict:
    """Todo lo que una plantilla necesita de un fit, ya resuelto."""
    from . import branding                                    # noqa: PLC0415
    f = require(fit_id, property_id)
    r = latest_run(fit_id)
    rep = representative(fit_id)
    b = brief_preview(f)
    return {
        "fit": f,
        "brief": b,
        "brief_summary": briefmod.summary(b) if b else None,
        "preset_label": presets.PRESET_LABEL.get(f["workplace_preset"], f["workplace_preset"]),
        "style_label": presets.STYLE_LABEL.get(f["visual_style"], f["visual_style"]),
        "run": r["run"] if r else None,
        "alternatives": r["alternatives"] if r else [],
        "fit_alternatives": fit_alternatives(fit_id),
        "delivered": delivered(fit_id),
        "representative": rep,
        "representative_why": SELECTED_BY_LABEL.get((rep or {}).get("selected_by"), ""),
        "brand": branding.prospect(f) if f["kind"] == PROSPECT else branding.brokerage(),
    }
