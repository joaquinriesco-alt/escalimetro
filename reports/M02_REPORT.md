# M02 REPORT

## Status

**DECISION_REQUIRED** — el ejecutor está construido y probado sin gasto; activarlo depende de una
decisión de Joaquín (DR-9) y de dos acciones suyas.

| | estado | por qué |
|---|---|---|
| `BUILT` | **sí** | workflow, preflight, verificación, tests, simulación end-to-end y guía |
| `ACTIVATED` | **no** | GitHub sólo dispara `issues` desde la rama por defecto (`main`), y el workflow no está ahí; el secreto `CLAUDE_CODE_OAUTH_TOKEN` está AUSENTE |
| `E2E_REAL_PROVEN` | **no** | ninguna TASK corrió todavía a través de GitHub Actions con Claude real |

Hasta que se active, el ciclo sigue siendo el del protocolo §5.2: Joaquín escribe «Ejecuta» y el ID.

## Qué cambió

**El ejecutor**, en cuatro jobs con permisos mínimos
([`.github/workflows/escalimetro-auto-task.yml`](../.github/workflows/escalimetro-auto-task.yml)):

1. **`gate`**, sin secretos. Un `if:` a nivel de job —antes de que exista un runner— exige que el
   evento sea `issues/opened` de este repo, y que actor, id, emisor y autor sean
   `joaquinriesco-alt` (tipo `User`, `OWNER`), con el título del marcador. Después corre
   `scripts/auto_task.py preflight` (detalle en Evidencia).
2. **`claude`**, sólo si `gate` dio `ok`. Hace checkout del commit exacto de la TASK y crea la rama
   hija `auto/<id>-issue-<n>`; Claude trabaja ahí con un token de GitHub **de sólo lectura**,
   herramientas acotadas, sin `git push` y sin web. Sus commits salen como `git bundle`.
3. **`publish`**, sin credencial de Anthropic. `scripts/auto_task.py verify` revisa el bundle y,
   si pasa, crea la rama: nunca la fuerza, nunca mergea. No corre si alguien canceló.
4. **`notify`**, que sólo puede comentar: avisa en el issue qué pasó y dónde quedó.

**El contrato** `ESCALIMETRO_AUTO_TASK_V1`: cinco claves exactas en el issue; lo autoritativo es
`tasks/<ID>.md` en el commit nombrado. **D-012** amplía la superficie de ChatGPT de D-010 con ese
issue, estrictamente mecánico.

**Ajustes fuera del ejecutor:**

- `scripts/secret_scan.py`: el escaneo pasa a `main()`, para que sus patrones se importen sin
  escanear el repo. La CLI se comporta igual.
- `tests/test_ai_handoff.py`: el estado declara una sola base, y el ejecutor y el handoff
  comparten la regla de IDs y de secciones.
- Guía [`AUTO_TASK_EXECUTOR.md`](../docs/ai-development/AUTO_TASK_EXECUTOR.md), protocolo §5.3,
  D-012, `CLAUDE.md` y `CURRENT_STATE.md`.

Ni `src/`, ni `webapp/`, ni E37, ni producto.

## Archivos principales

```
.github/workflows/escalimetro-auto-task.yml     nuevo · el ejecutor (gate · claude · publish · notify)
scripts/auto_task.py                            nuevo · preflight y verify, sin shell ni red propia
tests/test_m02_auto_task.py                     nuevo · contrato, compuertas, verify, workflow, simulación
docs/ai-development/AUTO_TASK_EXECUTOR.md       nuevo · guía, activación, riesgos, primera prueba
experiments/M02/review_findings.json            nuevo · la revisión adversarial
experiments/M02/research_sources.json           nuevo · fuentes oficiales consultadas, con citas
scripts/secret_scan.py                          el escaneo en main(); mismos patrones y misma salida
tests/test_ai_handoff.py                        base única y reglas compartidas con el ejecutor
docs/ai-development/*  ·  CLAUDE.md             protocolo §5.3, D-012, estado, paso 4
```

## Tests

```
baseline:    2171 passed · 2 failed · 8 skipped · 7 xfailed   @ 24eff44 (la TASK de ChatGPT)
post-change: 2271 passed · 2 failed · 8 skipped · 7 xfailed   @ el commit de M02, antes de
             completar esta sección
             +100 = 95 de tests/test_m02_auto_task.py
                  + 2 tests nuevos de tests/test_ai_handoff.py (base única, IDs compartidos)
                  + 3 casos de handoff que se parametrizan solos: este REPORT y los enlaces de
                    este REPORT y de AUTO_TASK_EXECUTOR.md
tests/test_m02_auto_task.py + tests/test_ai_handoff.py: 131 passed, re-corridos después de
             completar este REPORT
```

Las dos corridas completas se hicieron en worktrees limpios del commit nombrado: en el checkout de
trabajo hay archivos sin trackear que cambian el conteo. Los 2 fallos son los históricos
(`CURRENT_STATE.md` → Tests) y son los mismos en las dos corridas.

## Acceptance criteria

1. **PASS** — handoff §5.2. `git diff --name-status origin/e37_reconstruction_lab...origin/m02_github_executor`
   → `A tasks/M02.md` en el commit `24eff44`, 0 detrás de la base. El preflight del propio
   ejecutor, corrido contra GitHub con un evento simulado para M02, da PASS (Evidencia).
2. **PASS** — `git diff 6324b1f HEAD -- src/` vacío.
3. **PASS** — un solo workflow, dedicado; el repo no tenía ninguno (test).
4. **PASS** — el `if:` del job `gate` exige el actor y otros nueve campos antes del runner; `claude`
   repite el actor. Un test exige la conjunción exacta: un `&&` cambiado por `||` lo rompe.
5. **PASS** — parser y preflight cubiertos en `tests/test_m02_auto_task.py` (95 tests en total, con
   fixtures válidos y adversariales).
6. **PASS** — el preflight verifica:
   - el commit exacto, por nombre de ref exacto;
   - el ancestro, y que la base siga vigente;
   - el diff de un único archivo agregado, normal y no symlink;
   - el path y el ID.
7. **PASS** — una rama movida después del issue falla con `TASK_BRANCH_MOVED`. También falla una
   rama señuelo `x/refs/heads/<rama>` con un commit no aprobado.
8. **PASS** — un actor no autorizado no llega a runner (compuerta 1) y, si llegara, el preflight lo
   rechaza; el único secreto aparece sólo en el job `claude`, después de las dos compuertas (test).
9. **PASS** — el prompt lleva ID, rama, commit y la orden de leer `CLAUDE.md` y el protocolo; un test
   comprueba que no contiene texto de la TASK.
10. **PASS** — la rama hija la crea el workflow desde el commit de la TASK, y `base_branch` recibe la
    rama de la TASK. La investigación mostró que en modo automatización la action no crea ramas, así
    que se hizo determinista en el workflow (guía §4).
11. **PASS** — sin merge, sin deploy, sin cambio de rama por defecto: el único push es
    `refs/heads/$IMPL_BRANCH`, sin forzar (tests).
12. **PASS** — sin `allowed_non_write_users`, `allowed_bots`, `pull_request_target` ni
    `show_full_output` (test, sobre el workflow sin comentarios).
13. **PASS** — `scripts/secret_scan.py`: sólo el falso positivo conocido de E32. La evidencia de
    `experiments/M02/` pasó por los mismos patrones y no tiene rutas locales. `verify` además rechaza
    publicar algo con forma de credencial.
14. **PASS** — los tests usan repos git locales y listados de issues falsos; un test estático prohíbe
    librerías de red en el módulo. Ninguna llamada a Anthropic ni a OpenAI.
15. **PASS** — una ruta: `CLAUDE_CODE_OAUTH_TOKEN` + `GITHUB_TOKEN`. Presencia sólo por nombre
    (`gh secret list`) y, en el workflow, un paso que imprime PRESENTE o AUSENTE (guía §5–§6).
16. **PASS** — el bloqueo real está documentado: `issues` sólo dispara desde la rama por defecto
    (fuente: docs.github.com). Es DR-9.
17. **PASS** — simulación end-to-end sin gasto, con dos variantes:
    - fixture válido → PASS → prompt y `base_branch` esperados; fixtures adversariales → FAIL;
    - cadena completa: preflight → commits simulados → verify → push a un origin local → el mismo
      issue otra vez da `ALREADY_EXECUTED`.
18. **PASS** — `test_ai_handoff.py`, adaptado sin relajar nada:
    - una TASK recién escrita cuenta como pendiente (regla de E37);
    - el estado declara una sola base, que el ejecutor lee con la misma función;
    - todo ID de `tasks/` es uno que el ejecutor acepta, y las secciones exigidas son las mismas.
19. **PASS** — suite sin fallos nuevos (Tests).
20. **PASS** — `BUILT` / `ACTIVATED` / `E2E_REAL_PROVEN` separados (Status); no se llama PASS a lo
    que no corrió.
21. **PASS** — versiones y SHAs (Evidencia) y fuentes oficiales con fecha (guía, «Fuentes», y
    `experiments/M02/research_sources.json`).
22. **PASS** — lo que Joaquín hace una sola vez (Decisiones requeridas).
23. **PASS** — la TASK inocua M03 (Exact next action).
24. **PASS** — sin PR, sin merge, sin deploy.

## Evidencia

### Handoff directo y preflight contra GitHub real

```
$ git log --format='%h %an %cI %s' origin/e37_reconstruction_lab..origin/m02_github_executor
24eff44 joaquinriesco-alt 2026-09-30T20:31:20-03:00 M02 - define GitHub-native Claude executor task
$ git diff --name-status origin/e37_reconstruction_lab...origin/m02_github_executor
A	tasks/M02.md

# evento simulado (issue #9001, nunca creado) contra el remoto real, sólo lecturas:
$ GITHUB_ACTOR=joaquinriesco-alt GITHUB_REPOSITORY=joaquinriesco-alt/escalimetro \
    python scripts/auto_task.py preflight --event evento_m02.json --repo .
PREFLIGHT OK · actor
PREFLIGHT OK · título
PREFLIGHT OK · contrato
PREFLIGHT OK · rama de la TASK en el commit exacto
PREFLIGHT OK · base declarada, vigente y ancestro
PREFLIGHT OK · diff = sólo la TASK
PREFLIGHT OK · TASK con formato y aprobación
PREFLIGHT OK · sin ejecución previa ni issue duplicado
PREFLIGHT PASS M02 → auto/m02-issue-9001
```

### Estado de GitHub (verificado con `gh api`, 2026-09-30)

- rama por defecto `main` (`c6de3f9`), **sin protección** y sin rulesets;
- Actions habilitado, `allowed_actions=all`, `sha_pinning_required=false`;
- 0 workflows y 0 secretos: `CLAUDE_CODE_OAUTH_TOKEN` **AUSENTE**;
- la GitHub App de Claude: **NO_VERIFICABLE**, porque la credencial de `gh` no puede listar
  instalaciones. La ruta elegida no la necesita;
- Railway: Joaquín informó en la TASK que deshabilitó el Auto Deploy del servicio `backend`. Eso
  **no es verificable** por la API; desde entonces no hubo pushes a `main`.

### Actions fijadas (verificadas contra el repo de cada una, 2026-09-30)

| action | versión | SHA | por qué |
|---|---|---|---|
| `anthropics/claude-code-action` | v1.0.238 | `12dd8d74c712f5f3669365b2369b558c495b1104` | última v1; `@v1` es un tag móvil (se movió hoy). Respecto de v1.0.237 sólo cambia la versión del CLI |
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` | última |
| `actions/setup-python` | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` | última |
| `actions/upload-artifact` | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` | última |
| `actions/download-artifact` | v8.0.1 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` | última |

El SHA fija la action, no el CLI de Claude Code que ella descarga al correr.

### Lo que la investigación cambió del diseño

1. **En modo automatización la action no crea ramas**, y `base_branch` sólo informa. Por eso la
   rama la crea el workflow, de forma determinista.
2. **Los chequeos de actor de la action corren dentro de su paso, con el secreto ya cargado.** Por
   eso la compuerta es un `if:` de job, como recomienda la propia documentación de Claude Code.
3. **La action escribe el token de GitHub en `.git/config`, legible por Claude.** Por eso Claude
   corre con un token de sólo lectura, y la escritura vive en otro job, sin credencial de Anthropic.
4. **Con un `prompt`, el modo «tag» metería el cuerpo del issue como instrucciones.** Por eso no se
   usa `track_progress`, y el cuerpo del issue nunca llega al prompt.

### Revisión adversarial

Tres revisores —seguridad del workflow, burlar preflight y verify, cobertura de la TASK— y un
verificador por hallazgo: **15 confirmados**, 13 refutados
([`experiments/M02/review_findings.json`](../experiments/M02/review_findings.json)).

Los confirmados se agrupan en nueve defectos, todos corregidos y con test:

- la rama señuelo que burlaba `ls-remote`;
- rutas prohibidas que pasaban con tildes, comillas de git o mayúsculas;
- cancelar no detenía la publicación;
- la misma TASK podía correr dos veces;
- una base vieja se aceptaba por declararse a sí misma;
- una «Decisión aprobada» citada en un bloque de código contaba como aprobación;
- la guía exageraba lo que protege el scrub de credenciales;
- los tests de la compuerta no detectaban un `||`;
- el comentario anunciaba una rama que no se había empujado.

Cinco endurecimientos salieron de hallazgos refutados pero baratos de cerrar:
- `.claude/`, `.mcp.json` y el propio ejecutor quedan prohibidos;
- se revisa cada commit, no sólo el árbol final;
- se buscan secretos en el diff antes de empujar;
- la TASK tiene que ser un archivo normal, no un symlink;
- el bundle se retiene 1 día.

### Llamadas pagas

**Ninguna.** Ni Anthropic, ni OpenAI, ni GitHub Actions corrió el workflow.

## Regresiones

Ninguna (Tests). `scripts/secret_scan.py` cambió de forma, no de comportamiento: sigue encontrando
el mismo falso positivo de E32 y saliendo con 1.

## Limitaciones

1. **No está activado ni probado de verdad.** Todo lo demostrado es local o de sólo lectura. La
   primera corrida real puede encontrar algo que la documentación no dice, por ejemplo cómo resuelve
   la action el chequeo de permisos con un `GITHUB_TOKEN` de sólo lectura.
2. **El autor de un issue que abre ChatGPT no está verificado** (no hay issues en el repo). Si
   figura como bot, la compuerta lo rechaza —falla cerrado— y hay que decidir a quién autorizar.
   Se comprueba antes de activar (guía §9.1).
3. **La credencial de Anthropic queda expuesta al código que corre en el job `claude`** (tests y
   dependencias incluidos); el scrub es parcial. Ver guía §8.
4. **Consume el mismo límite de uso** que Claude Code interactivo, y el token dura un año.
5. **Cambiar el ejecutor exige volver a llevarlo a la rama por defecto**: lo que corre es la copia
   de ahí, no la de la cadena. Por diseño, una ejecución automática no puede modificarlo.
6. **Web y herramientas fuera de la lista no están disponibles en una ejecución automática.** Una
   TASK que las necesite se corre a mano, por §5.2.

## Decisiones requeridas

### DR-9 — Cómo activar el ejecutor

Contexto: GitHub sólo dispara `issues` desde la rama por defecto. El workflow y
`scripts/auto_task.py` tienen que estar en `main`, o la rama por defecto tiene que cambiar. `main`
está en E16.12, sin protección, con historia de deploys de Railway.

Por qué no es técnico: mover `main` o la rama por defecto es `MERGE_GATE` y se cruza con DR-1 y
DR-8.

- **A.** Resolver DR-1 primero: proteger `main` (DR-8), confirmar en Railway que `backend` no
  despliega `main`, y avanzar `main` por fast-forward hasta la punta auditada (que incluye M02).
  `main` vuelve a ser la verdad y el ejecutor queda activo.
- **B.** Llevar a `main` sólo los dos archivos del ejecutor, en un commit propio. Es lo mínimo,
  pero `main` se separa de la cadena: el merge futuro deja de ser fast-forward.
- **C.** Cambiar la rama por defecto a una rama de integración. No toca `main`, pero cambia lo que
  ve quien abre el repo, y esa rama hay que mantenerla al día a mano.

Impacto: con B o C el ejecutor corre con la copia de esos archivos, que hay que actualizar a mano
cada vez que cambien.
Recomendación técnica: **A**. Resuelve tres decisiones abiertas de una vez y deja una sola verdad.
NO IMPLEMENTADO AÚN.

### OPERATOR_ACTION_REQUIRED (Joaquín, una sola vez, después de la auditoría de M02)

1. `claude setup-token`, y después `gh secret set CLAUDE_CODE_OAUTH_TOKEN -R
   joaquinriesco-alt/escalimetro`, pegando el valor en el prompt de `gh`. Nunca en un chat ni en el
   repo.
2. Recomendado: en Settings → Actions, exigir acciones fijadas por SHA y permitir sólo las seis del
   workflow (guía §6).
3. Antes de activar: que ChatGPT abra un issue cualquiera para verificar con qué identidad aparece
   (guía §9.1).

## Commit / branch / PR

Rama `m02_github_executor`, dos commits sobre `01940c6` (`e37_reconstruction_lab`): `24eff44`, la
TASK, escrito por ChatGPT en GitHub; y el de M02, con todo lo demás. Este REPORT viaja en ese
segundo commit: su hash está en `git log -1 origin/m02_github_executor`. La rama queda 101 commits
delante de `main` y 0 detrás, verificado contra GitHub después del push
(`gh api repos/joaquinriesco-alt/escalimetro/compare/main...m02_github_executor`).
Sin PR, sin merge, sin deploy, sin issue, sin secreto, sin workflow en `main`.

Después del push, el issue de transporte de M02 ya no pasaría el preflight: la rama de la TASK se
movió (`TASK_BRANCH_MOVED`). Es lo esperado. Una TASK se ejecuta una sola vez.

## Exact next action

**Para Joaquín:** decidir DR-9 y hacer las acciones de arriba.
**Para ChatGPT, después:** escribir la TASK inocua **M03 — prueba del ejecutor** en
`m03_executor_smoke`, desde la base que declare el estado. Que pida sólo una nota en
`experiments/M03/` con el número de issue y de run, su REPORT y el estado. Después, abrir el issue
`[ESCALIMETRO_AUTO_TASK] M03`.

Si los cuatro jobs pasan y la rama `auto/m03-issue-<n>` aparece con su REPORT sin que Joaquín abra
Claude, el estado puede decir ACTIVADO y E2E real probado.
**Para Claude:** nada hasta recibir un ID, o un issue.
