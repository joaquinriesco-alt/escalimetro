# E05 — Hybrid spatial reasoning

    SPATIAL STRATEGY → GEOMETRIC SOLVER → DETERMINISTIC VALIDATOR → ARCHITECTURAL CRITIC → REPAIR / ITERATION

Paquete `src/escalimetro/layout/e05/`. E04 (`layout/solver.py`, `strips.py`, `circulation.py`, `scoring.py`,
`render.py`) queda congelado como baseline: E05 reutiliza su validador, su scoring, su raster y su renderer.

| capa | módulo | qué hace | determinista |
|---|---|---|---|
| rasgos del shell | `features.py` | regiones (bahías) etiquetadas por fachada/rumbo, fachada con luz, acceso, distancias | sí |
| estrategia | `strategy.py` | `SpatialStrategy` (intención, sin coordenadas) + 8 familias generadas desde roles | sí |
| espina y bandas | `bands.py` | patrón de sección por región → bandas con profundidades reales, pasillos desplazados fuera de pilares y alineados a la rejilla, slots libres, conectores sólo donde hacen falta, verificación raster | sí |
| pre-flight | `preflight.py` | demanda vs oferta por clase de profundidad, rectángulo mayor (directorio) y dónde cabe, capacidad de puestos, inviabilidades obvias | sí |
| solver | `cpsolver.py` | CP-SAT: una opción (slot, orientación) por recinto; bloques de puestos parametrizados (bench 2×2…2×6, filas); Σ puestos = 40; NoOverlap por slot; recepción ≤ 8 m como dominio; pilares nunca bajo mobiliario | reproducible con seed y límite de tiempo (el óptimo puede variar con el límite) |
| validador | E04 `Solver.validate` | inside/core/pilares/colisiones/programa/conteos/circulación/puertas/within_8m | sí |
| crítico | `critic.py` | `RuleBasedCritic` → `CritiqueReport` (12 aspectos) + `RepairSuggestions`; `OpenAIVisionCritic` = contrato sin llamadas | sí |
| reparación | `critic.to_repair_constraints` + `cpsolver.RepairConstraints` | sugerencias → restricciones (adyacencia, prohibir fachada/banda, pesos, mínimo de puestos en fachada) → re-solve | sí |
| ranking | `critic.rank` | hard_valid (binario) → geométrico (E04) → arquitectónico → total; inválido nunca gana | sí |
| orquestador | `run.py` | corre todo, registra iteraciones, sonda de capacidad, visuales | — |

## Frontera de proveedores

- Código determinista / Claude: geometría, solver, restricciones, tests, validación, JSON.
- OpenAI (futuro): `OpenAIVisionCritic` (crítica con visión sobre `layout_e05_geometry.png` + JSON), comparación
  entre alternativas y lámina comercial premium a partir de `layout.json` + `layout_e05_commercial_base.svg`
  **sin cambiar geometría** (la geometría es la lista de `Placement`; cualquier lámina se genera desde ella).

## Regla de fallo

Sin candidato con `hard_valid = true` → Gate E1 FAIL. La sonda `seats_mode="max"` (máximo de puestos con el
programa de recintos completo) es diagnóstico y se etiqueta como tal; nunca es un candidato.
