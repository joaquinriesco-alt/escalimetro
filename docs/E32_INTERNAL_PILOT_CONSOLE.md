# E32 — ESCALÍMETRO LAB: la consola interna

## Propósito

Una sola web interna para operar Escalímetro **sin terminal**: cargar una propiedad real,
procesarla con el motor real, mirar los resultados, aprobarlos o rechazarlos, y anotar qué
funcionó. Es el laboratorio de producto, no la web pública ni el producto final.

Y es, además, la sala de control que permite completar E31.1: el bake-off real de proveedores de
ambientación se arma, se lanza, se revisa y se decide desde acá.

## Rutas

| Ruta | Qué es |
|---|---|
| `/lab/` | Portada: resumen, propiedades con su avance y los bloqueos del piloto |
| `/lab/new` | Crear propiedad (paso 1) |
| `/lab/p/<id>` | Resumen: avance derivado, valoración, notas, últimos movimientos |
| `/lab/p/<id>/plano` | Subir plano, verlo, abrir la revisión técnica |
| `/lab/p/<id>/fotos` | Subir fotos, elegir la **foto principal** |
| `/lab/p/<id>/material` | Programa base, plano comercial, layout, ambientación |
| `/lab/p/<id>/prospectos` | Pro: fit requests, A/B/C |
| `/lab/p/<id>/pack` | Vista previa del pack, export, salida degradada |
| `/lab/p/<id>/actividad` | Línea de tiempo y notas de prueba |
| `/lab/config` | Modo de producto, marca, preparación del piloto |
| `/lab/benchmark` | Dataset, smoke tests, bake-off, resultados, aprobación |
| `/lab/review/next` | Siguiente candidato sin revisar |
| `/lab/feedback.json` | Feedback estructurado, para analizar después |

Las pantallas técnicas que ya existían y funcionan bien se reusan tal cual: el intake de E27.3
(`/case/<id>`) para revisar la planta, y la revisión de ambientación de E31 (`/staging/attempt/<id>`),
que ahora además tiene **modo ciego**.

## Flujo

```
crear propiedad → subir plano → ANALIZAR (intake E27.3: escala, acceso, confirmar lo detectado)
→ publicar material comercial → programa base → generar layout
→ subir fotos → elegir foto principal
→ ambientación (sólo con proveedor APROBADO) → revisión humana → aprobar
→ pack → descargar ZIP
→ [Pro] prospecto → A/B/C → propuesta y pack del prospecto
→ notas y valoración en cada paso
```

## El avance no se declara

Cada paso del checklist sale de un hecho: un archivo en el volumen, una fila en la base, un
artefacto del motor. **No hay ninguna ruta para marcar un paso como hecho**, y hay un test que lo
comprueba. Lo mismo la línea de tiempo: se deriva de los artefactos en vez de mantener una tabla de
eventos paralela que se desincronizaría el primer día que un camino nuevo olvide escribirla. Lo
único que se guarda son las acciones humanas que no dejan otro rastro: notas, valoraciones,
aprobaciones de proveedor y smoke tests.

## ONE_OFF

Una propiedad · un plano comercial · **un** layout representativo · **una** imagen ambientada
aprobada · pack descargable.

Los reintentos de ambientación son mecánica interna (tope de 3 por foto principal), no créditos del
cliente: la superficie de cliente no tiene ningún botón de «regenerar».

## PRO

Habilita prospectos: cada uno con su nombre, marca, headcount, forma de trabajo, estilo y su propio
A/B/C. Un prospecto nuevo no pisa a los anteriores. Se cambia de modo en `/lab/config`.

## Staging Lab

Para una propiedad: elegir foto principal, elegir estilo, generar, ver costo y latencia, comparar
original contra candidato (lado a lado, alternar, cortina), decidir fidelidad PASS/FAIL, calidad
1–5, aprobar o rechazar, reintentar.

**Tres cosas distintas que la consola no mezcla:**

| | Qué significa |
|---|---|
| Credencial presente | hay una clave en el entorno. Nada más. |
| Smoke test OK | ese proveedor respondió una vez con una imagen. Nada más. |
| **Proveedor aprobado** | una persona miró las tasas del bake-off y decidió. **Sólo esto** habilita que una imagen llegue a un cliente. |

Mientras nadie apruebe un proveedor, el producto dice `STAGING PROVIDER NOT YET APPROVED` y el pack
base se queda en `NEEDS_STAGING`. Se puede experimentar desde el benchmark, pero **un candidato
experimental no se convierte en entregable**: nace marcado, y aprobarlo no lo publica. Tampoco
revive si después se aprueba a ese mismo proveedor — lo que se generó antes de la decisión se
generó antes de la decisión.

`ESCALIMETRO_STAGING_PROVIDER` ya **no elige nada**. Se conserva sólo para que la consola pueda
decir que está puesta y que no manda.

## Bake-off desde la web

1. **Dataset** — se arma seleccionando fotos reales de cualquier propiedad, con sus rasgos
   difíciles (`WINDOWS`, `COLUMNS`, `DOORS`, `GLAZING`, `CEILING`, `CORNER`, `WIDE_ANGLE`,
   `EXTERIOR_VIEW`, `OPEN_PLAN`, `OTHER_DIFFICULT`). Contadores: N/8 fotos, N/3 espacios. El
   manifiesto `staging_benchmark_v1.json` se **genera** desde la base en cada cambio y se escribe
   en el volumen.
2. **Smoke tests** — una llamada real por proveedor. No aprueba, no selecciona, no publica.
3. **Bake-off** — proveedores con credencial (BFL excluido por licencia), corridas por foto, estilo
   fijo CONTEMPORARY. Muestra `fotos × corridas × proveedores = intentos` y el **gasto estimado**;
   exige confirmación explícita. Los intentos se encolan y la página sondea el progreso: la consola
   no se congela.
4. **Revisión a ciegas** — no se ve proveedor, modelo ni costo hasta guardar el veredicto. Botón
   «siguiente sin revisar» para recorrer 40 candidatos.
5. **Resultados** — por proveedor, con el rótulo **PILOT OBSERVED RATE**. Nunca «probado
   estadísticamente».
6. **Aprobación** — la consola muestra `GATE PASSED` / `GATE NOT PASSED` y **no aprueba a nadie**.
   Aprobar es un acto humano que guarda la evidencia (muestra, tasas, costo por aprobada, latencia).
   Un proveedor que no cumple la compuerta sólo se puede aprobar con motivo escrito, y queda marcado
   como `OVERRIDE` para siempre.

## Credenciales

Se configuran **una sola vez, fuera de la consola**: un archivo `.env` en la raíz del repo (ya está
en `.gitignore`), y se exporta antes de arrancar:

```bash
set -a; source .env; set +a
```

La consola **detecta** si existen y muestra booleanos y nombres de variable. Nunca un valor, ni un
fragmento, ni la longitud. «Sin terminal» empieza después de ese paso único.

## Cómo ejecutarlo localmente

```bash
cd ~/escalimetro-repo && git checkout e32_internal_pilot_console
ESCALIMETRO_DEV=1 ESCALIMETRO_DATA_DIR=./.data-lab PYTHONPATH=src PORT=8030 .venv/bin/python wsgi.py
```

Abrir **http://127.0.0.1:8030/lab/**.

Con credenciales:

```bash
set -a; source .env; set +a
ESCALIMETRO_DEV=1 ESCALIMETRO_DATA_DIR=./.data-lab PYTHONPATH=src PORT=8030 .venv/bin/python wsgi.py
```

## Resetear los datos de prueba sin tocar producción

Todo el estado vive bajo `ESCALIMETRO_DATA_DIR`. Para empezar de cero:

```bash
rm -rf ./.data-lab
```

Producción usa su propio volumen en Railway y no se ve afectada: el LAB no está desplegado.
Para importar los casos históricos (GPS 403 y 401) a un directorio nuevo, arrancar sin
`ESCALIMETRO_MIGRATE=0`.

## Limitaciones

1. **Sin roles.** Una cuenta compartida, como desde E28. Quien entra ve todo. Es la deuda
   estructural pendiente y lo primero antes de un cliente real.
2. **El bake-off real sigue sin correr**: faltan fotos reales y las dos credenciales. La consola
   existe precisamente para que eso deje de requerir terminal.
3. El intake de la planta se hace en la pantalla técnica de E27.3, que tiene otro aspecto. Funciona
   y está enlazada, pero no está unificada visualmente con el LAB.
4. Los layouts A/B/C tardan minutos; la página muestra el estado pero hay que recargar a mano.
5. El pack puede exportarse degradado, siempre con motivo escrito y declarado en el manifiesto.
