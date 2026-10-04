# ESCALÍMETRO — Estado actual

> **Última actualización:** 2026-10-04 · al cerrar `E45.2` · rama `auto/e45_2-issue-17`
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
| `main` | `f466ccf` · 2026-10-02 | merge del PR #9 (**M05**, bootstrap de live status; antes `d097069`, M02.1, que es su ancestro). Es lo que ve `refs/remotes/origin/main` en el checkout de E45.2; **no se reverificó con `git ls-remote`** (el sandbox no permite red). Hasta E45 este estado declaraba `d097069`. Rama por defecto en GitHub. Entre `c6de3f9` y `edd50e0` avanzó por fast-forward desde `c6de3f9` (E16.12) el 2026-10-01, 12:39 UTC, para activar el ejecutor: lo autorizó Joaquín y lo ejecutó ChatGPT (`tasks/M03.md`, en la rama `m03_executor_smoke`); GitHub registra el push como `joaquinriesco-alt`. Contiene toda la cadena hasta M02. |
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
| `auto/e40-issue-6` | — | rama automática de E40, hija de `e40_public_landing`. Punta y conteos **no verificados contra GitHub** |
| `e41_plano_corporativo_request` | `96357ca` | la TASK E41 de ChatGPT (sólo `tasks/E41.md`), hija de `auto/e40-issue-6` según el preflight |
| `auto/e41-issue-10` | — | rama automática de E41, hija de `e41_plano_corporativo_request`. No verificada contra GitHub |
| `e42_request_to_internal_property` | `89a1d0b` | la TASK E42 de ChatGPT (sólo `tasks/E42.md`), hija de `auto/e41-issue-10` según el preflight |
| `auto/e42-issue-11` | — | rama automática de E42, hija de `e42_request_to_internal_property`. No verificada contra GitHub |
| `e43_corporate_plan_delivery` | `2109169` | la TASK E43 de ChatGPT (sólo `tasks/E43.md`), hija de `auto/e42-issue-11` según el preflight |
| `auto/e43-issue-12` | — | rama automática de E43, hija de `e43_corporate_plan_delivery`. No verificada contra GitHub |
| `e44_online_plan_benchmark` | `aee31a6` | la TASK E44 de ChatGPT (sólo `tasks/E44.md`), hija de `auto/e43-issue-12` según el preflight |
| `auto/e44-issue-13` | — | rama automática de E44, hija de `e44_online_plan_benchmark`. No verificada contra GitHub |
| `e45_web_pilot_40_cases` | `62b6a96` | la TASK E45 de ChatGPT (sólo `tasks/E45.md`), hija de `auto/e44-issue-13` según el preflight |
| `auto/e45-issue-14` | — | rama automática de E45, hija de `e45_web_pilot_40_cases`. No verificada contra GitHub |
| `e45_2_mobile_upload_hardening` | `bbaa887` | la TASK E45.2 de ChatGPT (sólo `tasks/E45.2.md`), hija de `auto/e45-issue-14` según el preflight |
| `auto/e45_2-issue-17` | esta entrega | rama automática de E45.2, hija de `e45_2_mobile_upload_hardening` · **base para la próxima TASK**. La publica el workflow. No verificada contra GitHub |

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
  /lab/pedidos/*        bandeja INTERNA (E42, E43, Basic Auth): pedido de /planos → propiedad del LAB
                        → generar candidato → aprobar para entrega → enlace
  /planos/*             superficie PÚBLICA (E40, E41, E43): landing + pedido de Plano Corporativo
                        (email + plano → tabla plano_requests, DATA_DIR/plano_requests/) +
                        /planos/entrega/<token> (plano aprobado, enlace opaco, sin auth)
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

**E45.2** — endurecimiento de la carga móvil de la web piloto (issue #17). Status en
[`reports/E45.2_REPORT.md`](../../reports/E45.2_REPORT.md). CREAR acepta HEIC/HEIF de iPhone (se decodifican
y entran al proyecto como JPG; el motor no depende de HEIC; dependencia nueva `pillow-heif`), con límites
explícitos —20 fotos, 15 MB por foto, 120 MB por lote, 25 MB el plano real— que se aplican leyendo en trozos
y antes de crear caso, proyecto o eventos; el plano real también se valida por contenido y sigue oculto.
MEJORAR no cambió. `src/` intacto. Sin deploy ni llamadas pagadas. Siguiente: probar con un iPhone real.

Antes, **E45** — web piloto para cargar y evaluar los 40 casos de E44 (issue #14). Status **PASS** (sin casos
reales: 0/40). `/lab/campaign/e44/` (Basic Auth): «¿Qué necesitas hacer?» → MEJORAR (1 plano → ANTES/DESPUÉS
por `ensure_case` + `ingest.auto_prepare` + `publish_commercial_floorplan`; sin planta lista queda NECESITA
REVISIÓN en el LAB, nunca un resultado inventado) o CREAR (fotos + m² + referencia; plano real en bloque
«MODO PILOTO — NO SE ENVÍA AL MOTOR»; corrida E37, corrección hija, **CERRAR RECONSTRUCCIÓN Y COMPARAR** →
reveal → lado a lado); panel con MEJORAR n/20 · CREAR n/20 y estados humanos; evaluación RESULTADO y UX/UI
por separado, con historial, guardada como eventos E44 (sin puntaje compuesto). Todo vive en el manifiesto
E44 (`webapp/campaign.py` ampliado: `import_upload`, `start_*`/`settle`, casos DEMO fuera de los N). 50 tests
nuevos; con E37/E40–E44, 270 passed; suite completa **no corrida**; `src/` intacto. Capturas DEMO en
`reports/E45_screens/`. **No medido:** CREAR con proveedor real (falta `OPENAI_API_KEY`), MEJORAR sobre
láminas reales, y la UX (la juzga Joaquín). Siguiente: Joaquín revisa capturas y decide si autoriza un
deploy piloto. Detalle en [`reports/E45_REPORT.md`](../../reports/E45_REPORT.md).

Antes, **E44** — benchmark online 20 MEJORAR + 20 CREAR (issue #13). Status **PARTIAL**: instrumento listo,
**0 de 40 casos reales** capturados/ejecutados/completados. El ejecutor no tiene Internet (no se
relajó), no hay bundle de casos y falta `OPENAI_API_KEY`. Entrega `webapp/campaign.py` +
`scripts/e44_campaign.py` + [`docs/E44_CAMPAIGN.md`](../E44_CAMPAIGN.md): manifiesto con provenance,
importador de bundles capturados fuera del ejecutor, duplicados, PII, estado derivado (una URL no es
un caso), resultados de sólo inserción, auditoría de ceguera, cierre blind → reveal → evaluación sobre
E37, resumen sin score compuesto e índice HTML. 20 tests en verde. Sin conclusiones de calidad: no hay
datos. Siguiente cuello de botella: capturar los bundles fuera del ejecutor y decidir el gasto de
OpenAI (Joaquín). Detalle en [`reports/E44_REPORT.md`](../../reports/E44_REPORT.md).

Antes, **E43** — Plano Corporativo revisable + enlace de entrega (issue #12). Status **PASS**. Cierra en la
rama el circuito SUBIR → PREPARAR → REVISAR → GENERAR → APROBAR → COMPARTIR LINK. Detalle del pedido
en `/lab/pedidos/<id>` (etapa derivada: no lista / lista / candidato / aprobado); «generar» llama a
`floorplan.publish_commercial_floorplan` sólo con la geometría lista (si no, 409 sin efectos);
«APROBAR PARA ENTREGA» congela una copia `FLOORPLAN_DELIVERED`, crea un token opaco (43 caracteres) y
pone el pedido en `READY_FOR_DELIVERY` (nunca `DELIVERED`). `GET /planos/entrega/<token>` sirve, sin
auth, sólo esa copia; token malformado o desconocido → 404; regenerar no cambia lo aprobado; aprobar
dos veces es idempotente. No envía email ni corre motor, layouts o staging. Corrige un hallazgo de
E42: el título de la propiedad llevaba el email del cliente y se dibuja en el plano. Límites: sin
revocación ni re-aprobación; el trazado real sobre un shell confirmado no se ejercitó en tests (se
sustituyó sólo el dibujo). 24 tests nuevos en verde (`tests/test_e43_plano_corporativo_entrega.py`);
con E27–E36 y handoff, 420 passed y sólo falla el preexistente de `origin/main`; suite completa **no
corrida**. Detalle en [`reports/E43_REPORT.md`](../../reports/E43_REPORT.md).

Antes, **E42** — pedido recibido → propiedad interna (issue #11). Status **PASS**. `/lab/pedidos/` (Basic
Auth) lista los pedidos de E41; «PREPARAR EN LAB» (`POST /lab/pedidos/<id>/preparar`) crea una
propiedad del LAB con el plano del pedido como `FLOORPLAN_ORIGINAL` (vía `assets.save_upload`),
guarda `property_id`/`prepared_at` en `plano_requests`, pasa el pedido a `IN_PROGRESS` y redirige a la
propiedad. Idempotente (reclamo atómico `RECEIVED→PREPARING`); si falla, deshace y vuelve a
`RECEIVED`. No corre motor, no envía emails, no entrega nada al cliente. Límite: un proceso muerto a
mitad deja el pedido en `PREPARING`, visible y sin botón. 14 tests nuevos en verde
(`tests/test_e42_pedido_a_propiedad.py`); suite completa **no corrida**; sigue fallando el
preexistente de `origin/main`. Detalle en [`reports/E42_REPORT.md`](../../reports/E42_REPORT.md).

Antes, **E41** — pedido público mínimo de Plano Corporativo (issue #10). Status **PASS**. `/planos/solicitar`
ahora es un formulario con dos inputs, email + plano (PDF/JPG/PNG): un POST válido guarda el archivo
en `DATA_DIR/plano_requests/<id>/`, inserta un pedido `RECEIVED` con id opaco en `plano_requests` y
redirige (303) a una confirmación; uno inválido da 400 sin dejar pedido ni archivo. Sólo recepción:
no corre el motor, no envía emails, no hay panel; los pedidos sólo se ven leyendo la base. Sin
deduplicación más allá de PRG ni freno contra abuso (ver REPORT). Tests nuevos en verde
(`tests/test_e41_plano_corporativo_request.py`); suite completa **no corrida**. Falla
`test_ai_handoff::test_el_main_declarado_es_el_de_origin_no_el_local`: `origin/main` es `f466ccf` y la
tabla declara `d097069`; no es de E41 y no se reparó. Detalle en
[`reports/E41_REPORT.md`](../../reports/E41_REPORT.md).

Antes, **E40** — landing pública mínima (issue #6). Status **PARTIAL**: implementada y con tests,
**sin capturas desktop/mobile** (el sandbox no permitió generarlas). Primera superficie pública:
`/planos/` (hero PLANOS QUE AYUDAN A VENDER, CTA SUBIR PROPIEDAD, Plano Corporativo → Crear Plano →
PRO Layouts) y `/planos/solicitar` (entonces «próximamente»; E41 le puso el formulario). Fuera de
Basic Auth, aislada (`webapp/public.py`, sin base ni motor); el resto de las rutas y `/healthz` quedan
como antes. Sin precios. 21 tests nuevos en verde (`tests/test_e40_public_landing.py`); suite completa **no corrida**.
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

**Producto (E39):** el paso 1 (landing pública) está hecho en E40, salvo las capturas; el paso 2
(pedido de Plano Corporativo) en E41; E42 lo conecta al LAB y E43 produce y entrega por enlace. La
siguiente TASK no debe ampliar features por inercia: debe auditar el circuito completo como producto
y decidir qué falta para probarlo con un caso real. Se escribe como TASK nueva, no se ejecuta desde acá.

Una TASK nueva la escribe ChatGPT en GitHub desde la base `auto/e45_2-issue-17`
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
