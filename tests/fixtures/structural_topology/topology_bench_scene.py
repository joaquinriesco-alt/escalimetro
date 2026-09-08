"""E18 §6 — banco procedural de TOPOLOGÍA. Una fuente vectorial por escena, muchas resoluciones.

REGLA DEL CICLO: **todo se dibuja con el MISMO ancho**. Si las clases se distinguieran por grosor, el
experimento estaría midiendo width otra vez, que es exactamente lo que el §1 prohíbe. Aquí la única
variable observable es la ESTRUCTURA.

Cada escena declara su verdad topológica desde el vector: puntas, uniones en L, en T, en X, ciclos y
recintos cerrados. El ground truth NO se deriva del algoritmo que se evalúa (§9).
"""
import cv2
import numpy as np

GENERATOR_VERSION = "e18-topology-bench/1.0.0"
PAPEL = 255
W_UNICO = 0.0045          # ancho ÚNICO de todo trazo, fracción del lado mayor
NEGRO, GRIS_OSC, GRIS_MED = 35, 90, 150


def _t(S):
    return max(1, int(round(W_UNICO * S)))


# --- primitivas vectoriales ----------------------------------------------------------------------
def poly(pts, cerrado=False):
    return {"tipo": "poly", "pts": pts, "cerrado": cerrado}


def rect(x, y, w, h):
    return poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], cerrado=True)


def texto(t, x, y, esc=0.9):
    return {"tipo": "texto", "t": t, "xy": (x, y), "esc": esc}


def grilla(xs, ys, x0=0.04, x1=0.96, y0=0.04, y1=0.96):
    return {"tipo": "grilla", "xs": xs, "ys": ys, "ext": (x0, x1, y0, y1)}


def hatch(x, y, w, h, paso=0.02):
    return {"tipo": "hatch", "box": (x, y, w, h), "paso": paso}


#: cada escena: (id, clase, [objetos], ground truth topológico declarado)
#: gt: endpoints, L, T, X, cycles, closed_regions, components, long_path (fracción del lado)
ESCENAS = [
    # ---------------- WALL-LIKE ----------------
    ("P1_linea_larga", "wall_like", [poly([(0.10, 0.20), (0.80, 0.20)])],
     dict(endpoints=2, L=0, T=0, X=0, cycles=0, closed=0, components=1, long_path=0.70)),
    ("P2_L_larga", "wall_like", [poly([(0.12, 0.15), (0.12, 0.70), (0.75, 0.70)])],
     dict(endpoints=2, L=1, T=0, X=0, cycles=0, closed=0, components=1, long_path=1.18)),
    ("P3_T", "wall_like", [poly([(0.10, 0.25), (0.80, 0.25)]), poly([(0.45, 0.25), (0.45, 0.75)])],
     dict(endpoints=3, L=0, T=1, X=0, cycles=0, closed=0, components=1, long_path=0.70)),
    ("P4_recinto_con_vano", "wall_like",
     [poly([(0.20, 0.20), (0.70, 0.20), (0.70, 0.70), (0.45, 0.70)]), poly([(0.33, 0.70), (0.20, 0.70), (0.20, 0.20)])],
     dict(endpoints=2, L=3, T=0, X=0, cycles=0, closed=0, components=1, long_path=1.50)),
    ("P5_dos_recintos", "wall_like",
     [rect(0.15, 0.20, 0.30, 0.35), rect(0.45, 0.20, 0.30, 0.35)],
     dict(endpoints=0, L=4, T=4, X=0, cycles=2, closed=2, components=1, long_path=1.30)),
    ("P6_red_ortogonal", "wall_like",
     [rect(0.12, 0.15, 0.66, 0.60), poly([(0.45, 0.15), (0.45, 0.75)]), poly([(0.12, 0.45), (0.78, 0.45)])],
     dict(endpoints=0, L=4, T=4, X=1, cycles=4, closed=4, components=1, long_path=1.26)),
    ("P7_muro_con_puerta", "wall_like",
     [poly([(0.10, 0.30), (0.40, 0.30)]), poly([(0.52, 0.30), (0.85, 0.30)])],
     dict(endpoints=4, L=0, T=0, X=0, cycles=0, closed=0, components=2, long_path=0.33)),
    ("P8_muro_microcortes", "wall_like",
     [poly([(0.10, 0.35), (0.35, 0.35)]), poly([(0.36, 0.35), (0.60, 0.35)]), poly([(0.61, 0.35), (0.86, 0.35)])],
     dict(endpoints=6, L=0, T=0, X=0, cycles=0, closed=0, components=3, long_path=0.25)),
    ("P9_tramo_corto_en_red", "wall_like",
     [rect(0.15, 0.20, 0.55, 0.45), poly([(0.42, 0.20), (0.42, 0.30)])],
     dict(endpoints=1, L=4, T=1, X=0, cycles=1, closed=1, components=1, long_path=1.10)),
    ("P10_esquina_cambio", "wall_like",
     [poly([(0.15, 0.25), (0.65, 0.25), (0.65, 0.72)])],
     dict(endpoints=2, L=1, T=0, X=0, cycles=0, closed=0, components=1, long_path=0.97)),
    # ---------------- HARD NEGATIVES ----------------
    ("N1_mesa", "furniture", [rect(0.30, 0.30, 0.22, 0.16)],
     dict(endpoints=0, L=4, T=0, X=0, cycles=1, closed=1, components=1, long_path=0.76)),
    ("N2_varias_mesas", "furniture",
     [rect(0.12 + 0.24 * i, 0.25 + 0.28 * j, 0.16, 0.12) for i in range(3) for j in range(2)],
     dict(endpoints=0, L=24, T=0, X=0, cycles=6, closed=6, components=6, long_path=0.56)),
    ("N3_escritorio_patas", "furniture",
     [rect(0.25, 0.25, 0.26, 0.18), poly([(0.29, 0.43), (0.29, 0.52)]), poly([(0.47, 0.43), (0.47, 0.52)])],
     dict(endpoints=2, L=4, T=2, X=0, cycles=1, closed=1, components=1, long_path=0.88)),
    ("N4_texto", "text", [texto("SALA DE REUNIONES", 0.15, 0.40)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
    ("N5_texto_grande", "text", [texto("PLANTA", 0.15, 0.45, 2.6)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
    ("N6_grilla", "grid", [grilla([0.18, 0.38, 0.58, 0.78], [0.22, 0.50, 0.78])],
     dict(endpoints=14, L=0, T=0, X=12, cycles=6, closed=6, components=1, long_path=0.92)),
    ("N7_hatch", "grid", [hatch(0.25, 0.25, 0.35, 0.30)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
    ("N8_cotas", "annotation",
     [poly([(0.15, 0.30), (0.70, 0.30)]), poly([(0.15, 0.27), (0.15, 0.33)]), poly([(0.70, 0.27), (0.70, 0.33)]),
      texto("4.50", 0.38, 0.27, 0.6)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
    ("N9_leader", "annotation",
     [poly([(0.20, 0.60), (0.42, 0.38), (0.62, 0.38)]), texto("NPT +0.15", 0.63, 0.38, 0.6)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
    ("N10_simbolo", "annotation",
     [rect(0.35, 0.35, 0.14, 0.14), poly([(0.35, 0.35), (0.49, 0.49)]), poly([(0.49, 0.35), (0.35, 0.49)])],
     dict(endpoints=0, L=4, T=0, X=1, cycles=5, closed=5, components=1, long_path=0.56)),
    ("N11_mueble_pegado", "furniture",
     [poly([(0.10, 0.30), (0.85, 0.30)]), rect(0.35, 0.30, 0.18, 0.14)],
     dict(endpoints=2, L=2, T=2, X=0, cycles=1, closed=1, components=1, long_path=0.75)),
    ("N12_anotacion_cruzando", "annotation",
     [poly([(0.10, 0.35), (0.85, 0.35)]), texto("EJE 3", 0.40, 0.37, 0.7)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
    ("N13_rectangulo_grande", "furniture", [rect(0.15, 0.20, 0.60, 0.45)],
     dict(endpoints=0, L=4, T=0, X=0, cycles=1, closed=1, components=1, long_path=2.10)),
    ("N14_muebles_conectados", "furniture",
     [rect(0.15, 0.30, 0.20, 0.14), rect(0.35, 0.30, 0.20, 0.14), rect(0.55, 0.30, 0.20, 0.14)],
     dict(endpoints=0, L=4, T=8, X=0, cycles=3, closed=3, components=1, long_path=1.08)),
    ("N15_mezcla", "mixed",
     [grilla([0.20, 0.55, 0.85], [0.30, 0.70]), rect(0.30, 0.36, 0.16, 0.12), texto("OFICINA", 0.55, 0.80, 0.7)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
    # ---------------- AMBIGUAS ----------------
    ("A1_rect_largo", "ambiguous", [rect(0.15, 0.35, 0.62, 0.07)],
     dict(endpoints=0, L=4, T=0, X=0, cycles=1, closed=1, components=1, long_path=1.38)),
    ("A2_estanteria", "ambiguous",
     [rect(0.15, 0.33, 0.62, 0.09)] + [poly([(0.15 + 0.10 * i, 0.33), (0.15 + 0.10 * i, 0.42)]) for i in range(1, 6)],
     dict(endpoints=0, L=4, T=10, X=0, cycles=6, closed=6, components=1, long_path=1.42)),
    ("A3_barra", "ambiguous", [poly([(0.15, 0.30), (0.70, 0.30), (0.70, 0.40)])],
     dict(endpoints=2, L=1, T=0, X=0, cycles=0, closed=0, components=1, long_path=0.65)),
    ("A4_mesa_perimetral", "ambiguous", [rect(0.18, 0.22, 0.58, 0.48)],
     dict(endpoints=0, L=4, T=0, X=0, cycles=1, closed=1, components=1, long_path=2.12)),
    ("A5_biombo", "ambiguous",
     [poly([(0.20, 0.30), (0.45, 0.30)]), poly([(0.45, 0.30), (0.45, 0.55)])],
     dict(endpoints=2, L=1, T=0, X=0, cycles=0, closed=0, components=1, long_path=0.50)),
    # ---------------- CASOS CRÍTICOS ----------------
    ("C1_recinto_vs_mesa", "critical",
     [rect(0.12, 0.20, 0.34, 0.30), rect(0.58, 0.20, 0.20, 0.15)],
     dict(endpoints=0, L=8, T=0, X=0, cycles=2, closed=2, components=2, long_path=1.28)),
    ("C2_red_vs_grilla", "critical",
     [rect(0.08, 0.15, 0.36, 0.40), poly([(0.26, 0.15), (0.26, 0.55)]),
      grilla([0.58, 0.72, 0.86], [0.20, 0.40, 0.60], 0.52, 0.92, 0.15, 0.70)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
    ("C3_muro_con_texto", "critical",
     [rect(0.15, 0.22, 0.55, 0.40), texto("SALA 3", 0.30, 0.44, 0.8)],
     dict(endpoints=None, L=None, T=None, X=None, cycles=None, closed=None, components=None, long_path=None)),
]


def render(escena_id: str, side: int, gris: int = NEGRO, degrade: str = "none", corte_px: int = 0):
    """Rasteriza UNA escena. `corte_px` introduce microcortes deterministas de N px."""
    esc = dict((e[0], e) for e in ESCENAS)[escena_id]
    S = side
    H = int(round(S * 0.80))
    img = np.full((H, S), PAPEL, np.uint8)
    gt_mask = np.zeros((H, S), np.uint8)
    t = _t(S)

    def P(p):
        return (int(round(p[0] * S)), int(round(p[1] * S)))

    for ob in esc[2]:
        if ob["tipo"] == "poly":
            pts = [P(p) for p in ob["pts"]]
            for dst, val in ((img, gris), (gt_mask, 255)):
                cv2.polylines(dst, [np.array(pts, np.int32)], ob["cerrado"], val, t)
        elif ob["tipo"] == "texto":
            e = ob["esc"] * S / 1400.0
            for dst, val in ((img, gris), (gt_mask, 255)):
                cv2.putText(dst, ob["t"], P(ob["xy"]), cv2.FONT_HERSHEY_SIMPLEX, e, val,
                            max(1, int(round(t * 0.8))))
        elif ob["tipo"] == "grilla":
            x0, x1, y0, y1 = ob["ext"]
            for x in ob["xs"]:
                for dst, val in ((img, gris), (gt_mask, 255)):
                    cv2.line(dst, P((x, y0)), P((x, y1)), val, t)
            for y in ob["ys"]:
                for dst, val in ((img, gris), (gt_mask, 255)):
                    cv2.line(dst, P((x0, y)), P((x1, y)), val, t)
        elif ob["tipo"] == "hatch":
            x, y, w, h = ob["box"]; paso = ob["paso"]
            n = int((w + h) / paso)
            for i in range(n):
                a = (x + i * paso, y); b = (x, y + i * paso)
                for dst, val in ((img, gris), (gt_mask, 255)):
                    cv2.line(dst, P(a), P(b), val, max(1, t // 2))
            x0p, y0p = P((x, y)); x1p, y1p = P((x + w, y + h))
            for dst in (img, gt_mask):
                pass
            m = np.zeros_like(gt_mask); m[y0p:y1p, x0p:x1p] = 255
            gt_mask[m == 0] = gt_mask[m == 0]

    if corte_px:
        rng = np.random.default_rng(7)
        ys, xs = np.where(gt_mask > 0)
        if len(xs):
            for _ in range(6):
                i = int(rng.integers(0, len(xs)))
                cv2.circle(img, (int(xs[i]), int(ys[i])), corte_px, PAPEL, -1)

    if degrade == "blur":
        img = cv2.GaussianBlur(img, (0, 0), max(0.6, S / 1600.0))
    elif degrade == "jpeg":
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 55])
        img = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), {"gt_mask": gt_mask, "clase": esc[1], "gt": esc[3],
                                                   "side": S, "height": H, "stroke_px": t}


def escenas():
    return [(e[0], e[1]) for e in ESCENAS]
