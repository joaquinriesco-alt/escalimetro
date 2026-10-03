"""E43 — entrega de un Plano Corporativo aprobado, por enlace público opaco.

Sin Flask y sin motor: sólo base + capa de assets. Lo usan la bandeja interna (aprobar) y la ruta
pública (resolver un token). Dos reglas de diseño:

1. **Lo aprobado es una copia.** `floorplan.publish_commercial_floorplan` purga el comercial
   anterior al regenerar; si el enlace apuntara a ese asset, regenerar cambiaría en silencio lo que
   ve el cliente. Al aprobar se congela una copia `FLOORPLAN_DELIVERED`, y regenerar no la toca.
2. **El token sólo abre el asset de su pedido.** Se resuelve token → pedido → `assets.get(asset_id,
   property_id)`, la barrera de E28.2; nadie pasa un path ni un asset_id.

Aprobar nunca envía nada ni marca «entregado»: el estado es `READY_FOR_DELIVERY`, porque este
sistema no sabe si el cliente recibió el enlace.
"""
from __future__ import annotations

import os
import re
import secrets
from typing import Dict, Optional

from . import store
from .domain import assets

READY_FOR_DELIVERY = "READY_FOR_DELIVERY"
#: 32 bytes aleatorios en base64 urlsafe sin relleno = 43 caracteres.
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class EntregaError(RuntimeError):
    """No se puede aprobar: el mensaje se le muestra al operador."""


def candidato(property_id: str) -> Optional[Dict]:
    """El plano comercial actual de la propiedad (`publish_commercial_floorplan` deja uno solo)."""
    return assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL)


def aprobar(request_id: str, asset_id: str) -> Optional[str]:
    """Aprueba `asset_id` —que debe ser el candidato actual de la propiedad del pedido— y devuelve
    el token. Idempotente: si el pedido ya está aprobado devuelve None y no cambia nada (ni el
    token ni el asset); cambiar lo aprobado exigiría una revocación explícita que E43 no define."""
    ped = store.q1("SELECT * FROM plano_requests WHERE request_id=?", (request_id,))
    if ped is None or not ped["property_id"]:
        raise EntregaError("el pedido no tiene propiedad preparada")
    if ped["delivery_token"]:
        return None
    pid = ped["property_id"]
    cand = candidato(pid)
    # Se aprueba lo que el operador vio: si regeneró entre la vista previa y el click, no coincide.
    if cand is None or cand["asset_id"] != asset_id:
        raise EntregaError("el candidato cambió o no existe: revísalo de nuevo antes de aprobar")
    origen = assets.path_of(cand)
    if not os.path.isfile(origen):
        raise EntregaError("el archivo del candidato no está en disco")
    with open(origen, "rb") as fh:
        blob = fh.read()
    copia = assets.save_bytes(pid, assets.FLOORPLAN_DELIVERED, "plano_corporativo.png", blob,
                              cand["mime_type"], source_asset_id=cand["asset_id"],
                              metadata={"request_id": request_id, "sha256_candidato": cand["sha256"]})
    token = secrets.token_urlsafe(32)
    # Compare-and-set: dos aprobaciones simultáneas no pueden dejar dos tokens.
    conn = store.connect()
    try:
        cur = conn.execute(
            "UPDATE plano_requests SET delivery_token=?, delivery_asset_id=?, approved_at=?, status=? "
            "WHERE request_id=? AND delivery_token IS NULL",
            (token, copia, store.now(), READY_FOR_DELIVERY, request_id))
        conn.commit()
    except Exception:
        conn.rollback()
        assets.delete(copia, pid)
        raise
    if cur.rowcount != 1:
        assets.delete(copia, pid)
        return None
    return token


def resolver(token: str) -> Optional[Dict]:
    """token → {asset, mime, path, created_at} del plano aprobado, o None. Nada interno sale de acá."""
    if not isinstance(token, str) or not _TOKEN.match(token):
        return None
    ped = store.q1("SELECT property_id, delivery_asset_id, approved_at FROM plano_requests "
                   "WHERE delivery_token=?", (token,))
    if ped is None or not ped["delivery_asset_id"] or not ped["property_id"]:
        return None
    a = assets.get(ped["delivery_asset_id"], ped["property_id"])
    if a is None or a["kind"] != assets.FLOORPLAN_DELIVERED:
        return None
    path = assets.path_of(a)
    if not os.path.isfile(path):
        return None
    return {"path": path, "mime": a["mime_type"], "approved_at": ped["approved_at"]}
