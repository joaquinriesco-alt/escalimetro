# E16.13.1 — CONTRATO GEOMÉTRICO MULTI-COMPONENTE (CONTRACT-ONLY)

> **UN NÚCLEO ES UNA ENTIDAD SEMÁNTICA QUE PUEDE OCUPAR VARIAS REGIONES.**
> Este ciclo mueve UNA variable: el contrato. El productor no se toca, y eso se comprueba con un
> hash del texto de sus funciones, no con una afirmación en el informe.

## 1. Por qué existe este documento y no el de E16.13

E16.13 cambió el contrato Y el productor en el mismo ciclo (quitó el cierre morfológico de enlace,
dejó de quedarse con la componente mayor, cambió el orden de etiquetado, agregó exclusión de
envolvente). Con dos variables movidas a la vez, ningún efecto observado se podía atribuir. Ese
experimento queda registrado como **INVALID_EXPERIMENT_EVIDENCE** en el commit `ee4334e`, preservado
en la rama `e16_13_invalid_backup` y **no** promovido a baseline.

## 2. La frontera, automatizada

`src/escalimetro/generalization/producer_freeze.py` extrae el texto exacto de `build_core`,
`wall_map`, `enclosed_cell_anchors`, `open_floor`, sus constantes (`SEARCH_MARGIN_FRAC`, `LINK_FRAC`,
`LINK_MIN_OVERLAP`, `ANCHOR_MAX_FRAC`) y los archivos completos `segmentation/structural.py` y
`semantic_hint.py`, y los hashea. El test
`test_el_productor_no_cambio_respecto_de_la_base_limpia` compara ese hash contra la revisión base y
falla nombrando la función que cambió. Un segundo test comprueba que el commit inválido **no** habría
pasado esa frontera.

## 3. Representación — `geometry/core_components.py`

`CoreComponentSet` = 1..N anillos + máscara de unión + áreas. `CONTRACT_VERSION = "core-geometry/2.0.0"`.

**Canonicalización geométrica vs reparación semántica.** Sólo la primera es contract-safe:

| Situación | Política | Por qué |
|---|---|---|
| orden de las piezas | canonicaliza: área desc., luego esquina superior izquierda | dos entradas iguales serializan igual |
| máscara de unión | canonicaliza | misma afirmación, otra forma |
| **región diminuta** | **se conserva, se mide (`min_component_frac`) y la juzga el contrato** | descartarla taparía un defecto aguas arriba, y no hay umbral calibrado |
| **regiones que se solapan** | **`InvalidCoreGeometry`** | dos regiones no pueden reclamar los mismos píxeles; fusionarlas inventa una geometría aceptable a partir de evidencia defectuosa |
| **región fuera de la huella** | **`InvalidCoreGeometry`** | recortarla sería reparación semántica |

No hay `NOISE_COMPONENT_MIN_FRAC`. La política declarada es
`NOISE_POLICY = "NOT_CALIBRATED_KEEP_AND_REPORT"`, y la tolerancia de solape y de salirse de la
huella es **cero por diseño**: un umbral de "cuánto se perdona" sería otra constante sin calibrar.

## 4. `.ring` — la compatibilidad no puede costar silencio

E16.13 resolvió la compatibilidad con una propiedad `ring` que devolvía calladamente la región mayor:
un lector de la era single-ring habría creído tener el núcleo completo mientras recibía una parte.
Aquí:

* `CoreComponentSet.single_ring()` devuelve el anillo **sólo si hay una región**; si hay varias lanza
  `MultiComponentCoreError`;
* `largest_ring_view()` existe y lo dice en el nombre;
* `CoreCandidate.__post_init__` **prohíbe construir** un candidato de varias regiones que además
  cargue un `ring`, así que `.ring` nunca puede contener una parte haciéndose pasar por el todo.

## 5. Contrato de aceptación

`components_max` desaparece; **ningún valor heredado cambia** (hay un test que lo compara contra la
revisión base). Lo que cambia es el ámbito:

| Métrica | Ámbito | Por qué |
|---|---|---|
| `wall_fraction`, `solidity`, `open_floor_invasion`, `scope_overlap` | **PER-COMPONENT** | cada región tiene que ser un bloque construido y estar donde la semántica señaló |
| `footprint_frac`, `hint_iou`, `centroid_in_hint` | **UNION** | describen el conjunto |
| `components` | **OBSOLETA como veto** | es propiedad del dibujo, no del núcleo |

Medido sobre fixtures declarados: un candidato con una región ocupable da `open_floor_invasion`
0,109 sobre la unión —pasaría— y 0,549 en la región culpable —veta—. Tres regiones legítimas dan
solidez 0,477 de unión contra 0,99 por región: la solidez de unión mide el reparto de la planta.

Una región que no cumple **veta el candidato completo**: recortar en silencio lo que no se puede
justificar es la clase de error que E16.11 detectó.

## 6. Identidad semántica en la salida

`Core` gana un bloque estructurado `CoreGroup(semantic_core_id, component_index, component_count,
contract_version, candidate_status)`, opcional y `None` en registros anteriores. Con él, un consumidor
distingue **un núcleo de tres regiones** de **tres núcleos**; con una nota de texto (`"core 2/3"`, lo
que hacía el intento inválido) no podía.

## 7. `fabricated_fraction` — experimental, fuera del contrato

Vive en `geometry/core_fabrication.py`, no lo importa `core_geometry.py`, no está en
`CORE_ACCEPTANCE` y no participa de ningún veto: `bridge_validation = NOT_CALIBRATED`. Mide bien
—0,1464 para un puente por piso abierto contra 0,0005 para el candidato honesto del mismo dibujo—
pero depende de excluir la envolvente del piso, y esa regla pertenece a la capa de evidencia, que en
este ciclo está congelada.
