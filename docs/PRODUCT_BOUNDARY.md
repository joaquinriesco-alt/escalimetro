# Límite de producto — Escalímetro

Escalímetro es un motor de **pre-diseño / factibilidad / test-fit**.

> Escalímetro termina donde empieza el proyecto de arquitectura.

No reemplaza al arquitecto. No produce proyecto ejecutivo, planos municipales, detalles ni
especificaciones. Produce, a partir de una representación pobre (JPG/PDF comercial), una
geometría estructurada honesta (con confidence/provenance) y, sobre ella, alternativas de
ocupación comparables para decidir *si* un espacio sirve, *cuánto* cabe y *a qué costo
aproximado*. Todo lo que sale de Escalímetro es insumo para una conversación comercial o
para el encargo a un profesional, no un entregable de obra.

## Motor futuro (no implementado)

Agnóstico a vertical:

```
shell        geometría normalizada (Floorplate JSON — ETAPA 1)
+ constraints normativa mínima, accesos, evacuación, luz, pilares
+ program     lo que hay que meter (puestos, salas, camillas, mesas, racks…)
+ modules     piezas repetibles con dimensiones y reglas de adyacencia
+ rules       cómo se combinan (circulaciones, distancias, orientaciones)
+ scoring     cómo se compara una alternativa con otra
```

Vertical inicial: **OFFICE**.

Verticales futuras (NO se implementan ahora): retail, industrial/logística, clínicas,
gimnasios, restaurantes, colegios, otros espacios operativos repetibles.

Cada vertical se implementa después como *program/rule template* sobre el mismo motor,
nunca como un motor separado. Si una vertical necesita cambiar el motor, la abstracción
está mal y se arregla el motor, no se bifurca.

## Lo que ETAPA 1 garantiza a ETAPA 2

- Un polígono de unidad con status y provenance por elemento.
- Escala con método explícito (`published_area_inferred` no es una medición).
- `unknowns[]` explícitos: el generador no puede asumir lo que no está.
- `target_localization` y el registro de intervención humana, para medir el costo real
  de normalizar cada plano.
