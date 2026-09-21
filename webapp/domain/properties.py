"""E28.1 — la entidad PROPERTY y su estado comercial.

Regla que gobierna este módulo (§6 del encargo): **el estado de una propiedad no se declara, se
deriva de hechos**. Hechos son: si hay plano subido, qué dice el artefacto del CASE vinculado, si
hay corridas con layout, si hay un pack exportado. La columna `status` existe para poder listar y
filtrar rápido, pero se recalcula cada vez que se lee: no es una segunda fuente de verdad que pueda
quedar desincronizada del motor.

La otra regla: el vocabulario técnico del CASE (NEEDS_CONFIRMATION, requires_confirmation, shell)
no cruza esta frontera. Una propiedad que necesita que un humano nuestro mire la planta dice
`NEEDS_INTERNAL_REVIEW` hacia adentro y "Estamos preparando la planta" hacia afuera.
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .. import store

#: V1 sólo opera oficinas. El campo existe para no tener que migrar cuando se abra otro tipo, pero
#: nada más que OFFICE es funcional en E28 y la UI no ofrece alternativas.
ASSET_TYPES = ("OFFICE",)

#: Estados de PRODUCTO. Deliberadamente menos que los del CASE: el cliente no necesita saber si lo
#: que falta es el perímetro o los pilares, sólo si su planta está lista.
PROPERTY_STATES = (
    "DRAFT",             # creada; todavía no subió el plano
    "PREPARING",         # hay plano; el caso técnico aún no está listo (incluye revisión interna)
    "FLOORPLAN_READY",   # la planta quedó lista; aún no hay layouts
    "LAYOUTS_READY",     # hay al menos una corrida con layouts
    "PACK_READY",        # existe un pack exportado
    "BLOCKED",           # fuera de contrato V1 (planta no limpia) o el caso falló técnicamente
    "FAILED",            # falla técnica de ESTA capa, no del motor
)

#: Cómo se le cuenta cada estado a un cliente. Sin jerga, sin nombres de artefactos.
CUSTOMER_LABEL = {
    "DRAFT": "Falta subir el plano",
    "PREPARING": "Estamos preparando la planta",
    "FLOORPLAN_READY": "Plano listo",
    "LAYOUTS_READY": "Alternativas listas",
    "PACK_READY": "Pack listo",
    "BLOCKED": "Necesitamos revisar esta propiedad",
    "FAILED": "Necesitamos revisar esta propiedad",
}

#: Estados del CASE que exigen que un operador nuestro intervenga antes de poder seguir.
CASE_NEEDS_OPERATOR = ("UPLOADED", "NEEDS_INPUT", "NEEDS_CONFIRMATION", "FAILED", "INPUT_NOT_READY")

SCHEMA_VERSION = "property_v1"


def new_id() -> str:
    """Identificador interno, opaco y no adivinable. Nunca deriva de nada que escriba el usuario:
    es también el nombre del directorio de assets, así que tiene que ser seguro por construcción."""
    return "p_" + uuid.uuid4().hex[:12]


def create(title: str, asset_type: str = "OFFICE", city: str = "", country: str = "",
           reference: str = "", published_area_m2: Optional[float] = None,
           notes: str = "") -> str:
    if asset_type not in ASSET_TYPES:
        raise ValueError(f"tipo de propiedad no soportado en V1: {asset_type}")
    pid = new_id()
    now = store.now()
    store.ex("INSERT INTO properties(property_id, schema_version, title, asset_type, country, city,"
             " reference, published_area_m2, floorplan_case_id, status, notes, created_at,"
             " updated_at) VALUES (?,?,?,?,?,?,?,?,NULL,'DRAFT',?,?,?)",
             (pid, SCHEMA_VERSION, (title or "Propiedad").strip()[:160], asset_type,
              country.strip()[:80], city.strip()[:80], reference.strip()[:200],
              published_area_m2, notes.strip()[:2000], now, now))
    return pid


def get(property_id: str) -> Optional[Dict]:
    row = store.q1("SELECT * FROM properties WHERE property_id=?", (property_id,))
    return dict(row) if row else None


def require(property_id: str) -> Dict:
    p = get(property_id)
    if p is None:
        raise LookupError(property_id)
    return p


def touch(property_id: str) -> None:
    store.ex("UPDATE properties SET updated_at=? WHERE property_id=?", (store.now(), property_id))


def link_case(property_id: str, case_id: str) -> None:
    """Vincula un CASE existente. No crea ni modifica el caso: eso es trabajo del adaptador."""
    require(property_id)
    if store.q1("SELECT case_id FROM cases WHERE case_id=?", (case_id,)) is None:
        raise LookupError(case_id)
    otra = store.q1("SELECT property_id FROM properties WHERE floorplan_case_id=? "
                    "AND property_id<>?", (case_id, property_id))
    if otra is not None:
        raise ValueError(f"ese plano ya pertenece a otra propiedad ({otra['property_id']})")
    store.ex("UPDATE properties SET floorplan_case_id=?, updated_at=? WHERE property_id=?",
             (case_id, store.now(), property_id))


def set_notes(property_id: str, notes: str) -> None:
    store.ex("UPDATE properties SET notes=?, updated_at=? WHERE property_id=?",
             (notes.strip()[:2000], store.now(), property_id))


# ===================================================================================================
# Estado DERIVADO — la parte que importa
# ===================================================================================================
def facts(property_id: str) -> Dict:
    """Los hechos crudos de los que sale todo lo demás. Sin interpretación."""
    from . import assets, packs                                # noqa: PLC0415 (ciclo de import)
    p = require(property_id)
    case = None
    if p["floorplan_case_id"]:
        row = store.q1("SELECT * FROM cases WHERE case_id=?", (p["floorplan_case_id"],))
        case = dict(row) if row else None
    fit = 0
    if case:
        fit = store.q1(
            "SELECT COUNT(*) n FROM alternatives a JOIN runs r ON r.run_id=a.run_id "
            "WHERE r.case_id=? AND a.status='FIT'", (case["case_id"],))["n"]
    f = {
        "property": p,
        "case": case,
        "case_status": (case or {}).get("status"),
        "has_floorplan_asset": bool(assets.first_of_kind(property_id, "FLOORPLAN_ORIGINAL")),
        "n_photos": len(assets.list_of_kind(property_id, "PHOTO_ORIGINAL")),
        "n_fit_layouts": fit,
        "has_pack_export": packs.has_export(property_id),
        "pack_readiness": None,
    }
    # E31 §21 — la completitud del pack base es un hecho más, y el único que puede decir PACK_READY
    if f["has_floorplan_asset"] and f["case_status"] not in ("INPUT_NOT_READY", "FAILED"):
        try:
            f["pack_readiness"] = packs.readiness(property_id)["state"]
        except Exception:                                     # noqa: BLE001 — nunca rompe la lista
            f["pack_readiness"] = None
    return f


def derive_status(f: Dict) -> str:
    """Hechos → estado de producto. Única definición; nadie más decide esto."""
    case_status = f["case_status"]
    if case_status in ("INPUT_NOT_READY", "FAILED"):
        return "BLOCKED"
    if not f["has_floorplan_asset"]:
        return "DRAFT"
    # E31 §21 — PACK_READY exige lo prometido (plano + layout + imagen ambientada aprobada) o un
    # override interno con motivo. Un ZIP viejo en el volumen no convierte a la propiedad en lista.
    if f["has_pack_export"] and f.get("pack_readiness") in ("READY", "DEGRADED"):
        return "PACK_READY"
    if f["n_fit_layouts"]:
        return "LAYOUTS_READY"
    if case_status in ("READY", "COMPLETE", "PARTIAL"):
        return "FLOORPLAN_READY"
    return "PREPARING"


def needs_internal_review(f: Dict) -> bool:
    """§10 — un caso que pide intervención humana NO se le cuenta al cliente como tal: entra en la
    cola interna. Si hay plano pero todavía no hay caso, también nos toca a nosotros."""
    if f["case"] is None:
        return bool(f["has_floorplan_asset"])
    return f["case_status"] in CASE_NEEDS_OPERATOR


def view(property_id: str) -> Dict:
    """Vista completa para plantillas y para la API interna. Recalcula y persiste el estado."""
    f = facts(property_id)
    estado = derive_status(f)
    if f["property"]["status"] != estado:
        store.ex("UPDATE properties SET status=?, updated_at=? WHERE property_id=?",
                 (estado, store.now(), property_id))
        f["property"]["status"] = estado
    f["status"] = estado
    f["customer_label"] = CUSTOMER_LABEL.get(estado, "En preparación")
    f["needs_internal_review"] = needs_internal_review(f)
    return f


def listing() -> List[Dict]:
    return [view(r["property_id"]) for r in
            store.q("SELECT property_id FROM properties ORDER BY created_at DESC")]


def needing_review() -> List[Dict]:
    """§17 — la cola interna. Sale de los hechos, no de una bandera que alguien tenga que mantener."""
    return [v for v in listing() if v["needs_internal_review"]]
