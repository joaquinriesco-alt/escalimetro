"""Familia de fixtures de E16.13.1 — un núcleo es UNA entidad que puede ocupar VARIAS regiones.

Las clases de este ciclo no preguntan "¿dónde está el núcleo?" sino "¿puede el motor REPRESENTAR el
núcleo que el dibujo tiene, y juzgarlo?". Por eso las DIEZ declaran el candidato en el JSON: el
productor queda congelado en este ciclo y exigirle que genere estas geometrías fue exactamente el
error del intento anterior. Lo que se prueba aquí es representación + contrato, con la geometría
puesta a mano.

Lámina 1500×950, planta distinta a la de cualquier caso real. Ninguna coordenada, proporción,
cantidad, área ni color proviene de un plano de desarrollo.

  A_SINGLE_COMPONENT_LEGACY     un bloque compacto: el caso degenerado de 1..N      -> accept, 1 región
  B_TWO_LEGITIMATE_COMPONENTS   dos bloques separados por circulación               -> accept, 2 regiones
  C_THREE_LEGITIMATE_COMPONENTS tres bloques repartidos en una banda                -> accept, 3 regiones
  D_FABRICATED_BRIDGE           candidato que cruza piso abierto para unir dos       -> diagnóstico de fabricación
  E_SPURIOUS_COMPONENT          dos bloques + una región sobre papel en blanco       -> reject
  F_TINY_COMPONENT              dos bloques + una región diminuta                    -> se CONSERVA y la juzga el contrato
  G_OVERLAPPING_COMPONENTS      dos anillos que se solapan                           -> InvalidCoreGeometry
  H_COMPONENT_OUTSIDE_FOOTPRINT una región fuera de la huella                        -> InvalidCoreGeometry
  I_DISTRIBUTED_ANCHOR_COVERAGE anclas repartidas entre las regiones                 -> COMPLETE sobre la unión
  J_OPEN_FLOOR_COMPONENT        dos bloques + una región que es piso ocupable        -> reject

Ejecutar: python tests/fixtures/core_components/make_e16_13_1_family.py
"""
import json
import os

import cv2
import numpy as np

W, H = 1500, 950
OUT = os.path.dirname(os.path.abspath(__file__))
PAPEL, MURO, FINO = 255, 40, 120
RING = [(110, 110), (1390, 110), (1390, 600), (1230, 600), (1230, 850), (110, 850)]


def hoja():
    return np.full((H, W), PAPEL, np.uint8)


def planta(img, t=11):
    cv2.polylines(img, [np.array(RING, np.int32)], True, MURO, t)


def bloque(img, x, y, w, h, celdas=5, t=10):
    """Un bloque de servicio: envolvente de muro con recintos cerrados adentro."""
    cv2.rectangle(img, (x, y), (x + w, y + h), MURO, t)
    if celdas >= 2:
        for i in range(1, celdas):
            cv2.line(img, (x + int(i * w / celdas), y), (x + int(i * w / celdas), y + h), MURO, t - 2)


# El mobiliario se dibuja SIEMPRE antes que la estructura. La primera versión de esta familia lo
# dibujaba encima, y un rectángulo de mobiliario sobrescribía píxeles de muro con su propio gris:
# el muro quedaba perforado, la celda cerrada se abría al piso ocupable y una pieza legítima medía
# `open_floor_invasion = 0,305`. Era un error de dibujo del fixture, no del motor.
def mobiliario(img, seed=7, n=55, evitar=((380, 1120), (200, 720))):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x = int(rng.integers(150, 1200)); y = int(rng.integers(150, 780))
        if evitar[0][0] < x < evitar[0][1] and evitar[1][0] < y < evitar[1][1]:
            continue
        cv2.rectangle(img, (x, y), (x + int(rng.integers(35, 70)), y + int(rng.integers(25, 55))),
                      FINO, 3)


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def guardar(nombre, img, hint, espera, **extra):
    cv2.imwrite(os.path.join(OUT, nombre + ".png"), cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    d = {"hint_region": hint, "footprint_ring": RING, "expected": espera}
    d.update(extra)
    json.dump(d, open(os.path.join(OUT, nombre + ".json"), "w"), indent=1)
    return nombre


# --- geometrías base ---------------------------------------------------------------------------
UNO = (470, 250, 330, 230)              # bloque único
DOS_A = (470, 240, 300, 230)            # par: bloque superior
DOS_B = (470, 560, 300, 210)            # par: bloque inferior, separado por circulación
TRES_C = (900, 250, 190, 240)           # tercero, lateral


def main():
    hechos = []

    img = hoja(); planta(img); mobiliario(img); bloque(img, *UNO, celdas=5)
    hechos.append(guardar("A_SINGLE_COMPONENT_LEGACY", img, [440, 220, 830, 540], "accept",
                          candidate_rings=[rect(465, 245, 805, 485)], expected_components=1))

    img = hoja(); planta(img); mobiliario(img); bloque(img, *DOS_A); bloque(img, *DOS_B)
    hechos.append(guardar("B_TWO_LEGITIMATE_COMPONENTS", img, [440, 210, 800, 800], "accept",
                          candidate_rings=[rect(465, 235, 775, 475), rect(465, 555, 775, 775)],
                          expected_components=2))

    img = hoja(); planta(img); mobiliario(img, evitar=((380, 1160), (200, 800)))
    bloque(img, *DOS_A); bloque(img, *DOS_B); bloque(img, *TRES_C, celdas=3)
    hechos.append(guardar("C_THREE_LEGITIMATE_COMPONENTS", img, [440, 210, 1130, 800], "accept",
                          candidate_rings=[rect(465, 235, 775, 475), rect(465, 555, 775, 775),
                                           rect(895, 245, 1095, 495)],
                          expected_components=3))

    # D: el dibujo de B, con un candidato DECLARADO que une los dos bloques cruzando piso abierto.
    #    Es el negativo del ciclo: la forma que el productor anterior fabricaba para tener una pieza.
    img = hoja(); planta(img); mobiliario(img); bloque(img, *DOS_A); bloque(img, *DOS_B)
    hechos.append(guardar("D_FABRICATED_BRIDGE", img, [440, 210, 800, 800], "measure",
                          candidate_rings=[rect(465, 235, 775, 775)],
                          honest_rings=[rect(465, 235, 775, 475), rect(465, 555, 775, 775)]))

    # E: dos bloques + una pieza que no está construida (trazo fino de mobiliario encadenado)
    # E: dos bloques legítimos + una tercera pieza sobre papel en blanco. Es la clase "geometría que
    #    el dibujo no respalda": ninguna tinta, ningún recinto, nada. Su fabricación mide 1,000.
    img = hoja(); planta(img); mobiliario(img, evitar=((380, 1230), (200, 800)))
    bloque(img, *DOS_A); bloque(img, *DOS_B)
    hechos.append(guardar("E_SPURIOUS_COMPONENT", img, [440, 210, 1130, 800], "reject",
                          candidate_rings=[rect(465, 235, 775, 475), rect(465, 555, 775, 775),
                                           rect(920, 300, 1180, 520)]))

    # F, G, H: formas sucias sobre el dibujo de B. Lo que se prueba es la NORMALIZACIÓN.
    # F: una región diminuta NO se descarta. Descartarla sería reparación semántica —taparía un
    #    defecto del productor— y no hay umbral de tamaño calibrado. Se conserva, se mide y la juzgan
    #    las mismas invariantes que a las demás.
    img = hoja(); planta(img); mobiliario(img); bloque(img, *DOS_A); bloque(img, *DOS_B)
    hechos.append(guardar("F_TINY_COMPONENT", img, [440, 210, 800, 800], "keep_and_judge",
                          candidate_rings=[rect(465, 235, 775, 475), rect(465, 555, 775, 775),
                                           rect(830, 300, 848, 318)],
                          expected_components=3))

    img = hoja(); planta(img); mobiliario(img); bloque(img, *DOS_A); bloque(img, *DOS_B)
    hechos.append(guardar("G_OVERLAPPING_COMPONENTS", img, [440, 210, 800, 800], "invalid",
                          candidate_rings=[rect(465, 235, 775, 475), rect(600, 400, 775, 620)]))

    img = hoja(); planta(img); mobiliario(img); bloque(img, *DOS_A); bloque(img, *DOS_B)
    hechos.append(guardar("H_COMPONENT_OUTSIDE_FOOTPRINT", img, [440, 210, 800, 800], "invalid",
                          candidate_rings=[rect(465, 235, 775, 475), rect(1290, 700, 1450, 820)]))

    # I: anclas repartidas entre las dos piezas. La completitud se evalúa sobre la UNIÓN, así que un
    #    candidato con las dos piezas está completo y uno con una sola no lo está.
    img = hoja(); planta(img); mobiliario(img, evitar=((380, 1160), (200, 800)))
    bloque(img, *DOS_A, celdas=5); bloque(img, *DOS_B, celdas=5); bloque(img, *TRES_C, celdas=3)
    hechos.append(guardar("I_DISTRIBUTED_ANCHOR_COVERAGE", img, [440, 210, 1130, 800], "complete",
                          candidate_rings=[rect(465, 235, 775, 475), rect(465, 555, 775, 775),
                                           rect(895, 245, 1095, 495)],
                          partial_rings=[rect(465, 235, 775, 475)]))

    # J: dos bloques + una pieza que es piso ocupable con muro alrededor. La invasión por componente
    #    es la que veta: promediada sobre la unión, quedaría disimulada.
    img = hoja(); planta(img); mobiliario(img, evitar=((380, 1220), (200, 800)))
    bloque(img, *DOS_A); bloque(img, *DOS_B)
    cv2.rectangle(img, (880, 250), (1180, 560), MURO, 10)
    hechos.append(guardar("J_OPEN_FLOOR_COMPONENT", img, [440, 210, 1200, 800], "reject",
                          candidate_rings=[rect(465, 235, 775, 475), rect(465, 555, 775, 775),
                                           rect(600, 480, 1100, 550)]))

    for n in hechos:
        print(n)


if __name__ == "__main__":
    main()
