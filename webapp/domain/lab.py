"""E32 — ESCALÍMETRO LAB: lo que la consola interna necesita saber de una propiedad.

Dos cosas viven acá y ninguna es una pantalla:

1. **El avance real.** Una lista de pasos con estado, cada uno derivado de un hecho verificable
   —un archivo en el volumen, una fila en la base, un artefacto del motor—. §6 del encargo lo pide
   con estas palabras: "No checkboxes manuales decorativos". Nadie puede marcar un paso como hecho;
   el paso está hecho o no lo está.

2. **La línea de tiempo.** También DERIVADA. No hay una tabla de eventos que alguien tenga que
   acordarse de escribir en cada mutación: esa tabla se desincroniza el primer día que un camino
   nuevo olvide llamarla, y entonces la consola miente sobre lo que pasó. Lo único que se guarda
   son las acciones humanas que no dejan otro rastro (una nota, una valoración, la aprobación de un
   proveedor), porque ésas no se pueden deducir de ningún artefacto.

Todo lo de este módulo es INTERNO. Las notas y las valoraciones no salen en ningún pack ni en
ninguna propuesta, y hay test de eso.
"""
from __future__ import annotations

import os
import uuid
from typing import Dict, List, Optional

from .. import intake, store
from . import (assets, fits, floorplan, ingest, packs, pilot, presets, properties,
               staging, units)

#: §17 — valoración interna. Tres estados y nada más: esto no es un CRM.
PROPERTY_FEEDBACK = (("GOOD", "Funcionó"), ("NEEDS_WORK", "Hay que ajustar"),
                     ("BAD_INPUT", "El material de entrada no servía"))
FIT_FEEDBACK = (("GOOD", "Buen resultado"), ("NEEDS_WORK", "Mejorable"), ("BAD", "No sirve"))
NOTE_SCOPES = ("PROPERTY", "FIT", "LAYOUT", "STAGING")


# =================================================================================================
# §6 — AVANCE, derivado de hechos
# =================================================================================================
def progress(property_id: str) -> List[Dict]:
    """Los pasos del producto puntual, en orden, cada uno con su hecho de respaldo.

    `done` sale siempre de mirar algo real. `detail` dice qué se miró, para que cuando un paso
    aparezca incompleto se sepa exactamente qué falta en vez de tener que adivinarlo."""
    p = properties.require(property_id)
    t = floorplan.technical_state(property_id)
    plano_orig = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
    plano_com = assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL)
    layouts = packs.layout_assets(property_id)
    fotos = assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL)
    h = staging.hero(property_id)
    st = staging.state(property_id)
    base = fits.base_of(property_id)
    pack = packs.get(property_id)
    listo = packs.readiness(property_id)

    def paso(clave, nombre, done, detalle, ruta=None, bloqueado=False):
        return {"key": clave, "name": nombre, "done": bool(done), "detail": detalle,
                "route": ruta, "blocked": bloqueado}

    return [
        paso("data", "Datos", bool(p["title"]),
             " · ".join(x for x in [p["city"], p["reference"],
                                    f'{p["published_area_m2"]:.0f} m²'
                                    if p["published_area_m2"] else ""] if x) or "sin detalle"),
        paso("floorplan", "Plano subido", plano_orig is not None,
             plano_orig["original_filename"] if plano_orig else "falta el plano"),
        paso("case", "Caso técnico creado", bool(t["case_id"]),
             t["case_id"] or "se crea al preparar la planta"),
        paso("geometry", "Geometría revisada", bool(t["ready"]),
             "planta confirmada" if t["ready"] else
             (", ".join(t["pending"]) if t["pending"] else "falta analizar y confirmar")),
        paso("commercial", "Plano comercial", plano_com is not None,
             "publicado" if plano_com else "se publica cuando la planta está confirmada"),
        paso("program", "Programa base", bool(base and base["headcount"]),
             f'{base["headcount"]} personas · '
             f'{presets.PRESET_LABEL.get(base["workplace_preset"], "")}'
             if (base and base["headcount"]) else "falta decir cuántas personas"),
        paso("layout", "Layout representativo", bool(layouts),
             f"{len(layouts)} publicado(s)" if layouts else "falta generar o publicar"),
        paso("photos", "Fotos", bool(fotos),
             f"{len(fotos)} foto(s)" if fotos else "falta subir fotos"),
        paso("hero", "Foto principal", h is not None,
             h["original_filename"] if h else "falta elegirla"),
        paso("staging", "Ambientación aprobada", st["state"] == "APPROVED", st["reason"],
             bloqueado=st["state"] == "STAGING_PROVIDER_NOT_APPROVED"),
        paso("pack", "Pack listo", bool(pack and pack["export_name"]
                                        and listo["state"] in ("READY", "DEGRADED")),
             "exportado" if (pack and pack["export_name"]) else
             ("falta: " + ", ".join(listo["missing"]) if listo["missing"] else "listo para armar")),
    ]


def summary(property_id: str) -> Dict:
    ps = progress(property_id)
    hechos = sum(1 for x in ps if x["done"])
    return {"steps": ps, "done": hechos, "total": len(ps),
            "pct": round(100 * hechos / len(ps)) if ps else 0,
            "next": next((x for x in ps if not x["done"]), None)}


def overview() -> Dict:
    """El resumen de arriba del dashboard. Sin BI: cinco números que se pueden verificar."""
    props = properties.listing()
    listas = necesitan = staging_pend = 0
    n_fits = 0
    for v in props:
        pid = v["property"]["property_id"]
        if v["status"] == "PACK_READY":
            listas += 1
        if v["needs_internal_review"]:
            necesitan += 1
        # "pendiente" = la propiedad quiere una imagen ambientada y todavía no la tiene, sea
        # porque falta generarla, porque falta revisarla o porque nadie aprobó un proveedor.
        # Dejar fuera el último caso haría que el tablero dijera 0 justo cuando más falta.
        if staging.state(pid)["state"] in ("NEEDS_STAGING", "STAGING_REVIEW", "GENERATING",
                                           "STAGING_NEEDS_MANUAL_REVIEW",
                                           "STAGING_PROVIDER_NOT_APPROVED"):
            staging_pend += 1
        n_fits += len(fits.list_for(pid, include_base=False))
    return {"properties": len(props), "ready": listas, "need_review": necesitan,
            "staging_pending": staging_pend, "fit_requests": n_fits,
            "staging_review_queue": len(staging.pending_review_all())}


def rows() -> List[Dict]:
    """Una fila por propiedad para la portada."""
    out = []
    for v in properties.listing():
        pid = v["property"]["property_id"]
        s = summary(pid)
        out.append({"v": v, "p": v["property"], "progress": s,
                    "staging": staging.state(pid),
                    "pack": packs.readiness(pid),
                    "fits": len(fits.list_for(pid, include_base=False)),
                    "last": v["property"]["updated_at"]})
    return out


# =================================================================================================
# §15 — LÍNEA DE TIEMPO, derivada
# =================================================================================================
def timeline(property_id: str) -> List[Dict]:
    """Qué pasó y cuándo, leído de los artefactos. Ordenado de lo más nuevo a lo más viejo."""
    p = properties.require(property_id)
    ev: List[Dict] = [{"at": p["created_at"], "kind": "created", "text": "Propiedad creada"}]

    for a in assets.all_of(property_id):
        etiqueta = {
            assets.FLOORPLAN_ORIGINAL: "Plano subido",
            assets.PHOTO_ORIGINAL: "Foto subida",
            assets.FLOORPLAN_COMMERCIAL: "Plano comercial publicado",
            assets.LAYOUT_RENDER: "Alternativa publicada",
            assets.PHOTO_STAGED: "Imagen ambientada publicada",
            assets.BEFORE_AFTER: "Antes/después generado",
            assets.PACK_EXPORT: "Pack exportado",
        }.get(a["kind"])
        if etiqueta:
            ev.append({"at": a["created_at"], "kind": a["kind"].lower(),
                       "text": f'{etiqueta} · {a["original_filename"]}'})

    cid = p["floorplan_case_id"]
    if cid:
        it = store.q1("SELECT analyzed_at, updated_at FROM intake WHERE case_id=?", (cid,))
        if it and it["analyzed_at"]:
            ev.append({"at": it["analyzed_at"], "kind": "analyzed",
                       "text": "Análisis de la planta ejecutado"})
        t = floorplan.technical_state(property_id)
        if t["ready"] and it and it["updated_at"]:
            ev.append({"at": it["updated_at"], "kind": "confirmed",
                       "text": "Geometría confirmada por revisión humana"})
        for r in store.q("SELECT * FROM runs WHERE case_id=? ORDER BY created_at", (cid,)):
            n_fit = store.q1("SELECT COUNT(*) n FROM alternatives WHERE run_id=? AND status='FIT'",
                             (r["run_id"],))["n"]
            ev.append({"at": r["created_at"], "kind": "run",
                       "text": f'Corrida del motor {r["run_id"]} · {r["status"]} · '
                               f'{n_fit} alternativa(s) con layout', "ref": r["run_id"]})

    for f in fits.list_for(property_id, include_archived=True):
        ev.append({"at": f["created_at"], "kind": "fit",
                   "text": f'{"Programa base" if f["kind"] == "BASE" else "Prospecto"}: {f["label"]}',
                   "ref": f["fit_id"]})

    for a in staging.list_for(property_id, include_benchmark=True):
        txt = {"QUEUED": "Ambientación encolada", "RUNNING": "Ambientación generando",
               "GENERATED": "Candidato de ambientación generado",
               "FAILED": "Intento de ambientación fallido"}.get(a["status"], a["status"])
        extra = f' · {a["provider"]}' + (" · experimental" if a["experimental"] else "")
        ev.append({"at": a["created_at"], "kind": "staging", "text": txt + extra,
                   "ref": a["attempt_id"]})
        if a["reviewed_at"]:
            ev.append({"at": a["reviewed_at"], "kind": "staging_review",
                       "text": f'Revisión humana: fidelidad {a["fidelity_status"]}'
                               f' · {a["review_status"]}', "ref": a["attempt_id"]})

    for n in notes(property_id):
        ev.append({"at": n["created_at"], "kind": "note", "text": f'Nota: {n["body"]}'})
    for e in pilot.events(property_id=property_id, limit=50):
        ev.append({"at": e["created_at"], "kind": "event", "text": _event_text(e)})

    return sorted(ev, key=lambda x: x["at"] or "", reverse=True)


def _event_text(e: Dict) -> str:
    d = e["detail_obj"]
    if e["kind"] == "PROVIDER_SMOKE":
        return (f'Smoke test de {d.get("provider")}: '
                f'{"OK" if d.get("ok") else "falló"}'
                + (f' · {d.get("latency_ms")} ms' if d.get("latency_ms") else ""))
    if e["kind"] == "PROVIDER_APPROVED":
        return f'Proveedor aprobado: {d.get("provider")} · {d.get("model")}'
    return e["kind"]


# =================================================================================================
# §16/§17 — NOTAS Y VALORACIÓN. Internas, y se quedan adentro.
# =================================================================================================
def add_note(property_id: str, body: str, scope: str = "PROPERTY",
             fit_id: Optional[str] = None, author: str = "") -> str:
    properties.require(property_id)
    cuerpo = (body or "").strip()
    if not cuerpo:
        raise ValueError("La nota está vacía.")
    if scope not in NOTE_SCOPES:
        raise ValueError(f"ámbito de nota desconocido: {scope}")
    nid = "nt_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO lab_notes(note_id, property_id, fit_id, scope, body, author, created_at) "
             "VALUES (?,?,?,?,?,?,?)",
             (nid, property_id, fit_id, scope, cuerpo[:2000], (author or "")[:80], store.now()))
    return nid


def notes(property_id: str, fit_id: Optional[str] = None) -> List[Dict]:
    if fit_id:
        rows = store.q("SELECT * FROM lab_notes WHERE property_id=? AND fit_id=? "
                       "ORDER BY created_at DESC", (property_id, fit_id))
    else:
        rows = store.q("SELECT * FROM lab_notes WHERE property_id=? ORDER BY created_at DESC",
                       (property_id,))
    return [dict(r) for r in rows]


def delete_note(note_id: str, property_id: str) -> bool:
    r = store.q1("SELECT note_id FROM lab_notes WHERE note_id=? AND property_id=?",
                 (note_id, property_id))
    if r is None:
        return False
    store.ex("DELETE FROM lab_notes WHERE note_id=?", (note_id,))
    return True


def set_feedback(property_id: str, value: str) -> None:
    validos = [k for k, _ in PROPERTY_FEEDBACK]
    if value and value not in validos:
        raise ValueError(f"valoración desconocida: {value}")
    store.ex("UPDATE properties SET lab_feedback=?, updated_at=? WHERE property_id=?",
             (value or None, store.now(), property_id))


def set_fit_feedback(fit_id: str, property_id: str, value: str) -> None:
    fits.require(fit_id, property_id)
    validos = [k for k, _ in FIT_FEEDBACK]
    if value and value not in validos:
        raise ValueError(f"valoración desconocida: {value}")
    store.ex("UPDATE fit_requests SET lab_feedback=?, updated_at=? WHERE fit_id=?",
             (value or None, store.now(), fit_id))


def feedback_export() -> List[Dict]:
    """§17 — el feedback estructurado, listo para analizar después. No entrena nada hoy."""
    out = []
    for p in store.q("SELECT property_id, title, lab_feedback FROM properties"):
        pid = p["property_id"]
        out.append({"property_id": pid, "title": p["title"], "feedback": p["lab_feedback"],
                    "notes": [{"scope": n["scope"], "body": n["body"], "at": n["created_at"]}
                              for n in notes(pid)],
                    "fits": [{"fit_id": f["fit_id"], "label": f["label"],
                              "feedback": f.get("lab_feedback")}
                             for f in fits.list_for(pid, include_archived=True)],
                    "staging": [{"attempt_id": a["attempt_id"], "provider": a["provider"],
                                 "fidelity": a["fidelity_status"], "quality": a["quality_score"],
                                 "review": a["review_status"],
                                 "reasons": a["failure_reasons_list"]}
                                for a in staging.list_for(pid, include_benchmark=True)]})
    return out


# =================================================================================================
# E33 — PACK 1 y PACK 2 en lenguaje de producto.
#
# Todo lo de abajo traduce el pipeline real a tres o cuatro filas que un corredor entiende. No hay
# lógica nueva: hay una capa que decide qué mostrar y qué esconder. Los estados técnicos
# (SEARCH_EXHAUSTED, NEEDS_CONFIRMATION, STAGING_PROVIDER_NOT_APPROVED) no cruzan esta frontera;
# se traducen a "Necesita revisión", "Preparando" o "No pudimos generarlo" y el código original
# queda disponible en el detalle técnico para quien lo necesite.
# =================================================================================================
PENDIENTE, PREPARANDO, REVISION, LISTO, FALLO = (
    "Pendiente", "Preparando", "Necesita revisión", "Listo", "No pudimos generarlo")


def _paso(nombre, estado, detalle="", accion=None, ruta=None, tecnico=""):
    return {"name": nombre, "state": estado, "detail": detalle, "action": accion, "route": ruta,
            "done": estado == LISTO, "tech": tecnico}


def pack1(property_id: str) -> Dict:
    """PACK 1 — PUBLICACIÓN. Plano comercial, un layout tipo y una imagen ambientada.

    Nunca tres layouts, nunca prospectos, nunca proveedor: eso es Pack 2 o backstage."""
    t = floorplan.technical_state(property_id)
    plano_orig = assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL)
    plano_com = assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL)
    layouts = packs.layout_assets(property_id)
    base = fits.base_of(property_id)
    st = staging.state(property_id)
    hero = staging.hero(property_id)
    pack = packs.get(property_id)
    listo = packs.readiness(property_id)

    # ---- plano comercial
    if plano_com:
        p_plano = _paso("Plano comercial", LISTO, "listo para presentar", tecnico=t["case_status"])
    elif not plano_orig:
        p_plano = _paso("Plano comercial", PENDIENTE, "falta subir el plano")
    elif t["case_status"] in ("INPUT_NOT_READY", "FAILED"):
        p_plano = _paso("Plano comercial", FALLO,
                        "el plano que subiste no se puede leer en esta versión",
                        tecnico=t["case_status"])
    elif (units.get(property_id) or {}).get("status") == units.NEEDS_INTERNAL_REVIEW:
        # E35 §16 — cuando lo único que falta es saber cuál de las oficinas de la lámina es ésta,
        # el paso tiene que decir ESO. Mandar a "revisar el plano" era ofrecerle a alguien la
        # herramienta técnica para un problema que se resuelve con un clic más arriba en la
        # misma página.
        p_plano = _paso("Plano comercial", REVISION,
                        "necesitamos que nos indiques cuál es la oficina",
                        accion="Elegir la oficina", ruta="oficina", tecnico=t["case_status"])
    elif not t["ready"]:
        inf = ingest.get(property_id) or {}
        p_plano = _paso("Plano comercial", REVISION,
                        (inf or {}).get("review_reason") or "necesitamos revisar el plano",
                        accion="Revisar plano", ruta="revisar", tecnico=t["case_status"])
    else:
        p_plano = _paso("Plano comercial", PREPARANDO, "listo para generar")

    # ---- layout tipo
    corrida = fits.latest_run(base["fit_id"]) if base else None
    estado_run = (corrida or {}).get("run", {}).get("status")
    if layouts:
        p_layout = _paso("Layout tipo", LISTO, "una distribución representativa")
    elif not (base and base["headcount"]):
        p_layout = _paso("Layout tipo", PENDIENTE, "falta decirnos cuántas personas trabajarían acá")
    elif estado_run in ("QUEUED", "RUNNING"):
        p_layout = _paso("Layout tipo", PREPARANDO, "generando la distribución", tecnico=estado_run)
    elif corrida and not fits.fit_alternatives(base["fit_id"]):
        p_layout = _paso("Layout tipo", FALLO,
                         "no encontramos una distribución válida para ese programa en esta planta",
                         tecnico="SEARCH_EXHAUSTED")
    elif not t["ready"]:
        p_layout = _paso("Layout tipo", PENDIENTE, "primero hay que preparar el plano")
    else:
        p_layout = _paso("Layout tipo", PREPARANDO, "listo para generar")

    # ---- ambientación
    mapa = {"APPROVED": (LISTO, "imagen ambientada de tu foto principal"),
            "STAGING_REVIEW": (PREPARANDO, "revisando la imagen"),
            "GENERATING": (PREPARANDO, "generando la imagen"),
            "NEEDS_STAGING": (PREPARANDO, "listo para generar"),
            "NOT_REQUESTED": (PENDIENTE, "elegí cuál de tus fotos ambientamos"),
            "STAGING_PROVIDER_NOT_APPROVED": (PENDIENTE, "pendiente de validar proveedor"),
            "STAGING_UNAVAILABLE": (PENDIENTE, "pendiente de validar proveedor"),
            "STAGING_NEEDS_MANUAL_REVIEW": (REVISION, "necesita que lo miremos")}
    e, d = mapa.get(st["state"], (PENDIENTE, st["reason"]))
    if e == PENDIENTE and not hero and assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL):
        d = "elegí cuál de tus fotos ambientamos"
    p_staging = _paso("Ambientación", e, d, tecnico=st["state"])

    pasos = [p_plano, p_layout, p_staging]
    return {
        "steps": pasos,
        "ready": all(p["done"] for p in pasos),
        "any": any(p["done"] for p in pasos),
        "can_run": bool(plano_orig) and not all(p["done"] for p in pasos),
        "floorplan": plano_com, "layout": layouts[0] if layouts else None,
        "staged": staging.approved_hero(property_id),
        "before_after": (packs.before_after_assets(property_id) or [None])[0],
        "hero": hero,
        "photos": assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL),
        "original": plano_orig,
        "headcount": (base or {}).get("headcount"),
        "pack": pack, "downloadable": bool(pack and pack["export_name"]),
        "missing": listo["missing"], "readiness": listo["state"],
    }


def pack1_advance(property_id: str) -> Dict:
    """«GENERAR PACK 1»: hace TODO lo que se pueda hacer solo y se detiene donde hace falta una
    persona. No falla ruidosamente en el medio: devuelve lo que hizo y lo que quedó pendiente.

    E34 — la diferencia con E33 es que ya no manda a nadie a medir la escala ni a marcar el acceso.
    Analiza la planta sin preguntar nada (`ingest.auto_prepare`), deja registrado qué dedujo y con
    cuánta confianza, y sólo pide una persona cuando el motor mismo dice que le falta algo."""
    hecho: List[str] = []
    p = properties.require(property_id)
    # La foto principal no depende del plano: si hay fotos, se elige una ya, aunque la geometría
    # todavía necesite una vuelta. Atarla al avance del plano la dejaba sin elegir justo en los
    # casos en que el usuario más necesita ver que algo pasó.
    if staging.hero(property_id) is None:
        elegida = propose_hero(property_id)
        if elegida:
            staging.set_hero(property_id, elegida["asset_id"])
            hecho.append("elegimos una foto principal")
    if not assets.first_of_kind(property_id, assets.FLOORPLAN_ORIGINAL):
        return {"done": hecho, "blocked": "Subí el plano de la propiedad."}
    if not p["floorplan_case_id"]:
        floorplan.ensure_case(property_id)
        hecho.append("preparamos el plano")
    t = floorplan.technical_state(property_id)
    case_id = properties.require(property_id)["floorplan_case_id"]
    if not t["ready"] and intake.load_floorplate(case_id) is None:
        # el motor todavía no miró esta planta: que la mire, sin preguntarle nada al usuario
        ingest.auto_prepare(property_id)
        hecho.append("analizamos el plano")
        t = floorplan.technical_state(property_id)
    if not t["ready"]:
        inf = ingest.get(property_id) or {}
        # E35 §16 — si lo único que falta es saber cuál de las oficinas de la lámina es ésta, no se
        # manda a nadie a la herramienta técnica: se pregunta acá mismo, con la planta a la vista.
        sel = units.get(property_id)
        if sel and sel["status"] == units.NEEDS_INTERNAL_REVIEW:
            return {"done": hecho, "blocked": "Necesitamos que nos indiques cuál es la oficina.",
                    "action": "elegir_oficina", "inference": inf, "units": sel}
        return {"done": hecho,
                "blocked": "Necesitamos revisar el plano antes de continuar.",
                "action": "revisar", "inference": inf}
    if not assets.first_of_kind(property_id, assets.FLOORPLAN_COMMERCIAL):
        floorplan.publish_commercial_floorplan(property_id)
        hecho.append("generamos el plano comercial")
    base = fits.base_of(property_id)
    if not (base and base["headcount"]):
        return {"done": hecho, "blocked": "Decinos cuántas personas trabajarían acá.",
                "action": "programa"}
    if not packs.layout_assets(property_id):
        corrida = fits.latest_run(base["fit_id"])
        estado = (corrida or {}).get("run", {}).get("status")
        if corrida and fits.fit_alternatives(base["fit_id"]):
            floorplan.publish_layouts(property_id, fit_id=base["fit_id"])
            hecho.append("publicamos el layout tipo")
        elif estado not in ("QUEUED", "RUNNING"):
            fits.generate(base["fit_id"])
            hecho.append("empezamos a generar el layout")
    st = staging.state(property_id)
    if st["state"] == "NEEDS_STAGING" and st["hero_asset_id"]:
        aid = staging.create_attempt(property_id, st["hero_asset_id"],
                                     (base or {}).get("visual_style") or presets.DEFAULT_STYLE)
        staging.enqueue(aid)
        hecho.append("empezamos a ambientar la foto")
    properties.touch(property_id)
    return {"done": hecho, "blocked": None}


def propose_hero(property_id: str) -> Optional[Dict]:
    """§10 — propone una foto principal sin pedirla.

    Heurística deliberadamente simple: la foto de mayor superficie en píxeles entre las que tienen
    una resolución decente, sin repetir un archivo idéntico. No hace falta visión por computador
    para esto, y construirla sólo para elegir una foto sería gastar en el lugar equivocado. Si
    ninguna destaca, la primera válida. El usuario puede cambiarla siempre."""
    fotos = assets.list_of_kind(property_id, assets.PHOTO_ORIGINAL)
    if not fotos:
        return None
    vistos, unicas = set(), []
    for f in fotos:
        if f["sha256"] in vistos:
            continue
        vistos.add(f["sha256"])
        unicas.append(f)
    con_medida = [f for f in unicas if (f["width_px"] or 0) * (f["height_px"] or 0) > 0]
    if not con_medida:
        return unicas[0]
    return max(con_medida, key=lambda f: f["width_px"] * f["height_px"])


def enable_pack2(property_id: str) -> None:
    """En el laboratorio, pedir una propuesta implica el producto que la permite.

    §21 — el LAB existe para evaluar el producto, no para que Joaquín piense en ONE_OFF vs Pro.
    En el CLIENTE eso sigue siendo una decisión comercial con su pantalla y su tope, y los tests de
    E32.2 la protegen. Acá se ajusta el producto simulado de ESTA propiedad y de ninguna otra."""
    from . import entitlements                                # noqa: PLC0415
    if entitlements.product_of(property_id) != "PRO":
        entitlements.set_product(property_id, "PRO")


def pack2_list(property_id: str) -> List[Dict]:
    """Las propuestas de esta propiedad, la más nueva primero, en lenguaje de producto."""
    out = []
    for f in fits.list_for(property_id, include_base=False):
        fv = fits.view(f["fit_id"], property_id)
        r = fv.get("run") or {}
        alts = fv["alternatives"]
        con_layout = [a for a in alts if a["status"] == "FIT"]
        if r.get("status") in ("QUEUED", "RUNNING"):
            estado, detalle = PREPARANDO, "generando las alternativas"
        elif con_layout:
            estado, detalle = LISTO, f"{len(con_layout)} alternativa(s)"
        elif alts:
            estado, detalle = (FALLO,
                               "no encontramos distribuciones válidas para ese programa en esta planta")
        else:
            estado, detalle = PENDIENTE, "falta generar"
        out.append({"fit": f, "view": fv, "state": estado, "detail": detalle,
                    "run": r or None, "alternatives": alts, "fit_alternatives": con_layout,
                    "pack": packs.get(property_id, f["fit_id"])})
    return out


def property_view(property_id: str) -> Dict:
    """Todo lo que la ÚNICA página de una propiedad necesita, ya traducido."""
    from . import reviews                                     # noqa: PLC0415
    v = properties.view(property_id)
    p1 = pack1(property_id)
    hist = reviews.history(property_id)
    # Lookup por artefacto para la plantilla. Se arma acá y no con un bucle en Jinja porque un
    # `{% set %}` dentro de un `{% for %}` NO sale del bucle: la calificación guardada se veía en
    # la base y no en pantalla. Verlo exigió abrir el navegador; ningún test de ruta lo habría dicho.
    clave = lambda t, a, f: f"{t}|{a or ''}|{f or ''}"        # noqa: E731
    return {"v": v, "p": v["property"], "pack1": p1, "pack2": pack2_list(property_id),
            "inference": ingest.get(property_id),
            # E35 §6 — la pregunta de la unidad viaja con la página, no con una pantalla aparte.
            "units": units.get(property_id),
            "reviews": hist,
            "revs": {clave(r["artifact_type"], r["artifact_id"], r["fit_id"]): r for r in hist},
            "presets": presets.CATALOG, "styles": presets.VISUAL_STYLES,
            "preset_default": presets.DEFAULT_PRESET, "style_default": presets.DEFAULT_STYLE,
            "notes": notes(property_id)}


def simple_rows() -> List[Dict]:
    """Las tarjetas de la portada. Sin case_id, sin run_id, sin estado técnico."""
    out = []
    for v in properties.listing():
        pid = v["property"]["property_id"]
        p1 = pack1(pid)
        props = pack2_list(pid)
        listas = sum(1 for x in props if x["state"] == LISTO)
        out.append({
            "p": v["property"],
            "pack1": (LISTO if p1["ready"] else (PREPARANDO if p1["any"] else PENDIENTE)),
            "pack1_done": sum(1 for s in p1["steps"] if s["done"]), "pack1_total": len(p1["steps"]),
            "pack2": (f"{listas} propuesta(s)" if listas else
                      ("generando" if any(x["state"] == PREPARANDO for x in props) else "ninguna")),
            "photos": len(p1["photos"]),
            "cover": p1["floorplan"] or p1["layout"] or p1["original"],
        })
    return out
