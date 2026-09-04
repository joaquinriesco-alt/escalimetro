"""E08 — ESCALIMETRO PRESENTATION STANDARD 02.

Qué cambia respecto de 01, y por qué:

- **Se elimina la barra lateral.** Consumía 380 px que ahora son planta. Las plantas pasan de 600 a 748 px
  de ancho: +25 %, que es lo único que el lector mira de verdad.
- **Titular.** 01 empezaba con una tabla de programa. 02 empieza con una frase que responde la pregunta
  del lector antes de que la formule.
- **Menos números, mejor elegidos.** De 4 KPIs + 4 filas de detalle por columna a 3 KPIs. El resto del
  dato existe en el JSON, no en la lámina.
- **Un callout por alternativa**, en el color de la alternativa: la razón para elegirla, en una línea.
- **Programa en una sola banda horizontal**, porque es idéntico en las tres y repetirlo era ruido.
- **Jerarquía por tamaño y peso, no por color.** El color sólo identifica alternativa.

Lo que NO cambia: las plantas. Son el mismo SVG del renderer sobre el mismo Layout validado, incrustado
sin recalcular una sola coordenada. `geometry_locked` se mantiene y se verifica por hash."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..case_context import CaseContext
from ..fit_evidence import FitEvidence, PresentationFit, presentation_fit
from ..layout.model import Layout, ShellM
from ..layout.render import render_layout_svg

PALETTE = {
    "paper": "#ffffff", "band": "#f6f6f4", "ink": "#141a23", "muted": "#69727e", "faint": "#9aa2ad",
    "line": "#e0e3e8", "hair": "#eceef2", "accent": "#b5452f", "good": "#2f6d4f",
    "A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a",
}
LEGEND = [("Puestos", "#dfe7f5"), ("Salas y directorio", "#dfeee2"), ("Recepción", "#f7e3d3"),
          ("Cocina · comedor · cabinas", "#f2e7db"), ("Lounge", "#ece0ef"), ("Circulación", "#fbf3dd"),
          ("Núcleo", "#e3e5e8"), ("Pilar", "#111111")]

W, H = 2400, 1400
M = 48
GUT = 26
COL_W = (W - 2 * M - 2 * GUT) // 3
COL_X = [M, M + COL_W + GUT, M + 2 * (COL_W + GUT)]


def _esc(t: str) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _t(x, y, s, size=14, fill=PALETTE["ink"], w=400, anchor="start", ls=0.0, op=1.0):
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" fill="{fill}" font-weight="{w}" '
            f'text-anchor="{anchor}" letter-spacing="{ls}" opacity="{op}">{_esc(s)}</text>')


def _wrap(t: str, n: int) -> List[str]:
    out, line = [], ""
    for word in str(t).split():
        if len(line) + len(word) + 1 > n:
            out.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def _plan(layout: Layout, shell: ShellM, width_px: int = 1500) -> Tuple[str, int, int]:
    """La planta validada, tal cual. Sólo se omite el chrome del lienzo."""
    svg = render_layout_svg(layout, shell, "commercial", width_px=width_px, chrome=False, margin=10)
    head = svg.split(">", 1)[0]
    wv = int(float(head.split('width="')[1].split('"')[0]))
    hv = int(float(head.split('height="')[1].split('"')[0]))
    body = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
    return body, wv, hv


def _num(t: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", t or "")
    return float(m.group(1)) if m else 0.0


def build_board02(alts: List[Dict], shell: ShellM, spec: Dict, ctx: CaseContext = None,
                  evidence: FitEvidence = None) -> str:
    """alts: [{alt, layout, metrics, critique, row}] en el orden que manda `spec["alternative_order"]`.

    E16.1 — antes esta función recibía `fit: Dict` y además imprimía `"543 m² publicados"` y
    `"539 m² útiles del modelo"` como literales. Las Standard 02 y 03 habrían dicho 543 m² para
    cualquier inmueble. Ahora:

        superficie publicada  ← ctx.published_area_label()                     SOURCE_FACT
        útil del modelo       ← alts[0]["metrics"]["usable_area_m2"]           COMPUTED_RESULT
        escala y confianza    ← PresentationFit.from_evidence(ctx, evidence)   COMPUTED_RESULT

    Mismo contrato que la Standard 01 (E15.2/E15.3): un diccionario con las claves correctas no es
    evidencia. La copy se deriva aquí dentro, desde la evidencia."""
    if ctx is None:
        raise ValueError("build_board02 necesita un CaseContext: la identidad del inmueble es dato "
                         "del caso, no un literal del renderer")
    if isinstance(evidence, PresentationFit):
        raise TypeError("build_board02 recibe la EVIDENCIA (FitEvidence), no la copy ya formateada: "
                        "un PresentationFit construido a mano tiene el tipo correcto y ninguna "
                        "procedencia")
    if not isinstance(evidence, FitEvidence):
        raise TypeError("build_board02 necesita una FitEvidence cargada desde los artefactos "
                        "computados (fit_evidence.load(case_dir)). Un diccionario con las claves "
                        "correctas NO es evidencia: un veredicto es un RESULTADO COMPUTADO con "
                        "procedencia, no un blob escrito a mano.")
    fit = presentation_fit(ctx, evidence)      # la copy se deriva DENTRO del boundary controlado
    order = spec["alternative_order"]
    by = {a["alt"]: a for a in alts}
    copy = spec["alternative_copy"]
    callout = {c["alternative_id"]: c["text"] for c in spec.get("callouts", [])}
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
         f'<rect width="{W}" height="{H}" fill="{PALETTE["paper"]}"/>']

    # ---------- cabecera: marca discreta, titular grande, veredicto a la derecha -------------------
    o.append(_t(M, 52, "ESCALÍMETRO", 15, PALETTE["muted"], 700, ls=3.4))
    o.append(_t(M, 74, "pre-design · feasibility · test-fit", 11.5, PALETTE["faint"], 400, ls=1.4))
    o.append(_t(M, 138, spec["headline"], 44, PALETTE["ink"], 700, ls=-0.4))
    o.append(_t(M, 172, spec["subtitle"], 17, PALETTE["muted"]))

    vw, vx = 560, W - M - 560
    o.append(f'<rect x="{vx}" y="34" width="{vw}" height="112" rx="8" fill="{PALETTE["band"]}"/>')
    o.append(f'<rect x="{vx}" y="34" width="5" height="112" rx="2" fill="{PALETTE["good"]}"/>')
    o.append(_t(vx + 28, 64, "VEREDICTO", 10.5, PALETTE["faint"], 700, ls=2.0))
    for i, ln in enumerate(_wrap(spec["fit_verdict_copy"], 44)[:2]):
        o.append(_t(vx + 28, 90 + i * 24, ln, 19, PALETTE["ink"], 600))
    o.append(_t(vx + 28, 136, f'ESCALA: {fit.scale} · confianza {fit.scale_confidence}',
                12.5, PALETTE["accent"], 700, ls=0.6))

    # ---------- banda de programa (idéntico en las tres) ------------------------------------------
    by_ = 196
    o.append(f'<rect x="{M}" y="{by_}" width="{W - 2 * M}" height="60" rx="6" fill="{PALETTE["band"]}"/>')
    o.append(_t(M + 24, by_ + 25, "EL MISMO PROGRAMA EN LAS TRES", 10.5, PALETTE["faint"], 700, ls=2.0))
    items = [("40", "puestos"), ("4", "oficinas privadas"), ("5", "salas"), ("1", "directorio de 12"),
             ("3", "phone booths"), ("1", "recepción"), ("1", "cocina"), ("1", "comedor"), ("1", "lounge")]
    x = M + 24
    for val, lab in items:
        o.append(_t(x, by_ + 48, val, 18, PALETTE["ink"], 700))
        o.append(_t(x + 8 + 11 * len(val), by_ + 48, lab, 14, PALETTE["muted"]))
        x += 34 + 11 * len(val) + 8 * len(lab)
    # SOURCE_FACT: la superficie publicada es dato del caso. COMPUTED_RESULT: la útil del modelo sale
    # de las métricas de E04, igual que en la Standard 01 (layout/e07/board.py).
    o.append(_t(W - M - 24, by_ + 25, f"{ctx.published_area_label()} publicados", 13,
                PALETTE["muted"], 600, anchor="end"))
    o.append(_t(W - M - 24, by_ + 48, f'{by[order[0]]["metrics"]["usable_area_m2"]:.0f} m² útiles del modelo',
                13, PALETTE["ink"], 600, anchor="end"))

    # ---------- columnas ---------------------------------------------------------------------------
    sy = 288
    col_h = H - sy - 128
    for k, alt in enumerate(order):
        a = by[alt]
        x = COL_X[k]
        col = PALETTE[alt]
        o.append(f'<rect x="{x}" y="{sy}" width="{COL_W}" height="{col_h}" rx="8" fill="{PALETTE["paper"]}" '
                 f'stroke="{PALETTE["line"]}"/>')
        o.append(f'<rect x="{x}" y="{sy}" width="{COL_W}" height="6" rx="3" fill="{col}"/>')
        # título
        ty = sy + 62
        o.append(_t(x + 28, ty, alt, 42, col, 700))
        o.append(_t(x + 28 + 40, ty, copy[alt]["label"], 30, PALETTE["ink"], 700, ls=-0.2))
        o.append(_t(x + 28, ty + 30, copy[alt]["priority"], 15, col, 600, ls=0.4))
        cy = ty + 56
        for ln in _wrap(copy[alt]["one_liner"], 58)[:2]:
            o.append(_t(x + 28, cy, ln, 15, PALETTE["muted"])); cy += 21
        # planta — geometría intacta
        box_y = sy + 172
        bw = COL_W - 24
        body, wv, hv = _plan(a["layout"], shell)
        bh = int(bw * hv / wv)
        o.append(f'<svg x="{x + 12}" y="{box_y}" width="{bw}" height="{bh}" viewBox="0 0 {wv} {hv}" '
                 f'preserveAspectRatio="xMidYMid meet">{body}</svg>')
        # KPIs: tres, no siete
        m, row = a["metrics"], a["row"]
        kpis = [("40", "puestos"), ("16", "recintos"),
                (f'{row["circulation_m2"]:.0f} m²', "circulación")]
        ky = box_y + bh + 62
        o.append(f'<rect x="{x + 28}" y="{ky - 46}" width="{COL_W - 56}" height="1" fill="{PALETTE["hair"]}"/>')
        kw = (COL_W - 56) / 3
        for i, (v, lab) in enumerate(kpis):
            o.append(_t(x + 28 + i * kw, ky, v, 30, PALETTE["ink"], 700))
            o.append(_t(x + 28 + i * kw, ky + 22, lab, 12, PALETTE["muted"], 500, ls=0.8))
        # callout
        cyy = ky + 62
        if callout.get(alt):
            lines = _wrap(callout[alt], 46)[:2]
            o.append(f'<rect x="{x + 28}" y="{cyy - 22}" width="4" height="{18 * len(lines) + 10}" rx="2" fill="{col}"/>')
            for i, ln in enumerate(lines):
                o.append(_t(x + 44, cyy - 6 + i * 19, ln, 14.5, PALETTE["ink"], 600))
            cyy += 19 * len(lines) + 14
        # fortalezas
        for s in (spec["strengths"].get(alt) or [])[:3]:
            for j, ln in enumerate(_wrap(s, 50)[:2]):
                if j == 0:
                    o.append(f'<circle cx="{x + 33}" cy="{cyy - 5}" r="2.6" fill="{col}"/>')
                o.append(_t(x + 46, cyy, ln, 14, PALETTE["muted"])); cyy += 19
            cyy += 5
        # ideal para, anclado abajo
        iy = sy + col_h - 62
        o.append(f'<rect x="{x + 12}" y="{iy - 30}" width="{COL_W - 24}" height="72" rx="6" fill="{PALETTE["band"]}"/>')
        o.append(_t(x + 28, iy - 8, "IDEAL PARA", 10, PALETTE["faint"], 700, ls=1.8))
        for j, ln in enumerate(_wrap(copy[alt].get("ideal_for", ""), 52)[:2]):
            o.append(_t(x + 28, iy + 14 + j * 18, ln, 14, PALETTE["ink"], 500))

    # ---------- pie: leyenda + disclaimer ----------------------------------------------------------
    fy = H - 96
    o.append(f'<rect x="{M}" y="{fy - 26}" width="{W - 2 * M}" height="1" fill="{PALETTE["line"]}"/>')
    lx = M
    for name, colr in LEGEND:
        o.append(f'<rect x="{lx}" y="{fy - 10}" width="14" height="11" rx="2" fill="{colr}" stroke="{PALETTE["line"]}"/>')
        o.append(_t(lx + 22, fy, name, 12, PALETTE["muted"])); lx += 40 + 7.0 * len(name)
    o.append(_t(M, fy + 34, spec["disclaimer_copy"], 12.5, PALETTE["muted"]))
    o.append(_t(W - M, fy, "ESCALÍMETRO PRESENTATION STANDARD 02", 11.5, PALETTE["faint"], 700,
                anchor="end", ls=1.6))
    o.append(_t(W - M, fy + 34, "Escalímetro termina donde empieza el proyecto de arquitectura.", 12.5,
                PALETTE["muted"], anchor="end"))
    o.append("</svg>")
    return "\n".join(o)
