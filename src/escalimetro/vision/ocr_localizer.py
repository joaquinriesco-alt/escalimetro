"""OCRVisionInterpreter — localización automática de la unidad objetivo por texto visible.

Método general (sin coordenadas de ningún caso):
1. OCR (tesseract) sobre la imagen ampliada ×3, modo "texto disperso" (psm 11).
2. Tokens cuyos dígitos coinciden con el número de la unidad ("403" para "Oficina 403").
3. Cada hit se clasifica por el color que lo rodea:
   - rodeado de relleno saturado  → label DENTRO de la unidad → hint `unit_region`
     (point = centro del texto, color de relleno en `notes`).
   - rodeado de blanco y con una muestra de color a la izquierda → entrada de LEYENDA
     → hint `legend_swatch` con el color de la muestra.
4. Si ambos coinciden en color, la confianza sube.

Los hints sólo localizan. El polígono lo hace la segmentación sobre píxeles reales.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .base import Hint, VisionInterpreter, VisionResult


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _ring_color(img_bgr: np.ndarray, x0: int, y0: int, x1: int, y1: int, pad: int) -> Tuple[Optional[np.ndarray], float]:
    """Color mediano (BGR) del anillo de `pad` px alrededor del bbox, ignorando píxeles oscuros
    (tinta). Devuelve (color, saturación media 0..255)."""
    h, w = img_bgr.shape[:2]
    X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)
    patch = img_bgr[Y0:Y1, X0:X1].copy()
    inner = np.zeros(patch.shape[:2], bool)
    inner[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = True
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    sel = (~inner) & (gray > 120)
    if sel.sum() < 20:
        return None, 0.0
    px = patch[sel]
    med = np.median(px, axis=0)
    sat = cv2.cvtColor(np.uint8([[med]]), cv2.COLOR_BGR2HSV)[0, 0, 1]
    return med, float(sat)


def _legend_swatch(img_bgr: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> Optional[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
    """Busca una muestra de color saturado a la izquierda del texto (patrón de leyenda)."""
    h, w = img_bgr.shape[:2]
    th = y1 - y0
    X0, X1 = max(0, x0 - 12 * th), max(0, x0 - 2)   # la leyenda puede decir 'Oficinas 403': la muestra queda lejos del número
    Y0, Y1 = max(0, y0 - th), min(h, y1 + th)
    if X1 <= X0:
        return None
    patch = img_bgr[Y0:Y1, X0:X1]
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    m = (hsv[..., 1] > 20) & (hsv[..., 2] > 80)
    if m.sum() < 0.05 * m.size:
        return None
    ys, xs = np.where(m)
    med = np.median(patch[m], axis=0)
    return med, (int(X0 + xs.min()), int(Y0 + ys.min()), int(X0 + xs.max()), int(Y0 + ys.max()))


class OCRVisionInterpreter(VisionInterpreter):
    name = "ocr"

    def __init__(self, upscale: float = 3.0, min_conf: int = 60):
        self.upscale = upscale
        self.min_conf = min_conf

    def interpret(self, image_bgr: np.ndarray, target_unit: str, known_area_m2: Optional[float] = None) -> VisionResult:
        import pytesseract
        number = _digits(target_unit)
        if not number:
            return VisionResult(provider=self.name, model="tesseract", hints=[], raw={"error": "unidad sin número"})
        big = cv2.resize(image_bgr, None, fx=self.upscale, fy=self.upscale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
        d = pytesseract.image_to_data(gray, config="--psm 11", output_type=pytesseract.Output.DICT)
        s = self.upscale
        hints: List[Hint] = []
        tokens = []
        for i, t in enumerate(d["text"]):
            conf = float(d["conf"][i])
            if not t.strip() or conf < self.min_conf:
                continue
            bb = (int(d["left"][i] / s), int(d["top"][i] / s), int((d["left"][i] + d["width"][i]) / s),
                  int((d["top"][i] + d["height"][i]) / s))
            tokens.append((t, conf, bb))
            if _digits(t) != number:
                continue
            x0, y0, x1, y1 = bb
            color, sat = _ring_color(image_bgr, x0, y0, x1, y1, pad=max(6, (y1 - y0)))
            hints.append(Hint(kind="unit_label", confidence=conf / 100, bbox=bb, text=t))
            if color is not None and sat > 20:   # rellenos pálidos (sat ~30) son comunes en planos comerciales
                hints.append(Hint(kind="unit_region", confidence=min(0.9, conf / 100), point=((x0 + x1) / 2, (y0 + y1) / 2),
                                  bbox=bb, text=t, color_bgr=tuple(int(c) for c in color),
                                  notes=f"sat={sat:.0f}; label dentro de región coloreada"))
            else:
                sw = _legend_swatch(image_bgr, x0, y0, x1, y1)
                if sw is not None:
                    col, sbb = sw
                    hints.append(Hint(kind="legend_swatch", confidence=min(0.8, conf / 100), bbox=sbb, text=t,
                                      point=(float((sbb[0] + sbb[2]) / 2), float((sbb[1] + sbb[3]) / 2)),
                                      color_bgr=tuple(int(c) for c in col), notes="muestra de leyenda"))
        # coherencia región ↔ leyenda: mismo color → sube confianza
        reg = [h for h in hints if h.kind == "unit_region"]
        leg = [h for h in hints if h.kind == "legend_swatch"]
        if reg and leg:
            cr, cl = np.array(reg[0].color_bgr), np.array(leg[0].color_bgr)
            if np.abs(cr - cl).max() < 25:
                for h in reg:
                    h.confidence = min(0.95, h.confidence + 0.1)
                    h.notes += "; coincide con leyenda"
            else:
                for h in reg:
                    h.notes += f"; NO coincide con la muestra de leyenda {leg[0].color_bgr} (leyenda inconsistente o hit falso)"
        return VisionResult(provider=self.name, model="tesseract-5", hints=hints,
                            raw={"tokens": [(t, c, list(b)) for t, c, b in tokens]})
