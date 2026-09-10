# E22 — EVALUATOR SENSITIVITY UNDER FROZEN QA EVIDENCE

**Veredicto: E22-D — ALTERNATIVE WORSE. Gate absoluto = FAIL. Vía QA semántica cerrada.**

## Qué se probó

E19.1, E20 y E21 midieron el mismo sesgo ARCH → FURN con tres contratos de salida distintos sobre
el mismo evaluador. E22 no prueba un cuarto contrato: cambia **el evaluador** y deja todo lo demás
byte a byte igual — mismo banco (SHA `2b3e2eb0…`), mismo prompt (SHA `ab58d99e…`), mismo manifest
(SHA `43de0430…`), mismas 144 assertions, mismo orden.

Evaluador alternativo: **`sonnet`** (autodeclarado Claude Sonnet 5). Uno solo, elegido por la regla
del §3 **antes** de mostrar una sola imagen del banco. PRIORIDAD 1 (otra familia/proveedor) resultó
no satisfacible: las cuatro configuraciones vision-capable del entorno son de la misma familia.
Se aplicó PRIORIDAD 2. `MODEL_IDENTITY_VERIFIABILITY = CONFIGURATION_LEVEL_ONLY`.

## Resultado

| métrica | sonnet | opus (E21) | Δ |
|---|---|---|---|
| ERROR_CATCH_RATE | 0.4444 | 0.5694 | −0.1250 |
| ERROR_CATCH_RATE falsa-ARCH | 0.8889 | 0.6944 | +0.1944 |
| **ERROR_CATCH_RATE falsa-FURN** | **0.0000** | 0.4444 | **−0.4444** |
| CORRECT_PASS_RATE | 0.6111 | 0.7639 | −0.1528 |
| CORRECT_PASS_RATE true-ARCH | 0.2222 | 0.5556 | −0.3333 |
| **CORRECT_PASS_RATE true-FURN** | **1.0000** | 0.9722 | +0.0278 |
| BALANCED_QA_ACCURACY | 0.5278 | 0.6667 | −0.1389 |
| IDEAL_PAIR_RATE | 0.4444 | 0.5417 | −0.0972 |
| PASS_ASYMMETRY | 0.7778 | 0.4166 | +0.3611 |
| CATCH_ASYMMETRY | 0.8889 | 0.2500 | +0.6389 |

Bootstrap (10.000 remuestreos, unidad = image target): `DELTA_BALANCED_QA` = −0.1389,
IC95 [−0.2361, −0.0417] — el intervalo entero por debajo de cero.
`DELTA_TRUE_ARCH_PASS` = −0.3333, IC95 [−0.5128, −0.1613].

Gate absoluto: 3 de 10 pasan. FAIL.

## El hallazgo

El sesgo no es del evaluador. Cambiarlo lo **amplifica**.

`sonnet` responde MUEBLE casi incondicionalmente:

- se afirma FURNITURE y es cierto → CONSISTENT **36/36**
- se afirma FURNITURE y es falso (el objeto es un recinto) → REVIEW **0/36**. Ni una vez.
- se afirma RECINTO y es cierto → CONSISTENT sólo **8/36**
- se afirma RECINTO y es falso → REVIEW **32/36**

Por receta, el catch sobre assertions falsas es **0/4 en las ocho recetas de recinto** y 3/4–8/8 en
las ocho de mueble. No es detección baja: es un prior fijo, más rígido que el de opus.

Acuerdo llamada a llamada entre los dos evaluadores: 101/144 = 0.7014. Difieren, pero difieren
**en la misma dirección**.

## Desviación de protocolo declarada

7 de las 144 llamadas (4.9 %) violaron la restricción de herramientas: usaron Bash para recortar y
ampliar **la misma imagen asignada**. La auditoría de los logs confirma que ninguna leyó otra imagen,
ni el ground truth, ni el baseline, ni el repositorio: **cero fuga de información**. No se descartó
ni se repitió ninguna; las 144 entran en la métrica pre-registrada.

Sensibilidad excluyendo las 7 imágenes afectadas (130 llamadas): `DELTA_BALANCED_QA` pasa de −0.1389
a −0.0692, que ya no alcanza el umbral de D. El hallazgo central no se mueve: falsa-FURN catch sigue
en 0.0000 y `PASS_ASYMMETRY` sube a 0.7931.

Es decir: la frontera D/C depende de esas 7 llamadas; **C se sostiene en los dos análisis**, y
ambos veredictos disparan la misma stop rule.

## Decisión

`SEMANTIC QA PATH CLOSED UNDER CURRENT VISUAL EVIDENCE.`

No hay cuarto evaluador. No hay cuarto contrato. No se abre GPS, no se abre RES, el tercer plano
sigue UNSEEN.

## Qué prueba y qué no

**Prueba:** bajo esta evidencia visual congelada, el sesgo ARCH → FURN sobrevive al cambio de
configuración de evaluador, y la configuración más fuerte disponible distinta de `opus` lo empeora.

**No prueba:** independencia de proveedor (PRIORIDAD 2, no 1). Nada sobre planos reales. Nada sobre
detección de muros. Nada sobre producción.
