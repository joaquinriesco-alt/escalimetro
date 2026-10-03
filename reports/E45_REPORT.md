# E45 REPORT

## Status
PASS — web piloto lista y probada en la rama, con capturas desktop/móvil y sin deploy. La calidad de
la UX **no** se afirma: la juzga Joaquín usando la web. Sin casos reales cargados (0/40), como pedía la TASK.

## Qué cambió
Una superficie protegida (HTTP Basic) en `/lab/campaign/e44/` para cargar, procesar y evaluar los 40
casos de E44 sin CLI. **No es otro sistema de campaña**: cada caso es un caso del manifiesto E44
(`DATA_DIR/e44/`), y estado, N, ceguera, cierre, reveal y evaluaciones salen de `webapp/campaign.py`.

### Mapa del flujo
```
/            ¿Qué necesitas hacer?  → MEJORAR UN PLANO | CREAR UN PLANO   (+ MEJORAR n/20 · CREAR n/20)
MEJORAR  /mejorar (1 archivo) → caso: MATERIAL CARGADO → PROCESAR
         → listo: ANTES / DESPUÉS + abrir/descargar → [panel piloto: evaluar]
         → no listo: NECESITA REVISIÓN (REVISAR EN EL LAB · VOLVER A INTENTAR · DAR POR NO RESUELTO)
CREAR    /crear (fotos + m² + enlace/texto + [MODO PILOTO: plano real]) → caso: MATERIAL CARGADO
         → PROCESAR (cola E37) → PROCESANDO → reconstrucción «esquemática · referencial»
         → CORREGIR (corrida hija, n veces) → [CERRAR RECONSTRUCCIÓN Y COMPARAR] → RECONSTRUCCIÓN | PLANO REAL
         → [panel piloto: evaluar]
/panel   progreso grande + tarjetas (estado, miniaturas, fecha, rating, ABRIR CASO, NUEVO MEJORAR/CREAR)
```
Vista producto (blanco, planos grandes) y panel piloto (banda tintada «MODO PILOTO», borde punteado)
están separados en cada pantalla; la evaluación va siempre al final.

## Archivos principales
- `webapp/pilot.py` (blueprint, vista-modelo, archivos por rol) · `webapp/templates/pilot/*` · `webapp/static/pilot.css`
- `webapp/campaign.py` (ampliado, ver «Integración») · `webapp/app.py` (registro) · `scripts/e45_demo_screens.py`
- `tests/test_e45_web_pilot.py` (50 tests) · `reports/E45_screens/` (capturas)

## Rutas nuevas (todas con `auth.require`; los POST con la guarda de mismo origen de E37)
`GET /` elegir · `GET /panel` · `GET|POST /mejorar` · `GET|POST /crear` · `GET /caso/<id>` ·
`POST /caso/<id>/{procesar,sin-resultado,corregir,cerrar,evaluar/plano,evaluar/ux}` ·
`GET /caso/<id>/archivo/<entrada|foto-N|despues|reconstruccion|real>`. Modificadas: ninguna ruta existente.

## Integración exacta con E44 / E37 / E43
- Alta: `campaign.import_upload` arma un bundle temporal y llama a **`_import_case`** (sha256, provenance,
  PII, duplicados, plano real a la zona oculta de E37). Origen `WEB_UPLOAD`, fuente «carga web del piloto»;
  enlace de origen opcional; nombres del usuario no se conservan (`plano.ext`, `foto_NN.ext`, `plano_real.ext`).
  Un rechazo no deja evidencia huérfana (arreglo de `_import_case`).
- MEJORAR: `start_improve` = propiedad + `FLOORPLAN_ORIGINAL` + `floorplan.ensure_case` + **`ingest.auto_prepare`**
  (el análisis automático del LAB); `finish_improve` = `floorplan.publish_commercial_floorplan` sólo si
  `technical_state.ready`. Sin planta lista no hay resultado: queda NECESITA REVISIÓN (confirmación humana en
  el LAB) y se puede dar por no resuelto (`pipeline` con `reached_output=false`, nunca éxito). `run_improve`
  (CLI de E44) ahora compone ambas mitades. **Hallazgo:** el `run_improve` de E44 no llamaba a `auto_prepare`,
  así que una lámina recién subida nunca estaba «lista».
- CREAR: `start_create`/`start_correction` (E37 `create_initial` / `create_correction`, cola de E37) +
  `settle` (asienta `pipeline`/`correction` cuando la corrida termina) + `close_blind` (con auditoría de
  ceguera) + `reveal`. El botón único cierra y revela; el reveal exige el cierre (regla de E44).
- Evaluaciones: eventos de sólo inserción de E44. Resultado = `evaluation` (schema `e45_pilot_v1`, completa el
  caso); UX = `ux_evaluation` (no completa nada). `summary()` ahora tolera evaluaciones sin las dimensiones
  de E44 (no las inventa) y agrega la sección `pilot` con los dos juicios por separado.
- DEMO: `demo: true` en el caso; `count()` y `summary()` los excluyen; la detección de duplicados los aísla;
  el fixture sólo corre sobre casos demo.

## Ejemplo de evaluación RESULTADO vs UX/UI (caso demo, `desktop_11_*`)
Resultado: `MALO` → luego `BUENO` («Revisado de nuevo», `supersedes_seq`), ¿publicaría? no → sí, ¿corrección humana? sí, 6 → 3 min.
UX/UI: `BUENO`, ¿entendió de inmediato? sí, faltaba: «Un ejemplo de plano antes de subir». Dos juicios distintos, sin puntaje compuesto; las dos versiones quedan en `results/`.

## Prueba de DEMO fuera de los N
`scripts/e45_demo_screens.py` sembró 9 casos demo (+20+20 para el panel a escala) y verificó
`count() == 0` en todos los campos de ambas pistas (`assert` en el script). Test:
`test_los_demo_no_cuentan_ni_chocan_con_casos_reales` (también `summary().status == BLOCKED`).

## Prueba de blindness
Tests adversariales (en `tests/test_e45_web_pilot.py`): el nombre del plano real (`SECRETO_GT_7781.png`), su
sha256, su nombre guardado y `reconstruction_gt` no aparecen en ninguna pantalla, miniatura ni SVG antes del reveal;
ni en `inputs`/`params`/`build_request` de ninguna corrida (incluida la hija); `archivo/real` y la ruta de E37
dan 404 antes del reveal; 12 variantes del selector (`../real`, `REAL`, `foto-99`…) dan 404; sin cerrar no se
revela, sin confirmar no se cierra, una auditoría fallida bloquea el cierre y el reveal; igual-a-una-foto se
rechaza («no es ciego»); la evaluación exige el reveal; tras el cierre no se corrige.

## Tests
baseline:    E44 20 passed @ 62b6a96
post-change: `test_e44 + e43 + e37 + e45 + e40 + e41 + e42`: **270 passed, 0 failed** @ árbol de trabajo de este commit.
E45: 50 passed. Suite completa (~12 min): **no corrida**; ver Limitaciones.
`git diff 6324b1f HEAD -- src/` → vacío (0 líneas).

## Acceptance criteria
1. PASS — `/lab/campaign/e44/` arranca MEJORAR o CREAR sin CLI. 2. PASS — primera pantalla `desktop_01`.
3. PASS — alta E44 (test). 4. PASS — `ensure_case` + `auto_prepare` + `publish_commercial_floorplan` reales (espía en test; sólo el análisis y el trazado se sustituyen en tests). 5. PASS — ANTES/DESPUÉS.
6. PASS. 7. PASS — `HIDDEN_FROM_ENGINE`, y la UI lo explica. 8. PASS. 9. PASS — con motor de prueba en tests; **sin motor real** (no hay `OPENAI_API_KEY`). 10. PASS. 11. PASS. 12. PASS. 13. PASS. 14. PASS. 15. PASS. 16. PASS (revisión por jerga en tests; ver Limitaciones). 17. PASS — BLOQUEADO accionable, sin corrida ni éxito. 18–19. PASS como humo (tests + capturas); su usabilidad la juzga Joaquín.
20. PASS — ver capturas. 21. PASS. 22. PASS (270). 23. PASS. 24. PASS. 25. PASS. 26. ver commit. 27. PASS — sin merge/deploy/main.

## Evidencia
Capturas en `reports/E45_screens/`, todo DEMO sintético.
Desktop: `desktop_01_elegir` · `02_mejorar_subir` · `03_mejorar_cargado` · `04_mejorar_revision` · `05_mejorar_antes_despues` ·
`06_crear_subir_y_plano_real` · `07_crear_cargado` · `08_crear_reconstruccion_pre_reveal` · `09_crear_comparacion_post_reveal` ·
`10_crear_bloqueado_sin_credencial` · `11/12_evaluacion_resultado_y_ux_*` · `13_panel` · `14_panel_con_40_demo` (escala; contadores siguen 0/20).
Móvil (390 px): `mobile_01_elegir` · `02_mejorar_antes_despues` · `03_crear_subir` · `04_crear_comparacion` · `05_evaluacion` · `06_panel`.
Generadas con Chromium headless desde `scripts/e45_demo_screens.py`. La reconstrucción de las capturas es el FIXTURE de E37 (no una reconstrucción real).

## Regresiones
Ninguna detectada en los 270 tests. Cambios en E44 son aditivos (`summary` con `.get`, `count` sin demo, limpieza ante rechazo).

## Limitaciones
- **CREAR real nunca corrió:** falta `OPENAI_API_KEY` (y gasto aprobado). Probado con un adaptador de prueba; el comportamiento con el proveedor real, tiempos y costos no están medidos.
- **MEJORAR real sobre láminas reales no medido:** el análisis automático suele dejar NECESITA REVISIÓN; hoy se resuelve en el LAB (`/lab/p/<id>`), una vuelta fuera de la web piloto.
- MEJORAR sólo pide el archivo (sin m² publicados, que el motor podría usar para la escala): puede bajar la tasa de lectura automática; sin medir.
- Una primera corrida CREAR que falla queda registrada y no se reintenta (`pipeline` es inmutable en E44); sí se puede cerrar y evaluar.
- La evaluación web no captura las dimensiones detalladas de E44 (fidelidad, 6 dimensiones CREAR, errores); `summary()` no las cuenta para casos de la web.
- Una propiedad en ambas pistas sin enlace de referencia no se detecta como la misma (no hay clave de propiedad); no hay `both_tracks_reason` en la web.
- El SVG de reconstrucción es el de E37 y trae rótulos técnicos (p. ej. «el motor cree…»): no se reescribió para esta TASK.
- El tipo de propiedad se fija en `OFFICE` (población de E44); la web no lo pregunta.
- «Procesar» en CREAR usa un servicio con costo y el botón lo declara: es la confirmación de gasto (`confirm_paid=True`).
- Un proceso que muere con una corrida en vuelo la deja `FAILED` (regla de E37) y el caso queda SIN RESULTADO.
- Suite completa no corrida; los 2 fallos preexistentes siguen listados en `CURRENT_STATE.md`.
- Capturas: 8 MB en el repo público (sintéticas).

## Decisiones requeridas
Ninguna. (Pendientes de producto no tocados: dónde correr el piloto y si se autoriza un deploy.)

## Commit / branch / PR
Rama `auto/e45-issue-14` (hija de `e45_web_pilot_40_cases`, que sale de `auto/e44-issue-13`). La publica el workflow. No verificada contra GitHub desde el ejecutor (sin red). Sin PR, merge ni deploy.

## Exact next action
ChatGPT audita y se detiene. **Para empezar a cargar casos Joaquín necesita:** (1) un despliegue piloto autorizado por él (DR/DEPLOY_GATE) con `ESCALIMETRO_PASSWORD` y volumen en `ESCALIMETRO_DATA_DIR`; (2) `OPENAI_API_KEY` y el gasto aprobado para CREAR; (3) abrir `/lab/campaign/e44/` y revisar las capturas antes. Local: `ESCALIMETRO_DEV=1 ESCALIMETRO_DATA_DIR=./.data-lab PYTHONPATH=src PORT=8030 .venv/bin/python wsgi.py`. No se crea E46.
