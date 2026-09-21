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

from .. import store
from . import assets, fits, floorplan, packs, pilot, presets, properties, staging

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
        if staging.state(pid)["state"] in ("NEEDS_STAGING", "STAGING_REVIEW",
                                           "STAGING_NEEDS_MANUAL_REVIEW"):
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
