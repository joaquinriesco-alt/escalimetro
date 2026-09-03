# Arquitectura ETAPA 1

```
imagen ──► VisionInterpreter ──► hints (px, confidence)
   │                                   │
   └──► SegmentationProvider ◄─────────┘  (seeds/bbox)   ◄── overrides.json (polígono)
              │
              ▼ máscara
        GeometryExtractor  → contorno crudo → Douglas-Peucker (eps 0.4% perímetro) → snap ortogonal
              │
              ▼ ring px
        scale (área conocida) · detect_columns · classify_facade_segments · overrides
              │
              ▼
        Floorplate JSON ──► render_svg (m / px) ──► side_by_side.png · overlay.png
```

## Tres interfaces, cero acoplamiento

| Interfaz | Entrada | Salida | Implementaciones |
|---|---|---|---|
| `VisionInterpreter` | imagen, unidad objetivo | `hints` en px con confidence (+ color de relleno) | **ocr** (tesseract, local), manual, null, openai, anthropic, gemini |
| `SegmentationProvider` | imagen + seeds/bbox/polígono | máscara 0/255 + confidence + provenance | manual, opencv_flood, **opencv_color** (desde seed, CIELAB), sam2 |
| `GeometryExtractor` | máscara | ring simplificado + área px² | una sola; no importa nada de vision/segmentation (test lo verifica) |

Los VLM no dibujan geometría. Sólo localizan (dónde está la 403, dónde el núcleo, dónde la puerta).
La geometría siempre sale de píxeles reales de la imagen. Cambiar de proveedor no cambia un
solo número de `geometry/`.

## Precedencia por elemento

`override manual` > `heurística CV` > `hint VLM` > `unknown`

Un elemento que no se pudo obtener queda en `floorplate.unknowns[]` con razón. Nunca se rellena.

## Localización automática (E02)

`OCRVisionInterpreter`: tesseract ×3 → tokens cuyos dígitos = número de la unidad → cada hit se
clasifica por el color que lo rodea (relleno saturado = label dentro de la unidad → `unit_region`;
blanco + muestra de color a la izquierda = leyenda → `legend_swatch`). El pipeline con
`segmentation: auto` elige `opencv_color` si el label está sobre relleno de color, y `opencv_flood`
si no. Sin coordenadas de ningún caso en el código.

`opencv_color` desde seed: color mediano alrededor del seed (ignorando tinta) → distancia CIELAB
< 10 → tinta oscura como barrera → componente más cercano al seed → relleno de agujeros chicos,
huecos grandes conservados. Es lo que separa 403 (pálido) de 402 (medio) cuando NO hay muro entre
ambas: el límite es sólo de color.

Core automático: `detect_core_enclosed` — vacío encerrado por la unión de todas las unidades pintadas.
Pilares: `detect_hollow_columns` (rectángulos de tinta gris huecos, sobre imagen ×3) + `detect_columns`
(manchas oscuras). Fachada: estadísticas de banda exterior (color → party_wall; tinta/achurado →
core_wall; blanco + rayos libres → facade; blanco encerrado → corridor).

## Decisiones

- **Escala por área conocida.** `px_per_m = sqrt(area_px / area_m2)`. Fija el área por
  construcción, así que el error de área contra los 543 m² es 0 por definición. El benchmark de
  área se mide contra GT independiente (en px² contra polígono anotado; en m² sólo si hay otra
  fuente de escala). Ver `geometry/scale.py`.
- **Flood fill con muros dilatados.** Antes del flood se dilatan los muros `gap_px/2` para
  cerrar puertas; después se dilata la región para recuperar la franja. Kernel RECT para no
  redondear esquinas. Sin esto la máscara se fuga por la puerta al pasillo (medido: IoU 0.83 →
  0.99 en el fixture).
- **Fachada por ray-casting.** Un lado es fachada si rayos normales hacia afuera llegan al borde
  de la imagen sin cruzar tinta. Un pasillo blanco no engaña (choca con el muro de enfrente). Falla
  si hay leyendas/títulos fuera de la fachada → queda `unknown` conf 0.3, no `facade`.
- **Convención de perímetro = cara interior del muro.** Es lo que segmenta la máscara y lo que
  corresponde a superficie útil. El GT se anota igual.
- **Estructura**: se agregó `fixtures/` (generador sintético) y `overrides/` (HITL) a la
  estructura sugerida; `cases/<id>/case.json` describe cada caso para que todo sea CLI.

## Fuera de alcance (E01)

Layouts, PDF (adapter PyMuPDF queda para E02: `fitz.Page.get_pixmap` → misma ruta), OCR de
cotas, SAM2 ejecutado, editor web.
