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

#: Estados de caso del §4. Simples a propósito.
CASE_STATES = ("UPLOADED", "NEEDS_INPUT", "READY", "GENERATING", "COMPLETE", "PARTIAL", "FAILED")
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
CREATE INDEX IF NOT EXISTS ix_reviews_run ON reviews(run_id, alt);
CREATE INDEX IF NOT EXISTS ix_runs_case ON runs(case_id);
CREATE INDEX IF NOT EXISTS ix_briefs_case ON briefs(case_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    conn = connect()
    conn.executescript(SCHEMA)
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
