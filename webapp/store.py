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
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DATA_DIR = os.environ.get("ESCALIMETRO_DATA_DIR") or os.path.join(os.getcwd(), ".data")
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
CREATE INDEX IF NOT EXISTS ix_fits_prop ON fit_requests(property_id, created_at);
CREATE INDEX IF NOT EXISTS ix_fitruns_fit ON fit_runs(fit_id);
CREATE INDEX IF NOT EXISTS ix_assets_prop ON property_assets(property_id, kind, sort_order);
CREATE INDEX IF NOT EXISTS ix_props_case ON properties(floorplan_case_id);
CREATE INDEX IF NOT EXISTS ix_packs_prop ON packs(property_id);
CREATE INDEX IF NOT EXISTS ix_reviews_run ON reviews(run_id, alt);
CREATE INDEX IF NOT EXISTS ix_runs_case ON runs(case_id);
CREATE INDEX IF NOT EXISTS ix_briefs_case ON briefs(case_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def property_dir(property_id: str) -> str:
    """Directorio de assets de una propiedad, dentro del mismo volumen persistente que los casos.
    El `property_id` es generado por nosotros, así que no hay forma de que un nombre del usuario
    escape del directorio."""
    return os.path.join(DATA_DIR, "properties", property_id)


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
    os.makedirs(os.path.join(DATA_DIR, "brand"), exist_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    # Migración en sitio para bases creadas antes de E27.3: SQLite no tiene ADD COLUMN IF NOT
    # EXISTS, así que se mira el esquema. Sin esto, un volumen ya existente se rompería al arrancar.
    tiene = {r["name"] for r in conn.execute("PRAGMA table_info(intake)").fetchall()}
    for col in ("analyzed_at", "answers", "scale_points"):
        if col not in tiene:
            conn.execute(f"ALTER TABLE intake ADD COLUMN {col} TEXT")
    # E30 — un pack ahora puede ser el BASE de la propiedad o el de un fit request concreto.
    # Las bases de E28 ya tienen la tabla creada, así que la columna se añade en sitio.
    tiene_packs = {r["name"] for r in conn.execute("PRAGMA table_info(packs)").fetchall()}
    if "fit_id" not in tiene_packs:
        conn.execute("ALTER TABLE packs ADD COLUMN fit_id TEXT")
    if "kind" not in tiene_packs:
        conn.execute("ALTER TABLE packs ADD COLUMN kind TEXT NOT NULL DEFAULT 'BASE'")
    # Honestidad al reiniciar: un job que decía RUNNING murió con el proceso anterior. No se
    # reanuda solo y no se deja mintiendo en pantalla.
    conn.execute("UPDATE runs SET status='FAILED', finished_at=?, "
                 "log=COALESCE(log,'') || '\n[reinicio] el servicio se reinició durante la corrida' "
                 "WHERE status IN ('RUNNING','QUEUED')", (now(),))
    conn.execute("UPDATE alternatives SET status='FAILED' WHERE status='GENERATING'")
    conn.execute("UPDATE cases SET status='READY' WHERE status='GENERATING'")
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
