"""original | Planta Escalímetro, y overlay de verificación (perímetro sobre el original).

Rasteriza el SVG con cairosvg si existe; si no, dibuja la geometría con OpenCV.
El overlay es la prueba de fidelidad: la geometría se dibuja SOBRE la imagen original,
lo que hace imposible "imitar" sin coincidir.
"""
from __future__ import annotations

import cv2
import numpy as np

from ..schemas.floorplate import Floorplate
from .svg import render_svg


def _svg_to_bgr(svg: str, width: int) -> np.ndarray:
    try:
        import cairosvg
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=width)
        arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if arr is not None:
            return arr
    except Exception:
        pass
    return None


def _raster_fallback(fp: Floorplate, width: int) -> np.ndarray:
    ring = np.array(fp.perimeter.ring)
    x0, y0 = ring.min(0); x1, y1 = ring.max(0)
    s = (width - 80) / max(x1 - x0, 1)
    h = int((y1 - y0) * s + 120)
    img = np.full((h, width, 3), 255, np.uint8)
    tf = lambda p: (int(40 + (p[0] - x0) * s), int(40 + (p[1] - y0) * s))  # noqa: E731
    cv2.fillPoly(img, [np.array([tf(p) for p in fp.perimeter.ring], np.int32)], (250, 246, 242))
    cv2.polylines(img, [np.array([tf(p) for p in fp.perimeter.ring], np.int32)], True, (17, 17, 17), 2)
    for c in fp.core:
        cv2.fillPoly(img, [np.array([tf(p) for p in c.ring], np.int32)], (221, 221, 221))
        cv2.polylines(img, [np.array([tf(p) for p in c.ring], np.int32)], True, (17, 17, 17), 2)
    for col in fp.columns:
        cv2.rectangle(img, (tf(col.center)[0] - 4, tf(col.center)[1] - 4), (tf(col.center)[0] + 4, tf(col.center)[1] + 4), (17, 17, 17), -1)
    for e in fp.entrances:
        cv2.circle(img, tf(e.point), 7, (40, 39, 214), 2)
    cv2.putText(img, f"{fp.unit_label} {fp.area_m2 or '?'} m2 (raster fallback)", (40, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    return img


def overlay_on_original(image_bgr: np.ndarray, fp: Floorplate, only_perimeter: bool = False, upscale: int = 2) -> np.ndarray:
    """Geometría dibujada SOBRE el original (ampliado ×upscale para que las líneas de 1 px no tapen
    el dibujo). Es la prueba de fidelidad: el contorno debe seguir la unidad."""
    img = cv2.resize(image_bgr, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    P = lambda ring: [np.array([(x * upscale, y * upscale) for x, y in ring], np.int32)]  # noqa: E731
    cv2.polylines(img, P(fp.perimeter.ring), True, (0, 0, 255), 2)
    for hh in fp.holes:
        cv2.polylines(img, P(hh.ring), True, (0, 0, 255), 2)
    for (x, y) in fp.perimeter.ring:
        cv2.circle(img, (int(x * upscale), int(y * upscale)), 3, (0, 0, 255), -1)
    if only_perimeter:
        return img
    for c in fp.core:
        cv2.polylines(img, P(c.ring), True, (0, 160, 0), 2)
    for col in fp.columns:
        x, y = int(col.center[0] * upscale), int(col.center[1] * upscale)
        r = int(max(4, col.size_px * upscale / 2))
        cv2.rectangle(img, (x - r, y - r), (x + r, y + r), (255, 0, 0), 2)
    for e in fp.entrances:
        cv2.circle(img, (int(e.point[0] * upscale), int(e.point[1] * upscale)), 9, (0, 0, 255), 2)
    for wn in fp.windows:
        cv2.line(img, (int(wn.start[0] * upscale), int(wn.start[1] * upscale)), (int(wn.end[0] * upscale), int(wn.end[1] * upscale)), (200, 120, 0), 3)
    return img


def _overlay_legacy(image_bgr: np.ndarray, fp: Floorplate) -> np.ndarray:
    img = image_bgr.copy()
    cv2.polylines(img, [np.array(fp.perimeter.ring, np.int32)], True, (0, 0, 255), 2)
    for c in fp.core:
        cv2.polylines(img, [np.array(c.ring, np.int32)], True, (0, 160, 0), 2)
    for col in fp.columns:
        x, y = map(int, col.center)
        cv2.rectangle(img, (x - 5, y - 5), (x + 5, y + 5), (255, 0, 0), 1)
    for e in fp.entrances:
        cv2.circle(img, tuple(map(int, e.point)), 8, (0, 0, 255), 2)
    for w in fp.windows:
        cv2.line(img, tuple(map(int, w.start)), tuple(map(int, w.end)), (200, 120, 0), 3)
    return img


def side_by_side(image_bgr: np.ndarray, fp: Floorplate, panel_width: int = 1000) -> np.ndarray:
    svg = render_svg(fp, width_px=panel_width)
    right = _svg_to_bgr(svg, panel_width)
    if right is None:
        right = _raster_fallback(fp, panel_width)
    h0, w0 = image_bgr.shape[:2]
    left = cv2.resize(image_bgr, (panel_width, int(h0 * panel_width / w0)))
    H = max(left.shape[0], right.shape[0]) + 40
    canvas = np.full((H, panel_width * 2 + 30, 3), 255, np.uint8)
    canvas[40:40 + left.shape[0], :panel_width] = left
    canvas[40:40 + right.shape[0], panel_width + 30:] = right
    cv2.putText(canvas, "ORIGINAL", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.putText(canvas, "PLANTA ESCALIMETRO (geometria estructurada)", (panel_width + 40, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return canvas


def contour_svg(ring, w, h, stroke="#111", title="", raw=None) -> str:
    """SVG mínimo en px de la imagen: un contorno (y opcionalmente el crudo en rojo detrás)."""
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<rect width="100%" height="100%" fill="#fff"/>']
    if title:
        parts.append(f'<text x="6" y="14" font-size="11" font-family="Helvetica,Arial" fill="#666">{title} · {len(ring)} vértices</text>')
    if raw:
        parts.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in raw) + '" fill="none" stroke="#e33" stroke-width="0.7" opacity="0.7"/>')
    parts.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in ring) + f'" fill="none" stroke="{stroke}" stroke-width="1.5"/>')
    for (x, y) in ring:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.8" fill="{stroke}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def geometry_only(fp: Floorplate, width: int = 1600) -> np.ndarray:
    """Planta Escalímetro grande, sólo geometría (para revisión humana)."""
    svg = render_svg(fp, width_px=width)
    img = _svg_to_bgr(svg, width)
    return img if img is not None else _raster_fallback(fp, width)


def comparison_three(image_bgr: np.ndarray, fp: Floorplate, panel_width: int = 900,
                     source_name: str = "") -> np.ndarray:
    """ORIGINAL | OVERLAY | PLANTA ESCALÍMETRO — la imagen principal de revisión humana.

    E16.1 §19 — el panel izquierdo se rotulaba `"ORIGINAL GPS"`, así que la revisión de cualquier
    inmueble decía GPS. Ahora el rótulo es `ORIGINAL` y, si el caller declara la fuente real,
    `ORIGINAL · <fuente>`. No se mapea `GPS Property → GPS` para conservar el literal antiguo: eso
    sería otro hardcode."""
    h0, w0 = image_bgr.shape[:2]
    left = cv2.resize(image_bgr, (panel_width, int(h0 * panel_width / w0)), interpolation=cv2.INTER_CUBIC)
    ov = overlay_on_original(image_bgr, fp)
    mid = cv2.resize(ov, (panel_width, int(h0 * panel_width / w0)), interpolation=cv2.INTER_CUBIC)
    svg = render_svg(fp, width_px=panel_width)
    right = _svg_to_bgr(svg, panel_width)
    if right is None:
        right = _raster_fallback(fp, panel_width)
    H = max(left.shape[0], mid.shape[0], right.shape[0]) + 44
    gap = 24
    canvas = np.full((H, panel_width * 3 + gap * 2, 3), 255, np.uint8)
    original = f"ORIGINAL · {source_name}" if source_name else "ORIGINAL"
    for i, (panel, title) in enumerate([(left, original), (mid, "OVERLAY (geometria sobre el original)"),
                                        (right, "PLANTA ESCALIMETRO")]):
        x = i * (panel_width + gap)
        canvas[44:44 + panel.shape[0], x:x + panel_width] = panel
        cv2.putText(canvas, title, (x + 8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return canvas
