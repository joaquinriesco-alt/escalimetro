# E26 — LISTO PARA LA PRIMERA REVISIÓN ARQUITECTÓNICA HUMANA

E26 no mejora el motor. Quita de en medio todo lo que le habría mentido a un arquitecto al mirar estas
plantas, y pone las plantas delante de él.

## 1. Lo que estaba mal

Tres cosas, todas encontradas leyendo el camino productivo:

1. **El gate técnico exigía `open_seats == "40/40"` como literal.** Cualquier brief con otro conteo
   fallaba el gate aunque hubiera entregado exactamente lo pedido. El brief nuevo de la 401 pide 18.
2. **La lámina leía la evidencia de otra corrida.** `fit_evidence.load` iba siempre a `layouts/E07/` y
   `layouts/E06/`, así que una lámina de `layouts/E25_EQUILIBRADO` mostraba el veredicto de una corrida
   con otro brief y otra versión del motor — y salía `REQUIERE RECÁLCULO`, que es lo que pasa cuando
   una huella no coincide.
3. **La lámina publicaba fortalezas escritas de antemano.** "Fachada liberada para puestos" aparecía en
   la alternativa A pasara lo que pasara con la fachada de esa planta.

## 2. Gate general (§3)

```python
def gate_e1t(result, program):
    pedidos = open_workstations(program)                       # del BriefV1 REALMENTE ejecutado
    entregados = int(str(m["program_completeness"]["open_seats"]).split("/")[0])
    checks = {..., f"puestos_solicitados ({pedidos})": entregados == pedidos, ...}
```

El test ejecuta la función real con 1, 7, 18, 24, 40, 56 y 103 puestos, y comprueba que falla cuando
faltan. No es un regex sobre el archivo.

## 3. Evidencia de la propia corrida (§4)

`fit_evidence.load(case_dir, program_path, run_dir=...)`:

* la capa técnica sale de `run_dir`, no de `layouts/E07`;
* la robustez de escala de E06 **sólo** se consume si su procedencia declara el mismo programa. Si no
  coincide, no se hereda: `robustness = NOT_EVALUATED` y se explica por qué;
* la corrida escribe `run_provenance.json` (case, brief, out_name, floorplate_sha256, program_sha256,
  brief_sha256, engine_hash, engine_commit, seed, generated_at) y su frescura se juzga contra eso.

Sin `run_provenance.json`, la evidencia es `STALE` y no se presenta ningún FIT. Hay test.

Resultado sobre la corrida de la 403:

```
frescura=FRESH · técnica=FIT · robustez=NOT_EVALUATED
fuentes: E26_403/gates.json · E26_403/alternatives/A/metrics.json · E26_403/run_provenance.json
etiqueta de lámina: 'FIT TÉCNICO'        (antes: 'REQUIERE RECÁLCULO')
```

## 4. Copy honesta (§5)

Se eligió la opción A, en su forma mínima: **cifras medidas de esta planta** en vez de adjetivos. Ni
texto fijo ni lenguaje generado.

| antes | ahora |
|---|---|
| `FORTALEZAS` · "Fachada liberada para puestos" | `MEDIDO EN ESTA PLANTA` · programa entregado, circulación m²/%, espacio sin asignar m²/%, área programada neta |
| `IDEAL PARA` · "Empresas que priorizan costo por puesto" | retirado |
| `copy_short` sin rótulo | `INTENCIÓN DE LA ESTRATEGIA` + `spec.intent`, que es cierto por construcción |

En el handoff esas frases pasan a `strategy_intent_claims`, con un `_contract` que dice que no están
verificadas contra la planta. La lámina histórica Standard 01 de la 403 se **re-renderizó** con el
renderer corregido sobre la MISMA geometría, y su expectativa de test se re-baselineó a propósito.

> Deuda declarada: `ai/board02.py` (Standard 02/03, camino E08/E09) sigue imprimiendo `strengths`.
> E26 no lo corre y §14 pide no gastar el ciclo limpiando. Queda anotado.

## 5. Identidad y calidad (§6/§7)

Cada layout FIT deja dos archivos:

* `traceability.json` — case_id, brief_id, strategy, **layout_sha256**, engine_commit, brief_sha256,
  generated_at (+ engine_hash, program/floorplate/modules sha, out_name, seed).
* `quality.json` — layout_sha256, engine_commit, brief_sha256 + unallocated_area_m2/pct,
  residual_spaces, daylight_score, fragmentation, facade_use, architectural_score, circulation_pct,
  waste_pct, y `delta_vs_previous` cuando existe una corrida comparable del mismo case/brief/strategy.

La revisión humana se asocia a `layout_sha256`, no a un nombre de archivo. `quality.json` lleva escrito
que **no es una evaluación arquitectónica**.

## 6. GPS 403 — sin regresión

| alt | status | puestos | programa | viol | colis | circ | sin asignar | residual | arq | layout_sha256 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | FIT | 40/40 | completo | 0 | 0 | sí | 26.80 % | 71.8 m² | 0.706 | `753ecca6570ec767…` |
| B | FIT | 40/40 | completo | 0 | 0 | sí | 27.39 % | 53.1 m² | 0.772 | `61cd28dd9ca27702…` |
| C | FIT | 40/40 | completo | 0 | 0 | sí | 26.95 % | 64.5 m² | 0.717 | `1e7d63c59df0d4d5…` |

Runtime 411 s en total; A tardó 163.7 s, así que el KPI de 120 s por alternativa **no se cumplió** en
esta corrida. Es la misma no reproducibilidad de tiempo de pared que E25 documentó.

## 7. GPS 401 — primer segundo shell real

`BRIEF_401_V1`, congelado y hasheado antes del primer solve
(`cases/E26/BRIEF_401_V1_FREEZE.json`, sha `3b5608e8ba2d7607…`):
18 puestos open, 2 privados, 1 sala de 8, 1 de 4, recepción, kitchenette, comedor, 2 phone booths.
24 personas declaradas, 21 puestos permanentes, 9 recintos. **Sin directorio de 12** — 36 m² de sala en
una planta de 250 m² no es un programa real, y su ausencia además prueba que el motor no depende de que
ese módulo exista.

Resultado: **A, B y C → `SEARCH_EXHAUSTED`.** El brief no se tocó.

Diagnóstico (`cases/E26/E26_DIAGNOSTICO_401.json`, ablación de E25 sobre el modelo relajado; no se
modificó nada del search, §2 lo prohíbe):

```
401/A  BASELINE y todas las ablaciones     OPTIMAL   máximo DEMOSTRADO 13 puestos de 18
401/B  BASELINE y todas las ablaciones     OPTIMAL   máximo DEMOSTRADO 13 puestos de 18
401/C  BASELINE                            INFEASIBLE
401/C  sin min_bench_blocks (C exige ≥ 8)  OPTIMAL   13 puestos
```

Dos lecturas:

* **En A y B ninguna política ata.** El techo de 13 puestos es del generador y del empaque de bloques,
  no de las reglas de diseño. Es **el mismo cuello que E25 midió en DENSO sobre la 403**, ahora en otro
  shell: no era una particularidad de la 403.
* **En C ata `min_bench_blocks = 8`**, una constante de DesignPolicyV1 calibrada sobre una planta de
  543 m². En 253 m² obliga a fragmentar el trabajo en 8 bloques.

El área nominal decía que cabía (149.4 m² + 20 % de circulación = 186.8 m² sobre 253.6 m² disponibles,
ratio 0.737). El empaque sobre candidatos muestreados dice 13. Ninguno de los dos es una demostración
de que no quepa: `SEARCH_EXHAUSTED` significa que no lo encontramos.

**Lo que E26 aprendió sobre la pregunta de §9:** el motor produce plantas válidas en la 403 y no
produce ninguna en la 401 con un brief proporcionado a su tamaño. La generalidad a otro shell **no está
demostrada**.

## 8. Lo que E26 NO hizo

* No tocó candidate generation, caps, ranking, CP-SAT, `module_max_path`, bench constraints,
  dimensiones de módulos, spine, circulación ni pesos de scoring. El baseline de motor lo declara con
  `search_surface_touched = []` y hay un test que lo comprueba.
* No intentó conseguir más FIT. No volvió a DENSO ni a EJECUTIVO.
* **No rellenó ninguna evaluación arquitectónica.** Ni grade, ni reason_tags, ni free_note, ni mejor
  alternativa. Las revisiones que escribió un agente en E24 no se copiaron.
* No implementó `ARCHITECTURAL_HYPOTHESIS_01`. Queda registrada como
  `UNVALIDATED_BY_HUMAN_REVIEW` en `docs/ARCHITECTURAL_HYPOTHESIS_01.md`.
* No limpió el repo ni agregó ledgers nuevos.

## 9. Cómo revisar

```bash
cd ~/escalimetro-repo
git checkout e26_human_review_readiness
PYTHONPATH=src python3 tools/e26_build_review.py     # sólo si quieres regenerar el índice
python3 tools/e26_review_server.py                   # abre http://127.0.0.1:8765/review/
```

Sin login, sin base de datos, sin usuarios; escucha sólo en `127.0.0.1`. Las revisiones se validan
contra `contracts/human_review_v1.schema.json` y se guardan en `cases/<case>/reviews/E26/`. Si prefieres
no levantar el servidor, abre `review/index.html` directo y usa **Descargar JSON**.

La hoja estática, si sólo quieres mirar: `cases/E26/E26_REVIEW_SHEET.png`.
