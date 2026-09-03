"""E08 — garantía técnica de inmutabilidad geométrica.

`geometry_locked = true` deja de ser una convención escrita en un JSON y pasa a ser una comprobación:
se calcula un hash canónico de la geometría ANTES y DESPUÉS de cada llamada a IA. Si difieren, la corrida
falla. La IA nunca recibe objetos mutables del motor, pero eso no se asume: se verifica."""
from __future__ import annotations

import hashlib
import json
from typing import Dict, Optional

from ..layout.model import Layout, ShellM


def _r(v, n: int = 4):
    return round(float(v), n)


def canonical_geometry(layout: Layout, shell: Optional[ShellM] = None) -> Dict:
    """Representación canónica y ordenada de TODA la geometría que el producto considera intocable:
    shell, recintos, puestos, mobiliario, puertas, pilares y circulación."""
    placements = []
    for p in sorted(layout.placements, key=lambda p: p.id):
        placements.append({
            "id": p.id, "module": p.module, "rot": int(p.rot), "seats": int(p.seats or 0),
            "rect": [_r(p.x), _r(p.y), _r(p.w), _r(p.d)],
            "door": [_r(p.door[0]), _r(p.door[1])] if p.door else None,
            "desks": sorted([[_r(a), _r(b), _r(c), _r(e)] for a, b, c, e in (p.desks or [])]),
        })
    zones = layout.zones or {}
    geo = {
        "placements": placements,
        "shell_perimeter": [[_r(x), _r(y)] for x, y in zones.get("shell_perimeter", [])],
        "shell_core": zones.get("shell_core", []),
        "shell_columns": zones.get("shell_columns", []),
        "shell_entrance": zones.get("shell_entrance"),
        "scale_px_per_m": zones.get("scale_px_per_m"),
        "circulation_nodes": sorted([[n["id"], _r(n["xy"][0]), _r(n["xy"][1])]
                                     for n in (layout.circulation_graph or {}).get("nodes", [])]),
        "circulation_cells": sorted(map(list, layout.circulation_cells or [])),
    }
    if shell is not None:
        geo["shell_usable_wkt"] = shell.usable.wkt
    return geo


def geometry_hash(layout: Layout, shell: Optional[ShellM] = None) -> str:
    blob = json.dumps(canonical_geometry(layout, shell), sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class GeometryMutated(Exception):
    """La geometría cambió alrededor de una llamada a IA. Es un fallo duro, no una advertencia."""


class GeometryGuard:
    """Context manager: hashea al entrar, hashea al salir, falla si no coinciden."""

    def __init__(self, layout: Layout, shell: Optional[ShellM] = None, what: str = "ai_call"):
        self.layout, self.shell, self.what = layout, shell, what
        self.before: str = ""
        self.after: str = ""

    def __enter__(self):
        self.before = geometry_hash(self.layout, self.shell)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.after = geometry_hash(self.layout, self.shell)
        if self.before != self.after:
            raise GeometryMutated(f"{self.what}: geometry_hash_before != geometry_hash_after "
                                  f"({self.before[:12]}… != {self.after[:12]}…)")
        return False

    def to_dict(self) -> Dict:
        return {"what": self.what, "geometry_hash_before": self.before, "geometry_hash_after": self.after,
                "identical": self.before == self.after}
