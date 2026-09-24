"""E17.1 §4/§5 — LA REVISIÓN HUMANA DEL DIAGNÓSTICO, y el tablero del dogfood de 20 avisos.

=================================================================================================
Qué pregunta contesta esta muestra
=================================================================================================
Una sola, y conviene tenerla escrita donde se guarda el dato:

    ¿En cuántas publicaciones encontramos una mejora concreta que Escalímetro realmente pueda
    producir y que justifique contactar al corredor?

Por eso no hay un score nuevo. Hay tres juicios cerrados y un comentario:

    DIAGNÓSTICO      ¿lo que dijimos del aviso era cierto?      ACERTADO · PARCIAL · EQUIVOCADO
    OPORTUNIDAD      ¿hay algo que nosotros podamos resolver?   HAY_ALGO · NO_HAY
    CONTACTAR        ¿vale la pena llamar a este corredor?      SÍ · NO

Están deliberadamente separados porque pueden discrepar, y esa discrepancia es la información más
valiosa de la muestra. Un diagnóstico ACERTADO sin oportunidad significa que el instrumento
funciona y el negocio no está ahí. Un diagnóstico PARCIAL con oportunidad clara significa lo
contrario: hay negocio y el instrumento todavía no lo ve bien. Colapsarlos en un número haría
imposible distinguir esos dos mundos.

El juicio se guarda contra el INFORME sobre el que se emitió (`report_id`): si después
reanalizamos el aviso y el diagnóstico cambia, la revisión anterior sigue siendo sobre lo que esa
persona realmente vio.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ... import store
from . import analyzer, interventions as iv, listings

ACERTADO, PARCIAL, EQUIVOCADO = "ACERTADO", "PARCIAL", "EQUIVOCADO"
DIAGNOSES = (ACERTADO, PARCIAL, EQUIVOCADO)
DIAGNOSIS_LABEL = {ACERTADO: "Acertado", PARCIAL: "Parcial", EQUIVOCADO: "Equivocado"}

HAY_OPORTUNIDAD = "HAY_ALGO_QUE_ESCALIMETRO_PUEDE_RESOLVER"
SIN_OPORTUNIDAD = "NO_HAY_OPORTUNIDAD_CLARA"
OPPORTUNITIES = (HAY_OPORTUNIDAD, SIN_OPORTUNIDAD)
OPPORTUNITY_LABEL = {HAY_OPORTUNIDAD: "Hay algo que podemos resolver",
                     SIN_OPORTUNIDAD: "No hay oportunidad clara"}

SI, NO = "SI", "NO"
CONTACT = (SI, NO)
CONTACT_LABEL = {SI: "Sí", NO: "No"}

#: El tamaño de la muestra del dogfood. No es una meta que haya que gamificar: es cuándo la
#: pregunta de arriba se puede empezar a contestar.
TARGET = 20


class ReviewError(ValueError):
    pass


def save(listing_id: str, *, diagnosis: Optional[str] = None,
         opportunity: Optional[str] = None, worth_contacting: Optional[str] = None,
         comment: str = "") -> None:
    """Guarda o actualiza el juicio. Los tres campos son independientes: se puede responder uno y
    volver después, porque obligar a contestar los tres de una vez haría que se conteste cualquier
    cosa en el que no se tenga opinión."""
    listings.require(listing_id)
    if diagnosis and diagnosis not in DIAGNOSES:
        raise ReviewError(f"diagnóstico desconocido: {diagnosis}")
    if opportunity and opportunity not in OPPORTUNITIES:
        raise ReviewError(f"oportunidad desconocida: {opportunity}")
    if worth_contacting and worth_contacting not in CONTACT:
        raise ReviewError(f"respuesta desconocida: {worth_contacting}")
    r = analyzer.latest(listing_id)
    prev = get(listing_id) or {}
    store.ex("INSERT INTO listing_reviews(listing_id, diagnosis, opportunity, worth_contacting, "
             "comment, report_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?) "
             "ON CONFLICT(listing_id) DO UPDATE SET diagnosis=excluded.diagnosis, "
             "opportunity=excluded.opportunity, worth_contacting=excluded.worth_contacting, "
             "comment=excluded.comment, report_id=excluded.report_id, "
             "updated_at=excluded.updated_at",
             (listing_id, diagnosis or prev.get("diagnosis"),
              opportunity or prev.get("opportunity"),
              worth_contacting or prev.get("worth_contacting"),
              (comment or prev.get("comment") or "").strip()[:1000],
              (r or {}).get("report_id"), prev.get("created_at") or store.now(), store.now()))


def get(listing_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM listing_reviews WHERE listing_id=?", (listing_id,))
    return dict(r) if r else None


def complete(listing_id: str) -> bool:
    d = get(listing_id) or {}
    return all(d.get(k) for k in ("diagnosis", "opportunity", "worth_contacting"))


def dashboard() -> Dict:
    """El tablero del dogfood. Secundario a propósito: el producto es el informe, esto es el
    instrumento con el que decidimos si el producto sirve."""
    avisos = listings.listing_rows(limit=500)
    filas = []
    for l in avisos:
        rev = get(l["listing_id"]) or {}
        rep = analyzer.latest(l["listing_id"])
        resolubles = [f for f in (rep or {}).get("resolvable", [])]
        filas.append({
            "listing_id": l["listing_id"], "title": l["title"] or "Sin título",
            "score": (rep or {}).get("score"),
            "url_ingest_status": l.get("url_ingest_status"),
            "url_ingest_reason": l.get("url_ingest_reason"),
            "fields": l.get("fields_extracted_count") or 0,
            "photos": l.get("photos_extracted_count") or 0,
            "floorplans": l.get("floorplans_detected_count") or 0,
            "domain": (l.get("source_url") or "").split("/")[2] if l.get("source_url") else None,
            "commercial_state": (rep or {}).get("commercial_state"),
            "signals": (rep or {}).get("signals") or [],
            "resolvable": len(resolubles),
            "deliverable_today": sum(1 for f in resolubles if f["deliverable_today"]),
            "interventions": sorted({f["intervention"] for f in resolubles if f["intervention"]}),
            "diagnosis": rev.get("diagnosis"), "opportunity": rev.get("opportunity"),
            "worth_contacting": rev.get("worth_contacting"),
            "reviewed": complete(l["listing_id"]),
        })
    revisados = [f for f in filas if f["reviewed"]]
    por_diag = {d: sum(1 for f in revisados if f["diagnosis"] == d) for d in DIAGNOSES}
    por_inter: Dict[str, int] = {}
    for f in filas:
        for i in f["interventions"]:
            por_inter[i] = por_inter.get(i, 0) + 1
    con_oportunidad = sum(1 for f in revisados if f["opportunity"] == HAY_OPORTUNIDAD)
    contactar = sum(1 for f in revisados if f["worth_contacting"] == SI)
    # E17.2 §15 — las dos preguntas reales de la muestra, cada una con su bloque de métricas:
    #   1) ¿podemos analizar una URL casi solos?
    #   2) ¿hay oportunidad comercial aun cuando las fotos ya son buenas?
    con_url = [f for f in filas if f["url_ingest_status"]]
    por_estado = {e: sum(1 for f in con_url if f["url_ingest_status"] == e)
                  for e in ("SUCCESS", "PARTIAL", "FAILED")}
    fotos = [f["photos"] for f in con_url if f["url_ingest_status"] != "FAILED"]
    from .analyzer import (ALREADY_STRONG, RECOMMENDATION_ONLY, RESOLVABLE_OPPORTUNITY,
                           STATE_LABEL, VISUAL_STRONG)          # noqa: PLC0415
    estados = {e: sum(1 for f in filas if f["commercial_state"] == e)
               for e in (RESOLVABLE_OPPORTUNITY, RECOMMENDATION_ONLY, ALREADY_STRONG)}
    fuertes = sum(1 for f in filas if VISUAL_STRONG in f["signals"])
    analizados = len(filas) or 1
    ingest = {
        "with_url": len(con_url), "by_status": por_estado,
        "no_manual_pct": (round(100.0 * por_estado["SUCCESS"] / len(con_url), 1)
                          if con_url else None),
        "avg_photos": round(sum(fotos) / len(fotos), 1) if fotos else None,
        "with_floorplan": sum(1 for f in con_url if f["floorplans"]),
        "with_floorplan_pct": (round(100.0 * sum(1 for f in con_url if f["floorplans"])
                                     / len(con_url), 1) if con_url else None),
        "failures": {f["url_ingest_reason"]: sum(
            1 for g in con_url if g["url_ingest_reason"] == f["url_ingest_reason"])
            for f in con_url if f["url_ingest_status"] == "FAILED"},
        "domains": sorted({f["domain"] for f in con_url if f["domain"]}),
    }
    visual = {"strong": fuertes, "strong_pct": round(100.0 * fuertes / analizados, 1),
              "with_defect": analizados - fuertes,
              "with_defect_pct": round(100.0 * (analizados - fuertes) / analizados, 1)}
    comercial = {"by_state": estados, "state_labels": STATE_LABEL,
                 "pct": {k: round(100.0 * v / analizados, 1) for k, v in estados.items()}}
    return {
        "listings": len(filas), "target": TARGET, "reviewed": len(revisados),
        "by_diagnosis": por_diag, "diagnosis_labels": DIAGNOSIS_LABEL,
        "with_opportunity": con_oportunidad,
        "with_opportunity_pct": (round(100.0 * con_oportunidad / len(revisados), 1)
                                 if revisados else None),
        "worth_contacting": contactar,
        "worth_contacting_pct": (round(100.0 * contactar / len(revisados), 1)
                                 if revisados else None),
        # Lo que el sistema PROPUSO, que no es lo mismo que lo que un humano validó. Las dos
        # columnas juntas son las que dicen si el instrumento está viendo lo que hay.
        "ingest": ingest, "visual": visual, "commercial": comercial,
        "by_intervention": {k: por_inter[k] for k in sorted(por_inter)},
        "intervention_labels": {k: iv.label(k) for k in iv.TYPES},
        "support_labels": {k: iv.support_label(k) for k in iv.TYPES},
        "proposed_any": sum(1 for f in filas if f["resolvable"]),
        "deliverable_today": sum(1 for f in filas if f["deliverable_today"]),
        "rows": filas,
    }
