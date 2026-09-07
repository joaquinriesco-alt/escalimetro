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


class WholeShellProvider(SegmentationProvider):
    """E16.6 — huella de la planta en un plano de arquitectura, sin semilla.

    Por qué existe. `opencv_flood` resuelve un problema distinto: *crecer una región desde un punto
    que ya se sabe interior*. Esa abstracción es correcta para una unidad rellena de color dentro de
    una lámina multiunidad, donde el hint del OCR dice dónde empezar. Sobre un plano de planta
    completa en blanco y negro no hay tal punto: pedirle a alguien —o a una heurística— que elija
    "un píxel interior" reintroduce por la puerta de atrás la intervención que E16.5 eliminó.

    La pregunta correcta para un plano de arquitectura no es *dónde empiezo*, sino:

        ¿QUÉ ENCIERRAN LOS MUROS EXTERIORES?

    Y esa pregunta se responde por conectividad con el exterior, no por crecimiento desde un punto:
    el fondo de la hoja es alcanzable desde los bordes de la imagen; la huella del edificio no lo es.
    Todo lo que quede encerrado —mobiliario, textos, marcas de agua, núcleo, baños— está adentro por
    construcción, y no hay que reconocerlo ni removerlo. Ésa es la propiedad genérica: no depende del
    color, ni del contenido interior, ni de qué anotaciones traiga la lámina.

    El contrato de salida es el que `GeometryExtractor` consume: su contorno EXTERNO es el perímetro
    de la unidad (`RETR_EXTERNAL` + contorno mayor). Por eso la máscara es la huella LLENA delimitada
    por el muro exterior, no el espacio libre ni el área arrendable; el núcleo y las exclusiones se
    extraen aguas abajo por su cuenta.

    params:
      wall_thresh : gris < wall_thresh es tinta (muro, línea, texto). Default 110, el mismo umbral
                    de `opencv_flood`: es una constante de dominio del repo, no de un caso.
      gap_px      : ancho máximo de puerta o hueco de dibujo que se cierra antes de evaluar la
                    conectividad. Default 30, la misma noción de "≈1 m" que ya usa `opencv_flood`.
      min_roi_frac / max_roi_frac : banda plausible de la huella dentro de la región de interés.
                    `max_roi_frac` vale 1.0 a propósito: la región de interés es la extensión de la
                    tinta, y en una lámina sin anotaciones la huella ES esa extensión. Un primer
                    borrador puso 0.98 y un fixture genérico —una planta sola en la hoja, sin título—
                    lo desmintió antes de que este código viera ningún caso real. Lo que descarta una
                    máscara absurda es `min_fill` y la conectividad, no un techo sobre la fracción.
      min_fill    : cuánto de su propio recuadro debe llenar la huella. Descarta marcos delgados y
                    formas dispersas que no son una planta.
    """
    name = "whole_shell"

    def segment(self, req: SegmentationRequest) -> SegmentationResult:
        p = {"wall_thresh": 110, "gap_px": 30, "min_roi_frac": 0.10, "max_roi_frac": 1.0,
             "min_fill": 0.30, **(req.params or {})}
        img = req.image_bgr
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

        # 1. tinta = todo lo dibujado. No se distingue muro de mueble: no hace falta.
        ink = (gray < int(p["wall_thresh"])).astype(np.uint8) * 255
        # 2. cerrar puertas y huecos de dibujo para que el exterior no se filtre por un vano
        r = max(1, int(p["gap_px"]) // 2)
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * r + 1, 2 * r + 1))
        closed = cv2.dilate(ink, k)
        # 3. el exterior es lo alcanzable desde el borde de la hoja SIN cruzar tinta
        free = (closed == 0).astype(np.uint8)
        ff = np.zeros((h + 2, w + 2), np.uint8)
        border = np.zeros((h, w), np.uint8)
        for sx, sy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            if free[sy, sx]:
                cv2.floodFill(free, ff, (sx, sy), 2, 0, 0, 4)
        for x in range(0, w, max(1, w // 200)):          # el borde puede estar tapado en una esquina
            for y in (0, h - 1):
                if free[y, x] == 1:
                    cv2.floodFill(free, ff, (x, y), 2, 0, 0, 4)
        for y in range(0, h, max(1, h // 200)):
            for x in (0, w - 1):
                if free[y, x] == 1:
                    cv2.floodFill(free, ff, (x, y), 2, 0, 0, 4)
        border[free == 2] = 255
        # 4. lo NO alcanzable desde afuera: tinta + todo lo que la tinta encierra
        inside = np.where(border > 0, 0, 255).astype(np.uint8)
        # 5. la huella es la componente mayor de eso
        n, lab, stats, _ = cv2.connectedComponentsWithStats(inside, 8)
        if n <= 1:
            return SegmentationResult(mask=np.zeros((h, w), np.uint8), provider=self.name,
                                      confidence=0.0, provenance=Provenance.CV_SEGMENTATION.value,
                                      notes="sin region encerrada por tinta")
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        comp = (lab == idx).astype(np.uint8) * 255
        # 6. rellenar y devolver la franja que el cierre morfologico habia engordado
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        filled = np.zeros((h, w), np.uint8)
        cv2.drawContours(filled, [max(cnts, key=cv2.contourArea)], -1, 255, cv2.FILLED)
        filled = cv2.erode(filled, k)
        if req.bbox:
            x0, y0, x1, y1 = map(int, req.bbox)
            box = np.zeros((h, w), np.uint8); box[y0:y1, x0:x1] = 255
            filled &= box

        # 7. aceptacion: metricas declaradas de antemano, no elegidas mirando el resultado
        area = int((filled > 0).sum())
        roi_area = ((int(req.bbox[2]) - int(req.bbox[0])) * (int(req.bbox[3]) - int(req.bbox[1]))
                    if req.bbox else h * w)
        roi_frac = area / float(roi_area) if roi_area else 0.0
        ys, xs = np.where(filled > 0)
        fill = (area / float((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))) if area else 0.0
        n_cc = cv2.connectedComponentsWithStats(filled, 8)[0] - 1
        ok = (area > 0 and n_cc == 1
              and p["min_roi_frac"] <= roi_frac <= p["max_roi_frac"]
              and fill >= p["min_fill"])
        notes = (f"whole_shell wall_thresh={p['wall_thresh']} gap_px={p['gap_px']} "
                 f"roi_frac={roi_frac:.4f} fill={fill:.3f} componentes={n_cc} "
                 f"aceptacion={'PASS' if ok else 'FAIL'}")
        return SegmentationResult(mask=filled if ok else np.zeros((h, w), np.uint8),
                                  provider=self.name, confidence=0.65 if ok else 0.0,
                                  provenance=Provenance.CV_SEGMENTATION.value, notes=notes)


REGISTRY = {
    "manual": ManualPolygonProvider,
    "opencv_flood": OpenCVFloodProvider,
    "opencv_color": OpenCVColorRangeProvider,
    "sam2": SAM2Provider,
    "whole_shell": WholeShellProvider,
}
