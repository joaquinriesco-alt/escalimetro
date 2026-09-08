# E17 — REPRESENTACIÓN DE ANCHO ESTRUCTURAL (SPIKE)

> Spike de arquitectura. **El motor no cambia** y ninguna de estas representaciones está conectada
> al runtime. Veredicto: **B — el ancho se recupera; el ancho SOLO no discrimina en la banda fina.**

## 1. La magnitud buscada

```
local_stroke_width_px(x, y)  =  estimación del ancho gráfico local de una estructura oscura
                                en el ráster ORIGINAL
```

Es una magnitud **gráfica**: no es espesor de tabique, ni metros, ni escala del edificio. La única
exigencia es que guarde relación monótona con el ancho dibujado y que no se sature.

## 2. Por qué el spike

E16.16 midió que la representación vigente (`structural_ink` → morfología) comprime el ancho:
cuadruplicar la resolución multiplica el ancho dibujado por 4 y el medido por 2,5. Sobre esa
magnitud no hay umbral posible.

## 3. Banco

Una fuente vectorial (`e17-width-bench/1.0.0`) con 20 primitivas —escalera de anchos 1×…8×, dos
grises distintos al mismo ancho, paralelas, esquina, T, vano, recinto, mesa, escritorio, texto,
grilla, hatch y mezcla gruesa/fina—, rasterizada a 600/800/1000/1400/1800/2400 px, más variantes de
contraste, blur y JPEG. El ground truth de ancho sale del vector, no de la medición.

## 4. Resultados

| representación | error rel. | orden | estabilidad (CV) | junturas | contraste | costo @1400 |
|---|---|---|---|---|---|---|
| distance transform | 0,533 | 0,978 | 0,154 | 0,377 | 0,000 | 0,02 s |
| ridge scale-space | 0,306 | 0,922 | 0,151 | 0,244 | 0,000 | 0,30 s |
| **edge-pair** | **0,171** | 0,956 | **0,128** | **0,091** | 0,000 | **0,02 s** |
| morph scale-space | 0,687 | 0,922 | 0,159 | 0,625 | 0,000 | 0,38 s |

Las cuatro preservan el orden (0,92–0,98) y escalan con la resolución, que es exactamente lo que la
representación vigente no hace. **edge-pair** gana en error, junturas, costo y degradación, con un
modo de fallo identificado: donde no hay bordes cercanos —tinta muy fina a baja resolución— la
distancia al borde se dispara (37‰ en el hatch a 600 px).

## 5. El resultado que importa

Ancho medido, en milésimas del lado, con edge-pair:

```
muro 1×      1,4–2,5‰        mesa    1,4–2,5‰        texto  1,4–2,5‰      grilla 1,4–2,5‰
muro 3×+     4,3–13,3‰
```

**Un muro de 1× y una mesa de 1× miden lo mismo, porque miden lo mismo.** No es un defecto de la
representación: el ancho no contiene esa distinción. Desde 2×–3× hacia arriba, en cambio, la
separación es limpia (89–93 % de las muestras de muro por encima del máximo de tinta ajena).

## 6. Consecuencia

El ancho es recuperable y merece ser una señal. No basta por sí solo. La siguiente arquitectura debe
combinarlo con estructura —continuidad de línea, uniones, enclaustramiento—, y eso se diseña con
fixtures genéricos antes de tocar ningún caso.
