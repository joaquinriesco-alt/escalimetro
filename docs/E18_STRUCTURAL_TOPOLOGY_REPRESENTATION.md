# E18 — REPRESENTACIÓN DE TOPOLOGÍA ESTRUCTURAL (SPIKE)

> Spike de arquitectura. **El motor no cambia** y el ANCHO no participa en ninguna medición.
> Veredicto: **E — INFORMATION LIMIT**.

## 1. Qué se midió como "topología"

Propiedades observables sin semántica arquitectónica, nombradas por lo que se mide (§3):
componentes conectadas, puntas (grado 1), uniones en L, T y X, ciclos y recintos cerrados, camino
largo del componente mayor, densidad de uniones, densidad de puntas y periodicidad (pico de
autocorrelación de las proyecciones).

Todo el banco se dibuja con **un solo ancho**: si las clases se distinguieran por grosor, el
experimento estaría midiendo width otra vez.

## 2. Tres representaciones comparadas

| | F1 componentes | F1 puntas | F1 T | F1 X | F1 ciclos | CV multi-res (comp / puntas) | coste @1400 |
|---|---|---|---|---|---|---|---|
| **skeleton graph** | **1,00** | **1,00** | **0,891** | **0,884** | 0,988 | 0,02 / 0,07 | 0,050 s |
| line segment graph | 0,154 | 0,164 | 0,065 | 0,112 | 0,988 | 0,24 / 0,51 | 0,013 s |
| contour graph | 1,00 | — | — | — | 0,988 | 0,03 / — | **0,006 s** |

Degradación (variación media de la firma):

| | gris oscuro | gris medio | blur | JPEG q55 | microcortes 2 px |
|---|---|---|---|---|---|
| skeleton graph | 0,001 | 0,001 | 0,043 | **0,816** | **1,507** |
| line segment graph | 0,000 | 0,000 | 0,159 | 0,188 | 0,316 |
| contour graph | 0,000 | 0,000 | 0,016 | **0,003** | **0,077** |

El esqueleto reconstruye el grafo completo y es insensible al gris, pero se rompe con JPEG y con
microcortes. El grafo de contornos sólo ve enclaustramiento, y es el más robusto y barato.

## 3. Qué señal separa qué

AUC descriptiva, wall-like contra cada clase (0,5 = sin información; 0 y 1 = separación total):

| señal | mobiliario | texto | grilla | anotación | ambiguas |
|---|---|---|---|---|---|
| camino largo | 0,683 | **1,000** | 0,150 | 0,725 | 0,700 |
| densidad de uniones | 0,350 | **0,000** | 0,350 | **0,042** | 0,560 |
| densidad de puntas | 0,783 | **0,000** | 0,192 | 0,235 | 0,700 |
| periodicidad | 0,441 | 0,067 | **0,000** | 0,445 | 0,611 |
| ciclos | 0,183 | 0,071 | 0,325 | 0,417 | 0,360 |

**Texto y grilla sí se separan.** El mobiliario no: ninguna señal llega a una separación decisiva.

## 4. El caso crítico

Un recinto y una mesa de la **misma geometría y el mismo ancho** producen firmas **idénticas**:

```
comp = 1 · puntas = 0 · T = 0 · X = 0 · ciclos = 1 · densidad de uniones = 0 · camino = 0,56
```

Lo único que las diferencia es el **tamaño**, que no es topología y que ya sabemos que tampoco decide
—una mesa grande de sala de directorio existe—. Ni el ancho (E17) ni la topología (E18) contienen la
distinción muro/mueble.

## 5. Consecuencia

Seguir apilando heurísticas geométricas sobre el ráster tiene techo. La distinción que falta no es
geométrica: es de contexto. La arquitectura que corresponde estudiar es **geometría + contexto
semántico**, que este proyecto ya midió como viable en E16.9 (modelo de visión que propone, geometría
determinista que dispone, contrato que veta).
