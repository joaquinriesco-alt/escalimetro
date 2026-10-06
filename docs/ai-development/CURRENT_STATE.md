# ESCALÍMETRO — Estado actual

> **Última actualización:** 2026-10-06 · al cerrar `E48` · rama `auto/e48-issue-31`
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
| `auto/e45_2-issue-17` | `2f99819` (remota de seguimiento del checkout de E46; no reverificada contra GitHub) | rama automática de E45.2, hija de `e45_2_mobile_upload_hardening` |
| `e46_night_adversarial_audit` | `c9a215b` (ídem) | la TASK E46 de ChatGPT (sólo `tasks/E46.md`, verificado con `git diff --name-only`), hija de `auto/e45_2-issue-17` (`git merge-base --is-ancestor`) |
| `auto/e46-issue-18` | — | rama automática de E46, hija de `e46_night_adversarial_audit`. No verificada contra GitHub |
| `e47_2_h01_gt_guard` | `f3240ec` | la TASK E47.2 de ChatGPT (sólo `tasks/E47.2.md`), hija de `auto/e46-issue-18` según el preflight |
| `auto/e47_2-issue-21` | — | rama automática de E47.2, hija de `e47_2_h01_gt_guard`. No verificada contra GitHub |
| `e47_3_h03_atomic_claim` | `798c086` | la TASK E47.3 de ChatGPT (sólo `tasks/E47.3.md`), hija de `auto/e47_2-issue-21` según el preflight |
| `auto/e47_3-issue-22` | — | rama automática de E47.3, hija de `e47_3_h03_atomic_claim`. No verificada contra GitHub |
| `e47_4_h10_global_origin_guard` | `ad63dc8` | la TASK E47.4 de ChatGPT (sólo `tasks/E47.4.md`), hija de `auto/e47_3-issue-22` según el preflight |
| `auto/e47_4-issue-23` | — | rama automática de E47.4, hija de `e47_4_h10_global_origin_guard`. No verificada contra GitHub |
| `e47_5_h02_atomic_import` | `e643558` | la TASK E47.5 de ChatGPT (sólo `tasks/E47.5.md`), hija de `auto/e47_4-issue-23` según el preflight |
| `auto/e47_5-issue-24` | — | rama automática de E47.5, hija de `e47_5_h02_atomic_import`. No verificada contra GitHub |
| `e47_7_h16_photo_classification_perf_recovery` | `75811aa` | la TASK E47.7 de ChatGPT (sólo `tasks/E47.7.md`; recuperación de E47.6, cuyo issue #25 no es reutilizable), hija de `auto/e47_5-issue-24` según el preflight |
| `auto/e47_7-issue-26` | — | rama automática de E47.7, hija de `e47_7_h16_photo_classification_perf_recovery`. No verificada contra GitHub |
| `e47_8_h05_h20_create_retry_exclusion` | `5680f38` | la TASK E47.8 de ChatGPT (sólo `tasks/E47.8.md`), hija de `auto/e47_7-issue-26` según el preflight |
| `auto/e47_8-issue-27` | — | rama automática de E47.8, hija de `e47_8_h05_h20_create_retry_exclusion`. No verificada contra GitHub |
| `e47_9_h05_done_retry_recovery` | `13a5244` | la TASK E47.9 de ChatGPT (sólo `tasks/E47.9.md`), hija de `auto/e47_8-issue-27` según el preflight |
| `auto/e47_9-issue-28` | — | rama automática de E47.9, hija de `e47_9_h05_done_retry_recovery`. No verificada contra GitHub |
| `e47_11_h21_provider_error_resilience_recovery` | `e7b6f63` | la TASK E47.11 de ChatGPT (sólo `tasks/E47.11.md`; recuperación de E47.10, cuyo issue #29 no publicó nada), hija de `auto/e47_9-issue-28` según el preflight |
| `auto/e47_11-issue-30` | `a7d5c2f` (local; no reverificada contra GitHub) | rama automática de E47.11, hija de `e47_11_h21_provider_error_resilience_recovery`. Es el código que audita E48 |
| `e48_final_pre_pilot_readiness_audit` | `522aa1e` | la TASK E48 de ChatGPT (sólo `tasks/E48.md`, verificado con `git diff --name-only a7d5c2f HEAD`), hija de `auto/e47_11-issue-30` según el preflight |
| `auto/e48-issue-31` | esta entrega | rama automática de E48, hija de `e48_final_pre_pilot_readiness_audit` · **base para la próxima TASK**. La publica el workflow. No verificada contra GitHub (el sandbox no permite `git fetch`) |

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
  /lab/campaign/e44/*   web piloto de la campaña 20 + 20 (E44, E45, E45.2): MEJORAR / CREAR sin CLI,
                        panel, evaluación RESULTADO y UX por separado. Estado en DATA_DIR/e44/
                        (manifiesto + eventos de sólo inserción); auditada en E46 y E48 (NOT_READY)
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

**Suite completa en el sandbox de E46** (2026-10-05, Python 3.12.14, sin tesseract ni scikit-image):
`9 failed, 2896 passed, 12 skipped, 7 xfailed, 7 warnings, 1 error in 429.20s (0:07:09)` (≈ 7 min, no los ≈ 12 de otras máquinas). Fallan 9 + 1 error de colección: los 2
preexistentes de arriba y 7 **de entorno** —`test_e16_4` (opencv 5.0.0.93 / numpy 2.5.3 sin lock),
`test_e16_5` (falta el binario `tesseract`) y `test_e17_width_representation` ×5 + `test_e18` (colección)
por `scikit-image`, que no está declarado en ningún lado—. `src/` y esos tests son idénticos a `6324b1f`:
no es regresión de E37–E45.2. Los 378 tests de auditoría de E46 (`tests/test_e46_adv_*.py`) **fijan el
comportamiento actual**: los llamados `…_DEFECTO_Hxx` afirman un defecto y fallarán cuando se corrija.
E37 + E44 + E45 + E45.2: 195 passed.

**Suite completa en el sandbox de E48** (2026-10-06, Python 3.12.14, opencv 5.0.0, numpy 2.5.3, sin tesseract ni scikit-image), al comenzar:
`10 failed, 2976 passed, 12 skipped, 7 xfailed, 6 warnings, 1 error in 507.09s (0:08:27)` @ `522aa1e`. Los 9 fallos + 1 error de colección de E46 más
**uno nuevo, documental**: `test_ai_handoff[E47.2]` —`reports/E47.2_REPORT.md` no usa las secciones del protocolo §7—, que no es de producto y no se corrigió
en E48 (fuera de su diff). **Con los 96 tests de `tests/test_e48_audit.py` y este estado:** `10 failed, 3074 passed, 12 skipped, 7 xfailed, 7 warnings, 1 error in 509.04s (0:08:29)`
—los mismos 10 fallos + 1 error de colección de la línea base, ninguno nuevo—. Regresión focal E37 + E44 + E45 + E45.2 + E46 + E47: 620 passed. Los tests `…_DEFECTO_E48_*` fijan a propósito los bloqueantes de E48 y fallarán cuando se corrijan.

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

**E48** — auditoría final de readiness pre-piloto (issue #31). Status **PASS** (la auditoría se ejecutó completa); **veredicto: `NOT_READY`**.
Sobre el código de E47.11 (`a7d5c2f`) hay **tres bloqueantes reproducibles**, dos de ellos regresiones de lo que E47 declaró cerrado:
*E48-C1* (BLOCKER, **H03 reabierto**) un doble toque de PROCESAR de CREAR a 80–120 ms lanza **dos corridas pagadas**: el nombre del reclamo
(`create`/`create_N`) que E47.8 derivó de los eventos cambia cuando el primer POST registra `create_started`, y la guardia tarda porque `status()`
re-hashea toda la evidencia (65 ms con 87 MB; medido con 87 MB reales: 2 corridas a 100 ms); *E48-B1* (BLOCKER, **H01 reabierto**) el plano real con
marco gris/negro, o coloreado/en modo oscuro y girado, recortado, con borde o capturado, entra al motor como «foto» y `blind_audit` da OK (45 de 100 combinaciones
con GT coloreado; 4 de 75 con GT de papel); *E48-H17* (HIGH, antes MEDIUM) `settle`/`record` sin exclusión duplican eventos (`correction` ×6 con 8 hilos), inflan
`human_prompts` y dan 500. Cierran bien: H02, H05, H10, H16, H20, H21 y E47.9 en secuencia. El resto de los 17 MEDIUM/LOW de E46 se reclasificó
(`KNOWN_RISK_ACCEPTABLE`, H06 con severidad alta justificada, H04 y H13 con condición). Camino feliz MEJORAR/CREAR sin proveedor real y 20 + 20 → `PASS`: sin 500 ni
409 inesperados. Suite completa: `10 failed, 3074 passed` (los mismos fallos conocidos; ver «Tests»). Ninguna llamada pagada, ningún deploy ni merge, `src/` y `webapp/` intactos. Sin decisión de producto nueva (DR-11 sigue
pendiente de Joaquín). Detalle en [`reports/E48_REPORT.md`](../../reports/E48_REPORT.md). **Siguiente: ChatGPT escribe la TASK de reparación mínima
(C1 → H17 → B1) desde la base `auto/e48-issue-31`; luego una re-auditoría corta; sólo con `READY`, deploy controlado de FRONT + proveedor + UN caso real de smoke.**

**E47.11** — recuperación de E47.10 (issue #30). Status **PASS**; **H21 cerrado**: con él quedan cerrados los hallazgos
HIGH/BLOCKER priorizados de E46. Un error técnico de proveedor ya no rompe `settle()`, el caso ni el panel:
`campaign.sanitize_technical_error` sanea de forma determinista (números largos, teléfonos, emails, rutas, identificadores
largos, valores tras palabras de credencial, recorte a 200; genérico seguro si no se puede) antes de persistir el `error` de
`pipeline`/`correction` y de `improve_started`; el texto humano sigue sujeto a `_no_pii`. CREAR FAILED hostil queda asentado,
reintentable, `executed=0`, `completed=0`; MEJORAR hostil no da 409 ni huérfana. Focal E37/E44/E45/E46/E47: 620 passed; suite
completa no corrida. Sin literales con forma de credencial en el diff. Sin deploy, merge ni llamadas pagadas. Detalle en
[`reports/E47.11_REPORT.md`](../../reports/E47.11_REPORT.md). Siguiente entonces: E48 (hecha: ver arriba). Base entonces:
`auto/e47_11-issue-30`.

**E47.9** — recuperación de E47.8 (issue #28). Status **PASS**; **H05 cerrado** (ventana DONE no asentado → segundo POST),
H20 intacto, **H21 sigue pendiente**, readiness del piloto **`NOT_READY`**. `start_create` revalidaba el estado antes de
`settle()`; un DONE sin `pipeline` aún parecía CAPTURED y podía lanzar una segunda corrida inicial. Ahora el estado se revalida
tras asentar (igual que `run_create`): DONE no asentado → 409 y 0 llamadas a `runs.create_initial`; FAILED no asentado →
exactamente un reintento. 2 tests nuevos en `tests/test_e47_8_create_retry.py` (el de DONE falla sin el arreglo). Focal: 477
passed; `test_ai_handoff[E47.2]` sigue fallando (preexistente); suite completa no corrida. Sin deploy, merge ni llamadas pagadas.
Detalle en [`reports/E47.9_REPORT.md`](../../reports/E47.9_REPORT.md).
Base entonces: `auto/e47_9-issue-28`.

**E47.8** — cierra E46-H05 y E46-H20 (issue #27). Status **PASS para H05 y H20**; **H21 sigue pendiente**; readiness del
piloto **`NOT_READY`**. CREAR admite varios `pipeline` iniciales (con `attempt`) mientras ninguno sea DONE: un FAILED queda
inmutable en el historial, **no** cuenta como ejecutado/completado ni consume el N=20; el caso cuenta una vez al llegar un
DONE y desde entonces no hay otra corrida inicial (las correcciones siguen su flujo). `start_create` se reintenta desde la web
(botón VOLVER A INTENTAR), con un reclamo `O_EXCL` por intento (E47.3 intacto: 8 hilos → 1 corrida). `close_blind` ya no cierra
sobre un FAILED. `_find_duplicate` ignora excluidos y la recarga recibe `case_id`/carpeta/proyecto propios; el excluido queda
intacto. Focal: 790 passed, 1 failed ajeno (`test_ai_handoff[E47.2]`, REPORT sin secciones); suite completa no corrida; `skimage`
ausente. Sin deploy, merge ni llamadas pagadas. Detalle en [`reports/E47.8_REPORT.md`](../../reports/E47.8_REPORT.md).

**E47.7** — cierra E46-H16 (issue #26; recuperación de E47.6). Status **PASS para H16**; readiness del piloto sigue
**`NOT_READY`** (H05, H20, H21 y el resto de E46 pendientes). Causa: `add_asset` clasificaba cada foto a resolución
completa con `np.unique(axis=0)`. Ahora `classify.features` mide sobre ≤ 512 px (tamaño original para «ícono»), cuenta
colores con `bincount` (mismo número) y se reutiliza la imagen ya decodificada; `plan_guard` sin PNG temporal y con el GT
leído una vez. Benchmark en el mismo runner (`scripts/e47_7_h16_bench.py`): 12 MP **16,58 s → 0,417 s (≈ 40×)**; lote de 15
**211 s → 5,1 s**. H01 intacto (plano directo, JPEG y redimensionado bloqueados; thresholds sin tocar). 471 passed en
E37/E44/E45/E45.2/E46 (uploads, blindness, campaign) + E47.7; fallos ajenos: `skimage` ×5 y REPORT de E47.2 en handoff.
Suite completa no corrida. Limitación: medido en el runner con imágenes sintéticas, no en Railway/iPhone. Sin deploy, merge
ni llamadas pagadas. Detalle en [`reports/E47.7_REPORT.md`](../../reports/E47.7_REPORT.md).
**Base para la próxima TASK: `auto/e47_7-issue-26`.**

**E47.5** — cierra E46-H02 (issue #24). Status **PASS para H02**; readiness del piloto sigue **`NOT_READY`**
(H05, H16, H20, H21 y el resto de E46 pendientes). `campaign._import_case` corre ahora bajo `_manifest_lock`
(RLock + `flock` en `e44/manifest.lock`): duplicado → evidencia/proyecto → manifiesto es una sola sección
crítica; `exclude` y `register_url_only` usan el mismo candado; `_save` es atómico (temporal único + fsync +
`os.replace`). Dos cargas distintas conservan ambos casos; dos idénticas dan 303 + 400 (nunca 500) y un caso; el
cleanup sólo borra lo propio (nunca el caso de un ganador). Tests F1/F1b/F2/F3 de E46 reescritos como cerrados +
F2b/F3b; 640 passed en E37/E40/E41/E44/E45/E45.2/E46; suite completa, handoff, E42 y E43 no corridos. Limitación:
el candado serializa las importaciones y sólo cubre un host. Sin deploy, merge ni llamadas pagadas. Detalle en
[`reports/E47.5_REPORT.md`](../../reports/E47.5_REPORT.md). **Base para la próxima TASK: `auto/e47_5-issue-24`.**

**E47.4** — cierra E46-H10 (issue #23). Status **PASS para H10**; readiness del piloto sigue **`NOT_READY`**
(H02, H05, H16, H21 y el resto de E46 pendientes). `webapp/origin_guard.py` instala un único
`before_request` global: todo POST con `Origin`/`Referer` de otro host (incluido `Origin: null`) da 403 antes de
la vista; sin cabeceras pasa en rutas comunes (contrato de clientes internos) y se rechaza en las estrictas de
E37/piloto. Única excepción, por regla exacta: `POST /planos/solicitar`. `smoke/openai` con Origin ajeno ya no
llega a la llamada de proveedor. Tests H10/H10b de E46 reescritos como cerrados; 766 passed en
E37/E40–E46 + handoff, 1 failed **ajeno**: el REPORT de E47.2 no tiene las secciones del §7. Sin deploy, merge
ni llamadas pagadas; suite completa no corrida. Limitación: no es un token CSRF. Detalle en
[`reports/E47.4_REPORT.md`](../../reports/E47.4_REPORT.md). **Base para la próxima TASK: `auto/e47_4-issue-23`.**

**E47.3** — cierra E46-H03 (issue #22). Status **PASS para H03**; readiness del piloto sigue **`NOT_READY`**
(H10, H02, H05, H16, H21 y el resto de E46 pendientes). `campaign._claim` crea un archivo con `O_EXCL`
(`cases/<id>/claims/`) **antes** de crear la corrida/propiedad en PROCESAR CREAR, CORREGIR y PROCESAR MEJORAR
(y antes de publicar): dos peticiones simultáneas dan una corrida, una llamada simulada y un 409/400 limpio al
perdedor. El claim se libera si la acción falla sin dejar rastro (recuperación legítima intacta). Limitación: un
proceso muerto con el claim tomado deja el caso en «ya fue lanzada» hasta borrar el archivo; `correct_create`
(CLI) sin proteger. Tests F4/F7 de E46 reescritos (`…_H03_CERRADO`) + F4c; 578 passed en E37/E44/E45/E46; suite
completa no corrida. Sin deploy, merge ni llamadas pagadas. Detalle en
[`reports/E47.3_REPORT.md`](../../reports/E47.3_REPORT.md). **Base para la próxima TASK: `auto/e47_3-issue-22`.**

**E47.2** — cierra E46-H01 (issue #21). Status **PASS para H01**; readiness del piloto sigue **`NOT_READY`**
(H03, H10, H02, H05, H16, H21 y el resto de E46 pendientes). `webapp/plan_guard.py` rechaza, en
`campaign._prepare_create` y antes de crear nada, toda foto que `classify` ve como plano (sobre copia ≤ 512 px)
o que se parece al plano real (miniatura 32×32 en grises, misma proporción ±8 %, diferencia media ≤ 0,12 y
Pearson ≥ 0,90). Umbral conservador, sin calibrar con fotos reales; no cubre recortes/rotaciones, y con GT en
PDF sólo actúa `classify`. 577 tests verdes en E37/E44/E45/E46; suite completa no corrida. Sin deploy, merge ni
llamadas pagadas. Detalle en [`reports/E47.2_REPORT.md`](../../reports/E47.2_REPORT.md). **Base para la
próxima TASK: `auto/e47_2-issue-21`.**

**E46** — auditoría adversarial nocturna pre-piloto (issue #18). Status **PASS** (la auditoría se ejecutó
completa); **veredicto de readiness del piloto: `NOT_READY`**. 24 hallazgos —3 BLOCKER, 4 HIGH, 11 MEDIUM,
7 LOW— ninguno corregido (la TASK lo prohíbe; sólo tests de auditoría, REPORT y este estado). **BLOCKER:**
*H01* un plano re-codificado y subido como «foto» llega al motor y `blind_audit` da OK (la ceguera es sólo
por sha256); *H03* un doble disparo de PROCESAR crea dos corridas pagas (`confirm_paid=True` fijo; ventana
≤ 5 ms); *H10* ~67 rutas POST sin guarda de mismo origen —con `OPENAI_API_KEY` presente, un POST ajeno llega a
`/lab/benchmark/smoke/openai`; llamada sustituida, ninguna real—. **HIGH:** *H02* carrera en las cargas
(un manifiesto sin candado pierde casos: 30/30 rondas; doble envío da 500 en 20/25), *H05* una corrida CREAR
fallida es definitiva y excluir no libera la propiedad, *H16* cada foto de 12 MP cuesta ≈ 12 s de CPU
(20 fotos = 217 s en una petición), *H21* un error de proveedor con una racha de ≥ 9 dígitos mata el panel
y la página del caso. **Invariantes que sí se sostienen:** el GT no aparece en ninguna otra superficie
observable antes del reveal, los DEMO nunca cuentan, cierre → reveal → evaluación en orden y recuperable
ante cortes, la clave del proveedor no se persiste, toda ruta no pública exige credenciales. **NO PROBADO:**
Railway, iPhone/Safari, `docker build`, OpenAI real (modelo `gpt-5.6-sol` sin verificar). Sin deploy, merge ni
llamadas pagadas. Siguiente: Joaquín decide **DR-11** (arrancar o corregir antes) y **DR-12** (reintento y
exclusión); si hay TASK de corrección la escribe ChatGPT desde `auto/e46-issue-18`. Detalle y lista
priorizada en [`reports/E46_REPORT.md`](../../reports/E46_REPORT.md).

Antes, **E45.2** — endurecimiento de la carga móvil de la web piloto (issue #17). Status en
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
| **DR-11** (E46) | **Arrancar el piloto real con el veredicto `NOT_READY` o corregir antes.** A) TASK de corrección con la lista «MUST FIX» (H01, H10, H03, H21, H02, H16, H05/H20) y recién entonces el primer caso; B) probar con las mitigaciones operativas y aceptar H02/H05/H16/H21; C) esperar también a los MEDIUM. Recomendación técnica: A. Detalle en [`reports/E46_REPORT.md`](../../reports/E46_REPORT.md). **E47 aplicó la opción A para H01/H03/H10/H21/H02/H16/H05/H20, y E48 la re-auditó: `NOT_READY`** —quedan C1 (H03), B1 (H01) y H17 en [`reports/E48_REPORT.md`](../../reports/E48_REPORT.md)—; arrancar igual con mitigaciones operativas sigue siendo decisión de Joaquín. | `DEPLOY_GATE` |
| **DR-12** (E46) | **Reintento y exclusión de casos CREAR.** Hoy una corrida fallida es definitiva (sin botón, sin re-subida: el duplicado sigue bloqueando incluso tras `exclude`). A) permitir reintentar registrando cada intento; B) mantener el fallo definitivo pero liberar la propiedad al excluirla; C) dejarlo. Cambia qué cuenta como «ejecutado». | `EXPERIMENT_GATE` |
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
5. **Contradicciones documento ↔ código** que E46 dejó trazadas (detalle y tests en
   [`reports/E46_REPORT.md`](../../reports/E46_REPORT.md) §Contradicciones): `E45.2_REPORT` dice que una
   imagen pequeña en bytes pero enorme en píxeles «no agota memoria» (95 KB ⇒ ≈ 460 MB); `requirements.txt`
   se declara «espejo de pyproject» y no lo es; E44 declara resultados «de sólo inserción» pero `exclude`
   reescribe el manifiesto y `settle` puede duplicar un singleton; el reveal de E37 sigue vivo para los
   proyectos de la campaña.
6. **Contradicciones que E48 dejó trazadas:** (a) E47.8/E47.9 declaran **H03 y H05 cerrados** y E47.2 declara **H01 cerrado**; en sus fronteras no lo están (doble PROCESAR a 80–120 ms →
   dos corridas pagadas; plano real con marco oscuro o coloreado → entra al motor) — ver [`reports/E48_REPORT.md`](../../reports/E48_REPORT.md); (b) E46 titula «11 MEDIUM» y lista 10
   (3 + 4 + 10 + 7 = 24); (c) `reports/E47.2_REPORT.md` no tiene las secciones del protocolo §7 y el test de handoff lo marca en rojo desde entonces; (d) `exclude` (la salida de H20)
   no está en la UI del piloto: sólo en `scripts/e44_campaign.py`.

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
siguiente TASK no debe ampliar features por inercia. **E46 ya auditó el piloto** (veredicto `NOT_READY`,
lista «MUST FIX» en su REPORT): lo que sigue lo decide Joaquín (DR-11, DR-12); E46 no autoriza ninguna
corrección ni numera la TASK siguiente. Se escribe como TASK nueva, no se ejecuta desde acá.

Una TASK nueva la escribe ChatGPT en GitHub desde la base `auto/e48-issue-31`
([protocolo §5.2](DEVELOPMENT_PROTOCOL.md)). **E48 ya auditó el piloto tras la cadena E47** (`NOT_READY`): la TASK siguiente es la reparación mínima de sus tres
bloqueantes (C1, H17, B1 en ese orden); no se numera ni se ejecuta desde acá.

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
