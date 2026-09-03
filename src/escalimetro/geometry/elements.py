"""Heurísticas CV para elementos secundarios. Todas devuelven confidence baja/media y
status needs_confirmation: son candidatos, no verdades. El humano confirma o corrige.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import cv2
import numpy as np
from shapely.geometry import LineString, Point as ShPoint, Polygon as ShPolygon

from ..schemas.floorplate import Column, Entrance, FacadeSegment, Meta, Provenance, Status

Point = Tuple[float, float]


def detect_columns(image_bgr: np.ndarray, mask: np.ndarray, px_per_m: float | None,
                   dark_thresh: int = 90, min_m: float = 0.3, max_m: float = 1.2) -> List[Column]:
    """Pilares = manchas oscuras compactas dentro del perímetro con tamaño de 0.3–1.2 m.
    Sin escala, usa 6–40 px. Filtra por solidez para descartar textos."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    dark = ((gray < dark_thresh) & (mask > 0)).astype(np.uint8) * 255
    lo, hi = (min_m * px_per_m, max_m * px_per_m) if px_per_m else (6, 40)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(dark, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if not (lo <= w <= hi and lo <= h <= hi):
            continue
        ar = w / h
        if not 0.6 <= ar <= 1.6:
            continue
        solidity = a / float(w * h)
        if solidity < 0.7:
            continue
        cx, cy = cents[i]
        # excluir manchas pegadas al borde del perímetro (suelen ser muro), pero permitir pilares de fachada
        out.append(Column(center=(float(cx), float(cy)), size_px=float((w + h) / 2), shape="square",
                          meta=Meta(confidence=0.4, provenance=Provenance.CV_HEURISTIC.value,
                                    status=Status.NEEDS_CONFIRMATION.value,
                                    notes=f"blob oscuro {w}x{h}px solidez={solidity:.2f}")))
    return out


def classify_facade_segments(image_bgr: np.ndarray, mask: np.ndarray, ring: Sequence[Point],
                             band_px: int = 30, skip_px: int = 4, sat_thresh: int = 20, ink_thresh: int = 150,
                             samples: int = 9, ray_max_px: int | None = None) -> List[FacadeSegment]:
    """Clasifica cada lado del perímetro por lo que hay en una BANDA exterior (skip_px..band_px
    por la normal exterior), con estadísticas de píxeles, sin depender de líneas finas:

      color_frac  ≥ 0.30 → party_wall  (otra unidad pintada al otro lado: límite de arriendo)
      ink_frac ≥ 0.20 ó ink+hatch ≥ 0.60 → core_wall (tinta densa o achurado gris: núcleo, baños, escaleras)
      white_frac  ≥ 0.70 → facade si rayos hacia afuera llegan al borde sin tinta oscura;
                            corridor si la banda es blanca pero hay muro al frente
      otro               → unknown

    Todas quedan needs_confirmation. La banda se define en px: ajustar band_px ≈ 3 m × px_per_m."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h, w = gray.shape
    poly = ShPolygon(ring)
    n = len(ring)
    segs = []
    for i in range(n):
        a, b = np.array(ring[i]), np.array(ring[(i + 1) % n])
        d = b - a
        L = np.linalg.norm(d)
        if L < 1:
            continue
        nrm = np.array([d[1], -d[0]]) / L
        mid = (a + b) / 2
        if poly.contains(ShPoint(*(mid + nrm * 3))):
            nrm = -nrm
        vals = []
        for t in np.linspace(0.1, 0.9, samples):
            p0 = a + d * t
            for r in range(skip_px, band_px, 2):
                q = p0 + nrm * r
                x, y = int(round(q[0])), int(round(q[1]))
                if 0 <= x < w and 0 <= y < h:
                    if mask[y, x] > 0:
                        continue                              # dentro de la propia unidad (esquinas cóncavas)
                    vals.append((gray[y, x], hsv[y, x, 1], hsv[y, x, 2]))
                else:
                    vals.append((255, 0, 255))               # fuera de la imagen = exterior
        if not vals:
            kind, conf, note = "unknown", 0.2, "sin muestras"
        else:
            v = np.array(vals, dtype=float)
            color_frac = float(np.mean((v[:, 1] > sat_thresh) & (v[:, 2] > 80)))
            ink_frac = float(np.mean(v[:, 0] < ink_thresh))
            white_frac = float(np.mean((v[:, 0] >= 235) & (v[:, 1] <= sat_thresh)))
            mid_frac = float(np.mean((v[:, 0] >= ink_thresh) & (v[:, 0] < 235) & (v[:, 1] <= sat_thresh)))  # achurado/gris
            note = (f"banda {skip_px}-{band_px}px: color={color_frac:.2f} ink={ink_frac:.2f} hatch={mid_frac:.2f} "
                    f"white={white_frac:.2f} len={L:.0f}px")
            if color_frac >= 0.30:
                kind, conf = "party_wall", 0.6
            elif ink_frac >= 0.20 or ink_frac + mid_frac >= 0.60:
                kind, conf = "core_wall", 0.5
            elif white_frac >= 0.70:
                # banda blanca: ¿exterior o pasillo? Rayos hasta ray_max_px (default 4×band ≈ ancho máximo
                # de un pasillo); sólo la tinta oscura (< ink_thresh) bloquea, las líneas grises finas
                # del sitio no. Leyendas/textos lejanos quedan fuera del alcance del rayo.
                clear = 0
                rmax = ray_max_px or 4 * band_px
                for t in np.linspace(0.1, 0.9, samples):
                    p0 = a + d * t
                    hit = False
                    for r in range(band_px, rmax, 3):
                        q = p0 + nrm * r
                        x, y = int(round(q[0])), int(round(q[1]))
                        if not (0 <= x < w and 0 <= y < h):
                            break
                        if gray[y, x] < ink_thresh:
                            hit = True; break
                    clear += 0 if hit else 1
                rays = clear / samples
                note += f" rays_clear={rays:.2f}"
                if rays >= 0.5:
                    kind, conf = "facade", 0.6
                else:
                    kind, conf = "corridor", 0.4   # blanco pero encerrado: pasillo/circulación
            else:
                kind, conf = "unknown", 0.3
        segs.append(FacadeSegment(index=i, start=tuple(map(float, a)), end=tuple(map(float, b)), kind=kind,
                                  meta=Meta(confidence=conf, provenance=Provenance.CV_HEURISTIC.value,
                                            status=Status.NEEDS_CONFIRMATION.value, notes=note)))
    # lados cortos (< band_px) con clasificación 'unknown' entre dos vecinos del mismo tipo: heredan
    # (escalones/retranqueos de una fachada siguen siendo fachada)
    m = len(segs)
    for _ in range(3):   # corridas de varios lados cortos seguidos
        for j, sg in enumerate(segs):
            L = np.hypot(sg.end[0] - sg.start[0], sg.end[1] - sg.start[1])
            if sg.kind == "unknown" and L < band_px and m >= 3:
                # vecinos no-unknown más cercanos hacia atrás y adelante (saltando lados cortos unknown)
                def nb(step):
                    k = j
                    for _s in range(m):
                        k = (k + step) % m
                        if segs[k].kind != "unknown":
                            return segs[k].kind
                        Lk = np.hypot(segs[k].end[0] - segs[k].start[0], segs[k].end[1] - segs[k].start[1])
                        if Lk >= band_px:
                            return "unknown"
                    return "unknown"
                prev_k, next_k = nb(-1), nb(+1)
                if prev_k == next_k and prev_k != "unknown":
                    sg.kind = prev_k
                    sg.meta.confidence = 0.4
                    sg.meta.notes += f"; lado corto: hereda '{prev_k}' de los vecinos"
    return segs


def snap_point_to_ring(p: Point, ring: Sequence[Point]) -> Point:
    line = LineString(list(ring) + [ring[0]])
    q = line.interpolate(line.project(ShPoint(p)))
    return (float(q.x), float(q.y))


def detect_core_enclosed(image_bgr: np.ndarray, unit_mask: np.ndarray, sat_thresh: int = 20,
                         min_frac: float = 0.15, close_px: int = 9) -> List[Tuple[List[Point], float, str]]:
    """Núcleo como VACÍO ENCERRADO por la unión de todas las unidades coloreadas.

    Regla general en planos comerciales de oficinas: las unidades se pintan, el núcleo (ascensores,
    escaleras, baños) se deja sin pintar y queda rodeado por ellas. Se calcula la unión de regiones
    saturadas, se cierra, y los agujeros que superan min_frac del área de la unidad objetivo y tocan
    (o casi) la unidad objetivo son candidatos a core. Devuelve [(ring, confidence, notes)].
    Es candidato, no verdad: needs_confirmation."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    colored = ((hsv[..., 1] > sat_thresh) & (hsv[..., 2] > 80)).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (close_px, close_px))
    colored = cv2.morphologyEx(colored, cv2.MORPH_CLOSE, k)
    # quedarse con componentes grandes (descarta leyenda / muestras)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(colored, 8)
    unit_area = float((unit_mask > 0).sum())
    big = np.zeros_like(colored)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] > 0.05 * unit_area:
            big[lab == i] = 255
    cnts, hier = cv2.findContours(big, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    if hier is None:
        return out
    unit_d = cv2.dilate(unit_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (close_px * 2 + 1,) * 2))
    for i in range(len(cnts)):
        if hier[0][i][3] == -1:
            continue                       # sólo agujeros
        a = cv2.contourArea(cnts[i])
        if a < min_frac * unit_area:
            continue
        hole = np.zeros_like(colored); cv2.drawContours(hole, cnts, i, 255, cv2.FILLED)
        touches = (hole & unit_d).sum() > 0
        if not touches:
            continue
        # limpiar espigas (puertas pintadas, arcos) con apertura y simplificar
        hole = cv2.morphologyEx(hole, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
        hc, _ = cv2.findContours(hole, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not hc:
            continue
        c = max(hc, key=cv2.contourArea)
        eps = 0.012 * cv2.arcLength(c, True)
        ring = [tuple(map(float, p)) for p in cv2.approxPolyDP(c, eps, True).reshape(-1, 2)]
        out.append((ring, 0.5, f"vacío encerrado por unidades coloreadas; área={a:.0f}px² ({a / unit_area:.2f} de la unidad)"))
    return out


def detect_hollow_columns(image_bgr: np.ndarray, mask: np.ndarray, px_per_m: float | None,
                          ink_thresh: int = 175, min_m: float = 0.45, max_m: float = 2.0, upscale: int = 3,
                          exclude_bboxes: Sequence[Tuple[float, float, float, float]] = ()) -> List[Column]:
    """Pilares dibujados como rectángulos HUECOS (contorno de tinta gris con relleno de la unidad).

    En JPG de baja resolución (≈ 8 px/m) el contorno de un pilar mide 1 px y es gris, no negro:
    se trabaja sobre la imagen ampliada ×upscale (cúbica) para que el contorno sea conexo.
    Candidato = componente de tinta con bbox 0.45–2 m, aspecto 0.4–2.5, relleno de bbox ≥ 0.6,
    interior hueco ≥ 0.25 y sin vecinos de texto alineados. Devuelve centros en px originales."""
    up = cv2.resize(image_bgr, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    mask_up = cv2.resize(mask, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
    mask_up = cv2.dilate(mask_up, np.ones((3 * upscale, 3 * upscale), np.uint8))
    ink = ((gray < ink_thresh) & (mask_up > 0)).astype(np.uint8) * 255
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))   # reconectar contornos de 1 px
    lo, hi = ((min_m * px_per_m, max_m * px_per_m) if px_per_m else (4, 20))
    lo, hi = lo * upscale, hi * upscale
    n, lab, stats, cents = cv2.connectedComponentsWithStats(ink, 8)
    cands = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if not (lo <= w <= hi and lo <= h <= hi) or not 0.4 <= w / h <= 2.5:
            continue
        cx, cy = cents[i][0] / upscale, cents[i][1] / upscale
        if any(bx0 - 2 <= cx <= bx1 + 2 and by0 - 2 <= cy <= by1 + 2 for bx0, by0, bx1, by1 in exclude_bboxes):
            continue
        sub = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        filled = sub.copy()
        cnts, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(filled, cnts, -1, 1, cv2.FILLED)
        hollow = (filled.sum() - sub.sum()) / max(1, filled.sum())
        fill_ratio = filled.sum() / float(w * h)
        if fill_ratio < 0.6 or hollow < 0.25:
            continue
        cands.append((cx, cy, w / upscale, h / upscale, hollow))
    all_cc = [(cents[i][0] / upscale, cents[i][1] / upscale, stats[i][2] / upscale, stats[i][3] / upscale)
              for i in range(1, n) if stats[i][4] >= 4 * upscale]
    out = []
    for (cx, cy, w, h, hollow) in cands:
        near = [c for c in all_cc if abs(c[1] - cy) < h * 0.6 and 0 < abs(c[0] - cx) - (w + c[2]) / 2 < 1.0 * w
                and 0.5 <= c[3] / h <= 2.0]
        if near:
            continue
        shape = "square" if 0.8 <= w / h <= 1.25 else "rect"
        out.append(Column(center=(float(cx), float(cy)), size_px=float((w + h) / 2), shape=shape,
                          meta=Meta(confidence=0.5, provenance=Provenance.CV_HEURISTIC.value,
                                    status=Status.NEEDS_CONFIRMATION.value,
                                    notes=f"rectángulo hueco {w:.0f}x{h:.0f}px hueco={hollow:.2f}")))
    return out
