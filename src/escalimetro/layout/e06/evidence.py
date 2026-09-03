"""E06 — Evidencia secundaria de escala a partir del JPG y del Floorplate de E03.

Cada evidencia convierte una medida en píxeles en un RANGO de px/m usando un rango de dimensiones típicas
(nunca un valor exacto) y lo expresa como rango de factor respecto de la escala nominal. Las evidencias se
combinan sólo si son consistentes; si no, el resultado es UNKNOWN. Nada de esto es ground truth."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ...schemas.floorplate import Floorplate


@dataclass
class ScaleEvidence:
    source: str
    measured_px: float
    typical_range_m: Tuple[float, float]
    px_per_m_range: Tuple[float, float]
    factor_range: Tuple[float, float]        # respecto de la escala nominal (factor = nominal / ppm_evidencia)
    weight: float                            # 0..1: cuánto fiarse
    note: str

    def to_dict(self):
        return asdict(self)


@dataclass
class SecondaryScaleEvidence:
    nominal_px_per_m: float
    evidences: List[ScaleEvidence]
    combined_factor_range: Optional[Tuple[float, float]]
    verdict: str                             # CONSISTENT_WITH_NOMINAL | SUGGESTS_LARGER | SUGGESTS_SMALLER | UNKNOWN
    note: str

    def to_dict(self):
        return asdict(self)


def _ev(source, px, lo_m, hi_m, nominal, weight, note) -> ScaleEvidence:
    ppm = (px / hi_m, px / lo_m)                    # más metros típicos ⇒ menos px/m
    fac = (nominal / ppm[1], nominal / ppm[0])
    return ScaleEvidence(source, round(px, 2), (lo_m, hi_m), (round(ppm[0], 2), round(ppm[1], 2)),
                         (round(fac[0], 3), round(fac[1], 3)), weight, note)


def unit_fill_areas(image_path: str, samples: Dict[str, Tuple[int, int]], tol: int = 18) -> Dict[str, int]:
    """Área en px de la mancha de color conectada a cada punto de muestra (relleno de cada unidad)."""
    im = cv2.imread(image_path)
    out = {}
    for k, (x, y) in samples.items():
        c = im[y, x].astype(int)
        d = np.abs(im.astype(int) - c).sum(axis=2)
        mask = (d < tol).astype(np.uint8)
        n, lab = cv2.connectedComponents(mask)
        out[k] = int((lab == lab[y, x]).sum())
    return out


def collect(fp: Floorplate, image_path: Optional[str] = None, published: Optional[Dict[str, float]] = None,
            samples: Optional[Dict[str, Tuple[int, int]]] = None) -> SecondaryScaleEvidence:
    nominal = fp.scale.px_per_m
    evs: List[ScaleEvidence] = []
    # 1. hueco de puerta del acceso principal (wall_gap en px)
    if fp.primary_entrance is not None:
        cand = next((c for c in fp.entrance_candidates if abs(c.point[0] - fp.primary_entrance.point[0]) < 1 and abs(c.point[1] - fp.primary_entrance.point[1]) < 1), None)
        gap = None
        if cand:
            for e in cand.evidence:
                if e.startswith("wall_gap:"):
                    gap = float(e.split(":")[1].replace("px", ""))
        if gap:
            # ±2 px de error de detección a 800 px de ancho: se ensancha el rango
            evs.append(_ev("door_gap_primary_entrance", gap, 0.85, 1.10, nominal, 0.35,
                           f"hueco {gap:.0f} px ± 2 px; puerta simple típica 0.85–1.10 m; en un plano comercial el hueco dibujado no es fiable"))
            evs.append(_ev("door_gap_primary_entrance_err", gap + 2, 0.85, 1.10, nominal, 0.0, "cota de error +2 px (sólo informativa)"))
    # 2. periodo de montantes / módulo de fachada (autocorrelación de E03)
    periods = []
    for d in fp.daylight_segments:
        for e in d.evidence:
            if e.startswith("mullions:paso"):
                periods.append(float(e.split("paso")[1].split("px")[0]))
    if periods:
        per = float(np.median(periods))
        evs.append(_ev("facade_module_period", per, 2.7, 3.6, nominal, 0.3,
                       f"periodo {per:.0f} px (mediana de {len(periods)}); módulo estructural/de fachada típico 2.7–3.6 m si el periodo es de paños, "
                       f"NO de montantes finos (1.2–1.5 m daría un factor absurdo ≈ 0.45)"))
    # 3. tamaño de pilares dibujados
    sizes = [c.size_px for c in fp.column_candidates if c.status == "confirmed"]
    if sizes:
        s = float(np.median(sizes))
        evs.append(_ev("column_drawn_size", s, 0.5, 0.8, nominal, 0.1,
                       f"pilar dibujado {s:.1f} px (mediana de {len(sizes)}); pilar típico 0.5–0.8 m; en planos comerciales los pilares se dibujan exagerados: peso bajo"))
    # 4. consistencia de áreas publicadas entre unidades (misma escala ⇒ misma razón px²/m²)
    if image_path and published and samples:
        try:
            areas = unit_fill_areas(image_path, samples)
            ratios = {k: areas[k] / published[k] for k in areas if k in published and published[k] > 0 and areas[k] > 1000}
            if len(ratios) >= 2:
                ppms = {k: v ** 0.5 for k, v in ratios.items()}
                lo, hi = min(ppms.values()), max(ppms.values())
                evs.append(ScaleEvidence("published_area_consistency_across_units", float(np.mean(list(ratios.values()))),
                                         (0.0, 0.0), (round(lo, 2), round(hi, 2)), (round(nominal / hi, 3), round(nominal / lo, 3)), 0.25,
                                         f"px²/m² por unidad (relleno sin muros): {', '.join(f'{k}: {v:.0f}' for k, v in ratios.items())}; "
                                         f"dispersión {100 * (hi - lo) / lo:.0f} % ⇒ las áreas publicadas no son proporcionales al dibujo con una sola escala"))
        except Exception as e:  # noqa: BLE001
            pass
    # combinación: intersección de rangos ponderados (sólo evidencias con peso > 0)
    active = [e for e in evs if e.weight > 0]
    inter = None
    for e in active:
        r = e.factor_range
        inter = r if inter is None else (max(inter[0], r[0]), min(inter[1], r[1]))
    if not active:
        verdict, note, comb = "UNKNOWN", "sin evidencias medibles", None
    elif inter is None or inter[0] > inter[1]:
        verdict, note, comb = "UNKNOWN", "las evidencias no son consistentes entre sí (intersección vacía): no se combina", None
    else:
        comb = (round(inter[0], 3), round(inter[1], 3))
        if inter[0] <= 1.0 <= inter[1]:
            verdict = "CONSISTENT_WITH_NOMINAL"
        elif inter[0] > 1.0:
            verdict = "SUGGESTS_LARGER"
        else:
            verdict = "SUGGESTS_SMALLER"
        width = inter[1] - inter[0]
        note = f"intersección de rangos = factor {comb[0]}–{comb[1]} (ancho {100 * width:.0f} %): " + \
               ("demasiado ancha para decidir" if width > 0.1 else "acota la escala")
        if width > 0.1:
            verdict = "UNKNOWN"
    return SecondaryScaleEvidence(round(nominal, 3), evs, comb, verdict, note)
