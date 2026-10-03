# E42 REPORT

## Status
PASS

## Qué cambió
Un pedido público `RECEIVED` (E41) se convierte, desde una bandeja interna protegida, en una
propiedad real del LAB que ya trae el plano del cliente como `FLOORPLAN_ORIGINAL`.

- **Ruta interna:** `GET /lab/pedidos/` (lista) y `POST /lab/pedidos/<request_id>/preparar`.
  Ambas con `@auth.require` (HTTP Basic del LAB). Sin credenciales: 401.
- **Listado:** referencia, fecha, email, archivo, estado, y «PREPARAR EN LAB» (si `RECEIVED`) o
  «Abrir propiedad» (si ya tiene `property_id`). Sin filtros, búsqueda, paginación ni notas.
- **Persistencia:** dos columnas nuevas en `plano_requests`: `property_id` y `prepared_at`
  (en el `SCHEMA` y con migración en sitio para bases de E41, vía `PRAGMA table_info`).
- **Estado honesto:** `RECEIVED` → `PREPARING` (transitorio, reclamo) → `IN_PROGRESS`.
- **Reutilización del archivo de E41:** `pedidos.preparar` abre `plano_requests/<id>/<plan_file>`
  (basename; el nombre sale de la base) y lo pasa por
  `assets.save_upload(pid, FileStorage, FLOORPLAN_ORIGINAL)`, la misma capa del LAB: valida
  extensión, tamaño y contenido, y genera el nombre guardado. La propiedad sale de
  `properties.create` + `grants.grant_and_assign`, igual que `lab.create`. El original de E41 no
  se mueve ni se borra.
- **Sin duplicados:** el reclamo es un `UPDATE … SET status='PREPARING' WHERE status='RECEIVED'`
  y se mira `rowcount`: sólo un llamador lo gana. Doble click/retry ve 0 filas, no crea nada y
  redirige (303) a la propiedad si ya existe.
- **Falla a mitad:** `_deshacer` borra propiedad, concesión, assets y archivos creados, y devuelve
  el pedido a `RECEIVED`; la excepción se propaga (500). Reintentar es seguro.
- **Sin motor ni red:** `pedidos.py` no importa `engine` ni nada de red; no crea `cases` ni `runs`.

## Archivos principales
`webapp/pedidos.py` (nuevo) · `webapp/templates/lab/pedidos.html` (nuevo) · `webapp/store.py`
(columnas + migración) · `webapp/app.py` (registro) · `tests/test_e42_pedido_a_propiedad.py`.
`webapp/public.py` y el formulario de E41 no se tocaron.

## Tests
baseline:    suite completa no corrida
post-change: `tests/test_e42_pedido_a_propiedad.py` 14 passed. Junto con E40, E41, E32*, E33* y
`test_ai_handoff`: **223 passed, 1 failed** (el fallo es el preexistente de abajo). Suite completa
(~12 min) **no corrida**.

## Acceptance criteria
1. PASS — `test_la_bandeja_y_la_accion_exigen_basic_auth` (401 sin credenciales y con mala clave).
2. PASS — `test_el_listado_muestra_…`.
3. PASS — una única acción POST protegida.
4. PASS — `test_preparar_crea_una_propiedad_con_el_plano_y_redirige` (1 propiedad, 1 asset
   `FLOORPLAN_ORIGINAL` con los mismos bytes, concesión asignada); vía `assets.save_upload`.
5. PASS — `property_id`, `prepared_at`, `status=IN_PROGRESS` persistidos.
6. PASS — 303 a `/lab/p/<property_id>`, que responde 200.
7. PASS — `test_repetir_el_post_…`, `test_el_reclamo_atomico_…`.
8. PASS — `test_si_falla_a_mitad_…`, `test_un_archivo_faltante_…`, `test_el_contenido_invalido_…`.
9. PASS — `test_un_pedido_preparado_enlaza_…`.
10. PASS — `test_preparar_no_ejecuta_motor_ni_abre_red` (`socket.connect` prohibido; 0 `cases`/`runs`).
11. PASS — `test_el_formulario_publico_de_e41_sigue_sin_auth` + los tests de E41 en verde.
12. PASS — cubiertos auth, listado, preparación, import seguro, idempotencia, rollback, no motor, migración.
13. PASS — E40/E41/E32/E33 en verde.
14. PASS — `git diff 6324b1f HEAD -- src/` vacío (0 líneas).
15. PASS — este REPORT + `CURRENT_STATE.md`.
16. PASS — commit de implementación posterior al de la TASK.
17. PASS — sin merge, deploy ni movimiento de `main`.

## Evidencia
Prueba de HTTP Basic: los dos primeros tests; las rutas llevan `@auth.require`.
`git diff 6324b1f HEAD -- src/` → vacío.

## Regresiones
Ninguna conocida. Falla `test_ai_handoff::test_el_main_declarado_es_el_de_origin_no_el_local`
(`origin/main` = `f466ccf`, la tabla declara `d097069`): preexistente desde E41, no es de E42 y no
se reparó.

## Limitaciones
- Si el proceso muere entre el reclamo y el cierre, el pedido queda en `PREPARING`, visible y sin
  botón: no se auto-repara (mejor visible que duplicado). Resolverlo es manual hoy.
- Un fallo del POST se ve como 500, no como mensaje amable; es una superficie de operador.
- La propiedad se titula «Plano Corporativo · <email>» y usa el `request_id` como `reference`.
- La bandeja no está enlazada desde el menú del LAB (se llega por URL).
- Sin capturas de pantalla.

## Decisiones requeridas
Ninguna.

## Commit / branch / PR
Rama `auto/e42-issue-11` (hija de `e42_request_to_internal_property`). La publica el workflow.
Sin PR, merge ni deploy.

## Exact next action
**E43 — producir y entregar el Plano Corporativo desde una propiedad preparada**, reutilizando
`commercial_svg`/salida existente y manteniendo revisión humana concierge.
