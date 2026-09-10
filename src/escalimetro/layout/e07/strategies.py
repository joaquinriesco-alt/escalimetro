"""E07 — A EFICIENTE / B BALANCEADO / C COLABORATIVO.

Mismo shell, mismo programa, misma biblioteca, mismas restricciones duras. Lo que cambia es la INTENCIÓN de
space planning, expresada en tres capas encadenadas:

  1. SpatialGraph   — qué debe estar cerca de qué, qué ruta es de cliente, dónde va la luz.
  2. spine          — qué estrategia de circulación de E05 instancia la espina (patrón por región).
  3. solver_extra   — cómo el grafo se convierte en restricciones duras adicionales y pesos del objetivo.

Ninguna alternativa toca el brief: las tres resuelven EXACTAMENTE el mismo programa del cliente.
E24 §7: la partición del open space en barrios ya no es una tabla escrita a mano por alternativa; es
una PROPORCIÓN declarada en DesignPolicyV1 y repartida en enteros exactos sobre `open_workstations`."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List

from ...brief import DEFAULT_POLICY, DesignPolicyV1, apportion
from .graph import GraphEdge, SpatialGraph, program_nodes


@dataclass
class AlternativeSpec:
    alt: str                       # A | B | C
    name: str                      # EFICIENTE | BALANCEADO | COLABORATIVO
    intent: str                    # una línea, lenguaje de producto
    copy_short: str                # copy comercial (2 líneas máx)
    strengths: List[str]
    ideal_for: str
    spine_strategy: str            # id de estrategia E05 que instancia la espina
    bench_cfgs: List[int]
    weights: Dict[str, float]      # override de objectives_weights
    solver_extra: Dict             # restricciones/pesos adicionales del motor
    graph: SpatialGraph

    def to_dict(self):
        d = asdict(self); d["graph"] = self.graph.to_dict(); return d


def _edges(common: List[GraphEdge], extra: List[GraphEdge]) -> List[GraphEdge]:
    return common + extra


def _common_edges() -> List[GraphEdge]:
    """Principios comunes a A/B/C (§10 del brief E07): acceso, luz, circulación, adyacencias, privacidad."""
    return [
        GraphEdge("reception", "entrance", "entrance_priority", 1.0, hard=True, note="recepción ≤ 8 m de ruta del acceso"),
        GraphEdge("reception", "boardroom_12", "client_route", 0.8, note="el cliente llega al directorio desde recepción"),
        GraphEdge("reception", "meeting_8", "client_route", 0.8),
        GraphEdge("reception", "meeting_4", "client_route", 0.5),
        GraphEdge("kitchenette", "dining", "shared_support", 1.0, note="cocina y comedor deben tener relación directa"),
        GraphEdge("kitchenette", "reception", "prefer_far", 0.6),
        GraphEdge("phone_booth", "open_work_neighborhood_1", "prefer_near", 0.5),
        GraphEdge("phone_booth", "core", "acoustic_separation", 0.4, note="cabinas interiores, separadas del open"),
        GraphEdge("open_work_neighborhood_1", "facade_premium", "daylight_preference", 1.0),
        GraphEdge("private_office", "facade_premium", "daylight_preference", 0.5, note="pueden usar fachada, sin consumirla toda"),
        GraphEdge("reception", "open_work_neighborhood_1", "privacy_gradient", 0.7, note="public → semi-public → work → support"),
        GraphEdge("dining", "circulation", "must_connect", 1.0, hard=True),
    ]


def neighborhood_split(program: Dict, alt: str, policy: DesignPolicyV1 = DEFAULT_POLICY) -> List[int]:
    """§7 — puestos por barrio de trabajo de UNA alternativa, derivados del brief.

    Sin tablas por tamaño: proporción declarada × open_workstations, reparto por mayor resto, suma
    exacta. Con 40 puestos reproduce la intención histórica (A [24,16] · B [16,14,10] · C [12,10,10,8]).
    Los barrios que quedarían en 0 puestos no se instancian."""
    need = int(program["open_workstations_exact"])
    return [s for s in apportion(need, policy.proportions_for(alt)) if s > 0]


def build_alternatives(program: Dict, policy: DesignPolicyV1 = DEFAULT_POLICY) -> List[AlternativeSpec]:
    """Determinista: mismas entradas → mismas tres especificaciones."""
    common = _common_edges()
    sp = {alt: neighborhood_split(program, alt, policy) for alt in ("A", "B", "C")}

    # ---------- A — EFICIENTE ----------------------------------------------------------------------
    gA = SpatialGraph(
        "A_EFICIENTE",
        "Máxima eficiencia espacial: recintos agrupados en pocos bloques, circulación mínima y legible, "
        "open office compacto en pocos barrios grandes.",
        program_nodes(program, len(sp["A"]), sp["A"]),
        _edges(common, [
            GraphEdge("boardroom_12", "meeting_8", "prefer_near", 1.0, note="salas agrupadas en un solo bloque"),
            GraphEdge("meeting_8", "meeting_4", "prefer_near", 1.0),
            GraphEdge("private_office", "private_office", "prefer_near", 0.8, note="privados agrupados, un solo frente"),
            GraphEdge("open_work_neighborhood_1", "open_work_neighborhood_2", "prefer_near", 0.8),
            GraphEdge("lounge", "open_work_neighborhood_1", "prefer_near", 0.3),
        ]),
        {"space_efficiency": 1.0, "circulation_efficiency": 1.0, "compactness": 0.9, "open_work_daylight": 0.7,
         "low_residual": 0.9, "facade_preservation": 0.8, "collaboration": 0.2, "client_experience": 0.4},
    )
    A = AlternativeSpec(
        "A", "EFICIENTE",
        "La forma más eficiente de hacer funcionar el programa completo.",
        "Máxima eficiencia espacial con circulación compacta y alto aprovechamiento del área útil.",
        ["Menor superficie de circulación", "Recintos agrupados en pocos bloques", "Menor fragmentación del open office",
         "Fachada liberada para puestos"],
        "Empresas que priorizan costo por puesto y operación simple.",
        spine_strategy="A_PERIMETER_WORK",
        bench_cfgs=[6, 5, 4],
        weights={"circulation_efficiency": 0.18, "compactness": 0.14, "wasted_space": 0.12, "daylight_utilization": 0.24,
                 "facade_preservation": 0.14, "adjacency_quality": 0.07, "entrance_logic": 0.07,
                 "meeting_accessibility": 0.03, "privacy_gradient": 0.01},
        solver_extra={"max_bench_blocks": 7, "row_penalty_per_seat": 0.05, "branch_cost_scale": 3.0,
                      "max_facade_closed_rooms": 5, "hard_adjacent_pairs": [("kitchenette", "dining")],
                      "module_max_path": {"boardroom_12": 16.0},
                      "pair_bonus": [("boardroom_12", "meeting_8", 0.6), ("meeting_8", "meeting_4", 0.5),
                                     ("meeting_4", "meeting_4", 0.5), ("private_office", "private_office", 0.5),
                                     ("kitchenette", "dining", 0.6)]},
        graph=gA)

    # ---------- B — BALANCEADO ---------------------------------------------------------------------
    gB = SpatialGraph(
        "B_BALANCEADO",
        "Equilibrio entre llegada, salas, trabajo y luz: frente de cliente completo junto al acceso, "
        "puestos en la mejor fachada y soporte al fondo.",
        program_nodes(program, len(sp["B"]), sp["B"]),
        _edges(common, [
            GraphEdge("boardroom_12", "entrance", "client_route", 1.0, hard=True,
                      note="corrige E06: el directorio quedaba a 31 m del acceso"),
            GraphEdge("meeting_8", "reception", "prefer_near", 0.9),
            GraphEdge("private_office", "facade_premium", "prefer_far", 0.6,
                      note="corrige E06: 48 % de fachada premium con recintos cerrados"),
            GraphEdge("open_work_neighborhood_1", "facade_premium", "daylight_preference", 1.0),
            GraphEdge("lounge", "open_work_neighborhood_2", "prefer_near", 0.7),
            GraphEdge("dining", "kitchenette", "prefer_near", 1.0, hard=True, note="corrige E06: quedaban separados"),
        ]),
        {"space_efficiency": 0.6, "circulation_efficiency": 0.7, "compactness": 0.6, "open_work_daylight": 0.9,
         "low_residual": 0.6, "facade_preservation": 0.9, "collaboration": 0.6, "client_experience": 0.9},
    )
    B = AlternativeSpec(
        "B", "BALANCEADO",
        "El mejor equilibrio entre trabajo, reuniones y experiencia de cliente.",
        "Equilibrio entre puestos, salas, experiencia de trabajo y relación con clientes.",
        ["Directorio y salas junto al acceso", "Puestos en la mejor fachada", "Cocina y comedor integrados",
         "Recorrido de cliente sin cruzar el open office"],
        "Empresas que reciben clientes con frecuencia y quieren buen estándar de trabajo.",
        spine_strategy="B_CLIENT_FRONT",
        bench_cfgs=[6, 4, 3],
        weights={"daylight_utilization": 0.20, "entrance_logic": 0.14, "meeting_accessibility": 0.14,
                 "adjacency_quality": 0.14, "facade_preservation": 0.12, "circulation_efficiency": 0.10,
                 "privacy_gradient": 0.06, "compactness": 0.05, "wasted_space": 0.05},
        solver_extra={"module_max_path": {"boardroom_12": 14.0},
                      "max_facade_closed_rooms": 4, "row_penalty_per_seat": 0.06,
                      "hard_adjacent_pairs": [("kitchenette", "dining")],
                      "pair_bonus": [("kitchenette", "dining", 1.0), ("boardroom_12", "meeting_8", 0.4),
                                     ("lounge", "meeting_4", 0.2)]},
        graph=gB)

    # ---------- C — COLABORATIVO -------------------------------------------------------------------
    gC = SpatialGraph(
        "C_COLABORATIVO",
        "Interacción: hub de salas y lounge en el centro de la planta, cuatro barrios de trabajo pequeños "
        "alrededor y circulación que los cose.",
        program_nodes(program, len(sp["C"]), sp["C"]),
        _edges(common, [
            GraphEdge("lounge", "circulation", "prefer_near", 1.0, note="el lounge es parte del recorrido, no un rincón"),
            GraphEdge("lounge", "open_work_neighborhood_1", "prefer_near", 1.0),
            GraphEdge("lounge", "open_work_neighborhood_2", "prefer_near", 1.0),
            GraphEdge("meeting_4", "open_work_neighborhood_1", "prefer_near", 0.8, note="hub de salas junto al trabajo"),
            GraphEdge("meeting_4", "meeting_8", "prefer_near", 0.8),
            GraphEdge("dining", "lounge", "prefer_near", 0.8, note="comedor y lounge como zona de encuentro"),
            GraphEdge("open_work_neighborhood_3", "facade_premium", "daylight_preference", 1.0),
            GraphEdge("open_work_neighborhood_4", "facade_premium", "daylight_preference", 1.0),
        ]),
        {"space_efficiency": 0.5, "circulation_efficiency": 0.5, "compactness": 0.4, "open_work_daylight": 0.9,
         "low_residual": 0.5, "facade_preservation": 0.7, "collaboration": 1.0, "client_experience": 0.7},
    )
    C = AlternativeSpec(
        "C", "COLABORATIVO",
        "La solución que favorece la interacción entre equipos, con el mismo programa.",
        "Mayor integración entre equipos y espacios compartidos, manteniendo el programa completo.",
        ["Cuatro barrios de trabajo en vez de una franja monótona", "Lounge integrado a la circulación",
         "Salas y encuentro cerca del trabajo", "Comedor y lounge como zona social"],
        "Equipos que trabajan en proyectos y necesitan encontrarse durante el día.",
        spine_strategy="C_DUAL_NEIGHBORHOOD",
        bench_cfgs=[4, 3, 2],
        weights={"adjacency_quality": 0.20, "daylight_utilization": 0.18, "meeting_accessibility": 0.16,
                 "circulation_efficiency": 0.10, "entrance_logic": 0.10, "facade_preservation": 0.10,
                 "compactness": 0.06, "privacy_gradient": 0.05, "wasted_space": 0.05},
        solver_extra={"min_bench_blocks": 8, "row_penalty_per_seat": 0.05, "branch_cost_scale": 0.4,
                      "max_facade_closed_rooms": 4, "hard_adjacent_pairs": [("kitchenette", "dining")],
                      "module_max_path": {"boardroom_12": 18.0},
                      "pair_bonus": [("lounge", "meeting_4", 0.8), ("meeting_4", "meeting_8", 0.6),
                                     ("lounge", "dining", 0.6), ("kitchenette", "dining", 0.8),
                                     ("phone_booth", "meeting_4", 0.2)]},
        graph=gC)
    return [A, B, C]
