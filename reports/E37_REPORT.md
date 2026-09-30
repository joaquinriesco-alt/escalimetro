# E37 REPORT

## Status

**PASS** — los 20 criterios de aceptación se cumplen. El instrumento está listo y **no se hizo
ninguna llamada pagada**: `OPENAI_API_KEY` no estaba en el entorno, así que el motor real existe y
está probado contra un transporte falso, pero nunca reconstruyó una planta de verdad. Eso es el
siguiente experimento, no un pendiente de E37.

## Qué cambió

**El laboratorio**, en `/lab/reconstruction/` (se llega desde Ajustes → Herramientas técnicas; el
menú del LAB no cambia). El flujo de la TASK, entero:
`PROYECTOS → NUEVO PROYECTO → INPUTS / PLANO REAL OCULTO → MOTOR → GENERAR → RESULTADO → CALIFICAR →
CORREGIR → NUEVA CORRIDA → COMPARAR → REVELAR`.

- **Proyectos** con fotos (el input principal), videos y documentos (se guardan aunque ningún motor
  los use; cada corrida dice qué no mandó) y datos declarados. 34 fotos en un envío o en lotes.
- **Plano real oculto**: otra tabla y otra raíz de disco; la UI sólo sabe que existe; revelar es
  un POST confirmado e irreversible.
- **Contrato v1** de la reconstrucción: recintos con polígono normalizado *o sin ubicar*,
  conexiones, posición relativa, huella en metros sólo si el motor la estima, incertidumbres,
  evidencia por inferencia (qué fotos), y tres resultados válidos: `RECONSTRUCTED`,
  `INSUFFICIENT_EVIDENCE`, `CLARIFICATION_REQUIRED`. El SVG se dibuja desde el contrato, una vez,
  y se guarda con su sha256.
- **Registro de motores**: la UI no conoce ninguno por nombre. `openai_direct` (VLM directo,
  `gpt-5.6-sol` configurable, salida JSON estricta, `store: false`) y `fixture_replay`, que sólo
  existe con `ESCALIMETRO_RECON_FIXTURE=1`, dice en cada pantalla que no reconstruye, y sirvió para
  las capturas.
- **Corridas inmutables** por triggers de SQLite —los primeros del repo—; corrección en lenguaje
  natural que crea una corrida hija; aclaraciones encadenadas; comparación de 2–3 corridas;
  calificación con historial; **métricas 90/10 sin puntaje compuesto**.
- **Seguridad propia de la superficie**: guardia de mismo origen que falla cerrada (acá un POST
  gasta dinero o revela el plano) y tope de envío propio.

**Fuera del laboratorio**, lo mínimo:

- `webapp/store.py`: tablas `recon_*` y triggers al final de `SCHEMA`, dos carpetas, las corridas
  E37 en `reset_orphans()`, y `ex()` ahora hace **rollback** si la sentencia falla (sin eso, un
  error dejaba trabada la escritura de toda la app).
- `webapp/providers/base.py`: enmascara la clave **antes** de truncar un error (un proveedor podía
  partirla y dejar vivo el prefijo). Código de E31, arreglo de seguridad.
- `tests/test_ai_handoff.py`: una TASK que ChatGPT acaba de escribir cuenta como pendiente. La TASK
  E37, sola en su rama, dejaba la suite en rojo: el hueco era de M01.1.
- `requirements.txt`: `flask>=3.1` (el tope de envío por request lo necesita; ya estaba instalada).

Ni una línea de `src/`.

## Archivos principales

```
webapp/domain/reconstruction/__init__.py        nuevo
webapp/domain/reconstruction/contract.py        nuevo · contrato v1 y su validación
webapp/domain/reconstruction/render.py          nuevo · SVG desde el contrato
webapp/domain/reconstruction/projects.py        nuevo · proyectos, inputs, datos, cierre, bitácora
webapp/domain/reconstruction/groundtruth.py     nuevo · plano real oculto y reveal
webapp/domain/reconstruction/runs.py            nuevo · corridas, cola, calificación, comparación, métricas
webapp/domain/reconstruction/engines/           nuevo · registro, base, openai_direct, fixture
webapp/reconstruction.py                        nuevo · blueprint /lab/reconstruction
webapp/templates/recon/                         nuevo · 8 plantillas
webapp/static/app.css                           bloque E37 al final, todo bajo .recon
webapp/store.py · webapp/app.py                 tablas, triggers, carpetas, huérfanas, rollback; registro
webapp/providers/base.py                        enmascarar antes de truncar
webapp/templates/lab/debug.html · settings.html un enlace cada una
tests/test_e37_reconstruction_lab.py            nuevo · 104 tests
tests/test_ai_handoff.py                        TASKs pendientes
docs/E37_RECONSTRUCTION_LAB.md                  nuevo · cómo funciona, cómo agregar un motor, cómo correr Ricardo Lyon
experiments/E37/screenshots/                    nuevo · 8 capturas con datos sintéticos
experiments/E37/review_findings.json            nuevo · las dos revisiones adversariales
.env.example · requirements.txt                 4 nombres de variable · flask>=3.1
docs/ai-development/*                           estado, D-009, protocolo §5.2
```

## Tests

```
baseline:    2062 passed · 3 failed · 8 skipped · 7 xfailed   @ 609cd2a (la TASK de ChatGPT)
post-change: 2167 passed · 2 failed · 8 skipped · 7 xfailed   @ árbol de e37_reconstruction_lab
             +105 = 104 tests nuevos de E37 + el de handoff que fallaba en la base
tests/test_e37_reconstruction_lab.py: 104 passed · tests/test_ai_handoff.py: 29 passed,
             re-corridos después de escribir este REPORT
```

El tercer fallo de la base era `test_ai_handoff::test_toda_task_tiene_su_report_salvo_la_que_esta_en_curso`:
la TASK recién escrita por ChatGPT no tenía REPORT ni figuraba en curso. Ahora pasa, también sobre
`609cd2a`. Los 2 que quedan son los históricos (`CURRENT_STATE.md` → Tests).

## Acceptance criteria

1. **PASS** — Handoff. `git diff --name-status origin/m01_1_remote_truth...origin/e37_reconstruction_lab`
   → `A tasks/E37.md`, un solo commit (`609cd2a`, del 2026-09-30 14:19 -03:00);
   `git merge-base --is-ancestor origin/m01_1_remote_truth origin/e37_reconstruction_lab` → sí;
   0 commits detrás de la base.
2. **PASS** — `git diff 6324b1f HEAD -- src/` vacío. Ningún módulo de E37 importa el motor
   histórico (test `test_e37_no_importa_nada_del_motor_historico`).
3. **PASS** — proyecto con nombre, fotos, video, documentos y datos declarados; un test sube 34
   fotos, un video y un documento en un envío. Sin límite menor a 34; el tope de envío de esta
   superficie es 1200 MB.
4. **PASS** — plano real en `recon_ground_truth` y `DATA_DIR/reconstruction_gt/`, estado
   `HIDDEN_FROM_ENGINE`. Tests adversariales, en Evidencia.
5. **PASS** — cada corrida guarda id, proyecto, motor y versión, padre, inputs permitidos (id +
   sha256), prompt y su versión y sha256, parámetros con el modelo congelado, commit, marcas de
   tiempo, estado, salida, artefactos con sha256, latencia, costo si se conoce y error si falla —
   **también cuando falla después de haberle pagado al proveedor**—. Re-ejecutar o corregir crea
   otra corrida; la base impide modificar o borrar una terminada.
6. **PASS** — agregar un adaptador es `engines.register()`; un test registra uno nuevo y aparece en
   la UI sin tocar plantillas, y ninguna plantilla nombra un motor. `AVAILABLE` / `UNAVAILABLE`
   con razón.
7. **PASS** — `openai_direct`, modelo por `ESCALIMETRO_RECON_OPENAI_MODEL` (default
   `gpt-5.6-sol`). Sin credencial: `UNAVAILABLE / MISSING_CREDENTIAL` y cero red. Todos sus tests
   usan un transporte falso.
8. **PASS** — la corrida muestra el SVG, los recintos con confianza, superficie y fotos que los
   sostienen, conexiones, posición relativa, incertidumbres, evidencia faltante y la procedencia.
   `INSUFFICIENT_EVIDENCE` se muestra como resultado válido.
9. **PASS** — una calificación vigente por corrida, `EXCELENTE / BUENO / MALO / PESIMO` +
   comentario, con historial de sólo inserción.
10. **PASS** — la corrección crea una hija con el texto guardado; el motor recibe la representación
    anterior y la instrucción; la madre no cambia (test compara la fila antes y después).
11. **PASS** — `CLARIFICATION_REQUIRED` es un resultado del contrato; la respuesta del operador es
    otra hija, y el motor recibe toda la conversación: lo pedido, cada pregunta con sus opciones y
    cada respuesta.
12. **PASS** — comparación de 2 o 3 corridas del mismo proyecto: plano, motor y versión, modelo,
    calificación, recintos, prompts humanos acumulados en el linaje, latencia y costo. 1, 4 o una
    corrida ajena → 400.
13. **PASS** — sólo `POST /revelar` con confirmación cambia el estado; un trigger impide volver
    atrás o reemplazar el plano revelado. Las corridas anteriores quedan marcadas «a ciegas»,
    también las creadas antes de cargar el plano real.
14. **PASS** — por proyecto: prompts humanos (total y en la línea de la corrida final), minutos
    humanos si se registraron, calificación final, CAD manual sí/no, recintos detectados /
    esperados (esperados: tras revelar, o como etiqueta si no hay plano real) y juicio humano de
    adyacencias, posición relativa y utilidad de la geometría. Ninguna métrica compuesta; un test
    lo verifica.
15. **PASS** — el caso Ricardo Lyon se puede recrear (34 fotos + plano real oculto); probado con 34
    fotos sintéticas en tests y en la demo; pasos en `docs/E37_RECONSTRUCTION_LAB.md`.
16. **PASS** — test de reinicio (conexión nueva sobre el mismo volumen): proyectos, corridas,
    calificaciones, cierre y reveal intactos. Una corrida en vuelo al reiniciar queda `FAILED` y no
    se reanuda.
17. **PASS** — después de un flujo completo, 15 tablas del resto del producto siguen con 0 filas;
    E36 (`realpilot`), E33 (`reviews.stats`), E17 (tablero), intervenciones, menú del LAB y portada
    intactos. Lo confirmó además una dimensión dedicada de la revisión, sin hallazgos.
18. **PASS** — el flujo visible, en ese orden, en cada pantalla; el camino principal en castellano,
    sin ids ni códigos del contrato (quedan en «Procedencia técnica», plegada).
19. **PASS** — tests de ceguera, inmutabilidad, registro, proveedor simulado, corrección hija,
    reveal, persistencia y no contaminación. Suite sin fallos nuevos (Tests).
20. **PASS** — 8 capturas del flujo real con datos sintéticos (Evidencia).

## Evidencia

### Handoff directo ChatGPT → GitHub → Claude

```
$ git fetch origin --prune
 * [new branch]      e37_reconstruction_lab -> origin/e37_reconstruction_lab
$ git log --format='%h %an %cI %s' origin/m01_1_remote_truth..origin/e37_reconstruction_lab
609cd2a joaquinriesco-alt 2026-09-30T14:19:04-03:00 E37 - define Internal Reconstruction Lab
$ git diff --name-status origin/m01_1_remote_truth...origin/e37_reconstruction_lab
A	tasks/E37.md
```

La TASK tiene las ocho secciones del formato y dice quién la aprobó y cuándo. Empecé cuando
Joaquín escribió «Ejecuta E37», no porque el archivo existiera (protocolo §5.2). Autor del commit:
la cuenta del dueño del repo, que es con la que opera el conector de ChatGPT (DR-8 sigue abierta).

### Esquema

Siete tablas `recon_projects`, `recon_assets`, `recon_ground_truth`, `recon_runs`,
`recon_ratings`, `recon_judgments`, `recon_events` y doce triggers: corrida terminada inmutable,
identidad fija, corridas que no se borran; calificaciones, juicios y bitácora de sólo inserción;
reveal irreversible; plano revelado que no se reemplaza ni se borra. Todo en `CREATE … IF NOT
EXISTS` al final de `SCHEMA`, como el resto de las fases.

### Registro de motores, estado real

```
sin variables:            openai_direct  OpenAI multimodal directo v1  gpt-5.6-sol  UNAVAILABLE  MISSING_CREDENTIAL  paga
ESCALIMETRO_RECON_FIXTURE=1: + fixture_replay  FIXTURE — salida grabada  AVAILABLE  sin costo
```

### Ceguera del plano real: los tests adversariales

- un motor espía corre generación, corrección ambigua, respuesta y otra generación con video; en
  todo lo que recibió se busca el plano real como bytes, subcadena de bytes, base64, sha256,
  prefijo del sha, md5, nombre original, nombre guardado, carpeta, raíz `reconstruction_gt` y una
  marca embebida en el PNG. Tampoco hay ninguna ruta del volumen;
- lo mismo en el cuerpo HTTP que `openai_direct` le mandaría a OpenAI;
- ninguna fila de corrida guarda el sha, el nombre ni la carpeta del plano real;
- antes del reveal, ni la portada, ni el proyecto, ni la corrida, ni su SVG, ni su estado JSON, ni
  la comparación muestran nada del plano real, y su ruta responde 404;
- un input idéntico al plano real se rechaza en los dos sentidos; una foto ya usada por un motor
  no puede volverse plano real aunque se retire; y si igual ocurriera, la corrida falla con
  `INPUT_IS_GROUND_TRUTH` en vez de mandarla;
- `runs.py` y `engines/` no importan el módulo del plano real (test estático).

### Corrida madre → corrección → corrida hija (proyecto demo, motor FIXTURE)

| corrida | origen | instrucción | resultado | dormitorio principal | baño principal |
|---|---|---|---|---|---|
| #1 | inicial | — | plano esquemático | 14 m² | 4,5 m² |
| #2 | corrección de #1 | «el dormitorio principal era más grande» | plano esquemático; entendió «Dormitorio principal: más grande» | 18,5 m² | 4,5 m² |
| #3 | corrección de #2 | «arregla la franja de baños» | **pide aclaración**: «¿Qué recinto hay que cambiar…?» con opciones | — | — |
| #4 | respuesta a #3 | «el baño principal, más chico» | plano esquemático | 18,5 m² | 3,3 m² |

La #1 no cambió en ningún momento: su `output_sha256` es el mismo antes y después. #4 acumula 3
prompts humanos en su linaje. El fixture corrige con una regla de texto: esto prueba el flujo, no
la calidad de ningún motor.

### Capturas (datos sintéticos, motor FIXTURE)

| | |
|---|---|
| [01 · proyectos y motores](../experiments/E37/screenshots/01_proyectos_y_motores.png) | [02 · proyecto: 34 fotos, plano real oculto, motor](../experiments/E37/screenshots/02_proyecto_inputs_plano_real_oculto.png) |
| [03 · resultado de la corrida #1](../experiments/E37/screenshots/03_resultado_corrida_1.png) | [04 · corrida hija por prompt](../experiments/E37/screenshots/04_corrida_hija_por_prompt.png) |
| [05 · el motor pide una aclaración](../experiments/E37/screenshots/05_pide_aclaracion.png) | [06 · comparar, antes del reveal](../experiments/E37/screenshots/06_comparar_antes_del_reveal.png) |
| [07 · proyecto tras el reveal y métricas](../experiments/E37/screenshots/07_proyecto_tras_el_reveal_y_metricas.png) | [08 · comparar, con el plano real](../experiments/E37/screenshots/08_comparar_con_el_plano_real.png) |

Tomadas con Chrome headless contra un servidor local con carpeta de datos propia
(`.data-e37-demo`, fuera del repo; `.data-lab`, el piloto de E36, no se tocó).

### Revisión adversarial, dos rondas

[`experiments/E37/review_findings.json`](../experiments/E37/review_findings.json). Cada hallazgo lo
intentó refutar un segundo agente reproduciéndolo.

- **Ronda 1** (seis dimensiones): 26 hallazgos, **22 confirmados**, 4 refutados. Los dos más
  serios:
  - el plano real podía llegar al motor a través de una foto retirada que una corrida anterior
    seguía citando, y era el camino que la propia pantalla aconsejaba;
  - una llamada paga que terminaba en falla perdía tokens, latencia y respuesta.
- **Ronda 2**: verificó las 22 correcciones, repitió la dimensión de no contaminación —que en la
  primera ronda se colgó; esta vez 0 hallazgos— y atacó el código nuevo. 16 hallazgos, casi todos
  bajos: 6 confirmados, 1 que el verificador consideró no-defecto (se endureció igual) y 9 que el
  límite de uso dejó sin verificador, evaluados a mano contra el código. Todos reales.
- Los 38 están corregidos. Los 37 que eran de código tienen su test de regresión (`test_rev_*`,
  `test_r2_*`); el restante era una referencia de la documentación que no existía, y se agregó.

### Llamadas pagas

**Ninguna.** `OPENAI_API_KEY` ausente en todas las terminales de esta sesión; cada test de
`openai_direct` reemplaza `providers.base.TRANSPORT`. No hay costo ni latencia de una llamada real
que reportar.

## Regresiones

Ninguna. Los 2 fallos de la suite son los históricos. `tests/test_ai_handoff.py` fallaba en la
base (`609cd2a`) y ahora pasa, también sobre ese commit.

Cambios fuera de E37 con alcance en toda la app, los dos correcciones de seguridad o robustez:
`store.ex()` hace rollback si falla, y `providers/base.py` enmascara antes de truncar. La suite
completa pasa con ambos.

## Limitaciones

1. **Nada se reconstruyó de verdad.** El motor real está probado contra un proveedor simulado; su
   primera corrida real es el siguiente experimento. Las capturas usan el FIXTURE.
2. **Costo `unknown`.** No hay precio de lista para `gpt-5.6-sol` en el repo; se guardan los tokens.
   El gasto real se lee en la cuenta del proveedor hasta que alguien registre un precio fechado.
3. **La ceguera es de interfaz, no de proceso.** Un adaptador es código Python en el mismo proceso;
   nada le impide abrir el disco por su cuenta. Lo que se garantiza y se prueba es que no recibe
   nada del plano real.
4. **Modo DEV sin contraseña** escucha en `0.0.0.0` sin credenciales: con una clave real en el
   entorno, cualquier equipo de la red podría gastar o revelar. Documentado: con clave, poner
   `ESCALIMETRO_PASSWORD`.
5. **`reset_orphans()` corre en cualquier proceso que llame `create_app()`**, `wsgi.py` incluido.
   Es de toda la app y anterior a E37; E37 se protege del efecto, pero no se tocó la causa.
6. **Video y documentos** se guardan pero ningún motor de E37 los consume. Un motor futuro que
   declare `video` recibe el archivo entero en memoria.
7. **Una sola corrida no permite comparar**: la comparación pide 2 o 3. Con una, el plano real
   revelado se mira en la página del proyecto.

## Decisiones requeridas

Ninguna nueva de producto. Siguen abiertas DR-1 a DR-8. E37 no necesitó tocar `src/`, así que DR-6
no lo bloqueó.

Acciones de Joaquín —no decisiones— para el primer experimento real:

- poner `OPENAI_API_KEY` en el entorno del servidor, con `ESCALIMETRO_PASSWORD`;
- las 34 fotos y el plano real de Piso Ricardo Lyon I;
- aprobar el gasto de cada corrida, que la UI pide marcar.

## Commit / branch / PR

Rama `e37_reconstruction_lab`, dos commits sobre `958e39c` (`m01_1_remote_truth`): `609cd2a`, la
TASK, escrito por ChatGPT en GitHub; y el de E37, con todo lo demás. Este REPORT viaja en ese
segundo commit: su hash está en `git log -1 origin/e37_reconstruction_lab`. La rama queda 99
commits delante de `main` y 0 detrás, verificado contra GitHub después del push
(`gh api repos/joaquinriesco-alt/escalimetro/compare/main...e37_reconstruction_lab`).
Sin PR, sin merge, sin deploy.

## Exact next action

**Para Joaquín:** decidir si se corre Ricardo Lyon I con `openai_direct`. Si sí: clave en el
servidor y las 34 fotos más el plano real, siguiendo `docs/E37_RECONSTRUCTION_LAB.md`. Con ChatGPT,
la TASK de ese experimento —qué se mide, cuántas correcciones, contra qué línea base—, escrita en
GitHub desde la base `e37_reconstruction_lab`.
**Para Claude:** nada hasta recibir un ID.
