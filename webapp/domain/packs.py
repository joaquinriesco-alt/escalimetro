"""E28.6 — MARKETING PACK: el objeto comercial que se entrega.

Un pack es un manifiesto más un ZIP. La regla que lo gobierna es una sola y no es negociable:

    **el manifiesto dice la verdad sobre lo que hay dentro.**

Si no hay fotos ambientadas, el manifiesto dice `not_generated` y el ZIP no las trae. No se incluyen
marcadores de posición presentados como material real, ni documentos inventados para que el pack
"se vea completo". Un pack incompleto y honesto sirve; uno completo y falso destruye la confianza
que es justamente lo que se está vendiendo.

Todo asset del manifiesto es trazable (§21): de qué propiedad viene, de qué caso, de qué corrida,
de qué archivo original y con qué versión de esquema se generó.

E30 §4/§8 — ahora hay DOS packs y no se mezclan, porque son dos productos:

    BASE      el PACK DE PUBLICACIÓN de la propiedad. Marca de la corredora. Plano comercial,
              UNA alternativa representativa, fotos. Es lo que se compra de una vez.
    FIT       el pack de un fit request. Marca del prospecto. Las alternativas que el producto
              entregue. Es lo que se manda a un prospecto concreto, y hay uno por prospecto.

La regla de marca es dura y tiene test: **un pack BASE nunca lleva marca de prospecto**. Mandar
material con el logo de otro cliente, o publicar un aviso con el nombre de quien todavía no
arrendó, es un error comercial concreto y por eso se impide acá y no en una plantilla.
"""
from __future__ import annotations

import io
import json
import os
import uuid
import zipfile
from typing import Dict, List, Optional

from .. import store
from . import (assets, branding, entitlements, fits, floorplan, properties, proposal, staging,
               visual)

SCHEMA_VERSION = "marketing_pack_v1"

BASE = "BASE"
FIT = "FIT"
PACK_KINDS = (BASE, FIT)

#: Estados del pack. No hay "COMPLETE" todavía porque ningún pack puede estarlo mientras no haya
#: motor de ambientación: siempre le falta la imagen del §8.
PACK_STATES = ("VISUALS_PENDING", "FAILED")


def _asset_ref(a: Dict) -> Dict:
    """Cómo un asset aparece en el manifiesto: por identidad, nunca por ruta absoluta.

    No se filtra el path del volumen (§7/§24) y el manifiesto sigue siendo válido si el
    almacenamiento cambia."""
    return {"asset_id": a["asset_id"], "kind": a["kind"],
            "filename": a["original_filename"], "mime_type": a["mime_type"],
            "size_bytes": a["size_bytes"], "sha256": a["sha256"],
            "width_px": a["width_px"], "height_px": a["height_px"],
            "source_asset_id": a["source_asset_id"], "created_at": a["created_at"]}


# =================================================================================================
# E31 §21 — ¿ESTÁ LISTO EL PACK BASE? Se responde contra lo PROMETIDO, no contra lo que hay.
# =================================================================================================
READINESS_STATES = ("PREPARING", "NEEDS_STAGING", "STAGING_REVIEW", "READY", "DEGRADED", "BLOCKED")


class PackNotReady(RuntimeError):
    """Se intentó exportar un pack base que no cumple lo prometido y sin override interno."""


def readiness(property_id: str) -> Dict:
    """El pack de publicación promete: plano comercial + UN layout representativo + UNA imagen
    ambientada aprobada. `PACK_READY` sólo puede decirse cuando eso existe.

    Si el layout no se puede generar honestamente (SEARCH_EXHAUSTED en A/B/C), no se fabrica: el
    pack puede salir DEGRADADO, pero sólo con un motivo interno explícito, nunca en silencio."""
    p = properties.require(property_id)
    t = floorplan.technical_state(property_id)
    plano = assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL) is not None
    layouts = bool(layout_assets(property_id))
    st = staging.state(property_id)
    override = (p.get("pack_override_reason") or "").strip()
    faltan: List[str] = []
    if t["case_status"] in ("INPUT_NOT_READY", "FAILED"):
        return {"state": "BLOCKED", "missing": ["planta fuera de contrato o fallida"],
                "staging": st, "override": override}
    if not plano:
        faltan.append("plano comercial")
    if not layouts:
        faltan.append("alternativa representativa")
    if st["state"] != "APPROVED":
        faltan.append("imagen ambientada aprobada")
    if not faltan:
        estado = "READY"
    elif plano and override:
        # DEGRADADO: hay plano comercial pero falta layout y/o ambientación, y alguien de nuestro
        # equipo escribió por qué sale así. Sin plano no hay degradado que valga: no hay producto.
        estado = "DEGRADED"
    elif not plano:
        estado = "PREPARING"
    elif st["state"] in ("STAGING_REVIEW", "GENERATING"):
        estado = "STAGING_REVIEW"
    elif st["state"] in ("NOT_REQUESTED", "NEEDS_STAGING", "STAGING_UNAVAILABLE",
                         "STAGING_NEEDS_MANUAL_REVIEW"):
        estado = "NEEDS_STAGING" if layouts else "PREPARING"
    else:
        estado = "PREPARING"
    return {"state": estado, "missing": faltan, "staging": st, "override": override}


def set_override(property_id: str, reason: str) -> None:
    """Interno. Un pack degradado exige un motivo escrito; vacío lo quita."""
    properties.require(property_id)
    store.ex("UPDATE properties SET pack_override_reason=?, updated_at=? WHERE property_id=?",
             ((reason or "").strip()[:500] or None, store.now(), property_id))


def layout_assets(property_id: str, fit_id: Optional[str] = None) -> List[Dict]:
    """Los renders publicados que pertenecen a este pack.

    Con `fit_id`, sólo los de ESE fit: es lo que impide que la propuesta de un prospecto arrastre
    la alternativa que se generó para otro. Sin él (pack BASE), los que no son de ningún fit de
    prospecto, y como mucho tantos como el producto entregue."""
    meta = lambda a: (store.js(a["metadata"], {}) or {})            # noqa: E731
    todos = assets.list_of_kind(property_id, assets.LAYOUT_RENDER)
    if fit_id:
        propias = [a for a in todos if meta(a).get("fit_id") == fit_id]
        f = fits.get(fit_id, property_id)
        if propias or (f and f["kind"] == fits.PROSPECT):
            # Un prospecto ve SÓLO lo suyo, aunque no haya nada: heredar la lámina de otro
            # programa sería presentarle como suyo un estudio que no lo es.
            return propias
        fit_id = None                        # el fit BASE cae al material de la propiedad
    tope = entitlements.max_layouts_in_pack()
    base = [a for a in todos
            if not meta(a).get("fit_id") or meta(a).get("fit_kind") == fits.BASE]
    if tope is not None and len(base) > tope:
        # se conserva la representativa, no "las primeras": §18
        rep = [a for a in base if meta(a).get("representative")]
        base = (rep or base)[:tope]
    return base


def build_manifest(property_id: str, fit_id: Optional[str] = None) -> Dict:
    v = properties.view(property_id)
    p = v["property"]
    plano_orig = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
    plano_com = assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL)
    fotos = assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL)
    layouts = layout_assets(property_id, fit_id)
    tecnico = floorplan.technical_state(property_id)
    kind = FIT if fit_id else BASE
    fitv = fits.view(fit_id, property_id) if fit_id else None
    corredora = branding.brokerage()
    staged = staging_assets(property_id, fit_id)
    antes_despues = before_after_assets(property_id, fit_id)
    listo = readiness(property_id) if kind == BASE else None

    avisos: List[str] = []
    if plano_com is None:
        avisos.append("todavía no hay plano comercial: la planta no está confirmada")
    if not layouts:
        avisos.append("todavía no hay alternativas de layout publicadas")
    if not fotos:
        avisos.append("la propiedad no tiene fotos cargadas")
    if not staged and kind == BASE:
        avisos.append("no hay imagen ambientada aprobada: el pack de publicación está incompleto")
    if listo and listo["state"] == "DEGRADED":
        avisos.append(f"pack degradado por decisión interna: {listo['override']}")
    if not corredora["name"]:
        avisos.append("la corredora no tiene marca configurada: el material sale sin logo")

    #: §20 — la marca del prospecto SÓLO existe en un pack de fit. En el BASE es None, no vacío:
    #: la diferencia importa para quien lea el manifiesto sin conocer la regla.
    marca_prospecto = None
    if fitv and fitv["fit"]["kind"] == fits.PROSPECT:
        pr = fitv["brand"]
        marca_prospecto = {"name": pr["name"], "color": pr["color"], "has_logo": pr["has_logo"]}

    return {
        "schema_version": SCHEMA_VERSION,
        "pack_kind": kind,
        "product_mode": entitlements.mode(),
        "generated_at": store.now(),
        "property": {"property_id": p["property_id"], "title": p["title"],
                     "asset_type": p["asset_type"], "city": p["city"], "country": p["country"],
                     "reference": p["reference"], "published_area_m2": p["published_area_m2"],
                     "status": v["status"]},
        "branding": {"brokerage": {"name": corredora["name"], "color": corredora["color"],
                                   "has_logo": corredora["has_logo"]},
                     "prospect": marca_prospecto},
        "fit_request": ({"fit_id": fitv["fit"]["fit_id"], "kind": fitv["fit"]["kind"],
                         "label": fitv["fit"]["label"],
                         "headcount": fitv["fit"]["headcount"],
                         "workplace_preset": fitv["fit"]["workplace_preset"],
                         "visual_style": fitv["fit"]["visual_style"],
                         "brief_mode": fitv["fit"]["brief_mode"],
                         "brief": fitv["brief"]} if fitv else None),
        "provenance": {"floorplan_case_id": tecnico["case_id"],
                       "case_status": tecnico["case_status"],
                       "property_schema_version": p["schema_version"],
                       "pack_schema_version": SCHEMA_VERSION},
        "source_assets": {"floorplan_original": _asset_ref(plano_orig) if plano_orig else None,
                          "photos_original": [_asset_ref(a) for a in fotos]},
        "floorplan_commercial": _asset_ref(plano_com) if plano_com else None,
        "layouts": [dict(_asset_ref(a), **{"meta": store.js(a["metadata"], {})}) for a in layouts],
        "photos_staged": [_staged_ref(a) for a in staged],
        "before_after": [dict(_asset_ref(a), disclosure=staging.DISCLOSURE,
                              staged_asset_id=(store.js(a["metadata"], {}) or {}).get("staged_asset_id"))
                         for a in antes_despues],
        "video": [],
        "visuals_status": visual.staging_status(property_id),
        "readiness": ({"state": listo["state"], "missing": listo["missing"],
                       "override_reason": listo["override"] or None} if listo else None),
        "warnings": avisos,
    }


def staging_assets(property_id: str, fit_id: Optional[str] = None) -> List[Dict]:
    """Sólo PHOTO_STAGED, y una PHOTO_STAGED sólo existe si un humano la aprobó. Los candidatos
    rechazados viven en otra parte y no tienen forma de llegar acá."""
    out = []
    for a in assets.list_of_kind(property_id, assets.PHOTO_STAGED):
        if (store.js(a["metadata"], {}) or {}).get("fit_id") == fit_id:
            out.append(a)
    return out


def before_after_assets(property_id: str, fit_id: Optional[str] = None) -> List[Dict]:
    return [a for a in assets.list_of_kind(property_id, assets.BEFORE_AFTER)
            if (store.js(a["metadata"], {}) or {}).get("fit_id") == fit_id]


def _staged_ref(a: Dict) -> Dict:
    """§22 — lo que el manifiesto dice de una imagen ambientada: origen, proveedor/modelo, estilo,
    disclosure y hashes. NO el prompt, NO rutas, NO notas de revisión."""
    m = store.js(a["metadata"], {}) or {}
    return dict(_asset_ref(a), **{
        "source_asset_id": m.get("source_asset_id"), "attempt_id": m.get("attempt_id"),
        "provider": m.get("provider"), "model": m.get("model"),
        "visual_style": m.get("visual_style"), "request_version": m.get("request_version"),
        "input_sha256": m.get("input_sha256"), "output_sha256": m.get("output_sha256"),
        "human_review": {"fidelity": m.get("fidelity_status"), "quality": m.get("quality_score")},
        "disclosure": staging.DISCLOSURE, "disclosure_long": staging.DISCLOSURE_LONG})


def create(property_id: str, fit_id: Optional[str] = None) -> str:
    """Crea (o regenera) un pack. Idempotente por (propiedad, fit): uno vigente de cada uno.

    Regenerar reemplaza al anterior a propósito: un pack es una foto del material de HOY, y tener
    tres versiones distintas circulando es exactamente el problema que resuelve."""
    properties.require(property_id)
    if fit_id:
        fits.require(fit_id, property_id)
    man = build_manifest(property_id, fit_id)
    pack_id = "pk_" + uuid.uuid4().hex[:12]
    if fit_id:
        store.ex("DELETE FROM packs WHERE property_id=? AND fit_id=?", (property_id, fit_id))
    else:
        store.ex("DELETE FROM packs WHERE property_id=? AND fit_id IS NULL", (property_id,))
    store.ex("INSERT INTO packs(pack_id, property_id, schema_version, status, manifest, "
             "export_name, created_at, fit_id, kind) VALUES (?,?,?,?,?,NULL,?,?,?)",
             (pack_id, property_id, SCHEMA_VERSION, "VISUALS_PENDING",
              json.dumps(man, ensure_ascii=False, indent=2), store.now(),
              fit_id, FIT if fit_id else BASE))
    return pack_id


def get(property_id: str, fit_id: Optional[str] = None) -> Optional[Dict]:
    if fit_id:
        row = store.q1("SELECT * FROM packs WHERE property_id=? AND fit_id=? "
                       "ORDER BY created_at DESC LIMIT 1", (property_id, fit_id))
    else:
        row = store.q1("SELECT * FROM packs WHERE property_id=? AND fit_id IS NULL "
                       "ORDER BY created_at DESC LIMIT 1", (property_id,))
    if row is None:
        return None
    d = dict(row)
    d["manifest_obj"] = store.js(d["manifest"], {})
    return d


def has_export(property_id: str) -> bool:
    row = store.q1("SELECT export_name FROM packs WHERE property_id=? AND export_name IS NOT NULL",
                   (property_id,))
    return row is not None


def proposal_html(property_id: str, fit_id: Optional[str] = None,
                  url_for_asset=None) -> str:
    """La propuesta de este pack. `url_for_asset(clase, nombre, asset)` devuelve la URL de cada
    imagen: rutas relativas para el ZIP, rutas de la aplicación para la pantalla."""
    v = properties.view(property_id)
    p = v["property"]
    if fit_id:
        fitv = fits.view(fit_id, property_id)
    else:
        base = fits.base_of(property_id)
        fitv = fits.view(base["fit_id"], property_id) if base else None
    if fitv is None:
        # sin fit no hay programa que contar: se arma una propuesta mínima honesta
        fitv = {"fit": {"fit_id": None, "kind": BASE, "label": p["title"], "prospect_name": "",
                        "headcount": None, "notes": "", "workplace_preset": None,
                        "visual_style": None, "brief_mode": None},
                "brief": None, "brief_summary": None, "preset_label": None, "style_label": None,
                "brand": branding.brokerage(), "representative": None, "representative_why": ""}
    url = url_for_asset or (lambda clase, nombre, a: nombre)
    corredora = branding.brokerage()
    plano_com = assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL)
    layouts = layout_assets(property_id, fit_id)

    lays = []
    for a in layouts:
        meta = store.js(a["metadata"], {}) or {}
        # el motivo se lee de la LÁMINA, no del fit: así sigue siendo cierto cuando la corrida
        # vino de un caso vinculado a mano y el fit todavía no generó la suya.
        why = fits.SELECTED_BY_LABEL.get(meta.get("selected_by"), "")
        lays.append({"url": url("layouts", f'alternativa_{meta.get("alt", "")}', a),
                     "alt": meta.get("alt", ""), "name": meta.get("name", ""),
                     "representative": bool(meta.get("representative")),
                     "why": why if (meta.get("representative") and len(layouts) == 1) else ""})

    marca = fitv["brand"]
    logo = branding.logo(marca.get("logo_id"))
    tecnico = floorplan.technical_state(property_id)
    hero_staged = None
    for a in staging_assets(property_id, fit_id):
        orig = assets.get((store.js(a["metadata"], {}) or {}).get("source_asset_id") or "",
                          property_id)
        hero_staged = {"staged_url": url("photos_staged", "hero_ambientada", a),
                       "original_url": url("photos_staged", "hero_original", orig) if orig else None,
                       "style": (store.js(a["metadata"], {}) or {}).get("visual_style"),
                       "disclosure": staging.DISCLOSURE_LONG}
        break
    prov = {"Caso": tecnico["case_id"], "Motor": (fitv.get("run") or {}).get("engine_commit")
            if fitv.get("run") else None,
            "Programa": (fitv.get("brief") or {}).get("brief_id")}
    return proposal.render(
        p, fitv, corredora,
        floorplan_url=url("floorplan", "plano_comercial", plano_com) if plano_com else None,
        layout_urls=lays,
        logo_url=url("marca", "logo", logo) if logo else None,
        technical={k: v for k, v in prov.items() if v},
        staged=hero_staged)


def export_zip(property_id: str, fit_id: Optional[str] = None) -> Dict:
    """Arma el ZIP con lo que EXISTE. Devuelve el asset del export.

    Estructura, tal cual §16:
        /floorplan            plano original + plano comercial
        /layouts              las alternativas que este producto entrega
        /photos_original      las fotos tal como se subieron
        /marca                el logo que corresponda a este pack
        propuesta.html        la lámina de lectura, autocontenida
        manifest.json
    """
    properties.require(property_id)
    if fit_id:
        fits.require(fit_id, property_id)
    else:
        # §21 — el pack BASE no se exporta incompleto en silencio. O está listo, o alguien de
        # nuestro equipo escribió por qué sale degradado.
        listo = readiness(property_id)
        if listo["state"] not in ("READY", "DEGRADED"):
            raise PackNotReady("El pack de publicación todavía no está completo: falta "
                               + ", ".join(listo["missing"]) + ".")
    man = build_manifest(property_id, fit_id)
    buf = io.BytesIO()
    faltantes: List[str] = []
    rutas: Dict[str, str] = {}

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def meter(a: Dict, carpeta: str, nombre: str, ruta: Optional[str] = None) -> None:
            ruta = ruta or assets.path_of(a)
            if not os.path.exists(ruta):
                faltantes.append(a.get("asset_id") or nombre)
                return
            # el nombre DENTRO del zip se construye acá; nunca sale del filesystem ni del usuario
            destino = f"{carpeta}/{nombre}{os.path.splitext(ruta)[1].lower()}"
            z.write(ruta, destino)
            rutas[f"{carpeta}/{nombre}"] = destino

        plano = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
        if plano:
            meter(plano, "floorplan", "plano_original")
        com = assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL)
        if com:
            meter(com, "floorplan", "plano_comercial")
        for a in layout_assets(property_id, fit_id):
            alt = (store.js(a["metadata"], {}) or {}).get("alt", a["asset_id"])
            meter(a, "layouts", f"alternativa_{alt}")
        for i, a in enumerate(assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL), 1):
            meter(a, "photos_original", f"foto_{i:02d}")
        # §22/§23 — sólo la ambientada APROBADA, con su original al lado y el antes/después.
        for a in staging_assets(property_id, fit_id):
            meter(a, "photos_staged", "hero_ambientada")
            orig = assets.get((store.js(a["metadata"], {}) or {}).get("source_asset_id") or "",
                              property_id)
            if orig:
                meter(orig, "photos_staged", "hero_original")
            break
        for a in before_after_assets(property_id, fit_id):
            meter(a, "photos_staged", "antes_despues")
            break
        if staging_assets(property_id, fit_id):
            z.writestr("photos_staged/LEEME.txt",
                       staging.DISCLOSURE_LONG + "\nLa foto original se incluye al lado.\n")

        # §20 — el logo del pack: el del prospecto si es un pack de fit con marca propia; si no,
        # el de la corredora. Nunca los dos, y nunca el del prospecto en un pack BASE.
        marca_logo = None
        if fit_id:
            f = fits.require(fit_id, property_id)
            if f["kind"] == fits.PROSPECT and f["prospect_logo_id"]:
                marca_logo = branding.logo(f["prospect_logo_id"], branding.PROSPECT)
        if marca_logo is None and not fit_id:
            marca_logo = branding.logo(branding.brokerage()["logo_id"], branding.BROKERAGE)
        if marca_logo:
            meter(marca_logo, "marca", "logo", ruta=branding.logo_path(marca_logo))

        def url_rel(carpeta: str, nombre: str, a) -> str:
            return rutas.get(f"{carpeta}/{nombre}", f"{carpeta}/{nombre}")

        z.writestr("propuesta.html", proposal_html(property_id, fit_id, url_rel))
        if rutas.get("photos_staged/hero_ambientada"):
            rutas.setdefault("photos_staged/LEEME", "photos_staged/LEEME.txt")
        if faltantes:
            man["warnings"].append(f"{len(faltantes)} asset(s) registrados sin archivo en disco")
        man["export"] = {"created_at": store.now(), "missing_assets": faltantes,
                         "contents": sorted(rutas.values()) + ["propuesta.html", "manifest.json"]}
        z.writestr("manifest.json", json.dumps(man, ensure_ascii=False, indent=2))

    # sólo se borra el ZIP ANTERIOR DE ESTE MISMO PACK: el pack base y el de cada prospecto
    # conviven, y regenerar el de uno no puede llevarse puesto el del otro.
    for viejo_zip in assets.list_of_kind(property_id, assets.PACK_EXPORT):
        if (store.js(viejo_zip["metadata"], {}) or {}).get("fit_id") == fit_id:
            assets.delete(viejo_zip["asset_id"], property_id)

    sufijo = f"_{fit_id}" if fit_id else ""
    aid = assets.save_bytes(property_id, assets.PACK_EXPORT,
                            f"pack{sufijo}.zip", buf.getvalue(), "application/zip",
                            metadata={"pack_schema_version": SCHEMA_VERSION,
                                      "pack_kind": FIT if fit_id else BASE, "fit_id": fit_id,
                                      "visuals_status": man["visuals_status"]["status"]})
    pack_id = create(property_id, fit_id)
    store.ex("UPDATE packs SET export_name=?, manifest=? WHERE pack_id=?",
             (aid, json.dumps(man, ensure_ascii=False, indent=2), pack_id))
    return {"pack_id": pack_id, "asset_id": aid, "manifest": man}
