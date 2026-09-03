from __future__ import annotations

import os
from typing import Tuple

import cv2
import numpy as np

from ..schemas.floorplate import Provenance
from .base import SegmentationProvider, SegmentationRequest, SegmentationResult


class ManualPolygonProvider(SegmentationProvider):
    """Máscara desde polígono anotado a mano (overrides.json → perimeter.ring)."""
    name = "manual"

    def segment(self, req: SegmentationRequest) -> SegmentationResult:
        if not req.polygon:
            raise ValueError("ManualPolygonProvider requiere polygon")
        h, w = req.image_bgr.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        pts = np.array(req.polygon, dtype=np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [pts], 255)
        return SegmentationResult(mask=mask, provider=self.name, confidence=1.0,
                                  provenance=Provenance.MANUAL.value, notes="polígono manual")


class OpenCVFloodProvider(SegmentationProvider):
    """Segmentación clásica por crecimiento de región desde seeds.

    Supuesto explícito (validar en Caso 001): en el plano comercial la unidad objetivo
    es una región de relleno aproximadamente uniforme (color o blanco) delimitada por
    muros más oscuros. Si el supuesto falla, el resultado se marca con baja confidence
    y el humano corrige con un polígono.

    params:
      tol         : tolerancia de color del floodFill (default 12)
      gap_px      : ancho máximo de puerta/hueco a cerrar, en px (default 30 ≈ 1 m a 30 px/m)
      wall_thresh : gris < wall_thresh se considera muro/tinta (default 110)
      min_area    : área mínima relativa a la imagen (default 0.002)
    """
    name = "opencv_flood"

    def segment(self, req: SegmentationRequest) -> SegmentationResult:
        p = {"tol": 12, "gap_px": 30, "wall_thresh": 110, "min_area": 0.002, **(req.params or {})}
        img = req.image_bgr
        h, w = img.shape[:2]
        if not req.seed_points:
            raise ValueError("OpenCVFloodProvider requiere seed_points (VLM hint o override)")
        # Muros = tinta oscura. Se dilatan gap_px/2 por lado para cerrar puertas y huecos de
        # hasta gap_px antes del flood fill; luego se dilata la región resultante para
        # recuperar la franja erosionada. gap_px ≈ ancho de puerta en px (≈1 m).
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        walls = (gray < p["wall_thresh"]).astype(np.uint8) * 255
        r = max(1, int(p["gap_px"]) // 2)
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * r + 1, 2 * r + 1))  # RECT preserva esquinas ortogonales
        walls_d = cv2.dilate(walls, k)
        blur = cv2.GaussianBlur(img, (3, 3), 0)
        blur[walls_d > 0] = (0, 0, 0)          # barrera para el flood fill
        acc = np.zeros((h, w), np.uint8)
        for (x, y) in req.seed_points:
            if walls_d[int(y), int(x)] > 0:
                continue                      # seed sobre muro dilatado: ignorar
            ff_mask = np.zeros((h + 2, w + 2), np.uint8)
            cv2.floodFill(blur.copy(), ff_mask, (int(x), int(y)), 255,
                          (p["tol"],) * 3, (p["tol"],) * 3, cv2.FLOODFILL_MASK_ONLY | 4 | (255 << 8))
            acc |= ff_mask[1:-1, 1:-1]
        if req.bbox:
            x0, y0, x1, y1 = map(int, req.bbox)
            box = np.zeros_like(acc); box[y0:y1, x0:x1] = 255
            acc &= box
        acc = cv2.dilate(acc, k)               # recuperar la franja que ocupaba el muro dilatado
        acc[walls > 0] = 0                     # pero no invadir el muro real
        # rellenar agujeros internos (textos, pilares, símbolos)
        cnts, _ = cv2.findContours(acc, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cnts:
            return SegmentationResult(mask=acc, provider=self.name, confidence=0.0,
                                      provenance=Provenance.CV_SEGMENTATION.value, notes="flood vacío")
        big = max(cnts, key=cv2.contourArea)
        filled = np.zeros_like(acc)
        cv2.drawContours(filled, [big], -1, 255, cv2.FILLED)
        frac = filled.sum() / 255 / (h * w)
        # confidence: heurística honesta — fracción razonable de la imagen
        conf = 0.6 if p["min_area"] <= frac <= 0.6 else 0.2
        notes = f"flood tol={p['tol']} gap_px={p['gap_px']} area_frac={frac:.4f} seeds={len(req.seed_points)}"
        return SegmentationResult(mask=filled, provider=self.name, confidence=conf,
                                  provenance=Provenance.CV_SEGMENTATION.value, notes=notes)


class OpenCVColorRangeProvider(SegmentationProvider):
    """Segmentación por color de relleno. Para planos comerciales donde cada unidad tiene su
    propio color (GPS, Colliers, CBRE...). Dos modos:

    - explícito: params.hsv_lo / hsv_hi (HSV OpenCV, H 0-179).
    - desde seed (default si hay seed_points): toma el color mediano de un parche alrededor del
      seed (ignorando tinta), y acepta píxeles con distancia CIELAB < params.lab_tol (default 10).
      Es lo que separa un azul pálido (unidad objetivo) de un azul medio (unidad vecina) cuando
      NO hay muro dibujado entre ambas — caso frecuente: la división es sólo de color.

    Luego: cierre morfológico chico, componente que contiene el seed (o el mayor), relleno de
    agujeros (textos, pilares, símbolos dentro de la unidad). Un hueco grande (patio, núcleo
    rodeado por la unidad) se conserva si supera params.hole_keep_frac del área (default 0.03).
    """
    name = "opencv_color"

    def segment(self, req: SegmentationRequest) -> SegmentationResult:
        p = {"lab_tol": 10.0, "close_px": 3, "sample_r": 10, "hole_keep_frac": 0.03, **(req.params or {})}
        img = req.image_bgr
        h, w = img.shape[:2]
        if "hsv_lo" in p and "hsv_hi" in p:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            raw = cv2.inRange(hsv, np.array(p["hsv_lo"]), np.array(p["hsv_hi"]))
            how = "rango HSV explícito"
        else:
            if not req.seed_points:
                raise ValueError("OpenCVColorRangeProvider requiere hsv_lo/hsv_hi o seed_points")
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sx, sy = int(req.seed_points[0][0]), int(req.seed_points[0][1])
            r = int(p["sample_r"])
            patch = lab[max(0, sy - r):sy + r, max(0, sx - r):sx + r]
            gpatch = gray[max(0, sy - r):sy + r, max(0, sx - r):sx + r]
            ref = np.median(patch[gpatch > 120].reshape(-1, 3), axis=0) if (gpatch > 120).sum() > 10 else np.median(patch.reshape(-1, 3), axis=0)
            dist = np.linalg.norm(lab - ref, axis=2)
            raw = (dist < p["lab_tol"]).astype(np.uint8) * 255
            how = f"Lab ref={[round(float(v), 1) for v in ref]} tol={p['lab_tol']}"
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (int(p["close_px"]), int(p["close_px"])))
        raw = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, k)
        if p.get("ink_barrier", True):
            # la tinta (muros, líneas) separa componentes: evita fugas por zonas de color parecido
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            raw[gray < int(p.get("ink_thresh", 100))] = 0
        n, lab_cc, stats, cents = cv2.connectedComponentsWithStats(raw, 8)
        if n <= 1:
            return SegmentationResult(mask=raw, provider=self.name, confidence=0.0,
                                      provenance=Provenance.CV_SEGMENTATION.value, notes=f"{how}; sin componentes")
        idx = None
        for (x, y) in (req.seed_points or []):
            # el seed suele caer sobre el TEXTO del label (tinta): tomar el componente más cercano
            # dentro de sample_r que tenga un área mínima
            r = int(p["sample_r"]) * 2
            ys, xs = np.mgrid[max(0, int(y) - r):min(h, int(y) + r), max(0, int(x) - r):min(w, int(x) + r)]
            labs = lab_cc[ys, xs]
            cand = [(np.hypot(xs[labs == l] - x, ys[labs == l] - y).min(), l) for l in np.unique(labs) if l > 0
                    and stats[l, cv2.CC_STAT_AREA] > 50]
            if cand:
                idx = min(cand)[1]; break
        if idx is None:
            idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        comp = (lab_cc == idx).astype(np.uint8) * 255
        # rellenar agujeros pequeños; conservar huecos grandes
        cnts, hier = cv2.findContours(comp, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        out = np.zeros_like(comp)
        outer = [i for i in range(len(cnts)) if hier[0][i][3] == -1]
        big = max(outer, key=lambda i: cv2.contourArea(cnts[i]))
        cv2.drawContours(out, cnts, big, 255, cv2.FILLED)
        area = cv2.contourArea(cnts[big])
        kept_holes = 0
        for i in range(len(cnts)):
            if hier[0][i][3] == big and cv2.contourArea(cnts[i]) >= p["hole_keep_frac"] * area:
                cv2.drawContours(out, cnts, i, 0, cv2.FILLED); kept_holes += 1
        frac = out.sum() / 255 / (h * w)
        conf = 0.7 if 0.01 <= frac <= 0.6 else 0.3
        return SegmentationResult(mask=out, provider=self.name, confidence=conf,
                                  provenance=Provenance.CV_SEGMENTATION.value,
                                  notes=f"{how}; componente con seed; area_frac={frac:.4f}; huecos conservados={kept_holes}")


class SAM2Provider(SegmentationProvider):
    """Adapter para SAM 2 (Meta). Requiere `sam2` instalado y checkpoint en ESCALIMETRO_SAM2_CKPT.
    Prompt = seed_points (positivos) y/o bbox. No se ejecuta en E01."""
    name = "sam2"

    def segment(self, req: SegmentationRequest) -> SegmentationResult:
        ckpt = os.environ.get("ESCALIMETRO_SAM2_CKPT")
        cfg = os.environ.get("ESCALIMETRO_SAM2_CFG", "sam2_hiera_l.yaml")
        if not ckpt:
            raise RuntimeError("SAM2Provider: falta ESCALIMETRO_SAM2_CKPT")
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        predictor = SAM2ImagePredictor(build_sam2(cfg, ckpt))
        predictor.set_image(cv2.cvtColor(req.image_bgr, cv2.COLOR_BGR2RGB))
        pts = np.array(req.seed_points, dtype=np.float32) if req.seed_points else None
        labels = np.ones(len(pts), dtype=np.int32) if pts is not None else None
        box = np.array(req.bbox, dtype=np.float32) if req.bbox else None
        masks, scores, _ = predictor.predict(point_coords=pts, point_labels=labels, box=box, multimask_output=True)
        i = int(np.argmax(scores))
        return SegmentationResult(mask=(masks[i] > 0).astype(np.uint8) * 255, provider=self.name,
                                  confidence=float(scores[i]), provenance=Provenance.ML_SEGMENTATION.value)


REGISTRY = {
    "manual": ManualPolygonProvider,
    "opencv_flood": OpenCVFloodProvider,
    "opencv_color": OpenCVColorRangeProvider,
    "sam2": SAM2Provider,
}
