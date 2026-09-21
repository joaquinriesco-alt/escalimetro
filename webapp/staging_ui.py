"""E31 §11 — REVISIÓN HUMANA de ambientación. Interna. La única autoridad sobre la fidelidad.

Acá se ve ORIGINAL contra CANDIDATO, lado a lado, con alternancia y cortina, y se decide:

    FIDELIDAD   PASS / FAIL (+ motivos)     ← compuerta dura
    CALIDAD     1–5, sólo si PASS
    PUBLICACIÓN aprobar / rechazar

El revisor puede rechazar una imagen atractiva, y debe hacerlo si cambió la propiedad. Los avisos
automáticos aparecen como lo que son: razones para mirar mejor, nunca un veredicto.

Vive en su propio Blueprint para que la superficie de cliente no tenga ni un enlace hacia acá.
"""
from __future__ import annotations

import json
import os

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

from . import auth, benchmark, providers
from .domain import assets, entitlements, fits, packs, presets, properties, staging

bp = Blueprint("staging", __name__, url_prefix="/staging")
REVIEWER = os.environ.get("ESCALIMETRO_REVIEWER", "Joaquín Riesco")
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "benchmarks", "staging_benchmark_v1.json")


def _manifest():
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


@bp.get("/")
@auth.require
def queue():
    return render_template(
        "staging.html", por_revisar=staging.pending_review_all(),
        por_generar=staging.needing_staging_all(), proveedores=providers.catalog(),
        seleccionado=os.environ.get(providers.ENV_SELECT) or "",
        manifiesto=_manifest(), estilos=presets.VISUAL_STYLES,
        propiedades={p["property_id"]: p for p in
                     (dict(r) for r in staging.store.q("SELECT property_id, title FROM properties"))},
        pendientes_cola=staging.pending())


@bp.post("/<property_id>/generate")
@auth.require
def generate(property_id):
    """Crea y encola UN intento para la foto principal. El estilo sale del programa base salvo
    que el operador lo cambie acá."""
    p = properties.get(property_id)
    if p is None:
        abort(404)
    h = staging.hero(property_id)
    if h is None:
        return render_template("error.html", msg="La propiedad no tiene foto principal elegida.",
                               back=url_for("staging.queue")), 400
    base = fits.base_of(property_id)
    estilo = request.form.get("visual_style") or (base or {}).get("visual_style") \
        or presets.DEFAULT_STYLE
    try:
        aid = staging.create_attempt(property_id, h["asset_id"], estilo,
                                     provider_name=request.form.get("provider") or None)
    except (staging.StagingError, entitlements.EntitlementError, presets.PresetError,
            staging.visual.VisualStagingError) as e:
        return render_template("error.html", msg=str(e), back=url_for("staging.queue")), 400
    staging.enqueue(aid)
    return redirect(url_for("staging.review_page", attempt_id=aid))


@bp.get("/attempt/<attempt_id>")
@auth.require
def review_page(attempt_id):
    a = staging.get(attempt_id)
    if a is None:
        abort(404)
    src = assets.get(a["source_asset_id"], a["property_id"])
    return render_template(
        "staging_review.html", a=a, src=src, p=properties.require(a["property_id"]),
        motivos=staging.FAILURE_REASONS, reviewer=REVIEWER,
        intentos=staging.list_for(a["property_id"], a["source_asset_id"], a["fit_id"],
                                  include_benchmark=True),
        retries_left=staging.retries_left(a["property_id"], a["source_asset_id"], a["fit_id"]),
        estado=staging.state(a["property_id"]), errores=[])


@bp.get("/attempt/<attempt_id>/image")
@auth.require
def candidate_image(attempt_id):
    """El CANDIDATO. Sólo desde acá, sólo autenticado. No es un asset y el cliente no lo ve."""
    a = staging.get(attempt_id)
    ruta = staging.candidate_path(a) if a else None
    if not ruta or not os.path.exists(ruta):
        abort(404)
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(
        os.path.splitext(ruta)[1], "image/png")
    return send_file(ruta, mimetype=mime)


@bp.post("/attempt/<attempt_id>/review")
@auth.require
def review(attempt_id):
    a = staging.get(attempt_id)
    if a is None:
        abort(404)
    f = request.form
    try:
        staging.review(attempt_id, fidelity=f.get("fidelity", ""),
                       quality=f.get("quality") or None, publication=f.get("publication", ""),
                       reasons=f.getlist("reasons"), notes=f.get("notes") or "",
                       reviewer=f.get("reviewer") or REVIEWER)
    except staging.ReviewError as e:
        a = staging.get(attempt_id)
        src = assets.get(a["source_asset_id"], a["property_id"])
        return render_template(
            "staging_review.html", a=a, src=src, p=properties.require(a["property_id"]),
            motivos=staging.FAILURE_REASONS, reviewer=REVIEWER,
            intentos=staging.list_for(a["property_id"], a["source_asset_id"], a["fit_id"],
                                      include_benchmark=True),
            retries_left=staging.retries_left(a["property_id"], a["source_asset_id"], a["fit_id"]),
            estado=staging.state(a["property_id"]), errores=[str(e)]), 400
    return redirect(url_for("staging.review_page", attempt_id=attempt_id))


@bp.post("/attempt/<attempt_id>/retry")
@auth.require
def retry(attempt_id):
    """Reintentar = OTRO intento (§17). El rechazado se conserva."""
    a = staging.get(attempt_id)
    if a is None:
        abort(404)
    try:
        nuevo = staging.create_attempt(a["property_id"], a["source_asset_id"], a["visual_style"],
                                       fit_id=a["fit_id"], provider_name=a["provider"])
    except (staging.StagingError, entitlements.EntitlementError,
            staging.visual.VisualStagingError) as e:
        return render_template("error.html", msg=str(e),
                               back=url_for("staging.review_page", attempt_id=attempt_id)), 400
    staging.enqueue(nuevo)
    return redirect(url_for("staging.review_page", attempt_id=nuevo))


@bp.post("/<property_id>/override")
@auth.require
def override(property_id):
    """§21 — un pack degradado sólo con motivo escrito. Vacío lo quita."""
    if properties.get(property_id) is None:
        abort(404)
    packs.set_override(property_id, request.form.get("reason") or "")
    return redirect(url_for("customer.detail", property_id=property_id))


@bp.post("/<property_id>/fits/<fit_id>/generate")
@auth.require
def generate_for_fit(property_id, fit_id):
    """§25 — «Ambientar para esta propuesta», detrás del derecho Pro. Mínimo: la relación existe."""
    if fits.get(fit_id, property_id) is None:
        abort(404)
    h = staging.hero(property_id)
    if h is None:
        return render_template("error.html", msg="La propiedad no tiene foto principal elegida.",
                               back=url_for("staging.queue")), 400
    f = fits.require(fit_id, property_id)
    try:
        aid = staging.create_attempt(property_id, h["asset_id"], f["visual_style"], fit_id=fit_id)
    except (staging.StagingError, entitlements.EntitlementError,
            staging.visual.VisualStagingError) as e:
        return render_template("error.html", msg=str(e), back=url_for("staging.queue")), 400
    staging.enqueue(aid)
    return redirect(url_for("staging.review_page", attempt_id=aid))


@bp.get("/benchmark")
@auth.require
def benchmark_page():
    man = _manifest()
    return render_template("staging_benchmark.html", manifiesto=man,
                           errores=benchmark.validate_manifest(man) if man else ["sin manifiesto"],
                           proveedores=providers.catalog(), gate=benchmark.GATE,
                           criterios=staging.visual.PILOT_CRITERIA)
