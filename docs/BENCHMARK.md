# Benchmark ETAPA 1

`python -m escalimetro bench --case cases/<id>` → `outputs/benchmark.json`.
Código: `benchmarks/metrics.py`, `benchmarks/run_benchmark.py`.

| métrica | cómo | umbral Gate E0 |
|---|---|---|
| `perimeter_iou` | IoU polígono pred vs GT (shapely) | ≥ 0.95 |
| `area_error_pct_vs_gt_px` | (área_px pred − GT)/GT | \|·\| ≤ 3 % |
| `area_error_pct_vs_gt_m2` | igual en m² — **0 por construcción si la escala viene del área publicada**; sólo informativo | — |
| `hausdorff_px/m` | Hausdorff entre contornos | informativo |
| `mean_boundary_dist_px/m` | distancia media simétrica (400 muestras) | informativo |
| `core_centroid_err_m` | distancia de centroides core[0] | ≤ 1.0 m |
| `columns` | P/R/F1 con emparejamiento greedy, tol 0.6 m | F1 ≥ 0.8 |
| `entrance_err_m` | distancia al acceso principal GT | ≤ 1.5 m |
| `segment_semantic.accuracy` | kind de cada lado GT vs lado pred más cercano | ≥ 0.8 |
| `core_iou` | IoU polígono core | informativo |
| `vertices_gt` / `vertices_pred` | cantidad de vértices | informativo |
| `human_correction_burden` | clicks por tipo (seed, confirm, accesos, pilares ±, ventanas, relabels, vértices dibujados) → `total_clicks`, `estimated_seconds` (4 s/click, supuesto) | objetivo < 60 s |

Advertencia sobre el área: como la escala se deriva de los 543 m², el error de área en m² contra
esa misma cifra es tautológico. El criterio "≤ ±3 %" del Gate se evalúa en px² contra polígono GT
independiente, o en m² sólo cuando el GT trae escala de otra fuente (cota, barra, DWG).


`bench --pred <dir>` evalúa cualquier carpeta con `floorplate.json` (pases A/B del mismo caso).

## Resultado Caso 001 real (GPS 403) — ver cases/001_gps_403/notes.md

Pase A automático: IoU 0.968 · área −2.4 % (px² vs GT) · Hausdorff 10 px · core IoU 0.87 · pilares R 0.4 ·
accesos ninguno · semántica 15/16 · 0 clicks → FAIL (accesos, pilares).
Pase B asistido (10 clicks, ~40 s estimados, localización sigue automática): PASS.

## Resultado fixture sintético (900) — mecánica, no fidelidad

IoU 0.994 · área −0.59 % · Hausdorff 1.4 px (0.05 m) · core 0 m · columnas F1 1.0 ·
acceso 3.5 px (0.13 m) · semántica 5/6 · escala recuperada 26.92 vs 27.00 px/m real (−0.3 %).
Gate: PASS. Lo que esto prueba: el pipeline no distorsiona geometría ni inventa. Lo que NO prueba:
que segmente bien un JPG real de GPS.
