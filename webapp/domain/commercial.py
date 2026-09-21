"""E28.4 — PLANO COMERCIAL: la planta base, presentable, antes de proponer nada.

Qué es y qué no es (§11). Es la representación de LA PLANTA TAL COMO ESTÁ: perímetro, núcleo,
pilares, fachada con luz y acceso. **No es la Alternativa A.** Es la pieza que falta entre "el plano
que recibimos" y "el layout que proponemos", y sin ella un before/after no tiene "before".

No hay limpieza automática de planos acá: esto se dibuja desde la geometría que el motor YA
interpretó y un humano YA confirmó. Si el caso no está listo, no hay plano comercial, y se dice.

Se apoya en el mismo encuadre que `shellview` (que E26.1 arregló para que el núcleo no salga
cortado) y añade lo que una lámina comercial necesita y la vista técnica no: fachada acristalada,
barra de escala y un pie sobrio. Sin overlays de debug, sin cajas de confirmación, sin brief.
"""
from __future__ import annotations

from typing import Optional

from shapely.geometry import Point

from ..shellview import _partes, _path

PALETA = {
    "muro": "#1d2430", "relleno": "#ffffff", "nucleo": "#e6e8ec", "nucleo_borde": "#aab0b9",
    "pilar": "#1d2430", "vidrio": "#3f86c9", "acceso": "#b5452f", "tinta": "#4a5160",
    "suave": "#9aa2ad",
}


def commercial_svg(shell, titulo: str = "", area_m2: Optional[float] = None,
                   width_px: int = 2000, margin: int = 80) -> str:
    """SVG de la planta base. `shell` es el ShellM que produce el motor (metros)."""
    dibujado = [shell.perimeter, *shell.core, *shell.columns, Point(shell.entrance).buffer(0.4)]
    minx = min(g.bounds[0] for g in dibujado); miny = min(g.bounds[1] for g in dibujado)
    maxx = max(g.bounds[2] for g in dibujado); maxy = max(g.bounds[3] for g in dibujado)
    pie = 92
    s = (width_px - 2 * margin) / (maxx - minx)
    H = int((maxy - miny) * s + 2 * margin + pie)

    def P(p):
        return (margin + (p[0] - minx) * s, margin + (maxy - p[1]) * s)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{H}" '
         f'viewBox="0 0 {width_px} {H}" font-family="Helvetica,Arial,sans-serif">',
         f'<rect width="100%" height="100%" fill="#ffffff"/>']

    # superficie arrendable
    for parte in _partes(shell.usable):
        o.append(f'<path d="{_path(parte, P)}" fill="{PALETA["relleno"]}" '
                 f'stroke="none"/>')
    for parte in _partes(shell.perimeter):
        o.append(f'<path d="{_path(parte, P)}" fill="none" stroke="{PALETA["muro"]}" '
                 f'stroke-width="4" stroke-linejoin="round"/>')

    # núcleo: se dibuja completo aunque caiga fuera del perímetro arrendado (E26.1)
    for c in shell.core:
        for parte in _partes(c):
            o.append(f'<path d="{_path(parte, P)}" fill="{PALETA["nucleo"]}" '
                     f'stroke="{PALETA["nucleo_borde"]}" stroke-width="2"/>')
        cx, cy = P(c.centroid.coords[0])
        o.append(f'<text x="{cx:.0f}" y="{cy:.0f}" font-size="17" fill="{PALETA["suave"]}" '
                 f'text-anchor="middle" letter-spacing="1.5">NÚCLEO</text>')

    # fachada con luz natural: lo que hace vendible una planta
    for d in getattr(shell, "daylight", []) or []:
        if getattr(d, "classification", "") not in ("confirmed_glazing", "likely_glazing"):
            continue
        (x1, y1), (x2, y2) = P(d.start), P(d.end)
        o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{PALETA["vidrio"]}" stroke-width="6" stroke-linecap="round"/>')

    for col in shell.columns:
        b = col.bounds
        a1, a2 = P((b[0], b[3])), P((b[2], b[1]))
        o.append(f'<rect x="{a1[0]:.1f}" y="{a1[1]:.1f}" width="{abs(a2[0]-a1[0]):.1f}" '
                 f'height="{abs(a2[1]-a1[1]):.1f}" fill="{PALETA["pilar"]}"/>')

    ex, ey = P(shell.entrance)
    o.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="10" fill="#ffffff" '
             f'stroke="{PALETA["acceso"]}" stroke-width="4"/>')
    o.append(f'<text x="{ex + 18:.0f}" y="{ey - 13:.0f}" font-size="17" fill="{PALETA["acceso"]}" '
             f'font-weight="bold" letter-spacing="1">ACCESO</text>')

    # ---- pie: rótulo, superficie y barra de escala ------------------------------------------
    by = H - pie + 34
    if titulo:
        o.append(f'<text x="{margin}" y="{by}" font-size="24" font-weight="600" '
                 f'fill="{PALETA["muro"]}">{_esc(titulo)}</text>')
    sub = "Planta base" + (f" · {area_m2:.0f} m² útiles" if area_m2 else "")
    o.append(f'<text x="{margin}" y="{by + 26}" font-size="14" fill="{PALETA["tinta"]}">'
             f'{_esc(sub)}</text>')
    bx = width_px - margin - 5 * s
    o.append(f'<line x1="{bx:.1f}" y1="{by + 4}" x2="{bx + 5 * s:.1f}" y2="{by + 4}" '
             f'stroke="{PALETA["muro"]}" stroke-width="3"/>')
    o.append(f'<text x="{bx + 5 * s / 2:.1f}" y="{by + 24}" font-size="13" '
             f'fill="{PALETA["tinta"]}" text-anchor="middle">5 m</text>')
    o.append(f'<text x="{width_px - margin}" y="{by + 26}" font-size="12" '
             f'fill="{PALETA["suave"]}" text-anchor="end">ESCALÍMETRO</text>')
    o.append("</svg>")
    return "\n".join(o)


def _esc(t: str) -> str:
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
