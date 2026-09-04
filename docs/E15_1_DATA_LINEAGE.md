# LINAJE DE DATOS — ESCALÍMETRO E15.1

Para que nunca más haya que adivinar de dónde salió `543`, `8.36`, `ROBUST_WITHIN` o `confidence LOW`.

## La frontera

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  SOURCE FACTS                      case.json                                     │
│  quién es el inmueble              case_id · unit_label · source_name            │
│                                    known_area_m2 · known_area_kind               │
│                                    sibling_units · configuración del pipeline    │
└───────────────────────────────┬──────────────────────────────────────────────────┘
                                │  from_case_dir()
                                ▼
                          ┌───────────────┐
                          │  CaseContext  │   ← INPUT. No transporta veredictos.
                          └───────┬───────┘
                                  │
┌─────────────────────────────────┴────────────────────────────────────────────────┐
│  DERIVED GEOMETRY                  outputs/floorplate.json                        │
│  qué midió el pipeline             perímetro · núcleo · pilares · accesos         │
│                                    scale.px_per_m · scale.meta.status/confidence  │
└───────────────────────────────┬──────────────────────────────────────────────────┘
                                │
┌───────────────────────────────┴──────────────────────────────────────────────────┐
│  COMPUTED EVIDENCE                 layouts/OFFICE_BALANCED_001/metrics.json       │
│  qué encontró el motor             layouts/E06/fit_robustness_report.json         │
│                                    layouts/E06/fit_verdict.json                   │
│                                    layouts/E07/gates.json                         │
└───────────────────────────────┬──────────────────────────────────────────────────┘
                                │  fit_evidence.load()
                                ▼
                          ┌───────────────┐
                          │  FitEvidence  │   ← RESULTADO. Dos capas + frescura.
                          └───────┬───────┘
                                  │
                    fit_evidence.presentation_fit(ctx, evidence)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION            build_board(alts, shell, fit=…, ctx=…)                   │
│  qué se le muestra a alguien   combina HECHOS + EVIDENCIA. No inventa ninguno.    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**La regla:** los hechos son entradas, los veredictos son salidas. No pertenecen al mismo archivo ni
a la misma capa conceptual.

## Tabla campo por campo

| campo | tipo semántico | fuente actual | consumidores |
|---|---|---|---|
| `case_id` | `SOURCE_FACT` | `case.json` | contexto, rutas de artefactos |
| `unit_label` | `SOURCE_FACT` | `case.json` (y `floorplate.json`) | título, slug, `layout_id` |
| `source_name` | `SOURCE_FACT` | `case.json` | título de lámina, unidad del veredicto |
| `display_name` | `SOURCE_FACT` | `case.json` (opcional) | título de lámina |
| `published_area_m2` | `SOURCE_FACT` | `case.json → known_area_m2`, confirmado en `floorplate.json` | escala, lámina, barrido de E06 |
| `published_area_kind` | `SOURCE_FACT` | `case.json` | nota de incertidumbre |
| `sibling_units` | `SOURCE_FACT` | `case.json` | evidencia secundaria de escala (E06) |
| `vision` / `segmentation` / `simplify_eps_frac` / `mask_open_px` | `SOURCE_FACT` (configuración) | `case.json` | pipeline de normalización |
| — | | | |
| `scale.px_per_m` | `DERIVED_GEOMETRY` | `floorplate.json` — `sqrt(px² / m²)` | shell, solver, lámina |
| `scale.method` | `DERIVED_GEOMETRY` | `floorplate.json` — `published_area_inferred` | nota de escala |
| `scale.meta.status` | `DERIVED_GEOMETRY` | `floorplate.json` — `inferred` | lámina |
| `scale.meta.confidence` | **`DERIVED_EVIDENCE`** | `floorplate.json` — `0.4 → LOW` | lámina, veredicto |
| perímetro, núcleo, pilares, accesos, fachada | `DERIVED_GEOMETRY` | `floorplate.json` | solver, render |
| — | | | |
| `technical_fit` | `COMPUTED_RESULT` | `E07/gates.json → E1-T`, o `OFFICE_BALANCED_001/metrics.json` | `FitEvidence`, lámina |
| `program_complete`, `open_seats` | `COMPUTED_RESULT` | `metrics.json → program_completeness` | `FitEvidence` |
| `hard_violations`, `collisions` | `COMPUTED_RESULT` | `metrics.json` | `FitEvidence` |
| `robustness` | `COMPUTED_RESULT` | `E06/fit_robustness_report.json → classification` | `FitEvidence`, lámina |
| `min_scale_factor_exact_fit`, `pct_scenarios_exact_fit` | `COMPUTED_RESULT` | `E06/fit_robustness_report.json` | `FitEvidence` |
| `primary_constraint` | `COMPUTED_RESULT` | `E06/fit_robustness_report.json` | diagnóstico |
| `reason` | `COMPUTED_RESULT` | `E06/fit_verdict.json` — construido de la clasificación y los factores | informe |
| `recommendation` (analítica) | `COMPUTED_RESULT` | `E06/fit_verdict.json` | informe |
| `primary_uncertainty` | `COMPUTED_RESULT` | `E06/fit_verdict.json` | informe |
| — | | | |
| `fit_label` | `PRESENTATION_DERIVED` | `ROBUSTNESS_LABEL[robustness]` en `fit_evidence.py` | lámina |
| `recommendation` (de lámina) | `PRESENTATION_DERIVED` | `RECOMMENDATION_COPY[robustness]` | lámina |
| `unit` del veredicto | `PRESENTATION_DERIVED` | `unit_label` + `source_name` del contexto | lámina, handoff |
| `note`, `disclaimer` | `PRESENTATION_DERIVED` | constante de presentación | lámina |
| `published_area_label`, `scale_label`, `title` | `PRESENTATION_DERIVED` | formateo del contexto | lámina |

## De dónde sale cada número que aparece en la lámina de la Oficina 403

| lo que se lee | valor | origen |
|---|---|---|
| `OFICINA 403 · GPS PROPERTY` | | `case.json → unit_label + source_name` · `SOURCE_FACT` |
| `543 m² publicados` | 543 | `case.json → known_area_m2` · `SOURCE_FACT` |
| `Escala asumida 8,36 px/m` | 8.3565 | `floorplate.json → scale.px_per_m` · `DERIVED_GEOMETRY` |
| `UNCONFIRMED` | | `floorplate.json → scale.meta.status` · `DERIVED_GEOMETRY` |
| `confianza LOW` | 0.4 | `floorplate.json → scale.meta.confidence` · `DERIVED_EVIDENCE` |
| `ROBUST WITHIN ASSUMED SCALE RANGE` | | `E06/fit_robustness_report.json → classification = ROBUST_FIT`, formateado por `ROBUSTNESS_LABEL` · `COMPUTED_RESULT` → `PRESENTATION_DERIVED` |
| `Confirma una dimensión real…` | | `RECOMMENDATION_COPY[ROBUST_FIT]` · `PRESENTATION_DERIVED` |
| `Puestos 40`, `Salas 5`, `Circulación 89 m²` | | `E07/alternatives/*/metrics.json` · `COMPUTED_RESULT` |

Antes de E15.1, las tres filas de `COMPUTED_RESULT` salían de un bloque escrito a mano dentro de
`case.json`.

## Dos capas de fit, no una

Colapsarlas fue lo que hizo que E15 mostrara `FIT NO EVALUADO` para la Oficina 401 cuando E14 ya
había producido evidencia técnica perfectamente válida.

| capa | pregunta | valores | fuente |
|---|---|---|---|
| **TÉCNICA** | ¿existe una solución que cumpla las restricciones duras? | `FIT` · `NO_FIT` · `NOT_EVALUATED` · `FAILURE` | `E07/gates.json → E1-T`, o `metrics.json` del layout nominal |
| **ROBUSTEZ** | ¿se mantiene en el rango de escala asumido? | `ROBUST_FIT` · `ROBUST_NO_FIT` · `LIKELY_FIT` · `BORDERLINE` · `NOT_EVALUATED` | `E06/fit_robustness_report.json → classification` |

Estado actual de los casos:

| caso | técnica | robustez | frescura |
|---|---|---|---|
| Oficina 403 | `FIT` | `ROBUST_FIT` | `LEGACY_VERIFIED` |
| Oficina 401 | `NO_FIT` | `ROBUST_NO_FIT` | `LEGACY_VERIFIED` |
| `TEST_GENERIC_CASE` | `NOT_EVALUATED` | `NOT_EVALUATED` | `NOT_EVALUATED` |

**La disposición comercial no vive aquí.** `BROKER_READY`, `READY_FOR_BROKER_REVIEW` y el Commercial
Gate pertenecen a E13, que tiene su propia validación con humanos. Hay un test que verifica que esos
términos no aparezcan en la evidencia técnica.

## Frescura

Tres caminos, en orden, sin comodines:

1. **El artefacto declara su procedencia** (`floorplate_sha256`, `program_sha256`, `engine_hash`) →
   se compara con la actual → `FRESH` o `STALE`.
2. **No la declara, pero está en `layouts/EVIDENCE_LEGACY.json`** con su `sha256` pinchado, y las
   huellas de floorplate y programa pinchadas ahí siguen coincidiendo → `LEGACY_VERIFIED`.
3. **Ninguna de las dos** → `STALE`.

`LEGACY_VERIFIED` es una excepción explícita, documentada y limitada: el registro nombra archivo por
archivo qué acepta y con qué hash. Un artefacto que no esté listado, o que haya cambiado, sale
`STALE`. Si cambia el floorplate o el programa, todo el registro deja de valer.

El hash del motor **no** se pincha en el registro legado, y es deliberado: E15.1 lo cambia por
diseño, y un cambio de arquitectura de metadatos no invalida un resultado geométrico anterior. Lo que
sí lo invalida es que cambie la geometría o el programa.

**Evidencia `STALE` no se presenta como actual.** La lámina muestra `REQUIERE RECÁLCULO`, nunca el
veredicto anterior.
