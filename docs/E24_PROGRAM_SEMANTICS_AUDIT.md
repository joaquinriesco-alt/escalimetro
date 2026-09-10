# E24 §4 — AUDITORÍA DE SEMÁNTICA DEL PROGRAMA (antes de escribir BriefV1)

Esta auditoría se escribió ANTES de tocar una línea de runtime. Cada afirmación cita archivo:línea del
árbol en `e23_mvp_v1` (HEAD 7536ecd). No es una descripción de intención: es lo que el código hace hoy.

## 1. `open_workstations_exact` — ÚNICA cantidad de asientos que es restricción dura

Consumidores (grep exhaustivo sobre `src/`):

| archivo:línea | uso |
|---|---|
| `src/escalimetro/layout/solver.py:64` | dimensiona la RESERVA de fachada para puestos (`desk_demand_m2 = need/6 · 4.8·3.2 · 1.25`) |
| `src/escalimetro/layout/solver.py:263` | genera clusters hasta cubrir `need` en el constructivo greedy |
| `src/escalimetro/layout/solver.py:421` | ídem en `build_strips` |
| `src/escalimetro/layout/solver.py:725` | **validación dura**: `if seats != need → violación` |
| `src/escalimetro/layout/e06/freeplace.py:366` | `need` del modelo CP-SAT (`seats_mode="exact"`) |
| `src/escalimetro/layout/e05/preflight.py:53` | área abierta demandada en el preflight de factibilidad |
| `src/escalimetro/layout/run.py:35` | `program_completeness.open_seats = f"{seats}/{need}"` |
| `src/escalimetro/layout/e05/cpsolver.py:101` | solver muerto respecto de producción (E23 §motor) |

La suma que se compara contra `need` está filtrada por módulo:

```
solver.py:724   seats = sum(p.seats for p in layout.placements
                            if p.module in ("workstation_cluster", "workstation_row"))
run.py:34       seats = sum(p.seats for p in layout.placements if p.module.startswith("workstation"))
```

**Conclusión 1.** `open_workstations_exact` = puestos fijos de open space, exactos, no ≥. Los asientos de
sala NO entran en esa suma porque el filtro es por módulo, no por `p.seats`.

## 2. `target_headcount` — NO es una restricción. Es un dato declarativo del brief

Consumidores (grep exhaustivo, `src/` completo): **dos**, ambos de presentación/metadata.

| archivo:línea | uso |
|---|---|
| `src/escalimetro/fit_evidence.py:314` | rellena `ev.headcount` cuando E06 no dejó veredicto |
| `src/escalimetro/validation/boards.py:193` | texto de lámina: `"{target_headcount} personas"` |

Ningún solver, ningún validador y ningún preflight lo lee. **Conclusión 2.** `target_headcount` es la
población que el cliente declara, y sirve para dimensionar soporte (comedor, salas) y para el relato.
Cambiarlo hoy no cambia una sola coordenada.

## 3. El delta headcount ↔ puestos ya estaba declarado, no resuelto

`program_templates/office_balanced_48.json` trae:

```
"target_headcount": 48,
"_headcount_note": "El brief dice 48 personas; los puestos fijos del programa son 40 open + 4 privados
                    = 44 + 1 recepción = 45. Los 48 se usan para dimensionar comedor y salas;
                    la diferencia (3) NO se rellena con puestos extra."
```

Es decir: el proyecto ya había decidido, en E05, que `target_headcount ≠ Σ puestos`. E24 no inventa esa
distinción; la formaliza y la valida.

## 4. `occupancy` por módulo: dónde está la trampa que §4 advierte

De `program_templates/modules_office.json`:

| módulo | kind | occupancy | ¿es headcount permanente? |
|---|---|---|---|
| `workstation_cluster` | furniture | 6 | **sí** (asiento fijo) |
| `workstation_row` | furniture | 3 | **sí** |
| `private_office` | room | 1 | **sí** |
| `reception` | room | 1 | **sí** (puesto atendido) |
| `meeting_4` | room | 4 | **no** — asientos de reunión |
| `meeting_8` | room | 8 | **no** |
| `boardroom_12` | room | 12 | **no** |
| `dining` | room | 16 | **no** — capacidad por turno |
| `lounge` | room | 8 | **no** |
| `phone_booth` | room | 1 | **no** — uso rotativo |
| `kitchenette` | room | 0 | — |

En `solver.py:258` cada recinto colocado recibe `seats = mod.occupancy if mod.kind == "room" else 0`.
Por lo tanto `sum(p.seats for p in placements)` SÍ mezcla asientos de reunión con puestos
(40 + 4·1 + 3·4 + 8 + 12 + 3·1 + 1 + 16 + 8 = 104 en el brief histórico). Esa suma no se usa como
restricción hoy, pero es exactamente el error que §4 prohíbe cometer al parametrizar. BriefV1 lo cierra
por construcción: nunca deriva puestos de `p.seats` sin filtro de módulo.

## 5. Regla consistente que adopta BriefV1 (y que E24 valida)

```
OPEN_WORKSTATIONS   = brief.open_workstations                (exacto; restricción dura del solver)
PERMANENT_SEATS     = open_workstations
                    + Σ_m count(m) · occupancy(m)  para m ∈ {private_office, reception}
MEETING_SEATS       = Σ_m count(m) · occupancy(m)  para m ∈ {meeting_4, meeting_8, boardroom_12}
SUPPORT_CAPACITY    = Σ_m count(m) · occupancy(m)  para m ∈ {dining, lounge}
TARGET_HEADCOUNT    = brief.target_headcount        (declarado; dimensiona soporte; NO es restricción)
UNSEATED_HEADCOUNT  = target_headcount − PERMANENT_SEATS      (se REPORTA, no se rellena)
```

Validación de consistencia del brief (no de la geometría):

* `open_workstations ≥ 1`
* `target_headcount ≥ PERMANENT_SEATS` → si no, `BRIEF_INCONSISTENT` y no se corre nada.
* `MEETING_SEATS` no participa jamás de `PERMANENT_SEATS`.
* `workstation_cluster` NO es un campo del brief: se deriva `ceil(open_workstations / 6)`.
  Con 40 → 7, que es exactamente el `count: 7` del template histórico.

Sobre el brief histórico: PERMANENT_SEATS = 40 + 4 + 1 = 45, TARGET_HEADCOUNT = 48,
UNSEATED_HEADCOUNT = 3. Reproduce el `_headcount_note` sin copiarlo.

## 6. Qué NO es brief (§5 — DesignPolicyV1)

Estaba mezclado dentro del mismo JSON de programa y sale de BriefV1:

* `objectives_weights` (9 pesos) — `office_balanced_48.json`
* `zoning_rules` — declarado en el template y **nunca leído**; el runtime usa
  `src/escalimetro/layout/zoning.py:23` `ZONE_OF_MODULE`. Es política de diseño, no cliente.
* pesos y `solver_extra` por alternativa — `e07/strategies.py`
* aristas de adyacencia `_common_edges()` — `e07/strategies.py:41`
* estrategias de espina A/B/C y `bench_cfgs` — `e07/strategies.py`
* geometría de módulos y holguras — `modules_office.json`

El cliente no controla nada de esto. Por eso `zoning.py:ZONE_OF_MODULE` **no se borra**: §6 prohíbe
eliminar por reflejo reglas arquitectónicas. Lo que se hace es reconocerlo como DesignPolicyV1 y quitar
del brief el `zoning_rules` duplicado y muerto.
