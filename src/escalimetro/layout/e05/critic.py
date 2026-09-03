"""E05 — Crítico arquitectónico (capa separada del solver) + RepairSuggestions estructuradas + ranking.

Frontera de proveedores: `CriticProvider` es la interfaz. `RuleBasedCritic` es determinista y corre sobre el
JSON del layout, las métricas E04 y las relaciones espaciales (lo que usa E05). `OpenAIVisionCritic` es el
punto de enchufe para crítica con visión sobre la imagen renderizada: NO hace llamadas en E05 (sin gasto),
sólo define el contrato. El crítico NUNCA cambia coordenadas: devuelve CritiqueReport + RepairSuggestions,
y `to_repair_constraints` las traduce a RepairConstraints para el solver."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Protocol

from shapely.geometry import box

from ..model import Layout
from .cpsolver import RepairConstraints

ASPECTS = ["arrival_sequence", "reception", "client_access_to_rooms", "privacy", "open_office_quality",
           "facade_use", "kitchenette_dining", "lounge_location", "circulation", "residual_spaces",
           "fragmentation", "architectural_plausibility"]


@dataclass
class RepairSuggestion:
    type: str                 # require_adjacent | forbid_on_facade | forbid_in_band | weight | min_seats_on_facade
    args: Dict
    reason: str


@dataclass
class CritiqueReport:
    candidate_id: str
    hard_valid: bool
    scores: Dict[str, float]              # aspecto → 0..1
    verdicts: Dict[str, str]              # aspecto → texto
    architectural_score: float
    broker_showable: bool
    repair_suggestions: List[RepairSuggestion] = field(default_factory=list)
    provider: str = "rule_based"

    def to_dict(self):
        d = asdict(self)
        return d


class CriticProvider(Protocol):
    name: str

    def critique(self, layout: Layout, metrics: Dict, strategy: Dict, render_png: Optional[str] = None) -> CritiqueReport: ...


def _by(layout: Layout, module: str):
    return [p for p in layout.placements if p.module == module]


def _touch(a, b, tol=0.15) -> bool:
    return a.poly.buffer(tol).intersects(b.poly)


class RuleBasedCritic:
    name = "rule_based"

    def critique(self, layout: Layout, metrics: Dict, strategy: Dict, render_png: Optional[str] = None) -> CritiqueReport:
        obj = (layout.scores or {}).get("objectives", {})
        nodes = {n["id"]: n for n in (layout.circulation_graph or {}).get("nodes", [])}
        sc, vd, sugg = {}, {}, []
        hard_valid = not layout.hard_violations
        # 1. llegada
        rec = _by(layout, "reception")
        path = nodes.get(rec[0].id, {}).get("path_m") if rec else None
        if path is None:
            sc["arrival_sequence"] = 0.0; vd["arrival_sequence"] = "sin ruta acceso→recepción"
        else:
            sc["arrival_sequence"] = max(0.0, min(1.0, 1.0 - max(0.0, path - 3.0) / 8.0))
            vd["arrival_sequence"] = f"recepción a {path} m de ruta del acceso"
        # 2. recepción: región pública + frente hacia el pasillo primario
        pub = strategy.get("public_zone", {}).get("region")
        rec_region = (rec[0].meta.get("region") or rec[0].meta.get("band", "").split(":")[0]) if rec else ""
        in_pub = bool(rec) and rec_region == pub
        sc["reception"] = (0.6 if in_pub else 0.0) + (0.4 if (path is not None and path <= 8.0) else 0.0)
        vd["reception"] = ("en la región del acceso" if in_pub else "fuera de la región del acceso") + (f", a {path} m" if path is not None else "")
        # 3. acceso de clientes a salas sin cruzar el open office
        sc["client_access_to_rooms"] = float(obj.get("meeting_accessibility", 0.0))
        vd["client_access_to_rooms"] = f"meeting_accessibility {sc['client_access_to_rooms']:.2f} (rutas acceso→salas junto a puestos)"
        # 4. privacidad
        priv = float(obj.get("privacy_gradient", 0.0))
        near_rec = 0
        for p in _by(layout, "private_office"):
            if rec and _touch(p, rec[0]):
                near_rec += 1
        sc["privacy"] = max(0.0, priv - 0.15 * near_rec)
        vd["privacy"] = f"gradiente {priv:.2f}; {near_rec} privados pegados a recepción"
        # 5. calidad del open office: benches (no filas sueltas) y luz
        seats = [p for p in layout.placements if p.module.startswith("workstation")]
        n_seats = sum(p.seats for p in seats) or 1
        bench_frac = sum(p.seats for p in seats if p.module == "workstation_cluster") / n_seats
        day = float(obj.get("daylight_utilization", 0.0))
        sc["open_office_quality"] = 0.5 * bench_frac + 0.5 * day
        vd["open_office_quality"] = f"{bench_frac:.0%} de puestos en benches; daylight {day:.2f}"
        if day < 0.5:
            sugg.append(RepairSuggestion("min_seats_on_facade", {"seats": int(0.6 * n_seats)}, f"daylight {day:.2f} < 0.5"))
        # 6. fachada
        fac = float(obj.get("facade_preservation", 0.0))
        sc["facade_use"] = fac
        vd["facade_use"] = (layout.scores or {}).get("detail", {}).get("facade_preservation", "")
        if fac < 0.5:
            sugg.append(RepairSuggestion("forbid_on_facade", {"module": "private_office"}, "privados consumen fachada"))
        # 7. kitchenette / comedor
        k, d = _by(layout, "kitchenette"), _by(layout, "dining")
        if k and d:
            if _touch(k[0], d[0]):
                sc["kitchenette_dining"] = 1.0; vd["kitchenette_dining"] = "adyacentes"
            elif (k[0].meta.get("band") or k[0].meta.get("region")) == (d[0].meta.get("band") or d[0].meta.get("region")) and k[0].poly.distance(d[0].poly) <= 2.0:
                sc["kitchenette_dining"] = 0.5; vd["kitchenette_dining"] = f"misma zona, separados {k[0].poly.distance(d[0].poly):.1f} m (pasillo entre medio)"
            else:
                sc["kitchenette_dining"] = 0.0; vd["kitchenette_dining"] = "separados"
                sugg.append(RepairSuggestion("require_adjacent", {"a": k[0].id, "b": d[0].id}, "kitchenette y comedor separados"))
        else:
            sc["kitchenette_dining"] = 0.0; vd["kitchenette_dining"] = "falta kitchenette o comedor"
        # 8. lounge
        lg = _by(layout, "lounge")
        if lg:
            near_ws = any(_touch(lg[0], p, 1.5) for p in seats)
            detail = (layout.scores or {}).get("detail", {}).get("adjacency_quality", "")
            sc["lounge_location"] = 0.5 * near_ws + 0.5 * (1.0 if "lounge con luz=0.6" in detail or "lounge con luz=0.7" in detail or "lounge con luz=0.8" in detail or "lounge con luz=0.9" in detail or "lounge con luz=1" in detail else 0.3)
            vd["lounge_location"] = ("junto a puestos" if near_ws else "lejos de puestos")
        else:
            sc["lounge_location"] = 0.0; vd["lounge_location"] = "sin lounge"
        # 9. circulación
        circ = float(obj.get("circulation_efficiency", 0.0))
        spine = (layout.zones or {}).get("spine", {})
        n_conn = len(spine.get("connectors", []))
        sc["circulation"] = max(0.0, circ - 0.05 * max(0, n_conn - 3))
        vd["circulation"] = f"eficiencia {circ:.2f}; {n_conn} conectores; pasillos {metrics.get('circulation_area_m2')} m²"
        # 10. residuales
        sc["residual_spaces"] = float(obj.get("wasted_space", 0.0))
        vd["residual_spaces"] = f"{metrics.get('wasted_area_m2')} m² en bolsillos; {metrics.get('unallocated_area_m2')} m² sin asignar"
        # 11. fragmentación: puestos repartidos en muchas bandas / bloques chicos
        bands_desks = {p.meta.get("band") or p.meta.get("region") for p in seats}
        small = sum(1 for p in seats if p.seats <= 3)
        sc["fragmentation"] = max(0.0, 1.0 - 0.1 * max(0, len(bands_desks) - 3) - 0.08 * small)
        vd["fragmentation"] = f"puestos en {len(bands_desks)} bandas; {small} bloques de ≤ 3 puestos"
        if small >= 3:
            sugg.append(RepairSuggestion("weight", {"objective": "compactness", "value": 0.16}, "muchos bloques chicos"))
        # 12. plausibilidad = media geométrica suave de lo anterior, castigada por invalidez
        vals = [sc[a] for a in ASPECTS if a in sc]
        plaus = sum(vals) / len(vals)
        if not hard_valid:
            plaus *= 0.5
        sc["architectural_plausibility"] = plaus
        vd["architectural_plausibility"] = ("candidato inválido: " if not hard_valid else "") + f"media de aspectos {plaus:.2f}"
        arch = sum(sc[a] for a in ASPECTS) / len(ASPECTS)
        showable = hard_valid and arch >= 0.6 and sc["reception"] >= 0.8 and sc["open_office_quality"] >= 0.5
        return CritiqueReport(layout.layout_id, hard_valid, {k: round(v, 3) for k, v in sc.items()}, vd, round(arch, 3),
                              showable, sugg, self.name)


class OpenAIVisionCritic:
    """Punto de enchufe (NO usado en E05): crítica con visión sobre la lámina renderizada. Contrato = mismo
    CritiqueReport. Sin llamadas pagadas hasta que se active explícitamente."""
    name = "openai_vision"

    def __init__(self, model: str = "gpt-4o", enabled: bool = False):
        self.model, self.enabled = model, enabled

    def critique(self, layout: Layout, metrics: Dict, strategy: Dict, render_png: Optional[str] = None) -> CritiqueReport:
        if not self.enabled:
            raise RuntimeError("OpenAIVisionCritic deshabilitado en E05 (sin llamadas pagadas). Usar RuleBasedCritic.")
        raise NotImplementedError("Integración OpenAI pendiente: enviar render_png + layout JSON, parsear CritiqueReport.")


def to_repair_constraints(report: CritiqueReport, max_items: int = 3) -> RepairConstraints:
    rc = RepairConstraints()
    for s in report.repair_suggestions[:max_items]:
        if s.type == "require_adjacent":
            rc.require_adjacent.append((s.args["a"], s.args["b"]))
        elif s.type == "forbid_on_facade":
            rc.forbid_module_on_facade.append(s.args["module"])
        elif s.type == "forbid_in_band":
            rc.forbid_module_in_band.append((s.args["module"], s.args["band"]))
        elif s.type == "weight":
            rc.weight_overrides[s.args["objective"]] = float(s.args["value"])
        elif s.type == "min_seats_on_facade":
            rc.min_seats_on_facade = int(s.args["seats"])
        rc.notes.append(f"{s.type}: {s.reason}")
    return rc


def rank(cands: List[Dict]) -> List[Dict]:
    """A. HARD VALIDITY (binario) — B. score geométrico (E04) — C. score arquitectónico (crítico) —
    D. total = 0.5·B + 0.5·C. Un candidato con hard_valid=false NUNCA gana: queda fuera del ranking."""
    valid = [c for c in cands if c["hard_valid"]]
    for c in cands:
        g, a = c.get("geometric_score") or 0.0, c.get("architectural_score") or 0.0
        c["total_score"] = round(0.5 * g + 0.5 * a, 4) if c["hard_valid"] else None
    valid.sort(key=lambda c: -c["total_score"])
    return valid
