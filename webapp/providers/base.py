"""E31 §16 — lo que comparten los tres adaptadores: transporte HTTP, multipart, secretos y errores.

Reglas que valen para cualquier adaptador y que se hacen cumplir acá:

* **la clave nunca sale de este paquete.** Se lee del entorno en el momento de la llamada, viaja en
  una cabecera y no se guarda en ningún objeto que pueda serializarse. `sanitize()` recorre lo que
  el proveedor devolvió y borra cualquier cadena que coincida con una credencial, por si un
  proveedor la refleja en un mensaje de error;
* **sin dependencias nuevas.** `urllib` de la biblioteca estándar; el multipart se arma a mano.
  Tres SDKs distintos con tres ritmos de versiones es exactamente la deuda que un piloto no
  necesita;
* **el transporte es un punto de inyección.** Los tests reemplazan `TRANSPORT` por una función
  que devuelve respuestas grabadas y así verifican la forma de la petición, el parseo y el manejo
  de errores sin gastar un centavo ni fingir que el benchmark ocurrió.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..domain import visual

#: Variables de entorno de credencial. SÓLO nombres; los valores no existen en el repo.
SECRET_VARS = ("GEMINI_API_KEY", "OPENAI_API_KEY", "BFL_API_KEY")

DEFAULT_TIMEOUT_S = int(os.environ.get("ESCALIMETRO_STAGING_TIMEOUT_S", "180"))


class ProviderError(visual.VisualStagingError):
    """El proveedor no devolvió una imagen utilizable. Lleva el estado HTTP y un mensaje saneado."""

    def __init__(self, provider: str, msg: str, status: Optional[int] = None):
        self.provider, self.status = provider, status
        super().__init__(f"[{provider}] " + (f"HTTP {status}: " if status else "") + sanitize(msg))


def env_key(var: str) -> Optional[str]:
    v = (os.environ.get(var) or "").strip()
    return v or None


def sanitize(obj: Any) -> Any:
    """Borra de cualquier estructura toda cadena que contenga una credencial del entorno."""
    secretos = [s for s in (env_key(v) for v in SECRET_VARS) if s]
    if isinstance(obj, str):
        for s in secretos:
            obj = obj.replace(s, "***")
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------------------------
# transporte
# ---------------------------------------------------------------------------------------------
def _urllib_transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes],
                      timeout: int) -> Tuple[int, Dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:      # noqa: S310 (https fijo)
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""


#: Punto de inyección. Los tests lo reemplazan; producción usa urllib.
TRANSPORT = _urllib_transport


def request(method: str, url: str, headers: Dict[str, str], body: Optional[bytes] = None,
            timeout: int = DEFAULT_TIMEOUT_S) -> Tuple[int, Dict[str, str], bytes]:
    return TRANSPORT(method, url, headers, body, timeout)


def request_json(provider: str, method: str, url: str, headers: Dict[str, str],
                 body: Optional[bytes] = None, timeout: int = DEFAULT_TIMEOUT_S) -> Dict:
    status, _, raw = request(method, url, headers, body, timeout)
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        data = {"_raw": raw[:500].decode("utf-8", "replace")}
    if status >= 400:
        raise ProviderError(provider, _error_text(data), status)
    return data


def _error_text(data: Dict) -> str:
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(err or data)[:500]


def multipart(fields: Dict[str, str], files: Sequence[Tuple[str, str, bytes, str]]
              ) -> Tuple[str, bytes]:
    """Codifica un formulario multipart/form-data. `files` = [(campo, nombre, bytes, mime)]."""
    limite = "----escalimetro-" + uuid.uuid4().hex
    partes: List[bytes] = []
    for k, v in fields.items():
        partes.append((f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n")
                      .encode("utf-8"))
    for campo, nombre, blob, mime in files:
        partes.append((f"--{limite}\r\nContent-Disposition: form-data; name=\"{campo}\"; "
                       f"filename=\"{nombre}\"\r\nContent-Type: {mime}\r\n\r\n").encode("utf-8"))
        partes.append(blob + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={limite}", b"".join(partes)


def image_dims(blob: bytes) -> Optional[Tuple[int, int]]:
    try:
        import io                                             # noqa: PLC0415
        from PIL import Image                                 # noqa: PLC0415
        with Image.open(io.BytesIO(blob)) as im:
            return im.width, im.height
    except Exception:                                         # noqa: BLE001
        return None


def nearest_aspect(w: int, h: int, opciones: Sequence[str]) -> str:
    """La relación de aspecto soportada más cercana a la de la foto. Preservar la proporción es
    parte del contrato (§8), así que no se pide 1:1 a ciegas."""
    objetivo = w / float(h)

    def val(s: str) -> float:
        a, b = s.split(":")
        return float(a) / float(b)
    return min(opciones, key=lambda s: abs(val(s) - objetivo))
