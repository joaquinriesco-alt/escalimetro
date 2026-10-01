# E40 REPORT

## Status
PARTIAL — la landing pública está implementada y probada; **faltan las capturas desktop y mobile**
(criterio de evidencia, no de aceptación). Ninguna decisión de producto quedó abierta.

## Qué cambió
Una superficie pública nueva, mínima y aislada bajo `/planos`, fuera de HTTP Basic:
- `GET /planos/` — landing: hero **PLANOS QUE AYUDAN A VENDER**, CTA **SUBIR PROPIEDAD**, y tres
  productos en orden: Plano Corporativo (marcado «producto de entrada», con borde y tamaño mayor) →
  Crear Plano (esquemático/referencial, dice que no es levantamiento exacto) → PRO Layouts
  (PLANTA + PROGRAMA → alternativas; sin editor ni dashboard).
- `GET /planos/solicitar` — pantalla honesta «Solicitud próximamente»: sin formulario, sin POST
  (405), no crea ni guarda nada. A ella lleva el CTA. El formulario real es de la TASK siguiente.
- Ilustración: un SVG propio y genérico dentro de la plantilla, rotulado «Ilustración esquemática».
  No reutiliza ningún asset de propiedades.

Aislamiento: `webapp/public.py` no importa store, engine ni nada del motor; las plantillas no
extienden `base.html` (cuyo menú enlaza herramientas internas). Las rutas internas no se tocaron:
siguen protegidas por `@auth.require`, ruta por ruta, como antes. `/healthz` no se tocó.

Sin precios, sin P-1/P-2/P-3/P-4 resueltas, sin nombres de estilos.

## Archivos principales
Nuevos: `webapp/public.py`, `webapp/templates/public/landing.html`,
`webapp/templates/public/solicitar.html`, `webapp/static/public.css`,
`tests/test_e40_public_landing.py`, `reports/E40_REPORT.md`.
Modificados: `webapp/app.py` (import + `register_blueprint(public.bp)`),
`docs/ai-development/CURRENT_STATE.md`.
`src/`, `.github/`, doctrina: sin cambios.

## Tests
baseline:    no medida en esta ejecución (la suite completa dura ≈12 min; no se corrió)
post-change: `tests/test_e40_public_landing.py` + `tests/test_ai_handoff.py`: **72 passed**;
             `tests/test_e27_webapp.py` + E40: **76 passed**. Suite completa **no corrida**.

## Acceptance criteria
1. PASS — `test_landing_200_sin_auth`: 200 sin `Authorization` y sin `WWW-Authenticate`.
2. PASS — `test_hero_tres_productos_en_orden_y_cta`.
3. PASS — mismo test: orden Plano Corporativo → Crear Plano → PRO Layouts.
4. PASS — etiqueta «PRODUCTO DE ENTRADA» y estilo destacado (revisión de CSS; **no visto en captura**).
5. PASS — `test_crear_plano_no_afirma_exactitud`.
6. PASS — texto «PLANTA + PROGRAMA → alternativas de layout y cabida», sin controles de edición.
7. PASS — `test_sin_precios_ni_ofertas_prohibidas` (sin `$`, CLP, UF, USD, «desde», porcentajes).
8. PASS — mismo test (staging, video, scoring, benchmark, LAB, debug, ambientación, jerga del motor).
9. PASS — `test_solicitar_200_sin_auth_y_no_finge_un_pedido` y `test_cta_apunta_a_la_pagina_honesta`.
10. PARTIAL — CSS responsivo (grilla a una columna bajo 760 px, botón de ancho completo), pero **no
    verificado visualmente**: sin capturas.
11. PASS — `test_rutas_internas_representativas_dan_401` (`/`, `/lab/`, `/properties/`,
    `/settings`), `test_post_interno_sigue_protegido` (`POST /upload`) y la variante con rutas
    adicionales.
12. PASS — `test_sin_fuga_de_contenido_interno`; la vista no consulta la base.
13. PASS — 21 tests nuevos (parametrizados incluidos), todos en verde.
14. PASS — `git diff 6324b1f HEAD -- src/` vacío (0 líneas).
15. PASS — este REPORT y `CURRENT_STATE.md`.
16. PASS — commit de implementación en `auto/e40-issue-6`.
17. PASS — sin merge, deploy ni PR.

## Evidencia
- Ruta local: `http://localhost:<PORT>/planos/` (LAB: `ESCALIMETRO_DEV=1 … PORT=8030 .venv/bin/python wsgi.py`).
- Landing 200 sin Authorization y rutas internas 401: los tests citados, con contraseña puesta
  (el modo dev abriría todo y no probaría nada).
- Diff de `src/` contra `6324b1f`: vacío.
- **Capturas: no hay.** En esta ejecución el sandbox exigió aprobación para crear directorios y
  levantar el servidor desde la shell, y no hay aprobación interactiva. No se simularon.
  Chromium existe en la máquina (`chromium --headless --screenshot`), así que repetirlo es
  una línea por tamaño (1280×900 y 390×844).

## Regresiones
Ninguna observada en los tests corridos. La suite completa no se corrió.

## Limitaciones
- Sin capturas (arriba): criterios 4 y 10 sin verificación visual.
- El texto de la landing es mío, basado en la TASK; la redacción comercial final la decide Joaquín.
- `/static/app.css` ya era público antes de E40 (Flask sirve `static/`); no es contenido interno.
- El CTA lleva a una página de «próximamente»: es lo que permite la TASK hasta que exista el pedido.

## Decisiones requeridas
Ninguna nueva. P-1…P-4 de E39 siguen pendientes y no bloquearon esta TASK.

## Commit / branch / PR
Rama `auto/e40-issue-6` (la publica el workflow). Sin PR, sin merge, sin deploy.

## Exact next action
1. Tomar las dos capturas (desktop 1280×900, mobile 390×844) de `/planos/` y versionarlas, o que
   ChatGPT/Joaquín las revisen localmente.
2. ChatGPT audita y escribe la TASK del paso 2 de E39 (pedido de Plano Corporativo), desde la base
   `auto/e40-issue-6`.
