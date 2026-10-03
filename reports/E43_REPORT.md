# E43 REPORT

## Status
PASS

## Qué cambió
Cierra el circuito mínimo de Plano Corporativo, sin precio, pago ni email:

> **SUBIR → PREPARAR → REVISAR → GENERAR → APROBAR → COMPARTIR LINK**

**Flujo exacto del operador** (todo bajo HTTP Basic):
1. `/lab/pedidos/` → «Entrega» abre `GET /lab/pedidos/<request_id>`, que muestra la etapa derivada de
   artefactos: *sin preparar* · *planta aún no lista: requiere revisión* · *lista para producir* ·
   *candidato generado* · *aprobado · enlace listo*.
2. Si la planta no está lista, no hay botón de generar: se sigue por la propiedad del LAB (camino de E42).
3. Con la geometría lista, `POST …/generar` llama **exactamente** a
   `floorplan.publish_commercial_floorplan` (deja un único `FLOORPLAN_COMMERCIAL`; regenerar lo reemplaza).
4. `GET …/candidato.png` lo muestra internamente. No existe ningún enlace público todavía.
5. `POST …/aprobar` (botón **APROBAR PARA ENTREGA**) fija el asset, crea el token y pasa el pedido a
   `READY_FOR_DELIVERY`. El operador copia el enlace del detalle y lo envía a mano.

**Cómo se fija el asset aprobado.** `publish_commercial_floorplan` purga el comercial anterior al
regenerar, así que apuntar el enlace a ese asset lo cambiaría en silencio. Al aprobar se guarda una
**copia congelada** de tipo nuevo `FLOORPLAN_DELIVERED` (carpeta `delivered/`, mismo `sha256` en la
metadata). Regenerar no la toca. El POST de aprobar lleva el `asset_id` que el operador vio y se
rechaza (409) si ya no es el candidato actual.

**Esquema mínimo.** Tres columnas nuevas en `plano_requests` (en el `SCHEMA` y con migración en sitio
para bases de E42): `delivery_token`, `delivery_asset_id`, `approved_at`. Estado: `READY_FOR_DELIVERY`
(nunca `DELIVERED`: nada prueba que el cliente recibió el enlace).

**Cómo se respeta readiness.** `etapa()` y `generar_post` consultan `floorplan.technical_state(...)["ready"]`
(las compuertas existentes) antes de llamar a nada; sin geometría lista → 409, no se invoca la salida
ni se crea asset/token. Además `publish_commercial_floorplan` devuelve `None` por sí misma. No se
relajó ninguna confirmación.

**Contrato de token y ruta pública** (`webapp/entrega.py`, `webapp/public.py`):
- Token = `secrets.token_urlsafe(32)` → 43 caracteres `[A-Za-z0-9_-]` (256 bits), no secuencial.
  Cualquier otra forma → 404 sin tocar la base.
- `GET /planos/entrega/<token>` → página «Plano Corporativo listo» (`noindex`, sin `base.html`, sin menú).
- `GET /planos/entrega/<token>/plano.png` (`?descargar=1` fuerza descarga) → sólo el asset aprobado,
  `Cache-Control: private, no-store`.
- Resolución: token → pedido → `assets.get(delivery_asset_id, property_id)` (barrera de E28.2) y
  `kind == FLOORPLAN_DELIVERED`. Nunca se acepta un path ni un asset_id del usuario.
- Sin Basic. Es de sólo lectura: abrirlo no escribe nada.

**Idempotencia.** Aprobar de nuevo no rota ni cambia token, asset ni fecha (devuelve sin efecto). La
aprobación es un compare-and-set (`WHERE delivery_token IS NULL`); el que pierde borra su copia, sin
huérfanos. Cambiar lo ya aprobado exigiría una revocación explícita, que E43 no define.

## Archivos principales
`webapp/entrega.py` (nuevo) · `webapp/pedidos.py` (rutas de entrega; título sin email) · `webapp/public.py` · `webapp/store.py` ·
`webapp/domain/assets.py` (tipo `FLOORPLAN_DELIVERED`) · `webapp/templates/lab/pedido.html`,
`public/entrega.html` (nuevas) · `webapp/templates/lab/pedidos.html` · `tests/test_e43_plano_corporativo_entrega.py`.

## Tests
baseline:    suite completa no corrida
post-change: `tests/test_e43_plano_corporativo_entrega.py` 24 passed. Con E40/E41/E42: 96 passed.
E27, E28, E30, E32–E36 y `test_ai_handoff`: **420 passed, 1 failed** (el preexistente, abajo).
Suite completa (~12 min) **no corrida**; `test_e18_topology_representation.py` no se puede colectar
en este entorno (falta `skimage`), ajeno a E43.

## Acceptance criteria
1. PASS — `test_el_pedido_preparado_conserva_su_propiedad`.
2. PASS — `test_sin_geometria_lista_…`, `test_con_geometria_no_confirmada_…`: 409, salida no invocada, sin asset ni token.
3. PASS — `test_generar_usa_publish_commercial_floorplan_…` (espía; un único candidato tras regenerar).
4. PASS — `test_el_candidato_se_previsualiza_internamente…` y `test_toda_la_operacion_interna_exige_basic_auth` (401).
5. PASS — mismo test: sin token ni `/planos/entrega/` antes de aprobar; `test_un_pedido_sin_aprobar_…`.
6. PASS — `test_aprobar_persiste_asset_token_timestamp_y_estado`.
7. PASS — `test_la_ruta_publica_responde_sin_auth_…`.
8. PASS — `test_la_pagina_publica_no_expone_pii_ids_paths_ni_navegacion` (email, request/property/asset id, DATA_DIR, `/lab`).
9. PASS — `test_tokens_inexistentes_o_malformados_dan_404`.
10. PASS — `test_un_token_nunca_sirve_el_asset_de_otro_pedido` (asset de otra propiedad o de otro tipo → 404).
11. PASS — `test_repetir_la_aprobacion_es_idempotente`, `test_el_reclamo_de_aprobacion_es_atomico`.
12. PASS — `test_regenerar_no_cambia_el_plano_detras_del_enlace_aprobado`.
13. PASS — `test_abrir_el_enlace_no_cambia_el_estado_ni_escribe`.
14. PASS — `test_generar_aprobar_y_abrir_el_enlace_no_abren_red_ni_ejecutan_motor` (`socket.connect`, `Popen`, `engine.submit` prohibidos; sin imports ajenos en `entrega.py`/`public.py`).
15. PASS — E40/E41/E42 y LAB (E27–E36) verdes salvo el preexistente.
16. PASS — los tests cubren readiness, generación, preview, aprobación, token, 404, aislamiento, idempotencia y no-PII.
17. PASS — `git diff 6324b1f HEAD -- src/` → vacío (0 líneas).
18. PASS — este REPORT + `CURRENT_STATE.md`.
19. PASS — commit de implementación posterior al de la TASK.
20. PASS — sin merge, deploy ni movimiento de `main`.

## Evidencia
- `git diff 6324b1f HEAD -- src/` → 0 líneas.
- Preflight de la TASK: `tasks/E43.md` en `e43_corporate_plan_delivery`, base `auto/e42-issue-11` (lo
  verificó el preflight del ejecutor; no se reverificó acá).
- La generación se probó con el trazado sustituido (`_shell_of` y `commercial_svg`), pero con el
  `publish_commercial_floorplan` real —incluida su purga— y CairoSVG real. El trazado real sobre un
  shell confirmado del motor **no se ejercitó** en estos tests.

## Regresiones
Ninguna conocida. Falla `test_ai_handoff::test_el_main_declarado_es_el_de_origin_no_el_local`
(`origin/main` = `f466ccf`, la tabla declara `d097069`): preexistente desde E41, no se reparó.

## Limitaciones
- Una vez aprobado, no hay revocar ni re-aprobar otro candidato: para cambiarlo hace falta una
  decisión explícita (rotar/revocar token) que E43 no tomó. Regenerar sí es posible, pero no afecta el enlace.
- El enlace no vence y no hay registro de aperturas (a propósito: sin analytics).
- No se envía email: el operador copia y manda el enlace.
- Un fallo de generación inesperado fuera de `FloorplanError` se ve como 500.
- Sin capturas de pantalla.

## Hallazgo corregido en E43 (cambia E42)
E42 titulaba la propiedad «Plano Corporativo · <email>» y `commercial_svg` **dibuja ese título en la
imagen**: el email del cliente habría quedado impreso en el plano entregado por el enlace público.
Corregido: `pedidos.TITULO = "Plano Corporativo"` para las propiedades nuevas, y `generar_post` limpia
el título de las ya preparadas por E42 si contiene el email, antes de generar. Test:
`test_el_email_nunca_llega_al_titulo_dibujado_en_el_plano`. El operador sigue identificando el pedido
por su email en la bandeja. Es un cambio de privacidad local, no de producto.

## Decisiones requeridas
Ninguna.

## Commit / branch / PR
Rama `auto/e43-issue-12` (hija de `e43_corporate_plan_delivery`); la publica el workflow. Sin PR,
merge ni deploy.

## Exact next action
Auditar el circuito completo como producto (no ampliar features): recorrerlo con un caso real y
decidir qué falta para probarlo —en particular la ausencia de revocación y el trazado real sobre un
shell confirmado—.
Se escribe como TASK nueva desde `auto/e43-issue-12`.
