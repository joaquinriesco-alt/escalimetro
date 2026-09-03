"""E07 — Visuales: diagramas de SpatialGraph, comparación A/B/C y perfil de rendimiento.

Paleta categórica validada con el validador del skill dataviz (light, surface #fcfcfb):
A #2a78d6 · B #eb6834 · C #1baf7a — separación CVD ΔE 9.2 (deuteranopía) y 27.6 en visión normal.
El aqua queda bajo 3:1 de contraste con el fondo, así que TODAS las barras llevan etiqueta directa
(relieve exigido por el validador). Un eje por gráfico, sin dobles escalas, grilla recesiva."""
from __future__ import annotations

from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..render import _poly_pts, _Tf
from .graph import SpatialGraph

ALT_COLORS = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}
INK, MUTED, GRID, SURFACE = "#1d2430", "#6b7480", "#e6e8ec", "#fcfcfb"
REL_COLORS = {"must_connect": "#1d2430", "client_route": "#b5452f", "prefer_near": "#2a78d6",
              "prefer_far": "#8b93a1", "daylight_preference": "#eda100", "shared_support": "#1baf7a",
              "acoustic_separation": "#4a3aa7", "privacy_gradient": "#e87ba4", "entrance_priority": "#b5452f",
              "staff_route": "#6b7480"}
ZONE_X = {"PUBLIC": 0, "SEMI_PUBLIC": 1, "WORK": 2, "SUPPORT": 3, "": 4}


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def spatial_graph_svg(graphs: List[SpatialGraph], width: int = 2400) -> str:
    """Tres paneles: nodos por zona (público → semi-público → trabajo → soporte) y relaciones tipadas."""
    PW, PH = 780, 545
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{3 * PW + 60}" height="{PH + 120}" '
         f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
         f'<rect width="100%" height="100%" fill="#ffffff"/>']
    for gi, g in enumerate(graphs):
        ox = 20 + gi * (PW + 10)
        col = list(ALT_COLORS.values())[gi]
        o.append(f'<rect x="{ox}" y="20" width="{PW - 20}" height="{PH + 60}" rx="6" fill="#fbfbfa" stroke="#e2e4e8"/>')
        o.append(f'<rect x="{ox}" y="20" width="{PW - 20}" height="4" rx="2" fill="{col}"/>')
        o.append(f'<text x="{ox + 20}" y="58" font-size="20" font-weight="700" fill="{INK}">{_esc(g.graph_id.replace("_", " — "))}</text>')
        y0 = 84
        for j, ln in enumerate(_wrap(g.intent, 74)[:3]):
            o.append(f'<text x="{ox + 20}" y="{y0 + j * 17}" font-size="12" fill="{MUTED}">{_esc(ln)}</text>')
        # posiciones: columna por zona, apilado por orden
        anchors = {"entrance": (ox + 60, 190), "facade_premium": (ox + PW - 90, 175),
                   "core": (ox + PW - 90, 560), "circulation": (ox + PW / 2 - 10, 560)}
        pos, per_zone = {}, {}
        for n in g.nodes:
            if n.kind == "anchor":
                pos[n.id] = anchors.get(n.id, (ox + PW / 2, 400))
                continue
            zx = ZONE_X.get(n.zone, 4)
            k = per_zone.get(zx, 0); per_zone[zx] = k + 1
            pos[n.id] = (ox + 110 + zx * 165, 245 + k * 62)
        # aristas
        for e in g.edges:
            if e.a not in pos or e.b not in pos:
                continue
            (x1, y1), (x2, y2) = pos[e.a], pos[e.b]
            c = REL_COLORS.get(e.relation, MUTED)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 26
            dash = '' if e.hard else ' stroke-dasharray="5,4"'
            o.append(f'<path d="M{x1:.0f},{y1:.0f} Q{mx:.0f},{my:.0f} {x2:.0f},{y2:.0f}" fill="none" stroke="{c}" '
                     f'stroke-width="{2.4 if e.hard else 1.4}" opacity="{0.95 if e.hard else 0.6}"{dash}/>')
        # nodos
        for n in g.nodes:
            x, y = pos[n.id]
            if n.kind == "anchor":
                o.append(f'<rect x="{x - 62:.0f}" y="{y - 15:.0f}" width="124" height="28" rx="14" fill="#eef0f3" stroke="#c8ccd4"/>')
                o.append(f'<text x="{x:.0f}" y="{y + 5:.0f}" font-size="11.5" fill="{MUTED}" text-anchor="middle" font-weight="600">{_esc(n.id)}</text>')
                continue
            label = n.id.replace("open_work_neighborhood_", "barrio ").replace("_12", " 12").replace("_8", " 8").replace("_4", " 4")
            fill = {"PUBLIC": "#f7e3d3", "SEMI_PUBLIC": "#dfeee2", "WORK": "#dfe7f5", "SUPPORT": "#f2e7db"}.get(n.zone, "#eeeeee")
            extra = f" ×{n.count}" if n.count > 1 else (f" · {n.seats}p" if n.seats else "")
            o.append(f'<rect x="{x - 74:.0f}" y="{y - 17:.0f}" width="148" height="34" rx="5" fill="{fill}" stroke="#c8ccd4"/>')
            o.append(f'<text x="{x:.0f}" y="{y + 4:.0f}" font-size="12" fill="{INK}" text-anchor="middle">{_esc(label + extra)}</text>')
        # encabezados de zona
        for z, zx in (("PÚBLICO", 0), ("SEMI-PÚBLICO", 1), ("TRABAJO", 2), ("SOPORTE", 3)):
            o.append(f'<text x="{ox + 110 + zx * 165:.0f}" y="222" font-size="10.5" fill="{MUTED}" '
                     f'text-anchor="middle" font-weight="700" letter-spacing="1">{z}</text>')
    # leyenda de relaciones
    lx, ly = 30, PH + 96
    o.append(f'<text x="{lx}" y="{ly}" font-size="11.5" font-weight="700" fill="{MUTED}">RELACIONES:</text>')
    lx += 110
    for rel, c in REL_COLORS.items():
        o.append(f'<line x1="{lx}" y1="{ly - 4}" x2="{lx + 26}" y2="{ly - 4}" stroke="{c}" stroke-width="2.4"/>')
        o.append(f'<text x="{lx + 32}" y="{ly}" font-size="11.5" fill="{INK}">{rel}</text>')
        lx += 46 + 7.2 * len(rel)
    o.append(f'<text x="30" y="{ly + 22}" font-size="11.5" fill="{MUTED}">Línea continua = relación dura '
             f'(el motor la traduce en restricción). Línea punteada = preferencia ponderada.</text>')
    o.append("</svg>")
    return "\n".join(o)


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


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=10, length=0)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def comparison_png(rows: List[Dict], path: str):
    """Pequeños múltiplos: una métrica por panel, tres barras (A/B/C) con etiqueta directa."""
    panels = [("architectural_score", "Score arquitectónico", "{:.2f}", True),
              ("daylight", "Luz en puestos (0–1)", "{:.2f}", True),
              ("circulation_m2", "Circulación (m²)", "{:.0f}", False),
              ("residual_m2", "Espacio residual (m²)", "{:.0f}", False),
              ("client_route", "Recorrido de cliente (0–1)", "{:.2f}", True),
              ("boardroom_path_m", "Directorio: ruta desde acceso (m)", "{:.1f}", False),
              ("facade_consumption_pct", "Fachada con luz ocupada por recintos (%)", "{:.0f}", False),
              ("work_blocks", "Bloques de trabajo (barrios)", "{:.0f}", None),
              ("generation_s", "Tiempo de generación (s)", "{:.0f}", False)]
    fig, axes = plt.subplots(3, 3, figsize=(15, 10.5), dpi=130)
    fig.patch.set_facecolor("#ffffff")
    alts = [r["alt"] for r in rows]
    colors = [ALT_COLORS[a] for a in alts]
    for ax, (key, title, fmt, higher_better) in zip(axes.ravel(), panels):
        vals = [(r.get(key) if r.get(key) is not None else 0) for r in rows]
        bars = ax.bar(alts, vals, color=colors, width=0.62, zorder=3, edgecolor=SURFACE, linewidth=2)
        top = max(vals) if max(vals) > 0 else 1
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + top * 0.045, fmt.format(v), ha="center", va="bottom",
                    fontsize=11, color=INK, fontweight="600")
        ax.set_ylim(0, top * 1.30)
        sub = "" if higher_better is None else ("↑ mejor" if higher_better else "↓ mejor")
        ax.set_title(f"{title}   {sub}", fontsize=11.5, color=INK, loc="left", pad=10, fontweight="600")
        _style(ax)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.yaxis.grid(False)
    fig.suptitle("Comparación A / B / C · mismo shell, mismo programa, mismas restricciones duras",
                 fontsize=15, color=INK, x=0.012, ha="left", y=0.985, fontweight="700")
    fig.text(0.012, 0.945, "A EFICIENTE (azul) · B BALANCEADO (naranja) · C COLABORATIVO (verde) — "
                           "no hay ganador absoluto: cada columna optimiza objetivos distintos.",
             fontsize=11, color=MUTED, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(path, facecolor="#ffffff"); plt.close(fig)


def performance_png(profiles: List[Dict], path: str, target_s: float = 120.0):
    """Barras apiladas horizontales: tiempo por etapa y alternativa (una sola escala, etiquetas directas)."""
    stages = [("candidate_generation_s", "Generación de candidatos", "#2a78d6"),
              ("warm_start_s", "Warm start (capacidad)", "#7fb0e8"),
              ("solver_feasibility_s", "CP-SAT factibilidad", "#eb6834"),
              ("solver_optimization_s", "CP-SAT optimización", "#f2a882"),
              ("validation_s", "Validación determinista", "#1baf7a"),
              ("critic_s", "Crítico arquitectónico", "#8fd8bd"),
              ("render_s", "Render", "#eda100")]
    fig, ax = plt.subplots(figsize=(13, 5.0), dpi=130)
    fig.patch.set_facecolor("#ffffff")
    ys = np.arange(len(profiles))[::-1]
    labels = [f'{p["alternative"]}' for p in profiles]
    for k, p in enumerate(profiles):
        left = 0.0
        for key, name, col in stages:
            v = float(p.get(key) or 0.0)
            if v <= 0:
                continue
            ax.barh(ys[k], v, left=left, color=col, height=0.55, zorder=3, edgecolor="#ffffff", linewidth=2,
                    label=name if k == 0 else None)
            if v >= 6:
                ax.text(left + v / 2, ys[k], f"{v:.0f}", ha="center", va="center", fontsize=10, color="#ffffff",
                        fontweight="700")
            left += v
        ax.text(left + 2, ys[k], f"total {p['total_s']:.0f} s" + ("  · geometría reutilizada" if p.get("reused_geometry") else ""),
                va="center", fontsize=11, color=INK, fontweight="600")
    ax.axvline(target_s, color="#b5452f", lw=1.4, ls="--", zorder=4)
    ax.text(target_s + 2, ys[0] + 0.45, f"objetivo E07: {target_s:.0f} s", color="#b5452f", fontsize=10.5, fontweight="600")
    ax.set_yticks(ys); ax.set_yticklabels(labels, fontsize=12, color=INK, fontweight="700")
    ax.set_xlabel("segundos", color=MUTED, fontsize=11)
    ax.set_xlim(0, max(target_s * 1.15, max(p["total_s"] for p in profiles) * 1.25))
    _style(ax)
    ax.xaxis.grid(True, color=GRID, lw=0.8); ax.yaxis.grid(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False, fontsize=9.5, ncol=4,
              labelcolor=INK)
    ax.set_title("Perfil de rendimiento por alternativa (etapas del motor)", fontsize=14, color=INK, loc="left",
                 pad=14, fontweight="700")
    fig.tight_layout(); fig.savefig(path, facecolor="#ffffff"); plt.close(fig)


def qa_summary_png(burdens: List[Dict], path: str):
    """Resumen del QA interno: operaciones, geometría preservada y minutos estimados."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), dpi=130, gridspec_kw={"width_ratios": [1.15, 1]})
    fig.patch.set_facecolor("#ffffff")
    alts = [b["alternative"] for b in burdens]
    colors = [ALT_COLORS[a] for a in alts]
    ax = axes[0]
    vals = [b["geometry_preserved_pct"] for b in burdens]
    bars = ax.bar(alts, vals, color=colors, width=0.6, zorder=3, edgecolor=SURFACE, linewidth=2)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.1f} %", ha="center", fontsize=11, color=INK, fontweight="600")
    ax.axhline(90, color="#b5452f", ls="--", lw=1.2, zorder=4)
    ax.set_xlim(-0.6, 3.05)
    ax.text(2.55, 90.6, "umbral E1-A: 90 %", color="#b5452f", fontsize=10, ha="left")
    ax.set_ylim(0, 108); ax.set_title("Geometría automática preservada tras QA interno", fontsize=12,
                                      color=INK, loc="left", pad=10, fontweight="600")
    _style(ax); ax.set_yticks([])
    ax = axes[1]
    vals = [b["estimated_minutes"] for b in burdens]
    bars = ax.bar(alts, vals, color=colors, width=0.6, zorder=3, edgecolor=SURFACE, linewidth=2)
    for b, v, bd in zip(bars, vals, burdens):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.12, f"{v:.1f} min · {bd['operation_count']} ops",
                ha="center", fontsize=10.5, color=INK, fontweight="600")
    ax.axhline(5, color="#b5452f", ls="--", lw=1.2, zorder=4)
    ax.set_xlim(-0.6, 3.05)
    ax.text(2.55, 5.12, "umbral E1-A: 5 min", color="#b5452f", fontsize=10, ha="left")
    ax.set_ylim(0, max(6.2, max(vals) * 1.5))
    ax.set_title("QA interno: minutos ESTIMADOS (no medidos con humano)", fontsize=12, color=INK, loc="left",
                 pad=10, fontweight="600")
    _style(ax); ax.set_yticks([])
    fig.suptitle("QA interno por alternativa", fontsize=14, color=INK, x=0.012, ha="left", y=0.99, fontweight="700")
    fig.tight_layout(rect=[0, 0, 1, 0.93]); fig.savefig(path, facecolor="#ffffff"); plt.close(fig)
