# E16.14 — PRODUCTOR DE NÚCLEO MULTI-COMPONENTE

> El semantic hint dice DÓNDE BUSCAR. La evidencia estructural dice QUÉ EXISTE.
> El productor decide QUÉ REGIONES PROPONER. El contrato decide SI ESA PROPUESTA ES ACEPTABLE.
> Una variable en este ciclo: **el productor**.

## 1. Dónde se perdía la información

El productor de E16.10 tenía tres puntos de pérdida, todos en `build_core`:

1. `MORPH_CLOSE` de radio fijo (2,5 % del lado mayor) sobre la evidencia — **fabrica** una franja
   donde el dibujo tiene circulación;
2. `cluster = (lab == mayor)` — de N piezas queda UNA, elegida por **tamaño**;
3. `drawContours(max(cnts))` + rellenar + volver a quedarse con la mayor — segunda pérdida, y el
   relleno del contorno externo se traga espacio que nadie encierra.

Ninguna sobrevive. "El núcleo es la componente mayor" queda descartado como principio: una pieza
grande puede ser fachada, mobiliario encadenado, perímetro o **una parte** del núcleo. Y "tomar todas
las piezas del alcance" es igual de falso: convertiría la pista en geometría.

## 2. Las tres responsabilidades

| Fase | Qué hace | Qué NO hace |
|---|---|---|
| **DISCOVERY** | componentes conectadas del mapa de muros congelado, con una reparación de ráster del **mismo tamaño** que la apertura de grosor de E16.7/E16.8-CORE | no enlaza: el elemento no alcanza más lejos que el ancho de trazo, así que no puede cruzar un pasillo ni un vano |
| **SELECTION** | una pieza entra si es **interior**, vive **mayormente dentro del alcance** semántico (`LINK_MIN_OVERLAP`, constante ya existente) y **encierra al menos una celda cerrada significativa** | no usa tamaño, no usa distancia, no consulta el contrato |
| **OUTPUT** | devuelve las piezas **separadas** | no inventa conexión |

"Significativa" no es un número nuevo: es la definición ya congelada en E16.11 —área ≥
`significant_min_ratio` × la mayor celda del alcance—. Hace falta porque, medido, el mapa de muros
congelado admite trazo de mobiliario de 3 px a la escala de estas láminas, y un rectángulo de
mobiliario encierra una celda igual que un ducto: lo que los separa no es el grosor —esa señal está
agotada— sino la masa del recinto respecto del mayor del alcance.

**Abstención:** si ninguna pieza cumple las tres condiciones, el productor no propone nada. No
entrega la mejor de las malas.

## 3. Sin lazo cerrado contra el juez

El productor propone **una vez** y no lee el veredicto. No importa `accept_core`, ni
`evaluate_completeness`, ni `CORE_ACCEPTANCE`, ni `fabricated_fraction` (test que lo verifica sobre
el AST). Reutiliza una constante congelada; eso no es leer un veredicto, es no inventar un tamaño
mínimo propio.

## 4. Frontera automatizada, invertida

`generalization/scope_guard.py` hashea el texto de CONTRATO, EVIDENCIA (tinta estructural, mapa de
muros, celdas cerradas, `open_floor` y sus constantes), PISTA SEMÁNTICA y AGUAS ABAJO. El test falla
nombrando la función si alguno cambia. E16.13.1 congeló el productor; E16.14 congela todo lo demás.

## 5. Qué se midió (P1–P12, geometría NO declarada)

Recall total (1,000 sobre las cajas de verdad) en todas las clases limpias, con precisión 0,96–1,00 y
**cero** regiones espurias en P2, P3, P4, P5, P7 y P9 — incluido el caso que E16.10 no podía
representar: dos y tres bloques separados por circulación, sin puente.

Seis desviaciones declaradas, todas con la misma causa aguas arriba (tinta no estructural admitida
como muro): una región de mobiliario de más en P1 y P12; una oficina encadenada por mobiliario en P6
(precisión 0,51); recall 0,51 en P8 por fusión con la envolvente; y ausencia de abstención en P10 y
P11. Ninguna se parcheó con una heurística nueva.
