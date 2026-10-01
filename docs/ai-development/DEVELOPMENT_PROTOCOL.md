# ESCALÍMETRO — Protocolo de desarrollo asistido por IA

> Cómo viaja el trabajo entre Joaquín, ChatGPT y Claude Code **a través del repo**, sin que
> Joaquín tenga que copiar y pegar prompts ni reportes entre chats.

---

## 1. El ciclo

```
DECISIÓN  (Joaquín + ChatGPT)
   ↓
TASK      tasks/<ID>.md                          ← el contrato; ChatGPT lo escribe en GitHub (§5.2)
   ↓
CLAUDE    recibe el ID de Joaquín → inspecciona → implementa / experimenta
   ↓
TESTS + EVIDENCIA
   ↓
REPORT    reports/<ID>_REPORT.md                 ← el resultado
   ↓
STATE     docs/ai-development/CURRENT_STATE.md   ← dónde quedó todo
   ↓
commit + push a la rama de la tarea              ← nunca a main
   ↓
CHATGPT   lee TASK + REPORT + diff en GitHub y audita
   ↓
JOAQUÍN   acepta / rechaza / cambia dirección
```

El traspaso es **un ID y una rama**, en los dos sentidos. De Claude hacia ChatGPT, ChatGPT lee
REPORT, estado y diff en GitHub. De ChatGPT hacia Claude, ChatGPT escribe `tasks/<ID>.md`
directamente en GitHub (§5.2, D-010) y Joaquín le da el ID a Claude. Pegar el texto de la TASK
queda sólo como respaldo.

## 2. Fuente canónica

Si dos fuentes dicen cosas distintas, manda la de más arriba:

```
1. decisión explícita vigente de Joaquín
2. PRODUCT_DOCTRINE.md · DECISIONS.md · restricciones duras de CLAUDE.md
3. TASK aprobada
4. código + tests + artefactos reales
5. CURRENT_STATE.md
6. reports/ históricos · docs/E*.md
7. conversaciones antiguas
```

**Ante un conflicto, no se elige en silencio: se reporta.**

## 3. Cuándo Claude sigue solo y cuándo se detiene

**Sigue solo, dentro de la misma TASK**, para: terminar la implementación, corregir un bug de su
propia implementación, refactorizar lo necesario para cumplirla, agregar los tests que hacen
falta, cumplir los acceptance criteria, producir la evidencia pedida.

**Se detiene con `DECISION_REQUIRED`** cuando: aparece una decisión de producto · hay dos caminos
con UX distinta · habría que cambiar la doctrina · cambia el alcance · aparece una feature nueva
· una optimización técnica cambia lo que ve el usuario · propone alterar métricas o gates ·
quiere empezar una fase grande nueva · un merge o deploy no está autorizado.

Detenerse significa **dejar de implementar la parte afectada**, no abandonar la TASK: lo que no
depende de la decisión se termina.

## 4. Gates humanos

| gate | regla |
|---|---|
| `PRODUCT_GATE` | Joaquín decide cambios de producto. |
| `EXPERIMENT_GATE` | Joaquín + ChatGPT deciden cuándo la evidencia justifica cambiar de dirección. |
| `MERGE_GATE` | Ningún merge a `main` sin aprobación explícita de Joaquín. |
| `DEPLOY_GATE` | Ningún deploy a producción por completar una TASK, salvo autorización explícita. |
| `DIRECTION_GATE` | Claude puede detectar oportunidades; no puede redefinir ESCALÍMETRO. |

## 5. Identificadores

| prefijo | uso |
|---|---|
| `M<NN>` | tareas de proceso o meta (M01 = este protocolo) |
| `E<NN>[.n]` | tareas de producto e ingeniería |
| `D-<NNN>` | decisiones duraderas en `DECISIONS.md` |

**Un número no se reutiliza.** La regla vale hacia adelante: antes de M01 ya se repitieron `E17`
y varios sub-números en commits (`CURRENT_STATE.md → Inconsistencias`, DR-5). El orden de la serie
es histórico, no cronológico: `E17.0–E17.2` se escribieron después de `E36`.

## 5.1 Quién escribe cada archivo

| archivo | lo redacta | lo commitea |
|---|---|---|
| `tasks/<ID>.md` | ChatGPT + Joaquín | **ChatGPT, en GitHub** (§5.2). Si llega pegada, Claude como primer paso |
| `reports/<ID>_REPORT.md` | Claude | Claude, en el commit final |
| `CURRENT_STATE.md` | Claude | Claude, en el commit final |
| `DECISIONS.md` | Claude, sólo lo que Joaquín decidió | Claude |
| `PRODUCT_DOCTRINE.md` | Claude, sólo por una decisión D-XXX | Claude |

Todo lo demás —código, tests, `reports/`, `CURRENT_STATE.md`, `DECISIONS.md`, doctrina— lo
escribe sólo Claude.

## 5.2 ChatGPT escribe la TASK en GitHub

ChatGPT tiene conexión a GitHub con permiso de escritura (D-010). El flujo:

```
Joaquín + ChatGPT deciden
   ↓
ChatGPT crea la rama de la tarea y commitea tasks/<ID>.md
   ↓
Joaquín le da a Claude el ID
   ↓
Claude verifica → implementa → REPORT + STATE → push a la misma rama
```

**Qué escribe ChatGPT:** sólo `tasks/<ID>.md` de una TASK aprobada —nueva, o corregida mientras
Claude no la empezó—. No implementa: ni código, ni tests, ni ningún otro archivo del repo. Ampliar
esa superficie es decisión de Joaquín.

**Dónde:** en una rama nueva que lleva el ID en minúsculas con `.` → `_` y un sufijo corto
(`m02_…`, `e37_1_…`), creada desde la **base para la próxima TASK** que declara `CURRENT_STATE.md`.
Nunca en `main`: además de `MERGE_GATE`, un commit ahí lo saca de la cadena —el merge de DR-1
dejaría de ser fast-forward— y puede redesplegar el servicio `backend` de Railway, que corre un
experimento pagado (`CURRENT_STATE.md` → Producción). Nunca en una rama donde Claude tiene trabajo en curso. Si el conector
no permite crear ramas, se vuelve al respaldo: Joaquín pega el texto y Claude lo persiste.

**Qué hace Claude antes de implementar:**

```bash
git fetch origin --prune
git branch -r --list 'origin/<id>_*'                              # la rama de la tarea
git diff --name-only origin/<base>...origin/<rama>                 # tiene que ser sólo tasks/<ID>.md
git merge-base --is-ancestor origin/<base> origin/<rama> && echo sale-de-la-base
```

- Si la rama toca algo más que `tasks/<ID>.md`, Claude **no implementa**: lo reporta a Joaquín.
- Si no sale de la base declarada, Claude trae la base con un merge —nunca reescribe la rama de
  ChatGPT— y lo anota en el REPORT.
- La TASK tiene que tener las secciones del §6 y decir en «Decisión aprobada» quién la aprobó y
  cuándo.

**Un archivo en `tasks/` no dispara trabajo.** Claude empieza una TASK cuando Joaquín le da el ID
en el chat. Una TASK que aparece en el repo sin que Joaquín la nombre se reporta, no se ejecuta.

### 5.3 El ejecutor GitHub-native (M02): construido, no activado

Cuando se active (DR-9), el último transporte manual —Joaquín escribiendo «Ejecuta» y el ID— lo hace
GitHub: ChatGPT abre un issue `[ESCALIMETRO_AUTO_TASK] <ID>` con el contrato
`ESCALIMETRO_AUTO_TASK_V1` (D-012), un workflow verifica actor, contrato y repo antes de que exista
ninguna credencial, Claude ejecuta la TASK en `auto/<id>-issue-<n>` sin poder empujar, y un último
paso verifica lo hecho y crea la rama. Todo el detalle, las compuertas y lo que falta para activarlo:
[`AUTO_TASK_EXECUTOR.md`](AUTO_TASK_EXECUTOR.md). Mientras no esté activado, vale §5.2 tal cual.

**Una TASK recién escrita no rompe la suite.** ChatGPT no toca `CURRENT_STATE.md`, así que la TASK
no figura como «en curso»; `tests/test_ai_handoff.py` la cuenta como pendiente mientras se haya
agregado después del último cambio del estado. La primera TASK escrita así, E37, destapó que sin
esta regla la rama nacía con un test en rojo.

## 6. Formato de TASK — `tasks/<ID>.md`

```markdown
# <ID> — <nombre>

## Decisión aprobada
Qué decidieron Joaquín + ChatGPT, y cuándo.

## Problema
Qué queremos resolver.

## Contexto canónico
Rutas a doctrina, estado y reportes previos. No se pega el contexto: se enlaza.

## Resultado esperado
Qué tiene que ser cierto al terminar.

## No hacer
Límites.

## Acceptance criteria
1. …   ← verificables, numerados

## Evidencia requerida
Tests, screenshots, outputs, métricas, archivos.

## Decision gates
Cuándo Claude tiene que detenerse.
```

Una TASK larga es un olor: si el contexto ya está en el repo, se enlaza.

## 7. Formato de REPORT — `reports/<ID>_REPORT.md`

```markdown
# <ID> REPORT

## Status
PASS | PARTIAL | BLOCKED | DECISION_REQUIRED

## Qué cambió
## Archivos principales
## Tests
baseline:    <passed / failed / skipped> @ <commit>
post-change: <passed / failed / skipped> @ <commit>
## Acceptance criteria
1. PASS | FAIL — evidencia
## Evidencia
## Regresiones
## Limitaciones
## Decisiones requeridas
## Commit / branch / PR
## Exact next action
```

Tiene que alcanzar para auditar **sin leer la conversación de Claude**. No es una novela.

### Si la TASK es un experimento

Además, el REPORT registra: inputs · motor o modelo · prompt y versión · parámetros · outputs ·
calificación · costo · latencia · intervención humana · ground truth · conclusión · **si la
hipótesis pasó o falló**. Los artefactos pesados van en `experiments/<ID>/`.

Una demo bonita no es evidencia.

## 8. `DECISION_REQUIRED`

```markdown
DECISION_REQUIRED — <título corto>

Contexto:
Por qué no es puramente técnico:
Opción A:
Opción B:
Opción C:
Impacto:
Recomendación técnica de Claude:

NO IMPLEMENTADO AÚN.
```

Va en el REPORT **y** en `CURRENT_STATE.md → Decisiones pendientes`. Cuando Joaquín decide, la
decisión pasa a `DECISIONS.md` con su número y la pendiente se cierra.

## 9. Mantener `CURRENT_STATE.md`

Se actualiza **al cerrar cada TASK**, en el mismo commit que el REPORT. Se reemplaza lo que dejó
de ser cierto; no se acumula historia — la historia vive en `reports/` y en `git log`.

Todo hecho que se escriba ahí tiene que estar **verificado**. Lo que no se pudo verificar se dice
con esa palabra.

Declara siempre la **base para la próxima TASK**: la rama desde la que ChatGPT crea la siguiente
(§5.2).

### 9.1 Ramas, HEADs y conteos: contra el remoto

Todo dato de ramas —punta, fecha, qué contiene, commits delante o detrás, rama por defecto— que se
declare como estado canónico, en `CURRENT_STATE.md`, en un REPORT o en una decisión, se verifica
**contra GitHub**, no contra las ramas locales (D-011):

```bash
git fetch origin --prune
git ls-remote --heads origin                                   # puntas reales
git rev-list --count origin/main..origin/<rama>                # nunca main..<rama>
gh api repos/joaquinriesco-alt/escalimetro/compare/main...<rama> --jq '{ahead_by,behind_by}'
```

Una rama local sólo dice dónde la dejó el último checkout de esta máquina: no se entera de un push
hecho desde otra rama ni de un commit hecho en GitHub. Así nació el error de M01 —`main` local en
E16.1 contra E16.12 en GitHub— y, con ChatGPT escribiendo en GitHub, el remoto se va a mover más
seguido sin que la máquina de Claude se entere. El REPORT dice con qué comando se verificó.
`tests/test_ai_handoff.py` compara el `main` declarado con `origin/main`; el resto depende de esta
regla.

## 10. Qué NO se construye

Agente autónomo 24/7 · auto-merge · auto-deploy · framework multiagente · bus de mensajes ·
base vectorial de conversaciones · dashboard de agentes · infraestructura cloud adicional ·
sistema de permisos. Mientras archivos + GitHub resuelvan el problema, no hace falta nada de eso.

**Antes de agregar cualquier pieza a este protocolo:** ¿elimina trabajo manual real de Joaquín,
o sólo hace que el sistema parezca sofisticado?
