"""Render limpio del shell: perímetro, núcleo, pilares, acceso. Sin overlays de debug.

E27 §20 — por qué este módulo existe y no es un PNG en disco: la columna SHELL de la revisión
E26 se veía rota en cualquier checkout que no fuera el del autor. La causa no era la ruta del
HTML (que era correcta) sino que `cases/*/outputs/*.png` está en `.gitignore:24`, así que
`shell_clean.png` nunca viajó con el repo ni con un deploy. Los PNG de layout sí viajan porque
viven bajo `layouts/`, que ese patrón no captura — de ahí la asimetría "A/B/C se ven, SHELL no".

La corrección de fondo es no depender de un archivo: el shell se dibuja bajo demanda desde
`floorplate.json`, que es fuente versionada. Sin archivo intermedio no hay 404 posible.

El dibujo es el mismo de E26. Vive FUERA de `src/escalimetro/` a propósito: E27 es
producto y web, no motor, y el hash del motor no se mueve por un renderer (§7).
`tools/e26_shell_png.py` importa de aquí para que haya una sola implementación (§21).
"""
from __future__ import annotations


def shell_svg(shell, width_px: int = 1500, margin: int = 60) -> str:
    minx, miny, maxx, maxy = shell.perimeter.bounds
    s = (width_px - 2 * margin) / (maxx - minx)
    H = int((maxy - miny) * s + 2 * margin)

    def P(p):
        return (margin + (p[0] - minx) * s, margin + (maxy - p[1]) * s)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{H}" '
         f'viewBox="0 0 {width_px} {H}" font-family="Helvetica,Arial,sans-serif">',
         f'<rect width="100%" height="100%" fill="#ffffff"/>']
    pts = " ".join(f"{P(c)[0]:.1f},{P(c)[1]:.1f}" for c in shell.perimeter.exterior.coords)
    o.append(f'<polygon points="{pts}" fill="#fafafa" stroke="#1d2430" stroke-width="3"/>')
    for c in shell.core:
        cp = " ".join(f"{P(x)[0]:.1f},{P(x)[1]:.1f}" for x in c.exterior.coords)
        o.append(f'<polygon points="{cp}" fill="#e3e5e8" stroke="#9aa0a8" stroke-width="2"/>')
        cx, cy = P(c.centroid.coords[0])
        o.append(f'<text x="{cx:.0f}" y="{cy:.0f}" font-size="16" fill="#6b7480" '
                 f'text-anchor="middle">NUCLEO</text>')
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
    o.append("</svg>")
    return "\n".join(o)
