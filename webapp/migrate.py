"""E27 §19 — importa a la web los casos que ya existen en el repo (GPS 403 y GPS 401).

No se regenera nada y no se cambia ningún resultado: se copian los artefactos tal cual y se
registran en la base. 403 entra con sus tres alternativas FIT; 401 entra con sus tres estados
SEARCH_EXHAUSTED, que es lo que el motor respondió y lo que hay que mostrar.

Es idempotente: correrlo dos veces no duplica casos ni pisa revisiones ya escritas.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from typing import Dict, List, Optional

from . import engine, store

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEED = [
    {"case_id": "001_gps_403", "src": "cases/001_gps_403", "run": "E26_403",
     "brief_file": "briefs/BRIEF_EQUILIBRADO.json", "title": "Oficina 403",
     "source_name": "GPS Property", "area": 543.0},
    {"case_id": "002_gps_401", "src": "cases/002_gps_401", "run": "E26_401",
     "brief_file": "briefs/BRIEF_401_V1.json", "title": "Oficina 401",
     "source_name": "GPS Property", "area": 252.0},
]
#: Lo que el caso necesita para que el motor pueda volver a correr sobre él desde la web.
COPY_FILES = ["case.json", "overrides.json", "overrides_assisted.json"]
COPY_DIRS = ["outputs"]


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _copy(src: str, dst: str) -> None:
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    elif os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def migrate_one(spec: Dict) -> Optional[str]:
    case_id, src = spec["case_id"], os.path.join(REPO_ROOT, spec["src"])
    if not os.path.exists(os.path.join(src, "case.json")):
        return None
    cdir = store.case_dir(case_id)
    os.makedirs(cdir, exist_ok=True)
    for f in COPY_FILES:
        _copy(os.path.join(src, f), os.path.join(cdir, f))
    for d in COPY_DIRS:
        _copy(os.path.join(src, d), os.path.join(cdir, d))
    original = json.load(open(os.path.join(src, "case.json"), encoding="utf-8")).get("image", "")
    if original:
        _copy(os.path.join(src, original), os.path.join(cdir, original))
    run_id = spec["run"]
    _copy(os.path.join(src, "layouts", run_id), os.path.join(cdir, "layouts", run_id))

    # preview desde el original (para que la vista del caso no dependa de ningún PNG del repo)
    ext = os.path.splitext(original)[1].lower()
    if original and ext:
        try:
            from . import intake                              # noqa: PLC0415
            intake.make_preview(case_id, os.path.join(cdir, original), ext)
        except Exception:                                     # noqa: BLE001
            pass

    brief_src = os.path.join(REPO_ROOT, spec["brief_file"])
    brief = json.load(open(brief_src, encoding="utf-8"))
    brief_id = brief["brief_id"]
    os.makedirs(os.path.join(cdir, "briefs"), exist_ok=True)
    brief_dst = os.path.join(cdir, "briefs", f"{brief_id}.json")
    _copy(brief_src, brief_dst)
    brief_sha = _sha(brief_dst)

    results = engine.collect(case_id, run_id)
    n_fit = sum(1 for r in results if r["status"] == "FIT")
    status = "COMPLETE" if n_fit == len(results) else ("PARTIAL" if results else "READY")
    ecommit = next((r["quality"].get("engine_commit") for r in results
                    if r.get("quality")), None) or engine.engine_commit()

    if store.q1("SELECT case_id FROM cases WHERE case_id=?", (case_id,)) is None:
        store.ex("INSERT INTO cases(case_id, title, original_filename, source_file, mime, "
                 "uploaded_at, status, track, published_area_m2, source_name, notes) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (case_id, spec["title"], original or "(sin archivo)", original,
                  "image/png", store.now(), status, "DEVELOPMENT", spec["area"],
                  spec["source_name"], "Importado de E26 — resultados sin regenerar."))
        store.ex("INSERT INTO intake(case_id, declared_clean, confirmed, missing, updated_at) "
                 "VALUES (?,?,?,?,?)",
                 (case_id, "yes", json.dumps(["perimeter", "core", "columns", "daylight",
                                              "scale_assumption"]), json.dumps([]), store.now()))
    else:
        store.ex("UPDATE cases SET status=? WHERE case_id=?", (status, case_id))

    if store.q1("SELECT brief_id FROM briefs WHERE brief_id=?", (brief_id,)) is None:
        store.ex("INSERT INTO briefs(brief_id, case_id, name, headcount, workstations, rooms, "
                 "brief_sha256, created_at) VALUES (?,?,?,?,?,?,?,?)",
                 (brief_id, case_id, brief_id.replace("_", " ").title(),
                  brief["target_headcount"], brief["open_workstations"],
                  json.dumps(brief["rooms"], ensure_ascii=False), brief_sha, store.now()))

    if store.q1("SELECT run_id FROM runs WHERE run_id=?", (run_id,)) is None:
        store.ex("INSERT INTO runs(run_id, case_id, brief_id, status, engine_commit, created_at, "
                 "started_at, finished_at, log) VALUES (?,?,?,?,?,?,?,?,?)",
                 (run_id, case_id, brief_id, "DONE", ecommit, store.now(), store.now(),
                  store.now(), "[migración E27] corrida importada de E26; no se regeneró."))
    for r in results:
        store.ex("INSERT OR REPLACE INTO alternatives"
                 "(run_id, alt, name, status, layout_sha256, metrics, quality, detail) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (run_id, r["alt"], r["name"], r["status"], r["layout_sha256"],
                  json.dumps(r["metrics"], ensure_ascii=False) if r["metrics"] else None,
                  json.dumps(r["quality"], ensure_ascii=False) if r["quality"] else None,
                  json.dumps(r["detail"], ensure_ascii=False) if r["detail"] else None))
    return case_id


def run() -> List[str]:
    done = []
    for spec in SEED:
        try:
            cid = migrate_one(spec)
            if cid:
                done.append(cid)
        except Exception as e:                                # noqa: BLE001
            print(f"[migrate] {spec['case_id']}: {e!r}")
    return done
