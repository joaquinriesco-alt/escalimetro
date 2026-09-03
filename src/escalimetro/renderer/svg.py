"""Renderer SVG de la Planta Escalímetro. Sólo geometría del Floorplate JSON — nunca píxeles
de la imagen original. El estilo codifica el status: confirmado = sólido; inferido = normal;
needs_confirmation = punteado; unknown = gris.
"""
from __future__ import annotations

from typing import List

from ..schemas.floorplate import Floorplate

STYLE = {
    "confirmed": 'stroke="#111" stroke-width="{w}" fill="none"',
    "inferred": 'stroke="#111" stroke-width="{w}" fill="none"',
    "needs_confirmation": 'stroke="#111" stroke-width="{w}" stroke-dasharray="6,4" fill="none"',
    "unknown": 'stroke="#999" stroke-width="{w}" stroke-dasharray="2,3" fill="none"',
}
FACADE_COLORS = {"facade": "#1f77b4", "party_wall": "#555", "core_wall": "#8c564b", "corridor": "#999", "unknown": "#bbb"}


def _pts(ring, tf):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in map(tf, ring))


def render_svg(fp: Floorplate, width_px: int = 1200, margin: float = 40, units: str = "m",
               show_raw: bool = False, show_labels: bool = True) -> str:
    """units='m' escala a metros (requiere scale). units='px' usa píxeles fuente."""
    ring = fp.perimeter.ring
    if units == "m" and fp.scale.px_per_m:
        conv = fp.to_m
    else:
        conv = lambda p: (p[0], p[1])  # noqa: E731
        units = "px"
    # bounds sobre TODOS los elementos (el core suele quedar fuera del perímetro de la unidad)
    all_pts = list(ring) + [p for c in fp.core for p in c.ring] + [p for fe in fp.fixed_elements for p in fe.ring]
    pts = [conv(p) for p in all_pts]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = (x1 - x0) or 1, (y1 - y0) or 1
    s = (width_px - 2 * margin) / bw
    height_px = bh * s + 2 * margin + (60 if show_labels else 0)
    flip = units == "m"

    def tf(p):
        x, y = conv(p)
        X = margin + (x - x0) * s
        Y = margin + ((y1 - y) if flip else (y - y0)) * s
        return X, Y

    w_line = 2.0
    out: List[str] = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px:.0f}" '
                      f'viewBox="0 0 {width_px} {height_px:.0f}" font-family="Helvetica,Arial,sans-serif">',
                      '<rect width="100%" height="100%" fill="#fff"/>']
    # relleno de unidad
    out.append(f'<polygon points="{_pts(ring, tf)}" fill="#fafafa" stroke="none"/>')
    for h in fp.holes:
        out.append(f'<polygon points="{_pts(h.ring, tf)}" fill="#fff" stroke="none"/>')
    if show_raw and fp.perimeter.raw_ring:
        out.append(f'<polyline points="{_pts(fp.perimeter.raw_ring + fp.perimeter.raw_ring[:1], tf)}" '
                   f'stroke="#e33" stroke-width="0.6" fill="none" opacity="0.7"/>')
    # segmentos clasificados
    for seg in fp.facade_segments:
        (ax, ay), (bx, by) = tf(seg.start), tf(seg.end)
        col = FACADE_COLORS.get(seg.kind, "#bbb")
        dash = ' stroke-dasharray="8,5"' if seg.meta.status == "needs_confirmation" else ""
        out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{col}" '
                   f'stroke-width="{w_line*2.2:.1f}" opacity="0.9"{dash}/>')
    # perímetro
    out.append(f'<polygon points="{_pts(ring, tf)}" {STYLE.get(fp.perimeter.meta.status, STYLE["unknown"]).format(w=w_line)}/>')
    for h in fp.holes:
        out.append(f'<polygon points="{_pts(h.ring, tf)}" {STYLE.get(h.meta.status, STYLE["unknown"]).format(w=w_line)}/>')
    for c in fp.core:
        out.append(f'<polygon points="{_pts(c.ring, tf)}" {STYLE.get(c.meta.status, STYLE["unknown"]).format(w=w_line).replace(chr(34)+"none"+chr(34), chr(34)+"#ddd"+chr(34))}/>')
        cx, cy = tf(_centroid(c.ring))
        if show_labels:
            out.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="12" text-anchor="middle" fill="#333">{c.kind.upper()}</text>')
    for fe in fp.fixed_elements:
        out.append(f'<polygon points="{_pts(fe.ring, tf)}" {STYLE.get(fe.meta.status, STYLE["unknown"]).format(w=1.2).replace(chr(34)+"none"+chr(34), chr(34)+"#eee"+chr(34))}/>')
    for col in fp.columns:
        cx, cy = tf(col.center)
        r = max(3.0, col.size_px * s / (fp.scale.px_per_m if (units == "m" and fp.scale.px_per_m) else 1) / 2)
        st = STYLE.get(col.meta.status, STYLE["unknown"]).format(w=1.5).replace('fill="none"', 'fill="#111"')
        if col.meta.status == "needs_confirmation":
            st = st.replace('fill="#111"', 'fill="#fff"')
        out.append(f'<rect x="{cx-r:.1f}" y="{cy-r:.1f}" width="{2*r:.1f}" height="{2*r:.1f}" {st}/>')
    for w in fp.windows:
        (ax, ay), (bx, by) = tf(w.start), tf(w.end)
        out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#1f77b4" stroke-width="5"/>')
    for e in fp.entrances:
        ex, ey = tf(e.point)
        dash = ' stroke-dasharray="3,2"' if e.meta.status == "needs_confirmation" else ""
        out.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="7" fill="#fff" stroke="#d62728" stroke-width="2.5"{dash}/>')
        if show_labels:
            out.append(f'<text x="{ex+10:.1f}" y="{ey-8:.1f}" font-size="11" fill="#d62728">ACCESO {e.kind}</text>')
    if show_labels:
        area = f"{fp.area_m2:.1f} m²" if fp.area_m2 else "área: unknown"
        sc = f"escala: {fp.scale.px_per_m:.2f} px/m ({fp.scale.method})" if fp.scale.px_per_m else "escala: unknown"
        out.append(f'<text x="{margin}" y="{height_px-32:.0f}" font-size="14" fill="#111">{fp.unit_label} · {area} · {sc}</text>')
        out.append(f'<text x="{margin}" y="{height_px-14:.0f}" font-size="11" fill="#666">Planta Escalímetro · schema {fp.schema_version} · '
                   f'punteado = requiere confirmación · azul = fachada · gris = interior sin clasificar</text>')
        if units == "m":
            # barra de escala 5 m
            bx = width_px - margin - 5 * s; by = height_px - 40
            out.append(f'<line x1="{bx:.1f}" y1="{by:.0f}" x2="{bx+5*s:.1f}" y2="{by:.0f}" stroke="#111" stroke-width="3"/>')
            out.append(f'<text x="{bx:.1f}" y="{by-6:.0f}" font-size="11" fill="#111">5 m</text>')
    out.append("</svg>")
    return "\n".join(out)


def _centroid(ring):
    n = len(ring)
    return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)
