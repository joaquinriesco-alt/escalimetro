"""Escena vectorial única, rasterizable a cualquier resolución (E16.16 §4).

La geometría se define UNA vez en coordenadas normalizadas [0,1] sobre el lado mayor. Cada
rasterización usa exactamente la misma escena: lo que cambia es sólo el número de píxeles. Los
anchos de trazo también son fracciones, de modo que un muro sigue siendo un muro de la misma
proporción a 600 y a 2400 px — que es justamente la propiedad que el ciclo pone a prueba.
"""
import cv2
import numpy as np

PAPEL, MURO, FINO, TEXTO, GRIS = 255, 40, 120, 175, 150

# anchos como fracción del lado mayor
W_PERIM = 0.0085     # muro perimetral
W_TABIQUE = 0.0055   # tabique estructural delgado pero continuo
W_RECINTO = 0.0060
W_MOB = 0.0020       # mobiliario
W_GRID = 0.0012      # ejes / grilla
GAP_PUERTA = 0.014   # vano de puerta

PERIM = [(0.06, 0.10), (0.94, 0.10), (0.94, 0.62), (0.80, 0.62), (0.80, 0.92), (0.06, 0.92)]
TABIQUES = [((0.35, 0.10), (0.35, 0.42)), ((0.35, 0.42), (0.62, 0.42))]
ESQUINA = [((0.62, 0.62), (0.62, 0.92)), ((0.62, 0.62), (0.78, 0.62))]
RECINTO = (0.40, 0.52, 0.24, 0.26)          # x, y, w, h  (con vano de puerta abajo)
MESAS = [(0.10 + 0.075 * i, 0.66 + 0.09 * j, 0.055, 0.045) for i in range(3) for j in range(2)]
MOB_LINEAL = [((0.10, 0.20), (0.30, 0.20)), ((0.10, 0.28), (0.30, 0.28))]
GRILLA_V = [0.20, 0.50, 0.75]
GRILLA_H = [0.30, 0.75]
TEXTO_POS = (0.66, 0.30)


def _p(pt, S):
    return (int(round(pt[0] * S)), int(round(pt[1] * S)))


def _t(frac, S):
    return max(1, int(round(frac * S)))


def render(side: int):
    """Devuelve (imagen BGR, máscaras de verdad) para el lado mayor pedido."""
    S = side
    H = int(round(S * 0.66))
    img = np.full((H, S), PAPEL, np.uint8)
    gt_wall = np.zeros((H, S), np.uint8)
    gt_mob = np.zeros((H, S), np.uint8)
    gt_txt = np.zeros((H, S), np.uint8)
    gt_grid = np.zeros((H, S), np.uint8)

    def linea(dst, a, b, frac, val):
        cv2.line(dst, _p(a, S), _p(b, S), val, _t(frac, S))

    # --- grilla y ejes (negativo) -----------------------------------------------------------
    for x in GRILLA_V:
        linea(img, (x, 0.06), (x, 0.96), W_GRID, GRIS); linea(gt_grid, (x, 0.06), (x, 0.96), W_GRID, 255)
    for y in GRILLA_H:
        linea(img, (0.03, y), (0.97, y), W_GRID, GRIS); linea(gt_grid, (0.03, y), (0.97, y), W_GRID, 255)

    # --- mobiliario (negativo) --------------------------------------------------------------
    for (x, y, w, h) in MESAS:
        cv2.rectangle(img, _p((x, y), S), _p((x + w, y + h), S), FINO, _t(W_MOB, S))
        cv2.rectangle(gt_mob, _p((x, y), S), _p((x + w, y + h), S), 255, _t(W_MOB, S))
    for a, b in MOB_LINEAL:
        linea(img, a, b, W_MOB, FINO); linea(gt_mob, a, b, W_MOB, 255)

    # --- texto / rótulo (negativo) ----------------------------------------------------------
    esc = S / 1400.0
    cv2.putText(img, "PLANTA REFERENCIAL", _p(TEXTO_POS, S), cv2.FONT_HERSHEY_SIMPLEX,
                0.9 * esc, TEXTO, max(1, int(round(2 * esc))))
    cv2.putText(gt_txt, "PLANTA REFERENCIAL", _p(TEXTO_POS, S), cv2.FONT_HERSHEY_SIMPLEX,
                0.9 * esc, 255, max(1, int(round(2 * esc))))

    # --- estructura (positivo) --------------------------------------------------------------
    per = np.array([_p(q, S) for q in PERIM], np.int32)
    cv2.polylines(img, [per], True, MURO, _t(W_PERIM, S))
    cv2.polylines(gt_wall, [per], True, 255, _t(W_PERIM, S))
    for a, b in TABIQUES + ESQUINA:
        linea(img, a, b, W_TABIQUE, MURO); linea(gt_wall, a, b, W_TABIQUE, 255)

    x, y, w, h = RECINTO
    for a, b in (((x, y), (x + w, y)), ((x, y), (x, y + h)), ((x + w, y), (x + w, y + h))):
        linea(img, a, b, W_RECINTO, MURO); linea(gt_wall, a, b, W_RECINTO, 255)
    g = GAP_PUERTA
    for a, b in (((x, y + h), (x + w / 2 - g / 2, y + h)), ((x + w / 2 + g / 2, y + h), (x + w, y + h))):
        linea(img, a, b, W_RECINTO, MURO); linea(gt_wall, a, b, W_RECINTO, 255)

    fp = np.zeros((H, S), np.uint8)
    cv2.fillPoly(fp, [per], 255)
    return (cv2.cvtColor(img, cv2.COLOR_GRAY2BGR),
            {"wall": gt_wall, "furniture": gt_mob, "text": gt_txt, "grid": gt_grid,
             "footprint": fp, "room": RECINTO, "side": S, "height": H})
