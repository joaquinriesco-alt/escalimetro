"""Familia P1–P12 de E16.14 — fixtures de PRODUCTOR.

A diferencia de la familia de E16.13.1, aquí el candidato NO se declara: el fixture entrega dibujo,
huella y pista semántica, y el productor tiene que proponer 1..N regiones por su cuenta. Después el
contrato congelado las juzga. Esa es toda la prueba del ciclo.

Lámina 1600×1000, planta distinta a la de cualquier caso real. Ninguna coordenada, proporción,
cantidad, área ni color viene de un plano de desarrollo.

  P1  SINGLE_COMPACT           un bloque legítimo                          -> 1 región
  P2  TWO_COMPONENT_CORE       dos bloques separados por circulación       -> 2 regiones, sin puente
  P3  THREE_COMPONENT_CORE     tres piezas legítimas                       -> 3 regiones
  P4  PARTIAL_CLUSTER_TRAP     una pieza domina visualmente                -> NO devolver sólo la mayor
  P5  UNRELATED_CLOSED_ROOM    núcleo + recinto ordinario en el alcance    -> el recinto queda fuera
  P6  OVERBROAD_HINT           pista enorme con oficinas y ruido           -> no copiar el alcance
  P7  OPEN_FLOOR_SEPARATION    dos piezas separadas por circulación        -> 2 polígonos, sin puente
  P8  FACADE_TOUCH             pieza del núcleo pegada al perímetro        -> no absorber la envolvente
  P9  NOISE_AND_WATERMARK      tinta lineal ajena                          -> no se vuelve región
  P10 AMBIGUOUS_TWO_CLUSTERS   dos grupos plausibles, pista ambigua        -> abstención / no validado
  P11 NO_RELIABLE_STRUCTURE    sin evidencia suficiente                    -> abstención
  P12 NARROW_REAL_STRUCTURE    pieza angosta pero estructural (shaft)      -> NO eliminarla por chica

Ejecutar: python tests/fixtures/core_producer/make_e16_14_family.py
"""
import json
import os

import cv2
import numpy as np

W, H = 1600, 1000
OUT = os.path.dirname(os.path.abspath(__file__))
PAPEL, MURO, FINO, TEXTO = 255, 40, 120, 175
RING = [(120, 120), (1480, 120), (1480, 640), (1300, 640), (1300, 900), (120, 900)]


def hoja():
    return np.full((H, W), PAPEL, np.uint8)


def planta(img, t=12):
    cv2.polylines(img, [np.array(RING, np.int32)], True, MURO, t)


def bloque(img, x, y, w, h, celdas=4, t=10):
    """Bloque de servicio: envolvente de muro con recintos cerrados adentro. Las celdas son la
    evidencia neutral de recinto cerrado (E16.11: NO se afirma que sean ascensores)."""
    cv2.rectangle(img, (x, y), (x + w, y + h), MURO, t)
    for i in range(1, max(1, celdas)):
        cv2.line(img, (x + int(i * w / celdas), y), (x + int(i * w / celdas), y + h), MURO, t - 2)


def sala(img, x, y, w, h, t=10):
    """Recinto ordinario: cerrado, pero sin subdivisión y de tamaño de sala."""
    cv2.rectangle(img, (x, y), (x + w, y + h), MURO, t)


def mobiliario(img, seed=3, n=70, evitar=()):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x = int(rng.integers(170, 1250)); y = int(rng.integers(170, 830))
        if any(a < x < b and c < y < d for (a, b, c, d) in evitar):
            continue
        cv2.rectangle(img, (x, y), (x + int(rng.integers(35, 75)), y + int(rng.integers(25, 55))),
                      FINO, 3)


def marca_de_agua(img, x=430, y=760):
    cv2.putText(img, "EJEMPLO", (x, y), cv2.FONT_HERSHEY_SIMPLEX, 3.0, TEXTO, 7)


def caja(b):
    """Rectángulo (x, y, w, h) → caja [x0, y0, x1, y1] para la verdad declarada del fixture."""
    x, y, w_, h_ = b
    return [x, y, x + w_, y + h_]


def guardar(nombre, img, hint, espera, nota, **extra):
    cv2.imwrite(os.path.join(OUT, nombre + ".png"), cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    d = {"hint_region": hint, "footprint_ring": RING, "expected": espera, "spec": nota}
    d.update(extra)
    json.dump(d, open(os.path.join(OUT, nombre + ".json"), "w"), indent=1, ensure_ascii=False)
    return nombre


# --- geometrías base -----------------------------------------------------------------------------
A1 = (520, 260, 300, 220)          # bloque superior
A2 = (520, 600, 300, 200)          # bloque inferior (separado por circulación)
A3 = (960, 270, 210, 240)          # bloque lateral


def main():
    hechos = []
    ev = ((470, 1230, 210, 850),)

    img = hoja(); planta(img); mobiliario(img, evitar=ev); bloque(img, *A1, celdas=5)
    hechos.append(guardar("P1_SINGLE_COMPACT", img, [490, 230, 860, 520], 1,
                          "un bloque legítimo: el caso degenerado de 1..N",
                          truth_boxes=[caja(A1)]))

    img = hoja(); planta(img); mobiliario(img, evitar=ev)
    bloque(img, *A1, celdas=5); bloque(img, *A2, celdas=4)
    hechos.append(guardar("P2_TWO_COMPONENT_CORE", img, [490, 230, 860, 830], 2,
                          "dos bloques del mismo núcleo separados por circulación; sin puente",
                          truth_boxes=[caja(A1), caja(A2)]))

    img = hoja(); planta(img); mobiliario(img, evitar=ev)
    bloque(img, *A1, celdas=5); bloque(img, *A2, celdas=4); bloque(img, *A3, celdas=3)
    hechos.append(guardar("P3_THREE_COMPONENT_CORE", img, [490, 230, 1210, 830], 3,
                          "tres piezas legítimas repartidas",
                          truth_boxes=[caja(A1), caja(A2), caja(A3)]))

    # P4: una pieza mucho mayor que las otras dos. La regla "la mayor gana" devolvería 1.
    img = hoja(); planta(img); mobiliario(img, evitar=ev)
    bloque(img, 500, 250, 420, 330, celdas=6)
    bloque(img, 500, 660, 150, 130, celdas=2)
    bloque(img, 720, 660, 150, 130, celdas=2)
    hechos.append(guardar("P4_PARTIAL_CLUSTER_TRAP", img, [470, 220, 950, 820], 3,
                          "pieza dominante + dos piezas menores relacionadas: no basta con la mayor",
                          truth_boxes=[caja((500, 250, 420, 330)), caja((500, 660, 150, 130)),
                                       caja((720, 660, 150, 130))]))

    # P5: recinto ORDINARIO (sin subdividir, tamaño de sala) dentro del alcance semántico
    img = hoja(); planta(img); mobiliario(img, evitar=ev)
    bloque(img, *A1, celdas=5); bloque(img, *A2, celdas=4)
    sala(img, 980, 620, 260, 220)
    hechos.append(guardar("P5_UNRELATED_CLOSED_ROOM", img, [490, 230, 1280, 870], 2,
                          "el recinto ordinario está en el alcance y NO es núcleo",
                          truth_boxes=[caja(A1), caja(A2)]))

    # P6: pista enorme, con oficinas cerradas y ruido estructural dentro
    img = hoja(); planta(img); mobiliario(img, n=110, evitar=ev)
    bloque(img, *A1, celdas=5); bloque(img, *A2, celdas=4)
    sala(img, 980, 250, 300, 230); sala(img, 200, 250, 250, 200); sala(img, 200, 600, 250, 220)
    hechos.append(guardar("P6_OVERBROAD_HINT", img, [150, 180, 1400, 880], 2,
                          "la pista abarca casi la planta: el resultado no puede ser el alcance",
                          truth_boxes=[caja(A1), caja(A2)]))

    # P7: idéntico a P2 pero se comprueba explícitamente que NO hay puente en la circulación
    img = hoja(); planta(img); mobiliario(img, evitar=ev)
    bloque(img, *A1, celdas=5); bloque(img, *A2, celdas=4)
    hechos.append(guardar("P7_OPEN_FLOOR_SEPARATION", img, [490, 230, 860, 830], 2,
                          "la franja de circulación entre las dos piezas no puede quedar dentro",
                          gap_box=[520, 490, 820, 590], truth_boxes=[caja(A1), caja(A2)]))

    # P8: una pieza del núcleo pegada al muro perimetral
    img = hoja(); planta(img); mobiliario(img, evitar=((470, 1230, 110, 850),))
    bloque(img, 520, 132, 300, 210, celdas=5); bloque(img, *A2, celdas=4)
    hechos.append(guardar("P8_FACADE_TOUCH", img, [490, 110, 860, 830], 2,
                          "tocar el perímetro no puede absorber la envolvente del piso",
                          truth_boxes=[caja((520, 132, 300, 210)), caja(A2)]))

    # P9: marca de agua y mobiliario denso alrededor del núcleo
    img = hoja(); planta(img); mobiliario(img, n=150, seed=11, evitar=ev)
    bloque(img, *A1, celdas=5); bloque(img, *A2, celdas=4); marca_de_agua(img)
    hechos.append(guardar("P9_NOISE_AND_WATERMARK", img, [490, 230, 860, 830], 2,
                          "tinta lineal ajena no puede volverse una región del núcleo",
                          truth_boxes=[caja(A1), caja(A2)]))

    # P10: dos grupos estructurales plausibles y una pista que abarca los dos
    img = hoja(); planta(img); mobiliario(img, evitar=((170, 1250, 210, 850),))
    bloque(img, 260, 260, 240, 200, celdas=4); bloque(img, 260, 600, 240, 190, celdas=4)
    bloque(img, 1000, 260, 240, 200, celdas=4); bloque(img, 1000, 600, 240, 190, celdas=4)
    hechos.append(guardar("P10_AMBIGUOUS_TWO_CLUSTERS", img, [230, 230, 1270, 820], "ABSTAIN",
                          "dos grupos plausibles bajo una pista ambigua: la evidencia no distingue",
                          truth_boxes=[]))

    img = hoja(); planta(img); mobiliario(img, n=90, seed=5)
    hechos.append(guardar("P11_NO_RELIABLE_STRUCTURE", img, [490, 230, 860, 830], "ABSTAIN",
                          "sin evidencia estructural suficiente donde la pista señala",
                          truth_boxes=[]))

    # P12: pieza angosta pero estructural — un shaft con su recinto cerrado
    img = hoja(); planta(img); mobiliario(img, evitar=ev)
    bloque(img, *A1, celdas=5)
    bloque(img, 900, 300, 70, 190, celdas=1)
    hechos.append(guardar("P12_NARROW_REAL_STRUCTURE", img, [490, 230, 1010, 540], 2,
                          "una pieza angosta con recinto cerrado es estructura: no se filtra por chica",
                          truth_boxes=[caja(A1), caja((900, 300, 70, 190))]))

    for n in hechos:
        print(n)


if __name__ == "__main__":
    main()
