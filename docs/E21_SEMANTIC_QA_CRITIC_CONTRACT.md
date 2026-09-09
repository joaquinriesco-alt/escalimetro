# E21 — SEMANTIC QA CRITIC CONTRACT

**Veredicto: E21-D — ASYMMETRIC QA. E21-A = FAIL. No se autoriza E22.**

## Qué se probó

E19 mostró que el contexto lleva información semántica. E19.1 mostró que la señal replica pero
la calibración no. E20 cerró la vía de generación de candidatos: el contrato set-valued arregla la
seguridad (cobertura 0.986) y no la utilidad (BOTH_RATE 0.750).

E21 cierra una vía distinta. No se le pregunta al evaluador *qué es este objeto*, sino:
**el sistema determinista afirma que este objeto es X — ¿esa afirmación es visualmente
consistente, o debería revisarla un humano?**

Una sola variable respecto de E20: la pregunta. Mismo banco (SHA `2b3e2eb0…`), mismas 72 imágenes,
mismos SHA, motor byte a byte idéntico desde E16.16.

## Diseño

144 evaluaciones contrafactuales: por cada imagen, dos llamadas independientes sobre **el mismo
archivo** (mismo SHA), variando únicamente `{ASSERTED_ROLE}`.

- 72 assertions TRUE (se afirma el rol verdadero) — 36 ARCH, 36 FURN
- 72 assertions FALSE (se afirma el rol invertido) — 36 falsas-ARCH, 36 falsas-FURN

Un evaluador nuevo por llamada, sin memoria, sin ground truth, sin las otras llamadas. Orden desde
semilla 2101, declarado antes de la primera inferencia. Ninguna ola contiene los dos brazos de la
misma imagen; el agrupamiento es un barrido greedy determinista sobre ese orden, reproducible.

## Resultados

| métrica | valor | gate | |
|---|---|---|---|
| ERROR_CATCH_RATE overall | 0.5694 | ≥ 0.80 | FAIL |
| ERROR_CATCH_RATE falsa-ARCH | 0.6944 | ≥ 0.70 | FAIL |
| ERROR_CATCH_RATE falsa-FURN | 0.4444 | ≥ 0.70 | FAIL |
| CORRECT_PASS_RATE overall | 0.7639 | ≥ 0.75 | PASS |
| CORRECT_PASS_RATE true-ARCH | 0.5556 | ≥ 0.65 | FAIL |
| CORRECT_PASS_RATE true-FURN | 0.9722 | ≥ 0.65 | PASS |
| FALSE_ASSERTION_CONSISTENT_RATE | 0.4167 | ≤ 0.15 | FAIL |
| TRUE_ASSERTION_REVIEW_RATE | 0.2222 | ≤ 0.25 | PASS |
| INSUFFICIENT overall | 0.0139 | ≤ 0.15 | PASS |
| BALANCED_QA_ACCURACY | 0.6667 | ≥ 0.775 | FAIL |

Bootstrap (10.000 remuestreos, unidad = image target, los dos brazos juntos):

- ERROR_CATCH_RATE 0.5694, IC95 [0.4583, 0.6806]
- CORRECT_PASS_RATE 0.7639, IC95 [0.6667, 0.8611]
- BALANCED_QA_ACCURACY 0.6667, IC95 [0.5694, 0.7569]

El IC95 de la accuracy balanceada no toca el umbral 0.775 por arriba. No es un fallo por margen.

## El hallazgo

El critic no falla por falta de capacidad. Falla porque su juicio depende de **cuál rol se afirma**,
no de si la afirmación es correcta:

- Se afirma FURNITURE y es cierto → CONSISTENT en 35/36.
- Se afirma FURNITURE y es falso (el objeto es un recinto) → CONSISTENT en 20/36. **Pasa.**
- Se afirma ARCH y es cierto → CONSISTENT sólo en 20/36. **Duda de lo correcto.**
- Se afirma ARCH y es falso → REVIEW en 25/36.

Es el mismo sesgo direccional que E19.1 midió (ARCH→FURN en 16 de 23 respuestas cambiadas) y que
E20 midió (16 de 18 singletons fueron FURNITURE). Tercer ciclo consecutivo, tercer contrato de
salida distinto, mismo sesgo. **El sesgo no está en el contrato de salida. Está en el evaluador.**

Consecuencia operativa: el modo de falla peligroso —un recinto interpretado como mueble— es
justamente el que el critic deja pasar más de la mitad de las veces.

## Carga de revisión

P(REVIEW | correcta) = 0.2222, P(REVIEW | incorrecta) = 0.5694.

| tasa de error del determinista | tasa de revisión esperada | precisión de la revisión |
|---|---|---|
| 1 % | 0.2257 | 0.0252 |
| 5 % | 0.2396 | 0.1188 |
| 10 % | 0.2569 | 0.2216 |
| 20 % | 0.2917 | 0.3905 |
| 50 % | 0.3958 | 0.7193 |

Con un determinista al 10 % de error, el critic manda a revisión 1 de cada 4 objetos y 78 de cada
100 revisiones no encuentran nada. Un revisor humano deja de mirar mucho antes de eso.

## Pares (n = 72 imágenes)

IDEAL_PAIR_RATE = 0.5417 (39/72): TRUE→CONSISTENT y FALSE→REVIEW.

|  T \\ F | CONSISTENT | REVIEW | INSUFFICIENT |
|---|---|---|---|
| **CONSISTENT** | 15 | 39 | 1 |
| **REVIEW** | 14 | 2 | 0 |
| **INSUFFICIENT** | 1 | 0 | 0 |

15 imágenes reciben CONSISTENT en los dos brazos: el critic acepta las dos lecturas de la misma
imagen. 14 reciben REVIEW en el brazo verdadero y CONSISTENT en el falso: el juicio invertido.

## Límites declarados

- `PROVIDER_IDENTITY = UNKNOWN`, `PRODUCTION_REPRODUCIBILITY = NOT_PROVEN`.
- Banco sintético. Nada de esto dice nada sobre planos reales ni sobre detección de muros.
- Una llamada (`CRMQAT_T`) falló técnicamente dos veces —el subagente reportó no encontrar el
  archivo, que existe y cuyo SHA coincide con el manifest. Se registró como INSUFFICIENT_EVIDENCE
  con `TECHNICAL_RETRY = TRUE`, según el §48-49 del pre-registro. Esa abstención no es evaluativa.
  Es 1 de 144; ningún gate cambia de estado si se la excluye.
- El pre-registro fijó los ocho umbrales de E21-A de forma completa, pero registró los veredictos
  no-A (B a F) sólo por su etiqueta, sin definición numérica. La elección de D sobre C es
  descriptiva y no cambia la stop rule: cualquier veredicto distinto de A detiene igual.

## Decisión

La stop rule del pre-registro es explícita: sólo E21-A autoriza E22. **STOP total.**
Sin GPS, sin RES, sin E21.1, sin rediseño del prompt, sin tocar runtime, sin abrir el tercer plano.

## Qué queda cerrado

Tres ciclos han probado tres contratos de salida distintos sobre el mismo evaluador y el mismo
banco: clasificación directa (E19/E19.1), propuesta set-valued (E20) y crítica de QA (E21).
Los tres miden el mismo sesgo direccional. La conclusión razonable no es probar un cuarto contrato
de salida sobre el mismo evaluador — es que el eje de la variable estaba mal elegido.
