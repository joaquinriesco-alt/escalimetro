# Caso 001 — GPS Property, Oficina 403, 543 m² publicados

## Input

`original.png`: JPG publicado por GPS, recibido re-codificado como PNG por el canal de chat.
800×424 px, 72 dpi, RGB. Es el input real de un usuario; no existe versión mejor para este experimento.
SHA-256 en `outputs/floorplate.json → source_image.sha256`.

## Estado E02

- [x] Pase A automático (OCR "403" → color pálido → máscara): `outputs/pass_a/`
- [x] Pase B asistido (10 clicks: 2 confirm, 2 accesos, 6 pilares): `outputs/pass_b/` (= `outputs/`)
- [x] GT manual: `ground_truth/make_gt.py` → `floorplate_gt.json` (lectura ±2 px sobre crops ×4 con grilla)
- [x] bench A y B

## Hallazgos del plano real

- La leyenda de colores NO coincide con el plano: la muestra de "Oficinas 403" es azul medio,
  pero la 403 en el plano es el azul más pálido (BGR 241,234,209; sat 34). El texto dentro del plano es
  la señal fiable; el color de la leyenda no. El OCR lo registra en `vision_hints[].notes`.
- No hay muro dibujado entre 402/403 ni 401/403: el límite de arriendo es sólo un cambio de color.
  El flood fill por muros (E01) no sirve aquí; la segmentación por color CIELAB sí.
- La pintura termina en la cara interior de la fachada: entre la pintura y la línea exterior hay una
  banda de ~14 px (~1.6 m a la escala inferida) con pilares/montantes. Convención: perímetro = borde de pintura.
- La fachada sur es una poligonal con retranqueos de 4–6 px (≈0.5–0.7 m): al borde de la resolución.
- Pilares dibujados como rectángulos huecos de contorno gris de 1 px (7×15 px). Detector: 4/10 recall.
- Accesos: arcos de puerta de ~4 px. No hay heurística CV; anotados a mano (2 clicks).
- Ventanas: no distinguibles de la fachada a esta resolución → UNKNOWN.
- Sin cota, barra de escala, grilla ni texto dimensional: la única escala es 543 m² (tipo desconocido).

## Estado E03 (shell semántico)

- [x] Pase A automático con semántica: `outputs/pass_a/` — 4 candidatos de acceso, primary propuesto (570,300) needs_confirmation;
      pilares v2 P 1.0 R 0.9; luz: 3/5 lados con montantes detectados, 0 falsos claims; ready_for_layout=false
- [x] Pase C confirmado (9 clicks, ~36 s): `outputs/pass_c/` (= `outputs/`) — Gate E0.5 PASS, ready_for_layout=true
- [x] GT corregido: accesos. E02 anotó "arco en el eje central inferior del núcleo (500,331)": ERROR de lectura, la línea
      inferior del núcleo es continua. Con zoom ×8 las puertas son huecos con hoja en los muros oeste (429,302) y este (567,301)
      del núcleo, simétricos. El detector automático encontró ambos sin conocer el GT.
- [x] GT de luz: montantes visibles en oeste, sur (3 tramos) y este; escalones cortos no evaluables.

## Preguntas abiertas

- ¿543 m² útiles, arrendables o totales? Cambia la escala hasta ±10–20 %.
- ¿El JPG original (antes de pasar por el chat) tiene más resolución? Cambiaría pilares y accesos.
