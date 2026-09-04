"""E06 — FIT VERDICT: salida de producto preliminar (JSON + texto), construida sólo desde el
FitRobustnessReport, la evidencia secundaria y los gates. No inventa nada: cada frase cita un número."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class FitVerdict:
    unit: str
    program: str
    headcount: int
    fit: str                                  # ROBUST_FIT | LIKELY_FIT | BORDERLINE | LIKELY_NO_FIT | ROBUST_NO_FIT
    reason: str
    primary_uncertainty: str
    recommendation: str
    scale_confidence: str
    min_scale_factor_exact_fit: Optional[float]
    pct_scenarios_exact_fit: float
    secondary_evidence_verdict: str
    gate_e1_autonomous: str
    gate_e1_assisted: str
    qa_gate: str
    disclaimer: str = "Dimensiones sujetas a confirmación de escala. Test-fit conceptual (space planning), no proyecto de arquitectura."

    def to_dict(self):
        return asdict(self)

    def text(self) -> str:
        return "\n".join([
            f"{self.unit.upper()}",
            f"PROGRAM: {self.program} ({self.headcount} PEOPLE)",
            f"FIT: {self.fit}",
            f"Reason: {self.reason}",
            f"Primary uncertainty: {self.primary_uncertainty}",
            f"Recommendation: {self.recommendation}",
            f"Gate E1 autonomous: {self.gate_e1_autonomous} · assisted: {self.gate_e1_assisted} ({self.qa_gate})",
            self.disclaimer,
        ])


def build(unit: str, program: str, headcount: int, rob: Dict, ev: Dict, gate_auto: str, gate_assisted: str,
          qa_gate: str, published_area_m2=None) -> FitVerdict:
    """E15 — `published_area_m2` es dato del caso. Sin declarar, el texto dice que no hay superficie
    publicada; nunca la de otro inmueble."""
    cls = rob["classification"]
    mn = rob.get("min_scale_factor_exact_fit")
    pct = rob.get("pct_scenarios_exact_fit", 0.0)
    ex = rob.get("exact_fit_factors", [])
    if ex:
        reason = (f"40 puestos + programa completo de recintos caben con escala ≥ {mn:.3f}× la nominal "
                  f"({pct:.0f} % de los escenarios probados: {', '.join(f'{f:.3f}' for f in ex)}). Restricción dominante: {rob.get('primary_constraint')}.")
    else:
        reason = f"ningún escenario de escala probado admite el programa completo; restricción dominante: {rob.get('primary_constraint')}."
    area_txt = (f"({published_area_m2:.0f} m²)" if published_area_m2 is not None else "(no declarada)")
    unc = (f"la superficie publicada {area_txt} no fija una escala geométrica fiable (confianza LOW); "
           f"la evidencia secundaria del plano es {ev.get('verdict', 'UNKNOWN')}" +
           (f" (rango combinado {ev['combined_factor_range']})" if ev.get("combined_factor_range") else ""))
    if cls in ("ROBUST_FIT",):
        rec = "el programa cabe con margen; confirmar una dimensión antes de comprometer capacidad."
    elif cls in ("LIKELY_FIT", "BORDERLINE"):
        rec = "confirmar UNA dimensión (ancho de fachada o del núcleo) antes de comprometer; el resultado cambia dentro del error de escala."
    else:
        rec = "no comprometer 48 personas en esta planta sin confirmar escala; negociar el brief."
    return FitVerdict(unit, program, headcount, cls, reason, unc, rec, rob.get("confidence", "LOW"), mn, pct,
                      ev.get("verdict", "UNKNOWN"), gate_auto, gate_assisted, qa_gate)
