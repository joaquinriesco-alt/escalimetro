"""E24 §17 — PEDIDO vs ENTREGADO.

`requested` viene del BriefV1 compilado. `delivered` viene de las métricas del layout resuelto. Son dos
fuentes independientes: si el motor entrega otra cosa, la tabla lo muestra en vez de esconderlo."""
from __future__ import annotations

from typing import Dict

from ...brief import room_counts, total_rooms
from ..program_access import open_workstations


def delivery(program: Dict, r) -> Dict:
    req_rooms = room_counts(program)
    got_rooms = {k: int(v) for k, v in (r.metrics["program_completeness"]["rooms"] or {}).items()
                 if k not in ("workstation_cluster", "workstation_row")}
    need = open_workstations(program)
    got_seats = int(str(r.metrics["program_completeness"]["open_seats"]).split("/")[0])
    faltan = {m: req_rooms[m] - got_rooms.get(m, 0) for m in req_rooms if got_rooms.get(m, 0) != req_rooms[m]}
    return {
        "requested": {"open_workstations": need, "rooms": req_rooms, "rooms_total": total_rooms(program),
                      "target_headcount": int(program["target_headcount"])},
        "delivered": {"open_workstations": got_seats, "rooms": got_rooms,
                      "rooms_total": int(sum(got_rooms.values()))},
        "shortfall": {"open_workstations": need - got_seats, "rooms": faltan},
        "complete": bool(r.metrics["program_completeness"]["complete"]),
    }
