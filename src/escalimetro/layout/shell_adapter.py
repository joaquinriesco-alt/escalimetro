"""Floorplate 0.2.0 (px) → ShellM (metros). Exige shell_readiness.ready_for_layout = true."""
from __future__ import annotations

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from ..schemas.floorplate import Floorplate
from .model import DaylightEdge, ShellM


def shell_from_floorplate(fp: Floorplate, column_size_min_m: float = 0.5, column_size_max_m: float = 0.8) -> ShellM:
    if not fp.shell_readiness or not fp.shell_readiness.ready_for_layout:
        raise ValueError("El shell no está listo para layout (shell_readiness.ready_for_layout = false). "
                         f"Pendiente: {fp.shell_readiness and fp.shell_readiness.requires_confirmation}")
    if not fp.scale.px_per_m:
        raise ValueError("sin escala")
    ppm = fp.scale.px_per_m
    perim = Polygon([fp.to_m(p) for p in fp.perimeter.ring])
    if not perim.is_valid:
        perim = perim.buffer(0)
    cores = [Polygon([fp.to_m(p) for p in c.ring]).buffer(0) for c in fp.core]
    usable = perim.difference(unary_union(cores)) if cores else perim
    cols = []
    for c in fp.column_candidates:
        if c.status != "confirmed":
            continue
        cx, cy = fp.to_m(c.center)
        s = min(max(c.size_px / ppm, column_size_min_m), column_size_max_m)
        cols.append(box(cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2))
    if fp.primary_entrance is None or fp.primary_entrance.status != "confirmed":
        raise ValueError("primary_entrance no confirmado")
    ent = fp.to_m(fp.primary_entrance.point)
    dl = [DaylightEdge(fp.to_m(d.start), fp.to_m(d.end), d.classification, d.daylight_priority) for d in fp.daylight_segments]
    conf = "LOW" if fp.scale.method == "published_area_inferred" else ("HIGH" if fp.scale.meta.status == "confirmed" else "MEDIUM")
    return ShellM(perimeter=perim, usable=usable, core=cores, columns=cols, entrance=ent, daylight=dl, px_per_m=ppm,
                  scale_confidence=conf,
                  source={"case_id": fp.case_id, "unit": fp.unit_label, "scale_method": fp.scale.method,
                          "published_area_m2": fp.published_area_m2, "published_area_kind": fp.published_area_kind,
                          "usable_area_m2": round(usable.area, 1),
                          "column_size_note": f"tamaño de pilar = size_px/px_per_m acotado a [{column_size_min_m},{column_size_max_m}] m. "
                                              f"Los rectángulos detectados miden 1.0–1.5 m a la escala inferida (LOW): se asumen 0.8 m "
                                              f"(pilar típico de oficina de 4 pisos). SUPUESTO registrado; sujeto a confirmación de escala."})
