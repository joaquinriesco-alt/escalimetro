"""E35 §17 — CUÁNTAS VECES EL FLUJO "AUTOMÁTICO" NECESITÓ DE VERDAD A UNA PERSONA.

Un ingest sin fricción no se demuestra con una captura de pantalla: se demuestra contando. Cada vez
que alguien tiene que intervenir —elegir la unidad, fijar una escala, corregir geometría, rehacer
una ambientación— queda una fila con su motivo. Después se puede responder la única pregunta que
importa para saber si esto mejora: *de las últimas N propiedades, ¿en cuántas hubo que meter mano,
y en qué?*

Se registra el HECHO, no la intención: se llama cuando la intervención ya ocurrió. Y se muestra
sólo en Ajustes/Evaluaciones — a nadie que esté publicando una oficina le sirve ver este contador.
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .. import store

UNIT_SELECTION = "UNIT_SELECTION"
SCALE = "SCALE"
GEOMETRY = "GEOMETRY"
#: E36 §14 — el acceso principal va aparte de la geometría: E35 midió que es el componente con
#: el falso acepto confiado, y meterlo en la misma bolsa taparía justo lo que hay que vigilar.
ACCESS = "ACCESS"
STAGING = "STAGING"
OTHER = "OTHER"
REASONS = (UNIT_SELECTION, SCALE, GEOMETRY, ACCESS, STAGING, OTHER)

#: Cómo se llama cada motivo cuando hay que enseñarlo.
LABELS = {UNIT_SELECTION: "elegir la oficina en la lámina", SCALE: "fijar la escala",
          GEOMETRY: "corregir la geometría", ACCESS: "corregir el acceso principal",
          STAGING: "rehacer la ambientación", OTHER: "otra intervención"}


class InterventionError(ValueError):
    """Motivo fuera del vocabulario."""


def record(property_id: str, reason: str, detail: str = "") -> str:
    """Anota una intervención humana ya ocurrida."""
    if reason not in REASONS:
        raise InterventionError(f"motivo desconocido: {reason}. Admitidos: {', '.join(REASONS)}")
    iid = "iv_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO manual_interventions(intervention_id, property_id, reason, detail, "
             "created_at) VALUES (?,?,?,?,?)", (iid, property_id, reason, detail or "", store.now()))
    return iid


def count(property_id: str) -> int:
    r = store.q1("SELECT COUNT(*) n FROM manual_interventions WHERE property_id=?", (property_id,))
    return int(r["n"]) if r else 0


def by_reason(property_id: str) -> Dict[str, int]:
    """Cuántas por motivo. Los motivos sin filas valen 0 y no se omiten: un cero es información."""
    out = {r: 0 for r in REASONS}
    for row in store.q("SELECT reason, COUNT(*) n FROM manual_interventions WHERE property_id=? "
                       "GROUP BY reason", (property_id,)):
        if row["reason"] in out:
            out[row["reason"]] = int(row["n"])
    return out


def history(property_id: str, limit: int = 50) -> List[Dict]:
    return [dict(r) for r in store.q(
        "SELECT * FROM manual_interventions WHERE property_id=? ORDER BY created_at DESC LIMIT ?",
        (property_id, limit))]


def summary(limit: Optional[int] = None) -> Dict:
    """El agregado que se mira en Ajustes: cuántas propiedades pasaron solas y cuántas no."""
    props = [r["property_id"] for r in store.q("SELECT property_id FROM properties")]
    if limit:
        props = props[:limit]
    por_motivo = {r: 0 for r in REASONS}
    con_intervencion = 0
    for pid in props:
        c = by_reason(pid)
        if sum(c.values()):
            con_intervencion += 1
        for k, v in c.items():
            por_motivo[k] += v
    return {"properties": len(props), "with_intervention": con_intervencion,
            "fully_automatic": len(props) - con_intervencion, "by_reason": por_motivo,
            "labels": LABELS}
