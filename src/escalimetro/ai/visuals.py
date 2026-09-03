"""E08 — visuales: arquitectura de proveedores, workflow, desacuerdos, latencia y 01 vs 02.

Paleta categórica validada (dataviz): #2a78d6 / #eb6834 / #1baf7a, etiquetas directas, una escala por
panel, grilla recesiva."""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, GRID, SURFACE = "#141a23", "#69727e", "#e8eaee", "#fdfdfc"
SRC_COLORS = {"rule_based": "#6b7480", "anthropic": "#2a78d6", "openai_vision": "#eb6834",
              "deterministic_visual": "#9aa2ad"}
ALT_COLORS = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0, labelsize=11)
    ax.set_axisbelow(True)


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _t(x, y, s, size=13, fill=INK, w=400, anchor="start", ls=0.0):
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" fill="{fill}" font-weight="{w}" '
            f'text-anchor="{anchor}" letter-spacing="{ls}">{_esc(s)}</text>')


def _box(x, y, w, h, fill, stroke="#d9dce2", rx=6):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>'


# ---------------------------------------------------------------------------------------------------
def provider_architecture_svg(status: Dict[str, Dict], width: int = 2200) -> str:
    W, H = 2200, 1180
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    o.append(_t(60, 66, "Arquitectura de proveedores de IA", 30, INK, 700))
    o.append(_t(60, 96, "Un propósito, un proveedor configurable, un schema local. La geometría no "
                        "pertenece a esta capa.", 15, MUTED))

    # capa de producto
    o.append(_box(60, 140, W - 120, 118, "#f2f5fa", "#c9d6e8"))
    o.append(_t(88, 176, "MOTOR DETERMINISTA DE SPACE PLANNING — FUENTE DE VERDAD", 12, "#2a78d6", 700, ls=1.6))
    for i, s in enumerate(["layout.json", "floorplate.json", "validador determinista E04",
                           "crítico por reglas E05/E07"]):
        o.append(_box(92 + i * 500, 196, 460, 44, "#ffffff", "#c9d6e8", 4))
        o.append(_t(92 + i * 500 + 20, 224, s, 15, INK, 600))

    # orquestador
    o.append(_box(60, 296, W - 120, 108, "#fbfbfa"))
    o.append(_t(88, 330, "AI ORCHESTRATOR", 12, MUTED, 700, ls=1.8))
    for i, s in enumerate(["config por env", "geometry guard (hash antes/después)", "ejecución paralela",
                           "retries y fallback", "telemetría de uso y latencia"]):
        o.append(_box(92 + i * 400, 348, 368, 40, "#ffffff", "#e0e3e8", 4))
        o.append(_t(92 + i * 400 + 18, 374, s, 14, INK))

    # proveedores
    cols = [("spatial_review", "AnthropicSpatialReviewer", "Anthropic API", "StructuredSpatialReview",
             ["payload estructurado", "sin imagen", "13 aspectos"]),
            ("visual_review", "OpenAIVisualArchitecturalCritic", "OpenAI API", "VisualArchitecturalReview",
             ["render de la planta", "11 aspectos visuales", "¿se lee la estrategia?"]),
            ("presentation", "OpenAIPresentationDirector", "OpenAI API", "PresentationSpec",
             ["handoff + reviews", "copy y jerarquía", "NO dibuja la planta"])]
    for i, (purpose, cls, api, schema, bullets) in enumerate(cols):
        x = 60 + i * ((W - 120) // 3 + 10)
        w = (W - 120) // 3 - 10
        st = status.get(purpose, {})
        ok = st.get("status") == "AVAILABLE"
        color = "#2f6d4f" if ok else "#b5452f"
        o.append(_box(x, 442, w, 300, "#ffffff"))
        o.append(f'<rect x="{x}" y="442" width="{w}" height="5" rx="2" fill="{color}"/>')
        o.append(_t(x + 24, 486, cls, 18, INK, 700))
        o.append(_t(x + 24, 512, f'{api} · modelo: {st.get("model", "—")}', 13.5, MUTED))
        o.append(_t(x + 24, 540, f'schema: {schema}', 13, "#2a78d6", 600))
        for j, b in enumerate(bullets):
            o.append(f'<circle cx="{x + 30}" cy="{562 + j * 24}" r="2.6" fill="{MUTED}"/>')
            o.append(_t(x + 44, 567 + j * 24, b, 13.5, INK))
        o.append(_box(x + 24, 650, w - 48, 62, "#f7f7f5", "#e0e3e8", 4))
        o.append(_t(x + 40, 674, "ESTADO", 10, MUTED, 700, ls=1.6))
        o.append(_t(x + 40, 698, st.get("status", "—"), 17, color, 700))

    # fallback
    o.append(_box(60, 776, W - 120, 128, "#f7f7f5"))
    o.append(_t(88, 812, "FALLBACK DETERMINISTA — SIEMPRE DISPONIBLE", 12, MUTED, 700, ls=1.8))
    o.append(_t(88, 846, "Si Anthropic no está, la revisión estructurada la hace el crítico por reglas. "
                         "Si OpenAI no está, la crítica visual la sustituye una heurística geométrica que "
                         "DECLARA que no vio la planta.", 15, INK))
    o.append(_t(88, 876, "El space planning nunca depende de que un LLM esté arriba.", 15, "#2f6d4f", 600))

    # prohibiciones
    o.append(_box(60, 936, W - 120, 176, "#fdf6f4", "#e8c9c0"))
    o.append(_t(88, 972, "LO QUE NINGÚN PROVEEDOR PUEDE HACER", 12, "#b5452f", 700, ls=1.8))
    bans = ["cambiar coordenadas", "mover muros", "mover muebles", "cambiar puestos", "cambiar recintos",
            "cambiar puertas", "cambiar pilares", "cambiar circulación", "alterar escala",
            "declarar válida una geometría inválida"]
    for i, b in enumerate(bans):
        x = 92 + (i % 5) * 410
        y = 1008 + (i // 5) * 38
        o.append(_t(x, y, "×", 17, "#b5452f", 700))
        o.append(_t(x + 20, y, b, 15, INK))
    o.append(_t(88, 1096, "Garantía técnica: geometry_hash antes y después de cada llamada. Si cambia, la "
                          "corrida falla.", 14, "#b5452f", 600))
    o.append("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------------------------------------------
def ai_workflow_svg(width: int = 2200) -> str:
    W, H = 2200, 860
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    o.append(_t(60, 62, "Workflow: el solver filtra, la IA opina, el código renderiza", 28, INK, 700))
    o.append(_t(60, 92, "Control de costo por diseño: las APIs sólo ven tres layouts, nunca los miles de "
                        "candidatos internos.", 15, MUTED))
    steps = [("miles de candidatos", "~2 700 por alternativa", "#e8eaee", "#69727e"),
             ("validación determinista", "programa, colisiones, circulación", "#dfe7f5", "#2a78d6"),
             ("A / B / C validados", "3 layouts, geometry_locked", "#dfeee2", "#2f6d4f"),
             ("capa de IA", "3 revisores en paralelo", "#f7e3d3", "#eb6834"),
             ("agregador", "consenso o desacuerdo", "#f2e7db", "#b5452f"),
             ("PresentationSpec", "copy y jerarquía, sin geometría", "#ece0ef", "#7a4fa3"),
             ("renderer determinista", "STANDARD 02", "#dfeee2", "#2f6d4f")]
    x, y, w, h = 60, 150, 268, 108
    for i, (title, sub, fill, stroke) in enumerate(steps):
        o.append(_box(x, y, w, h, fill, stroke))
        for j, ln in enumerate(_wrap_svg(title, 20)[:2]):
            o.append(_t(x + 18, y + 36 + j * 22, ln, 16, INK, 700))
        o.append(_t(x + 18, y + 88, sub, 12, MUTED))
        if i < len(steps) - 1:
            o.append(f'<path d="M{x + w + 6},{y + h / 2} l22,0" stroke="{MUTED}" stroke-width="2"/>')
            o.append(f'<path d="M{x + w + 28},{y + h / 2} l-8,-5 l0,10 z" fill="{MUTED}"/>')
        x += w + 30
    # gasto
    o.append(_box(60, 300, W - 120, 96, "#f7f7f5"))
    o.append(_t(88, 336, "COSTO", 11, MUTED, 700, ls=1.8))
    o.append(_t(88, 368, "3 alternativas × 2 llamadas = 6 llamadas por proyecto. Si la IA viera los "
                         "candidatos, serían ~8 000 llamadas. El filtro no es una optimización: es la "
                         "condición para que esto sea viable.", 15.5, INK))
    # paralelo
    o.append(_t(60, 452, "Ejecución paralela", 20, INK, 700))
    o.append(_t(60, 478, "Anthropic no espera a OpenAI: reciben el mismo layout y son independientes. "
                         "Las barras son esquemáticas, no medidas.", 14, MUTED))
    lanes = [("rule_based", 0, 120, "#6b7480"), ("anthropic (structured)", 0, 620, "#2a78d6"),
             ("openai vision (render)", 0, 760, "#eb6834")]
    for i, (name, st, dur, col) in enumerate(lanes):
        yy = 516 + i * 52
        o.append(_t(60, yy + 22, name, 14, INK, 600))
        o.append(f'<rect x="420" y="{yy}" width="{dur}" height="30" rx="4" fill="{col}" opacity="0.85"/>')
        o.append(_t(430 + dur, yy + 21, "esquema — los tiempos reales están en ai_latency_profile.png", 12, MUTED))
    o.append(f'<line x1="420" y1="500" x2="420" y2="690" stroke="{GRID}" stroke-width="2"/>')
    o.append(_t(420, 712, "t0 — mismo payload a los tres", 12, MUTED))
    o.append(_box(60, 740, W - 120, 88, "#fdf6f4", "#e8c9c0"))
    o.append(_t(88, 776, "SI UN PROVEEDOR CAE", 11, "#b5452f", 700, ls=1.8))
    o.append(_t(88, 806, "timeout · 429 · JSON malformado · schema inválido · respuesta vacía → reintento "
                         "acotado → si falla, se registra provider_status y el pipeline continúa con los "
                         "demás. El space planning no se detiene.", 15, INK))
    o.append("</svg>")
    return "\n".join(o)


def _wrap_svg(t, n):
    out, line = [], ""
    for w in str(t).split():
        if len(line) + len(w) + 1 > n:
            out.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


# ---------------------------------------------------------------------------------------------------
def disagreements_png(aggs: Dict[str, Dict], mock: Optional[Dict], path: str):
    """Panel izquierdo: la corrida REAL. Panel derecho: dry-run con fixtures MOCK que ejercita el
    agregador cuando sí hay tres fuentes. El panel MOCK está rotulado como tal en el título."""
    n = 2 if mock else 1
    fig, axes = plt.subplots(1, n, figsize=(9.6 * n, 6.0), dpi=130, squeeze=False)
    fig.patch.set_facecolor("#ffffff")
    panels = [("Corrida real E08", aggs)] + ([("Dry-run con fixtures MOCK (no son opiniones reales)", mock)]
                                             if mock else [])
    for ax, (title, data) in zip(axes.ravel(), panels):
        aspects, srcs = [], []
        for alt in sorted(data):
            for a in sorted(data[alt]["consensus_scores"]):
                if a not in aspects:
                    aspects.append(a)
        rows = sorted(data)
        for alt in rows:
            for d in (data[alt].get("agreements", []) + data[alt].get("disagreements", []) +
                      data[alt].get("critical_disagreements", [])):
                for s in (d.get("scores") or {}):
                    if s not in srcs:
                        srcs.append(s)
        # matriz alternativa × aspecto con el delta máximo entre familias
        M = np.full((len(rows), len(aspects)), np.nan)
        kinds = np.zeros((len(rows), len(aspects)))
        for i, alt in enumerate(rows):
            for key, k in (("agreements", 1), ("disagreements", 2), ("critical_disagreements", 3)):
                for d in data[alt].get(key, []):
                    if d["aspect"] in aspects:
                        j = aspects.index(d["aspect"])
                        M[i, j] = d.get("delta") if d.get("delta") is not None else 1.0
                        kinds[i, j] = k
        cmap = matplotlib.colors.ListedColormap(["#f2f3f5", "#dfeee2", "#fbe6d6", "#f3c9bf"])
        ax.imshow(kinds, cmap=cmap, vmin=0, vmax=3, aspect="auto")
        for i in range(len(rows)):
            for j in range(len(aspects)):
                if kinds[i, j] < 2:                     # los acuerdos se leen por color, sin número
                    continue
                lab = "!" if np.isnan(M[i, j]) else f"{M[i, j]:.2f}"
                ax.text(j, i, lab, ha="center", va="center", fontsize=11, color=INK,
                        fontweight="700" if kinds[i, j] == 3 else "600")
        ax.set_xticks(range(len(aspects)))
        ax.set_xticklabels([a.replace("_", " ") for a in aspects], rotation=40, ha="right", fontsize=10)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([f'{r} · {data[r]["status"]}' for r in rows], fontsize=11, fontweight="700")
        ax.set_title(title, fontsize=13.5, color=INK, loc="left", pad=12, fontweight="700")
        ax.tick_params(colors=MUTED, length=0, pad=8)
        for s in ax.spines.values():
            s.set_visible(False)
    handles = [matplotlib.patches.Patch(facecolor=c, label=l) for c, l in
               (("#dfeee2", "acuerdo (Δ ≤ 0.12)"), ("#fbe6d6", "desacuerdo (Δ ≥ 0.30)"),
                ("#f3c9bf", "desacuerdo crítico"), ("#f2f3f5", "sin comparación entre familias"))]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=10.5, labelcolor=INK,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Acuerdos y desacuerdos entre críticos", fontsize=15.5, color=INK, x=0.008, ha="left",
                 y=0.995, fontweight="700")
    fig.tight_layout(rect=[0, 0.05, 1, 0.94])
    fig.savefig(path, facecolor="#ffffff", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------------
def latency_png(latencies: Dict[str, Dict[str, float]], status: Dict[str, Dict], path: str):
    fig, ax = plt.subplots(figsize=(13, 4.6), dpi=130)
    fig.patch.set_facecolor("#ffffff")
    srcs = ["rule_based", "anthropic", "openai_vision"]
    alts = sorted(latencies)
    y = np.arange(len(alts) * len(srcs), dtype=float)
    labels, vals, colors = [], [], []
    for a in alts:
        for s in srcs:
            labels.append(f"{a} · {s}")
            vals.append(float(latencies[a].get(s, 0.0)))
            colors.append(SRC_COLORS[s])
    bars = ax.barh(y[::-1], vals, color=colors, height=0.62, zorder=3, edgecolor="#ffffff", linewidth=1.5)
    for b, v, lab in zip(bars, vals, labels):
        note = ""
        purpose = {"anthropic": "spatial_review", "openai_vision": "visual_review"}.get(lab.split("· ")[1])
        if purpose and status.get(purpose, {}).get("status") != "AVAILABLE":
            note = "  (provider_unavailable — falla inmediata, sin llamada de red)"
        ax.text(v + max(vals) * 0.012, b.get_y() + b.get_height() / 2, f"{v:.1f} ms{note}",
                va="center", fontsize=10.5, color=INK)
    ax.set_yticks(y[::-1]); ax.set_yticklabels(labels, fontsize=11, color=INK)
    ax.set_xlabel("milisegundos (los tres revisores corren en paralelo)", color=MUTED, fontsize=11)
    ax.set_xlim(0, max(max(vals) * 1.6, 1.0))
    _style(ax); ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_title("Latencia por revisor y alternativa", fontsize=14, color=INK, loc="left", pad=14,
                 fontweight="700")
    fig.tight_layout(); fig.savefig(path, facecolor="#ffffff"); plt.close(fig)


# ---------------------------------------------------------------------------------------------------
def standard_compare_png(p01: str, p02: str, path: str, width: int = 2600):
    """01 arriba, 02 abajo, a la misma escala. La geometría es idéntica; cambia sólo la presentación."""
    a, b = cv2.imread(p01), cv2.imread(p02)
    tiles = []
    for img, label, color in ((a, "PRESENTATION STANDARD 01  (E07)", (90, 90, 90)),
                              (b, "PRESENTATION STANDARD 02  (E08)  -  misma geometria, otra lamina",
                               (60, 120, 40))):
        im = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])))
        bar = np.full((72, width, 3), 255, np.uint8)
        cv2.putText(bar, label, (24, 48), cv2.FONT_HERSHEY_DUPLEX, 1.1, color, 2, cv2.LINE_AA)
        cv2.line(bar, (0, 70), (width, 70), (220, 222, 226), 2)
        tiles.append(np.vstack([bar, im]))
    pad = np.full((36, width, 3), 255, np.uint8)
    cv2.imwrite(path, np.vstack([tiles[0], pad, tiles[1]]))
