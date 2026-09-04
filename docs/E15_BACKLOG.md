# BACKLOG E15 — hallazgos de E14

E14 dio `ASSISTED_GENERALIZATION_PASS`. No es un FAIL, así que este backlog **no es obligatorio** por
§36 del protocolo; se escribe igual porque los defectos existen y anotarlos ahora es más barato que
redescubrirlos en el tercer shell.

**Ninguno de estos ítems se corrigió en E14.** El motor entró congelado y salió congelado; tocarlos
habría invalidado el experimento.

Cada ítem lleva evidencia, hipótesis de causa raíz, etapa afectada y experimento propuesto. **Ninguno
lleva implementación**: decidir cómo arreglarlo es trabajo de E15, no de E14.

---

## P0 — impide procesar otro shell

### P0-1 · El veredicto de fit y la lámina de E07 están escritos a mano para la Oficina 403

**Evidencia.** `src/escalimetro/layout/e07/run.py:34-35` fija `"unit": "Oficina 403 (GPS Property)"` y
`"published_area_m2": 543.0` como constantes del módulo. `src/escalimetro/layout/e07/board.py:82,83,115`
rotula la lámina con `"OFICINA 403 · GPS PROPERTY"`, `"543 m² publicados"` y `("Publicada", "543 m²")`.

**Hipótesis de causa raíz.** E07 se escribió cuando existía un solo caso y el veredicto de fit se
trató como texto curado, no como dato derivado del floorplate. Nadie lo parametrizó porque nunca hubo
un segundo caso que lo obligara.

**Etapa afectada.** PRESENTATION, y por arrastre STRATEGIES: las tres alternativas se generan bien,
pero el artefacto que las comunica miente sobre qué inmueble son.

**Por qué no se manifestó en E14.** El segundo shell dio `TECHNICAL_NO_FIT`, así que E07 nunca se
ejecutó. Si hubiera dado FIT, la lámina habría dicho "Oficina 403 · 543 m² publicados" sobre la
geometría de la 401. Eso es un hallazgo del gate, no un accidente afortunado.

**Experimento propuesto.** Ejecutar E07 sobre un shell que sí dé FIT y comprobar cuántos campos de la
lámina y del veredicto salen incorrectos. Recién con esa lista decidir qué se parametriza y qué se
deriva del floorplate.

---

## P1 — degradan la calidad pero permiten resultado

### P1-1 · La localización automática falla cuando el rótulo tiene poco contraste

**Evidencia.** Con la Oficina 403 el OCR lee `403` dos veces —en el plano y en la leyenda— y emite el
hint `unit_region`. Con la 401 y la 402 lee el número **sólo en la leyenda**: sin token dentro de una
región coloreada no hay `unit_region` y el pipeline aborta con `RuntimeError` antes de segmentar.
Contraste medido del rótulo dentro del plano (p95 − p5 del gris): 403 = 206, 402 = 162, **401 = 140**.

**No es la causa.** El filtro de brillo de `_ring_color` (`gray > 120`) no interviene: el relleno de
401 tiene gris 173. El fallo es anterior, en la lectura del texto.

**Hipótesis de causa raíz.** Tesseract con `--psm 11` sobre una imagen de 72 dpi reescalada ×3 no
resuelve texto de bajo contraste partido en dos líneas. Es hipótesis: no se aisló cada factor.

**Etapa afectada.** NORMALIZATION / target localization.

**Experimento propuesto.** Correr el localizador con la imagen preprocesada de tres maneras
independientes —ecualización local, umbral adaptativo, y `--psm 6` sobre la banda del plano— y medir
cuántas de las tres unidades recupera cada una. Es un experimento de medición, no un parche: si
ninguna recupera la 401, el problema es de resolución del input y la respuesta correcta es el flujo
asistido, no una heurística nueva.

### P1-2 · Un mapa de unidades y posiciones de píxel de esta lámina, incrustado en el motor

**Evidencia.** `src/escalimetro/layout/e06/run.py:210-211`:
`{"401": 252, "402": 186, "403": 543}` y `{"401": (470,200), "402": (330,175), "403": (400,340)}`.

**Hipótesis de causa raíz.** El subcomando `report` de E06 necesitaba dibujar las tres unidades del
aviso y se resolvió con literales en lugar de leerlos del caso.

**Etapa afectada.** PRESENTATION. No se ejecutó en E14 (sólo se usó `sweep`).

**Experimento propuesto.** Ejecutar `e06 report` sobre el caso 002 y registrar qué produce. Es la vía
más rápida para saber si el mapa se usa como dato o sólo como decoración.

### P1-3 · `make_scenario` tiene el área de 403 como valor por defecto

**Evidencia.** `src/escalimetro/layout/e06/scale.py:50`:
`def make_scenario(fp, factor, published_m2: float = 543.0)`.

**Hipótesis de causa raíz.** Firma escrita con un solo caso en mente. En E14 no mordió porque el
sweep pasa el área explícitamente.

**Etapa afectada.** SCALE.

**Experimento propuesto.** Buscar todos los llamadores y comprobar cuáles omiten el argumento. Si son
cero, el riesgo es teórico y baja a P2.

---

## P2 — presentación y performance

### P2-1 · Nombre de archivo con el caso incrustado

**Evidencia.** `src/escalimetro/layout/run.py:94` lee `outputs/shell_semantics_403.png`. En el caso
002 OpenCV avisó (`can't open/read file`) y el guard `if orig is not None and shell_png is not None`
evitó el crash: el tríptico simplemente no se generó. **Degrada en silencio**, que es peor que fallar.

**Etapa afectada.** PRESENTATION.

**Experimento propuesto.** Ninguno hace falta: está observado. La decisión es de diseño — derivar el
nombre del `unit_label` o del `case_id`.

### P2-2 · Identificadores de layout con "403" incrustado

**Evidencia.** `src/escalimetro/layout/e07/engine.py:165,188`:
`lay.layout_id = f"OFFICE_403_{spec.alt}_{spec.name}"`.

**Etapa afectada.** PRESENTATION. Cosmético, pero contamina los artefactos de cualquier otro caso.

### P2-3 · Títulos y nombre de reporte de E06 con "403"

**Evidencia.** `src/escalimetro/layout/e06/run.py:190,229,231,281` — `"OFFICE 403 · assisted"`,
`fit_robustness_403.png`, `set_title("Oficina 403 · ...")`.

### P2-4 · La ventana de búsqueda de la muestra de leyenda está dimensionada sobre esta maquetación

**Evidencia.** `src/escalimetro/vision/ocr_localizer.py:52` —
`X0, X1 = max(0, x0 - 12*th), max(0, x0 - 2)`, con el comentario explicando que la muestra de
"Oficinas 403" queda lejos del número.

**Observado en E14.** Funcionó: encontró las tres muestras de leyenda. Pero es una constante ajustada
a un dibujo concreto y sólo un tercer shell, de otra fuente, dirá si sobrevive.

**Etapa afectada.** NORMALIZATION.

**Experimento propuesto.** Medir la distancia real muestra-número en al menos tres avisos de
corredores distintos antes de tocar el valor.

### P2-5 · El solver tarda más en el shell pequeño que en el grande

**Evidencia.** 166 s en 252 m² (Oficina 401) contra 84–115 s por alternativa en 543 m² (Oficina 403).

**Hipótesis de causa raíz.** La búsqueda no escala con el área sino con la dificultad: al no alcanzar
ningún candidato válido, el motor agotó los 12 sin poda temprana. Coincide con el modo de fallo F10
del premortem.

**Etapa afectada.** PERFORMANCE.

**Experimento propuesto.** Instrumentar el tiempo por candidato y comprobar si existe un punto a
partir del cual la completitud de programa ya es inalcanzable. **No optimizar todavía**: primero
medir si el caso NO_FIT es frecuente o excepcional.

---

## Lo que este backlog NO incluye

No incluye "hacer que la 401 quepa". El programa de 48 personas no cabe en 252 m² y esa es la
respuesta correcta, no un defecto que arreglar. Adaptar el programa al inmueble es una capacidad de
producto que puede valer la pena, pero es una decisión de qué construir, no un arreglo de un bug.
