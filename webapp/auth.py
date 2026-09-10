"""E27 §16 — protección mínima razonable: una sola cuenta, HTTP Basic.

No hay multiempresa, ni roles, ni invitaciones, ni recuperación de contraseña: es una herramienta
interna de una persona. Lo único que no es negociable es que no quede abierta a Internet
aceptando uploads anónimos.

Fail-closed: sin `ESCALIMETRO_PASSWORD` la app NO arranca en producción. Un despliegue al que se
le olvidó la variable se cae con un mensaje claro en vez de quedar público sin que nadie lo note.
"""
from __future__ import annotations

import hmac
import os
from functools import wraps

from flask import Response, request

USER = os.environ.get("ESCALIMETRO_USER", "joaquin")
PASSWORD = os.environ.get("ESCALIMETRO_PASSWORD", "")
DEV = os.environ.get("ESCALIMETRO_DEV", "") == "1"


class MissingPassword(RuntimeError):
    pass


def check_config() -> None:
    if not PASSWORD and not DEV:
        raise MissingPassword(
            "Falta ESCALIMETRO_PASSWORD. La app no arranca sin contraseña para no quedar "
            "abierta en Internet. Para desarrollo local: ESCALIMETRO_DEV=1.")


def _ok(u: str, p: str) -> bool:
    # compare_digest en ambos campos: no se filtra por tiempo cuál de los dos falló
    return hmac.compare_digest(u or "", USER) and hmac.compare_digest(p or "", PASSWORD)


def require(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if DEV and not PASSWORD:
            return fn(*a, **kw)
        auth = request.authorization
        if auth is None or not _ok(auth.username or "", auth.password or ""):
            return Response(
                "Escalímetro — herramienta interna.", 401,
                {"WWW-Authenticate": 'Basic realm="Escalimetro", charset="UTF-8"'})
        return fn(*a, **kw)
    return wrapper
