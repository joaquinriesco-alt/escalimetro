"""E09 — las diez visuales del experimento.

Regla de honestidad gráfica: un bloque sin datos se dibuja como BLOQUEADO, con la razón escrita, y nunca
con una barra en cero que se pueda confundir con una medición. Paleta categórica validada de E07/E08."""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
from matplotlib.patches import Patch     # noqa: E402

INK, MUTED, GRID, SURFACE = "#141a23", "#69727e", "#e8eaee", "#fdfdfc"
BLOCK_BG, BLOCK_INK = "#f4f5f7", "#b5452f"
SRC = [("rule_based", "rule-based", "#6b7480"), ("anthropic", "Anthropic", "#2a78d6"),
       ("openai_vision", "OpenAI Vision", "#eb6834")]
ALT_COLORS = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}
ALTS = ["A", "B", "C"]
STATUS_COLORS = {"AGREEMENT": "#dfeee2", "PARTIAL": "#f2f3f5", "DISAGREEMENT": "#fbe6d6",
                 "CRITICAL_DISAGREEMENT": "#f3c9bf", "BLOCKED": "#eceef2"}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0, labelsize=10.5)
    ax.set_axisbelow(True)


def _blocked(ax, title: str, reason: str, sub: str = ""):
    ax.set_facecolor(BLOCK_BG)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([]); ax.set_yticks([])
    ax.text(0.5, 0.60, "BLOQUEADO", ha="center", va="center", fontsize=22, color=BLOCK_INK,
            fontweight="700", transform=ax.transAxes)
    ax.text(0.5, 0.44, reason, ha="center", va="center", fontsize=12, color=INK, wrap=True,
            transform=ax.transAxes)
    if sub:
        ax.text(0.5, 0.30, sub, ha="center", va="center", fontsize=11, color=MUTED,
                transform=ax.transAxes)
    ax.set_title(title, fontsize=13, color=INK, loc="left", pad=12, fontweight="700")


def _fig(title: str, subtitle: str, figsize, nrows=1, ncols=1, **kw):
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, dpi=130, squeeze=False, **kw)
    fig.patch.set_facecolor("#ffffff")
    h = float(figsize[1])
    fig.text(0.008, 1 - 0.34 / h, title, fontsize=16, color=INK, ha="left", va="top", fontweight="700")
    if subtitle:
        fig.text(0.008, 1 - 0.68 / h, subtitle, fontsize=11.5, color=MUTED, ha="left", va="top")
    fig._e09_top = 1 - (1.05 if subtitle else 0.7) / h
    return fig, axes


def _save(fig, path, rect=(0, 0.02, 1, 0.90)):
    r = list(rect)
    r[3] = min(r[3], getattr(fig, "_e09_top", r[3]))
    fig.tight_layout(rect=r)
    fig.savefig(path, facecolor="#ffffff")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------------
# 1 — revisiones reales
# ---------------------------------------------------------------------------------------------------
def real_reviews(d: Dict, path: str):
    from .e09 import COMPARABLE, score_of
    fig, axes = _fig("Revisiones reales por alternativa",
                     "Tres fuentes independientes sobre la misma geometría. Una fuente sin llamada real "
                     "se dibuja como bloqueada, nunca como cero.", (15, 9.5), 3, 1)
    for i, alt in enumerate(ALTS):
        ax = axes[i][0]
        present = [(s, lab, col) for s, lab, col in SRC if d["reviews"][alt].get(s)]
        if not present:
            _blocked(ax, f"{alt}", "ninguna fuente emitió revisión", "")
            continue
        x = np.arange(len(COMPARABLE), dtype=float)
        w = 0.8 / max(len(SRC), 1)
        for k, (s, lab, col) in enumerate(SRC):
            rv = d["reviews"][alt].get(s)
            vals = [score_of(rv, a) for a in COMPARABLE] if rv else []
            if not rv:
                continue
            xs = [x[j] + (k - 1) * w for j, v in enumerate(vals) if v is not None]
            ys = [v for v in vals if v is not None]
            ax.bar(xs, ys, width=w * 0.92, color=col, label=lab, zorder=3, edgecolor="#ffffff",
                   linewidth=1.2)
        blocked = [lab for s, lab, _ in SRC if not d["reviews"][alt].get(s)]
        if blocked:
            ax.text(0.995, 0.93, "sin datos: " + ", ".join(blocked), transform=ax.transAxes,
                    ha="right", fontsize=10.5, color=BLOCK_INK, fontweight="700")
        ax.set_ylim(0, 1.05)
        ax.set_xticks(x)
        ax.set_xticklabels([a.replace("_", " ") for a in COMPARABLE] if i == 2 else [],
                           rotation=32, ha="right", fontsize=9.5)
        ax.set_ylabel(f"{alt}", fontsize=13, color=INK, fontweight="700", rotation=0, labelpad=18)
        _style(ax); ax.yaxis.grid(True, color=GRID, lw=0.8)
        if i == 0:
            ax.legend(loc="upper left", frameon=False, ncol=3, fontsize=10.5, labelcolor=INK)
    _save(fig, path, (0, 0.01, 1, 0.93))


# ---------------------------------------------------------------------------------------------------
# 2 — matriz de acuerdo
# ---------------------------------------------------------------------------------------------------
def agreement_matrix_png(d: Dict, path: str):
    from .e09 import COMPARABLE
    rows = d["matrix"]
    fig, axes = _fig("Matriz de acuerdo entre críticos",
                     "Δ máximo entre fuentes por aspecto. Umbrales de E08, sin recalibrar.", (15, 5.2))
    ax = axes[0][0]
    M = np.zeros((len(ALTS), len(COMPARABLE)))
    order = ["BLOCKED", "PARTIAL", "AGREEMENT", "DISAGREEMENT", "CRITICAL_DISAGREEMENT"]
    for r in rows:
        i, j = ALTS.index(r["alternative_id"]), COMPARABLE.index(r["aspect"])
        M[i, j] = order.index(r["agreement_status"])
    cmap = matplotlib.colors.ListedColormap([STATUS_COLORS[s] for s in order])
    ax.imshow(M, cmap=cmap, vmin=0, vmax=len(order) - 1, aspect="auto")
    for r in rows:
        i, j = ALTS.index(r["alternative_id"]), COMPARABLE.index(r["aspect"])
        txt = "—" if r["delta_max"] is None else f'{r["delta_max"]:.2f}'
        ax.text(j, i, txt, ha="center", va="center", fontsize=10.5, color=INK,
                fontweight="700" if r["agreement_status"] == "CRITICAL_DISAGREEMENT" else "400")
    ax.set_xticks(range(len(COMPARABLE)))
    ax.set_xticklabels([a.replace("_", " ") for a in COMPARABLE], rotation=32, ha="right", fontsize=10)
    ax.set_yticks(range(len(ALTS)))
    ax.set_yticklabels(ALTS, fontsize=13, fontweight="700")
    ax.tick_params(colors=MUTED, length=0, pad=8)
    for s in ax.spines.values():
        s.set_visible(False)
    n_block = sum(1 for r in rows if r["agreement_status"] == "BLOCKED")
    ax.set_title(f'"—" = una sola fuente disponible: no hay comparación posible '
                 f'({n_block} de {len(rows)} celdas)', fontsize=12, color=BLOCK_INK, loc="left", pad=12)
    fig.legend(handles=[Patch(facecolor=STATUS_COLORS[s], label=s.replace("_", " ").lower()) for s in order],
               loc="lower center", ncol=5, frameon=False, fontsize=10.5, labelcolor=INK,
               bbox_to_anchor=(0.5, -0.01))
    _save(fig, path, (0, 0.06, 1, 0.90))


# ---------------------------------------------------------------------------------------------------
# 3 — caso recepción
# ---------------------------------------------------------------------------------------------------
def reception_png(d: Dict, path: str):
    fig, axes = _fig("Caso de control: la recepción",
                     "El crítico por reglas la penaliza en las tres alternativas. La pregunta de E09 es si "
                     "los modelos lo confirman.", (15, 5.2), 1, 3)
    for i, alt in enumerate(ALTS):
        ax = axes[0][i]
        c = d["reception"][alt]
        ax.axvspan(0, 0.5, color="#fbeae6", zorder=0)
        ax.axvspan(0.65, 1.0, color="#eef6f1", zorder=0)
        ax.axvline(0.65, color="#dfe2e6", lw=1, zorder=1)
        for k, (s, lab, col) in enumerate(SRC):
            v = c.get(s)
            y = 2 - k
            ax.text(-0.03, y, lab, ha="right", va="center", fontsize=10.5, color=INK,
                    transform=ax.get_yaxis_transform(which="grid"))
            if v is None:
                ax.text(0.5, y, "no ejecutado", ha="center", va="center", fontsize=10.5,
                        color=BLOCK_INK, fontweight="700")
            else:
                ax.scatter([v], [y], s=170, color=col, zorder=4, edgecolor="#ffffff", linewidth=1.5)
                ax.text(v, y + 0.3, f"{v:.2f}", ha="center", fontsize=11, color=INK, fontweight="700")
        ax.set_xlim(0, 1); ax.set_ylim(-0.5, 2.75)
        ax.set_yticks([]); ax.set_xticks([0, 0.5, 1.0])
        ax.set_xticklabels(["0", "0.50", "1"], fontsize=10)
        _style(ax); ax.xaxis.grid(False)
        ax.set_title(f'{alt} · {c["classification"]}', fontsize=13, color=INK, loc="left", pad=10,
                     fontweight="700")
        words, line, lines = c["reason"].split(), "", []
        for w in words:
            if len(line) + len(w) + 1 > 42:
                lines.append(line); line = w
            else:
                line = f"{line} {w}".strip()
        lines.append(line)
        for j, ln in enumerate(lines[:3]):
            ax.text(0.0, -0.14 - j * 0.075, ln, transform=ax.transAxes, fontsize=9.5, color=MUTED)
    _save(fig, path, (0.03, 0.10, 1, 0.88))


# 4 — legibilidad de estrategia
# ---------------------------------------------------------------------------------------------------
def strategy_png(d: Dict, path: str):
    fig, axes = _fig("¿La estrategia declarada se lee en la planta?",
                     "A eficiencia · B equilibrio · C colaboración. La heurística por reglas no es un "
                     "juicio; los modelos son quienes deben responder.", (14, 5.0))
    ax = axes[0][0]
    x = np.arange(3, dtype=float)
    w = 0.26
    any_ai = False
    for k, (s, lab, col) in enumerate(SRC):
        key = {"rule_based": "rule_based_heuristic", "anthropic": "anthropic_structured",
               "openai_vision": "openai_visual"}[s]
        vals = [d["strategy"][a][key] for a in ALTS]
        xs = [x[j] + (k - 1) * w for j, v in enumerate(vals) if v is not None]
        ys = [v for v in vals if v is not None]
        if ys:
            any_ai |= s != "rule_based"
            b = ax.bar(xs, ys, width=w * 0.9, color=col, label=lab, zorder=3, edgecolor="#ffffff",
                       linewidth=1.5)
            for bb, v in zip(b, ys):
                ax.text(bb.get_x() + bb.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center",
                        fontsize=11, color=INK, fontweight="700")
        else:
            for j in range(3):
                ax.text(x[j] + (k - 1) * w, 0.04, "sin\ndato", ha="center", va="bottom", fontsize=9.5,
                        color=BLOCK_INK, fontweight="700")
    ax.set_xticks(x); ax.set_xticklabels(["A EFICIENTE", "B BALANCEADO", "C COLABORATIVO"],
                                         fontsize=12, fontweight="700")
    ax.set_xlim(-0.55, 2.62)
    ax.set_ylim(0, 1.30); _style(ax); ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.legend(loc="upper left", frameon=False, ncol=3, fontsize=10.5, labelcolor=INK)
    if not any_ai:
        ax.text(0.985, 0.965, "Los dos modelos no ejecutaron: la comparación que da sentido a este "
                              "gráfico sigue pendiente.", transform=ax.transAxes, ha="right",
                va="top", fontsize=12, color=BLOCK_INK, fontweight="700")
    _save(fig, path)


# ---------------------------------------------------------------------------------------------------
# 5 — ablación
# ---------------------------------------------------------------------------------------------------
def ablation_png(d: Dict, path: str):
    fig, axes = _fig("Ablación de proveedores",
                     "¿Hacen falta los dos modelos? Cuatro configuraciones sobre las mismas tres plantas.",
                     (14, 5.4))
    ax = axes[0][0]
    ax.set_xlim(0, 10); ax.set_ylim(0, 5)
    ax.axis("off")
    cols = ["configuración", "fuentes", "issues", "acuerdos", "desacuerdos", "confianza", "latencia máx",
            "costo", "estado"]
    xs = [0.1, 2.5, 4.0, 4.9, 5.9, 7.05, 7.85, 8.75, 9.55]
    for x, c in zip(xs, cols):
        ax.text(x, 4.45, c.upper(), fontsize=9.5, color=MUTED, fontweight="700")
    ax.plot([0.05, 9.95], [4.3, 4.3], color=GRID, lw=1.2)
    for i, r in enumerate(d["ablation"]):
        y = 3.7 - i * 0.85
        blocked = r["status"] != "EXECUTED"
        ax.text(xs[0], y, r["config"], fontsize=12.5, color=INK, fontweight="700")
        ax.text(xs[0], y - 0.28, r["label"], fontsize=10.5, color=MUTED)
        ax.text(xs[1], y, str(len(r["sources"])), fontsize=12, color=INK)
        if blocked:
            ax.text(xs[2], y, "sin dato — falta " + ", ".join(r.get("blocked_sources", [])),
                    fontsize=11, color=BLOCK_INK, fontweight="600")
            ax.text(xs[8], y, "BLOCKED", fontsize=11.5, color=BLOCK_INK, fontweight="700")
        else:
            for x, v in zip(xs[2:8], [r["issues_detected"], r["agreements"], r["disagreements"],
                                      f'{r["confidence"]:.2f}' if r["confidence"] is not None else "—",
                                      f'{r["max_latency_ms"]:.0f} ms',
                                      f'US$ {r["estimated_cost_usd"]:.4f}']):
                ax.text(x, y, str(v), fontsize=12, color=INK)
            ax.text(xs[8], y, "OK", fontsize=11.5, color="#2f6d4f", fontweight="700")
        ax.plot([0.05, 9.95], [y - 0.45, y - 0.45], color="#f1f2f4", lw=1)
    _save(fig, path, (0, 0.02, 1, 0.88))


# ---------------------------------------------------------------------------------------------------
# 6 — costo y latencia
# ---------------------------------------------------------------------------------------------------
def cost_latency_png(d: Dict, path: str):
    fig, axes = _fig("Costo y latencia reales del workflow",
                     "Todo lo que cobró y todo lo que tardó esta corrida de tres alternativas.",
                     (15, 4.8), 1, 2)
    ax = axes[0][0]
    labels, tok_in, tok_out, cost, cols = [], [], [], [], []
    for s, lab, col in SRC:
        g = d["by_source"].get(s)
        labels.append(lab); cols.append(col)
        tok_in.append(g["input_tokens"] if g else 0)
        tok_out.append(g["output_tokens"] if g else 0)
        cost.append(g["estimated_cost"] if g else 0.0)
    y = np.arange(len(labels))[::-1]
    ax.barh(y, tok_in, color=cols, height=0.35, zorder=3, label="entrada")
    ax.barh(y - 0.38, tok_out, color=cols, height=0.35, alpha=0.55, zorder=3, label="salida")
    for i, (a, b) in enumerate(zip(tok_in, tok_out)):
        src = SRC[i][0]
        g = d["by_source"].get(src) or {}
        calls = g.get("calls", 0)
        if src == "rule_based":
            note, col = f"  ·  {calls} llamadas locales, sin tokens ni costo", MUTED
        elif calls == 0:
            note, col = "  ·  SIN LLAMADA REAL — API KEY MISSING", BLOCK_INK
        else:
            note, col = f"  ·  {calls} llamadas a la API", INK
        ax.text(max(a, b) + max(max(tok_in + tok_out), 1) * 0.02, y[i] - 0.19,
                f"{a} in / {b} out · US$ {cost[i]:.4f}{note}", va="center", fontsize=10.5,
                color=col, fontweight="700" if col == BLOCK_INK else "400")
    ax.set_yticks(y - 0.19); ax.set_yticklabels(labels, fontsize=11.5, color=INK)
    ax.set_xlabel("tokens", color=MUTED, fontsize=11)
    ax.set_xlim(0, max(max(tok_in + tok_out) * 1.9, 10))
    _style(ax); ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_title("Tokens y costo por fuente", fontsize=13, color=INK, loc="left", pad=10, fontweight="700")

    ax = axes[0][1]
    seq, par = d["sequential_equivalent_ms"], d["parallel_wall_ms"]
    ax.barh([1], [seq], color="#9aa2ad", height=0.42, zorder=3)
    ax.barh([0], [par], color="#2f6d4f", height=0.42, zorder=3)
    ax.text(seq * 1.02, 1, f"{seq:.0f} ms  equivalente secuencial", va="center", fontsize=11, color=INK)
    ax.text(par * 1.02, 0, f"{par:.0f} ms  real, en paralelo", va="center", fontsize=11, color=INK,
            fontweight="700")
    ax.set_yticks([]); ax.set_xlim(0, max(seq, par) * 1.75)
    ax.set_xlabel("milisegundos", color=MUTED, fontsize=11)
    _style(ax); ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_title(f'Latencia: {d["latency_saved_pct"]:.0f} % ahorrado por paralelismo', fontsize=13,
                 color=INK, loc="left", pad=10, fontweight="700")
    _save(fig, path)


# ---------------------------------------------------------------------------------------------------
# 7 — geometry hash
# ---------------------------------------------------------------------------------------------------
def geometry_hash_png(d: Dict, path: str):
    fig, axes = _fig("Geometry guard — hash canónico antes y después de toda la capa de IA",
                     "shell · recintos · puestos · mobiliario · puertas · pilares · circulación · escala",
                     (15, 3.9))
    ax = axes[0][0]
    ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 4)
    for x, c in ((0.1, "ALTERNATIVA"), (1.4, "HASH ANTES (sha256)"), (5.2, "HASH DESPUÉS"), (9.0, "IDÉNTICO")):
        ax.text(x, 3.5, c, fontsize=10, color=MUTED, fontweight="700")
    ax.plot([0.05, 9.95], [3.35, 3.35], color=GRID, lw=1.2)
    for i, a in enumerate(ALTS):
        y = 2.85 - i * 0.7
        ok = d["hash_before"][a] == d["hash_after"][a]
        ax.text(0.1, y, a, fontsize=15, color=ALT_COLORS[a], fontweight="700")
        ax.text(1.4, y, d["hash_before"][a][:44], fontsize=10.5, color=INK, family="monospace")
        ax.text(5.2, y, d["hash_after"][a][:44], fontsize=10.5, color=INK, family="monospace")
        ax.text(9.0, y, "SI" if ok else "NO", fontsize=14,
                color="#2f6d4f" if ok else BLOCK_INK, fontweight="700")
        ax.plot([0.05, 9.95], [y - 0.3, y - 0.3], color="#f1f2f4", lw=1)
    ok = d["geometry_ok"]
    ax.text(0.1, 0.45, "geometry_locked = true — ninguna llamada a IA movió una coordenada."
            if ok else "E09 FAIL — la geometría cambió", fontsize=13,
            color="#2f6d4f" if ok else BLOCK_INK, fontweight="700")
    _save(fig, path, (0, 0.02, 1, 0.88))


# ---------------------------------------------------------------------------------------------------
# 8 — valor por proveedor
# ---------------------------------------------------------------------------------------------------
def value_summary_png(d: Dict, path: str):
    fig, axes = _fig("Valor incremental por proveedor",
                     "Juicio cualitativo sobre esta corrida. Sin fórmulas falsas de ROI.", (14, 4.8))
    ax = axes[0][0]
    ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 4)
    cols = [(0.1, "PROVEEDOR"), (2.6, "ROL"), (5.6, "HALLAZGOS ÚNICOS"), (7.3, "DUPLICADOS"),
            (8.3, "VALOR INCREMENTAL")]
    for x, c in cols:
        ax.text(x, 3.5, c, fontsize=9.5, color=MUTED, fontweight="700")
    ax.plot([0.05, 9.95], [3.35, 3.35], color=GRID, lw=1.2)
    tone = {"ESSENTIAL": "#2f6d4f", "USEFUL": "#2a78d6", "MARGINAL": "#c9a227",
            "REDUNDANT": "#b5452f", "INSUFFICIENT_EVIDENCE": BLOCK_INK, "PENDING_JUDGEMENT": MUTED}
    for i, r in enumerate(d["value"]):
        y = 2.8 - i * 0.8
        lab = dict((s, l) for s, l, _ in SRC)[r["provider"]]
        col = dict((s, c) for s, _, c in SRC)[r["provider"]]
        ax.text(0.1, y, lab, fontsize=13, color=col, fontweight="700")
        ax.text(2.6, y, r["role"], fontsize=11.5, color=INK)
        ax.text(5.6, y, "—" if r["unique_useful_findings"] is None else str(r["unique_useful_findings"]),
                fontsize=12, color=INK)
        ax.text(7.3, y, "—" if r["duplicate_findings"] is None else str(r["duplicate_findings"]),
                fontsize=12, color=INK)
        ax.text(8.3, y, r["incremental_value"].replace("_", " "), fontsize=11.5,
                color=tone.get(r["incremental_value"], INK), fontweight="700")
        if r.get("reason"):
            ax.text(2.6, y - 0.3, r["reason"][:96], fontsize=10, color=MUTED)
        ax.plot([0.05, 9.95], [y - 0.48, y - 0.48], color="#f1f2f4", lw=1)
    _save(fig, path, (0, 0.02, 1, 0.88))


# ---------------------------------------------------------------------------------------------------
# 9 — 01 vs 02 vs 03
# ---------------------------------------------------------------------------------------------------
def compare_three(case: str, out: str, path: str, width: int = 2400):
    p01 = os.path.join(case, "layouts", "E07", "ESCALIMETRO_PRESENTATION_STANDARD_01.png")
    p02 = os.path.join(case, "ai", "E08", "ESCALIMETRO_PRESENTATION_STANDARD_02.png")
    p03 = os.path.join(out, "ESCALIMETRO_PRESENTATION_STANDARD_03.png")
    tiles = []
    for p, label, col in ((p01, "STANDARD 01  (E07)  -  direccion humana", (90, 90, 90)),
                          (p02, "STANDARD 02  (E08)  -  PresentationSpec determinista", (60, 120, 40)),
                          (p03, "STANDARD 03  (E09)  -  PresentationSpec de OpenAI", (47, 69, 181))):
        bar = np.full((70, width, 3), 255, np.uint8)
        cv2.putText(bar, label, (24, 46), cv2.FONT_HERSHEY_DUPLEX, 0.95, col, 2, cv2.LINE_AA)
        cv2.line(bar, (0, 68), (width, 68), (220, 222, 226), 2)
        if os.path.exists(p):
            im = cv2.imread(p)
            im = cv2.resize(im, (width, int(im.shape[0] * width / im.shape[1])))
        else:
            im = np.full((360, width, 3), 244, np.uint8)
            cv2.putText(im, "NO PRODUCIDA", (int(width * 0.34), 150), cv2.FONT_HERSHEY_DUPLEX, 1.8,
                        (47, 69, 181), 3, cv2.LINE_AA)
            cv2.putText(im, "Sin PresentationSpec real de OpenAI no hay lamina 03: dirigirla yo mismo",
                        (int(width * 0.13), 220), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (110, 114, 126), 2,
                        cv2.LINE_AA)
            cv2.putText(im, "invalidaria la ablacion 02 vs 03, que es justo lo que E09 quiere medir.",
                        (int(width * 0.14), 262), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (110, 114, 126), 2,
                        cv2.LINE_AA)
        tiles.append(np.vstack([bar, im]))
    pad = np.full((30, width, 3), 255, np.uint8)
    cv2.imwrite(path, np.vstack([tiles[0], pad, tiles[1], pad, tiles[2]]))


# ---------------------------------------------------------------------------------------------------
def render_all(out: str, d: Dict):
    real_reviews(d, os.path.join(out, "real_reviews_abc.png"))
    agreement_matrix_png(d, os.path.join(out, "provider_agreement_matrix.png"))
    reception_png(d, os.path.join(out, "reception_case_study.png"))
    strategy_png(d, os.path.join(out, "strategy_readability_comparison.png"))
    ablation_png(d, os.path.join(out, "provider_ablation.png"))
    cost_latency_png(d, os.path.join(out, "real_cost_latency.png"))
    geometry_hash_png(d, os.path.join(out, "geometry_hash_check.png"))
    value_summary_png(d, os.path.join(out, "provider_value_summary.png"))
    compare_three(d["case"], out, os.path.join(out, "presentation_01_02_03.png"))
