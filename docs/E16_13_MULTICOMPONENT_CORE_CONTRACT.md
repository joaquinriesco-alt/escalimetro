# E16.13 — CONTRATO GEOMÉTRICO MULTI-COMPONENTE DEL NÚCLEO

> **UN NÚCLEO ES UNA ENTIDAD SEMÁNTICA QUE PUEDE OCUPAR VARIAS REGIONES.**
> No se fabrican puentes para satisfacer un tipo de dato, ni se rechazan piezas correctas por estar
> separadas.

## 1. La afirmación que quedó falsada

E16.10 codificó "un núcleo correcto es una sola componente conectada" en dos lugares a la vez:

* el **productor** unía piezas con un cierre morfológico de radio fijo (2,5 % del lado mayor) y luego
  se quedaba con la componente mayor;
* el **contrato** exigía `components_max = 1`.

E16.12 midió el costo. Un conjunto de servicio distribuido —bloques separados por circulación, que es
como se construyen los edificios— devuelve varias piezas correctas y el contrato las rechazaba; la
única forma de cumplir la regla era engordar la geometría hasta cruzar espacio abierto. Sobre el
candidato histórico del caso de desarrollo, el **68 %** de sus píxeles no era estructura ni estaba
encerrado por estructura.

El reemplazo **no** es `components <= N`. La cantidad de piezas es una propiedad del dibujo, no del
objeto. El contrato pregunta propiedades.

## 2. Tres conceptos que no son el mismo

| Concepto | Qué es |
|---|---|
| **CORE SEMANTIC ENTITY** | el conjunto de infraestructura permanente que constituye el núcleo |
| **CORE GEOMETRIC COMPONENT** | una región espacial individual de ese conjunto |
| **CORE CANDIDATE** | las 1..N componentes que el productor propone para esa entidad |

N regiones de un núcleo **no** son N núcleos. El motor no hace esa segunda afirmación.

## 3. Representación canónica — `geometry/core_components.py`

`CoreComponentSet` = lista de anillos + máscara de unión + cuentas de normalización.
`CONTRACT_VERSION = "core-geometry/2.0.0"` (1.x era single-ring: un lector antiguo puede detectarlo).

Política declarada y determinista para las tres formas sucias:

| Entrada | Política | Registro |
|---|---|---|
| pieza bajo el piso de ruido (`NOISE_COMPONENT_MIN_FRAC = 0.002` de la huella) | se descarta en la normalización | `normalized_away` |
| piezas que se solapan | se fusionan; nunca geometría doble | `merged_overlaps` |
| pieza fuera de la huella | **no se normaliza**: `InvalidCoreGeometry` | excepción |

Orden canónico: área descendente y, a igualdad, esquina superior izquierda — dos candidatos iguales
serializan igual. `ring` sobrevive como **vista de compatibilidad**: la pieza mayor, explícitamente
parcial.

Este módulo **no** agrupa piezas por cercanía. Dos piezas no pertenecen al mismo núcleo por estar
juntas; la relación la establece la evidencia semántica aguas arriba, y aquí sólo se exige que cada
pieza tenga relación con el alcance que esa evidencia señaló.

## 4. Productor: la evidencia decide la conectividad

El cierre morfológico de radio fijo desaparece (`LINK_FRAC` queda nombrado como obsoleto para que
nadie lo reintroduzca). Lo único que se cierra ahora es una holgura **menor que el ancho de trazo**:
un hueco de dos píxeles en una línea de nueve es un artefacto del ráster, no una separación
arquitectónica. Dos exclusiones explícitas:

* una pieza que no vive mayormente en la zona de búsqueda no entra (un muro de fachada la roza);
* la **envolvente del piso** no entra: el perímetro ya está representado por `Perimeter`, y rellenar
  lo que encierra convertiría la planta completa en núcleo.

## 5. Migración de cada métrica (§13)

| Métrica | Ámbito | Por qué |
|---|---|---|
| `wall_fraction` | **PER-COMPONENT** | cada pieza tiene que estar construida; el promedio deja que una pieza maciza tape una vacía |
| `solidity` | **PER-COMPONENT** | la envolvente convexa de la unión atraviesa la circulación: mide el reparto de la planta, no el objeto. Medido: tres bloques legítimos dan 0,650 sobre la unión y 0,996 por pieza |
| `open_floor_invasion` | **PER-COMPONENT** | medido: un candidato con una pieza ocupable da 0,109 sobre la unión —pasa— y 0,549 en la pieza culpable —veta— |
| `scope_overlap` | **PER-COMPONENT** | relación de cada pieza con el alcance semántico; reemplaza cualquier idea de pertenencia por cercanía |
| `footprint_frac` | **UNION** | el tamaño del núcleo es el del conjunto; una pieza chica es legítima |
| `hint_iou`, `centroid_in_hint` | **UNION** | la pista describe el conjunto |
| `components` | **OBSOLETA como veto** | se mide y se reporta; no decide |
| `fabricated_fraction` | **MEDIDA, NO VETA** | ver §6 |

Una pieza que no cumple las invariantes **veta el candidato completo**: el motor no recorta en
silencio lo que no puede justificar. Descartarla calladamente sería la misma clase de error que
E16.11 detectó cuando el candidato dejaba fuera un bloque sin decirlo.

## 6. Fabricación: se mide y todavía no veta

`fabricated_fraction` = fracción del candidato que no es estructura ni está encerrada **por una misma
pieza** de estructura. El enclaustramiento se evalúa pieza por pieza y sin la envolvente: con
enclaustramiento conjunto, el muro perimetral respalda cualquier cosa dentro del edificio y la
métrica vale cero siempre (medido).

Sobre el mismo dibujo y la misma pista: candidato que cruza el piso abierto para tener una sola
pieza → **0,146**; las dos piezas honestas → **0,0005**. Una pieza sobre papel en blanco → **1,000**.

`bridge_validation = NOT_CALIBRATED`. El banco disponible —diez fixtures sintéticos— no basta para
separar un puente fabricado de un recinto interior grande sin inventar un número, y poner 5 % sería
exactamente el tipo de constante que este proyecto persigue. La métrica informa; no decide.

## 7. Salida

`cores_from_candidate()` convierte UNA entidad en N entradas `Core` del esquema, cada una con
procedencia y su lugar en el conjunto (`core 2/3`), la versión del contrato, su `fabricated_fraction`
y el estado de la validación de puente. El esquema ya era `List[Core]` y el solver ya hacía
`unary_union`: aguas abajo no cambia nada.

## 8. Regresión declarada

Dos clases de la familia de E16.10 dejaron de aceptarse: `B_hint_demasiado_grande` y
`D_watermark_y_texto`. **No se movió ningún umbral para recuperarlas.** El experimento controlado
está en el informe del ciclo: en D, el mismo dibujo sin la marca de agua da solidez por pieza 0,736 y
0,995 y se acepta; con la marca de agua, 0,526 y 0,533. La causa no es la partición en componentes:
es que `solidity_min = 0.55` se calibró sobre geometría **cerrada morfológicamente**, que convexifica,
y ahora mide la forma real de cada pieza. Qué tinta llega a ser una pieza lo decide el criterio de
muro de E16.7/E16.8-CORE, cuyo piso de grosor `max(3, k//4)` vale 3 px —el mínimo— en láminas de
hasta ~1800 px de lado: a esa escala "grueso" no discrimina nada.
