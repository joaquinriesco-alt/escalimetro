# E16.11 — Completitud del núcleo: plausible ≠ completo

## 1. El falso positivo que se cierra

El contrato de E16.10 mide siete propiedades —coherencia con la pista, estructura permanente, tamaño,
compacidad, conectividad, invasión de piso ocupable— y todas responden a la misma pregunta:

> ¿este candidato **parece** un núcleo?

Ninguna responde la otra:

> ¿tenemos evidencia de que **contiene** el conjunto estructural relevante, y no sólo una parte?

Sobre el plano de desarrollo, el candidato pasó las siete y dejó fuera el banco principal de
ascensores. `CORE_ACCEPTED` significaba "plausible" y se leía como "correcto". Esa distancia entre
las dos lecturas es el defecto que este ciclo corrige.

## 2. Qué son realmente las anclas — y por qué cambió su nombre

`enclosed_cells` → **`enclosed_cell_anchors`**, y la métrica `vertical_circulation_anchors` →
**`enclosed_cell_anchors_inside` / `_in_drawing`**.

Lo que el código mide: componentes conectadas de espacio libre, encerradas por muro dilatado, que no
son la dominante y que no superan el 2 % de la huella. Una caja de ascensor produce una de estas
celdas; **una bodega, un cuarto técnico, un baño individual y un hueco de dibujo también**. Que en el
plano de desarrollo las mayores fueran cabinas de ascensor fue una observación sobre ese dibujo, no
una propiedad del detector.

```
LA VARIABLE DICE LO QUE SABEMOS, NO LO QUE INFERIMOS.
```

Lo que sí sabemos, y alcanza: una celda cerrada es **evidencia de construcción permanente**.

## 3. Dos preguntas, dos estados, un veredicto

| Campo | Valores |
|---|---|
| `plausibility_status` | `PLAUSIBLE` · `NOT_PLAUSIBLE` (los siete criterios de E16.10) |
| `completeness_status` | `COMPLETE` · `INCOMPLETE` · `COMPLETENESS_NOT_EVALUATED` |
| `status` | `CORE_ACCEPTED` · `CORE_REJECTED_IMPLAUSIBLE` · `CORE_REJECTED_INCOMPLETE` · `CORE_UNVALIDATED_NO_COMPLETENESS_EVIDENCE` |

`CORE_ACCEPTED` exige **las dos**. No hay ningún camino por el que "plausible" sola produzca aceptado,
y la ausencia de evidencia produce un estado propio en vez de un pase.

## 4. La métrica

```
significativa   : área ≥ 10 % del ancla MAYOR dentro del alcance semántico
mass_coverage   : masa significativa dentro del candidato / masa significativa total
COMPLETE        : mass_coverage ≥ 0.80  y  ≥ 2 anclas significativas
```

Tres decisiones, cada una contra una regla tonta:

- **Masa, no conteo.** Cubrir nueve celdas diminutas y dejar fuera la grande no es cubrir el núcleo.
  Es también lo que impide la regla prohibida "cubrir todas las celdas": una celda puede quedar fuera
  sin consecuencias si su masa es marginal.
- **Significativas, no todas.** Una celda cuya área es una fracción ínfima de la mayor es ruido.
- **Umbral por debajo de 1.** Un recinto cerrado vecino que la pista abarcó de más —bodega, cuarto
  técnico, oficina cerrada— no obliga a nada mientras su masa sea la de un recinto ordinario. Lo que
  no puede quedar fuera es un quinto de la evidencia.

`dominant_anchors_outside` (anclas ≥ 25 % de la mayor que quedaron fuera) se **reporta y no veta**: un
núcleo al que le falta una pieza grande se lee distinto de uno al que le faltan varias chicas, y esa
diferencia le sirve a quien audita — pero un segundo umbral podría pelearse con el primero.

### Un camino que se probó y se descartó

El primer borrador agrupaba las anclas por proximidad y medía la cobertura del grupo de mayor masa.
Falló en el fixture del recinto ajeno por una razón instructiva: la distancia de enlace era una
fracción de la diagonal de **la pista**, así que una pista más floja producía un cluster más glotón y
el recinto vecino entraba. **Un criterio cuya severidad depende de lo prolijo que haya sido el
intérprete semántico no es un criterio.** La cobertura de masa con piso de significancia no tiene ese
defecto: no tiene ningún parámetro de distancia, y hay un test que lo verifica sobre el contrato.

## 5. Familia de fixtures

`tests/fixtures/core_completeness/make_e16_11_family.py`, lámina 1400×900. El fixture declara también
el **candidato**, porque la pregunta del ciclo es "dado un candidato, ¿está completo?" y el productor
quedó congelado: declararlo permite el par A/B —mismo dibujo, misma pista, candidato completo y
parcial— que un productor determinista no puede dar en el mismo dibujo.

| Fixture | Clase | Esperado | `mass_coverage` | Resultado |
|---|---|---|---|---|
| `A_COMPLETE_CLUSTER` | tres bloques, candidato los cubre | COMPLETE | 1,000 | ✔ |
| `B_PARTIAL_CLUSTER` | **mismo dibujo y pista**, candidato parcial | INCOMPLETE | 0,437 | ✔ |
| `C_UNRELATED_CLOSED_ROOM` | recinto ajeno dentro del alcance | COMPLETE | 0,900 | ✔ |
| `D_TINY_NOISE_ANCHORS` | núcleo + celdas diminutas | COMPLETE | 0,980 | ✔ |
| `E_DISTRIBUTED_SERVICE_BLOCKS` | bloques separados por circulación | COMPLETE | 1,000 | ✔ |
| `F_COMPACT_FALSE_COMPLETE` | compacto y de buen aspecto, un tercio del conjunto | INCOMPLETE | 0,422 | ✔ |
| `G_NO_RELIABLE_ANCHORS` | sin evidencia suficiente | NOT_EVALUATED | — | ✔ |

Margen: acepta entre 0,90 y 1,00; rechaza entre 0,42 y 0,44. El umbral 0,80 no cae cerca de ningún
resultado observado.

Un fixture se corrigió durante el diseño y queda dicho: `C` dibujaba el recinto ajeno de 170×150 —más
masa de celda cerrada que cualquier pieza del núcleo—, y eso no representaba la clase "recinto vecino"
sino una ambigüedad real donde rechazar es lo correcto. Pasó a tener tamaño de recinto ordinario.
