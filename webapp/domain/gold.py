"""E36 §8/§9 — LA ETIQUETA DE VERDAD SOBRE LA GEOMETRÍA, QUE NO ES LA CALIFICACIÓN DEL PRODUCTO.

=================================================================================================
Por qué dos datasets y no uno
=================================================================================================
E33 ya pregunta «¿cómo quedó?» con Excelente/Bueno/Malo/Pésimo. Es tentador reutilizar eso para
calibrar: si el Pack quedó bueno, la geometría estaría bien. **Es falso y peligroso.**

Un Pack 1 puede quedar «Bueno» con el núcleo mal recortado —se ve bien, el layout entra igual— y
puede quedar «Malo» con la geometría perfecta porque el estilo visual no gustó. Usar el juicio de
producto como prueba de corrección geométrica metería ruido justo en la medición que E35 demostró
que más falta hace: la del acceso principal, que acierta una de dos.

Por eso hay dos vocabularios y dos tablas:

    PRODUCT REVIEW   EXCELENTE · BUENO · MALO · PÉSIMO      → ¿sirve como entregable?
    GEOMETRY GOLD    CORRECTO · INCORRECTO · INCOMPLETO · NO_APLICA → ¿el motor leyó bien el plano?

=================================================================================================
Por qué INCOMPLETO es su propio veredicto
=================================================================================================
Que el motor se equivoque y que se quede corto no son el mismo error. En la 403 un humano agregó
seis pilares que el motor no vio: los nueve que sí detectó estaban bien. Contar eso como
«incorrecto» diría que el detector de pilares falla cuando lo que falla es su recall, y llevaría a
subir un umbral que no tiene nada que ver. `INCOMPLETO` mantiene separadas las dos cosas.

`NO_APLICA` también hace falta y no es relleno: una planta sin núcleo —el caso RES— no tiene
núcleo mal detectado, no tiene núcleo. Forzar CORRECTO/INCORRECTO ahí sería fabricar una muestra.

=================================================================================================
Cuándo una propiedad sirve para calibrar
=================================================================================================
`GOLD_REVIEW_COMPLETE` no exige etiquetar los siete componentes: exige juicio humano sobre los que
el motor efectivamente decidió. Un componente que el motor no emitió no se puede juzgar, y pedirlo
sólo haría el flujo pesado (§8) sin agregar evidencia.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .. import intake, store

#: Los componentes sobre los que tiene sentido emitir un juicio de verdad. Son los mismos que el
#: motor decide, más la unidad, que es la decisión previa a todas (E35 §8).
UNIT = "unit"
PERIMETER = "perimeter"
CORE = "core"
PRIMARY_ENTRANCE = "primary_entrance"
COLUMNS = "columns"
DAYLIGHT = "daylight"
SCALE = "scale"
COMPONENTS = (UNIT, PERIMETER, CORE, PRIMARY_ENTRANCE, COLUMNS, DAYLIGHT, SCALE)

COMPONENT_LABEL = {
    UNIT: "La oficina elegida", PERIMETER: "El contorno de la planta", CORE: "El núcleo",
    PRIMARY_ENTRANCE: "Por dónde se entra", COLUMNS: "Los pilares",
    DAYLIGHT: "Las fachadas con luz natural", SCALE: "La escala",
}

CORRECTO = "CORRECTO"
INCORRECTO = "INCORRECTO"
INCOMPLETO = "INCOMPLETO"
NO_APLICA = "NO_APLICA"
VERDICTS = (CORRECTO, INCORRECTO, INCOMPLETO, NO_APLICA)
VERDICT_LABEL = {CORRECTO: "Correcto", INCORRECTO: "Incorrecto", INCOMPLETO: "Incompleto",
                 NO_APLICA: "No aplica"}

#: Un veredicto que cuenta como "el motor acertó" a efectos de precisión. `INCOMPLETO` NO entra:
#: se cuenta aparte, porque un acepto sucio no es un acepto correcto (E35 §12).
GOOD = (CORRECTO,)


class GoldError(ValueError):
    """Componente o veredicto fuera del vocabulario."""


def _engine_confidences(property_id: str) -> Dict[str, Optional[float]]:
    """Las confianzas que el motor tenía cuando se etiquetó. Se congelan con la etiqueta: si se
    recalcularan después, la auditoría compararía una etiqueta vieja con un motor nuevo."""
    from . import ingest, properties, units                    # noqa: PLC0415
    p = properties.get(property_id) or {}
    case_id = p.get("floorplan_case_id")
    fp = intake.load_floorplate(case_id) if case_id else None
    out: Dict[str, Optional[float]] = dict.fromkeys(COMPONENTS, None)
    if fp:
        out.update(ingest.element_confidences(fp))
        esc = fp.get("scale") or {}
        out[SCALE] = (float((esc.get("meta") or {}).get("confidence") or 0.4)
                      if esc.get("px_per_m") else None)
    sel = units.get(property_id)
    if sel:
        out[UNIT] = sel["confidence"]
    return out


def save(property_id: str, component: str, verdict: str, note: str = "",
         author: str = "") -> None:
    """Un juicio humano sobre un componente. Reemplaza el anterior: la última mirada es la válida."""
    if component not in COMPONENTS:
        raise GoldError(f"componente desconocido: {component}")
    if verdict not in VERDICTS:
        raise GoldError(f"veredicto desconocido: {verdict}")
    from .. import engine                                      # noqa: PLC0415
    conf = _engine_confidences(property_id).get(component)
    store.ex("INSERT INTO gold_labels(property_id, component, verdict, note, engine_confidence, "
             "engine_version, author, created_at) VALUES (?,?,?,?,?,?,?,?) "
             "ON CONFLICT(property_id, component) DO UPDATE SET verdict=excluded.verdict, "
             "note=excluded.note, engine_confidence=excluded.engine_confidence, "
             "engine_version=excluded.engine_version, author=excluded.author, "
             "created_at=excluded.created_at",
             (property_id, component, verdict, (note or "").strip()[:500], conf,
              engine.engine_commit(), (author or "")[:80], store.now()))


def of_property(property_id: str) -> Dict[str, Dict]:
    return {r["component"]: dict(r) for r in
            store.q("SELECT * FROM gold_labels WHERE property_id=?", (property_id,))}


def judgeable(property_id: str) -> List[str]:
    """Qué componentes se pueden juzgar en ESTA propiedad: aquellos sobre los que el motor
    efectivamente se pronunció. Pedir juicio sobre lo que nadie decidió no produce evidencia."""
    confs = _engine_confidences(property_id)
    return [c for c in COMPONENTS if confs.get(c) is not None]


def review_state(property_id: str) -> Dict:
    """Qué falta para que esta propiedad sirva de evidencia de calibración."""
    puede = judgeable(property_id)
    hay = of_property(property_id)
    faltan = [c for c in puede if c not in hay]
    confs = _engine_confidences(property_id)
    return {
        "judgeable": puede, "labelled": sorted(hay), "missing": faltan,
        "complete": bool(puede) and not faltan,
        "labels": hay, "confidences": confs,
        "rows": [{"component": c, "label": COMPONENT_LABEL[c], "confidence": confs.get(c),
                  "verdict": (hay.get(c) or {}).get("verdict"),
                  "note": (hay.get(c) or {}).get("note") or ""} for c in puede],
    }


def complete(property_id: str) -> bool:
    return review_state(property_id)["complete"]


def rows_for_calibration(property_ids: List[str]) -> List[Dict]:
    """Las etiquetas en el formato que consume `calibration.metrics`.

    Se emiten sólo las que tienen confianza del motor registrada: sin ese número no hay nada que
    comparar contra un umbral, y una fila sin confianza inflaría la muestra sin aportar evidencia."""
    if not property_ids:
        return []
    marcas = ",".join("?" * len(property_ids))
    out = []
    for r in store.q(f"SELECT * FROM gold_labels WHERE property_id IN ({marcas})",
                     tuple(property_ids)):
        if r["engine_confidence"] is None or r["verdict"] == NO_APLICA:
            continue
        out.append({
            "case_id": r["property_id"], "component": r["component"],
            "engine_confidence": r["engine_confidence"],
            "human_verdict": {CORRECTO: "CONFIRMED", INCORRECTO: "DISAGREES_WITH_HUMAN",
                              INCOMPLETO: "CORRECTED_INCOMPLETE"}[r["verdict"]],
            "note": r["note"] or "", "engine_version": r["engine_version"],
            "confidence_provenance": f"artefacto de {r['property_id']} al etiquetar",
            "label_provenance": [f"gold_labels:{r['property_id']}:{r['component']}"],
        })
    return out
