"""Renders del layout. Una sola fuente de geometría (Layout + ShellM); dos estilos:
  - geometry: planta técnica verificable (cotas de módulos, ids, grafo de circulación, pilares, zonas)
  - commercial: misma geometría, presentación limpia con mobiliario legible y paleta suave.
La geometría NO cambia entre ambos: los dos leen los mismos Placement.x/y/w/d y desks.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..renderer.side_by_side import _svg_to_bgr
from .model import Layout, Placement, ShellM

LABELS = {"workstation_cluster": "Open space", "workstation_row": "Open space", "private_office": "Oficina privada",
          "meeting_4": "Sala 4", "meeting_8": "Sala 8", "boardroom_12": "Directorio 12", "phone_booth": "Phone booth",
          "reception": "Recepción", "kitchenette": "Kitchenette", "dining": "Comedor", "lounge": "Lounge"}
COMMERCIAL_FILL = {"workstation_cluster": "#f4f6f9", "workstation_row": "#f4f6f9", "private_office": "#e8eef6", "meeting_4": "#e6f0ea",
                   "meeting_8": "#e6f0ea", "boardroom_12": "#dfeae3", "phone_booth": "#f1ede4", "reception": "#f6efe6",
                   "kitchenette": "#f3ede8", "dining": "#f3ede8", "lounge": "#f0e9ef"}
TECH_FILL = {"WORK": "#eef3fb", "SEMI_PUBLIC": "#eaf5ee", "PUBLIC": "#fbf1e6", "SUPPORT": "#f5f0ea", "": "#f4f4f4"}


class _Tf:
    def __init__(self, shell: ShellM, width_px: int, margin: float, extra_bottom: float = 0.0):
        minx, miny, maxx, maxy = shell.perimeter.bounds
        cx = [minx, maxx]; cy = [miny, maxy]
        for c in shell.core:
            b = c.bounds; cx += [b[0], b[2]]; cy += [b[1], b[3]]
        self.x0, self.x1, self.y0, self.y1 = min(cx), max(cx), min(cy), max(cy)
        self.s = (width_px - 2 * margin) / (self.x1 - self.x0)
        self.m = margin
        self.W = width_px
        self.H = (self.y1 - self.y0) * self.s + 2 * margin + extra_bottom

    def __call__(self, p):
        return (self.m + (p[0] - self.x0) * self.s, self.m + (self.y1 - p[1]) * self.s)

    def rect(self, x, y, w, d):
        X, Y = self((x, y + d))
        return X, Y, w * self.s, d * self.s


def _poly_pts(tf, poly):
    return " ".join(f"{X:.1f},{Y:.1f}" for X, Y in (tf(p) for p in poly.exterior.coords))


def _desk_glyph(tf, x, y, w, d, style: str) -> List[str]:
    """Puesto 1.6×1.6: mesa 1.6×0.8 pegada al lado interior + silla. Orientación: la mesa va al lado
    de la celda que da hacia el centro del cluster (se resuelve fuera; aquí mesa en la mitad superior)."""
    o = []
    X, Y, W, D = tf.rect(x, y, w, d)
    if w >= d:      # celda horizontal: mesa arriba (0.8) silla abajo
        tX, tY, tW, tD = X + 0.05 * W, Y + 0.05 * D, 0.9 * W, 0.45 * D
        cX, cY, r = X + W / 2, Y + 0.75 * D, 0.14 * min(W, D)
    else:
        tX, tY, tW, tD = X + 0.05 * W, Y + 0.05 * D, 0.45 * W, 0.9 * D
        cX, cY, r = X + 0.75 * W, Y + D / 2, 0.14 * min(W, D)
    if style == "commercial":
        o.append(f'<rect x="{tX:.1f}" y="{tY:.1f}" width="{tW:.1f}" height="{tD:.1f}" rx="2" fill="#ffffff" stroke="#8a94a6" stroke-width="1"/>')
        o.append(f'<circle cx="{cX:.1f}" cy="{cY:.1f}" r="{r:.1f}" fill="#c9d2df" stroke="#8a94a6" stroke-width="1"/>')
    else:
        o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{W:.1f}" height="{D:.1f}" fill="none" stroke="#7a8aa6" stroke-width="0.8" stroke-dasharray="3,2"/>')
        o.append(f'<rect x="{tX:.1f}" y="{tY:.1f}" width="{tW:.1f}" height="{tD:.1f}" fill="none" stroke="#33415c" stroke-width="1"/>')
        o.append(f'<circle cx="{cX:.1f}" cy="{cY:.1f}" r="{r:.1f}" fill="none" stroke="#33415c" stroke-width="1"/>')
    return o


def _room_furniture(tf, p: Placement, style: str) -> List[str]:
    o = []
    X, Y, W, D = tf.rect(p.x, p.y, p.w, p.d)
    s = tf.s
    stroke = "#8a94a6" if style == "commercial" else "#33415c"
    fill = "#ffffff" if style == "commercial" else "none"
    cx, cy = X + W / 2, Y + D / 2
    if p.module in ("meeting_4", "meeting_8", "boardroom_12"):
        n = {"meeting_4": 4, "meeting_8": 8, "boardroom_12": 12}[p.module]
        tl = {"meeting_4": 1.6, "meeting_8": 2.4, "boardroom_12": 4.2}[p.module] * s
        tw = {"meeting_4": 0.8, "meeting_8": 1.0, "boardroom_12": 1.4}[p.module] * s
        if W < D:
            tl, tw = tw, tl
        o.append(f'<rect x="{cx - tl / 2:.1f}" y="{cy - tw / 2:.1f}" width="{tl:.1f}" height="{tw:.1f}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        per_side = n // 2
        for k in range(per_side):
            if W >= D:
                px = cx - tl / 2 + (k + 0.5) * tl / per_side
                for py in (cy - tw / 2 - 0.35 * s, cy + tw / 2 + 0.35 * s):
                    o.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{0.22 * s:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
            else:
                py = cy - tw / 2 + (k + 0.5) * tw / per_side
                for px in (cx - tl / 2 - 0.35 * s, cx + tl / 2 + 0.35 * s):
                    o.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{0.22 * s:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    elif p.module == "private_office":
        tl, tw = 1.8 * s, 0.8 * s
        if W < D:
            tl, tw = tw, tl
        o.append(f'<rect x="{cx - tl / 2:.1f}" y="{cy - tw / 2:.1f}" width="{tl:.1f}" height="{tw:.1f}" rx="2" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        o.append(f'<circle cx="{cx:.1f}" cy="{cy + (tw / 2 + 0.35 * s if W >= D else 0):.1f}" r="{0.22 * s:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    elif p.module == "phone_booth":
        o.append(f'<rect x="{cx - 0.3 * s:.1f}" y="{cy - 0.2 * s:.1f}" width="{0.6 * s:.1f}" height="{0.4 * s:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    elif p.module == "reception":
        o.append(f'<rect x="{X + 0.3 * s:.1f}" y="{Y + 0.3 * s:.1f}" width="{2.4 * s if W >= D else 0.7 * s:.1f}" height="{0.7 * s if W >= D else 2.4 * s:.1f}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
        for k in range(3):
            o.append(f'<rect x="{X + W - 0.9 * s:.1f}" y="{Y + 0.4 * s + k * 0.8 * s:.1f}" width="{0.6 * s:.1f}" height="{0.6 * s:.1f}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    elif p.module == "kitchenette":
        if W >= D:
            o.append(f'<rect x="{X + 0.1 * s:.1f}" y="{Y + 0.1 * s:.1f}" width="{W - 0.2 * s:.1f}" height="{0.6 * s:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        else:
            o.append(f'<rect x="{X + 0.1 * s:.1f}" y="{Y + 0.1 * s:.1f}" width="{0.6 * s:.1f}" height="{D - 0.2 * s:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    elif p.module == "dining":
        for k in range(4):
            gx = X + W * (0.25 + 0.5 * (k % 2)); gy = Y + D * (0.25 + 0.5 * (k // 2))
            o.append(f'<rect x="{gx - 0.6 * s:.1f}" y="{gy - 0.4 * s:.1f}" width="{1.2 * s:.1f}" height="{0.8 * s:.1f}" rx="2" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    elif p.module == "lounge":
        o.append(f'<rect x="{X + 0.4 * s:.1f}" y="{Y + 0.4 * s:.1f}" width="{2.0 * s:.1f}" height="{0.8 * s:.1f}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        o.append(f'<rect x="{X + 0.4 * s:.1f}" y="{Y + D - 1.2 * s:.1f}" width="{2.0 * s:.1f}" height="{0.8 * s:.1f}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        o.append(f'<rect x="{X + 2.9 * s:.1f}" y="{cy - 0.4 * s:.1f}" width="{0.9 * s:.1f}" height="{0.8 * s:.1f}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    return o


def render_layout_svg(layout: Layout, shell: ShellM, style: str = "geometry", width_px: int = 1800,
                      title: str = "", grid_cell: Optional[float] = None, circulation_cells=None, show_strips: bool = True,
                      highlight_ids=None, chrome: bool = True, margin: float = 60) -> str:
    """highlight_ids (E06): ids de placements a resaltar (borde rojo grueso) — p. ej. lo que cambió un QA humano.
    chrome (E07): False = sin pie ni barra de escala (para incrustar la MISMA planta en una lámina). La
    geometría dibujada es idéntica; sólo se omite el chrome del lienzo."""
    tf = _Tf(shell, width_px, margin, extra_bottom=(0 if not chrome else (190 if style == "commercial" else 150)))
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{tf.W}" height="{tf.H:.0f}" viewBox="0 0 {tf.W} {tf.H:.0f}" '
         f'font-family="Helvetica,Arial,sans-serif">', '<rect width="100%" height="100%" fill="#ffffff"/>']
    # shell
    o.append(f'<polygon points="{_poly_pts(tf, shell.perimeter)}" fill="{"#fbfbfb" if style == "commercial" else "#ffffff"}" stroke="none"/>')
    # circulación (celdas) — técnica: sombreado; comercial: tono muy suave
    if circulation_cells and grid_cell:
        col = "#e9ecf2" if style == "commercial" else "#fff2cc"
        for (i, j) in circulation_cells:
            x = shell.perimeter.bounds[0] + i * grid_cell; y = shell.perimeter.bounds[1] + j * grid_cell
            X, Y, W, D = tf.rect(x, y, grid_cell, grid_cell)
            o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{W + 0.5:.1f}" height="{D + 0.5:.1f}" fill="{col}" stroke="none"/>')
    # franjas y conectores (sólo técnica)
    if style == "geometry" and show_strips:
        for kind, depth, r in layout.zones.get("strips", []):
            X, Y, W, D = tf.rect(r[0], r[1], r[2] - r[0], r[3] - r[1])
            col = {"desks": "#7a8aa6", "rooms": "#6b9a7a", "corridor": "#c9a227"}.get(kind, "#999")
            o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{W:.1f}" height="{D:.1f}" fill="none" stroke="{col}" stroke-width="0.8" stroke-dasharray="4,3" opacity="0.7"/>')
        for r in layout.zones.get("connectors", []):
            X, Y, W, D = tf.rect(r[0], r[1], r[2] - r[0], r[3] - r[1])
            o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{W:.1f}" height="{D:.1f}" fill="#fff2cc" stroke="#c9a227" stroke-width="0.8" opacity="0.6"/>')
    # recintos
    for p in layout.placements:
        X, Y, W, D = tf.rect(p.x, p.y, p.w, p.d)
        if p.module.startswith("workstation"):
            if style == "geometry":
                o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{W:.1f}" height="{D:.1f}" fill="{TECH_FILL["WORK"]}" stroke="#7a8aa6" stroke-width="1"/>')
            for (dx, dy, dw, dd) in p.desks:
                o += _desk_glyph(tf, dx, dy, dw, dd, style)
            continue
        fill = COMMERCIAL_FILL.get(p.module, "#f4f4f4") if style == "commercial" else TECH_FILL.get(p.zone, "#f4f4f4")
        stroke = "#3a3a3a" if style == "commercial" else "#222"
        sw = 1.6 if style == "commercial" else 1.4
        o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{W:.1f}" height="{D:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        o += _room_furniture(tf, p, style)
        # puerta
        if p.door:
            dX, dY = tf(p.door)
            o.append(f'<circle cx="{dX:.1f}" cy="{dY:.1f}" r="{0.45 * tf.s:.1f}" fill="#ffffff" stroke="{stroke}" stroke-width="1"/>')
            o.append(f'<line x1="{dX - 0.45 * tf.s:.1f}" y1="{dY:.1f}" x2="{dX + 0.45 * tf.s:.1f}" y2="{dY:.1f}" stroke="{stroke}" stroke-width="1"/>')
        # etiqueta
        fs = max(9, min(13, 0.32 * tf.s))
        label = LABELS.get(p.module, p.module)
        if style == "geometry":
            label = f"{p.id} · {p.w:.1f}×{p.d:.1f}"
        elif p.module in ("meeting_4", "meeting_8", "boardroom_12", "dining", "private_office"):
            label += f" · {p.seats}" if p.seats else ""
        o.append(f'<text x="{X + W / 2:.1f}" y="{Y + D / 2 + (D * 0.28 if p.module not in ("phone_booth",) else 0):.1f}" font-size="{fs:.0f}" '
                 f'text-anchor="middle" fill="#333" opacity="0.9">{label}</text>')
    # core, pilares, perímetro
    for c in shell.core:
        o.append(f'<polygon points="{_poly_pts(tf, c)}" fill="#d9d9d9" stroke="#444" stroke-width="1.6"/>')
        cx, cy = tf((c.centroid.x, c.centroid.y))
        o.append(f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="13" text-anchor="middle" fill="#555">NÚCLEO</text>')
    for c in shell.columns:
        o.append(f'<polygon points="{_poly_pts(tf, c)}" fill="#222" stroke="none"/>')
    o.append(f'<polygon points="{_poly_pts(tf, shell.perimeter)}" fill="none" stroke="#111" stroke-width="2.6"/>')
    # acceso y grafo
    eX, eY = tf(shell.entrance)
    o.append(f'<circle cx="{eX:.1f}" cy="{eY:.1f}" r="9" fill="#ffffff" stroke="#c0392b" stroke-width="3"/>')
    o.append(f'<text x="{eX + 12:.1f}" y="{eY - 10:.1f}" font-size="12" fill="#c0392b" font-weight="bold">ACCESO</text>')
    if style == "geometry":
        for n in layout.circulation_graph.get("nodes", []):
            if n["id"] == "entrance":
                continue
            X, Y = tf(n["xy"])
            o.append(f'<line x1="{eX:.1f}" y1="{eY:.1f}" x2="{X:.1f}" y2="{Y:.1f}" stroke="#c9a227" stroke-width="0.6" opacity="0.5"/>')
    # pie
    base = tf.H - (190 if style == "commercial" else 150) + 24
    if not chrome:
        pass
    elif style == "commercial":
        o.append(f'<text x="{margin}" y="{base:.0f}" font-size="22" fill="#111" font-weight="bold">{title or layout.layout_id}</text>')
        seats = sum(p.seats for p in layout.placements if p.module.startswith("workstation"))
        priv = sum(1 for p in layout.placements if p.module == "private_office")
        m = layout.metrics or {}
        o.append(f'<text x="{margin}" y="{base + 26:.0f}" font-size="13" fill="#333">Capacidad: {seats} puestos open + {priv} oficinas privadas · '
                 f'{sum(1 for p in layout.placements if p.module in ("meeting_4", "meeting_8", "boardroom_12"))} salas · '
                 f'comedor, lounge, {sum(1 for p in layout.placements if p.module == "phone_booth")} phone booths</text>')
        o.append(f'<text x="{margin}" y="{base + 46:.0f}" font-size="12" fill="#555">Superficie útil {shell.usable.area:.0f} m² (escala inferida de la superficie publicada) · '
                 f'circulación {m.get("circulation_area_m2", "—")} m² · programa neto {m.get("net_programmed_area_m2", "—")} m²</text>')
        o.append(f'<text x="{margin}" y="{base + 66:.0f}" font-size="11" fill="#8a1f1f">Dimensiones sujetas a confirmación de escala. Test-fit conceptual, no proyecto de arquitectura.</text>')
        o.append(f'<text x="{tf.W - margin:.0f}" y="{base:.0f}" font-size="14" text-anchor="end" fill="#111" font-weight="bold">ESCALÍMETRO</text>')
        o.append(f'<text x="{tf.W - margin:.0f}" y="{base + 18:.0f}" font-size="10" text-anchor="end" fill="#777">pre-design · feasibility · test-fit</text>')
    else:
        o.append(f'<text x="{margin}" y="{base:.0f}" font-size="16" fill="#111">{title or layout.layout_id} — planta técnica (metros, escala {shell.px_per_m:.2f} px/m {shell.scale_confidence})</text>')
        o.append(f'<text x="{margin}" y="{base + 20:.0f}" font-size="11" fill="#555">Franjas: gris = puestos · verde = recintos · amarillo = pasillo/conector · sombreado = pasillos usados por el grafo · líneas finas = grafo acceso→puerta</text>')
        o.append(f'<text x="{margin}" y="{base + 38:.0f}" font-size="11" fill="#555">Score {layout.scores.get("total") if layout.scores else "—"} · violaciones duras: {len(layout.hard_violations)} · seed {layout.seed} · Dimensiones sujetas a confirmación de escala.</text>')
    for p in layout.placements:
        if highlight_ids and p.id in highlight_ids:
            X, Y, W, D = tf.rect(p.x, p.y, p.w, p.d)
            o.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{W:.1f}" height="{D:.1f}" fill="none" stroke="#d62728" stroke-width="4" stroke-dasharray="8,4"/>')
    # candidato inválido: se marca en AMBAS plantas (nunca se presenta como test-fit válido)
    if layout.hard_violations:
        prog = [v for v in layout.hard_violations if v.startswith("programa") or v.startswith("puestos")]
        msg = "CANDIDATO INVÁLIDO — " + ("; ".join(prog) if prog else f"{len(layout.hard_violations)} violaciones duras")
        o.append(f'<rect x="{margin}" y="{margin - 44:.0f}" width="{tf.W - 2 * margin:.0f}" height="34" fill="#fdecec" stroke="#b42318" stroke-width="1.5"/>')
        o.append(f'<text x="{margin + 12}" y="{margin - 21:.0f}" font-size="15" fill="#b42318" font-weight="bold">{msg} · no es un test-fit válido (Gate E1 FAIL)</text>')
    # barra 5 m
    if chrome:
        bx = tf.W - margin - 5 * tf.s; by = base + (100 if style == "commercial" else 60)
        o.append(f'<line x1="{bx:.1f}" y1="{by:.0f}" x2="{bx + 5 * tf.s:.1f}" y2="{by:.0f}" stroke="#111" stroke-width="3"/>')
        o.append(f'<text x="{bx:.1f}" y="{by - 6:.0f}" font-size="11" fill="#111">5 m</text>')
    o.append("</svg>")
    return "\n".join(o)


def render_png(layout: Layout, shell: ShellM, style: str, path: str, width_px: int = 1800, **kw) -> np.ndarray:
    svg = render_layout_svg(layout, shell, style, width_px, **kw)
    img = _svg_to_bgr(svg, width_px)
    if img is None:
        raise RuntimeError("cairosvg no disponible")
    cv2.imwrite(path, img)
    with open(path.replace(".png", ".svg"), "w", encoding="utf-8") as f:
        f.write(svg)
    return img


def triptych(panels: List[Tuple[np.ndarray, str]], panel_width: int = 900) -> np.ndarray:
    imgs = []
    for img, title in panels:
        h, w = img.shape[:2]
        imgs.append((cv2.resize(img, (panel_width, int(h * panel_width / w)), interpolation=cv2.INTER_AREA), title))
    H = max(i.shape[0] for i, _ in imgs) + 44
    gap = 24
    canvas = np.full((H, panel_width * len(imgs) + gap * (len(imgs) - 1), 3), 255, np.uint8)
    for k, (img, title) in enumerate(imgs):
        x = k * (panel_width + gap)
        canvas[44:44 + img.shape[0], x:x + panel_width] = img
        cv2.putText(canvas, title, (x + 8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    return canvas
