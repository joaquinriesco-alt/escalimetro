"""E19 §4/§6 — banco procedural PAREADO y CONTRAFACTUAL de CONTEXTO.

REGLA DEL CICLO: dentro de cada par, los pixeles del TARGET son BYTE-IDENTICOS entre la escena
ARCHITECTURAL_ENCLOSURE y la escena FURNITURE_OBJECT. Lo unico que cambia es lo que ocurre FUERA
del recuadro objetivo.

La identidad se garantiza por CONSTRUCCION, no por revision: se dibuja el contexto, se blanquea el
recuadro objetivo completo, y recien despues se dibujan el marcador y el target. Cualquier objeto de
contexto que invadiera el recuadro desaparece; el generador reporta cuantos pixeles borro asi
(`leakage_px`) para que el numero sea auditable.

Todo se dibuja con UN SOLO ancho y UN SOLO gris: ni el ancho (E17) ni el gris pueden separar clases.
No hay texto en ninguna escena (§7).
"""
import cv2
import numpy as np

GENERATOR_VERSION = "e19-context-bench/1.0.0"

SIDE = 1200
PAPEL = 255
TINTA = 35                 # gris UNICO de todo el dibujo
GRIS_MARCA = 130           # gris del marcador neutro, identico en ambas clases
W_UNICO = 0.0035           # ancho UNICO de todo trazo, fraccion del lado
MARGEN_CROP = 0.008        # margen fijo del recuadro objetivo
CLEARANCE = 0.018          # distancia minima del contexto al bbox del target (> MARGEN_CROP + ancho)
LEJANIA = 0.055            # distancia minima del FONDO al bbox del target
ANCHO_CORREDOR = 0.062     # separacion entre las dos lineas de un corredor

CLASES = ("ARCHITECTURAL_ENCLOSURE", "FURNITURE_OBJECT")


def _t(S=SIDE):
    return max(1, int(round(W_UNICO * S)))


# --- primitivas ----------------------------------------------------------------------------------
def poly(pts, cerrado=False):
    return {"tipo": "poly", "pts": pts, "cerrado": cerrado}


def rect(x, y, w, h):
    return poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], cerrado=True)


def linea(p, q):
    return poly([p, q])


def recinto_con_puerta(x, y, w, h, lado="S", frac=0.45, vano=0.055):
    """Rectangulo con un vano en un lado. El vano es contexto, nunca parte del target."""
    e = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    lados = {"N": (e[0], e[1]), "E": (e[1], e[2]), "S": (e[2], e[3]), "O": (e[3], e[0])}
    out = []
    for k, (a, b) in lados.items():
        if k != lado:
            out.append(linea(a, b))
            continue
        ax, ay = a; bx, by = b
        L = max(1e-9, ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5)
        ux, uy = (bx - ax) / L, (by - ay) / L
        d0 = max(0.0, frac * L - vano / 2); d1 = min(L, frac * L + vano / 2)
        out.append(linea(a, (ax + ux * d0, ay + uy * d0)))
        out.append(linea((ax + ux * d1, ay + uy * d1), b))
    return out


def silla(cx, cy, s=0.026):
    return rect(cx - s / 2, cy - s / 2, s, s)


def puesto(x, y, w=0.075, h=0.048, sillas=True):
    """Escritorio con o sin silla. Aparece en AMBAS clases (anti-atajo §6)."""
    o = [rect(x, y, w, h)]
    if sillas:
        o.append(silla(x + w / 2, y + h + 0.030))
    return o


def banco_puestos(x, y, n=3, w=0.075, h=0.048, sillas=True):
    o = []
    for i in range(n):
        o += puesto(x + i * (w + 0.012), y, w, h, sillas)
    return o


def corredor(x0, x1, y, ancho=None, vertical=False):
    ancho = ANCHO_CORREDOR if ancho is None else ancho
    if vertical:
        return [linea((y, x0), (y, x1)), linea((y + ancho, x0), (y + ancho, x1))]
    return [linea((x0, y), (x1, y)), linea((x0, y + ancho), (x1, y + ancho))]


def envolvente(m=0.045):
    return [rect(m, m, 1 - 2 * m, 1 - 2 * m)]


def mullions(x0, x1, y, n=9, largo=0.020):
    return [linea((x0 + i * (x1 - x0) / (n - 1), y), (x0 + i * (x1 - x0) / (n - 1), y + largo))
            for i in range(n)]


def nucleo(x, y, w, h):
    """Bloque de servicio: tres celdas apiladas. Contexto tipico de recinto."""
    o = [rect(x, y, w, h)]
    for k in (1, 2):
        o.append(linea((x, y + k * h / 3), (x + w, y + k * h / 3)))
    return o


# --- geometria de los targets --------------------------------------------------------------------
#: 12 tamanos (aspecto y orientacion variados) x 3 anclas = 36 pares
_TAM = [(0.10, 0.08), (0.14, 0.10), (0.18, 0.12), (0.22, 0.16), (0.26, 0.18), (0.30, 0.20),
        (0.12, 0.18), (0.16, 0.22), (0.20, 0.26), (0.34, 0.14), (0.28, 0.10), (0.24, 0.24)]
_ANCLA = [(0.16, 0.18), (0.38, 0.36), (0.56, 0.20)]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def targets():
    out = []
    for i in range(36):
        w, h = _TAM[i % 12]
        ax, ay = _ANCLA[i // 12]
        x = _clamp(ax, 0.10, 0.90 - w)
        y = _clamp(ay, 0.10, 0.90 - h)
        out.append((f"PAR{i + 1:02d}", (round(x, 4), round(y, 4), w, h)))
    return out


def _cabe(x, y, w, h, m=0.045):
    return x >= m and y >= m and x + w <= 1 - m and y + h <= 1 - m


def _lejos(x, y, w, h, t, m=None):
    """True si el objeto no invade el bbox del target expandido por m (CLEARANCE por defecto)."""
    m = CLEARANCE if m is None else m
    tx, ty, tw, th = t
    return not (x < tx + tw + m and x + w > tx - m and
                y < ty + th + m and y + h > ty - m)


# --- fondo COMPARTIDO por las dos clases del par ----------------------------------------------------
def _espeja(objs):
    out = []
    for o in objs:
        out.append({**o, "pts": [(1 - px, py) for px, py in o["pts"]]})
    return out


def _bloque_de_planta(b0, b1, n_salas, amoblado):
    """Un trozo de planta real: circulacion, puestos, bateria de recintos y nucleo."""
    H = b1 - b0
    if H < 0.22:
        return []
    o = []
    yc = b0 + 0.030
    o += corredor(0.060, 0.940, yc)
    yb = yc + ANCHO_CORREDOR + 0.032
    yr = b1 - 0.115
    if yb + 0.100 < yr - 0.010:
        o += banco_puestos(0.075, yb, 3, sillas=True)
        o += banco_puestos(0.345, yb, 3, sillas=False)
    if yr > yb + 0.020:
        for k in range(n_salas):
            bx = 0.065 + 0.160 * k
            if bx + 0.145 < 0.640:
                o += recinto_con_puerta(bx, yr, 0.145, 0.115, "N", 0.5)
                if amoblado and k == 0:
                    o += puesto(bx + 0.020, yr + 0.045, 0.070, 0.040, False)
        o += nucleo(0.690, max(b0 + 0.10, yr - 0.120), 0.235, min(0.235, b1 - max(b0 + 0.10, yr - 0.120)))
    return o


def fondo(t, seed):
    """Telon de fondo IDENTICO en las dos escenas del par: envolvente, fachada y un bloque de planta
    en la banda libre mas amplia. Nada de esto se acerca al target a menos de LEJANIA, asi que no
    puede llevar informacion de clase: la unica diferencia entre A y B es el ANILLO LOCAL."""
    x, y, w, h = t
    o = envolvente(0.040)
    arriba = y - 0.050
    abajo = 0.950 - (y + h)
    if abajo >= arriba:
        b0, b1 = y + h + LEJANIA, 0.950
        o += mullions(0.055, 0.945, 0.040, 13)
    else:
        b0, b1 = 0.050, y - LEJANIA
        o += mullions(0.055, 0.945, 0.940, 13)
    n_salas = 2 + (seed % 3)
    bloque = _bloque_de_planta(b0, b1, n_salas, amoblado=(seed % 3 != 1))
    if seed % 2 == 1:
        bloque = _espeja(bloque)
    o += [z for z in bloque]
    return o


# --- anillo local: ARCHITECTURAL_ENCLOSURE ---------------------------------------------------------
def _e1_banda_de_recintos(t):
    """El target es un recinto mas de una banda, con puertas que dan al mismo corredor."""
    x, y, w, h = t; o = []
    for dx in (-(w + CLEARANCE), w + CLEARANCE):
        nx = x + dx
        if _cabe(nx, y, w, h):
            o += recinto_con_puerta(nx, y, w, h, "S", 0.5)
    yc = y + h + CLEARANCE
    if yc + 0.055 < 0.95:
        o += corredor(max(0.06, x - 1.3 * w), min(0.94, x + 2.3 * w), yc)
    return o


def _e2_corredor_en_L(t):
    x, y, w, h = t; o = []
    yc = y + h + CLEARANCE
    if yc + 0.055 < 0.95:
        o += corredor(max(0.06, x - 0.10), min(0.94, x + w + 0.20), yc)
    xc = x + w + CLEARANCE
    if xc + 0.055 < 0.95:
        o += corredor(max(0.06, y - 0.10), yc, xc, 0.055, vertical=True)
    ny = y - CLEARANCE - h * 0.7
    if _cabe(x, ny, w, h * 0.7):
        o += recinto_con_puerta(x, ny, w, h * 0.7, "S", 0.5)
    return o


def _e3_pod_aislado(t):
    """ANTI-ATAJO: recinto exento en planta abierta. No hay NADA pegado a el."""
    return []


def _e4_junto_al_nucleo(t):
    x, y, w, h = t; o = []
    nx = x + w + CLEARANCE
    if _cabe(nx, y, 0.15, h) and h > 0.09:
        o += nucleo(nx, y, 0.15, h)
    else:
        nx = x - CLEARANCE - 0.15
        if _cabe(nx, y, 0.15, max(h, 0.10)):
            o += nucleo(nx, y, 0.15, max(h, 0.10))
    yc = y + h + CLEARANCE
    if yc + 0.055 < 0.95:
        o += corredor(max(0.06, x - 0.08), min(0.94, x + w + 0.22), yc)
    return o


def _e5_bateria(t):
    x, y, w, h = t; o = []
    sw, sh = max(0.085, w * 0.55), max(0.070, h * 0.45)
    for i in range(3):
        nx = x + w + CLEARANCE
        ny = y + i * (sh + 0.008)
        if _cabe(nx, ny, sw, sh) and ny + sh <= y + h + 0.12:
            o += recinto_con_puerta(nx, ny, sw, sh, "E", 0.5)
    yc = y + h + CLEARANCE
    if yc + 0.055 < 0.95:
        o += corredor(max(0.06, x - 0.08), min(0.94, x + w + 0.30), yc)
    return o


def _e6_recinto_con_puestos_afuera(t):
    """ANTI-ATAJO: hay mobiliario y sillas pegados TAMBIEN en la clase recinto."""
    x, y, w, h = t; o = []
    ny = y + h + CLEARANCE
    if _cabe(x, ny, 0.245, 0.100):
        o += banco_puestos(x, ny, 3, sillas=True)
    elif _cabe(x - 0.26, y, 0.245, 0.100):
        o += banco_puestos(x - 0.26, y, 3, sillas=True)
    nx = x - CLEARANCE - w
    if _cabe(nx, y, w, h):
        o += recinto_con_puerta(nx, y, w, h, "S", 0.5)
    return o


def _e7_recinto_contra_fachada(t):
    """Espejo de _f7: la adyacencia a fachada NO decide la clase."""
    x, y, w, h = t; o = []
    yl = y - CLEARANCE
    if yl > 0.05:
        o.append(linea((0.055, yl), (0.945, yl)))
    for dx in (-(w + CLEARANCE), w + CLEARANCE):
        nx = x + dx
        if _cabe(nx, y, w, h):
            o += recinto_con_puerta(nx, y, w, h, "S", 0.5)
    return o


def _e8_entre_corredores(t):
    x, y, w, h = t; o = []
    for yc in (y + h + CLEARANCE, y - CLEARANCE - ANCHO_CORREDOR):
        if 0.05 < yc and yc + ANCHO_CORREDOR < 0.95:
            o += corredor(max(0.06, x - 0.12), min(0.94, x + w + 0.12), yc)
    return o


# --- anillo local: FURNITURE_OBJECT ----------------------------------------------------------------
def _f1_mesa_con_sillas(t):
    x, y, w, h = t; o = []
    n = max(2, min(5, int(w / 0.065)))
    for i in range(n):
        cx = x + w * (i + 0.5) / n
        if y - CLEARANCE - 0.016 > 0.05:
            o.append(silla(cx, y - CLEARANCE - 0.016))
        if y + h + CLEARANCE + 0.016 < 0.95:
            o.append(silla(cx, y + h + CLEARANCE + 0.016))
    return o


def _f2_mesa_entre_mesas(t):
    x, y, w, h = t; o = []
    for dx in (-(w + CLEARANCE), w + CLEARANCE):
        nx = x + dx
        if _cabe(nx, y, w, h):
            o.append(rect(nx, y, w, h))
    return o


def _f3_junto_a_puestos(t):
    """ANTI-ATAJO: mesa SIN sillas propias."""
    x, y, w, h = t; o = []
    ny = y + h + CLEARANCE
    if _cabe(x, ny, 0.245, 0.100):
        o += banco_puestos(x, ny, 3, sillas=True)
    nx = x - CLEARANCE - 0.245
    if _cabe(nx, y, 0.245, 0.100):
        o += banco_puestos(nx, y, 3, sillas=False)
    return o


def _f4_contra_particion(t):
    """ANTI-ATAJO: mueble PEGADO a un muro largo. Muro adyacente no implica recinto."""
    x, y, w, h = t; o = []
    yl = y + h + CLEARANCE
    if yl < 0.94:
        o.append(linea((0.055, yl), (0.945, yl)))
    else:
        o.append(linea((0.055, y - CLEARANCE), (0.945, y - CLEARANCE)))
    return o


def _f5_dentro_de_una_sala(t):
    """ANTI-ATAJO maximo: el target es la MESA que esta DENTRO de una sala."""
    x, y, w, h = t
    m = CLEARANCE + 0.030
    rx, ry, rw, rh = x - m, y - m, w + 2 * m, h + 2 * m
    if not _cabe(rx, ry, rw, rh):
        return _f2_mesa_entre_mesas(t)
    o = recinto_con_puerta(rx, ry, rw, rh, "S", 0.5)
    yc = ry + rh + CLEARANCE
    if yc + 0.055 < 0.95:
        o += corredor(max(0.06, rx - 0.06), min(0.94, rx + rw + 0.14), yc)
    return o


def _f6_mesa_junto_a_circulacion(t):
    """ANTI-ATAJO: la adyacencia a un corredor tampoco decide la clase."""
    x, y, w, h = t; o = []
    yc = y + h + CLEARANCE
    if yc + 0.055 < 0.95:
        o += corredor(max(0.06, x - 0.12), min(0.94, x + w + 0.20), yc)
    n = max(2, min(4, int(w / 0.075)))
    for i in range(n):
        cx = x + w * (i + 0.5) / n
        if y - CLEARANCE - 0.016 > 0.05:
            o.append(silla(cx, y - CLEARANCE - 0.016))
    return o


def _f7_mueble_contra_fachada(t):
    """Espejo de _e7."""
    x, y, w, h = t; o = []
    yl = y - CLEARANCE
    if yl > 0.05:
        o.append(linea((0.055, yl), (0.945, yl)))
    for dx in (-(w + CLEARANCE), w + CLEARANCE):
        nx = x + dx
        if _cabe(nx, y, w, h):
            o.append(rect(nx, y, w, h))
    return o


def _f8_mueble_aislado(t):
    """Espejo de _e3: nada pegado."""
    return []


RECETAS_E = [_e1_banda_de_recintos, _e2_corredor_en_L, _e3_pod_aislado, _e4_junto_al_nucleo,
             _e5_bateria, _e6_recinto_con_puestos_afuera, _e7_recinto_contra_fachada,
             _e8_entre_corredores]
RECETAS_F = [_f1_mesa_con_sillas, _f2_mesa_entre_mesas, _f3_junto_a_puestos, _f4_contra_particion,
             _f5_dentro_de_una_sala, _f6_mesa_junto_a_circulacion, _f7_mueble_contra_fachada,
             _f8_mueble_aislado]

NOMBRES_E = ["banda_de_recintos", "corredor_en_L", "pod_aislado", "junto_al_nucleo",
             "bateria_de_recintos", "recinto_con_puestos_afuera", "recinto_contra_fachada",
             "entre_corredores"]
NOMBRES_F = ["mesa_con_sillas", "mesa_entre_mesas", "junto_a_puestos", "contra_particion",
             "dentro_de_una_sala", "junto_a_circulacion", "mueble_contra_fachada",
             "mueble_aislado"]


def pares():
    """(pid, target, idx_receta_enclosure, idx_receta_furniture).

    PAR01-PAR04 usan la familia critica E1/F1 (§15). El resto recorre las ocho recetas de cada
    clase con pasos coprimos, para que las recetas espejo (E3/F8, E7/F7) casi nunca coincidan.
    """
    out = []
    for i, (pid, t) in enumerate(targets()):
        if i < 4:
            ie, if_ = 0, 0
        else:
            ie, if_ = i % 8, (i * 5 + 2) % 8
        out.append((pid, t, ie, if_))
    return out


# --- rasterizado ----------------------------------------------------------------------------------
def _dibuja(img, objs, S, color=TINTA):
    g = _t(S)
    for o in objs:
        pts = np.array([[int(round(px * S)), int(round(py * S))] for px, py in o["pts"]], np.int32)
        cv2.polylines(img, [pts], o.get("cerrado", False), int(color), g, cv2.LINE_8)


def caja_crop(t, S=SIDE):
    x, y, w, h = t
    m = MARGEN_CROP
    g = _t(S)
    x0 = int(round((x - m) * S)) - g; y0 = int(round((y - m) * S)) - g
    x1 = int(round((x + w + m) * S)) + g; y1 = int(round((y + h + m) * S)) + g
    return max(0, x0), max(0, y0), min(S, x1), min(S, y1)


def _marcador(img, caja, S):
    """Marcador neutro: rectangulo punteado en el borde del recuadro. IDENTICO en ambas clases."""
    x0, y0, x1, y1 = caja
    paso = max(6, S // 120)
    for x in range(x0, x1, paso * 2):
        cv2.line(img, (x, y0), (min(x + paso, x1 - 1), y0), GRIS_MARCA, 2)
        cv2.line(img, (x, y1 - 1), (min(x + paso, x1 - 1), y1 - 1), GRIS_MARCA, 2)
    for y in range(y0, y1, paso * 2):
        cv2.line(img, (x0, y), (x0, min(y + paso, y1 - 1)), GRIS_MARCA, 2)
        cv2.line(img, (x1 - 1, y), (x1 - 1, min(y + paso, y1 - 1)), GRIS_MARCA, 2)


def render(pid, clase, S=SIDE):
    """Devuelve (imagen, caja_crop, leakage_px). El target se dibuja SIEMPRE al final."""
    d = dict((p[0], p) for p in pares())[pid]
    pid_, t, ie, if_ = d
    receta = RECETAS_E[ie] if clase == "ARCHITECTURAL_ENCLOSURE" else RECETAS_F[if_]
    img = np.full((S, S), PAPEL, np.uint8)
    _dibuja(img, fondo(t, int(pid_[3:])), S)
    _dibuja(img, receta(t), S)
    caja = caja_crop(t, S)
    x0, y0, x1, y1 = caja
    antes = img[y0:y1, x0:x1]
    leakage = int((antes != PAPEL).sum())
    img[y0:y1, x0:x1] = PAPEL                      # keep-out duro: garantiza identidad del crop
    _marcador(img, caja, S)
    _dibuja(img, [rect(*t)], S)                    # el TARGET, siempre el mismo
    return img, caja, leakage


def crop(img, caja):
    x0, y0, x1, y1 = caja
    return img[y0:y1, x0:x1].copy()


def receta_nombre(pid, clase):
    d = dict((p[0], p) for p in pares())[pid]
    return NOMBRES_E[d[2]] if clase == "ARCHITECTURAL_ENCLOSURE" else NOMBRES_F[d[3]]
