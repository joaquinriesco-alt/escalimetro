# ESCALÍMETRO — Protocolo de desarrollo asistido por IA

> Cómo viaja el trabajo entre Joaquín, ChatGPT y Claude Code **a través del repo**, sin que
> Joaquín tenga que copiar y pegar prompts ni reportes entre chats.

---

## 1. El ciclo

```
DECISIÓN  (Joaquín + ChatGPT)
   ↓
TASK      tasks/<ID>.md                          ← el contrato
   ↓
CLAUDE    inspecciona → implementa / experimenta
   ↓
TESTS + EVIDENCIA
   ↓
REPORT    reports/<ID>_REPORT.md                 ← el resultado
   ↓
STATE     docs/ai-development/CURRENT_STATE.md   ← dónde quedó todo
   ↓
commit + push a una rama propia                  ← nunca a main
   ↓
CHATGPT   lee TASK + REPORT + diff por URL pública y audita
   ↓
JOAQUÍN   acepta / rechaza / cambia dirección
```

El repo es **público**: ChatGPT lee cualquier archivo por su URL de GitHub. De Claude hacia
ChatGPT el traspaso es **un ID y una rama**. De ChatGPT hacia Claude, mientras ChatGPT no escriba
en el repo, **el texto de la TASK se pega una vez** y Claude lo persiste (§5.1).

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

**Un número no se reutiliza.** El orden de la serie es histórico, no cronológico: `E17.0–E17.2`
se escribieron después de `E36`. Ver `CURRENT_STATE.md → Inconsistencias` y DR-5.

## 5.1 Quién escribe cada archivo

| archivo | lo redacta | lo commitea |
|---|---|---|
| `tasks/<ID>.md` | ChatGPT + Joaquín | **Claude, como primer paso de la tarea**, en la rama de la tarea |
| `reports/<ID>_REPORT.md` | Claude | Claude, en el commit final |
| `CURRENT_STATE.md` | Claude | Claude, en el commit final |
| `DECISIONS.md` | Claude, sólo lo que Joaquín decidió | Claude |
| `PRODUCT_DOCTRINE.md` | Claude, sólo por una decisión D-XXX | Claude |

ChatGPT no tiene acceso de escritura al repo y no implementa. Por eso, mientras no haya otra vía,
**el texto de la TASK es lo único que Joaquín todavía pega**, una vez, y queda persistido.
Alternativa si ChatGPT puede crear issues en GitHub: la TASK va como issue y Claude la lee con
`gh issue view <n>` antes de copiarla a `tasks/`.

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

## 10. Qué NO se construye

Agente autónomo 24/7 · auto-merge · auto-deploy · framework multiagente · bus de mensajes ·
base vectorial de conversaciones · dashboard de agentes · infraestructura cloud adicional ·
sistema de permisos. Mientras archivos + GitHub resuelvan el problema, no hace falta nada de eso.

**Antes de agregar cualquier pieza a este protocolo:** ¿elimina trabajo manual real de Joaquín,
o sólo hace que el sistema parezca sofisticado?
