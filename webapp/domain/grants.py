"""E32.2 §10 — CONCESIONES: un Pack cubre una propiedad. Sin dinero.

Una concesión es el derecho a preparar UNA propiedad. Nace de una compra —que todavía no existe: no
hay checkout, ni Stripe, ni facturas— o se simula desde el LAB para poder probar. Lo que importa es
la semántica:

    AVAILABLE   comprada y sin usar: habilita crear una propiedad.
    ASSIGNED    ya está puesta en una propiedad, y no se puede volver a usar.

Por qué esto y no un contador: "¿cuántas propiedades tiene esta cuenta?" es la pregunta equivocada.
La correcta es "¿le queda algún Pack sin usar?". Con la primera, un corredor que compró tres Packs
parecía estar violando su plan; con la segunda, simplemente tiene tres propiedades preparadas, que
es exactamente lo que pagó.

**`PackRequired` no es `EntitlementError`.** Que falte un Pack no tiene nada que ver con Pro, y
confundirlos es lo que hacía que la pantalla dijera "necesitás Pro" cuando lo que hacía falta era
otra compra de cien dólares.
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .. import store
from . import entitlements

AVAILABLE, ASSIGNED = "AVAILABLE", "ASSIGNED"
#: De dónde salió el derecho. SIMULATED_LAB deja explícito que nadie pagó.
SOURCES = ("PURCHASE", "SIMULATED_LAB", "LEGACY")


class PackRequired(PermissionError):
    """No queda ningún Pack sin usar. Hace falta otra compra — no Escalímetro Pro."""

    reason = "PACK_REQUIRED"

    def __init__(self, msg: str = ""):
        super().__init__(msg or "Este Pack ya está asignado a una propiedad. Para preparar otra "
                                "propiedad hace falta otro Pack.")


def create(product: str = entitlements.DEFAULT_PRODUCT, source: str = "SIMULATED_LAB",
           note: str = "") -> str:
    """Crea una concesión disponible. En el LAB esto representa una compra simulada."""
    if product not in entitlements.PRODUCTS:
        raise ValueError(f"producto desconocido: {product}")
    if source not in SOURCES:
        raise ValueError(f"origen desconocido: {source}")
    gid = "gr_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO pack_grants(grant_id, source, product, status, property_id, note, "
             "created_at) VALUES (?,?,?,?,NULL,?,?)",
             (gid, source, product, AVAILABLE, note[:300], store.now()))
    return gid


def get(grant_id: str) -> Optional[Dict]:
    row = store.q1("SELECT * FROM pack_grants WHERE grant_id=?", (grant_id,))
    return dict(row) if row else None


def available(product: Optional[str] = None) -> List[Dict]:
    if product:
        rows = store.q("SELECT * FROM pack_grants WHERE status=? AND product=? ORDER BY created_at",
                       (AVAILABLE, product))
    else:
        rows = store.q("SELECT * FROM pack_grants WHERE status=? ORDER BY created_at", (AVAILABLE,))
    return [dict(r) for r in rows]


def has_available(product: Optional[str] = None) -> bool:
    return bool(available(product))


def of_property(property_id: str) -> Optional[Dict]:
    row = store.q1("SELECT * FROM pack_grants WHERE property_id=?", (property_id,))
    return dict(row) if row else None


def assign(grant_id: str, property_id: str) -> None:
    """Pone una concesión en una propiedad. Una concesión se usa UNA vez: reasignarla sería
    permitir dos propiedades con una sola compra."""
    g = get(grant_id)
    if g is None:
        raise LookupError(grant_id)
    if g["status"] != AVAILABLE:
        raise PackRequired("Ese Pack ya está asignado a una propiedad.")
    if of_property(property_id) is not None:
        raise PackRequired("Esa propiedad ya tiene su Pack.")
    store.ex("UPDATE pack_grants SET status=?, property_id=?, assigned_at=? WHERE grant_id=?",
             (ASSIGNED, property_id, store.now(), grant_id))
    store.ex("UPDATE properties SET product=?, updated_at=? WHERE property_id=?",
             (g["product"], store.now(), property_id))


def consume(product: str, property_id: str) -> str:
    """Toma la primera concesión disponible de ese producto y la asigna. Lanza `PackRequired` si
    no queda ninguna: es el camino del cliente."""
    libres = available(product)
    if not libres:
        raise PackRequired()
    assign(libres[0]["grant_id"], property_id)
    return libres[0]["grant_id"]


def grant_and_assign(product: str, property_id: str, source: str = "SIMULATED_LAB",
                     note: str = "") -> str:
    """Crea la concesión y la asigna de una vez. Es lo que hace el LAB: cada propiedad de prueba
    representa una compra propia, así que no hay tope y tampoco se falsea que haya uno."""
    gid = create(product, source, note)
    assign(gid, property_id)
    return gid


def summary() -> Dict:
    """Para la consola: cuántos Packs hay, cuántos libres, cuántos puestos."""
    filas = [dict(r) for r in store.q("SELECT status, product, COUNT(*) n FROM pack_grants "
                                      "GROUP BY status, product")]
    libres = sum(f["n"] for f in filas if f["status"] == AVAILABLE)
    puestos = sum(f["n"] for f in filas if f["status"] == ASSIGNED)
    return {"available": libres, "assigned": puestos, "total": libres + puestos,
            "by": filas,
            "available_by_product": {p: len(available(p)) for p in entitlements.PRODUCTS}}
