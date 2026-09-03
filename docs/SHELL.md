# Shell semántico (E03) — schema 0.2.0

Un `Floorplate` 0.1.1 es geometría. Un shell 0.2.0 agrega lo que un motor de layout necesita saber
para no equivocarse: por dónde entra la gente, dónde hay luz, qué no se puede mover.

## Campos nuevos (todos opcionales; 0.1.1 sigue cargando)

```
entrance_candidates[]    {point, kind: primary|secondary|unknown, confidence, evidence[], width_px, segment_index, status, provenance}
primary_entrance         el candidato elegido (automático: inferred / needs_confirmation; humano: confirmed) | null
exterior_facade_segments índices de facade_segments con kind = facade
daylight_segments[]      {index, start, end, classification, confidence, daylight_priority 0..1, evidence[], status, provenance}
column_candidates[]      {center, size_px, confidence, evidence[], status, provenance}
north_arrow              {detected, angle_deg, meta} — sólo por declaración humana; nunca cálculo solar
shell_readiness          {geometry_ready, entrance_ready, columns_ready, daylight_ready, requires_confirmation[], ready_for_layout, notes}
```

## Accesos — `semantics/entrance.py`

Evidencias y pesos: topología (lado core_wall/corridor) 0.15 · interrupción del muro 0.5–2.5 m 0.30 ·
símbolo de puerta junto al hueco 0.25 · intrusión de pintura en el hueco 0.15 · ancho típico 0.7–1.5 m
0.10 · eje de circulación 0.05. `primary` = mejor candidato con conf ≥ 0.5; si otro está a < 0.1,
empate → `needs_confirmation` y el humano elige (`confirm: ["entrance"]` o `entrance_choice`).

## Luz natural — `semantics/daylight.py`

Lados interiores → `opaque` (prioridad 0). Lados `facade` → banda exterior 2–18 px: periodicidad de
tinta por autocorrelación (montantes; ac ≥ 0.33, paso 0.8–4 m, ≥ 2.5 periodos) → `likely_glazing`;
franja sólida gruesa sin patrón → `opaque`; resto → `exterior_unknown`. `confirmed_glazing` sólo
humano. Prioridades: 1.0 / 0.75 / 0.4 / 0.2 / 0.0. Sin orientación solar.

## Pilares v2 — `semantics/columns_v2.py`

Semillas (rectángulos huecos a 4 umbrales + manchas oscuras) → rejilla (filas/columnas de semillas;
cada salto observado es un módulo candidato; ±1 salto desde los extremos) → verificación local
obligatoria (anillo de tinta ≥ 0.4, interior claro ≥ 0.5, producto ≥ 0.3 sobre imagen ×3). Nunca se
agrega un pilar sin verificación.

## Readiness

`ready_for_layout = true` sólo si: perímetro y core confirmados, primary_entrance confirmado,
todos los pilares candidatos confirmados, todos los lados exteriores confirmados con clasificación
≠ unknown, y la escala confirmada o aceptada explícitamente como supuesto (`confirm:
["scale_assumption"]`, que queda anotado en `notes` — no convierte la escala en medición).

## Gate E0.5 (bench)

IoU ≥ 0.95 · core ≤ 1 m · primary confirmado y a ≤ 1.5 m del GT · pilares R = 1.0, P ≥ 0.9 · fachada
exterior clasificada · ≥ 1 lado likely/confirmed glazing · 0 falsos claims (luz y pilares) · burden
< 60 s · ready_for_layout.
