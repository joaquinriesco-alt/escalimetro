# LINAJE DE DATOS — ESCALÍMETRO E15.3

Sucede a `E15_2_DATA_LINEAGE.md`. E15.2 dijo haber cerrado la frontera. Cerró tres puertas y dejó dos
abiertas, más una semántica inventada. E15.3 corrige hechos, no narrativa.

## Qué cambió respecto de E15.2

| hueco | antes de E15.3 | después de E15.3 |
|---|---|---|
| **A** presentación | `build_board` exigía un `PresentationFit`. Es un dataclass: su `__init__` es público, así que `PresentationFit(technical_fit="FIT", …)` se construía a mano y llegaba a la lámina | `build_board` recibe la **`FitEvidence`** y deriva la copy dentro del boundary; un `PresentationFit` pasado como argumento se rechaza explícitamente |
| **B** procedencia legada | `producer_engine_baseline: "E14"` más una nota admitiendo que el productor real no se conocía | `producer_engine_baseline: null` + `status: UNKNOWN` + `verified_compatible_from_baseline: "E14"` |
| **C** confianza de escala | umbrales numéricos `<0.5 LOW`, `<0.8 MEDIUM`, `HIGH` inventados en E15.2 | la regla del pipeline, que ya existía en `layout/shell_adapter.py`: método y estado de la escala |
| **§6** afirmación sin respaldo | una `FitEvidence(technical="FIT", source_artifacts=[])` era presentable | `has_provenance`: una afirmación exige artefactos; `NOT_EVALUATED` no |

## La regla nueva: una afirmación necesita evidencia, una ausencia no

```python
@property
def has_provenance(self) -> bool:
    if not self.evaluated:      # NOT_EVALUATED es la AUSENCIA de un resultado
        return True             # exigirle artefactos sería exigir procedencia de la nada
    return bool(self.source_artifacts)
```

`FIT` y `NO_FIT` son afirmaciones sobre el mundo. `NOT_EVALUATED` es la constatación de que nadie
miró. Pedirle procedencia a lo segundo dejaría al caso genérico sin poder decir "no lo he evaluado".

## Dos contratos de procedencia, que no se colapsan

Este es el punto de E15.3. Un archivo de procedencia no puede decir algo que no sabemos.

| | **PRODUCTOR CONOCIDO** | **ANCLA DE COMPATIBILIDAD VERIFICADA** |
|---|---|---|
| qué afirma | qué versión del motor produjo este artefacto | desde qué baseline registrado se puede verificar compatibilidad hacia el vigente |
| cómo se sabe | el artefacto lo registró al producirse | comparando baselines guardados |
| campo | `producer_engine_baseline` + `status: KNOWN` | `verified_compatible_from_baseline` |
| quién lo usa | artefactos con procedencia propia | el registro legado de la 403 y la 401 |
| si falta | `STALE` | `STALE` |

La 403 y la 401 son anteriores a que existiera ningún baseline. Su productor es **desconocido**, y así
está escrito. Lo que sí es verificable —que E14 es el baseline registrado más antiguo desde el que se
puede comprobar compatibilidad— vive en su propio campo, con su propio nombre.

```python
def _legacy_engine_ok(reg, compat_path=COMPATIBILITY_FILE) -> (bool, str):
    status   = (reg.get("producer_engine_baseline_status") or "").upper()
    producer = reg.get("producer_engine_baseline")
    if producer and status != "UNKNOWN":
        return engine_is_compatible(producer, compat_path)      # productor real declarado
    anchor = reg.get("verified_compatible_from_baseline")
    if not anchor:
        return False, "el registro legado no declara productor conocido ni ancla de compatibilidad …"
    ok, why = engine_is_compatible(anchor, compat_path)
    if not ok:
        return False, f"el ancla de compatibilidad verificada '{anchor}' ya no vale: {why}"
    return True, ""
```

## La frontera, con la puerta de presentación cerrada

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  SOURCE FACTS                 case.json                                               │
│  validate_case_input()  ── rechaza ──▶  DERIVED_EVIDENCE / COMPUTED_RESULT / UNKNOWN  │
└───────────────────────────────┬──────────────────────────────────────────────────────┘
                                │  from_case_dir()
                                ▼
                          ┌───────────────┐
                          │  CaseContext  │  scale_confidence se deriva con la regla
                          └───────┬───────┘  del pipeline (shell_adapter), sin umbrales
                                  │          inventados
┌─────────────────────────────────┴──────────────────────────────────────────────────────┐
│  DERIVED GEOMETRY / EVIDENCE      outputs/floorplate.json                               │
│                                   scale.method · scale.meta.status · scale.px_per_m     │
└─────────────────────────────────┬──────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┴──────────────────────────────────────────────────────┐
│  COMPUTED RESULT       E04 metrics · E06 fit_robustness_report · E07 gates              │
│                                                                                         │
│  _freshness()  ──▶  floorplate_sha256 · program_sha256                                  │
│                     _legacy_engine_ok(): productor conocido, o ancla verificada          │
└─────────────────────────────────┬──────────────────────────────────────────────────────┘
                                  │  fit_evidence.load()
                                  ▼
                          ┌───────────────┐
                          │  FitEvidence  │  has_provenance: una afirmación exige artefactos
                          └───────┬───────┘
                                  │
                     build_board(alts, shell, EVIDENCE, ctx=ctx)
                                  │
                                  │  ← la copy se deriva AQUÍ DENTRO
                                  ▼
                     presentation_fit(ctx, evidence) -> PresentationFit
                                  ▼
                            Board / Summary
```

La diferencia con E15.2 es dónde se cruza la última flecha. Antes la copy se construía fuera y el
board comprobaba su tipo; un tipo lo puede fabricar cualquiera con los valores correctos. Ahora la
copy se construye dentro, desde evidencia que tiene que demostrar de dónde salió.

## Por qué esto no es seguridad

Python permite editar el código. Quien quiera mentir, miente. Lo que se busca es arquitectónico: que
el **camino normal** de presentación no permita que valores escritos a mano se conviertan
accidentalmente en un veredicto técnico vigente. La diferencia entre una mentira deliberada y un
error que nadie nota es toda la diferencia que un sistema de este tipo puede ofrecer.

## Confianza de escala: de dónde sale la clasificación

E15.2 introdujo `< 0.5 → LOW`, `< 0.8 → MEDIUM`, `HIGH` en otro caso. Esos umbrales no existían en
ninguna parte del motor. Un ciclo que declaraba no cambiar la lógica de escala no puede decidir
cuándo una medición pasa a ser `MEDIUM` o `HIGH`.

Lo que sí existía, desde antes de E15.2:

- `src/escalimetro/layout/shell_adapter.py:34` — la clasificación real del pipeline:
  `LOW` si `scale.method == "published_area_inferred"`, si no `HIGH` cuando `meta.status == "confirmed"`, si no `MEDIUM`
- `src/escalimetro/layout/e06/scale.py:38` — el vocabulario: `enum: ["LOW", "MEDIUM", "HIGH"]`

`_confidence_label` ahora reusa esa regla y no define ninguna. Para la 403 y la 401,
`method == "published_area_inferred"` ⇒ `LOW`, igual que antes: la lámina sigue byte-idéntica.
