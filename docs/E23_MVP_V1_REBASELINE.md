# E23 — REBASELINE MVP V1: MOTOR DE LAYOUT SHELL-ONLY

**Veredicto: SÍ estamos en condiciones de construir V1 shell-only.** El motor de layout ya genera
tres alternativas válidas y distintas sobre un shell real. Lo que falta no es el motor: es el
camino de entrada, la parametrización del brief y el volumen de shells.

## El hecho central

Sobre GPS 403 (539.2 m² útiles), el motor produjo **A, B y C**, las tres:

```
programa completo · 40/40 puestos · 0 violaciones duras · 0 colisiones · circulación conectada
E1-T = PASS en las tres
diferencia geométrica  A vs B 50.0 %   A vs C 88.5 %   B vs C 76.9 %
circulación            A 16.7 %   B 17.1 %   C 14.5 %
desperdicio            A 11.9 %   B  9.4 %   C 14.3 %
runtime                A 114.8 s  B 83.8 s  C 101.4 s   (total 302 s)
```

Programa colocado por alternativa: 1 boardroom_12, 1 reception, 1 meeting_8, 3 meeting_4,
4 private_office, 3 phone_booth, 1 kitchenette, 1 dining, 1 lounge, + clusters y filas de puestos.

## Auditoría del pipeline A–O

| # | Etapa | Estado | Archivos | Bloquea MVP |
|---|---|---|---|---|
| A | INPUT | **PARTIAL** | `case_context.py`, `cases/*/case.json` | no |
| B | SHELL ACCEPTANCE | **MISSING** | 5 gates dispersos: `pipeline.py:120`, `semantics/shell.py:131-169`, `layout/shell_adapter.py:16-43`, `e05/preflight.py`, `e07/pipeline.py:68-110` | **SÍ** |
| C | SCALE | **PARTIAL** | `geometry/scale.py`, `area_semantics.py:85-111` | **SÍ** |
| D | GEOMETRY | **WORKING** | `pipeline.py`, `geometry/`, `segmentation/` | no |
| E | FIXED ELEMENTS | **PARTIAL** | `geometry/elements.py`, `overrides/` | no |
| F | PROGRAM / BRIEF | **PARTIAL** | `layout/model.py:123-132`, `program_templates/` (2 archivos) | **SÍ** |
| G | ZONING | **WORKING** | `layout/zoning.py` | no |
| H | SPACE GENERATION | **WORKING** | `e06/freeplace.py` (CP-SAT), `e05/bands.py`, `solver.py` | no |
| I | CIRCULATION | **PARTIAL** | `layout/circulation.py:42-94` (verificación raster real) | no |
| J | FURNITURE / CAPACITY | **WORKING** | `freeplace.py:330-338`, `render.py:49-119` | no |
| K | CONSTRAINT CHECKING | **WORKING** | `solver.py:715-762` | no |
| L | SCORING / RANKING | **WORKING** | `scoring.py` (9 objetivos), `e05/critic.py` (12 aspectos) | no |
| M | MULTI-OPTION | **WORKING** | `e07/strategies.py`, `e07/engine.py:161-190` | no |
| N | RENDERING | **WORKING** | `layout/render.py:122-232`, `e07/board.py:73-235` | no |
| O | DELIVERY / EXPORT | **PARTIAL** | SVG/PNG/JSON sí; sin PDF/XLSX; **sin verbo CLI** | **SÍ** |

RESEARCH_ONLY (fuera de V1): `cases/generalization/E17..E22`, `semantic_hint.py`, `ai/` (E08–E12),
`validation/` (E13), `geometry/core_*` de E16.10–E16.16.

## Qué funciona hoy de verdad

- **Creación de recintos:** CP-SAT sobre candidatos rectangulares anclados a la red de circulación,
  con `AddNoOverlap2D` global (`e06/freeplace.py:347-580`). Filtros duros previos: fuera del usable,
  invade zona de acceso, cruza pilar, no toca circulación (`:256-296`).
- **Puestos:** hasta el escritorio individual, con `Σ asientos == need` como restricción dura.
- **Obstáculos:** núcleo restado del usable (`shell_adapter.py:34`), pilares como obstáculos con la
  regla arquitectónica de pilar embebido en tabique a ≤0.6 m (`solver.py:736-745`).
- **Circulación:** geometría real + verificación raster con BFS geodésico desde el acceso y **una
  puerta alcanzable por recinto**; si falta, es violación dura (`circulation.py:23-59`).
- **Diversidad:** estructural, no estocástica — tres intenciones con espina, benches y pesos
  distintos (`e07/strategies.py:59-175`), y se mide (`e07/engine.py:206-219`).
- **Scoring:** 9 objetivos geométricos con pesos que vienen del template, más 12 aspectos del
  crítico con bucle crítica→reparación real (`e05/run.py:192-222`).
- **Lámina A|B|C** de 2400×1160 que incrusta las plantas validadas sin recalcular coordenadas.

## Qué no funciona hoy

1. **No hay camino de una sola orden.** El CLI empaquetado sólo tiene `run` y `bench`
   (`cli.py:22,29`). Layout se ejecuta con cuatro `python -m` distintos, y E07 exige que E06 haya
   dejado evidencia de fit primero (`e07/run.py:83`).
2. **No hay gate de aceptación de entrada.** Cinco compuertas con vocabularios distintos, ninguna
   responde "¿este plano es procesable?" antes de gastar el pipeline. RES quemó cinco corridas
   antes de descubrir que su escala era inconsumible.
3. **El brief no es parametrizable.** Existen 2 plantillas (una es variante de diagnóstico) y hay
   conteos cableados en 5 lugares: `e05/strategy.py:133` (`seats_total = 40`),
   `e07/strategies.py:68,104,142`, `e07/pipeline.py:207` (`target_headcount: 48`),
   `e07/board.py:25`, `render.py:16-21`.
4. **La escala es el cuello de botella real para shells nuevos.** Sólo hay tres métodos
   (`published_area_inferred`, `manual`, `unknown`). No hay lector de barra de escala ni de cota.
   GPS quedó como SUPUESTO; RES fue rechazado.
5. **Sin espesor de tabique.** Un recinto es un rectángulo sin muro (`model.py:69-70`), así que las
   salas quedan flotando con holguras entre sí en vez de compartir partición.
6. **Sin egreso.** Cero líneas sobre evacuación, distancia de recorrido o ancho por ocupación.
7. **Un solo shell ha pasado por el motor.** 401 = NO_FIT correcto (252 m² no dan 40 puestos);
   RES = nunca llegó.
8. **Código muerto no marcado:** `e05/cpsolver.py` (352 líneas) y los generadores de `solver.py`
   quedaron fuera del camino de producción; `generalization/visuals.py` (211 líneas) no tiene
   ningún importador.

## Revisión arquitectónica del output actual

Miré `layouts_abc_geometry.png`. Nota honesta: **B — CORREGIBLE**, no A — BUENO.

Bien: el paquete inferior derecho (recepción, comedor, kitchenette, boardroom junto al acceso) es
una decisión razonable y se repite en las tres. La ocupación de programa es 56.7 % del usable, que
es un número de mercado defendible.

Mal:
- las salas y privados **flotan como cajas sueltas**, con esquirlas entre ellas; sin espesor de
  tabique no se lee como planta construible;
- **no hay pasillo legible**: la circulación es una mancha que envuelve, no una espina;
- el grafo acceso→puertas sale en abanico desde el acceso, señal de que muchos recintos se alcanzan
  por diagonal y no por corredor;
- **la geometría del perímetro superior está mal**: el núcleo sobresale por encima de la línea de
  perímetro. Eso viene de la etapa D/E, no del motor de layout;
- 9.4 %–14.3 % de desperdicio.

Etiquetas del esquema de revisión que aplican hoy: `sin_espesor_de_tabique`,
`sin_pasillo_legible`, `espacio_desperdiciado`, `conflicto_nucleo`.

## GPS y RES como input V1

| caso | veredicto | por qué |
|---|---|---|
| **GPS 403** | `READY_WITH_SMALL_HITL` | `ready_for_layout: true`, `requires_confirmation: []` — pero sólo tras `overrides_shell.json`: 6 confirmaciones + 1 pilar añadido ≈ 7 clicks. La escala es SUPUESTO (`published_area_inferred`, 543 m² tipo `unknown`, 8.357 px/m). Sirve, y su escala hay que confirmarla. |
| **GPS 401** | `READY_WITH_SMALL_HITL` como shell | Es la misma lámina que 403 (sha256 idéntico), otra unidad. Localización `assisted` porque el OCR falló con el rótulo a contraste 140. Como shell es aceptable; el `NO_FIT` es del brief, no del input. |
| **RES** | `NOT_READY_V1` | Dos razones independientes, cada una suficiente: (1) `scale.px_per_m = null`, `SCALE_INCOMPATIBLE_REGION` — el área publicada es `useful` y la región recuperable es `full_footprint`; (2) el propio `case.json` declara "no se limpió el mobiliario" y el plano lleva rótulo "Plano y mobiliario referencial" + watermark. Está **dominado por un layout previo**. |

**RES siendo NOT_READY_V1 ya no es un fallo del producto.** Es exactamente el input que V1 declara
fuera de contrato. No se toca el motor para aceptarlo.

## Estrategia de escala V1

Métodos existentes: `scale_from_known_area` (área publicada + matriz de compatibilidad región×tipo,
20 celdas en `area_semantics.py:85-111`), `scale_manual` (px/m humano), `scale_unknown`.
No implementados: barra de escala, texto de cota.

Mecanismo mínimo sano para V1, en este orden:

1. **`SCALE_CONFIRMED`** — el usuario declara px/m o una distancia conocida entre dos puntos.
   Es el camino barato y es el que desbloquea shells nuevos.
2. **`SCALE_INFERRED_MATCHED_REGION`** — área publicada con región declarada compatible.
3. **`SCALE_UNCONFIRMED_REGION`** — se puede seguir, pero el layout hereda la incertidumbre y la
   lámina debe decirlo. Es donde está GPS hoy.
4. **`SCALE_INCOMPATIBLE_REGION`** → `SCALE_UNRESOLVED`. Se pide confirmación humana; no se infiere.

No reutilizar como verdad validada ningún px/m histórico declarado incompatible: el 44.542 px/m de
RES está explícitamente rechazado y no vuelve.

## Top 5 bloqueadores, ordenados por dependencia

```
B1  BRIEF PARAMETRIZABLE          ─┐
    dataclass + schema, quitar los  │
    5 hardcodes de conteo           ├─→ B3  UNA SOLA ORDEN
                                    │       shell + brief → 3 layouts + lámina
B2  ACEPTACIÓN DE ENTRADA + ESCALA ─┘       (CLI, sin exigir E06 previo)
    un gate, cuatro veredictos,             │
    camino de confirmación humana           ├─→ B4  ARNÉS DE LOTE + REVISIÓN
                                            │       N casos → 3N layouts + hoja de revisión
                                            │
B5  CALIDAD ARQUITECTÓNICA ─────────────────┘
    espesor de tabique, espina de pasillo,
    control de esquirlas
```

B1 y B2 son independientes entre sí y ambos alimentan B3. B5 corre en paralelo y se dirige con las
etiquetas que devuelva la revisión humana, no por intuición.

## Arquitectura mínima objetivo

```
imagen ──► NORMALIZACIÓN ──► floorplate.json ──► ACEPTACIÓN (ShellInputV1)
             (existe D)                             (B2, nuevo)
                                                        │
                                    SHELL_ACCEPTED ──────┤── INPUT_NOT_READY / INVALID_INPUT
                                                        │        SCALE_UNRESOLVED → HITL
                                                        ▼
                                brief.json ──► MOTOR (existe H·I·J·K·L·M) ──► A, B, C
                                (B1)                                            │
                                                                                ▼
                                                          RENDER + LÁMINA (existe N) ──► revisión
```

Todo lo que dice "existe" ya funciona. Lo nuevo es B1, B2 y la costura B3.

## Plan hacia 20 shells × 20 briefs × 60 layouts

- **20 briefs** salen de B1: parametrizar headcount, mix de salas y privados sobre las plantillas
  actuales. Es trabajo de datos, no de motor. Barato.
- **20 shells** es el trabajo caro. Hoy hay 1 utilizable. Requiere conseguir plantas libres
  específicamente para V1 (§13: **no** se gasta el tercer plano en esto) y pasarlas por B2.
  Presupuesto realista de HITL: ~7 clicks por shell, como GPS.
- **60 layouts** = 20 × 3 alternativas, generados por B3 y corridos por B4.
- **Revisión:** `contracts/human_review_v1.schema.json`. Cada layout recibe A_GOOD /
  B_CORRECTABLE / C_BAD + etiquetas. Sin ML. El objetivo de la fase es que la proporción de
  A_GOOD suba entre E27 y E28.

**Advertencia de costo:** el motor tarda ~100 s por alternativa (302 s las tres). 60 layouts son
~100 minutos de cómputo. No es bloqueante, pero la promesa "en segundos" del §25 hoy es "en cinco
minutos" y conviene decirlo antes de venderla.

## Roadmap E24–E28

| ciclo | qué entrega | qué se abre y se mira |
|---|---|---|
| **E24** | B1 + B2: `BriefV1` con dataclass y schema, los 5 hardcodes fuera; `ShellInputV1` implementado sobre el schema de E23 | el MISMO shell 403 con **3 briefs distintos** → 9 layouts. Si el motor sólo sabía hacer 40 puestos, aquí se ve. |
| **E25** | B3: `escalimetro layout --case X --brief Y` en una orden, sin exigir E06 | la lámina de 403 regenerada por una sola orden, byte-comparada con la histórica |
| **E26** | B2 a escala: conseguir 6–8 plantas libres, pasarlas por aceptación | hoja de contactos: cada shell con su veredicto y sus clicks |
| **E27** | B4: arnés de lote + captura de revisión | 60 layouts en contacto + primera tanda de notas A/B/C |
| **E28** | B5 dirigido por las etiquetas más frecuentes de E27 | mismo caso antes/después: ¿subió la proporción de A_GOOD? |

Cada ciclo abre una imagen y se responde: **está mejor / está peor / sirve / no sirve.**

## Riesgos

1. **Conseguir 20 plantas libres reales** es el riesgo dominante y no es técnico. Si sólo aparecen
   6, la fase igual sirve pero baja la confianza.
2. **La escala vuelve a bloquear.** Si las plantas nuevas no traen área publicada ni cota, todo
   depende de que el usuario confirme px/m. Si esa fricción resulta inaceptable, hay que reabrir
   lectura de barra de escala — y eso sí es visión.
3. **B5 puede ser más grande de lo que parece.** Espesor de tabique cambia el modelo geométrico
   (`Placement.poly`), no es cosmético.
4. **El benchmark actual protege el fracaso.** Hay baselines congelados que registran E04 FAIL
   (33/40) y E05 FAIL (34/40); si alguien mejora el motor, se ponen rojos por diseño. Hay que
   actualizarlos a conciencia, no borrarlos.
5. **Los hashes de geometría A/B/C no protegen lo que parecen.** `df6b8605…`, `5c5c2769…`,
   `e12cc722…` se comparan contra un JSON congelado, no se recomputan desde `layout.json`: seguirían
   verdes aunque el solver cambiara. Conviene arreglarlo cuando se toque el motor.

## Salud de ingeniería vs capacidad de producto

```
ENGINEERING HEALTH   1060 passed · 2 skipped · 7 xfailed · secret scan CLEAN · coupling 0
PRODUCT CAPABILITY   1 shell real llevado a 3 layouts válidos · 0 tests end-to-end imagen→layout
                     2 plantillas de brief · 0 órdenes únicas · calidad arquitectónica CORREGIBLE
```

Los dos números se reportan por separado a partir de ahora. 1.060 tests verdes no significan que el
producto genere un buen layout, y este ciclo lo deja escrito.
