# PROTOCOLO DEL GATE DE GENERALIZACIÓN — ESCALÍMETRO E14

## 1. La pregunta

Escalímetro se desarrolló entero sobre un caso: la Oficina 403 de GPS Property, 543 m². Eso crea un
riesgo que ninguna cantidad de tests internos detecta:

> ¿El motor actual puede tomar un segundo shell real y producir un resultado razonable **sin
> modificar el motor para ese shell**?

E14 responde eso y nada más. No es desarrollo de features. No es "hacer que funcione como sea".

## 2. Regla absoluta — zero tuning

Antes de mirar el resultado del segundo shell se **congela el motor** y se hashea. Desde ese momento
está prohibido modificar solver, catálogo de emplazamientos, generación de candidatos, pesos del
objetivo, restricciones duras o blandas, reglas de circulación, dimensiones de recintos o puestos,
lógica de anclajes, lógica de recepción, pesos de luz o privacidad, reglas de adyacencia, definición
de estrategias, semántica del SpatialGraph, umbrales de scoring, el crítico de layout o las
heurísticas de extracción geométrica — **con el objetivo de hacer pasar el segundo shell**.

Al terminar se recalculan los mismos hashes. Si el motor cambió, **E14 es inválido**, sin importar
si el segundo shell "quedó mejor".

Un FAIL honesto vale más que otro PASS obtenido afinando heurísticas.

## 3. Selección del segundo shell

La regla se declara **antes** de ejecutar, y se ejecuta **un solo** candidato: no se prueban dos y se
reporta el mejor.

> Entre los candidatos REALES del repositorio que no sean el caso de entrenamiento, elegir el de
> identificador numéricamente MENOR que cumpla: (a) rótulo legible en el dibujo, (b) polígono
> delimitado por borde continuo, (c) superficie publicada en la leyenda.

Prioridad: real antes que sintético; geometría distinta de la del caso de entrenamiento; perímetro
separable; acceso identificable; núcleo y pilares interpretables. No se usa web ni se descarga nada:
sólo evidencia que ya está en el repositorio.

## 4. Nivel de generalización

| nivel | qué significa |
|---|---|
| **INTRA-DRAWING** | el segundo shell viene de la misma lámina fuente. Comparte estilo gráfico, convenciones, resolución y contexto de núcleo y fachada. |
| **CROSS-DRAWING** | viene de otro archivo, otra fuente, otro corredor. |

Un PASS intra-drawing **no autoriza** a afirmar que Escalímetro generaliza a cualquier oficina. Sólo
prueba que el pipeline no está acoplado a la geometría concreta del caso de entrenamiento.

## 5. Nada de transferir etiquetas

No se transfieren perímetros, columnas, puertas, accesos, fachadas ni emplazamientos desde el caso de
entrenamiento. Lo único transferible, si comparten imagen, es información **global** demostrablemente
común: escala de píxel, sistema de coordenadas, orientación, y la geometría del núcleo del edificio
cuando físicamente es la misma. Aun así el shell target debe detectarse de forma independiente.

## 6. AUTO antes que ASSISTED

Primero se ejecuta el pipeline **completamente automático** y se guarda el resultado. Sólo después,
si no alcanza shell ready, se permite HITL — y sólo con mecanismos que ya existían.

Máximo **10 operaciones conceptuales**. Permitido: confirmar target, agregar o quitar una columna,
corregir un acceso, corregir un segmento de fachada, resolver una ambigüedad de borde. Prohibido:
dibujar el layout, mover salas, corregir el solver, hacer el fit a mano.

Se registra: número de operaciones, segundos humanos estimados, y cada override exacto.

## 7. El programa no se adapta

Se usa **exactamente el mismo programa** del caso de entrenamiento: 40 puestos open, 4 oficinas
privadas, 3 salas de 4, 1 sala de 8, 1 directorio de 12, 3 phone booths, recepción, kitchenette,
comedor y lounge.

No se reduce para conseguir un PASS. Si el segundo shell es demasiado chico, **NO_FIT es una
excelente señal de generalización**: significa que el motor sabe distinguir un inmueble que sirve de
uno que no.

## 8. NO_FIT no es SOLVER_FAILURE

| | qué es |
|---|---|
| **NO_FIT** | el motor exploró correctamente y no encontró solución que cumpla las restricciones duras |
| **SOLVER_FAILURE** | excepción, representación inválida, catálogo vacío por bug, timeout patológico, geometría inválida, o incapacidad de explorar un caso plausible |

**No se llama "no cabe" a un crash.** La distinción se sustenta con evidencia: ausencia de excepción,
geometría válida, catálogo no vacío, candidatos efectivamente evaluados, y —si el modelo exacto lo
permite— una respuesta INFEASIBLE en lugar de un timeout.

## 9. Scorecard

| | chequeo |
|---|---|
| G0 | INPUT — existe un segundo shell real |
| G1 | LOCALIZATION — target identificado |
| G2 | NORMALIZATION — shell ready, AUTO o ASSISTED |
| G3 | PROGRAM EXECUTION — el motor produce FIT/NO_FIT sin crash |
| G4 | GEOMETRY SAFETY — 0 colisiones, restricciones coherentes, circulación computable |
| G5 | SEMANTIC QUALITY — acceso, núcleo y fachada correctos según la evidencia disponible |
| G6 | ZERO TUNING — hash del motor antes == después |
| G7 | RUNTIME — registrado, sin umbral artificial |

Resultado global, **exactamente cuatro valores**, sin quinta categoría:

`GENERALIZATION_PASS` · `ASSISTED_GENERALIZATION_PASS` · `GENERALIZATION_FAIL` · `INSUFFICIENT_INPUT`

## 10. PASS no significa FIT

Es el punto que más fácil se malinterpreta. Un shell entendido correctamente, un solver ejecutado
correctamente, un resultado NO_FIT explicable y cero tuning **son un PASS**. Se está validando el
motor, no la capacidad del inmueble.

## 11. Auditoría de acoplamiento

Se inspecciona el código congelado buscando heurísticas acopladas al caso de entrenamiento: números
mágicos, coordenadas, etiquetas de unidad, dimensiones específicas, posiciones de píxel, anclajes
fijos, máscaras por fuente, nombres de archivo, áreas incrustadas y condicionales por caso.

Cada hallazgo se clasifica en `BENIGN`, `CASE_COUPLING_RISK` o `CONFIRMED_CASE_COUPLING`, y se anota
si llegó a manifestarse en esta corrida. **No se corrige nada dentro de E14**: los arreglos son
backlog.

## 12. Si da FAIL

No se arregla. Se escribe un backlog ordenado por P0 (impide procesar otro shell), P1 (degrada la
calidad pero permite resultado) y P2 (presentación o performance). Cada ítem lleva evidencia,
hipótesis de causa raíz, etapa afectada y experimento propuesto — nunca implementación.

## 13. Si da PASS

Tampoco se mejora nada. El siguiente experimento debe ser **más difícil**: un shell de otro archivo y
otra fuente. Un PASS intra-drawing no es una victoria; es la mitad más fácil del problema.

## 14. Cómo repetirlo

```bash
# 0 · congelar
PYTHONPATH=src python -c "from escalimetro.generalization.freeze import manifest,write; \
  write('cases/generalization/E14/FROZEN_ENGINE_MANIFEST.json', manifest('.','<commit>','freeze'))"

# 1 · AUTO
PYTHONPATH=src python -m escalimetro.cli run --case <caso> --out <caso>/outputs/auto

# 2 · ASSISTED (<= 10 operaciones, sólo si AUTO no alcanza)
PYTHONPATH=src python -m escalimetro.cli run --case <caso> \
  --overrides overrides_assisted.json --out <caso>/outputs/assisted

# 3 · nominal, mismo programa
PYTHONPATH=src python -m escalimetro.layout.run --case <caso> \
  --program program_templates/office_balanced_48.json

# 4 · robustez, rangos de E06 sin tocar
PYTHONPATH=src python -m escalimetro.layout.e06.run sweep --case <caso>

# 5 · verificar el congelamiento
PYTHONPATH=src python -m pytest tests/test_e14_generalization.py -q
```

E14 **no** llama a OpenAI ni a Anthropic ni a Railway. Mide la generalización del motor determinista.
La capa de crítica por IA viene después, si el segundo caso resulta técnicamente válido.
