"""E40 — la única superficie pública de ESCALÍMETRO.

Todo lo demás de la app está detrás de HTTP Basic (`auth.require`, ruta por ruta). Esta superficie
es nueva, mínima y aislada a propósito: no lee la base, no toca DATA_DIR ni el motor, y sus
plantillas no extienden `base.html` (cuyo menú enlaza herramientas internas). Así abrirla no puede
exponer casos, propiedades, corridas ni uploads: no tiene acceso a ellos.

Sólo páginas estáticas bajo `/planos`. El pedido real (formulario) es de la TASK siguiente: por eso
`/planos/solicitar` dice con honestidad que todavía no se puede pedir.
"""
from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("public", __name__, url_prefix="/planos")


@bp.get("/")
def landing():
    return render_template("public/landing.html")


@bp.get("/solicitar")
def solicitar():
    return render_template("public/solicitar.html")
