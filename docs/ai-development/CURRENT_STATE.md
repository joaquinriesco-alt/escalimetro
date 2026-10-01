# ESCALÍMETRO — Estado actual

> **Última actualización:** 2026-10-01 · al cerrar `E40` · rama `auto/e40-issue-6`
> Todo lo que está acá fue verificado al escribirlo: el código contra el repo; las ramas **contra
> GitHub**, no contra las ramas locales ([protocolo §9.1](DEVELOPMENT_PROTOCOL.md)); las cifras de
> los pilotos contra `.data-lab/` de la máquina de desarrollo, que **no** está en el repo.
> Lo no verificado lo dice.
> Se actualiza al cerrar cada TASK, en el mismo commit que su REPORT.

---

## En una línea

ESCALÍMETRO convierte material inmobiliario —planos, fotos, publicaciones— en **planos
comerciales**. El core declarado es **CREAR PLANO + MEJORAR PLANO** ([D-001](DECISIONS.md)).
Para quién es **no está definido en la doctrina** —es decisión de Joaquín—; hasta hoy el trabajo
se hizo sobre oficinas de corredoras (LAB) y avisos de portales chilenos (E17). Hoy **MEJORAR PLANO existe en parte**
(dentro del LAB) y **CREAR PLANO no existe**: ninguna línea del repo infiere un plano a partir de
fotos, video o una URL. Desde E37 existe el **instrumento** para aprenderlo: un laboratorio que
compara motores de reconstrucción con el plano real oculto hasta el final.

## Ramas

| rama | punta | qué es |
|---|---|---|
| `main` | `d097069` · 2026-10-01 | **M02.1** (antes `edd50e0`, M02). Es lo que ve `refs/remotes/origin/main` en el checkout de E39 y coincide con lo que dice `tasks/M03.1.md`; no se reverificó con `git ls-remote` (sin red en el sandbox). Rama por defecto en GitHub. Entre `c6de3f9` y `edd50e0` avanzó por fast-forward desde `c6de3f9` (E16.12) el 2026-10-01, 12:39 UTC, para activar el ejecutor: lo autorizó Joaquín y lo ejecutó ChatGPT (`tasks/M03.md`, en la rama `m03_executor_smoke`); GitHub registra el push como `joaquinriesco-alt`. Contiene toda la cadena hasta M02. |
| `e36_real_property_pilot` | `ae64d35` · 2026-09-23 | **congelada para desarrollo**; su experimento sigue activo (ver abajo) |
| `e17_2_url_first_ingest` | `4c0934a` · 2026-09-25 | E17.0–E17.2, la punta del código de producto |
| `e37_reconstruction_lab` | `01940c6` · 2026-09-30 | E37 |
| `m02_github_executor` | `edd50e0` · 2026-09-30 | M02; idéntica a `main` |
| `m03_executor_smoke` | `2e14080` · 2026-10-01 | la TASK M03 de ChatGPT (sólo `tasks/M03.md`) · 1 delante de `main`. Su ejecución falló (issue #2) y, tal como está, no pasa el preflight otra vez (ver Bloqueos) |
| `m02_1_bubblewrap_bootstrap` | `d097069` | `main` + la TASK M02.1 + M02.1. Según `tasks/M03.1.md`, `main` avanzó a este commit por fast-forward (ChatGPT, sin force); **Claude no pudo verificarlo contra GitHub** en M03.1 (el sandbox no permitió `git fetch` / `ls-remote`) |
| `m03_1_executor_smoke` | `8fed69e` | la TASK M03.1 de ChatGPT (sólo `tasks/M03.1.md`), hija de `m02_1_bubblewrap_bootstrap` |
| `auto/m03_1-issue-3` | `9a4e83a` | rama automática de M03.1, hija de `m03_1_executor_smoke` |
| `e39_vivan_los_planos_audit` | `3afdcc7` | la TASK E39 de ChatGPT (sólo `tasks/E39.md`), hija de `auto/m03_1-issue-3` según el preflight |
| `auto/e39-issue-5` | `d37887f` (no verificado contra GitHub) | rama automática de E39, hija de `e39_vivan_los_planos_audit` |
| `e40_public_landing` | `69570e4` | la TASK E40 de ChatGPT (sólo `tasks/E40.md`), hija de `auto/e39-issue-5` según el preflight |
| `auto/e40-issue-6` | esta entrega | rama automática de E40, hija de `e40_public_landing` · **base para la próxima TASK**. La publica el workflow. Punta y conteos **no verificados contra GitHub** en E40 (no se corrió `git fetch` / `ls-remote`) |

Las filas de `main`, `m03_executor_smoke` y `m02_github_executor` de arriba son de antes de M03.1;
la afirmación sobre `main` de esta fila, y los conteos, **no están reverificados** (ver §9.1 del protocolo).

`main` contiene la cadena entera hasta M02. Delante de él hay tres ramas:
- las dos que salen de su punta, `m03_executor_smoke` y `m02_1_bubblewrap_bootstrap`;
- `e16_13_invalid_backup`, un respaldo de E16.13 que nunca se promovió: 1 commit propio
  (`ee4334e`) y 101 detrás.

La cadena sigue lineal:
`e30_product_direction` ⊂ … ⊂ `e36_real_property_pilot` ⊂ `e17_property_potential` ⊂
`e17_2_url_first_ingest` ⊂ `m01_ai_handoff` ⊂ `m01_1_remote_truth` ⊂ `e37_reconstruction_lab` ⊂
`m02_github_executor` = `main`.

Verificado el 2026-10-01 contra GitHub:
- las puntas, con `git ls-remote --heads origin`;
- los conteos, con `gh api repos/joaquinriesco-alt/escalimetro/compare/main...<rama>`: `m02_github_executor` identical, `m03_executor_smoke` 1 / 0, `e37_reconstruction_lab` 0 / 2;
- que cada eslabón es ancestro de `origin/main`, con `git merge-base --is-ancestor`;
- todas las ramas de `ls-remote`, con `git rev-list --left-right --count origin/main...origin/<rama>`;
- el push que movió `main`, con `gh api …/activity`.

**Producción:** dos servicios de Railway ([`README.md`](../../README.md) §Railway). GitHub registra
cada deploy (`gh api repos/joaquinriesco-alt/escalimetro/deployments`); el repo no.

- **`web`** —la webapp— despliega `e27_internal_web_app`. Último deploy: `1ae6a0b` (E27.3),
  `success` el 2026-09-21, el mismo día en que se verificó sano (reporte E34). **No verificado
  desde entonces.** Su URL figura en ese deploy de GitHub, no en el repo; la que se usó antes
  respondía 404.
- **`backend`** —runtime del experimento E09— despliega **`main`**, y su arranque **ejecuta E09,
  que llama a OpenAI y a Anthropic**: según el README, cada redeploy cuesta dinero. Cada push a
  `main` de septiembre produjo un deploy segundos después; el último, `c6de3f9`, `success` el
  2026-09-08, con reintentos fallidos el 2026-09-10. **Joaquín informó el 2026-09-30 (TASK M02)
  que deshabilitó el Auto Deploy de `backend`.** El 2026-10-01 `main` se movió (`c6de3f9` →
  `edd50e0`) y GitHub **no registró ningún deploy** (el último sigue siendo el del 2026-09-21,
  verificado ese día). Coincide con lo informado; la configuración de Railway en sí sigue sin ser
  verificable desde acá. Si el Auto Deploy volviera a activarse, mover `main` lo redesplegaría.

## Arquitectura

```
src/escalimetro/        motor: imagen de plano → floorplate.json → layouts CP-SAT
                        CONGELADO desde E28 contra 6324b1f (D-008)
webapp/                 Flask + SQLite + archivos en ESCALIMETRO_DATA_DIR
                        recibe PDF, PNG o JPG; rasteriza el PDF antes de pasarlo al motor
  /case/*, /run/*,      herramienta técnica: casos, corridas y revisión (hasta E27)
  /review/*
  /properties/*         superficie de la propiedad para el cliente (E28.5, E30)
  /staging/*            revisión de ambientación (E31)
  /lab/*                LAB interno: plano comercial + layout tipo + ambientación
                        (E32–E36, sobre piezas de E28–E31)
  /property/*           ingest de URL + diagnóstico de publicación (E17.0–E17.2)
  /lab/reconstruction/* laboratorio de CREAR PLANO: motores, corridas inmutables, plano real
                        oculto (E37). Tablas recon_*; plano real en DATA_DIR/reconstruction_gt/
.github/workflows/      escalimetro-auto-task.yml: ejecutor GitHub-native de TASKs (M02), con el
                        aislamiento de subprocesos de M02.1 (bubblewrap, antes de la credencial)
scripts/auto_task.py    su preflight y su verificación. ACTIVO en main desde el 2026-10-01, con la
                        versión de M02: M02.1 rige cuando llegue a main (DR-10)
```

## Capacidades reales, contra la doctrina

| doctrina | estado | detalle |
|---|---|---|
| **CREAR PLANO** | **instrumento listo, motor sin medir** | E37: laboratorio `/lab/reconstruction/` con registro de motores. Motor real: `openai_direct` (VLM directo, `gpt-5.6-sol`), **nunca corrido**: falta `OPENAI_API_KEY`. Ninguna reconstrucción real todavía. |
| **MEJORAR PLANO** | **parcial** | El LAB produce *plano comercial* desde un plano subido, vía el motor. Lee láminas con unidades demarcadas por color o sembradas; las multiunidad piden un clic (E35). **Calidad sin medir** sobre muestra real: eso es E36. |
| infraestructura: ingest de URL | funciona | 2026-09-25: Portal Inmobiliario + MercadoLibre **4/4 SUCCESS**, sin carga manual; detecta planos en la galería. Zillow bloquea. |
| aplicación: layouts | funciona | CP-SAT, 3 alternativas. |
| aplicación: ambientación | bloqueada | sin proveedor aprobado ni credenciales. |
| aplicación: scoring de publicaciones | funciona | no es core (D-001); ver DR-3. |

## Tests

`2312 passed · 2 failed · 8 skipped · 7 xfailed` en un worktree limpio del commit de M02.1 en
`m02_1_bubblewrap_bootstrap`, 2026-10-01. Detalle en [`reports/M02.1_REPORT.md`](../../reports/M02.1_REPORT.md).
Los 2 fallos son **preexistentes** —desde E27 por lo menos; dependen de artefactos regenerables
que `.gitignore` excluye— y no se tocan:
`test_e12_hardening::test_el_html_muestra_la_etapa_que_fallo`,
`test_e15_case_contract::test_las_rutas_de_artefactos_se_derivan_del_caso`.

`tests/test_ai_handoff.py` verifica que este sistema no se desincronice: toda TASK con su REPORT,
enlaces que resuelven, decisiones coherentes, nada que parezca un secreto, y que el `main` que
declara la tabla de ramas sea el de `origin/main` y no el de la rama local.

## Experimentos

| experimento | estado | espera |
|---|---|---|
| **E36 — piloto de geometría real** (mide MEJORAR PLANO) | activo | a Joaquín: cargar planos reales en `/lab` y juzgar cada componente en «Revisión del plano». Meta: 10 planos **únicos**. Hoy: **1/10**; ese plano tiene 7 etiquetas, **las 7 provisionales**, 0 humanas. Se corre con el LAB de `e36_real_property_pilot` o de cualquier rama posterior; la rama está congelada sólo para desarrollo. |
| **E17 — muestra de 20 avisos** | en pausa | a DR-4. El scoring que mide no es core. |
| **E37 — Reconstruction Lab: Piso Ricardo Lyon I** (mide CREAR PLANO) | listo para correr | a Joaquín: `OPENAI_API_KEY` en el servidor (con `ESCALIMETRO_PASSWORD`), las 34 fotos y el plano real. Pasos en [`docs/E37_RECONSTRUCTION_LAB.md`](../E37_RECONSTRUCTION_LAB.md). La línea base de 2026-08-16 es referencia, no verdad actual. |

`MIN_SAMPLE = 10` de D-005 es **por componente** (etiquetas humanas); la meta de E36 es 10
**planos**. Coinciden en número, no en unidad. Los datos del piloto viven en `.data-lab/` y
`.data-potential/`, fuera del repo.

## Bloqueos (acción de Joaquín, no decisión de producto)

- **Ambientación:** faltan `OPENAI_API_KEY` y `GEMINI_API_KEY` (0/2); corpus 3/8 fotos reales de
  1/3 propiedades. BFL excluido hasta aprobar su licencia (D-006).
- **Reconstrucción (E37):** la misma `OPENAI_API_KEY` falta para el primer motor real. Sin ella el
  laboratorio sólo corre el FIXTURE. Cada corrida real cuesta dinero y pide confirmación; su precio
  por token no está registrado en el repo.
- **Ejecutor GitHub-native (M02):** activo en `main`, pero la copia de `main` no prepara
  bubblewrap. Por eso **cualquier issue de transporte muere al instalar Claude Code**, antes de
  llamar a Anthropic y sin publicar nada: así murió la de M03 (issue #2, run `36864248192`).
  La reparación es M02.1, que espera la auditoría y DR-10.
  - El secreto `CLAUDE_CODE_OAUTH_TOKEN` está **PRESENTE** desde el 2026-10-01 (verificado sólo por
    nombre).
  - **M03, tal como está, no pasa el preflight otra vez.** Su issue ya existe, y el preflight
    rechaza un segundo issue para el mismo ID (`DUPLICATE_ISSUE`, simulado contra GitHub).
    Reintentarla con ese ID exigiría cambiar el issue #2 y su rama, y eso lo deciden Joaquín y
    ChatGPT. Lo directo es una TASK inocua nueva, con otro ID
    ([`AUTO_TASK_EXECUTOR.md`](AUTO_TASK_EXECUTOR.md) §9).
- **Producción:** sin verificar desde el 2026-09-21. `main` ya se movió una vez sin que GitHub
  registrara un deploy (ver Producción). Aun así, la configuración de Railway sólo la ve Joaquín.

## Última tarea completada

**E40** — landing pública mínima (issue #6). Status **PARTIAL**: implementada y con tests, **sin
capturas desktop/mobile** (el sandbox no permitió generarlas). Existe la primera superficie pública:
`/planos/` (hero PLANOS QUE AYUDAN A VENDER, CTA SUBIR PROPIEDAD, Plano Corporativo → Crear Plano →
PRO Layouts) y `/planos/solicitar` («próximamente», no crea pedidos). Fuera de Basic Auth, aislada
(`webapp/public.py`, sin base ni motor); el resto de las rutas y `/healthz` quedan como antes. Sin
precios. 21 tests nuevos en verde (`tests/test_e40_public_landing.py`); suite completa **no corrida**.
Detalle en [`reports/E40_REPORT.md`](../../reports/E40_REPORT.md).

Antes, **E39** — VIVAN LOS PLANOS: auditoría y plan (issue #5). Sólo documentación, sin cambios de producto.
North Star aprobado por Joaquín (2026-10-01): *planos que ayudan a vender*; secuencia
**Plano Corporativo → Crear Plano → PRO Layouts**. Entrega
[`docs/E39_VIVAN_LOS_PLANOS_AUDIT.md`](../E39_VIVAN_LOS_PLANOS_AUDIT.md): inventario clasificado,
producto mínimo, reutilización y plan de 9 pasos pequeños. Hallazgo central: **no existe ninguna
superficie pública** (todo está tras HTTP Basic de cuenta única); lo vendible más cerca es el plano
comercial de `commercial.py`. Status DECISION_REQUIRED en [`reports/E39_REPORT.md`](../../reports/E39_REPORT.md).
`PRODUCT_DOCTRINE.md` **no se cambió**: sigue diciendo core = CREAR + MEJORAR y layouts/PRO como no-core
(ver P-4 abajo).

Antes, **E38** — **no implementó nada**: su run `36927264632` terminó verde pero Claude dejó 0 commits
y 0 archivos (`VERIFY NOTHING`); no es avance de producto. El ejecutor trata mal ese caso (workflow
verde sin commits); **registrado, no reparado**. `tasks/E38.md` existe en su rama (según la TASK).

Antes, **M03.1** — segunda prueba real del ejecutor (issue #3): **PASS global, verificado externamente por
ChatGPT** (dato de la TASK E39; Claude no lo reverificó). El circuito TASK → Actions → Claude →
verificación → publicación quedó probado. Detalle en [`reports/M03.1_REPORT.md`](../../reports/M03.1_REPORT.md),
cuyo status PARTIAL era el de la ejecución antes de esa auditoría.

Antes: **M02.1** — reparación del aislamiento del ejecutor. Antes de la credencial, el job `claude` ahora:
- instala bubblewrap;
- apaga docker, que equivale a root;
- libera AppArmor;
- prueba un sandbox real, y falla cerrado si algo no opera.

El scrub sigue activo y el job corre en `ubuntu-24.04` fijo. Construido y probado sin gasto; **sin
ejecución real**: rige cuando llegue a `main`. Status en
[`reports/M02.1_REPORT.md`](../../reports/M02.1_REPORT.md).

Antes: **M02** (el ejecutor), **E37** (Internal Reconstruction Lab), **M01.1** (verdad remota).

## Tarea actual

Ninguna. Esperando decisión de Joaquín.

## Decisiones pendientes

| id | decisión | gate |
|---|---|---|
| **DR-2** | El repo es **público**, y ya es pública la estrategia empujada en ramas anteriores (el pricing de E30). El precio de E17 no estaba en el repo: lo publicó `M01_REPORT.md`, y M01.1 lo quitó del archivo, pero sigue en el commit `2efd0c3`. Según Joaquín, ChatGPT ya tiene conexión a GitHub con escritura; si esa conexión lee repos privados —no verificado por Claude—, hacerlo privado ya no exige configurar nada nuevo. | `PRODUCT_GATE` |
| **DR-3** | Qué hacer con `/property` y el scoring de E17 bajo D-001. | `PRODUCT_GATE` |
| **DR-4** | La muestra de 20 avisos: correrla, reorientarla a insumos de CREAR PLANO, o cancelarla. | `EXPERIMENT_GATE` |
| **DR-5** | Convención de IDs ante los dos `E17`. Baja prioridad. | `PRODUCT_GATE` |
| **DR-6** | Si el congelamiento del motor (D-008) sigue en pie bajo D-001. CREAR PLANO probablemente lo necesite. | `PRODUCT_GATE` |
| **DR-7** | Aprobar o no la licencia de BFL (D-006). | `PRODUCT_GATE` |
| **DR-8** | Proteger `main` en GitHub. Hoy no tiene protección de rama (verificado): con ChatGPT escribiendo en GitHub, lo único que impide un push directo a `main` es el protocolo, y un push a `main` puede disparar el deploy pagado de `backend`. | `MERGE_GATE` |
| **DR-10** | Llevar M02.1 a `main`: fast-forward de `edd50e0` a la punta de `m02_1_bubblewrap_bootstrap` (2 commits: la TASK y M02.1). Sin eso, el ejecutor sigue muriendo al instalar Claude Code. Antes, la auditoría de ChatGPT. **Posiblemente ya ejecutada:** `origin/main` apunta a `d097069` (M02.1) en el checkout de E39; no verificado contra GitHub. | `MERGE_GATE` |
| **P-1** (E39) | **Pricing: CLP vs UF.** North Star pegado: Plano Corporativo $10.000 CLP, Crear Plano ≈$50.000 CLP, PRO ≈$150.000 CLP/mes; decisión posterior del mismo día: 0,25 UF mejorar y 1 UF crear. No hay decisión de cuál reemplaza a cuál. No publicar precios antes. | `PRODUCT_GATE` |
| **P-2** (E39) | Cuáles son los 2–3 estilos (hoy hay 5 en `presets.py`, sólo de ambientación). Bloquea sólo la variante de presentación del plano. | `PRODUCT_GATE` |
| **P-3** (E39) | Alcance de PRO que el North Star no resuelve (alternativas por prospecto, ambientación incluida, modalidad). | `PRODUCT_GATE` |
| **P-4** (E39) | Reconciliar D-001 (layouts/PRO = no core) con el North Star (PRO Layouts como tercer escalón). Cambiar la doctrina es de Joaquín. | `PRODUCT_GATE` |
| — | **Para quién es ESCALÍMETRO.** La doctrina no lo define. Es estrategia pura: Claude no propone opciones. | `PRODUCT_GATE` |

Detalle de P-1 a P-4 en [`docs/E39_VIVAN_LOS_PLANOS_AUDIT.md`](../E39_VIVAN_LOS_PLANOS_AUDIT.md) §5.

Opciones de DR-2 a DR-7 en [`reports/M01_REPORT.md`](../../reports/M01_REPORT.md); de DR-8, en
[`reports/M01.1_REPORT.md`](../../reports/M01.1_REPORT.md); de DR-10, en
[`reports/M02.1_REPORT.md`](../../reports/M02.1_REPORT.md).

**DR-1** (qué es `main`) y **DR-9** (cómo activar el ejecutor) quedaron resueltas el 2026-10-01,
según `tasks/M03.md` (rama `m03_executor_smoke`). Joaquín autorizó avanzar `main` a M02 y activar el
ejecutor, y ChatGPT ejecutó el fast-forward. Es la opción A de
[`reports/M02_REPORT.md`](../../reports/M02_REPORT.md). Lo que esa opción pedía antes —proteger
`main`— no se hizo y sigue en DR-8.

## Inconsistencias conocidas

1. **IDs repetidos.** Dos `E17`: `docs/E17_STRUCTURAL_WIDTH_REPRESENTATION.md` (serie del motor,
   anterior) y `docs/E17_PROPERTY_POTENTIAL.md` + ramas `e17_*` (producto, septiembre). Y en
   commits, `E28.6`, `E32.2`, `E36.1` y `E36.2` nombran dos pasos distintos cada uno; por eso la
   cita a `E36.1` de D-005 es ambigua.
2. **`README.md`** describe «ETAPA 1». Tiene un aviso al inicio; el resto es historia.
3. **`docs/PRODUCT_V1_SCOPE.md` y `docs/PRODUCT_BOUNDARY.md`** contradicen D-001. Tienen aviso de
   reemplazo; no se reescribieron.
4. **`/property`** está construido sobre el diagnóstico de la publicación, que D-001 declara
   aplicación. Desde E17.1 muestra primero las oportunidades y deja el puntaje como secundario.

## Siguiente acción aprobada

**Ninguna técnica.** Para que el ejecutor funcione, en orden:

1. ChatGPT audita M02.1 ([`reports/M02.1_REPORT.md`](../../reports/M02.1_REPORT.md)).
2. Joaquín decide DR-10: llevar M02.1 a `main`.
3. ChatGPT escribe una TASK inocua nueva, con otro ID porque M03 no pasa el preflight otra vez,
   desde la base declarada, y abre su issue. El ejecutor queda probado de verdad sólo con el
   criterio completo de [`AUTO_TASK_EXECUTOR.md`](AUTO_TASK_EXECUTOR.md) §9:
   - el paso «Aislamiento verificado» dice `AISLAMIENTO: OK`;
   - los cuatro jobs terminan en verde;
   - aparece la rama `auto/<id>-issue-<n>` con su REPORT;
   - el issue tiene el comentario;
   - `main` no cambió.

Independiente: **correr el primer experimento real de E37**, Piso Ricardo Lyon I con
`openai_direct`, que necesita `OPENAI_API_KEY` y el material.

**Producto (E39):** el paso 1 (landing pública) está hecho en E40, salvo las capturas. Siguen los
pasos 2–3 de la auditoría: pedido de Plano Corporativo. Se escribe como TASK nueva, no se ejecuta
desde acá.

Una TASK nueva la escribe ChatGPT en GitHub desde la base `auto/e40-issue-6`
([protocolo §5.2](DEVELOPMENT_PROTOCOL.md)).

## Glosario

| término | significa |
|---|---|
| **plano comercial** | salida de MEJORAR PLANO: el plano existente, limpio y publicable |
| **plano esquemático comercial** | salida de CREAR PLANO: plano inferido, referencial, con incertidumbre declarada |
| **LAB** | consola interna `/lab`, donde se prepara el material de una propiedad |
| **lámina** | la imagen o PDF del plano tal como la publica un corredor |
| **multiunidad** | lámina que dibuja varias oficinas; hay que elegir cuál es la del aviso |
| **floorplate** | `floorplate.json`: la geometría que el motor extrae de una lámina |
| **cabida / test-fit / layout** | cuántos puestos o recintos caben y cómo se distribuyen |
| **PRO** | producto recurrente para trabajar propiedades; aplicación, no core |
| **ambientación** | staging virtual de fotos; aplicación, bloqueada |
| **`THRESHOLD_UNCALIBRATED`** | estado con que el LAB marca sus umbrales de autoaceptación mientras no hay muestra para calibrarlos (`webapp/domain/ingest.py`, D-005). No es parte del motor |

## Qué NO decide Claude

Cambiar el core · convertir una aplicación en producto · pricing · UX estratégica · otra
vertical · redefinir CREAR o MEJORAR PLANO · poner PRO, layouts, staging o video en el centro ·
relajar criterios de fidelidad · inventar doctrina · ocultar fallos para mejorar métricas ·
empezar sola una fase grande · merge a `main` · deploy.
