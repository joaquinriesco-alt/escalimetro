"""E27 §7/§9 — puente al motor EXISTENTE y cola de jobs.

Decisión de arquitectura: el motor se invoca como SUBPROCESO del módulo que ya existe

    python -m escalimetro.layout.e07.run --case <case_dir> --brief <brief.json> --out-name <run_id>

y sus resultados se leen de los artefactos que ese módulo ya escribe (metrics.json, quality.json,
traceability.json, no_fit.json). Ni una línea del algoritmo se toca ni se copia: candidate
generation, caps, ranking, CP-SAT, module_max_path, bench constraints, dimensiones, espina,
circulación y pesos quedan exactamente donde estaban.

Por qué subproceso y no import: aísla el crash. Una corrida que muere por memoria o por una
excepción del solver no se lleva puesto el servidor web, y el log queda entero para leerlo.

Cola: un hilo trabajador y una tabla. Es lo más simple que cumple §9 (la request HTTP no espera
minutos). No hay Redis, ni Celery, ni broker. Si el proceso muere, `store.init()` marca la corrida
como FAILED en el arranque siguiente en vez de dejarla diciendo "generando" para siempre.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from typing import Dict, List, Optional

from . import intake, store

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALTS = ("A", "B", "C")
#: Techo de pared por corrida. El motor apunta a <120 s por alternativa; esto es sólo un seguro
#: contra una corrida colgada, no un presupuesto de búsqueda (ése vive dentro del motor).
RUN_TIMEOUT_S = int(os.environ.get("ESCALIMETRO_RUN_TIMEOUT_S", "3600"))

_jobs: "queue.Queue[str]" = queue.Queue()
_worker: Optional[threading.Thread] = None
_lock = threading.Lock()


def engine_commit() -> str:
    """Commit del motor que produjo un resultado. Va a cada revisión (§12).

    En el contenedor no hay `.git` (lo excluye .dockerignore), así que `git rev-parse` no sirve:
    se usa el SHA que Railway inyecta. Sin esto la trazabilidad diría "unknown" en producción,
    que es justo el dato que §12 exige no perder."""
    sha = os.environ.get("ESCALIMETRO_ENGINE_COMMIT") or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    if sha:
        return sha.strip()
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=10)
        sha = (out.stdout or "").strip() or "unknown"
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                               capture_output=True, text=True, timeout=10)
        return sha + ("+dirty" if (dirty.stdout or "").strip() else "")
    except Exception:
        return os.environ.get("ESCALIMETRO_ENGINE_COMMIT", "unknown")


def run_dir(case_id: str, run_id: str) -> str:
    return os.path.join(store.case_dir(case_id), "layouts", run_id)


# ---------------------------------------------------------------------------------------------
# lectura de resultados — sólo lee lo que el motor ya escribe
# ---------------------------------------------------------------------------------------------
def _read(path: str) -> Optional[Dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def collect(case_id: str, run_id: str) -> List[Dict]:
    """Estado real de cada alternativa a partir de los artefactos. Nunca inventa un estado:
    si no hay ni layout ni no_fit.json, la alternativa es FAILED y se dice."""
    base = os.path.join(run_dir(case_id, run_id), "alternatives")
    out = []
    for alt in ALTS:
        d = os.path.join(base, alt)
        tr = _read(os.path.join(d, "traceability.json")) or {}
        qa = _read(os.path.join(d, "quality.json"))
        me = _read(os.path.join(d, "metrics.json"))
        nf = _read(os.path.join(d, "no_fit.json"))
        if me is not None:
            status, detail = "FIT", None
        elif nf is not None:
            status, detail = nf.get("status", "FAILED"), nf
        else:
            status, detail = "FAILED", {"reason": "el motor no dejó artefacto para esta alternativa"}
        out.append({"alt": alt, "status": status, "name": (nf or {}).get("name") or _name_of(qa, tr),
                    "layout_sha256": tr.get("layout_sha256"), "metrics": me,
                    "quality": qa, "detail": detail})
    return out


def _name_of(qa: Optional[Dict], tr: Dict) -> str:
    return {"A": "EFICIENTE", "B": "BALANCEADO", "C": "COLABORATIVO"}.get(tr.get("strategy") or "", "")


# ---------------------------------------------------------------------------------------------
# ejecución
# ---------------------------------------------------------------------------------------------
def _execute(run_id: str) -> None:
    row = store.q1("SELECT * FROM runs WHERE run_id=?", (run_id,))
    if row is None:
        return
    case_id, brief_id = row["case_id"], row["brief_id"]
    cdir = store.case_dir(case_id)
    brief_path = os.path.join(cdir, "briefs", f"{brief_id}.json")
    _c = store.q1("SELECT status FROM cases WHERE case_id=?", (case_id,))
    prev_case = _c["status"] if _c else "NEEDS_INPUT"

    # E27.2 §4/§6 — última verificación antes de gastar cinco minutos de CPU. Si al job le falta un
    # input del usuario, NO se llama al motor: el resultado sería un traceback y el usuario vería
    # FAILED por algo que es suyo y corregible. Se devuelve el caso a NEEDS_INPUT con la lista.
    faltan = intake.blockers_for_generate(case_id)
    if faltan:
        store.ex("UPDATE runs SET status='FAILED', started_at=?, finished_at=?, log=? "
                 "WHERE run_id=?",
                 (store.now(), store.now(),
                  "[web] no se ejecutó el motor porque faltan datos del intake:\n  - "
                  + "\n  - ".join(faltan), run_id))
        for alt in ALTS:
            store.ex("INSERT OR REPLACE INTO alternatives(run_id, alt, status) "
                     "VALUES (?,?,'FAILED')", (run_id, alt))
        store.ex("UPDATE cases SET status='NEEDS_INPUT' WHERE case_id=?", (case_id,))
        return

    store.ex("UPDATE runs SET status='RUNNING', started_at=?, engine_commit=? WHERE run_id=?",
             (store.now(), engine_commit(), run_id))
    store.ex("UPDATE cases SET status='GENERATING' WHERE case_id=?", (case_id,))
    for alt in ALTS:
        store.ex("INSERT OR REPLACE INTO alternatives(run_id, alt, status) VALUES (?,?,'GENERATING')",
                 (run_id, alt))
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "src"), MPLBACKEND="Agg")
    cmd = [sys.executable, "-m", "escalimetro.layout.e07.run",
           "--case", cdir, "--brief", brief_path, "--out-name", run_id]
    log, failed = "", False
    try:
        p = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True,
                           timeout=RUN_TIMEOUT_S)
        log = (p.stdout or "") + (p.stderr or "")
        failed = p.returncode != 0
    except subprocess.TimeoutExpired:
        log, failed = f"[web] la corrida superó {RUN_TIMEOUT_S} s y se cortó", True
    except Exception as e:                                    # noqa: BLE001 — el log es el producto
        log, failed = f"[web] no se pudo lanzar el motor: {e!r}", True

    results = collect(case_id, run_id)
    for r in results:
        store.ex("INSERT OR REPLACE INTO alternatives"
                 "(run_id, alt, name, status, layout_sha256, metrics, quality, detail) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (run_id, r["alt"], r["name"], r["status"], r["layout_sha256"],
                  json.dumps(r["metrics"], ensure_ascii=False) if r["metrics"] else None,
                  json.dumps(r["quality"], ensure_ascii=False) if r["quality"] else None,
                  json.dumps(r["detail"], ensure_ascii=False) if r["detail"] else None))
    n_fit = sum(1 for r in results if r["status"] == "FIT")
    # El estado del CASO no miente: si el motor corrió y ninguna alternativa dio layout, el caso
    # no es FAILED (el motor hizo su trabajo y respondió con un estado honesto), es PARTIAL.
    #
    # E27.2 §6 — y si la corrida revienta por un motivo TÉCNICO, la que falla es la corrida, no el
    # caso: el shell sigue preparado y se puede reintentar. El caso vuelve a donde estaba.
    if failed and n_fit == 0 and all(r["status"] == "FAILED" for r in results):
        run_status = "FAILED"
        case_status = prev_case if prev_case in ("READY", "COMPLETE", "PARTIAL") else "NEEDS_INPUT"
    elif n_fit == len(ALTS):
        run_status, case_status = "DONE", "COMPLETE"
    else:
        run_status, case_status = "DONE", "PARTIAL"
    store.ex("UPDATE runs SET status=?, finished_at=?, log=? WHERE run_id=?",
             (run_status, store.now(), log[-20000:], run_id))
    store.ex("UPDATE cases SET status=? WHERE case_id=?", (case_status, case_id))


def _loop() -> None:
    while True:
        run_id = _jobs.get()
        try:
            _execute(run_id)
        except Exception as e:                                # noqa: BLE001
            store.ex("UPDATE runs SET status='FAILED', finished_at=?, log=? WHERE run_id=?",
                     (store.now(), f"[web] error del worker: {e!r}", run_id))
        finally:
            _jobs.task_done()


def start_worker() -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, name="escalimetro-jobs", daemon=True)
            _worker.start()


def enqueue(run_id: str) -> None:
    start_worker()
    _jobs.put(run_id)


def pending() -> int:
    return _jobs.qsize()
