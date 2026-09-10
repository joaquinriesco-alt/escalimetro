# E25 §10 — EXPERIMENTOS DIAGNÓSTICOS, REGISTRADOS ANTES DE CORRERLOS

Escrito y hasheado ANTES de ejecutar ninguno. El diagnóstico PRE queda congelado en
`E25_DIAGNOSTICO_PRE_3x3.json` antes de esto.

## Qué pregunta responde cada uno

La pregunta de E25 es una sola: **¿DENSO y EJECUTIVO no caben, o el search no los encuentra?**
El diagnóstico PRE ya mostró la forma del problema: el warm start (`maximize Σ puestos ≤ N`, con el
programa completo de recintos colocado) termina en `FEASIBLE`, no en `OPTIMAL`, con menos puestos que
los que pide el brief. Un incumbente no es una cota. Los experimentos convierten ese incumbente en una
cota demostrada, o lo rompen.

## EXP-1 — COTA SUPERIOR DE PUESTOS SOBRE EL CONJUNTO DE CANDIDATOS ACTUAL

* Mismo conjunto de candidatos que E24 (step 1.0, poda con cap 200).
* `seats_mode = "max"`, `feasibility_only = False`.
* 1 worker, seed 1, **600 s** de límite.
* Se registra: status, mejor objetivo (= máximo de puestos alcanzado), mejor cota, gap.

Lectura:

* `OPTIMAL` y `max_seats < solicitados` → **el conjunto de candidatos actual no puede entregar el
  brief**. Como ese conjunto fue podado heurísticamente, esto es `SEARCH_EXHAUSTED`,
  NUNCA `PROVEN_INFEASIBLE`.
* `OPTIMAL` y `max_seats >= solicitados` → el conjunto sí da; el fallo de E24 fue de tiempo.
* `FEASIBLE` (no probó optimalidad) → sigue sin concluirse.

## EXP-2 — MISMO, CON EL CONJUNTO DE CANDIDATOS AMPLIADO

* `step = 0.8` (paso de posición más fino, el default de `generate_candidates`).
* **Sin poda**: `per_module_cap = 10**9` y sin colapso por dominancia.
* Resto idéntico a EXP-1.

Lectura:

* `max_seats` sube hasta cubrir el brief → **la poda/el paso eran el cuello**. Es un problema de
  generación de candidatos, corregible de forma general.
* `max_seats` NO sube → el techo no viene de la poda; viene de la geometría o de las restricciones
  duras del modelo V1.

## EXP-3 — FACTIBILIDAD EXACTA LARGA

Sólo para las combinaciones en que EXP-1 o EXP-2 muestren que los puestos SÍ son alcanzables.

* `seats_mode = "exact"`, `feasibility_only = True`, mejor conjunto de candidatos disponible.
* 1 worker, seed 1, **600 s**.

Lectura: `FEASIBLE`/`OPTIMAL` → existe un layout válido para ese brief; el fallo de E24 fue de search.

## LO QUE ESTOS EXPERIMENTOS NO PUEDEN CONCLUIR

Ninguno puede producir `PROVEN_INFEASIBLE` para el problema real. El conjunto de candidatos es siempre
una discretización (rectángulos anclados a elementos de circulación, en posiciones muestreadas). Aunque
EXP-2 quite la poda, sigue siendo un muestreo. Lo máximo que se puede afirmar con honestidad es:

> `SEARCH_EXHAUSTED` — con este generador y este modelo no encontramos solución.

## PROHIBIDO EN ESTOS EXPERIMENTOS

* Tocar puestos, privados, salas, dimensiones, zoning, restricciones duras, shell, núcleo, pilares,
  acceso o escala.
* Cambiar un brief.
* Probar parámetros hasta que aparezca un FIT (parameter fishing). Los tres experimentos están
  fijados aquí y se corren en este orden; lo que salga, sale.

---

# ADENDA — registrada tras congelar el diagnóstico PRE, antes de correr ningún experimento

El PRE mostró que DENSO y EJECUTIVO fallan por razones DISTINTAS, y eso obliga a agregar un cuarto
experimento antes de tocar código.

```
DENSO      warm (Σ puestos ≤ 56, programa completo)  FEASIBLE con 48 / 52 / 51 puestos
EJECUTIVO  warm (Σ puestos ≤ 24, programa completo)  INFEASIBLE en A y B; FEASIBLE con 19 en C
```

El warm es una RELAJACIÓN del problema exacto. Que sea INFEASIBLE en EJECUTIVO A/B significa que el
bloqueo no está en los puestos: está en colocar los 22 recintos. Que sea FEASIBLE en DENSO significa
que los recintos sí entran y lo que falta son puestos.

Contraejemplo que ya invalida la lectura ingenua del warm: **EQUILIBRADO/B tiene warm = 38 puestos y
la fase exacta encuentra 40 y termina OPTIMAL.** El incumbente del warm NO es una cota superior. Por
eso EXP-1 existe: convertir incumbentes en cotas demostradas.

## EXP-4 — ¿QUÉ RESTRICCIÓN BLOQUEA A EJECUTIVO? (ablación)

Sobre el modelo warm (el relajado) de EJECUTIVO A y B, quitando UNA restricción por vez y midiendo si
deja de ser INFEASIBLE:

1. `max_facade_closed_rooms` (A = 5, B = 4) — constante de DesignPolicyV1 calibrada sobre 16 recintos.
2. `module_max_path` (cota de ruta acceso→puerta del directorio).
3. `hard_adjacent_pairs` (kitchenette+dining).
4. `min_bench_blocks` / `max_bench_blocks`.
5. la cota dura de recepción a ≤ 8 m del acceso.

Es DIAGNÓSTICO puro: identifica la restricción que ata. **No autoriza por sí solo a relajarla.** Si la
que ata es una constante que no escala con el tamaño del programa, eso es un acoplamiento al brief
histórico y se corrige generalizando la constante — no bajando el estándar. Si la que ata es una regla
arquitectónica real, EJECUTIVO simplemente no cabe bajo esa regla y se reporta así.
