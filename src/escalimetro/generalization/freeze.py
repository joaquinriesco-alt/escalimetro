"""E14 — congelamiento del motor.

Regla del experimento: el motor entra congelado y sale congelado. Este módulo hashea el conjunto
exacto de archivos que constituyen el motor determinista más su configuración, para poder demostrar
después —no afirmar— que ningún parámetro cambió entre antes y después del segundo shell.

Qué se considera motor congelado: todo el código bajo `src/escalimetro/` que existía al momento del
freeze, EXCEPTO este propio paquete `generalization`, más las plantillas de programa y los catálogos
de módulos. La capa de IA se incluye aunque E14 no la use: si cambiara, el experimento tampoco sería
comparable.

Lo que NO se hashea: nada que contenga credenciales. Aquí sólo hay código y JSON de configuración."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Dict, List

EXCLUDE_DIRS = ("__pycache__", os.path.join("escalimetro", "generalization"))
CONFIG_FILES = ["program_templates/modules_office.json",
                "program_templates/office_balanced_48.json",
                "program_templates/office_balanced_48_diag36.json"]


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def engine_files(root: str = ".") -> List[str]:
    out: List[str] = []
    src = os.path.join(root, "src", "escalimetro")
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        if os.path.join("escalimetro", "generalization") in dirpath:
            continue
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), root))
    for c in CONFIG_FILES:
        if os.path.exists(os.path.join(root, c)):
            out.append(c)
    return sorted(out)


def _group(rel: str) -> str:
    p = rel.replace("\\", "/")
    if p.startswith("program_templates/"):
        return "catalog"
    for key, name in (("/layout/solver", "solver"), ("/layout/e07", "strategies"),
                      ("/layout/", "layout"), ("/geometry/", "geometry"),
                      ("/semantics/", "semantics"), ("/segmentation/", "segmentation"),
                      ("/vision/", "vision"), ("/renderer/", "renderer"),
                      ("/schemas/", "schemas"), ("/ai/", "ai"), ("/overrides/", "overrides")):
        if key in p:
            return name
    return "core"


def manifest(root: str = ".", commit: str = "", note: str = "") -> Dict:
    files = engine_files(root)
    per_file = {f: _sha(os.path.join(root, f)) for f in files}
    groups: Dict[str, List[str]] = {}
    for f in files:
        groups.setdefault(_group(f), []).append(f)
    group_hash = {}
    for g, fs in sorted(groups.items()):
        h = hashlib.sha256()
        for f in sorted(fs):
            h.update(f.encode()); h.update(per_file[f].encode())
        group_hash[g] = h.hexdigest()
    total = hashlib.sha256()
    for f in files:
        total.update(f.encode()); total.update(per_file[f].encode())
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "commit": commit, "note": note, "n_files": len(files),
            "engine_hash": total.hexdigest(), "group_hashes": group_hash,
            "file_hashes": per_file}


def compare(before: Dict, after: Dict) -> Dict:
    """Diferencia estricta. `identical` es el único resultado aceptable para que E14 sea válido."""
    b, a = before["file_hashes"], after["file_hashes"]
    changed = sorted(f for f in set(b) & set(a) if b[f] != a[f])
    removed = sorted(set(b) - set(a))
    added = sorted(set(a) - set(b))
    return {"identical": not (changed or removed or added),
            "engine_hash_before": before["engine_hash"], "engine_hash_after": after["engine_hash"],
            "changed": changed, "removed": removed, "added_to_engine_set": added,
            "groups_changed": sorted(g for g in before["group_hashes"]
                                     if after["group_hashes"].get(g) != before["group_hashes"][g])}


def write(path: str, data: Dict) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return path
