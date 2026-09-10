"""E26 §10 — render limpio del shell (perímetro, núcleo, pilares, acceso). Sin overlays de debug."""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import cv2                                                            # noqa: E402
from escalimetro.case_context import from_case_dir                    # noqa: E402
from escalimetro.layout.e06.scale import scaled_shell                 # noqa: E402
from escalimetro.renderer.side_by_side import _svg_to_bgr             # noqa: E402
from escalimetro.schemas.floorplate import Floorplate                 # noqa: E402


def shell_svg(shell, width_px=1500, margin=60):
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
        o.append(f'<text x="{cx:.0f}" y="{cy:.0f}" font-size="16" fill="#6b7480" text-anchor="middle">NUCLEO</text>')
    for col in shell.columns:
        b = col.bounds
        a1, a2 = P((b[0], b[3])), P((b[2], b[1]))
        o.append(f'<rect x="{a1[0]:.1f}" y="{a1[1]:.1f}" width="{abs(a2[0]-a1[0]):.1f}" '
                 f'height="{abs(a2[1]-a1[1]):.1f}" fill="#111111"/>')
    ex, ey = P(shell.entrance)
    o.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="9" fill="#ffffff" stroke="#b5452f" stroke-width="4"/>')
    o.append(f'<text x="{ex + 16:.0f}" y="{ey - 12:.0f}" font-size="18" fill="#b5452f" font-weight="bold">ACCESO</text>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    for case in ("cases/001_gps_403", "cases/002_gps_401"):
        ctx = from_case_dir(os.path.join(ROOT, case))
        shell = scaled_shell(Floorplate.load(ctx.require_floorplate()), 1.0)
        img = _svg_to_bgr(shell_svg(shell), 1500)
        d = os.path.join(ROOT, case, "outputs")
        p = os.path.join(d, "shell_clean.png")
        cv2.imwrite(p, img)
        print(p, img.shape)
    return 0


if __name__ == "__main__":
    sys.exit(main())
