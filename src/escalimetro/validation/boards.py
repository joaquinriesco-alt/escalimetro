"""E13 — láminas de validación: BLIND y REVEAL.

Regla dura (§7): la geometría es la EXACTA de E07. Este módulo **no dibuja plantas**: extrae el SVG
comercial que E07 ya produjo (`presentation_handoff.json → svg.commercial_base`), le quita el pie de
lienzo —que es donde va el título con el nombre de la estrategia— y lo incrusta tal cual. Ninguna
coordenada se recalcula, ni se mueve, ni se embellece. La planta base se dibuja desde `shell_geometry`,
que también es dato de E07.

Lo único que E13 aporta es composición editorial: tipografía, márgenes, jerarquía y leyenda."""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Tuple

from ..brief import program_rows, total_rooms
from ..case_context import CaseContext, from_case_dir
from ..layout.program_access import open_workstations
from .blind import BLIND, REAL_NAMES, mapping_for

#: programa congelado por defecto. No es identidad de caso: es el programa del experimento, y el
#: caller puede pasar otro. Ver E16.1 §13.
DEFAULT_PROGRAM = "program_templates/office_balanced_48.json"

# ---------------------------------------------------------------------------------------------------
# paleta — neutra a propósito: ningún color "gana" (§43, sesgo por color)
# ---------------------------------------------------------------------------------------------------
PAL = {"paper": "#ffffff", "panel": "#f6f6f4", "ink": "#1d2430", "muted": "#6b7480",
       "line": "#d9dce2", "warn": "#8a1f1f", "chip": "#eceef2"}

LEGEND = [("Puestos de trabajo", "#dfe7f5"), ("Salas y directorio", "#dfeee2"), ("Recepción", "#f7e3d3"),
          ("Cocina / comedor / cabinas", "#f2e7db"), ("Lounge", "#ece0ef"), ("Circulación", "#e9ecf2"),
          ("Núcleo del edificio", "#e3e5e8"), ("Pilar", "#222222")]

# E24 §6 — programa y KPIs comunes se DERIVAN del brief compilado, no se escriben aquí.


def _common_metrics(program: Dict) -> List[Tuple[str, str]]:
    """Idéntico en las tres alternativas: el mismo programa del cliente resuelto completo."""
    need = open_workstations(program)
    return [("Programa", "completo"), ("Puestos open", f"{need} / {need}"),
            ("Recintos", f"{total_rooms(program)} / {total_rooms(program)}")]

W, H = 4900, 1390
SIDE_X, SIDE_W = 60, 500
COL_X = [620, 2050, 3480]
COL_W = 1380
PLAN_Y = 330


# ---------------------------------------------------------------------------------------------------
def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _t(x, y, s, size=15, fill=PAL["ink"], weight=400, anchor="start", ls=0.0, op=1.0) -> str:
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}" letter-spacing="{ls}" opacity="{op}">{_esc(s)}</text>')


CHROME_Y = 1060          # todo lo que E07 dibuja bajo esta y es pie de lienzo, no planta


def strip_chrome(svg: str) -> Tuple[str, int, int]:
    """Devuelve (cuerpo, ancho, alto) de la planta SIN el pie de lienzo de E07.

    El pie contiene el título con el nombre de la estrategia ('OFICINA 403 · A EFICIENTE'), que es
    precisamente lo que no puede ver el evaluador. Se eliminan los elementos cuya `y` cae bajo
    CHROME_Y; ninguna coordenada de la planta se toca."""
    head = svg[:svg.index(">") + 1]
    wv = int(float(re.search(r'width="([\d.]+)"', head).group(1)))
    body = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
    keep = []
    for line in body.strip().splitlines():
        m = re.search(r'\sy(?:1)?="([\d.]+)"', line)
        if m and float(m.group(1)) >= CHROME_Y:
            continue
        keep.append(line)
    return "\n".join(keep), wv, CHROME_Y - 20


def visible_text(svg: str) -> str:
    """Sólo el texto que un humano lee en la lámina. Es lo que se audita por fugas: las coordenadas
    numéricas del SVG no son información visible y producirían falsos positivos."""
    return " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))


# ---------------------------------------------------------------------------------------------------
def base_plan_svg(shell: Dict, width: int = 900) -> str:
    """Planta base (§30): sólo el envolvente, el núcleo, los pilares y el acceso. Dibujada desde
    `shell_geometry` de E07 — mismos metros, misma escala, sin programa encima."""
    per = shell["perimeter"]
    xs = [p[0] for p in per]; ys = [p[1] for p in per]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    m = 14
    k = (width - 2 * m) / (x1 - x0)
    hgt = int((y1 - y0) * k + 2 * m)

    def P(x, y):                                     # y invertida: el SVG crece hacia abajo
        return (m + (x - x0) * k, hgt - m - (y - y0) * k)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{hgt}" '
         f'viewBox="0 0 {width} {hgt}" font-family="Helvetica,Arial,sans-serif">',
         f'<rect width="100%" height="100%" fill="#ffffff"/>']
    pts = " ".join(f"{P(*p)[0]:.1f},{P(*p)[1]:.1f}" for p in per)
    o.append(f'<polygon points="{pts}" fill="#fbfbfb" stroke="#111" stroke-width="2.2"/>')
    for c in shell["core"]:
        cp = " ".join(f"{P(*p)[0]:.1f},{P(*p)[1]:.1f}" for p in c)
        o.append(f'<polygon points="{cp}" fill="#e3e5e8" stroke="#9aa0aa" stroke-width="1.2"/>')
    for b in shell["columns"]:
        ax, ay = P(b[0], b[1]); bx, by = P(b[2], b[3])
        o.append(f'<rect x="{min(ax,bx):.1f}" y="{min(ay,by):.1f}" width="{abs(bx-ax):.1f}" '
                 f'height="{abs(by-ay):.1f}" fill="#222" stroke="none"/>')
    ex, ey = P(*shell["entrance"])
    o.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="8" fill="#ffffff" stroke="#c0392b" stroke-width="3"/>')
    o.append(_t(ex + 12, ey - 10, "ACCESO", 12, "#c0392b", 700))
    o.append("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------------------------------------------
def _sidebar(shell: Dict, program: Dict) -> List[str]:
    o: List[str] = []
    x = SIDE_X
    o.append(f'<rect x="{x}" y="{PLAN_Y - 46}" width="{SIDE_W}" height="{H - PLAN_Y - 20}" '
             f'fill="{PAL["panel"]}" stroke="{PAL["line"]}"/>')
    y = PLAN_Y - 14
    o.append(_t(x + 24, y, "PLANTA BASE", 16, PAL["muted"], 700, ls=1.6)); y += 16

    base = base_plan_svg(shell, SIDE_W - 48)
    bh = int(re.search(r'height="(\d+)"', base).group(1))
    inner = base[base.index(">") + 1: base.rindex("</svg>")]
    o.append(f'<g transform="translate({x + 24},{y})">{inner}</g>')
    y += bh + 40

    o.append(_t(x + 24, y, "PROGRAMA SOLICITADO", 16, PAL["muted"], 700, ls=1.6)); y += 30
    for name, qty in program_rows(program):
        o.append(_t(x + 24, y, name, 18))
        o.append(_t(x + SIDE_W - 24, y, qty, 18, PAL["ink"], 700, anchor="end"))
        y += 28
    y += 22

    o.append(_t(x + 24, y, "LEYENDA", 16, PAL["muted"], 700, ls=1.6)); y += 28
    for name, col in LEGEND:
        o.append(f'<rect x="{x + 24}" y="{y - 13}" width="17" height="17" fill="{col}" '
                 f'stroke="{PAL["line"]}"/>')
        o.append(_t(x + 50, y, name, 17))
        y += 26
    return o


def _column(i: int, label: str, plan_body: str, pw: int, ph: int, program: Dict) -> List[str]:
    x = COL_X[i]
    o: List[str] = [f'<rect x="{x}" y="{PLAN_Y - 46}" width="{COL_W}" height="{H - PLAN_Y - 20}" '
                    f'fill="{PAL["paper"]}" stroke="{PAL["line"]}"/>']
    o.append(f'<rect x="{x}" y="{PLAN_Y - 46}" width="{COL_W}" height="60" fill="{PAL["chip"]}" '
             f'stroke="{PAL["line"]}"/>')
    o.append(_t(x + COL_W / 2, PLAN_Y - 2, label, 32, PAL["ink"], 700, anchor="middle", ls=2.4))

    k = (COL_W - 40) / pw
    o.append(f'<g transform="translate({x + 20},{PLAN_Y + 40}) scale({k:.5f})">{plan_body}</g>')

    y = PLAN_Y + 40 + int(ph * k) + 46
    for name, val in _common_metrics(program):
        o.append(_t(x + 26, y, name, 19, PAL["muted"]))
        o.append(_t(x + COL_W - 26, y, val, 19, PAL["ink"], 700, anchor="end"))
        y += 30
    return o


def build_board(handoffs: Dict[str, Dict], labels: Dict[str, str], order: List[str],
                title: str, subtitle: str, ctx: CaseContext = None, program: Dict = None) -> str:
    """Compone la lámina. `order` son las alternativas reales en el orden en que se muestran;
    `labels` dice con qué texto se rotula cada una (X/Y/Z en ciega, A/B/C en revelada).

    E16.1 — el encabezado decía `"Oficina 403 · 543 m² publicados · 48 personas"` como literal, así
    que la lámina ciega de CUALQUIER caso habría llevado la identidad de la 403 delante de un broker
    real. Ahora: la unidad y la superficie salen del `CaseContext` (SOURCE_FACT) y el headcount del
    programa congelado (PROGRAM FACT)."""
    if ctx is None:
        raise ValueError("build_board necesita un CaseContext: la identidad del inmueble es dato del "
                         "caso, no un literal de la lámina de validación")
    if not program or "target_headcount" not in program:
        raise ValueError("build_board necesita el programa congelado: el headcount es un dato del "
                         "programa, no un literal de la lámina")
    shell = handoffs[order[0]]["shell_geometry"]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Helvetica,Arial,sans-serif">',
         f'<rect width="100%" height="100%" fill="{PAL["paper"]}"/>']

    o.append(_t(SIDE_X, 92, title, 46, PAL["ink"], 700))
    o.append(_t(SIDE_X, 138, subtitle, 22, PAL["muted"]))
    unidad = ctx.display_name or ctx.unit_label
    o.append(_t(W - SIDE_X, 92,
                f'{unidad}  ·  {ctx.published_area_label()} publicados  ·  '
                f'{program["target_headcount"]} personas', 26, PAL["ink"], 700, anchor="end"))
    o.append(_t(W - SIDE_X, 132, "Test-fit conceptual. Dimensiones sujetas a confirmación de escala.",
                19, PAL["warn"], anchor="end"))
    o.append(f'<line x1="{SIDE_X}" y1="{PLAN_Y - 80}" x2="{W - SIDE_X}" y2="{PLAN_Y - 80}" '
             f'stroke="{PAL["ink"]}" stroke-width="2"/>')

    o += _sidebar(shell, program)
    for i, alt in enumerate(order):
        body, pw, ph = strip_chrome(handoffs[alt]["svg"]["commercial_base"])
        o += _column(i, labels[alt], body, pw, ph, program)

    o.append(_t(SIDE_X, H - 24, "ESCALÍMETRO  ·  pre-design  ·  feasibility  ·  test-fit",
                17, PAL["muted"]))
    o.append("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------------------------------------------
def load_program_facts(program_path: str = DEFAULT_PROGRAM) -> Dict:
    """El programa congelado. Es un HECHO DE ENTRADA del experimento, no del renderer."""
    return json.load(open(program_path, encoding="utf-8"))


def load_handoffs(case: str) -> Dict[str, Dict]:
    base = os.path.join(case, "layouts", "E07", "alternatives")
    return {a: json.load(open(os.path.join(base, a, "presentation_handoff.json"), encoding="utf-8"))
            for a in ("A", "B", "C")}


def blind_board(case: str, respondent_index: int = 0, program_path: str = DEFAULT_PROGRAM) -> str:
    h = load_handoffs(case)
    mp = mapping_for(respondent_index)
    order = [mp[b] for b in BLIND]
    labels = {mp[b]: f"OPTION {b}" for b in BLIND}
    return build_board(h, labels, order,
                       "TEST-FIT · TRES ALTERNATIVAS",
                       "Mismo local, mismo programa. Tres distribuciones posibles.",
                       ctx=from_case_dir(case), program=load_program_facts(program_path))


def reveal_board(case: str, program_path: str = DEFAULT_PROGRAM) -> str:
    h = load_handoffs(case)
    order = ["A", "B", "C"]
    return build_board(h, REAL_NAMES, order,
                       "TEST-FIT · TRES ALTERNATIVAS",
                       "Las mismas tres distribuciones, ahora con su intención de diseño.",
                       ctx=from_case_dir(case), program=load_program_facts(program_path))
