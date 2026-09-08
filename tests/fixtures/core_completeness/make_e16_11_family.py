"""Familia de fixtures de E16.11 — completitud del núcleo por cobertura del cluster de anclas.

A diferencia de la familia de E16.10, aquí el fixture DECLARA el candidato además de la pista. La
razón: la pregunta de este ciclo es "dado un candidato, ¿está completo?", y el productor geométrico
quedó congelado. Declarar el candidato permite construir el par A/B —mismo dibujo, misma pista, un
candidato completo y otro parcial— que es la prueba central del ciclo y que un productor
determinista, por definición, no puede darnos en el mismo dibujo.

Lámina 1400×900, planta distinta a la de cualquier caso real. Ninguna coordenada, proporción,
cantidad, área ni color proviene de un plano de desarrollo.

  A_COMPLETE_CLUSTER          cluster de tres bloques, candidato los cubre     -> COMPLETE
  B_PARTIAL_CLUSTER           MISMO dibujo y pista, candidato parcial          -> INCOMPLETE
  C_UNRELATED_CLOSED_ROOM     núcleo + recinto cerrado ajeno en el alcance     -> COMPLETE
  D_TINY_NOISE_ANCHORS        núcleo + celdas diminutas dispersas              -> COMPLETE
  E_DISTRIBUTED_SERVICE_BLOCKS bloques separados por circulación, ambos dentro -> COMPLETE
  F_COMPACT_FALSE_COMPLETE    candidato compacto sobre un tercio del cluster   -> INCOMPLETE
  G_NO_RELIABLE_ANCHORS       sin evidencia suficiente para medir              -> NOT_EVALUATED

Ejecutar: python tests/fixtures/core_completeness/make_e16_11_family.py
"""
import json
import os

import cv2
import numpy as np

W, H = 1400, 900
OUT = os.path.dirname(os.path.abspath(__file__))
PAPEL, MURO, FINO = 255, 40, 120
RING = [(100, 100), (1300, 100), (1300, 560), (1180, 560), (1180, 800), (100, 800)]


def hoja():
    return np.full((H, W), PAPEL, np.uint8)


def planta(img, t=10):
    cv2.polylines(img, [np.array(RING, np.int32)], True, MURO, t)


def celdas(img, x, y, n, cw=80, ch=120, gap=14):
    """Fila de recintos cerrados contiguos dentro de un envolvente de muro."""
    cv2.rectangle(img, (x - 16, y - 16), (x + n * (cw + gap) + 2, y + ch + 16), MURO, 9)
    for i in range(n):
        x0 = x + i * (cw + gap)
        cv2.rectangle(img, (x0, y0 := y), (x0 + cw, y0 + ch), MURO, 7)


def sala_cerrada(img, x, y, w, h):
    cv2.rectangle(img, (x, y), (x + w, y + h), MURO, 9)


def ruido(img, seed=4, n=26):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x = int(rng.integers(150, 1150)); y = int(rng.integers(150, 700))
        if 420 < x < 1000 and 220 < y < 660:
            continue
        s = int(rng.integers(14, 26))
        cv2.rectangle(img, (x, y), (x + s, y + s), MURO, 5)


def mobiliario(img, seed=9, n=60):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x = int(rng.integers(140, 1160)); y = int(rng.integers(140, 720))
        if 400 < x < 1020 and 200 < y < 680:
            continue
        cv2.rectangle(img, (x, y), (x + int(rng.integers(35, 70)), y + int(rng.integers(25, 55))),
                      FINO, 3)


def nucleo_tres_bloques(img):
    """Tres bloques de servicio repartidos en una banda, separados por circulación."""
    celdas(img, 470, 240, 3)            # bloque superior
    celdas(img, 470, 500, 4)            # bloque inferior
    sala_cerrada(img, 860, 240, 150, 190)   # bloque lateral


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def guardar(nombre, img, hint, cand, espera):
    cv2.imwrite(os.path.join(OUT, nombre + ".png"), cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    json.dump({"hint_region": hint, "candidate_ring": cand, "footprint_ring": RING,
               "expected_completeness": espera},
              open(os.path.join(OUT, nombre + ".json"), "w"), indent=1)
    return nombre


def main():
    hechos = []
    HINT = [430, 200, 1050, 680]
    COMPLETO = rect(440, 210, 1030, 660)

    img = hoja(); planta(img); nucleo_tres_bloques(img); mobiliario(img)
    hechos.append(guardar("A_COMPLETE_CLUSTER", img, HINT, COMPLETO, "COMPLETE"))

    # B: EXACTAMENTE el mismo dibujo y la misma pista; sólo cambia el candidato
    img2 = img.copy()
    hechos.append(guardar("B_PARTIAL_CLUSTER", img2, HINT, rect(440, 210, 1030, 450), "INCOMPLETE"))

    # C: un recinto cerrado ajeno lejos del núcleo, dentro del alcance semántico
    img = hoja(); planta(img); nucleo_tres_bloques(img); mobiliario(img)
    # recinto ajeno de tamaño ORDINARIO: la clase es "un recinto cerrado vecino", no "una sala tan
    # grande como el núcleo entero". La primera versión lo dibujó de 170×150 —más masa de celda
    # cerrada que cualquier pieza del núcleo— y eso no representaba la clase: representaba una
    # ambigüedad real, donde rechazar es lo correcto.
    sala_cerrada(img, 210, 640, 95, 85)
    hechos.append(guardar("C_UNRELATED_CLOSED_ROOM", img, [180, 200, 1050, 790], COMPLETO,
                          "COMPLETE"))

    # D: ruido de celdas diminutas por toda la planta
    img = hoja(); planta(img); nucleo_tres_bloques(img); ruido(img); mobiliario(img)
    hechos.append(guardar("D_TINY_NOISE_ANCHORS", img, [420, 190, 1060, 700], COMPLETO, "COMPLETE"))

    # E: dos bloques separados por una circulación ancha; el candidato contiene los dos
    img = hoja(); planta(img); mobiliario(img)
    celdas(img, 460, 240, 3); celdas(img, 460, 560, 3)
    hechos.append(guardar("E_DISTRIBUTED_SERVICE_BLOCKS", img, [430, 200, 1000, 740],
                          rect(440, 210, 990, 730), "COMPLETE"))

    # F: candidato compacto y de buen aspecto sobre un solo bloque del cluster
    img = hoja(); planta(img); nucleo_tres_bloques(img); mobiliario(img)
    hechos.append(guardar("F_COMPACT_FALSE_COMPLETE", img, HINT, rect(455, 225, 830, 400),
                          "INCOMPLETE"))

    # G: sin celdas cerradas suficientes para hablar de cluster
    img = hoja(); planta(img); mobiliario(img)
    sala_cerrada(img, 600, 300, 220, 220)
    hechos.append(guardar("G_NO_RELIABLE_ANCHORS", img, [560, 260, 900, 580],
                          rect(590, 290, 830, 530), "COMPLETENESS_NOT_EVALUATED"))

    for n in hechos:
        print(n)


if __name__ == "__main__":
    main()
