"""E15 §27 — previsualización del contrato de metadatos.

Demuestra qué diría la capa de presentación para un caso **sin generar ningún layout**. Usa
exactamente el mismo camino de datos que usaría una lámina real —`CaseContext` y `fit_verdict_for`—
y pone un marcador de posición donde iría la planta.

Está marcada como METADATA CONTRACT PREVIEW · NO REAL LAYOUT precisamente para que nadie la confunda
con un test-fit. Su único propósito es responder una pregunta: si el próximo shell da FIT, ¿la
presentación diría 403 y 543 m²? La respuesta debe verse, no afirmarse."""
from __future__ import annotations

from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                        # noqa: E402

from ..case_context import CaseContext                                 # noqa: E402
from ..layout.e07.board import _wrap                                   # noqa: E402
from ..layout.e07.run import fit_verdict_for                           # noqa: E402

INK, MUT, LINE, WARN, OK = "#1d2430", "#6b7480", "#d9dce2", "#8a1f1f", "#2f6d4f"


def presentation_strings(ctx: CaseContext) -> Dict[str, str]:
    """Los textos que la lámina emitiría para este caso. Un solo origen: el CaseContext."""
    fit = fit_verdict_for(ctx)
    return {
        "cabecera": ctx.title(),
        "subtítulo": (f"Test-fit comparativo · {ctx.published_area_label()} publicados · "
                      f"programa para {fit.get('headcount', '?')} personas"),
        "pie de planta": f"{ctx.unit_title()} · A EFICIENTE",
        "superficie publicada": ctx.published_area_label(),
        "escala asumida": ctx.scale_label(),
        "veredicto de fit": " ".join(_wrap(fit.get("fit_label", ""), 20)[:2]),
        "escala declarada": f"{fit.get('scale')} · confianza {fit.get('scale_confidence')}",
        "unidad del veredicto": str(fit.get("unit")),
        "layout_id": ctx.layout_id("A", "EFICIENTE"),
        "artefacto de robustez": ctx.artifacts.robustness_png.split("/")[-1],
        "artefacto semántico": ", ".join(p.split("/")[-1] for p in ctx.artifacts.semantics_png_candidates),
    }


def render(contexts: List[CaseContext], out: str) -> str:
    n = len(contexts)
    rows = list(presentation_strings(contexts[0]).keys())
    fig, ax = plt.subplots(figsize=(6.2 + 5.2 * n, 1.9 + 0.42 * len(rows)), dpi=150)
    ax.set_facecolor("white")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    ax.text(0.005, 1.06, "METADATA CONTRACT PREVIEW · NO REAL LAYOUT", fontsize=15,
            fontweight="bold", color=WARN, transform=ax.transAxes)
    ax.text(0.005, 1.015, "Qué diría la capa de presentación para cada caso, por el mismo camino de "
                          "datos que usaría una lámina real. No hay geometría aquí.",
            fontsize=10.5, color=MUT, transform=ax.transAxes)

    xs = [0.005] + [0.30 + i * (0.70 / n) for i in range(n)]
    ax.text(xs[0], 0.955, "campo de presentación", fontsize=10.5, fontweight="bold", color=MUT)
    for i, c in enumerate(contexts):
        ax.text(xs[i + 1], 0.955, c.case_id, fontsize=10.5, fontweight="bold", color=INK)
    y = 0.90
    vals = [presentation_strings(c) for c in contexts]
    for k in rows:
        ax.text(xs[0], y, k, fontsize=10, color=MUT)
        for i, v in enumerate(vals):
            txt = v[k]
            ax.text(xs[i + 1], y, txt if len(txt) < 46 else txt[:44] + "…", fontsize=10, color=INK)
        y -= 0.90 / (len(rows) + 1)
    ax.text(0.005, -0.055, "Ningún valor de una columna aparece en otra: la identidad del inmueble "
                           "viaja como dato, no como constante del motor.",
            fontsize=10, color=OK, style="italic", transform=ax.transAxes)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out
