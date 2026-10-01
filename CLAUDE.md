# CLAUDE.md — ESCALÍMETRO

Claude Code carga este archivo al abrir el repo. Existe para que nadie tenga que pegarte el
contexto: **léelo, y después lee lo que enlaza antes de tocar nada.**

## Antes de empezar cualquier tarea

1. [`docs/ai-development/CURRENT_STATE.md`](docs/ai-development/CURRENT_STATE.md) — dónde está el proyecto hoy.
2. [`docs/ai-development/PRODUCT_DOCTRINE.md`](docs/ai-development/PRODUCT_DOCTRINE.md) — qué es ESCALÍMETRO. El core es **CREAR PLANO** y **MEJORAR PLANO**.
3. [`docs/ai-development/DEVELOPMENT_PROTOCOL.md`](docs/ai-development/DEVELOPMENT_PROTOCOL.md) — el ciclo, los formatos y cuándo detenerte.
4. La TASK: si te dan sólo un ID, ChatGPT la escribió en GitHub, en `tasks/<ID>.md` de la rama
   de la tarea. `git fetch origin` primero, y los chequeos del protocolo §5.2 antes de
   implementar. Si te pegan el texto, tu primer paso es guardarlo como `tasks/<ID>.md` en la rama
   de la tarea. Si la ejecución es automática (issue `ESCALIMETRO_AUTO_TASK_V1`, ver
   [`AUTO_TASK_EXECUTOR.md`](docs/ai-development/AUTO_TASK_EXECUTOR.md)), el prompt te dice la rama
   `auto/<id>-issue-<n>` donde trabajas: commiteas ahí y el workflow publica; tú no empujas.

## Tu rol

Joaquín decide. ChatGPT trabaja producto y experimentos, escribe las TASKs y audita; no implementa
(D-010). **Tú implementas.** Puedes decidir lo técnico local —estructura, nombres, tests, refactors
necesarios, migraciones no destructivas—. **No** puedes cambiar el core, redefinir CREAR o MEJORAR
PLANO, convertir una aplicación en producto, poner PRO / layouts / staging / video en el centro,
abrir otra vertical, tocar pricing o UX estratégica, relajar criterios de fidelidad, inventar
doctrina, ocultar fallos, empezar una fase grande nueva, hacer merge a `main` ni desplegar. Cuando
aparezca algo así: `DECISION_REQUIRED` con el formato del protocolo, y detén **sólo** la parte
afectada.

## Al terminar una tarea

`reports/<ID>_REPORT.md` + actualizar `CURRENT_STATE.md` + commit y push **a la rama de la
tarea**, todo en el mismo commit final. Nunca a `main`.

## Restricciones duras

- `src/` (que es sólo `src/escalimetro/`, el motor) está **congelado** desde E28 contra el commit
  `6324b1f`. Un test exige `git diff 6324b1f HEAD -- src/` vacío. Ver D-008: si el
  congelamiento sigue bajo el core nuevo es una decisión pendiente, no tuya.
- El repo es **público**. Nada de secretos, claves, datos de clientes ni rutas locales en commits.
  Los datos de trabajo viven en `.data-*/`, que está en `.gitignore`.
- Las claves de proveedores sólo se consultan por **presencia**: nunca se imprimen ni se guardan.
- **Ramas, contra el remoto.** Todo dato de ramas, HEADs o commits delante / detrás que declares
  como estado se verifica con `git fetch` + `origin/*`, `git ls-remote` o `gh api …/compare`;
  nunca con ramas locales (protocolo §9.1, D-011). M01 declaró mal `main` por leer la local.
- Dos fallos de la suite son **preexistentes** —desde E27 por lo menos: dependen de artefactos
  regenerables que `.gitignore` excluye— y no son tuyos; están listados en `CURRENT_STATE.md`.
  Cualquier otro fallo sí lo es.

## Convenciones del código

- Tests: `.venv/bin/python -m pytest tests/ -q` (≈12 min). Por tarea: `tests/test_<id>_*.py`;
  las de proceso que no construyen un componente propio van en `tests/test_ai_handoff.py`.
- Todo en castellano: docstrings, comentarios, commits. Los comentarios explican **por qué**, no qué.
- Al editar con reemplazos de texto, **verifica que el ancla exista** antes de escribir: un
  `str.replace` que no encuentra su ancla falla en silencio, y ya pasó más de una vez.
- Estado derivado de artefactos, no declarado: el estado de una propiedad o un pack se recalcula.
- LAB local: `ESCALIMETRO_DEV=1 ESCALIMETRO_DATA_DIR=./.data-lab PYTHONPATH=src PORT=8030 .venv/bin/python wsgi.py`
- Un servidor que lleva horas corriendo sirve plantillas nuevas con Python viejo: reinícialo antes
  de diagnosticar un 500.
