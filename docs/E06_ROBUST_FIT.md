# E06 — Robust space planning + assisted QA

    SHELL + PROGRAM + CONSTRAINTS  →  FEASIBILITY + SPATIAL ALTERNATIVES + CONFIDENCE + FAST HUMAN QA

Paquete `src/escalimetro/layout/e06/`. E04 y E05 congelados (tests de baseline).

| módulo | qué hace |
|---|---|
| `scale.py` | `ScaleScenario`: la escala nominal (published_area_inferred, LOW) multiplicada por un factor; sólo cambia el shell |
| `freeplace.py` | ORTHOGONAL_FREE_PLACEMENT: red = espina E05 + ramales candidatos (perpendiculares, T, lazos); candidatos rectangulares finitos por módulo anclados a cualquier elemento de la red, ambas orientaciones, filtrados por shell/núcleo/pilares/acceso; CP-SAT con NoOverlap2D elige candidatos + ramales; Σ puestos = 40 duro; recepción ≤ 8 m por dominio |
| `sweep.py` | barrido de escala con el MISMO brief; `FitRobustnessReport` + clasificación (umbrales = hipótesis de producto) |
| `evidence.py` | evidencia secundaria de escala del JPG (rangos, nunca valores exactos); UNKNOWN si es inconsistente |
| `qa.py` | `HumanCorrectionOperation` (ACCEPT/MOVE/ROTATE/SWAP/RESIZE_TO_VALID_VARIANT/DELETE/ADD/LOCK), re-validación determinista, `HumanCorrectionBurden` (minutos ESTIMADOS), gates asistidos |
| `verdict.py` | FIT VERDICT (producto preliminar) |
| `run.py` | `sweep` / `qa` / `report` |

Frontera de proveedores: sin cambios respecto de E05 (`OpenAIVisionCritic` sigue siendo un contrato sin llamadas).
La geometría validada nunca la cambia un LLM: sólo el solver o una `HumanCorrectionOperation`, y siempre pasa
por `Solver.validate` de E04 después.
