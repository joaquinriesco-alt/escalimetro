# E08 — OpenAI + Anthropic API orchestration

    LAYOUTS VALIDADOS  →  3 CRÍTICOS EN PARALELO  →  AGREGADOR  →  PresentationSpec  →  RENDER DETERMINISTA

Paquete `src/escalimetro/ai/`. El solver no se tocó. E08 no genera layouts: consume los A/B/C de E07.

## Principio

**Ningún LLM tiene autoridad sobre geometría.** La fuente de verdad es `layout.json` + `floorplate.json`
+ el validador determinista de E04. Los modelos interpretan, critican, comparan y escriben; no mueven un
muro ni declaran válida una geometría inválida.

Esto no es una convención: `geometry_guard.py` calcula un hash canónico de shell, recintos, puestos,
mobiliario, puertas, pilares y circulación antes y después de cada llamada. Si difieren, la corrida falla.

## Chat ≠ API

| | herramienta de desarrollo | dependencia del producto |
|---|---|---|
| Anthropic | Claude Code / Claude Chat, usados para construir ESCALÍMETRO | `AnthropicProvider`, con su credencial, su costo, su latencia y su modo de fallo |
| OpenAI | ChatGPT, usado para coordinar el proyecto | `OpenAIProvider`, ídem |

E08 implementa la columna de la derecha. La izquierda no aparece en el runtime.

## Estructura

    ai/
      config.py               AIProviderConfig; todo por env, nada hardcodeado; la clave nunca se serializa
      schemas.py              schemas locales + prohibición de coordenadas en outputs de IA
      geometry_guard.py       hash canónico y context manager que falla si la geometría cambia
      costs.py                reported / estimated / unknown, nunca mezclados
      telemetry.py            ledger por proyecto, alternativa y proveedor; scrub de credenciales
      prompts/                prompts versionados en archivos, no en código
      providers/base.py       contrato, extracción de JSON, retries, taxonomía de errores
      providers/anthropic_provider.py
      providers/openai_provider.py
      providers/deterministic_provider.py   fallback que nunca se cae
      reviewers.py            los tres revisores y el payload común
      review_aggregator.py    consenso y desacuerdo, sin promedios ciegos
      orchestrator.py         resuelve proveedores, paraleliza, agrega, mide
      board02.py              PRESENTATION STANDARD 02 (renderer determinista)
      visuals.py              arquitectura, workflow, desacuerdos, latencia, 01 vs 02
      run.py                  corrida sobre A/B/C de E07

## Los tres críticos

| | entrada | qué juzga | schema |
|---|---|---|---|
| `RuleBasedReviewer` | métricas + crítico E05/E07 | lo verificable | `StructuredSpatialReview` |
| `AnthropicSpatialReviewer` | payload estructurado, **sin imagen** | lógica espacial: llegada, recorrido de cliente, privacidad, adyacencias, coherencia con la estrategia | `StructuredSpatialReview` |
| `OpenAIVisualArchitecturalCritic` | render de la planta + contexto | lo que un validador no puede ver: proporciones, fragmentación, zonas muertas, si la estrategia se **lee** | `VisualArchitecturalReview` |

Los tres usan el mismo vocabulario de aspectos. Eso es lo que hace comparable el desacuerdo.

## Agregador

`AggregatedReview` guarda `agreements`, `disagreements` y `critical_disagreements` por separado. Nunca
promedia un desacuerdo fuerte: si el crítico por reglas ve la recepción bien y el visual la ve absurda,
el promedio esconde justo lo que importa.

Dos fuentes de la **misma familia** no cuentan como evidencia independiente: el visual determinista
deriva del mismo crítico por reglas, así que coincidir con él no significa nada. Sólo se comparan
familias distintas.

`AI_REVIEW_STATUS`: `CONSENSUS_GOOD` · `CONSENSUS_WEAK` · `DISAGREEMENT` · `CRITICAL_DISAGREEMENT` ·
`PROVIDER_UNAVAILABLE`. Una alternativa con `CRITICAL_DISAGREEMENT` no pasa sola a presentación final:
queda en `INTERNAL_REVIEW`.

## Fallos y fallback

Taxonomía explícita: `timeout`, `rate_limit`, `provider_unavailable`, `malformed_json`,
`empty_response`, `provider_failed_schema`, `auth_error`. Reintentos acotados (`AI_PROVIDER_MAX_RETRIES`,
con backoff), sin bucles. Un proveedor caído se registra y el pipeline sigue con los demás. Si caen los
dos, el crítico determinista sostiene el producto.

Los schemas se validan **del lado del cliente** aunque el proveedor soporte structured output nativo. Un
JSON parcialmente válido no se acepta en silencio.

## Control de costo

El solver filtra primero. La IA ve exactamente tres layouts validados por proyecto — nunca los ~2 700
candidatos internos por alternativa. Son 6 llamadas por proyecto en vez de ~8 000. No es una
optimización: es la condición para que la capa de IA sea viable.

## Presentación

OpenAI produce un `PresentationSpec` (orden, titular, copy, prioridad de métricas, callouts, jerarquía,
espaciado, roles de color). **El código renderiza.** No se usa image generation para dibujar plantas: las
plantas de la lámina son el mismo SVG del renderer sobre el Layout validado, incrustado sin recalcular
una coordenada.

## Ejecutar

    cp .env.example .env      # completar credenciales
    PYTHONPATH=src python -m escalimetro.ai.run --case cases/001_gps_403 \
        --mock-disagreement tests/fixtures/ai/mock_reviews.json

Sin credenciales el pipeline corre igual y reporta `NOT EXECUTED — API KEY MISSING`. Los tests de
integración real (`-m integration`) se saltan solos cuando no hay keys; los tests normales no gastan
dinero.
