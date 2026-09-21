# E31 — BENCHMARK DE AMBIENTACIÓN

**Fecha: 2026-09-21. Estado: NOT_RUN.**

## Tabla de proveedores

| Proveedor | Modelo | Generaciones | Éxito API | Fidelidad PASS | Aprobadas | Calidad media (PASS) | Reintentos | Latencia mediana / p95 | Costo total | Costo / aprobada | Fallos recurrentes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini | gemini-3.1-flash-image | 0 | — | — | — | — | — | — | — | — | — |
| openai | gpt-image-2.5-sunburst | 0 | — | — | — | — | — | — | — | — | — |
| bfl | flux-kontext-pro | 0 | — | — | — | — | — | — | — | — | — |

**Estado por proveedor: `HUMAN_ACTION_REQUIRED` en los tres** — sin credencial en el entorno.

No hay filas porque no hubo generaciones. No hay cherry-picking porque no hay nada que elegir. La
tabla se llena con `python -m webapp.benchmark report`, que la calcula desde `staging_attempts`
(sólo revisiones humanas), y no a mano.

## Dataset

`benchmarks/staging_benchmark_v1.json` — **0 fotos**, estado `AWAITING_REAL_PHOTOS`.

Se buscó en el repo, en los fixtures de tests, en `.data/` y en las propiedades existentes: todo
lo que hay son planos, contact sheets y dibujos sintéticos. §6 prohíbe usar imágenes sintéticas
como benchmark principal y stock sin licencia. El manifiesto espera 8–12 fotos reales de al menos
3 espacios, con ventanas, pilares, cielos, esquinas, gran angular y algún caso difícil.

## Protocolo (fijo, versionado)

* **Petición canónica** `staging_request_v1` (`webapp/domain/staging.py::canonical_request`):
  un solo texto para todos los proveedores, con la lista de PRESERVAR (cámara, perspectiva,
  proporciones, muros, ventanas —cantidad, posición, tamaño—, pilares, puertas, cielo, piso, vista
  exterior), la de PUEDE CAMBIAR (mobiliario, plantas, luminarias decorativas, alfombras, arte,
  accesorios) y la de PROHIBIDO (ampliar ventanas, borrar pilares, añadir muros, cambiar altura,
  inventar puertas, alterar la vista, cambiar proporciones, mover la cámara). Hash SHA-256 del
  contrato en cada intento; hay test de que todos los proveedores reciben el mismo hash.
* **Estilo fijo:** CONTEMPORARY. No se mezclan los 5 estilos en el primer benchmark.
* **Repeticiones:** 2 por foto. 10 fotos × 2 × 3 proveedores = 60 salidas (ideal).
* **Sin máscara, sin prompt upsampling** (BFL `prompt_upsampling=false`; OpenAI `input_fidelity=high`).
* **Seed:** BFL y Gemini lo aceptan; OpenAI no. La repetibilidad se mide comparando las dos
  corridas, no se configura.

## Rúbrica de fidelidad (compuerta dura, §9)

PASS sólo si se preservan: A perspectiva · B ventanas (cantidad y posición) · C pilares · D puertas
y vanos · E muros visibles · F cielo · G límites del piso · H vista exterior no fabricada · I sin
geometría imposible · J sigue siendo reconociblemente la misma sala. **Un solo cambio material =
FAIL.** No se promedia. Motivos cerrados: `window_changed`, `column_changed`,
`wall_or_opening_changed`, `ceiling_changed`, `perspective_changed`, `view_changed`,
`proportions_changed`, `impossible_geometry`, `other`.

## Calidad (§10)

Sólo después de PASS, 1–5: fotorrealismo, escala del mobiliario, ubicación, coherencia de luz,
estética, verosimilitud de oficina, listo para publicar. La calidad no se guarda cuando la
fidelidad falla: un 5/5 alucinado es FAIL y hay test.

## Diagnóstico automático (§12)

Tamaño y proporción, salida en blanco o corrupta, SSIM en gris a 512 px, IoU de bordes Canny,
distancia dHash. Producen `AUTO_WARNING` y nada más: ningún aviso marca PASS ni FAIL. Hay test.

## Métricas (§13)

Por proveedor: generaciones, éxito API, revisadas, fidelidad PASS y tasa, aprobadas y tasa,
calidad media entre PASS, reintentos, latencia media/mediana/p95, costo total y base (medido o de
lista), costo por generación / por PASS / por aprobada, motivos de fallo, versiones de modelo, y
`sample_thin` cuando hay menos de 20 revisiones.

**La métrica que manda es la tasa de imágenes aprobadas por un humano.**

## Resultado

Ninguno. Ver `docs/E31_PROVIDER_DECISION.md`.
