"""E17.0 — LA RUTA NUEVA: `/property`.

Es una superficie **aislada**. No reemplaza el LAB, no comparte su navegación y no toca su
producto. Vive aparte porque contesta otra pregunta a otra persona: el LAB prepara material para
publicar una oficina que trabajamos nosotros; esto diagnostica un aviso que alguien ya publicó.

La pantalla de entrada tiene una sola pregunta y un solo botón. Todo lo demás —cargar fotos,
completar datos, pedir el análisis del plano— aparece después del primer resultado, cuando ya hay
algo que mejorar. Pedirlo antes sería cobrar el formulario por adelantado.
"""
from __future__ import annotations

import os
from typing import Optional

from flask import (Blueprint, abort, jsonify, redirect, render_template, request, send_file,
                   url_for)

from . import auth, store
from .domain.potential import (analyzer, demos, fetcher, interventions as iv, listings, plans,
                               reviews as previews, urlingest)

bp = Blueprint("potential", __name__, url_prefix="/property")


def _l(listing_id: str):
    d = listings.get(listing_id)
    if not d:
        abort(404)
    return d


def _page(listing_id: str, errores=None, code: int = 200):
    l = _l(listing_id)
    html = render_template(
        "potential/listing.html", l=l, errores=errores or [],
        report=analyzer.latest(listing_id),
        photos=listings.media_of(listing_id, listings.PHOTO),
        conceptual=listings.media_of(listing_id, listings.CONCEPTUAL),
        plan=plans.state(listing_id), spatial=plans.capability(listing_id),
        demos_list=demos.of_listing(listing_id), demo_status=demos.STATUS_LABEL,
        types=listings.PROPERTY_TYPES, type_label=listings.TYPE_LABEL,
        catalog=iv.CATALOG, disclosure=iv.DISCLOSURE,
        units=plans.unit_state(listing_id),
        provenance=urlingest.provenance(listing_id),
        ingest_status_label=urlingest.STATUS_LABEL, ingest_reasons=urlingest.REASON_LABEL,
        review=previews.get(listing_id) or {},
        diagnoses=previews.DIAGNOSES, diagnosis_label=previews.DIAGNOSIS_LABEL,
        opportunities=previews.OPPORTUNITIES, opportunity_label=previews.OPPORTUNITY_LABEL,
        contact_opts=previews.CONTACT, contact_label=previews.CONTACT_LABEL,
        history=analyzer.history(listing_id))
    return (html, code) if code != 200 else html


# =================================================================================================
# entrada
# =================================================================================================
@bp.get("/")
@auth.require
def home():
    return render_template("potential/home.html", rows=listings.listing_rows())


@bp.post("/analizar")
@auth.require
def analizar():
    """E17.2 §1 — EL LINK ES EL INPUT. Se pega una URL y el sistema trae lo que pueda: datos,
    fotos y plano. El usuario sólo interviene si algo queda ambiguo.

    Sin URL se crea igual y se carga a mano: el camino manual no desaparece, deja de ser el
    principal."""
    f = request.form
    url = (f.get("url") or "").strip()
    if not url:
        lid = listings.create(title=(f.get("title") or "").strip(), source=listings.MANUAL)
        analyzer.run(lid)
        return redirect(url_for("potential.listing", listing_id=lid))
    res = urlingest.ingest_url(url)
    lid = res["listing_id"]
    # Si vino un plano en la galería, se le pregunta al modelo de candidatos de E35 cuál es la
    # unidad ANTES de analizar: así la pregunta aparece en el primer informe y no en el segundo.
    if res["floorplans"]:
        plans.resolve_units(lid)
        if not plans.needs_unit_pick(lid):
            try:
                plans.analyze(lid)
            except (listings.ListingError, ValueError):
                pass                                           # el plano no se deja leer: se dice en el informe
    analyzer.run(lid)
    return redirect(url_for("potential.listing", listing_id=lid))


@bp.post("/l/<listing_id>/reintentar")
@auth.require
def reintentar(listing_id):
    """§16 — [ Reintentar ]. Un portal que falló una vez puede no fallar la siguiente."""
    l = _l(listing_id)
    if not l["source_url"]:
        return _page(listing_id, ["este aviso no tiene una publicación de origen"], 400)
    urlingest.ingest_url(l["source_url"], listing_id=listing_id)
    if plans.plan_media(listing_id):
        plans.resolve_units(listing_id)
    analyzer.run(listing_id)
    return redirect(url_for("potential.listing", listing_id=listing_id))


@bp.get("/l/<listing_id>")
@auth.require
def listing(listing_id):
    return _page(listing_id)


@bp.post("/l/<listing_id>/datos")
@auth.require
def datos(listing_id):
    _l(listing_id)
    try:
        # §9 — lo que corrige una persona queda marcado MANUAL_OVERRIDE y ya no lo pisa una
        # reextracción. Corregir un dato y que el siguiente análisis lo borre haría inútil
        # corregirlo.
        urlingest.manual_override(listing_id, {k: request.form.get(k) for k in listings.CAMPOS
                                               if k in request.form})
    except listings.ListingError as e:
        return _page(listing_id, [str(e)], 400)
    analyzer.run(listing_id)
    return redirect(url_for("potential.listing", listing_id=listing_id) + "#informe")


@bp.post("/l/<listing_id>/material")
@auth.require
def material(listing_id):
    _l(listing_id)
    errores = []
    for archivo in request.files.getlist("photos"):
        if not (archivo and archivo.filename):
            continue
        try:
            listings.add_media(listing_id, archivo, listings.PHOTO)
        except listings.ListingError as e:
            errores.append(f"{archivo.filename}: {e}")
    plano = request.files.get("plan")
    if plano and plano.filename:
        try:
            listings.add_media(listing_id, plano, listings.PLAN)
        except listings.ListingError as e:
            errores.append(f"{plano.filename}: {e}")
    if errores:
        return _page(listing_id, errores, 400)
    analyzer.run(listing_id)
    return redirect(url_for("potential.listing", listing_id=listing_id) + "#informe")


@bp.post("/l/<listing_id>/portada")
@auth.require
def portada(listing_id):
    _l(listing_id)
    try:
        listings.set_cover(listing_id, (request.form.get("media_id") or "").strip() or None)
    except listings.ListingError as e:
        return _page(listing_id, [str(e)], 400)
    analyzer.run(listing_id)
    return redirect(url_for("potential.listing", listing_id=listing_id) + "#informe")


@bp.post("/l/<listing_id>/reanalizar")
@auth.require
def reanalizar(listing_id):
    _l(listing_id)
    analyzer.run(listing_id)
    return redirect(url_for("potential.listing", listing_id=listing_id) + "#informe")


@bp.get("/l/<listing_id>/m/<media_id>")
@auth.require
def media(listing_id, media_id):
    m = listings.media(media_id, listing_id)
    if not m:
        abort(404)
    ruta = listings.media_path(m)
    if not os.path.exists(ruta):
        abort(404)
    return send_file(ruta, mimetype=m["mime_type"])


# =================================================================================================
# capacidad espacial — el motor existente, invocado, no copiado
# =================================================================================================
@bp.post("/l/<listing_id>/plano/analizar")
@auth.require
def plano_analizar(listing_id):
    """Corre el pipeline de planos EXISTENTE sobre el plano del aviso.

    Es una acción explícita y no parte del informe: hacer esperar unos segundos a quien sólo
    quería ver su score sería cobrarle el costo de una capacidad que todavía no pidió."""
    _l(listing_id)
    try:
        plans.analyze(listing_id)
    except (listings.ListingError, ValueError) as e:
        return _page(listing_id, [str(e)], 400)
    analyzer.run(listing_id)
    return redirect(url_for("potential.listing", listing_id=listing_id) + "#espacial")


@bp.get("/l/<listing_id>/unidades.png")
@auth.require
def unidades_png(listing_id):
    """La lámina con las unidades candidatas pintadas. El dibujo lo hace `domain.units`, el mismo
    que usa el LAB: si hubiera dos paletas, el número del plano dejaría de coincidir con el del
    botón el día que alguien toque una."""
    _l(listing_id)
    destino = os.path.join(store.listing_dir(listing_id), "unidades.png")
    ruta = plans.candidates_overlay(listing_id, destino)
    if not ruta:
        abort(404)
    return send_file(ruta, mimetype="image/png", max_age=0)


@bp.post("/l/<listing_id>/unidad")
@auth.require
def elegir_unidad(listing_id):
    """UN clic. Persiste la selección, vuelve a correr el motor y sigue en esta misma pantalla.

    No crea una `property`, no crea una concesión de pack y no toca nada del LAB: lo único que se
    guarda es qué región de la lámina es la de este aviso."""
    _l(listing_id)
    try:
        plans.pick_unit(listing_id, (request.form.get("candidate_id") or "").strip())
        plans.analyze(listing_id)
    except (listings.ListingError, ValueError) as e:
        return _page(listing_id, [str(e)], 400)
    analyzer.run(listing_id)
    return redirect(url_for("potential.listing", listing_id=listing_id) + "#espacial")


@bp.post("/l/<listing_id>/revision")
@auth.require
def revision(listing_id):
    """§4 — la revisión humana del diagnóstico, para el dogfood de 20 avisos."""
    _l(listing_id)
    f = request.form
    try:
        previews.save(listing_id, diagnosis=(f.get("diagnosis") or "").strip() or None,
                      opportunity=(f.get("opportunity") or "").strip() or None,
                      worth_contacting=(f.get("worth_contacting") or "").strip() or None,
                      comment=f.get("comment") or "")
    except previews.ReviewError as e:
        return _page(listing_id, [str(e)], 400)
    return redirect(url_for("potential.listing", listing_id=listing_id) + "#revision")


@bp.get("/dogfood")
@auth.require
def dogfood():
    """§5 — el tablero de la muestra. Secundario: el producto es el informe."""
    return render_template("potential/dogfood.html", panel=previews.dashboard())


@bp.post("/l/<listing_id>/demo")
@auth.require
def demo(listing_id):
    """Registra el contrato de una demostración. No simula nada: si no hay proveedor aprobado, la
    demo queda `NOT_AVAILABLE` con el motivo escrito."""
    _l(listing_id)
    try:
        demos.request(listing_id, (request.form.get("intervention") or "").strip(),
                      (request.form.get("media_id") or "").strip() or None)
    except demos.DemoError as e:
        return _page(listing_id, [str(e)], 400)
    return redirect(url_for("potential.listing", listing_id=listing_id) + "#demos")


@bp.get("/l/<listing_id>/report.json")
@auth.require
def report_json(listing_id):
    """El informe completo, con la aritmética. Existe para que el score se pueda auditar sin leer
    el código: cada criterio con su medición, su peso y sus puntos."""
    _l(listing_id)
    r = analyzer.latest(listing_id)
    if not r:
        abort(404)
    return jsonify({"listing_id": listing_id, "score": r["score"], "max_score": r["max_score"],
                    "analyzer_version": r["analyzer_version"],
                    "engine_version": r["engine_version"],
                    "created_at": r["created_at"],
                    "dimensions": r["dimensions_obj"],
                    "capabilities": r["capabilities_obj"],
                    "findings": [{k: f[k] for k in
                                  ("code", "dimension", "level", "headline", "explanation",
                                   "intervention", "score_delta", "rank")}
                                 | {"evidence": f["evidence_obj"]} for f in r["findings"]],
                    "_note": "el score mide qué tan bien la publicación muestra el potencial del "
                             "inmueble. No es una predicción de venta."})
