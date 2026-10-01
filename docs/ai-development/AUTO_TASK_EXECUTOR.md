# Ejecutor GitHub-native de TASKs (M02)

> **Estado: CONSTRUIDO · NO ACTIVADO · sin prueba real end-to-end.**
> El workflow existe en la rama `m02_github_executor` y en las que salgan de ella. GitHub sólo
> dispara eventos `issues` desde la rama por defecto (`main`), y `main` no lo tiene. Activarlo es
> la decisión DR-9 de [`CURRENT_STATE.md`](CURRENT_STATE.md). Hasta entonces, el ciclo sigue siendo
> el del [protocolo §5.2](DEVELOPMENT_PROTOCOL.md): Joaquín le dice a Claude «Ejecuta M03».

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
| 3 | job `claude` | sólo con `ok == true` y el mismo actor; token de GitHub **de sólo lectura**; credencial de Anthropic sólo en el paso de Claude; herramientas acotadas, sin `git push`, sin web | Claude no puede empujar ni aunque lea el token |
| 4 | `scripts/auto_task.py verify`, job `publish` | lo que hizo Claude llega como `git bundle`; tiene que descender de la TASK; ningún commit —no sólo el árbol final— toca `.github/`, `src/`, `tasks/`, `.claude/`, `.mcp.json` ni el propio ejecutor (rutas comparadas sin comillas de git y sin distinguir mayúsculas); nada agregado con forma de credencial; ninguna rama `auto/<id>-*` existe todavía | `REJECT`: no se publica nada y `notify` lo dice en el issue |
| 5 | GitHub | `GITHUB_TOKEN` no tiene permiso `workflows`; sus pushes no disparan otros workflows | — |

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

Después de que ChatGPT audite M02 y de que DR-9 esté decidida:

1. **Credencial.** En su máquina, `claude setup-token` (aprueba en el navegador), y después:

   ```bash
   gh secret set CLAUDE_CODE_OAUTH_TOKEN -R joaquinriesco-alt/escalimetro
   ```

   El valor se pega en el prompt de `gh`, nunca en un chat, un REPORT o el repo. Para comprobar
   sólo la presencia: `gh secret list -R joaquinriesco-alt/escalimetro`. Un recordatorio a los
   11 meses, para renovarlo.
2. **Ajustes recomendados de Actions** (Settings → Actions → General):
   - exigir acciones fijadas por SHA (`sha_pinning_required`);
   - permitir sólo `actions/checkout`, `actions/setup-python`, `actions/upload-artifact`,
     `actions/download-artifact`, `anthropics/claude-code-action` y `oven-sh/setup-bun`; la última
     la usa la de Anthropic por dentro.
3. **Activar** según lo que decida DR-9: el workflow y `scripts/auto_task.py` tienen que estar en la
   rama por defecto.

## 7. Cómo se apaga

**Una corrida en curso:** «Cancel workflow» en GitHub. Cancelar detiene la publicación: no se
empaqueta ni se empuja nada; `notify` igual avisa en el issue. (Un job que agota su tiempo también
termina «cancelado» y tampoco publica.)

**El ejecutor entero**, con cualquiera de estas: borrar el secreto (`gh secret delete
CLAUDE_CODE_OAUTH_TOKEN -R …`); deshabilitar el workflow (`gh workflow disable
escalimetro-auto-task`); sacar el archivo de la rama por defecto; deshabilitar Actions del repo.

## 8. Riesgos que quedan

- **El SHA fija la action, no el CLI de Claude Code**, que la action descarga al correr.
- **El código que corre en el job `claude` puede leer la credencial de Anthropic.** Esto incluye a
  Claude vía `.venv/bin/python`, los tests, `conftest.py` y las dependencias de
  `requirements.txt`. `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` saca la credencial del entorno que heredan
  los procesos que Claude lanza, pero es parcial: sin aislamiento de procesos —que este workflow no
  instala—, un proceso del mismo usuario puede leerla de `/proc/<pid>/environ` o con `sudo`. Hay que
  tratarla como expuesta a todo lo que corre en ese job. Ese código también lee el token de GitHub
  (sólo lectura) y el archivo del evento (público). Endurecerlo —instalar `bubblewrap` como hace la
  propia action con usuarios externos— es una opción para DR-9, no un hecho.
- **Quién figura como autor de un issue que abre ChatGPT** (Joaquín o un bot) no está verificado:
  todavía no hay ningún issue en el repo. Si figura como bot, la compuerta lo rechaza —falla
  cerrado— y hace falta decidir a quién más autorizar. Se comprueba antes de activar (§9).
- **El log de Actions es público**: el prompt se imprime. Lleva sólo el ID, la rama, el commit y
  reglas; nunca la TASK, el issue ni un secreto.
- Un repo público deja abrir issues a cualquiera; la compuerta 1 es la que impide que uno ajeno
  llegue a un runner con secretos.

## 9. Primera prueba real (después de activar)

1. **Atribución, sin riesgo:** antes de activar, ChatGPT abre un issue cualquiera en el repo y se
   mira con
   `gh api repos/joaquinriesco-alt/escalimetro/issues/<n> --jq '{u:.user.login,t:.user.type,app:.performed_via_github_app.slug,a:.author_association}'`.
   Tiene que dar `joaquinriesco-alt`, `User`, `OWNER`. Sin workflow en `main`, ese issue no
   dispara nada.
2. **TASK inocua M03:** ChatGPT escribe `tasks/M03.md` en `m03_executor_smoke` desde la base
   declarada. Pide algo verificable y sin riesgo: una nota en `experiments/M03/` con el número de
   issue y de run, su REPORT y el estado con la nueva base, sin tocar código.
3. ChatGPT abre el issue `[ESCALIMETRO_AUTO_TASK] M03` con el contrato.
4. Se comprueba en GitHub: run verde en los tres jobs; rama `auto/m03-issue-<n>` con REPORT;
   comentario en el issue; nada en `main`.
5. Recién entonces el estado puede decir **ACTIVADO** y **E2E real probado**.

## Fuentes (consultadas el 2026-09-30)

- `anthropics/claude-code-action` en v1.0.238 (commit `12dd8d74c712f5f3669365b2369b558c495b1104`):
  `action.yml`, `src/modes/detector.ts`, `src/modes/agent/index.ts`, `src/github/token.ts`,
  `src/entrypoints/run.ts`, `docs/security.md`, `docs/faq.md`, `docs/setup.md`.
- code.claude.com/docs/en/github-actions (destino de docs.anthropic.com), /authentication,
  /github-actions-cloud-providers, /env-vars.
- docs.github.com: eventos que disparan workflows (`issues` sólo desde la rama por defecto),
  contextos (`jobs.<id>.if` no ve secretos), inyección de scripts, `GITHUB_TOKEN`, sintaxis de
  `permissions`, uso seguro (fijar por SHA).
