"""Genera un caso SINTÉTICO para probar la mecánica del pipeline (NO es el Caso 001).

Dibuja con OpenCV un piso con 3 oficinas, núcleo central, pilares y una puerta, al estilo
de un plano comercial (relleno claro, muros negros, textos). Como la geometría es conocida,
el ground truth es exacto. Sirve para: tests, benchmark de mecánica, y detectar regresiones.
No dice nada sobre la fidelidad con un JPG real: eso sólo lo prueba el Caso 001.

Uso: python fixtures/make_synthetic.py cases/900_synthetic_fixture
"""
from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from escalimetro.schemas.floorplate import (SCHEMA_VERSION, Column, Core, CoordinateSystem, Entrance, FacadeSegment,  # noqa: E402
                                             Floorplate, Meta, Perimeter, Provenance, Scale, SourceImage, Status)

PX_PER_M = 27.0         # escala verdadera (secreto para el pipeline)
W, H = 1400, 1000
WALL = 6

# Oficina objetivo "OF. 903" (sintética): polígono en L con un quiebre, en px
UNIT = [(120, 120), (760, 120), (760, 520), (560, 520), (560, 880), (120, 880)]
CORE = [(760, 380), (900, 380), (900, 620), (760, 620)]
OTHER1 = [(900, 120), (1280, 120), (1280, 520), (900, 520)]
OTHER2 = [(640, 600), (1280, 600), (1280, 880), (640, 880)]   # se dibuja antes que el core, que la tapa
CORRIDOR = [(560, 520), (760, 520), (760, 600), (640, 600), (640, 880), (560, 880)]   # pasillo en L de 80 px ≈ 3 m
COLUMNS = [(200, 200), (480, 200), (200, 480), (480, 480), (200, 800), (480, 800)]
ENTRANCE = (560, 700)   # sobre el muro este del tramo sur (da al pasillo)
COL_SIZE = int(0.5 * PX_PER_M)


def gt_ring():
    """GT = cara interior del muro (convención de la máscara y de la superficie útil)."""
    from shapely.geometry import Polygon
    inner = Polygon(UNIT).buffer(-WALL / 2, join_style=2)
    return [tuple(map(float, p)) for p in list(inner.exterior.coords)[:-1]]


def gt_area_m2():
    from shapely.geometry import Polygon
    return Polygon(gt_ring()).area / PX_PER_M ** 2


def draw(path):
    img = np.full((H, W, 3), 255, np.uint8)
    cv2.fillPoly(img, [np.array(UNIT, np.int32)], (235, 225, 210))       # oficina objetivo resaltada
    cv2.fillPoly(img, [np.array(OTHER1, np.int32)], (215, 240, 235))   # otras unidades pintadas (sat ~25)
    cv2.fillPoly(img, [np.array(OTHER2, np.int32)], (215, 240, 235))
    cv2.fillPoly(img, [np.array(CORRIDOR, np.int32)], (250, 250, 250))
    cv2.fillPoly(img, [np.array(CORE, np.int32)], (180, 180, 180))
    cv2.polylines(img, [np.array(OTHER2, np.int32)], True, (20, 20, 20), WALL)
    for poly in (UNIT, OTHER1, OTHER2, CORRIDOR, CORE):
        cv2.polylines(img, [np.array(poly, np.int32)], True, (20, 20, 20), WALL)
    # puerta: hueco en el muro + arco
    ex, ey = ENTRANCE
    cv2.rectangle(img, (ex - WALL, ey - 12), (ex + WALL, ey + 12), (235, 225, 210), -1)
    cv2.ellipse(img, (ex, ey - 12), (24, 24), 0, 0, 90, (20, 20, 20), 1)
    for (cx, cy) in COLUMNS:
        cv2.rectangle(img, (cx - COL_SIZE // 2, cy - COL_SIZE // 2), (cx + COL_SIZE // 2, cy + COL_SIZE // 2), (20, 20, 20), -1)
    # ventanas: línea doble en fachadas norte y oeste
    for (a, b) in [((120, 120), (760, 120)), ((120, 120), (120, 880))]:
        cv2.line(img, a, b, (90, 90, 90), 2)
    cv2.putText(img, "OF. 903", (330, 320), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (40, 40, 40), 2)
    cv2.putText(img, f"{gt_area_m2():.0f} m2", (330, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 40), 2)
    cv2.putText(img, "OF. 901", (1010, 320), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (40, 40, 40), 2)
    cv2.putText(img, "OF. 902", (940, 760), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (40, 40, 40), 2)
    cv2.putText(img, "NUCLEO", (775, 505), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(img, "SINTETICO - NO ES CASO 001", (20, H - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
    cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 85])


def ground_truth(case_dir):
    conf = Meta(1.0, Provenance.MANUAL.value, Status.CONFIRMED.value, "sintético exacto")
    # lados de UNIT: 0 norte(fachada) 1 este-norte(party OF901... en realidad da a OF901/core) 2 sur-interior 3 este-sur(pasillo) 4 sur(fachada) 5 oeste(fachada)
    ring = gt_ring()
    # shapely puede rotar el anillo: alinear para que empiece en el vértice más cercano a UNIT[0]
    i0 = min(range(len(ring)), key=lambda i: (ring[i][0] - UNIT[0][0]) ** 2 + (ring[i][1] - UNIT[0][1]) ** 2)
    ring = ring[i0:] + ring[:i0]
    if ring[1][1] > ring[0][1] + 1:  # orientación: el segundo vértice debe ir hacia el este (norte = índice 0)
        ring = [ring[0]] + ring[1:][::-1]
    kinds = ["facade", "unknown", "corridor", "corridor", "facade", "facade"]
    segs = [FacadeSegment(i, ring[i], ring[(i + 1) % 6], kinds[i], conf) for i in range(6)]
    from shapely.geometry import Polygon
    fp = Floorplate(SCHEMA_VERSION, "900_synthetic_fixture", "OF. 903 (sintética)",
                    SourceImage("original.jpg", W, H), CoordinateSystem(),
                    Scale(PX_PER_M, "manual", None, conf), Perimeter(ring, [], conf),
                    core=[Core([tuple(map(float, p)) for p in CORE], "core", conf)],
                    columns=[Column((float(x), float(y)), float(COL_SIZE), "square", conf) for x, y in COLUMNS],
                    entrances=[Entrance((float(ENTRANCE[0]), float(ENTRANCE[1])), 24.0, "main", conf)],
                    facade_segments=segs, area_m2=gt_area_m2(), area_px2=Polygon(ring).area, area_meta=conf)
    fp.save(os.path.join(case_dir, "ground_truth", "floorplate_gt.json"))


def main(case_dir):
    os.makedirs(os.path.join(case_dir, "ground_truth"), exist_ok=True)
    os.makedirs(os.path.join(case_dir, "outputs"), exist_ok=True)
    draw(os.path.join(case_dir, "original.jpg"))
    ground_truth(case_dir)
    area = round(gt_area_m2())   # simula "superficie publicada" redondeada
    json.dump({"case_id": "900_synthetic_fixture", "image": "original.jpg", "unit_label": "OF. 903 (sintética)",
               "known_area_m2": area, "known_area_kind": "useful", "overrides": "overrides.json",
               "vision": "manual", "segmentation": "opencv_flood"},
              open(os.path.join(case_dir, "case.json"), "w"), indent=2, ensure_ascii=False)
    # overrides mínimos que un humano daría en 1 minuto: un seed, el core y el acceso
    json.dump({"seed_points": [[300, 600]],
               "core": [{"ring": CORE, "kind": "core"}],
               "entrances": [{"point": list(ENTRANCE), "kind": "main"}]},
              open(os.path.join(case_dir, "overrides.json"), "w"), indent=2)
    with open(os.path.join(case_dir, "notes.md"), "w") as f:
        f.write("# 900_synthetic_fixture\n\nCaso SINTÉTICO generado por fixtures/make_synthetic.py. "
                "Prueba la mecánica del pipeline, no la fidelidad con planos reales. "
                f"Escala verdadera {PX_PER_M} px/m; área GT {gt_area_m2():.2f} m².\n")
    print(f"fixture en {case_dir}: área GT {gt_area_m2():.2f} m², publicada {area} m²")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "cases/900_synthetic_fixture")
