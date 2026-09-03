"""Fachada exterior y luz natural — clasificación por evidencia gráfica, sin asumir fachada = ventana.

Para cada lado del perímetro:
  - lados interiores (party_wall / core_wall / corridor) → `opaque` para efectos de luz (no entra luz
    por ahí), evidencia "interior_boundary". No dice nada del muro físico.
  - lados `facade` → se analiza la BANDA EXTERIOR (2..band_px por la normal, entre la pintura y la
    línea exterior) buscando:
      · montantes: patrón periódico de tinta a lo largo del lado (autocorrelación ≥ 0.33, paso 0.8–4 m, ≥ 2.5 periodos);
      · doble línea: dos mínimos oscuros en el perfil transversal separados 2–8 px;
      · continuidad: fracción del largo con tinta en la banda.
    likely_glazing  = montantes regulares (con o sin doble línea)
    exterior_unknown= fachada sin patrón legible (doble línea sola, o nada)
    opaque          = franja de tinta sólida y gruesa (≥ 3 px) sin montantes
  - `confirmed_glazing` sólo lo pone un humano (override `daylight_confirm`).
  - lados `unknown` → `unknown`.

daylight_priority (0..1) para el motor de layout: confirmed 1.0 · likely 0.75 · exterior_unknown 0.4 ·
unknown 0.2 · opaque 0.0. No hay orientación solar: la flecha norte se registra si el humano la
declara (`north_angle_deg`), nunca se convierte en cálculo solar aquí.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from shapely.geometry import Point as ShPoint, Polygon as ShPolygon

Point = Tuple[float, float]
PRIORITY = {"confirmed_glazing": 1.0, "likely_glazing": 0.75, "exterior_unknown": 0.4, "unknown": 0.2, "opaque": 0.0}


@dataclass
class DaylightSegment:
    index: int
    start: Point
    end: Point
    classification: str
    confidence: float
    daylight_priority: float
    evidence: List[str] = field(default_factory=list)
    facade_kind: str = ""


def _band_profiles(gray, a, b, nrm, band_px):
    """Devuelve (along, across): along[i] = mín gris a lo largo (offsets 2..band); across[o] = mín gris
    del perfil transversal promediado a lo largo."""
    L = int(np.linalg.norm(b - a))
    d = (b - a) / max(L, 1)
    h, w = gray.shape
    M = np.full((L, band_px), 255, np.int32)
    for i in range(L):
        for o in range(band_px):
            q = a + d * i + nrm * o
            x, y = int(round(q[0])), int(round(q[1]))
            if 0 <= x < w and 0 <= y < h:
                M[i, o] = gray[y, x]
    return M


def _periodicity(M: np.ndarray, ppm: float, thresh: int = 150, min_m: float = 0.8, max_m: float = 4.0):
    """Busca un patrón periódico de tinta a lo largo del lado (montantes de ventana) por
    autocorrelación, probando (a) el mínimo de la banda y (b) cada offset por separado — los
    montantes viven a un offset concreto entre la pintura y la línea exterior.
    Devuelve (ac, lag_px, offset, dark_frac) del mejor candidato o None."""
    L = M.shape[0]
    lo, hi = int(min_m * ppm), min(int(max_m * ppm), L // 2)
    if hi <= lo:
        return None
    best = None
    series = [("min", M[:, 2:].min(axis=1))] + [(f"off{o}", M[:, o]) for o in range(2, M.shape[1])]
    for name, col in series:
        s = (col < thresh).astype(float)
        fr = float(s.mean())
        if not (0.1 < fr < 0.8):
            continue
        s -= s.mean()
        if s.std() == 0:
            continue
        ac = np.correlate(s, s, "full")[L - 1:]
        ac = ac / ac[0]
        lag = lo + int(np.argmax(ac[lo:hi + 1]))
        if best is None or ac[lag] > best[0]:
            best = (float(ac[lag]), int(lag), name, fr)
    return best


def classify_daylight(image_bgr: np.ndarray, ring: Sequence[Point], facade_segments, px_per_m: Optional[float],
                      band_px: int = 18, tick_thresh: int = 120) -> List[DaylightSegment]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    poly = ShPolygon(ring)
    out = []
    for seg in facade_segments:
        a, b = np.array(seg.start, float), np.array(seg.end, float)
        L = float(np.linalg.norm(b - a))
        if L < 1:
            continue
        if seg.kind in ("party_wall", "core_wall", "corridor"):
            out.append(DaylightSegment(seg.index, seg.start, seg.end, "opaque", 0.6, PRIORITY["opaque"],
                                       [f"interior_boundary:{seg.kind}"], seg.kind))
            continue
        if seg.kind != "facade":
            out.append(DaylightSegment(seg.index, seg.start, seg.end, "unknown", 0.2, PRIORITY["unknown"],
                                       ["lado sin clasificar"], seg.kind))
            continue
        d = (b - a) / L
        nrm = np.array([d[1], -d[0]])
        if poly.contains(ShPoint(*((a + b) / 2 + nrm * 3))):
            nrm = -nrm
        M = _band_profiles(gray, a, b, nrm, band_px)
        along = M[:, 2:].min(axis=1)                       # tinta más oscura en la banda, por posición
        across = np.median(M, axis=0)                      # perfil transversal típico
        ev: List[str] = []
        # montantes: periodicidad por autocorrelación (ac ≥ 0.33, paso 0.8–4 m, ≥ 2.5 periodos en el lado)
        ppm = px_per_m or 10.0
        per = _periodicity(M, ppm)
        regular = False
        if per is not None:
            ac, lag, name, fr = per
            periods = L / lag
            if ac >= 0.33 and periods >= 2.5:
                regular = True
                ev.append(f"mullions:paso {lag}px ({lag / ppm:.2f} m), autocorr {ac:.2f}, {periods:.1f} periodos, serie {name}")
            else:
                ev.append(f"no_periodic:mejor autocorr {ac:.2f} a {lag}px ({periods:.1f} periodos)")
        peaks = [1] if regular else []
        # doble línea transversal
        dark_o = [o for o in range(len(across)) if across[o] < 150]
        runs = []
        for o in dark_o:
            if runs and o - runs[-1][-1] <= 1:
                runs[-1].append(o)
            else:
                runs.append([o])
        if len(runs) >= 2 and 2 <= (runs[1][0] - runs[0][-1]) <= 8:
            ev.append(f"double_line:sep {runs[1][0] - runs[0][-1]}px")
        thick_solid = any(len(r) >= 3 for r in runs) and float(np.mean(along < 150)) > 0.85
        continuity = float(np.mean(M[:, 2:].min(axis=1) < 200))
        ev.append(f"ink_continuity:{continuity:.2f}")
        if regular:
            conf = 0.5 + 0.3 * min(1.0, (per[0] - 0.33) / 0.3) + (0.1 if any(e.startswith("double_line") for e in ev) else 0.0)
            cls = "likely_glazing"
        elif thick_solid and not peaks:
            cls, conf = "opaque", 0.5
            ev.append("solid_thick_wall")
        else:
            cls, conf = "exterior_unknown", 0.4
        out.append(DaylightSegment(seg.index, seg.start, seg.end, cls, round(conf, 2), PRIORITY[cls], ev, seg.kind))
    return out
