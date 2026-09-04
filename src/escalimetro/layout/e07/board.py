"""E07 — ESCALÍMETRO PRESENTATION STANDARD 01.

Una lámina, tres columnas (A EFICIENTE / B BALANCEADO / C COLABORATIVO), barra lateral de programa y
leyenda, veredicto de fit y branding. Las plantas se INCRUSTAN tal cual: cada columna contiene el SVG que
produce el renderer sobre el Layout validado (`chrome=False`, sólo se omite el pie del lienzo). Ninguna
coordenada se recalcula aquí: esta capa sólo compone, colorea y titula."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ...case_context import CaseContext
from ...fit_evidence import PresentationFit
from ..model import Layout, ShellM
from ..render import render_layout_svg

PALETTE = {
    "paper": "#ffffff", "panel": "#f7f7f5", "ink": "#1d2430", "muted": "#6b7480", "line": "#d9dce2",
    "accent": "#b5452f", "good": "#2f6d4f",
    "A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a",       # paleta categórica validada (dataviz)
}
LEGEND = [("Puestos de trabajo", "#dfe7f5"), ("Salas y directorio", "#dfeee2"), ("Recepción", "#f7e3d3"),
          ("Cocina / comedor / cabinas", "#f2e7db"), ("Lounge", "#ece0ef"), ("Circulación", "#fbf3dd"),
          ("Núcleo del edificio", "#e3e5e8"), ("Pilar", "#111111")]
PROGRAM_ROWS = [("Puestos open space", "40"), ("Oficinas privadas", "4"), ("Salas de 4", "3"), ("Sala de 8", "1"),
                ("Directorio de 12", "1"), ("Phone booths", "3"), ("Recepción", "1"), ("Kitchenette", "1"),
                ("Comedor", "1"), ("Lounge", "1")]

W, H = 2400, 1160
SIDEBAR_X, SIDEBAR_W = 40, 380
COL_X = [460, 1110, 1760]
COL_W = 600


def _num(t: str) -> float:
    """primer número del veredicto del crítico (los veredictos son texto auditable, no datos)."""
    m = re.search(r"(\d+(?:\.\d+)?)", t or "")
    return float(m.group(1)) if m else 0.0


def _esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _text(x, y, t, size=14, fill=PALETTE["ink"], weight=400, anchor="start", ls=0.0, opacity=1.0, family=None):
    fam = f' font-family="{family}"' if family else ""
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}" letter-spacing="{ls}" opacity="{opacity}"{fam}>{_esc(t)}</text>')


def _wrap(t: str, n: int) -> List[str]:
    out, line = [], ""
    for w in t.split():
        if len(line) + len(w) + 1 > n:
            out.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def _plan_svg(layout: Layout, shell: ShellM, width_px: int = 1300) -> Tuple[str, int, int]:
    """SVG de la planta con la MISMA geometría del layout validado, sin pie de lienzo."""
    svg = render_layout_svg(layout, shell, "commercial", width_px=width_px, chrome=False, margin=14)
    head = svg.split(">", 1)[0]
    wv = int(float(head.split('width="')[1].split('"')[0]))
    hv = int(float(head.split('height="')[1].split('"')[0]))
    body = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
    return body, wv, hv


def build_board(alts: List[Dict], shell: ShellM, fit: PresentationFit = None, subtitle: str = "",
                ctx: CaseContext = None) -> str:
    """alts: [{spec, result}] en orden A, B, C.

    E15 — la identidad del inmueble llega en `ctx` (CaseContext).
    E15.1 — el veredicto llega en `fit`, y **por separado**: son dos capas distintas y el board recibe
    las dos explícitamente. `fit` sólo puede venir de `fit_evidence.presentation_fit(ctx, evidence)`,
    que es la única función autorizada a convertir un resultado computado en copy de lámina. El board
    no puede fabricar un veredicto ni leerlo del contexto."""
    if ctx is None:
        raise ValueError("build_board necesita un CaseContext: la identidad del inmueble es dato del "
                         "caso, no un valor por defecto del board")
    if not isinstance(fit, PresentationFit):
        raise TypeError("build_board necesita un PresentationFit construido desde una FitEvidence "
                        "(fit_evidence.presentation_fit(ctx, evidence)). Un diccionario con las claves "
                        "correctas NO es evidencia: un veredicto es un RESULTADO COMPUTADO con "
                        "procedencia, no un blob escrito a mano.")
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
         f'<rect width="{W}" height="{H}" fill="{PALETTE["paper"]}"/>']
    # ---------- cabecera ---------------------------------------------------------------------------
    o.append(f'<rect x="0" y="0" width="{W}" height="112" fill="{PALETTE["panel"]}"/>')
    o.append(f'<rect x="0" y="112" width="{W}" height="2" fill="{PALETTE["line"]}"/>')
    o.append(_text(40, 52, "ESCALÍMETRO", 30, PALETTE["ink"], 700, ls=2.4))
    o.append(_text(40, 78, "pre-design · feasibility · test-fit", 12, PALETTE["muted"], 400, ls=1.6))
    o.append(f'<rect x="300" y="26" width="1.5" height="62" fill="{PALETTE["line"]}"/>')
    o.append(_text(336, 52, ctx.title(), 24, PALETTE["ink"], 600, ls=0.6))
    o.append(_text(336, 80, subtitle or (f"Test-fit comparativo · {ctx.published_area_label()} publicados · "
                                        f"programa para {fit.get('headcount', '?')} personas"),
                   14, PALETTE["muted"]))
    # veredicto (derecha)
    vx = W - 40 - 700
    o.append(f'<rect x="{vx}" y="18" width="700" height="78" rx="6" fill="#ffffff" stroke="{PALETTE["line"]}"/>')
    o.append(_text(vx + 22, 42, "FIT", 10.5, PALETTE["muted"], 700, ls=1.8))
    fit_lines = _wrap(fit.get("fit_label", "FIT NO EVALUADO"), 20)[:2]
    for i, ln in enumerate(fit_lines):
        o.append(_text(vx + 22, 64 + i * 20, ln, 18, PALETTE["good"], 700))
    o.append(f'<rect x="{vx + 400}" y="30" width="1.2" height="54" fill="{PALETTE["line"]}"/>')
    o.append(_text(vx + 430, 42, "SCALE", 10.5, PALETTE["muted"], 700, ls=1.8))
    o.append(_text(vx + 430, 64, fit.get("scale", "UNCONFIRMED"), 18, PALETTE["accent"], 700))
    o.append(_text(vx + 430, 84, f"confianza {fit.get('scale_confidence', 'UNKNOWN')}", 12, PALETTE["muted"]))
    # ---------- barra lateral ----------------------------------------------------------------------
    sy = 152
    o.append(f'<rect x="{SIDEBAR_X}" y="{sy}" width="{SIDEBAR_W}" height="{H - sy - 96}" rx="6" fill="{PALETTE["panel"]}"/>')
    y = sy + 34
    o.append(_text(SIDEBAR_X + 22, y, "PROGRAMA", 12, PALETTE["muted"], 700, ls=1.8)); y += 10
    o.append(f'<rect x="{SIDEBAR_X + 22}" y="{y}" width="{SIDEBAR_W - 44}" height="1" fill="{PALETTE["line"]}"/>')
    y += 26
    for label, val in PROGRAM_ROWS:
        o.append(_text(SIDEBAR_X + 22, y, label, 14, PALETTE["ink"]))
        o.append(_text(SIDEBAR_X + SIDEBAR_W - 22, y, val, 14, PALETTE["ink"], 700, anchor="end"))
        y += 27
    y += 6
    o.append(f'<rect x="{SIDEBAR_X + 22}" y="{y}" width="{SIDEBAR_W - 44}" height="1" fill="{PALETTE["line"]}"/>')
    y += 30
    o.append(_text(SIDEBAR_X + 22, y, "IDÉNTICO EN A, B Y C", 11, PALETTE["muted"], 600, ls=1.4)); y += 22
    for ln in _wrap("Las tres alternativas resuelven el mismo programa completo sobre el mismo shell, "
                    "con las mismas restricciones. Sólo cambia la estrategia de space planning.", 44):
        o.append(_text(SIDEBAR_X + 22, y, ln, 12.5, PALETTE["muted"])); y += 18
    y += 22
    o.append(_text(SIDEBAR_X + 22, y, "SUPERFICIE", 11, PALETTE["muted"], 600, ls=1.4)); y += 24
    for label, val in (("Publicada", ctx.published_area_label()),
                       ("Útil del modelo", f'{alts[0]["result"].metrics["usable_area_m2"]:.0f} m²'),
                       ("Escala asumida", ctx.scale_label())):
        o.append(_text(SIDEBAR_X + 22, y, label, 13, PALETTE["ink"]))
        o.append(_text(SIDEBAR_X + SIDEBAR_W - 22, y, val, 13, PALETTE["ink"], 600, anchor="end")); y += 24
    y += 18
    o.append(_text(SIDEBAR_X + 22, y, "LEYENDA", 11, PALETTE["muted"], 600, ls=1.4)); y += 20
    for name, col in LEGEND:
        o.append(f'<rect x="{SIDEBAR_X + 22}" y="{y - 10}" width="16" height="13" rx="2" fill="{col}" stroke="{PALETTE["line"]}"/>')
        o.append(_text(SIDEBAR_X + 48, y, name, 12.5, PALETTE["ink"])); y += 22
    y += 14
    o.append(f'<rect x="{SIDEBAR_X + 22}" y="{y - 14}" width="{SIDEBAR_W - 44}" height="1" fill="{PALETTE["line"]}"/>')
    y += 16
    for ln in _wrap(fit.get("recommendation", "Confirma una dimensión real antes de comprometer capacidad."), 42):
        o.append(_text(SIDEBAR_X + 22, y, ln, 12.5, PALETTE["accent"], 600)); y += 18
    # ---------- columnas ---------------------------------------------------------------------------
    for k, item in enumerate(alts):
        spec, r = item["spec"], item["result"]
        x = COL_X[k]
        col = PALETTE[spec.alt]
        o.append(f'<rect x="{x}" y="{sy}" width="{COL_W}" height="{H - sy - 96}" rx="6" fill="#ffffff" stroke="{PALETTE["line"]}"/>')
        o.append(f'<rect x="{x}" y="{sy}" width="{COL_W}" height="5" rx="2" fill="{col}"/>')
        ty = sy + 46
        o.append(f'<rect x="{x + 20}" y="{ty - 26}" width="34" height="34" rx="4" fill="{col}"/>')
        o.append(_text(x + 37, ty - 2, spec.alt, 20, "#ffffff", 700, anchor="middle"))
        o.append(_text(x + 66, ty, spec.name, 22, PALETTE["ink"], 700, ls=1.0))
        cy = ty + 26
        for ln in _wrap(spec.copy_short, 56)[:2]:
            o.append(_text(x + 20, cy, ln, 13.5, PALETTE["muted"])); cy += 19
        # planta incrustada (geometría idéntica al layout validado)
        box_y, box_h = sy + 104, 330
        o.append(f'<rect x="{x + 14}" y="{box_y}" width="{COL_W - 28}" height="{box_h}" rx="4" fill="#fdfdfc"/>')
        body, wv, hv = _plan_svg(r.layout, shell)
        o.append(f'<svg x="{x + 14}" y="{box_y}" width="{COL_W - 28}" height="{box_h}" viewBox="0 0 {wv} {hv}" '
                 f'preserveAspectRatio="xMidYMid meet">{body}</svg>')
        # KPIs
        m, c = r.metrics, r.critique
        obj = (r.layout.scores or {}).get("objectives", {})
        kpis = [("Puestos", m["program_completeness"]["open_seats"].split("/")[0]),
                ("Salas", str(sum(v for k2, v in m["program_completeness"]["rooms"].items()
                                  if k2 in ("meeting_4", "meeting_8", "boardroom_12")))),
                ("Circulación", f'{m["circulation_area_m2"]:.0f} m²'),
                ("Luz en puestos", f'{obj.get("daylight_utilization", 0):.2f}')]
        ky = box_y + box_h + 40
        kw = (COL_W - 40) / 4
        for i, (lab, val) in enumerate(kpis):
            kx = x + 20 + i * kw
            o.append(_text(kx, ky, val, 21, PALETTE["ink"], 700))
            o.append(_text(kx, ky + 19, lab, 11, PALETTE["muted"], 500, ls=0.6))
        o.append(f'<rect x="{x + 20}" y="{ky + 36}" width="{COL_W - 40}" height="1" fill="{PALETTE["line"]}"/>')
        # fortalezas
        fy = ky + 62
        o.append(_text(x + 20, fy, "FORTALEZAS", 11, PALETTE["muted"], 700, ls=1.6)); fy += 24
        for s in spec.strengths[:4]:
            lines = _wrap(s, 52)
            o.append(f'<circle cx="{x + 26}" cy="{fy - 5}" r="3" fill="{col}"/>')
            for j, ln in enumerate(lines[:2]):
                o.append(_text(x + 38, fy, ln, 13, PALETTE["ink"])); fy += 18
            fy += 6
        # detalle secundario (informativo para el revisor comercial)
        dy = fy + 16
        o.append(f'<rect x="{x + 20}" y="{dy - 26}" width="{COL_W - 40}" height="1" fill="{PALETTE["line"]}"/>')
        o.append(_text(x + 20, dy, "DETALLE", 11, PALETTE["muted"], 700, ls=1.6)); dy += 24
        det = [("Fachada con recintos cerrados", f'{_num(c["verdicts"].get("facade_use", "")):.0f} %'),
               ("Recepción desde el acceso", f'{_num(c["verdicts"].get("arrival_sequence", "")):.1f} m'),
               ("Espacio residual", f'{m["wasted_area_m2"]:.0f} m²'),
               ("Bloques de trabajo", f'{sum(1 for p in r.layout.placements if p.module.startswith("workstation"))}')]
        for lab, val in det:
            o.append(_text(x + 20, dy, lab, 12.5, PALETTE["muted"]))
            o.append(_text(x + COL_W - 20, dy, val, 12.5, PALETTE["ink"], 600, anchor="end")); dy += 21
        # ideal para
        iy = H - 96 - 74
        o.append(f'<rect x="{x + 14}" y="{iy - 26}" width="{COL_W - 28}" height="62" rx="4" fill="{PALETTE["panel"]}"/>')
        o.append(_text(x + 26, iy - 6, "IDEAL PARA", 10.5, PALETTE["muted"], 700, ls=1.4))
        for j, ln in enumerate(_wrap(spec.ideal_for, 54)[:2]):
            o.append(_text(x + 26, iy + 14 + j * 17, ln, 13, PALETTE["ink"], 500))
    # ---------- pie --------------------------------------------------------------------------------
    fy = H - 62
    o.append(f'<rect x="0" y="{fy - 26}" width="{W}" height="{H - fy + 26}" fill="{PALETTE["panel"]}"/>')
    o.append(f'<rect x="0" y="{fy - 26}" width="{W}" height="1.5" fill="{PALETTE["line"]}"/>')
    o.append(_text(40, fy, "Dimensiones sujetas a confirmación de escala · SCALE: UNCONFIRMED (superficie publicada, "
                           "confianza LOW).", 13, PALETTE["accent"], 600))
    o.append(_text(40, fy + 22, "Test-fit conceptual para evaluación de espacio. No constituye proyecto de arquitectura. "
                                "Geometría generada y validada automáticamente (programa completo, sin colisiones, "
                                "circulación conectada).", 12.5, PALETTE["muted"]))
    o.append(_text(W - 40, fy, "ESCALÍMETRO PRESENTATION STANDARD 01", 12, PALETTE["muted"], 700, anchor="end", ls=1.2))
    o.append(_text(W - 40, fy + 22, "Escalímetro termina donde empieza el proyecto de arquitectura.", 12,
                   PALETTE["muted"], anchor="end"))
    o.append("</svg>")
    return "\n".join(o)
