# E36 — PILOTO REAL: dejar de inventar y empezar a medir

E35 terminó con una conclusión que E36 toma al pie de la letra: **no hay evidencia suficiente para
seguir afinando heurísticas ni umbrales.** Dos unidades sobre una lámina no calibran nada, y ningún
razonamiento arregla eso. Lo único que lo arregla es procesar propiedades reales. E36 no agrega
inteligencia: agrega realidad, y construye el instrumento para registrarla.

---

## 1. El último salto de UX

E35 reportó que la confirmación del contorno sacaba al operador a otra pantalla. Ya no. Las tres
intervenciones posibles de Pack 1 ocurren **dentro de la página de la propiedad**:

| tipo | pregunta | respuesta |
|---|---|---|
| `UNIT_SELECTION` | ¿Cuál es la oficina? | un clic sobre una zona pintada |
| `GEOMETRY_CONFIRM` | ¿Esto corresponde a la oficina? | Sí / Necesita corrección |
| `SCALE` | *(sólo si ninguna fuente alcanzó)* | declarar la lámina, o medir a mano |

Medido en el navegador sobre el 403 real: `#oficina` → `#pack1` → `#revision` → `#pack1`, todo bajo
`/lab/p/<id>`. **Un shell.** La herramienta técnica de E27 sigue existiendo detrás, como último
recurso, no como paso normal.

El SVG de lo detectado se **dibuja desde el artefacto**, no se sirve desde disco: un archivo puede
ser de una corrida anterior, y pedir un «sí» sobre geometría vieja sería pedir confirmación de algo
que ya no es lo que se va a usar.

## 2. QA interno ≠ datos del cliente

El cliente entrega **plano, fotos, nombre y quizá los m²**. Unidad, geometría, escala, acceso y
núcleo son trabajo nuestro. La interfaz lo dice con esas palabras —«Necesitamos revisar el plano»,
nunca «Complete los siguientes campos»— y hay un test que lo verifica buscando ese vocabulario.

## 3. Qué cuenta como N

Dos filtros simultáneos, y ninguno es cosmético:

**Procedencia.** Sólo `REAL_BROKER`, `REAL_PUBLIC_LISTING`, `REAL_INTERNAL`. `source_type` nace en
`NULL` a propósito: "sin declarar" no es lo mismo que "real", y una propiedad heredada no se
convierte en evidencia porque estuviera ahí antes.

**Unicidad.** El sha256 del plano original. Verificado en el LAB real: cuatro propiedades marcadas
como piloto —«Apoquindo 3000 · piso 4», «Oficina 403», «Mi oficina», «X»— comparten un plano y el
panel muestra **1 / 10**, con la nota «1 plano repetido: sirve para repetibilidad, no para tamaño de
muestra». Representa al grupo la propiedad con etiquetas de verdad; a igualdad, la más antigua.

Contar mal acá sería peor que no contar: daría por calibrado algo que no lo está, que es justo lo
que E35 se negó a hacer.

## 4. Dos juicios, dos tablas

```
PRODUCT REVIEW   EXCELENTE · BUENO · MALO · PÉSIMO              → ¿sirve como entregable?
GEOMETRY GOLD    CORRECTO · INCORRECTO · INCOMPLETO · NO_APLICA → ¿el motor leyó bien el plano?
```

Un Pack 1 puede quedar «Bueno» con el núcleo mal recortado —se ve bien y el layout entra igual— y
puede quedar «Malo» con la geometría perfecta porque el estilo no gustó. Usar el juicio de producto
como prueba de corrección geométrica metería ruido justo donde más falta hace la medición.

`INCOMPLETO` es su propio veredicto: en la 403 un humano agregó seis pilares que el motor no vio,
pero los nueve detectados estaban bien. Llamar a eso «incorrecto» diría que el detector falla cuando
lo que falla es su recall. `NO_APLICA` tampoco es relleno: una planta sin núcleo no tiene un núcleo
mal detectado; forzar CORRECTO/INCORRECTO ahí fabricaría muestra.

Sólo se pide juicio sobre los componentes que el motor **efectivamente decidió**. Pedirlo sobre lo
que nadie emitió no produce evidencia, sólo fricción.

## 5. Cuándo un umbral queda calibrado

Dos condiciones, las dos necesarias:

```
sample_count >= MIN_SAMPLE (10)     AND     threshold_exercised == true
```

`threshold_exercised` significa que hubo casos a ambos lados de la vara. Con n = 12 todos del mismo
lado, el umbral nunca fue puesto a prueba y el estado sigue siendo `THRESHOLD_UNCALIBRATED`. Hay un
test para cada mitad del contrato.

**E36 no mueve ningún umbral.** Aun cuando un componente llega a `CALIBRATED`, `proposal()` devuelve
los valores actuales para que una persona decida (§12).

## 6. Lo que mide el panel

| métrica | qué contesta |
|---|---|
| propiedades reales N / 10 → N / 20 | ¿ya hay muestra? |
| % totalmente automáticas · mediana de intervenciones · motivo más frecuente | ¿«automático» es verdad? |
| tiempos entre seis hitos | ¿cuánto demora preparar una propiedad? |
| Pack 1 % Excelente/Bueno · motivos negativos | ¿el entregable sirve? |
| Pack 2 % con alguna alternativa buena · % todas malas | el layout engine como producto |
| falsos aceptos / falsos rechazos por componente | ¿los umbrales separan algo? |
| corpus de ambientación N / 8 fotos, N / 3 propiedades | ¿se puede correr E31.1? |

Lo que no se midió sale `None`, no `0`: un cero se promedia y miente; un `None` se excluye y se
cuenta como lo que es, una medición que no existe. Los tiempos son **reloj de pared entre hitos** y
la nota lo dice explícitamente — no son tiempo de atención humana, que nadie midió.

`ACCESS` se separa de `GEOMETRY` como motivo de intervención porque E35 encontró ahí el falso
acepto confiado: meterlo en la misma bolsa taparía justo lo que hay que vigilar.

## 7. Corpus de ambientación

Se construye solo a partir del piloto: fotos de propiedades con procedencia real, con su sha256,
dimensiones, si es candidata a hero y sus etiquetas de dificultad. Una foto de fixture no dice nada
sobre cómo responde un proveedor con material de un cliente. El panel muestra la presencia de
credenciales —nunca su valor, ni su longitud— y **no ejecuta nada** sin una acción explícita.

## 8. Export

`/lab/pilot/export.json` lleva lo que permite reproducir un juicio: tiempos, intervenciones,
confianzas del motor, etiquetas de verdad con la versión del motor que las produjo, calificaciones
de producto, tags negativos y hashes. Deja fuera nombres, ciudades, referencias de origen,
comentarios libres y rutas del sistema de archivos. Un export que arrastra datos «por si acaso» es
una fuga esperando ocurrir, y hay un test que busca cada uno de esos campos en el JSON crudo.

## 9. Lo que E36 NO hace

No mejora el ranking de candidatos, ni el detector de acceso, ni el de núcleo, ni pilares, ni
daylight, ni la escala por puertas. No toca `src/`. No cambia un umbral. **La misión es medir**, y
un instrumento que se ajusta a sí mismo mientras mide no es un instrumento.
