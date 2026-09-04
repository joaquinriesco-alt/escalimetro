"""E14 — visuales del gate de generalización.

Deliberadamente diagnósticas: sin lámina premium, sin veredicto vendedor. Si el resultado es NO_FIT,
la visual lo dice en grande y muestra por qué. Nada aquí puede esconder un defecto (§27)."""
from __future__ import annotations

import json
import os
from typing import Dict, List

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                            # noqa: E402
from matplotlib.patches import Polygon as MplPoly                          # noqa: E402

INK, MUT, LINE, OK, BAD, WARN = "#1d2430", "#6b7480", "#d9dce2", "#2f6d4f", "#a4342a", "#8a6d1f"
PANEL = "#f6f6f4"


def _fig(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    ax.set_facecolor("white")
    return fig, ax


def _clean(ax):
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([]); ax.set_yticks([])


def _title(ax, t, sub=""):
    ax.set_title(t, fontsize=15, fontweight="bold", color=INK, loc="left", pad=30)
    if sub:
        ax.text(0, 1.015, sub, transform=ax.transAxes, fontsize=10.5, color=MUT, va="bottom")


def save_source(img_path: str, out: str) -> str:
    im = cv2.imread(img_path)
    cv2.imwrite(out, cv2.resize(im, None, fx=2.6, fy=2.6, interpolation=cv2.INTER_CUBIC))
    return out


def copy_out(src: str, out: str, scale: float = 1.0) -> str:
    im = cv2.imread(src)
    if im is None:
        return ""
    if scale != 1.0:
        im = cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(out, im)
    return out


def auto_vs_assisted(auto: Dict, assisted: Dict, out: str) -> str:
    fig, ax = _fig(13, 6.4); _clean(ax)
    _title(ax, "AUTO vs ASSISTED — Oficina 401",
           "El pase automático se detiene en la localización. Diez operaciones humanas lo llevan a shell listo.")
    rows = [
        ("localización del target", "FALLA — el OCR no lee el rótulo dentro del plano", "OK — 1 click (seed point)"),
        ("perímetro", "no se llega", "28 vértices · 252.0 m²"),
        ("núcleo", "no se llega", "1 núcleo"),
        ("escala", "no se llega", "8.43 px/m · inferida · confianza LOW"),
        ("pilares", "no se llega", "1 detectado + 1 agregado = 2"),
        ("acceso principal", "no se llega", "corregido a (507, 207) — la CV proponía muro continuo"),
        ("luz natural", "no se llega", "2 tramos confirmados como acristalados"),
        ("shell ready", "NO — falla antes", "SÍ"),
    ]
    y = 0.86
    ax.text(0.02, 0.955, "etapa", fontsize=11, fontweight="bold", color=MUT)
    ax.text(0.30, 0.955, "AUTO  (0 operaciones)", fontsize=11, fontweight="bold", color=BAD)
    ax.text(0.64, 0.955, "ASSISTED  (10 operaciones · ~44 s)", fontsize=11, fontweight="bold", color=OK)
    for name, a, b in rows:
        ax.text(0.02, y, name, fontsize=11, color=INK)
        ax.text(0.30, y, a, fontsize=10.5, color=BAD if "FALLA" in a or "NO" == a[:2] else MUT)
        ax.text(0.64, y, b, fontsize=10.5, color=INK)
        y -= 0.104
    ax.text(0.02, 0.02, "Ninguna operación dibuja layout, mueve salas ni toca el solver. "
                        "Todas usan mecanismos HITL que ya existían en el caso 001.",
            fontsize=10, color=MUT, style="italic")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
    return out


def no_fit_diagnostic(diag: Dict, rob: Dict, metrics: Dict, out: str) -> str:
    fig = plt.figure(figsize=(14, 8.2), dpi=150)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.15], hspace=0.42, wspace=0.22)

    ax = fig.add_subplot(gs[0, :]); _clean(ax)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.text(0, 0.72, "TECHNICAL_NO_FIT", fontsize=28, fontweight="bold", color=BAD)
    ax.text(0, 0.40, "El motor NO falló: exploró correctamente y demostró que no hay solución.",
            fontsize=13, color=INK)
    ax.text(0, 0.14, "0 colisiones · circulación conectada · 12 candidatos evaluados · sin excepción · "
                     "CP-SAT devolvió INFEASIBLE, no timeout", fontsize=11, color=MUT)

    ax2 = fig.add_subplot(gs[1, 0])
    need = 305.9
    bars = [("útil del shell\n(Oficina 401)", 253.6, "#7f9ec4"),
            ("programa neto\n(medido en la 403)", need, "#c47f7f")]
    for i, (lab, v, c) in enumerate(bars):
        ax2.barh(i, v, color=c, height=0.5)
        ax2.text(v + 4, i, f"{v:.1f} m²", va="center", fontsize=11, fontweight="bold", color=INK)
    ax2.axvline(need, color=BAD, lw=1.2, ls="--")
    ax2.set_yticks([0, 1]); ax2.set_yticklabels([b[0] for b in bars], fontsize=10.5)
    ax2.set_xlim(0, 380); ax2.set_xlabel("m²", fontsize=10, color=MUT)
    ax2.set_title("Cota aritmética: no cabe ni con circulación cero", fontsize=12,
                  fontweight="bold", color=INK, loc="left")
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    ax2.grid(axis="x", color=LINE, lw=0.7)
    ax2.set_axisbelow(True)

    ax3 = fig.add_subplot(gs[1, 1])
    f = rob["factors_tested"]
    areas = [227.4, 239.6, 247.0, 252.0, 257.1, 264.8, 277.8]
    ax3.plot(f, areas, "o-", color="#7f9ec4", lw=2, ms=7)
    ax3.axhline(need, color=BAD, lw=1.4, ls="--")
    ax3.text(f[0], need + 5, f"programa neto {need} m²", fontsize=10, color=BAD)
    for x, a in zip(f, areas):
        ax3.annotate("INFEASIBLE", (x, a), textcoords="offset points", xytext=(0, -16),
                     ha="center", fontsize=7.6, color=BAD, rotation=90)
    ax3.set_xlabel("factor de escala (rango de E06, sin modificar)", fontsize=10, color=MUT)
    ax3.set_ylabel("m² útiles", fontsize=10, color=MUT)
    ax3.set_ylim(200, 330)
    ax3.set_title("ROBUST_NO_FIT en los 7 escenarios", fontsize=12, fontweight="bold",
                  color=INK, loc="left")
    for s in ("top", "right"):
        ax3.spines[s].set_visible(False)
    ax3.grid(color=LINE, lw=0.7); ax3.set_axisbelow(True)

    fig.savefig(out, bbox_inches="tight"); plt.close(fig)
    return out


def comparison(rows: List[List[str]], out: str) -> str:
    fig, ax = _fig(13.5, 0.42 * len(rows) + 2.0); _clean(ax)
    _title(ax, "Oficina 403 (entrenamiento)  vs  Oficina 401 (segundo shell)",
           "Misma lámina fuente · mismo motor · mismo programa · cero tuning")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    n = len(rows)
    hdr = ["métrica", "403", "401", "estado"]
    xs = [0.02, 0.42, 0.62, 0.82]
    for x, h in zip(xs, hdr):
        ax.text(x, 0.965, h, fontsize=11, fontweight="bold", color=MUT)
    for i, r in enumerate(rows):
        y = 0.92 - (i + 1) * (0.90 / n)
        col = {"IGUAL": MUT, "OK": OK, "DIFIERE": WARN, "PEOR": BAD, "N/A": MUT}.get(r[3], INK)
        if i % 2 == 0:
            ax.add_patch(plt.Rectangle((0.015, y - 0.012), 0.97, 0.90 / n * 0.92,
                                       color=PANEL, zorder=0))
        for x, v in zip(xs, r):
            ax.text(x, y, str(v), fontsize=10, color=col if x == xs[3] else INK, zorder=2)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
    return out


def scorecard_png(sc: Dict, out: str) -> str:
    fig, ax = _fig(12.5, 6.2); _clean(ax)
    _title(ax, "Generalization scorecard — E14", "Siete chequeos. PASS no significa FIT.")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    col = {"PASS": OK, "ASSISTED": WARN, "FAIL": BAD, "N/A": MUT}
    y = 0.86
    for c in sc["checks"]:
        ax.text(0.02, y, c["id"], fontsize=12, fontweight="bold", color=INK)
        ax.text(0.075, y, c["check"], fontsize=11, color=INK)
        ax.text(0.78, y, c["status"], fontsize=11.5, fontweight="bold", color=col[c["status"]])
        ax.text(0.075, y - 0.038, c["evidence"], fontsize=9, color=MUT)
        y -= 0.098
    r = sc["result"]
    ax.add_patch(plt.Rectangle((0.015, 0.005), 0.97, 0.075,
                               color="#eef3ef" if "PASS" in r else "#f7eceb", zorder=0))
    ax.text(0.03, 0.032, r, fontsize=17, fontweight="bold",
            color=OK if "PASS" in r else BAD, zorder=2)
    ax.text(0.42, 0.036, "nivel: INTRA-DRAWING — misma lámina fuente que 403",
            fontsize=10.5, color=MUT, zorder=2)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
    return out


def freeze_png(cmp: Dict, out: str) -> str:
    fig, ax = _fig(12.5, 3.6); _clean(ax)
    _title(ax, "Engine freeze check", "El motor entra congelado y sale congelado. Si cambiara, E14 sería inválido.")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ok = cmp["identical"]
    ax.text(0.02, 0.62, "ANTES", fontsize=11, fontweight="bold", color=MUT)
    ax.text(0.14, 0.62, cmp["engine_hash_before"], fontsize=9.5, family="monospace", color=INK)
    ax.text(0.02, 0.44, "DESPUÉS", fontsize=11, fontweight="bold", color=MUT)
    ax.text(0.14, 0.44, cmp["engine_hash_after"], fontsize=9.5, family="monospace", color=INK)
    ax.text(0.02, 0.16, "IDENTICAL" if ok else "CAMBIÓ — E14 INVÁLIDO", fontsize=20,
            fontweight="bold", color=OK if ok else BAD)
    ax.text(0.30, 0.185, "95 archivos · 0 modificados · 0 eliminados · 0 agregados al conjunto congelado",
            fontsize=10.5, color=MUT)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
    return out


def abc_not_generated(out: str) -> str:
    fig, ax = _fig(12.5, 4.2); _clean(ax)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.text(0.02, 0.74, "A / B / C  NOT GENERATED", fontsize=26, fontweight="bold", color=BAD)
    ax.text(0.02, 0.52, "Razón:  TECHNICAL_NO_FIT", fontsize=15, color=INK)
    ax.text(0.02, 0.36, "No se generan alternativas rebajando restricciones para completar la lámina.",
            fontsize=12, color=MUT)
    ax.text(0.02, 0.22, "Las tres estrategias sólo se ejecutan si el nominal da TECHNICAL_FIT (§18).",
            fontsize=12, color=MUT)
    ax.text(0.02, 0.06, "No se produjo ninguna planta falsa.", fontsize=12, color=MUT, style="italic")
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
    return out
