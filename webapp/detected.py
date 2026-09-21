"""E27.3 §5 — dibujo de LO QUE EL MOTOR DETECTÓ, sobre la planta que subió el usuario.

Por qué existe este módulo y no se reutiliza `shellview.shell_svg`: aquel dibuja un shell YA
construido, y construirlo pasa por `layout/shell_adapter.py`, que se niega a devolver nada mientras
`ready_for_layout` sea falso. Es decir: justo antes de la confirmación humana —que es cuando hace
falta enseñar el dibujo— el render de siempre no está disponible, por diseño.

Así que esto dibuja directamente desde `floorplate.json`, en el sistema de coordenadas de la imagen
original, para poder superponerse a la planta subida. No interpreta nada: pinta lo que el pipeline
ya escribió. Si un elemento no fue detectado, no se dibuja y no se pregunta por él.
"""
from __future__ import annotations

from typing import Dict, List, Optional

#: Colores del overlay. Cada elemento del formulario de confirmación usa el MISMO color que su
#: dibujo, para que "Núcleo" en la lista y el polígono gris en la planta sean obviamente lo mismo.
COLORS = {
    "perimeter": "#1d2430",
    "core": "#7a8598",
    "columns": "#111111",
    "daylight": "#2f7ac4",
    "entrance": "#b5452f",
}


def overlay_svg(fp: Dict) -> Optional[str]:
    """SVG transparente con la geometría detectada, en píxeles de la imagen original."""
    img = fp.get("source_image") or {}
    w, h = img.get("width_px"), img.get("height_px")
    if not w or not h:
        return None
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
         f'preserveAspectRatio="none" class="ovl">']

    ring = ((fp.get("perimeter") or {}).get("ring")) or []
    if ring:
        pts = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in ring)
        o.append(f'<polygon points="{pts}" fill="none" stroke="{COLORS["perimeter"]}" '
                 f'stroke-width="3" vector-effect="non-scaling-stroke"/>')

    for c in fp.get("core") or []:
        pts = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in (c.get("ring") or []))
        if pts:
            o.append(f'<polygon points="{pts}" fill="{COLORS["core"]}" fill-opacity="0.35" '
                     f'stroke="{COLORS["core"]}" stroke-width="2" vector-effect="non-scaling-stroke"/>')

    for col in fp.get("column_candidates") or []:
        cx, cy = col.get("center") or (None, None)
        if cx is None:
            continue
        s = max(float(col.get("size_px") or 8), 6)
        o.append(f'<rect x="{cx - s / 2:.1f}" y="{cy - s / 2:.1f}" width="{s:.1f}" height="{s:.1f}" '
                 f'fill="{COLORS["columns"]}" fill-opacity="0.85"/>')

    ext = set(fp.get("exterior_facade_segments") or [])
    for d in fp.get("daylight_segments") or []:
        if d.get("index") not in ext or d.get("classification") == "unknown":
            continue
        (x1, y1), (x2, y2) = d.get("start"), d.get("end")
        o.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{COLORS["daylight"]}" stroke-width="5" stroke-linecap="round" '
                 f'vector-effect="non-scaling-stroke" opacity="0.9"/>')

    ent = fp.get("primary_entrance") or {}
    if ent.get("point"):
        ex, ey = ent["point"]
        o.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="9" fill="#ffffff" '
                 f'stroke="{COLORS["entrance"]}" stroke-width="4" vector-effect="non-scaling-stroke"/>')
    o.append("</svg>")
    return "\n".join(o)


# ===================================================================================================
# Qué se detectó, en lenguaje de producto (§9: nada de vocabulario interno en pantalla)
# ===================================================================================================
def summary(fp: Dict) -> List[Dict]:
    """Una fila por elemento: qué es, cuánto encontró y si hay que revisarlo.

    `key` es el valor que el runtime espera en `overrides.confirm`; nunca se muestra."""
    filas: List[List] = []
    ring = ((fp.get("perimeter") or {}).get("ring")) or []
    filas.append(["perimeter", "Perímetro", f"contorno de {len(ring)} lados" if ring else None])

    core = fp.get("core") or []
    filas.append(["core", "Núcleo", f"{len(core)} núcleo(s): ascensores, escaleras, baños"
                  if core else None])

    cols = fp.get("column_candidates") or []
    filas.append(["columns", "Pilares", f"{len(cols)} pilar(es)" if cols else None])

    ext = set(fp.get("exterior_facade_segments") or [])
    vidr = [d for d in (fp.get("daylight_segments") or [])
            if d.get("index") in ext and d.get("classification") != "unknown"]
    filas.append(["daylight", "Fachada / ventanas",
                  f"{len(vidr)} tramo(s) con luz natural" if vidr else None])

    out = []
    for key, etiqueta, detalle in filas:
        out.append({"key": key, "label": etiqueta, "detail": detalle,
                    "found": detalle is not None, "color": COLORS.get(key, "#1d2430")})
    return out


def scale_row(fp: Dict) -> Dict:
    """La escala se cuenta aparte: según de dónde salga, se confirma o no se pregunta.

    Medida por el usuario (dos puntos + distancia real) → ya está confirmada y NO se vuelve a
    preguntar (§10). Estimada desde la superficie publicada → sí hay que confirmarla, y se dice
    de dónde salió."""
    sc = fp.get("scale") or {}
    ppm = sc.get("px_per_m")
    metodo = sc.get("method")
    estado = ((sc.get("meta") or {}).get("status"))
    if metodo == "manual":
        texto = "Medida por vos sobre el plano."
    elif metodo == "published_area_inferred":
        texto = ("Estimada a partir de la superficie publicada"
                 + (f" ({sc.get('reference_area_m2')} m²)" if sc.get("reference_area_m2") else "")
                 + ". Conviene confirmarla o medirla sobre el plano.")
    else:
        texto = "No se pudo determinar."
    return {"confirmed": estado == "confirmed", "needs_confirm": bool(ppm) and estado != "confirmed",
            "text": texto, "has_scale": bool(ppm)}
