# ESCALÍMETRO — herramienta interna (E27). Puesta en marcha

Servicio único: web + motor existente + volumen persistente + cola de jobs en proceso.

## 1. Desplegar en Railway (5 minutos, una sola vez)

1. Entrar a **railway.app** con tu cuenta.
2. **New Project → Deploy from GitHub repo → `joaquinriesco-alt/escalimetro`**.
3. En *Settings → Source*, elegir la rama **`e27_internal_web_app`**.
   Railway detecta el `Dockerfile` solo; no hay que configurar build command.
4. En *Settings → Variables*, agregar:

   | variable | valor |
   |---|---|
   | `ESCALIMETRO_PASSWORD` | la contraseña que quieras (obligatoria: sin ella la app no arranca) |
   | `ESCALIMETRO_USER` | `joaquin` (opcional; es el default) |
   | `ESCALIMETRO_REVIEWER` | tu nombre, como queda firmado en cada revisión |

5. En *Settings → Volumes*, **Add Volume** con mount path **`/data`**.
   Esto es lo que hace que las plantas, los briefs, las corridas y las revisiones
   sobrevivan a cada deploy. Sin volumen, un redeploy borra el trabajo.
6. *Settings → Networking → **Generate Domain***. Esa es la URL.

Comprobación: `https://<tu-dominio>/healthz` debe responder
`{"cases": 2, "jobs_pending": 0, "ok": true}`.

## 2. Recursos

El motor usa CP-SAT y OpenCV: **2 GB de RAM** es el mínimo cómodo. Una corrida de tres
alternativas tarda unos 5 minutos de CPU. El plan gratuito de Railway se queda corto;
el Hobby alcanza.

## 3. Local

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
ESCALIMETRO_DEV=1 ESCALIMETRO_DATA_DIR=./.data .venv/bin/python wsgi.py
```

`ESCALIMETRO_DEV=1` es lo único que permite arrancar sin contraseña, y sólo en local.

## 4. Variables

| variable | default | para qué |
|---|---|---|
| `ESCALIMETRO_PASSWORD` | — | **obligatoria en producción**. Sin ella la app se niega a arrancar |
| `ESCALIMETRO_USER` | `joaquin` | usuario del Basic Auth |
| `ESCALIMETRO_DATA_DIR` | `./.data` | raíz del estado. En Railway: `/data` (ya viene en el Dockerfile) |
| `ESCALIMETRO_REVIEWER` | `Joaquín Riesco` | firma de las revisiones |
| `ESCALIMETRO_MAX_UPLOAD_MB` | `40` | tope por planta |
| `ESCALIMETRO_RUN_TIMEOUT_S` | `3600` | seguro contra una corrida colgada |
| `ESCALIMETRO_MIGRATE` | `1` | importa GPS 403 y 401 al arrancar (idempotente) |
| `ESCALIMETRO_DEV` | — | `1` permite arrancar sin contraseña. **Nunca en producción** |

## 5. Qué hay dentro de `/data`

```
/data
├── escalimetro.db              cases, briefs, runs, alternatives, reviews
└── cases/<case_id>/
    ├── original.<ext>          el archivo que subiste, intacto
    ├── preview.png             derivado, regenerable
    ├── case.json               generado desde el intake
    ├── overrides.json          tus confirmaciones humanas
    ├── outputs/floorplate.json geometría leída
    ├── briefs/<BRIEF_ID>.json  BriefV1 del formulario
    └── layouts/<run_id>/       lo que escribió el motor
```

El repo no guarda nada de esto. Un deploy reemplaza código, no trabajo.

## 6. Backup

`https://<dominio>/reviews.json` exporta todas las revisiones en el formato de
`contracts/human_review_v1.schema.json`. Guardalo cuando termines una sesión de revisión.
