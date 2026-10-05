"""E47.2 (cierra E46-H01) — que el plano real no entre al motor disfrazado de foto.

La ceguera de CREAR se hacía cumplir por sha256: el mismo dibujo recodificado (JPEG) o
redimensionado tiene otro sha y pasaba. Acá se compara el CONTENIDO, de forma determinista y sin
red, y se corta antes de crear el proyecto o cualquier request al motor.

Dos bloqueos independientes:
  1. la foto parece un plano (`classify`, el mismo criterio de E37 `looks_like_plan`), medido sobre
     una copia reducida: el clasificador crece más que lineal con la resolución (E46-H21);
  2. la foto se parece al plano real: miniatura en grises de 32×32 (INTER_AREA), misma proporción
     y correlación de Pearson alta con diferencia media baja.

El GT sólo se lee aquí, para comparar; nada de lo que se devuelve lo contiene (ni nombre ni sha).
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional

LADO_CLASIFICACION = 512        # px del lado mayor para `classify`
LADO_MINIATURA = 32
CORR_MIN = 0.90                 # correlación de Pearson de las miniaturas
DIF_MAX = 0.12                  # diferencia media absoluta, normalizada a 0..1
PROPORCION_TOL = 0.08           # tolerancia relativa del ancho/alto

MENSAJE = ("{nombre}: parece el plano de la propiedad ({motivo}). Retira esta imagen de las fotos "
           "—el plano real se sube aparte— y vuelve a cargar el caso.")


def _leer(path: str):
    import cv2                                                # noqa: PLC0415
    return cv2.imread(path, cv2.IMREAD_COLOR)


def _miniatura(img):
    import cv2                                                # noqa: PLC0415
    import numpy as np                                        # noqa: PLC0415
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (LADO_MINIATURA, LADO_MINIATURA),
                      interpolation=cv2.INTER_AREA).astype(np.float64) / 255.0


def parece_plano(img) -> Optional[str]:
    """Motivo si `classify` ve un plano en la imagen (reducida), o None."""
    import cv2                                                # noqa: PLC0415
    from .domain.potential import classify                    # noqa: PLC0415
    h, w = img.shape[:2]
    k = LADO_CLASIFICACION / float(max(h, w))
    if k < 1:
        img = cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.png")
        cv2.imwrite(p, img)
        c = classify.classify(p)
    return c.get("why") if c.get("kind") == classify.FLOORPLAN else None


def se_parece(img, gt_img) -> bool:
    """¿Es `img` el mismo dibujo que `gt_img` (recodificado o a otro tamaño)?"""
    import numpy as np                                        # noqa: PLC0415
    ha, wa = img.shape[:2]
    hb, wb = gt_img.shape[:2]
    if abs((wa / ha) / (wb / hb) - 1.0) > PROPORCION_TOL:
        return False
    a, b = _miniatura(img), _miniatura(gt_img)
    if float(np.abs(a - b).mean()) > DIF_MAX:
        return False
    if a.std() < 1e-6 or b.std() < 1e-6:
        return False                                          # plano de un solo color: sin señal
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1]) >= CORR_MIN


def motivo_de_rechazo(foto_path: str, gt_path: Optional[str]) -> Optional[str]:
    """Texto del motivo si la foto no debe llegar al motor; None si es una foto normal."""
    img = _leer(foto_path)
    if img is None:
        return None                                           # ilegible: lo rechaza `add_asset`
    motivo = parece_plano(img)
    if motivo:
        return motivo
    gt = _leer(gt_path) if gt_path else None
    if gt is not None and se_parece(img, gt):
        return "es visualmente igual al plano real que cargaste"
    return None


def revisar_fotos(rutas: list, gt_path: Optional[str]) -> None:
    """Lanza `ValueError` con un mensaje accionable en la primera foto que sea un plano."""
    for nombre, path in rutas:
        motivo = motivo_de_rechazo(path, gt_path)
        if motivo:
            raise ValueError(MENSAJE.format(nombre=nombre, motivo=motivo))
