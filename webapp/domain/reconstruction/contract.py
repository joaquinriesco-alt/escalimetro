"""E37 §Contrato mínimo — la representación estructurada de una reconstrucción, versión 1.

La fuente de verdad de una corrida es ESTO, no una imagen: recintos, conexiones, posición relativa,
geometría aproximada, incertidumbre y la evidencia que sostiene cada inferencia. El SVG se dibuja
desde acá (`render`), así que dos motores distintos se comparan sobre lo mismo.

Decisiones de forma, y por qué:

* **coordenadas normalizadas.** Cada recinto es un polígono en un marco 0..1 (x hacia la derecha,
  y hacia abajo) que cubre la huella de la planta. Un motor casi nunca sabe metros; si los estima,
  los declara aparte en `footprint`, con de dónde los saca. Así la proporción conocida y la escala
  inventada no se confunden;
* **un recinto puede no tener polígono.** Saber que existe un walk-in y no saber dónde está es un
  resultado honesto (E37: «NO inventar geometría oculta»). Queda en la lista, sin ubicar, con sus
  relaciones si las hay;
* **el esquema es compatible con el modo estricto de OpenAI**: todo campo es obligatorio y lo
  opcional es anulable, sin cotas numéricas. Las cotas —confianza en 0..1, coordenadas dentro del
  marco, referencias que existen— las revisa `validate()`, porque un proveedor puede cumplir la
  forma y equivocarse en el fondo.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Tuple

CONTRACT_ID = "escalimetro.reconstruction.v1"

RECONSTRUCTED = "RECONSTRUCTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
OUTCOMES = (RECONSTRUCTED, INSUFFICIENT_EVIDENCE, CLARIFICATION_REQUIRED)

ROOM_TYPES = ("LIVING", "DINING", "LIVING_DINING", "KITCHEN", "BEDROOM", "BATHROOM", "TOILET",
              "WALK_IN_CLOSET", "CLOSET", "HALLWAY", "ENTRY", "LAUNDRY", "TERRACE", "BALCONY",
              "STUDY", "STORAGE", "OTHER")
CONNECTION_KINDS = ("DOOR", "OPENING", "ADJACENT", "UNKNOWN")
RELATIONS = ("LEFT_OF", "RIGHT_OF", "ABOVE", "BELOW", "NEXT_TO")
IMPACTS = ("HIGH", "MEDIUM", "LOW")

#: Cuánto puede salirse un vértice del marco antes de que sea un error y no un redondeo.
FRAME_TOLERANCE = 0.02
#: Por debajo de esta confianza el recinto se dibuja punteado: se muestra, pero no se afirma.
LOW_CONFIDENCE = 0.5
#: Cotas de sentido común. No afinan nada: sólo impiden que un número absurdo pase el contrato y
#: reviente después, al dibujar (un entero de 400 dígitos es finito para Python).
MAX_ABS_NUMBER = 1e7
FOOTPRINT_M = (0.5, 10000.0)
MAX_ASPECT = 50.0
MAX_AREA_M2 = 100000.0
MAX_LEVELS = 200


def _obj(props: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "properties": props,
            "required": list(props)}


def _nullable(schema: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(schema)
    t = out.get("type")
    out["type"] = [t, "null"] if isinstance(t, str) else list(t) + ["null"]
    return out


_EVIDENCE = {"type": "array", "items": _obj({
    "asset_ids": {"type": "array", "items": {"type": "string"}},
    "observation": {"type": "string"},
})}

SCHEMA: Dict[str, Any] = _obj({
    "contract": {"type": "string", "enum": [CONTRACT_ID]},
    "outcome": {"type": "string", "enum": list(OUTCOMES)},
    "summary": {"type": "string"},
    "levels": {"type": "integer"},
    "footprint": _obj({
        "width_m": {"type": ["number", "null"]},
        "depth_m": {"type": ["number", "null"]},
        "basis": {"type": "string"},
    }),
    "rooms": {"type": "array", "items": _obj({
        "id": {"type": "string"},
        "label": {"type": "string"},
        "room_type": {"type": "string", "enum": list(ROOM_TYPES)},
        "level": {"type": "integer"},
        "polygon": _nullable({"type": "array",
                              "items": {"type": "array", "items": {"type": "number"}}}),
        "area_m2": {"type": ["number", "null"]},
        "confidence": {"type": "number"},
        "evidence": _EVIDENCE,
        "uncertainty": {"type": ["string", "null"]},
    })},
    "connections": {"type": "array", "items": _obj({
        "id": {"type": "string"},
        "from_room": {"type": "string"},
        "to_room": {"type": "string"},
        "kind": {"type": "string", "enum": list(CONNECTION_KINDS)},
        "confidence": {"type": "number"},
        "evidence": _EVIDENCE,
    })},
    "relations": {"type": "array", "items": _obj({
        "room": {"type": "string"},
        "relation": {"type": "string", "enum": list(RELATIONS)},
        "other_room": {"type": "string"},
        "confidence": {"type": "number"},
        # la posición relativa es justo lo que falló en la prueba histórica: también cita evidencia
        "evidence": _EVIDENCE,
    })},
    "uncertainties": {"type": "array", "items": _obj({
        "subject": {"type": "string"},
        "issue": {"type": "string"},
        "impact": {"type": "string", "enum": list(IMPACTS)},
    })},
    "missing_evidence": {"type": "array", "items": {"type": "string"}},
    "clarification": _nullable(_obj({
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
    })),
    "correction": _nullable(_obj({
        "understood_as": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "string"}},
    })),
})


class ContractError(ValueError):
    """La salida de un motor no cumple el contrato. La corrida falla con esto, no se maquilla."""


def validate(obj: Any, *, known_asset_ids: Tuple[str, ...] = ()) -> List[str]:
    """Valida forma y fondo. Devuelve las ADVERTENCIAS; lanza `ContractError` si no se puede usar.

    Lo que invalida: no cumplir el esquema, ids repetidos, conexiones o relaciones hacia recintos
    que no existen, confianzas fuera de 0..1, polígonos de menos de tres vértices o fuera del
    marco, y un resultado que contradice su propio `outcome` (RECONSTRUCTED sin ningún recinto
    ubicado, CLARIFICATION_REQUIRED sin pregunta). Lo que sólo advierte: evidencia que cita una
    foto que el motor no recibió —el motor la inventó, y eso conviene verlo, pero no borra el
    resto del resultado—."""
    import jsonschema                                           # noqa: PLC0415 (dependencia declarada)

    def finitos(v: Any, donde: str = "") -> None:
        # JSON admite 1e400, que Python lee como infinito; el esquema lo acepta como número y el
        # dibujo después revienta. Se corta acá, como contrato inválido, y no más adelante.
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            try:
                ok = math.isfinite(float(v)) and abs(float(v)) <= MAX_ABS_NUMBER
            except OverflowError:
                ok = False
            if not ok:
                raise ContractError(f"número fuera de rango en {donde or '(raíz)'}")
        if isinstance(v, dict):
            for k, x in v.items():
                finitos(x, f"{donde}/{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                finitos(x, f"{donde}/{i}")
    finitos(obj)
    try:
        jsonschema.validate(obj, SCHEMA)
    except jsonschema.ValidationError as e:
        donde = "/".join(str(p) for p in e.absolute_path) or "(raíz)"
        raise ContractError(f"no cumple el esquema en {donde}: {e.message[:300]}") from None

    errores: List[str] = []
    avisos: List[str] = []
    ids = [r["id"] for r in obj["rooms"]]
    if len(ids) != len(set(ids)):
        errores.append("hay recintos con el mismo id")
    conocidos = set(ids)

    def conf(v: float, donde: str) -> None:
        if not (0.0 <= v <= 1.0):
            errores.append(f"{donde}: confianza {v} fuera de 0..1")

    def evidencia(ev: List[Dict], donde: str) -> None:
        for e in ev:
            for a in e["asset_ids"]:
                if known_asset_ids and a not in known_asset_ids:
                    avisos.append(f"{donde} cita la foto «{a}», que el motor no recibió")

    for r in obj["rooms"]:
        donde = f"recinto {r['id']}"
        conf(r["confidence"], donde)
        evidencia(r["evidence"], donde)
        pts = r["polygon"]
        if pts is not None:
            if len(pts) < 3 or any(len(p) != 2 for p in pts):
                errores.append(f"{donde}: el polígono necesita al menos tres vértices [x, y]")
            elif any(not (-FRAME_TOLERANCE <= c <= 1 + FRAME_TOLERANCE) for p in pts for c in p):
                errores.append(f"{donde}: el polígono sale del marco normalizado 0..1")
        if r["area_m2"] is not None and not (0 < r["area_m2"] <= MAX_AREA_M2):
            errores.append(f"{donde}: superficie fuera de rango")
    ids_con = [c["id"] for c in obj["connections"]]
    if len(ids_con) != len(set(ids_con)):
        errores.append("hay conexiones con el mismo id")
    for c in obj["connections"]:
        donde = f"conexión {c['id']}"
        conf(c["confidence"], donde)
        evidencia(c["evidence"], donde)
        for extremo in (c["from_room"], c["to_room"]):
            if extremo not in conocidos:
                errores.append(f"{donde}: apunta a «{extremo}», que no es un recinto")
    for rel in obj["relations"]:
        conf(rel["confidence"], f"relación {rel['room']}")
        evidencia(rel["evidence"], f"relación {rel['room']}")
        for extremo in (rel["room"], rel["other_room"]):
            if extremo not in conocidos:
                errores.append(f"relación: «{extremo}» no es un recinto")
    fp = obj["footprint"]
    for k in ("width_m", "depth_m"):
        if fp[k] is not None and not (FOOTPRINT_M[0] <= fp[k] <= FOOTPRINT_M[1]):
            errores.append(f"footprint.{k} fuera de {FOOTPRINT_M[0]}..{FOOTPRINT_M[1]} m")
    if fp["width_m"] and fp["depth_m"]:
        razon = fp["depth_m"] / fp["width_m"]
        if not (1 / MAX_ASPECT <= razon <= MAX_ASPECT):
            errores.append("la proporción de la huella es absurda")
    if not (1 <= obj["levels"] <= MAX_LEVELS):
        errores.append("levels fuera de rango")

    outcome = obj["outcome"]
    if outcome == RECONSTRUCTED and not any(r["polygon"] for r in obj["rooms"]):
        errores.append("RECONSTRUCTED sin ningún recinto ubicado: eso es INSUFFICIENT_EVIDENCE")
    if outcome == CLARIFICATION_REQUIRED and not obj["clarification"]:
        errores.append("CLARIFICATION_REQUIRED sin la pregunta")
    if outcome == INSUFFICIENT_EVIDENCE and not (obj["missing_evidence"] or obj["summary"].strip()):
        errores.append("INSUFFICIENT_EVIDENCE sin decir qué falta")
    if errores:
        raise ContractError("; ".join(errores[:8]))
    return avisos


def placed(obj: Dict) -> List[Dict]:
    return [r for r in (obj or {}).get("rooms", []) if r.get("polygon")]


def unplaced(obj: Dict) -> List[Dict]:
    return [r for r in (obj or {}).get("rooms", []) if not r.get("polygon")]
