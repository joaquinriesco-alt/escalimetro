"""E28.3 — el adaptador entre una PROPIEDAD y el motor de plantas.

Este es el único lugar del dominio de producto que sabe que existe un CASE. Todo lo demás
—propiedades, assets, packs, la interfaz de cliente— pasa por acá. Si mañana el motor cambia de
forma, se cambia este archivo y nada más.

Lo que este adaptador NO hace, y es el punto (§10):

* no confirma nada por su cuenta;
* no escribe en `floorplate.json` ni en ningún artefacto del motor;
* no se salta `shell_adapter` ni ninguna compuerta existente;
* no marca READY para que una demo funcione.

Si el caso necesita que un humano mire la planta, la propiedad lo dice hacia adentro
(`needs_internal_review`) y hacia afuera dice "Estamos preparando la planta". Nada más.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from .. import engine, intake, store
from . import assets, properties


class FloorplanError(RuntimeError):
    """Falla de ESTA capa (no del motor). Va a `PROPERTY.status = FAILED`."""


def ensure_case(property_id: str) -> str:
    """Crea —o devuelve— el CASE del plano de esta propiedad.

    Idempotente a propósito: llamarlo dos veces no duplica casos ni vuelve a copiar el archivo."""
    p = properties.require(property_id)
    if p["floorplan_case_id"]:
        if store.q1("SELECT case_id FROM cases WHERE case_id=?", (p["floorplan_case_id"],)):
            return p["floorplan_case_id"]
        # el caso desapareció del volumen: se vuelve a crear en vez de arrastrar un puntero roto
        store.ex("UPDATE properties SET floorplan_case_id=NULL WHERE property_id=?", (property_id,))
    plano = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
    if plano is None:
        raise FloorplanError("la propiedad todavía no tiene plano")
    ruta = assets.path_of(plano)
    if not os.path.exists(ruta):
        raise FloorplanError("el archivo del plano no está en el volumen")
    case_id = intake.create_case_from_path(ruta, plano["original_filename"], p["title"])
    # el área publicada declarada por el cliente es un hecho de entrada del caso, igual que en E27
    if p["published_area_m2"]:
        store.ex("UPDATE cases SET published_area_m2=?, title=? WHERE case_id=?",
                 (p["published_area_m2"], p["title"], case_id))
    properties.link_case(property_id, case_id)
    return case_id


def technical_state(property_id: str) -> Dict:
    """Lo que el motor dice, sin traducir. Para uso INTERNO."""
    p = properties.require(property_id)
    cid = p["floorplan_case_id"]
    if not cid:
        return {"case_id": None, "case_status": None, "ready": False, "pending": []}
    row = store.q1("SELECT status FROM cases WHERE case_id=?", (cid,))
    fp = intake.load_floorplate(cid)
    sr = (fp or {}).get("shell_readiness") or {}
    return {"case_id": cid, "case_status": (row or {})["status"] if row else None,
            "ready": bool(sr.get("ready_for_layout")),
            "pending": intake.humanize_missing(sr.get("requires_confirmation") or []),
            "has_geometry": fp is not None}


def customer_state(property_id: str) -> Dict:
    """Lo mismo, en lenguaje de cliente. Nunca incluye el motivo técnico."""
    t = technical_state(property_id)
    if t["case_id"] is None:
        return {"step": "floorplan", "done": False, "text": "Falta subir el plano"}
    if t["ready"]:
        return {"step": "floorplan", "done": True, "text": "Plano listo"}
    return {"step": "floorplan", "done": False, "text": "Estamos preparando la planta"}


# ---------------------------------------------------------------------------------------------
# outputs del motor que la capa comercial puede publicar
# ---------------------------------------------------------------------------------------------
def layout_runs(property_id: str) -> List[Dict]:
    """Corridas del caso con al menos una alternativa FIT, de la más nueva a la más vieja."""
    p = properties.require(property_id)
    if not p["floorplan_case_id"]:
        return []
    out = []
    for r in store.q("SELECT * FROM runs WHERE case_id=? ORDER BY created_at DESC",
                     (p["floorplan_case_id"],)):
        alts = [dict(a) for a in store.q(
            "SELECT * FROM alternatives WHERE run_id=? ORDER BY alt", (r["run_id"],))]
        if any(a["status"] == "FIT" for a in alts):
            out.append({"run": dict(r), "alternatives": alts})
    return out


def latest_layouts(property_id: str) -> Optional[Dict]:
    runs = layout_runs(property_id)
    return runs[0] if runs else None


def layout_asset_path(property_id: str, run_id: str, alt: str, kind: str = "commercial") -> Optional[str]:
    """Ruta del render que YA produjo el motor. No se genera nada nuevo acá."""
    p = properties.require(property_id)
    if not p["floorplan_case_id"] or alt not in engine.ALTS:
        return None
    if store.q1("SELECT run_id FROM runs WHERE run_id=? AND case_id=?",
                (run_id, p["floorplan_case_id"])) is None:
        return None                                           # corrida de otro caso: no se sirve
    nombre = {"commercial": "layout_commercial.png", "technical": "layout_technical.svg"}[kind]
    ruta = os.path.join(engine.run_dir(p["floorplan_case_id"], run_id), "alternatives", alt, nombre)
    return ruta if os.path.exists(ruta) else None


# ---------------------------------------------------------------------------------------------
# publicación: convertir salidas del motor en assets comerciales de la propiedad
# ---------------------------------------------------------------------------------------------
def _shell_of(case_id: str):
    """ShellM del caso. Pasa por `shell_adapter`, así que hereda su negativa a construir un shell
    que no esté listo: si el caso no está confirmado, esto lanza y NO hay plano comercial."""
    import sys                                                # noqa: PLC0415
    sys.path.insert(0, os.path.join(intake.REPO_ROOT, "src"))
    from escalimetro.case_context import from_case_dir        # noqa: PLC0415
    from escalimetro.layout.e06.scale import scaled_shell     # noqa: PLC0415
    from escalimetro.schemas.floorplate import Floorplate     # noqa: PLC0415
    ctx = from_case_dir(store.case_dir(case_id))
    return scaled_shell(Floorplate.load(ctx.require_floorplate()), 1.0)


def publish_commercial_floorplan(property_id: str) -> Optional[str]:
    """Genera el PLANO COMERCIAL de la propiedad. Devuelve el asset_id, o None si todavía no
    corresponde porque la planta no está lista.

    No fuerza nada: si `shell_adapter` se niega, no hay plano y el estado lo refleja."""
    from . import assets, commercial                          # noqa: PLC0415
    t = technical_state(property_id)
    if not t["case_id"] or not t["ready"]:
        return None
    try:
        shell = _shell_of(t["case_id"])
    except Exception as e:                                    # noqa: BLE001
        raise FloorplanError(f"no se pudo construir la planta base: {e}") from e
    p = properties.require(property_id)
    svg = commercial.commercial_svg(shell, p["title"], shell.usable.area)
    try:
        import cairosvg                                       # noqa: PLC0415
        png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=2000)
    except Exception as e:                                    # noqa: BLE001
        raise FloorplanError(f"no se pudo rasterizar la planta base: {e}") from e
    assets.purge_kind(property_id, assets.FLOORPLAN_COMMERCIAL)
    origen = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
    return assets.save_bytes(
        property_id, assets.FLOORPLAN_COMMERCIAL, "plano_comercial.png", png, "image/png",
        source_asset_id=(origen or {}).get("asset_id"),
        metadata={"case_id": t["case_id"], "usable_area_m2": round(shell.usable.area, 1),
                  "renderer": "commercial_v1",
                  "_nota": "planta base: NO es la alternativa A"})


def publish_layouts(property_id: str, run_id: Optional[str] = None,
                    fit_id: Optional[str] = None) -> List[str]:
    """Publica como assets comerciales los renders que el motor YA produjo. No genera geometría,
    no vuelve a correr nada y no elige por calidad arquitectónica.

    E30 §4/§18 — CUÁNTAS se publican lo decide el producto, no el solver:

        Pro      las alternativas con layout de la corrida (hasta tres).
        ONE_OFF  exactamente UNA, la representativa, elegida por el criterio declarado en
                 `fits.pick_representative` y con el motivo guardado en el asset.

    El motor sigue calculando A/B/C en los dos casos: eso es cómo está hecho y no se toca. La
    diferencia es comercial y vive acá."""
    from . import assets, entitlements, fits                  # noqa: PLC0415
    if fit_id:
        f = fits.require(fit_id, property_id)
        ultimo = fits.latest_run(fit_id)
        if ultimo is None:
            return []
        entregar = fits.delivered(fit_id)
        rep = fits.representative(fit_id)
        etiqueta, clase = f["label"], f["kind"]
    else:
        # camino heredado de E28: la propiedad está vinculada a un caso que ya tenía corridas y
        # ninguna nació de un fit request. Sigue funcionando, con el mismo tope de producto.
        ultimo = latest_layouts(property_id)
        if run_id and ultimo and ultimo["run"]["run_id"] != run_id:
            ultimo = next((r for r in layout_runs(property_id)
                           if r["run"]["run_id"] == run_id), None)
        if ultimo is None:
            return []
        rep = fits.pick_representative(ultimo["run"], ultimo["alternatives"])
        entregar = ([a for a in ultimo["alternatives"] if a["status"] == "FIT"]
                    if entitlements.allows(entitlements.ABC_ALTERNATIVES)
                    else ([rep["alt"]] if rep else []))
        etiqueta, clase = "", None

    p = properties.require(property_id)
    assets.purge_kind(property_id, assets.LAYOUT_RENDER)
    origen = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
    rep_alt = (rep or {}).get("alt", {}).get("alt")
    creados = []
    for alt in entregar:
        if alt["status"] != "FIT":
            continue
        ruta = layout_asset_path(property_id, ultimo["run"]["run_id"], alt["alt"])
        if not ruta:
            continue
        with open(ruta, "rb") as fh:
            blob = fh.read()
        es_rep = alt["alt"] == rep_alt
        creados.append(assets.save_bytes(
            property_id, assets.LAYOUT_RENDER, f"alternativa_{alt['alt']}.png", blob, "image/png",
            source_asset_id=(origen or {}).get("asset_id"),
            metadata={"alt": alt["alt"], "name": alt["name"],
                      "case_id": p["floorplan_case_id"], "run_id": ultimo["run"]["run_id"],
                      "brief_id": ultimo["run"]["brief_id"],
                      "engine_commit": ultimo["run"]["engine_commit"],
                      "layout_sha256": alt["layout_sha256"],
                      "fit_id": fit_id, "fit_label": etiqueta, "fit_kind": clase,
                      "representative": es_rep,
                      "selected_by": (rep or {}).get("selected_by") if es_rep else None,
                      "quality": store.js(alt["quality"], {})}))
    return creados


def publish_all(property_id: str, fit_id: Optional[str] = None) -> Dict:
    """Lo que hace el botón «Preparar material comercial»."""
    plano = publish_commercial_floorplan(property_id)
    layouts = publish_layouts(property_id, fit_id=fit_id)
    properties.touch(property_id)
    return {"floorplan_commercial": plano, "layouts": layouts}
