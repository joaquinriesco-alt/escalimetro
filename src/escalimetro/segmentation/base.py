"""SegmentationProvider — devuelve una máscara binaria (uint8 0/255) de la unidad objetivo
en el tamaño de la imagen original. El proveedor puede ser OpenCV clásico, SAM2 o un humano.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np

Point = Tuple[float, float]


@dataclass
class SegmentationRequest:
    image_bgr: np.ndarray
    seed_points: Sequence[Point] = ()          # puntos dentro de la unidad (del VLM o del humano)
    bbox: Optional[Tuple[float, float, float, float]] = None
    polygon: Optional[Sequence[Point]] = None  # override humano
    params: Optional[dict] = None


@dataclass
class SegmentationResult:
    mask: np.ndarray            # uint8, 0/255, HxW
    provider: str
    confidence: float
    provenance: str             # valor de schemas.Provenance
    notes: str = ""
    # E16.7 — métricas medidas y parámetros efectivamente usados, incluidos los derivados de la
    # imagen. Se persisten tal cual: un parámetro adaptativo que no queda escrito es un parámetro
    # oculto.
    diagnostics: Optional[dict] = None


class SegmentationProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def segment(self, req: SegmentationRequest) -> SegmentationResult:
        ...
