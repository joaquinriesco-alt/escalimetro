"""E31 — AMBIENTACIÓN: intentos, revisión humana y la única imagen que llega al pack.

La pregunta que E31 responde no es "¿podemos generar una oficina bonita?" sino "¿podemos, de forma
repetible, tomar una foto real de una oficina vacía y producir una versión ambientada publicable
SIN MENTIR SOBRE LA PROPIEDAD?". Todo este módulo está construido alrededor de esa última cláusula.

Las cuatro reglas que gobiernan el archivo:

1. **Un intento es un registro, no una imagen del cliente.** Lo que devuelve el proveedor se guarda
   como CANDIDATO en un directorio interno; no entra en `property_assets` y el cliente no lo ve.
   Recién cuando una persona lo aprueba se publica como `PHOTO_STAGED`, con procedencia a la foto
   original y al intento. Un candidato rechazado se conserva —es evidencia— y nunca se pisa.

2. **La fidelidad es una compuerta dura, y la decide un humano.** Una imagen preciosa que corrió
   una ventana está reprobada. Ninguna métrica automática puede marcar PASS: como mucho produce
   un AUTO_WARNING para que el revisor mire con más cuidado (§12). La calidad se puntúa DESPUÉS de
   la fidelidad y nunca la compensa: un 5/5 alucinado es FAIL.

3. **No hay modo degradado.** Si el proveedor falla, si la imagen no sirve, si el revisor la
   rechaza: no se publica. Jamás se pasa la foto original como ambientada. Jamás se dice
   "completo" omitiendo la ambientación en silencio (§26).

4. **La petición es canónica y versionada** (§7/§8). Todos los proveedores reciben el MISMO
   contrato de preservación con el MISMO estilo; el hash del prompt viaja en cada intento. Comparar
   proveedores con prompts distintos no compararía proveedores.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
import uuid
from typing import Dict, List, Optional

from .. import store
from . import assets, entitlements, presets, properties, visual

REQUEST_VERSION = "staging_request_v1"

#: Estados del intento (lo técnico) — separados de la revisión (lo humano).
ATTEMPT_STATES = ("QUEUED", "RUNNING", "GENERATED", "FAILED")
REVIEW_STATES = ("PENDING", "APPROVED", "REJECTED")
FIDELITY_STATES = ("PENDING", "PASS", "FAIL")

#: Motivos de fallo de fidelidad (§11). Es una lista cerrada para poder agregar por proveedor;
#: "other" existe para no forzar una categoría equivocada.
FAILURE_REASONS = (
    ("window_changed", "Cambió una ventana (cantidad, posición o tamaño)"),
    ("column_changed", "Cambió o desapareció un pilar"),
    ("wall_or_opening_changed", "Cambió un muro, puerta o vano"),
    ("ceiling_changed", "Cambió el cielo o su altura"),
    ("perspective_changed", "Cambió la perspectiva o la posición de cámara"),
    ("view_changed", "Cambió lo que se ve por las ventanas"),
    ("proportions_changed", "Cambiaron las proporciones del espacio"),
    ("impossible_geometry", "Geometría imposible"),
    ("other", "Otro"),
)
FAILURE_KEYS = tuple(k for k, _ in FAILURE_REASONS)

#: §23 — lo que acompaña a toda imagen ambientada, en el pack y en pantalla.
DISCLOSURE = "Ambientación referencial."
DISCLOSURE_LONG = ("Ambientación referencial. El mobiliario y la decoración son una propuesta "
                   "digital sobre la foto real; no existen en la propiedad.")

#: Estados de la ambientación de UNA propiedad (§21/§26). Se derivan de hechos, como todo.
PROPERTY_STAGING_STATES = ("STAGING_UNAVAILABLE", "NOT_REQUESTED", "NEEDS_STAGING", "GENERATING",
                           "STAGING_REVIEW", "APPROVED", "STAGING_NEEDS_MANUAL_REVIEW")


class StagingError(ValueError):
    """Problema que el usuario u operador puede corregir."""


class ReviewError(StagingError):
    """La revisión viola una regla dura (p. ej. aprobar con fidelidad FAIL)."""


# =================================================================================================
# §8 — LA PETICIÓN CANÓNICA. Una sola, versionada, igual para todos los proveedores.
# =================================================================================================
PRESERVE = (
    "camera position", "perspective and focal length", "room dimensions and proportions",
    "every visible wall", "every window: count, position and size", "structural columns",
    "doors and openings", "ceiling geometry and height", "floor boundaries",
    "the exterior view through the windows", "all core architectural elements",
)
MAY_CHANGE = (
    "furniture", "plants", "decorative lighting fixtures", "rugs", "artwork",
    "loose accessories", "non-structural decorative elements", "mood within the selected style",
)
FORBIDDEN = (
    "expanding or adding windows", "deleting or moving columns", "adding structural walls",
    "changing ceiling height", "inventing doors", "altering the exterior view",
    "changing room proportions", "changing the camera position",
)

#: Fragmento de estilo para el proveedor. Interno y en inglés: los modelos responden mejor así y el
#: cliente nunca lo ve (§22 prohíbe filtrar el prompt). NO contiene ni un dato geométrico.
STYLE_PROMPT = {
    "CORPORATE": "corporate office: restrained, institutional, orderly; light wood, grey, glass, "
                 "neutral textiles",
    "CONTEMPORARY": "contemporary office: current, bright, clean; light oak, white, plants, "
                    "slim metal",
    "CREATIVE": "creative office: informal, warm, with accents of saturated colour; textiles, "
                "wood, plants",
    "INDUSTRIAL": "industrial office: raw, technical, characterful; black metal, exposed ceiling, "
                  "concrete, leather",
    "PREMIUM": "premium office: quiet, expensive, noble materials; walnut, stone, brass, heavy "
               "textiles",
}


def canonical_request(style: str) -> Dict:
    """El contrato que recibe TODO proveedor. Cambiarlo es cambiar `REQUEST_VERSION`."""
    presets.require_style(style)
    prompt = (
        "Virtually stage this real photograph of an EMPTY office for a commercial listing. "
        f"Style: {STYLE_PROMPT[style]}. "
        "Add only furniture, plants, decorative lighting, rugs, artwork and loose accessories, "
        "arranged plausibly for an office, at correct scale, with lighting consistent with the "
        "photo. "
        "STRICTLY PRESERVE, pixel for pixel where possible: " + "; ".join(PRESERVE) + ". "
        "DO NOT: " + "; ".join(FORBIDDEN) + ". "
        "The result must be recognizably the same room from the same camera, photorealistic, "
        "with no text, no people and no watermarks added."
    )
    req = {"request_version": REQUEST_VERSION, "visual_style": style,
           "preserve": list(PRESERVE), "may_change": list(MAY_CHANGE),
           "forbidden": list(FORBIDDEN), "prompt": prompt}
    req["prompt_hash"] = hashlib.sha256(
        json.dumps(req, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return req


def to_provider_request(property_id: str, source_asset_id: str, style: str,
                        fit_id: Optional[str] = None) -> visual.StagingRequest:
    req = canonical_request(style)
    return visual.StagingRequest(property_id=property_id, source_asset_id=source_asset_id,
                                 style_preset=style, fit_id=fit_id,
                                 context={"request_version": REQUEST_VERSION,
                                          "prompt": req["prompt"], "prompt_hash": req["prompt_hash"]},
                                 must_preserve=list(PRESERVE), may_edit=list(MAY_CHANGE))


# =================================================================================================
# §18 — FOTO PRINCIPAL. El cliente elige UNA; no se ambienta todo por defecto.
# =================================================================================================
def set_hero(property_id: str, asset_id: str) -> None:
    a = assets.get(asset_id, property_id)
    if a is None or a["kind"] != assets.PHOTO_ORIGINAL:
        raise StagingError("Elegí una de las fotos de esta propiedad como foto principal.")
    store.ex("UPDATE properties SET hero_photo_asset_id=?, updated_at=? WHERE property_id=?",
             (asset_id, store.now(), property_id))


def hero(property_id: str) -> Optional[Dict]:
    p = properties.require(property_id)
    hid = p.get("hero_photo_asset_id")
    if not hid:
        return None
    a = assets.get(hid, property_id)
    return a if (a and a["kind"] == assets.PHOTO_ORIGINAL) else None


# =================================================================================================
# §17 — INTENTOS
# =================================================================================================
def _candidates_dir(property_id: str) -> str:
    return os.path.join(store.property_dir(property_id), "staging")


def candidate_path(attempt: Dict) -> Optional[str]:
    if not attempt.get("output_stored"):
        return None
    return os.path.join(_candidates_dir(attempt["property_id"]), attempt["output_stored"])


def get(attempt_id: str, property_id: Optional[str] = None) -> Optional[Dict]:
    """Con `property_id`, un intento de otra propiedad no existe (misma barrera que `assets`)."""
    row = store.q1("SELECT * FROM staging_attempts WHERE attempt_id=?", (attempt_id,))
    if row is None:
        return None
    d = dict(row)
    if property_id is not None and d["property_id"] != property_id:
        return None
    d["failure_reasons_list"] = store.js(d["failure_reasons"], []) or []
    d["auto_warnings_list"] = store.js(d["auto_warnings"], []) or []
    return d


def require(attempt_id: str, property_id: Optional[str] = None) -> Dict:
    a = get(attempt_id, property_id)
    if a is None:
        raise LookupError(attempt_id)
    return a


def list_for(property_id: str, source_asset_id: Optional[str] = None,
             fit_id: Optional[str] = None, include_benchmark: bool = False) -> List[Dict]:
    sql, args = "SELECT attempt_id FROM staging_attempts WHERE property_id=?", [property_id]
    if source_asset_id:
        sql += " AND source_asset_id=?"; args.append(source_asset_id)
    if fit_id is None:
        sql += " AND fit_id IS NULL"
    else:
        sql += " AND fit_id=?"; args.append(fit_id)
    if not include_benchmark:
        sql += " AND benchmark_id IS NULL"
    sql += " ORDER BY created_at DESC"
    return [get(r["attempt_id"]) for r in store.q(sql, tuple(args))]


def attempts_used(property_id: str, source_asset_id: str, fit_id: Optional[str] = None) -> int:
    return len(list_for(property_id, source_asset_id, fit_id))


def retries_left(property_id: str, source_asset_id: str, fit_id: Optional[str] = None):
    """§20 — los reintentos son mecánica de producción, no créditos del cliente, y tienen tope.
    None = sin tope (Pro)."""
    tope = entitlements.limit("staging_attempts_per_hero")
    if tope is None:
        return None
    return max(0, tope - attempts_used(property_id, source_asset_id, fit_id))


def create_attempt(property_id: str, source_asset_id: str, style: str,
                   fit_id: Optional[str] = None, provider_name: Optional[str] = None,
                   benchmark_id: Optional[str] = None) -> str:
    """Registra un intento en QUEUED. No llama a nadie todavía.

    Comprueba los derechos ANTES de gastar: un fit de prospecto exige Pro; un pack base tiene un
    tope de reintentos por foto principal. Los intentos de benchmark no consumen el cupo de un
    cliente ni se publican jamás."""
    properties.require(property_id)
    src = assets.get(source_asset_id, property_id)
    if src is None or src["kind"] != assets.PHOTO_ORIGINAL:
        raise StagingError("La foto de origen no pertenece a esta propiedad.")
    presets.require_style(style)
    if fit_id is not None:
        entitlements.require(entitlements.MULTIPLE_STAGING)
        from . import fits                                    # noqa: PLC0415
        fits.require(fit_id, property_id)
    if benchmark_id is None:
        left = retries_left(property_id, source_asset_id, fit_id)
        if left is not None and left <= 0:
            raise entitlements.EntitlementError(
                entitlements.MULTIPLE_STAGING,
                "Se agotaron los intentos internos para esta foto. Corresponde revisión manual, "
                "no otro intento automático.")
    prov = visual.get_provider(provider_name)
    req = canonical_request(style)
    ruta = assets.path_of(src)
    if not os.path.exists(ruta):
        raise StagingError("El archivo de la foto de origen no está en el volumen.")
    aid = "st_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO staging_attempts(attempt_id, property_id, source_asset_id, fit_id, "
             "benchmark_id, visual_style, provider, model, request_version, prompt_hash, "
             "input_sha256, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'QUEUED',?)",
             (aid, property_id, source_asset_id, fit_id, benchmark_id, style, prov.name,
              prov.model, REQUEST_VERSION, req["prompt_hash"], src["sha256"], store.now()))
    return aid


def run_attempt(attempt_id: str) -> Dict:
    """Ejecuta UN intento de forma síncrona: llama al proveedor, guarda el candidato, mide.

    Cualquier error del proveedor deja el intento en FAILED con el mensaje y SIN candidato. No hay
    reintento automático dentro del mismo intento: reintentar es crear otro intento (§17), para que
    cada llamada quede contada y pagada por separado."""
    a = require(attempt_id)
    if a["status"] not in ("QUEUED", "FAILED"):
        return a
    src = assets.get(a["source_asset_id"], a["property_id"])
    prov = visual.get_provider(a["provider"])
    t0 = time.monotonic()
    store.ex("UPDATE staging_attempts SET status='RUNNING', started_at=?, error=NULL "
             "WHERE attempt_id=?", (store.now(), attempt_id))
    try:
        if not prov.available():
            raise visual.ProviderNotConfigured(
                f"El proveedor '{a['provider']}' no tiene credencial en este entorno.")
        with open(assets.path_of(src), "rb") as fh:
            blob = fh.read()
        req = to_provider_request(a["property_id"], a["source_asset_id"], a["visual_style"],
                                  a["fit_id"])
        out = prov.stage_photo(req, blob, src["mime_type"])
        _validate_output(out)
        ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(
            out.mime_type, ".png")
        stored = uuid.uuid4().hex + ext
        d = _candidates_dir(a["property_id"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, stored), "wb") as fh:
            fh.write(out.image_bytes)
        sha = hashlib.sha256(out.image_bytes).hexdigest()
        avisos = diagnostics(assets.path_of(src), os.path.join(d, stored))
        store.ex("UPDATE staging_attempts SET status='GENERATED', output_stored=?, output_sha256=?, "
                 "model=?, cost_usd=?, cost_basis=?, latency_ms=?, pipeline_ms=?, seed=?, "
                 "auto_warnings=?, completed_at=? WHERE attempt_id=?",
                 (stored, sha, out.model, out.cost_usd, out.cost_basis, int(out.latency_ms),
                  int((time.monotonic() - t0) * 1000), out.seed,
                  json.dumps(avisos, ensure_ascii=False), store.now(), attempt_id))
    except Exception as e:                                    # noqa: BLE001 — se registra, no se traga
        store.ex("UPDATE staging_attempts SET status='FAILED', error=?, pipeline_ms=?, "
                 "completed_at=? WHERE attempt_id=?",
                 (_safe_error(e), int((time.monotonic() - t0) * 1000), store.now(), attempt_id))
    return require(attempt_id)


def _validate_output(out: visual.ProviderOutput) -> None:
    """Un proveedor que devuelve nada, o algo que no es una imagen, falló: no se guarda."""
    # El umbral es deliberadamente bajo: la defensa real es la cabecera y, después, el diagnóstico
    # (`blank_output`). Un umbral alto rechazaría PNGs pequeños legítimos y no protegería de nada.
    if not out.image_bytes or len(out.image_bytes) < 128:
        raise visual.VisualStagingError("el proveedor devolvió una imagen vacía o truncada")
    cabeceras = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")
    if not out.image_bytes.startswith(cabeceras):
        raise visual.VisualStagingError("el proveedor devolvió algo que no es PNG/JPEG/WEBP")


def _safe_error(e: Exception) -> str:
    """El mensaje de error se guarda y se muestra al operador. Nunca puede contener una clave:
    los adaptadores ya no la ponen en sus excepciones, y acá se recorta por si acaso."""
    msg = f"{e.__class__.__name__}: {e}"
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "BFL_API_KEY"):
        v = os.environ.get(var)
        if v and v in msg:
            msg = msg.replace(v, "***")
    return msg[:2000]


# ---- cola: un hilo, como el motor. Un intento no bloquea la request HTTP. ---------------------
_jobs: "queue.Queue[str]" = queue.Queue()
_worker: Optional[threading.Thread] = None
_lock = threading.Lock()


def _loop() -> None:
    while True:
        aid = _jobs.get()
        try:
            run_attempt(aid)
        except Exception as e:                                # noqa: BLE001
            store.ex("UPDATE staging_attempts SET status='FAILED', error=?, completed_at=? "
                     "WHERE attempt_id=?", (_safe_error(e), store.now(), aid))
        finally:
            _jobs.task_done()


def enqueue(attempt_id: str) -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, name="escalimetro-staging", daemon=True)
            _worker.start()
    _jobs.put(attempt_id)


def pending() -> int:
    return _jobs.qsize()


# =================================================================================================
# §12 — DIAGNÓSTICO AUTOMÁTICO: apoyo, no autoridad
# =================================================================================================
def diagnostics(original_path: str, staged_path: str) -> List[str]:
    """Devuelve una lista de AUTO_WARNING. Nunca un veredicto.

    Cada aviso es una razón para que el revisor mire con más cuidado, no una conclusión: una
    similitud estructural baja puede ser una ventana movida o simplemente un sofá grande. Por eso
    esto alimenta la pantalla de revisión y nada más."""
    avisos: List[str] = []
    try:
        import cv2                                            # noqa: PLC0415
        import numpy as np                                    # noqa: PLC0415
        o = cv2.imread(original_path, cv2.IMREAD_COLOR)
        s = cv2.imread(staged_path, cv2.IMREAD_COLOR)
        if s is None:
            return ["corrupt_output"]
        if o is None:
            return ["original_unreadable"]
        if s.std() < 2.0:
            avisos.append("blank_output")
        ho, wo = o.shape[:2]
        hs, ws = s.shape[:2]
        if (hs, ws) != (ho, wo):
            avisos.append(f"size_changed:{wo}x{ho}->{ws}x{hs}")
        if abs((wo / ho) - (ws / hs)) > 0.02:
            avisos.append("aspect_ratio_changed")
        # comparación estructural a la misma escala, en gris, a 512 px de ancho
        escala = 512.0 / max(wo, 1)
        dim = (512, max(1, int(ho * escala)))
        og = cv2.cvtColor(cv2.resize(o, dim, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        sg = cv2.cvtColor(cv2.resize(s, dim, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        try:
            from skimage.metrics import structural_similarity  # noqa: PLC0415
            ssim = float(structural_similarity(og, sg))
            if ssim < 0.35:
                avisos.append(f"low_structural_similarity:{ssim:.2f}")
        except Exception:                                     # noqa: BLE001
            pass
        eo = cv2.Canny(og, 80, 160) > 0
        es = cv2.Canny(sg, 80, 160) > 0
        union = np.logical_or(eo, es).sum()
        iou = float(np.logical_and(eo, es).sum() / union) if union else 1.0
        if iou < 0.15:
            avisos.append(f"edge_structure_drift:{iou:.2f}")
        if _dhash_distance(og, sg) > 24:
            avisos.append("perceptual_drift")
    except Exception as e:                                    # noqa: BLE001
        avisos.append(f"diagnostics_error:{e.__class__.__name__}")
    return avisos


def _dhash_distance(a, b) -> int:
    import cv2                                                # noqa: PLC0415
    import numpy as np                                        # noqa: PLC0415

    def h(img):
        r = cv2.resize(img, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
        return (r[:, 1:] > r[:, :-1]).flatten()
    return int(np.count_nonzero(h(a) != h(b)))


# =================================================================================================
# §9–§11 — REVISIÓN HUMANA. La única autoridad sobre la fidelidad.
# =================================================================================================
def review(attempt_id: str, fidelity: str, quality: Optional[int], publication: str,
           reasons: Optional[List[str]] = None, notes: str = "", reviewer: str = "") -> Dict:
    """Registra la revisión. Reglas duras, y se hacen cumplir acá y no en el formulario:

      · fidelidad FAIL ⇒ no se puede aprobar la publicación, con cualquier calidad;
      · la calidad sólo se registra si la fidelidad pasó (§10: no se promedia una alucinación);
      · aprobar publica el asset (§22); rechazar conserva el candidato (§17)."""
    a = require(attempt_id)
    if a["status"] != "GENERATED":
        raise ReviewError("Sólo se revisa un intento que generó una imagen.")
    if fidelity not in ("PASS", "FAIL"):
        raise ReviewError("Decí si la fidelidad arquitectónica pasa o falla.")
    if publication not in ("APPROVE", "REJECT"):
        raise ReviewError("Decí si se aprueba o se rechaza la publicación.")
    reasons = [r for r in (reasons or []) if r in FAILURE_KEYS]
    if fidelity == "FAIL":
        if publication == "APPROVE":
            raise ReviewError("Una imagen que cambia la propiedad no se publica, por bonita que sea.")
        if not reasons:
            raise ReviewError("Indicá al menos un motivo del fallo de fidelidad.")
        quality = None
    else:
        if quality is None:
            raise ReviewError("Puntuá la calidad (1 a 5) cuando la fidelidad pasa.")
        try:
            quality = int(quality)
        except (TypeError, ValueError):
            raise ReviewError("La calidad tiene que ser un número entre 1 y 5.")
        if not 1 <= quality <= 5:
            raise ReviewError("La calidad tiene que ser un número entre 1 y 5.")
        reasons = []
    if a["benchmark_id"] and publication == "APPROVE":
        # un intento de benchmark se juzga igual pero NUNCA se publica a un cliente
        estado = "APPROVED"
    else:
        estado = "APPROVED" if publication == "APPROVE" else "REJECTED"
    store.ex("UPDATE staging_attempts SET fidelity_status=?, quality_score=?, review_status=?, "
             "failure_reasons=?, review_notes=?, reviewer=?, reviewed_at=? WHERE attempt_id=?",
             (fidelity, quality, estado, json.dumps(reasons), (notes or "")[:2000],
              (reviewer or "")[:80], store.now(), attempt_id))
    if estado == "APPROVED" and not a["benchmark_id"]:
        _publish(attempt_id)
    return require(attempt_id)


def _publish(attempt_id: str) -> str:
    """§22 — el candidato aprobado se convierte en PHOTO_STAGED con procedencia a la foto original
    y al intento. Para el pack base hay UNA sola: la anterior se retira (el intento queda)."""
    a = require(attempt_id)
    ruta = candidate_path(a)
    if not ruta or not os.path.exists(ruta):
        raise ReviewError("El candidato aprobado no está en el volumen.")
    src = assets.get(a["source_asset_id"], a["property_id"])
    if a["fit_id"] is None:
        for viejo in assets.list_of_kind(a["property_id"], assets.PHOTO_STAGED):
            if not (store.js(viejo["metadata"], {}) or {}).get("fit_id"):
                assets.delete(viejo["asset_id"], a["property_id"])
                store.ex("UPDATE staging_attempts SET output_asset_id=NULL WHERE output_asset_id=?",
                         (viejo["asset_id"],))
        for viejo in assets.list_of_kind(a["property_id"], assets.BEFORE_AFTER):
            if not (store.js(viejo["metadata"], {}) or {}).get("fit_id"):
                assets.delete(viejo["asset_id"], a["property_id"])
    with open(ruta, "rb") as fh:
        blob = fh.read()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(
        os.path.splitext(ruta)[1], "image/png")
    meta = {"attempt_id": attempt_id, "source_asset_id": a["source_asset_id"],
            "provider": a["provider"], "model": a["model"], "visual_style": a["visual_style"],
            "request_version": a["request_version"], "prompt_hash": a["prompt_hash"],
            "input_sha256": a["input_sha256"], "output_sha256": a["output_sha256"],
            "fidelity_status": a["fidelity_status"], "quality_score": a["quality_score"],
            "fit_id": a["fit_id"], "disclosure": DISCLOSURE, "disclosure_long": DISCLOSURE_LONG}
    aid = assets.save_bytes(a["property_id"], assets.PHOTO_STAGED,
                            f"foto_ambientada{os.path.splitext(ruta)[1]}", blob, mime,
                            source_asset_id=a["source_asset_id"], metadata=meta)
    store.ex("UPDATE staging_attempts SET output_asset_id=? WHERE attempt_id=?", (aid, attempt_id))
    try:
        before_after(a["property_id"], src, assets.get(aid, a["property_id"]), attempt_id)
    except Exception:                                         # noqa: BLE001 — el compuesto es un extra
        pass
    properties.touch(a["property_id"])
    return aid


# =================================================================================================
# §24 — ANTES / DESPUÉS: un compuesto, no contenido generativo nuevo
# =================================================================================================
def before_after(property_id: str, original: Dict, staged: Dict, attempt_id: str) -> Optional[str]:
    """Lado a lado, misma altura, con la leyenda de §23. Nada más se toca."""
    from PIL import Image, ImageDraw                          # noqa: PLC0415
    o = Image.open(assets.path_of(original)).convert("RGB")
    s = Image.open(assets.path_of(staged)).convert("RGB")
    H = 900
    o = o.resize((max(1, int(o.width * H / o.height)), H))
    s = s.resize((max(1, int(s.width * H / s.height)), H))
    gutter, strip = 24, 64
    lienzo = Image.new("RGB", (o.width + gutter + s.width, H + strip), "white")
    lienzo.paste(o, (0, 0))
    lienzo.paste(s, (o.width + gutter, 0))
    d = ImageDraw.Draw(lienzo)
    d.text((12, H + 18), "ANTES · foto real", fill=(60, 60, 60))
    d.text((o.width + gutter + 12, H + 18), f"DESPUÉS · {DISCLOSURE}", fill=(60, 60, 60))
    import io                                                 # noqa: PLC0415
    buf = io.BytesIO()
    lienzo.save(buf, format="PNG", optimize=True)
    fit_id = (store.js(staged["metadata"], {}) or {}).get("fit_id")
    return assets.save_bytes(property_id, assets.BEFORE_AFTER, "antes_despues.png", buf.getvalue(),
                             "image/png", source_asset_id=original["asset_id"],
                             metadata={"staged_asset_id": staged["asset_id"], "attempt_id": attempt_id,
                                       "fit_id": fit_id, "disclosure": DISCLOSURE,
                                       "composite": "side_by_side_v1"})


# =================================================================================================
# §21/§26 — EL ESTADO DE LA AMBIENTACIÓN DE UNA PROPIEDAD, derivado de hechos
# =================================================================================================
def approved_hero(property_id: str) -> Optional[Dict]:
    """La PHOTO_STAGED del pack base, si existe. Sólo puede existir vía `_publish`."""
    for a in assets.list_of_kind(property_id, assets.PHOTO_STAGED):
        if not (store.js(a["metadata"], {}) or {}).get("fit_id"):
            return a
    return None


def state(property_id: str) -> Dict:
    h = hero(property_id)
    aprobado = approved_hero(property_id)
    prov = visual.get_provider()
    intentos = list_for(property_id, h["asset_id"], None) if h else []
    activos = [a for a in intentos if a["status"] in ("QUEUED", "RUNNING")]
    por_revisar = [a for a in intentos if a["status"] == "GENERATED" and a["review_status"] == "PENDING"]
    left = retries_left(property_id, h["asset_id"], None) if h else None

    if aprobado:
        st, razon, man = "APPROVED", "imagen ambientada aprobada por revisión humana", "approved"
    elif not h:
        st, razon, man = "NOT_REQUESTED", "falta elegir la foto principal", "not_requested"
    elif activos:
        st, razon, man = "GENERATING", "generando", "pending"
    elif por_revisar:
        st, razon, man = "STAGING_REVIEW", "hay un candidato esperando revisión humana", "pending"
    elif left is not None and left <= 0:
        # antes que "no hay proveedor": si los intentos se agotaron, lo que corresponde es que una
        # persona mire el caso, tenga o no credencial el entorno de hoy
        st, razon, man = ("STAGING_NEEDS_MANUAL_REVIEW",
                          "se agotaron los intentos sin una imagen aprobada", "not_generated")
    elif not prov.available():
        st, razon, man = "STAGING_UNAVAILABLE", "no hay proveedor de ambientación configurado", "not_generated"
    else:
        st, razon, man = "NEEDS_STAGING", "foto principal elegida; falta generar y aprobar", "not_generated"
    return {"state": st, "reason": razon, "manifest_status": man,
            "hero_asset_id": h["asset_id"] if h else None,
            "approved_asset_id": aprobado["asset_id"] if aprobado else None,
            "attempts": len(intentos), "pending_review": len(por_revisar),
            "retries_left": left, "provider_available": prov.available(),
            "customer_text": CUSTOMER_TEXT[st]}


#: Cómo se le cuenta cada estado al cliente. Sin vocabulario de proveedor ni de QA.
CUSTOMER_TEXT = {
    "STAGING_UNAVAILABLE": "Todavía no disponible",
    "NOT_REQUESTED": "Elegí la foto principal para que la ambientemos",
    "NEEDS_STAGING": "En preparación",
    "GENERATING": "En preparación",
    "STAGING_REVIEW": "En revisión",
    "APPROVED": "Lista",
    "STAGING_NEEDS_MANUAL_REVIEW": "En revisión",
}


def pending_review_all() -> List[Dict]:
    """La cola interna de revisión: todo candidato generado sin veredicto, de cualquier propiedad."""
    return [get(r["attempt_id"]) for r in store.q(
        "SELECT attempt_id FROM staging_attempts WHERE status='GENERATED' AND review_status='PENDING' "
        "ORDER BY created_at")]


def needing_staging_all() -> List[Dict]:
    """Propiedades con foto principal elegida y sin imagen aprobada ni candidato pendiente."""
    out = []
    for r in store.q("SELECT property_id FROM properties WHERE hero_photo_asset_id IS NOT NULL"):
        st = state(r["property_id"])
        if st["state"] in ("NEEDS_STAGING", "STAGING_NEEDS_MANUAL_REVIEW", "STAGING_UNAVAILABLE"):
            out.append(dict(st, property=properties.require(r["property_id"])))
    return out
