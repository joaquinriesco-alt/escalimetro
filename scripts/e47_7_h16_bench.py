"""E47.7 (H16) — benchmark determinista del costo de clasificar fotos de CREAR.

Mide, por foto, lo que paga una carga de la campaña antes de llamar al motor: la guardia H01
(`plan_guard.motivo_de_rechazo`), la lectura de `add_asset` y su `_looks_like_plan`. Las imágenes se
generan con semilla fija (ruido suavizado + grano, JPEG calidad 90), así que el antes y el después
corren sobre los mismos bytes. Uso:

    PYTHONPATH=src .venv/bin/python scripts/e47_7_h16_bench.py [--salida ruta.json] [--lote 15]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DIMS = ((4000, 3000), (4000, 3000), (4000, 3000), (3024, 4032), (2048, 1536))   # (ancho, alto)


def _foto(w, h, semilla):
    import cv2
    import numpy as np
    rng = np.random.default_rng(semilla)
    base = rng.integers(0, 255, size=(h // 40, w // 40, 3), dtype=np.uint8)
    img = cv2.resize(base, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.int16)
    img += rng.integers(-18, 18, size=img.shape, dtype=np.int16)           # grano de sensor
    return np.clip(img, 0, 255).astype(np.uint8)


def _plano(w, h):
    import cv2
    import numpy as np
    img = np.full((h, w, 3), 250, np.uint8)
    for i in range(1, 8):
        cv2.rectangle(img, (w * i // 10, h // 6), (w * (i + 1) // 10, h * 5 // 6), (40, 40, 40), 6)
    cv2.line(img, (w // 10, h // 2), (w * 9 // 10, h // 2), (30, 30, 30), 5)
    return img


def preparar(dest):
    import cv2
    fotos = []
    for i, (w, h) in enumerate(DIMS):
        p = os.path.join(dest, "foto%d_%dx%d.jpg" % (i, w, h))
        cv2.imwrite(p, _foto(w, h, 100 + i), [cv2.IMWRITE_JPEG_QUALITY, 90])
        fotos.append(p)
    gt = os.path.join(dest, "gt.png")
    cv2.imwrite(gt, _plano(1600, 1200))
    plano = os.path.join(dest, "plano4000.jpg")
    cv2.imwrite(plano, _plano(4000, 3000), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return fotos, gt, plano


def costo_foto(path, gt):
    """Lo que paga una foto en la campaña: guardia H01 + lectura y clasificación de add_asset."""
    import cv2
    from webapp import plan_guard
    from webapp.domain.reconstruction import projects
    t = time.perf_counter()
    motivo = plan_guard.motivo_de_rechazo(path, gt)
    t_guardia = time.perf_counter() - t
    t = time.perf_counter()
    cv2.imread(path, cv2.IMREAD_COLOR)
    projects._looks_like_plan(path)
    t_asset = time.perf_counter() - t
    return motivo, t_guardia, t_asset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida")
    ap.add_argument("--lote", type=int, default=15)
    ap.add_argument("--repeticiones", type=int, default=3)
    a = ap.parse_args()
    import cv2
    with tempfile.TemporaryDirectory() as d:
        fotos, gt, plano = preparar(d)
        filas = []
        for p in fotos:
            runs = []
            for _ in range(a.repeticiones):
                motivo, tg, ta = costo_foto(p, gt)
                runs.append(tg + ta)
            filas.append({"archivo": os.path.basename(p), "motivo": motivo,
                          "segundos_mediana": round(statistics.median(runs), 3),
                          "segundos_guardia": round(tg, 3), "segundos_asset": round(ta, 3)})
        motivo_plano, _, _ = costo_foto(plano, gt)
    med_grande = statistics.median(f["segundos_mediana"] for f in filas[:4])
    lote = [filas[i % len(filas)]["segundos_mediana"] for i in range(a.lote)]
    res = {"python": platform.python_version(), "cv2": cv2.__version__, "cpu": os.cpu_count(),
           "dims_ancho_alto": DIMS, "fotos": filas,
           "mediana_12mp_s": round(med_grande, 3),
           "lote_s": {"fotos": a.lote, "total": round(sum(lote), 2)},
           "plano_4000x3000_bloqueado": bool(motivo_plano)}
    out = json.dumps(res, indent=2, ensure_ascii=False)
    print(out)
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")


if __name__ == "__main__":
    main()
