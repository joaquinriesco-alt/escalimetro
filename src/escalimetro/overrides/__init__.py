"""Human-in-the-loop: overrides.json por caso.

Formato (todas las claves opcionales; coordenadas en px de original.jpg):

{
  "seed_points": [[x, y]],              # puntos dentro de la unidad → segmentación
  "segmentation_params": {"tol": 12},   # parámetros del provider
  "perimeter": {"ring": [[x,y],...]},   # reemplaza la máscara/perímetro completo
  "known_area": {"m2": 543, "kind": "useful|total|unknown"},
  "scale": {"px_per_m": 12.3},          # fuerza escala
  "core": [{"ring": [[x,y],...], "kind": "core"}],
  "entrances": [{"point": [x,y], "kind": "main", "width_px": 20}],
  "columns": {"replace": false, "add": [{"center": [x,y], "size_px": 10}], "remove_near": [[x,y]]},
  "windows": [{"start": [x,y], "end": [x,y]}],
  "facade_kinds": {"3": "facade", "7": "party_wall"},   # por índice de segmento
  "fixed_elements": [{"ring": [...], "kind": "wc", "label": "baño"}],
  "vision_hints": [ {...Hint...} ]      # hints manuales para ManualVisionInterpreter
}

Un override es siempre provenance=manual, confidence=1, status=confirmed.
Script auxiliar: `escalimetro annotate` (renderer/annotate.py) genera un PNG con grilla
de coordenadas para leer px a ojo sin editor.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Overrides:
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | None) -> "Overrides":
        if not path or not os.path.exists(path):
            return cls({})
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def has(self, key: str) -> bool:
        return key in self.data and self.data[key] not in (None, [], {})
