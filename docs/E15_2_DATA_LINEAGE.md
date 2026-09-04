# LINAJE DE DATOS — ESCALÍMETRO E15.2

Sucede a `E15_1_DATA_LINEAGE.md`. E15.1 dibujó la frontera; E15.2 la cierra. Tres agujeros quedaban
abiertos y los tres permitían que un HECHO ESCRITO A MANO ocupara el lugar de un RESULTADO COMPUTADO.

## Qué cambió respecto de E15.1

| hueco | antes de E15.2 | después de E15.2 |
|---|---|---|
| **A** `scale_confidence` | `DERIVED_EVIDENCE`, pero seguía en la whitelist de `case.json`, y `from_case_dir` lo leía de ahí | prohibido en `case.json` (`DERIVED_EVIDENCE_NOT_ALLOWED`); se deriva de `floorplate.json → scale.meta.confidence` |
| **B** `LEGACY_VERIFIED` | pinchaba `floorplate_sha256` y `program_sha256`; un cambio **semántico** del motor no lo invalidaba | el registro declara `producer_engine_baseline` y se contrasta contra `ENGINE_COMPATIBILITY.json` |
| **C** `fit` de presentación | `build_board` aceptaba cualquier `dict` con las claves correctas | sólo acepta `PresentationFit`, dataclass congelada construible únicamente desde una `FitEvidence` |

## La frontera, ahora completa

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  SOURCE FACTS                 case.json                                            │
│  quién es el inmueble         case_id · unit_label · source_name · display_name    │
│                               known_area_m2 · known_area_kind · sibling_units      │
│                               overrides · vision · segmentation · eps · mask_open  │
│                                                                                    │
│  validate_case_input()  ── rechaza ──▶  DERIVED_EVIDENCE_NOT_ALLOWED   (A)         │
│                                          COMPUTED_RESULT_NOT_ALLOWED               │
│                                          UNKNOWN_CASE_FIELD                        │
└───────────────────────────────┬───────────────────────────────────────────────────┘
                                │  from_case_dir()
                                ▼
                          ┌───────────────┐
                          │  CaseContext  │  INPUT. scale_confidence se DERIVA aquí,
                          └───────┬───────┘  no se lee del caso.
                                  │
┌─────────────────────────────────┴───────────────────────────────────────────────────┐
│  DERIVED GEOMETRY / DERIVED EVIDENCE      outputs/floorplate.json                    │
│  qué midió el pipeline                    scale.px_per_m · scale.meta.confidence     │
└─────────────────────────────────┬───────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┴───────────────────────────────────────────────────┐
│  COMPUTED RESULT       E04 metrics.json · E06 fit_robustness_report · E07 gates.json │
│                                                                                      │
│  _freshness()  ── comprueba ──▶  floorplate_sha256 · program_sha256                  │
│                                  producer_engine_baseline vs ENGINE_COMPATIBILITY (B)│
└─────────────────────────────────┬───────────────────────────────────────────────────┘
                                  │  fit_evidence.load()
                                  ▼
                          ┌───────────────┐
                          │  FitEvidence  │  RESULTADO. Dos capas + frescura.
                          └───────┬───────┘
                                  │  PresentationFit.from_evidence(ctx, ev)   (C)
                                  ▼           TypeError si no es una FitEvidence
                          ┌────────────────┐
                          │ PresentationFit│  frozen dataclass. Un dict no la impersona.
                          └───────┬────────┘
                                  ▼
                     build_board(alts, shell, fit=PresentationFit, ctx=CaseContext)
```

## Tabla campo por campo

| FIELD | SEMANTIC TYPE | SOURCE | VALIDATION | CONSUMERS |
|---|---|---|---|---|
| `case_id` | `SOURCE_FACT` | `case.json` | en `CASE_INPUT_FIELDS` | contexto, rutas de artefactos |
| `unit_label` | `SOURCE_FACT` | `case.json` | en `CASE_INPUT_FIELDS`; confirmado contra `floorplate.json` | título, slug, `layout_id` |
| `source_name` | `SOURCE_FACT` | `case.json` | en `CASE_INPUT_FIELDS` | título de lámina, unidad del veredicto |
| `display_name` | `SOURCE_FACT` | `case.json` (opcional) | en `CASE_INPUT_FIELDS` | título de lámina |
| `published_area_m2` | `SOURCE_FACT` | `case.json → known_area_m2` | en `CASE_INPUT_FIELDS` | escala, lámina, barrido E06 |
| `published_area_kind` | `SOURCE_FACT` | `case.json → known_area_kind` | en `CASE_INPUT_FIELDS` | nota de incertidumbre |
| `sibling_units` | `SOURCE_FACT` | `case.json` | en `CASE_INPUT_FIELDS` | evidencia secundaria de escala (E06) |
| `vision`, `segmentation`, `simplify_eps_frac`, `mask_open_px`, `overrides`, `image`, `image_note` | `SOURCE_FACT` (configuración) | `case.json` | en `CASE_INPUT_FIELDS` | pipeline de normalización |
| — | | | | |
| `scale_px_per_m` | `DERIVED_GEOMETRY` | `floorplate.json → scale.px_per_m` | **prohibido en `case.json`** (`DERIVED_EVIDENCE_NOT_ALLOWED`) | shell, solver, lámina |
| `scale_status` | `DERIVED_GEOMETRY` | `floorplate.json → scale.meta.status` | **prohibido en `case.json`** | lámina |
| perímetro, núcleo, pilares, accesos, fachada | `DERIVED_GEOMETRY` | `floorplate.json` | esquema de floorplate | solver, render |
| `scale_confidence` | **`DERIVED_EVIDENCE`** | `floorplate.json → scale.meta.confidence`, etiquetado por `_confidence_label()` (`<0.5 LOW`, `<0.8 MEDIUM`, si no `HIGH`) | **prohibido en `case.json` — cierre A** | lámina, veredicto, `PresentationFit` |
| `usable_area_m2` / `area_m2` | `DERIVED_EVIDENCE` | `floorplate.json` | **prohibido en `case.json`** | E06 |
| — | | | | |
| `technical_fit` | `COMPUTED_RESULT` | `E07/gates.json → E1-T`, o `metrics.json` del layout nominal | **prohibido en `case.json`** (`COMPUTED_RESULT_NOT_ALLOWED`); frescura por hashes + baseline de motor | `FitEvidence`, `PresentationFit`, lámina |
| `robustness_status` | `COMPUTED_RESULT` | `E06/fit_robustness_report.json → classification` | **prohibido en `case.json`**; misma frescura | `FitEvidence`, lámina |
| `hard_violations`, `collisions` | `COMPUTED_RESULT` | `metrics.json` | **prohibido en `case.json`** | `FitEvidence` |
| `program_completeness`, `open_seats` | `COMPUTED_RESULT` | `metrics.json` | **prohibido en `case.json`** | `FitEvidence` |
| `min_scale_factor_exact_fit`, `pct_scenarios_exact_fit`, `primary_constraint` | `COMPUTED_RESULT` | `E06/fit_robustness_report.json` | esquema de E06 | diagnóstico, informe |
| `reason`, `primary_uncertainty` | `COMPUTED_RESULT` | `E06/fit_verdict.json` | — | informe, `PresentationFit` |
| `freshness` | `COMPUTED_RESULT` (meta) | `_freshness()` — hashes de floorplate y programa **+ `producer_engine_baseline`** | `engine_is_compatible()` contra `ENGINE_COMPATIBILITY.json` — cierre B | `FitEvidence`, lámina |
| — | | | | |
| `fit_label` | `PRESENTATION_DERIVED` | `ROBUSTNESS_LABEL[robustness]` | sólo alcanzable vía `PresentationFit.from_evidence` — cierre C | lámina |
| `recommendation` (lámina) | `PRESENTATION_DERIVED` | `RECOMMENDATION_COPY[robustness]` | ídem | lámina |
| `fit` (etiqueta corta) | `PRESENTATION_DERIVED` | derivado de `technical_fit` + `freshness` | ídem | lámina |
| `unit`, `note`, `scale`, `program` | `PRESENTATION_DERIVED` | contexto + evidencia, formateados | ídem | lámina, handoff |
| `_provenance` | `PRESENTATION_DERIVED` (traza) | tupla de artefactos leídos por `FitEvidence` | inmutable (dataclass congelada) | auditoría |
| — | | | | |
| `BROKER_READY`, `READY_FOR_BROKER_REVIEW`, Commercial Gate | **fuera de esta frontera** | E13, con validación humana | test que verifica que no aparezcan en la evidencia técnica | E13 |

## Compatibilidad de motor (cierre B)

`ENGINE_COMPATIBILITY.json` no compara hashes de repositorio: eso declararía incompatible cualquier
cambio de comentario. Declara **transiciones** entre baselines, cada una con:

- `changed_files` / `added_files` / `removed_files` — **computados** desde los baselines guardados, no escritos a mano
- `kind` — `NON_SEMANTIC` o `SEMANTIC`; único juicio humano del archivo
- `semantic_surface_touched` — justificación a nivel de línea para cada archivo tocado que está en la superficie semántica (36 archivos: lo que determina qué computa el solver)

Cadena vigente:

| transición | archivos modificados | nuevos | tipo |
|---|---|---|---|
| E14 → E15 | 8 | 1 (`case_context.py`) | `NON_SEMANTIC` |
| E15 → E15.1 | 3 | 1 (`fit_evidence.py`) | `NON_SEMANTIC` |
| E15.1 → E15.2 | 3 (`case_context.py`, `fit_evidence.py`, `layout/e07/board.py`) | 0 | `NON_SEMANTIC` |

`compatible_with_current = ["E14", "E15", "E15.1", "E15.2"]`.

**Limitación declarada, no demostrada:** E14 es el baseline más antiguo registrado. Los artefactos de
403 y 401 son anteriores a cualquier baseline. Lo que sí está verificado es que E15 regeneró los
artefactos E06 de la 403 idénticos bajo un motor posterior. El resto es una declaración, y está
escrita como tal en el campo `limitation` del archivo.

## Por qué una dataclass congelada (cierre C)

Antes de E15.2 esto pasaba el contrato:

```python
build_board(alts, shell, fit={"technical_fit": "FIT",
                              "fit_label": "ROBUST WITHIN ASSUMED SCALE RANGE"}, ctx=ctx)
```

Fallaba después, con un `IndexError` por una clave faltante — es decir, el contrato no lo rechazaba;
lo rechazaba el azar. Ahora el tipo es la frontera: `build_board` exige una instancia de
`PresentationFit`, y `PresentationFit` sólo se construye desde una `FitEvidence`. Un veredicto es un
RESULTADO COMPUTADO CON PROCEDENCIA, no un blob con las claves correctas.
