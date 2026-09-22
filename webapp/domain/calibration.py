"""E35 §11–§14 — ¿SIRVEN LOS UMBRALES DE AUTOACEPTACIÓN, O SÓLO PARECEN NÚMEROS?

E34 dejó cinco varas escritas (perímetro 0.60, núcleo 0.50, acceso 0.70, pilares 0.55, luz 0.45) y
una honestidad pendiente: nadie había comprobado que separaran lo aceptable de lo que no. Este
módulo hace esa comprobación contra las marcas humanas que YA existían en el repositorio, y publica
el resultado aunque sea incómodo.

=================================================================================================
Qué se mide y qué NO
=================================================================================================
NO se mide accuracy global. Un sistema que manda todo a revisión tiene accuracy perfecta y valor
cero; uno que acepta todo tiene cobertura perfecta y es peligroso. Las dos cifras que importan van
por separado y por componente (§12):

    AUTO_ACCEPT_PRECISION  de lo que se aceptó solo, ¿cuánto resultó estar bien?
    AUTO_ACCEPT_COVERAGE   de todo lo que se podría haber aceptado, ¿cuánto se aceptó?

La precisión manda. Un falso rechazo cuesta un clic; un falso acepto cuesta un entregable con la
geometría equivocada y la credibilidad de que "el sistema lo revisó".

=================================================================================================
El resultado, y por qué no se "calibró" nada
=================================================================================================
La muestra etiquetada del repositorio son DOS unidades sobre UNA lámina. Para que un umbral quede
validado hace falta, como mínimo, verlo discriminar: algún caso por encima que resulte correcto y
alguno por debajo que resulte incorrecto. En esta muestra **ningún componente tiene eso**. Por lo
tanto todos los umbrales quedan marcados `THRESHOLD_UNCALIBRATED` y NO se tocan sus valores: mover
un número para que el dataset propio quede bonito es peor que no tener dataset.

Lo que sí se midió y hay que decir en voz alta: el acceso principal, que es el componente con la
confianza más alta del sistema (0.95 y 0.90), acertó **una de dos**. En la 401 el motor eligió un
vano del muro del núcleo con 0.90 de confianza y la persona que miró la misma lámina con zoom marcó
otro, a 64 px. El umbral de 0.70 no habría evitado ese acepto, porque 0.90 lo supera con holgura.
Un umbral no discrimina cuando el error llega con confianza alta.

=================================================================================================
Cómo se decide entonces qué se acepta solo: por CONSECUENCIA, no por estadística que no hay
=================================================================================================
Sin datos para calibrar, la política se elige por la única propiedad que sí se puede razonar: **si
el error se vería o no en el entregable**.

    invisible  la unidad elegida y la escala. Un plano de la oficina de al lado, o la misma planta
               con un 20 % más de metros, se ve perfecto. Nadie lo va a pillar mirando el PDF, y el
               error viaja a un cliente. Estos BLOQUEAN (E35 §8 y §5).
    semivisible el núcleo. Un vacío mal recortado parece plausible en cualquier caso, y además
               arrastra el área. Con 0.50 contra 0.50 no hay medición: va a revisión (§14).
    visible    acceso, pilares, luz natural. Un acceso en el muro equivocado o un pilar de menos se
               ven en la lámina y en el layout, y el circuito de calificación de E33 los caza. Se
               aceptan por regla para que EXISTA un borrador, marcados como provisionales — no como
               validados — y con su tasa de desacuerdo publicada en Ajustes.

Mandar también lo visible a revisión no sería más conservador: sería dejar de entregar. El costo de
un falso acepto visible es una calificación MALO y una regeneración; el de uno invisible es un
entregable equivocado que nadie detecta.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from .ingest import AUTO_CONFIRM_THRESHOLDS, THRESHOLD_UNCALIBRATED, UNCERTAINTY_BAND

DATASET_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "docs", "E35_CALIBRATION_DATASET.json")

#: Veredictos humanos admitidos. `DISAGREES_WITH_HUMAN` es deliberadamente distinto de
#: `CORRECTED_INCOMPLETE`: no es lo mismo que el motor se equivoque a que se quede corto, y meterlos
#: en la misma bolsa inflaría o desinflaría la precisión según convenga.
CONFIRMED = "CONFIRMED"
DISAGREES = "DISAGREES_WITH_HUMAN"
CORRECTED_INCOMPLETE = "CORRECTED_INCOMPLETE"
REJECTED = "REJECTED"
UNLABELLED = "UNLABELLED"

#: Un acepto cuenta como ERROR cuando el humano dijo otra cosa o lo rechazó. Que se haya quedado
#: corto se cuenta aparte: es un acepto sucio, no un acepto equivocado.
FALSE_ACCEPT_VERDICTS = (DISAGREES, REJECTED)

#: §12 — cuántas muestras hacen falta antes de decir que un umbral está calibrado. Con 0 fallos en
#: n pruebas, la cota superior al 95 % de la tasa de fallo es ≈ 3/n (regla de tres): con n=2 eso es
#: 150 %, o sea ninguna información; con n=10 recién baja a 30 %. Diez es el mínimo para que la
#: medición pueda descartar un umbral peligroso, no para que lo confirme.
MIN_SAMPLE = 10

#: §12 — si el error de este componente se vería o no en lo que se entrega. Es lo que decide la
#: política mientras no haya calibración. Ver el encabezado.
VISIBILITY = {"unit": "INVISIBLE", "scale": "INVISIBLE", "perimeter": "SEMIVISIBLE",
              "core": "SEMIVISIBLE", "primary_entrance": "VISIBLE", "columns": "VISIBLE",
              "daylight": "VISIBLE"}


def dataset(path: Optional[str] = None) -> Dict:
    """El dataset medido. Lo genera `scripts/e35_calibrate.py`; acá sólo se lee."""
    p = path or DATASET_PATH
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"cases": [], "rows": []}


def effective_threshold(component: str) -> Optional[float]:
    t = AUTO_CONFIRM_THRESHOLDS.get(component)
    return None if t is None else round(t + UNCERTAINTY_BAND.get(component, 0.0), 3)


def metrics(rows: Optional[List[Dict]] = None) -> Dict:
    """Precisión y cobertura de autoaceptación, por componente. Nunca un número global.

    Sólo entran filas con etiqueta humana: una fila sin etiqueta no dice nada sobre si el umbral
    acertó, y contarla como acierto sería fabricar evidencia."""
    rows = dataset()["rows"] if rows is None else rows
    por: Dict[str, Dict] = {}
    for r in rows:
        comp = r.get("component")
        if not comp or "error" in r:
            continue
        d = por.setdefault(comp, {
            "component": comp, "threshold": AUTO_CONFIRM_THRESHOLDS.get(comp),
            "band": UNCERTAINTY_BAND.get(comp, 0.0),
            "effective_threshold": effective_threshold(comp),
            "visibility": VISIBILITY.get(comp, "UNKNOWN"),
            "sample_count": 0, "unlabelled": 0, "would_accept": 0, "true_accept": 0,
            "false_accept": 0, "accepted_incomplete": 0, "false_review": 0, "true_review": 0,
            "confidences": []})
        conf, verdicto = r.get("engine_confidence"), r.get("human_verdict")
        if conf is not None:
            d["confidences"].append(conf)
        if verdicto == UNLABELLED or conf is None:
            d["unlabelled"] += 1
            continue
        d["sample_count"] += 1
        umbral = d["effective_threshold"]
        acepta = umbral is not None and conf >= umbral
        if acepta:
            d["would_accept"] += 1
            if verdicto in FALSE_ACCEPT_VERDICTS:
                d["false_accept"] += 1
            elif verdicto == CORRECTED_INCOMPLETE:
                d["accepted_incomplete"] += 1
            else:
                d["true_accept"] += 1
        elif umbral is None:
            # la escala no se gobierna con una vara de confianza sino con el orden de E35 §8
            # (unidad → escala → contraste). Contarla como "rechazada por el umbral" pondría en la
            # tabla un falso rechazo que nunca ocurrió: una fila engañosa en una auditoría es un
            # defecto, no un detalle.
            d["not_threshold_governed"] = d.get("not_threshold_governed", 0) + 1
        else:
            # mandar a revisión algo que la persona acabó confirmando tal cual es un FALSO RECHAZO:
            # costó un clic que no hacía falta. Es el error barato, y se cuenta igual.
            if verdicto == CONFIRMED:
                d["false_review"] += 1
            else:
                d["true_review"] += 1
    for d in por.values():
        n, acc = d["sample_count"], d["would_accept"]
        d["auto_accept_precision"] = None if acc == 0 else round(d["true_accept"] / acc, 3)
        d["auto_accept_coverage"] = None if n == 0 else round(acc / n, 3)
        # ¿el umbral llegó siquiera a discriminar? Hace falta ver casos a los dos lados con
        # veredictos coherentes. Si todo cayó del mismo lado, el número no fue puesto a prueba.
        d["threshold_exercised"] = bool(acc) and bool(n - acc)
        d["status"] = ("NOT_THRESHOLD_GOVERNED" if d["effective_threshold"] is None else
                       "CALIBRATED" if n >= MIN_SAMPLE and d["threshold_exercised"]
                       else THRESHOLD_UNCALIBRATED)
        d["min_sample"] = MIN_SAMPLE
    return {"components": [por[k] for k in sorted(por)],
            "cases": dataset().get("cases", []),
            "labelled_rows": sum(d["sample_count"] for d in por.values()),
            "unlabelled_rows": sum(d["unlabelled"] for d in por.values()),
            "status": THRESHOLD_UNCALIBRATED if any(
                d["status"] == THRESHOLD_UNCALIBRATED for d in por.values()) else "CALIBRATED"}


def proposal() -> Dict:
    """Qué umbrales propone la medición. §13: si la muestra no alcanza, NO se propone nada.

    Devolver los mismos números no es pereza: es el resultado. Cambiarlos con doce filas sería
    presentar una opinión como si fuera una calibración."""
    m = metrics()
    return {"status": m["status"], "min_sample": MIN_SAMPLE,
            "current": dict(AUTO_CONFIRM_THRESHOLDS), "bands": dict(UNCERTAINTY_BAND),
            "proposed": None if m["status"] == THRESHOLD_UNCALIBRATED
                        else dict(AUTO_CONFIRM_THRESHOLDS),
            "why": ("la muestra etiquetada no alcanza para validar ningún umbral: ninguno llegó a "
                    "discriminar casos a ambos lados de su vara. Se conservan los valores de E34 y "
                    "se declara la falta de calibración."
                    if m["status"] == THRESHOLD_UNCALIBRATED else
                    "la muestra alcanza y los umbrales actuales se sostienen"),
            "components": m["components"]}
