"""E28.6 — MARKETING PACK: el objeto comercial que se entrega.

Un pack es un manifiesto más un ZIP. La regla que lo gobierna es una sola y no es negociable:

    **el manifiesto dice la verdad sobre lo que hay dentro.**

Si no hay fotos ambientadas, el manifiesto dice `not_generated` y el ZIP no las trae. No se incluyen
marcadores de posición presentados como material real, ni documentos inventados para que el pack
"se vea completo". Un pack incompleto y honesto sirve; uno completo y falso destruye la confianza
que es justamente lo que se está vendiendo.

Todo asset del manifiesto es trazable (§21): de qué propiedad viene, de qué caso, de qué corrida,
de qué archivo original y con qué versión de esquema se generó.
"""
from __future__ import annotations

import io
import json
import os
import uuid
import zipfile
from typing import Dict, List, Optional

from .. import store
from . import assets, floorplan, properties, visual

SCHEMA_VERSION = "marketing_pack_v1"

#: Estados del pack. No hay "COMPLETE" todavía porque en E28 ningún pack puede estarlo.
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


def build_manifest(property_id: str) -> Dict:
    v = properties.view(property_id)
    p = v["property"]
    plano_orig = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
    plano_com = assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL)
    fotos = assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL)
    layouts = assets.list_of_kind(property_id, assets.LAYOUT_RENDER)
    tecnico = floorplan.technical_state(property_id)

    avisos: List[str] = []
    if plano_com is None:
        avisos.append("todavía no hay plano comercial: la planta no está confirmada")
    if not layouts:
        avisos.append("todavía no hay alternativas de layout publicadas")
    if not fotos:
        avisos.append("la propiedad no tiene fotos cargadas")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": store.now(),
        "property": {"property_id": p["property_id"], "title": p["title"],
                     "asset_type": p["asset_type"], "city": p["city"], "country": p["country"],
                     "reference": p["reference"], "published_area_m2": p["published_area_m2"],
                     "status": v["status"]},
        "provenance": {"floorplan_case_id": tecnico["case_id"],
                       "case_status": tecnico["case_status"],
                       "property_schema_version": p["schema_version"],
                       "pack_schema_version": SCHEMA_VERSION},
        "source_assets": {"floorplan_original": _asset_ref(plano_orig) if plano_orig else None,
                          "photos_original": [_asset_ref(a) for a in fotos]},
        "floorplan_commercial": _asset_ref(plano_com) if plano_com else None,
        "layouts": [dict(_asset_ref(a), **{"meta": store.js(a["metadata"], {})}) for a in layouts],
        "photos_staged": [],
        "before_after": [],
        "video": [],
        "visuals_status": visual.staging_status(),
        "warnings": avisos,
    }


def create(property_id: str) -> str:
    """Crea (o regenera) el pack de una propiedad. Idempotente por propiedad: uno vigente."""
    properties.require(property_id)
    man = build_manifest(property_id)
    pack_id = "pk_" + uuid.uuid4().hex[:12]
    store.ex("DELETE FROM packs WHERE property_id=?", (property_id,))
    store.ex("INSERT INTO packs(pack_id, property_id, schema_version, status, manifest, "
             "export_name, created_at) VALUES (?,?,?,?,?,NULL,?)",
             (pack_id, property_id, SCHEMA_VERSION, "VISUALS_PENDING",
              json.dumps(man, ensure_ascii=False, indent=2), store.now()))
    return pack_id


def get(property_id: str) -> Optional[Dict]:
    row = store.q1("SELECT * FROM packs WHERE property_id=? ORDER BY created_at DESC LIMIT 1",
                   (property_id,))
    if row is None:
        return None
    d = dict(row)
    d["manifest_obj"] = store.js(d["manifest"], {})
    return d


def has_export(property_id: str) -> bool:
    row = store.q1("SELECT export_name FROM packs WHERE property_id=? AND export_name IS NOT NULL",
                   (property_id,))
    return row is not None


def export_zip(property_id: str) -> Dict:
    """Arma el ZIP con lo que EXISTE. Devuelve el asset del export.

    Estructura, tal cual §16:
        /floorplan            plano original + plano comercial
        /layouts              A/B/C publicados
        /photos_original      las fotos tal como se subieron
        manifest.json
    """
    properties.require(property_id)
    man = build_manifest(property_id)
    buf = io.BytesIO()
    faltantes: List[str] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def meter(a: Dict, carpeta: str, nombre: str) -> None:
            ruta = assets.path_of(a)
            if not os.path.exists(ruta):
                faltantes.append(a["asset_id"])
                return
            # el nombre DENTRO del zip se construye acá; nunca sale del filesystem ni del usuario
            z.write(ruta, f"{carpeta}/{nombre}{os.path.splitext(a['stored_name'])[1]}")

        plano = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
        if plano:
            meter(plano, "floorplan", "plano_original")
        com = assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL)
        if com:
            meter(com, "floorplan", "plano_comercial")
        for a in assets.list_of_kind(property_id, assets.LAYOUT_RENDER):
            alt = (store.js(a["metadata"], {}) or {}).get("alt", a["asset_id"])
            meter(a, "layouts", f"alternativa_{alt}")
        for i, a in enumerate(assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL), 1):
            meter(a, "photos_original", f"foto_{i:02d}")
        if faltantes:
            man["warnings"].append(f"{len(faltantes)} asset(s) registrados sin archivo en disco")
        man["export"] = {"created_at": store.now(), "missing_assets": faltantes}
        z.writestr("manifest.json", json.dumps(man, ensure_ascii=False, indent=2))

    assets.purge_kind(property_id, assets.PACK_EXPORT)
    aid = assets.save_bytes(property_id, assets.PACK_EXPORT,
                            f"pack_{property_id}.zip", buf.getvalue(), "application/zip",
                            metadata={"pack_schema_version": SCHEMA_VERSION,
                                      "visuals_status": man["visuals_status"]["status"]})
    pack_id = create(property_id)
    store.ex("UPDATE packs SET export_name=?, manifest=? WHERE pack_id=?",
             (aid, json.dumps(man, ensure_ascii=False, indent=2), pack_id))
    return {"pack_id": pack_id, "asset_id": aid, "manifest": man}
