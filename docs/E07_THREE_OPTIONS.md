# E07 — Three-option automated space planning

    MISMO SHELL + MISMO PROGRAMA + MISMAS RESTRICCIONES  →  A EFICIENTE / B BALANCEADO / C COLABORATIVO

Paquete `src/escalimetro/layout/e07/`. E04, E05 y E06 congelados (tests de baseline). El motor geométrico es
el de E06 (`freeplace.py`): E07 no inventa geometría nueva, decide **intención de space planning**.

## Por qué las tres son distintas

No son tres semillas. La diferencia entra por tres capas encadenadas, en este orden:

1. **SpatialGraph** (`graph.py`) — qué debe estar cerca de qué, antes de que exista una coordenada. Nodos de
   programa (recintos + barrios de trabajo + anclas del shell) y aristas tipadas: `must_connect`,
   `prefer_near`, `prefer_far`, `client_route`, `staff_route`, `privacy_gradient`, `daylight_preference`,
   `shared_support`, `acoustic_separation`, `entrance_priority`.
2. **spine_strategy** — qué patrón de circulación de E05 instancia la espina (A `A_PERIMETER_WORK`,
   B `B_CLIENT_FRONT`, C `C_DUAL_NEIGHBORHOOD`).
3. **weights + solver_extra** (`strategies.py`) — cómo el grafo se convierte en restricciones duras
   adicionales (`hard_adjacent_pairs`, `module_max_path`, `max_facade_closed_rooms`, `min/max_bench_blocks`)
   y en pesos del objetivo.

| | A EFICIENTE | B BALANCEADO | C COLABORATIVO |
|---|---|---|---|
| barrios de trabajo | 2 (24+16) | 3 (16+14+10) | 4 (12+10+10+8) |
| bench_cfgs | 6,5,4 | 6,4,3 | 4,3,2 |
| peso dominante | luz 0.24 · circulación 0.18 | luz 0.20 · acceso/salas/adyacencia 0.14 | adyacencia 0.20 · luz 0.18 |
| restricción propia | ramales caros (×3.0) | directorio ≤ 14 m del acceso | ≥ 8 bloques, ramales baratos (×0.4) |

Principios comunes a las tres (§10 del brief, no negociables): recepción en el acceso, luz natural
priorizada para puestos, circulación legible y no residual, kitchenette+comedor adyacentes (restricción
dura), gradiente de privacidad público → semipúblico → trabajo → soporte.

## Motor y rendimiento (`engine.py`)

Por alternativa: geometría de red y candidatos (reutilizada entre alternativas cuando coinciden espina y
bench_cfgs) → warm start de capacidad (`seats_mode="max"`) → fase de factibilidad sin objetivo con `AddHint`
→ optimización con hint y early stop → validación determinista de **ambos** candidatos → se elige el mejor
válido. `Profile` registra cada etapa. KPI: < 120 s por alternativa.

Técnicas que bajaron 291 s (E06) a < 120 s: poda de candidatos dominados (`freeplace.prune`), literales por
tipo de módulo en vez de por instancia (elimina la simetría entre recintos idénticos), warm starts, reuso de
geometría, early stop, reintento adaptativo cuando la factibilidad devuelve UNKNOWN.

No se busca óptimo matemático global. Se busca un buen plan válido, y la validez es la que decide.

## Gates separados (`pipeline.py`)

| gate | qué decide | quién |
|---|---|---|
| **E1-T** | programa completo, 40/40, 0 violaciones, 0 colisiones, circulación conectada | software |
| **E1-A** | crítico ≥ 0.65, sin aspecto crítico, QA ≤ 5 min, ≥ 90 % de geometría preservada | software, `PASS_PROVISIONAL` |
| **E1-C** | ¿un broker enviaría esto a un cliente? | humano externo; el software sólo llega a `READY_FOR_BROKER_REVIEW` |

`SHELL_DOMINATED_ASPECTS = {"residual_spaces"}`: toda solución válida sobre la 403 deja bolsillos
estructurales (E06 68 m²; E07 62–86 m²). Se reporta siempre y no invalida: el gate mide decisiones de
diseño, no limitaciones de la cáscara.

`broker_showable` del crítico interno **no** se usa para E1-C.

## QA interno (no es una función del producto)

`InternalQABurden` mide la revisión interna: `operation_count`, `geometry_changed_pct`,
`estimated_minutes`, `reason_for_correction`. Los minutos son **estimados**; sin humano real cronometrado no
existe `measured_minutes`. Si una alternativa necesitara rediseño, E1-A es FAIL. El cliente nunca ve esta
capa, y el producto no expone PIN / LOCK / MOVE / SWAP / ROTATE: quien quiere mover un recinto necesita un
arquitecto, no un editor.

## Escala

E07 **no** repite el barrido de E06. Escala nominal (543 m² publicados, confianza LOW), contrato
`ScaleCalibrationInput` intacto. Toda salida declara `FIT: ROBUST_WITHIN_ASSUMED_SCALE_RANGE` y
`SCALE: UNCONFIRMED`.

## Presentación (`board.py`, `visuals.py`)

`ESCALIMETRO_PRESENTATION_STANDARD_01`: una lámina, tres columnas, barra de programa y leyenda. Las plantas
se **incrustan** — cada columna contiene el SVG que produce el renderer sobre el Layout validado
(`chrome=False`); ninguna coordenada se recalcula. Técnico y comercial comparten exactamente la misma
transformación.

`presentation_handoff.json` (uno por alternativa) lleva `geometry_locked = true`: una capa de presentación
puede cambiar color, trazo, tipografía, etiquetas, iconografía, composición y narrativa; no puede mover ni
redibujar muros, shell, recintos, puestos, mobiliario, puertas, pilares ni circulación, y tiene prohibido
usar image generation para redibujar la planta.

## Ejecutar

    PYTHONPATH=src python -m escalimetro.layout.e07.run --case cases/001_gps_403

Salidas en `cases/001_gps_403/layouts/E07/`.
