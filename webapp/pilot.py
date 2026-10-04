"""E45 — web piloto de la campaña E44: una superficie para probar a la vez el PRODUCTO (MEJORAR /
CREAR PLANO) y la EXPERIENCIA (UX/UI), en `/lab/campaign/e44/`.

No es otro sistema de campaña: todo lo que cuenta —casos, provenance, estado, N, ceguera, cierre,
reveal, evaluaciones— vive en `webapp/campaign.py` (E44) y acá sólo se muestra y se dispara. Los
casos se guardan en el manifiesto de E44; el estado humano (NUEVO, PROCESANDO…) se DERIVA de sus
eventos, no se declara.

Dos registros separados en cada pantalla, a propósito:

* la **vista producto**: lo que vería un corredor (subir, esperar, ver el plano). Sin motores,
  contratos, hashes ni jerga;
* el **panel piloto** (banda tintada «MODO PILOTO»): plano real oculto, cierre ciego, evaluación.

El plano real de CREAR nunca se sirve ni se nombra antes del reveal: la única ruta que lo entrega
exige además que el evento `reveal` exista en la campaña.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from flask import (Blueprint, abort, redirect, render_template, request, send_file, url_for)
from werkzeug.exceptions import RequestEntityTooLarge

from . import auth, campaign, mobile_upload, reconstruction
from .domain.reconstruction.projects import ReconError

bp = Blueprint("pilot", __name__, url_prefix="/lab/campaign/e44")
# Mismo resguardo de origen que el laboratorio de E37: aquí un POST puede gastar dinero o revelar
# el plano real, y HTTP Basic lo reenvía el navegador solo.
bp.before_request(reconstruction._guardas)                     # noqa: SLF001


@bp.before_request
def _tope_de_envio():
    """E45.2: `_guardas` deja el tope de E37 (1200 MB por envío), pensado para lotes de laboratorio.
    El POST de CREAR del piloto tiene un tope propio: werkzeug corta el cuerpo al pasarlo, antes de
    que ninguna vista lea nada."""
    if request.method == "POST" and request.endpoint == "pilot.crear_post":
        request.max_content_length = mobile_upload.MAX_ENVIO_BYTES
    return None

CREATE_ENGINE = "openai_direct"
DEMO_ENGINE = "fixture_replay"
LABEL = {campaign.IMPROVE: "MEJORAR", campaign.CREATE: "CREAR"}
_CID = re.compile(campaign._ID.pattern)                         # noqa: SLF001
_FIND_ID = re.compile(r"e44-(?:imp|cre)-[0-9a-f]{10}")


def _operator() -> str:
    return os.environ.get("ESCALIMETRO_REVIEWER", "Joaquín Riesco")


# --------------------------------------------------------------------------------------------
# estado humano, derivado de los artefactos
# --------------------------------------------------------------------------------------------
NUEVO, CARGADO, PROCESANDO, REVISION = "NUEVO", "MATERIAL CARGADO", "PROCESANDO", "NECESITA REVISIÓN"
LISTO, EVALUADO, BLOQUEADO = "RESULTADO LISTO", "EVALUADO", "BLOQUEADO"
SIN_RESULTADO, EXCLUIDO = "SIN RESULTADO", "EXCLUIDO"
_CLASE = {NUEVO: "nuevo", CARGADO: "cargado", PROCESANDO: "procesando", REVISION: "revision",
          LISTO: "listo", EVALUADO: "evaluado", BLOQUEADO: "bloqueado", SIN_RESULTADO: "sinres",
          EXCLUIDO: "bloqueado"}


def _case_or_404(case_id: str) -> Dict[str, Any]:
    if not _CID.match(case_id or ""):
        abort(404)
    case = campaign.get(case_id)
    if case is None:
        abort(404)
    return case


def _last(case_id: str, kind: str) -> Optional[Dict[str, Any]]:
    xs = campaign._of(case_id, kind)                            # noqa: SLF001
    return xs[-1] if xs else None


def _chain(case_id: str) -> List[Dict[str, Any]]:
    return campaign._of(case_id, "pipeline") + campaign._of(case_id, "correction")  # noqa: SLF001


def _final_run(case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """La corrida que se muestra: la elegida al cerrar, o la última de la cadena."""
    from .domain.reconstruction import runs                      # noqa: PLC0415
    cl = _last(case["case_id"], "closure")
    if cl:
        return runs.get(cl["data"]["final_run_id"])
    ok = campaign.last_done_run(case["case_id"])
    if ok:
        return runs.get(ok)
    ch = _chain(case["case_id"])
    return runs.get(ch[-1]["data"]["run_id"]) if ch else None


def _state(case: Dict[str, Any]) -> Dict[str, str]:
    """(clave de fase, rótulo) — fases: nuevo, cargado, procesando, revision, resultado, sinres,
    bloqueado, evaluado, excluido."""
    cid, tr = case["case_id"], case["track"]
    st = campaign.status(case)
    if st == campaign.EXCLUDED:
        return {"fase": "excluido", "label": EXCLUIDO}
    if st == campaign.URL_ONLY:
        return {"fase": "nuevo", "label": NUEVO}
    if st in (campaign.BLOCKED_CRED, campaign.BLOCKED_MATERIAL):
        return {"fase": "bloqueado", "label": BLOQUEADO}
    if st == campaign.COMPLETED:
        return {"fase": "evaluado", "label": EVALUADO}
    if campaign.pending_run(cid) is not None and tr == campaign.CREATE:
        return {"fase": "procesando", "label": PROCESANDO}
    pip = campaign._of(cid, "pipeline")                          # noqa: SLF001
    if st == campaign.EXECUTED:
        ok = pip[0]["data"].get("reached_output") if tr == campaign.IMPROVE \
            else pip[0]["data"].get("status") == "DONE"
        return ({"fase": "resultado", "label": LISTO} if ok
                else {"fase": "sinres", "label": SIN_RESULTADO})
    # CAPTURED
    if tr == campaign.IMPROVE and campaign._of(cid, "improve_started"):  # noqa: SLF001
        return {"fase": "revision", "label": REVISION}
    return {"fase": "cargado", "label": CARGADO}


def _ordinal(case: Dict[str, Any]) -> int:
    mismos = [c for c in campaign.load()["cases"] if c["track"] == case["track"]
              and bool(c.get("demo")) == bool(case.get("demo"))]
    return 1 + next(i for i, c in enumerate(mismos) if c["case_id"] == case["case_id"])


def _evals(case_id: str, kind: str) -> List[Dict[str, Any]]:
    """Historial completo, de la más nueva a la más vieja. Nada se reemplaza: se agrega."""
    return list(reversed(campaign._of(case_id, kind)))           # noqa: SLF001


def _rating_of(case_id: str) -> Optional[str]:
    e = _last(case_id, "evaluation")
    return (e["data"].get("rating") if e else None)


# --------------------------------------------------------------------------------------------
# archivos que se muestran (nunca por nombre: por rol, resueltos desde el manifiesto)
# --------------------------------------------------------------------------------------------
def _evidence(case: Dict[str, Any], role: str) -> List[str]:
    ev = campaign.case_dir(case["case_id"])
    return [os.path.join(ev, "evidence", a["file"]) for a in case["assets"] if a["role"] == role]


def _plan_preview(case: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """El plano subido, como imagen. Un PDF se rasteriza la primera vez (derivado, regenerable)."""
    src = next(iter(_evidence(case, campaign.ROLE_PLAN)), None)
    if not src or not os.path.isfile(src):
        return None
    if not src.lower().endswith(".pdf"):
        return {"path": src, "mime": "image/jpeg" if src.lower().endswith((".jpg", ".jpeg"))
                else "image/png"}
    dest = os.path.join(campaign.case_dir(case["case_id"]), "preview_plano.png")
    if not os.path.isfile(dest):
        try:
            import pymupdf                                       # noqa: PLC0415
            doc = pymupdf.open(src)
            page = doc[0]
            zoom = min(3.0, 2200 / max(page.rect.width, page.rect.height))
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(dest)
        except Exception:                                        # noqa: BLE001
            return None
    return {"path": dest, "mime": "image/png"}


def _improve_output(case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from .domain import assets                                   # noqa: PLC0415
    p = _last(case["case_id"], "pipeline")
    if not p or not p["data"].get("output_asset_id"):
        return None
    a = assets.get(p["data"]["output_asset_id"], p["data"]["property_id"])
    return a if a and os.path.isfile(assets.path_of(a)) else None


def _recon_path(case: Dict[str, Any]) -> Optional[str]:
    from .domain.reconstruction import runs                      # noqa: PLC0415
    run = _final_run(case)
    return runs.svg_path(run) if run else None


def _gt_visible(case: Dict[str, Any]) -> bool:
    """El plano real se muestra sólo si el reveal ocurrió EN LA CAMPAÑA y E37 lo confirma."""
    if case["track"] != campaign.CREATE or not campaign._of(case["case_id"], "reveal"):  # noqa: SLF001
        return False
    from .domain.reconstruction import groundtruth                # noqa: PLC0415
    return groundtruth.serving_path(case["recon_project_id"]) is not None


def _thumbs(case: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """URL de miniatura de entrada y salida, o None. Para el panel."""
    cid = case["case_id"]
    u = lambda w: url_for("pilot.archivo", case_id=cid, cual=w)   # noqa: E731
    if case["track"] == campaign.IMPROVE:
        return {"entrada": u("entrada") if _plan_preview(case) else None,
                "salida": u("despues") if _improve_output(case) else None}
    fotos = _evidence(case, campaign.ROLE_PHOTO)
    return {"entrada": url_for("pilot.archivo", case_id=cid, cual="foto-1") if fotos else None,
            "salida": u("reconstruccion") if _recon_path(case) else None}


# --------------------------------------------------------------------------------------------
# vista-modelo del caso
# --------------------------------------------------------------------------------------------
def _view(case: Dict[str, Any]) -> Dict[str, Any]:
    from .domain.reconstruction import runs                      # noqa: PLC0415
    cid, tr = case["case_id"], case["track"]
    if tr == campaign.CREATE:
        campaign.settle(cid)                       # asienta las corridas que ya terminaron
    s = _state(case)
    v: Dict[str, Any] = {
        "case": case, "track": tr, "label": LABEL[tr], "n": _ordinal(case), "fase": s["fase"],
        "estado": s["label"], "clase": _CLASE[s["label"]], "demo": bool(case.get("demo")),
        "published_m2": case.get("published_m2"),
        "referencia": (case.get("declared") or {}).get("description"),
        "link": (case.get("source_urls") or [None])[0],
        "n_fotos": len(_evidence(case, campaign.ROLE_PHOTO)),
        "evals_plano": _evals(cid, "evaluation"), "evals_ux": _evals(cid, "ux_evaluation"),
        "refresh": s["fase"] == "procesando", "error": None, "bloqueo": None}
    bl = _last(cid, "blocked")
    if bl:
        v["bloqueo"] = bl["data"]["status"]
    if tr == campaign.IMPROVE:
        v["entrada"] = _plan_preview(case) is not None
        st = campaign.improve_state(cid)
        v["mejorar"] = st
        pip = _last(cid, "pipeline")
        v["despues"] = _improve_output(case) is not None
        v["motivo"] = (pip["data"].get("error") if pip else None) or (st or {}).get("error")
        v["puede_evaluar_plano"] = pip is not None
        v["puede_evaluar_ux"] = pip is not None
    else:
        final = _final_run(case)
        cierre = _last(cid, "closure")
        v["cerrado"] = cierre is not None
        v["revelado"] = bool(campaign._of(cid, "reveal"))        # noqa: SLF001
        v["gt_cargado"] = True                                    # el alta de CREAR lo exige
        v["recon"] = _recon_path(case) is not None
        v["run"] = None
        if final:
            v["run"] = {"status": final["status"], "ok": final["status"] == runs.DONE,
                        "outcome": runs.OUTCOME_LABEL.get(final["outcome"] or "", ""),
                        "outcome_code": final["outcome"], "error": bool(final.get("error")),
                        "corregible": runs.correctable(final)}
        v["correcciones"] = [e["data"].get("prompt", "") for e in
                             campaign._of(cid, "correction")]     # noqa: SLF001
        v["puede_cerrar"] = bool(final) and final["status"] in (runs.DONE, runs.FAILED) \
            and not cierre and s["fase"] in ("resultado", "sinres")
        v["puede_corregir"] = (bool(final) and not cierre and v["run"]["corregible"]
                               and s["fase"] == "resultado")
        v["puede_evaluar_plano"] = v["revelado"]
        v["puede_evaluar_ux"] = v["revelado"] or s["fase"] == "bloqueado"
        v["gt_visible"] = _gt_visible(case)
    if s["fase"] == "bloqueado" and tr == campaign.IMPROVE:
        v["puede_evaluar_ux"] = True
    return v


# --------------------------------------------------------------------------------------------
# páginas
# --------------------------------------------------------------------------------------------
def _resumen() -> Dict[str, Any]:
    m = campaign.load()
    return {t: campaign.count(t, m) for t in campaign.TRACKS}


@bp.context_processor
def _limites():
    return {"lim": {"fotos": mobile_upload.MAX_FOTOS, "foto_mb": mobile_upload.MAX_FOTO_MB,
                    "lote_mb": mobile_upload.MAX_LOTE_MB, "plano_mb": mobile_upload.MAX_PLANO_REAL_MB,
                    "accept": mobile_upload.ACCEPT_FOTOS}}


@bp.errorhandler(RequestEntityTooLarge)
def _demasiado(_e):
    return render_template("pilot/error.html", msg="El envío es demasiado grande. Sube menos "
                           f"fotos o más livianas (máximo {mobile_upload.MAX_FOTOS} fotos, "
                           f"{mobile_upload.MAX_LOTE_MB} MB en total).",
                           back=url_for("pilot.elegir")), 413


@bp.get("/")
@auth.require
def elegir():
    return render_template("pilot/elegir.html", n=_resumen(), target=campaign.TARGET)


@bp.get("/panel")
@auth.require
def panel():
    m = campaign.load()
    tarjetas = {"real": [], "demo": []}
    for c in m["cases"]:
        if c["track"] not in campaign.TRACKS:
            continue
        if c["track"] == campaign.CREATE:
            campaign.settle(c["case_id"])
        s = _state(c)
        tarjetas["demo" if c.get("demo") else "real"].append({
            "case": c, "label": LABEL[c["track"]], "n": _ordinal(c), "estado": s["label"],
            "clase": _CLASE[s["label"]], "fecha": c["captured_on"],
            "rating": _rating_of(c["case_id"]), "thumbs": _thumbs(c)})
    return render_template("pilot/panel.html", n=_resumen(), target=campaign.TARGET,
                           tarjetas=tarjetas["real"], demos=tarjetas["demo"])


def _form_error(plantilla: str, msg: str, code: int = 400, **ctx):
    dup = _FIND_ID.search(msg)
    return render_template(plantilla, error=msg, dup=dup.group(0) if dup else None,
                           form=request.form, **ctx), code


@bp.get("/mejorar")
@auth.require
def mejorar_form():
    return render_template("pilot/mejorar_nuevo.html", error=None, dup=None, form={})


@bp.post("/mejorar")
@auth.require
def mejorar_post():
    f = request.files.get("plano")
    try:
        archivo = (f.filename, f.read()) if f and f.filename else None
        if archivo is None:
            raise campaign.CampaignError("Elige el plano que quieres mejorar.")
        cid = campaign.import_upload(campaign.IMPROVE, [archivo], author=_operator())
    except campaign.CampaignError as e:
        return _form_error("pilot/mejorar_nuevo.html", str(e))
    return redirect(url_for("pilot.caso", case_id=cid), code=303)


@bp.get("/crear")
@auth.require
def crear_form():
    return render_template("pilot/crear_nuevo.html", error=None, dup=None, form={})


def _m2(raw: str) -> Optional[float]:
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        x = float(raw)
    except ValueError:
        raise campaign.CampaignError("Los m² publicados deben ser un número.") from None
    if not (0 < x < 1e6):
        raise campaign.CampaignError("Los m² publicados deben ser un número mayor que cero.")
    return x


@bp.post("/crear")
@auth.require
def crear_post():
    try:
        # E45.2: cantidad y formato se revisan antes de leer un byte, y cada archivo se lee en
        # trozos con tope por archivo y por lote (nunca `read()` a ciegas)
        fotos = mobile_upload.leer_fotos(request.files.getlist("fotos"))
        gt_t = mobile_upload.leer_plano_real(request.files.get("plano_real"))
        cid = campaign.import_upload(
            campaign.CREATE, fotos, reference=request.form.get("referencia", ""),
            published_m2=_m2(request.form.get("m2", "")), ground_truth=gt_t, author=_operator())
    except (campaign.CampaignError, mobile_upload.UploadError) as e:
        return _form_error("pilot/crear_nuevo.html", str(e))
    return redirect(url_for("pilot.caso", case_id=cid), code=303)


@bp.get("/caso/<case_id>")
@auth.require
def caso(case_id: str):
    return _pagina(_case_or_404(case_id))


def _pagina(case: Dict[str, Any], error: Optional[str] = None, code: int = 200):
    v = _view(case)
    v["error"] = error
    html = render_template("pilot/caso.html", v=v, ratings=campaign.RATINGS,
                           rating_label={"EXCELENTE": "EXCELENTE", "BUENO": "BUENO", "MALO": "MALO",
                                         "PESIMO": "PÉSIMO"})
    return (html, code) if code != 200 else html


@bp.post("/caso/<case_id>/procesar")
@auth.require
def procesar(case_id: str):
    case = _case_or_404(case_id)
    try:
        if case["track"] == campaign.IMPROVE:
            if not campaign._of(case_id, "improve_started"):      # noqa: SLF001
                campaign.start_improve(case_id)
                campaign.finish_improve(case_id)
            else:
                campaign.finish_improve(case_id, retry_prepare=True)
        else:
            campaign.start_create(
                case_id, DEMO_ENGINE if case.get("demo") else CREATE_ENGINE,
                author=_operator(), confirm_paid=True)   # el botón dice que hay costo: es la confirmación
    except campaign.CampaignError as e:
        return _pagina(case, str(e), 409)
    return redirect(url_for("pilot.caso", case_id=case_id), code=303)


@bp.post("/caso/<case_id>/sin-resultado")
@auth.require
def sin_resultado(case_id: str):
    """«Dar por no resuelto»: queda escrito que NO hubo Plano Corporativo (nunca un éxito)."""
    case = _case_or_404(case_id)
    if case["track"] != campaign.IMPROVE:
        abort(404)
    try:
        campaign.finish_improve(case_id, give_up_reason="la planta no quedó lista: se dio por no "
                                "resuelto")
    except campaign.CampaignError as e:
        return _pagina(case, str(e), 409)
    return redirect(url_for("pilot.caso", case_id=case_id), code=303)


@bp.post("/caso/<case_id>/corregir")
@auth.require
def corregir(case_id: str):
    case = _case_or_404(case_id)
    if case["track"] != campaign.CREATE:
        abort(404)
    texto = (request.form.get("texto") or "").strip()
    try:
        if not texto:
            raise campaign.CampaignError("Escribe qué hay que corregir.")
        campaign.start_correction(case_id, texto, author=_operator(), confirm_paid=True)
    except (campaign.CampaignError, ReconError) as e:
        return _pagina(case, str(e), 400)
    return redirect(url_for("pilot.caso", case_id=case_id), code=303)


@bp.post("/caso/<case_id>/cerrar")
@auth.require
def cerrar(case_id: str):
    """CERRAR RECONSTRUCCIÓN Y COMPARAR: cierre ciego (con su auditoría) y, sólo si pasa, reveal."""
    case = _case_or_404(case_id)
    if case["track"] != campaign.CREATE:
        abort(404)
    if request.form.get("confirmo") != "1":
        return _pagina(case, "Para cerrar hay que confirmarlo: después no se puede seguir "
                             "corrigiendo.", 400)
    v = _view(case)
    if not v["puede_cerrar"] and not v["cerrado"]:
        return _pagina(case, "Todavía no hay una reconstrucción terminada que cerrar.", 409)
    try:
        if not v["cerrado"]:
            campaign.close_blind(case_id, campaign.last_done_run(case_id))
        if not v["revelado"]:
            campaign.reveal(case_id, author=_operator())
    except campaign.CampaignError as e:
        return _pagina(case, str(e), 409)
    return redirect(url_for("pilot.caso", case_id=case_id) + "#comparacion", code=303)


# --------------------------------------------------------------------------------------------
# evaluación: dos juicios independientes, con historial
# --------------------------------------------------------------------------------------------
def _yn(name: str) -> Optional[bool]:
    return {"si": True, "no": False}.get(request.form.get(name) or "")


def _comment(name: str) -> Optional[str]:
    t = (request.form.get(name) or "").strip()
    return t or None


@bp.post("/caso/<case_id>/evaluar/plano")
@auth.require
def evaluar_plano(case_id: str):
    case = _case_or_404(case_id)
    if not _view(case)["puede_evaluar_plano"]:
        return _pagina(case, "Todavía no hay un resultado que evaluar.", 409)
    prev = _last(case_id, "evaluation")
    try:
        mins = (request.form.get("minutos") or "").strip().replace(",", ".")
        data = {"schema": campaign.PILOT_SCHEMA, "rating": request.form.get("rating"),
                "comment": _comment("comentario"), "would_publish": _yn("publicaria"),
                "needed_human_correction": _yn("correccion_humana"),
                "human_minutes": float(mins) if mins else None,
                "supersedes_seq": prev["seq"] if prev else None}
        if data["would_publish"] is None or data["needed_human_correction"] is None:
            raise campaign.CampaignError("Responde las dos preguntas de sí o no.")
        campaign.record(case_id, "evaluation", data)
    except ValueError:
        return _pagina(case, "Los minutos deben ser un número.", 400)
    except campaign.CampaignError as e:
        return _pagina(case, str(e), 400)
    return redirect(url_for("pilot.caso", case_id=case_id) + "#evaluacion", code=303)


@bp.post("/caso/<case_id>/evaluar/ux")
@auth.require
def evaluar_ux(case_id: str):
    case = _case_or_404(case_id)
    if not _view(case)["puede_evaluar_ux"]:
        return _pagina(case, "La evaluación de la experiencia se hace al final del recorrido.", 409)
    prev = _last(case_id, "ux_evaluation")
    data = {"rating": request.form.get("rating"), "comment": _comment("comentario"),
            "understood_immediately": _yn("entendi"),
            "extra_step_comment": _comment("sobraba"), "missing_comment": _comment("faltaba"),
            "supersedes_seq": prev["seq"] if prev else None}
    try:
        if data["understood_immediately"] is None:
            raise campaign.CampaignError("Responde si entendiste de inmediato qué hacer.")
        campaign.record(case_id, "ux_evaluation", data)
    except campaign.CampaignError as e:
        return _pagina(case, str(e), 400)
    return redirect(url_for("pilot.caso", case_id=case_id) + "#evaluacion", code=303)


# --------------------------------------------------------------------------------------------
# archivos
# --------------------------------------------------------------------------------------------
def _send(path: str, mime: str, nombre: Optional[str] = None):
    resp = send_file(path, mimetype=mime, max_age=0, as_attachment=bool(nombre),
                     download_name=nombre)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.get("/caso/<case_id>/archivo/<cual>")
@auth.require
def archivo(case_id: str, cual: str):
    """Entrada, resultado, reconstrucción o plano real. El `cual` es un rol, nunca un nombre de
    archivo: lo que se sirve sale del manifiesto, no de la URL."""
    case = _case_or_404(case_id)
    tr = case["track"]
    if cual == "entrada" and tr == campaign.IMPROVE:
        p = _plan_preview(case)
        if p:
            return _send(p["path"], p["mime"])
    elif cual.startswith("foto-") and tr == campaign.CREATE and cual[5:].isdigit():
        fotos = _evidence(case, campaign.ROLE_PHOTO)
        i = int(cual[5:]) - 1
        if 0 <= i < len(fotos) and os.path.isfile(fotos[i]):
            ext = os.path.splitext(fotos[i])[1].lower()
            return _send(fotos[i], {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg"))
    elif cual == "despues" and tr == campaign.IMPROVE:
        from .domain import assets                                # noqa: PLC0415
        a = _improve_output(case)
        if a:
            return _send(assets.path_of(a), a["mime_type"],
                         "plano_corporativo.png" if request.args.get("descargar") else None)
    elif cual == "reconstruccion" and tr == campaign.CREATE:
        p = _recon_path(case)
        if p:
            return _send(p, "image/svg+xml")
    elif cual == "real" and tr == campaign.CREATE and _gt_visible(case):
        from .domain.reconstruction import groundtruth            # noqa: PLC0415
        s = groundtruth.serving_path(case["recon_project_id"])
        if s and os.path.isfile(s["path"]):
            return _send(s["path"], s["mime"])
    abort(404)          # incluido el plano real antes del reveal: para la web no existe
