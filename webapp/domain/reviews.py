"""E33 §12 — EVALUACIONES DE PRODUCTO: lo único que el laboratorio existe para capturar.

Cuatro valores y nada más: **EXCELENTE · BUENO · MALO · PÉSIMO**. Ni estrellas, ni 1–10, ni
deslizadores. Una escala de diez puntos parece más información y es menos: nadie distingue un 6 de
un 7 de forma reproducible, y después no se puede agrupar. Cuatro categorías se eligen rápido y se
cuentan sin ambigüedad.

Dos reglas que gobiernan este módulo:

1. **Calificar nunca es obligatorio.** Ni todos los artefactos, ni los motivos, ni el comentario.
   Una evaluación que exige cinco campos no se completa, y un laboratorio sin datos no sirve.

2. **La procedencia se guarda siempre y no se muestra nunca.** Cada evaluación se ata al motor, al
   sha del artefacto, al proveedor y a la corrida que lo produjo. El usuario no ve nada de eso —§16:
   "El usuario NO ve estos campos técnicos"— pero sin ello «el layout quedó mal» es una opinión
   sobre nada: no se sabe qué versión hay que arreglar.
"""
from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional

from .. import store

#: Las cuatro. En este orden, que es el que va en pantalla.
RATINGS = ("EXCELENTE", "BUENO", "MALO", "PESIMO")
RATING_LABEL = {"EXCELENTE": "Excelente", "BUENO": "Bueno", "MALO": "Malo", "PESIMO": "Pésimo"}
NEGATIVE = ("MALO", "PESIMO")

#: Qué se puede calificar. `PACK1`/`PACK2` son el resultado en conjunto.
ARTIFACTS = ("PLANO", "LAYOUT", "STAGING", "PACK1", "ALTERNATIVA", "PACK2")
ARTIFACT_LABEL = {"PLANO": "Plano comercial", "LAYOUT": "Layout tipo", "STAGING": "Ambientación",
                  "PACK1": "Pack 1", "ALTERNATIVA": "Alternativa", "PACK2": "Propuesta"}

#: §14 — qué falló, por tipo de artefacto. Listas cerradas para poder agrupar después; "Otro"
#: existe para no forzar una categoría equivocada.
FAIL_TAGS = {
    "LAYOUT": ["Distribución", "Circulación", "Densidad", "Luz", "Programa",
               "Se ve poco realista", "Otro"],
    "ALTERNATIVA": ["Distribución", "Circulación", "Densidad", "Luz", "Programa",
                    "Se ve poco realista", "Otro"],
    "STAGING": ["Cambió arquitectura", "Mobiliario", "Escala", "Estilo", "Poco realista", "Otro"],
    "PLANO": ["Geometría", "Legibilidad", "Escala", "Elementos faltantes", "Otro"],
    "PACK1": ["Incompleto", "Presentación", "No lo mandaría", "Otro"],
    "PACK2": ["Incompleto", "Presentación", "No lo mandaría", "Otro"],
}
#: §15 — qué funcionó. Una sola lista: no hace falta más granularidad para lo bueno.
GOOD_TAGS = ["Distribución", "Claridad", "Presentación", "Realismo", "Otro"]


def tags_for(artifact_type: str, rating: str) -> List[str]:
    if rating in NEGATIVE:
        return FAIL_TAGS.get(artifact_type, ["Otro"])
    return GOOD_TAGS


def save(property_id: str, artifact_type: str, rating: str, artifact_id: Optional[str] = None,
         fit_id: Optional[str] = None, reason_tags: Optional[List[str]] = None,
         comment: str = "", provenance: Optional[Dict] = None, author: str = "") -> str:
    """Guarda una evaluación. `provenance` es lo que el artefacto sepa de sí mismo; lo que falte
    queda en None, sin inventarse."""
    if rating not in RATINGS:
        raise ValueError(f"calificación desconocida: {rating}")
    if artifact_type not in ARTIFACTS:
        raise ValueError(f"tipo de artefacto desconocido: {artifact_type}")
    validas = set(tags_for(artifact_type, rating))
    tags = [t for t in (reason_tags or []) if t in validas]
    pr = provenance or {}
    rid = "rv_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO product_reviews(review_id, property_id, artifact_type, artifact_id, "
             "fit_id, rating, reason_tags, comment, engine_version, artifact_sha256, provider, "
             "model, run_id, author, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (rid, property_id, artifact_type, artifact_id, fit_id, rating,
              json.dumps(tags, ensure_ascii=False), (comment or "").strip()[:2000],
              pr.get("engine_version"), pr.get("artifact_sha256"), pr.get("provider"),
              pr.get("model"), pr.get("run_id"), (author or "")[:80], store.now()))
    return rid


def _row(r) -> Dict:
    d = dict(r)
    d["tags"] = store.js(d["reason_tags"], []) or []
    d["rating_label"] = RATING_LABEL.get(d["rating"], d["rating"])
    d["artifact_label"] = ARTIFACT_LABEL.get(d["artifact_type"], d["artifact_type"])
    return d


def latest(property_id: str, artifact_type: str, artifact_id: Optional[str] = None,
           fit_id: Optional[str] = None) -> Optional[Dict]:
    """La última evaluación de ese artefacto. Recalificar es volver a guardar: se conserva la
    historia y manda la más reciente."""
    sql = ("SELECT * FROM product_reviews WHERE property_id=? AND artifact_type=?")
    args: List = [property_id, artifact_type]
    if artifact_id is not None:
        sql += " AND artifact_id=?"; args.append(artifact_id)
    if fit_id is None:
        sql += " AND fit_id IS NULL"
    else:
        sql += " AND fit_id=?"; args.append(fit_id)
    sql += " ORDER BY created_at DESC LIMIT 1"
    r = store.q1(sql, tuple(args))
    return _row(r) if r else None


def for_property(property_id: str) -> List[Dict]:
    return [_row(r) for r in store.q(
        "SELECT * FROM product_reviews WHERE property_id=? ORDER BY created_at DESC",
        (property_id,))]


def history(property_id: str) -> List[Dict]:
    """§17 — la lista que se ve al final de la propiedad: una línea por artefacto, la más nueva."""
    vistos, out = set(), []
    for r in for_property(property_id):
        clave = (r["artifact_type"], r["artifact_id"], r["fit_id"])
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append(r)
    return out


def stats() -> Dict:
    """§18 — el resumen de aprendizaje. Cuentas, no BI."""
    filas = [_row(r) for r in store.q("SELECT * FROM product_reviews")]
    por_rating = {k: 0 for k in RATINGS}
    por_tipo: Dict[str, Dict[str, int]] = {}
    motivos: Dict[str, int] = {}
    for f in filas:
        por_rating[f["rating"]] = por_rating.get(f["rating"], 0) + 1
        t = por_tipo.setdefault(f["artifact_type"], {k: 0 for k in RATINGS})
        t[f["rating"]] += 1
        if f["rating"] in NEGATIVE:
            for tag in f["tags"]:
                motivos[tag] = motivos.get(tag, 0) + 1
    total = len(filas)
    return {
        "total": total,
        "properties_rated": len({f["property_id"] for f in filas}),
        "by_rating": por_rating,
        "pct": {k: (round(100 * v / total) if total else 0) for k, v in por_rating.items()},
        "by_artifact": {k: dict(v, total=sum(v.values())) for k, v in por_tipo.items()},
        "top_failures": dict(sorted(motivos.items(), key=lambda kv: -kv[1])[:8]),
        "labels": RATING_LABEL, "artifact_labels": ARTIFACT_LABEL,
    }
