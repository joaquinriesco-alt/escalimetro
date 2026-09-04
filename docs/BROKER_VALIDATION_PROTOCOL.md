# PROTOCOLO DE VALIDACIÓN COMERCIAL — ESCALÍMETRO E13

## 1. Qué medimos y por qué

Ningún software puede autodeclarar que un layout es comercialmente enviable. El gate E1-C es humano
por definición. La pregunta que este protocolo responde es una sola:

> **¿Un broker mandaría este test-fit a un cliente real hoy, sin pedir primero que un arquitecto lo
> redibuje?**

No medimos si gusta. No medimos si parece innovador. No hay NPS. Medimos **intención comercial
declarada** y, en las fases siguientes, comportamiento real.

## 2. Qué NO es esto

No es investigación académica. Con cinco a diez evaluadores no hay significancia estadística y el
protocolo prohíbe reportar porcentajes sin el conteo bruto al lado: "60 %" con n=5 significa "3 de 5"
y así debe escribirse. Lo que buscamos es señal gruesa: rechazo sistemático, defectos repetidos,
diferencias entre alternativas, y si la QA humana es necesaria u opcional.

## 3. Muestra

| | |
|---|---|
| mínimo | 5 evaluadores |
| objetivo | 10 evaluadores |
| segmento primario | brokers de oficinas, ejecutivos de leasing, corredores comerciales, profesionales inmobiliarios que muestran plantas a clientes |
| segmento secundario | arquitectos de test-fit |

Los arquitectos se registran y se reportan **por separado**. No entran en el numerador del gate de
layout: su criterio es más exigente y distinto del criterio comercial, y mezclarlos convertiría el
resultado en un promedio sin significado. El gate exige al menos 4 evaluadores del segmento comercial.

## 4. Cegado

Durante toda la evaluación inicial el evaluador ve **OPTION X, OPTION Y, OPTION Z**. Nunca ve:

- los nombres A EFICIENTE / B BALANCEADO / C COLABORATIVO;
- ningún puntaje interno, de reglas o de modelos;
- la hipótesis sobre la recepción;
- los gates E1-T / E1-A / E1-C;
- ninguna mención de automatización, modelos o herramientas, hasta el paso 6 de la entrevista.

Las tres alternativas se dibujan con el mismo renderer, la misma paleta y el mismo nivel de detalle,
y su bloque de métricas es idéntico —las tres cumplen 40/40 puestos y 16/16 recintos— de modo que no
haya ninguna pista numérica sobre cuál es cuál.

## 5. Randomización

Se usan las **seis** permutaciones de A/B/C, asignadas por índice de evaluador (0→ABC, 1→ACB, …,
5→CBA, 6→ABC otra vez). El prompt original proponía cinco; con cinco cada alternativa no ocupa cada
posición el mismo número de veces, y el sesgo de posición es precisamente lo que la randomización
existe para cancelar. Con seis, cada alternativa ocupa cada posición exactamente dos veces por cada
seis evaluadores. El orden usado se guarda en `display_order` para poder auditarlo después.

## 6. Material que recibe el evaluador

Una sola lámina: `BROKER_VALIDATION_BLIND_BOARD.png`. Contiene planta base, programa solicitado,
leyenda, las tres alternativas y la advertencia de escala. No contiene puntajes, hashes, métricas de
solver, telemetría, ni lenguaje persuasivo ("optimizado", "inteligente", "premium", "generado por IA").

La geometría es la **exacta** de E07. E13 no redibuja, no mueve, no corrige y no embellece: extrae el
SVG que E07 ya produjo y le quita el pie de lienzo, que es donde iba el nombre de la estrategia.

## 7. Preguntas

| # | pregunta | tipo |
|---|---|---|
| Q1 | ¿Mandarías este test-fit al cliente sin pedir antes que un arquitecto lo redibuje? | YES / NO, por opción |
| Q2 | Si tuvieras que mandar UNA sola, ¿cuál? | X / Y / Z / NINGUNA |
| Q3 | ¿Cuánta confianza te daría enviarla? | 1–5, por opción |
| Q4 | ¿Ves algún error que te impediría enviarla? | YES / NO + hasta 3 categorías |
| Q40 | ¿Qué cambiarías antes de enviarlo? | NO_CHANGE / MINOR / MATERIAL / REDESIGN |
| Q14 | ¿Está bien resuelta la llegada y recepción? ¿Cambiarías su ubicación? | YES / NO |
| Q15 | ¿Cómo describirías esta alternativa? | máximo 2 etiquetas |
| Q16 | ¿Las tres son suficientemente distintas? | YES / NO + par |
| Q18 | ¿Qué haces hoy? ¿Cuánto tarda? ¿Con qué frecuencia? | cerradas |
| Q17 | ¿Sería útil en tu trabajo? ¿En qué momento? | YES / NO + caso de uso |
| Q19 | ¿Lo usarías si tardara < 2 min? ¿Para qué % de tus búsquedas? | YES / NO + rango |
| Q20 | ¿Necesitas QA de arquitecto antes de enviar? | ALWAYS / SOMETIMES / IMPORTANT_CLIENTS_ONLY / NO |
| Q41 | sólo arquitectos: ¿cuánto tiempo para dejarla enviable? | rango |

Q1 no admite "tal vez": la decisión forzada es el punto. Q2 es distinta de Q1 — puede haber tres
YES y una sola preferida.

## 8. Taxonomía de defectos

`ARRIVAL` `RECEPTION` `CLIENT_ROUTE` `BOARDROOM` `MEETING_ROOMS` `PRIVACY` `WORKSTATIONS` `DAYLIGHT`
`KITCHEN_DINING` `LOUNGE` `CIRCULATION` `ADJACENCY` `DENSITY` `READABILITY` `PROGRAM_MISSING`
`PROGRAM_EXCESS` `OTHER`

Un comentario puede llevar más de una categoría. La codificación la hace el entrevistador después de
la sesión, no el evaluador durante.

## 9. Caso de control: la recepción

Existe una hipótesis interna sobre la recepción que **no se revela**. Después de las preguntas
abiertas se pregunta si la llegada y la recepción están bien resueltas y si cambiaría su ubicación.
Eso permite contrastar, más adelante, cuatro juicios sobre el mismo aspecto: el humano, el crítico
por reglas, y los dos modelos. Si el humano dice que está bien y el crítico por reglas la castiga,
el defecto está en el crítico, no en la planta.

## 10. Umbrales — fijados antes de ver un solo dato

### Gate de calidad de layout

| | chequeo | umbral |
|---|---|---|
| G0 | muestra | >= 5 evaluadores y >= 4 del segmento comercial |
| G1 | send rate **sobre la alternativa preferida** | >= 70 % |
| G2 | confianza >= 4 sobre la preferida | >= 60 % |
| G3 | mismo defecto bloqueante compartido | < 30 % |
| G4 | cambio requerido NO_CHANGE o MINOR sobre la preferida | >= 70 % |

**G1 se mide sobre la preferida y no sobre "al menos una de las tres".** Con tres opciones al 40 % de
send rate individual, "al menos una" da 78 % y el gate pasaría sin que ninguna alternativa fuese
enviable. Ese agujero está cerrado a propósito. Una respuesta NINGUNA en Q2 cuenta como no enviable.

**G4 es el chequeo menos amable y por eso es el más valioso.** "Sí, la mandaría" cuesta poco decirlo;
"movería el directorio" es una respuesta material aunque venga acompañada de un sí. Un evaluador que
dice YES en Q1 y MATERIAL en Q40 no aporta un aprobado: aporta un defecto.

G2 está correlacionada con G1 —quien manda algo suele confiar en ello— así que endurece el gate pero
no es evidencia independiente. Se reporta como tal.

### Gate de valor de producto

| | chequeo | umbral |
|---|---|---|
| P1 | turnaround actual de 1–2 días o más, o no hacen test-fit | >= 60 % |
| P2 | lo necesitan al menos mensualmente | >= 50 % |
| P3 | lo usarían si tardara menos de 2 minutos | >= 70 % |
| P4 | serviría para >= 26 % de sus búsquedas | >= 50 % |

La necesidad de QA humana **se mide y se reporta, pero no es gate**: un producto con revisión humana
puede ser un negocio perfectamente viable. Lo que sí sería una señal grave es que la QA requerida
tarde tanto como el proceso actual, y para eso está Q41.

### Regla

Los umbrales **no se modifican después de ver resultados**. Si al leer los datos parecen mal
calibrados, eso se anota como aprendizaje para la ronda siguiente.

## 11. Clasificación por alternativa

| clase | criterio |
|---|---|
| `BROKER_READY` | send rate >= 70 % y confianza >= 4 en >= 60 % y bloqueantes < 30 % |
| `BORDERLINE` | send rate 50–69 % |
| `REJECTED` | send rate < 50 % |

Sin usar ningún puntaje de modelo.

## 12. Esquema de datos

`broker_validation_responses.csv`, una fila por RESPONDENT × OPTION. Columnas en
`src/escalimetro/validation/schema.py`. El CSV **no** guarda nombre, correo, teléfono ni empresa.

`validate_rows` comprueba dos cosas: que cada valor esté en su vocabulario, y que los campos por
evaluador sean idénticos en sus tres filas. Un CSV donde el mismo evaluador prefiere X en una fila e Y
en otra está mal capturado y no debe llegar a la scorecard.

## 13. Niveles de evidencia

| nivel | qué es | dónde ocurre |
|---|---|---|
| **L1 DECLARED** | "sí, lo mandaría" | la entrevista de E13 |
| **L2 SIMULATED** | elige una y redacta el correo con que la mandaría | al final de la misma entrevista |
| **L3 REAL** | la manda a un cliente real y se registra qué pasó | piloto posterior, 3 brokers |

El Commercial Gate fuerte es L3. E13 produce L1 y, cuando el evaluador coopera, L2. **L1 solo no
puede cerrar E1-C**: es la señal más barata que existe y la más fácil de dar por cortesía.

## 14. Piloto L3 (diseñado, no ejecutado)

3 brokers · 1 oportunidad real cada uno · 1 test-fit de Escalímetro. Se registra: enviado / no
enviado; si el cliente hizo preguntas; si pidió revisión; si el broker pidió un arquitecto; y si la
propiedad avanzó o se descartó. La métrica que importa es la primera: **cuántos de los tres lo
mandaron de verdad.**

## 15. Cómo ejecutar

1. Abre `ESCALIMETRO_BROKER_VALIDATION_PACK.html` (doble clic, sin servidor).
2. Sigue la hoja del entrevistador. Un evaluador por sesión, índice consecutivo desde 0.
3. Exporta las tres filas y pégalas en `broker_validation_responses.csv`.
4. Con 5 filas de evaluador completas, carga el CSV en la scorecard.
5. Lee el resultado de los dos gates por separado.

## 16. Cómo interpretar

| layout | producto | lectura |
|---|---|---|
| PASS | PASS | el sistema sirve y alguien lo necesita: avanzar |
| FAIL | PASS | hay dolor real y el output no está listo: arreglar el motor, no el pitch |
| PASS | FAIL | los planos sirven pero nadie los necesita así: repensar el producto |
| FAIL | FAIL | parar y revisar el supuesto de fondo |

## 17. Qué NO constituye un PASS

E1-C no pasa porque alguien diga "está increíble". E1-C pasa cuando evidencia real demuestra que un
profesional está dispuesto a usar esto frente a un cliente. Un cumplido no es evidencia.
