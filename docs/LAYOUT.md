# Motor de layout (E04)

Escalímetro termina donde empieza el proyecto de arquitectura: PRE-DESIGN / FEASIBILITY / TEST-FIT.
El motor no sabe que resuelve una oficina. Resuelve:

    SHELL + PROGRAM + MODULES + CONSTRAINTS + OBJECTIVES + SCORING

`OFFICE` es sólo el primer *program template* (`program_templates/office_balanced_48.json`) con su
biblioteca de módulos (`program_templates/modules_office.json`). Nada del brief vive en el código.

## Pipeline

1. `shell_adapter.shell_from_floorplate` — Floorplate 0.2.0 (px) → `ShellM` (m). Exige
   `shell_readiness.ready_for_layout = true` y `primary_entrance` confirmado. Pilares: cajas cuadradas de
   `size_px / px_per_m` acotadas a [0.5, 0.8] m (supuesto registrado en `ShellM.source`). Escala
   `published_area_inferred` → `scale_confidence = LOW`.
2. `grid.Grid` — raster 0.4 m: interior, obstáculos (pilares), distancia geodésica al acceso, distancia y
   prioridad de luz natural.
3. `zoning.compute_zones` — PUBLIC (≤ 7 m geodésicos del acceso), WORK (≤ 6 m de fachada con luz),
   SUPPORT (interior, > 10 m del acceso), SEMI_PUBLIC (resto). Son zonas *candidatas*: el scoring premia
   la coincidencia módulo–zona (`ZONE_OF_MODULE`), no la impone.
4. `strips` — descomposición del usable en bahías rectangulares (líneas de vértice + rectángulo máximo
   voraz), cada bahía se corta en 1–3 segmentos y a cada segmento se le asigna una *sección* = secuencia
   de franjas `desks | corridor | rooms` desde el lado de referencia (fachada o acceso). Toda sección
   contiene un pasillo y todo recinto/puesto toca un pasillo: la circulación no es residual.
5. `solver.Solver.build_strips` — búsqueda local (restarts × iteraciones) sobre la configuración de bahías
   (eje, cortes, secciones) con fitness = 0.4·recintos + 0.3·puestos + 0.1·acceso + 0.1·conectividad +
   0.1·pasillos libres de pilares. `plan_strips` asigna recintos por clase de profundidad (ambas
   orientaciones) y rellena puestos (bench 2×3, 2×2, filas de 3). `junction_connectors` une bahías.
6. `Solver.validate` — restricciones duras: dentro del usable, fuera del núcleo, sin intersectar pilares
   (excepción registrada: pilar cuyo centro cae a ≤ 0.6 m del borde de un recinto cerrado = pilar en línea
   de tabique, `meta.embedded_columns`), sin colisiones, zona libre del acceso, programa completo y conteos
   exactos, circulación conectada (erosión 1.2 m + BFS desde el acceso) y puerta para cada recinto.
7. `scoring.score` — nueve objetivos ∈ [0,1] con pesos del template (`objectives_weights`).
8. `render.render_layout_svg` — planta técnica y planta comercial desde la MISMA lista de `Placement`.

## Estrategia elegida y por qué

Búsqueda local sobre franjas (strip planning) y no CP-SAT: el problema real no es el packing exacto sino
la topología (pasillos, puertas, bahías con fachada). Las franjas codifican la topología de oficina
convencional (puestos a la fachada, pasillo, recintos al fondo), lo que hace verificable cada candidato y
hace legible el fallo cuando no hay solución. CP-SAT sería el siguiente paso si la exploración de
secciones demuestra que la capacidad existe pero la heurística no la encuentra.

## Cómo correr

    PYTHONPATH=src python3 -m escalimetro.layout.run --case cases/001_gps_403 --candidates 8 --seed 1

Salidas en `cases/<id>/layouts/<layout_id>/`: `layout.json`, `metrics.json`, `layout_001_geometry.png/svg`,
`layout_001_commercial.png/svg`, `geometry_vs_commercial.png`, `original_shell_layout.png`.

## Regla de fallo

Si ningún candidato satisface todas las restricciones duras, `status = "FAIL: sin candidato válido"` y se
devuelve el mejor parcial (menos faltas de programa, luego menos violaciones) marcado como inválido, con
sus violaciones listadas. El programa nunca se reduce en silencio; una variante reducida es otro template
con otro `template_id`.

Toda salida: **Dimensiones sujetas a confirmación de escala.**
