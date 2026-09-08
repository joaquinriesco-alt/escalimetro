# E16.10 — Núcleo: semántica que propone, geometría que dispone, contrato que veta

## 1. La arquitectura

```
pista semántica  →  reduce el espacio de búsqueda
                 →  GEOMETRÍA DETERMINISTA sobre evidencia estructural
                 →  CONTRATO DE ACEPTACIÓN que puede vetar
```

E16.9 midió dos cosas que fijan este diseño: un modelo general de visión identifica el núcleo en dos
familias gráficas distintas (el OCR del motor no lo consigue en ninguna), y lo que entrega es un
**recuadro**, no geometría. Un recuadro que cubre el 28 % de una planta no es un núcleo; es una pista
sobre dónde mirar.

## 2. `SemanticHint` — el tipo

`src/escalimetro/semantic_hint.py`. Campos: `kind`, `approximate_region`, `confidence`,
`semantic_evidence`, `provenance`, `provider`, `model`, `schema_version`, `source_image_sha256`,
`created_at`, `raw_response_sha256`, `approximate_polygon`, `notes`.

- **`approximate_region` se llama así a propósito** y su artefacto lleva un `_warning` explícito: es
  una pista, nunca geometría aceptada.
- **Un dict cualquiera no puede hacerse pasar por pista**: `__post_init__` rechaza `kind` inválido,
  procedencia inventada, confianza fuera de vocabulario, región degenerada, evidencia vacía y sha de
  imagen mal formado.
- **Procedencias**: `VLM`, `OCR`, `MANUAL_QA`. La última es herramienta interna trazable, no parte
  del flujo del cliente.
- **`UNKNOWN` es preferible a una procedencia falsa**: las pistas de desarrollo de este ciclo
  declaran `provider=UNKNOWN`, `model=UNKNOWN` y una nota que dice de dónde salieron.

## 3. Cache y reproducibilidad

Un intérprete no determinista no puede vivir dentro de una corrida reproducible: dos ejecuciones del
mismo motor congelado darían resultados distintos y el ciclo de congelamiento dejaría de significar
algo. Por eso la pista se cachea como artefacto y el pipeline consume el **artefacto**.

```
cache_key = sha256(image_sha | provider | model | schema_version)[:16]
ruta      = <caso>/semantic/hint_<key>.json
```

Cambiar de proveedor, de modelo o de versión de contrato produce **otra** pista: no se reutiliza una
cacheada bajo condiciones distintas. Sin artefacto y sin proveedor: `SEMANTIC_HINT_UNAVAILABLE`.
Nunca un núcleo inventado por una heurística de reemplazo silenciosa.

## 4. Geometría determinista

`src/escalimetro/geometry/core_geometry.py`. Sólo señales ya justificadas por ciclos anteriores:

| Señal | Origen | Rol aquí |
|---|---|---|
| evidencia estructural (contraste local) | E16.7 | base de todo |
| **muro = trazo grueso Y lineal** | investigado en E16.8-CORE | separa muro de mobiliario y de texto |
| celdas interiores cerradas | E16.8-CORE | anclas de circulación vertical |
| conectividad y piso libre dominante | E16.6/E16.7 | medir invasión de espacio ocupable |

Procedimiento: la pista define una zona de búsqueda (ensanchada un 3 % del lado mayor, porque una
pista es aproximada por definición) → semilla = muros y anclas dentro de esa zona → enlace
morfológico a la escala a la que dos bloques de servicio se leen como un mismo núcleo → **se
incorporan enteras las componentes de muro que el cluster toca y que viven mayormente en la zona**,
lo que permite que el borde siga a la estructura y salga del recuadro → relleno del contorno externo,
se devuelve la franja del enlace, se conserva la pieza mayor.

Dos métricas existen para hacer auditable que el resultado **no es el recuadro**: `hint_iou` y
`outside_hint_frac`. Si el polígono fuera una copia de la pista, la primera sería ~1 y la segunda 0.

## 5. Contrato de aceptación

Congelado antes de mirar ningún caso de desarrollo. Cada umbral nombra una propiedad general y se
prueba por los **dos** lados con fixtures.

| Métrica | Umbral | Propiedad que representa |
|---|---|---|
| `hint_iou` | ≥ 0.15 | coherencia con lo que la semántica señaló. Bajo a propósito: la pista es un recuadro grueso y el núcleo una figura flaca; exigir más obligaría a parecerse al recuadro |
| `centroid_in_hint` | requerido | el centro del hallazgo cae donde la semántica dijo |
| `wall_fraction` | ≥ 0.12 | estructura permanente: un núcleo está CONSTRUIDO; una porción equivalente de piso abierto tiene fracción de muro cercana a cero |
| `footprint_frac` | 0.02 – 0.35 | tamaño plausible: ni un armario ni media planta |
| `solidity` | ≥ 0.55 | compacidad: un bloque, no una constelación de fragmentos |
| `components` | = 1 | conectividad |
| `open_floor_invasion` | ≤ 0.30 | no invadir el espacio ocupable: si la mayor parte del candidato es piso abierto dominante, es oficina con muros alrededor |

`vertical_circulation_anchors` se **registra como evidencia y no veta**: hay dibujos que no dejan ver
celdas cerradas, y su ausencia no prueba que no haya circulación vertical.

## 6. Familia de fixtures

`tests/fixtures/core/make_e16_10_family.py`, lámina 1200×820, planta con quiebre; ninguna coordenada,
proporción ni cantidad viene de un caso real. El fixture **declara su huella** en el JSON en vez de
pedírsela al proveedor de segmentación: lo que se prueba aquí es la geometría de núcleo, y hacerla
depender de otra capa convertiría un fallo de segmentación en un falso fallo de core.

| Fixture | Clase | Esperado |
|---|---|---|
| `A_core_compacto` | núcleo compacto, pista ajustada | acepta |
| `B_hint_demasiado_grande` | pista enorme con oficinas alrededor | acepta, y `hint_iou` debe quedar lejos de 1 |
| `C_bloques_con_circulacion` | ascensores + escalera + baños con pasillo entre medio | acepta |
| `D_watermark_y_texto` | marca de agua y anotación sobre el núcleo | acepta |
| `E_mobiliario_denso` | mobiliario denso alrededor | acepta |
| `F_hint_equivocada` | la pista apunta a piso abierto | rechaza |
| `G_fragmentada` | **misma pista correcta que A**, estructura fragmentada | **rechaza** |
| `H_sin_pista` | sin artefacto de pista | no se llega a geometría |

`G` es el fixture central de este ciclo: usa exactamente la pista del fixture bueno y aun así el
contrato veta. **Una pista correcta no garantiza un núcleo aceptado.**
