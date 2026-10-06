# E48 REPORT — Auditoría final de readiness pre-piloto

## Status
**PASS** — la auditoría se ejecutó completa (capas A–I de la TASK) y cumple sus criterios de aceptación.
Lo que el sandbox no puede observar está marcado **NO PROBADO**, no inferido.

## VEREDICTO

**NOT_READY**

Tres hallazgos reproducibles bloquean el piloto de 20 MEJORAR + 20 CREAR. Dos de ellos son **regresiones
de la propia cadena E47** que sus REPORT declaraban cerradas (H03 y H01), y el tercero es H17, que E46
dejó en MEDIUM y la cadena E47 nunca tocó:

| # | id | severidad | qué rompe | por qué bloquea (criterio 15 de la TASK) |
|---|---|---|---|---|
| 1 | **E48-C1** | BLOCKER | un doble toque de PROCESAR a 80–120 ms lanza **dos corridas pagadas** | puede duplicar costo (H03 no quedó cerrado) |
| 2 | **E48-B1** | BLOCKER | un plano real con marco gris/negro, o coloreado, girado/recortado/capturado, entra al motor como «foto» y `blind_audit` da OK | invalida la ceguera sin aviso (H01 no quedó cerrado) |
| 3 | **E48-H17** | HIGH | dos `settle`/`record` simultáneos duplican eventos (`correction` ×6 con 8 hilos), infla `human_prompts` y da 500 | contamina un resultado medido y rompe el uso normal con 2 pestañas |

Corrección mínima sugerida (sin implementar) y la lista completa en «Hallazgos nuevos» y «Exact next action».
Ningún otro riesgo bloquea: el resto se clasificó `KNOWN_RISK_ACCEPTABLE` o `NOT_REPRODUCED` con justificación (tabla de MEDIUM/LOW).

## Qué cambió
Sólo evidencia: `tests/test_e48_audit.py` (96 tests de auditoría), este REPORT y `CURRENT_STATE.md`. **Ningún
archivo productivo** (`src/`, `webapp/`, `.github/`, `scripts/`, `Dockerfile`, `requirements.txt`, plantillas, CSS)
cambió: ver «Diff prohibido». Los tests siguen la convención de E46: los llamados `…_DEFECTO_E48_*` afirman el
comportamiento defectuoso a propósito (para que el REPORT lo cite con una reproducción ejecutable) y fallarán el
día que se corrija; cada docstring lo dice. El resto son invariantes que SÍ se sostienen.

## Archivos principales
| archivo | contenido |
|---|---|
| `tests/test_e48_audit.py` | B (ceguera, transformaciones del plano real), C (concurrencia/costo), D (recovery), E (cargas), F (superficie), G (métricas), I (camino feliz) |
| `reports/E48_REPORT.md` | este informe |
| `docs/ai-development/CURRENT_STATE.md` | estado y base para la próxima TASK: `auto/e48-issue-31` |

## Commit / base, duración y metodología
- **Código auditado:** `a7d5c2fc03d7430a581f72ca4aba7dd1e749e19c` (`auto/e47_11-issue-30`, E47.11). TASK en
  `522aa1ead5afbdfb1a00a1b35cc25e9e85ce7cc1` (`e48_final_pre_pilot_readiness_audit`): `git diff --name-only a7d5c2f HEAD`
  → sólo `tasks/E48.md`. Rama de trabajo: `auto/e48-issue-31`. Verificado con ramas locales/remotas de seguimiento;
  **`git fetch` no está permitido en este sandbox**, así que las ramas no se reverificaron con `git ls-remote`.
- **Duración:** ≈ 1 h de reloj (11:25–12:30 UTC del 2026-10-06, por las marcas de archivo), con 2 corridas completas de la suite
  (8 min 27 s la primera) más corridas focales. La TASK no exigía tiempo fijo: se cerró al cubrir A–I y al dejar de aparecer
  hallazgos nuevos en los sondeos.
- **Metodología:** (1) lectura de CLAUDE.md, CURRENT_STATE, protocolo, TASK, E46 completo y el código de `campaign.py`,
  `pilot.py`, `plan_guard.py`, `origin_guard.py`, `mobile_upload.py`, `classify.py`; (2) suite completa antes de tocar nada;
  (3) sondeos exploratorios con scripts temporales (en `.data-e48/`, ignorado por git, no commiteados) para cada hipótesis;
  (4) sólo lo informativo se convirtió en test; (5) hipótesis adversariales sobre las **fronteras** de cada fix, no repetición
  de sus tests: transformaciones del plano real, intercalados de hilos con y sin barrera, evidencia de tamaño realista,
  errores hostiles, planos de portal reales del repo.

## Comandos ejecutados (resumen)
```
.venv/bin/python -m pytest tests/ -q --no-header -p no:cacheprovider --continue-on-collection-errors     # suite completa (antes y después)
.venv/bin/python -m pytest tests/test_e48_audit.py -q                                                     # 96 tests nuevos
.venv/bin/python -m pytest tests/test_e37_reconstruction_lab.py tests/test_e44_campaign.py tests/test_e45_web_pilot.py \
    tests/test_e45_2_mobile_upload.py tests/test_e46_adv_*.py tests/test_e47_7_h16_perf.py \
    tests/test_e47_8_create_retry.py tests/test_e47_11_provider_error.py -q                               # regresión focal: 620 passed
.venv/bin/python .data-e48/probe_h01.py / probe_h01b.py                                                   # matriz de transformaciones (75 con GT de papel + 100 con GT coloreado)
.venv/bin/python -m pytest .data-e48/test_probe_*.py -q -s                                                # sondeos de carrera, doble costo, costo de status()
git diff 6324b1f HEAD -- src/ ; git diff a7d5c2f HEAD -- <rutas productivas>                              # diffs prohibidos
.venv/bin/python scripts/secret_scan.py                                                                    # escaneo de secretos
```
Sin red, sin deploy, sin merge, sin PR, **cero llamadas pagadas**: el motor «real» de CREAR sólo se ejerció con adaptadores de
prueba (`motor_de_prueba`, heredado del fixture); `OPENAI_API_KEY` sólo se fijó a valores inventados dentro de tests para probar
que se enmascara. Nunca se usó una credencial real.

## Tests
baseline (antes de E48):  `10 failed, 2976 passed, 12 skipped, 7 xfailed, 6 warnings, 1 error in 507.09s (0:08:27)` @ `522aa1e`
post-change (con E48):    **`10 failed, 3074 passed, 12 skipped, 7 xfailed, 7 warnings, 1 error in 509.04s (0:08:29)`** @ `auto/e48-issue-31` (con este REPORT y `CURRENT_STATE` ya escritos;
                          3074 − 2976 = 98 = los 96 tests de E48 + 2 casos parametrizados de `test_ai_handoff` que aparecen con la TASK y el REPORT nuevos; los 10 fallos y el error de
                          colección son **exactamente los mismos** que en la línea base, sin ninguno nuevo; 7 warnings = 6 previos + 1 `DecompressionBombWarning`)
                          Tras esa corrida se hicieron estables `C4`, `C5` y `C6`: sus invariantes de COSTO pasaron a «a lo sumo una corrida/publicación» y toleran el 500 espurio que H17
                          introduce (otra petición lee un evento mientras el ganador lo escribe), y `C6` asienta el FAILED antes de lanzar los hilos. Re-verificado:
                          `tests/test_e48_audit.py` 96 passed, y con `test_ai_handoff.py` sólo falla el conocido `[E47.2]`.
E48 solos:                `96 passed`  ·  regresión focal E37+E44+E45+E45.2+E46+E47: `620 passed` (idéntico al de E47.11).

### Suite completa — clasificación de fallos
| test | clase | evidencia |
|---|---|---|
| `test_ai_handoff::test_cada_report_tiene_status_valido_y_sus_secciones[E47.2]` | **regresión de PROCESO de la cadena E47** (documental, no de producto) | `reports/E47.2_REPORT.md` no usa las secciones del protocolo §7; falla desde E47.2 y todos los REPORT E47.3–E47.11 lo arrastran. No se tocó: editar un REPORT ajeno queda fuera del diff de E48. Corrección trivial en la TASK de reparación |
| `test_e12_hardening::test_el_html_muestra_la_etapa_que_fallo` | **preexistente** (lista de CURRENT_STATE) | artefactos regenerables fuera del repo |
| `test_e15_case_contract::test_las_rutas_de_artefactos_se_derivan_del_caso` | **preexistente** | ídem |
| `test_e16_4_res_case::test_el_motor_coincide_con_el_baseline_vigente_declarado` | **entorno** | opencv 5.0.0 / numpy 2.5.3 sin lock; `src/` idéntico a `6324b1f` |
| `test_e16_5_localization::test_la_localizacion_de_403_por_ocr_no_cambio` | **entorno** | falta el binario `tesseract` (el Dockerfile sí lo instala) |
| `test_e17_width_representation` ×5 y `test_e18_topology_representation` (colección) | **entorno / H15** | `scikit-image` no está instalado ni declarado |

Ninguna **regresión de producto** atribuible a la cadena E47 aparece en la suite: las regresiones de producto que sí existen (C1, B1, H17)
no las detecta ningún test previo — por eso son hallazgos de E48 y no fallos de la suite. `xfail`: 7 conocidos (E37–E45.2); `skip`: 12, ninguno
del piloto (con `-rs` sobre E45.2 + E46 uploads/resilience: 0 omitidos).

## Matriz de cobertura (A–I de la TASK)
| capa | resultado | tests / evidencia |
|---|---|---|
| **A** regresión H01/H02/H03/H05/H10/H16/H20/H21/E47.9 | **H** (H01 y H03 se rompen en sus fronteras) | tabla siguiente |
| **B** ceguera / contaminación | **H** | `B1–B9`: matriz de 18 transformaciones × 2 planos + variantes coloreadas + extremo a extremo |
| **C** concurrencia / idempotencia / costo | **H** | `C1–C11b` |
| **D** fallos / reinicios / corrupción | **P** (con riesgos clasificados) | `D1–D6` + E46 `E1–E12` |
| **E** cargas / móvil / recursos | **P** (+ H07/H19 clasificados) | `E1–E4` + E45.2 + E46 `D1–D7` |
| **F** seguridad / superficies | **P** | `F1–F5` + E46 `G1–G6` |
| **G** métricas del experimento | **P** | `G1–G4` (20+20, FAILED, retry, exclusión, DEMO) |
| **H** suite completa / entorno | **P** (fallos clasificados) | arriba |
| **I** camino feliz sin proveedor real | **P** | `I1–I3` |

## Reprueba de los fixes prioritarios (A)
| id | veredicto E48 | evidencia | límite hallado |
|---|---|---|---|
| **H01** (plano disfrazado de foto) | **ROTO EN LA FRONTERA** → E48-B1 | planos de papel: 36/36 transformaciones bloqueadas (`B1`); pero **borde gris/negro**, **plano coloreado/modo oscuro/teñido** + giro, recorte, borde, captura o perspectiva **pasan** (`B2`, `B3`, `B4`) | el parecido de miniaturas 32×32 exige misma proporción y orientación; `classify` exige «papel blanco» |
| **H02** (importación concurrente) | **CIERRA** | `C1` (4 idénticos → 303+400×3, 4 rondas), `C2` (6 distintos → 6 casos, 0 huérfanos E37), `C3` (carga+exclusión), E46 `F1–F3`, `D2` | — |
| **H03** (doble disparo / costo) | **ROTO EN LA FRONTERA** → E48-C1 | `C6` (mismo estado → 1 corrida) cierra; `C11`/`C11a`/`C11b`: dos POST a 80–120 ms con evidencia realista → **2 `create_initial`, 2 `create_started`, dos 303** | el nombre del reclamo (`create`, `create_2`…) se calcula **después** de la guardia y depende de los eventos |
| **H05** (retry CREAR) | **CIERRA** | `D6`, `G1` (FAILED → FAILED → DONE cuenta una vez; historial inmutable), `C7` | un retry concurrente sufre C1 |
| **H10** (same-origin global) | **CIERRA** | `F1`: todas las rutas POST (>50) × 6 variantes de Origin/Referer → 403 salvo `/planos/solicitar`; `F2` sin otros métodos; `F3` excepción exacta | no es token CSRF (conocido) |
| **H16** (costo de clasificar) | **CIERRA** | `E1`: 20 fotos de 4000×3000 (≈ 87 MB) por la web **< 12 s** incluyendo generarlas (E46: 217 s) | `status()` re-hashea la evidencia (E48-P1) |
| **H20** (exclusión) | **CIERRA** (con una salvedad operativa) | `G1`, `G4` (CREAR y MEJORAR: recarga con identidad y propiedad nuevas, historial viejo intacto, N correcto) | `exclude` **sólo existe como API/CLI** (`scripts/e44_campaign.py exclude`): no hay botón |
| **H21** (error de proveedor) | **CIERRA** | `D4`: ruta, URL, email, teléfono, clave con forma de credencial, racha de 13 dígitos, NUL y saltos de línea → panel/caso 200, FAILED sin consumir N, retry → DONE; la clave **real** del entorno no aparece ni en la base; el sanitizador está acotado (error ≤ 2000 caracteres → 0,02 s; la versión sin tope sería cuadrática, `H22`) | la bitácora E37 (base) conserva el texto saneado sólo de la clave real; lo visible desde la campaña va saneado |
| **E47.9** (DONE no asentado) | **CIERRA en secuencia** | `C7`: 0 llamadas nuevas con DONE sin asentar + 3 POST | con POST simultáneos aparece el 500/duplicado de H17 (no un lanzamiento) |

## Hallazgos nuevos

### E48-C1 · BLOCKER · Un doble toque de PROCESAR (CREAR) lanza dos corridas pagadas — H03 no quedó cerrado
- *Qué*: `start_create` hace `settle` → guardia («¿hay un `create_started` sin asentar? ¿el estado es CAPTURED?») → **`_create_claim_name`**
  → `_claim` → `runs.create_initial` → `record("create_started")`. Desde E47.8 el nombre del reclamo es `create` / `create_N` con
  `N = max(len(create_started), len(pipeline)) + 1`: **cambia en cuanto el primer POST registra `create_started`**. Un segundo POST que ya pasó la guardia y
  calcula el nombre después obtiene `create_2`, un nombre libre, y lanza otra corrida. El mismo flujo sirve para el reintento (`create_3`…).
- *Por qué ahora es humano y no de milisegundos*: la guardia incluye `status()`, que recalcula el **sha256 de toda la evidencia** del caso en cada
  llamada (`materials_ok`), y `record()` lo repite. Con 20 fotos de 12 MP (**87 MB**) `status()` tarda **65 ms**; con 13 MB, 10 ms. E46 medía una ventana de
  ≤ 5 ms (0/100 a ≥ 10 ms); esta ventana está entre ≈ 90 y ≈ 155 ms.
- *Repro natural* (sondeo, 87 MB reales, dos POST por HTTP, `enqueue` sin ejecutar): separación 0/10/30/60 ms → 1 corrida; **100 ms → 2 corridas (303 + 303,
  `create_started` ×2)**; 200/400 ms → 1. Repetido con otra evidencia de 87 MB (con la suite completa corriendo en paralelo, que desplaza la banda): 80 ms → 1; **100, 120 y 140 ms → 2
  corridas (303 + 303)**. Con `status()` emulado a 60 ms (`C11b`, reproducible y sin archivos grandes): separaciones 0–60 → 1 corrida;
  **80, 100, 120 ms → 2**; 140–260 → 1.
- *Repro determinista*: `.venv/bin/python -m pytest tests/test_e48_audit.py -k "C11 or C11a"` (intercalado forzado del primer y segundo POST).
- *Impacto*: un segundo cobro por cada doble toque / reintento del navegador móvil / dos pestañas. No hay guardia en el cliente (E46-J4). Es la intención de
  H03 y de la TASK («máximo una llamada pagable por intención»).
- *Origen*: **regresión de E47.8** (antes el nombre era constante, y E47.3 era correcto), no vista por E47.8/E47.9, cuyos tests de concurrencia sólo cubren
  peticiones que calculan el nombre sobre el mismo estado (`C6` reproduce eso y pasa).
- *Corrección mínima sugerida (no implementada)*: que el nombre del reclamo del intento dependa sólo de los `pipeline` **asentados** (`len(pipeline) + 1`: no cambia al
  registrar `create_started`) o, mejor, un candado por caso (RLock + `flock`, como `_manifest_lock`) que cubra guardia → reclamo → `create_initial` → `record`;
  de paso, que `status()` no recalcule el sha256 en cada llamada (cache por tamaño+mtime) para no agrandar ninguna ventana (E48-P1).

### E48-B1 · BLOCKER · El plano real transformado sigue llegando al motor como «foto» — H01 no quedó cerrado
- *Qué*: `plan_guard` tiene dos defensas: `classify` (≥ 45 % de píxeles > 235 y saturación ≤ 0,20 → «plano») y el parecido de miniaturas 32×32 en grises
  (proporción ±8 %, diferencia media ≤ 0,12, Pearson ≥ 0,90). Ambas dependen de **papel blanco** y de **misma orientación/proporción**.
- *Matriz* (planos del repo: dos planos de portal distintos y el fixture sintético `cases/900_synthetic_fixture/original.jpg`; `cases/002_gps_401/original.png` es copia
  byte a byte de `001`, así que son **3 planos distintos**). Con el plano real de papel blanco, 3 planos × 25 transformaciones = 75 combinaciones: **71 se bloquean** (JPEG
  q15–q90, reescalados ×0,5/800/×2/300 px, giros 90/180/270, espejo, recortes 3/8/15 %, bordes **blancos** 5/20 %, captura de pantalla, perspectiva, grises, desenfoque, binarizado) y
  **4 pasan: el borde gris y el borde negro de 10 %** en 2 de los 3 planos (el tercero conserva ≥ 45 % de blanco y `classify` lo ve).
  Con un plano **coloreado** (recintos rellenos, modo oscuro, teñido, o el plano con marco gris como GT; 4 variantes × 25 transformaciones = 100 combinaciones): **45 pasan** —
  giro 90/180/270, espejo, recorte 8/15 %, borde 5 % blanco/gris/negro, captura de pantalla (y su JPEG), perspectiva, binarizado—. Siguen bloqueados el mismo archivo
  re-codificado/reescalado/grises/desenfocado (`B3b`).
- *Extremo a extremo* (`B4`): GT = plano de portal; una «foto» = ese plano con marco gris → 303, `blind_audit == {ok: True}` y los bytes viajan en la petición
  que armaría el motor (`runs.build_request(...).images`). Ninguna pantalla avisa.
- *Falsos positivos*: 0 en una foto real (la única versionada, de matplotlib) y 6 sintéticas (`B5`, `B5b`); un rechazo es accionable, no deja caso ni proyecto y se
  recupera quitando la foto (`B5c`). **No se pudo reproducir un falso positivo**, pero el corpus de fotos reales es de 1: NO PROBADO con un set de portal.
- *Impacto*: el experimento CREAR deja de medir lo que dice, sin aviso (gate «fuga del GT»). Exige que alguien suba un plano transformado entre las fotos
  (galería de portal, captura), no un ataque. La TASK define cualquier bypass de un plano «razonablemente transformado» como `NOT_READY`; los giros, recortes,
  bordes y capturas están en su lista explícita.
- *Corrección mínima sugerida (no implementada)*: parecido invariante a giro/espejo/recorte/borde (p. ej. emparejamiento de características ORB/AKAZE entre la
  foto y el plano real, o plantilla multiescala en los 8 giros/espejos sobre bordes) y un detector de «dibujo de líneas» que no dependa del papel blanco
  (densidad de bordes + paleta pequeña + regiones planas). Los tests `B2`/`B3`/`B4` pasarán a exigir el bloqueo.

### E48-H17 · HIGH → BLOCKS_PILOT · `settle` y `record` no tienen exclusión: eventos duplicados, 500 y métrica inflada
- *Qué*: E46-H17 (MEDIUM) sigue exactamente igual y ahora tiene consecuencias medibles: `settle` decide «¿ya está asentada?» y `record` escribe, sin candado y
  **sin guarda de unicidad para `correction`**; `n = len(listdir) + 1` y `open(..., "x")` colisionan.
- *Medido* (sondeos): 2 hilos × 40 correcciones → **66 eventos `correction` para 40 correcciones (26 duplicadas)**, 20 `FileExistsError`; con 8 hilos **248 para 40**.
  `pipeline` con 2 hilos × 25 casos: 11 rondas anómalas (5 `FileExistsError`, 2 `JSONDecodeError` al leer un archivo a medio escribir, y duplicados). Doble toque en CERRAR:
  3/20 con dos `closure`, 1/20 un 500. Doble toque en EVALUAR: 20/20 dos evaluaciones iguales (historial de sólo inserción; el estado y el N no cambian).
- *Repro determinista*: `C8` (dos `correction` con el mismo `run_id` y `human_prompts == 2` para **una** corrección pedida), `C9` (`FileExistsError`/duplicado de `pipeline`),
  `C10` (doble `closure`), `C7` (doble PROCESAR con DONE sin asentar → 303 nunca, pero 500 intermitente y dos `pipeline` DONE del mismo `run_id`).
- *Impacto*: `human_prompts` («¿cuántos prompts humanos requiere cada caso?», métrica pedida por E44) se infla en silencio y la página del caso muestra la corrección dos
  veces; un 500 espurio en un GET normal; la «inmutabilidad de singletons» no se cumple. **No** cambia N ni los ratings: el N se deriva de «existe».
  Probabilidad con un operador y una pestaña: baja (hacen falta dos peticiones dentro de unos milisegundos tras terminar la corrida); con dos pestañas (panel + caso) o un
  reintento del navegador, plausible; ante la duda, y siendo la misma corrección que C1, se clasifica bloqueante.
- *Corrección mínima sugerida*: el mismo candado por caso de E48-C1 alrededor de `settle` y `record`; `record("correction")` idempotente por `run_id`; `seq` asignado con
  `O_EXCL` en bucle; lectura de eventos tolerante.

### Observaciones (no bloquean)
- **E48-P1 · `status()` cuesta O(evidencia)**: cada llamada re-hashea todos los archivos del caso. `GET /` hace 40 llamadas y `GET /panel` 80 con 40 casos; con casos de
  60–87 MB son ≈ 1–3 s por carga del panel, y es lo que ensancha la ventana de C1. MEDIUM; mejora trivial (cache por tamaño + mtime).
- **E48-D3 · reclamo huérfano**: si `record("create_started")` falla o el proceso muere tras `create_initial` y antes de registrar, el reclamo `O_EXCL` queda y el caso responde
  «ya fue lanzada» para siempre; **no hay gasto** (la corrida no llegó a la cola, `enqueue == []`) y se sale con `exclude` + recarga, pero `exclude` no está en la UI (`D3`).
  Ventana de milisegundos: `KNOWN_RISK_ACCEPTABLE`. Idéntico para `improve`/`improve_publish` en MEJORAR.
- **E48-O1 · `exclude` sin UI**: toda salida de un caso atascado o mal cargado exige `scripts/e44_campaign.py exclude <id> "<motivo>"` en el servidor. Para el piloto es una
  dependencia operativa del operador técnico, no un defecto; debe estar en el checklist.
- **E48-T1 · test de proceso**: `test_ai_handoff[E47.2]` falla por el formato del REPORT de E47.2 (arriba).

## Reclasificación de los MEDIUM / LOW de E46
E46 titula «11 MEDIUM» pero lista 10 (H04, H06, H07, H08, H13, H14, H15, H17, H19, H20); con 3 BLOCKER, 4 HIGH y 7 LOW suman los 24 que declara. Se reclasificó cada uno.

| id | ¿reproduce? | impacto en el piloto | clasificación actual | ¿bloquea READY? | mitigación operativa |
|---|---|---|---|---|---|
| **H04** reveal de E37 por fuera | **sí** (`B9`; E46 `DEFECTO_H04`) | exige un POST deliberado, con confirmación, a una pantalla de `/lab/reconstruction` a la que **el piloto no enlaza** (ninguna página del piloto contiene esa ruta). El motor nunca recibe el plano real; se pierde la ceguera del **operador**. Rastro: `closure.gt_state_at_closure == REVEALED` y `gt_state_at_creation` de la corrida hija | `KNOWN_RISK_ACCEPTABLE` | **no** | no abrir `/lab/reconstruction` durante el piloto; revisar `gt_state_at_closure` al exportar. Fix barato: negarse a corregir/cerrar si `gt_state != HIDDEN_FROM_ENGINE` y marcarlo en `summary()` |
| **H06** evento ilegible tumba el panel | **sí** (`D1`; E46 `E3/E3b`) | un evento truncado/vacío (corte entre `open('x')` y `json.dump`, o disco lleno) da 500 en `/`, `/panel` y el caso, y `summary()/count()` fallan; la UI no ofrece reparación. Requiere un `kill`/disco lleno dentro de una ventana de submilisegundo por escritura (≈ 600 escrituras en los 40 casos); se recupera borrando UN archivo | `KNOWN_RISK_ACCEPTABLE` (severidad alta, justificada) | **no** | tras cualquier reinicio inesperado o aviso de disco: listar `e44/cases/*/results/` y borrar los de 0 bytes; vigilar el espacio del volumen. **Recomendado en la TASK de reparación** (escritura atómica `tmp` + `os.link` y lectura tolerante son pequeñas) |
| **H07** MEJORAR sin tope de píxeles | **sí** (`E4`; E46 `D4e/D7`) | PNG/JPG: `f.read()` con tope de 40 MB y 8 bytes de cabecera, sin tope de píxeles antes de `cv2.imread`; el PDF sí se rasteriza con tope. Un plano de portal (≤ 4 000 px) cuesta decenas de MB; sólo un escaneo ≥ 20 000 px o material fabricado exige GB (NO ejecutado) | `KNOWN_RISK_ACCEPTABLE` | **no** | MEJORAR sólo con planos de portal/PDF; no subir escaneos de gran formato; si se necesita, exportar a ≤ 6 000 px |
| **H08** carga no atómica | **sí** (`D2`) | tras un fallo de `_save` (disco lleno) queda un proyecto E37 huérfano y el 1.er reintento da 500; el 2.º entra. **Ningún caso aceptado se pierde ni se borra evidencia ajena** (`D2`) | `KNOWN_RISK_ACCEPTABLE` | no | repetir la carga una vez más; el huérfano no cuenta en N |
| **H13** formulario público escribe hasta 40 MB sin freno | **sí** (E46 `DEFECTO_H13`) | un actor externo que conozca la URL puede llenar el volumen del piloto (→ H06). El piloto es interno y la URL no se publica | `KNOWN_RISK_ACCEPTABLE` bajo la condición de dominio no difundido | no, **condicional** | no enlazar ni anunciar el dominio de FRONT; vigilar el espacio; si el dominio se hace público, tratarlo como bloqueante |
| **H14** sin cabeceras de seguridad | **sí** (E46 `DEFECTO_H14`) | clickjacking exige que el operador visite una página ajena con sesión iniciada en el piloto; ventana privada | `KNOWN_RISK_ACCEPTABLE` | no | no navegar otros sitios con la sesión del piloto abierta |
| **H15** dependencias | **sí** (E46 `K2/K3/K5`) | `skimage` sólo lo usa el SSIM de ambientación (try/except) y 2 módulos de test: ajeno al piloto. Las cotas son `>=`: el build de FRONT resolverá versiones del día; aquí verificadas: Python 3.12.14, numpy 2.5.3, opencv 5.0.0, Pillow 12.3.0, pillow-heif 1.8.0/libheif 1.23.4, pymupdf 1.28.2, Flask 3.1.3, Werkzeug 3.1.9 | `KNOWN_RISK_ACCEPTABLE` | no | tras el deploy: `pip freeze` de la imagen y comparar con lo anterior antes del smoke; el smoke de un caso real MEJORAR + uno CREAR detecta incompatibilidad |
| **H17** registro de eventos sin exclusión | **sí** (`C8/C9/C10`) | ver E48-H17 | **`BLOCKS_PILOT`** | **sí** | una sola pestaña del piloto abierta; no abrir el panel mientras un caso está PROCESANDO |
| **H19** foto de 95 KB → ~460 MB | **sí** (E46 `D4d`) | acotado por el tope de 80 Mpx y 12 000 px; una foto de iPhone de 12 MP cuesta ≈ 124 MB; sólo material fabricado llega a 460 MB. Con 1 operador la carga es secuencial | `KNOWN_RISK_ACCEPTABLE` | no | memoria del plan de Railway ≥ 1 GB; no subir paneles gigantes |
| **H20** exclusión libera duplicados | **no** (cerrado) | `G1/G4` | cerrado (E47.8) | no | `exclude` sólo por CLI (E48-O1) |
| **H09** URLs sin detector de PII | **sí** (E46 `A3`) | sólo si el operador pega una URL con datos personales | `KNOWN_RISK_ACCEPTABLE` | no | no pegar enlaces con `?tel=`/`@` |
| **H11** credenciales no ASCII → 500 | **sí** (E46 `G2d/G2e`) | una `ESCALIMETRO_PASSWORD` con `ñ` haría imposible entrar | `KNOWN_RISK_ACCEPTABLE` | no | contraseña ASCII |
| **H12** `minutos="1e999"` → inf | **sí** (E46 `C8`) | sólo por error del operador; ensucia el total de minutos | `KNOWN_RISK_ACCEPTABLE` | no | escribir minutos normales |
| **H18** `foto-²` → 500 | **sí** (E46 `G4b`) | sólo por una URL fabricada a mano | `KNOWN_RISK_ACCEPTABLE` | no | — |
| **H22** `_EMAIL` cuadrático | **sí** en comentarios humanos; **no** en la ruta de errores de proveedor (`error` ≤ 2000 caracteres → 0,02 s) | un comentario de ≥ 20 000 caracteres seguidos tardaría segundos–minutos; sólo el operador lo envía | `KNOWN_RISK_ACCEPTABLE` / `NOT_REPRODUCED` en errores | no | comentarios cortos |
| **H23** residuo `e44/tmp*/plano_real.png` tras un `kill` | **sí** (E46 `E12`) | ninguna ruta lo sirve; sólo es legible con acceso al volumen | `KNOWN_RISK_ACCEPTABLE` | no | limpiar `e44/tmp*` tras un reinicio inesperado |
| **H24** `.dockerignore` ≠ `.gitignore` | **sí por código** (E46 `K8`; sin Docker) | sólo si se despliega desde una máquina de desarrollo (`railway up`) y no desde GitHub: copiaría `.data-*` a la imagen | `KNOWN_RISK_ACCEPTABLE` | no | desplegar **desde GitHub**, nunca `railway up` desde el equipo de desarrollo |

## Pruebas por capa

### Ceguera transformada (B)
- `B1` (36): JPEG q40/q90, ×0,5, ×2, giros 90/180/270, espejo, recortes 3/8/15 %, borde blanco 5/20 %, captura (y JPEG de la captura), perspectiva, grises, desenfoque → **bloqueados** (por `classify` salvo el ícono de 300 px, que cae por parecido).
  `B1b`: el mismo archivo y la miniatura de 300 px → bloqueados.
- `B2`, `B3` (7), `B4`: **bypass reproducidos** (arriba). `B3b` (6): el mismo plano coloreado re-codificado/reescalado/en grises/desenfocado → bloqueado.
- `B5/B5b/B5c`: fotos normales pasan; el rechazo es accionable y se recupera.
- `B6`: la petición al motor (inicial y corrección) no contiene nombre (`PLANO_SECRETO_9913`), sha, nombre guardado, carpeta oculta, bytes del plano real ni su marca interna.
- `B7`: 12 URLs × GET/HEAD con `Range`, mayúsculas, `%72eal`, `..%2f`, `../`, barras finales y rutas de E37 → 404/405; el GT no se sirve antes del reveal.
- `B8`: no se puede corregir tras el reveal (web ni API). `B9`: H04 (arriba).

### Concurrencia / idempotencia / costo (C)
- `C1` 4 envíos idénticos × 4 rondas → siempre `[303, 400, 400, 400]`, 4 casos. `C2` 6 cargas distintas → 6 casos, 6 proyectos E37, auditoría de ceguera OK. `C3` carga + exclusión simultáneas → sin pérdida.
- `C4` doble PROCESAR de MEJORAR ×4 casos → **1 publicación, 1 propiedad** cada vez. `C5` triple CORREGIR → **1 corrida hija** (`create_correction` ×1).
- `C6` FAILED sin asentar + 4 POST sobre el mismo estado → 1 reintento. `C7` DONE sin asentar + 3 POST → 0 corridas nuevas (pero ver H17).
- **`C11`, `C11a`, `C11b`: doble corrida pagada** (E48-C1). **`C8`, `C8b`, `C9`, `C10`**: H17.

### Recovery (D)
- `D1` evento vacío tumba `/`, `/panel` y el caso; la UI no ofrece reparación (clasificado). `D2` fallo de `_save`: ningún caso aceptado se pierde, la evidencia ajena queda intacta, el reintento entra al 2.º intento.
- `D3` caída entre reclamo y `create_started`: caso atascado, **sin gasto**, salida con exclusión + recarga. `D4` error hostil de proveedor: sin 500, sin secretos en lo que persiste la campaña, retry → DONE una vez.
- `D5` MEJORAR con PDF roto ×5: sin 409 ni huérfanas. `D6` reinicio con corrida en curso → FAILED → retry → DONE; historial inmutable.

### Cargas y rendimiento (E)
- `E1` 20 fotos de 4000×3000 (≈ 87 MB, bajo los 120 MB) → 303 en **< 12 s** (E46: 217 s). `E2` 21 fotos, 15 MB + 1 byte, HEIC falso, GIF y PNG truncado → 400 sin dejar caso ni proyecto. `E3` PNG que declara 20 000×20 000 → 400 sin decodificar.
  `E4`: MEJORAR **no** acota los píxeles (H07/H19), documentado y clasificado. Regresión E45.2 + E46 (222 tests: límites en el borde exacto, HEIC → JPG con pillow-heif 1.8.0, bombas, extensión × contenido): 222 passed, 0 omitidos.
- No se ejecutó ninguna bomba capaz de agotar memoria. HEIC real de iPhone (10 bits, Display P3), Railway y red móvil: **NO PROBADO**.

### Seguridad (F)
`F1`: todas las rutas POST × {Origin ajeno, `null`, Referer ajeno, otro puerto, `https` vs `http`, subdominio engañoso} → 403, salvo la excepción pública exacta. `F2`: sin métodos fuera de GET/POST. `F3`: la excepción es sólo `/planos/solicitar`.
`F4`: con contraseña, toda ruta GET menos `/healthz` y `/planos*` pide credenciales. `F5`: ninguna página del piloto ni archivo de datos contiene la clave ni rutas locales. Escaneo de secretos del diff: ver «Diff prohibido».

### Métricas del experimento (G)
`G1` FAILED → FAILED → DONE cuenta **una vez** (`captured 1, executed 1`); cerrar no completa; la UX sola no completa; reevaluar no suma; excluir libera el N; la recarga no hereda historial ni proyecto. `G2` DEMO no consume N ni bloquea a un real.
`G3` **20 + 20 → `PASS`**; excluir uno → `PARTIAL` (19); recargar → `PASS`; ninguna página del caso ni el panel dan error. `G4` MEJORAR: excluir y recargar el mismo plano → propiedad y caso nuevos, el viejo intacto.

### Camino feliz integrado, sin proveedor real (I)
`I1` MEJORAR (planta lista) y CREAR (corrección, cierre, reveal, evaluación resultado + UX), panel y resumen, índice HTML: sin 500 ni 409 inesperados. `I2` CREAR FAILED → reintento → DONE → cerrar → reveal → evaluar → excluir → recargar. `I3` **MEJORAR con el motor real** (sin sustituir `ensure_case`/`auto_prepare`) sobre dos planos de portal del repo: no cae, queda en NECESITA REVISIÓN
(lo honesto) o publica un resultado real; nunca un «después» inventado.

## Acceptance criteria
1. **PASS** — E46, los 9 REPORT E47 relevantes y `CURRENT_STATE` leídos antes de concluir.
2. **PASS** — regresión focal de H01/H02/H03/H05/H10/H16/H20/H21/E47.9 (tabla «Reprueba»), 620 passed.
3. **PASS** — adversarial integrado nuevo alrededor de las fronteras (96 tests); descubrió E48-C1 y E48-B1, que ningún test previo veía.
4. **PASS** — tabla de los 17 MEDIUM/LOW de E46 (10 + 7) con las seis columnas pedidas.
5. **PASS** — suite completa ejecutada, números exactos arriba y abajo.
6. **PASS** — camino feliz MEJORAR y CREAR (`I1–I3`).
7. **PASS** — ceguera con transformaciones adicionales del GT (`B1–B4`): **fallo del sistema auditado**, no de la auditoría.
8. **PASS** — concurrencia/retry/idempotencia (`C1–C11b`): **fallo del sistema auditado** (C1, H17).
9. **PASS** — cargas y rendimiento sin pruebas destructivas.
10. **PASS** — seguridad, same-origin, serving, PII técnica (`F1–F5`, `B7`, `D4`).
11. **PASS** — el diff de E48 son sólo tests de auditoría, este REPORT y CURRENT_STATE.
12. **PASS** — cero llamadas reales o pagadas.
13. **PASS** — cero deploy y cero merge.
14. **PASS** — sección `## VEREDICTO` con exactamente `NOT_READY`.
15. **PASS (veredicto negativo)** — `READY` no se emite: quedan reproducibles E48-C1 (costo duplicado), E48-B1 (ceguera) y E48-H17 (contamina un resultado y rompe el uso normal).
16. **PASS** — todo riesgo clasificado `KNOWN_RISK_ACCEPTABLE` exige una acción deliberada fuera del flujo normal, material patológico o afecta módulos ajenos al piloto, con la justificación en la tabla (H06 con severidad alta justificada).
17. **N/A** — no es `READY`; el smoke de un caso se define al re-auditar (ver «Exact next action»).
18. **PASS** — blockers ordenados por prioridad con su corrección mínima, sin implementarla.
19. **PASS** — este REPORT y `CURRENT_STATE.md` en el mismo commit.
20. **PASS** — el estado declarado no es más optimista que la evidencia: dos «cerrados» de E47 se reabren.

## Evidencia
Los tests y números están arriba; los sondeos no commiteados se reprodujeron como tests (`C8b`, `C11b`) o se citan con su cifra: matriz de transformaciones (75 combinaciones con GT de papel + 100 con GT coloreado),
doble costo con 87 MB reales (`create_initial` ×2 a 100 ms), `settle` simultáneo (66/40 con 2 hilos; 248/40 con 8), costo de `status()` (65 ms con 87 MB; 10 ms con 13 MB; 40 y 80 llamadas por
`/` y `/panel` con 40 casos), sanitizador (acotado a 2000 caracteres: 0,02 s; sin tope sería 2 s a 20 000 y 20 s a 60 000).

## Diff prohibido
`git diff 6324b1f HEAD -- src/` → vacío. `git diff a7d5c2f HEAD -- src/ .github/ webapp/ scripts/ Dockerfile requirements.txt pyproject.toml docs/E44_CAMPAIGN.md` → vacío.
Cambios del commit: `tests/test_e48_audit.py` (nuevo), `reports/E48_REPORT.md` (nuevo), `docs/ai-development/CURRENT_STATE.md`. Escaneo de secretos (`scripts/secret_scan.py`): **ningún hallazgo en los archivos de E48**; sólo marca un literal ficticio **preexistente** (`tests/test_e32_internal_console.py:227`, una clave de
mentira para un test), que no es de esta entrega ni se tocó. Los literales con forma de clave de E48 son de menos de 20 caracteres a propósito.
**No hubo deploy, merge, PR ni llamadas pagadas.**

## Regresiones
Respecto de lo que E47 declaró cerrado: **H03** (E48-C1, regresión de E47.8) y **H01** (E48-B1, cierre incompleto de E47.2) se reabren por una condición de frontera. Respecto de los E46 no tocados: H17 no cambió, pero ahora tiene
consecuencia medible. La suite de producto no mostró ningún test nuevo en rojo; el único fallo atribuible a la cadena es el documental de E47.2.

## Limitaciones
- Todo es de este sandbox (GitHub runner, Python 3.12.14, opencv 5.0.0, numpy 2.5.3): tiempos y memoria no son de Railway.
- **NO PROBADO**: Railway (deploy, volumen, memoria del plan, timeouts del proxy, reinicios reales), iPhone/Safari y red móvil (doble toque real, `meta refresh`, reintento del navegador), `docker build`, HEIC real de iPhone, OpenAI real (modelo `gpt-5.6-sol` sin verificar), fotos reales de portal (el corpus de falsos positivos es 1 foto real + 6 sintéticas), ramas contra GitHub (sin red).
- Los tiempos de C1 dependen de la CPU y del tamaño de la evidencia: la banda de 80–120 ms es la de esta máquina con `status()` ≈ 60–65 ms; en Railway se desplaza, no desaparece.
- `C8b` y `C11b` miden carreras con hilos: `C8b` se omite si la carrera no se reproduce; `C11b` falla si en esta máquina ninguna separación da dos corridas (lo que sólo ocurriría si se corrige C1).
- Los tests `…_DEFECTO_E48_*` fijan el comportamiento defectuoso a propósito: cualquier corrección los hará fallar y deberán actualizarse junto con ella.

## Decisiones requeridas
Ninguna decisión de producto nueva: los tres blockers son técnicos y su clasificación no la exige. Sigue pendiente **DR-11** (arrancar con `NOT_READY` o corregir antes): con este veredicto la opción «corregir antes» del DR-11 aplica; si Joaquín prefiere
arrancar con mitigaciones operativas (un solo toque por botón, una pestaña, planos fuera de la galería de fotos), es una decisión suya (`DEPLOY_GATE`) y el veredicto técnico sigue siendo `NOT_READY`.

## Commit / branch / PR
Rama `auto/e48-issue-31` (hija de `e48_final_pre_pilot_readiness_audit` = `522aa1e`, que sólo agrega `tasks/E48.md` sobre `a7d5c2f`). Un commit final con los tests de auditoría, este REPORT y `CURRENT_STATE.md`. La publica el workflow. **Sin PR, merge ni deploy.**
Base para la próxima TASK: **`auto/e48-issue-31`**.

## Exact next action
Joaquín lee el veredicto. ChatGPT escribe, **desde la base `auto/e48-issue-31`**, una TASK de reparación mínima (este REPORT no la crea ni la numera) con este orden:

1. **E48-C1** — nombre del reclamo estable (o candado por caso) y `status()` sin re-hashear: los tests `C11`, `C11a`, `C11b` pasan a exigir una sola corrida a toda separación.
2. **E48-H17** — exclusión por caso en `settle`/`record` (+ idempotencia de `correction`, `seq` con `O_EXCL`, lectura tolerante): `C8`, `C9`, `C10`.
3. **E48-B1** — parecido invariante a giro/espejo/recorte/borde y detector de dibujo de líneas sin papel blanco: `B2`, `B3`, `B4`.
4. Opcionales de bajo costo en la misma TASK: H06 (escritura atómica de eventos), H04 (negarse a corregir/cerrar si el GT ya no está oculto) y corregir el formato de `reports/E47.2_REPORT.md`.

Después, una nueva auditoría corta de esas fronteras. Sólo con `READY` se pasa al deploy controlado de FRONT (BACK intacto), la configuración separada del proveedor y UN caso real de smoke antes de abrir los 40.
