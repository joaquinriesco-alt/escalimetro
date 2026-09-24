"""E17.0 — EL CONTRATO DEL ANTES / DESPUÉS.

La demostración gratuita de UNA intervención es la pieza comercial del producto: es lo que
convierte un diagnóstico en algo que se ve. Todavía no está conectada a ningún proveedor, y este
módulo existe igual, por una razón deliberada del encargo:

    «Prefiero contracts honestos y placeholders explícitos antes que features simuladas.»

Así que una demo puede existir con estado `NOT_AVAILABLE` y decir por qué. Lo que NO puede es
aparecer como lista mostrando una imagen que no se generó: quien vea un antes/después tiene que
estar viendo el inmueble real con una visualización referencial encima, nunca una foto de archivo.

Cada demo nace con su etiqueta `CONCEPTUAL_VISUALIZATION`, su frase de divulgación y el contrato
de veracidad de su intervención —qué preservar, qué puede cambiar— copiado en el momento de
crearse. Copiado y no referenciado a propósito: si mañana cambiamos el catálogo, una demo vieja
tiene que seguir diciendo bajo qué reglas se hizo.
"""
from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional

from ... import store
from . import interventions as iv, listings

NOT_AVAILABLE = "NOT_AVAILABLE"
REQUESTED = "REQUESTED"
GENERATING = "GENERATING"
READY = "READY"
FAILED = "FAILED"
STATUSES = (NOT_AVAILABLE, REQUESTED, GENERATING, READY, FAILED)

STATUS_LABEL = {NOT_AVAILABLE: "todavía no disponible", REQUESTED: "pedida",
                GENERATING: "generándose", READY: "lista", FAILED: "no se pudo generar"}


class DemoError(ValueError):
    pass


def providers_ready() -> Dict:
    """¿Hay con qué generar? Presencia de credenciales, nunca su valor — la misma regla que rige
    el resto del sistema desde E32."""
    from .. import pilot                                       # noqa: PLC0415
    r = pilot.readiness()
    aprobado = r.get("approved")
    return {"approved_provider": (aprobado or {}).get("provider"),
            "credentials_present": r.get("credentials_present", 0),
            "ready": bool(aprobado)}


def request(listing_id: str, intervention: str, source_media_id: Optional[str] = None,
            notes: str = "") -> str:
    """Registra la intención de demostrar una intervención sobre un medio concreto.

    Si no hay proveedor aprobado, la demo queda en `NOT_AVAILABLE` con el motivo escrito. No se
    encola nada, no se simula nada y no se promete una fecha."""
    listings.require(listing_id)
    if intervention not in iv.TYPES:
        raise DemoError(f"intervención desconocida: {intervention}")
    if source_media_id and not listings.media(source_media_id, listing_id):
        raise DemoError("ese medio no es de este aviso")
    contrato = iv.contract(intervention)
    prov = providers_ready()
    if not contrato["generative"]:
        estado, nota = READY, ("no requiere generación: es una decisión sobre el material que ya "
                               "existe")
    elif prov["ready"]:
        estado, nota = REQUESTED, "hay proveedor aprobado"
    else:
        estado, nota = NOT_AVAILABLE, ("todavía no hay un proveedor de imagen aprobado; el "
                                       "contrato queda registrado y la demo se generará cuando lo "
                                       "haya")
    did = "dm_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO intervention_demos(demo_id, listing_id, intervention, source_media_id, "
             "status, visualization_class, disclosure, provider, notes, created_at, updated_at) "
             "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
             (did, listing_id, intervention, source_media_id, estado,
              iv.CONCEPTUAL_VISUALIZATION, iv.DISCLOSURE, prov["approved_provider"],
              json.dumps({"note": notes or nota, "contract": contrato}, ensure_ascii=False),
              store.now(), store.now()))
    return did


def get(demo_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM intervention_demos WHERE demo_id=?", (demo_id,))
    if not r:
        return None
    d = dict(r)
    d["notes_obj"] = store.js(d["notes"], {}) or {}
    d["status_label"] = STATUS_LABEL.get(d["status"], d["status"])
    d["intervention_label"] = iv.label(d["intervention"])
    return d


def of_listing(listing_id: str) -> List[Dict]:
    return [get(r["demo_id"]) for r in store.q(
        "SELECT demo_id FROM intervention_demos WHERE listing_id=? ORDER BY created_at DESC",
        (listing_id,))]


def attach_result(demo_id: str, result_media_id: str, provider: str = "", model: str = "") -> None:
    """Sólo se llama cuando existe una imagen de verdad. Es el único camino a `READY` para una
    intervención generativa, y por eso exige el medio: no hay forma de marcar lista una demo que
    no tiene resultado."""
    d = get(demo_id)
    if not d:
        raise DemoError("esa demo no existe")
    if not listings.media(result_media_id, d["listing_id"]):
        raise DemoError("ese resultado no es de este aviso")
    store.ex("UPDATE intervention_demos SET result_media_id=?, status=?, provider=?, model=?, "
             "updated_at=? WHERE demo_id=?",
             (result_media_id, READY, provider or d["provider"], model, store.now(), demo_id))


def before_after(demo_id: str) -> Optional[Dict]:
    """El par que se muestra. Devuelve `None` en vez de medio par: un antes sin después no es un
    antes/después, es una foto."""
    d = get(demo_id)
    if not d or not d["source_media_id"] or not d["result_media_id"]:
        return None
    return {"demo_id": demo_id, "intervention": d["intervention"],
            "intervention_label": d["intervention_label"],
            "before_media_id": d["source_media_id"], "after_media_id": d["result_media_id"],
            "disclosure": d["disclosure"], "visualization_class": d["visualization_class"]}
