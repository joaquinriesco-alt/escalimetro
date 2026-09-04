# AUDITORÍA DE LITERALES DE CASO — E15

Búsqueda de `403`, `543`, `001_gps_403`, `GPS Property`, `shell_semantics_403`, `fit_robustness_403` y `OFFICE_403` sobre todo el repositorio versionado, después de implementar el contrato genérico de caso.

**No se busca eliminar la palabra 403 del repositorio.** La historia puede hablar de la 403; el motor genérico no. Cada ocurrencia se clasifica en una de cinco categorías permitidas, y la sexta —`GENERIC_ENGINE_COUPLING`— debe quedar en cero para OF01–OF07.

## Resultado

```
ocurrencias totales:          181
CASE_METADATA                8
TEST_EXPECTATION             73
DOCUMENTATION_HISTORY        85
EXPERIMENT_SPECIFIC          10
HISTORICAL_FIXTURE           5
GENERIC_ENGINE_COUPLING      0
```

**GENERIC_ENGINE_COUPLING: 0.** Es el resultado que E15 exige.

Hay un test parametrizado —`test_el_motor_generico_no_contiene_identidad_de_ningun_caso`— que recorre los nueve módulos del motor genérico y falla si aparece cualquiera de los siete literales en una línea de **código** (los docstrings y comentarios están excluidos a propósito: ahí la historia sí puede nombrar el caso).

## Los nueve módulos del motor genérico

| módulo | ocurrencias en código | en docstring / comentario |
|---|---|---|
| `src/escalimetro/case_context.py` | **0** | 7 |
| `src/escalimetro/layout/e06/run.py` | **0** | 4 |
| `src/escalimetro/layout/e06/scale.py` | **0** | 3 |
| `src/escalimetro/layout/e06/verdict.py` | **0** | 0 |
| `src/escalimetro/layout/e07/board.py` | **0** | 0 |
| `src/escalimetro/layout/e07/engine.py` | **0** | 0 |
| `src/escalimetro/layout/e07/pipeline.py` | **0** | 1 |
| `src/escalimetro/layout/e07/run.py` | **0** | 1 |
| `src/escalimetro/layout/run.py` | **0** | 1 |

## Categorías

| categoría | qué agrupa | ocurrencias |
|---|---|---|
| `CASE_METADATA` | datos del inmueble en `case.json` y notas del caso: es exactamente donde deben estar | 8 |
| `TEST_EXPECTATION` | tests que apuntan al caso 001 o fijan sus hashes; su trabajo es nombrarlo | 73 |
| `DOCUMENTATION_HISTORY` | docs, docstrings, comentarios y ejemplos de uso | 85 |
| `EXPERIMENT_SPECIFIC` | E08/E09/E12 (validación por API), E13 (validación con brokers) y E14 (generalización): experimentos deliberadamente sobre la 403 | 10 |
| `HISTORICAL_FIXTURE` | resto del código no perteneciente al motor genérico de layouts | 5 |
| **`GENERIC_ENGINE_COUPLING`** | **prohibida** | **0** |

## Archivos con más ocurrencias

| archivo | total | categorías |
|---|---|---|
| `tests/test_e15_case_contract.py` | 41 | TEST_EXPECTATION 37, DOCUMENTATION_HISTORY 4 |
| `docs/E15_BACKLOG.md` | 18 | DOCUMENTATION_HISTORY 18 |
| `tests/test_e14_generalization.py` | 15 | TEST_EXPECTATION 14, DOCUMENTATION_HISTORY 1 |
| `README.md` | 9 | DOCUMENTATION_HISTORY 9 |
| `src/escalimetro/case_context.py` | 7 | DOCUMENTATION_HISTORY 7 |
| `cases/001_gps_403/notes.md` | 7 | DOCUMENTATION_HISTORY 7 |
| `cases/001_gps_403/case.json` | 7 | CASE_METADATA 7 |
| `src/escalimetro/layout/e06/run.py` | 4 | DOCUMENTATION_HISTORY 4 |
| `src/escalimetro/generalization/visuals.py` | 4 | EXPERIMENT_SPECIFIC 4 |
| `tests/test_case_001_real.py` | 4 | TEST_EXPECTATION 3, DOCUMENTATION_HISTORY 1 |
| `docs/E07_THREE_OPTIONS.md` | 4 | DOCUMENTATION_HISTORY 4 |
| `src/escalimetro/cli.py` | 3 | DOCUMENTATION_HISTORY 3 |
| `src/escalimetro/layout/e06/scale.py` | 3 | DOCUMENTATION_HISTORY 3 |
| `tests/test_e06.py` | 3 | TEST_EXPECTATION 3 |
| `docs/ARCHITECTURE.md` | 3 | DOCUMENTATION_HISTORY 3 |
| `src/escalimetro/validation/boards.py` | 2 | DOCUMENTATION_HISTORY 1, EXPERIMENT_SPECIFIC 1 |
| `src/escalimetro/vision/ocr_localizer.py` | 2 | DOCUMENTATION_HISTORY 1, HISTORICAL_FIXTURE 1 |
| `tests/test_e13_broker_validation.py` | 2 | TEST_EXPECTATION 2 |

## Ocurrencias en código fuera del motor genérico, una por una

| archivo:línea | literal | categoría | por qué se permite |
|---|---|---|---|
| `program_templates/modules_office.json:322` | `403` | `HISTORICAL_FIXTURE` | — |
| `program_templates/office_balanced_48_diag36.json:81` | `403` | `HISTORICAL_FIXTURE` | — |
| `scripts/build_broker_validation_pack.py:19` | `403`, `001_gps_403` | `EXPERIMENT_SPECIFIC` | Default sobreescribible por `ESCALIMETRO_CASE` del script de E13. |
| `src/escalimetro/ai/board02.py:113` | `543` | `EXPERIMENT_SPECIFIC` | Lámina del experimento E08 sobre la 403. §38 prohíbe modificar la capa de IA en E15. Deuda anotada. |
| `src/escalimetro/ai/orchestrator.py:65` | `403`, `001_gps_403` | `EXPERIMENT_SPECIFIC` | Etiqueta de proyecto para telemetría del experimento de IA. No toca geometría ni presentación (§17). |
| `src/escalimetro/ai/railway_e09_runner.py:32` | `403`, `001_gps_403` | `EXPERIMENT_SPECIFIC` | `DEFAULT_CASE` del runtime de validación E09; sobreescribible por `ESCALIMETRO_CASE` y por `--case`. E09/E12 son un experimento sobre la 403 (§17). |
| `src/escalimetro/generalization/scorecard.py:31` | `GPS Property` | `EXPERIMENT_SPECIFIC` | Evidencia del experimento E14. |
| `src/escalimetro/generalization/visuals.py:101` | `403` | `EXPERIMENT_SPECIFIC` | Visuales del experimento E14, que compara 403 contra 401 por definición. |
| `src/escalimetro/generalization/visuals.py:139` | `403` | `EXPERIMENT_SPECIFIC` | Visuales del experimento E14, que compara 403 contra 401 por definición. |
| `src/escalimetro/generalization/visuals.py:143` | `403` | `EXPERIMENT_SPECIFIC` | Visuales del experimento E14, que compara 403 contra 401 por definición. |
| `src/escalimetro/generalization/visuals.py:176` | `403` | `EXPERIMENT_SPECIFIC` | Visuales del experimento E14, que compara 403 contra 401 por definición. |
| `src/escalimetro/schemas/__init__.py:1` | `403` | `DOCUMENTATION_HISTORY` | Falso positivo: `F403` es un código de flake8. |
| `src/escalimetro/schemas/floorplate.py:207` | `403` | `HISTORICAL_FIXTURE` | Comentario con un ejemplo de `unit_label`. |
| `src/escalimetro/validation/boards.py:174` | `403`, `543` | `EXPERIMENT_SPECIFIC` | Lámina ciega de E13, construida para validar ESTE caso con brokers. §38 prohíbe modificar E13 en E15. Deuda anotada. |
| `src/escalimetro/vision/base.py:25` | `403`, `543` | `HISTORICAL_FIXTURE` | Comentario con ejemplos de texto leído por OCR. |
| `src/escalimetro/vision/ocr_localizer.py:52` | `403` | `HISTORICAL_FIXTURE` | OF12: comentario sobre la maquetación. §35 prohíbe tocar el OCR en E15; espera al caso cross-drawing. |

## Qué queda como deuda

Dos láminas siguen rotulando la 403 a mano: `ai/board02.py` (E08) y `validation/boards.py` (E13). Las dos están fuera del alcance de E15 por §38, que prohíbe expresamente tocar la capa de IA y el sistema de validación con brokers. Ninguna pertenece al motor genérico de layouts y ninguna se ejecuta en el camino que recorrería un shell nuevo con FIT. Quedan anotadas para cuando ese ciclo llegue.
