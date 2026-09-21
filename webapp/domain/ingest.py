"""E34 — INFERIR LO QUE EL USUARIO NO TIENE POR QUÉ SABER.

La regla de producto: **el usuario entrega el inmueble, Escalímetro resuelve el resto.** Nadie que
quiera publicar una oficina debería tener que marcar dos puntos sobre un plano para declarar la
escala, ni señalar por dónde se entra.

=================================================================================================
Lo que YA hacía el motor, y que la aplicación estaba tapando
=================================================================================================
Al analizar una planta, el pipeline ya deduce solo:

* la **escala**, cuando hay superficie publicada (`published_area_inferred`);
* el **acceso principal**, con su propia confianza y evidencia (`primary_entrance`);
* pilares, fachada y luz natural, cada uno con su estado.

Y ya decide si eso alcanza: `shell_readiness.ready_for_layout`. En las dos plantas reales del repo
ese campo sale en `true` **sin una sola confirmación humana**. La fricción no estaba en el motor:
estaba en un formulario de esta aplicación que pedía escala, acceso y "¿está limpia la planta?"
antes de dejar mirar nada.

E34 quita ese formulario del camino y deja que el motor hable primero.

=================================================================================================
Escala por puertas: qué se puede y qué no
=================================================================================================
§4 pide inferir escala desde puertas con ancho nominal de 0.90 m. Se implementa, con medianas y
descarte de atípicos — y con una advertencia medida sobre datos reales, no teórica:

Lo que el motor expone son `entrance_candidates`, que son **vanos del perímetro** (accesos), no
puertas interiores. En la 403 sus anchos son 4, 6, 10 y 16 px con una escala real de 8.36 px/m:
es decir 0.48, 0.72, 1.20 y 1.91 m. Ninguno es una puerta simple de 0.90 m; son entradas. Además,
a 8 px/m **un píxel son 12 cm**, así que medio píxel de error en un vano de 7 px ya es un 7 % de
escala.

Conclusión honesta, que el código refleja: la escala por puertas es un **último recurso**, su
confianza nace baja y el contraste contra la superficie publicada existe para desmentirla, no para
adornarla. Cuando hay superficie publicada, esa es la fuente; las puertas sirven para comprobarla.
"""
from __future__ import annotations

import json
import statistics
from typing import Dict, List, Optional, Tuple

from .. import intake, store
from . import properties

#: Ancho nominal de una puerta simple de oficina. Referencia, no certeza.
NOMINAL_DOOR_M = 0.90
#: Vanos plausibles como puerta simple, en metros, una vez estimada la escala.
SINGLE_DOOR_RANGE = (0.70, 1.15)
#: Mínimo de píxeles para que un vano sea medible. Por debajo, el error de cuantización domina.
MIN_DOOR_PX = 4.0
#: Diferencia relativa a partir de la cual dos métodos de escala se consideran en desacuerdo.
CROSS_CHECK_TOLERANCE = 0.12
#: Confianza mínima para seguir sin intervención humana.
MIN_AUTO_CONFIDENCE = 0.55

#: §8 — la vara por elemento para aceptar SIN que mire una persona. Son las confianzas que el
#: propio motor emite, no números nuestros: aceptamos su detección cuando él mismo la da por buena
#: con holgura. Lo que queda por debajo va a revisión interna con su nombre.
#: Las plantas reales del repo dan: perímetro 0.70 · núcleo 0.50 · pilares 0.70 (mediana) ·
#: luz natural 0.60 (mediana) · acceso 0.95. Los umbrales se fijan por debajo de eso a propósito,
#: pero no tanto como para aceptar cualquier cosa.
#: El contorno y el núcleo se piden juntos pero no valen lo mismo: el perímetro define el shell
#: entero, y el núcleo es una resta dentro de él. Por eso tienen varas distintas y se exigen las
#: dos, en vez de resumirlos en un mínimo que castigaría al perímetro por la duda sobre el núcleo.
AUTO_CONFIRM_THRESHOLDS = {
    "perimeter": 0.60,
    "core": 0.50,
    "primary_entrance": 0.70,
    "columns": 0.55,
    "daylight": 0.45,
}
#: Cómo se traduce cada compuerta al vocabulario de `overrides.confirm` que el motor entiende.
#: NO son los mismos nombres: `shell_readiness.requires_confirmation` habla de "perimeter/core" y
#: "primary_entrance", y el pipeline espera "perimeter"+"core" y "entrance" (documentado en
#: src/escalimetro/semantics/shell.py). Pasar los nombres sin traducir no da error: simplemente no
#: confirma nada, y la planta se queda pendiente para siempre sin que nadie sepa por qué.
CONFIRM_KEYS = {
    "perimeter/core": ["perimeter", "core"],
    "primary_entrance": ["entrance"],
    "columns": ["columns"],
    "daylight": ["daylight"],
    "scale_assumption": ["scale_assumption"],
}

#: Cómo se llama cada compuerta cuando hay que explicarla.
GATE_LABELS = {
    "perimeter/core": "el contorno de la planta y su núcleo",
    "primary_entrance": "por dónde se entra",
    "columns": "los pilares",
    "daylight": "las fachadas con luz natural",
    "scale_assumption": "la escala del plano",
}

PUBLISHED_AREA, AUTO_DOOR, MANUAL, UNKNOWN = "PUBLISHED_AREA", "AUTO_DOOR", "MANUAL", "UNKNOWN"
AUTO, NONE = "AUTO", "NONE"
AUTO_ACCEPTED_BY_RULE, HUMAN_CONFIRMED, PENDING = ("AUTO_ACCEPTED_BY_RULE", "HUMAN_CONFIRMED",
                                                   "PENDING")


# =================================================================================================
# escala por puertas
# =================================================================================================
def door_widths_px(fp: Dict) -> List[float]:
    """Los anchos de vano que el motor detectó, en píxeles. Sin filtrar todavía."""
    out = []
    for c in (fp.get("entrance_candidates") or []):
        w = c.get("width_px")
        if w and float(w) >= MIN_DOOR_PX:
            out.append(float(w))
    pe = fp.get("primary_entrance") or {}
    # el acceso principal suele repetir uno de los candidatos; se suma sólo si es otro vano
    if pe.get("width_px") and float(pe["width_px"]) >= MIN_DOOR_PX:
        if float(pe["width_px"]) not in out:
            out.append(float(pe["width_px"]))
    # NO se deduplica: cuatro vanos que miden lo mismo son cuatro evidencias, no una. Quitar los
    # repetidos borraba justamente la señal más fuerte que puede tener este método.
    return sorted(out)


def _narrowest_cluster(widths: List[float]) -> List[float]:
    """Se queda con el grupo MÁS ANGOSTO de vanos.

    Por qué el más angosto y no todos: sin escala no se puede saber cuál vano es una puerta simple
    y cuál una entrada doble —es circular—. Lo único defendible es suponer que los vanos más
    estrechos son los más cercanos a una puerta simple, y descartar los anchos, que casi siempre
    son accesos principales. Si se mezclaran, la mediana quedaría entre una puerta y una entrada, y
    la escala saldría mal con aspecto de estar bien."""
    if len(widths) <= 1:
        return list(widths)
    med = statistics.median(widths)
    angostos = [w for w in widths if w <= med * 1.35]
    return angostos or [min(widths)]


def _mad_filter(xs: List[float]) -> Tuple[List[float], List[float]]:
    """Descarta atípicos por desviación absoluta mediana. Devuelve (conservados, descartados)."""
    if len(xs) < 3:
        return list(xs), []
    med = statistics.median(xs)
    desv = statistics.median([abs(x - med) for x in xs]) or 0.0
    if desv == 0:
        return list(xs), []
    keep = [x for x in xs if abs(x - med) <= 3.0 * desv]
    drop = [x for x in xs if x not in keep]
    return (keep or list(xs)), drop


def scale_from_doors(fp: Dict) -> Optional[Dict]:
    """Hipótesis de escala desde los vanos detectados, o None si no hay evidencia utilizable.

    La confianza sale de tres cosas medibles, no de una corazonada: cuántos vanos hay, qué tan de
    acuerdo están entre sí, y cuánto pesa el error de cuantización a esa resolución. Un solo vano
    de 5 px no puede producir una escala confiable, y el número lo dice."""
    todos = door_widths_px(fp)
    if not todos:
        return None
    grupo = _narrowest_cluster(todos)
    usados, descartados = _mad_filter(grupo)
    if not usados:
        return None
    mediana = statistics.median(usados)
    px_per_m = mediana / NOMINAL_DOOR_M

    # 1) cuántas evidencias. Una sola puerta es una anécdota.
    c_n = {1: 0.35, 2: 0.55, 3: 0.68}.get(len(usados), 0.78)
    # 2) acuerdo entre ellas (dispersión relativa)
    if len(usados) >= 2:
        disp = (max(usados) - min(usados)) / mediana
        c_disp = max(0.0, 1.0 - disp)
    else:
        c_disp = 0.6
    # 3) cuantización: medio píxel de error sobre la mediana, en tanto por uno
    c_quant = max(0.0, 1.0 - (0.5 / mediana))

    conf = round(c_n * (0.5 + 0.5 * c_disp) * c_quant, 3)
    return {"source": AUTO_DOOR, "px_per_m": round(px_per_m, 4), "confidence": conf,
            "evidence_count": len(usados), "widths_px": usados, "discarded_px": descartados,
            "median_px": mediana, "nominal_m": NOMINAL_DOOR_M,
            "notes": (f"mediana de {len(usados)} vano(s) = {mediana:.1f} px, "
                      f"puerta simple de referencia {NOMINAL_DOOR_M} m")}


# =================================================================================================
# contraste contra la superficie publicada
# =================================================================================================
def cross_check(fp: Dict, hypothesis: Optional[Dict]) -> Dict:
    """Compara la escala inferida contra la superficie publicada.

    §5 — la diferencia es una SEÑAL, nunca una corrección: no se deforma la geometría para que el
    área dé. Si coinciden, sube la confianza; si divergen de verdad, esto va a revisión interna."""
    out: Dict = {"published_area_m2": fp.get("published_area_m2"),
                 "engine_px_per_m": (fp.get("scale") or {}).get("px_per_m"),
                 "engine_method": (fp.get("scale") or {}).get("method")}
    area_px2 = fp.get("area_px2")
    pub = fp.get("published_area_m2")
    if hypothesis and area_px2:
        derivada = area_px2 / (hypothesis["px_per_m"] ** 2)
        out["door_derived_area_m2"] = round(derivada, 1)
        if pub:
            dif = abs(derivada - pub) / pub
            out["area_relative_difference"] = round(dif, 3)
            out["agrees"] = dif <= CROSS_CHECK_TOLERANCE
    if hypothesis and out.get("engine_px_per_m"):
        d = abs(hypothesis["px_per_m"] - out["engine_px_per_m"]) / out["engine_px_per_m"]
        out["scale_relative_difference"] = round(d, 3)
        out["scale_agrees"] = d <= CROSS_CHECK_TOLERANCE
    return out


# =================================================================================================
# la decisión
# =================================================================================================
def decide(fp: Dict) -> Dict:
    """Qué escala se usa, con qué confianza y por qué. No escribe nada; sólo decide.

    Orden del §4: superficie publicada cuando la hay (es lo que el motor ya aplica y lo que mejor
    funciona en las plantas reales), y puertas como último recurso cuando no la hay."""
    esc = fp.get("scale") or {}
    puertas = scale_from_doors(fp)
    cc = cross_check(fp, puertas)
    metodo = esc.get("method") or ""

    if metodo == "manual":
        fuente, ppm, conf = MANUAL, esc.get("px_per_m"), 1.0
        nota = "escala medida por una persona"
    elif esc.get("px_per_m") and metodo.startswith("published_area"):
        fuente, ppm = PUBLISHED_AREA, esc["px_per_m"]
        conf = float((esc.get("meta") or {}).get("confidence") or 0.4)
        # el acuerdo con las puertas la respalda; el desacuerdo NO la baja por debajo de lo que el
        # motor ya dijo, porque las puertas son la evidencia más débil de las dos
        if cc.get("scale_agrees"):
            conf = min(0.9, conf + 0.2)
        nota = "escala deducida de la superficie publicada"
    elif puertas:
        fuente, ppm, conf = AUTO_DOOR, puertas["px_per_m"], puertas["confidence"]
        nota = puertas["notes"]
    else:
        fuente, ppm, conf = UNKNOWN, None, 0.0
        nota = "sin superficie publicada, sin cota y sin vanos medibles"

    pe = fp.get("primary_entrance") or {}
    acceso_conf = float(pe.get("confidence") or 0.0)
    acceso_fuente = AUTO if pe.get("point") else NONE
    if (pe.get("provenance") or "") == "manual":
        acceso_fuente = MANUAL

    listo = bool((fp.get("shell_readiness") or {}).get("ready_for_layout"))

    # ¿Hace falta que mire una persona? La autoridad sobre "se puede seguir" es del MOTOR: si dijo
    # ready_for_layout, ya evaluó sus propias compuertas y dejó escrito el supuesto que asume. Mi
    # umbral sólo gobierna lo que deduzco YO —la escala por puertas—, que es la evidencia más
    # débil de todas y merece una vara más alta que la del motor.
    revisar = not listo
    if fuente == AUTO_DOOR and conf < MIN_AUTO_CONFIDENCE:
        revisar = True
    # Un desacuerdo con las puertas sólo cuenta como señal si la hipótesis de puertas es creíble.
    # En plantas reales los vanos detectados son ACCESOS (1.2–2.0 m), no puertas simples de 0.90 m,
    # así que casi siempre discrepan: tratar esa discrepancia como prueba mandaría todo a revisión
    # por culpa del estimador más flojo, que es exactamente al revés.
    if (puertas and puertas["confidence"] >= MIN_AUTO_CONFIDENCE
            and cc.get("scale_agrees") is False):
        revisar = True

    return {
        "scale_source": fuente, "scale_value": ppm, "scale_confidence": round(conf, 3),
        "evidence_count": (puertas or {}).get("evidence_count", 0),
        "cross_checks": cc, "door_hypothesis": puertas,
        "access_source": acceso_fuente, "access_confidence": round(acceso_conf, 3),
        "geometry_source": AUTO_ACCEPTED_BY_RULE if listo else PENDING,
        "ready": listo, "needs_review": revisar,
        "review_reason": (None if not revisar else
                          ("la planta necesita revisión antes de continuar" if not listo else
                           "la escala deducida no es lo bastante confiable")),
        "notes": nota,
    }


# =================================================================================================
# persistencia y uso desde el producto
# =================================================================================================
def save(property_id: str, case_id: str, d: Dict) -> None:
    store.ex("INSERT INTO ingest_inference(property_id, case_id, scale_source, scale_value, "
             "scale_confidence, evidence_count, cross_checks, access_source, access_confidence, "
             "geometry_source, notes, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
             "ON CONFLICT(property_id) DO UPDATE SET case_id=excluded.case_id, "
             "scale_source=excluded.scale_source, scale_value=excluded.scale_value, "
             "scale_confidence=excluded.scale_confidence, evidence_count=excluded.evidence_count, "
             "cross_checks=excluded.cross_checks, access_source=excluded.access_source, "
             "access_confidence=excluded.access_confidence, "
             "geometry_source=excluded.geometry_source, notes=excluded.notes, "
             "updated_at=excluded.updated_at",
             (property_id, case_id, d["scale_source"], d["scale_value"], d["scale_confidence"],
              d["evidence_count"], json.dumps(d["cross_checks"], ensure_ascii=False),
              d["access_source"], d["access_confidence"], d["geometry_source"], d["notes"],
              store.now()))


def get(property_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM ingest_inference WHERE property_id=?", (property_id,))
    if r is None:
        return None
    d = dict(r)
    d["cross_checks_obj"] = store.js(d["cross_checks"], {}) or {}
    return d


def declare_whole_drawing(property_id: str) -> Dict:
    """«El dibujo completo es esta oficina.» Un hecho que sólo una persona puede declarar, y que se
    pregunta ÚNICAMENTE cuando la localización automática no alcanzó."""
    p = properties.require(property_id)
    case_id = p["floorplan_case_id"]
    if not case_id:
        raise ValueError("la propiedad todavía no tiene un caso técnico")
    intake.set_drawing_scope(case_id, "whole_shell")
    return auto_prepare(property_id)


def auto_prepare(property_id: str) -> Dict:
    """Analiza la planta SIN pedirle nada al usuario y registra qué se dedujo.

    Es el reemplazo del formulario de intake en el camino normal: no se pregunta si la planta está
    limpia, ni la escala, ni el acceso. El motor mira, deduce y dice si le alcanza. Cuando no le
    alcanza, la medición manual sigue existiendo en la herramienta técnica — como último recurso,
    no como primer paso."""
    p = properties.require(property_id)
    case_id = p["floorplan_case_id"]
    if not case_id:
        raise ValueError("la propiedad todavía no tiene un caso técnico")
    # la superficie publicada, si el cliente la dio, es un hecho de entrada del caso
    if p["published_area_m2"]:
        store.ex("UPDATE cases SET published_area_m2=? WHERE case_id=?",
                 (p["published_area_m2"], case_id))
    res = intake.analyze(case_id)
    fp = intake.load_floorplate(case_id)

    # Segunda pasada: el motor pidió confirmar lo que detectó. Lo que supere su propia vara se
    # acepta POR REGLA y se vuelve a correr con esas confirmaciones; lo que no, queda pendiente y
    # se dice con nombre. Nunca se confirma un grupo que el motor no dio por bueno.
    auto = auto_confirmations(fp) if fp else {"accept": [], "pending": [], "asked": []}
    if fp and auto["accept"]:
        escala_ok = bool((fp.get("scale") or {}).get("px_per_m"))
        confirmar = list(auto["confirm_keys"])
        if escala_ok and "scale_assumption" in auto["asked"]:
            confirmar.append("scale_assumption")
        intake.apply_confirmations(case_id, {k: "ok" for k in confirmar})
        fp = intake.load_floorplate(case_id)
        auto = dict(auto, applied=confirmar)

    if fp is None:
        # el motivo más común y el único que una persona puede resolver en un clic: la lámina
        # tiene varias unidades y no se pudo saber cuál es ésta. El motor localiza por el nombre
        # de la propiedad (OCR sobre el dibujo), así que "Oficina 403" funciona y "Mi oficina" no.
        sin_localizar = "Sin localización" in (res.get("log") or "")
        d = {"scale_source": UNKNOWN, "scale_value": None, "scale_confidence": 0.0,
             "evidence_count": 0, "cross_checks": {}, "access_source": NONE,
             "access_confidence": 0.0, "geometry_source": PENDING, "ready": False,
             "needs_review": True, "door_hypothesis": None,
             "blocked_on": "localization" if sin_localizar else "pipeline",
             "review_reason": ("no pudimos identificar cuál de las oficinas de la lámina es ésta"
                               if sin_localizar else
                               "no pudimos leer la geometría de este plano"),
             "notes": ("la lámina parece tener más de una unidad" if sin_localizar
                       else "el plano no se pudo procesar")}
    else:
        d = decide(fp)
        d["auto_confirmations"] = auto
        if auto.get("pending"):
            d["needs_review"] = True
            d["review_reason"] = ("necesitamos revisar " + ", ".join(auto["pending_labels"]))
    save(property_id, case_id, d)
    d["log"] = res.get("log", "")
    return d


# =================================================================================================
# §8 — ACEPTACIÓN AUTOMÁTICA POR REGLA
# =================================================================================================
def _median_conf(items: List[Dict], key: str = "confidence") -> Optional[float]:
    vals = [float(i.get(key)) for i in (items or []) if i.get(key) is not None]
    return statistics.median(vals) if vals else None


def element_confidences(fp: Dict) -> Dict[str, Optional[float]]:
    """La confianza que el MOTOR le da a cada grupo. No se inventa ninguna."""
    perim = float(((fp.get("perimeter") or {}).get("meta") or {}).get("confidence") or 0.0)
    nucleos = [c.get("meta", {}) for c in (fp.get("core") or [])]
    pe = fp.get("primary_entrance") or {}
    return {
        "perimeter": perim,
        "core": _median_conf(nucleos),
        "primary_entrance": float(pe.get("confidence") or 0.0) if pe.get("point") else None,
        "columns": _median_conf(fp.get("column_candidates") or []),
        "daylight": _median_conf(fp.get("daylight_segments") or []),
    }


def auto_confirmations(fp: Dict) -> Dict:
    """Qué se puede aceptar por regla y qué tiene que mirar una persona.

    Esto NO es auto-confirmar a ciegas: cada grupo se acepta sólo si la confianza que el propio
    motor publicó supera una vara escrita, y lo aceptado queda marcado como
    `AUTO_ACCEPTED_BY_RULE`, nunca como `HUMAN_CONFIRMED`. La diferencia viaja en la procedencia y
    se ve en el detalle técnico: quien lea un layout puede saber que su planta nunca la miró nadie.

    `scale_assumption` es aparte: no es una detección con confianza, es el motor pidiendo que
    alguien reconozca que la escala salió de la superficie publicada y no de una medición. Se
    acepta cuando la escala viene de una fuente que aceptamos, y el supuesto queda registrado."""
    piden = list((fp.get("shell_readiness") or {}).get("requires_confirmation") or [])
    confs = element_confidences(fp)
    aceptados, pendientes, detalle = [], [], {}
    for gate in piden:
        if gate == "scale_assumption":
            continue                                   # lo resuelve `decide`, junto con la escala
        # una compuerta puede exigir más de una medida: "perimeter/core" son dos, y hacen falta
        # las dos. Basta que una no llegue para que la compuerta quede pendiente.
        partes = ["perimeter", "core"] if gate == "perimeter/core" else [gate]
        ok = True
        detalle[gate] = {}
        for parte in partes:
            umbral = AUTO_CONFIRM_THRESHOLDS.get(parte)
            c = confs.get(parte)
            detalle[gate][parte] = {"confidence": c, "threshold": umbral}
            if umbral is None or c is None or c < umbral:
                ok = False
        (aceptados if ok else pendientes).append(gate)
    claves = [k for g in aceptados for k in CONFIRM_KEYS.get(g, [])]
    return {"accept": aceptados, "confirm_keys": claves, "pending": pendientes, "detail": detalle,
            "asked": piden,
            "pending_labels": [GATE_LABELS.get(g, g) for g in pendientes]}
