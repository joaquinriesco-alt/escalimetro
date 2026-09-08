"""Familia S1–S8 de E16.15 — falsar la RELACIÓN DE SELECCIÓN del productor.

P1–P12 preguntan "¿cuántas regiones propone?". Esta familia pregunta otra cosa: **¿de qué depende que
una pieza sea seleccionada?**, y está construida para romper la relación nueva —responsabilidad
topológica sobre una celda cerrada, evaluada con la MISMA dilatación canónica con la que la celda
existe— por los dos lados.

Lámina 1400×900 y trazos distintos a los de P1–P12: la relación no puede depender de la escala del
ráster ni de una geometría concreta. Ninguna coordenada, proporción o cifra viene de un plano real.

  S1 CLOSED_CELL_WITH_DOOR_GAP        recinto que sólo cierra con la reparación canónica -> SELECCIONA
  S2 SAME_GEOMETRY_WITHOUT_ANCHOR     misma estructura, sin recinto cerrado               -> NO selecciona
  S3 FURNITURE_ENCLOSURE              mobiliario que aparenta cerrar una celda            -> NO selecciona
  S4 WATERMARK_OR_TEXT_CELL           tinta gráfica cerrada dentro del alcance            -> NO selecciona
  S5 TWO_REAL_COMPONENTS_SEPARATED    dos piezas legítimas separadas por circulación      -> 2 regiones, 0 px fabricados
  S6 SMALL_VALID_ANCHOR               celda chica pero legítima                           -> SELECCIONA (desacople)
  S7 LARGE_UNRELATED_ANCHOR           recinto grande ajeno dentro del alcance             -> NO selecciona
  S8 AMBIGUOUS_STRUCTURAL_CLUSTERS    dos alternativas plausibles                         -> mide la abstención

Ejecutar: python tests/fixtures/core_selection/make_e16_15_family.py
"""
import json
import os

import cv2
import numpy as np

W, H = 1400, 900
OUT = os.path.dirname(os.path.abspath(__file__))
PAPEL, MURO, FINO, TEXTO = 255, 45, 125, 180
RING = [(100, 100), (1300, 100), (1300, 580), (1120, 580), (1120, 800), (100, 800)]


def hoja():
    return np.full((H, W), PAPEL, np.uint8)


def planta(img, t=11):
    cv2.polylines(img, [np.array(RING, np.int32)], True, MURO, t)


def recinto(img, x, y, w, h, t=9, gap=0, celdas=1):
    """Recinto de muro. `gap` deja un vano de puerta en el muro inferior: el recinto sólo queda
    cerrado tras la reparación canónica, que es exactamente la clase S1."""
    cv2.line(img, (x, y), (x + w, y), MURO, t)
    cv2.line(img, (x, y), (x, y + h), MURO, t)
    cv2.line(img, (x + w, y), (x + w, y + h), MURO, t)
    if gap:
        cv2.line(img, (x, y + h), (x + w // 2 - gap // 2, y + h), MURO, t)
        cv2.line(img, (x + w // 2 + gap // 2, y + h), (x + w, y + h), MURO, t)
    else:
        cv2.line(img, (x, y + h), (x + w, y + h), MURO, t)
    for i in range(1, celdas):
        cv2.line(img, (x + int(i * w / celdas), y), (x + int(i * w / celdas), y + h), MURO, t - 2)


def muro_abierto(img, x, y, w, h, t=9):
    """La MISMA masa de muro, en L: no encierra nada."""
    cv2.line(img, (x, y), (x + w, y), MURO, t)
    cv2.line(img, (x, y), (x, y + h), MURO, t)


def mobiliario(img, seed=6, n=45, evitar=()):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x = int(rng.integers(150, 1050)); y = int(rng.integers(150, 720))
        if any(a < x < b and c < y < d for (a, b, c, d) in evitar):
            continue
        cv2.rectangle(img, (x, y), (x + int(rng.integers(40, 80)), y + int(rng.integers(30, 60))),
                      FINO, 3)


def guardar(nombre, img, hint, espera, nota, **extra):
    cv2.imwrite(os.path.join(OUT, nombre + ".png"), cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    d = {"hint_region": hint, "footprint_ring": RING, "expected_selected": espera, "spec": nota}
    d.update(extra)
    json.dump(d, open(os.path.join(OUT, nombre + ".json"), "w"), indent=1, ensure_ascii=False)
    return nombre


A = (450, 240, 280, 200)          # recinto principal
B = (450, 560, 280, 180)          # segundo recinto, separado por circulación
EV = ((420, 1000, 200, 780),)


def main():
    hechos = []

    img = hoja(); planta(img); mobiliario(img, evitar=EV)
    # UN solo recinto con vano de puerta. La primera versión lo dibujó con cuatro celdas, y tres de
    # ellas quedaban cerradas incluso SIN la reparación canónica: el fixture no probaba la clase que
    # declara. Corregido, y declarado.
    # DOS correcciones de fixture, ambas por contradecir su propia especificación y ambas medidas
    # antes de fijarlas: (1) el vano mide MENOS que la escala de trazo —con un vano mayor ninguna de
    # las dos definiciones cierra la celda y el fixture no probaría nada—; (2) el recinto es lo
    # bastante chico como para que su celda sea un ancla: con 280×200 su interior superaba el tope
    # `ANCHOR_MAX_FRAC` y no había ancla ninguna que discutir.
    recinto(img, 450, 240, 140, 130, celdas=1, gap=18)
    hechos.append(guardar("S1_CLOSED_CELL_WITH_DOOR_GAP", img, [420, 210, 780, 480], 1,
                          "el recinto tiene un vano de puerta menor que la escala de trazo: su celda "
                          "sólo existe bajo la reparación canónica que usa el detector",
                          truth_boxes=[[450, 240, 590, 370]]))

    img = hoja(); planta(img); mobiliario(img, evitar=EV)
    muro_abierto(img, *A)
    hechos.append(guardar("S2_SAME_GEOMETRY_WITHOUT_ANCHOR", img, [420, 210, 780, 480], 0,
                          "misma masa de muro, sin recinto: estar dentro de la pista no basta",
                          truth_boxes=[]))

    img = hoja(); planta(img); mobiliario(img, evitar=EV)
    cv2.rectangle(img, (520, 300), (660, 400), FINO, 3)
    hechos.append(guardar("S3_FURNITURE_ENCLOSURE", img, [420, 210, 780, 480], 0,
                          "mobiliario que aparenta cerrar una celda dentro de la pista",
                          truth_boxes=[]))

    img = hoja(); planta(img); mobiliario(img, evitar=EV)
    cv2.putText(img, "REFERENCIAL", (450, 400), cv2.FONT_HERSHEY_SIMPLEX, 2.4, TEXTO, 6)
    hechos.append(guardar("S4_WATERMARK_OR_TEXT_CELL", img, [420, 210, 900, 480], 0,
                          "tinta gráfica cerrada dentro del alcance", truth_boxes=[]))

    img = hoja(); planta(img); mobiliario(img, evitar=EV)
    recinto(img, *A, celdas=4); recinto(img, *B, celdas=3)
    hechos.append(guardar("S5_TWO_REAL_COMPONENTS_SEPARATED", img, [420, 210, 780, 780], 2,
                          "dos piezas legítimas separadas por circulación; sin puente",
                          truth_boxes=[[450, 240, 730, 440], [450, 560, 730, 740]],
                          gap_box=[460, 460, 720, 540]))

    img = hoja(); planta(img); mobiliario(img, evitar=EV)
    recinto(img, *A, celdas=4)
    recinto(img, 830, 300, 60, 90, t=9, celdas=1)
    hechos.append(guardar("S6_SMALL_VALID_ANCHOR", img, [420, 210, 940, 480], 2,
                          "la celda chica respalda pertenencia aunque el contrato de completitud la "
                          "considere poco significativa: productor y completitud están desacoplados",
                          truth_boxes=[[450, 240, 730, 440], [830, 300, 890, 390]],
                          small_anchor_box=[830, 300, 890, 390]))

    img = hoja(); planta(img); mobiliario(img, evitar=((420, 1060, 200, 780),))
    recinto(img, *A, celdas=4)
    recinto(img, 800, 250, 250, 240, t=9)      # recinto grande: su celda supera el tope de ancla
    hechos.append(guardar("S7_LARGE_UNRELATED_ANCHOR", img, [420, 210, 1080, 520], 1,
                          "un recinto grande dentro del alcance no entra por ser grande",
                          truth_boxes=[[450, 240, 730, 440]]))

    img = hoja(); planta(img); mobiliario(img, evitar=((180, 1060, 200, 780),))
    recinto(img, 230, 250, 210, 180, celdas=3); recinto(img, 230, 560, 210, 170, celdas=3)
    recinto(img, 830, 250, 210, 180, celdas=3); recinto(img, 830, 560, 210, 170, celdas=3)
    hechos.append(guardar("S8_AMBIGUOUS_STRUCTURAL_CLUSTERS", img, [200, 220, 1080, 770], "AMBIGUO",
                          "dos alternativas plausibles bajo una pista ambigua", truth_boxes=[]))

    for n in hechos:
        print(n)


if __name__ == "__main__":
    main()
