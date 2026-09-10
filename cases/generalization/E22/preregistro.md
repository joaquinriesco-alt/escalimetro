# E22 — PRE-REGISTRO
# Escrito y hasheado ANTES de la inferencia #1. PREREGISTRATION_FROZEN = TRUE desde ese momento.

## Base
HEAD             f396e29cde0f68a1462bd5c241a8f3b94e08393b   (e21)
rama de trabajo  e22, creada desde f396e29c
BACKUP_GATE      PASS — origin/e21 == f396e29cde0f68a1462bd5c241a8f3b94e08393b,
                 verificado con git fetch + git ls-remote en la maquina del usuario;
                 e21 local == f396e29c; 0 archivos versionados modificados
main             c6de3f9646047eeba209c5d3d4ef5e6ccb85c26f  (sin mover)

## Pregunta
El sesgo ARCH -> FURN de E19.1 / E20 / E21, es especifico del evaluador,
o sobrevive al ejecutar el MISMO experimento QA con otro evaluador de vision?
UNICA VARIABLE = EVALUATOR. Todo lo demas congelado.

## Inventario y seleccion (SS3, SS4)
INVENTARIO_MODELOS.txt  SHA256 c402b6e74babbad0ec490061f866cf0fc538fd50cbed40d7bcd617277af9a7bf
Levantado y hasheado ANTES de mostrar una sola imagen del banco.

Configuraciones vision-capable disponibles: opus (baseline), sonnet, haiku, fable.
Las cuatro se autodeclaran familia Claude / Anthropic.
PRIORIDAD 1 (otra familia/provider) NO SATISFACIBLE en este entorno sin instalar ni credenciales.
SELECTION_PRIORITY_USED = PRIORIDAD 2

EVALUADOR ALTERNATIVO CONGELADO = sonnet
  CONFIGURED_PARAMETER         = sonnet
  CONFIGURED_MODEL             = autodeclarado "Claude Sonnet 5"
  PROVIDER_IDENTITY            = UNKNOWN (autodeclaracion, no verificable desde aqui)
  MODEL_FAMILY_VERIFIABILITY   = CONFIGURATION_LEVEL_ONLY
  MODEL_IDENTITY_VERIFIABILITY = CONFIGURATION_LEVEL_ONLY
  VISION_CAPABLE               = SI (verificado sobre imagen neutra, no del banco)
UNO SOLO. No se probara otro. No ensemble. No second chance. No sustitucion posterior.

Conclusion permitida bajo PRIORIDAD 2: sensibilidad a configuracion/evaluator.
NO independencia de proveedor. Se declarara asi pase lo que pase.

## Banco (congelado, SS5)
tests/fixtures/semantic_context/context_bench_scene.py
SHA256 2b3e2eb06248f3897b4bf663ce39930fc111b59560ccffd7cac8478141be6f81   (== E19/E19.1/E20/E21)
72 imagenes FULL_CONTEXT, 36 ARCH y 36 FURN.
Los 144 sha_img del manifest verificados uno a uno contra el disco ANTES de este pre-registro:
  faltantes 0 · con SHA distinto 0 · desajustes contra el manifest de E19.1 0
Nada se añade, quita, corrige ni re-renderiza.

## Manifest (congelado, SS5)
cases/generalization/E21/manifest.json
SHA256 43de0430755fccdbc1e182efa1fb1ac28b64a6caa1d04fd14859370d4c4b78f8
144 assertions. Mismos call_id, mismo GT, misma distribucion, mismos asserted roles.
Balance verificado: TRUE-ARCH 36 · TRUE-FURN 36 · FALSE-ARCH 36 · FALSE-FURN 36.

## Prompt (congelado, SS6)
cases/generalization/E21/prompt_qa_congelado.txt
SHA256 ab58d99ebe98923dff4cb2d1af43866630c954574b18a4db6c6ef920ca36170d
Verificado ANTES de la inferencia #1. Ni una palabra cambia: mismo texto, mismos roles, mismo
output contract, mismo campo evidence, misma tool restriction, mismo wording de los tres veredictos.
Sustitucion unica: {ASSERTED_ROLE}.

## Baseline (congelado, SS7)
cases/generalization/E21/respuestas_e21.txt
SHA256 312ee30c106711c7aa845181fdb176a0cf4409e994d72463993e752853f17f5f
NO se re-ejecuta `opus`. El evaluador alternativo NO ve estas respuestas ni el GT.
Se abre para comparar SOLO despues de completar las 144 inferencias nuevas.

## Orden y despacho
SEMILLA = 2101. Se REUTILIZA EXACTAMENTE el orden y las 12 olas de 12 ya pre-registrados y
committeados en el manifest de E21. Motivo declarado aqui, antes de correr: reutilizar el orden
elimina un grado de libertad nuevo, es verificable contra un artefacto ya versionado, y ninguna
llamada tiene memoria, asi que el orden no puede arrastrar estado. Ninguna ola contiene los dos
brazos de la misma imagen.

## Protocolo (SS9)
144 evaluaciones nuevas. UNA imagen + UNA assertion por evaluador. Evaluador nuevo cada vez.
Sin memoria, sin conversacion persistente, sin batching, sin resultados previos.
Sin GT, sin repo, sin E17-E21, sin respuestas baseline, sin GPS, sin RES, sin tercer plano.
Read solo sobre la ruta explicita. Sin Glob, Grep, Bash, WebSearch ni listado de directorios.
Fallo tecnico: UNA sola repeticion con misma imagen, misma assertion, mismo prompt, mismo
evaluador, registrando TECHNICAL_RETRY = TRUE. No se elige respuesta por calidad.

## Metricas (SS10)
ERROR_CATCH_RATE overall / false-ARCH / false-FURN
CORRECT_PASS_RATE overall / true-ARCH / true-FURN
TRUE_ASSERTION_REVIEW_RATE · FALSE_ASSERTION_CONSISTENT_RATE · INSUFFICIENT_RATE
BALANCED_QA_ACCURACY = (ERROR_CATCH_RATE + CORRECT_PASS_RATE) / 2
IDEAL_PAIR_RATE
Definiciones identicas a E21. No se cambia ninguna despues de ver resultados.

## Gate absoluto (SS11) — el gate original E21-A, sin relajar nada
E22-A PASS solo si TODOS:
  ERROR_CATCH_RATE overall        >= 0.80
  ERROR_CATCH_RATE por clase      >= 0.70
  CORRECT_PASS_RATE overall       >= 0.75
  CORRECT_PASS_RATE por clase     >= 0.65
  FALSE_ASSERTION_CONSISTENT_RATE <= 0.15
  TRUE_ASSERTION_REVIEW_RATE      <= 0.25
  INSUFFICIENT overall            <= 0.15
  BALANCED_QA_ACCURACY            >= 0.775

## Comparacion pareada (SS12)
DELTA_ERROR_CATCH · DELTA_CORRECT_PASS · DELTA_BALANCED_QA · DELTA_IDEAL_PAIR
DELTA_TRUE_ARCH_PASS · DELTA_TRUE_FURN_PASS · DELTA_FALSE_ARCH_CATCH · DELTA_FALSE_FURN_CATCH
Todos calculados como alternativo menos baseline, target por target.

## Indices de asimetria (SS13)
PASS_ASYMMETRY  = CORRECT_PASS_true_FURN - CORRECT_PASS_true_ARCH   baseline 0.9722-0.5556=0.4166
CATCH_ASYMMETRY = ERROR_CATCH_false_ARCH - ERROR_CATCH_false_FURN   baseline 0.6944-0.4444=0.2500

## Materialidad (SS14) — descriptiva, NO es un gate
MATERIAL_BQA_CHANGE           |DELTA_BALANCED_QA|   >= 0.10
MATERIAL_ARCH_PASS_CHANGE     |DELTA_TRUE_ARCH_PASS| >= 0.15
MATERIAL_ASYMMETRY_REDUCTION  PASS_ASYMMETRY alternativo <= 0.20
No se convierten en gates absolutos despues del resultado.

## Bootstrap (SS15)
10.000 remuestreos. Unidad = IMAGE TARGET; TRUE y FALSE del mismo target se mueven juntos.
IC95 para: ERROR_CATCH_RATE alt · CORRECT_PASS_RATE alt · BALANCED_QA alt ·
DELTA_BALANCED_QA · DELTA_TRUE_ARCH_PASS · PASS_ASYMMETRY · CATCH_ASYMMETRY.

## Pairwise (SS16)
Distribucion 3x3 completa por imagen e IDEAL_PAIR_RATE. Comparacion target por target contra E21.

## Stop rules
Ningun veredicto abre GPS, RES ni el tercer plano. Ni siquiera E22-A.
E22-A -> STOP, unico siguiente permitido E23 en un prompt humano posterior.
E22-B -> STOP, decision humana posterior, sin adaptar el banco.
E22-C / E22-D -> STOP, SEMANTIC QA PATH CLOSED UNDER CURRENT VISUAL EVIDENCE.
E22-F -> STOP, limitacion de entorno.
Prohibido tras ver resultados: probar otro modelo, mover thresholds, reinterpretar gates,
excluir recetas, rerun selectivo, elegir la mejor de varias corridas, ensemble, cambiar semilla.
