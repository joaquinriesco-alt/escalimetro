# ESCALÍMETRO — Estado actual

> **Última actualización:** 2026-09-30 · al cerrar `M01.1` · rama `m01_1_remote_truth`
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
fotos, video o una URL.

## Ramas

| rama | punta | qué es |
|---|---|---|
| `main` | `c6de3f9` · 2026-09-08 | **E16.12**. Rama por defecto en GitHub. Ver DR-1. |
| `e36_real_property_pilot` | `ae64d35` · 2026-09-23 | **congelada para desarrollo**; su experimento sigue activo (ver abajo) |
| `e17_property_potential` | `0819cb3` · 2026-09-24 | E17.0–E17.1 |
| `e17_2_url_first_ingest` | `4c0934a` · 2026-09-25 | **punta del código de producto** · 94 commits delante de `main` |
| `m01_ai_handoff` | `2efd0c3` · 2026-09-29 | lo anterior + el sistema de handoff · 95 delante de `main` |
| `m01_1_remote_truth` | esta entrega | lo anterior + M01.1 · **base para la próxima TASK** |

La cadena es lineal, nada está mergeado y ninguna rama está detrás de `main`:
`main` ⊂ `e30_product_direction` ⊂ `e31_staging_pilot` ⊂ `e32_internal_pilot_console` ⊂
`e32_2_entitlement_semantics` ⊂ `e33_simple_product_lab` ⊂ `e34_zero_friction_ingest` ⊂
`e35_robust_zero_friction_ingest` ⊂ `e36_real_property_pilot` ⊂ `e17_property_potential` ⊂
`e17_2_url_first_ingest` ⊂ `m01_ai_handoff` ⊂ `m01_1_remote_truth`.
Las ramas `e30`–`e35` son eslabones intermedios.

Verificado el 2026-09-30 contra GitHub: puntas con `git ls-remote --heads origin`; conteos con
`gh api repos/joaquinriesco-alt/escalimetro/compare/main...<rama>` (`e17_2`: 94 / 0,
`m01_ai_handoff`: 95 / 0) y con `git rev-list` sobre `origin/*` para los eslabones. Hasta M01.1
este documento decía «`main` en E16.1, 107 commits atrás»: era la rama `main` **local**, trece
commits detrás de GitHub ([`reports/M01.1_REPORT.md`](../../reports/M01.1_REPORT.md)).

**Producción:** dos servicios de Railway ([`README.md`](../../README.md) §Railway). GitHub registra
cada deploy (`gh api repos/joaquinriesco-alt/escalimetro/deployments`); el repo no.

- **`web`** —la webapp— despliega `e27_internal_web_app`. Último deploy: `1ae6a0b` (E27.3),
  `success` el 2026-09-21, el mismo día en que se verificó sano (reporte E34). **No verificado
  desde entonces.** Su URL figura en ese deploy de GitHub, no en el repo; la que se usó antes
  respondía 404.
- **`backend`** —runtime del experimento E09— despliega **`main`**, y su arranque **ejecuta E09,
  que llama a OpenAI y a Anthropic**: según el README, cada redeploy cuesta dinero. Cada push a
  `main` de septiembre produjo un deploy segundos después; el último, `c6de3f9`, `success` el
  2026-09-08, con reintentos fallidos el 2026-09-10. Si sigue conectado hoy **no está verificado** (es configuración de Railway). Mover
  `main` —el merge de DR-1, o un push por error— puede redesplegarlo.

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
```

## Capacidades reales, contra la doctrina

| doctrina | estado | detalle |
|---|---|---|
| **CREAR PLANO** | **no existe** | 0 líneas. El ingest trae fotos y datos; nada los convierte en plano. |
| **MEJORAR PLANO** | **parcial** | El LAB produce *plano comercial* desde un plano subido, vía el motor. Lee láminas con unidades demarcadas por color o sembradas; las multiunidad piden un clic (E35). **Calidad sin medir** sobre muestra real: eso es E36. |
| infraestructura: ingest de URL | funciona | 2026-09-25: Portal Inmobiliario + MercadoLibre **4/4 SUCCESS**, sin carga manual; detecta planos en la galería. Zillow bloquea. |
| aplicación: layouts | funciona | CP-SAT, 3 alternativas. |
| aplicación: ambientación | bloqueada | sin proveedor aprobado ni credenciales. |
| aplicación: scoring de publicaciones | funciona | no es core (D-001); ver DR-3. |

## Tests

`2061 passed · 2 failed · 8 skipped · 7 xfailed` sobre el árbol de `m01_1_remote_truth`, 2026-09-30.
Detalle en [`reports/M01.1_REPORT.md`](../../reports/M01.1_REPORT.md).
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

`MIN_SAMPLE = 10` de D-005 es **por componente** (etiquetas humanas); la meta de E36 es 10
**planos**. Coinciden en número, no en unidad. Los datos del piloto viven en `.data-lab/` y
`.data-potential/`, fuera del repo.

## Bloqueos (acción de Joaquín, no decisión de producto)

- **Ambientación:** faltan `OPENAI_API_KEY` y `GEMINI_API_KEY` (0/2); corpus 3/8 fotos reales de
  1/3 propiedades. BFL excluido hasta aprobar su licencia (D-006).
- **Producción:** sin verificar desde el 2026-09-21. Y **antes de cualquier merge a `main`**, hay
  que confirmar en Railway si el servicio `backend` sigue desplegando `main`: su arranque corre un
  experimento pagado (ver Producción).

## Última tarea completada

**M01.1** — el estado de `main` corregido contra GitHub, la regla de verificar ramas contra el
remoto (D-011) y ChatGPT escribiendo las TASKs directamente en GitHub (D-010). Sin cambios de
funcionalidad. Status en [`reports/M01.1_REPORT.md`](../../reports/M01.1_REPORT.md).
Antes: **M01** — el sistema de handoff por el repo; y **E17.2** — ingest URL-first, `4c0934a`.

## Tarea actual

Ninguna. Esperando decisión de Joaquín.

## Decisiones pendientes

| id | decisión | gate |
|---|---|---|
| **DR-1** | Qué es `main`. Está en E16.12, 95 commits detrás de la punta, y GitHub lo muestra por defecto: quien no indique la rama ve código de E16.12. Mergear puede redesplegar el servicio `backend` de Railway (ver Producción). | `MERGE_GATE` |
| **DR-2** | El repo es **público**, y ya es pública la estrategia empujada en ramas anteriores (el pricing de E30). El precio de E17 no estaba en el repo: lo publicó `M01_REPORT.md`, y M01.1 lo quitó del archivo, pero sigue en el commit `2efd0c3`. Según Joaquín, ChatGPT ya tiene conexión a GitHub con escritura; si esa conexión lee repos privados —no verificado por Claude—, hacerlo privado ya no exige configurar nada nuevo. | `PRODUCT_GATE` |
| **DR-3** | Qué hacer con `/property` y el scoring de E17 bajo D-001. | `PRODUCT_GATE` |
| **DR-4** | La muestra de 20 avisos: correrla, reorientarla a insumos de CREAR PLANO, o cancelarla. | `EXPERIMENT_GATE` |
| **DR-5** | Convención de IDs ante los dos `E17`. Baja prioridad. | `PRODUCT_GATE` |
| **DR-6** | Si el congelamiento del motor (D-008) sigue en pie bajo D-001. CREAR PLANO probablemente lo necesite. | `PRODUCT_GATE` |
| **DR-7** | Aprobar o no la licencia de BFL (D-006). | `PRODUCT_GATE` |
| **DR-8** | Proteger `main` en GitHub. Hoy no tiene protección de rama (verificado): con ChatGPT escribiendo en GitHub, lo único que impide un push directo a `main` es el protocolo, y un push a `main` puede disparar el deploy pagado de `backend`. | `MERGE_GATE` |
| — | **Para quién es ESCALÍMETRO.** La doctrina no lo define. Es estrategia pura: Claude no propone opciones. | `PRODUCT_GATE` |

Opciones de DR-1 a DR-7 en [`reports/M01_REPORT.md`](../../reports/M01_REPORT.md); de DR-8, en
[`reports/M01.1_REPORT.md`](../../reports/M01.1_REPORT.md).

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

**Ninguna técnica.** Hay una iniciativa aprobada sin TASK escrita: **Internal Reconstruction
Lab** ([D-009](DECISIONS.md)), definida en [`tasks/M01.md`](../../tasks/M01.md) §Fuente. Siguiente paso: Joaquín + ChatGPT
la deciden y ChatGPT escribe su TASK en GitHub, con acceptance criteria
([protocolo §5.2](DEVELOPMENT_PROTOCOL.md)). Choca con DR-6 si necesita tocar el motor.

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
