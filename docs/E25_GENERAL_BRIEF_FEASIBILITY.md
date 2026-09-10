# E25 — VIABILIDAD GENERAL DE BRIEFS + DIAGNÓSTICO DE BÚSQUEDA

**La pregunta:** ¿DENSO y EJECUTIVO no caben en GPS 403, o el motor no los encuentra?

**La respuesta corta:** no lo sabemos, y ahora el motor lo dice así en vez de decir "no cabe".
Lo que sí sabemos es más específico y más útil: **DENSO y EJECUTIVO fallan por razones distintas**, y
ninguna de las dos es una demostración de infactibilidad.

## 1. El error que E25 corrige

E24 reportó `NO_FIT (INFEASIBLE)`. CP-SAT devuelve `INFEASIBLE` cuando prueba que no hay solución
**en el modelo que recibió**. Ese modelo se construye sobre un conjunto de candidatos que el generador
muestrea y luego poda. Probar infactibilidad sobre un subconjunto no prueba nada sobre el problema.

Cinco estados, con una regla de producto que no se negocia:

| estado | significa | ¿autoriza decir "no cabe"? |
|---|---|---|
| `FIT` | existe layout que cumple todas las restricciones duras | — |
| `PROVEN_INFEASIBLE` | no existe solución en el espacio COMPLETO del modelo V1 | **sí** |
| `SEARCH_EXHAUSTED` | el solver probó infactibilidad dentro de un espacio INCOMPLETO | **no** |
| `TIMEOUT_NO_SOLUTION` | se agotó el presupuesto sin solución | **no** |
| `TIMEOUT_WITH_INCUMBENT` | hay solución válida; no se terminó de optimizar | — |

`src/escalimetro/layout/search_status.py`. La regla está impuesta **por construcción**: el clasificador
recibe un `CandidateSpace` y sólo devuelve `PROVEN_INFEASIBLE` si `space.complete` es `True`. En V1 ese
descriptor se construye con `sampled_positions=True, dominance_pruned=True, capped=True`, así que
**el motor V1 no puede emitir `PROVEN_INFEASIBLE` ni por accidente**. Hay test.

## 2. Señal de capacidad, sin CP-SAT (§6)

| brief | puestos | privados | recintos | neta m² | + circ | total | / 539.2 | señal |
|---|---|---|---|---|---|---|---|---|
| DENSO | 56 | 2 | 14 | 314.1 | 78.5 | 392.6 | **0.728** | CLEARLY_PLAUSIBLE |
| EQUILIBRADO | 40 | 4 | 16 | 305.9 | 76.5 | 382.4 | **0.709** | CLEARLY_PLAUSIBLE |
| EJECUTIVO | 24 | 8 | 22 | 343.5 | 85.9 | 429.4 | **0.796** | CLEARLY_PLAUSIBLE |

**DENSO carga 8 m² más que EQUILIBRADO** (+2.6 %), y EQUILIBRADO resuelve en las tres estrategias.
Una suma de áreas no demuestra factibilidad geométrica, pero sí descarta la explicación fácil: no es
que el programa "no quepa por área".

## 3. Diagnóstico PRE: dos fallos distintos, no uno (§5)

Con el pipeline de E24 intacto, instrumentado:

```
                 candidatos      warm (Σ puestos ≤ N, programa completo)     exacta
DENSO/A       2762 → 1556        FEASIBLE  48 puestos de 56                 INFEASIBLE
DENSO/B       2696 → 1556        FEASIBLE  52 puestos de 56                 UNKNOWN
DENSO/C       2466 → 1480        FEASIBLE  51 puestos de 56                 UNKNOWN
EQUILIBRADO/A 2762 → 1556        FEASIBLE  40 puestos de 40                 OPTIMAL
EQUILIBRADO/B 2696 → 1556        FEASIBLE  38 puestos de 40                 OPTIMAL   ←
EQUILIBRADO/C 2466 → 1480        FEASIBLE  40 puestos de 40                 OPTIMAL
EJECUTIVO/A   2762 → 1556        INFEASIBLE                                 INFEASIBLE
EJECUTIVO/B   2696 → 1556        INFEASIBLE                                 INFEASIBLE
EJECUTIVO/C   2466 → 1480        FEASIBLE  19 puestos de 24                 UNKNOWN
```

Dos lecturas que cambian todo:

1. **EQUILIBRADO/B tiene warm = 38 y la fase exacta encuentra 40 y termina OPTIMAL.** El incumbente
   del warm NO es una cota superior. Cualquier razonamiento del tipo "el warm llegó a 48, entonces 56
   es imposible" es inválido.
2. **En EJECUTIVO A y B el warm —que es una RELAJACIÓN— ya es INFEASIBLE.** El bloqueo no está en los
   puestos: está en colocar los 22 recintos.

## 4. Auditoría del generador (§7)

Preguntas del prompt, respondidas con números.

**A. ¿Llega al solver el espacio completo?** No. Los candidatos son rectángulos anclados a elementos
de circulación, en posiciones muestreadas cada `step` metros, luego colapsados por dominancia y
topados por módulo. De 24 892 rectángulos intentados sobreviven 2 762 (11 %).

**B. ¿Qué subconjunto llega?** Causas de descarte medidas (DENSO/A): choca elemento fijo 32.3 %,
fuera del bbox 26.5 %, fuera del usable 23.1 %, duplicado 4.8 %, choca pilar 1.7 %, invade la zona de
acceso 0.3 %, no toca circulación 0.04 %.

**C. ¿El tope elimina candidatos necesarios?** Sí, y de forma sesgada por brief sin nombrar ningún
brief: el tope era **plano por tipo de módulo**. EJECUTIVO pide 8 oficinas privadas y recibía el mismo
pool de 200 que EQUILIBRADO con 4 — 25 candidatos por instancia contra 50.

**D. ¿El ranking favorece al brief histórico?** El resampleo tras el tope ordena por `(path_m,
daylight_m)` y toma uno de cada k. No favorece un brief, pero sesga hacia una distribución uniforme en
el orden de RUTA, no en el espacio.

**E. ¿Los benches representan totales arbitrarios?** Sí aritméticamente (A ofrece bloques de
{2,3,4,5,6,8,10,12} asientos), pero **la poda los destruía**: la clave de dominancia era
`(celda 1.2 m, rotación, primer elemento tocado)` — **sin el tamaño**. Un bench 2×6 y uno 2×2 anclados
en el mismo punto colapsaban a uno. `workstation_cluster` pasaba de 251 candidatos a **98**.

**F. ¿Hay módulos con conjunto vacío?** Ninguno vacío, pero uno casi: **`boardroom_12` tenía 15
posiciones en toda la planta** (7.2 × 5.0 m es el rectángulo más grande del programa), y el filtro de
ruta de la estrategia A dejaba 12.

**G. ¿Hay soluciones que nunca llegan a CP-SAT?** Sí, necesariamente: el espacio es muestreado. Por eso
`PROVEN_INFEASIBLE` está prohibido en V1.

## 5. Tres defectos generales, tres correcciones generales (§11)

Ninguna menciona un brief, un número de puestos ni un identificador.

**D1 — la clave de dominancia ignoraba el TAMAÑO del candidato.**
Corrección: la huella `(w, d)` entra en la clave.
Efecto medido: `workstation_cluster` 98 → **211** candidatos (+115 %).

**D2 — el tope era plano por tipo de módulo, ciego a la demanda del programa.**
Corrección: `cap_efectivo = max(cap_base, 80 × nº de instancias)`. La demanda sale del programa
compilado, no de ningún brief.
Efecto medido: `private_office` en EJECUTIVO, tope 200 → **640**.

**D3 — el paso de muestreo era constante, así que un módulo grande obtenía 15 posiciones y uno pequeño
700.** Corrección: piso de cobertura por instancia (`MIN_CANDIDATOS_POR_INSTANCIA = 40`); el módulo que
queda por debajo se regenera con el paso a la mitad, hasta 2 rondas o paso 0.2 m.
Efecto medido: `boardroom_12` 15 → **56** candidatos brutos; `private_office` en EJECUTIVO 255 → **507**.

## 6. Qué demostraron los experimentos (§10)

Registrados en `cases/E25/E25_EXPERIMENTOS_REGISTRADOS.md` **antes** de correrse.

### EXP-1 — cota demostrada de puestos (`maximize Σ puestos`, 1 worker, seed fija)

| combo | pide | generador E24 | generador E25 | cota superior |
|---|---|---|---|---|
| DENSO/A | 56 | **OPTIMAL 48** | **OPTIMAL 51** | 51.2 |
| DENSO/B | 56 | FEASIBLE 53 | FEASIBLE 52 | 56.2 |
| DENSO/C | 56 | FEASIBLE 53 | FEASIBLE **55** | 56.3 |
| EJECUTIVO/A | 24 | INFEASIBLE | INFEASIBLE | — |
| EJECUTIVO/B | 24 | INFEASIBLE | INFEASIBLE | — |
| EJECUTIVO/C | 24 | FEASIBLE 19 | FEASIBLE 20 | 24.4 |

Lectura honesta:

* **DENSO/A**: el máximo demostrado sobre el conjunto de candidatos subió de 48 a 51. Sigue por debajo
  de 56, y sigue siendo una cota **sobre un conjunto incompleto** → `SEARCH_EXHAUSTED`.
* **DENSO/B y /C**: la cota superior del solver no excluye 56 (56.2 y 56.3). C llegó a 55, a un puesto.
  No concluido.
* **EJECUTIVO/A y /B**: infactible incluso en el modelo relajado, con el conjunto ampliado.

### EXP-4 — ablación: ¿qué ata a EJECUTIVO?

Sobre el modelo warm, quitando una restricción por vez (60 s, determinista):

```
EJECUTIVO/A  BASELINE                       INFEASIBLE
EJECUTIVO/A  sin max_facade_closed_rooms    INFEASIBLE
EJECUTIVO/A  sin module_max_path            UNKNOWN     ← deja de estar demostrado infactible
EJECUTIVO/A  sin hard_adjacent_pairs        INFEASIBLE
EJECUTIVO/A  sin bench_blocks               INFEASIBLE
EJECUTIVO/A  sólo geometría                 UNKNOWN
EJECUTIVO/B  BASELINE                       INFEASIBLE
EJECUTIVO/B  (cada una por separado)        INFEASIBLE
EJECUTIVO/B  sólo geometría                 UNKNOWN     ← sólo cede el conjunto completo
```

**La restricción que ata a EJECUTIVO/A es `module_max_path` — el directorio a ≤ 16 m de ruta del
acceso.** En B ninguna cede sola: es la combinación de políticas.

Y aquí E25 se detiene a propósito. `module_max_path` **no** es una constante acoplada al brief
histórico: es una regla de recorrido de cliente, arquitectura real. Relajarla para que EJECUTIVO
"quepa" sería exactamente lo que §12 prohíbe. Lo que corresponde es reportar que **el perfil ejecutivo
de 22 recintos es incompatible con las políticas A y B sobre esta planta**, y dejar que E26 decida si
cede la política o cede el brief. E25 no lo decide.

## 7. Reproducibilidad (§9)

E24 observó: mismo input, misma seed, distinta geometría y distinto runtime. Causa exacta, en
`freeplace.solve_free`:

1. `num_search_workers = 2` — CP-SAT corre búsquedas en paralelo y devuelve la que gane la carrera.
2. `max_time_in_seconds` — el corte es por tiempo de **pared**, así que depende de la carga de la
   máquina. Se vio dentro de una misma corrida de E24: la fase de factibilidad de la alternativa A
   tardó 18.2 s una vez y 93.3 s otra.
3. El corte anticipado `early_stop_after_s` también mide tiempo de pared.

**`DETERMINISTIC_DEV_MODE`**: `ESCALIMETRO_DETERMINISTIC=1` o el parámetro `deterministic=True`.
Activa 1 worker, `max_deterministic_time` en vez de tiempo de pared, `randomize_search = False`, seed
fija, y **apaga el corte anticipado por tiempo de pared**. Es modo de DESARROLLO: no se activa solo.

## 8. Lo que E25 NO hizo

* No relajó tamaños mínimos, circulación, colisiones, núcleo, pilares, usable, restricciones duras,
  programa, cantidades ni shell.
* No introdujo ninguna rama por brief. Hay dos tests que lo verifican leyendo el código y el AST.
* No corrigió calidad arquitectónica: sigue siendo **B — CORREGIBLE** y es E26.
* No abrió el tercer plano.
