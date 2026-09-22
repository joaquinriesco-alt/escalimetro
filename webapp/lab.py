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

from flask import (Blueprint, abort, current_app, jsonify, redirect, render_template, request,
                   send_file, url_for)

from . import (auth, benchmark as bench, briefs as briefmod, detected, engine, intake,
               store)
from .domain import (assets, branding, calibration, entitlements, fits, floorplan, gold,
                     grants, ingest, interventions, lab as labdom, packs, pilot, presets,
                     properties, realpilot, reviews, staging, units)

bp = Blueprint("lab", __name__, url_prefix="/lab")
OPERATOR = os.environ.get("ESCALIMETRO_REVIEWER", "Joaquín Riesco")

#: E33 — ya no hay pestañas. Una propiedad es UNA página: datos, insumos, Pack 1, Pack 2 y
#: evaluaciones, en ese orden vertical. Las pestañas eran siete aplicaciones adentro de una.


@bp.app_context_processor
def _ctx():
    """De toda la app, no sólo de este blueprint: las pantallas de ambientación se abren desde el
    LAB y tienen que renderizar su misma cabecera. Sin esto, salir a «Ambientación» te dejaba en
    otro shell, con otra barra, que llevaba a la superficie de cliente."""
    return {"cola": engine.pending() + staging.pending()}


def _p(property_id):
    p = properties.get(property_id)
    if p is None:
        abort(404)
    return p


def _err(msg, back, code=400):
    return render_template("error.html", msg=msg, back=back), code


@bp.get("/")
@auth.require
def home():
    """§3 — sólo mis propiedades. Ni contadores técnicos, ni bloqueos del piloto, ni case_id."""
    return render_template("lab/home.html", filas=labdom.simple_rows())


@bp.get("/new")
@auth.require
def new():
    """En el LAB cada propiedad nueva representa una COMPRA propia: se crea su concesión simulada y
    se le asigna. Por eso no hay tope y tampoco hace falta inventar una excepción — el operador
    puede crear veinte propiedades ONE_OFF porque eso son veinte Packs, no una violación de plan."""
    return render_template("lab/new.html", errors={}, form=None, marca=branding.brokerage())


@bp.post("/new")
@auth.require
def create():
    """§5 paso 1 — datos. Lo mínimo para empezar; el resto se completa en las pestañas."""
    f = request.form
    titulo = (f.get("title") or "").strip()
    if not titulo:
        return render_template("lab/new.html", form=f, marca=branding.brokerage(),
                               errors={"title": "Ponle un nombre o referencia."}), 400
    area = (f.get("published_area_m2") or "").strip()
    try:
        area_v = float(area) if area else None
        if area_v is not None and area_v <= 0:
            raise ValueError
    except ValueError:
        return render_template("lab/new.html", form=f, marca=branding.brokerage(),
                               errors={"published_area_m2": "Superficie inválida."}), 400
    pid = properties.create(titulo, "OFFICE", city=f.get("city") or "",
                            reference=f.get("reference") or "", published_area_m2=area_v,
                            notes=f.get("notes") or "")
    grants.grant_and_assign(entitlements.default_product(), pid, source="SIMULATED_LAB",
                            note="compra simulada desde el LAB")
    errores = _recibir(pid, request)
    if errores:
        return render_template("lab/new.html", form=f, marca=branding.brokerage(),
                               errors={"archivos": " · ".join(errores)}), 400
    return redirect(url_for("lab.propiedad", property_id=pid))


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
def _pagina(property_id, errores=None, code=200):
    """§6 — la ÚNICA página de una propiedad."""
    datos = labdom.property_view(property_id)
    html = render_template("lab/property.html", errores=errores or [],
                           ratings=reviews.RATINGS, rating_label=reviews.RATING_LABEL,
                           fail_tags=reviews.FAIL_TAGS, good_tags=reviews.GOOD_TAGS,
                           source_labels=realpilot.SOURCE_LABEL,
                           modules=briefmod.MODULE_LABELS, **datos)
    return (html, code) if code != 200 else html


@bp.get("/p/<property_id>")
@auth.require
def propiedad(property_id):
    _p(property_id)
    return _pagina(property_id)


@bp.get("/p/<property_id>/status.json")
@auth.require
def propiedad_status(property_id):
    """§25 — sondeo simple para no obligar a recargar mientras el motor trabaja."""
    _p(property_id)
    p1 = labdom.pack1(property_id)
    props = labdom.pack2_list(property_id)
    return jsonify({
        "pack1": [{"name": s["name"], "state": s["state"], "detail": s["detail"]}
                  for s in p1["steps"]],
        "pack1_ready": p1["ready"],
        "pack2": [{"fit_id": x["fit"]["fit_id"], "label": x["fit"]["label"],
                   "state": x["state"], "detail": x["detail"]} for x in props],
        "working": any(s["state"] == labdom.PREPARANDO for s in p1["steps"])
                   or any(x["state"] == labdom.PREPARANDO for x in props),
    })


# ---- insumos --------------------------------------------------------------------------------
@bp.post("/p/<property_id>/archivos")
@auth.require
def archivos(property_id):
    _p(property_id)
    errores = _recibir(property_id, request)
    return _pagina(property_id, errores, 400) if errores else \
        redirect(url_for("lab.propiedad", property_id=property_id))


@bp.post("/p/<property_id>/hero")
@auth.require
def hero(property_id):
    _p(property_id)
    try:
        staging.set_hero(property_id, request.form.get("asset_id", ""))
    except staging.StagingError as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#pack1")


@bp.post("/p/<property_id>/foto/<asset_id>/borrar")
@auth.require
def borrar_foto(property_id, asset_id):
    _p(property_id)
    a = assets.get(asset_id, property_id)
    if a is None or a["kind"] != assets.PHOTO_ORIGINAL:
        abort(404)
    if staging.list_for(property_id, asset_id, include_benchmark=True):
        return _pagina(property_id, ["Esa foto ya se usó para ambientar: se conserva."], 400)
    assets.delete(asset_id, property_id)
    bench.remove_photo(asset_id)
    return redirect(url_for("lab.propiedad", property_id=property_id))


# ---- PACK 1 ---------------------------------------------------------------------------------
@bp.post("/p/<property_id>/pack1")
@auth.require
def generar_pack1(property_id):
    """§7 — un solo botón. Hace todo lo que puede y dice dónde hace falta una persona."""
    _p(property_id)
    f = request.form
    try:
        if (f.get("headcount") or "").strip():
            fid = fits.ensure_base(property_id, f["headcount"],
                                   presets.require_preset(f.get("workplace_preset")
                                                          or presets.DEFAULT_PRESET),
                                   presets.require_style(f.get("visual_style")
                                                         or presets.DEFAULT_STYLE))
            fits.set_express(fid, int(f["headcount"]),
                             f.get("workplace_preset") or presets.DEFAULT_PRESET,
                             f.get("visual_style") or presets.DEFAULT_STYLE)
        res = labdom.pack1_advance(property_id)
    except (fits.FitError, presets.PresetError, floorplan.FloorplanError,
            entitlements.EntitlementError, briefmod.BriefFormError, ValueError) as e:
        return _pagina(property_id, [str(e)], 400)
    if res.get("action") == "elegir_oficina":
        # E35 §16 — la ambigüedad de unidad se resuelve EN la página, no en otra pantalla.
        return redirect(url_for("lab.propiedad", property_id=property_id) + "#oficina")
    if res.get("action") == "revisar_inline":
        # E36 §3 — y la confirmación de geometría tampoco saca a nadie de acá.
        return redirect(url_for("lab.propiedad", property_id=property_id) + "#revision")
    if res.get("action") == "revisar":
        return redirect(url_for("lab.revisar_plano", property_id=property_id))
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#pack1")


@bp.get("/p/<property_id>/candidatos.png")
@auth.require
def candidatos_png(property_id):
    """La lámina con las zonas candidatas pintadas y numeradas. Es toda la interfaz de la pregunta:
    el operador no lee un id, mira la planta."""
    _p(property_id)
    destino = os.path.join(store.property_dir(property_id), "unit_candidates.png")
    try:
        ruta = units.overlay(property_id, destino)
    except units.UnitError:
        ruta = None
    if not ruta:
        abort(404)
    return send_file(ruta, mimetype="image/png", max_age=0)


@bp.post("/p/<property_id>/elegir-oficina")
@auth.require
def elegir_oficina(property_id):
    """UN clic (§6). Ni nombre técnico, ni unit id, ni coordenadas, ni escala, ni acceso.

    Después de elegir, el pipeline sigue solo: se vuelve a preparar la planta con la unidad ya
    resuelta y se cae en el camino normal de Pack 1."""
    _p(property_id)
    try:
        units.pick(property_id, (request.form.get("candidate_id") or "").strip())
        interventions.record(property_id, interventions.UNIT_SELECTION,
                             "el operador eligió la oficina sobre la lámina")
        ingest.auto_prepare(property_id)
    except (units.UnitError, ValueError) as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#pack1")


@bp.get("/p/<property_id>/revisar-plano")
@auth.require
def revisar_plano(property_id):
    """§6 — el fallback, no el paso normal.

    E34 sólo trae acá cuando la deducción automática no alcanzó, y ofrece primero lo que una
    persona puede resolver en un clic sin entender nada del motor. La medición manual de escala
    sigue existiendo detrás, en la herramienta técnica, como último recurso."""
    _p(property_id)
    try:
        case_id = floorplan.ensure_case(property_id)
    except (LookupError, floorplan.FloorplanError) as e:
        return _pagina(property_id, [str(e)], 400)
    return render_template("lab/revisar.html", property_id=property_id, case_id=case_id,
                           p=properties.require(property_id),
                           tecnico=floorplan.technical_state(property_id),
                           compuertas=ingest.pending_gates(property_id),
                           unidad=units.get(property_id),
                           inferencia=ingest.get(property_id))


@bp.post("/p/<property_id>/plano-completo")
@auth.require
def plano_completo(property_id):
    """«El dibujo completo es esta oficina.» Único hecho de la fuente que el motor no deduce."""
    _p(property_id)
    try:
        ingest.declare_whole_drawing(property_id)
    except (ValueError, intake.IntakeError) as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#pack1")


@bp.get("/p/<property_id>/deteccion.svg")
@auth.require
def deteccion_svg(property_id):
    """Lo que el motor leyó de esta planta, servido desde el LAB.

    Existe como ruta propia y no como enlace al caso técnico por una razón de E36 §25: el objetivo
    es UN shell. Mandar al operador a /case/<id> para ver un dibujo lo saca de la experiencia."""
    p = _p(property_id)
    case_id = p["floorplan_case_id"]
    if not case_id:
        abort(404)
    fp = intake.load_floorplate(case_id)
    svg = detected.overlay_svg(fp) if fp else None
    if svg is None:
        abort(404)
    # Se dibuja desde el artefacto y no se sirve un archivo: un SVG en disco puede ser de una
    # corrida anterior, y mostrar geometría vieja mientras se pide confirmarla sería pedir un
    # "sí" sobre algo que ya no es lo que se va a usar.
    return current_app.response_class(svg, mimetype="image/svg+xml")


@bp.post("/p/<property_id>/confirmar-geometria")
@auth.require
def confirmar_geometria(property_id):
    """E36 §3.B — «¿esto corresponde a la oficina?» → Sí. Inline, sin cambiar de pantalla."""
    _p(property_id)
    try:
        ingest.confirm_pending(property_id)
        interventions.record(property_id, interventions.GEOMETRY,
                             "confirmó la geometría detectada, inline")
        labdom.pack1_advance(property_id)
    except (ValueError, intake.IntakeError, floorplan.FloorplanError,
            entitlements.EntitlementError) as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#pack1")


@bp.post("/p/<property_id>/gold")
@auth.require
def gold_label(property_id):
    """E36 §8/§9 — el juicio de VERDAD sobre un componente de la geometría.

    No es la calificación del producto y no se guarda en la misma tabla: que un Pack quedara
    «Bueno» no prueba que el núcleo estuviera bien recortado."""
    _p(property_id)
    f = request.form
    try:
        gold.save(property_id, (f.get("component") or "").strip(),
                  (f.get("verdict") or "").strip(), f.get("note") or "", OPERATOR)
        if (f.get("verdict") or "") == gold.INCORRECTO:
            motivo = {gold.PRIMARY_ENTRANCE: interventions.ACCESS,
                      gold.UNIT: interventions.UNIT_SELECTION,
                      gold.SCALE: interventions.SCALE}.get(f.get("component"),
                                                           interventions.GEOMETRY)
            interventions.record(property_id, motivo,
                                 f"marcado INCORRECTO en la revisión de verdad: {f.get('component')}")
    except gold.GoldError as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#revision-verdad")


@bp.post("/p/<property_id>/piloto")
@auth.require
def piloto(property_id):
    """E36 §5/§7 — marcar la propiedad como parte del piloto real y declarar de dónde salió.

    La procedencia se DECLARA, no se infiere: no hay forma de mirar un archivo y saber si vino de
    una corredora o de un fixture, y adivinarlo inflaría la muestra con material que no es real."""
    _p(property_id)
    f = request.form
    try:
        realpilot.mark(property_id, in_pilot=f.get("in_pilot") == "1",
                       source_type=(f.get("source_type") or "").strip() or None,
                       source_reference=f.get("source_reference"))
    except realpilot.PilotError as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#revision-verdad")


@bp.get("/pilot/export.json")
@auth.require
def pilot_export():
    """E36 §22 — el dataset para auditar después. Sin nombres, sin rutas, sin credenciales."""
    return jsonify(realpilot.export())


@bp.post("/p/<property_id>/confirmar-plano")
@auth.require
def confirmar_plano(property_id):
    """«Lo que detectaron está bien.» E35 §14 — desde que el núcleo cae en la banda de
    incertidumbre, esta confirmación deja de ser excepcional y tiene que costar UN clic."""
    _p(property_id)
    try:
        ingest.confirm_pending(property_id)
        interventions.record(property_id, interventions.GEOMETRY,
                             "el operador confirmó la geometría detectada")
    except (ValueError, intake.IntakeError) as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#pack1")


@bp.post("/p/<property_id>/reanalizar")
@auth.require
def reanalizar(property_id):
    """Volver a mirar la planta después de una corrección en la herramienta técnica."""
    _p(property_id)
    try:
        ingest.auto_prepare(property_id)
    except ValueError as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#pack1")


@bp.post("/p/<property_id>/pack1/descargar")
@auth.require
def armar_pack1(property_id):
    _p(property_id)
    base = fits.base_of(property_id)
    try:
        floorplan.publish_all(property_id, fit_id=(base or {}).get("fit_id"))
        packs.export_zip(property_id)
    except (floorplan.FloorplanError, packs.PackNotReady) as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("customer.download_pack", property_id=property_id))


# ---- PACK 2 ---------------------------------------------------------------------------------
@bp.post("/p/<property_id>/pack2")
@auth.require
def generar_pack2(property_id):
    """§9 — el formulario simple de una propuesta, dentro de la misma página."""
    _p(property_id)
    f = request.form
    logo_id = None
    archivo = request.files.get("prospect_logo")
    # Se comprueba ANTES de crear nada: si el plano no está listo, generar va a fallar igual, y
    # una propuesta a medias en la lista es peor que un mensaje claro.
    if not floorplan.technical_state(property_id)["ready"]:
        return _pagina(property_id, ["Para hacer una propuesta necesitamos el plano preparado. "
                                     "Generá primero el Pack 1."], 400)
    try:
        labdom.enable_pack2(property_id)
        if archivo and archivo.filename:
            logo_id = branding.save_logo(archivo, branding.PROSPECT)
        preset = presets.require_preset(f.get("workplace_preset") or presets.DEFAULT_PRESET)
        estilo = presets.require_style(f.get("visual_style") or presets.DEFAULT_STYLE)
        fid = fits.create_prospect(property_id, f.get("prospect_name") or "", f.get("headcount"),
                                   preset, estilo, f.get("prospect_color") or "", logo_id,
                                   notes=f.get("notes") or "")
        if (f.get("workstations") or "").strip():
            rooms = {m: f.get(f"room_{m}") or 0 for m, _ in briefmod.MODULE_LABELS}
            fits.set_advanced_brief(fid, briefmod.build(f.get("prospect_name") or "PROPUESTA",
                                                        f.get("headcount"), f["workstations"],
                                                        rooms))
        else:
            fits.set_express(fid, int(f.get("headcount")), preset, estilo)
        fits.generate(fid)
    except (fits.FitError, presets.PresetError, branding.BrandError, briefmod.BriefFormError,
            entitlements.EntitlementError, ValueError) as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#pack2")


@bp.post("/p/<property_id>/pack2/<fit_id>/descargar")
@auth.require
def armar_pack2(property_id, fit_id):
    _p(property_id)
    if fits.get(fit_id, property_id) is None:
        abort(404)
    try:
        floorplan.publish_all(property_id, fit_id=fit_id)
        packs.export_zip(property_id, fit_id)
    except (floorplan.FloorplanError, packs.PackNotReady, LookupError) as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("customer.download_fit_pack", property_id=property_id, fit_id=fit_id))


# ---- EVALUACIÓN -----------------------------------------------------------------------------
@bp.post("/p/<property_id>/evaluar")
@auth.require
def evaluar(property_id):
    """§12 — cuatro botones. Motivos y comentario, opcionales."""
    _p(property_id)
    f = request.form
    try:
        reviews.save(property_id, f.get("artifact_type", ""), f.get("rating", ""),
                     artifact_id=f.get("artifact_id") or None, fit_id=f.get("fit_id") or None,
                     reason_tags=f.getlist("tags"), comment=f.get("comment") or "",
                     provenance=_procedencia(property_id, f), author=OPERATOR)
    except ValueError as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id)
                    + (f.get("anchor") or "#evaluaciones"))


def _procedencia(property_id, f):
    """§16 — lo que el artefacto sepa de sí mismo. Lo que no se sepa queda en None: no se inventa.
    Nada de esto se le muestra al usuario; existe para poder saber QUÉ versión produjo un 'malo'."""
    tipo, aid = f.get("artifact_type"), f.get("artifact_id") or None
    pr = {"engine_version": engine.engine_commit()}
    # E35 §15 — de qué ingest salió esto. Se lee del registro, no se recalcula: lo que importa es
    # con qué se produjo el artefacto que se está calificando, no lo que diría el motor hoy.
    sel = units.get(property_id)
    if sel:
        pr["unit_selection_source"] = sel["source"]
        pr["unit_selection_confidence"] = sel["confidence"]
    inf = ingest.get(property_id)
    if inf:
        pr["scale_source"] = inf["scale_source"]
        pr["scale_confidence"] = inf["scale_confidence"]
    case_id = properties.require(property_id)["floorplan_case_id"]
    fp = intake.load_floorplate(case_id) if case_id else None
    if fp:
        pr["geometry_confidences"] = ingest.element_confidences(fp)
    a = assets.get(aid, property_id) if aid else None
    if a:
        pr["artifact_sha256"] = a["sha256"]
        meta = store.js(a["metadata"], {}) or {}
        pr["run_id"] = meta.get("run_id")
        pr["provider"] = meta.get("provider")
        pr["model"] = meta.get("model")
    if tipo == "ALTERNATIVA" and f.get("fit_id"):
        r = fits.latest_run(f["fit_id"])
        if r:
            pr["run_id"] = r["run"]["run_id"]
            pr["engine_version"] = r["run"]["engine_commit"] or pr["engine_version"]
            alt = next((x for x in r["alternatives"] if x["alt"] == aid), None)
            if alt:
                pr["artifact_sha256"] = alt["layout_sha256"]
    if tipo == "STAGING":
        st = staging.approved_hero(property_id)
        if st:
            meta = store.js(st["metadata"], {}) or {}
            pr.update({"artifact_sha256": st["sha256"], "provider": meta.get("provider"),
                       "model": meta.get("model")})
    return pr


@bp.post("/p/<property_id>/nota")
@auth.require
def nota(property_id):
    _p(property_id)
    try:
        labdom.add_note(property_id, request.form.get("body", ""), author=OPERATOR)
    except ValueError as e:
        return _pagina(property_id, [str(e)], 400)
    return redirect(url_for("lab.propiedad", property_id=property_id) + "#evaluaciones")


# =================================================================================================
# §2/§22 — AJUSTES. Lo técnico existe y no se borra: deja de ser protagonista.
# =================================================================================================
@bp.get("/ajustes")
@auth.require
def config():
    return render_template("lab/settings.html", marca=branding.brokerage(),
                           preparacion=pilot.readiness(), stats=reviews.stats())


@bp.get("/ajustes/evaluaciones")
@auth.require
def evaluaciones():
    """§18 — el resumen de aprendizaje. Acá, no en la navegación principal.

    E35 §12/§17 añade las dos cifras que dicen si el ingest está mejorando o sólo lo parece: la
    precisión de autoaceptación por componente y cuántas veces hizo falta una persona."""
    panel = realpilot.dashboard()
    # Dos tablas de calibración a propósito: la del PILOTO REAL —que es la que manda (§7: REAL_*
    # only)— y la de E35 sobre los casos del repositorio, que sigue siendo la única evidencia
    # medida mientras el piloto no llegue a muestra. Mezclarlas escondería cuál es cuál.
    return render_template("lab/evaluaciones.html", stats=reviews.stats(),
                           calib=panel["calibration"], propuesta=panel["proposal"],
                           historico=calibration.metrics(), panel=panel,
                           manual=interventions.summary(),
                           source_labels=realpilot.SOURCE_LABEL,
                           filas=[dict(r, prop=properties.get(r["property_id"]))
                                  for r in (reviews._row(x) for x in store.q(
                                      "SELECT * FROM product_reviews ORDER BY created_at DESC "
                                      "LIMIT 200"))])


@bp.get("/debug")
@auth.require
def debug():
    """§22/§26 — la puerta de atrás. Todo el tooling de E27–E32 sigue vivo y accesible desde acá;
    lo que cambia es que ya no está en el camino de nadie que quiera probar el producto."""
    return render_template("lab/debug.html", preparacion=pilot.readiness(),
                           packs=grants.summary(), producto=entitlements.summary(),
                           modos=entitlements.PRODUCTS, etiquetas=entitlements.PRODUCT_LABEL,
                           default=entitlements.default_product(),
                           propiedades=properties.listing(),
                           productos={v["property"]["property_id"]:
                                      entitlements.product_of(v["property"]["property_id"])
                                      for v in properties.listing()})


@bp.post("/debug/modo")
@auth.require
def set_modo():
    try:
        entitlements.set_default_product(request.form.get("mode", ""))
    except ValueError:
        abort(400)
    return redirect(url_for("lab.debug"))


@bp.post("/debug/producto/<property_id>")
@auth.require
def set_product(property_id):
    _p(property_id)
    try:
        entitlements.set_product(property_id, request.form.get("product", ""))
    except (ValueError, LookupError) as e:
        return _err(str(e), url_for("lab.debug"))
    return redirect(url_for("lab.debug"))


@bp.post("/debug/recheck")
@auth.require
def recheck():
    """§A de E32 — sólo vuelve a detectar configuración. No revela ninguna clave."""
    pilot.log_event("ENV_RECHECK", detail={"credentials": [
        {"provider": p["name"], "credential": p["credential"]}
        for p in pilot.readiness()["providers"]]}, author=OPERATOR)
    return redirect(url_for("lab.benchmark") if request.form.get("from") == "benchmark"
                    else url_for("lab.debug"))


@bp.get("/feedback.json")
@auth.require
def feedback_json():
    return jsonify(labdom.feedback_export())


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


# =================================================================================================
# Rutas de E32 que ya no existen como pantalla. Se conservan como redirección para que ningún
# enlace guardado muera: todas llevan a la única página de la propiedad.
# =================================================================================================
@bp.get("/p/<property_id>/<any(resumen, plano, fotos, material, prospectos, pack, actividad):seccion>")
@auth.require
def _vieja_pestana(property_id, seccion):
    _p(property_id)
    ancla = {"material": "#pack1", "prospectos": "#pack2", "pack": "#pack1",
             "actividad": "#evaluaciones", "fotos": "#insumos", "plano": "#insumos"}.get(seccion, "")
    return redirect(url_for("lab.propiedad", property_id=property_id) + ancla)
