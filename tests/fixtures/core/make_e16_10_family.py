"""Fixtures sintéticos de la familia E16.10 — geometría de núcleo guiada por pista semántica.

Representan CLASES: cómo puede presentarse un núcleo y cómo puede equivocarse una pista. Ninguna
coordenada, proporción, color o cantidad proviene de un caso real; la lámina es de otro tamaño y la
planta de otra forma que los dos dibujos de desarrollo del proyecto.

  A  core compacto dentro de una pista correcta                 -> ACEPTA
  B  pista demasiado grande, con oficinas alrededor             -> ACEPTA (la geometría no copia la pista)
  C  ascensores + escalera + baños unidos por circulación       -> ACEPTA
  D  marca de agua y texto denso dentro de la pista             -> ACEPTA (texto no es muro)
  E  mobiliario denso alrededor del núcleo                      -> ACEPTA
  F  pista apuntando a una región equivocada (piso abierto)     -> RECHAZA
  G  estructura fragmentada, sin bloque                         -> RECHAZA
  H  sin pista                                                  -> el pipeline no llega a geometría

Ejecutar: python tests/fixtures/core/make_e16_10_family.py
"""
import json
import os

import cv2
import numpy as np

W, H = 1200, 820
OUT = os.path.dirname(os.path.abspath(__file__))
PAPEL, MURO, FINO, TEXTO = 255, 40, 120, 165


def hoja():
    return np.full((H, W), PAPEL, np.uint8)


#: Anillo del perímetro. El fixture DECLARA su huella en el JSON en vez de pedírsela al proveedor de
#: segmentación: lo que se prueba aquí es la geometría de núcleo, y hacerla depender de otra capa
#: convertiría un fallo de segmentación en un falso fallo de core.
RING = [(90, 90), (1110, 90), (1110, 500), (1010, 500), (1010, 730), (90, 730)]


def planta(img, t=9):
    cv2.polylines(img, [np.array(RING, np.int32)], True, MURO, t)
    return RING


def bloque_ascensores(img, x, y, n=4, cw=70, ch=110, gap=12):
    """Cabinas: cajas cerradas contiguas. Es la firma gráfica de la circulación vertical."""
    cv2.rectangle(img, (x - 14, y - 14), (x + n * (cw + gap) + 2, y + ch + 14), MURO, 8)
    for i in range(n):
        x0 = x + i * (cw + gap)
        cv2.rectangle(img, (x0, y), (x0 + cw, y + ch), MURO, 6)
        cv2.line(img, (x0, y), (x0 + cw, y + ch), FINO, 2)
        cv2.line(img, (x0 + cw, y), (x0, y + ch), FINO, 2)


def escalera(img, x, y, w=220, h=150):
    cv2.rectangle(img, (x, y), (x + w, y + h), MURO, 8)
    for i in range(1, 12):
        cv2.line(img, (x + 10, y + int(i * h / 12)), (x + w - 10, y + int(i * h / 12)), FINO, 2)


def banos(img, x, y, w=150, h=200):
    cv2.rectangle(img, (x, y), (x + w, y + h), MURO, 8)
    cv2.line(img, (x, y + h // 2), (x + w, y + h // 2), MURO, 6)
    for cy in (y + h // 4, y + 3 * h // 4):
        for i in range(3):
            cv2.circle(img, (x + 30 + i * 45, cy), 12, FINO, 2)


def mobiliario(img, n=70, seed=5, val=FINO):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x = int(rng.integers(120, 980)); y = int(rng.integers(120, 700))
        if 380 < x < 900 and 250 < y < 620:
            continue
        a = int(rng.integers(30, 70)); b = int(rng.integers(24, 50))
        cv2.rectangle(img, (x, y), (x + a, y + b), val, 3)


def marca_de_agua(img, x=430, y=300):
    cv2.putText(img, "EJEMPLO", (x, y + 120), cv2.FONT_HERSHEY_SIMPLEX, 3.2, 200, 8)
    cv2.putText(img, "referencial", (x + 20, y + 190), cv2.FONT_HERSHEY_SIMPLEX, 1.6, 205, 4)


def texto_denso(img, x=440, y=300):
    """Anotación densa ENCIMA del núcleo. La primera versión de este fixture la dibujaba DEBAJO, en
    piso abierto y dentro del recuadro de la pista, y eso mezclaba dos clases: 'texto sobre el
    núcleo' y 'la pista incluye piso abierto anotado'. El candidato crecía hasta el texto y el
    contrato lo rechazaba por invasión — correctamente, pero por otra razón que la que el fixture
    quería probar. La clase que interesa aquí es la de una marca de agua sobre el núcleo."""
    for i in range(5):
        cv2.putText(img, "ANOTACION TECNICA", (x, y + 26 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXTO, 2)


def nucleo(img):
    escalera(img, 430, 270)
    bloque_ascensores(img, 430, 460)
    banos(img, 700, 270)


def guardar(nombre, img, hint, espera):
    cv2.imwrite(os.path.join(OUT, nombre + ".png"), cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    json.dump({"hint_region": hint, "expected": espera, "footprint_ring": RING},
              open(os.path.join(OUT, nombre + ".json"), "w"), indent=1)
    return nombre


def main():
    hechos = []
    img = hoja(); planta(img); nucleo(img)
    hechos.append(guardar("A_core_compacto", img, [410, 250, 880, 610], "accept"))

    img = hoja(); planta(img); nucleo(img); mobiliario(img)
    hechos.append(guardar("B_hint_demasiado_grande", img, [200, 150, 1050, 700], "accept"))

    img = hoja(); planta(img)
    escalera(img, 400, 250); bloque_ascensores(img, 400, 480); banos(img, 720, 250)
    hechos.append(guardar("C_bloques_con_circulacion", img, [380, 230, 900, 630], "accept"))

    img = hoja(); planta(img); nucleo(img); marca_de_agua(img); texto_denso(img)
    hechos.append(guardar("D_watermark_y_texto", img, [410, 250, 880, 610], "accept"))

    img = hoja(); planta(img); nucleo(img); mobiliario(img, n=160, seed=11)
    hechos.append(guardar("E_mobiliario_denso", img, [410, 250, 880, 610], "accept"))

    img = hoja(); planta(img); nucleo(img); mobiliario(img)
    hechos.append(guardar("F_hint_equivocada", img, [130, 120, 380, 400], "reject"))

    img = hoja(); planta(img)
    rng = np.random.default_rng(3)
    for _ in range(14):
        x = int(rng.integers(420, 860)); y = int(rng.integers(260, 600))
        cv2.line(img, (x, y), (x + int(rng.integers(60, 140)), y), MURO, 9)
    hechos.append(guardar("G_fragmentada", img, [410, 250, 880, 610], "reject"))

    img = hoja(); planta(img); nucleo(img)
    cv2.imwrite(os.path.join(OUT, "H_sin_pista.png"), cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    hechos.append("H_sin_pista")

    for n in hechos:
        print(n)


if __name__ == "__main__":
    main()
