# E37 — INTERNAL RECONSTRUCTION LAB: el instrumento para aprender CREAR PLANO

CREAR PLANO es core (D-001) y hasta E37 no existía ni una línea que lo intentara. E37 no construye
el motor ganador: construye el **banco de pruebas** donde se comparan motores de reconstrucción de
forma reproducible, sin mirar el plano real antes de tiempo, y midiendo cuánto trabajo humano hace
falta para llegar a una planta útil. La TASK es [`tasks/E37.md`](../tasks/E37.md); el resultado,
[`reports/E37_REPORT.md`](../reports/E37_REPORT.md).

---

## 1. Qué es, en una pantalla

`/lab/reconstruction/` — se llega desde Ajustes → Herramientas técnicas. El flujo:

```
PROYECTOS → NUEVO PROYECTO → INPUTS / PLANO REAL OCULTO → MOTOR → GENERAR → RESULTADO →
CALIFICAR → CORREGIR → NUEVA CORRIDA → COMPARAR → REVELAR
```

Un **proyecto** junta fotos (el input principal), videos y documentos (se guardan aunque ningún
motor los use todavía), datos declarados (superficies, dormitorios, baños, niveles, contexto) y,
opcionalmente, el **plano real**, que queda oculto. Cada **corrida** es inmutable. Una **corrección**
en lenguaje natural crea una corrida hija. Al final, una persona **revela** el plano real.

## 2. Arquitectura

| capa | dónde vive | qué hace |
|---|---|---|
| motor histórico | `src/escalimetro/` | **intocable** (D-008). E37 no lo importa. |
| contrato v1 | `webapp/domain/reconstruction/contract.py` | la representación estructurada y su validación |
| dibujo | `…/render.py` | el SVG, dibujado desde el contrato |
| proyectos e inputs | `…/projects.py` | proyectos, inputs, datos declarados, cierre, bitácora |
| plano real | `…/groundtruth.py` | carga, ocultamiento y reveal. Nada que arme la entrada de un motor lo importa |
| corridas | `…/runs.py` | crear, ejecutar en cola, calificar, linaje, comparación, métricas |
| motores | `…/engines/` | registro + adaptadores (`openai_direct`, `fixture_replay`) |
| superficie | `webapp/reconstruction.py`, `webapp/templates/recon/` | blueprint `/lab/reconstruction` |
| datos | `DATA_DIR/reconstruction/<proyecto>/` y `DATA_DIR/reconstruction_gt/<proyecto>/` | inputs y corridas; el plano real en otra raíz |

## 3. Por qué tablas propias, y el plano real en otra raíz

Las tablas son `recon_*`, sin clave foránea a `properties`. Es el mismo argumento que E17: un
proyecto de reconstrucción metido en `properties` aparecería en la portada del LAB, en los conteos
del piloto E36 y recibiría una concesión de pack al siguiente arranque. Un test recorre las
quince tablas del resto del producto después de un flujo completo y exige cero filas.

El plano real vive en `recon_ground_truth` y en `DATA_DIR/reconstruction_gt/`, **fuera** de la
carpeta del proyecto. No es prolijidad: es lo que hace que la ceguera no dependa de que nadie mire.

## 4. El contrato v1

`escalimetro.reconstruction.v1`. La fuente de verdad de una corrida es esto, no una imagen:

- `outcome`: `RECONSTRUCTED` · `INSUFFICIENT_EVIDENCE` · `CLARIFICATION_REQUIRED`. Los tres son
  resultados válidos; ninguno se maquilla.
- `rooms[]`: id, etiqueta, tipo, nivel, **polígono en un marco normalizado 0..1** (x a la derecha,
  y hacia abajo) **o `null`** si el motor sabe que el recinto existe pero no dónde, superficie
  estimada o `null`, confianza 0..1, evidencia (ids de fotos + observación), incertidumbre.
- `connections[]`: puerta, abertura, contiguos o desconocida, con confianza y evidencia.
- `relations[]`: posición relativa explícita, útil para recintos sin polígono.
- `footprint`: ancho y fondo en metros **sólo** si el motor los estima, con de dónde salen.
- `uncertainties[]`, `missing_evidence[]`, `clarification`, `correction`.

El esquema es compatible con el modo estricto de salida estructurada de OpenAI (todo obligatorio,
lo opcional anulable, sin cotas numéricas). Las cotas y las referencias cruzadas las revisa
`contract.validate()`: una salida que no cumple deja la corrida `FAILED` con `CONTRACT_INVALID`.

El SVG se dibuja una vez, al cerrar la corrida, y se guarda con su sha256: si el dibujo cambia
mañana, las corridas viejas siguen mostrando lo que mostraban. Los recintos de confianza baja van
punteados; los que no tienen polígono quedan en una franja «sin ubicar». Todo texto del motor se
escapa.

## 5. Registro de motores

La UI no conoce ningún motor por nombre: lista `engines.catalog()`. Agregar uno:

```python
from webapp.domain.reconstruction import engines

class ColmapMasVlm(engines.EngineAdapter):
    engine_id = "colmap_vlm"
    name = "COLMAP + VLM por recinto"
    version = "1"
    provider = "local + openai"
    pipeline = "estructura por COLMAP, semántica por VLM, ensamblaje propio"
    capabilities = ("photos", "video", "declared_data", "correction", "clarification")
    paid = True

    def availability(self): ...          # AVAILABLE, o UNAVAILABLE con razón
    def default_params(self): ...        # se congelan en la corrida al crearla
    def reconstruct(self, req): ...      # EngineRequest → EngineResult (contrato v1 sin validar)

engines.register(ColmapMasVlm())
```

Lo que recibe un motor es `EngineRequest`: imágenes en memoria con un id opaco, los datos
declarados, parámetros y, si es una corrección, el plano anterior y la instrucción. Ni rutas, ni
nombre del proyecto, ni nombres de archivo. Metadatos por motor: `engine_id`, nombre, versión,
proveedor, modelo, pipeline, disponibilidad, capacidades, parámetros, si cuesta dinero y un aviso
si no es una reconstrucción real.

## 6. Los dos motores de E37

**`openai_direct` — OpenAI multimodal directo.** Fotos + datos declarados → contrato v1 en un
paso, vía `POST /v1/responses` con salida JSON estricta. Modelo `gpt-5.6-sol` por defecto,
configurable con `ESCALIMETRO_RECON_OPENAI_MODEL`; el modelo se congela en la corrida al crearla.
Fotos reducidas a 1600 px en el lado mayor. `store: false`. Sin `OPENAI_API_KEY` aparece
`UNAVAILABLE / MISSING_CREDENTIAL` y no toca la red; con clave, **cada corrida y cada corrección
exigen marcar la confirmación de gasto**. Sin reintentos: reintentar es otra corrida. Costo: el repo
no tiene precio de lista para este modelo, así que queda `unknown` y se guardan los tokens.

**`fixture_replay` — FIXTURE.** Sólo existe con `ESCALIMETRO_RECON_FIXTURE=1`. Devuelve siempre la
misma planta de un 2D/2B, no mira las fotos, y corrige con una regla de texto («<recinto> más
grande / más chico»; si no nombra un recinto, pide aclaración). Lo dice en cada pantalla. Sirve
para recorrer el flujo y sacar las capturas del REPORT sin gastar; **no es un motor A, B ni C**.

## 7. Corridas inmutables

Una corrida congela al crearse: motor y versión, parámetros, ids y sha256 de los inputs que el
motor va a recibir, datos declarados, commit del código y estado del plano real. Al terminar guarda
salida, advertencias, versión y sha256 del prompt, lo que se mandó (sin imágenes), tokens, latencia,
costo y artefactos (`output.json`, `plan.svg`, `request.json`, `response.json`) con sus sha256.

La inmutabilidad la hace cumplir SQLite con triggers —los primeros del repo—: una corrida
terminada no se modifica, su identidad no cambia ni en cola, ninguna se borra; calificaciones,
juicios y bitácora son de sólo inserción; revelar no se deshace y el plano revelado no se reemplaza.

Una corrida que **falla después de hablar con el proveedor** —contrato inválido, respuesta cortada,
JSON roto, negativa— igual guarda lo que costó: latencia, tokens, versión del prompt, qué se mandó
(`request.json`) y la respuesta cruda (`response.json`). Esa llamada se pagó.

La ejecución corre en un hilo de fondo. Al reiniciar, lo que quedó en vuelo se cierra `FAILED` y
**no se reanuda**: reanudar sería volver a pagar sin que nadie lo pidiera. Si un segundo proceso
contra el mismo volumen (otro `wsgi.py`) da por muerta una corrida que en realidad seguía, el
resultado tardío no se escribe en ella: queda en la bitácora como `LATE_RESULT_DISCARDED`, con sus
tokens y su latencia. Un input que cambió en
disco desde que se creó la corrida la hace fallar (`INPUT_CHANGED`) en vez de ejecutarla sobre otra
cosa. Los inputs se retiran, no se borran: una corrida vieja los sigue citando.

## 8. La ceguera del plano real, en capas

1. otra tabla y otra raíz de disco;
2. `runs` y `engines` no importan `groundtruth` (lo verifica un test estático);
3. la entrada del motor sale sólo de los ids de inputs congelados en la corrida;
4. un input idéntico al plano real se rechaza, en los dos sentidos; una foto que **parece** un plano
   se marca con el mismo clasificador del ingest de avisos;
5. antes del reveal la UI sabe una sola cosa —que existe—; la ruta que lo sirve responde 404 y la
   bitácora no guarda ni nombre ni hash;
6. revelar es un POST con confirmación, queda en la bitácora y lo protege un trigger;
7. un motor espía corre generación, corrección, aclaración y respuesta, y un test busca el plano
   real en todo lo que recibió: bytes, base64, sha256, prefijo, md5, nombre, carpeta y una marca
   embebida en el PNG.

Límite honesto: un adaptador es código Python dentro del mismo proceso. Nada le impide abrir el
disco por su cuenta. La garantía es de interfaz, y está probada; no es un sandbox.

## 9. Métricas 90/10

Por proyecto, cada dato por separado y **sin puntaje compuesto**: prompts humanos (en el proyecto y
en la línea de la corrida final), minutos humanos si se registraron, calificación de la corrida
final, si hizo falta CAD manual, recintos detectados / esperados (los esperados, sólo después de
revelar) y juicio humano de adyacencias, posición relativa y utilidad de la geometría. Lo que falta
dice que falta.

## Cómo ejecutarlo

Sin gastar, con el FIXTURE y una carpeta de datos propia (nunca `.data-lab`, que es el piloto E36):

```bash
ESCALIMETRO_DEV=1 ESCALIMETRO_DATA_DIR=./.data-e37 ESCALIMETRO_MIGRATE=0 ESCALIMETRO_RECON_FIXTURE=1 PYTHONPATH=src PORT=8037 .venv/bin/python wsgi.py
```

Con OpenAI real: la clave va en el entorno **del servidor**, sólo por presencia. Tres cuidados:

- **pon `ESCALIMETRO_PASSWORD`**. En modo DEV sin contraseña el servidor escucha en `0.0.0.0` sin
  pedir credenciales: cualquier equipo de la red podría lanzar corridas pagas o revelar el plano;
- no exportes la clave en la terminal donde corres `pytest`: `tests/test_e08_ai.py` hace una
  llamada paga real cuando encuentra `OPENAI_API_KEY`;
- todo POST de esta superficie tiene que traer `Origin` (o `Referer`) del mismo host y esquema; el
  navegador lo manda solo. Un script tiene que agregarlo, por ejemplo
  `curl -H 'Origin: http://localhost:8037' -F name=... http://localhost:8037/lab/reconstruction/nuevo`.
  Sin esa cabecera la respuesta es 403: es la guardia contra un formulario de otro sitio que
  dispare una corrida paga con las credenciales guardadas del navegador.

Variables nuevas (nombres en `.env.example`): `ESCALIMETRO_RECON_OPENAI_MODEL`,
`ESCALIMETRO_RECON_FIXTURE`, `ESCALIMETRO_RECON_MAX_REQUEST_MB` (tope de un envío en esta superficie,
1200 MB por defecto) y `ESCALIMETRO_RECON_MAX_VIDEO_MB` (500 MB por video).

## Cómo cargar Piso Ricardo Lyon I (el benchmark histórico)

1. Nuevo proyecto: «Piso Ricardo Lyon I, Providencia»; superficie total 87, útil 76, dormitorios 2,
   baños 2, niveles 1.
2. Fotos: las 34, JPG o PNG (HEIC hay que exportarlo a JPG antes). Se pueden elegir todas juntas o
   en lotes; revisar que ninguna quede marcada «parece un plano», y retirarla si es el plano.
3. Plano real: el plano del aviso o del corredor, PDF o imagen. Queda oculto.
4. Generar con `openai_direct` marcando la confirmación de gasto. Calificar. Corregir con frases
   como las de la prueba de 2026-08-16 («el dormitorio 2 está al fondo», «la franja de baños va
   entre los dormitorios»), hasta tres.
5. Comparar las corridas, revelar, anotar recintos esperados y los tres juicios.

La línea base histórica (inventario ~9/10, conexiones ~80 %, posiciones ~60–65 %, forma ~55–60 %,
proporciones ~50 %) es **referencia, no verdad actual**: el modelo de aquella sesión no quedó
registrado.

## Lo que E37 NO hace

Motores COLMAP, Plane-DUSt3R o de profundidad (el registro los admite sin tocar la UI) · CAD,
edición de muros o arrastre · autenticación nueva, facturación, CRM, colaboración, BI · un puntaje
de calidad compuesto · llamadas pagas desde tests, arranque o migraciones · tocar `src/`, E36 o E17.

## Deuda conocida

- El video y los documentos se guardan pero ningún motor los consume todavía; cada corrida lo dice.
- La numeración «Foto N» de la página del proyecto es la de los inputs activos; la de una corrida
  es la de los inputs que esa corrida recibió. Pueden diferir si se retiran o agregan fotos.
- No hay precio de lista para `gpt-5.6-sol`: el costo real hay que leerlo en la cuenta del
  proveedor hasta que alguien registre uno fechado.
- El límite de escritura del adaptador es de interfaz, no de proceso (§8).
- `store.reset_orphans()` corre en cualquier proceso que llame `create_app()` —`wsgi.py` lo hace al
  importarse—, no sólo en el servidor vivo. E37 se protege del efecto (resultado tardío en la
  bitácora, nada escrito en una corrida ajena), pero la causa es de toda la app y no se tocó.
- Un video se carga entero en memoria para un motor que declare la capacidad `video` (hasta 500 MB
  por defecto). Ningún motor de E37 la declara.
