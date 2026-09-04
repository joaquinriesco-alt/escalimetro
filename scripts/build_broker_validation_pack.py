#!/usr/bin/env python3
"""E13 — regenera todo el material de validación comercial.

    PYTHONPATH=src python scripts/build_broker_validation_pack.py

Es determinista: con los mismos artefactos de E07 produce byte a byte los mismos archivos, así que
regenerarlo no ensucia el diff. No toca el motor ni genera geometría."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from escalimetro.ai.svg_rasterizer import rasterize_and_write          # noqa: E402
from escalimetro.validation.blind import leaks                          # noqa: E402
from escalimetro.validation.boards import blind_board, reveal_board, visible_text   # noqa: E402
from escalimetro.validation.forms import form_html, pack_html, scorecard_html       # noqa: E402
from escalimetro.validation.schema import empty_csv                     # noqa: E402

CASE = os.environ.get("ESCALIMETRO_CASE", "cases/001_gps_403")
OUT = os.path.join(CASE, "validation", "E13")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    boards = (("BROKER_VALIDATION_BLIND_BOARD", blind_board(CASE, 0), True),
              ("BROKER_VALIDATION_REVEAL_BOARD", reveal_board(CASE), False))
    for name, svg, must_be_clean in boards:
        open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8").write(svg)
        rasterize_and_write(svg, 5200, os.path.join(OUT, name + ".png"), what=name)
        found = leaks(visible_text(svg))
        if must_be_clean and found:
            print(f"[e13] FUGA en {name}: {found}")
            return 1
        print(f"[e13] {name}  fugas: {found or 'ninguna'}")

    open(os.path.join(OUT, "BROKER_VALIDATION_FORM.html"), "w", encoding="utf-8").write(form_html())
    open(os.path.join(OUT, "BROKER_VALIDATION_SCORECARD.html"), "w",
         encoding="utf-8").write(scorecard_html())
    csv_path = os.path.join(OUT, "broker_validation_responses.csv")
    if not os.path.exists(csv_path):                     # nunca sobrescribir entrevistas reales
        open(csv_path, "w", encoding="utf-8").write(empty_csv())
    else:
        print("[e13] broker_validation_responses.csv ya existe — NO se toca")
    open(os.path.join(OUT, "ESCALIMETRO_BROKER_VALIDATION_PACK.html"), "w",
         encoding="utf-8").write(pack_html(CASE))
    print(f"[e13] material en {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
