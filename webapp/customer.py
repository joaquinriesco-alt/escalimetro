"""E28.5 / E30 — SUPERFICIE DE CLIENTE. Separada de ESCALÍMETRO INTERNAL.

La frontera es real aunque hoy no haya roles: vive en su propio Blueprint, sus propias plantillas
(`templates/customer/`) y su propio vocabulario. Un cliente que entre acá no ve —ni puede navegar
hacia— shell, núcleo, pilares, confirmaciones geométricas ni corridas del solver.

E30 §4 — esta superficie sirve a DOS productos que no se mezclan:

    Pack de publicación   una propiedad, un pack, una alternativa representativa. Es un ENTREGABLE.
    Escalímetro Pro       muchos prospectos sobre la misma planta preparada. Es un FLUJO.

Cuál de los dos está activo lo dice `entitlements`, y cuando dice que no, **el dominio corta**: acá
sólo se traduce ese corte a un 403 con un texto que explica qué producto lo incluye. Si la única
defensa fuera esconder el botón, el límite del producto sería una sugerencia.

DEUDA DECLARADA (§9 de E28): la autenticación sigue siendo una sola cuenta compartida. Esto NO es
un sistema de roles: un usuario autenticado puede escribir a mano una URL interna y llegar.
Separar de verdad exige RBAC. Es lo primero a resolver antes de que esto vea a un cliente real, y
por eso tampoco existe todavía un enlace público de propuesta (ver `domain/proposal.py`).
"""
from __future__ import annotations

import os

from flask import (Blueprint, abort, redirect, render_template, request, send_file, url_for)

from . import auth, briefs as briefmod, store
from .domain import (assets, branding, entitlements, fits, floorplan, packs, presets, properties,
                     staging)

bp = Blueprint("customer", __name__, url_prefix="/properties")


@bp.errorhandler(entitlements.EntitlementError)
def _sin_derecho(e):
    """Un límite de producto no es un error: es la diferencia entre lo que se compró y lo otro."""
    return render_template("customer/locked.html", msg=str(e),
                           modo=entitlements.summary()), 403


@bp.app_errorhandler(entitlements.EntitlementError)
def _sin_derecho_global(e):
    return render_template("customer/locked.html", msg=str(e),
                           modo=entitlements.summary()), 403


@bp.context_processor
def _ctx():
    """`puede_crear` se calcula acá y no en la plantilla: el tope de propiedades es una regla de
    producto, y una plantilla que la adivine con un `or not lista` termina mintiendo en las
    pantallas donde esa lista no existe."""
    tope = entitlements.limit("properties")
    return {"producto": entitlements.summary(), "corredora": branding.brokerage(),
            "puede_crear": tope is None or len(properties.listing()) < tope,
            "porque": fits.SELECTED_BY_LABEL}


def _pasos(v):
    """Los pasos que el cliente ve. Uno por fila, con estado. Nada más."""
    pid = v["property"]["property_id"]
    t = floorplan.technical_state(pid)
    plano_com = assets.first_of_kind(pid, assets.FLOORPLAN_COMMERCIAL)
    layouts = assets.list_of_kind(pid, assets.LAYOUT_RENDER)
    fotos = assets.list_of_kind(pid, assets.PHOTO_ORIGINAL)
    pack = packs.get(pid)
    base = fits.base_of(pid)
    una = not entitlements.allows(entitlements.ABC_ALTERNATIVES)
    st = staging.state(pid)
    listo = packs.readiness(pid)
    return [
        {"nombre": "Plano",
         "estado": "listo" if plano_com else ("preparando" if t["case_id"] else "pendiente"),
         "detalle": "Recibido y preparado" if plano_com else
                    ("Estamos preparando la planta" if t["case_id"] else "Falta subir el plano")},
        {"nombre": "Programa",
         "estado": "listo" if (base and base["headcount"]) else "pendiente",
         "detalle": f'{base["headcount"]} personas · '
                    f'{presets.PRESET_LABEL.get(base["workplace_preset"], "")}'
                    if (base and base["headcount"]) else "Falta decirnos cuántas personas son"},
        {"nombre": "Alternativa representativa" if una else "Alternativas de layout",
         "estado": "listo" if layouts else "pendiente",
         "detalle": (f"{len(layouts)} alternativa(s)" if layouts else "Todavía no disponibles")},
        {"nombre": "Fotos",
         "estado": "listo" if fotos else "pendiente",
         "detalle": f"{len(fotos)} foto(s) recibidas" if fotos else "Todavía no subiste fotos"},
        {"nombre": "Imagen ambientada",
         "estado": "listo" if st["state"] == "APPROVED" else "pendiente",
         "detalle": st["customer_text"]},
        {"nombre": "Pack de publicación",
         "estado": "listo" if (pack and pack["export_name"] and listo["state"] in ("READY", "DEGRADED"))
                   else "pendiente",
         "detalle": ("Listo para descargar" if (pack and pack["export_name"]
                                               and listo["state"] in ("READY", "DEGRADED"))
                     else ("Falta: " + ", ".join(listo["missing"]) if listo["missing"]
                           else "Se arma cuando todo lo anterior esté listo"))},
    ]


def _prop_or_404(property_id):
    p = properties.get(property_id)
    if p is None:
        abort(404)
    return p


def _fit_or_404(property_id, fit_id):
    f = fits.get(fit_id, property_id)
    if f is None:
        abort(404)
    return f


# =============================================================================================
# propiedades
# =============================================================================================
@bp.get("/")
@auth.require
def index():
    return render_template("customer/list.html", propiedades=properties.listing())


@bp.get("/new")
@auth.require
def new():
    _comprobar_cupo_propiedades()
    return render_template("customer/new.html", errors={}, form=None)


def _comprobar_cupo_propiedades():
    """§17 — el pack de publicación cubre una propiedad. El tope se comprueba en el servidor."""
    tope = entitlements.limit("properties")
    if tope is not None and len(properties.listing()) >= tope:
        raise entitlements.EntitlementError(entitlements.MULTIPLE_PROPERTIES)


@bp.post("/new")
@auth.require
def create():
    _comprobar_cupo_propiedades()
    f = request.form
    titulo = (f.get("title") or "").strip()
    if not titulo:
        return render_template("customer/new.html", form=f,
                               errors={"title": "Ponle un nombre a la propiedad."}), 400
    area = (f.get("published_area_m2") or "").strip()
    try:
        area_v = float(area) if area else None
        if area_v is not None and area_v <= 0:
            raise ValueError
    except ValueError:
        return render_template("customer/new.html", form=f,
                               errors={"published_area_m2": "La superficie debe ser un número "
                                                            "mayor que cero."}), 400
    pid = properties.create(titulo, "OFFICE", city=f.get("city") or "",
                            reference=f.get("reference") or "", published_area_m2=area_v)
    errores = _recibir_archivos(pid, request)
    if errores:
        return render_template("customer/uploaded.html", pid=pid, errores=errores,
                               titulo=titulo), 400
    return redirect(url_for("customer.detail", property_id=pid))


def _recibir_archivos(pid, req):
    """Guarda plano y fotos. Devuelve la lista de problemas en lenguaje de cliente."""
    errores = []
    plano = req.files.get("floorplan")
    if plano and plano.filename:
        try:
            assets.save_upload(pid, plano, assets.FLOORPLAN_ORIGINAL)
        except assets.AssetError as e:
            errores.append(f"{plano.filename}: {e}")
    for foto in req.files.getlist("photos"):
        if not foto or not foto.filename:
            continue
        try:
            assets.save_upload(pid, foto, assets.PHOTO_ORIGINAL)
        except assets.AssetError as e:
            errores.append(f"{foto.filename}: {e}")
    properties.touch(pid)
    return errores


def _detalle(property_id, errores=None, code=200):
    v = properties.view(property_id)
    base = fits.base_of(property_id)
    html = render_template(
        "customer/detail.html", v=v, p=v["property"], pasos=_pasos(v),
        plano=assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL),
        plano_com=assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL),
        fotos=assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL),
        layouts=assets.list_of_kind(property_id, assets.LAYOUT_RENDER),
        pack=packs.get(property_id), errores=errores or [],
        hero=staging.hero(property_id), staged=staging.approved_hero(property_id),
        antes_despues=(packs.before_after_assets(property_id) or [None])[0],
        ambientacion=staging.state(property_id), listo=packs.readiness(property_id),
        disclosure=staging.DISCLOSURE, disclosure_long=staging.DISCLOSURE_LONG,
        base=fits.view(base["fit_id"], property_id) if base else None,
        prospectos=[fits.view(f["fit_id"], property_id)
                    for f in fits.list_for(property_id, include_base=False)],
        presets_wp=presets.CATALOG, estilos=presets.VISUAL_STYLES,
        preset_default=presets.DEFAULT_PRESET, estilo_default=presets.DEFAULT_STYLE)
    return (html, code) if code != 200 else html


@bp.get("/<property_id>")
@auth.require
def detail(property_id):
    _prop_or_404(property_id)
    return _detalle(property_id)


@bp.post("/<property_id>/assets")
@auth.require
def upload(property_id):
    _prop_or_404(property_id)
    errores = _recibir_archivos(property_id, request)
    return _detalle(property_id, errores, 400 if errores else 200) if errores else \
        redirect(url_for("customer.detail", property_id=property_id))


@bp.post("/<property_id>/hero")
@auth.require
def set_hero(property_id):
    """§18 — el cliente elige UNA foto principal. No se ambienta todo por defecto: es lo que mantiene
    claros el costo, la revisión y la promesa del producto."""
    _prop_or_404(property_id)
    try:
        staging.set_hero(property_id, request.form.get("asset_id", ""))
    except staging.StagingError as e:
        return _detalle(property_id, [str(e)], 400)
    return redirect(url_for("customer.detail", property_id=property_id))


@bp.post("/<property_id>/assets/<asset_id>/delete")
@auth.require
def delete_asset(property_id, asset_id):
    """Sólo antes de procesar, y sólo assets de ESTA propiedad."""
    _prop_or_404(property_id)
    a = assets.get(asset_id, property_id)
    if a is None:
        abort(404)
    if a["kind"] not in (assets.PHOTO_ORIGINAL, assets.FLOORPLAN_ORIGINAL):
        abort(400)
    if a["kind"] == assets.FLOORPLAN_ORIGINAL and properties.require(property_id)["floorplan_case_id"]:
        abort(400)                                    # el plano ya entró al pipeline: no se borra
    if a["kind"] == assets.PHOTO_ORIGINAL and staging.list_for(property_id, asset_id):
        abort(400)                                    # ya tiene intentos de ambientación: es evidencia
    assets.delete(asset_id, property_id)
    properties.touch(property_id)
    return redirect(url_for("customer.detail", property_id=property_id))


@bp.get("/<property_id>/asset/<asset_id>")
@auth.require
def serve_asset(property_id, asset_id):
    """Servir por IDENTIDAD, nunca por ruta. Un asset de otra propiedad no existe desde aquí."""
    _prop_or_404(property_id)
    a = assets.get(asset_id, property_id)
    if a is None:
        abort(404)
    ruta = assets.path_of(a)
    if not os.path.exists(ruta):
        abort(404)
    return send_file(ruta, mimetype=a["mime_type"])


# =============================================================================================
# §10 — PROGRAMA. Express por defecto; avanzado sólo en Pro.
# =============================================================================================
def _leer_express(f):
    return (f.get("headcount"), presets.require_preset(f.get("workplace_preset")
                                                       or presets.DEFAULT_PRESET),
            presets.require_style(f.get("visual_style") or presets.DEFAULT_STYLE),
            (f.get("target_seats") or "").strip() or None)


@bp.post("/<property_id>/program")
@auth.require
def set_program(property_id):
    """El programa BASE de la propiedad: cuántas personas y cómo trabajan. Nada más (§10)."""
    _prop_or_404(property_id)
    f = request.form
    try:
        headcount, preset, estilo, objetivo = _leer_express(f)
        fid = fits.ensure_base(property_id, headcount, preset, estilo)
        fits.set_express(fid, int(headcount), preset, estilo,
                         int(objetivo) if objetivo else None)
    except (presets.PresetError, fits.FitError, ValueError) as e:
        return _detalle(property_id, [str(e)], 400)
    if f.get("generate"):
        return _generar(property_id, fid)
    return redirect(url_for("customer.detail", property_id=property_id))


@bp.post("/<property_id>/fits")
@auth.require
def create_fit(property_id):
    """§9 — un fit request por prospecto. Sólo Pro."""
    _prop_or_404(property_id)
    f = request.form
    logo_id = None
    archivo = request.files.get("prospect_logo")
    try:
        if archivo and archivo.filename:
            entitlements.require(entitlements.PROSPECT_BRANDING)
            logo_id = branding.save_logo(archivo, branding.PROSPECT)
        headcount, preset, estilo, _ = _leer_express(f)
        fid = fits.create_prospect(property_id, f.get("prospect_name") or "", headcount,
                                   preset, estilo, f.get("prospect_color") or "", logo_id,
                                   notes=f.get("notes") or "")
        fits.set_express(fid, int(headcount), preset, estilo)
    except (presets.PresetError, fits.FitError, branding.BrandError, ValueError) as e:
        return _detalle(property_id, [str(e)], 400)
    if f.get("generate"):
        return _generar(property_id, fid)
    return redirect(url_for("customer.fit_detail", property_id=property_id, fit_id=fid))


def _generar(property_id, fit_id):
    try:
        fits.generate(fit_id)
    except fits.FitError as e:
        return _detalle(property_id, [str(e)], 400)
    return redirect(url_for("customer.fit_detail", property_id=property_id, fit_id=fit_id))


@bp.post("/<property_id>/fits/<fit_id>/generate")
@auth.require
def generate_fit(property_id, fit_id):
    _fit_or_404(property_id, fit_id)
    return _generar(property_id, fit_id)


@bp.post("/<property_id>/fits/<fit_id>/program")
@auth.require
def update_fit_program(property_id, fit_id):
    _fit_or_404(property_id, fit_id)
    f = request.form
    try:
        headcount, preset, estilo, objetivo = _leer_express(f)
        if f.get("mode") == fits.ADVANCED:
            rooms = {m: f.get(f"room_{m}") or 0 for m, _ in briefmod.MODULE_LABELS}
            errs = briefmod.field_errors(f.get("brief_name") or "PROGRAMA", headcount,
                                         f.get("workstations"), rooms, briefmod.MODULES_PATH)
            if errs:
                return _fit_page(property_id, fit_id, list(errs.values()), 400)
            b = briefmod.build(f.get("brief_name") or "PROGRAMA", headcount,
                               f.get("workstations"), rooms)
            fits.set_advanced_brief(fit_id, b)
        else:
            fits.set_express(fit_id, int(headcount), preset, estilo,
                             int(objetivo) if objetivo else None)
    except (presets.PresetError, fits.FitError, briefmod.BriefFormError, ValueError) as e:
        return _fit_page(property_id, fit_id, [str(e)], 400)
    if f.get("generate"):
        return _generar(property_id, fit_id)
    return redirect(url_for("customer.fit_detail", property_id=property_id, fit_id=fit_id))


@bp.post("/<property_id>/fits/<fit_id>/archive")
@auth.require
def archive_fit(property_id, fit_id):
    """§9 — se archiva, no se borra. El material generado sigue existiendo."""
    f = _fit_or_404(property_id, fit_id)
    if f["kind"] == fits.BASE:
        abort(400)
    fits.archive(fit_id)
    return redirect(url_for("customer.detail", property_id=property_id))


def _fit_page(property_id, fit_id, errores=None, code=200):
    v = properties.view(property_id)
    fv = fits.view(fit_id, property_id)
    html = render_template(
        "customer/fit.html", v=v, p=v["property"], fv=fv, f=fv["fit"],
        errores=errores or [], presets_wp=presets.CATALOG, estilos=presets.VISUAL_STYLES,
        modules=briefmod.MODULE_LABELS,
        sugeridos=(presets.rooms_for_form(fv["fit"]["workplace_preset"], fv["fit"]["headcount"])
                   if fv["fit"]["headcount"] else {}),
        layouts=packs.layout_assets(property_id, fit_id),
        plano_com=assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL),
        pack=packs.get(property_id, fit_id))
    return (html, code) if code != 200 else html


@bp.get("/<property_id>/fits/<fit_id>")
@auth.require
def fit_detail(property_id, fit_id):
    _fit_or_404(property_id, fit_id)
    return _fit_page(property_id, fit_id)


@bp.get("/<property_id>/fits/<fit_id>/proposal")
@auth.require
def fit_proposal(property_id, fit_id):
    """La propuesta tal como la vería el prospecto. Es el MISMO documento que va en el ZIP."""
    _fit_or_404(property_id, fit_id)

    def url(carpeta, nombre, a):
        if carpeta == "marca":
            return url_for("customer.fit_logo", property_id=property_id, fit_id=fit_id)
        return url_for("customer.serve_asset", property_id=property_id, asset_id=a["asset_id"])

    return packs.proposal_html(property_id, fit_id, url)


@bp.get("/<property_id>/fits/<fit_id>/logo")
@auth.require
def fit_logo(property_id, fit_id):
    f = _fit_or_404(property_id, fit_id)
    lg = branding.logo(f["prospect_logo_id"], branding.PROSPECT)
    if lg is None or not os.path.exists(branding.logo_path(lg)):
        abort(404)
    return send_file(branding.logo_path(lg), mimetype=lg["mime_type"])


# =============================================================================================
# packs
# =============================================================================================
@bp.post("/<property_id>/pack")
@auth.require
def build_pack(property_id):
    """El pack BASE de la propiedad (§8). Publica lo que corresponda y arma el ZIP."""
    _prop_or_404(property_id)
    base = fits.base_of(property_id)
    try:
        floorplan.publish_all(property_id, fit_id=(base or {}).get("fit_id"))
        packs.export_zip(property_id)
    except (floorplan.FloorplanError, packs.PackNotReady) as e:
        return _detalle(property_id, [str(e)], 400)
    return redirect(url_for("customer.detail", property_id=property_id))


@bp.post("/<property_id>/fits/<fit_id>/pack")
@auth.require
def build_fit_pack(property_id, fit_id):
    _fit_or_404(property_id, fit_id)
    try:
        floorplan.publish_all(property_id, fit_id=fit_id)
    except floorplan.FloorplanError as e:
        return _fit_page(property_id, fit_id, [str(e)], 400)
    packs.export_zip(property_id, fit_id)
    return redirect(url_for("customer.fit_detail", property_id=property_id, fit_id=fit_id))


def _descargar(property_id, fit_id, nombre):
    pack = packs.get(property_id, fit_id)
    if not pack or not pack["export_name"]:
        abort(404)
    a = assets.get(pack["export_name"], property_id)
    if a is None or not os.path.exists(assets.path_of(a)):
        abort(404)
    return send_file(assets.path_of(a), mimetype="application/zip", as_attachment=True,
                     download_name=nombre)


@bp.get("/<property_id>/pack.zip")
@auth.require
def download_pack(property_id):
    _prop_or_404(property_id)
    return _descargar(property_id, None, f"escalimetro_{property_id}.zip")


@bp.get("/<property_id>/fits/<fit_id>/pack.zip")
@auth.require
def download_fit_pack(property_id, fit_id):
    _fit_or_404(property_id, fit_id)
    return _descargar(property_id, fit_id, f"escalimetro_{fit_id}.zip")


# =============================================================================================
# §20 — marca de la corredora. De la cuenta, no de la propiedad.
# =============================================================================================
@bp.get("/brand")
@auth.require
def brand():
    return render_template("customer/brand.html", marca=branding.brokerage(), errores=[])


@bp.post("/brand")
@auth.require
def save_brand():
    f = request.form
    logo_id = None
    archivo = request.files.get("logo")
    try:
        if archivo and archivo.filename:
            logo_id = branding.save_logo(archivo, branding.BROKERAGE)
        branding.set_brokerage(f.get("name") or "", f.get("color") or "", logo_id)
    except branding.BrandError as e:
        return render_template("customer/brand.html", marca=branding.brokerage(),
                               errores=[str(e)]), 400
    return redirect(url_for("customer.brand"))


@bp.get("/brand/logo")
@auth.require
def brand_logo():
    lg = branding.logo(branding.brokerage()["logo_id"], branding.BROKERAGE)
    if lg is None or not os.path.exists(branding.logo_path(lg)):
        abort(404)
    return send_file(branding.logo_path(lg), mimetype=lg["mime_type"])
