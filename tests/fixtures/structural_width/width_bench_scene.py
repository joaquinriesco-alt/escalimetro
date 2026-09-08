"""E17 §4 — banco vectorial orientado a WIDTH. Una fuente, muchas resoluciones.

GENERATOR_VERSION identifica la geometría: si cambia, las mediciones no son comparables.

Todo se define en coordenadas normalizadas sobre el lado mayor. Los anchos son fracciones, así que
una "línea de 3×" es la misma línea a 600 y a 2400 px, sólo que con más píxeles.
"""
import cv2
import numpy as np

GENERATOR_VERSION = "e17-width-bench/1.0.0"
PAPEL = 255
W0 = 0.0015                       # unidad de ancho: 1× (fracción del lado mayor)

#: (clase, id, ancho en unidades W0, gris, geometría)
#: NEGRO=35, GRIS_OSC=90, GRIS_MED=150
NEGRO, GRIS_OSC, GRIS_MED = 35, 90, 150

PRIMITIVAS = [
    # A–F: escalera de anchos, línea horizontal aislada, mismo gris
    ("line",  "A_w1", 1, NEGRO, ("h", 0.10, 0.42, 0.06)),
    ("line",  "B_w2", 2, NEGRO, ("h", 0.10, 0.42, 0.12)),
    ("line",  "C_w3", 3, NEGRO, ("h", 0.10, 0.42, 0.18)),
    ("line",  "D_w4", 4, NEGRO, ("h", 0.10, 0.42, 0.24)),
    ("line",  "E_w6", 6, NEGRO, ("h", 0.10, 0.42, 0.30)),
    ("line",  "F_w8", 8, NEGRO, ("h", 0.10, 0.42, 0.36)),
    # Q/R: mismo ancho, distinto gris  (Q gruesa clara, R fina muy oscura)
    ("line",  "Q_w6_gris", 6, GRIS_MED, ("h", 0.10, 0.42, 0.44)),
    ("line",  "R_w2_negro", 2, NEGRO, ("h", 0.10, 0.42, 0.50)),
    ("line",  "Q2_w6_gris_osc", 6, GRIS_OSC, ("h", 0.10, 0.42, 0.56)),
    # G: dos paralelas cercanas
    ("pair",  "G_par", 3, NEGRO, ("h", 0.10, 0.42, 0.64)),
    # H: esquina L,  I: unión en T,  J: puerta / discontinuidad
    ("corner", "H_L", 4, NEGRO, ("l", 0.52, 0.06, 0.16)),
    ("tee",    "I_T", 4, NEGRO, ("t", 0.52, 0.30, 0.16)),
    ("gap",    "J_puerta", 4, NEGRO, ("h", 0.52, 0.84, 0.52)),
    # K: rectángulo cerrado (recinto)
    ("rect",   "K_recinto", 4, NEGRO, ("r", 0.52, 0.60, 0.18, 0.14)),
    # L/M: mobiliario
    ("furniture", "L_mesa", 1, GRIS_OSC, ("r", 0.10, 0.72, 0.10, 0.07)),
    ("furniture", "M_escritorio", 1, GRIS_OSC, ("desk", 0.26, 0.72, 0.12, 0.08)),
    # N: texto, O: grilla fina, P: hatch
    ("text",  "N_texto", 0, GRIS_OSC, ("txt", 0.52, 0.78)),
    ("grid",  "O_grilla", 1, GRIS_MED, ("grid", 0.0, 0.0, 0.0, 0.0)),
    ("hatch", "P_hatch", 1, GRIS_OSC, ("hatch", 0.80, 0.30, 0.14, 0.16)),
    # U: gruesa y fina próximas
    ("mix",   "U_mixto", 6, NEGRO, ("mix", 0.62, 0.86, 0.68)),
]


def _t(u, S):
    """ancho en píxeles para `u` unidades W0 a lado S. Es la VERDAD del banco."""
    return max(1, int(round(u * W0 * S)))


def expected_width_px(u, S):
    return u * W0 * S


def render(side: int, contrast: str = "normal", degrade: str = "none"):
    S = side
    H = int(round(S * 0.92))
    img = np.full((H, S), PAPEL, np.uint8)
    gt = {}                                  # id -> máscara (uint8) de esa primitiva
    def m():
        return np.zeros((H, S), np.uint8)
    def P(x, y):
        return (int(round(x * S)), int(round(y * S)))
    ajuste = {"normal": 0, "claro": 60, "muy_claro": 100}[contrast]

    for clase, pid, u, gris, geo in PRIMITIVAS:
        g = min(240, gris + ajuste)
        t = _t(u, S) if u else 0
        k = m()
        tipo = geo[0]
        if tipo == "h":
            _, x0, x1, y = geo
            for dst, val in ((img, g), (k, 255)):
                cv2.line(dst, P(x0, y), P(x1, y), val, t)
            if clase == "pair":
                sep = _t(4, S)
                for dst, val in ((img, g), (k, 255)):
                    cv2.line(dst, (P(x0, y)[0], P(x0, y)[1] + sep), (P(x1, y)[0], P(x1, y)[1] + sep), val, t)
            if clase == "gap":
                hueco = _t(10, S)
                cx = (P(x0, y)[0] + P(x1, y)[0]) // 2
                cv2.line(img, (cx - hueco // 2, P(x0, y)[1]), (cx + hueco // 2, P(x0, y)[1]), PAPEL, t + 2)
                cv2.line(k, (cx - hueco // 2, P(x0, y)[1]), (cx + hueco // 2, P(x0, y)[1]), 0, t + 2)
        elif tipo == "l":
            _, x, y, lado = geo
            for dst, val in ((img, g), (k, 255)):
                cv2.line(dst, P(x, y), P(x + lado, y), val, t)
                cv2.line(dst, P(x, y), P(x, y + lado), val, t)
        elif tipo == "t":
            _, x, y, lado = geo
            for dst, val in ((img, g), (k, 255)):
                cv2.line(dst, P(x, y), P(x + lado, y), val, t)
                cv2.line(dst, P(x + lado / 2, y), P(x + lado / 2, y + lado * 0.7), val, t)
        elif tipo == "r":
            _, x, y, w_, h_ = geo
            for dst, val in ((img, g), (k, 255)):
                cv2.rectangle(dst, P(x, y), P(x + w_, y + h_), val, t)
        elif tipo == "desk":
            _, x, y, w_, h_ = geo
            for dst, val in ((img, g), (k, 255)):
                cv2.rectangle(dst, P(x, y), P(x + w_, y + h_), val, t)
                for dx in (0.02, w_ - 0.02):
                    cv2.line(dst, P(x + dx, y + h_), P(x + dx, y + h_ + 0.03), val, t)
        elif tipo == "txt":
            _, x, y = geo
            esc = S / 1400.0
            for dst, val in ((img, g), (k, 255)):
                cv2.putText(dst, "SALA DE REUNIONES", P(x, y), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8 * esc, val, max(1, int(round(2 * esc))))
        elif tipo == "grid":
            for xg in (0.24, 0.46, 0.70, 0.92):
                for dst, val in ((img, g), (k, 255)):
                    cv2.line(dst, P(xg, 0.03), P(xg, 0.90), val, t)
        elif tipo == "hatch":
            _, x, y, w_, h_ = geo
            paso = _t(6, S)
            x0p, y0p = P(x, y); x1p, y1p = P(x + w_, y + h_)
            for i in range(0, (x1p - x0p) + (y1p - y0p), max(2, paso)):
                for dst, val in ((img, g), (k, 255)):
                    cv2.line(dst, (x0p + i, y0p), (x0p, y0p + i), val, t)
            k[:y0p, :] = 0; k[y1p:, :] = 0; k[:, :x0p] = 0; k[:, x1p:] = 0
        elif tipo == "mix":
            _, x0, x1, y = geo
            for dst, val in ((img, g), (k, 255)):
                cv2.line(dst, P(x0, y), P(x1, y), val, t)                       # gruesa
                cv2.line(dst, P(x0, y + 0.02), P(x1, y + 0.02), val, _t(1, S))  # fina pegada
        gt[pid] = k

    if degrade == "blur":
        img = cv2.GaussianBlur(img, (0, 0), max(0.6, S / 1400.0))
    elif degrade == "jpeg":
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 55])
        img = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), gt


def clases():
    return {pid: (clase, u, gris) for clase, pid, u, gris, _ in PRIMITIVAS}
