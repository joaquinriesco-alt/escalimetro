"""E37 — el plano esquemático, dibujado DESDE la representación estructurada.

Nunca desde una imagen generada: la geometría la afirma el contrato, y el dibujo sólo la muestra.
Por eso la incertidumbre se ve —un recinto de confianza baja va punteado y translúcido, uno sin
ubicar queda en una franja aparte— en vez de rellenarse para que el plano parezca completo.

El SVG de una corrida se dibuja UNA vez, al cerrarla, y se guarda con su sha256. Si este archivo
cambia mañana, las corridas viejas siguen mostrando lo que mostraban: una corrida no cambia en
silencio por volver a abrirla (E37 §16). `RENDERER_VERSION` queda registrado junto al archivo.

Todo texto que viene del motor se escapa: el SVG se sirve como `image/svg+xml` desde el mismo
origen, y una etiqueta de recinto es texto de un proveedor, no marcado nuestro.
"""
from __future__ import annotations

import html
from typing import Dict, List, Optional, Tuple

from . import contract

RENDERER_VERSION = "recon_svg_v1"

LABEL_PX = 24
AREA_PX = 18
NOTE_PX = 17

WIDTH = 1000
MARGIN = 40
UNPLACED_ROW = 28

#: Tintes por tipo de recinto. Suaves a propósito: el color ayuda a leer, no afirma nada.
_TINT = {
    "LIVING": "#f3e9dc", "DINING": "#f3e9dc", "LIVING_DINING": "#f3e9dc", "KITCHEN": "#e6efe6",
    "BEDROOM": "#e3eaf5", "BATHROOM": "#dff0f2", "TOILET": "#dff0f2", "WALK_IN_CLOSET": "#ece6f3",
    "CLOSET": "#ece6f3", "HALLWAY": "#f1f1f1", "ENTRY": "#f1f1f1", "LAUNDRY": "#e6efe6",
    "TERRACE": "#eef3e2", "BALCONY": "#eef3e2", "STUDY": "#e3eaf5", "STORAGE": "#f1f1f1",
    "OTHER": "#f4f4f4",
}
_CONN_STYLE = {
    "DOOR": 'stroke="#b5452f" stroke-width="3"',
    "OPENING": 'stroke="#b5452f" stroke-width="2" stroke-dasharray="8 5"',
    "ADJACENT": 'stroke="#6b7480" stroke-width="1.5"',
    "UNKNOWN": 'stroke="#6b7480" stroke-width="1.5" stroke-dasharray="2 5"',
}


def _e(v) -> str:
    return html.escape(str(v), quote=True)


def _centroid(pts: List[List[float]]) -> Tuple[float, float]:
    """Centroide de área (no el promedio de vértices, que se va hacia el lado con más quiebres)."""
    a = cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if abs(a) < 1e-9:
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    return (cx / (3 * a), cy / (3 * a))


def aspect(plan: Dict) -> Optional[float]:
    """Alto/ancho de la huella, si el motor declaró ambas medidas. None si no: se dibuja cuadrado y
    se dice que la proporción no se conoce, en vez de adivinarla."""
    fp = (plan or {}).get("footprint") or {}
    w, d = fp.get("width_m"), fp.get("depth_m")
    if w and d and w > 0 and d > 0:
        return float(d) / float(w)
    return None


def svg(plan: Dict, *, caption: str = "") -> str:
    """El SVG completo de una representación v1. `caption` es el pie (motor, corrida)."""
    plan = plan or {}
    rooms = plan.get("rooms") or []
    ubicados = contract.placed(plan)
    sin_ubicar = contract.unplaced(plan)
    prop = aspect(plan)
    inner_w = WIDTH - 2 * MARGIN
    inner_h = inner_w * (prop if prop else 1.0)
    alto_plano = MARGIN + inner_h + MARGIN
    extra = (30 + UNPLACED_ROW * len(sin_ubicar)) if sin_ubicar else 0
    alto = int(alto_plano + extra + 110)

    def P(x: float, y: float) -> Tuple[float, float]:
        return (MARGIN + x * inner_w, MARGIN + y * inner_h)

    out: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {alto}" '
        f'width="{WIDTH}" height="{alto}" font-family="Helvetica, Arial, sans-serif">',
        f'<rect x="0" y="0" width="{WIDTH}" height="{alto}" fill="#ffffff"/>',
        f'<rect x="{MARGIN}" y="{MARGIN}" width="{inner_w:.1f}" height="{inner_h:.1f}" '
        f'fill="none" stroke="#d6d9dd" stroke-dasharray="6 6"/>',
    ]
    centros: Dict[str, Tuple[float, float]] = {}
    for r in ubicados:
        pts = [P(float(x), float(y)) for x, y in r["polygon"]]
        centros[r["id"]] = P(*_centroid(r["polygon"]))
        baja = float(r.get("confidence", 0)) < contract.LOW_CONFIDENCE
        trazo = ' stroke-dasharray="7 5"' if baja else ""
        opac = "0.55" if baja else "1"
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        out.append(f'<polygon points="{d}" fill="{_TINT.get(r.get("room_type"), "#f4f4f4")}" '
                   f'fill-opacity="{opac}" stroke="#1d2430" stroke-width="2"{trazo}>'
                   f'<title>{_e(r.get("label", ""))} · confianza {float(r.get("confidence", 0)):.2f}'
                   f'</title></polygon>')
    for c in plan.get("connections") or []:
        a, b = centros.get(c.get("from_room")), centros.get(c.get("to_room"))
        if a and b:
            out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                       f'{_CONN_STYLE.get(c.get("kind"), _CONN_STYLE["UNKNOWN"])} '
                       f'stroke-opacity="0.55"/>')
    for r in ubicados:
        cx, cy = centros[r["id"]]
        baja = float(r.get("confidence", 0)) < contract.LOW_CONFIDENCE
        etiqueta = _e(r.get("label", "")) + (" ?" if baja else "")
        out.append(f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="{LABEL_PX}" '
                   f'fill="#1d2430" paint-order="stroke" stroke="#ffffff" stroke-width="5">'
                   f'{etiqueta}</text>')
        if r.get("area_m2"):
            out.append(f'<text x="{cx:.1f}" y="{cy + AREA_PX + 6:.1f}" text-anchor="middle" '
                       f'font-size="{AREA_PX}" fill="#6b7480" paint-order="stroke" stroke="#ffffff" '
                       f'stroke-width="4">≈ {float(r["area_m2"]):.0f} m²</text>')
    y = alto_plano
    if sin_ubicar:
        out.append(f'<text x="{MARGIN}" y="{y + 10:.1f}" font-size="{NOTE_PX}" fill="#b5452f">'
                   f'Sin ubicar ({len(sin_ubicar)}): el motor cree que existen pero no sabe dónde'
                   f'</text>')
        for i, r in enumerate(sin_ubicar):
            yy = y + 10 + UNPLACED_ROW * (i + 1)
            nota = f" — {_e(r['uncertainty'])}" if r.get("uncertainty") else ""
            out.append(f'<text x="{MARGIN + 12}" y="{yy:.1f}" font-size="{NOTE_PX - 1}" fill="#1d2430">'
                       f'· {_e(r.get("label", ""))}{nota}</text>')
        y += extra
    # leyenda de conexiones: el trazo entre centros es una relación, no un muro ni un pasillo
    ly = y + 28
    lx = MARGIN
    for kind, texto in (("DOOR", "puerta"), ("OPENING", "abertura"), ("ADJACENT", "contiguos"),
                        ("UNKNOWN", "sin saber")):
        out.append(f'<line x1="{lx}" y1="{ly - 5}" x2="{lx + 34}" y2="{ly - 5}" '
                   f'{_CONN_STYLE[kind]}/>')
        out.append(f'<text x="{lx + 42}" y="{ly}" font-size="15" fill="#6b7480">{texto}</text>')
        lx += 170
    out.append(f'<text x="{lx}" y="{ly}" font-size="15" fill="#6b7480">punteado = confianza baja</text>')
    pie = "Plano esquemático · referencial · no es un levantamiento"
    if not prop:
        pie += " · proporción desconocida: dibujado en un marco cuadrado"
    out.append(f'<text x="{MARGIN}" y="{y + 60:.1f}" font-size="16" fill="#6b7480">{_e(pie)}</text>')
    if caption:
        out.append(f'<text x="{MARGIN}" y="{y + 84:.1f}" font-size="16" fill="#6b7480">'
                   f'{_e(caption)}</text>')
    if not rooms:
        out.append(f'<text x="{WIDTH / 2:.0f}" y="{alto_plano / 2:.0f}" text-anchor="middle" '
                   f'font-size="18" fill="#6b7480">Sin recintos: el motor no dibujó una planta</text>')
    out.append("</svg>")
    return "\n".join(out)
