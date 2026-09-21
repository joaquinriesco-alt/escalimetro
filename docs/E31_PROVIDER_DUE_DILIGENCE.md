# E31 — DILIGENCIA DE PROVEEDORES DE AMBIENTACIÓN

**Fecha de consulta: 2026-09-21.** Todo lo de abajo se leyó ese día en la documentación oficial
que se cita. Los precios cambian; los términos también. Antes de gastar, releer.

**Qué se buscó:** 2–3 proveedores con edición de imagen real (imagen + texto → imagen editada) y
uso comercial de la salida. No se seleccionó nada por moda ni por benchmarks de terceros: lo único
que decide es el bake-off sobre nuestras fotos, y ese bake-off **no se corrió** (sin credenciales).

## Resumen

| | Google Gemini | OpenAI Images | Black Forest Labs |
|---|---|---|---|
| Modelo elegido para el piloto | `gemini-3.1-flash-image` | `gpt-image-2.5-sunburst` | `flux-kontext-pro` |
| Alternativas | `gemini-3-pro-image` (premium) · `gemini-3.1-flash-lite-image` (1K, no multi-ref) | `gpt-image-2.5-flare` (rápido) · `gpt-image-2` | `flux-kontext-max` · FLUX.2 [pro]/[max]/[flex] (edición por MP) |
| Edición imagen+texto | Sí | Sí (`/v1/images/edits`) | Sí |
| Referencias múltiples | Hasta 14 | Varias imágenes | Hasta 4 (Kontext, experimental) / 8 (FLUX.2) |
| Máscara / inpainting | No documentado | `mask`, pero "prompt-based", sin precisión de píxel | FLUX.1 Fill [pro] (aparte, $0.05) |
| Control de profundidad | No | No | No en Kontext |
| Control de fidelidad al input | Sólo por prompt | **`input_fidelity: high`** | Por diseño del modelo (edición contextual) |
| `seed` | En `generationConfig` de la referencia REST; ausente en la guía de imagen | **No** | **Sí** |
| Salida | 0.5K/1K/2K/4K, ratios fijos | 1024²/1536×1024/1024×1536/auto/custom (múltiplos de 16) | ratio 21:9–9:21; PNG/JPEG/WEBP |
| Precio por imagen (edición) | **$0.067** (1K, medido por tokens: $0.50/M entrada, $60/M salida) | por tokens: $8/M imagen entrada, $5/M texto, $30/M salida (≈$0.05–0.21 según calidad) | **$0.04** fijo (pro) · $0.08 (max) |
| Latencia publicada | no | "hasta 2 min" en prompts complejos | no (asíncrono con sondeo) |
| Marca de agua | SynthID en TODA salida | no documentado | no documentado |
| Uso comercial de la salida | Sí; Google no reclama propiedad | Sí; "Customer owns all Output" | Sí, según Developer ToS |
| Uso de nuestros datos para entrenar | **No en el tier pago**; sí en el gratuito | **No por defecto** (retención 30 días abuso; ZDR opcional) | **SÍ: licencia perpetua sobre Inputs y Outputs, sin opt-out** |
| Apto para el piloto | Sí | Sí | Sí para el bake-off; **decisión pendiente** para fotos de clientes |

## Google — Gemini API

* **Modelos** (guía de generación de imágenes): `gemini-3.1-flash-image` — "the most versatile
  model, generalist workhorse model for all tasks", recomendado para edición; `gemini-3-pro-image`
  premium; `gemini-3.1-flash-lite-image` sólo 1K y "not optimized for multiple reference inputs or
  multi-turn sequential editing"; `gemini-2.5-flash-image` deprecado.
* **Edición:** imagen + texto → imagen; hasta 14 referencias. Sin máscara, sin control de
  profundidad.
* **API:** la guía muestra hoy `POST /v1beta/interactions` (entrada `{type:"image", mime_type,
  data}`; salida en `interaction.output_image.data`). La referencia REST de `generateContent`
  documenta `inline_data`, `generationConfig.responseModalities`, `imageConfig{aspectRatio,
  imageSize}`, `seed` y la salida en `candidates[].content.parts[].inlineData.data`. **El adaptador
  está codificado contra `generateContent`** (tiene `seed`, que la repetibilidad necesita) y lo
  declara; sin credencial no se pudo verificar en vivo cuál acepta el modelo 3.1.
* **Precio** (estándar, por millón de tokens): entrada $0.50; salida $60 → $0.045 (0.5K), $0.067
  (1K), $0.101 (2K), $0.151 (4K). Pro: entrada $2, salida $120. Batch a mitad.
* **Salida:** 512/1K/2K/4K; ratios 1:1, 3:2, 2:3, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9. **SynthID
  en todas las imágenes** (invisible; compatible con nuestra obligación de disclosure).
* **Términos:** "Google won't claim ownership over that content"; uso comercial permitido. Tier
  pago: "Google doesn't use your prompts... or responses to improve our products"; tier gratuito:
  sí los usa. **Usar sólo con facturación activa.**
* Fuentes: ai.google.dev/gemini-api/docs/image-generation · ai.google.dev/gemini-api/docs/pricing ·
  ai.google.dev/api/generate-content · ai.google.dev/gemini-api/terms.

## OpenAI — Images API

* **Modelos para edición** (referencia `createEdit`): `gpt-image-2.5-sunburst` ("precision model",
  snapshot `gpt-image-2.5-sunburst-2026-09-08`), `gpt-image-2.5-flare` (rápido, por defecto),
  `gpt-image-2`, `gpt-image-1.5`, `gpt-image-1`, `gpt-image-1-mini`.
* **API:** `POST /v1/images/edits`, multipart `image` (varias) + `mask` opcional; `prompt`, `model`,
  `n`, `size` (`1024x1024`, `1536x1024`, `1024x1536`, `auto`, o `WIDTHxHEIGHT` múltiplo de 16 entre
  1:3 y 3:1, ≤3840 px por lado, 655.360–8.294.400 px), `quality` (`low|medium|high|xhigh|max|auto`),
  **`input_fidelity` (`high|low`)**, `output_format`, `output_compression`, `background`.
  Respuesta `data[].b64_json` + `usage{input_tokens, output_tokens, input_tokens_details{image_tokens,
  text_tokens}}` → el costo se **mide** por intento.
* **Máscara:** "masking with GPT Image is entirely prompt-based" — no preserva píxeles con
  precisión. Por eso el adaptador no usa máscara: la preservación se pide por contrato de texto,
  igual que a los demás, y `input_fidelity=high`.
* **`seed`:** no existe. La repetibilidad se mide con dos corridas, no se configura.
* **Precio** (estándar, por millón de tokens, 2.5 y 2): imagen entrada $8, cache $2, salida $30,
  texto $5. Referencias de terceros para 1024² en gpt-image-2: $0.006 low / $0.053 medium / $0.211
  high — orientativo; lo que cuenta es `usage`.
* **Limitaciones declaradas:** latencia hasta 2 min; dificultad con colocación precisa de
  elementos en composiciones estructuradas (relevante para nosotros).
* **Términos:** Business Terms — "you retain all ownership rights in Input and own all Output"; API:
  datos no usados para entrenar por defecto; retención 30 días para abuso; Zero Data Retention para
  clientes elegibles. (Las páginas de openai.com/policies devolvieron 403 al fetcher; citado desde la
  página de datos de developers.openai.com y los extractos oficiales indexados.)
* Fuentes: developers.openai.com/api/docs/guides/image-generation ·
  developers.openai.com/api/docs/api-reference/images/createEdit ·
  developers.openai.com/api/docs/pricing · developers.openai.com/api/docs/guides/your-data ·
  openai.com/policies/business-terms.

## Black Forest Labs — FLUX API

* **Modelos de edición:** FLUX.1 Kontext [pro] ($0.04/imagen) y [max] ($0.08/imagen), edición
  contextual con preservación estructural; FLUX.2 [pro] (edición desde $0.045/MP), [max] $0.07/MP,
  [flex] $0.05/MP, [klein] 9B $0.015/MP; FLUX.1 Fill [pro] $0.05 (inpainting con máscara).
* **API (Kontext pro):** `POST https://api.bfl.ai/v1/flux-kontext-pro`, cabecera `x-key`; cuerpo
  `prompt`, `input_image` (base64/URL, ≤20 MB / 20 MP), `input_image_2..4` (experimental), **`seed`**,
  `aspect_ratio` (21:9–9:21), `output_format`, `prompt_upsampling` (false: no queremos que reescriba
  nuestro contrato), `safety_tolerance` 0–6, `webhook_url`. Respuesta `{id, polling_url}`; sondeo
  GET a `polling_url` cada 0,5 s; estados `Pending | Ready | Error | Failed | Content Moderated |
  Request Moderated`; imagen en `result.sample`, **URL firmada válida 10 minutos**.
* **FLUX.2 [pro]:** `POST /v1/flux-2-pro`, hasta 8 imágenes de entrada, `width/height`, devuelve
  `cost` en créditos ($0.01), `input_mp`, `output_mp`.
* **Términos (FLUX API Service Terms, "Last Revised on August 4, 2026"):**
  > "Developer grants the Company a fully paid, royalty-free, perpetual, irrevocable, worldwide,
  > non-exclusive, and fully sublicensable right and license to use, sub-license, distribute,
  > reproduce, modify, adapt, publicly perform, and publicly display Developer's Input and Output
  > for the purpose of operating the FLUX Services, improving the Company's products and services,
  > and developing new products and services."

  Sin opt-out. **Esto significa que las fotos de la propiedad de un cliente quedarían licenciadas a
  BFL a perpetuidad.** Es la objeción de licencia más seria de las tres y **la decide Joaquín**, no
  este piloto. Para el bake-off con fotos propias es aceptable; para fotos de clientes reales, no
  sin esa decisión. También: "Developer may not host... an API endpoint to any FLUX AI Models that
  allows third parties to integrate or otherwise use the FLUX AI Models" — no es nuestro caso
  (vendemos imágenes, no acceso al modelo). Los Developer ToS (según extracto indexado) no reclaman
  propiedad de la salida y permiten uso personal o comercial por el desarrollador y sus usuarios.
* Fuentes: docs.bfl.ml/kontext/kontext_image_editing.md ·
  docs.bfl.ml/api-reference/models/edit-or-create-an-image-with-flux1-kontext-[pro].md ·
  docs.bfl.ml/api-reference/models/generate-or-edit-an-image-with-flux2-[pro].md ·
  docs.bfl.ml/quick_start/pricing.md · bfl.ai/legal/flux-api-service-terms ·
  bfl.ai/legal/developer-terms-of-service.

## Evaluados y no preseleccionados

* **Luma (`photon-1`, `photon-flash-1`)** — `modify_image_ref{url, weight 0–1}`: "Higher the weight,
  closer to the input image but less diverse". Es un dial de parecido, no una edición con
  preservación estructural declarada; sin máscara; sin precio ni términos en la página consultada.
  Candidato de reserva si los tres primeros fallan la compuerta. Fuente: docs.lumalabs.ai.
* **fal.ai** — aloja GPT Image 2, Nano Banana 2 y FLUX, más una LoRA "apartment staging" sobre
  FLUX.2 con parámetro de intensidad. Excluido como ruta: §5 prohíbe wrappers cuando existe la API
  oficial, y la licencia de esa LoRA no está declarada.

## Lo que NO se usa

Modelos con licencia no comercial (FLUX [dev] Non-Commercial License v2.0), datasets CC-BY-NC,
assets 3D con licencia incompatible, wrappers no oficiales.

## Estado

Ninguna credencial de estos proveedores existe en el entorno de trabajo. No se creó ninguna cuenta,
no se compró crédito, no se cambió ningún plan (§4). Los adaptadores están escritos contra estas
referencias y verificados con respuestas grabadas; la primera llamada real la hace una persona con
la clave y con esta ficha al lado.
