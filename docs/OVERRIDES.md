# Human-in-the-loop — `cases/<id>/overrides.json`

Flujo de 5 minutos, sin editor:

1. `python -m escalimetro run --case cases/001_gps_403` con al menos `seed_points`.
   Si no hay seeds ni VLM, el pipeline se detiene y lo dice.
2. Abrir `outputs/original_grid.png` (grilla cada 100 px con coordenadas) y `outputs/overlay.png`.
3. Escribir coordenadas en `overrides.json`. Volver a correr. Repetir.

Todas las claves son opcionales. Coordenadas en px de `original.jpg`.

```json
{
  "seed_points": [[x, y]],
  "segmentation_params": {"tol": 12, "gap_px": 30, "wall_thresh": 110},
  "perimeter": {"ring": [[x, y], ...]},
  "known_area": {"m2": 543, "kind": "useful"},
  "scale": {"px_per_m": 12.3},
  "core": [{"ring": [[x, y], ...], "kind": "core"}],
  "entrances": [{"point": [x, y], "kind": "main", "width_px": 20}],
  "columns": {"replace": false, "add": [{"center": [x, y], "size_px": 10}], "remove_near": [[x, y]]},
  "windows": [{"start": [x, y], "end": [x, y]}],
  "facade_kinds": {"3": "facade", "7": "party_wall"},
  "fixed_elements": [{"ring": [[x, y], ...], "kind": "wc", "label": "baño"}],
  "vision_hints": [{"kind": "unit_region", "confidence": 1, "point": [x, y]}],
  "confirm": ["perimeter", "core", "columns", "facade", "entrance", "daylight", "scale_assumption"],
  "entrance_choice": {"index": 1},
  "daylight_confirm": {"3": "likely_glazing", "7": "confirmed_glazing"},
  "north_angle_deg": 12.0,
  "facade_params": {"band_px": 30, "ray_max_px": 120},
  "bbox": [x0, y0, x1, y1]
}
```

`confirm` acepta un elemento inferido sin redibujarlo (status → confirmed, provenance intacta,
nota "confirmado por humano"). Cuenta 1 click en el HUMAN CORRECTION BURDEN.

Localización: si `seed_points`/`bbox` vienen del humano → `target_localization = assisted`;
si vienen del OCR/VLM → `automatic`; `perimeter` → `manual`. Los demás overrides (core, accesos,
pilares, confirm) NO cambian la localización.

Reglas:

- Un override siempre queda `provenance=manual, confidence=1, status=confirmed`.
- `perimeter` reemplaza la segmentación completa (provider `manual`). Úsalo sólo si el flood fill
  falla; si funciona, corrige con `segmentation_params` para que el resultado siga siendo
  reproducible por CV.
- `entrances[].point` se proyecta al perímetro automáticamente.
- `facade_kinds` usa el `index` de `facade_segments` en el `floorplate.json` de la corrida anterior.
  Si cambia el perímetro, cambian los índices: revisar.
- `columns.remove_near` elimina candidatos CV a < 15 px del punto.

Ground truth (`ground_truth/floorplate_gt.json`) usa el mismo schema; se puede generar copiando
`outputs/floorplate.json` y corrigiendo a mano — pero anotado con criterio independiente del
pipeline, o el benchmark se mide a sí mismo.
