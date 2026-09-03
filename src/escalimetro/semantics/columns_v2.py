"""Pilares v2 (E03): detección + modulación verificada.

1. Semillas: detector de rectángulos huecos de E02 en varios umbrales de tinta (unión, sin duplicados)
   + detector de manchas oscuras. Alta precisión, recall bajo.
2. Rejilla: los pilares de oficina van en filas y columnas. Se agrupan las x y las y de las semillas
   (tolerancia tol_px); cada salto observado entre grupos es un módulo candidato y se extiende ±1
   salto hacia afuera de los extremos (dentro del bbox de la unidad).
3. Verificación local OBLIGATORIA: en cada intersección de rejilla sin pilar se evalúa un
   "puntaje de rectángulo hueco" sobre la imagen ×3: tinta en el anillo del bbox esperado y claridad
   en el interior. Sólo se agrega si supera el umbral. Nunca se agrega un pilar "porque toca".
Cada pilar lleva evidence[] (seed:hollow / seed:dark / grid:verified) y confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..geometry.elements import detect_columns, detect_hollow_columns

Point = Tuple[float, float]


@dataclass
class ColumnCandidate:
    center: Point
    size_px: float
    confidence: float
    evidence: List[str] = field(default_factory=list)
    status: str = "needs_confirmation"


def _cluster(vals: Sequence[float], tol: float) -> List[float]:
    vals = sorted(vals)
    groups: List[List[float]] = []
    for v in vals:
        if groups and v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [float(np.mean(g)) for g in groups]


def _extend(lines: List[float], lo: float, hi: float) -> Tuple[List[float], Optional[float]]:
    """Extiende la lista de líneas ±1 salto observado, dentro de [lo, hi]. Devuelve (líneas, módulo mínimo)."""
    if len(lines) < 2:
        return lines, None
    gaps = sorted(set(round(float(g)) for g in np.diff(sorted(lines)) if g > 0))
    if not gaps:
        return lines, None
    out = list(lines)
    # cada salto observado es un módulo candidato (69 y 169 px pueden convivir: 1 y 2.5 módulos);
    # la verificación local decide. Se extiende ±1 salto desde cada extremo.
    for module in gaps:
        if min(lines) - module >= lo:
            out.append(min(lines) - module)
        if max(lines) + module <= hi:
            out.append(max(lines) + module)
    return sorted(set(out)), float(min(gaps))


def hollow_rect_score(gray_up: np.ndarray, cx: float, cy: float, w: float, h: float, up: int,
                      ink_thresh: int = 185) -> Tuple[float, float]:
    """Puntaje (ring_ink, interior_light) de un rectángulo hueco centrado en (cx,cy) de w×h px
    originales, buscando el mejor desplazamiento ±3 px."""
    best = (0.0, 0.0)
    H, W = gray_up.shape
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            x0, y0 = int((cx + dx - w / 2) * up), int((cy + dy - h / 2) * up)
            x1, y1 = int((cx + dx + w / 2) * up), int((cy + dy + h / 2) * up)
            if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H or x1 - x0 < 4 or y1 - y0 < 4:
                continue
            patch = gray_up[y0:y1, x0:x1]
            ink = patch < ink_thresh
            t = max(1, up)                                   # grosor del anillo = 1 px original
            ring = np.zeros_like(ink); ring[:t, :] = 1; ring[-t:, :] = 1; ring[:, :t] = 1; ring[:, -t:] = 1
            inner = ~ring.astype(bool)
            ring_ink = float(ink[ring.astype(bool)].mean())
            interior_light = float((~ink)[inner].mean()) if inner.sum() else 0.0
            score = ring_ink * interior_light
            if score > best[0] * best[1]:
                best = (ring_ink, interior_light)
    return best


def detect_columns_v2(image_bgr: np.ndarray, mask: np.ndarray, px_per_m: Optional[float],
                      exclude_bboxes: Sequence = (), tol_px: float = 8.0, up: int = 3,
                      ring_min: float = 0.4, interior_min: float = 0.5) -> List[ColumnCandidate]:
    ppm = px_per_m or 10.0
    seeds: List[ColumnCandidate] = []

    def add(center, size, conf, ev):
        for s in seeds:
            if np.hypot(s.center[0] - center[0], s.center[1] - center[1]) < tol_px:
                s.confidence = max(s.confidence, conf)
                if ev not in s.evidence:
                    s.evidence.append(ev)
                return
        seeds.append(ColumnCandidate((float(center[0]), float(center[1])), float(size), conf, [ev]))

    for th in (165, 175, 190, 200):
        for c in detect_hollow_columns(image_bgr, mask, px_per_m, ink_thresh=th, exclude_bboxes=exclude_bboxes):
            add(c.center, c.size_px, 0.6, f"seed:hollow@{th}")
    for c in detect_columns(image_bgr, mask, px_per_m):
        if not any(bx0 - 2 <= c.center[0] <= bx1 + 2 and by0 - 2 <= c.center[1] <= by1 + 2 for bx0, by0, bx1, by1 in exclude_bboxes):
            add(c.center, c.size_px, 0.5, "seed:dark")
    if len(seeds) >= 2:
        for s in seeds:
            if len(s.evidence) >= 2:
                s.confidence = min(0.8, s.confidence + 0.1)

    # rejilla
    gray_up = cv2.cvtColor(cv2.resize(image_bgr, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2GRAY)
    mask_d = cv2.dilate(mask, np.ones((int(0.6 * ppm) * 2 + 1,) * 2, np.uint8))
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(seeds) < 2:
        return seeds
    xl, xh, yl, yh = xs.min(), xs.max(), ys.min(), ys.max()
    size_w = float(np.median([s.size_px for s in seeds]))
    # tamaño esperado del rectángulo: usar w/h medianos de las semillas huecas si existen
    Xs = _cluster([s.center[0] for s in seeds], tol_px)
    Ys = _cluster([s.center[1] for s in seeds], tol_px)
    Xs, mx = _extend(Xs, xl, xh)
    Ys, my = _extend(Ys, yl, yh)
    grid_ev = []
    for gx in Xs:
        for gy in Ys:
            if any(np.hypot(s.center[0] - gx, s.center[1] - gy) < tol_px * 1.5 for s in seeds):
                continue
            if not (0 <= int(gy) < mask_d.shape[0] and 0 <= int(gx) < mask_d.shape[1]) or mask_d[int(gy), int(gx)] == 0:
                continue
            best = None
            for (w, h) in ((size_w, size_w), (size_w * 0.6, size_w * 1.3), (size_w * 1.3, size_w * 0.6)):
                r_ink, i_light = hollow_rect_score(gray_up, gx, gy, w, h, up)
                if best is None or r_ink * i_light > best[0] * best[1]:
                    best = (r_ink, i_light, w, h)
            r_ink, i_light, w, h = best
            if r_ink >= ring_min and i_light >= interior_min and r_ink * i_light >= 0.3:
                seeds.append(ColumnCandidate((float(gx), float(gy)), float((w + h) / 2),
                                             round(0.35 + 0.3 * min(1.0, (r_ink - ring_min) / 0.4), 2),
                                             [f"grid:intersección x={gx:.0f} y={gy:.0f} (módulo x={mx and round(mx)} y={my and round(my)})",
                                              f"local_rect:ring_ink={r_ink:.2f} interior_light={i_light:.2f}"]))
            else:
                grid_ev.append(f"grid_rejected x={gx:.0f} y={gy:.0f} ring={r_ink:.2f} light={i_light:.2f}")
    seeds.sort(key=lambda s: (s.center[1], s.center[0]))
    for s in seeds:
        s.evidence = [e for e in s.evidence]
    if grid_ev:
        seeds and seeds[0].evidence.append("rejected:" + "; ".join(grid_ev[:6]))
    return seeds
