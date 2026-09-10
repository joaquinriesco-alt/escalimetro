"""E24 §14 — confirmación humana de escala.

Vía PRIMARIA: el usuario marca dos puntos sobre la imagen y declara cuántos metros hay entre ellos.

    px_per_m = |AB| en píxeles / distancia_real_m

Vía SECUNDARIA: el usuario escribe px/m directamente. Se acepta, pero es peor: nadie puede
reproducirla ni discutirla; sólo se puede creerle.

Lo que E24 §14 prohíbe explícitamente y aquí NO existe: leer cotas del dibujo, leer la barra de
escala, inferir la escala desde el área publicada como si estuviera confirmada. Los datos crudos
(A, B, distancia) se guardan para poder reproducir el número más tarde."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

USER_CONFIRMED_DISTANCE = "USER_CONFIRMED_DISTANCE"
USER_DECLARED_PX_PER_M = "USER_DECLARED_PX_PER_M"


class ScaleConfirmationError(ValueError):
    pass


@dataclass(frozen=True)
class ScaleConfirmation:
    method: str                      # two_point_distance | px_per_m
    px_per_m: float
    provenance: str
    point_a_px: Optional[Sequence[float]] = None
    point_b_px: Optional[Sequence[float]] = None
    real_distance_m: Optional[float] = None
    pixel_distance: Optional[float] = None
    note: str = ""

    @classmethod
    def from_two_points(cls, a: Sequence[float], b: Sequence[float], real_distance_m: float,
                        note: str = "") -> "ScaleConfirmation":
        if real_distance_m is None or float(real_distance_m) <= 0:
            raise ScaleConfirmationError(f"distancia real inválida: {real_distance_m}")
        d = math.dist((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))
        if d <= 0:
            raise ScaleConfirmationError("los dos puntos de la escala son el mismo punto")
        return cls("two_point_distance", d / float(real_distance_m), USER_CONFIRMED_DISTANCE,
                   [float(a[0]), float(a[1])], [float(b[0]), float(b[1])], float(real_distance_m), d, note)

    @classmethod
    def from_px_per_m(cls, px_per_m: float, note: str = "") -> "ScaleConfirmation":
        if px_per_m is None or float(px_per_m) <= 0:
            raise ScaleConfirmationError(f"px_per_m inválido: {px_per_m}")
        return cls("px_per_m", float(px_per_m), USER_DECLARED_PX_PER_M, note=note or
                   "vía secundaria: el usuario declaró px/m sin dos puntos; no es reproducible")

    @classmethod
    def from_case(cls, d: Optional[Dict]) -> Optional["ScaleConfirmation"]:
        """Lee `scale_confirmation` de case.json. Ausente → None (no hay confirmación humana)."""
        if not d:
            return None
        m = d.get("method")
        if m == "two_point_distance":
            return cls.from_two_points(d["point_a_px"], d["point_b_px"], d["real_distance_m"],
                                       d.get("note", ""))
        if m == "px_per_m":
            return cls.from_px_per_m(d["px_per_m"], d.get("note", ""))
        raise ScaleConfirmationError(f"método de confirmación de escala desconocido: {m!r}")

    def to_dict(self) -> Dict:
        out = {"method": self.method}
        if self.point_a_px is not None:
            out["point_a_px"] = list(self.point_a_px)
            out["point_b_px"] = list(self.point_b_px)
            out["real_distance_m"] = self.real_distance_m
            out["pixel_distance"] = round(float(self.pixel_distance), 4)
        out["px_per_m"] = round(float(self.px_per_m), 6)
        if self.note:
            out["note"] = self.note
        return out
