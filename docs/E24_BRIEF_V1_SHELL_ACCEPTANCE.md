# E24 — BRIEF V1 + SHELL ACCEPTANCE + PRUEBA VISUAL 3×3

**Qué se movió:** el programa del cliente salió del código. **Qué apareció:** el motor sólo resuelve
el brief para el que fue afinado.

## 1. El resultado que importa

Nueve intentos sobre el MISMO shell (GPS 403, 539.2 m² útiles), el MISMO motor y la MISMA política de
diseño. Lo único que cambia por fila es el brief del cliente.

|            | A EFICIENTE | B BALANCEADO | C COLABORATIVO |
|------------|-------------|--------------|----------------|
| **DENSO** (56 puestos, 2 privados)      | NO_FIT (INFEASIBLE) | SIN RESULTADO (UNKNOWN) | SIN RESULTADO (UNKNOWN) |
| **EQUILIBRADO** (40 puestos, 4 privados)| **FIT 40/40**       | **FIT 40/40**           | **FIT 40/40**           |
| **EJECUTIVO** (24 puestos, 8 privados)  | NO_FIT (INFEASIBLE) | NO_FIT (INFEASIBLE)     | SIN RESULTADO (UNKNOWN) |

Reproducido en dos corridas independientes con el mismo resultado por celda.

Los tres estados NO son el mismo estado y la lámina los distingue:

* **FIT** — hay layout válido: programa completo, 0 violaciones duras, 0 colisiones, circulación conectada.
* **NO_FIT (INFEASIBLE)** — CP-SAT **prueba** que no hay asignación válida **sobre el conjunto de
  candidatos podado** (cap 200 por módulo, `bench_cfgs` de la alternativa). No prueba que el programa
  no quepa en el shell: prueba que este generador de candidatos no ofrece una combinación que lo resuelva.
* **SIN RESULTADO (UNKNOWN)** — el solver no concluyó dentro del presupuesto de tiempo del producto
  (feas 25 s con reintento, opt 34 s). No dice nada sobre factibilidad, ni a favor ni en contra.

**E24 no determinó si DENSO y EJECUTIVO caben en la 403.** Determinó que el motor, tal como está, no
puede responderlo dentro de su propio presupuesto de tiempo. Esa es la pregunta que hereda E25.

No se redujo el programa, no se cambiaron dimensiones, no se relajaron restricciones y no se tocó
ningún brief después de verlo fallar (§9). Los tres briefs se congelaron y hashearon antes del primer
layout.

## 2. El brief histórico no se rompió

`BRIEF_EQUILIBRADO` es el equivalente semántico de `office_balanced_48.json` — no una copia byte a
byte, sino el mismo contenido: mismo `program`, mismo `open_workstations_exact` (40), mismo
`target_headcount` (48), mismos `objectives_weights`, mismas particiones de barrio.

|                       | E23 / E07 | E24 / EQUILIBRADO |
|-----------------------|-----------|-------------------|
| puestos open A/B/C    | 40/40     | 40/40             |
| programa completo     | sí (3/3)  | sí (3/3)          |
| violaciones · colisiones | 0 · 0  | 0 · 0             |
| circulación conectada | sí        | sí                |
| útil m²               | 539.2     | 539.2             |
| programa neto m²      | 305.9     | 305.9             |

La **geometría** sí cambió (A vs B pasó de 50.0 % a 74.1 % de diferencia). No es un efecto de E24: las
entradas del solver son idénticas y la semilla es un entero fijo. CP-SAT corre con límite de tiempo de
**pared**, así que el resultado depende de la carga de la máquina. Se ve en la misma corrida: la fase
de factibilidad de A tardó 18.2 s una vez y 93.3 s otra, y el KPI de 120 s por alternativa se cumplió
en una corrida y no en la otra. **El motor no es reproducible corrida a corrida.** Es un hecho previo
a E24 que E24 dejó a la vista.

## 3. Qué salió del motor (§6)

Auditoría completa de la semántica previa en `docs/E24_PROGRAM_SEMANTICS_AUDIT.md`. Lo removido:

| dónde estaba | qué era |
|---|---|
| 8 puntos del runtime | `open_workstations_exact` con **40 por defecto** → ahora `program_access.open_workstations()` levanta `ProgramContractError` si el programa no lo declara |
| `e05/strategy.py:133` | `seats_total = 40` → parámetro `open_workstations` de `generate_strategies` |
| `e07/strategies.py` ×3 | tablas de barrios `[24,16]` / `[16,14,10]` / `[12,10,10,8]` → proporciones + reparto por mayor resto |
| `e07/pipeline.py:207` | `{"target_headcount": 48, "open_workstations": 40}` en el handoff → bloque derivado con **pedido vs entregado** |
| `e07/board.py:25`, `validation/boards.py:34,39`, `ai/board02.py:133,174` | `("Puestos open space","40")`, `("Puestos open","40 / 40")`, `("16","recintos")` → `brief.program_rows()` |
| `e06/run.py:115,307`, `e06/sweep.py:136`, `e06/verdict.py:65` | `max_seats = 40`, `"OFFICE_BALANCED_48", 48`, `"40 puestos"`, `"48 personas"` |
| `deterministic_provider.py:116` | `"Mismo programa para 48 personas"` |
| `e06/run.py:238` | `axhline(40, "brief: 40 puestos")` en el gráfico de robustez |

**Lo que NO se borró, a propósito** (§6 prohíbe eliminar por reflejo): la taxonomía de módulos y sus
etiquetas (`render.LABELS`, `COMMERCIAL_FILL`), la zonificación arquitectónica
(`zoning.ZONE_OF_MODULE`), la biblioteca de módulos con sus dimensiones, las holguras, y la
configuración interna de cada estrategia. Nada de eso es el brief de un cliente.

## 4. La separación que exige §3

```
BriefV1            QUÉ PIDE EL CLIENTE
                   brief_id · target_headcount · open_workstations · rooms[{module, count}]

DesignPolicyV1     CÓMO ESCALÍMETRO LO DISEÑA — interno, no expuesto
                   pesos del objetivo · zonificación · adyacencias · proporciones de barrio ·
                   estrategias A/B/C · anchos de pasillo · posiciones
```

`BriefV1.from_dict` **rechaza** cualquier campo fuera de los cuatro: si alguien intenta declarar
`objectives_weights` en el brief, es `BriefError`. El brief tampoco puede declarar
`workstation_cluster`: los clusters se derivan (`ceil(open_workstations / 6)`; con 40 da 7, igual que
la plantilla histórica).

`zoning_rules` estaba duplicado en las plantillas de programa y **nunca se leía**: el runtime usaba
`ZONE_OF_MODULE`. Ahora `DesignPolicyV1.zoning_rules()` lo **deriva** de esa única fuente, y el brief
ya no lo lleva.

## 5. La semántica que §4 pedía auditar antes de escribir nada

```
OPEN_WORKSTATIONS   puestos fijos de open space, EXACTOS. Única cantidad que es restricción dura.
PERMANENT_SEATS     open_workstations + Σ count·occupancy sobre {private_office, reception}
MEETING_SEATS       Σ count·occupancy sobre {meeting_4, meeting_8, boardroom_12}   ← jamás headcount
TARGET_HEADCOUNT    declarado. Dimensiona soporte y relato. NO es restricción del solver.
UNSEATED_HEADCOUNT  target_headcount − PERMANENT_SEATS. Se REPORTA; no se rellena con puestos extra.
```

Con el brief histórico: 40 puestos + 4 privados + 1 recepción = **45 permanentes**, 48 declarados,
**3 sin puesto**, y **32 asientos de reunión** que no son headcount. `target_headcount` se consume hoy
en exactamente dos lugares, ambos de presentación (`fit_evidence.py:314`, `validation/boards.py:193`):
cambiarlo no mueve una sola coordenada, y hay un test que lo prueba.

La trampa que §4 advertía es real: `sum(p.seats for p in placements)` da **104** en el brief histórico
porque cada recinto colocado recibe `seats = occupancy`. BriefV1 nunca deriva puestos de esa suma.

## 6. Aceptación de shell — implementada, no sólo especificada (§11-§15)

| caso | veredicto | HITL pendiente |
|---|---|---|
| GPS 403 | `SHELL_ACCEPTED` | escala, elementos fijos |
| GPS 401 | `SHELL_ACCEPTED` | escala, elementos fijos |
| RES     | `INPUT_NOT_READY` | perímetro, escala, acceso, elementos fijos |

Precedencia declarada en el módulo antes de correr ningún caso:
`INVALID_INPUT > INPUT_NOT_READY > SCALE_UNRESOLVED > SHELL_ACCEPTED`. Un check en `NEEDS_HITL`
**nunca bloquea**: agrega una pregunta. Un test-fit con la escala por confirmar es exactamente el
producto V1; uno sin perímetro, no.

> Honestidad sobre esta coincidencia: §15 pre-declaró estos tres veredictos y yo implementé los checks
> después de leerlo. Que coincidan es **consistencia**, no confirmación independiente.

**RES no está listo por dos razones independientes**, y las dos quedan registradas:
`shell_declared_clean = false` (FAIL) y `px_per_m = null` con `SCALE_INCOMPATIBLE_REGION` (FAIL).
Gana `INPUT_NOT_READY` por precedencia.

### `not_layout_dominated` (§12)

Fuente **única**: el hecho de intake `shell_declared_clean`, campo nuevo de `case.json`.

```
true      → PASS
unknown   → NEEDS_HITL   (una confirmación simple: "¿esta planta viene libre?")
false     → FAIL → INPUT_NOT_READY
```

Prohibido inferirlo del dibujo. La prohibición se comprueba leyendo el **árbol de imports** de
`src/escalimetro/shell_input/`: no importa IA, VLM, SemanticHint, `area_semantics` ni `cv2`. Un test
pasa el mismo caso con los tres valores y verifica que el veredicto cambia sólo por eso.

Para RES, `false` no lo inventé: el propio `case.json` ya lo decía en prosa desde E16.4 (*"no se
limpió el mobiliario"*, *"El plano muestra 4 oficinas privadas y 8 baños"*). E24 estructura un hecho
que ya estaba escrito. Para 403 y 401 nadie lo declaró nunca: `unknown` es la respuesta honesta.

### Escala (§14)

Vía primaria: el usuario marca **punto A**, **punto B** y declara **cuántos metros** hay entre ellos.

```
px_per_m = |AB| en píxeles / distancia_real_m        provenance = USER_CONFIRMED_DISTANCE
```

Los datos crudos se guardan para poder recomputar el número; un test lo recomputa. Vía secundaria:
px/m escrito a mano (`USER_DECLARED_PX_PER_M`), que se acepta pero se marca como no reproducible. No
se construyó lector de cotas ni de barra de escala.

**Ningún caso real declara todavía una escala confirmada**, y hay un test que lo verifica. E24
implementó el mecanismo; no inventó una medición que nadie tomó. Por eso GPS 403 sigue con la escala
en `NEEDS_HITL`.

## 7. Calidad arquitectónica: se CALIFICA, no se corrige (§19)

Las tres alternativas del brief base, calificadas contra `contracts/human_review_v1.schema.json`:

| alt | grado | reason_tags |
|---|---|---|
| A | `B_CORRECTABLE` | sin_espesor_de_tabique, sin_pasillo_legible, espacio_desperdiciado, conflicto_nucleo, mala_adyacencia |
| B | `B_CORRECTABLE` | + mala_proporcion |
| C | `B_CORRECTABLE` | + privados_mal_ubicados |

Lo que se repite en las tres:

1. **Sin espesor de tabique.** Los recintos son rectángulos de línea única. No hay muro.
2. **Sin pasillo legible.** La circulación es el hueco que sobra entre objetos, no un espacio dibujado.
3. **Franja bajo el núcleo ocupada.** La única conexión entre el ala izquierda y el ala del acceso pasa
   por debajo del núcleo, y en las tres esa franja lleva una fila de puestos.
4. **Recepción / comedor / kitchenette contiguos** junto al acceso: la cocina termina pegada a la
   recepción, que es la adyacencia que la propia estrategia declara evitar.
5. **Vacíos grandes** sin uso asignado (49–78 m² de desperdicio medido).

Ninguna se enviaría a un cliente sin corregirla. Ninguna es `C_BAD`: el programa está completo, no hay
colisiones y la circulación conecta. **B — CORREGIBLE** es el estado real, y corregirlo es E25.

## 8. Falsa protección corregida (§21, quirúrgico)

Los hashes de geometría A/B/C se comparaban entre **dos JSON congelados**
(`EXPECTED_GEOMETRY_HASHES.json` contra `geometry_hash_check.json`): habrían seguido verdes aunque el
solver cambiara. Se agregó **un** test que recalcula `geometry_hash(layout, shell)` desde
`layout.json` y el shell del caso, y lo compara con el esperado. Los tres coinciden. Es una sola
función y un solo test: no expandió E24.

## 9. Deuda que E24 deja anotada, no resuelta

1. **El motor sólo sabe hacer 40 puestos.** Seis de nueve celdas sin layout. Tres de ellas ni siquiera
   son una prueba de infactibilidad, sino un timeout. La sospecha concreta: el generador de candidatos
   (poda a 200 por módulo, `bench_cfgs` fijos por alternativa) es el cuello de botella, no el shell.
   Verificable subiendo el cap y midiendo — E24 no lo hizo para no perseguir un FIT.
2. **CP-SAT no es reproducible** entre corridas: mismo input, distinta geometría y distinto runtime.
   Cualquier baseline geométrico que se congele hoy es frágil por construcción.
3. **La banda de programa de la Standard 02 cuenta el directorio dos veces** (`5 salas` +
   `1 directorio de 12`, sobre 3+1+1 recintos de reunión). E24 **reprodujo** la agrupación histórica en
   vez de corregirla: cambiar lo que dice una lámina no era la variable de este ciclo. Queda anotado.
4. **La calidad arquitectónica sigue en B.** Es E25.
