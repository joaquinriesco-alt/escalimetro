"""Estimación de escala.

Método principal desde E01: superficie publicada. `px_per_m = sqrt(area_px2 / area_m2)`.
Eso fija el área por construcción —el error contra la superficie publicada es 0 por definición—
así que el benchmark de área debe medirse contra ground truth independiente (cota, barra de escala,
DWG), NO contra la cifra publicada. Ver docs/BENCHMARK.md.

E16.8 — LO QUE FALTABA. La fórmula era correcta y la pregunta previa no se hacía: ¿`area_px2` y
`area_m2` miden la MISMA región del espacio? El tipo de área publicada (`useful`, `rentable`,
`total`, `unknown`) sólo movía la confianza; no tenía poder de veto, y una escala inválida salía
igual, con un número de aspecto normal. Ahora la inferencia pasa por
`area_semantics.region_compatibility`, y cuando las regiones no se corresponden no hay escala: hay
un motivo. La nota sobre el mercado chileno que vivía en este docstring —a veces se publica útil, a
veces total con prorrateo— dejó de ser una advertencia para el lector y pasó a ser código.
"""
from __future__ import annotations

import math
from typing import Optional

from ..area_semantics import (COMPATIBLE, INCOMPATIBLE, SCALE_CONFIRMED, SCALE_MATCHED_REGION,
                              SCALE_NOT_EVALUATED, UNKNOWN_REGION, AreaObservation,
                              region_compatibility)
from ..schemas.floorplate import Meta, Provenance, Scale, Status


def scale_from_known_area(area_px2: float, area_m2: float, area_kind: str = "unknown",
                          pixel_region: str = UNKNOWN_REGION,
                          declared_region: Optional[str] = None,
                          source: str = "") -> Scale:
    """Escala desde una superficie publicada, SI y sólo si las dos regiones se corresponden.

    - regiones compatibles  → escala inferida con la correspondencia registrada;
    - correspondencia indemostrable → escala inferida marcada como SUPUESTO (es lo que el motor
      hacía siempre, ahora dicho en voz alta);
    - regiones incompatibles → NO hay escala. `px_per_m` queda en None y el valor que habría salido
      se guarda en `rejected_px_per_m`, para trazabilidad, nunca para consumo.
    """
    if area_px2 <= 0 or area_m2 <= 0:
        raise ValueError("áreas deben ser > 0")
    obs = AreaObservation(value_m2=float(area_m2), kind=area_kind, source=source,
                          declared_region=declared_region)
    match = region_compatibility(pixel_region, obs)
    px_per_m = math.sqrt(area_px2 / area_m2)
    common = dict(reference_area_m2=area_m2, pixel_region=pixel_region, area_kind=area_kind,
                  semantic_validity=match.state, semantic_reason=match.reason)

    if match.compatibility == INCOMPATIBLE:
        return Scale(px_per_m=None, method="published_area_rejected", rejected_px_per_m=px_per_m,
                     meta=Meta(confidence=0.0, provenance=Provenance.KNOWN_AREA.value,
                               status=Status.UNKNOWN.value,
                               notes=f"escala NO inferida: {match.reason}. El valor que habría "
                                     f"resultado ({px_per_m:.3f} px/m) queda registrado como "
                                     f"rejected_px_per_m y no debe consumirse"),
                     **common)

    if match.compatibility == COMPATIBLE:
        # La correspondencia está demostrada (por vocabulario o declarada por la fuente). Sigue
        # siendo inferida, no medida: el área publicada podría estar mal.
        conf = 0.8 if match.by_declaration else 0.75
        return Scale(px_per_m=px_per_m, method="published_area_inferred", meta=Meta(
            confidence=conf, provenance=Provenance.KNOWN_AREA.value, status=Status.INFERRED.value,
            notes=f"sqrt({area_px2:.0f}px² / {area_m2} m²); {match.reason}"), **common)

    conf = {"useful": 0.7, "rentable": 0.4, "total": 0.3}.get(area_kind, 0.4)
    return Scale(px_per_m=px_per_m, method="published_area_inferred", meta=Meta(
        confidence=conf, provenance=Provenance.KNOWN_AREA.value, status=Status.INFERRED.value,
        notes=f"sqrt({area_px2:.0f}px² / {area_m2} m²); depende de que {area_m2} m² sea el área del "
              f"polígono segmentado (tipo declarado: {area_kind}); el área resultante NO valida nada"),
        **common)


def scale_manual(px_per_m: float, notes: str = "") -> Scale:
    """Escala medida o declarada por un humano. No pasa por la matriz de regiones porque no divide
    dos áreas: no hay dos regiones que corresponder."""
    return Scale(px_per_m=px_per_m, method="manual", semantic_validity=SCALE_CONFIRMED,
                 semantic_reason="escala declarada por un humano",
                 meta=Meta(confidence=1.0, provenance=Provenance.MANUAL.value,
                           status=Status.CONFIRMED.value, notes=notes))


def scale_unknown() -> Scale:
    return Scale(px_per_m=None, method="unknown", semantic_validity=SCALE_NOT_EVALUATED,
                 semantic_reason="no hay superficie publicada, barra de escala ni cota",
                 meta=Meta(0.0, Provenance.UNKNOWN.value, Status.UNKNOWN.value))
