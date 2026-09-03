# Floorplate JSON — schema 0.2.0 (lee 0.1.1)

Fuente de verdad: `src/escalimetro/schemas/floorplate.py` (dataclasses + `json_schema()`).

## Coordenadas

- Se serializa **todo en px de `source_image`**, origen arriba-izquierda, y hacia abajo.
- Metros se derivan: `Floorplate.to_m(p)` = `((x - x_min)/px_per_m, (y_max - y)/px_per_m)`,
  origen abajo-izquierda del bbox del perímetro, y hacia arriba. Un solo sistema almacenado
  evita inconsistencias cuando se corrige la escala.

## Meta (en cada elemento)

| campo | valores |
|---|---|
| `confidence` | 0..1 |
| `provenance` | `manual` · `known_area` · `cv_segmentation` · `ml_segmentation` · `vlm` · `cv_heuristic` · `derived` · `unknown` — **no existe `generated`** |
| `status` | `confirmed` · `inferred` · `needs_confirmation` · `unknown` |
| `notes` | parámetros/razón, texto libre |

## Estructura

```
schema_version   "0.1.0"
case_id, unit_label
source_image     {path, width_px, height_px, sha256, dpi}
coordinate_system{units, origin, y_axis, note}
scale            {px_per_m|null, method: known_area|scale_bar|dimension_text|manual|unknown, reference_area_m2, meta}
perimeter        {ring[], raw_ring[], meta}
holes[]          {ring, meta}              patios/vacíos dentro de la unidad
core[]           {ring, kind, meta}        núcleo (puede estar fuera del perímetro de la unidad)
columns[]        {center, size_px, shape, meta}
entrances[]      {point (sobre el ring), width_px, kind, meta}
windows[]        {start, end, meta}
facade_segments[]{index, start, end, kind: facade|party_wall|core_wall|corridor|unknown, meta}
fixed_elements[] {ring, kind: wc|kitchen|shaft|stairs|other, label, meta}
area_m2, area_px2, area_meta
published_area_m2, published_area_kind   (0.1.1) cifra comercial tal cual; useful|rentable|total|unknown
target_localization                      (0.1.1) automatic|assisted|manual|unknown
unknowns[]       {element, reason}
(0.2.0) entrance_candidates[], primary_entrance, exterior_facade_segments[], daylight_segments[],
        column_candidates[], north_arrow, shell_readiness — ver docs/SHELL.md
pipeline         {version, vision, vision_model, segmentation, simplify_eps_frac, snap_orthogonal, overrides}
```

## Versionado

Cambio incompatible → bump minor y migrador en `schemas/migrations.py` (no existe aún; no hace
falta hasta la 0.2). `from_dict` rechaza versiones distintas.
