"""Estimación de escala.

Método principal en E01: superficie publicada. px_per_m = sqrt(area_px2 / area_m2).
Esto fija el área por construcción: el error de área contra la superficie publicada es 0
por definición, así que el benchmark de área debe medirse contra ground truth independiente
(otra fuente: cota, barra de escala, plano DWG), NO contra los 543 m². Ver docs/BENCHMARK.md.

Nota sobre 'superficie publicada': en Chile los corredores publican a veces superficie útil,
a veces total (con prorrateo de áreas comunes). Si es total, la escala derivada del polígono
útil queda sesgada. Se registra como unknown hasta confirmar.
"""
from __future__ import annotations

import math
from typing import Optional

from ..schemas.floorplate import Meta, Provenance, Scale, Status


def scale_from_known_area(area_px2: float, area_m2: float, area_kind: str = "unknown") -> Scale:
    """Escala desde una superficie publicada. method = published_area_inferred: la escala DEPENDE
    de que la cifra comercial corresponda al polígono segmentado. Si es arrendable/total, la
    escala queda sesgada (px_per_m demasiado chico → todo se ve más grande de lo que es)."""
    if area_px2 <= 0 or area_m2 <= 0:
        raise ValueError("áreas deben ser > 0")
    px_per_m = math.sqrt(area_px2 / area_m2)
    conf = {"useful": 0.7, "rentable": 0.4, "total": 0.3}.get(area_kind, 0.4)
    return Scale(px_per_m=px_per_m, method="published_area_inferred", reference_area_m2=area_m2,
                 meta=Meta(confidence=conf, provenance=Provenance.KNOWN_AREA.value,
                           status=Status.INFERRED.value,
                           notes=f"sqrt({area_px2:.0f}px² / {area_m2} m²); depende de que {area_m2} m² sea el área del "
                                 f"polígono segmentado (tipo declarado: {area_kind}); el área resultante NO valida nada"))


def scale_manual(px_per_m: float, notes: str = "") -> Scale:
    return Scale(px_per_m=px_per_m, method="manual", meta=Meta(confidence=1.0, provenance=Provenance.MANUAL.value,
                                                                status=Status.CONFIRMED.value, notes=notes))


def scale_unknown() -> Scale:
    return Scale(px_per_m=None, method="unknown", meta=Meta(0.0, Provenance.UNKNOWN.value, Status.UNKNOWN.value))
