"""Candidatos de acceso — evidencia combinada, sin coordenadas de ningún caso.

Un acceso a una unidad de oficina está, casi siempre, en el límite entre la unidad y la
circulación común (núcleo, pasillo). Sobre ese límite buscamos:

  A. topología      — el lado del perímetro es `core_wall` o `corridor` (no fachada, no otra unidad);
  B. interrupción   — la línea de muro (tinta) se corta en un tramo de 0.5–2.5 m;
  C. símbolo        — hay tinta pequeña (hoja/arco de puerta) junto al hueco, del lado de la unidad;
  D. intrusión      — la pintura de la unidad entra en el hueco (la máscara cruda sobresale de la abierta);
  E. circulación    — el hueco está frente a un lobby/eje del núcleo (más cerca del centro del lado del núcleo).

Cada candidato lista sus evidencias; la confianza es la suma de pesos. `primary` se propone sólo
si hay un candidato claramente mejor; si dos empatan (accesos simétricos), ambos quedan
`primary` con status needs_confirmation y el humano elige.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from shapely.geometry import Point as ShPoint, Polygon as ShPolygon

Point = Tuple[float, float]

WEIGHTS = {"topology": 0.15, "wall_gap": 0.30, "door_symbol": 0.25, "paint_intrusion": 0.15,
           "door_width_typical": 0.10, "circulation_axis": 0.05}


@dataclass
class EntranceCandidate:
    point: Point
    kind: str                      # primary | secondary | unknown
    confidence: float
    evidence: List[str] = field(default_factory=list)
    width_px: Optional[float] = None
    segment_index: Optional[int] = None


def _profile_along(gray: np.ndarray, a: np.ndarray, b: np.ndarray, nrm: np.ndarray, offsets: Sequence[int]) -> np.ndarray:
    """Para cada px a lo largo de a→b, mínimo de gris en las posiciones a + t·d + o·nrm (o en offsets)."""
    L = int(np.linalg.norm(b - a))
    d = (b - a) / max(L, 1)
    h, w = gray.shape
    prof = np.full(L, 255, np.int32)
    for i in range(L):
        p = a + d * i
        vals = []
        for o in offsets:
            q = p + nrm * o
            x, y = int(round(q[0])), int(round(q[1]))
            if 0 <= x < w and 0 <= y < h:
                vals.append(int(gray[y, x]))
        prof[i] = min(vals) if vals else 255
    return prof


def _runs(mask1d: np.ndarray) -> List[Tuple[int, int]]:
    runs, start = [], None
    for i, v in enumerate(mask1d):
        if v and start is None:
            start = i
        if not v and start is not None:
            runs.append((start, i)); start = None
    if start is not None:
        runs.append((start, len(mask1d)))
    return runs


def detect_entrance_candidates(image_bgr: np.ndarray, ring: Sequence[Point], facade_segments, core_rings,
                               raw_mask: Optional[np.ndarray], opened_mask: Optional[np.ndarray],
                               px_per_m: Optional[float], wall_thresh: int = 130,
                               min_m: float = 0.5, max_m: float = 2.5) -> List[EntranceCandidate]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    ppm = px_per_m or 10.0
    lo, hi = int(min_m * ppm), int(max_m * ppm)
    poly = ShPolygon(ring)
    n = len(ring)
    intr = None
    if raw_mask is not None and opened_mask is not None:
        intr = ((raw_mask > 0) & (opened_mask == 0)).astype(np.uint8)
    core_centers = [np.mean(np.array(c), axis=0) for c in core_rings] if core_rings else []
    cands: List[EntranceCandidate] = []
    for seg in facade_segments:
        if seg.kind not in ("core_wall", "corridor"):
            continue
        a, b = np.array(seg.start, float), np.array(seg.end, float)
        L = np.linalg.norm(b - a)
        if L < lo:
            continue
        d = (b - a) / L
        nrm = np.array([d[1], -d[0]])
        if poly.contains(ShPoint(*((a + b) / 2 + nrm * 3))):
            nrm = -nrm                                    # exterior
        # B. perfil del muro (0..6 px hacia afuera: el muro está justo fuera de la pintura)
        prof = _profile_along(gray, a, b, nrm, offsets=range(0, 7))
        absent = prof >= wall_thresh
        # una hoja de puerta dibujada cruza el hueco con 1–2 px de tinta: cerrar huecos de ≤ 2 px
        absent = cv2.morphologyEx(absent.astype(np.uint8).reshape(1, -1), cv2.MORPH_CLOSE, np.ones((1, 3), np.uint8)).reshape(-1) > 0
        for (s, e) in _runs(absent):
            ln = e - s
            if not (lo <= ln <= hi):
                continue
            if s == 0 or e == len(prof):
                continue                                   # el hueco toca un vértice: probablemente esquina, no puerta
            mid = a + d * ((s + e) / 2)
            ev = ["topology:" + seg.kind, f"wall_gap:{ln}px"]
            conf = WEIGHTS["topology"] + WEIGHTS["wall_gap"]
            # C. símbolo de puerta: tinta pequeña del lado interior, junto al hueco
            x0, y0 = mid - nrm * 12 - d * (ln / 2 + 4), mid + nrm * 2 + d * (ln / 2 + 4)
            X0, X1 = int(max(0, min(x0[0], y0[0]))), int(min(w, max(x0[0], y0[0])))
            Y0, Y1 = int(max(0, min(x0[1], y0[1]))), int(min(h, max(x0[1], y0[1])))
            if X1 > X0 and Y1 > Y0:
                win = (gray[Y0:Y1, X0:X1] < 150).astype(np.uint8)
                # excluir la franja del propio muro (offset 0..2)
                ncc, lab, stats, _ = cv2.connectedComponentsWithStats(win, 8)
                symbols = [i for i in range(1, ncc) if 2 <= stats[i, cv2.CC_STAT_AREA] <= 40
                           and max(stats[i, 2], stats[i, 3]) <= max(4, ln + 2)]
                if symbols:
                    ev.append(f"door_symbol:{len(symbols)} trazos pequeños junto al hueco")
                    conf += WEIGHTS["door_symbol"]
            # D. intrusión de pintura
            if intr is not None:
                gx, gy = int(round(mid[0])), int(round(mid[1]))
                r = max(3, ln // 2)
                patch = intr[max(0, gy - r):gy + r, max(0, gx - r):gx + r]
                if patch.sum() >= 3:
                    ev.append(f"paint_intrusion:{int(patch.sum())}px")
                    conf += WEIGHTS["paint_intrusion"]
            # ancho típico de puerta 0.7–1.5 m
            if px_per_m and 0.7 * ppm <= ln <= 1.5 * ppm:
                ev.append("door_width_typical")
                conf += WEIGHTS["door_width_typical"]
            # E. eje de circulación: cerca del centro del lado del núcleo o del centro del core
            if core_centers:
                dist_axis = min(abs(np.dot(mid - c, d)) for c in core_centers)
                if dist_axis < 0.35 * L:
                    ev.append("circulation_axis")
                    conf += WEIGHTS["circulation_axis"]
            cands.append(EntranceCandidate(point=(float(mid[0]), float(mid[1])), kind="unknown",
                                           confidence=round(min(conf, 0.95), 2), evidence=ev,
                                           width_px=float(ln), segment_index=seg.index))
    cands.sort(key=lambda c: -c.confidence)
    if cands:
        best = cands[0].confidence
        for c in cands:
            if c.confidence >= 0.5 and c.confidence >= best - 0.1:
                c.kind = "primary"
            elif c.confidence >= 0.35:
                c.kind = "secondary"
    return cands


def choose_primary(cands: List[EntranceCandidate]) -> Tuple[Optional[EntranceCandidate], str, str]:
    """Devuelve (candidato, status, nota). status = inferred si hay un ganador claro,
    needs_confirmation si hay empate o baja confianza, unknown si no hay candidatos."""
    prim = [c for c in cands if c.kind == "primary"]
    if not prim:
        return (None, "unknown", "sin candidato con confianza ≥ 0.5")
    if len(prim) == 1 and prim[0].confidence >= 0.7:
        return (prim[0], "inferred", "ganador claro")
    return (prim[0], "needs_confirmation",
            f"{len(prim)} candidatos empatados (Δconf < 0.1): accesos simétricos o ambiguos; el humano elige")
