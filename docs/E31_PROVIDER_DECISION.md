# E31 — DECISIÓN DE PROVEEDOR DE AMBIENTACIÓN

**Fecha: 2026-09-21.**

## Decisión: NINGUNA — el bake-off no se corrió

`STAGING_PROVIDER_NOT_APPROVED`

No hay ganador porque no hay evidencia. No se seleccionó ningún proveedor y
`ESCALIMETRO_STAGING_PROVIDER` queda vacío: el producto responde que no hay proveedor y ningún pack
de publicación puede declararse completo sin una imagen aprobada o un motivo interno escrito.

## Por qué no se corrió

| Requisito | Estado |
|---|---|
| Credenciales de proveedor en el entorno | **Ninguna.** No existe `GEMINI_API_KEY`, `OPENAI_API_KEY` ni `BFL_API_KEY`. No se creó ninguna cuenta ni se compró crédito (§4). |
| Fotos reales de oficinas vacías | **Cero disponibles localmente.** El repo, los fixtures y las propiedades existentes sólo contienen planos y dibujos de prueba. No se rellenó con imágenes sintéticas ni con stock sin licencia (§6). |

Cualquiera de las dos bastaba para no correr. Las dos faltan.

## Tamaño de la muestra

0 generaciones · 0 revisiones · 0 proveedores comparados.

## Resultados

Ninguno. `benchmarks/staging_benchmark_results.json` dice `NOT_RUN`. La tabla de proveedores de
`docs/E31_STAGING_BENCHMARK.md` está vacía a propósito.

## Lo que sí queda decidido, con fundamento

1. **Los tres candidatos del piloto** (`docs/E31_PROVIDER_DUE_DILIGENCE.md`): Gemini 3.1 Flash Image,
   OpenAI gpt-image-2.5-sunburst con `input_fidelity=high`, FLUX.1 Kontext [pro]. Los tres tienen
   adaptador escrito y verificado con respuestas grabadas.
2. **La compuerta** (§14): fidelidad ≥ 85 %, aprobación ≥ 75 %, sin patrón estructural recurrente,
   costo por imagen aprobada ≤ USD 4 (compatible con un pack de ~USD 100), derechos verificados por
   escrito. Con menos de 20 revisiones es evidencia de piloto, no prueba.
3. **El orden de prioridad si más de uno pasa** (§15): fidelidad → aprobación → repetibilidad →
   costo por aprobada → latencia → simplicidad. Nunca el más barato por generación.
4. **Una objeción de licencia previa a cualquier resultado:** los términos del servicio API de BFL
   otorgan a BFL una licencia perpetua sobre Inputs y Outputs para mejorar sus productos, sin
   opt-out. Para fotos propias del bake-off es aceptable; para fotos de clientes reales **lo decide
   Joaquín**, no este documento.

## Qué hace falta para decidir

1. Ocho a doce fotos reales de oficinas vacías, de al menos tres espacios, subidas a propiedades
   (`python -m webapp.benchmark init --from-properties ...`).
2. Dos o tres credenciales en el entorno, con facturación activa (Gemini: tier pago, para que no
   usen las fotos para entrenar).
3. `python -m webapp.benchmark run --providers gemini,openai,bfl --runs 2 --style CONTEMPORARY`.
4. Revisar cada candidato en `/staging` — la persona que revisa tiene que conocer las fotos
   originales, y la compuerta 1 se juzga antes de mirar lo demás.
5. `python -m webapp.benchmark report --benchmark-id ...` y volver a este archivo.

Costo estimado del bake-off completo (10 fotos × 2 corridas × 3 proveedores = 60 imágenes) con las
tarifas publicadas: Gemini ≈ USD 1.3, OpenAI ≈ USD 2–8 según calidad, BFL ≈ USD 0.8. Bajo y medible
(§4); lo que cuesta es el tiempo de revisión humana, no la API.

## Limitaciones de esta decisión

Es una no-decisión con evidencia de por qué. No dice que ningún proveedor sirva; dice que no se
sabe, y que el sistema está construido para no fingir que se sabe.
