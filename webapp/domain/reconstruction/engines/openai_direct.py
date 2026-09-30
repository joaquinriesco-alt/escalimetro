"""E37 §Baseline multimodal — OpenAI directo: fotos + datos declarados → contrato v1, en un paso.

Es el primer motor real y a propósito el más simple: un modelo multimodal mira las fotos y
devuelve la representación estructurada, con salida JSON estricta contra el esquema del contrato.
No hay reconstrucción geométrica intermedia; ese es el techo que el laboratorio tiene que medir.

Reglas que este adaptador cumple:

* **sin credencial no hay red.** `availability()` mira la PRESENCIA de la clave; `reconstruct()`
  la vuelve a mirar antes de armar nada. Sin clave el motor aparece UNAVAILABLE /
  MISSING_CREDENTIAL y nunca simula un resultado;
* **una llamada es un gasto.** Este adaptador no se llama solo: lo invoca la cola cuando un
  operador apretó «Generar» con la confirmación marcada. Ni los tests, ni el arranque, ni una
  migración pasan por acá con red (los tests reemplazan `providers.base.TRANSPORT`);
* **el modelo se congela al crear la corrida.** `default_params()` lee la variable de entorno en
  ese momento y el valor queda en la corrida; ejecutarla después con otro entorno no la cambia;
* **se guarda lo que se mandó**, salvo las imágenes: instrucciones, texto, esquema, versión del
  prompt y su sha256, cuántas fotos y a qué tamaño. Con eso una corrida se puede auditar;
* **sin reintentos.** Reintentar es crear otra corrida, que queda registrada;
* **costo honesto.** No hay precio de lista para este modelo en el repo, así que el costo queda
  `unknown` y se guardan los tokens que el proveedor reporte. Un precio inventado es peor que
  ninguno.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from ....providers import base as http
from .. import contract
from .base import (AVAILABLE, CORRECTION, MISSING_CREDENTIAL, UNAVAILABLE, Availability,
                   EngineAdapter, EngineError, EngineRequest, EngineResult)

ENGINE_ID = "openai_direct"
KEY_ENV = "OPENAI_API_KEY"
MODEL_ENV = "ESCALIMETRO_RECON_OPENAI_MODEL"
#: El baseline que pide E37. Configurable por entorno sin tocar código.
DEFAULT_MODEL = "gpt-5.6-sol"
URL = "https://api.openai.com/v1/responses"
PROMPT_VERSION = "recon_openai_direct_v1"

INSTRUCTIONS = """Eres un motor de reconstrucción de plantas del laboratorio interno de ESCALÍMETRO.
Recibes fotos de una propiedad y, a veces, datos que declaró el operador. Devuelves un PLANO
ESQUEMÁTICO COMERCIAL como representación estructurada, siguiendo exactamente el esquema JSON.

Reglas:
1. Es referencial, no un levantamiento. Nunca finjas certeza geométrica.
2. No inventes geometría para que el plano se vea completo. Si sabes que un recinto existe pero no
   dónde está, déjalo con polygon = null y explica por qué en uncertainty.
3. Cada recinto, cada conexión y cada relación de posición cita su evidencia: los ids de las
   fotos, tal como se indican antes de cada imagen (por ejemplo "rca_..."), y qué se observa.
4. Coordenadas: un marco normalizado 0..1 que cubre la huella de la planta; x crece hacia la
   derecha, y crece hacia abajo. Polígonos de al menos 3 vértices dentro del marco. Los recintos
   no deberían superponerse.
5. footprint.width_m y footprint.depth_m sólo si puedes estimarlos (por ejemplo, de la superficie
   declarada); si no, null. footprint.basis dice de dónde sale la escala.
6. confidence va de 0 a 1 y tiene que ser honesta.
7. Si la evidencia no alcanza para una planta útil, outcome = INSUFFICIENT_EVIDENCE y
   missing_evidence dice qué falta.
8. En una corrección, parte del plano anterior, aplica sólo lo que pide la instrucción y conserva
   todo lo demás; explícalo en correction.understood_as y correction.changes. Si la instrucción es
   ambigua (no queda claro qué recinto o qué cambio), no adivines: outcome =
   CLARIFICATION_REQUIRED, con una pregunta y opciones en clarification, y devuelve el plano
   anterior sin cambios.
9. Los datos declarados vienen del operador y pueden estar mal: úsalos, pero si las fotos los
   contradicen, dilo en uncertainties.
10. Responde en castellano. contract = "escalimetro.reconstruction.v1"."""


def _prompt_sha() -> str:
    h = hashlib.sha256()
    h.update(PROMPT_VERSION.encode("utf-8"))
    h.update(INSTRUCTIONS.encode("utf-8"))
    h.update(json.dumps(contract.SCHEMA, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def _downscale(data: bytes, max_px: int, quality: int = 88) -> Dict[str, Any]:
    """La foto, reducida a `max_px` en el lado mayor y recodificada JPEG. Devuelve bytes y
    medidas. Mandar 34 fotos de teléfono a resolución completa es pagar por píxeles que el modelo
    reduce de todos modos."""
    try:
        import cv2                                            # noqa: PLC0415
        import numpy as np                                    # noqa: PLC0415
    except ImportError as e:                                  # pragma: no cover
        raise EngineError("INPUT_UNREADABLE", f"falta una dependencia de imagen: {e}") from None
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise EngineError("INPUT_UNREADABLE", "una foto no se pudo decodificar")
    h, w = img.shape[:2]
    s = min(1.0, float(max_px) / float(max(h, w)))
    if s < 1.0:
        img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise EngineError("INPUT_UNREADABLE", "una foto no se pudo recodificar")
    return {"data": buf.tobytes(), "width": int(img.shape[1]), "height": int(img.shape[0])}


def _declared_text(declared: Dict[str, Any]) -> str:
    utiles = {k: v for k, v in (declared or {}).items() if v not in (None, "", [], {})}
    if not utiles:
        return "El operador no declaró datos."
    return "Datos declarados por el operador (pueden estar mal): " + json.dumps(
        utiles, ensure_ascii=False, sort_keys=True)


def _output_text(data: Any) -> str:
    """El texto de la respuesta. En el JSON crudo de /v1/responses no existe `output_text`: es
    una comodidad del SDK. Se arma recorriendo `output[].content[]`.

    Cada forma de fallar tiene su nombre: un proveedor que devuelve 200 con `status: failed`, un
    proxy que devuelve HTML o una respuesta cortada no son lo mismo, y confundirlos con «vino
    vacía» borra justo lo que hay que mirar."""
    if not isinstance(data, dict):
        raise EngineError("NOT_JSON", "la respuesta no es un objeto JSON")
    if "_raw" in data:                                         # 2xx con un cuerpo que no es JSON
        raise EngineError("NOT_JSON", "la respuesta no es JSON: "
                          + http.sanitize(str(data["_raw"]))[:300])
    estado = data.get("status")
    err = data.get("error") if isinstance(data.get("error"), dict) else {}
    detalle = http.sanitize(" ".join(str(x) for x in (err.get("code"), err.get("message"))
                                     if x))[:500]
    if estado == "incomplete":
        det = data.get("incomplete_details")
        motivo = (det.get("reason") if isinstance(det, dict) else det) or "sin motivo"
        raise EngineError("INCOMPLETE", f"el proveedor cortó la respuesta "
                                        f"({http.sanitize(str(motivo))[:200]})")
    if estado not in (None, "completed"):
        raise EngineError(str(estado).upper()[:40], detalle or "sin detalle")
    if detalle:                                                 # sin estado, pero con un error
        raise EngineError("PROVIDER_ERROR", detalle)
    salida = data.get("output")
    if salida is not None and not isinstance(salida, list):
        raise EngineError("MALFORMED", "`output` no es una lista")
    textos: List[str] = []
    for item in salida or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        contenido = item.get("content")
        if contenido is not None and not isinstance(contenido, list):
            raise EngineError("MALFORMED", "`content` no es una lista")
        for c in contenido or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "refusal":
                raise EngineError("REFUSAL", http.sanitize(
                    str(c.get("refusal") or "el modelo se negó"))[:500])
            if c.get("type") == "output_text":
                t = c.get("text")
                if t is not None and not isinstance(t, str):
                    raise EngineError("MALFORMED", "el texto de la respuesta no es texto")
                textos.append(t or "")
    if not textos:
        raise EngineError("EMPTY", "la respuesta no trae texto")
    return "".join(textos)


class OpenAIDirect(EngineAdapter):
    engine_id = ENGINE_ID
    name = "OpenAI multimodal directo"
    version = "1"
    provider = "openai"
    pipeline = "VLM directo: fotos + datos declarados → contrato v1, salida JSON estricta"
    capabilities = ("photos", "declared_data", "correction", "clarification")
    paid = True

    def model(self) -> str:
        return (os.environ.get(MODEL_ENV) or "").strip() or DEFAULT_MODEL

    def default_params(self) -> Dict[str, Any]:
        return {"model": self.model(), "image_detail": "high", "max_image_px": 1600,
                "max_output_tokens": 16000, "reasoning_effort": None, "timeout_s": 600,
                "photos_on_correction": True}

    def availability(self) -> Availability:
        if http.env_key(KEY_ENV) is None:
            return Availability(UNAVAILABLE, MISSING_CREDENTIAL,
                                f"falta {KEY_ENV} en el entorno del servidor")
        return Availability(AVAILABLE)

    # -----------------------------------------------------------------------------------------
    def build_body(self, req: EngineRequest) -> Dict[str, Any]:
        """El cuerpo de la petición, con las imágenes ya reducidas. Separado de `reconstruct()`
        para que los tests puedan mirar exactamente qué saldría sin gastar nada."""
        p = req.params
        mandar_fotos = req.mode != CORRECTION or p.get("photos_on_correction", True)
        partes: List[Dict[str, Any]] = []
        texto = ["Modo: " + ("corrección de un plano anterior." if req.mode == CORRECTION
                             else "reconstrucción inicial."),
                 _declared_text(req.declared)]
        if req.ignored_inputs:
            texto.append("No se envían (este motor no los consume): "
                         + ", ".join(req.ignored_inputs) + ".")
        if req.mode == CORRECTION:
            texto.append("Plano anterior (contrato v1):\n"
                         + json.dumps(req.previous or {}, ensure_ascii=False))
            if req.clarification_context:
                texto.append("Antes preguntaste: " + req.clarification_context)
            texto.append("Instrucción del operador: «" + (req.instruction or "") + "»")
        texto.append(f"Fotos: {len(req.images) if mandar_fotos else 0}. "
                     "Cada una va precedida de su id.")
        partes.append({"type": "input_text", "text": "\n\n".join(texto)})
        enviadas = []
        if mandar_fotos:
            for i, im in enumerate(req.images, 1):
                red = _downscale(im.data, int(p.get("max_image_px") or 1600))
                enviadas.append({"asset_id": im.asset_id, "width": red["width"],
                                 "height": red["height"], "bytes": len(red["data"])})
                partes.append({"type": "input_text", "text": f"Foto {i} · id {im.asset_id}"})
                partes.append({"type": "input_image", "detail": p.get("image_detail") or "high",
                               "image_url": "data:image/jpeg;base64,"
                                            + base64.b64encode(red["data"]).decode("ascii")})
        body: Dict[str, Any] = {
            "model": p.get("model") or DEFAULT_MODEL,
            "instructions": INSTRUCTIONS,
            "input": [{"role": "user", "content": partes}],
            "text": {"format": {"type": "json_schema", "name": "reconstruction_v1",
                                "schema": contract.SCHEMA, "strict": True}},
            "max_output_tokens": int(p.get("max_output_tokens") or 16000),
            # que el proveedor no guarde fotos de clientes más allá de la llamada
            "store": False,
        }
        if p.get("reasoning_effort"):
            body["reasoning"] = {"effort": p["reasoning_effort"]}
        body["_enviadas"] = enviadas                          # se quita antes de mandar
        return body

    def reconstruct(self, req: EngineRequest) -> EngineResult:
        key = http.env_key(KEY_ENV)
        if key is None:
            # Segunda barrera: aunque la corrida se haya creado con clave, sin clave no hay red.
            raise EngineError(MISSING_CREDENTIAL, f"falta {KEY_ENV} en el entorno del servidor")
        body = self.build_body(req)
        enviadas = body.pop("_enviadas")
        texto_usuario = body["input"][0]["content"][0]["text"]
        resumen = {"url": URL, "model": body["model"], "prompt_version": PROMPT_VERSION,
                   "images_sent": len(enviadas), "images": enviadas,
                   "image_detail": req.params.get("image_detail"),
                   "max_output_tokens": body["max_output_tokens"],
                   "reasoning_effort": req.params.get("reasoning_effort"),
                   "ignored_inputs": list(req.ignored_inputs), "instructions": INSTRUCTIONS,
                   "user_text": texto_usuario, "store": body["store"]}
        # lo que ya se sabe antes de llamar: si la llamada falla, la corrida lo guarda igual
        parcial: Dict[str, Any] = {"prompt_version": PROMPT_VERSION,
                                   "prompt_sha256": _prompt_sha(), "request_summary": resumen,
                                   "cost_basis": "unknown"}
        t0 = time.monotonic()
        try:
            data = http.request_json(ENGINE_ID, "POST", URL,
                                     {"Authorization": f"Bearer {key}",
                                      "Content-Type": "application/json"},
                                     json.dumps(body).encode("utf-8"),
                                     timeout=int(req.params.get("timeout_s") or 600))
        except Exception as e:                                # noqa: BLE001 — red, HTTP, timeout
            parcial["latency_ms"] = int((time.monotonic() - t0) * 1000)
            raise EngineError("PROVIDER", http.sanitize(str(e))[:1500], parcial) from None
        parcial["latency_ms"] = int((time.monotonic() - t0) * 1000)
        uso = (data.get("usage") if isinstance(data, dict) else None) or {}
        parcial["usage"] = {k: uso.get(k) for k in ("input_tokens", "output_tokens",
                                                    "total_tokens") if k in uso}
        parcial["raw"] = http.sanitize({k: v for k, v in data.items() if k != "output"}
                                       if isinstance(data, dict) else {"_no_objeto": str(data)[:500]})
        modelo = http.sanitize(str((data.get("model") if isinstance(data, dict) else None)
                                   or body["model"]))
        parcial["request_summary"] = dict(resumen, model_reported=modelo)
        try:
            texto = _output_text(data)
            parcial["raw"]["output_text"] = http.sanitize(texto)
            salida = json.loads(texto)
        except EngineError as e:
            e.partial = {**parcial, **e.partial}
            raise
        except ValueError:
            raise EngineError("NOT_JSON", "la respuesta no es JSON: "
                              + http.sanitize(texto)[:300], parcial) from None
        return EngineResult(
            output=salida, model=modelo, latency_ms=parcial["latency_ms"],
            prompt_version=PROMPT_VERSION, prompt_sha256=parcial["prompt_sha256"],
            request_summary=resumen, raw=parcial["raw"], usage=parcial["usage"],
            cost_usd=None, cost_basis="unknown")
