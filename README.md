# Escalímetro — Laboratorio de Normalización (ETAPA 1)

JPG/PDF de una planta comercial → geometría estructurada (`Floorplate JSON`) → Planta Escalímetro (SVG).
Nada se dibuja "a mano alzada" ni con generación de imágenes: toda salida proviene de la máscara
segmentada sobre la imagen real, con `confidence` y `provenance` por elemento.

## Instalar y correr

```bash
pip install -e ".[dev]"
python fixtures/make_synthetic.py cases/900_synthetic_fixture   # caso sintético (mecánica)
python -m escalimetro run   --case cases/900_synthetic_fixture
python -m escalimetro bench --case cases/900_synthetic_fixture
pytest -q
```

Caso real (requiere `tesseract` en PATH para la localización automática: `apt install tesseract-ocr`):

```bash
python -m escalimetro run   --case cases/001_gps_403 --out cases/001_gps_403/outputs/pass_a   # PASE A automático
python -m escalimetro bench --case cases/001_gps_403 --pred cases/001_gps_403/outputs/pass_a
python -m escalimetro run   --case cases/001_gps_403 --out cases/001_gps_403/outputs/pass_b --overrides overrides_assisted.json
python -m escalimetro bench --case cases/001_gps_403 --pred cases/001_gps_403/outputs/pass_b   # PASE B asistido
python -m escalimetro run   --case cases/001_gps_403 --out cases/001_gps_403/outputs/pass_c --overrides overrides_shell.json
python -m escalimetro bench --case cases/001_gps_403 --pred cases/001_gps_403/outputs/pass_c   # E03: shell confirmado, Gate E0.5
python cases/001_gps_403/ground_truth/make_gt.py            # regenera el GT manual
```

Shell semántico (E03): `outputs/shell_semantics_403.png`, `outputs/shell_comparison_403.png`, `docs/SHELL.md`.

Revisión humana: `outputs/comparison_403.png` (ORIGINAL | OVERLAY | PLANTA) y `outputs/geometry_only.png`.

Salidas en `cases/<id>/outputs/`: `floorplate.json`, `planta_escalimetro.svg` (metros),
`planta_escalimetro_px.svg` (px, con contorno crudo en rojo), `side_by_side.png`, `overlay.png`
(geometría sobre el original: prueba de fidelidad), `mask.png`, `original_grid.png`, `benchmark.json`.

## Docs

- `docs/ARCHITECTURE.md` — capas, interfaces, precedencia de fuentes
- `docs/FLOORPLATE_SCHEMA.md` — schema 0.1.1
- `docs/SHELL.md` — shell semántico 0.2.0: accesos, luz, pilares v2, readiness, Gate E0.5
- `docs/PRODUCT_BOUNDARY.md` — qué es y qué no es Escalímetro; motor agnóstico a vertical
- `docs/OVERRIDES.md` — human-in-the-loop
- `docs/BENCHMARK.md` — métricas y Gate E0

---

## Railway — backend validation runtime

El experimento multi-modelo (E09) **no se puede ejecutar desde el entorno de desarrollo**: su egress
bloquea `api.openai.com` y `railway.com` (E10 lo dejó documentado). El runtime real de la validación es
el servicio `backend` de Railway, que es donde viven las credenciales.

| | |
|---|---|
| GitHub | https://github.com/joaquinriesco-alt/escalimetro |
| Railway Project | `ESCALIMETRO` |
| Service | `backend` |
| Branch | `main` |
| Root Directory | `/` |
| Start Command | `PYTHONPATH=src python -m escalimetro.ai.railway_e09_runner` |

### Variables requeridas en el servicio `backend`

Sólo los NOMBRES. Los valores viven exclusivamente en Railway: no van al repo, ni a `.env`, ni a GitHub
Secrets, ni al frontend, ni al informe HTML, ni a los logs.

```
OPENAI_API_KEY
ANTHROPIC_API_KEY
OPENAI_MODEL_VISION
OPENAI_MODEL_PRESENTATION
ANTHROPIC_MODEL_REVIEWER
AI_PROVIDER_TIMEOUT
AI_PROVIDER_MAX_RETRIES
```

`PORT` lo inyecta Railway; el runner lo lee de `os.environ["PORT"]` y cae a 8080 sólo en local.

### Qué hace el servicio

`escalimetro.ai.railway_e09_runner` hace tres cosas y ninguna más:

1. **run** — ejecuta una vez `escalimetro.ai.e09`, que es la fuente de verdad del experimento. El wrapper
   no duplica esa lógica: la importa.
2. **report** — arma `ESCALIMETRO_E09_REAL_REPORT.html`, un único archivo con todas las imágenes
   embebidas como data URI. Sin dependencias externas ni rutas locales.
3. **serve** — levanta un servidor HTTP mínimo.

| ruta | qué devuelve |
|---|---|
| `/` | el informe HTML completo |
| `/health` | `{"status":"ok"}` |
| `/status` | `api_execution`, `gate_api`, `gate_multi_model_value`, `report_ready` |

No expone entorno, ni filesystem, ni configuración, ni logs. Cualquier otra ruta responde 404.

Si el experimento falla, el servidor se levanta igual y el informe explica qué falló: un despliegue que
muere en silencio no sirve para diagnosticar nada.

### Verificación local (sin credenciales)

```bash
PYTHONPATH=src python -m escalimetro.ai.railway_e09_runner --no-serve   # corre y genera el informe
PORT=8080 PYTHONPATH=src python -m escalimetro.ai.railway_e09_runner    # además, sirve en :8080
```

Sin `OPENAI_API_KEY` ni `ANTHROPIC_API_KEY` el experimento termina en `BLOCKED — API KEY MISSING`, el
informe se genera igual y cada bloque sin datos aparece marcado como bloqueado. Nunca se inventa una
revisión ni una cifra de costo.

### Garantía geométrica

El `GeometryGuard` hashea shell, recintos, puestos, mobiliario, puertas, pilares, circulación y escala
antes y después de toda la capa de IA. Hashes esperados de las tres alternativas de E07:

```
A  df6b86058ebb…
B  5c5c276923dd…
C  e12cc722485b…
```

Si alguno cambia, la corrida es FAIL por seguridad geométrica aunque las llamadas a los proveedores hayan
funcionado. Ningún modelo puede mover una coordenada.
