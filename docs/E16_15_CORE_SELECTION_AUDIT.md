# E16.15 — AUDITORÍA DEL CRITERIO DE SELECCIÓN DEL PRODUCTOR

> Ciclo de EVIDENCIA: se audita, se mide y se registra. **El motor no cambia.**

## 1. El defecto auditado

E16.14 dejó dos definiciones de "encerrado" dentro del mismo motor:

| | Operación | Dónde |
|---|---|---|
| detector de celdas | dilata el muro con `RECT(k)` y busca espacio libre | `enclosed_cell_anchors` |
| selector del productor | rellena huecos del muro **sin dilatar** | `core_producer.select` (E16.14) |

Un recinto con vano de puerta menor que la escala de trazo existe como celda cerrada para el primero
y no para el segundo. Es lo que dejó al caso de desarrollo sin candidato.

## 2. Qué se probó

Un candidato v3 que sustituye la compuerta por una **relación topológica de responsabilidad**: una
pieza pertenece si TODO el anillo de contacto de una celda del alcance es muro de esa pieza, cerrado
con la MISMA dilatación canónica con la que la celda existe. Sin tamaño, sin distancia y sin usar
`significant_min_ratio` —que pertenece al contrato de completitud, no a la pertenencia—.

Medido a nivel de productor, con la evidencia y la pista congeladas:

```
RES   65 descubiertas → 3 seleccionadas   (9, 4 y 1 celdas asociadas; 7,95 % de la huella)
GPS   25 descubiertas → 2 seleccionadas   (1 y 2 celdas asociadas)
```

La inconsistencia "0 con una definición, 3 con la otra" queda eliminada.

## 3. Por qué NO se embarcó

Quitar la compuerta de significancia —que es lo correcto— destruye la precisión del banco sintético:
en P1–P12 las regiones espurias suben de 0 a 4–7 en las clases limpias. Causa medida: a la escala de
los fixtures el filtro de grosor del mapa de muros congelado (`max(3, k//4)`) satura en su piso y
admite trazo de mobiliario.

```
semiancho de tinta (p50/p75/p90)   banco P2 (1600×1000, umbral 5 px): 2,87 / 4,78 / 5,73
                                   RES     (1788×1070, umbral 5 px): 1,91 / 2,87 / 4,78
```

El banco es ~1,5× más grueso que el caso real frente al mismo umbral: su mobiliario cae por encima
del filtro y el de un plano publicado por debajo. Por eso ambos productores —el vigente y el
candidato— seleccionan lo mismo en la familia S: el límite está aguas arriba.

## 4. Estado

* **SELECTION ARCHITECTURE: FAIL** como criterio embarcable. La unificación de "encerrado" es
  correcta y necesaria, y por sí sola no sostiene la pertenencia mientras la evidencia de muro admita
  tinta no estructural a estas resoluciones.
* El candidato queda como artefacto medido (`cases/generalization/E16_15/`), no importable.
* `P10` sigue siendo **AMBIGUITY_NOT_RESOLVED**: no hay señal genérica disponible que distinga un
  núcleo repartido de dos clusters alternativos sin una regla de distancia, que está prohibida.
