# LINAJE DE DATOS — ESCALÍMETRO E16.1

Sucede a `E15_3_DATA_LINEAGE.md`. E15.1–E15.3 dibujaron y cerraron la frontera **para la Standard
01**. E16 descubrió que otras cinco rutas genéricas nunca la cruzaron: llevaban la identidad de la
Oficina 403 escrita a mano. E16.1 las alinea con el mismo contrato.

## Qué rutas se corrigieron

| ruta | antes | después |
|---|---|---|
| `ai/board02.py` — Standard 02 y 03 | `"543 m² publicados"`, `"539 m² útiles del modelo"` literales; `fit: Dict` | `ctx.published_area_label()`, `metrics["usable_area_m2"]`, `FitEvidence` |
| `validation/boards.py` — lámina ciega de brokers | `"Oficina 403 · 543 m² publicados · 48 personas"` literal | `ctx.unit_label`, `ctx.published_area_label()`, `program["target_headcount"]` |
| `ai/railway_e09_runner.py` | `DEFAULT_CASE = "cases/001_gps_403"`; `EXPECTED_HASH_PREFIX` universal | sin caso por defecto; expectativa declarada por el caso |
| `ai/orchestrator.py` | `project: str = "001_gps_403"` | `project` obligatorio |
| `renderer/side_by_side.py` | rótulo `"ORIGINAL GPS"` | `ORIGINAL` o `ORIGINAL · <fuente del caso>` |

## La frontera, ahora en todas las láminas

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  SOURCE FACTS          case.json                                                      │
│                        case_id · unit_label · display_name · source_name              │
│                        known_area_m2 · known_area_kind · sibling_units                │
│                        validate_case_input() rechaza derivados y resultados           │
└───────────────────────────────┬──────────────────────────────────────────────────────┘
                                │  from_case_dir()
                                ▼
                          ┌───────────────┐
                          │  CaseContext  │◄──────────────────────────────┐
                          └───────┬───────┘                               │
                                  │                                       │
┌─────────────────────────────────┴──────────────────────┐                │
│  DERIVED GEOMETRY      outputs/floorplate.json          │                │
│  perímetro · núcleo · pilares · scale.px_per_m          │                │
│  DERIVED EVIDENCE      scale.meta.status / .confidence  │                │
└─────────────────────────────────┬──────────────────────┘                │
                                  │  scaled_shell()                       │
                                  ▼                                       │
                          ┌───────────────┐                               │
                          │    ShellM     │                               │
                          └───────┬───────┘                               │
                                  │                                       │
┌─────────────────────────────────┴──────────────────────┐                │
│  PROGRAM FACTS         program_templates/*.json         │                │
│  target_headcount · recintos · pesos                    │                │
└─────────────────────────────────┬──────────────────────┘                │
                                  │                                       │
┌─────────────────────────────────┴──────────────────────┐                │
│  COMPUTED RESULT       E04 metrics · E06 robustness      │                │
│                        E07 gates · usable_area_m2        │                │
│  _freshness(): hashes + productor conocido / ancla       │                │
└─────────────────────────────────┬──────────────────────┘                │
                                  │  fit_evidence.load()                   │
                                  ▼                                       │
                          ┌───────────────┐                               │
                          │  FitEvidence  │  has_provenance                │
                          └───────┬───────┘                               │
                                  │                                       │
        ┌─────────────────────────┼─────────────────────────┬─────────────┘
        ▼                         ▼                         ▼
  build_board              build_board02            validation.build_board
  (Standard 01)          (Standard 02 y 03)         (lámina ciega/revelada)
        │                         │                         │
        └─────────── presentation_fit(ctx, evidence) ───────┘
                                  ▼
                            PresentationFit
                                  ▼
                            láminas / summary
```

Y las dos rutas que no son láminas:

```
runner Railway      ── caso ──▶  --case | ESCALIMETRO_CASE          (nunca un default)
                    ── expectativa de regresión ──▶  cases/<caso>/ai/E09/EXPECTED_GEOMETRY_HASHES.json

orquestador IA      ── project ──▶  argumento obligatorio del caller

side_by_side        ── rótulo ──▶  ORIGINAL · {ctx.source_name}
```

## La regla, en una línea

**Nunca:** `PRESENTATION → constantes de caso incrustadas.**
**Siempre:** hechos del caso desde `CaseContext`, geometría desde el floorplate, resultados desde
`FitEvidence`, headcount desde el programa congelado.

## Productor conocido vs ancla verificada — sin cambios desde E15.3

E16.1 no toca este contrato y no fabrica procedencia nueva. La 403 y la 401 siguen con
`producer_engine_baseline: null`, `status: UNKNOWN`, `verified_compatible_from_baseline: "E14"`. **No
se regeneró evidencia técnica como si la hubiera producido E16.1.**

## Qué NO se corrigió, y por qué

`ai/board02.py` sigue imprimiendo la banda de programa (`40 puestos`, `4 oficinas privadas`, `5
salas`…) como literales. Eso es acoplamiento **al programa**, no al caso: cualquier inmueble con el
mismo `office_balanced_48.json` renderiza correcto, y uno con otro programa renderizaría mal. E16.1
tenía alcance declarado —los acoplamientos de caso que E16 encontró— y ampliarlo habría sido tuning
fuera de contrato. Queda como deuda declarada.
