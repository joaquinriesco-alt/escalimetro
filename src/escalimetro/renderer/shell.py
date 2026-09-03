"""Render del SHELL semántico: Planta Escalímetro + acceso principal/secundario + fachada exterior +
segmentos de luz probable + pilares con estado + leyenda de confidence. Sin mobiliario."""
from __future__ import annotations

import cv2
import numpy as np

from ..schemas.floorplate import Floorplate
from .side_by_side import _raster_fallback, _svg_to_bgr, overlay_on_original
from .svg import _centroid

DAYLIGHT_STYLE = {"confirmed_glazing": ("#1f77b4", 7, ""), "likely_glazing": ("#4c9fd8", 6, ""),
                  "exterior_unknown": ("#9ecae1", 5, ' stroke-dasharray="6,5"'), "opaque": ("#444", 3, ""),
                  "unknown": ("#bbb", 3, ' stroke-dasharray="2,3"')}


def render_shell_svg(fp: Floorplate, width_px: int = 1400, margin: float = 48) -> str:
    ring = fp.perimeter.ring
    conv = fp.to_m if fp.scale.px_per_m else (lambda p: (p[0], p[1]))
    flip = bool(fp.scale.px_per_m)
    all_pts = list(ring) + [p for c in fp.core for p in c.ring]
    pts = [conv(p) for p in all_pts]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = (width_px - 2 * margin) / ((x1 - x0) or 1)
    legend_h = 150
    height = (y1 - y0) * s + 2 * margin + legend_h

    def tf(p):
        x, y = conv(p)
        return margin + (x - x0) * s, margin + ((y1 - y) if flip else (y - y0)) * s

    P = lambda r: " ".join(f"{x:.1f},{y:.1f}" for x, y in map(tf, r))  # noqa: E731
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height:.0f}" viewBox="0 0 {width_px} {height:.0f}" '
         f'font-family="Helvetica,Arial,sans-serif">', '<rect width="100%" height="100%" fill="#fff"/>',
         f'<polygon points="{P(ring)}" fill="#fafafa" stroke="none"/>']
    # luz / fachada: banda desplazada 7 px hacia afuera del perímetro para no tapar la línea negra
    from shapely.geometry import Point as ShPoint, Polygon as ShPolygon
    svg_poly = ShPolygon([tf(p) for p in ring])
    for d in fp.daylight_segments:
        col, wdt, dash = DAYLIGHT_STYLE.get(d.classification, DAYLIGHT_STYLE["unknown"])
        (ax, ay), (bx, by) = tf(d.start), tf(d.end)
        L = max(1e-6, ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5)
        nx, ny = (by - ay) / L, -(bx - ax) / L
        if svg_poly.contains(ShPoint((ax + bx) / 2 + nx * 3, (ay + by) / 2 + ny * 3)):
            nx, ny = -nx, -ny
        off = 7 if d.classification != "opaque" else 4
        op = 0.5 + 0.5 * d.confidence
        o.append(f'<line x1="{ax+nx*off:.1f}" y1="{ay+ny*off:.1f}" x2="{bx+nx*off:.1f}" y2="{by+ny*off:.1f}" stroke="{col}" '
                 f'stroke-width="{wdt}" opacity="{op:.2f}" stroke-linecap="round"{dash}/>')
    # perímetro y core
    dash = "" if fp.perimeter.meta.status == "confirmed" else ' stroke-dasharray="6,4"'
    o.append(f'<polygon points="{P(ring)}" fill="none" stroke="#111" stroke-width="2.2"{dash}/>')
    for c in fp.core:
        dash = "" if c.meta.status == "confirmed" else ' stroke-dasharray="6,4"'
        o.append(f'<polygon points="{P(c.ring)}" fill="#dcdcdc" stroke="#333" stroke-width="1.8"{dash}/>')
        cx, cy = tf(_centroid(c.ring))
        o.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="13" text-anchor="middle" fill="#333">CORE</text>')
    # pilares
    for c in fp.column_candidates or []:
        cx, cy = tf(c.center)
        r = max(4.0, c.size_px * s / (fp.scale.px_per_m or 1) / 2) if fp.scale.px_per_m else max(4.0, c.size_px * s / 2)
        if c.status == "confirmed":
            o.append(f'<rect x="{cx-r:.1f}" y="{cy-r:.1f}" width="{2*r:.1f}" height="{2*r:.1f}" fill="#111"/>')
        else:
            o.append(f'<rect x="{cx-r:.1f}" y="{cy-r:.1f}" width="{2*r:.1f}" height="{2*r:.1f}" fill="#fff" stroke="#111" stroke-width="1.5" stroke-dasharray="3,2"/>')
            o.append(f'<text x="{cx+r+2:.1f}" y="{cy+4:.1f}" font-size="9" fill="#666">{c.confidence:.2f}</text>')
    # accesos
    for c in fp.entrance_candidates or []:
        is_p = fp.primary_entrance is not None and c.point == fp.primary_entrance.point
        ex, ey = tf(c.point)
        if is_p:
            dash = "" if c.status == "confirmed" else ' stroke-dasharray="3,2"'
            o.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="9" fill="#fff" stroke="#d62728" stroke-width="3"{dash}/>')
            o.append(f'<text x="{ex+12:.1f}" y="{ey-10:.1f}" font-size="12" fill="#d62728" font-weight="bold">ACCESO PRINCIPAL {c.confidence:.2f}</text>')
        elif c.kind in ("primary", "secondary"):
            o.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="6" fill="#fff" stroke="#e8888b" stroke-width="2" stroke-dasharray="3,2"/>')
            o.append(f'<text x="{ex+9:.1f}" y="{ey+4:.1f}" font-size="10" fill="#c66">cand. {c.confidence:.2f}</text>')
    # leyenda
    ly = height - legend_h + 18
    r = fp.shell_readiness
    o.append(f'<text x="{margin}" y="{ly:.0f}" font-size="14" fill="#111">{fp.unit_label} · shell semántico · escala {fp.scale.px_per_m and round(fp.scale.px_per_m, 2)} px/m ({fp.scale.method}) · '
             f'ready_for_layout={str(r.ready_for_layout).lower()}</text>')
    items = [("#1f77b4", 7, "confirmed_glazing"), ("#4c9fd8", 6, "likely_glazing"), ("#9ecae1", 5, "exterior_unknown"), ("#444", 3, "opaque (límite interior)")]
    x = margin
    for col, wdt, name in items:
        o.append(f'<line x1="{x}" y1="{ly+22:.0f}" x2="{x+34}" y2="{ly+22:.0f}" stroke="{col}" stroke-width="{wdt}"/>')
        o.append(f'<text x="{x+40}" y="{ly+26:.0f}" font-size="11" fill="#333">{name}</text>')
        x += 190
    o.append(f'<rect x="{margin}" y="{ly+38:.0f}" width="10" height="10" fill="#111"/><text x="{margin+16}" y="{ly+47:.0f}" font-size="11" fill="#333">pilar confirmado</text>')
    o.append(f'<rect x="{margin+150}" y="{ly+38:.0f}" width="10" height="10" fill="#fff" stroke="#111" stroke-dasharray="3,2"/><text x="{margin+166}" y="{ly+47:.0f}" font-size="11" fill="#333">pilar candidato (conf.)</text>')
    o.append(f'<circle cx="{margin+340}" cy="{ly+43:.0f}" r="6" fill="#fff" stroke="#d62728" stroke-width="2.5"/><text x="{margin+352}" y="{ly+47:.0f}" font-size="11" fill="#333">acceso principal</text>')
    o.append(f'<circle cx="{margin+490}" cy="{ly+43:.0f}" r="5" fill="#fff" stroke="#e8888b" stroke-width="2" stroke-dasharray="3,2"/><text x="{margin+502}" y="{ly+47:.0f}" font-size="11" fill="#333">candidato de acceso</text>')
    o.append(f'<text x="{margin}" y="{ly+68:.0f}" font-size="11" fill="#666">Confianza: opacidad de la línea ∝ confidence; punteado = requiere confirmación. '
             f'Sin orientación solar ({"norte declarado" if fp.north_arrow.detected else "norte no detectado"}). Sin mobiliario.</text>')
    o.append(f'<text x="{margin}" y="{ly+86:.0f}" font-size="11" fill="#666">requires_confirmation: {", ".join(r.requires_confirmation) or "—"} · {r.notes[:140]}</text>')
    if fp.scale.px_per_m:
        bx = width_px - margin - 5 * s; by = ly + 22
        o.append(f'<line x1="{bx:.1f}" y1="{by:.0f}" x2="{bx+5*s:.1f}" y2="{by:.0f}" stroke="#111" stroke-width="3"/><text x="{bx:.1f}" y="{by-6:.0f}" font-size="11">5 m</text>')
    o.append("</svg>")
    return "\n".join(o)


def shell_semantics_png(fp: Floorplate, width: int = 1600) -> np.ndarray:
    img = _svg_to_bgr(render_shell_svg(fp, width), width)
    return img if img is not None else _raster_fallback(fp, width)


def semantic_overlay(image_bgr: np.ndarray, fp: Floorplate, up: int = 2) -> np.ndarray:
    img = overlay_on_original(image_bgr, fp, only_perimeter=True, upscale=up)
    S = lambda p: (int(p[0] * up), int(p[1] * up))  # noqa: E731
    for c in fp.core:
        cv2.polylines(img, [np.array([S(p) for p in c.ring], np.int32)], True, (0, 160, 0), 2)
    for d in fp.daylight_segments or []:
        col = {"confirmed_glazing": (180, 90, 0), "likely_glazing": (216, 159, 76), "exterior_unknown": (225, 202, 158)}.get(d.classification)
        if col:
            cv2.line(img, S(d.start), S(d.end), col, 4)
    for c in fp.column_candidates or []:
        r = int(max(4, c.size_px * up / 2))
        x, y = S(c.center)
        cv2.rectangle(img, (x - r, y - r), (x + r, y + r), (255, 0, 0) if c.status == "confirmed" else (255, 120, 120), 2)
    for c in fp.entrance_candidates or []:
        is_p = fp.primary_entrance is not None and c.point == fp.primary_entrance.point
        cv2.circle(img, S(c.point), 10 if is_p else 6, (0, 0, 255) if is_p else (120, 120, 255), 3 if is_p else 2)
    return img


def shell_comparison(image_bgr: np.ndarray, fp: Floorplate, panel_width: int = 900) -> np.ndarray:
    h0, w0 = image_bgr.shape[:2]
    left = cv2.resize(image_bgr, (panel_width, int(h0 * panel_width / w0)), interpolation=cv2.INTER_CUBIC)
    ov = semantic_overlay(image_bgr, fp)
    mid = cv2.resize(ov, (panel_width, int(h0 * panel_width / w0)), interpolation=cv2.INTER_CUBIC)
    right = shell_semantics_png(fp, panel_width)
    H = max(left.shape[0], mid.shape[0], right.shape[0]) + 44
    gap = 24
    canvas = np.full((H, panel_width * 3 + gap * 2, 3), 255, np.uint8)
    for i, (panel, title) in enumerate([(left, "ORIGINAL"), (mid, "OVERLAY SEMANTICO"), (right, "SHELL ESCALIMETRO")]):
        x = i * (panel_width + gap)
        canvas[44:44 + panel.shape[0], x:x + panel_width] = panel
        cv2.putText(canvas, title, (x + 8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return canvas
