"""E17.2 §17 — TRAER UNA URL DE AFUERA SIN ABRIRLE LA PUERTA A CUALQUIERA.

=================================================================================================
Por qué este archivo existe separado
=================================================================================================
Pegar una URL y que el servidor la busque es la superficie de riesgo más clásica que hay: **SSRF**.
Quien controla la URL controla a qué dirección se conecta nuestro servidor, y desde adentro de una
red el servidor alcanza cosas que el atacante no: el endpoint de metadatos del proveedor de nube
(169.254.169.254, credenciales de instancia servidas en texto plano), bases de datos que sólo
escuchan en loopback, paneles internos sin autenticación.

Por eso la adquisición vive aparte del análisis y no comparte nada con él. Acá sólo se decide una
cosa: **si esta dirección se puede pedir, y cuánto**. Nada de esto sabe qué es un aviso.

=================================================================================================
Las defensas, y qué ataque para cada una
=================================================================================================
* **esquema** — sólo `http`/`https`. Cierra `file:///etc/passwd`, `ftp://`, `gopher://` (que sirvió
  históricamente para hablarle a Redis) y `data:`.
* **resolución previa** — se resuelven TODOS los registros del host y se rechaza si cualquiera cae
  en un rango privado, de loopback, link-local, multicast o reservado. Se miran todos y no sólo el
  primero porque un host puede resolver a una IP pública y a `127.0.0.1` a la vez.
* **redirecciones a mano** — cada salto se vuelve a validar. Un `302` hacia `http://169.254.169.254`
  es la forma estándar de saltarse un filtro que sólo mira la URL original.
* **timeout, tamaño y tipo** — para que una respuesta infinita o un binario de 2 GB no nos tumbe.
  El corte es por bytes leídos, no por `Content-Length`, que lo escribe el servidor remoto.
* **nada se ejecuta** — lo que baja es texto o bytes de imagen. No se evalúa JavaScript en el
  servidor, y por eso mismo la extracción se apoya en payloads estructurados y no en render.

Riesgo residual que queda escrito porque no se cierra acá: entre que se resuelve el nombre y que se
abre la conexión, el DNS podría cambiar de respuesta (*rebinding*). Cerrarlo del todo exige conectar
por IP y mandar el `Host` a mano, lo que rompe TLS con SNI y vale su propio trabajo. Para una URL
que pega voluntariamente un operador interno, la ventana es aceptable; para una superficie pública,
no lo sería.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

#: Sólo estos dos. Todo lo demás se rechaza por esquema, antes de mirar nada más.
ALLOWED_SCHEMES = ("http", "https")
#: Lo que aceptamos como página. Una imagen entra por `fetch_image`, con su propia lista.
HTML_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/jpg")

TIMEOUT = 12
MAX_HTML_BYTES = 3_000_000
MAX_IMAGE_BYTES = 12_000_000
MAX_REDIRECTS = 5
#: Un navegador cualquiera. NO es evasión de anti-bot: es el mínimo para que un servidor no nos
#: devuelva una página degradada por no declarar nada. Si un portal nos bloquea, se reporta
#: bloqueado (§16) y no se insiste con trucos.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

#: Motivos de fallo. Viajan hasta la pantalla: «no pudimos leerla» sin decir por qué no le sirve
#: a nadie, y sobre todo no se puede distinguir un portal que bloquea de un bug nuestro.
BAD_SCHEME = "BAD_SCHEME"
BLOCKED_HOST = "BLOCKED_HOST"
DNS_FAILED = "DNS_FAILED"
HTTP_BLOCKED = "HTTP_BLOCKED"
HTTP_ERROR = "HTTP_ERROR"
TOO_MANY_REDIRECTS = "TOO_MANY_REDIRECTS"
BAD_CONTENT_TYPE = "BAD_CONTENT_TYPE"
TOO_LARGE = "TOO_LARGE"
TIMEOUT_REACHED = "TIMEOUT"
NETWORK_ERROR = "NETWORK_ERROR"

REASON_LABEL = {
    BAD_SCHEME: "la dirección no es http ni https",
    BLOCKED_HOST: "esa dirección apunta a la red interna",
    DNS_FAILED: "no pudimos resolver ese dominio",
    HTTP_BLOCKED: "el portal bloqueó el pedido",
    HTTP_ERROR: "el portal respondió con un error",
    TOO_MANY_REDIRECTS: "demasiadas redirecciones",
    BAD_CONTENT_TYPE: "eso no es una página web",
    TOO_LARGE: "la respuesta es demasiado grande",
    TIMEOUT_REACHED: "el portal tardó demasiado",
    NETWORK_ERROR: "no pudimos conectarnos",
}


class FetchError(RuntimeError):
    def __init__(self, reason: str, detail: str = ""):
        self.reason, self.detail = reason, detail
        super().__init__(f"{reason}: {detail or REASON_LABEL.get(reason, '')}")


def _is_public(ip: str) -> bool:
    """¿Esta dirección está en la Internet pública?

    `is_global` de la librería estándar ya cubre loopback, privadas, link-local —incluido el
    169.254.169.254 de los metadatos de nube—, multicast y reservadas. Se usa eso en vez de una
    lista propia de rangos: una lista escrita a mano envejece y se le escapa un bloque."""
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def resolve_public(host: str) -> List[str]:
    """Todas las direcciones del host, o error si CUALQUIERA no es pública.

    Se miran todas y no sólo la primera: un nombre puede resolver a una IP pública y a 127.0.0.1
    al mismo tiempo, y entonces qué dirección se usa depende del orden que devuelva el resolver."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError) as e:
        raise FetchError(DNS_FAILED, f"{host}: {e}") from e
    ips = sorted({i[4][0] for i in infos})
    if not ips:
        raise FetchError(DNS_FAILED, host)
    malas = [ip for ip in ips if not _is_public(ip)]
    if malas:
        raise FetchError(BLOCKED_HOST, f"{host} resuelve a {', '.join(malas)}")
    return ips


def validate(url: str) -> Tuple[str, List[str]]:
    """Valida una URL y devuelve (url normalizada, ips). Lanza `FetchError` si no se puede pedir."""
    p = urlparse((url or "").strip())
    if p.scheme.lower() not in ALLOWED_SCHEMES:
        raise FetchError(BAD_SCHEME, p.scheme or "(sin esquema)")
    if not p.hostname:
        raise FetchError(BAD_SCHEME, "sin dominio")
    # una IP escrita directamente se valida igual: `http://127.0.0.1` no pasa por DNS
    if not _is_public(p.hostname):
        try:
            ipaddress.ip_address(p.hostname)
            raise FetchError(BLOCKED_HOST, p.hostname)
        except ValueError:
            pass                                              # es un nombre: lo resuelve el paso siguiente
    ips = resolve_public(p.hostname)
    return urlunparse(p), ips


def _open(url: str, accept: str, timeout: int):
    import urllib.error                                        # noqa: PLC0415
    import urllib.request                                      # noqa: PLC0415
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": accept,
        "Accept-Language": "es-CL,es;q=0.9", "Connection": "close"})
    try:
        # `redirects=False` a mano: el handler por defecto sigue saltos sin revalidar el destino,
        # que es justamente por donde se cuela un 302 hacia la red interna.
        return _no_redirect_opener().open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return e                                           # lo maneja el bucle de redirecciones
        if e.code in (401, 403, 429) or e.code == 451:
            raise FetchError(HTTP_BLOCKED, f"HTTP {e.code}") from e
        raise FetchError(HTTP_ERROR, f"HTTP {e.code}") from e
    except socket.timeout as e:
        raise FetchError(TIMEOUT_REACHED, str(e)) from e
    except urllib.error.URLError as e:
        motivo = TIMEOUT_REACHED if isinstance(e.reason, socket.timeout) else NETWORK_ERROR
        raise FetchError(motivo, str(e.reason)) from e
    except OSError as e:
        raise FetchError(NETWORK_ERROR, str(e)) from e


def _no_redirect_opener():
    """Un opener que NO sigue redirecciones: las devuelve para que el bucle las revalide.

    `HTTPRedirectHandler.redirect_request` devolviendo `None` es la forma documentada de decirle a
    urllib «no sigas»; entonces la redirección sale como `HTTPError` y el bucle de `_fetch` puede
    volver a validar el destino, que es exactamente lo que un 302 hacia la red interna busca
    evitar."""
    import urllib.request                                      # noqa: PLC0415

    class _Sin(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return urllib.request.build_opener(_Sin)


def _read_capped(resp, limite: int) -> bytes:
    """Lee hasta el límite y falla si hay más. El corte es por bytes REALMENTE leídos: el
    `Content-Length` lo escribe el servidor remoto y puede mentir."""
    datos = resp.read(limite + 1)
    if len(datos) > limite:
        raise FetchError(TOO_LARGE, f"más de {limite} bytes")
    return datos


def _fetch(url: str, accept: str, types: Tuple[str, ...], limite: int,
           timeout: int) -> Dict:
    from urllib.parse import urljoin                           # noqa: PLC0415
    actual, saltos = url, []
    for _ in range(MAX_REDIRECTS + 1):
        actual, ips = validate(actual)                         # se revalida EN CADA SALTO
        resp = _open(actual, accept, timeout)
        code = getattr(resp, "code", None) or getattr(resp, "status", 200)
        if code in (301, 302, 303, 307, 308):
            destino = resp.headers.get("Location")
            if not destino:
                raise FetchError(HTTP_ERROR, f"HTTP {code} sin destino")
            saltos.append(actual)
            actual = urljoin(actual, destino)
            continue
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if types and ctype and not any(ctype == t for t in types):
            raise FetchError(BAD_CONTENT_TYPE, ctype)
        datos = _read_capped(resp, limite)
        return {"url": actual, "final_url": actual, "redirects": saltos, "ips": ips,
                "status": code, "content_type": ctype, "bytes": datos, "size": len(datos)}
    raise FetchError(TOO_MANY_REDIRECTS, url)


def fetch_page(url: str, timeout: int = TIMEOUT) -> Dict:
    """Baja una página. Devuelve el HTML decodificado y la procedencia del pedido."""
    r = _fetch(url, "text/html,application/xhtml+xml,*/*;q=0.8", HTML_TYPES,
               MAX_HTML_BYTES, timeout)
    r["html"] = r.pop("bytes").decode("utf-8", "replace")
    return r


def fetch_image(url: str, timeout: int = TIMEOUT) -> Dict:
    """Baja una imagen. Mismas defensas; sólo cambian el tipo aceptado y el tope."""
    return _fetch(url, "image/avif,image/webp,image/*,*/*;q=0.8", IMAGE_TYPES,
                  MAX_IMAGE_BYTES, timeout)
