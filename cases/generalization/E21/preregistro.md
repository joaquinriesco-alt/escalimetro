# E21 — PRE-REGISTRO
# Escrito y hasheado ANTES de la primera inferencia. PROMPT_FROZEN = TRUE desde ese momento.

## Base
HEAD             b5152b06ab5add1cdad8ef292a986e343aae262b   (e20)
rama de trabajo  e21, creada desde b5152b06
BACKUP_GATE      PASS (origin/e20 == b5152b06ab5add1cdad8ef292a986e343aae262b, verificado con
                       git fetch + git ls-remote en la maquina del usuario)
main             c6de3f9646047eeba209c5d3d4ef5e6ccb85c26f  (sin mover)

## Hipotesis
No "que es este objeto", sino: el sistema determinista afirma que este objeto es X;
esa afirmacion, es visualmente consistente con el dibujo, o deberia revisarla un humano?

## Banco (congelado)
tests/fixtures/semantic_context/context_bench_scene.py
SHA256 2b3e2eb06248f3897b4bf663ce39930fc111b59560ccffd7cac8478141be6f81   (== E19/E19.1/E20)
72 imagenes FULL_CONTEXT, 36 ARCH y 36 FURN. Los 72 SHA verificados uno a uno contra
cases/generalization/E19_1/eval_manifest.json antes de este pre-registro.
Nada del banco se modifica ni se corrige.

## Diseno contrafactual
Por cada imagen, DOS evaluaciones independientes sobre la MISMA imagen (mismo SHA).
Unica variable: ASSERTED_ROLE.
  ARM TRUE  : se afirma el rol verdadero.
  ARM FALSE : se afirma el rol invertido.
72 TRUE + 72 FALSE = 144 evaluaciones.
Balance: 36 TRUE-ARCH, 36 TRUE-FURN, 36 FALSE-ARCH (afirmando ARCH sobre muebles),
         36 FALSE-FURN (afirmando FURN sobre recintos).

## Prompt
cases/generalization/E21/prompt_qa_congelado.txt
SHA256 ab58d99ebe98923dff4cb2d1af43866630c954574b18a4db6c6ef920ca36170d
Contiene el marcador {ASSERTED_ROLE}, sustituido en cada llamada por exactamente uno de los dos
nombres de rol. Ese es el unico texto que cambia entre llamadas. Congelado: no se cambia una palabra
despues del primer resultado.
El prompt pide tambien un campo `evidence` de una frase: se guarda para auditoria y NUNCA puntua
(§18). El contrato de decision es exactamente `qa_verdict` con los tres valores del §7.

## Protocolo
144 evaluaciones. UNA imagen + UNA assertion por evaluador. Evaluador nuevo cada vez, sin memoria,
sin conversacion persistente, sin respuestas previas, sin ground truth, sin repo, sin documentos de
ciclos anteriores, sin GPS/RES, sin tercer plano.
Tool restriction: Read solo sobre la ruta explicita. Sin Glob, Grep, Bash, WebSearch ni listado.
BATCHING = NONE.
Parametro de modelo: opus. Sesion configurada: claude-opus-5.
PROVIDER_IDENTITY = UNKNOWN.  PRODUCTION_REPRODUCIBILITY = NOT_PROVEN.
Fallo tecnico: una sola repeticion con la MISMA imagen, assertion y prompt, registrando
TECHNICAL_RETRY = TRUE. No se selecciona respuesta por calidad.

## Orden
SEMILLA = 2101, numpy default_rng, sobre las 144 assertions mezcladas (TRUE/FALSE y ARCH/FURN
completamente entremezcladas). Define UNICAMENTE el orden.
Las llamadas se despachan en 12 grupos de 12 siguiendo ese orden, con una restriccion adicional
declarada AQUI, antes de correr: ningun grupo contiene los dos brazos de la misma imagen (§12).
Cada evaluador es independiente y no ve las otras llamadas de su grupo; el agrupamiento es solo
concurrencia de despacho.

## Metricas congeladas (§13)
FALSE assertions : ERROR_CATCH_RATE = fraccion enviada a REVIEW.  overall / falsa-ARCH / falsa-FURN.
TRUE  assertions : CORRECT_PASS_RATE = fraccion marcada CONSISTENT. overall / true-ARCH / true-FURN.
Ademas: TRUE_ASSERTION_REVIEW_RATE, FALSE_ASSERTION_CONSISTENT_RATE,
        INSUFFICIENT_RATE (true / false / total),
        BALANCED_QA_ACCURACY = (ERROR_CATCH_RATE + CORRECT_PASS_RATE) / 2.
Carga (§14): P(REVIEW|correct), P(REVIEW|incorrect); EXPECTED_REVIEW_RATE y
        EXPECTED_REVIEW_PRECISION para tasas de error determinista 1 %, 5 %, 10 %, 20 %, 50 %.
Pairwise (§17): IDEAL_PAIR_RATE y la distribucion completa de los 3x3 pares por imagen.
Bootstrap (§16): 10.000 remuestreos, unidad = IMAGE TARGET, manteniendo juntos los dos brazos.
        IC95 de ERROR_CATCH_RATE, CORRECT_PASS_RATE y BALANCED_QA_ACCURACY.
No se cambia ninguna definicion despues de ver resultados. Sin confidence, sin thresholds,
sin calibracion (§19).

## Gates congelados (§15)
E21-A PASS solo si TODOS:
  ERROR_CATCH_RATE overall        >= 0.80
  ERROR_CATCH_RATE por clase      >= 0.70
  CORRECT_PASS_RATE overall       >= 0.75
  CORRECT_PASS_RATE por clase     >= 0.65
  FALSE_ASSERTION_CONSISTENT_RATE <= 0.15
  TRUE_ASSERTION_REVIEW_RATE      <= 0.25
  INSUFFICIENT overall            <= 0.15
  BALANCED_QA_ACCURACY            >= 0.775
E21-B HIGH DETECTION / HIGH REVIEW BURDEN
E21-C LOW DETECTION
E21-D ASYMMETRIC QA
E21-E EXPERIMENT INVALID
E21-F ENVIRONMENT LIMIT

## Stop rules
Solo E21-A autoriza E22 (GPS + RES). Cualquier otro resultado: STOP total, sin abrir GPS ni RES,
sin E21.1, sin rediseno de prompt, sin tocar runtime, sin abrir el tercer plano.
Prohibido tras ver resultados: mover thresholds, reinterpretar gates, excluir recetas, rerun
selectivo, elegir la mejor de varias corridas, cambiar modelo, ensemble o cambiar semilla.

## Interpretacion permitida si E21-A
"En un banco contrafactual controlado, una capa semantica detecta interpretaciones deterministas
incorrectas sin enviar a revision una fraccion excesiva de las correctas." Nada sobre planos reales,
deteccion de muros, generalizacion ni validacion de produccion.
