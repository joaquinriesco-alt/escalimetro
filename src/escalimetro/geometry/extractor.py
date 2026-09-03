"""GeometryExtractor: máscara → contorno → polígono simplificado que preserva quiebres.

Independiente del proveedor de segmentación. Trabaja en píxeles.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np
from shapely.geometry import Polygon as ShPolygon

Point = Tuple[float, float]


@dataclass
class ExtractedGeometry:
    raw_ring: List[Point]
    ring: List[Point]
    area_px2: float
    simplify_eps_px: float
    notes: str = ""


def mask_to_raw_contour(mask: np.ndarray) -> np.ndarray:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        raise ValueError("máscara vacía")
    return max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)


def snap_orthogonal(ring: List[Point], angle_tol_deg: float = 8.0) -> List[Point]:
    """Endereza lados casi horizontales/verticales sin mover los quiebres reales.
    Un lado se considera ortogonal si su ángulo está a < angle_tol de 0/90°.
    Los lados diagonales verdaderos (fachadas curvas o chaflanes) se dejan intactos."""
    pts = [list(p) for p in ring]
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ang = abs(np.degrees(np.arctan2(dy, dx))) % 180
        if ang < angle_tol_deg or ang > 180 - angle_tol_deg:      # horizontal
            y = (a[1] + b[1]) / 2; a[1] = b[1] = y
        elif abs(ang - 90) < angle_tol_deg:                        # vertical
            x = (a[0] + b[0]) / 2; a[0] = b[0] = x
    return [tuple(p) for p in pts]


def simplify_ring(raw: np.ndarray, eps_frac: float = 0.004, snap: bool = True) -> Tuple[List[Point], float]:
    """Douglas-Peucker con epsilon relativo al perímetro. eps_frac=0.004 preserva quiebres
    de ~0.4% del perímetro (≈ 0.4 m en una oficina de 100 m de perímetro)."""
    per = cv2.arcLength(raw.astype(np.float32).reshape(-1, 1, 2), True)
    eps = eps_frac * per
    approx = cv2.approxPolyDP(raw.astype(np.float32).reshape(-1, 1, 2), eps, True).reshape(-1, 2)
    ring = [tuple(map(float, p)) for p in approx]
    if snap:
        ring = snap_orthogonal(ring)
    # eliminar puntos duplicados consecutivos que el snap pueda crear
    out = []
    for p in ring:
        if not out or (abs(p[0] - out[-1][0]) > 0.5 or abs(p[1] - out[-1][1]) > 0.5):
            out.append(p)
    if len(out) > 2 and abs(out[0][0] - out[-1][0]) < 0.5 and abs(out[0][1] - out[-1][1]) < 0.5:
        out.pop()
    return out, eps


class GeometryExtractor:
    """open_px: apertura morfológica (RECT) previa al contorno. Elimina bolsillos y espigas de
    pintura más angostos que open_px (fugas alrededor de montantes de ventana, antialias). Se pierden
    quiebres reales más angostos que open_px: a 8 px/m, 5 px = 0.6 m. Documentado en notes."""

    def __init__(self, eps_frac: float = 0.004, snap: bool = True, open_px: int = 3):
        self.eps_frac = eps_frac
        self.snap = snap
        self.open_px = open_px

    def extract(self, mask: np.ndarray) -> ExtractedGeometry:
        if self.open_px and self.open_px > 1:
            k = cv2.getStructuringElement(cv2.MORPH_RECT, (self.open_px, self.open_px))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
        raw = mask_to_raw_contour(mask)
        ring, eps = simplify_ring(raw, self.eps_frac, self.snap)
        poly = ShPolygon(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)
            ring = [tuple(p) for p in list(poly.exterior.coords)[:-1]]
        return ExtractedGeometry(raw_ring=[tuple(p) for p in raw.tolist()], ring=ring,
                                 area_px2=float(poly.area), simplify_eps_px=float(eps),
                                 notes=f"open_px={self.open_px} DP eps={eps:.2f}px snap={self.snap} n_raw={len(raw)} n={len(ring)}")
