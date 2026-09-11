"""Render limpio del shell: perímetro, núcleo, pilares, acceso. Sin overlays de debug.

E27 §20 — por qué este módulo existe y no es un PNG en disco: la columna SHELL de la revisión
E26 se veía rota en cualquier checkout que no fuera el del autor. La causa no era la ruta del
HTML (que era correcta) sino que `cases/*/outputs/*.png` está en `.gitignore:24`, así que
`shell_clean.png` nunca viajó con el repo ni con un deploy. Los PNG de layout sí viajan porque
viven bajo `layouts/`, que ese patrón no captura — de ahí la asimetría "A/B/C se ven, SHELL no".

La corrección de fondo es no depender de un archivo: el shell se dibuja bajo demanda desde
`floorplate.json`, que es fuente versionada. Sin archivo intermedio no hay 404 posible.

E26.1 — segundo defecto, independiente del anterior y todavía vivo aquí: el lienzo se
dimensionaba con `shell.perimeter.bounds`, y en los dos casos reales el polígono de núcleo cae
ENTERO fuera del perímetro arrendado (403: 210.6 m² fuera de 543.0; 401: 206.9 m² fuera de
252.0 — intersección de área cero en ambos). Con ese encuadre el núcleo se dibujaba cortado
contra el borde de la imagen: en el 401 quedaban fuera del lienzo tres de sus cuatro esquinas.
Ahora el encuadre usa la envolvente de TODO lo que se dibuja. La geometría no se toca ni se
recorta: se dibuja completa, y el núcleo se rotula como lo que es, algo fuera del perímetro.

El dibujo es el mismo de E26. Vive FUERA de `src/escalimetro/` a propósito: E27 es
producto y web, no motor, y el hash del motor no se mueve por un renderer (§7).
`tools/e26_shell_png.py` importa de aquí para que haya una sola implementación (§21).
"""
from __future__ import annotations

from shapely.geometry import Point
from shapely.ops import unary_union


def _partes(g):
    """Polígonos individuales de un Polygon / MultiPolygon / GeometryCollection."""
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon" and not p.is_empty]


def _path(g, P):
    """SVG path de un polígono con sus huecos, proyectado con P."""
    d = []
    for poly in _partes(g):
        for ring in [poly.exterior, *poly.interiors]:
            d.append("M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in (P(c) for c in ring.coords)) + " Z")
    return " ".join(d)


def shell_svg(shell, width_px: int = 1500, margin: int = 60) -> str:
    dibujado = [shell.perimeter, *shell.core, *shell.columns, Point(shell.entrance).buffer(0.4)]
    minx, miny, maxx, maxy = unary_union(dibujado).bounds      # E26.1: envolvente de todo lo dibujado
    s = (width_px - 2 * margin) / (maxx - minx)
    H = int((maxy - miny) * s + 2 * margin)

    def P(p):
        return (margin + (p[0] - minx) * s, margin + (maxy - p[1]) * s)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{H}" '
         f'viewBox="0 0 {width_px} {H}" font-family="Helvetica,Arial,sans-serif">',
         f'<rect width="100%" height="100%" fill="#ffffff"/>']
    o.append(f'<path d="{_path(shell.perimeter, P)}" fill="#fafafa" stroke="#1d2430" '
             f'stroke-width="3" fill-rule="evenodd"/>')
    for c in shell.core:
        o.append(f'<path d="{_path(c, P)}" fill="#f4f5f6" stroke="#c2c8ce" stroke-width="2" '
                 f'stroke-dasharray="7 5" fill-rule="evenodd"/>')
        dentro = c.intersection(shell.perimeter)
        solido = dentro.area > 0.5                    # sólo si obstruye superficie, no una arista
        if solido:
            o.append(f'<path d="{_path(dentro, P)}" fill="#e3e5e8" stroke="#9aa0a8" '
                     f'stroke-width="2" fill-rule="evenodd"/>')
        cx, cy = P((dentro if solido else c).representative_point().coords[0])
        o.append(f'<text x="{cx:.0f}" y="{cy:.0f}" font-size="16" fill="#79828d" '
                 f'text-anchor="middle">NUCLEO</text>')
        if not solido:
            o.append(f'<text x="{cx:.0f}" y="{cy + 20:.0f}" font-size="13" fill="#9aa0a8" '
                     f'text-anchor="middle">fuera del perimetro arrendado</text>')
    for col in shell.columns:
        b = col.bounds
        a1, a2 = P((b[0], b[3])), P((b[2], b[1]))
        o.append(f'<rect x="{a1[0]:.1f}" y="{a1[1]:.1f}" width="{abs(a2[0]-a1[0]):.1f}" '
                 f'height="{abs(a2[1]-a1[1]):.1f}" fill="#111111"/>')
    ex, ey = P(shell.entrance)
    o.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="9" fill="#ffffff" stroke="#b5452f" '
             f'stroke-width="4"/>')
    o.append(f'<text x="{ex + 16:.0f}" y="{ey - 12:.0f}" font-size="18" fill="#b5452f" '
             f'font-weight="bold">ACCESO</text>')
    n_fuera = sum(1 for c in shell.core if c.intersection(shell.perimeter).area <= 0.5)
    a_core = sum(c.area for c in shell.core)
    pie = (f'perimetro {shell.perimeter.area:.1f} m2 · {len(shell.columns)} pilares · '
           f'{len(shell.core)} nucleo(s) {a_core:.1f} m2'
           + (' (fuera del perimetro)' if shell.core and n_fuera == len(shell.core) else ''))
    o.append(f'<text x="{margin}" y="{H - 18}" font-size="14" fill="#6b7480">{pie}</text>')
    o.append("</svg>")
    return "\n".join(o)
