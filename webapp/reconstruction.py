"""E37 — la superficie del Internal Reconstruction Lab, en `/lab/reconstruction/`.

Herramienta interna de aprendizaje, no producto: comparte el marco visual del LAB pero no su
navegación (los tests fijan ese menú en dos enlaces). Se llega desde Ajustes → Herramientas
técnicas, o escribiendo la dirección.

El flujo visible es el que pide la TASK:
PROYECTOS → NUEVO PROYECTO → INPUTS / PLANO REAL OCULTO → MOTOR → GENERAR → RESULTADO → CALIFICAR →
CORREGIR → NUEVA CORRIDA → COMPARAR → REVELAR.

Dos protecciones propias de esta superficie, porque acá un POST puede gastar dinero o revelar el
plano real:

* **mismo origen.** La app se autentica con HTTP Basic, que el navegador reenvía solo; sin esto,
  un formulario en otro sitio podría lanzar una corrida paga o un reveal. Un POST cuyo `Origin` o
  `Referer` apunte a otro host se rechaza;
* **tope de subida propio.** 34 fotos de teléfono en un solo envío superan el tope general de la
  app, pensado para una planta. Acá se sube lo que haga falta, en uno o varios lotes.
"""
from __future__ import annotations

import os
from typing import List, Optional

from flask import (Blueprint, abort, jsonify, redirect, render_template, request, send_file,
                   url_for)
from werkzeug.exceptions import RequestEntityTooLarge

from . import auth, origin_guard as origen_guard
from .domain.reconstruction import contract, engines, groundtruth, projects, runs

bp = Blueprint("reconstruction", __name__, url_prefix="/lab/reconstruction")

FLOW = ("PROYECTOS", "NUEVO PROYECTO", "INPUTS / PLANO REAL OCULTO", "MOTOR", "GENERAR",
        "RESULTADO", "CALIFICAR", "CORREGIR", "NUEVA CORRIDA", "COMPARAR", "REVELAR")


def _operator() -> str:
    return os.environ.get("ESCALIMETRO_REVIEWER", "Joaquín Riesco")


def max_request_mb() -> int:
    return int(os.environ.get("ESCALIMETRO_RECON_MAX_REQUEST_MB", "1200"))


@bp.before_request
def _guardas():
    """Un POST tiene que decir de dónde viene, y venir de acá. Falla cerrada: `Origin: null` (un
    documento opaco, un iframe aislado) o ninguna cabecera no alcanzan. Los navegadores mandan
    `Origin` en todo POST; un script propio lo agrega (ver `docs/E37_RECONSTRUCTION_LAB.md`)."""
    if request.method != "POST":
        return None
    if origen_guard.origen_ajeno(estricto=True):       # E47.4: la lógica es común a toda la app
        abort(403)
    request.max_content_length = max_request_mb() * 1024 * 1024
    return None


@bp.errorhandler(RequestEntityTooLarge)
def _demasiado(_e):
    return render_template("recon/error.html", msg=(
        f"El envío supera {max_request_mb()} MB. Sube las fotos en varios lotes desde la página "
        "del proyecto."), back=url_for("reconstruction.index")), 413


def _err(msg: str, back: str, code: int = 400):
    return render_template("recon/error.html", msg=msg, back=back), code


def _project_or_404(project_id: str):
    p = projects.get(project_id)
    if p is None:
        abort(404)
    return p


def _flow_state(p: Optional[dict], corridas: List[dict]) -> dict:
    """Qué pasos del flujo ya ocurrieron. Se deriva de lo guardado, no se declara."""
    hechos = {"PROYECTOS", "NUEVO PROYECTO"} if p else {"PROYECTOS"}
    if p:
        if projects.assets_of(p["project_id"]):
            hechos.add("INPUTS / PLANO REAL OCULTO")
        if corridas:
            hechos |= {"MOTOR", "GENERAR"}
        if any(r["status"] == runs.DONE for r in corridas):
            hechos.add("RESULTADO")
        if any(runs.current_rating(r["run_id"]) for r in corridas):
            hechos.add("CALIFICAR")
        if any(r["origin"] == runs.CORRECTION for r in corridas):
            hechos |= {"CORREGIR", "NUEVA CORRIDA"}
        if len([r for r in corridas if r["status"] == runs.DONE]) >= runs.COMPARE_MIN:
            hechos.add("COMPARAR")
        if p["gt_state"] == groundtruth.REVEALED:
            hechos.add("REVELAR")
    return {"steps": FLOW, "done": hechos}


# ---------------------------------------------------------------------------------------------
# proyectos
# ---------------------------------------------------------------------------------------------
@bp.get("/")
@auth.require
def index():
    return render_template("recon/index.html", proyectos=projects.listing(),
                           motores=engines.catalog(), flow=_flow_state(None, []))


@bp.get("/nuevo")
@auth.require
def new():
    return render_template("recon/new.html", campos=projects.DECLARED_FIELDS, errores=[],
                           form={}, flow=_flow_state(None, []))


@bp.post("/nuevo")
@auth.require
def create():
    f = request.form
    errores: List[str] = []
    try:
        declarados = projects.parse_declared(f)
    except projects.ReconError as e:
        errores.append(str(e))
        declarados = {}
    if not (f.get("name") or "").strip():
        errores.append("El proyecto necesita un nombre.")
    if errores:
        return render_template("recon/new.html", campos=projects.DECLARED_FIELDS,
                               errores=errores, form=f, flow=_flow_state(None, [])), 400
    pid = projects.create(f.get("name"), declarados, _operator())
    avisos = _recibir(pid)
    return redirect(url_for("reconstruction.project", project_id=pid,
                            avisos=len(avisos) or None) + "#inputs")


def _recibir(pid: str) -> List[str]:
    """Fotos, videos, documentos y plano real de un mismo formulario. Un archivo malo no tumba el
    resto: su error queda en la bitácora y se muestra en la página del proyecto."""
    mensajes: List[str] = []
    # El plano real PRIMERO: si el mismo archivo viene también entre las fotos, gana la intención
    # explícita (es el plano real, oculto) y la foto se rechaza. Al revés, el plano quedaría como
    # input del motor y el proyecto dejaría de ser ciego.
    gt = request.files.get("ground_truth")
    if gt and gt.filename:
        try:
            groundtruth.upload(pid, gt, _operator())
        except projects.ReconError as e:
            mensajes.append(f"Plano real: {e}")
    for campo, kind in (("photos", projects.PHOTO), ("videos", projects.VIDEO),
                        ("documents", projects.DOCUMENT)):
        _, m = projects.add_many(pid, request.files.getlist(campo), kind, _operator())
        mensajes += m
    if mensajes:
        projects.log(pid, "UPLOAD_NOTES", {"messages": mensajes[:60]}, author=_operator())
    return mensajes


def _ultimos_avisos(pid: str) -> List[str]:
    for e in projects.events(pid, limit=20):
        if e["kind"] == "UPLOAD_NOTES":
            return e["detail"].get("messages") or []
        if e["kind"] in ("ASSETS_ADDED", "GT_UPLOADED", "GT_REPLACED"):
            continue
        break
    return []


@bp.get("/p/<project_id>")
@auth.require
def project(project_id: str):
    return _project_page(project_id)


def _project_page(project_id: str, errores: Optional[List[str]] = None, code: int = 200):
    p = _project_or_404(project_id)
    corridas = runs.of_project(project_id)
    tarjetas = [runs.card(r, p) for r in corridas]
    hijos = {}
    for r in corridas:
        hijos.setdefault(r["parent_run_id"], []).append(r["run_id"])
    avisos = _ultimos_avisos(project_id) if request.args.get("avisos") else []
    html = render_template(
        "recon/project.html", p=p, errores=errores or [], avisos=avisos,
        fotos=projects.assets_of(project_id, projects.PHOTO),
        videos=projects.assets_of(project_id, projects.VIDEO),
        documentos=projects.assets_of(project_id, projects.DOCUMENT),
        retirados=[a for a in projects.assets_of(project_id, include_retired=True)
                   if a["retired_at"]],
        campos=projects.DECLARED_FIELDS, gt_existe=groundtruth.exists(project_id),
        gt=groundtruth.revealed_info(project_id), motores=engines.catalog(),
        tarjetas=tarjetas, por_id={t["run"]["run_id"]: t for t in tarjetas}, hijos=hijos,
        metricas=runs.metrics(project_id), juicio=projects.current_judgment(project_id),
        escala=projects.JUDGMENT_SCALE, escala_label=projects.JUDGMENT_LABEL,
        rating_label=runs.RATING_LABEL, bitacora=projects.events(project_id, limit=40),
        flow=_flow_state(p, corridas))
    return (html, code) if code != 200 else html


@bp.post("/p/<project_id>/inputs")
@auth.require
def add_inputs(project_id: str):
    _project_or_404(project_id)
    avisos = _recibir(project_id)
    return redirect(url_for("reconstruction.project", project_id=project_id,
                            avisos=len(avisos) or None) + "#inputs")


@bp.post("/p/<project_id>/datos")
@auth.require
def update_declared(project_id: str):
    _project_or_404(project_id)
    try:
        projects.update_declared(project_id, projects.parse_declared(request.form), _operator())
    except projects.ReconError as e:
        return _project_page(project_id, [str(e)], 400)
    return redirect(url_for("reconstruction.project", project_id=project_id) + "#datos")


@bp.post("/p/<project_id>/asset/<asset_id>/retirar")
@auth.require
def retire(project_id: str, asset_id: str):
    _project_or_404(project_id)
    try:
        projects.retire_asset(project_id, asset_id, _operator())
    except projects.ReconError as e:
        return _project_page(project_id, [str(e)], 400)
    return redirect(url_for("reconstruction.project", project_id=project_id) + "#inputs")


@bp.get("/p/<project_id>/asset/<asset_id>")
@auth.require
def asset(project_id: str, asset_id: str):
    a = projects.get_asset(project_id, asset_id)
    if a is None or not projects.input_allowed(project_id, a["sha256"]):
        abort(404)                             # un input igual al plano real oculto no se sirve
    ruta = projects.asset_path(a)
    if not os.path.exists(ruta):
        abort(404)
    return send_file(ruta, mimetype=a["mime_type"])


# ---------------------------------------------------------------------------------------------
# plano real
# ---------------------------------------------------------------------------------------------
@bp.post("/p/<project_id>/plano-real")
@auth.require
def upload_gt(project_id: str):
    _project_or_404(project_id)
    f = request.files.get("ground_truth")
    if not f or not f.filename:
        return _project_page(project_id, ["Elige el archivo del plano real."], 400)
    try:
        groundtruth.upload(project_id, f, _operator())
    except projects.ReconError as e:
        return _project_page(project_id, [str(e)], 400)
    return redirect(url_for("reconstruction.project", project_id=project_id) + "#plano-real")


@bp.get("/p/<project_id>/plano-real")
@auth.require
def serve_gt(project_id: str):
    _project_or_404(project_id)
    s = groundtruth.serving_path(project_id)
    if s is None or not os.path.exists(s["path"]):
        abort(404)                                           # oculto: no existe para la UI
    return send_file(s["path"], mimetype=s["mime"], max_age=0)


@bp.post("/p/<project_id>/revelar")
@auth.require
def reveal(project_id: str):
    _project_or_404(project_id)
    if request.form.get("confirm") != "1":
        return _project_page(project_id, ["Para revelar el plano real hay que confirmarlo."], 400)
    try:
        groundtruth.reveal(project_id, _operator())
    except projects.ReconError as e:
        return _project_page(project_id, [str(e)], 400)
    return redirect(url_for("reconstruction.project", project_id=project_id) + "#plano-real")


# ---------------------------------------------------------------------------------------------
# corridas
# ---------------------------------------------------------------------------------------------
@bp.post("/p/<project_id>/generar")
@auth.require
def generate(project_id: str):
    _project_or_404(project_id)
    f = request.form
    try:
        rid = runs.create_initial(project_id, f.get("engine_id") or "", _operator(),
                                  confirm_paid=f.get("confirm_paid") == "1")
    except projects.ReconError as e:
        return _project_page(project_id, [str(e)], 400)
    runs.enqueue(rid)
    return redirect(url_for("reconstruction.run_view", project_id=project_id, run_id=rid))


@bp.get("/p/<project_id>/r/<run_id>")
@auth.require
def run_view(project_id: str, run_id: str):
    return _run_page(project_id, run_id)


def _run_page(project_id: str, run_id: str, errores: Optional[List[str]] = None, code: int = 200):
    p = _project_or_404(project_id)
    r = runs.get_in_project(project_id, run_id)
    if r is None:
        abort(404)
    adapter = engines.get(r["engine_id"])
    html = render_template(
        "recon/run.html", p=p, r=r, t=runs.card(r, p), errores=errores or [],
        linaje=runs.lineage(r), hijos=runs.children(run_id),
        historial=runs.rating_history(run_id), ratings=runs.RATINGS,
        rating_label=runs.RATING_LABEL, placed=contract.placed(r["output"] or {}),
        unplaced=contract.unplaced(r["output"] or {}),
        motor=adapter.describe() if adapter else None,
        corregible=runs.correctable(r), kind_label=runs.CONNECTION_LABEL,
        type_label=runs.ROOM_TYPE_LABEL,
        rel_label=runs.RELATION_LABEL, impact_label=runs.IMPACT_LABEL,
        low=contract.LOW_CONFIDENCE, flow=_flow_state(p, runs.of_project(project_id)))
    return (html, code) if code != 200 else html


@bp.get("/p/<project_id>/r/<run_id>/plano.svg")
@auth.require
def run_svg(project_id: str, run_id: str):
    r = runs.get_in_project(project_id, run_id)
    ruta = runs.svg_path(r) if r else None
    if not ruta:
        abort(404)
    # el archivo guardado al cerrar la corrida, no un dibujo nuevo: si el renderer cambia, las
    # corridas viejas siguen mostrando lo que mostraban
    return send_file(ruta, mimetype="image/svg+xml", max_age=0)


@bp.get("/p/<project_id>/r/<run_id>/status.json")
@auth.require
def run_status(project_id: str, run_id: str):
    r = runs.get_in_project(project_id, run_id)
    if r is None:
        abort(404)
    return jsonify({"run_id": r["run_id"], "status": r["status"], "outcome": r["outcome"],
                    "finished": r["finished_at"] is not None})


@bp.post("/p/<project_id>/r/<run_id>/calificar")
@auth.require
def rate(project_id: str, run_id: str):
    _project_or_404(project_id)
    try:
        runs.rate(project_id, run_id, request.form.get("rating") or "",
                  request.form.get("comment") or "", _operator())
    except projects.ReconError as e:
        return _run_page(project_id, run_id, [str(e)], 400)
    return redirect(url_for("reconstruction.run_view", project_id=project_id, run_id=run_id)
                    + "#calificar")


@bp.post("/p/<project_id>/r/<run_id>/corregir")
@auth.require
def correct(project_id: str, run_id: str):
    _project_or_404(project_id)
    f = request.form
    try:
        rid = runs.create_correction(project_id, run_id, f.get("instruction") or "", _operator(),
                                     confirm_paid=f.get("confirm_paid") == "1")
    except projects.ReconError as e:
        return _run_page(project_id, run_id, [str(e)], 400)
    runs.enqueue(rid)
    return redirect(url_for("reconstruction.run_view", project_id=project_id, run_id=rid))


@bp.get("/p/<project_id>/comparar")
@auth.require
def compare(project_id: str):
    p = _project_or_404(project_id)
    try:
        columnas = runs.compare(project_id, request.args.getlist("r"))
    except projects.ReconError as e:
        return _project_page(project_id, [str(e)], 400)
    return render_template("recon/compare.html", p=p, columnas=columnas,
                           gt=groundtruth.revealed_info(project_id),
                           rating_label=runs.RATING_LABEL,
                           flow=_flow_state(p, runs.of_project(project_id)))


@bp.post("/p/<project_id>/cierre")
@auth.require
def judgment(project_id: str):
    _project_or_404(project_id)
    try:
        projects.save_judgment(project_id, request.form, _operator())
    except projects.ReconError as e:
        return _project_page(project_id, [str(e)], 400)
    return redirect(url_for("reconstruction.project", project_id=project_id) + "#metricas")
