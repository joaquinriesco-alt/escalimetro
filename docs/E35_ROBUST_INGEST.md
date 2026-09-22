# E35 — INGRESO ROBUSTO: SACAR EL NOMBRE DE LA GEOMETRÍA Y MEDIR LOS UMBRALES

E34 logró el cambio de UX correcto —nombre + plano + fotos → Pack 1— y dejó dos deudas que este
documento salda con medición, no con opinión.

---

## 1. El nombre era un input geométrico, y ya estaba roto

La cadena que E35 corta, verificada sobre la lámina real de GPS Property:

```
property.title → cases.title → case.json["unit_label"] → pipeline.cfg.unit_label
               → OCRVisionInterpreter.interpret(img, target_unit)
               → _digits("Oficina 403") == "403"
               → se busca ese número impreso SOBRE el dibujo
               → si cae dentro de un relleno saturado, ahí empieza la segmentación
```

Tres medidas sobre esa cadena:

| título | qué pasa hoy |
|---|---|
| `Oficina 403` | tesseract lee `403` en (481,367) con confianza 95 → funciona |
| `Oficina 401` | **`RuntimeError: Sin localización`** — el rótulo "OFICINA 401" está impreso en blanco sobre azul y no se lee a ninguna confianza útil; el único `401` legible está en la leyenda, fuera del plano |
| `Mi oficina` | `_digits` devuelve vacío → cero hints → mismo `RuntimeError` |

La segunda fila es la importante: **`cases/002_gps_401` es una propiedad real de este repositorio y
no tiene camino automático**, aun con el número correcto en el título. La dependencia del nombre no
era un riesgo futuro; ya estaba fallando en la mitad de la muestra.

Hay además una segunda puerta, más silenciosa: aunque `overrides.seed_points` tiene prioridad sobre
el hint de OCR, mientras el intérprete corra el título sigue decidiendo `has_color_hint` y con eso
qué estrategia de segmentación se usa (`strategy_for`). Por eso E35 no se conforma con adelantarse
en la precedencia: **apaga el intérprete** (`vision: "null"`) cuando ya sabe qué región mirar.

## 2. Qué mira ahora — `webapp/domain/units.py`

Señales del dibujo, ninguna del título:

| señal | qué aporta |
|---|---|
| relleno de color | una lámina que publica varias unidades las demarca pintándolas; la leyenda existe porque el color ES el identificador |
| superficie y proporción | 39.011 / 20.008 / 14.873 px sobre la 403 |
| densidad de tinta | un relleno de unidad tiene líneas encima; una muestra de leyenda es color plano |
| rótulos OCR del dibujo | evidencia, **no** llave de selección: en esta lámina sólo 1 de 3 es legible |
| fachada / núcleo | qué proporción del borde da al exterior y qué proporción a un vacío encerrado |

Validación independiente de que las regiones de color **son** las unidades: los cocientes de área en
píxeles reproducen los cocientes de superficie publicada.

| unidad | px | cociente medido | m² publicados | cociente publicado |
|---|---|---|---|---|
| 403 | 39.011 | 1.00 | 543 | 1.00 |
| 401 | 20.008 | 0.51 | 252 | 0.46 |
| 402 | 14.873 | 0.38 | 186 | 0.34 |

Márgenes de los filtros (medidos, **no calibrados**, n = 3 dibujos):

| filtro | unidades reales | ruido rechazado |
|---|---|---|
| ≥ 2 % del área dibujada | 4,7 %–12,7 % | 0,21 % (marca de agua del plano RES) |
| ≥ 15 % del mayor candidato | 0,37–1,00 | ≤ 0,04 (flecos de antialias), 0,02 (leyenda) |
| tinta ≤ 0,35 | 0,003–0,049 | 0,72–1,00 (texto y achurado) |

## 3. Por qué NO se autoselecciona el candidato más grande

Sería cómodo: la 403 es el doble que la siguiente. Pero **`cases/002_gps_401` es la segunda en
tamaño sobre la misma lámina**. Elegir por área entregaría, sin avisar, el plano comercial de la
oficina equivocada — el falso acepto que §12 pone por encima de cualquier cobertura. Con dos
unidades no hay forma de calibrar una regla de dominancia, así que no se inventa: **más de un
candidato ⇒ un clic**.

Ese clic no es una regresión: está en el registro HITL desde E14 —
`cases/002_gps_401/overrides_assisted.json` → `op 1: confirm_target, "click dentro de la Oficina
401", estimated_human_seconds: 4`. Lo que E35 elimina es tener que abrir la herramienta técnica
para darlo.

## 4. El orden: unidad → escala → contraste

`scale = sqrt(área_px / área publicada)` sólo significa algo si el área en píxeles es la de **esta**
oficina. Con el polígono equivocado el número sale igual de bien formado y es la escala de otra
cosa. Por eso `decide(fp, unit_resolved=False)` **bloquea** la superficie publicada en vez de
bajarle la confianza: una escala equivocada no es una escala poco confiable.

## 5. Calibración de autoaceptación — `webapp/domain/calibration.py`

Dataset: `docs/E35_CALIBRATION_DATASET.json`, generado por `scripts/e35_calibrate.py` sobre los
casos reales y **las marcas humanas que ya existían en el repositorio**. Ninguna etiqueta se creó
para este ejercicio. 12 filas con etiqueta, 6 sin ella.

| componente | visibilidad | vara | n | aceptaría | falsos aceptos | aceptos incompletos | precisión | cobertura |
|---|---|---|---|---|---|---|---|---|
| perimeter | semivisible | 0.60 | 2 | 2 | 0 | 0 | **1.00** | 1.00 |
| core | semivisible | 0.60 (0.50+0.10) | 2 | 0 | 0 | 0 | — | 0.00 |
| primary_entrance | visible | 0.70 | 2 | 2 | **1** | 0 | **0.50** | 1.00 |
| columns | visible | 0.55 | 2 | 2 | 0 | 2 | 0.00 | 1.00 |
| daylight | visible | 0.45 | 2 | 2 | 0 | 2 | 0.00 | 1.00 |
| scale | invisible | — | 2 | — | — | — | — | — |

**El hallazgo:** el componente con la confianza más alta del sistema es el que menos acierta. En la
401, el motor eligió un vano del muro del núcleo con **0.90** de confianza; la persona que miró la
misma lámina con zoom ×22 marcó otro, a 64 px. Un umbral de 0.70 no evita ese acepto, porque el
error llegó con confianza alta. Un umbral no discrimina cuando el error viene confiado.

## 6. Por qué no se cambió ningún umbral

Para que un umbral quede validado hace falta, como mínimo, **verlo discriminar**: algún caso por
encima que resulte correcto y alguno por debajo que resulte incorrecto. En esta muestra ningún
componente tiene eso (`threshold_exercised = false` en todos). Mover un número para que el dataset
propio quede bonito es peor que no tener dataset. Todos quedan `THRESHOLD_UNCALIBRATED` y
`proposal()["proposed"]` es `None`.

`MIN_SAMPLE = 10` sale de la regla de tres: con 0 fallos en n pruebas, la cota superior al 95 % de
la tasa de fallo es ≈ 3/n. Con n = 2 eso es 150 % —ninguna información—; con n = 10 recién baja a
30 %. Diez es el mínimo para poder **descartar** un umbral peligroso, no para confirmarlo.

## 7. `UNCERTAINTY_BAND` — provisional

El núcleo de las dos plantas reales sale en **0.50 contra un umbral de 0.50**. Pasar o no pasar
queda a merced del redondeo. Hasta tener evidencia, un elemento tiene que superar su vara **con
margen**: `UNCERTAINTY_BAND = {"core": 0.10}`.

El margen no se eligió al gusto: las confianzas que emite el motor sobre estos artefactos están
cuantizadas de a 0.10 (0.50, 0.60, 0.70, 0.80), así que un paso de su propia cuantización es el
número menos arbitrario disponible. **Es provisional.** Su costo está medido y es real: la cobertura
del núcleo cae de 1.00 a 0.00 sobre esta muestra, y las dos plantas que un humano había confirmado
ahora piden un clic. Se acepta porque 0.50 contra 0.50 no es una medición.

## 8. La política mientras no haya calibración: por consecuencia

Sin datos para calibrar, lo único que sí se puede razonar es **si el error se vería o no en lo que
se entrega**:

| clase | componentes | política | por qué |
|---|---|---|---|
| invisible | unidad, escala | **bloquea** | el plano de la oficina de al lado, o la misma planta con 20 % más de metros, se ve perfecto y viaja a un cliente |
| semivisible | perímetro, núcleo | perímetro acepta (2/2); núcleo a revisión por la banda | un vacío mal recortado parece plausible y arrastra el área |
| visible | acceso, pilares, luz | acepta **provisional**, no validado | se ven en la lámina y en el layout, y el circuito de calificación de E33 los caza |

Mandar también lo visible a revisión no sería más conservador: sería dejar de entregar. El costo de
un falso acepto visible es una calificación MALO y una regeneración; el de uno invisible es un
entregable equivocado que nadie detecta.

## 9. `DOOR_SCALE_NOT_PRODUCT_READY`

E34 midió que los vanos que expone el motor son **accesos del perímetro** (0.48–1.91 m sobre la 403),
no puertas simples de 0.90 m, y que a 8 px/m un píxel son 12 cm. E35 no refina nada sobre esos
mismos datos ni construye un detector de puertas interiores (§20): marca la hipótesis y la deja como
señal débil de contraste.

## 10. Lo que E35 NO hace

No infiere `drawing_scope`. E16.5 se niega a deducir de la imagen si una lámina publica varias
unidades o una planta entera, y hace bien. Este módulo responde una pregunta distinta y más
modesta —**por dónde empezar a mirar**— que es exactamente lo que `overrides.seed_points` ya
respondía cuando lo contestaba una persona. La declaración de la fuente, cuando existe, manda.
