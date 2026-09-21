"""E32 — ESCALÍMETRO LAB: la consola interna. Una sola web para operar el sistema sin terminal.

Qué es: el laboratorio de producto. Joaquín carga una propiedad real, la procesa con el motor real,
mira los resultados reales y anota qué funcionó. Nada acá es una demo: property real, case real,
motor real, staging real cuando exista proveedor aprobado.

Qué NO es: la web pública, la web comercial, ni el producto final. No hay signup, ni billing, ni
RBAC. Está detrás de la misma autenticación que el resto de la herramienta interna.

La consola **no duplica dominio**. Todo lo que muestra sale de los módulos que ya existen
—`lab`, `staging`, `packs`, `fits`, `benchmark`, `pilot`—; acá sólo hay rutas y traducción a
pantalla. Cuando un paso técnico ya tiene una pantalla buena (el intake de E27.3, la revisión de
ambientación de E31), el LAB enlaza a ella en vez de reimplementarla peor.

Regla que atraviesa todo: **ningún estado se declara**. El avance, el pack, la ambientación y la
línea de tiempo se derivan de artefactos. Si la consola dice que algo está listo, hay un archivo o
una fila que lo respalda.
"""
from __future__ import annotations

import os
from typing import Optional

from flask import (Blueprint, abort, jsonify, redirect, render_template, request, send_file,
                   url_for)

from . import auth, benchmark as bench, briefs as briefmod, engine, store
from .domain import (assets, branding, entitlements, fits, floorplan, lab as labdom, packs, pilot,
                     presets, properties, staging)

bp = Blueprint("lab", __name__, url_prefix="/lab")
OPERATOR = os.environ.get("ESCALIMETRO_REVIEWER", "Joaquín Riesco")

#: Las pestañas de una propiedad. Sin secciones vacías: cada una tiene contenido siempre.
TABS = [("resumen", "Resumen"), ("plano", "Plano"), ("fotos", "Fotos"),
        ("material", "Material base"), ("prospectos", "Prospectos"), ("pack", "Pack"),
        ("actividad", "Actividad")]


@bp.context_processor
def _ctx():
    return {"producto": entitlements.summary(), "tabs": TABS,
            "modo_pro": entitlements.allows(entitlements.PROSPECT_FIT_REQUESTS),
            "cola": engine.pending() + staging.pending()}


def _preset_estilo(f):
    """El preset y el estilo, ya con su valor por defecto aplicado. Se calculan UNA vez y se
    reusan: pasar el valor crudo del formulario después de haberlo defaulteado es la forma
    silenciosa de que un campo vacío llegue como None al dominio."""
    return (presets.require_preset(f.get("workplace_preset") or presets.DEFAULT_PRESET),
            presets.require_style(f.get("visual_style") or presets.DEFAULT_STYLE))


def _p(property_id):
    p = properties.get(property_id)
    if p is None:
        abort(404)
    return p


def _err(msg, back, code=400):
    return render_template("error.html", msg=msg, back=back), code


def _vista(property_id, tab, **extra):
    """Todo lo que comparten las pestañas de una propiedad: quién es y cómo va."""
    v = properties.view(property_id)
    return render_template(
        f"lab/{tab}.html", v=v, p=v["property"], tab=tab,
        avance=labdom.summary(property_id), staging_st=staging.state(property_id),
        listo=packs.readiness(property_id), **extra)


# =================================================================================================
# §4 — PORTADA
# =================================================================================================
@bp.get("/")
@auth.require
def home():
    return render_template("lab/home.html", resumen=labdom.overview(), filas=labdom.rows(),
                           preparacion=pilot.readiness())


@bp.get("/new")
@auth.require
def new():
    return render_template("lab/new.html", errors={}, form=None)


@bp.post("/new")
@auth.require
def create():
    """§5 paso 1 — datos. Lo mínimo para empezar; el resto se completa en las pestañas."""
    f = request.form
    titulo = (f.get("title") or "").strip()
    if not titulo:
        return render_template("lab/new.html", form=f,
                               errors={"title": "Ponle un nombre o referencia."}), 400
    area = (f.get("published_area_m2") or "").strip()
    try:
        area_v = float(area) if area else None
        if area_v is not None and area_v <= 0:
            raise ValueError
    except ValueError:
        return render_template("lab/new.html", form=f,
                               errors={"published_area_m2": "Superficie inválida."}), 400
    try:
        pid = properties.create(titulo, "OFFICE", city=f.get("city") or "",
                                reference=f.get("reference") or "", published_area_m2=area_v,
                                notes=f.get("notes") or "")
    except entitlements.EntitlementError as e:
        return _err(str(e), url_for("lab.home"), 403)
    errores = _recibir(pid, request)
    if errores:
        return _vista(pid, "plano", errores=errores, adjunto=_adjunto(pid)), 400
    return redirect(url_for("lab.resumen", property_id=pid))


def _recibir(pid, req):
    errores = []
    plano = req.files.get("floorplan")
    if plano and plano.filename:
        try:
            assets.save_upload(pid, plano, assets.FLOORPLAN_ORIGINAL)
        except assets.AssetError as e:
            errores.append(f"{plano.filename}: {e}")
    for foto in req.files.getlist("photos"):
        if foto and foto.filename:
            try:
                assets.save_upload(pid, foto, assets.PHOTO_ORIGINAL)
            except assets.AssetError as e:
                errores.append(f"{foto.filename}: {e}")
    properties.touch(pid)
    return errores


# =================================================================================================
# §5 — PESTAÑAS DE UNA PROPIEDAD
# =================================================================================================
@bp.get("/p/<property_id>")
@auth.require
def resumen(property_id):
    _p(property_id)
    return _vista(property_id, "resumen", linea=labdom.timeline(property_id)[:8],
                  notas=labdom.notes(property_id)[:3],
                  feedback_opts=labdom.PROPERTY_FEEDBACK)


def _adjunto(property_id):
    return {"plano": assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL),
            "case": floorplan.technical_state(property_id)}


@bp.get("/p/<property_id>/plano")
@auth.require
def plano(property_id):
    _p(property_id)
    return _vista(property_id, "plano", errores=[], adjunto=_adjunto(property_id))


@bp.post("/p/<property_id>/plano")
@auth.require
def subir_plano(property_id):
    _p(property_id)
    errores = _recibir(property_id, request)
    if errores:
        return _vista(property_id, "plano", errores=errores, adjunto=_adjunto(property_id)), 400
    return redirect(url_for("lab.plano", property_id=property_id))


@bp.post("/p/<property_id>/preparar")
@auth.require
def preparar(property_id):
    """§5 paso 4 — crea el caso técnico y lleva al intake de E27.3, que ya hace bien esta parte:
    escala medida sobre el plano, acceso, revisión de lo detectado. No se reimplementa acá."""
    _p(property_id)
    try:
        case_id = floorplan.ensure_case(property_id)
    except (LookupError, floorplan.FloorplanError) as e:
        return _err(str(e), url_for("lab.plano", property_id=property_id))
    return redirect(url_for("case_view", case_id=case_id) + f"?lab={property_id}")


@bp.get("/p/<property_id>/fotos")
@auth.require
def fotos(property_id):
    _p(property_id)
    return _vista(property_id, "fotos", errores=[],
                  fotos=assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL),
                  hero=staging.hero(property_id),
                  en_dataset={r["asset_id"] for r in store.q(
                      "SELECT asset_id FROM benchmark_photos WHERE property_id=?", (property_id,))})


@bp.post("/p/<property_id>/fotos")
@auth.require
def subir_fotos(property_id):
    _p(property_id)
    errores = _recibir(property_id, request)
    if errores:
        return _vista(property_id, "fotos", errores=errores,
                      fotos=assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL),
                      hero=staging.hero(property_id), en_dataset=set()), 400
    return redirect(url_for("lab.fotos", property_id=property_id))


@bp.post("/p/<property_id>/hero")
@auth.require
def hero(property_id):
    _p(property_id)
    try:
        staging.set_hero(property_id, request.form.get("asset_id", ""))
    except staging.StagingError as e:
        return _err(str(e), url_for("lab.fotos", property_id=property_id))
    return redirect(url_for("lab.fotos", property_id=property_id))


@bp.post("/p/<property_id>/foto/<asset_id>/borrar")
@auth.require
def borrar_foto(property_id, asset_id):
    _p(property_id)
    a = assets.get(asset_id, property_id)
    if a is None or a["kind"] != assets.PHOTO_ORIGINAL:
        abort(404)
    if staging.list_for(property_id, asset_id, include_benchmark=True):
        return _err("Esa foto ya tiene intentos de ambientación: es evidencia y no se borra.",
                    url_for("lab.fotos", property_id=property_id))
    assets.delete(asset_id, property_id)
    bench.remove_photo(asset_id)
    return redirect(url_for("lab.fotos", property_id=property_id))


@bp.get("/p/<property_id>/material")
@auth.require
def material(property_id):
    _p(property_id)
    base = fits.base_of(property_id)
    return _vista(property_id, "material", errores=[],
                  plano_com=assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL),
                  layouts=packs.layout_assets(property_id),
                  hero=staging.hero(property_id),
                  staged=staging.approved_hero(property_id),
                  antes=(packs.before_after_assets(property_id) or [None])[0],
                  intentos=staging.list_for(property_id),
                  base=fits.view(base["fit_id"], property_id) if base else None,
                  presets_wp=presets.CATALOG, estilos=presets.VISUAL_STYLES,
                  preset_default=presets.DEFAULT_PRESET, estilo_default=presets.DEFAULT_STYLE,
                  aprobado=pilot.approved(), disclosure=staging.DISCLOSURE_LONG)


@bp.post("/p/<property_id>/programa")
@auth.require
def programa(property_id):
    """El programa base: personas + forma de trabajo. Igual que el producto, sin CAD."""
    _p(property_id)
    f = request.form
    try:
        preset, estilo = _preset_estilo(f)
        fid = fits.ensure_base(property_id, f.get("headcount"), preset, estilo)
        fits.set_express(fid, int(f.get("headcount")), preset, estilo,
                         int(f["target_seats"]) if (f.get("target_seats") or "").strip() else None)
        if f.get("generate"):
            fits.generate(fid)
    except (presets.PresetError, fits.FitError, briefmod.BriefFormError, ValueError,
            entitlements.EntitlementError) as e:
        return _err(str(e), url_for("lab.material", property_id=property_id))
    return redirect(url_for("lab.material", property_id=property_id))


@bp.post("/p/<property_id>/publicar")
@auth.require
def publicar(property_id):
    """Publica plano comercial y la alternativa que el producto entregue."""
    _p(property_id)
    base = fits.base_of(property_id)
    try:
        floorplan.publish_all(property_id, fit_id=(base or {}).get("fit_id"))
    except (LookupError, floorplan.FloorplanError) as e:
        return _err(str(e), url_for("lab.material", property_id=property_id))
    return redirect(url_for("lab.material", property_id=property_id))


# ---- §11 STAGING LAB (por propiedad) ---------------------------------------------------------
@bp.post("/p/<property_id>/staging")
@auth.require
def generar_staging(property_id):
    """Genera un intento para la foto principal.

    El proveedor NO se pregunta en el flujo de producto: se usa el aprobado (§J). El selector
    interno existe sólo para experimentar, y lo que produce nace marcado como experimental y no
    puede publicarse."""
    _p(property_id)
    h = staging.hero(property_id)
    if h is None:
        return _err("Primero elegí la foto principal.",
                    url_for("lab.fotos", property_id=property_id))
    f = request.form
    prov = (f.get("provider") or "").strip() or None
    estilo = f.get("visual_style") or (fits.base_of(property_id) or {}).get("visual_style") \
        or presets.DEFAULT_STYLE
    try:
        aid = staging.create_attempt(property_id, h["asset_id"], estilo, provider_name=prov)
    except (staging.StagingError, entitlements.EntitlementError,
            staging.visual.VisualStagingError) as e:
        return _err(str(e), url_for("lab.material", property_id=property_id))
    staging.enqueue(aid)
    return redirect(url_for("staging.review_page", attempt_id=aid))


# ---- §8 PROSPECTOS ---------------------------------------------------------------------------
@bp.get("/p/<property_id>/prospectos")
@auth.require
def prospectos(property_id):
    _p(property_id)
    return _vista(property_id, "prospectos", errores=[],
                  lista=[fits.view(f["fit_id"], property_id)
                         for f in fits.list_for(property_id, include_base=False)],
                  presets_wp=presets.CATALOG, estilos=presets.VISUAL_STYLES,
                  preset_default=presets.DEFAULT_PRESET, estilo_default=presets.DEFAULT_STYLE,
                  feedback_opts=labdom.FIT_FEEDBACK)


@bp.post("/p/<property_id>/prospectos")
@auth.require
def crear_prospecto(property_id):
    _p(property_id)
    f = request.form
    logo_id = None
    archivo = request.files.get("prospect_logo")
    try:
        preset, estilo = _preset_estilo(f)
        if archivo and archivo.filename:
            logo_id = branding.save_logo(archivo, branding.PROSPECT)
        fid = fits.create_prospect(property_id, f.get("prospect_name") or "", f.get("headcount"),
                                   preset, estilo, f.get("prospect_color") or "", logo_id,
                                   notes=f.get("notes") or "")
        fits.set_express(fid, int(f.get("headcount")), preset, estilo)
    except (presets.PresetError, fits.FitError, branding.BrandError, ValueError,
            entitlements.EntitlementError) as e:
        return _err(str(e), url_for("lab.prospectos", property_id=property_id),
                    403 if isinstance(e, entitlements.EntitlementError) else 400)
    return redirect(url_for("lab.prospecto", property_id=property_id, fit_id=fid))


@bp.get("/p/<property_id>/prospectos/<fit_id>")
@auth.require
def prospecto(property_id, fit_id):
    _p(property_id)
    if fits.get(fit_id, property_id) is None:
        abort(404)
    fv = fits.view(fit_id, property_id)
    return _vista(property_id, "prospecto", errores=[], fv=fv, f=fv["fit"],
                  layouts=packs.layout_assets(property_id, fit_id),
                  pack=packs.get(property_id, fit_id),
                  notas=labdom.notes(property_id, fit_id),
                  feedback_opts=labdom.FIT_FEEDBACK,
                  presets_wp=presets.CATALOG, estilos=presets.VISUAL_STYLES)


@bp.post("/p/<property_id>/prospectos/<fit_id>/generar")
@auth.require
def generar_fit(property_id, fit_id):
    _p(property_id)
    if fits.get(fit_id, property_id) is None:
        abort(404)
    try:
        fits.generate(fit_id)
    except (fits.FitError, entitlements.EntitlementError, briefmod.BriefFormError) as e:
        return _err(str(e), url_for("lab.prospecto", property_id=property_id, fit_id=fit_id))
    return redirect(url_for("lab.prospecto", property_id=property_id, fit_id=fit_id))


@bp.post("/p/<property_id>/prospectos/<fit_id>/publicar")
@auth.require
def publicar_fit(property_id, fit_id):
    _p(property_id)
    if fits.get(fit_id, property_id) is None:
        abort(404)
    try:
        floorplan.publish_all(property_id, fit_id=fit_id)
        packs.export_zip(property_id, fit_id)
    except (floorplan.FloorplanError, packs.PackNotReady, LookupError) as e:
        return _err(str(e), url_for("lab.prospecto", property_id=property_id, fit_id=fit_id))
    return redirect(url_for("lab.prospecto", property_id=property_id, fit_id=fit_id))


# ---- §25 PACK --------------------------------------------------------------------------------
@bp.get("/p/<property_id>/pack")
@auth.require
def pack(property_id):
    _p(property_id)
    return _vista(property_id, "pack", errores=[], pack=packs.get(property_id),
                  contenido=_contenido(property_id))


def _contenido(property_id):
    """§25 — qué entraría al ZIP HOY. Se calcula mirando los assets, no una lista escrita a mano:
    así la vista previa no puede contradecir el archivo."""
    st = staging.state(property_id)
    return [
        {"n": "Plano comercial",
         "ok": assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL) is not None,
         "por_que": "se publica cuando la planta está confirmada"},
        {"n": "Alternativa representativa", "ok": bool(packs.layout_assets(property_id)),
         "por_que": "falta generar o publicar el layout"},
        {"n": "Plano original",
         "ok": assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL) is not None,
         "por_que": "falta subir el plano"},
        {"n": "Fotos originales",
         "ok": bool(assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL)),
         "por_que": "falta subir fotos"},
        {"n": "Imagen ambientada aprobada", "ok": st["state"] == "APPROVED",
         "por_que": st["reason"]},
        {"n": "Antes / después", "ok": bool(packs.before_after_assets(property_id)),
         "por_que": "se arma junto con la imagen ambientada"},
        {"n": "Propuesta", "ok": True, "por_que": ""},
        {"n": "Manifiesto", "ok": True, "por_que": ""},
    ]


@bp.post("/p/<property_id>/pack")
@auth.require
def armar_pack(property_id):
    _p(property_id)
    base = fits.base_of(property_id)
    try:
        floorplan.publish_all(property_id, fit_id=(base or {}).get("fit_id"))
        packs.export_zip(property_id)
    except (floorplan.FloorplanError, packs.PackNotReady) as e:
        return _vista(property_id, "pack", errores=[str(e)], pack=packs.get(property_id),
                      contenido=_contenido(property_id)), 400
    return redirect(url_for("lab.pack", property_id=property_id))


@bp.post("/p/<property_id>/pack/override")
@auth.require
def override(property_id):
    _p(property_id)
    packs.set_override(property_id, request.form.get("reason") or "")
    return redirect(url_for("lab.pack", property_id=property_id))


# ---- §15/§16/§17 ACTIVIDAD, NOTAS Y VALORACIÓN -----------------------------------------------
@bp.get("/p/<property_id>/actividad")
@auth.require
def actividad(property_id):
    _p(property_id)
    return _vista(property_id, "actividad", linea=labdom.timeline(property_id),
                  notas=labdom.notes(property_id), feedback_opts=labdom.PROPERTY_FEEDBACK)


@bp.post("/p/<property_id>/nota")
@auth.require
def nota(property_id):
    _p(property_id)
    try:
        labdom.add_note(property_id, request.form.get("body", ""),
                        request.form.get("scope") or "PROPERTY",
                        request.form.get("fit_id") or None, author=OPERATOR)
    except ValueError as e:
        return _err(str(e), url_for("lab.actividad", property_id=property_id))
    destino = request.form.get("next") or url_for("lab.actividad", property_id=property_id)
    return redirect(destino)


@bp.post("/p/<property_id>/nota/<note_id>/borrar")
@auth.require
def borrar_nota(property_id, note_id):
    _p(property_id)
    labdom.delete_note(note_id, property_id)
    return redirect(request.form.get("next") or url_for("lab.actividad", property_id=property_id))


@bp.post("/p/<property_id>/feedback")
@auth.require
def feedback(property_id):
    _p(property_id)
    try:
        if request.form.get("fit_id"):
            labdom.set_fit_feedback(request.form["fit_id"], property_id,
                                    request.form.get("value", ""))
        else:
            labdom.set_feedback(property_id, request.form.get("value", ""))
    except (ValueError, LookupError) as e:
        return _err(str(e), url_for("lab.resumen", property_id=property_id))
    return redirect(request.form.get("next") or url_for("lab.resumen", property_id=property_id))


@bp.get("/feedback.json")
@auth.require
def feedback_json():
    """§17 — el feedback estructurado, para analizarlo después. No entrena nada hoy."""
    return jsonify(labdom.feedback_export())


# =================================================================================================
# §24 — CONFIGURACIÓN + §A PANEL DE PREPARACIÓN
# =================================================================================================
@bp.get("/config")
@auth.require
def config():
    return render_template("lab/config.html", preparacion=pilot.readiness(),
                           marca=branding.brokerage(), modos=entitlements.PRODUCT_MODES,
                           etiquetas=entitlements.MODE_LABEL,
                           presets_wp=presets.CATALOG, estilos=presets.VISUAL_STYLES,
                           eventos=pilot.events(limit=15))


@bp.post("/config/modo")
@auth.require
def set_modo():
    try:
        entitlements.set_mode(request.form.get("mode", ""))
    except ValueError:
        abort(400)
    return redirect(request.form.get("next") or url_for("lab.config"))


@bp.post("/config/recheck")
@auth.require
def recheck():
    """§A — «RECHEQUEAR ENTORNO». Sólo vuelve a detectar configuración. No revela ninguna clave:
    lo único que cambia en pantalla son booleanos."""
    pilot.log_event("ENV_RECHECK", detail={"credentials": [
        {"provider": p["name"], "credential": p["credential"]}
        for p in pilot.readiness()["providers"]]}, author=OPERATOR)
    return redirect(url_for("lab.benchmark") if request.form.get("from") == "benchmark"
                    else url_for("lab.config"))


# =================================================================================================
# §B/§C/§D/§G — BAKE-OFF: dataset, smoke tests, ejecución y resultados
# =================================================================================================
@bp.get("/benchmark")
@auth.require
def benchmark():
    prep = pilot.readiness()
    ds = bench.dataset()
    bid = request.args.get("run") or bench.latest_run()
    return render_template(
        "lab/benchmark.html", preparacion=prep, dataset=ds, fotos=bench.eligible_photos(),
        rasgos=bench.DIFFICULT_FEATURES, errores_ds=bench.validate_manifest(ds),
        gate=bench.GATE, criterios=staging.visual.PILOT_CRITERIA,
        estimacion=bench.estimate([p["name"] for p in prep["providers"]
                                   if p["in_pilot"] and p["credential"]],
                                  len(ds["photos"]), 2),
        run=bid, progreso=bench.progress(bid) if bid else None,
        resultados=bench.results(bid, ds, pilot.PILOT_PROVIDERS) if bid else None,
        manifest_path=bench.manifest_path())


@bp.post("/benchmark/foto")
@auth.require
def benchmark_foto():
    """§B — sumar o quitar una foto del dataset, con sus rasgos difíciles."""
    f = request.form
    aid, pid = f.get("asset_id", ""), f.get("property_id", "")
    try:
        if f.get("action") == "remove":
            bench.remove_photo(aid)
        else:
            bench.add_photo(aid, pid, f.getlist("tags"), f.get("reason") or "")
    except ValueError as e:
        return _err(str(e), url_for("lab.benchmark"))
    return redirect(request.form.get("next") or url_for("lab.benchmark"))


@bp.post("/benchmark/smoke/<provider>")
@auth.require
def smoke(provider):
    """§C — UNA llamada real. Ni aprueba, ni selecciona, ni publica."""
    prep = pilot.readiness()
    p = next((x for x in prep["providers"] if x["name"] == provider), None)
    if p is None or p["excluded"]:
        return _err(f"Proveedor no disponible para el piloto: {provider}",
                    url_for("lab.benchmark"))
    if not p["credential"]:
        return _err(f"Falta la credencial de {provider} ({p['env']}) en el entorno. "
                    "Se configura una sola vez, fuera de esta consola.", url_for("lab.benchmark"))
    ds = bench.dataset()
    if not ds["photos"]:
        return _err("El smoke test usa una foto real del dataset. Sumá al menos una.",
                    url_for("lab.benchmark"))
    foto = ds["photos"][0]
    res = staging.smoke_test(provider, foto["asset_id"], foto["property_id"])
    return redirect(url_for("staging.review_page", attempt_id=res["attempt_id"]))


@bp.post("/benchmark/run")
@auth.require
def benchmark_run():
    """§D — lanza el bake-off real. Exige confirmación explícita del gasto estimado."""
    f = request.form
    provs = [p for p in f.getlist("providers") if p not in pilot.EXCLUDED]
    try:
        runs = max(1, min(4, int(f.get("runs") or 2)))
    except ValueError:
        runs = 2
    if not f.get("confirm"):
        return _err("Falta confirmar el gasto estimado antes de lanzar el lote.",
                    url_for("lab.benchmark"))
    try:
        res = bench.start(provs, runs, f.get("style") or bench.DEFAULT_STYLE, author=OPERATOR)
    except ValueError as e:
        return _err(str(e), url_for("lab.benchmark"))
    return redirect(url_for("lab.benchmark", run=res["benchmark_id"]))


@bp.get("/benchmark/<benchmark_id>/status.json")
@auth.require
def benchmark_status(benchmark_id):
    """§E — sondeo de progreso. La consola no se congela esperando al lote."""
    return jsonify(bench.progress(benchmark_id))


@bp.post("/benchmark/approve")
@auth.require
def approve_provider():
    """§H — la decisión es HUMANA. La consola muestra la compuerta; no aprueba a nadie."""
    f = request.form
    bid = f.get("benchmark_id") or bench.latest_run()
    if not bid:
        return _err("No hay un bake-off del que sacar evidencia.", url_for("lab.benchmark"))
    res = bench.results(bid, bench.dataset(), pilot.PILOT_PROVIDERS)
    prov = f.get("provider", "")
    met = (res.get("metrics") or {}).get(prov)
    if met is None:
        return _err(f"No hay métricas de {prov} en este bake-off.", url_for("lab.benchmark"))
    derechos = bool(f.get("rights_verified"))
    evidencia = {"benchmark_id": bid, "sample_size": met["reviewed"],
                 "fidelity_pass_rate": met["fidelity_pass_rate"],
                 "approval_rate": met["approval_rate"],
                 "cost_per_approved_usd": met["cost"]["per_approved_usd"],
                 "median_latency_ms": met["latency_ms"]["median"],
                 "sample_thin": met["sample_thin"], "rights_verified": derechos,
                 "gate": bench.gate(met, derechos)}
    try:
        pilot.approve(prov, (met["model"] or [""])[0], evidencia, reviewer=OPERATOR,
                      override_reason=f.get("override_reason") or "")
    except pilot.ApprovalError as e:
        return _err(str(e), url_for("lab.benchmark", run=bid))
    return redirect(url_for("lab.benchmark", run=bid))


@bp.post("/benchmark/revoke")
@auth.require
def revoke_provider():
    pilot.revoke(request.form.get("reason") or "", reviewer=OPERATOR)
    return redirect(url_for("lab.benchmark"))


# =================================================================================================
# §F — REVISIÓN RÁPIDA
# =================================================================================================
@bp.get("/review/next")
@auth.require
def next_unreviewed():
    """«SIGUIENTE SIN REVISAR». Sin nada pendiente, vuelve a la cola."""
    pend = staging.pending_review_all()
    actual = request.args.get("after")
    if actual:
        pend = [a for a in pend if a["attempt_id"] != actual]
    if not pend:
        return redirect(url_for("staging.queue"))
    return redirect(url_for("staging.review_page", attempt_id=pend[0]["attempt_id"]))
