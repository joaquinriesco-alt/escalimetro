"""E47.4 (cierra E46-H10) — guarda global de mismo origen para todo POST de la app.

La app se autentica con HTTP Basic, que el navegador reenvía solo: sin esta guarda, una página
ajena puede mandar un formulario con la sesión del operador a cualquier ruta con efectos
(staging, benchmark con proveedor, pedidos, /upload…). E37 ya protegía `/lab/reconstruction` y el
piloto E44 con `reconstruction._guardas`; esa guarda ahora vive acá y la app entera la aplica en
un solo `before_request`, antes de ejecutar ninguna vista.

Dos grados, a propósito:

* **estricto** (E37 y piloto): un POST sin `Origin` ni `Referer` también se rechaza. Esas rutas
  pueden gastar dinero o revelar el plano real, y su contrato ya era ese;
* **común** (el resto): un POST **sin** ninguna de las dos cabeceras se deja pasar, porque así
  trabajan los clientes internos y las automatizaciones existentes (curl, scripts, tests) y un
  navegador siempre manda `Origin` en un POST entre sitios. En cambio, cualquier cabecera que
  esté y apunte a otro host —incluido `Origin: null`— se rechaza.
"""
from __future__ import annotations

from urllib.parse import urlparse

from flask import abort, request

#: Rutas POST que por diseño aceptan un envío desde otro sitio (superficie pública de E40/E41,
#: sin Basic Auth ni sesión que un tercero pueda aprovechar). Se enumeran por regla, no por
#: prefijo: una ruta nueva bajo `/planos/` NO queda eximida sola.
EXENTAS = frozenset({"/planos/solicitar"})

#: Prefijos cuyo contrato es estricto (ver arriba).
ESTRICTAS = ("/lab/reconstruction", "/lab/campaign/e44")


def origen_ajeno(estricto: bool) -> bool:
    """True si el POST en curso no viene de este mismo origen."""
    # Detrás del proxy de Railway la app ve http aunque el navegador vea https: el esquema público
    # es el que declara el proxy. Un formulario de otro sitio no puede fijar esa cabecera.
    esquema = (request.headers.get("X-Forwarded-Proto") or request.scheme).split(",")[0].strip()
    vistos = [request.headers.get(c) for c in ("Origin", "Referer")]
    vistos = [v for v in vistos if v is not None]
    if not vistos:
        return estricto
    return any((urlparse(v).scheme, urlparse(v).netloc) != (esquema, request.host) for v in vistos)


def guardar():
    """`before_request` de la app. Falla con 403 antes de que corra la vista."""
    if request.method != "POST":
        return None
    regla = request.url_rule.rule if request.url_rule is not None else None
    if regla in EXENTAS:
        return None
    estricto = request.path.startswith(ESTRICTAS)
    if origen_ajeno(estricto):
        abort(403)
    return None


def instalar(app) -> None:
    app.before_request(guardar)
