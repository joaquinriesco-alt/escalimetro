"""VisionInterpreter — interfaz para modelos de visión (VLM).

El VLM NO dibuja geometría. Sólo entrega *hints* localizados en píxeles de la imagen
original, con confidence. La geometría siempre se extrae por CV/segmentación sobre
la imagen real. Así la lógica geométrica no depende del proveedor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass
class Hint:
    kind: str                 # unit_label | unit_region | core | entrance | column | facade | window | scale_bar | dimension_text
    confidence: float
    point: Optional[Point] = None
    bbox: Optional[BBox] = None
    text: str = ""            # texto leído (ej. "543 m²", "OF. 403")
    notes: str = ""
    color_bgr: Optional[Tuple[int, int, int]] = None   # color de relleno asociado (unit_region / legend_swatch)


@dataclass
class VisionResult:
    provider: str
    model: str
    hints: List[Hint] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def of(self, kind: str) -> List[Hint]:
        return [h for h in self.hints if h.kind == kind]

    def best(self, kind: str) -> Optional[Hint]:
        hs = self.of(kind)
        return max(hs, key=lambda h: h.confidence) if hs else None


class VisionInterpreter(ABC):
    """Contrato: dada la imagen y la unidad objetivo, devuelve hints en px de la imagen."""

    name: str = "abstract"

    @abstractmethod
    def interpret(self, image_bgr: np.ndarray, target_unit: str, known_area_m2: Optional[float] = None) -> VisionResult:
        ...


PROMPT_TEMPLATE = """Eres un asistente que lee planos comerciales de oficinas.
Imagen de {w}x{h} px. Unidad objetivo: "{unit}".
Devuelve SOLO JSON con una lista "hints". Cada hint: {{"kind": ..., "confidence": 0..1,
"point": [x,y] | null, "bbox": [x0,y0,x1,y1] | null, "text": "...", "notes": "..."}}.
kinds permitidos: unit_label, unit_region, core, entrance, column, facade, window, scale_bar, dimension_text.
Coordenadas en píxeles de la imagen tal como se entregó. Si no estás seguro, baja la confidence.
No inventes elementos que no ves."""
