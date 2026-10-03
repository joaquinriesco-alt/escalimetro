"""E42 — bandeja INTERNA de pedidos de Plano Corporativo (los que E41 recibe en público).

Cierra la brecha entre el pedido y el LAB: un pedido `RECEIVED` se convierte, con una sola acción,
en una propiedad real del LAB que ya trae el plano del cliente como `FLOORPLAN_ORIGINAL`. El
operador no vuelve a descargar ni a subir el archivo.

Lo que NO hace, a propósito: no corre el motor, no llama a ningún proveedor, no envía emails y no
entrega nada al cliente. Deja la propiedad lista y el operador sigue en el LAB con el flujo de
siempre. Todas las rutas están detrás de HTTP Basic (`auth.require`); nada de esto es público.
"""
from __future__ import annotations

import os
import re

from flask import Blueprint, abort, redirect, render_template, url_for
from werkzeug.datastructures import FileStorage

from . import auth, store
from .domain import assets, entitlements, grants, properties

bp = Blueprint("pedidos", __name__, url_prefix="/lab/pedidos")

_ID = re.compile(r"^pc_[0-9a-f]{32}$")
RECEIVED = "RECEIVED"
#: Transitorio: lo ocupa quien reclamó el pedido mientras construye la propiedad. Si el proceso
#: muere acá el pedido queda así, a la vista, y no ofrece botón: mejor visible que duplicado.
PREPARING = "PREPARING"
IN_PROGRESS = "IN_PROGRESS"


class PrepararError(RuntimeError):
    """El pedido no se pudo preparar; el pedido queda como estaba (RECEIVED)."""


def _reclamar(request_id: str) -> bool:
    """Compare-and-set atómico RECEIVED → PREPARING. Sólo un llamador lo gana: el doble click o el
    retry ven rowcount 0 y no crean nada. Va directo a la conexión porque `store.ex` no lo devuelve."""
    conn = store.connect()
    try:
        cur = conn.execute("UPDATE plano_requests SET status=? WHERE request_id=? AND status=?",
                           (PREPARING, request_id, RECEIVED))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return cur.rowcount == 1


def _deshacer(request_id: str, pid: str | None) -> None:
    """Borra lo que alcanzó a crearse y devuelve el pedido a RECEIVED, para que reintentar sea
    seguro y no quede una propiedad utilizable huérfana."""
    if pid:
        store.ex("DELETE FROM property_assets WHERE property_id=?", (pid,))
        store.ex("DELETE FROM pack_grants WHERE property_id=?", (pid,))
        store.ex("DELETE FROM properties WHERE property_id=?", (pid,))
        assets.drop_property_files(pid)
    store.ex("UPDATE plano_requests SET status=?, property_id=NULL, prepared_at=NULL "
             "WHERE request_id=? AND status=?", (RECEIVED, request_id, PREPARING))


def preparar(request_id: str) -> str | None:
    """Convierte el pedido en una propiedad del LAB. Devuelve su property_id, o None si el pedido
    ya no estaba en RECEIVED (otro lo reclamó o ya está preparado): en ese caso no hace nada."""
    if not _reclamar(request_id):
        return None
    pid = None
    try:
        ped = store.q1("SELECT * FROM plano_requests WHERE request_id=?", (request_id,))
        # El nombre sale de la base pero se reduce a su basename: nunca puede salirse del directorio.
        origen = os.path.join(store.plano_request_dir(request_id), os.path.basename(ped["plan_file"]))
        if not os.path.isfile(origen):
            raise PrepararError("el archivo del pedido no está en disco")
        pid = properties.create("Plano Corporativo · " + ped["email"], "OFFICE",
                                reference=request_id, notes="Pedido público de Plano Corporativo.")
        grants.grant_and_assign(entitlements.default_product(), pid, source="SIMULATED_LAB",
                                note="pedido público de Plano Corporativo (E42)")
        nombre = ped["original_filename"] or ped["plan_file"]
        if os.path.splitext(nombre)[1].lower() != os.path.splitext(ped["plan_file"])[1].lower():
            nombre = ped["plan_file"]
        # Pasa por `save_upload`, la misma capa del LAB: mismas validaciones de extensión, tamaño y
        # contenido, y el nombre guardado lo genera ella, no el cliente.
        with open(origen, "rb") as fh:
            assets.save_upload(pid, FileStorage(stream=fh, filename=nombre),
                               assets.FLOORPLAN_ORIGINAL)
        properties.touch(pid)
        store.ex("UPDATE plano_requests SET status=?, property_id=?, prepared_at=? "
                 "WHERE request_id=? AND status=?",
                 (IN_PROGRESS, pid, store.now(), request_id, PREPARING))
    except Exception:
        _deshacer(request_id, pid)
        raise
    return pid


@bp.get("/")
@auth.require
def bandeja():
    filas = store.q("SELECT request_id, created_at, email, original_filename, status, property_id "
                    "FROM plano_requests ORDER BY created_at DESC, request_id")
    return render_template("lab/pedidos.html", filas=filas)


@bp.post("/<request_id>/preparar")
@auth.require
def preparar_post(request_id: str):
    if not _ID.match(request_id):
        abort(404)
    ped = store.q1("SELECT property_id FROM plano_requests WHERE request_id=?", (request_id,))
    if ped is None:
        abort(404)
    pid = preparar(request_id)
    if pid is None:
        # Ya preparado (o en preparación): idempotente, se lleva al operador a la propiedad si existe.
        ped = store.q1("SELECT property_id FROM plano_requests WHERE request_id=?", (request_id,))
        if ped["property_id"]:
            return redirect(url_for("lab.propiedad", property_id=ped["property_id"]), code=303)
        return redirect(url_for("pedidos.bandeja"), code=303)
    return redirect(url_for("lab.propiedad", property_id=pid), code=303)
