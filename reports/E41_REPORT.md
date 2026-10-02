# E41 REPORT

## Status
PASS — el pedido público mínimo de Plano Corporativo (email + plano) está implementado y probado.
Ninguna decisión de producto quedó abierta. Un fallo de `tests/test_ai_handoff.py` ajeno a E41
(ver Regresiones).

## Qué cambió
`/planos/solicitar` dejó de ser placeholder:
- `GET` muestra un formulario con **exactamente dos inputs**: `email` y `plano` (archivo).
- `POST` valida, guarda el archivo, persiste el pedido y responde **303** a la confirmación
  `GET /planos/recibido/<request_id>` (POST/Redirect/GET: refrescar no reenvía nada).
- Un POST inválido responde **400** con el error visible y el email tipeado, sin pedido ni archivo.

Sin motor, sin proveedor externo, sin emails, sin precios, sin campos extra, sin listado ni panel
de pedidos. La landing no se tocó: su CTA sigue yendo a `/planos/solicitar`.

## Contrato exacto del POST
`POST /planos/solicitar`, `multipart/form-data`, sin Authorization:

| campo | regla |
|---|---|
| `email` | obligatorio; sin espacios en los bordes; `x@y.z` (regex simple), ≤254 caracteres |
| `plano` | obligatorio; extensión `.pdf/.png/.jpg/.jpeg` (`intake.ext_of`), cabecera que coincide con la extensión (`intake.sniff_ok`), no vacío, ≤ `ESCALIMETRO_MAX_UPLOAD_MB` (40 por defecto) |

Persistencia (reutiliza `intake.ALLOWED/ext_of/sniff_ok/MAX_UPLOAD_MB`; nada nuevo de infraestructura):
- Tabla `plano_requests` en `escalimetro.db` (`webapp/store.py`): `request_id` (`pc_` + 32 hex de
  `uuid4`), `email`, `plan_file`, `original_filename` (sólo informativo), `mime`, `size_bytes`,
  `status` (`RECEIVED`), `created_at` (UTC ISO).
- Archivo en `DATA_DIR/plano_requests/<request_id>/plano.<ext>`: el nombre en disco lo decide el
  servidor; el original nunca se usa como ruta.
- Orden: carpeta → guardar → validar tamaño y contenido → `INSERT`. Cualquier fallo o excepción borra
  la carpeta, de modo que no hay pedido sin archivo ni archivo sin pedido.

La confirmación sólo muestra la referencia opaca; no refleja el email.

## Ejemplo de pedido de test (sin datos reales)
```
request_id=pc_<32 hex>  email=Cliente@Example.com  plan_file=plano.pdf
original_filename=plano.pdf  mime=application/pdf  size_bytes=26  status=RECEIVED  created_at=<UTC>
```
(contenido `%PDF-1.4\n% plano de prueba\n`; ver `test_post_valido_crea_un_pedido_y_guarda_el_archivo`).

## Archivos principales
Modificados: `webapp/public.py`, `webapp/store.py` (tabla + `plano_request_dir`),
`webapp/templates/public/solicitar.html`, `webapp/static/public.css`,
`tests/test_e40_public_landing.py` (el test del «próximamente» y del 405 ya no aplica; ahora sólo
exige 200 sin auth), `docs/ai-development/CURRENT_STATE.md`.
Nuevos: `webapp/templates/public/recibido.html`, `tests/test_e41_plano_corporativo_request.py`,
`reports/E41_REPORT.md`. `src/`, `.github/`, `.claude/`, doctrina: sin cambios.

## Tests
baseline:    no medida (la suite completa dura ≈12 min; no se corrió)
post-change: `tests/test_e41_plano_corporativo_request.py` + `tests/test_e40_public_landing.py` +
             `tests/test_e27_webapp.py`: **113 passed**. Con `tests/test_ai_handoff.py`: 112 passed, 1 failed
             (preexistente, ver Regresiones). Suite completa **no corrida**.

## Acceptance criteria
1. PASS — `test_get_200_sin_auth_con_exactamente_dos_inputs`.
2. PASS — mismo test: 2 `<input>`, `email` y `plano`.
3. PASS — mismo test: ningún campo prohibido (teléfono, empresa, dirección, fotos, programa, personas, estilo, precio, textarea, select).
4. PASS — `test_post_valido_crea_un_pedido_y_guarda_el_archivo` (PDF, PNG, JPG, JPEG): 1 fila, 1 archivo con el contenido exacto.
5. PASS — mismo test: id `pc_`+32 hex, `created_at`, `status=RECEIVED`.
6. PASS — `test_prg_confirmacion_y_refresh_no_duplica`: 303, tres GET de la confirmación, siguen 1 fila y 1 archivo.
7. PASS — `test_email_ausente_o_invalido_no_deja_nada`, `test_archivo_ausente_o_no_permitido_no_deja_nada`, `test_archivo_demasiado_grande_no_deja_nada`: 400, mensaje visible, 0 filas, 0 archivos, 0 carpetas.
8. PASS — `test_nombre_original_no_permite_path_traversal`: `plan_file` siempre `plano.<ext>`, dentro de `plano_requests/`.
9. PASS — `test_post_no_toca_motor_ni_red`: `subprocess` y `socket.connect` prohibidos durante el POST, ningún módulo `escalimetro`/`openai`/`anthropic` importado por él, 0 casos y 0 corridas.
10. PASS — `test_landing_conserva_su_cta`.
11. PASS — `test_rutas_internas_siguen_pidiendo_basic`, `test_post_interno_sigue_protegido…` (401 con `Basic`).
12. PASS — 56 casos nuevos: happy path, validaciones, persistencia, archivo, PRG, protección interna, limpieza ante fallo del `INSERT`.
13. PASS — E40 y `test_e27_webapp.py` verdes (113 passed junto con E41).
14. PASS — `git diff 6324b1f HEAD -- src/` vacío (0 líneas).
15. PASS — este REPORT y `CURRENT_STATE.md` van en el mismo commit final.
16. PASS — el commit de E41 es posterior al de la TASK (`96357ca`).
17. PASS — sin merge, deploy ni movimiento de `main`.

## Evidencia
- POST inválido sin residuos: los tests de criterio 7 comprueban filas, archivos y carpetas bajo `plano_requests/`; `test_fallo_al_insertar_limpia_el_archivo` fuerza un fallo del `INSERT` (500) y verifica que no queda archivo.
- PRG: criterio 6. La respuesta del POST es 303, nunca 200 con el formulario procesado.
- Sin motor ni red: criterio 9. Por construcción, `webapp/public.py` sólo importa `intake` y `store`; `intake` importa `cv2` y `pymupdf` de forma diferida y este camino no los usa.
- `git diff 6324b1f HEAD -- src/`: salida vacía.

## Regresiones
Ninguna causada por E41. El test del «próximamente» de E40 se reemplazó a propósito: era la
contrapartida de este cambio.

`tests/test_ai_handoff.py::test_el_main_declarado_es_el_de_origin_no_el_local` falla: `CURRENT_STATE`
declara `main=d097069` y `origin/main` en este checkout es `f466ccf` («Merge pull request #9 … bootstrap/m05-prisma-live-status»).
`main` avanzó fuera de esta cadena de TASKs. **No lo reparé**: reescribir el estado de `main` exige
verificarlo contra GitHub (protocolo §9.1) y la fila de ramas no es de E41. Queda registrado.

## Limitaciones
- No se deduplica por email + archivo: dos envíos deliberados son dos pedidos. Sólo el refresh queda
  cubierto (PRG). Un «atrás» del navegador seguido de reenviar crearía otro pedido.
- Sin límite de tasa ni captcha: es una superficie pública que escribe en disco. El tope de tamaño
  es el existente (40 MB, y 160 MB por request en `MAX_CONTENT_LENGTH`). Un 413 por exceso de request no crea nada, pero muestra la página de error de Flask, no el formulario.
- El email no se verifica (no se envía nada). La regex sólo descarta lo evidentemente inválido.
- Sin capturas de pantalla.
- Los pedidos sólo se pueden ver leyendo la base; no hay panel (fuera de alcance).

## Decisiones requeridas
Ninguna para esta TASK. Protección contra abuso (límite de tasa / captcha) sería infraestructura o
UX nueva: se deja a Joaquín y ChatGPT si lo quieren antes de publicar la URL.

## Commit / branch / PR
Rama `auto/e41-issue-10`, hija de `e41_plano_corporativo_request` (`96357ca`). El workflow la publica.
Sin PR. Commit final: ver `git log -1` de la rama.

## Exact next action
Paso 3 (procesamiento/entrega del Plano Corporativo), como TASK nueva desde la base
`auto/e41-issue-10`: leer `plano_requests` con `status='RECEIVED'`, decidir con Joaquín qué es
«entregar» (P-1 y P-2 siguen abiertas: precio y estilos) y qué cambia `status`. Antes de publicar la
URL, decidir si hace falta un freno contra abuso.
