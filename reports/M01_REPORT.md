# M01 REPORT

## Status

**PASS** — con 7 decisiones pendientes para Joaquín (DR-1 a DR-7) más el público objetivo, que la
doctrina no define. Ninguna bloquea el uso del sistema.

## Qué cambió

El repo pasa a ser el canal entre ChatGPT y Claude. Antes no existía **ningún** mecanismo: ni
`CLAUDE.md`, ni `.github/`, ni issues, ni PRs, ni carpetas de tareas o reportes. Los reportes vivían
sólo en el chat; los `docs/E*.md` guardaban el razonamiento de diseño de cada fase, pero no su
estado, sus tests ni su resultado.

- **`CLAUDE.md`** — Claude Code lo carga solo al abrir el repo. Es la única pieza que automatiza
  transporte sin infraestructura: la doctrina y el protocolo llegan a cada sesión sin que nadie los
  pegue.
- **`docs/ai-development/`** — doctrina, estado, protocolo y decisiones.
- **`tasks/` y `reports/`** — con M01 como primer ciclo real.
- **`tests/test_ai_handoff.py`** — impide que el sistema se desincronice en silencio.
- **Avisos de reemplazo** al inicio de `README.md`, `docs/PRODUCT_V1_SCOPE.md` y
  `docs/PRODUCT_BOUNDARY.md`, que contradecían la doctrina nueva. No se reescribieron.

Ni una línea de `webapp/` ni de `src/`.

## Archivos principales

```
CLAUDE.md                                       nuevo
docs/ai-development/PRODUCT_DOCTRINE.md         nuevo
docs/ai-development/CURRENT_STATE.md            nuevo
docs/ai-development/DEVELOPMENT_PROTOCOL.md     nuevo
docs/ai-development/DECISIONS.md                nuevo · D-001 a D-008
tasks/M01.md                                    nuevo
reports/M01_REPORT.md                           nuevo
tests/test_ai_handoff.py                        nuevo
README.md · docs/PRODUCT_V1_SCOPE.md · docs/PRODUCT_BOUNDARY.md   aviso de 1–2 líneas
```

## Tests

```
baseline:    2036 passed · 2 failed · 8 skipped · 7 xfailed   @ 4c0934a
post-change: 2056 passed · 2 failed · 8 skipped · 7 xfailed   @ árbol de m01_ai_handoff
             (+20 = los tests nuevos de tests/test_ai_handoff.py; re-corridos tras las
              últimas correcciones de documentos: 20 passed)
```

Los 2 fallos son preexistentes desde E34 (listados en `CURRENT_STATE.md`).

## Acceptance criteria

1. **PASS** — doctrina persistida con el core y los roles: `PRODUCT_DOCTRINE.md`, D-001, D-002.
2. **PASS** — `CURRENT_STATE.md` verificado; cada hecho se chequeó contra el repo.
3. **PASS** — formatos de TASK, REPORT y `DECISION_REQUIRED` en `DEVELOPMENT_PROTOCOL.md` §6–§8.
4. **PASS** — `DECISIONS.md` con 9 decisiones, cada una con procedencia citable dentro del repo.
   La de D-001–D-004 y D-009 termina en `tasks/M01.md §Fuente`, un resumen redactado por Claude
   del documento original de Joaquín; lo dice explícitamente.
5. **PASS** — `CLAUDE.md` en la raíz; Claude Code lo carga automáticamente.
6. **PASS** — `tasks/M01.md` + este REPORT.
7. **PASS** — reconstrucción por un agente sin historial: ver Evidencia.
8. **PASS** — DR-1 a DR-7 explícitas, abajo y en `CURRENT_STATE.md`.
9. **PASS** — `tests/test_ai_handoff.py`: detectó en la primera corrida que M01 no tenía REPORT y
   que `CURRENT_STATE.md` enlazaba a un archivo inexistente.
10. **PASS** — sin regresiones (ver Tests).

## Evidencia

**Reconstrucción sin historial (criterio 7).** Un agente de sólo lectura, sin ninguna
conversación previa, leyó únicamente `CLAUDE.md`, los cuatro documentos de `docs/ai-development/`
y `tasks/M01.md`, y respondió las 12 preguntas de M01.

| pasada | leyó | respondidas | parciales | sin respuesta |
|---|---|---|---|---|
| 1 | docs canónicos, antes de las correcciones | 7 | 4 | 1 |
| 2 | docs canónicos + este REPORT, después de corregir | 11 | 1 | 0 |

La pasada 1 encontró defectos reales, y se corrigieron antes de entregar:

| hallazgo | corrección |
|---|---|
| D-001 decía que el ingest *es* core y la doctrina que *no* | unificado: infraestructura; lo que alimenta CREAR PLANO es dependencia directa del core |
| las decisiones citaban «M01 §N», un documento fuera del repo | `tasks/M01.md §Fuente` resume fielmente lo citado; las citas resuelven dentro del repo |
| la razón de D-001 era circular | se dice que la fuente no la da, en vez de inventar una |
| el alcance del congelamiento del motor era ambiguo, y chocaba con CREAR PLANO | D-008 lo documenta y DR-6 lo abre como decisión |
| no estaba dicho quién commitea las TASKs, si ChatGPT no escribe en el repo | protocolo §5.1 |
| faltaban decisiones: BFL, producción | agregadas a pendientes y bloqueos |
| «1/10 planos» y «7 provisionales» no se distinguían | aclarado: 1 plano con 7 etiquetas |
| términos sin definir | glosario en `CURRENT_STATE.md` |
| `CURRENT_STATE` afirmaba el público objetivo | se quitó: la doctrina no lo define; es decisión de Joaquín |

La pasada 2 dejó una pregunta parcial —faltaba la transcripción— y otras inconsistencias menores
(si Joaquín pega o no la TASK, la BFL sin número, qué commit corre en producción). Se corrigieron
también. Las dos transcripciones están en [`experiments/M01/`](../experiments/M01/), condensadas
pero con todas sus calificaciones y hallazgos.

Es el ciclo que M01 pretende instalar —implementación, auditoría independiente, corrección— y
corrió dos veces entero antes de llegar a ChatGPT.

## Regresiones

Ninguna. M01 sólo agrega documentación y un test.

Nota para la auditoría: `scripts/secret_scan.py` marca `tests/test_e32_internal_console.py:227`
como clave de OpenAI. Es un **valor falso deliberado** (`sk-SECRETO…`, junto a
`gm-SECRETO-TAMPOCO-…`) que existe para probar que la consola nunca muestra una credencial. Está
así desde E32–E33; no es de M01 y no es una clave real.

## Limitaciones

1. **Joaquín todavía pega una cosa: el texto de la TASK**, una vez, hacia Claude. ChatGPT no
   escribe en el repo. En el sentido contrario —de Claude hacia ChatGPT— ya no se copia nada:
   reporte, estado y decisiones se leen por URL.
2. **ChatGPT tiene que leer la rama correcta.** Con `main` 107 commits atrás, si no se le indica la
   rama ve código de E16.1 (DR-1).
3. **El test valida forma, no verdad.** Comprueba que cada TASK tiene REPORT y que los enlaces
   resuelven; no puede comprobar que lo escrito en `CURRENT_STATE` sea cierto. Eso sigue
   dependiendo de la disciplina de verificar antes de escribir y de la auditoría de ChatGPT.
4. **No se usan issues, PRs ni Actions.** Con archivos en un repo público alcanza; sumar otro canal
   duplicaría la fuente de verdad sin quitar trabajo.
5. El documento original de M01 **no** se subió verbatim: `tasks/M01.md §Fuente` lo resume. Subir el
   memo completo a un repo público es una decisión de Joaquín (DR-2), no de Claude.

## Decisiones requeridas

### DR-1 — Qué es `main`

Contexto: `main` está en E16.1 (`64fd9c5`, 2026-09-04), 107 commits detrás del trabajo real. Todo
lo posterior a E16.1 vive en una cadena lineal de ramas sin mergear. Producción tampoco corre desde
`main`, y qué commit está desplegado no está registrado.
Por qué no es técnico: decide qué ve por defecto cualquiera que abra el repo, incluido ChatGPT.
- **A.** Mergear la cadena hasta `m01_ai_handoff` en `main` tras auditarla. `main` vuelve a ser la verdad.
- **B.** Declarar una rama de integración (`develop`) como verdad técnica, dejando `main` como está.
- **C.** Seguir como hoy, indicando la rama en cada traspaso.

Impacto: con C, cada auditoría depende de que alguien recuerde nombrar la rama.
Recomendación técnica: **A**. La cadena es lineal, así que el merge es fast-forward y no tiene
conflictos; D-004 y `DEPLOY_GATE` siguen protegiendo producción.
NO IMPLEMENTADO AÚN.

### DR-2 — Visibilidad del repo

Contexto: el repo es público. Este sistema lo aprovecha —ChatGPT lee por URL, sin conectores—, y a
la vez hace pública la doctrina, las decisiones y el estado. Las ramas empujadas ya contienen
pricing (E30: ~USD 100 por propiedad; E17: CLP 14.990).
- **A.** Mantenerlo público y no escribir en el repo nada comercialmente sensible.
- **B.** Hacerlo privado y darle a ChatGPT acceso con el conector de GitHub.
- **C.** Público para el código, y la estrategia en otro lugar privado.

Impacto: B cierra la exposición pero agrega un paso de configuración a ChatGPT.
Recomendación técnica: **B** si la estrategia es sensible; si no, **A**. No es algo que el código
pueda decidir.
NO IMPLEMENTADO AÚN.

### DR-3 — `/property` y el scoring de E17 bajo D-001

Contexto: E17.0–E17.2 construyeron `/property` con el diagnóstico de la publicación en el centro;
D-001 lo declara aplicación. El ingest de URL que contiene sí es dependencia de CREAR PLANO.
- **A.** Conservar el ingest como infraestructura de CREAR PLANO y congelar el scoring.
- **B.** Conservar `/property` como está, como aplicación.
- **C.** Retirar `/property` y extraer el ingest a un módulo compartido.

Recomendación técnica: **A**. El ingest es lo reutilizable (18 campos y 29 fotos por URL,
verificado); el scoring no sirve al core.
NO IMPLEMENTADO AÚN.

### DR-4 — La muestra de 20 avisos de E17

Contexto: estaba lista para correr. Lo que mide —si el diagnóstico acierta y si vale la pena
contactar— es sobre el scoring, que ya no es core.
- **A.** Cancelarla.
- **B.** Reorientarla a insumos de CREAR PLANO: cuántos avisos traen plano, fotos suficientes,
  video, superficie declarada.
- **C.** Correrla como estaba.

Recomendación técnica: **B**. El dato que ya salió —de 5 avisos reales, 1 traía plano en la
galería— es exactamente lo que CREAR PLANO necesita saber.
NO IMPLEMENTADO AÚN.

### DR-5 — Convención de IDs

Contexto: hay dos `E17` distintos. Baja prioridad.
- **A.** La próxima tarea de producto es `E37`; los `E17.x` quedan como están.
- **B.** Renombrar los `E17.x` de producto.

Recomendación técnica: **A**. Renombrar ramas publicadas rompe enlaces sin ganar nada.
NO IMPLEMENTADO AÚN.

### DR-6 — El congelamiento del motor bajo D-001

Contexto: `src/` está congelado desde E28 (D-008). CREAR PLANO —inferir un plano desde fotos— no
tiene nada en el motor sobre qué apoyarse, y el Reconstruction Lab compara motores.
- **A.** Mantener el congelamiento: CREAR PLANO se construye como motor nuevo fuera de `src/escalimetro/`.
- **B.** Levantarlo para CREAR PLANO, con tests de regresión del pipeline actual.
- **C.** Levantarlo por completo.

Recomendación técnica: **A** para empezar. El motor actual resuelve MEJORAR PLANO y tiene tests
que protegen lo que ya funciona; un motor A/B/C nuevo encaja mejor como módulo aparte, y el
Reconstruction Lab justamente quiere comparar motores sin que uno contamine al otro.
NO IMPLEMENTADO AÚN.

### DR-7 — Licencia de BFL

Contexto: BFL está excluido del piloto de ambientación porque su cláusula otorga derechos sobre el
material enviado (D-006, E31). La ambientación es aplicación bajo D-001.
- **A.** Aprobar la licencia y habilitar BFL en el bake-off.
- **B.** Rechazarla y retirar BFL del catálogo.
- **C.** Dejarla pendiente hasta que la ambientación vuelva a ser prioridad.

Recomendación técnica: **C**. Con la ambientación fuera del core, no hay urgencia.
NO IMPLEMENTADO AÚN.

## Commit / branch / PR

Rama `m01_ai_handoff`, un solo commit sobre `4c0934a` (punta de `e17_2_url_first_ingest`).
Este REPORT viaja en ese commit: su hash está en `git log -1 m01_ai_handoff`.
Sin PR, sin merge, sin deploy.

## Exact next action

**Para Joaquín:** decidir DR-1 y DR-6 —son las dos que condicionan el siguiente trabajo— y, con
ChatGPT, escribir la TASK del Internal Reconstruction Lab.
**Para Claude:** nada hasta que exista esa TASK.
