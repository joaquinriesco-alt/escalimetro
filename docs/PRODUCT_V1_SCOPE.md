# ESCALÍMETRO V1 — ALCANCE DE PRODUCTO

> **La promesa:** *"Dame una planta libre y tu programa; te devuelvo alternativas de layout en segundos."*
>
> V1 **no** es "IA que entiende cualquier plano".

## Qué acepta V1

UNA planta shell / planta libre suficientemente limpia, de la que se pueda leer geometría:
perímetro útil, fachadas/ventanas cuando existan, núcleo, pilares, shafts, baños existentes,
escaleras, ascensores, accesos y demás elementos fijos que el layout no puede mover.

Puede traer texto, cotas, rótulos o marca de agua **si no impiden la lectura geométrica**.

## Qué NO tiene que resolver V1

- distinguir escritorio de recinto;
- distinguir mesa de muro;
- separar mobiliario existente de arquitectura;
- borrar un layout anterior;
- interpretar estaciones de trabajo existentes.

Si el plano trae mobiliario abundante o un layout previo que impide recuperar una shell confiable,
el veredicto es `INPUT_NOT_READY` y **eso no es un fallo del motor V1**. Es un input fuera de
contrato. La limpieza automática es V2 (ver `PLAN_CLEANING_DEFERRED.md`).

## Frontera HITL

V1 puede pedir confirmación de **una pregunta cerrada a la vez**:

| Pregunta | Permitida |
|---|---|
| ¿Este es el perímetro? | sí |
| ¿Esta escala es correcta? | sí |
| ¿Este es el acceso? | sí |
| ¿Estos elementos son fijos? | sí |

V1 **no** convierte a ESCALÍMETRO en CAD. No se dibuja cada recinto, no se fija a mano dónde va el
directorio, no se mueven salas una a una, no se diseña objeto por objeto. El producto entrega la
primera aproximación racional; el humano confirma hechos, no diseña.

## Qué entrega V1

3 alternativas por caso, geométricamente distintas, válidas y comparables:

```
A — EFICIENTE      B — BALANCEADO      C — COLABORATIVO
```

Las etiquetas sólo se usan cuando hay diversidad real detrás. Cada alternativa reporta puestos,
privados, salas, recintos del programa, área ocupada, circulación, capacidad, restricciones
incumplidas, score y trade-offs.

## Criterio diario

> ¿Esto nos acerca a generar un buen layout?

Si no: se posterga. En particular quedan **fuera del camino crítico** de V1 la limpieza automática,
el reconocimiento semántico general, el soporte de cualquier plano, el VLM productivo, el
multi-provider y la generalización a plantas amobladas.
