"""E27 — persistencia. SQLite para metadatos + filesystem para binarios, todo bajo DATA_DIR.

Por qué SQLite y no Postgres: es una herramienta interna de un solo usuario. Un archivo en el
volumen persistente da transacciones, consultas y cero infraestructura. Si algún día hay
concurrencia real, la interfaz de este módulo no cambia.

DATA_DIR es la ÚNICA raíz de estado. En Railway apunta al volumen montado; en local a ./.data.
Nada importante se escribe dentro del repo: un deploy no puede borrar el trabajo de Joaquín.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

#: Se normaliza a ABSOLUTA en la puerta, y no es cosmético. Con una ruta relativa el mismo archivo
#: se resuelve contra dos bases distintas: `open()` lo busca desde el directorio de trabajo y
#: `flask.send_file` desde el directorio del paquete. El resultado es que el ZIP se arma bien y la
#: imagen da 500, que es exactamente el tipo de fallo que sólo aparece en un despliegue.
DATA_DIR = os.path.abspath(os.environ.get("ESCALIMETRO_DATA_DIR")
                           or os.path.join(os.getcwd(), ".data"))
DB_PATH = os.path.join(DATA_DIR, "escalimetro.db")

#: Estados de caso. E27.3 §13 añade dos que la UX necesita distinguir y el flujo anterior confundía:
#:   INPUT_NOT_READY   la planta no viene limpia: está fuera del contrato de V1, no es un fallo
#:   NEEDS_CONFIRMATION el motor YA analizó y falta que un humano revise lo detectado
#: La diferencia importante es ANTES del análisis (NEEDS_INPUT) vs DESPUÉS (NEEDS_CONFIRMATION).
CASE_STATES = ("UPLOADED", "NEEDS_INPUT", "INPUT_NOT_READY", "NEEDS_CONFIRMATION", "READY",
               "GENERATING", "COMPLETE", "PARTIAL", "FAILED")
#: §14 — separar lo que se usa para desarrollo de lo que se reserva como evaluación futura.
TRACKS = ("DEVELOPMENT", "RESERVED")
#: §9 — estados por alternativa. SEARCH_EXHAUSTED nunca se traduce como "no cabe".
ALT_STATES = ("GENERATING", "FIT", "SEARCH_EXHAUSTED", "TIMEOUT_NO_SOLUTION",
              "TIMEOUT_WITH_INCUMBENT", "FAILED")

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  case_id           TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  source_file       TEXT NOT NULL,
  mime              TEXT NOT NULL,
  uploaded_at       TEXT NOT NULL,
  status            TEXT NOT NULL,
  track             TEXT NOT NULL DEFAULT 'DEVELOPMENT',
  published_area_m2 REAL,
  source_name       TEXT,
  notes             TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS intake (
  case_id        TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
  declared_clean TEXT,            -- 'yes' | 'no' | NULL (sin declarar)
  scale_px_per_m REAL,
  scale_method   TEXT,            -- 'two_points' | 'published_area' | 'existing'
  scale_note     TEXT,
  seed_point     TEXT,            -- JSON [x, y] en px de la imagen original
  entrance_point TEXT,            -- JSON [x, y]
  confirmed      TEXT,            -- JSON lista de confirmaciones
  missing        TEXT,            -- JSON lista de lo que falta (del motor, no inventado)
  scale_points   TEXT,            -- JSON [[x1,y1],[x2,y2]] de la medición humana
  analyzed_at    TEXT,            -- cuándo corrió el análisis; NULL = el motor no miró la planta
  answers        TEXT,            -- JSON {elemento: "ok"|"fix"} de la revisión humana posterior
  updated_at     TEXT
);
CREATE TABLE IF NOT EXISTS briefs (
  brief_id     TEXT PRIMARY KEY,
  case_id      TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  headcount    INTEGER NOT NULL,
  workstations INTEGER NOT NULL,
  rooms        TEXT NOT NULL,     -- JSON [{module, count}]
  brief_sha256 TEXT NOT NULL,
  created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  run_id        TEXT PRIMARY KEY,
  case_id       TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  brief_id      TEXT NOT NULL,
  status        TEXT NOT NULL,    -- QUEUED | RUNNING | DONE | FAILED
  engine_commit TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT,
  log           TEXT DEFAULT '',
  best_alt      TEXT              -- §12 mejor alternativa del caso: A|B|C|NINGUNA
);
CREATE TABLE IF NOT EXISTS alternatives (
  run_id        TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  alt           TEXT NOT NULL,
  name          TEXT,
  status        TEXT NOT NULL,
  layout_sha256 TEXT,
  metrics       TEXT,             -- JSON
  quality       TEXT,             -- JSON
  detail        TEXT,             -- JSON (no_fit.json cuando no hay layout)
  PRIMARY KEY (run_id, alt)
);
CREATE TABLE IF NOT EXISTS reviews (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id       TEXT NOT NULL,
  run_id        TEXT NOT NULL,
  alt           TEXT NOT NULL,
  grade         TEXT NOT NULL,    -- A_GOOD | B_CORRECTABLE | C_BAD
  reason_tags   TEXT NOT NULL,    -- JSON
  free_note     TEXT DEFAULT '',
  minutes_spent REAL DEFAULT 0,
  reviewer      TEXT NOT NULL,
  reviewed_at   TEXT NOT NULL,
  layout_sha256 TEXT,             -- §12 la revisión SIEMPRE queda ligada a la geometría juzgada
  engine_commit TEXT,
  brief_sha256  TEXT
);

-- ==============================================================================================
-- E28 — capa de PRODUCTO. Convive con las tablas del motor sin tocarlas: `properties` apunta a
-- `cases`, nunca al revés, y un caso sin propiedad sigue siendo perfectamente válido.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS properties (
  property_id       TEXT PRIMARY KEY,
  schema_version    TEXT NOT NULL,
  title             TEXT NOT NULL,
  asset_type        TEXT NOT NULL DEFAULT 'OFFICE',
  country           TEXT DEFAULT '',
  city              TEXT DEFAULT '',
  reference         TEXT DEFAULT '',
  published_area_m2 REAL,
  floorplan_case_id TEXT REFERENCES cases(case_id) ON DELETE SET NULL,
  status            TEXT NOT NULL DEFAULT 'DRAFT',
  notes             TEXT DEFAULT '',
  -- E36 §5/§7 — piloto real y procedencia del material. `source_type` nace NULL a propósito:
  -- "sin declarar" no es lo mismo que "real", y sólo lo REAL_* cuenta para calibrar.
  in_pilot          INTEGER NOT NULL DEFAULT 0,
  source_type       TEXT,
  source_reference  TEXT,
  -- E36 §15 — cuánto demora de verdad preparar una propiedad. Seis marcas, ningún tracking.
  pack1_started_at  TEXT,
  geometry_ready_at TEXT,
  layout_ready_at   TEXT,
  staging_ready_at  TEXT,
  pack1_ready_at    TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS property_assets (
  asset_id          TEXT PRIMARY KEY,
  property_id       TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  kind              TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  stored_name       TEXT NOT NULL,    -- nombre interno; el del usuario nunca toca el filesystem
  mime_type         TEXT NOT NULL,
  size_bytes        INTEGER NOT NULL,
  sha256            TEXT NOT NULL,
  width_px          INTEGER,
  height_px         INTEGER,
  sort_order        INTEGER NOT NULL DEFAULT 0,
  source_asset_id   TEXT REFERENCES property_assets(asset_id) ON DELETE SET NULL,
  metadata          TEXT,             -- JSON: procedencia y lo que haga falta sin migrar
  created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS packs (
  pack_id        TEXT PRIMARY KEY,
  property_id    TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  schema_version TEXT NOT NULL,
  status         TEXT NOT NULL,
  manifest       TEXT,               -- JSON
  export_name    TEXT,               -- nombre del ZIP dentro del directorio de la propiedad
  created_at     TEXT NOT NULL
);
-- ==============================================================================================
-- E30 — capa de PRODUCTO COMERCIAL. Tres ideas nuevas y nada más:
--   settings      configuración de la cuenta (modo de producto, marca de la corredora)
--   fit_requests  "evaluá esta propiedad para este prospecto"; una propiedad tiene muchas
--   fit_runs      qué corrida del motor pertenece a qué fit request
-- Ninguna toca las tablas del motor. Un run sin fit sigue siendo válido (los de E27 lo son).
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value      TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fit_requests (
  fit_id           TEXT PRIMARY KEY,
  property_id      TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  schema_version   TEXT NOT NULL,
  kind             TEXT NOT NULL,          -- BASE | PROSPECT
  label            TEXT NOT NULL,
  prospect_name    TEXT DEFAULT '',
  prospect_color   TEXT DEFAULT '',
  prospect_logo_id TEXT,                   -- brand_logos.logo_id
  headcount        INTEGER,
  workplace_preset TEXT NOT NULL,
  visual_style     TEXT NOT NULL,
  brief_mode       TEXT NOT NULL,          -- EXPRESS | ADVANCED
  brief_json       TEXT,                   -- BriefV1 compilado (JSON), tal como se manda al motor
  notes            TEXT DEFAULT '',
  archived         INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fit_runs (
  fit_id     TEXT NOT NULL REFERENCES fit_requests(fit_id) ON DELETE CASCADE,
  run_id     TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (fit_id, run_id)
);
CREATE TABLE IF NOT EXISTS brand_logos (
  logo_id     TEXT PRIMARY KEY,
  scope       TEXT NOT NULL,               -- BROKERAGE | PROSPECT
  stored_name TEXT NOT NULL,
  mime_type   TEXT NOT NULL,
  size_bytes  INTEGER NOT NULL,
  sha256      TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
-- ==============================================================================================
-- E31 — INTENTOS DE AMBIENTACIÓN. Un libro mayor, no una galería: cada intento es independiente,
-- auditable y se conserva aunque se rechace. Lo que sale de acá NO es un asset del cliente hasta
-- que un humano lo aprueba; recién entonces se publica como PHOTO_STAGED en property_assets.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS staging_attempts (
  attempt_id        TEXT PRIMARY KEY,
  property_id       TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  source_asset_id   TEXT NOT NULL,             -- la PHOTO_ORIGINAL de la que sale
  fit_id            TEXT,                      -- NULL = pack base; con valor = propuesta Pro
  benchmark_id      TEXT,                      -- con valor = nació del bake-off, no de un cliente
  visual_style      TEXT NOT NULL,
  provider          TEXT NOT NULL,
  model             TEXT,
  request_version   TEXT NOT NULL,
  prompt_hash       TEXT NOT NULL,
  input_sha256      TEXT NOT NULL,
  output_stored     TEXT,                      -- nombre interno del candidato; NO es un asset
  output_sha256     TEXT,
  output_asset_id   TEXT,                      -- PHOTO_STAGED publicado; sólo si APPROVED
  status            TEXT NOT NULL,             -- QUEUED | RUNNING | GENERATED | FAILED
  review_status     TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | APPROVED | REJECTED
  fidelity_status   TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | PASS | FAIL
  quality_score     INTEGER,                   -- 1..5, sólo si fidelity PASS
  failure_reasons   TEXT,                      -- JSON lista
  auto_warnings     TEXT,                      -- JSON lista (diagnóstico automático, NUNCA veredicto)
  cost_usd          REAL,
  cost_basis        TEXT,                      -- measured | list_price | unknown
  latency_ms        INTEGER,                   -- del proveedor
  pipeline_ms       INTEGER,                   -- total, de punta a punta
  seed              TEXT,
  error             TEXT,
  reviewer          TEXT,
  reviewed_at       TEXT,
  review_notes      TEXT,                      -- interno: NUNCA sale al pack
  started_at        TEXT,
  completed_at      TEXT,
  created_at        TEXT NOT NULL
);
-- ==============================================================================================
-- E32 — ESCALÍMETRO LAB. Tres tablas y ninguna duplica lo que ya se puede derivar:
--   benchmark_photos  qué fotos reales entran al bake-off, con sus rasgos difíciles
--   lab_notes         lo que Joaquín escribe mientras prueba ("el pilar quedó mal detectado")
--   lab_events        SÓLO acciones humanas sin otro hogar (aprobar proveedor, smoke test).
-- La línea de tiempo de una propiedad NO se guarda: se deriva de los artefactos, igual que su
-- estado. Un registro de eventos paralelo se desincroniza el día que alguien olvide escribirlo.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS benchmark_photos (
  asset_id    TEXT PRIMARY KEY REFERENCES property_assets(asset_id) ON DELETE CASCADE,
  property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  tags        TEXT,                        -- JSON: rasgos difíciles declarados por un humano
  reason      TEXT DEFAULT '',             -- por qué entra al benchmark
  added_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_notes (
  note_id     TEXT PRIMARY KEY,
  property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  fit_id      TEXT,
  scope       TEXT NOT NULL DEFAULT 'PROPERTY',   -- PROPERTY | FIT | LAYOUT | STAGING
  body        TEXT NOT NULL,
  author      TEXT DEFAULT '',
  created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_events (
  event_id    TEXT PRIMARY KEY,
  kind        TEXT NOT NULL,               -- PROVIDER_APPROVED | PROVIDER_SMOKE | BENCHMARK_RUN...
  property_id TEXT,
  detail      TEXT,                        -- JSON saneado: nunca credenciales
  author      TEXT DEFAULT '',
  created_at  TEXT NOT NULL
);
-- ==============================================================================================
-- E32.2 — DERECHOS DE COMPRA. Un Pack cubre UNA propiedad; una cuenta puede comprar muchos Packs.
-- El derecho vive en la COMPRA y en la PROPIEDAD, nunca en "cuántas propiedades hay en la base".
-- No hay dinero acá: una concesión se crea simulada desde el LAB o se otorgaría al cobrar.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS pack_grants (
  grant_id    TEXT PRIMARY KEY,
  source      TEXT NOT NULL,           -- SIMULATED_LAB | PURCHASE | LEGACY
  product     TEXT NOT NULL,           -- ONE_OFF | PRO
  status      TEXT NOT NULL,           -- AVAILABLE | ASSIGNED
  property_id TEXT REFERENCES properties(property_id) ON DELETE SET NULL,
  note        TEXT DEFAULT '',
  created_at  TEXT NOT NULL,
  assigned_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_grant_prop ON pack_grants(property_id)
  WHERE property_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_grant_status ON pack_grants(status, product);
-- ==============================================================================================
-- E33 — EVALUACIONES DE PRODUCTO. La razón por la que existe el laboratorio: poder decir si lo que
-- salió sirve. Cuatro valores, motivos opcionales y un comentario opcional.
-- La procedencia técnica (motor, sha del artefacto, proveedor, corrida) se guarda SIEMPRE y NO se
-- le muestra a nadie: es lo que permite correlacionar "esto quedó mal" con la versión exacta que
-- lo produjo. Sin eso, el feedback es una opinión sobre nada.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS product_reviews (
  review_id       TEXT PRIMARY KEY,
  property_id     TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  artifact_type   TEXT NOT NULL,       -- PLANO | LAYOUT | STAGING | PACK1 | ALTERNATIVA | PACK2
  artifact_id     TEXT,                -- asset_id, attempt_id o alt, según el tipo
  fit_id          TEXT,
  rating          TEXT NOT NULL,       -- EXCELENTE | BUENO | MALO | PESIMO
  reason_tags     TEXT,                -- JSON
  comment         TEXT DEFAULT '',
  engine_version  TEXT,
  artifact_sha256 TEXT,
  provider        TEXT,
  model           TEXT,
  run_id          TEXT,
  author          TEXT DEFAULT '',
  -- E35 §15 — con qué ingest se produjo lo que se está calificando. Sin esto, un "PÉSIMO" no
  -- distingue un motor malo de una unidad mal elegida o una escala supuesta.
  unit_selection_source     TEXT,
  unit_selection_confidence REAL,
  scale_source              TEXT,
  scale_confidence          REAL,
  geometry_confidences      TEXT,   -- JSON: la confianza del motor por elemento
  created_at      TEXT NOT NULL
);
-- ==============================================================================================
-- E34 — QUÉ DEDUJO EL SISTEMA AL INGERIR UNA PLANTA, y con cuánta confianza. Existe para poder
-- correlacionar después "este layout quedó malo" con "la escala se dedujo de 3 puertas con 0.62 de
-- confianza". Sin esto, el feedback no distingue un mal motor de un mal ingest.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS ingest_inference (
  property_id      TEXT PRIMARY KEY REFERENCES properties(property_id) ON DELETE CASCADE,
  case_id          TEXT,
  scale_source     TEXT,        -- PUBLISHED_AREA | AUTO_DOOR | MANUAL | UNKNOWN
  scale_value      REAL,        -- px_per_m finalmente usado
  scale_confidence REAL,
  evidence_count   INTEGER,
  cross_checks     TEXT,        -- JSON: área publicada vs derivada, acuerdo entre métodos
  access_source    TEXT,        -- AUTO | MANUAL | NONE
  access_confidence REAL,
  geometry_source  TEXT,        -- AUTO_ACCEPTED_BY_RULE | HUMAN_CONFIRMED | PENDING
  notes            TEXT,
  -- E35 — POR QUÉ hace falta una persona, en palabras. E34 lo calculaba y lo tiraba: la pantalla
  -- terminaba mostrando la nota de la escala como si fuera el motivo de la revisión.
  review_reason    TEXT,
  updated_at       TEXT NOT NULL
);
-- ==============================================================================================
-- E35 — QUÉ REGIÓN DE LA LÁMINA ES LA UNIDAD, y de dónde salió esa respuesta. Existe separada de
-- `ingest_inference` porque son dos certezas distintas (E35 §8): saber QUÉ polígono es la oficina
-- es previo e independiente de saber CUÁNTOS metros mide. Confundirlas fue el defecto de E34.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS unit_selection (
  property_id           TEXT PRIMARY KEY REFERENCES properties(property_id) ON DELETE CASCADE,
  case_id               TEXT,
  status                TEXT NOT NULL,   -- RESOLVED | NEEDS_INTERNAL_REVIEW | NO_DRAWING
  source                TEXT,            -- AUTO | HUMAN_PICK | DECLARED | PRE_EXISTING
  confidence            REAL,
  candidate_count       INTEGER,
  selected_candidate_id TEXT,
  candidates            TEXT,            -- JSON: el modelo completo, evidencia incluida
  evidence_summary      TEXT,
  reason_codes          TEXT,            -- JSON
  updated_at            TEXT NOT NULL
);
-- ==============================================================================================
-- E35 §17 — cuántas veces el flujo "automático" necesitó de verdad a una persona. Una fila por
-- intervención, con su motivo. Es la única forma de saber si el ingest mejora o sólo lo parece.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS manual_interventions (
  intervention_id TEXT PRIMARY KEY,
  property_id     TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  reason          TEXT NOT NULL,   -- UNIT_SELECTION | SCALE | GEOMETRY | STAGING | OTHER
  detail          TEXT DEFAULT '',
  created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_interv_prop ON manual_interventions(property_id, created_at);
-- ==============================================================================================
-- E36 §8/§9 — ETIQUETA DE VERDAD sobre la GEOMETRÍA, separada de la calificación de producto.
-- Que un Pack 1 haya quedado "Bueno" NO prueba que el núcleo estuviera bien recortado: son dos
-- juicios distintos sobre dos cosas distintas, y mezclarlos haría inútil la calibración. Una fila
-- por (propiedad, componente); la última vale.
-- ==============================================================================================
CREATE TABLE IF NOT EXISTS gold_labels (
  property_id       TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
  component         TEXT NOT NULL,   -- unit | perimeter | core | primary_entrance | columns | daylight | scale
  verdict           TEXT NOT NULL,   -- CORRECTO | INCORRECTO | INCOMPLETO | NO_APLICA
  note              TEXT DEFAULT '',
  engine_confidence REAL,            -- la confianza que el motor tenía CUANDO se etiquetó
  engine_version    TEXT,
  author            TEXT DEFAULT '',
  -- E36.1 — DE QUÉ CLASE DE JUICIO viene esta etiqueta. `author` no sirve para esto: es un valor
  -- por defecto del servidor (ESCALIMETRO_REVIEWER), no un registro de quién miró. Sólo
  -- HUMAN_VERIFIED es ground truth y sólo eso entra a calibración.
  provenance        TEXT NOT NULL DEFAULT 'PROVISIONAL_DOGFOOD',
  created_at        TEXT NOT NULL,
  PRIMARY KEY (property_id, component)
);
CREATE INDEX IF NOT EXISTS ix_gold_comp ON gold_labels(component, verdict);
CREATE INDEX IF NOT EXISTS ix_reviews_prop ON product_reviews(property_id, created_at);
CREATE INDEX IF NOT EXISTS ix_reviews_kind ON product_reviews(artifact_type, rating);
CREATE INDEX IF NOT EXISTS ix_notes_prop ON lab_notes(property_id, created_at);
CREATE INDEX IF NOT EXISTS ix_events_kind ON lab_events(kind, created_at);
CREATE INDEX IF NOT EXISTS ix_staging_prop ON staging_attempts(property_id, created_at);
CREATE INDEX IF NOT EXISTS ix_staging_review ON staging_attempts(review_status, status);
CREATE INDEX IF NOT EXISTS ix_fits_prop ON fit_requests(property_id, created_at);
CREATE INDEX IF NOT EXISTS ix_fitruns_fit ON fit_runs(fit_id);
CREATE INDEX IF NOT EXISTS ix_assets_prop ON property_assets(property_id, kind, sort_order);
CREATE INDEX IF NOT EXISTS ix_props_case ON properties(floorplan_case_id);
CREATE INDEX IF NOT EXISTS ix_packs_prop ON packs(property_id);
CREATE INDEX IF NOT EXISTS ix_reviews_run ON reviews(run_id, alt);
CREATE INDEX IF NOT EXISTS ix_runs_case ON runs(case_id);
CREATE INDEX IF NOT EXISTS ix_briefs_case ON briefs(case_id);

-- ================================================================================================
-- E17.0 — POTENCIAL DE UNA PUBLICACIÓN
-- ================================================================================================
-- Un LISTING no es una PROPERTY del LAB. Comparten la palabra y poco más: una property del LAB es
-- una oficina que nosotros preparamos para publicar, con su pack, su producto, sus concesiones y
-- su piloto; un listing es un aviso YA PUBLICADO por otro, del que sólo tenemos lo que el aviso
-- muestra. Meterlos en la misma tabla habría hecho aparecer cada aviso analizado en la portada del
-- LAB, en el contador del piloto y en las concesiones de pack —la migración de E32.2 le crea una a
-- toda propiedad sin ella—, que es exactamente el comportamiento existente que E17.0 no debe
-- romper. Tablas separadas; lo que sí se comparte es el PIPELINE DE PLANOS, vía `plan_case_id`.
CREATE TABLE IF NOT EXISTS listings (
  listing_id      TEXT PRIMARY KEY,
  title           TEXT NOT NULL DEFAULT '',
  property_type   TEXT NOT NULL DEFAULT 'UNKNOWN',  -- APARTMENT|HOUSE|OFFICE|RETAIL|WAREHOUSE|LAND|UNKNOWN
  operation       TEXT,                             -- SALE | RENT
  source          TEXT NOT NULL,                    -- MANUAL | URL
  source_url      TEXT,
  location        TEXT DEFAULT '',
  price           REAL,
  currency        TEXT,
  area_m2         REAL,
  bedrooms        INTEGER,
  bathrooms       INTEGER,
  parking         INTEGER,
  storage         INTEGER,
  orientation     TEXT,
  common_expenses REAL,
  description     TEXT DEFAULT '',
  cover_media_id  TEXT,
  -- El enlace al motor EXISTENTE. No se copia ni se reimplementa nada del pipeline de planos: se
  -- crea un caso con el mismo alta que usa el resto del sistema y se guarda su id.
  plan_case_id    TEXT REFERENCES cases(case_id) ON DELETE SET NULL,
  notes           TEXT DEFAULT '',
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listing_media (
  media_id          TEXT PRIMARY KEY,
  listing_id        TEXT NOT NULL REFERENCES listings(listing_id) ON DELETE CASCADE,
  kind              TEXT NOT NULL,    -- PHOTO | PLAN | CONCEPTUAL
  original_filename TEXT NOT NULL,
  stored_name       TEXT NOT NULL,    -- nombre interno; el del usuario nunca toca el filesystem
  mime_type         TEXT NOT NULL,
  size_bytes        INTEGER NOT NULL,
  sha256            TEXT NOT NULL,
  width_px          INTEGER,
  height_px         INTEGER,
  sort_order        INTEGER NOT NULL DEFAULT 0,
  -- Las MEDICIONES de esta imagen (luminancia, nitidez, huella perceptual…). Se guardan con el
  -- medio y no se recalculan al vuelo: el informe tiene que poder mostrar de dónde salió cada
  -- punto aunque el analizador cambie después.
  analysis          TEXT,
  metadata          TEXT,
  created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS potential_reports (
  report_id           TEXT PRIMARY KEY,
  listing_id          TEXT NOT NULL REFERENCES listings(listing_id) ON DELETE CASCADE,
  score               INTEGER NOT NULL,
  max_score           INTEGER NOT NULL,
  dimensions          TEXT NOT NULL,   -- JSON: por dimensión, cada criterio con su medición y sus puntos
  primary_opportunity TEXT,            -- JSON
  capabilities        TEXT,            -- JSON: qué sabemos hacer con ESTE material
  analyzer_version    TEXT NOT NULL,
  engine_version      TEXT,
  created_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS potential_findings (
  finding_id   TEXT PRIMARY KEY,
  report_id    TEXT NOT NULL REFERENCES potential_reports(report_id) ON DELETE CASCADE,
  listing_id   TEXT NOT NULL,
  dimension    TEXT NOT NULL,
  code         TEXT NOT NULL,
  level        TEXT NOT NULL,   -- HIGH | MEDIUM | LOW: tamaño de la OPORTUNIDAD, no gravedad
  headline     TEXT NOT NULL,
  explanation  TEXT NOT NULL,
  evidence     TEXT,            -- JSON: las mediciones que lo sostienen
  intervention TEXT,            -- tipo recomendado
  score_delta  REAL,            -- HEURÍSTICO: los puntos que recuperaría. No es una predicción.
  media_id     TEXT,
  rank         INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);
-- Contrato del ANTES / DESPUÉS. Existe desde ya aunque la generación visual todavía no esté
-- conectada: es preferible un contrato honesto con estado NOT_AVAILABLE a una demo simulada.
CREATE TABLE IF NOT EXISTS intervention_demos (
  demo_id             TEXT PRIMARY KEY,
  listing_id          TEXT NOT NULL REFERENCES listings(listing_id) ON DELETE CASCADE,
  intervention        TEXT NOT NULL,
  source_media_id     TEXT,
  result_media_id     TEXT,
  status              TEXT NOT NULL,   -- NOT_AVAILABLE | REQUESTED | GENERATING | READY | FAILED
  visualization_class TEXT NOT NULL,   -- CONCEPTUAL_VISUALIZATION
  disclosure          TEXT NOT NULL,
  provider            TEXT,
  model               TEXT,
  notes               TEXT DEFAULT '',
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_media_listing ON listing_media(listing_id, kind, sort_order);
CREATE INDEX IF NOT EXISTS ix_reports_listing ON potential_reports(listing_id, created_at);
CREATE INDEX IF NOT EXISTS ix_findings_report ON potential_findings(report_id, rank);
CREATE INDEX IF NOT EXISTS ix_demos_listing ON intervention_demos(listing_id, created_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seconds_between(a: Optional[str], b: Optional[str]) -> Optional[float]:
    """Segundos entre dos marcas ISO, o None si falta alguna o no se dejan leer.

    Devuelve None en vez de 0 cuando no se puede medir: un cero se promedia y miente; un None se
    excluye de la muestra y se cuenta como lo que es, una medición que no existe."""
    if not a or not b:
        return None
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except (TypeError, ValueError):
        return None


def property_dir(property_id: str) -> str:
    """Directorio de assets de una propiedad, dentro del mismo volumen persistente que los casos.
    El `property_id` es generado por nosotros, así que no hay forma de que un nombre del usuario
    escape del directorio."""
    return os.path.join(DATA_DIR, "properties", property_id)


def listing_dir(listing_id: str) -> str:
    """Directorio de medios de un aviso. Separado de `properties/` a propósito: son dos productos
    distintos sobre el mismo volumen, y mezclar sus archivos haría imposible borrar uno sin mirar
    el otro. El `listing_id` lo generamos nosotros, así que ningún nombre del usuario puede
    escapar del directorio."""
    return os.path.join(DATA_DIR, "listings", listing_id)


def brand_dir() -> str:
    """Los logos de marca no pertenecen a ninguna propiedad: la corredora es una sola y el logo
    de un prospecto se reusa entre fit requests. Viven aparte, en el mismo volumen."""
    return os.path.join(DATA_DIR, "brand")


def case_dir(case_id: str) -> str:
    """Carpeta del caso DENTRO del volumen persistente. Es también el `case_dir` que consume el
    motor existente: mismo contrato (`case.json` + `outputs/floorplate.json`), otra raíz."""
    return os.path.join(DATA_DIR, "cases", case_id)


def connect() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn = c
    return c


def init() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "cases"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "properties"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "listings"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "brand"), exist_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    # Migración en sitio para bases creadas antes de E27.3: SQLite no tiene ADD COLUMN IF NOT
    # EXISTS, así que se mira el esquema. Sin esto, un volumen ya existente se rompería al arrancar.
    tiene = {r["name"] for r in conn.execute("PRAGMA table_info(intake)").fetchall()}
    for col in ("analyzed_at", "answers", "scale_points"):
        if col not in tiene:
            conn.execute(f"ALTER TABLE intake ADD COLUMN {col} TEXT")
    # E34 — `drawing_scope` es un HECHO DE LA FUENTE (E16.5): si la lámina es una sola oficina o
    # varias. El motor se niega a deducirlo de la ausencia de datos, y hace bien. Se guarda cuando
    # una persona lo declara, que es la única forma honesta de saberlo.
    if "drawing_scope" not in tiene:
        conn.execute("ALTER TABLE intake ADD COLUMN drawing_scope TEXT")
    # E30 — un pack ahora puede ser el BASE de la propiedad o el de un fit request concreto.
    # Las bases de E28 ya tienen la tabla creada, así que la columna se añade en sitio.
    tiene_packs = {r["name"] for r in conn.execute("PRAGMA table_info(packs)").fetchall()}
    if "fit_id" not in tiene_packs:
        conn.execute("ALTER TABLE packs ADD COLUMN fit_id TEXT")
    if "kind" not in tiene_packs:
        conn.execute("ALTER TABLE packs ADD COLUMN kind TEXT NOT NULL DEFAULT 'BASE'")
    # E31 — la foto principal elegida y el motivo de un pack degradado son hechos de la propiedad.
    tiene_props = {r["name"] for r in conn.execute("PRAGMA table_info(properties)").fetchall()}
    if "hero_photo_asset_id" not in tiene_props:
        conn.execute("ALTER TABLE properties ADD COLUMN hero_photo_asset_id TEXT")
    if "pack_override_reason" not in tiene_props:
        conn.execute("ALTER TABLE properties ADD COLUMN pack_override_reason TEXT")
    # E32 — la valoración interna de una propiedad mientras se prueba (§17). No la ve el cliente.
    if "lab_feedback" not in tiene_props:
        conn.execute("ALTER TABLE properties ADD COLUMN lab_feedback TEXT")
    # E32.2 — el producto es de la PROPIEDAD, no de la cuenta. Las propiedades que ya existían
    # entran como ONE_OFF: es el default conservador, y tener muchos outputs históricos no es
    # evidencia de que alguien pagara Pro.
    if "product" not in tiene_props:
        conn.execute("ALTER TABLE properties ADD COLUMN product TEXT NOT NULL DEFAULT 'ONE_OFF'")
    # E36 §5/§7 — si la propiedad entra en el piloto real y de dónde salió su material. El default
    # de `source_type` es NULL —"sin declarar"— y no un valor cómodo: una propiedad heredada NO es
    # evidencia real hasta que alguien diga de dónde vino. Inventarle procedencia infla la muestra.
    for col in ("source_type", "source_reference", "pack1_started_at", "geometry_ready_at",
                "layout_ready_at", "staging_ready_at", "pack1_ready_at"):
        if col not in tiene_props:
            conn.execute(f"ALTER TABLE properties ADD COLUMN {col} TEXT")
    if "in_pilot" not in tiene_props:
        conn.execute("ALTER TABLE properties ADD COLUMN in_pilot INTEGER NOT NULL DEFAULT 0")
    # E32 §I — para qué se pidió un intento y si puede llegar a un cliente. Un candidato
    # experimental (smoke, bake-off, proveedor no aprobado) NUNCA se publica como entregable.
    tiene_att = {r["name"] for r in conn.execute("PRAGMA table_info(staging_attempts)").fetchall()}
    if "purpose" not in tiene_att:
        conn.execute("ALTER TABLE staging_attempts ADD COLUMN purpose TEXT NOT NULL DEFAULT 'PRODUCT'")
    if "experimental" not in tiene_att:
        conn.execute("ALTER TABLE staging_attempts ADD COLUMN experimental INTEGER NOT NULL DEFAULT 0")
    tiene_fits = {r["name"] for r in conn.execute("PRAGMA table_info(fit_requests)").fetchall()}
    if "lab_feedback" not in tiene_fits:
        conn.execute("ALTER TABLE fit_requests ADD COLUMN lab_feedback TEXT")
    # E35 §15 — el feedback de E33 se guardó sin saber de qué ingest venía. Las filas anteriores
    # se quedan con NULL: eso es "no se registró", que es la verdad, y no se rellena con supuestos.
    # E36.1 — las etiquetas que ya existían NO pueden reclamar verificación humana: se crearon
    # antes de que hubiera forma de registrar de qué clase de juicio venían. El default conservador
    # las deja como PROVISIONAL_DOGFOOD. No se borra ninguna: se excluyen de la calibración y se
    # muestran como pendientes de confirmar, que es lo que honestamente son.
    tiene_gold = {r["name"] for r in conn.execute("PRAGMA table_info(gold_labels)").fetchall()}
    if tiene_gold and "provenance" not in tiene_gold:
        conn.execute("ALTER TABLE gold_labels ADD COLUMN provenance TEXT NOT NULL "
                     "DEFAULT 'PROVISIONAL_DOGFOOD'")
    tiene_inf = {r["name"] for r in conn.execute("PRAGMA table_info(ingest_inference)").fetchall()}
    if "review_reason" not in tiene_inf:
        conn.execute("ALTER TABLE ingest_inference ADD COLUMN review_reason TEXT")
    tiene_rev = {r["name"] for r in conn.execute("PRAGMA table_info(product_reviews)").fetchall()}
    for col, tipo in (("unit_selection_source", "TEXT"), ("unit_selection_confidence", "REAL"),
                      ("scale_source", "TEXT"), ("scale_confidence", "REAL"),
                      ("geometry_confidences", "TEXT")):
        if col not in tiene_rev:
            conn.execute(f"ALTER TABLE product_reviews ADD COLUMN {col} {tipo}")
    # E32.2 — toda propiedad tiene que tener su concesión. Las heredadas reciben una LEGACY ya
    # asignada: así el modelo queda completo sin inventar una compra que nadie hizo. El SELECT se
    # materializa antes de insertar: iterar un cursor mientras se escribe la tabla que su subconsulta
    # lee es pedirle a SQLite que decida por nosotros.
    huerfanas = conn.execute(
        "SELECT property_id, product FROM properties p WHERE NOT EXISTS "
        "(SELECT 1 FROM pack_grants g WHERE g.property_id=p.property_id)").fetchall()
    for row in huerfanas:
        conn.execute("INSERT INTO pack_grants(grant_id, source, product, status, property_id, "
                     "note, created_at, assigned_at) VALUES (?,?,?,'ASSIGNED',?,?,?,?)",
                     ("gr_lg_" + uuid.uuid4().hex[:10], "LEGACY", row["product"] or "ONE_OFF",
                      row["property_id"], "propiedad anterior a E32.2", now(), now()))
    # E27.2 §6/§9 — reparación de estados heredados del bug que E27.2 corrige: un caso quedó en
    # FAILED porque se pudo pulsar "generar" sin preparar el shell. Eso nunca fue un fallo técnico,
    # era un intake incompleto. Si el caso no tiene geometría, su estado honesto es NEEDS_INPUT.
    # Sólo toca casos SIN floorplate: uno que sí lo tiene y falló de verdad conserva su FAILED.
    for row in conn.execute("SELECT case_id FROM cases WHERE status='FAILED'").fetchall():
        fp = os.path.join(case_dir(row["case_id"]), "outputs", "floorplate.json")
        if not os.path.exists(fp):
            conn.execute("UPDATE cases SET status='NEEDS_INPUT' WHERE case_id=?", (row["case_id"],))
    # un caso GENERATING que quedó colgado vuelve a donde su artefacto diga (no a READY a ciegas)
    conn.execute("UPDATE cases SET status='NEEDS_CONFIRMATION' WHERE status='ANALYZING'")
    conn.commit()


def reset_orphans() -> None:
    """Marca como fallido lo que quedó a medias cuando el proceso anterior murió.

    Vive APARTE de `init()` y sólo lo llama el arranque del servidor web. Estaba dentro de `init()`,
    y eso significaba que CUALQUIER proceso que abriera la base —una CLI, un script de
    comprobación— mataba las corridas y los intentos en vuelo del servidor, y mostraba un fallo que
    nunca ocurrió. Lo descubrí matando una corrida real con mi propio script de diagnóstico."""
    conn = connect()
    # E31 — un intento de ambientación que decía RUNNING murió con el proceso. Misma regla que
    # las corridas: no se reanuda solo ni se deja "generando" para siempre.
    conn.execute("UPDATE staging_attempts SET status='FAILED', completed_at=?, "
                 "error=COALESCE(error,'') || '[reinicio] el servicio se reinició durante la generación' "
                 "WHERE status IN ('RUNNING','QUEUED')", (now(),))
    # Honestidad al reiniciar: un job que decía RUNNING murió con el proceso anterior. No se
    # reanuda solo y no se deja mintiendo en pantalla.
    conn.execute("UPDATE runs SET status='FAILED', finished_at=?, "
                 "log=COALESCE(log,'') || '\n[reinicio] el servicio se reinició durante la corrida' "
                 "WHERE status IN ('RUNNING','QUEUED')", (now(),))
    conn.execute("UPDATE alternatives SET status='FAILED' WHERE status='GENERATING'")
    conn.execute("UPDATE cases SET status='READY' WHERE status='GENERATING'")
    conn.commit()


def q(sql: str, args: tuple = ()) -> List[sqlite3.Row]:
    return connect().execute(sql, args).fetchall()


def q1(sql: str, args: tuple = ()) -> Optional[sqlite3.Row]:
    return connect().execute(sql, args).fetchone()


def ex(sql: str, args: tuple = ()) -> None:
    conn = connect()
    conn.execute(sql, args)
    conn.commit()


def js(v: Any, default=None):
    """JSON tolerante: la UI nunca debe romperse por una columna vacía."""
    if v in (None, ""):
        return default
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return default
