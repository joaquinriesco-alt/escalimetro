# Ejecutor GitHub-native de TASKs (M02)

> **Estado: ACTIVO en `main` desde el 2026-10-01 · ninguna ejecución real exitosa.**
> GitHub dispara eventos `issues` con la copia del workflow que está en la rama por defecto
> (`main`). Con la autorización de Joaquín, ChatGPT avanzó `main` hasta M02 (`edd50e0`), y
> Joaquín cargó la credencial. La primera
> ejecución real —M03, issue #2, run `36864248192`— pasó la compuerta y murió al instalar Claude
> Code: con el scrub activo, Claude Code exige bubblewrap, y el runner no lo trae. **M02.1** lo
> prepara y lo prueba antes de la credencial (§3, compuerta 3), pero rige recién cuando llegue a
> `main`. Hasta entonces, cualquier issue de transporte falla igual, sin publicar nada; el ciclo
> sigue siendo el del [protocolo §5.2](DEVELOPMENT_PROTOCOL.md): Joaquín le dice a Claude «Ejecuta»
> y el ID.

Automatiza el **transporte y la ejecución de una TASK ya aprobada**, no el juicio. Joaquín sigue
siendo la autoridad final, ChatGPT sigue diseñando y auditando, Claude sigue implementando. No hay
auto-merge, auto-deploy, ni forma de que Claude encadene o invente TASKs.

---

## 1. El flujo, una vez activado

```
Joaquín + ChatGPT aprueban una TASK
   ↓
ChatGPT crea la rama de la TASK y tasks/<ID>.md                 (protocolo §5.2, D-010)
   ↓
ChatGPT abre un issue de transporte: contrato ESCALIMETRO_AUTO_TASK_V1      (D-012)
   ↓
GitHub Actions · job gate     compuerta + preflight, sin secretos
   ↓
GitHub Actions · job claude   Claude ejecuta la TASK en auto/<id>-issue-<n>, sin poder empujar
   ↓
GitHub Actions · job publish  verifica lo hecho y crea la rama (nunca si alguien canceló)
   ↓
GitHub Actions · job notify   comenta en el issue qué pasó y dónde quedó
   ↓
ChatGPT lee la rama y el REPORT en GitHub y audita
   ↓
Joaquín decide
```

## 2. El issue de transporte

Título, exacto: `[ESCALIMETRO_AUTO_TASK] <ID>`. Cuerpo, exacto (puede ir dentro de un bloque de
código; nada más fuera de él):

```
ESCALIMETRO_AUTO_TASK_V1
TASK_ID=M03
TASK_BRANCH=m03_executor_smoke
TASK_COMMIT=<SHA completo, 40 hex, del commit que agregó tasks/M03.md>
BASE_BRANCH=<la base que declara CURRENT_STATE.md>
TASK_PATH=tasks/M03.md
```

El issue no define nada: lo autoritativo es `tasks/<ID>.md` en `TASK_COMMIT`. No otorga permiso
para merge, deploy, cambios de doctrina ni otra TASK. Un issue que no cumple el contrato no
ejecuta nada.

## 3. Las compuertas, en orden

| # | dónde | qué | si falla |
|---|---|---|---|
| 1 | `if:` del job `gate`, antes de existir un runner | evento `issues/opened`, este repo, `github.actor` y su id, emisor, autor del issue (tipo `User`, `OWNER`), título con el marcador | el job se salta: ni checkout, ni secretos |
| 2 | `scripts/auto_task.py preflight` | actor otra vez; contrato estricto (exactamente 5 claves, formatos seguros, sin texto extra); la rama apunta HOY a `TASK_COMMIT` (nombre de ref exacto); la base existe, su `CURRENT_STATE.md` la declara y ninguna rama más nueva la reemplazó; la TASK desciende de la base; el diff base → TASK es sólo `tasks/<ID>.md`, archivo normal; la TASK tiene las 8 secciones, sin repetir, y «Decisión aprobada» con contenido real (no citado en un bloque de código ni en un comentario); no hay REPORT, rama `auto/<id>-*` ni otro issue anterior de esa TASK | `ok=false` y un código (`TASK_BRANCH_MOVED`, `BASE_SUPERSEDED`, `DUPLICATE_ISSUE`, `DIFF_NOT_ONLY_TASK`…): el job `claude` no corre |
| 3 | job `claude`, los dos primeros pasos: antes del checkout y de la credencial (M02.1) | `bubblewrap` y `socat` instalados con `apt`; la restricción de AppArmor sobre user namespaces liberada y releída; docker apagado; un sandbox de prueba, sin `sudo`, con user, PID y red propios y `/proc` nuevo, que no ve el PID del runner, corre con `no_new_privs` y no llega al socket de docker | el job termina con un error que dice por qué: ni checkout, ni Claude, ni credencial |
| 4 | job `claude` | sólo con `ok == true` y el mismo actor; token de GitHub **de sólo lectura**; credencial de Anthropic sólo en el paso de Claude; herramientas acotadas, sin `git push`, sin web; los comandos de Claude corren en el sandbox de la compuerta 3 | Claude no puede empujar ni aunque lea el token |
| 5 | `scripts/auto_task.py verify`, job `publish` | lo que hizo Claude llega como `git bundle`; tiene que descender de la TASK; ningún commit —no sólo el árbol final— toca `.github/`, `src/`, `tasks/`, `.claude/`, `.mcp.json` ni el propio ejecutor (rutas comparadas sin comillas de git y sin distinguir mayúsculas); nada agregado con forma de credencial; ninguna rama `auto/<id>-*` existe todavía | `REJECT`: no se publica nada y `notify` lo dice en el issue |
| 6 | GitHub | `GITHUB_TOKEN` no tiene permiso `workflows`; sus pushes no disparan otros workflows | — |

El preflight y la verificación se ejecutan desde la rama por defecto, no desde la rama de la
TASK: la TASK no puede reescribir a quien la juzga. El issue se lee del archivo del evento como
datos y nunca se interpola en un comando.

## 4. Ramas

```
<base declarada en CURRENT_STATE>
   └─ <rama de la TASK>               ChatGPT · sólo tasks/<ID>.md
        └─ auto/<id>-issue-<n>        Claude · implementación, tests, REPORT, STATE
```

`<id>` es el ID en minúsculas con `.` → `_`. Claude declara `auto/<id>-issue-<n>` como base para la
próxima TASK. Nadie mergea nada automáticamente.

La rama la crea el workflow, no la action: con un `prompt`, `claude-code-action` corre en modo
automatización, que no crea ramas, y su `base_branch` sólo informa. Se le pasa la rama de la TASK
igual, para que sus herramientas sepan de dónde se partió.

## 5. Autenticación: una sola ruta

**`CLAUDE_CODE_OAUTH_TOKEN`** (la suscripción de Joaquín) para Claude, y el **`GITHUB_TOKEN` del
job** para GitHub. Por qué:

- la documentación oficial de Claude Code la presenta como ruta soportada para GitHub Actions en
  planes Pro/Max, y las corridas usan la suscripción, no facturación de API;
- no hace falta instalar la GitHub App de Claude (que pide, entre otros, Workflows y Actions de
  escritura) ni `id-token: write`;
- el `GITHUB_TOKEN` vive lo que dura el job y lo acota el bloque `permissions`.

Lo que hay que saber:

- consume el **mismo límite de uso** que Joaquín usa en Claude Code interactivo;
- el token dura un año y no hay forma documentada de revocar sólo ese;
- **nunca** se configura `ANTHROPIC_API_KEY`: tendría precedencia y cobraría por API.

Alternativas documentadas y no implementadas: API key de Console (factura aparte), o federación de
identidad (sin secreto estático; requiere organización en Console y factura como API). Pasar a
cualquiera de ellas es una decisión, porque es gasto nuevo.

## 6. Lo que Joaquín hace una sola vez (OPERATOR_ACTION_REQUIRED)

Estado al 2026-10-01, verificado contra GitHub:

1. **Credencial: hecho.** `CLAUDE_CODE_OAUTH_TOKEN` existe desde el 2026-10-01, 12:36 UTC
   (verificado sólo por nombre). Se crea o renueva así: en su máquina, `claude setup-token`
   (aprueba en el navegador), y después:

   ```bash
   gh secret set CLAUDE_CODE_OAUTH_TOKEN -R joaquinriesco-alt/escalimetro
   ```

   El valor se pega en el prompt de `gh`, nunca en un chat, un REPORT o el repo. Para comprobar
   sólo la presencia: `gh secret list -R joaquinriesco-alt/escalimetro`. Dura un año: un
   recordatorio a los 11 meses.
2. **Activación: hecho.** `main` avanzó por fast-forward hasta `edd50e0` (M02) el 2026-10-01,
   12:39 UTC. Lo autorizó Joaquín y lo ejecutó ChatGPT (`tasks/M03.md`, en la rama
   `m03_executor_smoke`); GitHub registra el push como `joaquinriesco-alt`. Lo que corre es la
   copia de `main`: cada cambio del ejecutor, M02.1 incluido, rige recién cuando llega ahí.
3. **Pendiente, recomendado: ajustes de Actions** (Settings → Actions → General). Hoy
   `allowed_actions=all` y `sha_pinning_required=false`:
   - exigir acciones fijadas por SHA;
   - permitir sólo `actions/checkout`, `actions/setup-python`, `actions/upload-artifact`,
     `actions/download-artifact`, `anthropics/claude-code-action` y `oven-sh/setup-bun`; la última
     la usa la de Anthropic por dentro. M02.1 no agrega actions: instala paquetes con `apt`.

## 7. Cómo se apaga

**Una corrida en curso:** «Cancel workflow» en GitHub. Cancelar detiene la publicación: no se
empaqueta ni se empuja nada; `notify` igual avisa en el issue. (Un job que agota su tiempo también
termina «cancelado» y tampoco publica.)

**El ejecutor entero**, con cualquiera de estas: borrar el secreto (`gh secret delete
CLAUDE_CODE_OAUTH_TOKEN -R …`); deshabilitar el workflow (`gh workflow disable
escalimetro-auto-task`); sacar el archivo de la rama por defecto; deshabilitar Actions del repo.

## 8. Riesgos que quedan

- **El SHA fija la action y, con ella, la versión del CLI** (2.1.286, escrita en su código), pero
  el instalador se descarga de `claude.ai` al correr, sin hash.
- **Qué protege el aislamiento de M02.1 y qué no.** Cada comando que Claude corre —tests, `git`,
  `.venv/bin/python`— va a un sandbox de bubblewrap: sin la credencial en su entorno, con su propio
  PID namespace (no ve el `/proc` del runner ni el de la action), con `no_new_privs` (el `sudo`
  del runner no le sirve) y sin docker.
  - Docker equivale a root, porque el usuario `runner` está en su grupo. bubblewrap no bloquea
    sockets Unix: eso lo hace un filtro seccomp opcional de sandbox-runtime que acá no se instala.
    Por eso M02.1 apaga docker y la prueba exige que no responda. Una TASK que necesite docker no
    puede correr en el ejecutor.
  - Otros sockets con privilegios no se revisaron uno por uno.

  Fuera del sandbox quedan la action y el CLI de Claude, que tienen la
  credencial por diseño, y todo lo que corrió antes en el job: en particular `pip install -r
  requirements.txt`, donde un paquete comprometido podría dejar un proceso vivo que la lea
  después. Hay que tratarla como expuesta a las dependencias de `requirements.txt`. Los comandos
  de Claude sí leen el token de GitHub (sólo lectura) y el archivo del evento (público).
- **Liberar AppArmor vale para toda la VM del job.** El `sysctl` a 0 apaga la restricción de user
  namespaces en una VM efímera, igual que hace la propia action con usuarios externos. Un comando
  del sandbox gana superficie de kernel. La alternativa más acotada —un perfil de AppArmor sólo para
  `/usr/bin/bwrap`, como sugiere la documentación de Claude Code— no está probada con el CLI y,
  según sandbox-runtime, podría no cubrir a los procesos que Claude Code lanza dentro del sandbox.
- **El sandbox puede romper un comando sin romper el job.** Upstream reportó casos con bubblewrap
  presente en que cada comando de Bash falla y la action termina en «success»
  (claude-code-action#1547). Si pasa, Claude no logra commitear: la verificación da `NOTHING`, no
  se publica nada y el comentario del issue lo dice. Se mide en la primera ejecución real.
- **El job `claude` corre en `ubuntu-24.04` fijo.** `ubuntu-latest` pasa a 26.04 desde el
  2026-10-19, y 26.04 carga un perfil de AppArmor que deja sin capacidades a los hijos de bwrap.
  - El método de preparación (`apt` y `sysctl` a 0) es el que usa upstream en 24.04, y otros lo
    probaron en esta misma imagen.
  - Los pasos de M02.1 en sí sólo corrieron con binarios falsos: se miden en la primera ejecución
    real.
  - Pasar a 26.04 exige revisar esto antes: la prueba de la compuerta 3 no lo detecta todo.
- **Preparar el aislamiento depende de `apt`.** Lo que decide es instalar `bubblewrap` y `socat`
  desde Ubuntu: si un repositorio de terceros de la imagen hace fallar `apt-get update`, queda sólo
  un aviso. Si la instalación no responde, el job falla cerrado tras tres intentos de hasta
  3 minutos por comando.
- **Reintentar una TASK con el mismo ID no pasa el preflight**, aunque su ejecución haya muerto
  por infraestructura.
  - El preflight cuenta también los issues cerrados: un issue nuevo para M03 da `DUPLICATE_ISSUE`
    (simulado contra GitHub el 2026-10-01).
  - Además M03 da `BASE_SUPERSEDED` cuando M02.1 se declare base.
  - Reintentar con el mismo ID exigiría cambiar el issue anterior y la rama de la TASK, y eso lo
    deciden Joaquín y ChatGPT. Lo directo es una TASK nueva.
- **Atribución, verificada el 2026-10-01:** los issues que abre ChatGPT figuran como
  `joaquinriesco-alt`, `User`, `OWNER`, vía la app `chatgpt-codex-connector` (issues #1 y #2), y el
  de #2 pasó la compuerta 1 y el preflight. La compuerta no distingue un issue de ChatGPT de uno
  de Joaquín: D-012 autoriza a los dos.
- **El log de Actions es público**: el prompt se imprime. Lleva sólo el ID, la rama, el commit y
  reglas; nunca la TASK, el issue ni un secreto.
- Un repo público deja abrir issues a cualquiera; la compuerta 1 es la que impide que uno ajeno
  llegue a un runner con secretos.

## 9. Prueba real

**Lo que pasó**, 2026-10-01:

1. **Atribución** (issue #1): `joaquinriesco-alt`, `User`, `OWNER`, vía `chatgpt-codex-connector`.
   Cumple los campos de identidad de la compuerta 1. #1 no disparó ningún run, porque se cerró
   antes de que `main` tuviera el workflow; la compuerta la cruzó #2.
2. **M03** (issue #2, run `36864248192`):
   - `gate`: success;
   - `claude`: failure al instalar Claude Code, por falta de bubblewrap, antes de cualquier llamada
     a Anthropic;
   - `publish`: success, con verificación `NOTHING`: no publicó nada;
   - `notify`: comentó el resultado.

   No hubo rama `auto/m03-issue-2`, merge ni deploy. Como prueba end-to-end, **FAIL / BLOCKED**.

**Lo que sigue**, después de auditar M02.1 y de que `main` lo incluya:

3. M03, tal como está, no pasa el preflight otra vez: su issue ya existe (`DUPLICATE_ISSUE`), y su
   base deja de ser la vigente cuando M02.1 se declara base (`BASE_SUPERSEDED`). Lo directo es una
   TASK inocua nueva, con
   otro ID y desde la base que declare el estado, igual de verificable: una nota en
   `experiments/<ID>/` con el número de issue y de run, su REPORT y el estado.
4. ChatGPT abre su issue con el contrato.
5. Se comprueba en GitHub:
   - el paso «Aislamiento verificado» dice `AISLAMIENTO: OK`;
   - el run termina verde en los cuatro jobs;
   - aparece la rama `auto/<id>-issue-<n>` con su REPORT;
   - el issue tiene el comentario;
   - `main` no cambió.
6. Recién entonces el estado puede decir **E2E real probado**.

## Fuentes (consultadas el 2026-09-30)

- `anthropics/claude-code-action` en v1.0.238 (commit `12dd8d74c712f5f3669365b2369b558c495b1104`):
  `action.yml`, `src/modes/detector.ts`, `src/modes/agent/index.ts`, `src/github/token.ts`,
  `src/entrypoints/run.ts`, `docs/security.md`, `docs/faq.md`, `docs/setup.md`.
- code.claude.com/docs/en/github-actions (destino de docs.anthropic.com), /authentication,
  /github-actions-cloud-providers, /env-vars.
- docs.github.com: eventos que disparan workflows (`issues` sólo desde la rama por defecto),
  contextos (`jobs.<id>.if` no ve secretos), inyección de scripts, `GITHUB_TOKEN`, sintaxis de
  `permissions`, uso seguro (fijar por SHA).

## Fuentes de M02.1 (consultadas el 2026-10-01)

- El log del job `claude` del run `36864248192`: imagen `ubuntu-24.04` `20260927.320.1`, «Installing
  Claude Code v2.1.286», tres veces «bubblewrap is required for subprocess env scrubbing and
  isolation».
- `anthropics/claude-code-action` en `12dd8d74c712f5f3669365b2369b558c495b1104`:
  - `action.yml`: el paso «Install subprocess isolation dependencies» sólo corre con
    `allowed_non_write_users` y `continue-on-error`. Instala `bubblewrap socat` y pone el `sysctl`
    a 0, que es el mismo método que usa M02.1;
  - `src/entrypoints/run.ts`: CLI 2.1.286 vía `claude.ai/install.sh`;
  - `docs/security.md`.

  Esa misma tarde salió v1.0.239 (2026-10-01, 18:04 UTC). Sólo sube el CLI a 2.1.287 y no toca
  el `action.yml` raíz ni la condición de ese paso. El ejecutor sigue en v1.0.238: cambiar de
  versión no arregla nada y la TASK lo reserva para una decisión.
- code.claude.com/docs/en/env-vars (`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`: PID namespace en Linux),
  /sandboxing (bubblewrap y socat; Ubuntu 24.04 y AppArmor) y /settings-reference
  (`sandbox.bwrapPath`).
- `anthropics/claude-code`, CHANGELOG: el scrub en 2.1.83 y el PID namespace en 2.1.98. En 2.1.227,
  «Fixed every Bash command failing under claude-code-action with allowed_non_write_users on
  GitHub-hosted runners». El issue #96664 dice que el requisito de bubblewrap no está documentado.
- `anthropics/sandbox-runtime` en `117eb928202b53c80d3cb6527d88d1b90e4ca7a9`:
  - el código con el que envuelve los comandos en Linux;
  - el README, sobre Ubuntu 24.04 y AppArmor;
  - el issue #428: dentro de `bwrap` 0.9.0 el bounding set queda vacío y un user namespace anidado
    no puede mapear uids, así que la prueba no lo exige.
- code.claude.com/docs/en/sandboxing: el bloqueo de sockets Unix es un filtro seccomp opcional, y
  el socket de docker figura como la vía de escape canónica al host.
- `containers/bubblewrap` v0.9.0: el orden de los montajes y que `--proc` sólo monta un procfs
  nuevo con `--unshare-pid`.
- `actions/runner-images`:
  - Ubuntu2404-Readme en `ubuntu24/20260927.320`: sin bubblewrap ni socat;
  - #10443 y #11489: la restricción se resuelve en cada workflow;
  - #14748: `ubuntu-latest` pasa a 26.04 desde el 2026-10-19.
- Ubuntu 24.04, notas de versión: la restricción de user namespaces sin privilegios.
- docs.github.com: los runners alojados tienen `sudo` sin contraseña; `shell: bash` corre con
  `-eo pipefail`.
