"""E26 §5 — re-baseline de la lámina Standard 01 de la 403.

E26 cambió A PROPÓSITO lo que la lámina dice: fuera las fortalezas escritas de antemano y el bloque
IDEAL PARA, dentro las cifras medidas de la planta. La geometría NO cambia: se re-renderiza el MISMO
layout validado con el renderer corregido. Los tests de "lámina byte-idéntica" siguen protegiendo lo
que protegían —que la lámina no cambie en silencio—; lo que se actualiza es su expectativa."""
from __future__ import annotations
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import cv2                                                              # noqa: E402
from escalimetro import fit_evidence as FE                              # noqa: E402
from escalimetro.case_context import from_case_dir                      # noqa: E402
from escalimetro.layout.e06.scale import scaled_shell                   # noqa: E402
from escalimetro.layout.e07.board import build_board                    # noqa: E402
from escalimetro.layout.e07.strategies import build_alternatives        # noqa: E402
from escalimetro.layout.model import Layout, load_program               # noqa: E402
from escalimetro.renderer.side_by_side import _svg_to_bgr               # noqa: E402
from escalimetro.schemas.floorplate import Floorplate                   # noqa: E402

C = os.path.join(ROOT, "cases", "001_gps_403")
E07 = os.path.join(C, "layouts", "E07")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")


class R:
    def __init__(self, alt, name, layout, metrics, critique):
        self.alt, self.name, self.layout = alt, name, layout
        self.metrics, self.critique = metrics, critique


def main():
    prog = load_program(PROG)
    specs = {s.alt: s for s in build_alternatives(prog)}
    ctx = from_case_dir(C)
    shell = scaled_shell(Floorplate.load(ctx.require_floorplate()), 1.0)
    alts = []
    for a in "ABC":
        d = os.path.join(E07, "alternatives", a)
        alts.append({"spec": specs[a],
                     "result": R(a, specs[a].name, Layout.load(os.path.join(d, "layout.json")),
                                 json.load(open(os.path.join(d, "metrics.json"), encoding="utf-8")),
                                 json.load(open(os.path.join(d, "critique.json"), encoding="utf-8")))})
    svg = build_board(alts, shell, FE.load(C, PROG), ctx=ctx, program=prog)
    p = os.path.join(E07, "ESCALIMETRO_PRESENTATION_STANDARD_01.svg")
    open(p, "w", encoding="utf-8").write(svg)
    png = os.path.join(E07, "ESCALIMETRO_PRESENTATION_STANDARD_01.png")
    cv2.imwrite(png, _svg_to_bgr(svg, 3600))
    print("re-renderizados:", p, png)
    for mal in ("Fachada liberada para puestos", "IDEAL PARA"):
        assert mal not in svg, mal
    print("la lámina ya no contiene copy fija de fortalezas ni IDEAL PARA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
