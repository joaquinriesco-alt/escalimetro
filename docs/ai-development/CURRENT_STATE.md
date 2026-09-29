# ESCALÍMETRO — Estado actual

> **Última actualización:** 2026-09-29 · al cerrar `M01` · rama `m01_ai_handoff`
> Todo lo que está acá fue verificado al escribirlo: el código y las ramas contra el repo; las
> cifras de los pilotos contra `.data-lab/` de la máquina de desarrollo, que **no** está en el repo.
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
| `main` | `64fd9c5` · 2026-09-04 | **E16.1**. **107 commits** detrás de `e17_2_url_first_ingest`. Ver DR-1. |
| `e36_real_property_pilot` | `ae64d35` · 2026-09-23 | **congelada para desarrollo**; su experimento sigue activo (ver abajo) |
| `e17_property_potential` | `0819cb3` · 2026-09-24 | E17.0–E17.1 |
| `e17_2_url_first_ingest` | `4c0934a` · 2026-09-25 | **punta del código de producto** |
| `m01_ai_handoff` | esta entrega | lo anterior + este sistema de handoff, sin cambios de funcionalidad |

La cadena es lineal y nada está mergeado:
`main ⊂ e30 ⊂ e31 ⊂ e32 ⊂ e32_2 ⊂ e33 ⊂ e34 ⊂ e35 ⊂ e36 ⊂ e17_property_potential ⊂ e17_2 ⊂ m01`.
Las ramas `e30`–`e35` son eslabones intermedios, cada una contenida en la siguiente.

**Producción:** último estado verificado `e27.3` sano, el 2026-09-21 (reporte E34). **No
verificado desde entonces.** No está registrado en el repo ni qué commit está desplegado ni la URL
(la que se usó responde 404). Producción **no** corre desde `main`, que está en E16.1.

## Arquitectura

```
src/escalimetro/        motor: plano (JPG/PNG/PDF) → floorplate.json → layouts CP-SAT
                        CONGELADO desde E28 contra 6324b1f (D-008)
webapp/                 Flask + SQLite + archivos en ESCALIMETRO_DATA_DIR
  /case/*               herramienta técnica de medición (E27)
  /lab/*                LAB interno: plano comercial + layout tipo + ambientación (E28–E36)
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

`2036 passed · 2 failed · 8 skipped · 7 xfailed` @ `4c0934a` (antes de M01), 2026-09-29.
Después de M01: ver [`reports/M01_REPORT.md`](../../reports/M01_REPORT.md).
Los 2 fallos son **preexistentes desde E34** y no se tocan:
`test_e12_hardening::test_el_html_muestra_la_etapa_que_fallo`,
`test_e15_case_contract::test_las_rutas_de_artefactos_se_derivan_del_caso`.

`tests/test_ai_handoff.py` verifica que este sistema no se desincronice: toda TASK con su REPORT,
enlaces que resuelven, decisiones coherentes, nada que parezca un secreto.

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
- **Producción:** ni la URL ni el commit desplegado están registrados.

## Última tarea completada

**M01** — sistema de handoff por el repo: doctrina, protocolo, decisiones, este estado,
`CLAUDE.md`, `tasks/`, `reports/` y un test de consistencia. Sin cambios de funcionalidad.
Status en [`reports/M01_REPORT.md`](../../reports/M01_REPORT.md).
Antes: **E17.2** — ingest URL-first, cerrado con el fix de WebP en `4c0934a`.

## Tarea actual

Ninguna. Esperando decisión de Joaquín.

## Decisiones pendientes

| id | decisión | gate |
|---|---|---|
| **DR-1** | Qué es `main`. Está 107 commits atrás y GitHub lo muestra por defecto: quien no indique la rama ve código de E16.1. | `MERGE_GATE` |
| **DR-2** | El repo es **público**. Este sistema depende de eso (ChatGPT lee por URL); si se hace privado, ChatGPT necesita un conector de GitHub. Hoy ya es pública la estrategia empujada en ramas anteriores (pricing de E30 y E17). | `PRODUCT_GATE` |
| **DR-3** | Qué hacer con `/property` y el scoring de E17 bajo D-001. | `PRODUCT_GATE` |
| **DR-4** | La muestra de 20 avisos: correrla, reorientarla a insumos de CREAR PLANO, o cancelarla. | `EXPERIMENT_GATE` |
| **DR-5** | Convención de IDs ante los dos `E17`. Baja prioridad. | `PRODUCT_GATE` |
| **DR-6** | Si el congelamiento del motor (D-008) sigue en pie bajo D-001. CREAR PLANO probablemente lo necesite. | `PRODUCT_GATE` |
| **DR-7** | Aprobar o no la licencia de BFL (D-006). | `PRODUCT_GATE` |
| — | **Para quién es ESCALÍMETRO.** La doctrina no lo define. Es estrategia pura: Claude no propone opciones. | `PRODUCT_GATE` |

Opciones de DR-1 a DR-7 en [`reports/M01_REPORT.md`](../../reports/M01_REPORT.md).

## Inconsistencias conocidas

1. **Dos `E17`:** `docs/E17_STRUCTURAL_WIDTH_REPRESENTATION.md` (serie del motor, anterior) y
   `docs/E17_PROPERTY_POTENTIAL.md` + ramas `e17_*` (producto, septiembre).
2. **`README.md`** describe «ETAPA 1». Tiene un aviso al inicio; el resto es historia.
3. **`docs/PRODUCT_V1_SCOPE.md` y `docs/PRODUCT_BOUNDARY.md`** contradicen D-001. Tienen aviso de
   reemplazo; no se reescribieron.
4. **`/property`** pone en el centro un scoring que D-001 declara aplicación.

## Siguiente acción aprobada

**Ninguna técnica.** Hay una iniciativa aprobada sin TASK escrita: **Internal Reconstruction
Lab** ([D-009](DECISIONS.md)), definida en [`tasks/M01.md`](../../tasks/M01.md) §Fuente. Siguiente paso: Joaquín + ChatGPT
escriben su TASK con acceptance criteria. Choca con DR-6 si necesita tocar el motor.

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
| **`THRESHOLD_UNCALIBRATED`** | umbral del motor que todavía no tiene muestra para validarse (D-005) |

## Qué NO decide Claude

Cambiar el core · convertir una aplicación en producto · pricing · UX estratégica · otra
vertical · redefinir CREAR o MEJORAR PLANO · poner PRO, layouts, staging o video en el centro ·
relajar criterios de fidelidad · inventar doctrina · ocultar fallos para mejorar métricas ·
empezar sola una fase grande · merge a `main` · deploy.
