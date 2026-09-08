# E16.16 — ¿ES LA EVIDENCIA DE MURO INVARIANTE A LA RESOLUCIÓN?

> Ciclo de EVIDENCIA. **El motor no cambia.** Veredicto: **D — REPRESENTATION LIMIT**.

## 1. Régimen de los parámetros vigentes

`stroke_scale_px` = 1 % del lado mayor, con clamp [3, 51]. **No es la raíz**: se mantiene en 1,04–1,17 %
del lado en todo el rango medido. Lo que no es estable es el umbral de grosor derivado de ella:

| lado | k | umbral grosor | umbral/k | régimen |
|---|---|---|---|---|
| 600 | 7 | 3 | **0,429** | el piso absoluto domina |
| 800 | 9 | 3 | 0,333 | el piso absoluto domina |
| 1000 | 11 | 3 | 0,273 | el piso absoluto domina |
| 1400 | 15 | 3 | **0,200** | `k//4` domina (división entera) |
| 1800 | 19 | 5 | 0,263 | `k//4` domina |
| 2400 | 25 | 7 | 0,280 | `k//4` domina |

La proporción oscila **más del doble** (0,20–0,43). "Trazo grueso" significa cosas distintas según el
ráster.

## 2. Banco multi-resolución

Una escena vectorial única —perímetro, dos tabiques, esquina en L, recinto cerrado con vano de puerta,
mesas, mobiliario lineal, texto y grilla— rasterizada a 600/800/1000/1400/1800/2400 px. Todos los
anchos son fracciones del lado, así que un muro es el mismo muro en las seis.

Métricas separadas a propósito, para que un recall alto no pueda tapar falsos positivos:
`wall_recall`, `wall_precision`, y fracción de falsos positivos sobre mobiliario, texto y grilla.

## 3. Resultado con el motor vigente

| lado | recall | precisión | FP mobiliario | FP texto | FP grilla |
|---|---|---|---|---|---|
| 600 | **0,302** | 1,000 | 0,000 | 0,000 | 0,000 |
| 800 | **0,281** | 0,861 | **0,878** | 0,000 | 0,003 |
| 1000 | 1,000 | 0,959 | 0,878 | 0,000 | 0,002 |
| 1400 | 1,000 | 0,794 | **1,000** | 0,168 | **1,000** |
| 1800 | 1,000 | 0,963 | 0,854 | 0,000 | 0,002 |
| 2400 | 1,000 | 0,958 | 0,845 | 0,000 | 0,002 |

La hipótesis de E16.15 queda **confirmada como síntoma**: la misma escena cambia de clasificación sólo
por la resolución. Pero el problema es doble: por debajo de 1000 px el muro **no se reconoce**, y por
encima el mobiliario **sí** se reconoce como muro.

## 4. Tres candidatos, ninguno suficiente

| variante | recall | precisión | FP mobiliario |
|---|---|---|---|
| escala de trazo canónica (reescalar a k=20 y clasificar allí) | 0,302–1,000 | 0,701–0,956 | 0,492–0,999 |
| grosor por transformada de distancia (k/8) | 0,281–0,999 | 0,795–1,000 | 0,000–0,990 |
| ambas combinadas | 0,269–0,920 | 0,728–0,971 | 0,000–0,750 |

Ninguna alcanza invarianza y discriminación a la vez. Por §21 no se embarca ninguna.

## 5. La causa medida

El ancho de la tinta **no sigue** al ancho dibujado:

| lado | dibujado (mobiliario / tabique / perímetro) | tinta mobiliario | tinta muro |
|---|---|---|---|
| 600 | 1 / 3 / 5 px | 1,9 | 3,8 |
| 1400 | 3 / 8 / 12 px | 3,8 | 5,7 |
| 2400 | 5 / 13 / 20 px | 3,8 | 9,6 |

Cuadruplicar la resolución multiplica el ancho dibujado por 4 y el ancho de tinta medido por 2,5. La
capa de tinta —black-hat contra el fondo local— responde al **contraste local**, no al grosor: por
encima de la escala de trazo satura. Preguntarle "grosor" a esa representación es preguntarle algo
que ya no contiene, y por eso mover el umbral no arregla nada: no hay umbral que separe 3,8 de 5,7.

## 6. Consecuencia

`WALL_EVIDENCE` no se corrige con otra fórmula sobre la misma representación. La siguiente fase debe
estudiar una representación estructural distinta —una que mida grosor donde el grosor todavía existe:
sobre el gris, antes de reducirlo a una máscara binaria de contraste—. No corresponde reintentar el
selector de E16.15 antes de eso.
