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

from ... import intake, store
from . import listings

#: Qué sabemos del plano. `LOOKS_USABLE` es deliberadamente distinto de `USABLE`: el primero es
#: una impresión barata sobre la imagen, el segundo es el veredicto del motor tras leerla.
NO_PLAN = "NO_PLAN"
LOOKS_USABLE = "LOOKS_USABLE"
LOOKS_MULTI_UNIT = "LOOKS_MULTI_UNIT"
LOOKS_UNREADABLE = "LOOKS_UNREADABLE"
NOT_ANALYZED = "NOT_ANALYZED"
USABLE = "USABLE"
NEEDS_REVIEW = "NEEDS_REVIEW"
NOT_USABLE = "NOT_USABLE"

STATUS_LABEL = {
    NO_PLAN: "sin plano",
    LOOKS_USABLE: "hay un plano y parece legible",
    LOOKS_MULTI_UNIT: "hay un plano con varias unidades",
    LOOKS_UNREADABLE: "hay un plano pero no parece legible",
    NOT_ANALYZED: "el plano todavía no se analizó",
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
    l = listings.require(listing_id)
    base = inspect(listing_id)
    case_id = l["plan_case_id"]
    if not case_id:
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
    disponible = st["status"] in (LOOKS_USABLE, LOOKS_MULTI_UNIT, USABLE, NEEDS_REVIEW)
    return {
        # `has_plan` y `available` son distintos y los dos hacen falta: si el motor miró el plano
        # y no pudo leerlo, la capacidad NO está disponible, pero la sección tiene que seguir
        # visible. Esconderla haría desaparecer la pantalla justo después de que el operador
        # apretó "Analizar", que es cuando más necesita saber qué pasó.
        "has_plan": st["status"] != NO_PLAN,
        "available": disponible,
        "confirmed": st["status"] == USABLE,
        "commercial": comercial,
        "plan": st,
        "headline": ("Detectamos un plano. Podemos demostrar cómo podría utilizarse este espacio."
                     if disponible else "Miramos el plano de este aviso"),
    }
