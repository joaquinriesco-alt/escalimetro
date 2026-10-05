# E46 REPORT — Auditoría adversarial nocturna pre-piloto

## Status
**PASS** — la auditoría se ejecutó completa y cumple sus criterios de aceptación (ver más abajo; lo que el
sandbox no puede observar está marcado **NO PROBADO**, no inferido).

**Veredicto de readiness del piloto para el primer caso real: `NOT_READY`.**
Hay **3 hallazgos BLOCKER** (los tres vienen de los *decision gates* de la TASK: fuga del plano real al
motor y riesgo de llamadas pagadas involuntarias), **4 HIGH**, 11 MEDIUM y 7 LOW; ninguno se corrigió
(la TASK lo prohíbe). Cada BLOCKER/HIGH tiene reproducción ejecutable. Las correcciones mínimas están
descritas, no implementadas; hay mitigaciones operativas (no son correcciones) en la lista final.

Base: `auto/e45_2-issue-17` (`2f99819`) → TASK `e46_night_adversarial_audit` (`c9a215b`, sólo agrega
`tasks/E46.md`) → esta rama `auto/e46-issue-18`. Dato verificado con las ramas remotas **de seguimiento
del checkout** (`git rev-parse origin/…`, `git diff --name-only`, `git merge-base --is-ancestor`); **no
se reverificó con `git ls-remote`** (el sandbox no permite red).

## Qué cambió
Sólo evidencia: 5 archivos de tests de auditoría (`tests/test_e46_adv_*.py`, 378 tests),
este REPORT y `CURRENT_STATE.md`. **Ningún archivo productivo** (`src/`, `webapp/`, `.github/`,
`requirements.txt`, `Dockerfile`, `scripts/`) cambió: ver «Diff prohibido». Los tests **caracterizan el
comportamiento actual**: los que documentan un defecto se llaman `…_DEFECTO_Hxx` y afirman el
comportamiento defectuoso; el día que se corrija, ese test fallará y debe actualizarse (lo dice cada
docstring). No imponen ninguna feature.

## Archivos principales
| archivo | dominios | tests |
|---|---|---|
| `tests/test_e46_adv_blindness.py` | B (ceguera), parte de C/I | 13 |
| `tests/test_e46_adv_campaign.py` | A (E44), C (estados), H (DEMO), I (evaluaciones) | 88 |
| `tests/test_e46_adv_resilience.py` | E (persistencia/fallos), F (concurrencia) | 37 |
| `tests/test_e46_adv_uploads.py` | D (cargas hostiles, HEIC, límites, bombas) | 161 |
| `tests/test_e46_adv_surface.py` | G (auth/origen/artefactos), J (móvil), K (deps/runtime), M (contradicciones) | 79 |

## Metodología
1. **Lectura**: `CLAUDE.md`, `CURRENT_STATE`, protocolo, TASK; código de `webapp/campaign.py`,
   `pilot.py`, `mobile_upload.py`, `reconstruction.py`, `auth.py`, `store.py`, de
   `domain/reconstruction/{projects,runs,groundtruth,engines}`, plantillas del piloto y CSS.
2. **Línea base**: suite completa antes de tocar nada (cayó en colección por `skimage`; se repitió con
   `--continue-on-collection-errors`).
3. **Sondeos exploratorios** (scripts temporales, no commiteados) para cada hipótesis; sólo lo que
   resultó informativo se convirtió en test.
4. **Falsación activa**: cada invariante declarado en doctrina/REPORTs se intentó romper; las
   condiciones de carrera se fuerzan con una **barrera en la ventana exacta** (determinista) y,
   aparte, se miden de forma «natural» (sólo arrancan juntas) con tasas observadas.
5. **Fuzz sembrado** (semilla fija) de formularios y matrices de extensión × contenido.
6. **Regresión amplia**: suite completa con los tests nuevos.

Tiempo (reloj de pared medido con `date -u`; no hay cronómetro por fase, el reparto es aproximado): la ejecución fue de
**≈ 1 h 20 min**, de 2026-10-05 00:57 UTC (primer comando) a ≈ 02:15 UTC (cierre), con 4 corridas completas de la suite
(6 min 02 s la línea base y 7 min 09 s, 7 min 04 s y 7 min 09 s con E46; casi todas en segundo plano, mientras se
seguía trabajando). Reparto aproximado:
lectura y mapa del código ≈ 10 min · línea base y sondeos exploratorios ≈ 15 min · tests de ceguera y campaña ≈ 10 min ·
persistencia y concurrencia ≈ 8 min · cargas, superficie y dependencias ≈ 10 min · segunda ronda de hallazgos
(descubiertos por fuzz y estrés: H16, H21, H22, H23, H24) ≈ 8 min · documentos y verificaciones ≈ 5 min. La TASK pedía una
auditoría «prolongada»: no se rellenó tiempo; se cerró cuando A–M quedaron cubiertos y los últimos sondeos sólo aportaban
hallazgos LOW. **Cobertura no agotada** (candidatos a una segunda pasada, no se auditaron a fondo): las superficies de E27–E36
(LAB, staging, propiedad del cliente, benchmark) más allá de auth/origen; la lógica (no sólo el fuzz de formularios, `C10`) de `/lab/reconstruction/*` fuera de lo que
usa la campaña; las páginas públicas E40/E43 más allá de sus tests; y las áreas **NO PROBADO** de abajo.

## Comandos ejecutados (resumen)
```
.venv/bin/python -m pytest tests/ -q --no-header -p no:cacheprovider --durations=15            # 1.ª: error de colección
.venv/bin/python -m pytest tests/ -q --no-header -p no:cacheprovider --durations=15 --continue-on-collection-errors   # línea base
.venv/bin/python -m pytest tests/test_e37_reconstruction_lab.py tests/test_e44_campaign.py \
    tests/test_e45_web_pilot.py tests/test_e45_2_mobile_upload.py -q
.venv/bin/python -m pytest tests/test_e46_adv_*.py -q
.venv/bin/python -m pytest tests/ -q --durations=10 --continue-on-collection-errors            # final, con E46
git diff 6324b1f HEAD -- src/ ; git diff <TASK> -- <prohibidos>                                 # diffs prohibidos
```
Más sondeos con scripts temporales (RSS muestreado en subproceso, perfil con `cProfile`, rondas de
hilos, estrés de 40 iteraciones). **No hubo red, ni deploy, ni merge, ni PR, ni llamadas pagadas**: el
motor «real» de CREAR (`openai_direct`) sólo se ejerció con `OPENAI_API_KEY` ausente (BLOQUEADO) o con
claves falsas y adaptadores de prueba; las llamadas a proveedor de los tests de CSRF están sustituidas
por un registro.

## Tests
baseline (antes de E46):  `9 failed, 2516 passed, 12 skipped, 7 xfailed, 1 error, 5 warnings in 362.85s (0:06:02)` @ `c9a215b`
                           (1.ª corrida sin `--continue-on-collection-errors`: `1 error in 5.11s`, no es resultado)
post-change (con E46):    **`9 failed, 2896 passed, 12 skipped, 7 xfailed, 7 warnings, 1 error in 429.20s (0:07:09)`** @ `auto/e46-issue-18`
                           (corrida completa final, con este REPORT y `CURRENT_STATE` ya escritos; 2896 − 2516 = 380 = los 378 tests de E46
                           + 2 casos parametrizados de `test_ai_handoff` que aparecen con el REPORT nuevo; los 9 fallos y el error de
                           colección son **exactamente los mismos** que en la línea base; 7 warnings = 5 previos + 2 `DecompressionBombWarning`
                           de las bombas de prueba)
E37 + E44 + E45 + E45.2:  `195 passed in 36.89s`
E46 (5 archivos):         `378 passed, 2 warnings in 68.21s`
test_ai_handoff.py:       `81 passed` con los documentos finales
(Corridas intermedias de la suite con E46, con menos tests: `9 failed, 2892 passed … in 429.94s` y `9 failed, 2895 passed … in 424.27s`; mismos fallos.)

**Fallos de la suite, clasificados** (la suite completa tarda ≈ 6 min en esta máquina, no los ≈12 que dice
`CLAUDE.md`):

| test | clase | evidencia |
|---|---|---|
| `test_e12_hardening::test_el_html_muestra_la_etapa_que_fallo` | **preexistente conocido** (lista de `CURRENT_STATE`) | artefactos regenerables fuera del repo |
| `test_e15_case_contract::test_las_rutas_de_artefactos_se_derivan_del_caso` | **preexistente conocido** | ídem |
| `test_e16_4_res_case::test_el_motor_coincide_con_el_baseline_vigente_declarado` | **entorno** | opencv-python-headless 5.0.0.93 + numpy 2.5.3 (cotas `>=`, sin lock); `src/` y el test son idénticos a `6324b1f` (`git diff` vacío) |
| `test_e16_5_localization::test_la_localizacion_de_403_por_ocr_no_cambio` | **entorno** | el binario `tesseract` no está en el sandbox (el `Dockerfile` sí lo instala) |
| `test_e17_width_representation` ×5 y `test_e18_topology_representation` (colección) | **entorno / H15** | `scikit-image` no está instalado **ni declarado** en `requirements.txt` ni `pyproject.toml` |

Los 7 últimos **no estaban** en la lista de 2 de `CURRENT_STATE` (cifra de M02.1 en la máquina de
desarrollo: `2312 passed · 2 failed`): son propios de este sandbox. **No hay regresión atribuible a
E37–E45.2**: `src/` y esos 6 archivos de test son byte a byte los de `6324b1f`. Hilos «no capturados» en
dos warnings de E32/E33/E36 (`no such table: runs` tras la limpieza del tmp): ruido previo de la suite.

## Matriz de cobertura A–M
Resultado: **P** = probado sin hallazgo · **H** = hallazgo(s) · **NP** = no probado (se dice por qué).

| dominio | resultado | hallazgos | cobertura (tests) |
|---|---|---|---|
| **A** integridad E44 (provenance, dedup, PII, N) | **H** | H09, H20, H22, limitaciones A1b/A3b/A7/A10 | `campaign::A1–A11`; bundles hostiles ×13 parametrizados, symlink, GT=input |
| **B** ceguera CREAR antes del reveal | **H** | **H01**, H04, H23 | `blindness::B1–B9`: rastreo de TODA superficie GET + archivos + tablas + petición al proveedor en 3 etapas |
| **C** máquina de estados CREAR/MEJORAR | **H** | H03, H05 | `campaign::C1–C10`; fuzz sembrado (400 envíos al piloto, 500 a las rutas de E37); ids mal formados |
| **D** cargas (JPG/JPEG/PNG/WEBP/HEIC/HEIF/PDF…) | **H** | H07, H16, H19 | `uploads::D1–D7`: 161 tests (nombres, matriz ext×contenido, bordes exactos, bombas, HEIC, lotes, m²) |
| **E** persistencia/atomicidad, reintentos | **H** | H05, H06, H08, H21, H23 | `resilience::E1–E12`: fallos y kills simulados en ≈ 15 escenarios (guardado del manifiesto, E37 a mitad de camino, evento truncado, corte entre cierre y reveal, reinicio con corrida en cola, cola que no arranca, motor que explota, clave repetida en un error, `kill -9` a mitad de la carga…) |
| **F** doble clic, repetición, concurrencia | **H** | **H02**, **H03**, H17 | `resilience::F1–F9`: ventanas forzadas + rondas naturales |
| **G** auth, mismo origen, artefactos, ids/tokens | **H** | **H10**, H11, H13, H14, H18, limitación G2f | `surface::G1–G6` (incl. 15 variantes de Origin/Referer/X-Forwarded-Proto, fuzz de `archivo/<cual>`, ids cruzados) |
| **H** DEMO contra real, contaminación de métricas | **P** (+ limitación) | — (índice mezcla, ver abajo) | `campaign::H1–H6` (incl. borde 20+20 y exclusión) |
| **I** evaluaciones, cierre/reveal, no corrección posterior | **H** | H04, H12 | `campaign::C1/C2/C3/I1`, `blindness::H04` |
| **J** compatibilidad móvil inferible | **P** + **NP** | H03/H02 por falta de guardia de doble envío | `surface::J1–J5` (HTML, CSS, nombres de campos, `accept`); **NP**: iPhone/Safari reales |
| **K** dependencias/build/runtime 3.12 | **H** | H15, H24 | `surface::K1–K8`; **NP**: `docker build`, wheel de `pillow-heif` en la imagen |
| **L** regresión amplia | **P** | — | suite completa (ver «Tests») |
| **M** deuda que bloquea el primer caso real | **H** | H05, H16, H21 + contradicciones | `surface::M1–M4` + esta lista |

## Hallazgos
Formato: severidad · clase (**D**emostrado / **R**iesgo plausible no reproducido / **L**imitación
conocida) · reproducción · impacto · alcance · ¿lo detectaba un test previo? · corrección mínima **sugerida,
no implementada**. Todos los tests citados están en `tests/test_e46_adv_*.py`; se corren con
`.venv/bin/python -m pytest tests/<archivo> -k "<id>"`.

### BLOCKER

**E46-H01 · El plano real, re-codificado y subido como «foto», entra al motor y la auditoría de ceguera da OK** · BLOCKER · D
- *Qué*: la ceguera se hace cumplir por identidad byte a byte (sha256). Si entre las fotos va el mismo dibujo en otra
  codificación o tamaño —lo habitual en una galería de portal, donde el plano es una imagen más—, E37
  (`projects.add_asset`) lo marca `looks_like_plan=1` y devuelve una nota, pero `campaign._prepare_create` descarta
  esa nota, el caso se acepta, `blind_audit` devuelve `ok: True` y el motor lo recibe.
- *Repro*: `blindness::test_DEFECTO_H01_…` (JPEG de calidad 90 del plano real subido como foto: `marcadas == [1, 0]`,
  `blind_audit == {"ok": True}`, la imagen está en `build_request(...).images`, la página del piloto no avisa) y
  `blindness::test_B8_…` (mismo dibujo en PNG de 200×150).
- *Impacto*: el experimento CREAR deja de medir lo que dice medir **sin que nada lo avise**; los 20 casos
  podrían llevar resultados inválidos. Es el gate «fuga del GT».
- *Alcance*: toda carga CREAR (web y bundle). *Test previo*: ninguno (los de E37/E45 usan un solo input por sha).
- *Corrección mínima*: tratar `looks_like_plan` como rechazo (o aviso bloqueante con confirmación) en
  `_prepare_create`, y comparar además con un hash perceptual del plano real; mostrar la nota en el piloto.

**E46-H03 · Doble disparo de PROCESAR → dos corridas pagas (CREAR) / dos propiedades (MEJORAR)** · BLOCKER por *gate* («riesgo de llamadas pagadas involuntarias») · D (ventana forzada y rondas naturales de 0–5 ms)
- *Qué*: `start_create` comprueba «ya lanzada» y registra `create_started` en pasos separados, sin candado; la web
  fija `confirm_paid=True`. Dos peticiones simultáneas pasan ambas la comprobación.
- *Repro*: `resilience::test_F4_…` (barrera en `runs.create_initial`: 2 corridas, 2 llamadas al motor, 2
  `create_started`); `test_F7_…` (MEJORAR: 2 propiedades). Natural, 60 de 60 rondas con arranque simultáneo y 20 de 20
  con 5 ms de separación dan 2 corridas; **a 10, 20, 40, 80 y 150 ms: 0 de 100** (una persona que toca dos veces no
  llega a ese margen). La clasificación BLOCKER sigue la letra del gate; la probabilidad medida es baja.
- *Impacto*: un segundo cobro por doble disparo (reintento de red, dos pestañas, script). Acotado a 1 llamada extra por disparo.
- *Alcance*: `procesar`, `corregir` (misma estructura). *Test previo*: ninguno.
- *Corrección mínima*: reclamo atómico (crear el archivo de evento con nombre fijo con `open(..., "x")`, o una fila con `UNIQUE`)
  **antes** de `create_initial`/`improve_started`; es la misma técnica que ya usa `record` para los singletons.

**E46-H10 · ~67 rutas POST sin guarda de mismo origen; con `OPENAI_API_KEY` un POST ajeno llega a la llamada paga** · BLOCKER por *gate* · D (alcance) / R (llamada real: sustituida)
- *Qué*: sólo `/lab/reconstruction/*` y `/lab/campaign/e44/*` rechazan un `Origin`/`Referer` ajeno (`reconstruction._guardas`).
  Las demás (staging, LAB, benchmark, propiedades del cliente, pedidos, `/upload`, `/review`, `/settings`…) dependen sólo
  de HTTP Basic, que el navegador reenvía solo: la razón por la que E37 puso la guarda. `docs/E37` la describe para E37, no hay
  nada equivalente para el resto.
- *Repro*: `surface::test_DEFECTO_H10_…` (enumera `url_map`: 15+ rutas guardadas y ≥ 60 sin guarda, incluidas
  `staging.generate`, `staging.retry`, `lab.benchmark_run`, `lab.smoke`, `lab.approve_provider`, `pedidos.generar`,
  `potential.analizar`, `upload`) y `test_DEFECTO_H10b_…` (con `OPENAI_API_KEY` presente —el piloto de CREAR la exige—,
  `POST /lab/benchmark/smoke/openai` con `Origin: http://evil.example` llega a `staging.smoke_test`: «UNA llamada real», sin
  confirmación; **la llamada está sustituida por un registro, no se hizo ninguna real**).
- *Impacto*: una página ajena abierta en el navegador del operador con sesión activa puede disparar gasto en proveedores
  (y escrituras en el LAB). Requiere que el operador visite esa página.
- *Alcance*: toda la app salvo E37 y el piloto. *Test previo*: sólo los de E37/E45 sobre sus propias rutas.
- *Corrección mínima*: mover la guarda a un `before_request` del `app` para todo POST (excepto `/planos/solicitar`, que es público a propósito).

### HIGH

**E46-H02 · `import_upload`/`_import_case` no resiste la concurrencia: pérdida silenciosa de casos, 500 y destrucción de evidencia** · HIGH · D
- *Qué*: `_import_case` hace `load()` → trabajo largo (copia de evidencia, proyecto E37, plano real) → `_save()` del manifiesto
  **completo**, sin candado; y su `except` hace `rmtree(case_dir)`, que para el mismo material es la carpeta del caso ganador.
- *Repro*: `resilience::test_F1_…` (barrera tras `load()`: dos cargas **distintas** devuelven ambas un id válido y el manifiesto
  conserva una; la otra queda con evidencia y proyecto E37 sin caso; la web la redirige a un 404); `test_F1b_…` natural: **30 de
  30 rondas** pierden una; `test_F2_…` (intercalado forzado: el 2.º envío del mismo material borra la evidencia del 1.º → `URL_ONLY`);
  `test_F3_…` natural de doble envío idéntico: **20 de 25 rondas 500+500 sin caso** (`PermissionError`/`FileNotFoundError`), 5 de 25
  303+303 con un solo caso.
- *Impacto*: un doble toque en «SUBIR MATERIAL» (no hay guardia de cliente: `J4`) o dos pruebas a la vez pierden o ensucian
  casos del N; sin aviso. **H16 lo hace más probable** (la petición dura minutos).
- *Alcance*: ambas pistas. *Test previo*: ninguno (ni E44 ni E45 ni E45.2 ejercitan concurrencia).
- *Corrección mínima*: un `threading.Lock` alrededor de «chequeo de duplicados → creación → `_save`» (el proceso es único:
  `--workers 1`), y que el `rmtree` del `except` sólo borre lo que esa llamada creó.

**E46-H05 · Una corrida CREAR fallida es definitiva: no hay reintento y la propiedad no se puede volver a cargar** · HIGH · D
- *Qué*: el fallo del proveedor (timeout, 429, modelo inexistente) o un reinicio de Railway durante la corrida (`store.reset_orphans`
  pasa `QUEUED/RUNNING` a `FAILED`, «no se reanuda») se asienta como `pipeline` FAILED → caso «SIN RESULTADO». `start_create`
  exige `CAPTURED`; la página no ofrece reintento (sí lo ofrece para el bloqueo por credencial); y re-subir la misma propiedad
  choca con el duplicado, **también tras `exclude`** (H20).
- *Repro*: `resilience::test_E6_…` (reinicio con la corrida en cola), `test_E6b_…` (EngineError transitorio), `test_E7_…`
  (cola que no arranca: PROCESANDO hasta reiniciar), `campaign::test_A9_…`.
- *Impacto*: el **primer** caso real es el más expuesto (modelo `gpt-5.6-sol` sin verificar —ver NO PROBADO—, claves, timeouts de
  600 s): un error de configuración quema un caso de los 20 sin salida desde la web ni por CLI.
- *Alcance*: CREAR (MEJORAR tiene «volver a intentar»). *Test previo*: ninguno.
- *Corrección mínima*: permitir un nuevo `create_started` cuando el último `pipeline` es FAILED y no hay cierre (registrando el
  intento anterior), y que `_find_duplicate` ignore los excluidos. **Qué cuenta como «ejecutado» tras un reintento es una decisión de
  experimento de Joaquín: ver DECISION_REQUIRED DR-12.**

**E46-H16 · Cada foto de CREAR cuesta ~11–12 s de CPU: 20 fotos de 12 MP = 217 s en UNA petición** · HIGH · D (medido aquí; Railway **NO PROBADO**)
- *Qué*: `projects.add_asset` llama a `_looks_like_plan` → `classify.features`, que cuenta colores con `np.unique(q, axis=0)` sobre
  todos los píxeles (ordena N filas de 3 columnas). Crece más que lineal con la resolución.
- *Repro*: `uploads::test_D4g_…` (forma del costo con imágenes chicas) y medidas de esta auditoría: 2 fotos de 12 MP → 24,2 s
  (perfil: 23,3 s en `ndarray.sort`); **20 fotos de 12 MP (78 MB) → 217 s**; 1 HEIC de 12 MP → 10,3 s. Un caso de 6–15 fotos
  (el rango que supone E45.2) toma ≈ 70–175 s.
- *Impacto*: la petición se acerca o supera los 180 s del `--timeout` de gunicorn (con workers `gthread` ese límite no corta un hilo
  ocupado, pero un proxy o el navegador móvil sí pueden cortar la conexión: **NO PROBADO** en Railway); el iPhone queda esperando sin
  ninguna señal de progreso (la página no usa JS); el reintento dispara H02. Fotos de 48 MP, ×4.
- *Alcance*: toda carga CREAR por la web. *Test previo*: ninguno (los tests usan imágenes de 64×48).
- *Corrección mínima*: clasificar sobre una copia reducida (≤ 512 px) o saltarse `_looks_like_plan` hasta que H01 la reemplace; idealmente
  procesar la carga fuera de la petición.

**E46-H21 · Un error de proveedor (o de MEJORAR) con una racha de ≥ 9 dígitos mata el panel y la página del caso** · HIGH · D
- *Qué*: `record()` pasa el texto libre `error` por el detector de PII (teléfonos: 9+ dígitos con separadores). El mensaje de un fallo
  —un timestamp, un id de petición con una racha de dígitos, «ticket 123-456-7890»— lo dispara; `settle()`, que corre en **cada GET**
  del caso y del panel, lanza `CampaignError`, el `pipeline` nunca se registra, la corrida FAILED queda sin asentar.
- *Repro*: `resilience::test_E11_…` (error con `1700000000`: la página del caso y **`/panel` dan 500 para todos los casos**; el caso
  queda PROCESANDO; `/` y las páginas de otros casos abren), `test_E11b_…` (qué mensajes rompen y cuáles no),
  `test_E11c_…` (MEJORAR: `improve_started` no se registra, `procesar` da 409 «el caso contiene un email o teléfono» y deja una
  propiedad huérfana por intento). En estrés, **2 de 40** `procesar` de MEJORAR con un PDF roto dieron 409 de forma esporádica
  porque el texto del fallo trae rutas con ids aleatorios; ese flake lo destapó (y se compensó en `uploads::test_D7_…`).
- *Impacto*: un solo fallo del proveedor con la mala racha de dígitos deja inutilizable el panel del piloto hasta tocar archivos a mano.
- *Alcance*: CREAR y MEJORAR. *Test previo*: ninguno.
- *Corrección mínima*: no pasar por `_no_pii` el texto generado por el sistema (sólo lo que escribe una persona) y que `settle` registre
  el error sanitizado en vez de dejar propagar `CampaignError`.

**Reproducción rápida de los BLOCKER y HIGH** (cada comando corre en segundos, sin red ni gasto):
```
.venv/bin/python -m pytest tests/test_e46_adv_blindness.py -k "H01 or B8" -q            # H01
.venv/bin/python -m pytest tests/test_e46_adv_resilience.py -k "F4 or F7" -q            # H03
.venv/bin/python -m pytest tests/test_e46_adv_surface.py -k "H10" -q                    # H10
.venv/bin/python -m pytest tests/test_e46_adv_resilience.py -k "F1 or F2 or F3" -q      # H02
.venv/bin/python -m pytest tests/test_e46_adv_resilience.py -k "E6 or E7" -q            # H05
.venv/bin/python -m pytest tests/test_e46_adv_campaign.py -k "A9" -q                    # H05/H20
.venv/bin/python -m pytest tests/test_e46_adv_uploads.py -k "D4g" -q                    # H16 (forma del costo)
.venv/bin/python -m pytest tests/test_e46_adv_resilience.py -k "E11" -q                 # H21
```

### MEDIUM

**E46-H04 · Reveal fuera de banda por el laboratorio de E37** · MEDIUM · D · `blindness::test_DEFECTO_H04_…`
`/lab/reconstruction/p/<id>/revelar` sigue vivo para un proyecto de la campaña. Si se revela por ahí la campaña no se entera: se puede
seguir corrigiendo «a ciegas» y `cerrar` se acepta (`closure.gt_state_at_closure == "REVEALED"` es el único rastro; E37 sí marca la
corrida hija `gt_state_at_creation == REVEALED`). *Corrección*: `start_correction`/`close_blind` deben negarse si el proyecto E37 ya no está en `HIDDEN_FROM_ENGINE`.

**E46-H06 · Un evento ilegible envenena toda la campaña** · MEDIUM · D · `resilience::test_E3_…`, `test_E3b_…`, `test_E4_…`
`events()` no tolera un archivo truncado: un corte a mitad de escritura (`open("x")` + `json.dump`, no atómico) o disco lleno hace que
`/`, `/panel`, el caso, `count()` y `summary()` den 500; se recupera borrando el archivo a mano. *Corrección*: escribir a un temporal y
`os.link`/`os.replace`; leer con tolerancia y marcar el evento como corrupto.

**E46-H07 · MEJORAR no recibió el endurecimiento de E45.2** · MEDIUM · D (E45.2 lo declaró «no cubierto») · `resilience::test_E10_…`, `test_E10b_…`; `uploads::test_D4e_…`, `test_D7_…`
`mejorar_post` usa `f.read()` con el tope de 1200 MB heredado de E37; un PDF/PNG/JPEG roto o con 100 Mpx entra (sólo se miran 8 bytes
de cabecera) y la falla aparece después (queda registrada como NECESITA REVISIÓN). El mismo PNG de 10 000×10 000 se rechaza como plano
real de CREAR y se acepta como plano de MEJORAR; uno de 30 000×30 000 (~1 MB) haría pedir ~5 GB a OpenCV (**NO ejecutado**:
riesgo plausible no reproducido a esa escala). *Corrección*: pasar el plano por `mobile_upload.validar_plano`/`leer_limitado`.

**E46-H08 · La carga no es atómica ante fallos intermedios** · MEDIUM · D · `resilience::test_E1_…`, `test_E2_…`, `test_E9_…`, `test_E12_…`
Un fallo en `_save` o dentro de E37 deja proyectos E37 (con su plano real) huérfanos y, tras `_save` caído, un reintento 500 por la
evidencia de sólo lectura; en MEJORAR, una propiedad huérfana por intento. *Corrección*: orden «reservar → crear → publicar» con limpieza simétrica.

**E46-H13 · El formulario público de pedidos escribe hasta 40 MB sin cuenta ni freno, en el mismo volumen** · MEDIUM · D (E41 lo declaró) · `surface::test_DEFECTO_H13_…`
`POST /planos/solicitar` valida 8 bytes de cabecera: un «PDF» de 30 MB de basura se acepta y persiste; 12 repeticiones sin 429; sin
control de espacio. Puede llenar `/data`, donde vive el piloto. *Corrección*: tope de frecuencia y de espacio, y validar contenido.

**E46-H14 · Ninguna respuesta lleva cabeceras de seguridad** · MEDIUM · D · `surface::test_DEFECTO_H14_…`
Sin `X-Frame-Options`/`frame-ancestors`: la web piloto puede enmarcarse (los botones PROCESAR/CERRAR gastan o revelan) y la guarda de
Origin no lo frena (el clic nace dentro de nuestra página). Sin `nosniff` al servir imágenes (`uploads::test_D2f_…`: un JPEG con HTML
pegado se sirve como `image/jpeg`).

**E46-H15 · Dependencias: no declaradas, sin pins, `requirements.txt` ≠ `pyproject.toml`** · MEDIUM · D · `surface::test_K2_…`, `test_K3_…`, `test_K5_…`
`skimage` (usado por `staging.py` dentro de un `try/except: pass`, y por dos módulos de test) no está en ningún archivo: en producción el
chequeo SSIM de ambientación se omite en silencio y 6 tests no corren. Todas las cotas son `>=` sin lock (el baseline del motor ya difiere en
esta máquina). `requirements.txt` dice ser «espejo de pyproject» y tiene 3 paquetes más (flask, gunicorn, pillow-heif); `pyproject` pide
Python `>=3.10` y la imagen es 3.12. `PIL` entra sólo como transitiva.

**E46-H17 · El registro de eventos no es seguro bajo concurrencia** · MEDIUM · D (ventana forzada) · `resilience::test_F5_…`, `test_F6_…`
`settle()` (en cada GET) registra el «singleton» `pipeline` dos veces si dos vistas coinciden; `seq = len(listdir)+1` colisiona: del mismo
tipo uno falla (`FileExistsError`), de distinto tipo ambos se guardan con el mismo `seq` y el orden lo decide el nombre. Infla métricas
(`human_prompts`) y desordena la cronología. *Corrección*: el mismo candado de H02/H03.

**E46-H19 · Una foto de 95 KB puede costar ~460 MB de memoria** · MEDIUM · D · `uploads::test_D4d_…`
Un PNG gris de 8 900×8 900 (79,2 Mpx, bajo el tope de 80 Mpx) pesa 95 KB y entre la validación de Pillow y el `cv2.imread(IMREAD_COLOR)` de
E37 sube el RSS de 42 a 505 MB (una foto de 12 MP: 42→124 MB). Con `--threads 8`, varias a la vez. **Contradice** la frase de E45.2
«una imagen pequeña en bytes pero enorme en píxeles no agota memoria» (C-1). *Corrección*: bajar `MAX_PIXELES` o decodificar con `draft`/reducción.

**E46-H20 · `exclude` no libera la propiedad para volver a cargarla** · MEDIUM · D · `campaign::test_A9_…`
`_find_duplicate` recorre también los excluidos. Junto con H05 no queda camino de recuperación salvo editar el manifiesto. Además `exclude`
reescribe el manifiesto sin evento (no es de sólo inserción: `A8`).

### LOW

- **E46-H09** · D · `campaign::test_A3_…` — el detector de PII no revisa `source_urls`: un enlace con `?contacto=juan@correo.cl&tel=+569…`
  o `usuario:clave@host` se guarda y sale en el índice. *Corrección*: pasar las URLs por `_no_pii` (y quitar `userinfo`).
- **E46-H11** · D · `surface::test_G2d_…`, `test_G2e_…` — `hmac.compare_digest` con `str` no ASCII lanza `TypeError`: credenciales con tilde dan 500
  (sin bypass), y una `ESCALIMETRO_PASSWORD` con `ñ` haría imposible entrar. *Corrección*: comparar `bytes` (`.encode()`).
- **E46-H12** · D · `campaign::test_C8_…` — `minutos="1e999"` se acepta como `inf` y el total de minutos del resumen queda `inf`.
- **E46-H18** · D · `surface::test_G4b_…` — `GET …/archivo/foto-²` da 500 (`"²".isdigit()` es verdadero e `int()` falla); `foto-１` (fullwidth) se interpreta como 1.
- **E46-H22** · D · `campaign::test_A11_…` — `_EMAIL` es cuadrática y no suelta el GIL: 80 000 caracteres ≈ 20 s; el detector corre antes del tope de
  2000 y el formulario no recorta: un comentario de 500 KB congelaría el proceso ~13 min (sólo el operador puede enviarlo).
- **E46-H23** · D · `resilience::test_E12_…` — un kill a mitad de la carga deja el plano real en claro como `DATA_DIR/e44/tmp*/plano_real.png` (con
  `bundle.json`); ninguna ruta lo sirve, ningún arranque lo limpia, `blind_audit` no lo mira.
- **E46-H24** · R (sin Docker) · `surface::test_K8_…` — `.dockerignore` sólo excluye `.data`; `.gitignore` excluye además `.data-*/` (donde viven los
  datos de trabajo) y `.env*`. Un `docker build .`/`railway up` desde una máquina de desarrollo —no desde un clon limpio de GitHub— los copiaría a la
  imagen con `COPY . .` (junto con `node_modules/`). *Corrección*: igualar `.dockerignore` a `.gitignore`.

### Limitaciones conocidas (no son defectos nuevos)
`A1b` la clave de duplicados descarta la query (dos avisos que sólo difieren en `?id=` chocan) y no unifica `m.`, `index.html`, puerto, `//`,
`%31` · `A3b` el detector no ve texto ofuscado y da falso positivo con «85 90 95 100 m2» · `A7` el regex de id acepta un `\n` final (sin efecto:
404) · `A10` todo caso web se etiqueta `OFFICE` y con origen mínimo · `D4b` >160 Mpx informa «dañado» · `D4f` `Image.MAX_IMAGE_PIXELS` queda fijado
en todo el proceso · `D6` una foto repetida deja 2 assets en el manifiesto y 1 en E37 · `F9` sin tope de correcciones ni de gasto (cada una paga)
y `cost_basis` «unknown» · `G2f` sin límite de intentos de contraseña (una cuenta, 300 intentos seguidos → 300 × 401) · `D2b` el plano real no
acepta HEIC (una foto de iPhone de un plano en papel debe convertirse antes) · `H5` el índice HTML mezcla casos DEMO y reales sin rótulo · `I1` los eventos no tienen hash ni cadena (editar un
JSON a mano cambia el resumen sin rastro) y `record("correction")` por API se acepta tras el cierre (la web lo impide) · `E4` un manifiesto
ilegible tumba la campaña · el GET de una página del caso escribe (`settle`).

## Invariantes confirmados
- **GT no filtra antes del reveal por ninguna superficie observable** salvo H01 (el mismo dibujo subido como foto) y H23 (residuo tras un kill):
  páginas del piloto y de E37 (todas las rutas GET, status.json, svg, assets), cabeceras, archivos bajo `DATA_DIR` salvo `reconstruction_gt/`,
  todas las tablas salvo `recon_ground_truth`, eventos E44, índice HTML, petición que armaría `openai_direct`, camino BLOQUEADO — en 3 etapas
  (`B1`, `B9`), con un control positivo que sí lo encuentra tras el reveal (`B2`). Los nombres de usuario (unicode, traversal) no llegan a disco ni a la base (`B4`).
  `archivo/real` antes del reveal es indistinguible de un archivo inexistente (`G5`).
- Una URL sin assets verificados no es un caso ni suma a ningún N; el material alterado o perdido saca al caso de todo N (`A4`, `A5`).
- Los DEMO nunca cuentan (ni en `count`, ni en `summary`, ni en evaluaciones), no se pueden crear desde la web, no bloquean ni son bloqueados por un real, y un caso real no corre el motor fixture (`H1–H4`). El borde 20+20 → PASS y excluir uno → PARTIAL (`H6`).
- Cierre antes de reveal y reveal antes de evaluar, por la web y por la API; los singletons son inmutables (`C1–C3`); un corte entre el cierre y el reveal, o entre el reveal de E37 y el evento, falla cerrado y se recupera repitiendo «cerrar» (`E5`, `E5b`).
- Las evaluaciones se agregan (con `supersedes_seq`) y no se reescriben; un caso cuenta una vez; sin evaluación antes del reveal (`C1`, `F8`).
- La clave del proveedor no sobrevive en ningún archivo, tabla ni página aunque el motor la repita en un error (`E8b`); el EXIF de una foto no viaja al proveedor (`D5d`).
- Toda ruta (menos las 7 públicas esperadas) exige credenciales; ids de otro proyecto/corrida no abren recursos ajenos; el 404 es uniforme (`G1`, `G2`, `G4d`, `G6`). Tokens públicos con `secrets`/`uuid4`.
- El piloto y E37 sí rechazan `Origin`/`Referer` ajenos en las 15 variantes probadas (incl. `null`, esquema, puerto, subdominio engañoso) (`G3`).
- Los límites de E45.2 se cumplen en su borde exacto (20/21 fotos, 15 MiB ±1, 120 MiB ±1, 25 MiB ±1, 147 MiB → 413), la lectura se corta al pasarse, y los rechazos no dejan residuos (`D3`); bombas >80 Mpx o >12 000 px se rechazan antes de decodificar (`D4`); extensión × contenido, 92 combinaciones (`D2`, `D2b`, `D7b`).
- 900 envíos de basura con semilla fija (NUL, controles, RTL, emoji, inyección, plantillas, `1e999`/`nan`/`inf`): 400 al piloto (`C9`) y 500 a las
  rutas de E37 (`C10`), ningún 5xx.

## Invariantes rotos
GT ciego (H01) · una carga o un disparo = una vez (H02, H03) · «los resultados son de sólo inserción» y «el estado se deriva» (H17, H06, H20) ·
«cada fallo queda como resultado, nunca éxito» sin salida para el operador (H05) · guarda de origen en las rutas con efecto de gasto (H10) ·
«una imagen chica no agota memoria» (H19).

## Áreas no observables (NO PROBADO)
- **Railway**: deploy, healthcheck, volumen `/data` y permisos, memoria/CPU del plan, timeouts del proxy, reinicios reales. Los tiempos de H16
  son de esta máquina (GitHub runner), no de Railway.
- **iPhone/Safari/navegador real**: selector de archivos con `accept` HEIC, conversión «Originales/Más compatible» de iOS, `meta refresh` de
  6 s, subida por red móvil, CSRF/clickjacking en un navegador real (se infieren de las cabeceras y del código).
- **`docker build`** (sin Docker) y la disponibilidad de la wheel `pillow-heif` en la imagen (aquí 1.8.0 + libheif 1.23.4 funcionan en 3.12.14;
  este libheif **no** decodifica AVIF).
- **OpenAI real**: no hay clave ni red. El modelo por defecto `gpt-5.6-sol` (`ESCALIMETRO_RECON_OPENAI_MODEL` lo reemplaza) y la validación
  estricta del esquema nunca se ejercieron; el costo no se registra (`cost_basis: unknown`).
- **Ramas contra GitHub**: sin red; sólo ramas remotas de seguimiento del checkout.
- Un HEIC real de iPhone (10 bits, Display P3, ráfagas): los de prueba salen de `pillow-heif` (8 bits).

## Falsos positivos descartados
- **Desajuste de límites entre capas** (15 MiB de foto vs `lab_assets.MAX_MB`): ese tope es 40 MB, no hay desajuste.
- **Doble clic humano que duplica PROCESAR**: no reproducible con ≥ 10 ms de separación (0/100); por eso H03 se describe con su ventana real.
- **Leak del EXIF/GPS al proveedor**: la evidencia conserva el original, pero la petición re-codifica (`D5d`).
- **SSRF en `/property/analizar`**: `fetcher.py` valida IPs globales y cada redirección; no es un hallazgo.
- **Rutas sin credenciales** (8 en una primera enumeración): eran artefactos de mi relleno de URLs; las públicas reales son las 7 esperadas.
- **«Rutas POST sin guarda» (primera enumeración)**: el cliente de pruebas fijaba un `Origin` propio por defecto; se rehízo con cabeceras explícitas.
- **`/properties/new` 403**: es el corte por producto (entitlement), no una guarda de origen.
- Nombres con `"`/salto de línea fallaban por el codificador multipart de werkzeug, no por el servidor; se prueban ya escapados como lo hacen los navegadores.
- Un 409 intermitente de MEJORAR en mi propia corrida: no era una carrera de los tests sino H21.

## Deuda previa distinguida de regresiones nuevas
Ninguna regresión nueva atribuible a E37–E45.2: las suites de esos componentes pasan completas (195) y los 7 fallos adicionales de la suite son de
entorno con `src/` y tests idénticos a `6324b1f`. Todos los hallazgos son **de origen** (presentes desde que se introdujo cada pieza):
H10 (E27/E37), H01 y H05 (diseño de E44/E45), H02/H03/H17 (E44/E45), H16 (E37 `add_asset`), H21 (E44 `_check_payload`), H07 (E45.2 lo declaró),
H13 (E41 lo declaró), H15 (E17/E18).

## Contradicciones entre TASKs, REPORTs, CURRENT_STATE y código
- **C-1** `E45.2_REPORT`: «una imagen pequeña en bytes pero enorme en píxeles no agota memoria» ↔ H19 (`M2` fija el texto).
- **C-2** `requirements.txt`: «Espejo de [project.dependencies]» ↔ difiere en 3 paquetes (H15).
- **C-3** `CURRENT_STATE` («Tests»): `2312 passed · 2 failed` (M02.1) ↔ esta suite; ya actualizado.
- **C-4** `E44`: «resultados de sólo inserción» ↔ `exclude` reescribe el manifiesto (A8) y `settle` puede duplicar singletons (H17).
- **C-5** `pilot.py` («el plano real nunca se sirve ni se nombra antes del reveal») ↔ cierto en la web del piloto, pero el reveal de E37 sigue vivo (H04).
- **C-6** `CLAUDE.md`: «≈12 min» ↔ 6 min 03 s medidos aquí.
- **C-7** `E45.2` (TASK): pide `reports/E45_1_REPORT.md`/`reports/CURRENT_STATE.md` (nombres viejos); el REPORT ya lo anota. Sin consecuencias.
- **C-8** `E41`/`E45.2` recomiendan «una TASK corta» (freno de abuso; cota de lectura de MEJORAR) que nadie escribió: son H13 y H07.

## Acceptance criteria
1. **PASS** — este REPORT, veredicto `NOT_READY` sustentado por evidencia.
2. **PASS** — matriz A–M con resultado por dominio.
3. **PASS** — los 3 BLOCKER y los 4 HIGH tienen reproducción concreta; los riesgos no reproducidos (llamada real de H10, 5 GB de H07, Railway de H16) están marcados.
4. **PASS** — suite completa ejecutada; resultados y clasificación exactos arriba; nada quedó fuera salvo lo no observable.
5. **PASS** — E37+E44+E45+E45.2 (195) y los 5 archivos E46.
6. **PASS** — auditoría explícita de GT por todas las superficies (`B1–B9`); la fuga que sí existe (H01) y el residuo (H23) están reportados.
7. **PASS** — transiciones repetidas (`C1`, `C4`, `C5`), requests duplicados (`F1–F7`) y fallos simulados en ≈ 15 escenarios de persistencia (`E1–E12`).
8. **PASS** — inputs hostiles razonables sin pentest destructivo (`D1–D7`, fuzz `C9`/`C10`); la bomba grande no se ejecutó.
9. **PASS** — auth/origen/artefactos/exposición (`G1–G6`, `E8b`).
10. **PASS** — DEMO no contamina 20+20 ni evaluaciones (`H1–H6`); limitación del índice HTML.
11. **PASS (parcial por entorno)** — `pillow-heif` 1.8.0/Python 3.12.14 verificados aquí; la imagen Docker **NO PROBADO**.
12. **PASS** — diff de producción vacío (ver abajo).
13. **PASS** — la lista priorizada termina este REPORT.
14. **PASS** — los defectos críticos se documentaron con su reproducción y no se corrigieron; veredicto `NOT_READY`.
15. **PASS** — `CURRENT_STATE` actualizado con el resultado y la base, sin inventar una E47.

## Evidencia
Los tests y los números están arriba; las medidas que no son tests (RSS muestreado, perfil de H16, rondas naturales) se reprodujeron con
scripts temporales y se documentan donde se citan: H16 (`cProfile`: 23,3 s de 24,1 s en `ndarray.sort`), H19 (RSS 42→505 MB), H02 (30/30,
20/25), H03 (ventana ≤ 5 ms), H21 (2/40).

## Diff prohibido
`git diff c9a215b HEAD -- src/ .github/ executor/ webapp/ requirements.txt Dockerfile scripts/ docs/E44_CAMPAIGN.md` → **vacío**; `git diff 6324b1f HEAD -- src/` →
**vacío**. Cambios del commit: `tests/test_e46_adv_*.py` (nuevos), `reports/E46_REPORT.md` (nuevo), `docs/ai-development/CURRENT_STATE.md`.
(`executor/` no existe en el repo.) **No hubo deploy, merge, PR ni llamadas pagadas.**

## Regresiones
Ninguna atribuible a E37–E45.2 (ver «Tests»).

## Limitaciones
- Todo es de este sandbox: tiempos y memoria no son de Railway.
- Los tests de carrera con barrera demuestran que **la ventana existe**; su probabilidad natural se midió aparte y se informa (H02: alta; H03: ≤ 5 ms).
- Los tests `…_DEFECTO_Hxx` fijan el comportamiento defectuoso a propósito: cualquier corrección los hará fallar (con el mensaje del docstring) y deberán actualizarse junto con ella.
- `uploads::D4d` y `D4g` miden tiempo/memoria y pueden ser sensibles a máquinas muy distintas (umbrales holgados); `D4d` se omite sin `/proc` (macOS) y
  `surface::K1` se omite si el intérprete no es 3.12.
- `F1b`, `F3` y `F4b` dependen de hilos: sus aserciones son deliberadamente laxas (la tasa observada va en el REPORT, no en el test) y `F1b` se omite si
  la carrera no se reproduce.
- Los scripts de sondeo temporales (perfil, RSS, rondas) no se commitean: lo que importa quedó como test o como cifra citada.
- Sin acceso a GitHub: las ramas se verificaron contra las remotas de seguimiento locales.

## Decisiones requeridas
**DECISION_REQUIRED — arrancar el piloto con el veredicto NOT_READY (DR-11)**

Contexto: la TASK pide una recomendación de readiness; hay 3 BLOCKER y 4 HIGH. Arrancar el piloto real o corregir antes es una decisión de Joaquín (DEPLOY_GATE).
Por qué no es puramente técnico: expone dinero (H03/H10), validez del experimento (H01) y el calendario de mañana.
Opción A: TASK de corrección (la escribe ChatGPT desde `auto/e46-issue-18`) con la lista «MUST FIX» de abajo, y recién entonces cargar el primer caso real.
Opción B: probar mañana con las mitigaciones operativas (no son correcciones) y aceptar el riesgo de H02/H05/H16/H21; no cargar planos junto a las fotos, un solo disparo por botón y sin otras pestañas abiertas.
Opción C: no arrancar hasta cerrar también los MEDIUM.
Impacto: A retrasa el piloto lo que cueste esa TASK; B arriesga casos del N y gasto duplicado; C el máximo retraso.
Recomendación técnica de Claude: **A** (los fixes de H01/H03/H10/H21 son pequeños y locales; H02/H16 son lo que más probablemente romperá la primera carga real).

NO IMPLEMENTADO AÚN.

**DECISION_REQUIRED — reintento y exclusión de casos CREAR (DR-12)**

Contexto: H05 + H20: una corrida fallida es definitiva y excluir no libera la propiedad.
Por qué no es puramente técnico: qué cuenta como «ejecutado» y si un fallo transitorio puede repetirse cambia las métricas y los gates de la campaña (EXPERIMENT_GATE).
Opción A: permitir reintentar un `pipeline` FAILED registrando cada intento; sólo el último cuenta como resultado.
Opción B: mantener el fallo definitivo pero permitir excluir y re-cargar la propiedad (el caso excluido queda en el registro).
Opción C: dejarlo como está.
Impacto: A cambia la definición de «ejecutado»; B conserva la semántica pero cuesta un caso por falla; C quema un caso de los 20 por cada fallo.
Recomendación técnica de Claude: B como mínimo (no toca la semántica de N), A si Joaquín acepta contar sólo el último intento.

NO IMPLEMENTADO AÚN.

## Commit / branch / PR
Rama `auto/e46-issue-18` (hija de `e46_night_adversarial_audit` = `c9a215b`), un commit final con los tests de auditoría, este REPORT y
`CURRENT_STATE.md`. La publica el workflow. **Sin PR, merge ni deploy.**

## Exact next action
Joaquín lee el veredicto y decide DR-11 y DR-12. Si elige la opción A, ChatGPT escribe una TASK de corrección en GitHub desde la base
**`auto/e46-issue-18`** ([protocolo §5.2](../docs/ai-development/DEVELOPMENT_PROTOCOL.md)); este REPORT no crea ni numera esa TASK.

## Lista priorizada

**MUST FIX BEFORE FIRST REAL CASE**
1. **H01** rechazar/avisar un plano dentro de las fotos (`looks_like_plan`), y comparar con hash perceptual.
2. **H10** guarda de mismo origen para *todo* POST del app (salvo `/planos/solicitar`).
3. **H03** reclamo atómico de `create_started`/`improve_started` antes de llamar al motor.
4. **H21** no pasar el error generado por el sistema por el detector de PII; que `settle` no propague.
5. **H02** candado en `_import_case` + manifiesto atómico + `rmtree` sólo de lo propio.
6. **H16** clasificar sobre copia reducida (o no clasificar) para que 6–15 fotos no tarden minutos.
7. **H05/H20** salida para una corrida fallida (según DR-12) y `exclude` que libere el duplicado.
8. Verificar fuera del repo el modelo de `ESCALIMETRO_RECON_OPENAI_MODEL` y que `OPENAI_API_KEY` esté sólo en el servicio del piloto.

**FIX DURING PILOT**
H04 (negarse a corregir/cerrar con el GT ya revelado) · H06 (eventos atómicos y lectura tolerante) · H07 (MEJORAR con `leer_limitado`/`validar_plano`) ·
H08 · H17 · H19 · H13 (freno en `/planos/solicitar`) · H14 (`X-Frame-Options`, `nosniff`) · H15 (declarar `scikit-image` o quitar el import, pins/lock) ·
H24 (antes del primer build desde una máquina de desarrollo) · H20 si no entró arriba.

**ACCEPT FOR PILOT**
H09 · H11 (si la clave es ASCII) · H12 · H18 · H22 (sólo el operador lo dispara) · H23 (residuo inerte; limpiar a mano) · las limitaciones listadas
(`A1b`, `A3b`, `A10`, `D4b`, `D4f`, `D6`, `F9`, `H5`, `I1`).

**Mitigaciones operativas para quien decida B (no son correcciones)**: no subir el plano entre las fotos ni sus capturas; no tocar dos veces ningún
botón ni reintentar antes de ver la respuesta (la carga puede tardar minutos); un solo operador, una sola pestaña del piloto abierta; no navegar a
otros sitios con la sesión del LAB abierta (ventana privada para el piloto); subir pocas fotos por caso al principio (≈ 12 s cada una de 12 MP);
si una corrida falla, no confiar en «volver a procesar»: anotar el caso y esperar a DR-12; no pegar textos largos en comentarios.
