"""E16.11 — completitud del núcleo: ¿es *un* objeto plausible, o es *el* objeto?

EL FALSO POSITIVO QUE ESTE MÓDULO CIERRA
----------------------------------------
El contrato de E16.10 mide siete propiedades —coherencia con la pista, estructura permanente, tamaño,
compacidad, conectividad, invasión de piso ocupable— y todas responden a la misma pregunta:

    ¿este candidato PARECE un núcleo?

Ninguna responde la otra:

    ¿tenemos evidencia de que contiene el cluster estructural relevante, y no sólo una parte?

Sobre el plano de desarrollo, el candidato pasó las siete y dejó fuera el banco principal de
ascensores. `CORE_ACCEPTED` significaba "plausible", y se leía como "correcto". Esa distancia entre
las dos lecturas es el defecto.

QUÉ SE MIDE, Y QUÉ NO
---------------------
Las anclas son CELDAS CERRADAS (ver `enclosed_cell_anchors`): recintos sin puerta dibujada al piso.
No sabemos que sean ascensores. Sí sabemos dos cosas útiles y suficientes:

1. una celda cerrada es evidencia de construcción permanente;
2. las celdas cerradas de un núcleo aparecen AGRUPADAS, porque la infraestructura de un edificio se
   concentra; un cuarto técnico suelto en la otra punta de la planta no forma cluster con ellas.

De ahí la definición operacional:

    CLUSTER RELEVANTE = las anclas SIGNIFICATIVAS dentro del alcance semántico, ponderadas por masa.

    COMPLETITUD       = qué fracción de esa masa queda dentro del candidato.

Tres decisiones, y cada una existe para evitar una regla tonta:

* **Masa, no conteo.** Cubrir nueve celdas diminutas y dejar fuera la grande no es cubrir el núcleo.
  Es también lo que impide la regla prohibida "cubrir todas las celdas": una celda puede quedar fuera
  sin consecuencias si su masa es marginal.
* **Significativas, no todas.** Una celda cuya área es una fracción ínfima de la mayor es ruido
  gráfico y no puede arrastrar el veredicto.
* **Un umbral por debajo de 1.** Con `mass_coverage >= 0.80`, un recinto cerrado vecino que la pista
  abarcó de más —una bodega, un cuarto técnico, una oficina cerrada— no obliga a nada mientras su
  masa sea la de un recinto ordinario. Lo que no puede quedar fuera es un quinto de la evidencia.

UN CAMINO QUE SE PROBÓ Y SE DESCARTÓ, PORQUE IMPORTA
Un primer borrador agrupaba las anclas por proximidad y medía la cobertura del grupo de mayor masa.
Falló en el fixture del recinto ajeno por una razón instructiva: la distancia de enlace era una
fracción de la diagonal de la PISTA, así que una pista más floja producía un cluster más glotón y el
recinto vecino entraba. Un criterio cuya severidad depende de lo prolijo que haya sido el intérprete
semántico no es un criterio. La cobertura de masa con piso de significancia no tiene ese defecto: no
tiene ningún parámetro de distancia.

CUANDO NO SE PUEDE MEDIR
------------------------
Con una sola ancla significativa no hay cluster que evaluar: no se puede distinguir un núcleo
completo de uno parcial. El estado honesto es `COMPLETENESS_NOT_EVALUATED`, y el resultado global
NO se presenta como núcleo validado. La ausencia de evidencia no es evidencia de completitud.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# --- estados -----------------------------------------------------------------------------------
PLAUSIBLE = "PLAUSIBLE"
NOT_PLAUSIBLE = "NOT_PLAUSIBLE"

COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"
COMPLETENESS_NOT_EVALUATED = "COMPLETENESS_NOT_EVALUATED"

CORE_ACCEPTED = "CORE_ACCEPTED"
CORE_REJECTED_IMPLAUSIBLE = "CORE_REJECTED_IMPLAUSIBLE"
CORE_REJECTED_INCOMPLETE = "CORE_REJECTED_INCOMPLETE"
CORE_UNVALIDATED_NO_COMPLETENESS_EVIDENCE = "CORE_UNVALIDATED_NO_COMPLETENESS_EVIDENCE"

# --- contrato de completitud, congelado antes de reevaluar ningún caso --------------------------
COMPLETENESS_CONTRACT = {
    # Ruido gráfico: un ancla cuya área es menos de este múltiplo del ancla MAYOR del alcance no
    # participa. No es un tamaño absoluto ni una fracción de la huella: es relativo a la mayor pieza
    # de evidencia que el propio dibujo ofrece, así que se adapta a la escala del raster.
    "significant_min_ratio": 0.10,
    # Un ancla de al menos este múltiplo de la mayor es DOMINANTE. No veta: se reporta cuántas
    # quedaron fuera, porque un núcleo al que le falta una pieza grande se lee distinto de uno al que
    # le faltan varias chicas, y esa diferencia le sirve a quien audita.
    "dominant_min_ratio": 0.25,
    # Cuánta MASA del cluster relevante debe quedar dentro del candidato. Un polígono que deja fuera
    # más de un quinto de la masa del propio cluster al que pertenece no es ese objeto: es una parte.
    "mass_coverage_min": 0.80,
    # Evidencia mínima para poder hablar de completitud. Con una sola ancla significativa no hay
    # cluster: no se puede distinguir completo de parcial.
    "min_significant_anchors": 2,
}


@dataclass
class CompletenessEvidence:
    status: str
    metrics: Dict = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


def _components(mask: np.ndarray):
    n, lab, st, cen = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    piezas = [(i, int(st[i, cv2.CC_STAT_AREA]), (float(cen[i][0]), float(cen[i][1])))
              for i in range(1, n)]
    return piezas, lab


def evaluate_completeness(candidate_mask: np.ndarray, anchor_mask: np.ndarray,
                          hint_region: Tuple[float, float, float, float],
                          contract: Optional[Dict] = None) -> CompletenessEvidence:
    """¿El candidato contiene el cluster de anclas relevante, o sólo una parte?"""
    c = dict(COMPLETENESS_CONTRACT, **(contract or {}))
    h, w = candidate_mask.shape[:2]
    x0, y0, x1, y1 = [int(v) for v in hint_region]
    alcance = np.zeros((h, w), bool)
    alcance[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = True

    todas, lab = _components(anchor_mask)
    piezas = [(i, a, cen) for (i, a, cen) in todas
              if alcance[int(min(h - 1, max(0, cen[1]))), int(min(w - 1, max(0, cen[0])))]]
    if not piezas:
        return CompletenessEvidence(COMPLETENESS_NOT_EVALUATED,
                                    {"anchors_in_scope": 0, "significant_anchors": 0},
                                    ["no hay celdas cerradas dentro del alcance semántico: no hay "
                                     "con qué evaluar completitud"])
    mayor = max(p[1] for p in piezas)
    sig = [p for p in piezas if p[1] >= c["significant_min_ratio"] * mayor]
    metrics = {"anchors_in_scope": len(piezas), "significant_anchors": len(sig),
               "largest_anchor_px": int(mayor)}

    if len(sig) < c["min_significant_anchors"]:
        return CompletenessEvidence(COMPLETENESS_NOT_EVALUATED, metrics,
                                    [f"sólo {len(sig)} ancla(s) significativa(s) en el alcance: con "
                                     f"menos de {c['min_significant_anchors']} no hay cluster que "
                                     f"evaluar, y no se puede distinguir completo de parcial"])

    masa_total = float(sum(a for _, a, _ in sig))
    dentro = 0.0
    dominantes_fuera = 0
    for idx, area, _ in sig:
        pieza = (lab == idx)
        cubierta = (pieza & (candidate_mask > 0)).sum() >= 0.5 * area
        if cubierta:
            dentro += area
        elif area >= c["dominant_min_ratio"] * mayor:
            dominantes_fuera += 1
    cobertura = dentro / masa_total if masa_total else 0.0
    xs = [p[2][0] for p in sig]; ys = [p[2][1] for p in sig]
    metrics.update({
        "significant_mass_px": int(masa_total),
        "covered_mass_px": int(dentro),
        "mass_coverage": round(cobertura, 4),
        # evidencia, no veto: cuántas anclas GRANDES quedaron afuera. Informa la lectura humana sin
        # añadir un segundo umbral que pueda pelearse con el primero.
        "dominant_anchors_outside": int(dominantes_fuera),
        "anchor_span_px": round(float(np.hypot(max(xs) - min(xs), max(ys) - min(ys))), 1),
    })
    if cobertura < c["mass_coverage_min"]:
        return CompletenessEvidence(INCOMPLETE, metrics,
                                    [f"mass_coverage={cobertura:.3f} < {c['mass_coverage_min']}: el "
                                     f"candidato deja fuera masa de la evidencia estructural que la "
                                     f"propia semántica señaló"])
    return CompletenessEvidence(COMPLETE, metrics, [])


def overall_status(plausible: bool, completeness: str) -> str:
    """`CORE_ACCEPTED` deja de significar 'plausible aunque no sepamos si está completo'."""
    if not plausible:
        return CORE_REJECTED_IMPLAUSIBLE
    if completeness == COMPLETE:
        return CORE_ACCEPTED
    if completeness == INCOMPLETE:
        return CORE_REJECTED_INCOMPLETE
    return CORE_UNVALIDATED_NO_COMPLETENESS_EVIDENCE
