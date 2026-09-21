"""E28.5 — SUPERFICIE DE CLIENTE. Separada de ESCALÍMETRO INTERNAL.

La frontera es real aunque hoy no haya roles: vive en su propio Blueprint, sus propias plantillas
(`templates/customer/`) y su propio vocabulario. Un cliente que entre acá no ve —ni puede navegar
hacia— shell, núcleo, pilares, confirmaciones geométricas ni corridas del solver.

DEUDA DECLARADA (§9): la autenticación sigue siendo una sola cuenta compartida. Esto NO es un
sistema de roles: un usuario autenticado puede escribir a mano una URL interna y llegar. Separar de
verdad exige RBAC, y §9 dice explícitamente que no lo inventemos ahora. Queda anotado en
docs/E28_PROPERTY_PIPELINE.md como lo primero a resolver antes de que esto vea a un cliente real.

Lo que sí se respeta desde ya: ninguna plantilla de cliente enlaza a una ruta interna, y ningún
texto de esta superficie usa vocabulario del motor. Hay tests de ambas cosas.
"""
from __future__ import annotations

import os

from flask import (Blueprint, abort, redirect, render_template, request, send_file, url_for)

from . import auth, store
from .domain import assets, floorplan, packs, properties

bp = Blueprint("customer", __name__, url_prefix="/properties")

#: Pasos que el cliente ve. Uno por fila, con estado. Nada más.
def _pasos(v):
    t = floorplan.technical_state(v["property"]["property_id"])
    pid = v["property"]["property_id"]
    plano_com = assets.first_of_kind(pid, assets.FLOORPLAN_COMMERCIAL)
    layouts = assets.list_of_kind(pid, assets.LAYOUT_RENDER)
    fotos = assets.list_of_kind(pid, assets.PHOTO_ORIGINAL)
    pack = packs.get(pid)
    return [
        {"nombre": "Plano",
         "estado": "listo" if plano_com else ("preparando" if t["case_id"] else "pendiente"),
         "detalle": "Recibido y preparado" if plano_com else
                    ("Estamos preparando la planta" if t["case_id"] else "Falta subir el plano")},
        {"nombre": "Alternativas de layout",
         "estado": "listo" if layouts else "pendiente",
         "detalle": f"{len(layouts)} alternativa(s)" if layouts else "Todavía no disponibles"},
        {"nombre": "Fotos",
         "estado": "listo" if fotos else "pendiente",
         "detalle": f"{len(fotos)} foto(s) recibidas" if fotos else "Todavía no subiste fotos"},
        {"nombre": "Imágenes ambientadas",
         "estado": "pendiente",
         "detalle": "Todavía no disponibles en esta versión"},
        {"nombre": "Pack comercial",
         "estado": "listo" if (pack and pack["export_name"]) else "pendiente",
         "detalle": "Listo para descargar" if (pack and pack["export_name"])
                    else "Se arma cuando el plano y las alternativas estén listos"},
    ]


def _prop_or_404(property_id):
    p = properties.get(property_id)
    if p is None:
        abort(404)
    return p


@bp.get("/")
@auth.require
def index():
    return render_template("customer/list.html", propiedades=properties.listing())


@bp.get("/new")
@auth.require
def new():
    return render_template("customer/new.html", errors={}, form=None)


@bp.post("/new")
@auth.require
def create():
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
                               errors={"published_area_m2": "La superficie debe ser un número mayor que cero."}), 400
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


@bp.get("/<property_id>")
@auth.require
def detail(property_id):
    _prop_or_404(property_id)
    v = properties.view(property_id)
    return render_template(
        "customer/detail.html", v=v, p=v["property"], pasos=_pasos(v),
        plano=assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL),
        plano_com=assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL),
        fotos=assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL),
        layouts=assets.list_of_kind(property_id, assets.LAYOUT_RENDER),
        pack=packs.get(property_id), errores=[])


@bp.post("/<property_id>/assets")
@auth.require
def upload(property_id):
    _prop_or_404(property_id)
    errores = _recibir_archivos(property_id, request)
    if errores:
        v = properties.view(property_id)
        return render_template(
            "customer/detail.html", v=v, p=v["property"], pasos=_pasos(v),
            plano=assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL),
            plano_com=assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL),
            fotos=assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL),
            layouts=assets.list_of_kind(property_id, assets.LAYOUT_RENDER),
            pack=packs.get(property_id), errores=errores), 400
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


@bp.post("/<property_id>/pack")
@auth.require
def build_pack(property_id):
    _prop_or_404(property_id)
    packs.export_zip(property_id)
    return redirect(url_for("customer.detail", property_id=property_id))


@bp.get("/<property_id>/pack.zip")
@auth.require
def download_pack(property_id):
    _prop_or_404(property_id)
    pack = packs.get(property_id)
    if not pack or not pack["export_name"]:
        abort(404)
    a = assets.get(pack["export_name"], property_id)
    if a is None or not os.path.exists(assets.path_of(a)):
        abort(404)
    return send_file(assets.path_of(a), mimetype="application/zip", as_attachment=True,
                     download_name=f"escalimetro_{property_id}.zip")
