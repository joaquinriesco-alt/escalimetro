"""E05 — SpatialStrategy: intención arquitectónica estructurada, SIN coordenadas de mobiliario.

Una estrategia dice QUÉ va DÓNDE a nivel de regiones y bandas (fachada / interior), qué relaciones se
prefieren o prohíben, qué fachada es premium y cómo se ordena la llegada. El solver geométrico (cpsolver)
convierte esto en coordenadas; el validador determinista (E04) las verifica.

Las 8 familias se generan desde ROLES derivados de los rasgos del shell (región del acceso, región con más
fachada, región profunda, etc.), no desde coordenadas del caso: el mismo generador corre sobre otro shell.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .features import ShellFeatures, Region

# patrones de sección (de la fachada / lado de referencia hacia adentro). 'work' = puestos, 'rooms' = recintos,
# 'corr' = pasillo, 'mixed' = banda donde el solver decide (puestos o recintos), 'support' = booths/kitchenette
PATTERNS = {
    "work_first": ["work", "corr", "mixed"],
    "rooms_first": ["rooms", "corr", "mixed"],
    "work_only": ["work", "corr", "work"],
    "rooms_only": ["rooms", "corr", "rooms"],
    "deep_work_first": ["work", "corr", "rooms", "corr", "mixed"],
    "deep_rooms_first": ["rooms", "corr", "rooms", "corr", "mixed"],
    "mixed_first": ["mixed", "corr", "mixed"],            # el solver decide por tramo: puestos o recintos
    "deep_mixed_first": ["mixed", "corr", "rooms", "corr", "mixed"],
    "corr_first": ["corr", "mixed"],          # región angosta con el acceso en el lado largo
}

ROOM_MODULES = ["boardroom_12", "meeting_8", "meeting_4", "private_office", "reception", "kitchenette", "dining",
                "lounge", "phone_booth"]
CLIENT_ROOMS = ["boardroom_12", "meeting_8", "meeting_4"]
SUPPORT_ROOMS = ["kitchenette", "dining", "phone_booth"]


@dataclass
class SpatialStrategy:
    strategy_id: str
    family: str
    description: str
    public_zone: Dict                       # {"region": rid, "anchor": "entrance"}
    client_meeting_zone: Dict               # {"regions": [rid], "modules": [...]}
    work_neighborhoods: List[Dict]          # [{"name", "regions": [rid], "facade_band": "work"|"rooms", "target_seats"}]
    support_zone: Dict                      # {"regions": [rid], "modules": [...]}
    premium_daylight_edges: List[str]       # ids de aristas con luz que se consideran premium
    circulation_spine: Dict                 # {"primary_width_m", "secondary_width_m", "pattern_by_region": {rid: pattern}}
    room_clusters: List[List[str]]          # módulos que deben ir juntos (mismo slot / adyacentes)
    forbidden_relationships: List[Dict]     # [{"a", "b", "relation"}]
    preferred_relationships: List[Dict]     # [{"a", "b", "relation", "weight"}]
    facade_allocation_targets: Dict         # {"open_work_min": 0.6, "closed_rooms_max": 0.4}
    entrance_sequence: List[str]
    module_regions: Dict[str, List[str]]    # módulo → regiones permitidas (blando: penalización si se viola)
    bench_preference: List[int] = field(default_factory=lambda: [6, 5, 4, 3, 2])
    objective_weights: Dict[str, float] = field(default_factory=dict)
    preflight: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    def save(self, path: str) -> None:
        json.dump(self.to_dict(), open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Dict) -> "SpatialStrategy":
        return cls(**d)


SCHEMA = {
    "type": "object",
    "required": ["strategy_id", "family", "description", "public_zone", "client_meeting_zone", "work_neighborhoods",
                 "support_zone", "premium_daylight_edges", "circulation_spine", "room_clusters",
                 "forbidden_relationships", "preferred_relationships", "facade_allocation_targets",
                 "entrance_sequence", "module_regions"],
    "properties": {
        "strategy_id": {"type": "string"}, "family": {"type": "string"}, "description": {"type": "string"},
        "public_zone": {"type": "object", "required": ["region", "anchor"]},
        "client_meeting_zone": {"type": "object", "required": ["regions", "modules"]},
        "work_neighborhoods": {"type": "array", "minItems": 1,
                               "items": {"type": "object", "required": ["name", "regions", "facade_band", "target_seats"]}},
        "support_zone": {"type": "object", "required": ["regions", "modules"]},
        "premium_daylight_edges": {"type": "array", "items": {"type": "string"}},
        "circulation_spine": {"type": "object", "required": ["primary_width_m", "secondary_width_m", "pattern_by_region"]},
        "room_clusters": {"type": "array"},
        "forbidden_relationships": {"type": "array", "items": {"type": "object", "required": ["a", "b", "relation"]}},
        "preferred_relationships": {"type": "array", "items": {"type": "object", "required": ["a", "b", "relation", "weight"]}},
        "facade_allocation_targets": {"type": "object"},
        "entrance_sequence": {"type": "array", "items": {"type": "string"}},
        "module_regions": {"type": "object"},
    },
    "additionalProperties": True,
}


def _roles(f: ShellFeatures) -> Dict[str, object]:
    ent = f.region(f.entrance_region)
    others = [r for r in f.regions if r.id != ent.id]
    by_facade = sorted(f.regions, key=lambda r: -r.facade_len_m)
    fac_others = sorted(others, key=lambda r: -r.facade_len_m)
    deep = sorted(f.regions, key=lambda r: -r.depth_m)
    near = sorted(others, key=lambda r: r.entrance_path_m)
    return {"ent": ent, "others": others, "fac1": fac_others[0] if fac_others else ent,
            "fac2": fac_others[1] if len(fac_others) > 1 else (fac_others[0] if fac_others else ent),
            "deep": deep[0], "near": near[0] if near else ent, "far": near[-1] if near else ent,
            "all": [r.id for r in f.regions], "premium": [e.id for e in f.daylight_edges if e.priority >= 0.75]}


def _pattern_for(r: Region, facade_kind: str, deep_interior: str = "mixed") -> str:
    """Patrón de sección según geometría de la región y la intención (qué va en la fachada)."""
    short_facade = r.length_m < 0.7 * r.depth_m       # fachada en el lado corto (ala angosta)
    if short_facade or not r.facade_side:
        return "corr_first"                            # ala angosta: pasillo desde el lado largo del acceso, una banda
    if facade_kind == "corridor":
        return "corr_first"                            # pasillo perimetral: todo el programa en la banda interior
    if r.depth_m >= 11.0:
        return {"work": "deep_work_first", "rooms": "deep_rooms_first"}.get(facade_kind, "deep_mixed_first")
    return {"work": "work_first", "rooms": "rooms_first"}.get(facade_kind, "mixed_first")


def _base(f: ShellFeatures, R: Dict, sid: str, family: str, desc: str, facade_kind: Dict[str, str],
          client_regions: List[str], support_regions: List[str], work_regions: List[str],
          seats_total: int,
          extra_forbidden=None, extra_preferred=None, weights=None, bench=None) -> SpatialStrategy:
    ent = R["ent"]
    pat = {r.id: _pattern_for(r, facade_kind.get(r.id, "mixed")) for r in f.regions}
    module_regions = {
        "reception": [ent.id],                              # duro además en el solver: ≤ 8 m de ruta
        "boardroom_12": client_regions, "meeting_8": client_regions, "meeting_4": client_regions,
        "private_office": work_regions, "workstation": work_regions,
        "kitchenette": support_regions, "dining": support_regions, "phone_booth": support_regions + work_regions,
        "lounge": work_regions + support_regions,
    }
    # E24 §6 — los puestos vienen del BriefV1 (open_workstations). Antes había un 40 escrito aquí.
    seats_total = int(seats_total)
    neigh = []
    for k, rid in enumerate(work_regions):
        neigh.append({"name": f"barrio_{rid}", "regions": [rid], "facade_band": facade_kind.get(rid, "work"),
                      "target_seats": round(seats_total * f.region(rid).area_m2 / sum(f.region(x).area_m2 for x in work_regions))})
    forbidden = [{"a": "kitchenette", "b": "reception", "relation": "adjacent"},
                 {"a": "dining", "b": "reception", "relation": "adjacent"}] + (extra_forbidden or [])
    preferred = [{"a": "kitchenette", "b": "dining", "relation": "adjacent", "weight": 1.0},
                 {"a": "reception", "b": "meeting_4", "relation": "near", "weight": 0.5},
                 {"a": "boardroom_12", "b": "meeting_8", "relation": "adjacent", "weight": 0.5},
                 {"a": "lounge", "b": "workstation", "relation": "near", "weight": 0.5},
                 {"a": "phone_booth", "b": "workstation", "relation": "near", "weight": 0.3}] + (extra_preferred or [])
    return SpatialStrategy(
        strategy_id=sid, family=family, description=desc,
        public_zone={"region": ent.id, "anchor": "entrance"},
        client_meeting_zone={"regions": client_regions, "modules": CLIENT_ROOMS},
        work_neighborhoods=neigh,
        support_zone={"regions": support_regions, "modules": SUPPORT_ROOMS},
        premium_daylight_edges=R["premium"],
        circulation_spine={"primary_width_m": 1.5, "secondary_width_m": 1.2, "pattern_by_region": pat},
        room_clusters=[["kitchenette", "dining"], ["boardroom_12", "meeting_8"]],
        forbidden_relationships=forbidden, preferred_relationships=preferred,
        facade_allocation_targets={"open_work_min": 0.6, "closed_rooms_max": 0.4},
        entrance_sequence=["entrance", "reception", "client_meeting_zone", "work_neighborhoods", "support_zone"],
        module_regions=module_regions, bench_preference=bench or [6, 5, 4, 3, 2],
        objective_weights=weights or {})


def generate_strategies(f: ShellFeatures, open_workstations: int) -> List[SpatialStrategy]:
    """9 familias conceptualmente distintas, derivadas de roles. Determinista.

    `open_workstations` es el dato del brief (E24 §4): reparte los puestos entre los barrios de cada
    familia en proporción al área de sus regiones. No hay ningún total escrito a mano."""
    R = _roles(f)
    ent, fac1, fac2, deep, near, far = R["ent"], R["fac1"], R["fac2"], R["deep"], R["near"], R["far"]
    all_ids = R["all"]
    others = [r.id for r in R["others"]]
    out = []
    # A. PERIMETER WORK: puestos en toda fachada; recintos interiores; cliente cerca del acceso (interior)
    out.append(_base(f, R, "A_PERIMETER_WORK", "PERIMETER_WORK",
                     "Open office en toda la fachada iluminada; salas y soporte en bandas interiores; cliente junto al acceso.",
                     {rid: "mixed" for rid in all_ids}, client_regions=[ent.id, near.id, deep.id],
                     support_regions=[far.id, deep.id], seats_total=open_workstations, work_regions=all_ids,
                     weights={"daylight_utilization": 0.26, "facade_preservation": 0.14}))
    # B. CLIENT FRONT: recepción + directorio + salas principales en la región del acceso (fachada incluida)
    out.append(_base(f, R, "B_CLIENT_FRONT", "CLIENT_FRONT",
                     "Frente de cliente: recepción, directorio y salas principales en la región del acceso; trabajo en el resto.",
                     {**{rid: "mixed" for rid in all_ids}, ent.id: "rooms", deep.id: "rooms"},
                     client_regions=[ent.id, deep.id], support_regions=[far.id], seats_total=open_workstations, work_regions=others,
                     weights={"entrance_logic": 0.18, "meeting_accessibility": 0.14}))
    # C. DUAL NEIGHBORHOOD: dos barrios de trabajo (las dos regiones con más fachada) unidos por la espina
    out.append(_base(f, R, "C_DUAL_NEIGHBORHOOD", "DUAL_NEIGHBORHOOD",
                     "Dos barrios de trabajo en las dos regiones con más fachada, conectados por circulación central; cliente en el acceso.",
                     {fac1.id: "mixed", fac2.id: "mixed", ent.id: "rooms"}, client_regions=[ent.id, near.id],
                     support_regions=[x for x in all_ids if x not in (fac1.id, fac2.id)] or [far.id],
                     seats_total=open_workstations, work_regions=[fac1.id, fac2.id], weights={"adjacency_quality": 0.18}))
    # D. CENTRAL MEETING HUB: salas agrupadas en bandas interiores junto al núcleo/acceso; trabajo alrededor
    out.append(_base(f, R, "D_CENTRAL_MEETING_HUB", "CENTRAL_MEETING_HUB",
                     "Hub de salas en la banda interior (junto al núcleo) de la región con más fachada, con pasillo perimetral; open office en el resto.",
                     {**{rid: "mixed" for rid in all_ids}, fac1.id: "corridor"}, client_regions=[ent.id, near.id, fac1.id],
                     support_regions=[far.id], seats_total=open_workstations, work_regions=all_ids,
                     extra_preferred=[{"a": "meeting_4", "b": "meeting_8", "relation": "adjacent", "weight": 0.8}],
                     weights={"meeting_accessibility": 0.16, "adjacency_quality": 0.16}))
    # E. DAYLIGHT MAX: sólo puestos en fachada; privados interiores; benches largos
    out.append(_base(f, R, "E_DAYLIGHT_MAX", "DAYLIGHT_MAX",
                     "Maximizar puestos con fachada: benches largos en toda fachada, privados y salas interiores.",
                     {rid: "work" for rid in all_ids}, client_regions=[deep.id, ent.id],
                     support_regions=[far.id, deep.id], seats_total=open_workstations, work_regions=all_ids,
                     extra_forbidden=[{"a": "private_office", "b": "facade", "relation": "on_facade"}],
                     weights={"daylight_utilization": 0.32, "facade_preservation": 0.14}, bench=[6, 5, 4]))
    # F. COMPACT ROOMS: recintos cerrados concentrados en la región profunda + acceso; open office continuo
    out.append(_base(f, R, "F_COMPACT_ROOMS", "COMPACT_ROOMS",
                     "Recintos cerrados concentrados en bandas interiores hondas (pasillo perimetral en las dos regiones con más fachada) y en la región profunda; open office continuo en lo que queda.",
                     {**{rid: "mixed" for rid in all_ids}, deep.id: "rooms", fac1.id: "corridor", fac2.id: "corridor"},
                     client_regions=[deep.id, ent.id, fac1.id], support_regions=[deep.id, fac2.id],
                     seats_total=open_workstations, work_regions=[x for x in all_ids if x != deep.id], weights={"compactness": 0.16, "wasted_space": 0.12}))
    # G. <ENT> PUBLIC / <FAC1> WORK: usa explícitamente la posición real del acceso
    out.append(_base(f, R, f"G_{ent.id}_PUBLIC_{fac1.id}_WORK", "ENTRANCE_PUBLIC_FACADE_WORK",
                     f"Región del acceso ({ent.id}) = público + salas; región con más fachada ({fac1.id}) = trabajo; soporte en la más lejana ({far.id}).",
                     {**{rid: "mixed" for rid in all_ids}, ent.id: "rooms"}, client_regions=[ent.id, near.id],
                     support_regions=[far.id], seats_total=open_workstations, work_regions=[fac1.id, fac2.id, deep.id],
                     weights={"entrance_logic": 0.16, "daylight_utilization": 0.24}))
    # H. WORK (fachadas lejanas) + CLIENT (acceso): separación clara cliente / interno; privados con el trabajo
    out.append(_base(f, R, "H_WORK_FAR_CLIENT_ENTRANCE", "SPLIT_CLIENT_WORK",
                     "Separación cliente/interno: todo lo de cliente (recepción, directorio, salas) en la región del acceso y su vecina; trabajo y soporte en las fachadas lejanas.",
                     {**{rid: "mixed" for rid in all_ids}, ent.id: "rooms", near.id: "rooms"},
                     client_regions=[ent.id, near.id], support_regions=[far.id],
                     seats_total=open_workstations, work_regions=[x for x in all_ids if x not in (ent.id,)],
                     extra_forbidden=[{"a": "client_meeting_zone", "b": "work_neighborhoods", "relation": "through_traffic"}],
                     weights={"privacy_gradient": 0.16, "meeting_accessibility": 0.14}))
    # I. PERIMETER CORRIDOR: pasillo perimetral pegado a la línea de pilares en toda fachada larga; todo el
    #    programa en bandas interiores hondas (la respuesta a una línea de pilares a ~4 m de la fachada)
    out.append(_base(f, R, "I_PERIMETER_CORRIDOR", "PERIMETER_CORRIDOR",
                     "Pasillo perimetral junto a la fachada (antes de la línea de pilares) en todas las regiones con fachada larga; recintos y benches en una única banda interior honda.",
                     {**{rid: "corridor" for rid in all_ids if f.region(rid).facade_side and f.region(rid).length_m >= 0.7 * f.region(rid).depth_m and f.region(rid).depth_m < 11.0},
                      **{rid: "mixed" for rid in all_ids if f.region(rid).depth_m >= 11.0}},
                     client_regions=[ent.id, fac1.id], support_regions=[far.id, deep.id], seats_total=open_workstations, work_regions=all_ids,
                     weights={"wasted_space": 0.12, "daylight_utilization": 0.22}))
    return out
