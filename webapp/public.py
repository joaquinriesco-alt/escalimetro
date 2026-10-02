"""E40/E41 — la única superficie pública de ESCALÍMETRO.

Todo lo demás de la app está detrás de HTTP Basic (`auth.require`, ruta por ruta). Esta superficie
es mínima y aislada a propósito: sus plantillas no extienden `base.html` (cuyo menú enlaza
herramientas internas) y no importa el motor ni la cola de trabajo.

E41 le agrega lo único que escribe: recibir un pedido de Plano Corporativo (email + plano). Sólo
recepción. Persiste en la tabla `plano_requests` y en `DATA_DIR/plano_requests/<id>/`, y nada más:
no corre el motor, no llama a ningún proveedor, no envía emails. Lo único que lee de la base es el
pedido que acaba de crear, por su id opaco, para confirmarlo.
"""
from __future__ import annotations

import os
import re
import shutil
import uuid

from flask import Blueprint, abort, redirect, render_template, request, url_for

from . import intake, store

bp = Blueprint("public", __name__, url_prefix="/planos")

#: Deliberadamente simple: una dirección con arroba y un dominio con punto. Validar de verdad un
#: email sólo se logra enviándole algo, y E41 no envía.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_MAX = 254
_ID = re.compile(r"^pc_[0-9a-f]{32}$")
ESTADO_INICIAL = "RECEIVED"


@bp.get("/")
def landing():
    return render_template("public/landing.html")


@bp.get("/solicitar")
def solicitar():
    return render_template("public/solicitar.html", errores={}, email="")


@bp.post("/solicitar")
def solicitar_post():
    email = (request.form.get("email") or "").strip()
    archivo = request.files.get("plano")
    errores = {}
    if not email or len(email) > _EMAIL_MAX or not _EMAIL.match(email):
        errores["email"] = "Escribe un email válido, por ejemplo nombre@dominio.cl."
    nombre = (archivo.filename if archivo else "") or ""
    ext = ""
    if not nombre:
        errores["plano"] = "Adjunta el plano en PDF, JPG o PNG."
    else:
        try:
            ext = intake.ext_of(nombre)
        except intake.IntakeError:
            errores["plano"] = "Formato no aceptado. Sólo PDF, JPG o PNG."
    if errores:
        return render_template("public/solicitar.html", errores=errores, email=email), 400

    request_id = "pc_" + uuid.uuid4().hex
    rdir = store.plano_request_dir(request_id)
    destino = os.path.join(rdir, "plano" + ext)
    try:
        os.makedirs(rdir, exist_ok=True)
        archivo.save(destino)
        mb = os.path.getsize(destino) / 1e6
        if mb > intake.MAX_UPLOAD_MB:
            errores["plano"] = f"El archivo pesa {mb:.1f} MB; el máximo es {intake.MAX_UPLOAD_MB} MB."
        elif not intake.sniff_ok(destino, ext):
            errores["plano"] = "El contenido del archivo no coincide con su formato."
        if not errores:
            store.ex("INSERT INTO plano_requests(request_id, email, plan_file, original_filename, "
                     "mime, size_bytes, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (request_id, email, os.path.basename(destino), os.path.basename(nombre)[:200],
                      intake.ALLOWED[ext], os.path.getsize(destino), ESTADO_INICIAL, store.now()))
    except Exception:
        # Sin pedido no hay archivo: un fallo a medias no deja huérfanos en el volumen.
        shutil.rmtree(rdir, ignore_errors=True)
        raise
    if errores:
        shutil.rmtree(rdir, ignore_errors=True)
        return render_template("public/solicitar.html", errores=errores, email=email), 400
    # POST/Redirect/GET: refrescar la confirmación no reenvía el formulario.
    return redirect(url_for("public.recibido", request_id=request_id), code=303)


@bp.get("/recibido/<request_id>")
def recibido(request_id: str):
    if not _ID.match(request_id):
        abort(404)
    pedido = store.q1("SELECT request_id, created_at FROM plano_requests WHERE request_id=?",
                      (request_id,))
    if pedido is None:
        abort(404)
    return render_template("public/recibido.html", pedido=pedido)
