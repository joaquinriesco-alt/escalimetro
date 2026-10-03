# E44 REPORT

## Status
**PARTIAL** — la infraestructura de la campaña está lista y probada; **0 casos reales** capturados,
ejecutados o completados. Nada de lo medible se midió.

## Qué cambió
Instrumento mínimo que reutiliza lo existente (sin app paralela, sin tocar `src/`, `.github/` ni el
ejecutor):

- `webapp/campaign.py` — manifiesto con provenance (URL, fecha, fuente, tipo, m² publicados, assets
  con sha256 y `origin_url`), importador de **bundles** capturados fuera del ejecutor, detección de
  duplicados (URL canónica, sha de assets, misma propiedad entre pistas), filtro de PII, estado
  **derivado** de artefactos, resultados como eventos de sólo inserción, auditoría de ceguera,
  resumen e índice HTML de revisión.
- `scripts/e44_campaign.py` — CLI (`import`, `run-improve`, `run-create`, `correct`, `close`,
  `reveal`, `status`, `index`, `exclude`).
- `docs/E44_CAMPAIGN.md` — formato exacto del bundle y cómo correr la campaña sin debilitar el
  aislamiento.
- `tests/test_e44_campaign.py` — 20 tests.

**MEJORAR** corre por el camino real (`floorplan.ensure_case` + `publish_commercial_floorplan`); no
corrige ni confirma nada: si la planta no queda lista, eso es el resultado y se registra.
**CREAR** usa E37: proyecto con fotos como únicos inputs, plano real vía `groundtruth.upload`
(HIDDEN_FROM_ENGINE), correcciones como corridas hijas, **cierre blind** → reveal → evaluación. El
plano real no entra al manifiesto ni a `evidence/`. Sin credencial: `BLOCKED_MISSING_CREDENTIAL`.
`fixture_replay` se rechaza como motor de un caso.

## Tabla 20 + 20

| pista | listados | capturados | ejecutados | completados | meta |
|---|---|---|---|---|---|
| MEJORAR | 0 | 0 | 0 | 0 | 20 |
| CREAR | 0 | 0 | 0 | 0 | 20 |

No hay casos en este entorno: ningún provenance que reportar. **No se afirma haber probado ninguna
URL.** Exclusiones: ninguna. Ratings de Joaquín: ninguno (faltan los 40).

## Bloqueos (por qué es PARTIAL)
1. **Red:** el ejecutor está aislado de Internet a propósito (no se relajó; no se intentó). Los 40
   casos no se pueden capturar acá.
2. **Material:** no hay bundle de casos reales en el repo ni en el entorno.
3. **Credencial:** `OPENAI_API_KEY` ausente (verificada sólo por presencia). Sin ella ningún caso
   CREAR puede ejecutarse con el motor real `openai_direct` (`gpt-5.6-sol`); no hay model/versión/
   prompt/costo/latencia reales que reportar.

## Cómo completar la campaña sin debilitar la seguridad
1. Fuera del ejecutor, capturar 20 + 20 casos y armar el bundle (`docs/E44_CAMPAIGN.md`), con
   provenance y sha256 por asset; el plano real de CREAR sólo como `ground_truth_plan`.
2. En una máquina con red limitada a ese propósito y `OPENAI_API_KEY` configurada (decisión de gasto
   de Joaquín): `import`, `run-improve`/`run-create`, correcciones, `close`, `reveal`, evaluación.
3. `status` e `index` regeneran el resumen y el índice de revisión desde los artefactos.

## Prueba de blindness
`campaign.blind_audit` busca el sha256, el nombre original, el nombre guardado y la carpeta
`reconstruction_gt` en todo lo visible al motor (manifiesto, listado de `evidence/`, assets del
proyecto, inputs/params congelados de cada corrida) y rechaza que un input sea byte a byte el plano
real; `close_blind` la exige y la guarda en el cierre. Tests: el plano real no está en manifiesto ni
evidence; fuga adversarial (copia en `evidence/`, nombre en `notes`) detectada; plano real = input se
rechaza al importar; la petición que arma E37 para el motor no contiene sha ni nombre del GT; el
índice no muestra el plano real antes del reveal. Corridas del motor real: ninguna.

## Evidencia
- MEJORAR (dimensiones por separado, sin score compuesto): sin datos.
- CREAR (inventario, adyacencias, posiciones, forma global, proporciones, puertas; prompts y minutos
  humanos; CAD): sin datos.
- Errores recurrentes, ejemplos buenos/malos, qué evidencia necesita CREAR: **no hay base para
  decirlo**. Ninguna conclusión de calidad.

## Regresiones
E43 y E37 siguen en verde (148 passed junto con E44). `git diff 6324b1f HEAD -- src/` vacío. El fallo preexistente de `test_ai_handoff` sobre `origin/main` no es de E44.

## Limitaciones
- `pipeline` es singleton: un fallo transitorio del motor lo consume; reintentar exige decisión
  (corregir con una corrida hija sí es posible). Revisar tras los primeros casos reales.
- `run_improve` y `run_create` real no se ejercitaron con material real; `run_improve` se probó con un
  plano sintético que no produce planta lista (resultado registrado, no oculto).
- La evaluación y los ratings se cargan con `campaign.record(...)` (no hay formulario web).
- La suite completa no se corrió (~12 min).

## `git diff 6324b1f HEAD -- src/`
Vacío (verificado; también cubierto por `test_src_congelado`).

## Tests
`tests/test_e44_campaign.py` 20 passed; con `test_e43_plano_corporativo_entrega.py` y
`test_e37_reconstruction_lab.py`: 148 passed. Handoff incluido abajo si se corrió.

## Acceptance criteria
1–6, 26: PASS (manifiesto, pistas, duplicados, N honesto, índice, regenerable; tests de manifest, conteo, duplicados, ceguera, reveal, inmutabilidad). 7–10, 12–19, 30: **NO CUMPLIDOS** — 0/20 + 0/20 reales (§Bloqueos); 15, 17, 18, 19, 20 cubiertos por tests y código, sin casos reales. 11, 21, 31, 32: cumplidos (PARTIAL declarado). 22–25, 29: PASS. 27–28: este commit.

## Decisiones requeridas
Ninguna técnica. Para completar la campaña Joaquín debe decidir/proveer (no es DECISION_REQUIRED de producto): captura de los bundles fuera del ejecutor y gasto con `OPENAI_API_KEY`.

## Commit / branch / PR
Rama `auto/e44-issue-13`, hija de `e44_online_plan_benchmark`; la publica el workflow. Sin merge, deploy, PR ni cambios en `main`. Base para la próxima TASK: `auto/e44-issue-13`.

## Exact next action
No se crea E45: audita ChatGPT y decide Joaquín. Siguiente cuello de botella: capturar fuera del ejecutor 20 + 20 casos reales en bundle (`docs/E44_CAMPAIGN.md`) y correr la campaña con `OPENAI_API_KEY`.
