"""E07 — ESCALÍMETRO PRESENTATION STANDARD 01.

Una lámina, tres columnas (A EFICIENTE / B BALANCEADO / C COLABORATIVO), barra lateral de programa y
leyenda, veredicto de fit y branding. Las plantas se INCRUSTAN tal cual: cada columna contiene el SVG que
produce el renderer sobre el Layout validado (`chrome=False`, sólo se omite el pie del lienzo). Ninguna
coordenada se recalcula aquí: esta capa sólo compone, colorea y titula."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ...brief import program_rows
from ...case_context import CaseContext
from ...fit_evidence import FitEvidence, PresentationFit, presentation_fit
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
# E24 §6 — el programa de la barra lateral se DERIVA del brief (brief.program_rows). Antes estaba
# escrito aquí con los números de un cliente concreto: 40 puestos, 4 privados, 16 recintos.

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


def build_board(alts: List[Dict], shell: ShellM, evidence: FitEvidence = None, subtitle: str = "",
                ctx: CaseContext = None, program: Dict = None) -> str:
    """alts: [{spec, result}] en orden A, B, C.

    E15 — la identidad del inmueble llega en `ctx` (CaseContext).
    E15.1 — el veredicto llega por separado: son dos capas distintas.
    E15.2 — el veredicto tenía que ser un `PresentationFit`, no un dict.
    E15.3 — el board recibe la **EVIDENCIA**, no la copy. Exigir un `PresentationFit` sólo comprobaba
    la forma del contenedor: `PresentationFit(...)` es un dataclass y su `__init__` es público, así
    que cualquiera podía construir uno con `technical_fit="FIT"` y llegar hasta aquí. Ahora la copy se
    deriva **dentro** de esta capa a partir de una `FitEvidence`, y `PresentationFit.from_evidence`
    rechaza una evidencia que afirme un resultado sin artefactos que lo produzcan.

    Esto no es seguridad criptográfica —quien edite el código puede mentir— sino arquitectónica: el
    camino normal de presentación ya no permite que valores escritos a mano se conviertan en un
    veredicto técnico vigente."""
    if ctx is None:
        raise ValueError("build_board necesita un CaseContext: la identidad del inmueble es dato del "
                         "caso, no un valor por defecto del board")
    if isinstance(evidence, PresentationFit):
        raise TypeError("build_board recibe la EVIDENCIA (FitEvidence), no la copy ya formateada. Un "
                        "PresentationFit construido a mano tiene el tipo correcto y ninguna "
                        "procedencia: la copy se deriva aquí dentro, desde la evidencia.")
    if not isinstance(evidence, FitEvidence):
        raise TypeError("build_board necesita una FitEvidence cargada desde los artefactos computados "
                        "(fit_evidence.load(case_dir)). Un diccionario, u otro objeto con las claves "
                        "correctas, NO es evidencia: un veredicto es un RESULTADO COMPUTADO con "
                        "procedencia, no un blob escrito a mano.")
    if not program or "program" not in program:
        raise ValueError("build_board necesita el programa compilado del BriefV1: las cantidades de la "
                         "barra lateral son dato del cliente, no literales de la lámina (E24 §6)")
    fit = presentation_fit(ctx, evidence)      # la copy se deriva DENTRO del boundary controlado
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
    for label, val in program_rows(program):
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
        # E26 §5 — lo que se muestra es la INTENCIÓN declarada de la estrategia, rotulada como tal.
        # `copy_short` e `ideal_for` eran afirmaciones comerciales sobre el resultado ("fachada
        # liberada para puestos", "empresas que priorizan costo por puesto") que este layout concreto
        # puede no demostrar. La intención sí es verdadera por construcción: es lo que el motor buscó.
        o.append(_text(x + 20, cy, "INTENCIÓN DE LA ESTRATEGIA", 10, PALETTE["muted"], 700, ls=1.4))
        cy += 18
        for ln in _wrap(spec.intent, 56)[:2]:
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
        # E26 §5 — MEDIDO EN ESTA PLANTA, no fortalezas escritas de antemano.
        # El bloque "FORTALEZAS" repetía frases fijas por alternativa ("Fachada liberada para puestos")
        # que no dependían del layout producido. Se reemplaza por cifras de esta planta: son hechos, no
        # adjetivos, y no las escribe nadie a mano ni las genera un modelo de lenguaje.
        usable = m["usable_area_m2"] or 0.0
        def _pct(v):
            return f"{(100.0 * (v or 0.0) / usable):.1f} %" if usable else "—"
        medido = [("Programa entregado", "completo" if m["program_completeness"]["complete"] else "INCOMPLETO"),
                  ("Circulación", f'{m["circulation_area_m2"]:.0f} m² · {_pct(m["circulation_area_m2"])}'),
                  ("Espacio sin asignar", f'{(m.get("unallocated_area_m2") or 0):.0f} m² · '
                                          f'{_pct(m.get("unallocated_area_m2"))}'),
                  ("Área programada neta", f'{m["net_programmed_area_m2"]:.0f} m² · '
                                           f'{_pct(m["net_programmed_area_m2"])}')]
        fy = ky + 62
        o.append(_text(x + 20, fy, "MEDIDO EN ESTA PLANTA", 11, PALETTE["muted"], 700, ls=1.6)); fy += 24
        for lab, val in medido:
            o.append(_text(x + 20, fy, lab, 12.5, PALETTE["muted"]))
            o.append(_text(x + COL_W - 20, fy, val, 12.5, PALETTE["ink"], 600, anchor="end")); fy += 21
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
        # E26 §5 — el bloque "IDEAL PARA" era una afirmación comercial sobre a qué cliente le sirve
        # esta planta. Ni el motor ni el crítico lo pueden sostener. Se retira: silencio antes que
        # copy falsa. Vuelve cuando haya revisión humana que lo respalde.
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
