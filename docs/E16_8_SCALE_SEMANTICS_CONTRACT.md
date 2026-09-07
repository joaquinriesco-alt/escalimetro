# E16.8 — Contrato semántico de escala

## 1. El error de contrato que se cierra

```
px_per_m = sqrt(area_px2 / area_m2)
```

La fórmula siempre fue correcta. La pregunta previa no se hacía nunca:

> ¿`area_px2` y `area_m2` miden **la misma región del espacio**?

El tipo de área publicada (`useful`, `rentable`, `total`, `unknown`) existía desde E01 y sólo movía
un número de confianza. No tenía poder de veto. Una escala salía siempre, con aspecto normal.

**Por qué esto importa más que un detector roto:** un detector que no encuentra el núcleo deja un
vacío visible y el pipeline se detiene. Una escala tomada de otra región produce metros plausibles;
un px/m equivocado se ve igual de bien que el correcto, y todo lo que dependa de metros —anchos de
circulación, capacidad, FIT/NO_FIT— queda mal sin que nada lo advierta.

```
UNA CIFRA DE SUPERFICIE NO ES UNA ESCALA.
Es una observación sobre una región del espacio.
```

## 2. Regiones en píxeles

Qué recortó el motor. Sale del **hecho de origen** `drawing_scope`, no de una heurística sobre el
resultado.

| Región | Qué es | Quién la produce hoy |
|---|---|---|
| `full_footprint` | todo lo encerrado por el perímetro exterior | `whole_shell` (E16.6/E16.7) |
| `target_unit` | la unidad objetivo dentro de una lámina multiunidad | `opencv_flood` / `opencv_color` |
| `useful_region` | huella menos exclusiones **efectivamente calculadas** | nadie todavía — ver §6 |
| `unknown_region` | hay polígono, no se sabe qué representa | por defecto |

## 3. Tipos de área publicada

Vocabulario auditado antes de tocarlo. `useful`, `rentable`, `total` y `unknown` ya existían en
`case.json`, en el esquema y en el cálculo de confianza.

| Kind | ¿Existía? | Región semántica | ¿Puede escalar la huella completa? | Por qué |
|---|---|---|---|---|
| `useful` | sí | superficie útil según la fuente; excluye al menos comunes/núcleo | **no** | nombra una región menor que la huella, por definición |
| `rentable` | sí | arrendable; puede incorporar prorrateo | **no** | es una convención comercial, no una región del dibujo |
| `total` | sí | **ambiguo** | sólo con declaración | en el mercado chileno suele ser útil + prorrateo, pero el repo nunca lo definió y también se usa para "total del piso" |
| `full_footprint` | **no, agregado en E16.8** | área de lo encerrado por el perímetro | sí | faltaba la forma de decir la única cosa que autoriza la inferencia sobre una planta completa |
| `unknown` | sí | ninguna | como supuesto | no se puede demostrar nada |

## 4. Matriz de compatibilidad

Un solo criterio, aplicado igual a las 20 celdas: **COMPATIBLE** cuando el vocabulario define las dos
como la misma región; **INCOMPATIBLE** cuando las define como regiones distintas; **UNKNOWN** cuando
el vocabulario no alcanza. Ninguna celda está resuelta "porque en la práctica suele coincidir": ésa
es la puerta que E16.8 cierra.

| pixel region \ area kind | `full_footprint` | `useful` | `rentable` | `total` | `unknown` |
|---|---|---|---|---|---|
| `full_footprint` | **COMPATIBLE** | INCOMPATIBLE | INCOMPATIBLE | UNKNOWN | UNKNOWN |
| `useful_region` | INCOMPATIBLE | **COMPATIBLE** | UNKNOWN | UNKNOWN | UNKNOWN |
| `target_unit` | INCOMPATIBLE | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| `unknown_region` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

`target_unit × useful` es UNKNOWN y no COMPATIBLE a propósito: la unidad recortada **se parece** a su
superficie útil, y "se parece" no es una definición.

## 5. Estados y consecuencias

| Estado | Cuándo | `px_per_m` | Consecuencia |
|---|---|---|---|
| `SCALE_CONFIRMED` | escala humana (`scale_manual`) | valor | consumible |
| `SCALE_INFERRED_MATCHED_REGION` | regiones compatibles | valor | consumible, sigue siendo inferida |
| `SCALE_UNCONFIRMED_REGION` | correspondencia indemostrable | valor | supuesto: requiere `confirm: scale_assumption` |
| `SCALE_INCOMPATIBLE_REGION` | regiones distintas por definición | **None** | el solver no corre; la presentación no muestra confianza; el valor que habría salido queda en `rejected_px_per_m`, sólo para trazabilidad |
| `SCALE_NOT_EVALUATED` | no había con qué | None | — |

## 6. Región útil en píxeles: por qué todavía no existe

```
AUSENCIA DE DETECCIÓN  !=  DETECCIÓN DE AUSENCIA
```

`useful_pixel_region_area(footprint, exclusions, exclusions_evaluated)` levanta
`ExclusionsNotAvailable` mientras las exclusiones no hayan sido **evaluadas**. Un detector de núcleo
que devuelve lista vacía porque busca color en un plano en blanco y negro no ha demostrado que no
haya núcleo; restar cero y llamar "útil" al resultado convierte un detector roto en evidencia.

Mientras no exista un detector de exclusiones que funcione fuera de la lámina coloreada, no hay
`useful_region` en píxeles, y una escala que dependa de ella no es calculable. **Eso es correcto, no
un pendiente que E16.8 debiera tapar.**

## 7. Dos incertidumbres que no se mezclan

| | Pregunta | Herramienta | ¿La cura un barrido? |
|---|---|---|---|
| **Numérica** | "¿la escala es 43 o 46 px/m?" | barrido de robustez ±x % | sí |
| **Semántica** | "¿de qué superficie hablamos?" | matriz de regiones | **no** |

Un barrido de ±10 % sobre una base equivocada devuelve tres respuestas equivocadas con aspecto de
rango. Y una confirmación humana genérica (`confirm: ["scale_assumption"]`) acepta la incertidumbre
numérica; **no** puede declarar que dos regiones distintas son la misma. Para eso está
`known_area_region`, que es un hecho de origen y entra por `case.json`.

## 8. Equivalencia declarada por la fuente

```json
{ "known_area_m2": 1234.5, "known_area_kind": "useful",
  "known_area_region": "full_footprint" }
```

Si la fuente declara explícitamente qué región mide su cifra, esa declaración autoriza la inferencia
y queda registrada como tal (`by_declaration`). Es un hecho de origen, no una heurística: nadie la
deduce, alguien la afirma.
