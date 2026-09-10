"""E26 §10 — render limpio del shell (perímetro, núcleo, pilares, acceso). Sin overlays de debug."""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
import cv2                                                            # noqa: E402
from escalimetro.case_context import from_case_dir                    # noqa: E402
from escalimetro.layout.e06.scale import scaled_shell                 # noqa: E402
from escalimetro.renderer.side_by_side import _svg_to_bgr             # noqa: E402
from escalimetro.schemas.floorplate import Floorplate                 # noqa: E402
from webapp.shellview import shell_svg                                # noqa: E402




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
