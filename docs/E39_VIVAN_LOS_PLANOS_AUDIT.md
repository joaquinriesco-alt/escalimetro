# E39 — VIVAN LOS PLANOS: auditoría y plan de simplificación

> Diagnóstico y plan. **No cambia producto, doctrina, pricing ni código.** Nada se borró.
> Base auditada: `auto/m03_1-issue-3 @ 9a4e83a` + la TASK ([`tasks/E39.md`](../tasks/E39.md)).
> Todo lo que cita una ruta se leyó en el repo al escribir esto; lo que no se pudo verificar lo dice.

## 0. Cómo leer este documento

**North Star aprobado (Joaquín, 2026-10-01):** *PLANOS QUE AYUDAN A VENDER.* El plano es el
vehículo; se vende el potencial del espacio.
**Secuencia:** PLANO EXISTENTE → PLANO CORPORATIVO → CABIDA → LAYOUTS → VISUALIZACIÓN OPCIONAL.
**Prueba de cada pieza:** *¿esto hace que el plano ayude más a vender o a entender el potencial del
espacio?* Si no, no pertenece al core.

**Tensión con la doctrina vigente (se reporta, no se resuelve).**
[`PRODUCT_DOCTRINE.md`](ai-development/PRODUCT_DOCTRINE.md) (D-001) dice «core = CREAR PLANO +
MEJORAR PLANO» y pone **cabida, layouts, PRO, staging, video** en «lo que NO es core». El North
Star de E39 pone **Plano Corporativo → Crear Plano → PRO Layouts** como prioridad de producto, es
decir, PRO/Layouts como tercer escalón vendible. Son compatibles en el orden (los dos primeros
escalones son el core de D-001), pero **no hay decisión explícita** que mueva «layouts» fuera de
«aplicación». Este documento los trata como el tercer escalón **porque la TASK lo aprueba así**,
y deja la reconciliación de D-001 como decisión pendiente (§5, P-4). La doctrina no se tocó.

---

## 1. Inventario actual contra el North Star

### 1.1 Superficies web (qué existe hoy)

Todas las rutas están detrás de HTTP Basic con **una sola cuenta compartida**
(`webapp/auth.py`). **No existe ninguna página pública**: ni landing, ni intake anónimo, ni
pricing visible, ni checkout. `webapp/domain/proposal.py` lo declara por escrito: no hay enlace
anónimo porque abrirlo expondría el material de todas las propiedades.

| superficie | ruta | origen (archivo) | qué es hoy |
|---|---|---|---|
| Biblioteca de plantas | `/`, `/upload`, `/case/*`, `/run/*` | `webapp/app.py` | herramienta técnica E27: casos, corridas A/B/C, revisión, JSON |
| Cola de revisión | `/review/*` | `webapp/app.py` | QA humano interno antes de publicar al cliente |
| Producto / ajustes | `/settings*` | `webapp/app.py`, `domain/entitlements.py` | modo de producto por cuenta, presets, estilos, ambientación |
| Propiedades (cliente) | `/properties/*` | `webapp/customer.py` | propiedad, activos, programa, fits, propuesta, packs ZIP, marca |
| LAB | `/lab/*` | `webapp/lab.py` | consola simple E33: «Mis propiedades» → Pack 1 / Pack 2, evaluación, piloto de geometría, benchmark, debug |
| Ambientación | `/staging/*` | `webapp/staging_ui.py` | cola y revisión de staging virtual; bloqueada sin proveedor |
| Potencial | `/property/*` | `webapp/potential.py` | ingest de URL + diagnóstico/scoring de la publicación (E17) |
| Reconstrucción | `/lab/reconstruction/*` | `webapp/reconstruction.py` | laboratorio de CREAR PLANO (E37), plano real oculto |
| Salud | `/healthz` | `webapp/app.py` | liveness; no es producto |

**Navegación por marco** (cinco marcos distintos, uno por superficie):
`templates/base.html` (herramienta interna: LAB, Plantas, Revisión, Propiedades, Revisiones JSON,
Ambientación, Producto), `lab/base.html` («Mis propiedades · Ajustes»), `customer/base.html`
(«Mis propiedades · Nueva propiedad · Mi marca»), `potential/base.html`, `recon/*`. E33
(`docs/E33_SIMPLE_PRODUCT_LAB.md`) ya había diagnosticado «varias aplicaciones dentro de una
aplicación» y simplificó el LAB; los otros marcos siguen.

### 1.2 Pricing visible / configurado

- **Visible al usuario: ninguno.** Ninguna plantilla ni ruta muestra precio.
- **Configurado en código: ninguno.** `webapp/domain/grants.py` dice «no hay checkout, ni Stripe,
  ni facturas»; `entitlements.py` es «modelo de derechos, no de cobro» (`ONE_OFF` = «Pack de
  publicación», `PRO` = «Escalímetro Pro»).
- **Documentado, en tres lugares que no coinciden entre sí:**
  1. `docs/E30_PRODUCT_DIRECTION.md`: «~USD 100 / propiedad» (Pack) y «cuota mensual» (Pro). Un
     docstring de `grants.py` repite «cien dólares».
  2. North Star pegado en E39: Plano Corporativo **$10.000 CLP**, Crear Plano **≈ $50.000 CLP**,
     PRO **≈ $150.000 CLP/mes**.
  3. Decisión posterior del mismo 2026-10-01 (según la TASK): **0,25 UF** mejorar, **1 UF** crear.
  No se elige ninguna. Ver P-1.
- **Aviso:** el repo es público (DR-2) y (1) ya está publicado. Publicar (2) o (3) en una landing
  antes de cerrar P-1 repetiría ese problema.

### 1.3 Clasificación

Leyenda: **M**antener · **S**implificar · **E**liminar del producto visible (puede seguir interna) ·
**C**ambiar · **K**onstruir. Nada se elimina del repo.

| # | pieza (dónde vive) | clase | por qué, contra el North Star |
|---|---|---|---|
| 1 | **Ninguna entrada pública** (no existe) | **K** | El visitante no tiene dónde entrar. Es la brecha mayor. |
| 2 | **Plano comercial** — `domain/commercial.py` (`commercial_svg`), `shellview.py`, `domain/floorplan.py` | **M** | Es exactamente el «plano corporativo» en germen: planta limpia desde la geometría confirmada, fachada, escala, pie sobrio. Calidad sin medir (E36 1/10). |
| 3 | **Motor de plano → `floorplate.json`** (`src/escalimetro/`, `engine.py`, `intake.py`, `detected.py`) | **M** | Es lo que convierte un PDF/JPG en geometría. Congelado (D-008); no se toca. |
| 4 | **Revisión humana de geometría** (`/case/*/confirm`, `lab/revisar-plano`, `/lab/*/confirmar-geometria`) | **S** | Hoy es un formulario de ingeniero (marcar escala, semilla, entrada, ok/fix por elemento). Para el concierge inicial sirve interna; hay que reducirla a lo mínimo que un operador hace en minutos. |
| 5 | **LAB «Mis propiedades» → Pack 1** (`lab.py`, `domain/lab.py`, `templates/lab/*`) | **S** | Es el flujo operador más cercano al producto (subo plano → miro resultado → califico). Hay que recortar secciones (`resumen, plano, fotos, material, prospectos, pack, actividad`), evaluación, piloto, debug, benchmark. Sigue interno. |
| 6 | **Pack de publicación / marketing pack ZIP** (`domain/packs.py`, `/properties/*/pack.zip`) | **C** | Hoy entrega plano + 1 layout + fotos + ambientación. El entregable del North Star es **el plano corporativo**; el layout y la visualización pasan a opcionales. La regla «el manifiesto dice la verdad» (no incluir lo no generado) **se mantiene**. |
| 7 | **Branding** (`domain/branding.py`, `/properties/brand`) | **M** | La marca de la corredora sobre el plano es parte de «corporativo». La regla «un pack BASE nunca lleva marca de prospecto» se mantiene. |
| 8 | **Propuesta HTML autocontenida** (`domain/proposal.py`) | **M** | Lámina de lectura con marca, sin JS; sirve de entregable publicable de PRO. |
| 9 | **Cabida / layouts CP-SAT, A/B/C** (`src/` motor, `domain/fits.py`, `briefs.py`) | **M** (interno) → **S** al exponer | Es el corazón de PRO (planta + programa → alternativas). Funciona. Exponerlo exige un solo flujo «planta + programa → alternativas». |
| 10 | **Presets de lugar de trabajo** (`domain/presets.py`: DENSE, BALANCED, COLLABORATIVE, EXECUTIVE) | **M** | Es el «programa» de PRO sin pedir un brief técnico. Sólo cambia qué se pide, no la geometría. |
| 11 | **Fit requests por prospecto** (`customer.py` `/fits*`, `domain/fits.py`) | **M** | Es literalmente «reutilizar la planta para distintos prospectos». Nunca destruye los fits anteriores. |
| 12 | **Entitlements ONE_OFF / PRO + concesiones** (`domain/entitlements.py`, `grants.py`) | **S** | El modelo de derechos sirve, pero está nombrado por el vocabulario viejo (Pack de publicación / Pro) y por límites (1 layout vs A/B/C, 1 imagen ambientada) que no son los tres productos del North Star. Hay que reetiquetar **cuando** se decida el pricing (P-1), no antes. |
| 13 | **Estilos visuales** (`presets.py` → `VISUAL_STYLES`: CORPORATE, CONTEMPORARY, CREATIVE, INDUSTRIAL, PREMIUM) | **C** | Hay **5**; el límite pedido es **2–3**. Los nombres y la elección son de Joaquín (P-2): no se proponen taxonomías aquí. Hoy sólo gobiernan la imagen de ambientación, no el plano. |
| 14 | **Ambientación / staging** (`/staging/*`, `domain/staging.py`, `providers/*`, `domain/pilot.py`, `visual.py`) | **E** | Complemento, no centro; sin proveedor aprobado ni credenciales. Fuera de la navegación visible. |
| 15 | **Benchmark de proveedores** (`/lab/benchmark*`, `benchmark.py`) | **E** | Herramienta de decisión de proveedor de staging. Interna. |
| 16 | **Ingest de URL + scoring de publicaciones** (`/property/*`, `domain/potential/*`) | **E** | D-001 ya lo marca «no core». El scoring no ayuda a que el plano venda. La parte «URL → fotos/planos» queda como infraestructura posible de Crear Plano. |
| 17 | **Reconstrucción** (`/lab/reconstruction/*`, `domain/reconstruction/*`) | **M** (interna) | Es el instrumento para medir Crear Plano; motor real nunca corrido. Insumo, no producto. |
| 18 | **Crear Plano como producto** | **K** | **No existe** (CURRENT_STATE: ninguna línea infiere un plano desde fotos). Para vender Crear Plano a corto plazo sólo cabe un proceso concierge (§2.4). |
| 19 | **Revisión de resultados A/B/C, `reviews.json`, evaluación** (`/run/*`, `lab/evaluaciones`, `/reviews.json`) | **E** | Herramienta de calibración interna de calidad. |
| 20 | **Cola de revisión** (`/review/*`) | **M** (interna) | Es el «humano en el medio» del concierge: se reaprovecha como cola de pedidos. |
| 21 | **Vistas debug / piloto / feedback** (`/lab/debug*`, `/lab/pilot/export.json`, `/lab/feedback.json`) | **E** | Operación. |
| 22 | **Ejecutor GitHub-native** (`.github/`, `scripts/auto_task.py`) | **M** (fuera de alcance) | Infra de desarrollo. E38 reveló que una ejecución exitosa **sin commits** puede cerrar verde (`VERIFY NOTHING`). Se registra; **no se repara en E39**. |

---

## 2. Producto mínimo propuesto

Secuencia estricta: **Plano Corporativo → Crear Plano → PRO Layouts.** Staging, video, scoring y
renders no aparecen en ningún punto de la oferta; si existen después, cuelgan del plano.

### 2.1 Qué ve un visitante
Una página única, pública, **sin login**, con: la frase del North Star; un ejemplo antes/después
de un plano (el que ya produce `commercial_svg`); tres tarjetas en este orden —*Plano
Corporativo*, *Crear Plano*, *PRO Layouts*— y un botón por tarjeta que lleva a un formulario.
**Sin** precio hasta cerrar P-1. **Sin** menú de herramientas, laboratorio ni «herramienta interna».

### 2.2 Qué puede comprar / solicitar
| escalón | qué solicita | qué recibe |
|---|---|---|
| **Plano Corporativo** | sube su plano (PDF/JPG/PNG) | plano limpio con marca, publicable |
| **Crear Plano** | no tiene plano útil: manda lo que haya (fotos, URL, superficie, dirección) | planta comercial **esquemática y referencial**, nunca presentada como levantamiento (D-001, principio 3) |
| **PRO Layouts** | una planta ya preparada + un programa (personas o preset) | 1..N alternativas de cabida por prospecto, con la marca del prospecto |

Cómo se cobra queda **fuera** de este documento (P-1).

### 2.3 Inputs mínimos
- Plano Corporativo: archivo del plano, nombre de la propiedad, superficie publicada (opcional),
  logo/color de marca (opcional; `domain/branding.py` ya lo soporta), contacto.
- Crear Plano: fotos y/o URL, dirección, superficie declarada, contacto. Es lo que ya recoge
  `webapp/reconstruction.py` como proyecto.
- PRO Layouts: la planta (reutilizada), **personas** y uno de los presets de lugar de trabajo
  (`presets.py`), nombre y logo del prospecto. Un brief avanzado es opcional.

### 2.4 Qué queda humano / concierge al inicio
Todo lo que hoy ya es humano y no conviene automatizar aún: confirmar escala y entrada, revisar
la geometría detectada, publicar al cliente (`/review/*`, «Revisión del plano»), y para Crear Plano
**todo el trabajo**. El visitante no ve el laboratorio: el pedido entra por un formulario simple y
Joaquín (u operador) lo ejecuta en el LAB existente. La entrega inicial puede ser un enlace o un
archivo (la propuesta HTML y el ZIP ya son archivos). **Vender antes de automatizar la fábrica.**

### 2.5 Público vs interno
| público | interno (sigue existiendo, sin enlace público) |
|---|---|
| landing de tres escalones; formulario de pedido; (después) página de entrega al cliente con enlace con token | biblioteca de plantas, `/case`, `/run`, `/review`, `/lab` completo, `/properties`, `/staging`, `/property` (E17), `/lab/reconstruction`, benchmark, settings, debug |

Nota técnica: abrir **cualquier** ruta sin autenticar hoy expondría todo; lo público debe ser un
blueprint nuevo y mínimo, no una ruta suelta en los existentes (misma razón que da `proposal.py`).

### 2.6 Qué desaparece de la navegación pública
Ambientación/staging, benchmark, ingest de URL y scoring, reconstrucción, calificación A/B/C,
revisiones JSON, debug/piloto, «Producto/Ajustes» y el selector de modo. No se borra código ni
datos.

### 2.7 Dónde entran 2–3 estilos sin convertir el producto en un editor
Como **una selección única, al pedir el plano**, de entre 2–3 plantillas de presentación que
aplican a la **capa de presentación** del mismo plano (paleta, rotulado, pie); nunca a la
geometría. Hay un precedente de diseño en el repo: «un estilo no ve metros ni ventanas» y hay
test que lo verifica (`presets.py` §6). Hoy `PALETA` en `commercial.py` es **una sola** y los
estilos de `presets.py` sólo gobiernan la ambientación, así que **hay que construir** la
variante de plano. **Qué estilos son es decisión de Joaquín** (P-2) y, si no bloquea, se puede
lanzar con uno solo.

### 2.8 Cómo PRO reutiliza la planta para distintos prospectos/programas
Ya está modelado: una propiedad se prepara una vez y cada prospecto es un *fit request* nuevo
sobre la **misma geometría** (`domain/fits.py`; el segundo prospecto sale barato). Un fit =
nombre + marca + programa (preset + personas) → un BriefV1 → corrida del motor → alternativas →
propuesta/ZIP con marca del prospecto. El fit anterior se archiva, no se borra. Lo que falta no
es el modelo sino **exponerlo como un flujo único** «planta + programa → alternativas» (§4).
Alcance exacto de PRO: ver P-3.

---

## 3. Mapa de reutilización

**Reutilizable tal cual**
- Plano comercial desde geometría (`commercial.py`, `shellview.py`).
- Motor de planta y layouts (`src/`, congelado) y su cola (`engine.py`).
- Branding (`branding.py`), propuesta HTML (`proposal.py`), ZIP con manifiesto veraz (`packs.py`).
- Presets de programa (`presets.py` → `WORKPLACE_PRESETS`).
- Fits por prospecto (`fits.py`), cola de revisión (`/review/*`), `store`, migraciones.
- Upload y rasterizado de PDF (`intake.py`).

**Requiere adaptación**
- LAB → recortarlo a «subir plano → revisar → entregar» para operador.
- `packs.py`/`lab.py` Pack 1: que el entregable sea el plano corporativo y el layout/ambientación
  sea opcional.
- `entitlements.py`/`grants.py`: reetiquetar a los tres escalones **después** de P-1.
- Estilos: hoy 5 y sólo ambientación; pasar a 2–3 y a presentación de plano (P-2).
- Autenticación: de cuenta única a un mínimo que permita enlace de entrega con token (decisión
  técnica local, no de producto).
- `reconstruction.py`: proyecto de Crear Plano sin plano real oculto (hoy es un banco de pruebas).

**Falta**
- Landing y formulario de pedido público (blueprint nuevo y aislado).
- Entrega al cliente (enlace con token o archivo) y registro del pedido.
- Variantes de presentación del plano (2–3).
- Un motor real de Crear Plano (hoy sólo el instrumento; `openai_direct` nunca corrió).
- Cobro (no hay checkout; depende de P-1).
- Medición de la calidad del plano corporativo (E36 va 1/10).

**No vale la pena construir ahora**
- Staging, renders, video, reels, benchmark de proveedores; BFL.
- Scoring de publicaciones y búsqueda de oportunidades.
- Automatizar la «fábrica» completa (multi-tenant, roles, facturación) antes de vender.
- Editor/CAD, o corrección fina del plano por el cliente.
- Más verticales distintas de oficinas.

---

## 4. Plan de ejecución pequeño

Propuesta de **siguientes TASKs**, ordenadas y acotadas. **No se crean ahora**; cada una es de
ChatGPT/Joaquín. Ninguna toca `src/`.

| paso | TASK candidata | entregable verificable | depende de |
|---|---|---|---|
| 1 | **Landing pública mínima** (blueprint nuevo, sin login, sin precio) con la frase del North Star y las tres tarjetas | ruta pública que responde 200 sin auth; test de que el resto sigue protegido | — |
| 2 | **Pedido de Plano Corporativo** (formulario + subida + registro, sin cobro) | un pedido crea una propiedad/caso interno visible en `/review`; test de límites de subida | 1 |
| 3 | **Entregable Plano Corporativo** (una salida con marca desde `commercial_svg`, enlace con token o archivo) | plano publicable desde un caso real; sin servir material de otras propiedades | 2 |
| 4 | **Medir el plano corporativo** con el piloto E36 existente (10 planos reales) | informe de calidad con etiquetas humanas, sin relajar criterios | 3 (en paralelo) |
| 5 | **Recortar la navegación pública/operador** (ocultar, no borrar) | menús sin staging/benchmark/scoring/reconstrucción | 1 |
| 6 | **Pedido de Crear Plano concierge** (formulario + proceso manual; honesto: referencial) | pedido registrado y entrega esquemática etiquetada como referencial | 2 |
| 7 | **PRO Layouts: flujo único «planta + programa → alternativas»** sobre fits existentes | de una planta lista y un preset salen A/B/C con marca del prospecto | 3 |
| 8 | **Variantes de presentación del plano** | 2–3 plantillas que no alteren geometría (test) | **P-2** |
| 9 | **Cobro y pricing visible** | precios publicados y checkout | **P-1** |

Orden sugerido para vender antes de automatizar: **1 → 2 → 3** (primer producto vendible: Plano
Corporativo), en paralelo **4**; luego **5**, **6**, **7**; **8** y **9** cuando Joaquín decida.

---

## 5. Decisiones reales pendientes (sólo Joaquín)

**P-1 · DECISION_REQUIRED — pricing: CLP vs UF.** El North Star pegado dice $10.000 / ≈$50.000 /
≈$150.000 CLP/mes; una decisión posterior del mismo día dice 0,25 UF (mejorar) y 1 UF (crear).
No hay decisión explícita de cuál reemplaza a cuál, y de pasada no hay precio de PRO en UF.
Además E30 dejó «~USD 100/propiedad» en un doc público. **Bloquea:** paso 9 y cualquier precio
en la landing. **No bloquea:** pasos 1–8. No se resuelve por inferencia.

**P-2 · Los 2–3 estilos.** Cuáles son y cómo se llaman. Hoy hay 5 en `presets.py` (para
ambientación). **Bloquea sólo el paso 8**; se puede lanzar con un solo estilo.

**P-3 · Alcance de PRO que el North Star no resuelve.** Ejemplos: cuántas alternativas por
prospecto (hoy 1 en Pack, 3 en Pro); si PRO incluye marca de prospecto y regeneración (hoy sí); si
incluye ambientación (hoy sí, y aquí es «complemento»); modalidad mensual y si es por cartera o por
propiedad. **Bloquea:** paso 7 sólo en lo que cambie respecto de hoy.

**P-4 · Reconciliar D-001 con el North Star.** D-001 dice que layouts/PRO no son core; el North
Star los pone como tercer escalón de producto. Si los tres escalones reemplazan el «core» de
doctrina, es un cambio de `PRODUCT_DOCTRINE.md`, que sólo se cambia por decisión explícita
(`DECISIONS.md`). **No se modificó.** Se arrastra también DR-6 (si el congelamiento de `src/` sigue
bajo el core nuevo).

**P-5 · ¿Para quién?** Sigue abierta la pregunta de CURRENT_STATE («para quién es ESCALÍMETRO»):
el material real hoy es oficinas de corredoras. El North Star habla de «oficina» y «prospecto»,
pero no lo declara como decisión de vertical.

Lo que **no** es decisión de Joaquín y se resuelve técnicamente al implementar: nombre de
blueprint, esquema de tokens de entrega, formato del pedido.

---

## 6. Hecho registrado, no reparado

E38 (`tasks/E38.md`) **no implementó nada**: el run `36927264632` terminó verde pero Claude dejó 0
commits y 0 archivos (`VERIFY NOTHING`). No cuenta como avance de producto. El ejecutor trata mal
ese caso; **no se repara en E39** (fuera de alcance; infraestructura).

## 7. Cómo se verificó

Lectura directa de: `webapp/app.py` (rutas y blueprints), los cinco blueprints, los tres marcos
de navegación, `domain/entitlements.py`, `grants.py`, `presets.py`, `packs.py`, `commercial.py`,
`fits.py`, `proposal.py`, `auth.py`; `docs/E30_PRODUCT_DIRECTION.md`, `docs/E33_SIMPLE_PRODUCT_LAB.md`,
`PLAN_CLEANING_DEFERRED.md`; `PRODUCT_DOCTRINE.md`, `DECISIONS.md`. Rutas contadas por grep de
`@bp.get/post` y `register_blueprint`. **No se ejecutó la app ni la suite completa**; la
calidad del plano corporativo no está medida y no se afirma.
