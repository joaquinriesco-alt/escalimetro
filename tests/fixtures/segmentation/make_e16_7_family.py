"""Genera la familia de fixtures gráficos de E16.7.

Por qué existe este archivo. Los seis fixtures de E16.6 comparten un defecto: sus muros están
dibujados en negro sólido, que es exactamente la forma que el detector de entonces sabía ver. Pasar
esos fixtures no probaba que el método fuera genérico; probaba que el fixture y el método venían del
mismo supuesto. Esta familia representa CLASES GRÁFICAS —cómo puede estar trazado un plano— y no un
plano en particular: ninguna geometría, proporción, cantidad de recintos ni marca proviene de un
caso real. Se ejecuta con `python tests/fixtures/segmentation/make_e16_7_family.py`.

Clases (E16.7 §14 y §15):
  D0  muro oscuro / mobiliario claro          -> huella válida
  D1  muro gris claro / mobiliario oscuro     -> huella válida   (la clase que E16.6 no veía)
  D2  muro gris claro + ejes de replanteo     -> huella válida
  D3  muros de doble línea                    -> huella válida
  D4  perímetro con vanos de puerta           -> huella válida
  D5  rótulo trazado sobre el muro            -> CLASE ABIERTA: huella contaminada, aceptada
  N4  sólo mobiliario                         -> RECHAZO
  N5  sólo grilla de ejes                     -> RECHAZO
  N6  lámina de título / texto                -> RECHAZO
  N7  dos rectángulos grandes sin relación    -> RECHAZO (lámina ambigua)
  N8  croquis abierto                         -> RECHAZO
"""
import os

import cv2
import numpy as np

W, H = 1000, 700
OUT = os.path.dirname(os.path.abspath(__file__))

PAPEL = 255
GRIS_CLARO = 185      # un plano impreso en gris claro sigue siendo un plano
GRIS_MEDIO = 150
OSCURO = 45


def hoja():
    return np.full((H, W), PAPEL, np.uint8)


def rect(img, x0, y0, x1, y1, val, t):
    cv2.rectangle(img, (x0, y0), (x1, y1), int(val), t)


def mobiliario(img, val, n=26, seed=7):
    """Muebles: rectángulos pequeños dispersos. No representan ningún layout real."""
    rng = np.random.default_rng(seed)
    for _ in range(n):
        x = int(rng.integers(150, W - 220)); y = int(rng.integers(120, H - 180))
        a = int(rng.integers(18, 46)); b = int(rng.integers(14, 34))
        cv2.rectangle(img, (x, y), (x + a, y + b), int(val), 2)


def texto(img, val=GRIS_MEDIO, org=(30, 640)):
    """Rótulo de la lámina. Por defecto va en una zona libre: cuando el rótulo TOCA el muro, la
    huella se contamina, y esa clase tiene su propio fixture (D5) en vez de quedar mezclada aquí."""
    for i, s in enumerate(("NIVEL TIPO", "ESC 1:200", "LAMINA A-01")):
        cv2.putText(img, s, (org[0] + 190 * i, org[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, int(val), 2)


def ejes(img, val=GRIS_CLARO):
    """Ejes de replanteo: cruzan la hoja de borde a borde, por fuera del edificio."""
    for x in range(160, W - 100, 130):
        cv2.line(img, (x, 0), (x, H - 1), int(val), 1)
    for y in range(140, H - 80, 120):
        cv2.line(img, (0, y), (W - 1, y), int(val), 1)


def perimetro_L(img, val, t=6):
    """Planta en L. Forma arbitraria: sirve para que la huella no sea un rectángulo trivial."""
    pts = np.array([(120, 110), (760, 110), (760, 340), (880, 340),
                    (880, 590), (120, 590)], np.int32)
    cv2.polylines(img, [pts], True, int(val), t)
    return pts


def guardar(nombre, img):
    p = os.path.join(OUT, nombre + ".png")
    cv2.imwrite(p, cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    return p


def main():
    hechos = []

    # D0 · muro oscuro, mobiliario claro
    img = hoja(); perimetro_L(img, OSCURO); mobiliario(img, GRIS_CLARO); texto(img)
    hechos.append(guardar("D0_muro_oscuro_mobiliario_claro", img))

    # D1 · muro gris claro, mobiliario oscuro  (la clase invisible para un umbral global)
    img = hoja(); perimetro_L(img, GRIS_CLARO); mobiliario(img, OSCURO); texto(img)
    hechos.append(guardar("D1_muro_gris_claro_mobiliario_oscuro", img))

    # D2 · muro gris claro + ejes de replanteo que salen de la planta
    img = hoja(); ejes(img); perimetro_L(img, GRIS_CLARO); mobiliario(img, OSCURO); texto(img)
    hechos.append(guardar("D2_muro_gris_claro_con_ejes", img))

    # D3 · muros de doble línea (convención arquitectónica), en gris medio
    img = hoja()
    for d in (0, 9):
        pts = np.array([(120 + d, 110 + d), (760 - d, 110 + d), (760 - d, 340 + d),
                        (880 - d, 340 + d), (880 - d, 590 - d), (120 + d, 590 - d)], np.int32)
        cv2.polylines(img, [pts], True, int(GRIS_MEDIO), 2)
    mobiliario(img, OSCURO); texto(img)
    hechos.append(guardar("D3_doble_linea", img))

    # D4 · perímetro con vanos de puerta (huecos del ancho de una puerta)
    img = hoja(); perimetro_L(img, GRIS_CLARO)
    for (x, y) in ((300, 110), (560, 590), (880, 470)):
        cv2.line(img, (x - 9, y), (x + 9, y), PAPEL, 9)      # vano ≈ 18 px
    mobiliario(img, OSCURO); texto(img)
    hechos.append(guardar("D4_vanos_de_puerta", img))

    # D5 · rótulo trazado ENCIMA del muro perimetral. Clase abierta: la anotación queda conectada al
    #      edificio y la huella la absorbe. El fixture existe para MEDIR ese defecto, no para ocultarlo.
    img = hoja(); perimetro_L(img, GRIS_CLARO); mobiliario(img, OSCURO)
    texto(img, org=(600, 100))
    hechos.append(guardar("D5_rotulo_tocando_el_muro", img))

    # N4 · sólo mobiliario: no hay ninguna estructura a escala de la lámina
    img = hoja(); mobiliario(img, OSCURO, n=60, seed=11); texto(img)
    hechos.append(guardar("N4_solo_mobiliario", img))

    # N5 · sólo grilla de ejes: hay estructura, pero no encierra un edificio
    img = hoja(); ejes(img, GRIS_MEDIO); texto(img)
    hechos.append(guardar("N5_solo_grilla", img))

    # N6 · lámina de título: sólo texto
    img = hoja()
    for i, s in enumerate(("PROYECTO", "MEMORIA DE CALCULO", "REVISION B", "LAMINA 3 DE 12")):
        cv2.putText(img, s, (120, 180 + 90 * i), cv2.FONT_HERSHEY_SIMPLEX, 1.4, int(OSCURO), 3)
    hechos.append(guardar("N6_lamina_de_titulo", img))

    # N7 · dos rectángulos grandes sin relación: la lámina es ambigua, no hay UN objetivo
    img = hoja()
    rect(img, 90, 150, 450, 560, GRIS_MEDIO, 5)
    rect(img, 540, 150, 900, 560, GRIS_MEDIO, 5)
    texto(img)
    hechos.append(guardar("N7_dos_rectangulos", img))

    # N8 · croquis abierto: trazos largos que no cierran ningún recinto
    img = hoja()
    cv2.line(img, (120, 140), (820, 140), int(OSCURO), 4)
    cv2.line(img, (120, 140), (120, 520), int(OSCURO), 4)
    cv2.line(img, (300, 520), (820, 520), int(OSCURO), 4)
    mobiliario(img, GRIS_MEDIO, n=10, seed=3); texto(img)
    hechos.append(guardar("N8_croquis_abierto", img))

    for p in hechos:
        print(os.path.basename(p))


if __name__ == "__main__":
    main()
