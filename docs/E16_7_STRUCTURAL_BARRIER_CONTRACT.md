# E16.7 — Contrato de evidencia estructural

## 1. El supuesto que se retira

Hasta E16.6 el motor identificaba lo dibujado con una regla:

```
tinta  ==  gris < 110
```

Esa regla no describe un dibujo. Describe **una tinta concreta**. El mismo plano impreso con tóner
gastado, trazado en gris claro, o escaneado con el brillo alto, deja de tener un solo píxel bajo el
umbral y el motor deja de ver el edificio que un humano ve sin esfuerzo.

Medición sobre el segundo dibujo real (E16.6, `RUN_003`): el muro perimetral está trazado entre
gris 156 y gris 200. La regla marcaba el 4,06 % de la lámina como tinta y ninguno de esos píxeles
pertenecía al perímetro. El exterior alcanzaba el 72,3 % de la hoja y el mayor candidato encerrado
era el núcleo de ascensores.

## 2. La definición que la reemplaza

```
EVIDENCIA ESTRUCTURAL = píxel materialmente más oscuro que el fondo LOCAL del papel,
                        medido a la escala de trazo del dibujo.
```

Un trazo es un trazo por su **relación con el papel sobre el que está**, no por su valor absoluto.
Esa relación es invariante entre versiones del mismo dibujo; el valor absoluto no lo es.

Implementación (`src/escalimetro/segmentation/structural.py`): el fondo se estima cerrando la
imagen en gris con un elemento cuadrado de lado `stroke_scale_px`; la evidencia es
`fondo − imagen ≥ min_contrast`.

Dos magnitudes, ninguna de un caso:

| Parámetro | Valor | De dónde sale |
|---|---|---|
| `min_contrast` | 25 niveles (≈10 % del rango de 8 bits) | constante del MEDIO: ruido de escaneo, compresión y antialias mueven el gris unos pocos niveles; un trazo deliberado mueve decenas |
| `stroke_scale_frac` | 1 % del lado mayor, acotado a [3, 51] px | constante de ESCALA DE DIBUJO: más ancho que cualquier trazo, más angosto que cualquier recinto |

Nota deliberada sobre el black-hat: `cierre(gris) − gris` deja en cero el **interior** de una mancha
más ancha que el elemento estructurante. De un bloque macizo se marca su borde. Para este contrato
es irrelevante: un borde cerrado y un disco encierran lo mismo.

## 3. Lo que este contrato NO es

No es un detector de muros. No distingue muro de mobiliario, de texto ni de marca de agua, y no
tiene por qué. La segmentación whole-shell no pregunta *qué es cada trazo*, pregunta *qué queda
encerrado*. Un clasificador de elementos sería resolver parsing CAD para responder una pregunta
menor.

## 4. Las dos aceptaciones, separadas

```
dibujo → evidencia estructural → [ACEPTACIÓN DE BARRERA] → conectividad con el exterior
       → huella candidata → [ACEPTACIÓN DE MÁSCARA] → máscara
```

**Aceptación de barrera** (`structural.BARRIER_ACCEPTANCE`) — ¿vale la pena preguntar por
conectividad? Se juzga antes de mirar qué encierra.

| Métrica | Umbral | Por qué |
|---|---|---|
| `ink_frac` | 0.002 – 0.60 | hay dibujo y sigue siendo mayormente papel |
| `span_ratio` | ≥ 0.50 | una barrera perimetral es una estructura a escala del dibujo: su mayor componente conectada abarca media diagonal de la ROI. Mobiliario suelto y rótulos no |
| `outside_reachable_frac` | 0.02 – 0.98 | ni la barrera tapa la hoja ni el exterior lo alcanza todo |

**Aceptación de máscara** (`WholeShellProvider`) — ¿la huella resultante es una planta plausible?

| Métrica | Umbral | Por qué |
|---|---|---|
| `roi_frac` | 0.10 – 1.00 | banda plausible dentro de la región dibujada (E16.6) |
| `fill` | ≥ 0.30 | descarta marcos delgados y formas dispersas (E16.6) |
| `second_ratio` | < 0.50 | si el segundo candidato encerrado es comparable al primero, la lámina es ambigua y el proveedor no elige por el usuario (E16.7) |
| `open_ratio` | ≥ 0.10 | una huella de edificio contiene un espacio libre dominante; una retícula de ejes o una lámina de anotaciones sólo tiene celdas equivalentes (E16.7) |

Cualquiera de las dos capas puede fallar por su cuenta y lo dice con su propio motivo. Una barrera
inventada no se salva porque la máscara dé métricas bonitas, ni al revés.

`open_ratio = 0.10` se fijó contra el fixture genérico más sucio disponible
(`C_whole_shell_clutter`: 0.30, con mobiliario, ejes, textos y marca de agua) — tres veces de
margen, sin haber mirado ningún caso real.

## 5. Familia de fixtures

Generador: `tests/fixtures/segmentation/make_e16_7_family.py`. Representan **clases gráficas**, no
planos: ninguna geometría, proporción, cantidad de recintos ni marca proviene de un caso real.

| Fixture | Clase | Esperado |
|---|---|---|
| `D0_muro_oscuro_mobiliario_claro` | muro oscuro / mobiliario claro | huella |
| `D1_muro_gris_claro_mobiliario_oscuro` | muro gris claro / mobiliario oscuro | huella |
| `D2_muro_gris_claro_con_ejes` | muro claro + ejes que cruzan la planta | **no resuelta**: rechazo honesto |
| `D3_doble_linea` | muros de doble línea | huella |
| `D4_vanos_de_puerta` | perímetro con vanos | huella |
| `D5_rotulo_tocando_el_muro` | rótulo trazado sobre el muro | **no resuelta**: huella contaminada, aceptada |
| `N4_solo_mobiliario` | sólo mobiliario | rechazo |
| `N5_solo_grilla` | sólo retícula de ejes | rechazo |
| `N6_lamina_de_titulo` | lámina de texto | rechazo |
| `N7_dos_rectangulos` | dos candidatos grandes | rechazo (ambigua) |
| `N8_croquis_abierto` | croquis que no cierra | rechazo |

Los seis fixtures de E16.6 conservan su veredicto sin cambios.

## 6. Clases abiertas

Las dos son la misma falla: **estructura conectada al edificio que no es el edificio**.

`D2` — ejes de replanteo que cruzan la planta. Las celdas de la retícula se fusionan con la huella.
Aquí el contrato SÍ lo detecta (`open_ratio` 0.042 < 0.10) y rechaza: rechazo honesto en vez de
geometría equivocada.

`D5` — rótulo trazado sobre el muro perimetral. La huella lo absorbe y crece 1,2 %. Aquí el contrato
NO lo detecta: se acepta una máscara equivocada. El mismo efecto aparece en el fixture
`C_whole_shell_clutter` de E16.6 (+4,4 %), que antes no ocurría sólo porque el detector no veía los
ejes en gris claro.

Nada de esto es detección de tinta: es **selección** —cuál de las regiones encerradas es el
edificio— y por eso E16.7 no lo toca. Es la falla que queda a la vista para el próximo ciclo, y la
razón por la que la recomendación de E16.7 no es "otra heurística más".
