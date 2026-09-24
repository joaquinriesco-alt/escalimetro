"""E17.0 — ADAPTADOR AL MOTOR ESPACIAL QUE YA EXISTE.

=================================================================================================
La regla de este archivo
=================================================================================================
**No reimplementa nada.** El pipeline de planos —localización, segmentación, perímetro, núcleo,
escala, readiness— vive en `src/escalimetro/` y se invoca por el mismo alta de caso que usa el
resto del sistema (`webapp.intake`). Acá sólo se hacen tres cosas: detectar que hay un plano,
preguntarle al motor qué ve, y traducir su respuesta al vocabulario del producto nuevo.

Ningún contrato del motor cambia. Si mañana el motor mejora, este archivo no se entera: sigue
preguntando lo mismo.

=================================================================================================
Dos niveles de respuesta, y por qué
=================================================================================================
`inspect()` es **barato**: mira la imagen sin correr el motor. Contesta "¿hay un plano y tiene
pinta de poder leerse?" en milisegundos, que es lo que el informe necesita para decidir si ofrecer
la capacidad espacial. Reutiliza el modelo de candidatos de E35 —también de esta aplicación, no
del motor— para saber si la lámina demarca varias unidades.

`analyze()` es **caro**: corre el pipeline de verdad, unos segundos, y contesta qué geometría
recuperó el motor. Se invoca explícitamente, no al generar el informe: hacer esperar cinco
segundos a alguien que sólo quería ver su score sería cobrarle el costo de una capacidad que
todavía no pidió.

La distinción importa para no mentir: `inspect()` dice *parece* utilizable, `analyze()` dice *es*
utilizable, y el producto usa las dos palabras con cuidado.
"""
from __future__ import annotations

import os
from typing import Dict, Optional

import json

from ... import intake, store
from . import listings

#: Qué sabemos del plano. `LOOKS_USABLE` es deliberadamente distinto de `USABLE`: el primero es
#: una impresión barata sobre la imagen, el segundo es el veredicto del motor tras leerla.
NO_PLAN = "NO_PLAN"
LOOKS_USABLE = "LOOKS_USABLE"
LOOKS_MULTI_UNIT = "LOOKS_MULTI_UNIT"
LOOKS_UNREADABLE = "LOOKS_UNREADABLE"
NOT_ANALYZED = "NOT_ANALYZED"
NEEDS_UNIT_PICK = "NEEDS_UNIT_PICK"
USABLE = "USABLE"
NEEDS_REVIEW = "NEEDS_REVIEW"
NOT_USABLE = "NOT_USABLE"

STATUS_LABEL = {
    NO_PLAN: "sin plano",
    LOOKS_USABLE: "hay un plano y parece legible",
    LOOKS_MULTI_UNIT: "hay un plano con varias unidades",
    LOOKS_UNREADABLE: "hay un plano pero no parece legible",
    NOT_ANALYZED: "el plano todavía no se analizó",
    NEEDS_UNIT_PICK: "hay que indicar cuál de las unidades es la de este aviso",
    USABLE: "el motor leyó la planta completa",
    NEEDS_REVIEW: "el motor leyó la planta y algo necesita revisión",
    NOT_USABLE: "el motor no pudo leer la planta",
}


def plan_media(listing_id: str) -> Optional[Dict]:
    medios = listings.media_of(listing_id, listings.PLAN)
    return medios[0] if medios else None


def inspect(listing_id: str) -> Dict:
    """Mirada barata: ¿hay plano y tiene pinta de poder leerse? Sin correr el motor."""
    m = plan_media(listing_id)
    if not m:
        return {"status": NO_PLAN, "label": STATUS_LABEL[NO_PLAN], "media_id": None,
                "candidates": 0, "analyzed": False}
    ruta = listings.media_path(m)
    if (m["mime_type"] or "").endswith("pdf"):
        # El pipeline acepta PDF por el mismo alta que el resto; acá no se puede mirar sin
        # rasterizar, así que se dice lo que se sabe y no más.
        return {"status": LOOKS_USABLE, "label": "hay un plano en PDF", "media_id": m["media_id"],
                "candidates": 0, "analyzed": False,
                "note": "es un PDF: hay que analizarlo para saber qué contiene"}
    try:
        from .. import units                                   # noqa: PLC0415
        cands = units.candidates(ruta)
    except Exception as e:                                     # noqa: BLE001
        return {"status": LOOKS_UNREADABLE, "label": STATUS_LABEL[LOOKS_UNREADABLE],
                "media_id": m["media_id"], "candidates": 0, "analyzed": False,
                "note": f"no se pudo mirar el dibujo ({type(e).__name__})"}
    chico = (m["width_px"] or 0) < 400 or (m["height_px"] or 0) < 300
    if chico:
        estado = LOOKS_UNREADABLE
    elif len(cands) > 1:
        estado = LOOKS_MULTI_UNIT
    else:
        estado = LOOKS_USABLE
    return {"status": estado, "label": STATUS_LABEL[estado], "media_id": m["media_id"],
            "candidates": len(cands), "analyzed": False,
            "candidate_areas": [c["pixel_area"] for c in cands],
            "note": ("la lámina demarca varias unidades: hay que indicar cuál es"
                     if estado == LOOKS_MULTI_UNIT else
                     "el dibujo es muy chico para leerlo con precisión" if chico else "")}


# =================================================================================================
# E17.1 — ¿CUÁL DE LAS UNIDADES DE LA LÁMINA ES LA DE ESTE AVISO?
# =================================================================================================
# Es la misma pregunta que E35 resolvió para el LAB, y se contesta con el MISMO algoritmo: se
# importa `domain.units` y se llaman sus funciones puras. Acá no se reimplementa ni el modelo de
# candidatos, ni el ranking, ni el dibujo del overlay, ni la traducción al vocabulario del motor.
# Lo único propio es dónde se guarda el clic, porque un aviso no es una propiedad y no puede tener
# una fila en `unit_selection` sin arrastrar consigo una `property` que nadie pidió.


def resolve_units(listing_id: str) -> Dict:
    """Analiza la lámina del aviso y guarda la decisión. Idempotente, y un reanálisis NO borra un
    clic humano: la misma regla que protege la selección en el LAB."""
    from .. import units                                       # noqa: PLC0415
    ya = unit_state(listing_id)
    if ya and ya.get("source") == units.HUMAN_PICK and ya["status"] == units.RESOLVED:
        return ya
    m = plan_media(listing_id)
    if not m:
        return {"status": units.NO_DRAWING, "candidates": [], "candidate_count": 0,
                "source": None, "selected_candidate_id": None}
    try:
        d = units.analyze(listings.media_path(m))
    except units.UnitError as e:
        return {"status": units.NO_DRAWING, "candidates": [], "candidate_count": 0,
                "source": None, "selected_candidate_id": None, "note": str(e)}
    _save_units(listing_id, d)
    return unit_state(listing_id)


def pick_unit(listing_id: str, candidate_id: str) -> Dict:
    """UN clic del operador. No se le pide ni un nombre, ni un id técnico, ni coordenadas."""
    from .. import units                                       # noqa: PLC0415
    d = unit_state(listing_id)
    if not d or not d["candidates"]:
        raise listings.ListingError("este aviso todavía no tiene candidatos analizados")
    if candidate_id not in [c["candidate_id"] for c in d["candidates"]]:
        raise listings.ListingError(f"candidato desconocido: {candidate_id}")
    d.update({"status": units.RESOLVED, "source": units.HUMAN_PICK, "confidence": 1.0,
              "selected_candidate_id": candidate_id, "reason_codes": ["HUMAN_PICK"],
              "evidence_summary": f"elegido por una persona entre {len(d['candidates'])}"})
    _save_units(listing_id, d)
    return unit_state(listing_id)


def _save_units(listing_id: str, d: Dict) -> None:
    store.ex("INSERT INTO listing_unit_selection(listing_id, status, source, confidence, "
             "candidate_count, selected_candidate_id, candidates, evidence_summary, reason_codes, "
             "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(listing_id) DO UPDATE SET "
             "status=excluded.status, source=excluded.source, confidence=excluded.confidence, "
             "candidate_count=excluded.candidate_count, "
             "selected_candidate_id=excluded.selected_candidate_id, "
             "candidates=excluded.candidates, evidence_summary=excluded.evidence_summary, "
             "reason_codes=excluded.reason_codes, updated_at=excluded.updated_at",
             (listing_id, d["status"], d.get("source"), d.get("confidence"),
              d.get("candidate_count"), d.get("selected_candidate_id"),
              json.dumps(d.get("candidates") or [], ensure_ascii=False),
              d.get("evidence_summary") or "",
              json.dumps(d.get("reason_codes") or [], ensure_ascii=False), store.now()))


def unit_state(listing_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM listing_unit_selection WHERE listing_id=?", (listing_id,))
    if not r:
        return None
    d = dict(r)
    d["candidates"] = store.js(d["candidates"], []) or []
    d["reason_codes"] = store.js(d["reason_codes"], []) or []
    return d


def selected_unit(listing_id: str) -> Optional[Dict]:
    from .. import units                                       # noqa: PLC0415
    d = unit_state(listing_id)
    if not d or d["status"] != units.RESOLVED or not d["selected_candidate_id"]:
        return None
    return next((c for c in d["candidates"]
                 if c["candidate_id"] == d["selected_candidate_id"]), None)


def unit_overrides(listing_id: str) -> Dict:
    """Lo que la selección le dice al motor. La traducción la hace `units`, no este módulo."""
    from .. import units                                       # noqa: PLC0415
    return units.overrides_for_candidate(selected_unit(listing_id))


def candidates_overlay(listing_id: str, out_path: str) -> Optional[str]:
    """La lámina con los candidatos pintados. El dibujo lo hace `units.draw_candidates`, que es la
    misma rutina que usa el LAB: dos paletas distintas harían que el número del plano dejara de
    coincidir con el del botón el día que alguien toque una."""
    from .. import units                                       # noqa: PLC0415
    d = unit_state(listing_id)
    m = plan_media(listing_id)
    if not d or not d["candidates"] or not m:
        return None
    return units.draw_candidates(listings.media_path(m), d["candidates"], out_path)


def needs_unit_pick(listing_id: str) -> bool:
    """¿Hay que preguntar? Sólo cuando la lámina demarca varias unidades y nadie eligió todavía."""
    from .. import units                                       # noqa: PLC0415
    d = unit_state(listing_id)
    return bool(d and d["status"] == units.NEEDS_INTERNAL_REVIEW)


def ensure_case(listing_id: str) -> str:
    """Entrega el plano al pipeline EXISTENTE. Copia, no mueve: el archivo que subió el cliente es
    el original y no debe cambiar nunca."""
    l = listings.require(listing_id)
    if l["plan_case_id"]:
        return l["plan_case_id"]
    m = plan_media(listing_id)
    if not m:
        raise listings.ListingError("este aviso no tiene un plano cargado")
    case_id = intake.create_case_from_path(listings.media_path(m), m["original_filename"],
                                           l["title"] or "aviso")
    if l["area_m2"]:
        store.ex("UPDATE cases SET published_area_m2=? WHERE case_id=?", (l["area_m2"], case_id))
    store.ex("UPDATE listings SET plan_case_id=?, updated_at=? WHERE listing_id=?",
             (case_id, store.now(), listing_id))
    return case_id


def analyze(listing_id: str) -> Dict:
    """Corre el pipeline de verdad y traduce lo que el motor recuperó.

    Lo que se lee de `shell_readiness` es exactamente lo que el motor publica; no se recalcula ni
    se reinterpreta. Si el motor dice que le falta confirmar algo, acá se dice `NEEDS_REVIEW` y se
    listan sus propias razones, sin traducirlas a un juicio nuestro."""
    from .. import units                                       # noqa: PLC0415
    # E17.1 §1 — primero la unidad. Correr el motor sobre una lámina multiunidad sin saber cuál es
    # la de este aviso no falla de forma interesante: falla siempre, y además el intento anterior
    # de E17.0 terminaba en "no pudimos leerlo" cuando el problema no era leerlo sino elegir.
    sel = resolve_units(listing_id)
    if sel and sel.get("status") == units.NEEDS_INTERNAL_REVIEW:
        return {"status": NEEDS_UNIT_PICK, "label": STATUS_LABEL[NEEDS_UNIT_PICK],
                "case_id": None, "analyzed": False, "ready": False, "pending": [],
                "candidates": sel["candidates"],
                "note": f"la lámina demarca {sel['candidate_count']} unidades"}
    case_id = ensure_case(listing_id)
    res = intake.analyze(case_id)
    fp = intake.load_floorplate(case_id)
    if fp is None:
        sin_loc = "Sin localización" in (res.get("log") or "")
        return {"status": NOT_USABLE, "label": STATUS_LABEL[NOT_USABLE], "case_id": case_id,
                "analyzed": True, "ready": False, "pending": [],
                "note": ("la lámina parece tener más de una unidad y no supimos cuál es"
                         if sin_loc else "el motor no pudo leer la geometría de este plano")}
    sr = fp.get("shell_readiness") or {}
    listo = bool(sr.get("ready_for_layout"))
    esc = fp.get("scale") or {}
    return {
        "status": USABLE if listo else NEEDS_REVIEW,
        "label": STATUS_LABEL[USABLE if listo else NEEDS_REVIEW],
        "case_id": case_id, "analyzed": True, "ready": listo,
        "pending": list(sr.get("requires_confirmation") or []),
        "area_m2": fp.get("area_m2"),
        "scale_px_per_m": esc.get("px_per_m"),
        "scale_method": esc.get("method"),
        "columns": len(fp.get("column_candidates") or []),
        "core": len(fp.get("core") or []),
        "note": sr.get("notes") or "",
    }


def state(listing_id: str) -> Dict:
    """Lo que el producto necesita saber del plano: la mirada barata, más el resultado del motor
    si alguien ya lo pidió. Nunca corre el pipeline por su cuenta."""
    from .. import units                                       # noqa: PLC0415
    l = listings.require(listing_id)
    base = inspect(listing_id)
    case_id = l["plan_case_id"]
    if not case_id:
        # Sin caso todavía: si la lámina demarca varias unidades, lo que falta no es correr el
        # motor sino elegir, y la pantalla tiene que poder decir eso en vez de ofrecer un botón
        # que ya sabemos que va a fallar.
        sel = unit_state(listing_id)
        if sel and sel["status"] == units.NEEDS_INTERNAL_REVIEW:
            return dict(base, status=NEEDS_UNIT_PICK, label=STATUS_LABEL[NEEDS_UNIT_PICK],
                        candidates=sel["candidates"], analyzed=False,
                        note=f"la lámina demarca {sel['candidate_count']} unidades")
        return base
    fp = intake.load_floorplate(case_id)
    if fp is None:
        # Hay caso pero no hay geometría: el motor YA corrió y no pudo leerla. Decir "todavía no
        # se analizó" escondería un resultado real y le ofrecería al operador volver a apretar un
        # botón que ya apretó. Un intento fallido es información, no ausencia de información.
        return dict(base, case_id=case_id, analyzed=True, ready=False, status=NOT_USABLE,
                    label=STATUS_LABEL[NOT_USABLE],
                    note=("la lámina demarca varias unidades y el motor no supo cuál es la de "
                          "este aviso" if base["status"] == LOOKS_MULTI_UNIT else
                          "el motor no pudo leer la geometría de este plano"))
    sr = fp.get("shell_readiness") or {}
    listo = bool(sr.get("ready_for_layout"))
    return dict(base, case_id=case_id, analyzed=True, ready=listo,
                status=USABLE if listo else NEEDS_REVIEW,
                label=STATUS_LABEL[USABLE if listo else NEEDS_REVIEW],
                area_m2=fp.get("area_m2"),
                pending=list(sr.get("requires_confirmation") or []))


def capability(listing_id: str) -> Dict:
    """¿Podemos demostrar cabida en este inmueble? Es el upsell espacial del encargo, y la
    respuesta es del motor, no nuestra."""
    st = state(listing_id)
    l = listings.require(listing_id)
    comercial = l["property_type"] in listings.COMMERCIAL
    disponible = st["status"] in (LOOKS_USABLE, LOOKS_MULTI_UNIT, USABLE, NEEDS_REVIEW,
                                  NEEDS_UNIT_PICK)
    return {
        # `has_plan` y `available` son distintos y los dos hacen falta: si el motor miró el plano
        # y no pudo leerlo, la capacidad NO está disponible, pero la sección tiene que seguir
        # visible. Esconderla haría desaparecer la pantalla justo después de que el operador
        # apretó "Analizar", que es cuando más necesita saber qué pasó.
        "has_plan": st["status"] != NO_PLAN,
        "available": disponible,
        "confirmed": st["status"] == USABLE,
        "needs_pick": st["status"] == NEEDS_UNIT_PICK,
        "commercial": comercial,
        "plan": st,
        "headline": ("Detectamos un plano. Podemos demostrar cómo podría utilizarse este espacio."
                     if disponible else "Miramos el plano de este aviso"),
    }
