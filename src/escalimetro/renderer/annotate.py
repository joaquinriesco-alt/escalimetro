"""Genera original_grid.png: la imagen original con grilla y coordenadas en px cada N px,
para que un humano lea coordenadas y escriba overrides.json sin editor gráfico."""
from __future__ import annotations

import cv2
import numpy as np


def grid_image(image_bgr: np.ndarray, step: int = 100) -> np.ndarray:
    img = image_bgr.copy()
    h, w = img.shape[:2]
    for x in range(0, w, step):
        cv2.line(img, (x, 0), (x, h), (0, 0, 255), 1)
        cv2.putText(img, str(x), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    for y in range(0, h, step):
        cv2.line(img, (0, y), (w, y), (255, 0, 0), 1)
        cv2.putText(img, str(y), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
    for x in range(0, w, step // 2):
        for y in range(0, h, step // 2):
            img[y, x] = (0, 0, 0)
    return img
