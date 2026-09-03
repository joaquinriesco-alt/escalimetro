"""E06 — Modelo de incertidumbre de escala.

La escala nominal (8.36 px/m) sale de published_area_inferred = 543 m² y es LOW. Un ScaleScenario aplica un
factor a las dimensiones métricas del shell (px_per_m / factor ⇒ metros × factor, áreas × factor²). Módulos,
programa, clearances y tamaño físico de pilares (0.8 m) NO cambian: sólo cambia cuánto mide el shell."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from ...schemas.floorplate import Floorplate
from ..model import ShellM
from ..shell_adapter import shell_from_floorplate

DEFAULT_FACTORS = [0.95, 0.975, 0.99, 1.00, 1.01, 1.025, 1.05]


@dataclass
class ScaleScenario:
    scale_factor: float
    px_per_m: float
    implied_shell_area_m2: float           # usable × factor²
    implied_published_equiv_m2: float      # 543 × factor² (lo que "diría" el aviso si esta fuera la escala)
    source: str
    confidence: str
    layout_result: Dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


SCENARIO_SCHEMA = {
    "type": "object",
    "required": ["scale_factor", "px_per_m", "implied_shell_area_m2", "implied_published_equiv_m2", "source", "confidence", "layout_result"],
    "properties": {"scale_factor": {"type": "number", "minimum": 0.5, "maximum": 2.0}, "px_per_m": {"type": "number"},
                   "implied_shell_area_m2": {"type": "number"}, "implied_published_equiv_m2": {"type": "number"},
                   "source": {"type": "string"}, "confidence": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                   "layout_result": {"type": "object"}},
}


def scaled_shell(fp: Floorplate, factor: float) -> ShellM:
    """Shell métrico con la escala nominal multiplicada por `factor` (factor > 1 ⇒ planta más grande)."""
    import copy
    fp2 = copy.deepcopy(fp)
    fp2.scale.px_per_m = fp.scale.px_per_m / factor
    return shell_from_floorplate(fp2)


def make_scenario(fp: Floorplate, factor: float, published_m2: float = 543.0) -> ScaleScenario:
    sh = scaled_shell(fp, factor)
    return ScaleScenario(scale_factor=factor, px_per_m=round(fp.scale.px_per_m / factor, 4),
                         implied_shell_area_m2=round(sh.usable.area, 1),
                         implied_published_equiv_m2=round(published_m2 * factor * factor, 1),
                         source=f"published_area_inferred × {factor}", confidence="LOW")
