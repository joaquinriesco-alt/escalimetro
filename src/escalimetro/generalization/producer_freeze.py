"""E16.13.1 §16 — la frontera entre CONTRATO y PRODUCTOR, automatizada.

E16.13 se invalidó por mezclar dos variables en un mismo ciclo: cambió el contrato geométrico Y el
productor de geometría, así que ningún efecto observado se podía atribuir a uno u otro. Escribir en
el informe "no toqué el productor" no sirve: hay que poder comprobarlo.

Este módulo extrae del código fuente el TEXTO EXACTO de las funciones y constantes que forman el
productor y lo hashea. Un test compara ese hash contra el mismo cálculo sobre una revisión de
referencia de git. Si alguien toca una línea del productor, el test falla y dice cuál.

No entra en el hash del motor: vive en `generalization`, que `freeze.engine_files` excluye."""
from __future__ import annotations

import ast
import hashlib
import subprocess
from typing import Dict, List, Tuple

#: Lo que ES el productor. Cambiar cualquiera de estos nombres cambia CÓMO se obtiene la geometría, y
#: eso es la otra variable del experimento.
PRODUCER_SPEC: Dict[str, List[str]] = {
    "src/escalimetro/geometry/core_geometry.py": [
        "build_core", "wall_map", "enclosed_cell_anchors", "open_floor",
        "SEARCH_MARGIN_FRAC", "LINK_FRAC", "LINK_MIN_OVERLAP", "ANCHOR_MAX_FRAC",
    ],
    # archivos completos: la evidencia estructural y la pista semántica son entrada del productor
    "src/escalimetro/segmentation/structural.py": ["*"],
    "src/escalimetro/semantic_hint.py": ["*"],
}

#: Lo que SÍ puede cambiar en un ciclo contract-only. Es una lista blanca declarada, no un comentario.
CONTRACT_ALLOWLIST = [
    "src/escalimetro/geometry/core_components.py",     # representación
    "src/escalimetro/geometry/core_fabrication.py",    # diagnóstico experimental
    "src/escalimetro/geometry/core_completeness.py",   # contrato de completitud
    "src/escalimetro/schemas/floorplate.py",           # serialización y procedencia
    # de core_geometry.py sólo lo que NO está en PRODUCER_SPEC (contrato, métricas, salida)
]


def _segments(source: str, names: List[str]) -> Dict[str, str]:
    if names == ["*"]:
        return {"<file>": source}
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    out: Dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names:
            out[node.name] = "".join(lines[node.lineno - 1:node.end_lineno])
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    out[t.id] = "".join(lines[node.lineno - 1:node.end_lineno])
    faltan = [n for n in names if n not in out]
    if faltan:
        raise KeyError(f"no se encontraron en el fuente: {faltan}")
    return out


def producer_segments(read) -> Dict[str, str]:
    """`read(path) -> str`. Devuelve {"archivo::nombre": texto} para todo el productor."""
    out: Dict[str, str] = {}
    for path, names in sorted(PRODUCER_SPEC.items()):
        for name, txt in sorted(_segments(read(path), names).items()):
            out[f"{path}::{name}"] = txt
    return out


def producer_hash(read) -> str:
    h = hashlib.sha256()
    for k, v in sorted(producer_segments(read).items()):
        h.update(k.encode()); h.update(hashlib.sha256(v.encode()).digest())
    return h.hexdigest()


def read_worktree(root: str = "."):
    def _r(path: str) -> str:
        with open(f"{root}/{path}", encoding="utf-8") as fh:
            return fh.read()
    return _r


def read_git(rev: str, root: str = "."):
    def _r(path: str) -> str:
        return subprocess.run(["git", "-C", root, "show", f"{rev}:{path}"],
                              capture_output=True, text=True, check=True).stdout
    return _r


def compare(rev: str, root: str = ".") -> Tuple[bool, List[str], str, str]:
    """(idéntico, nombres que cambiaron, hash_antes, hash_después)."""
    antes = producer_segments(read_git(rev, root))
    ahora = producer_segments(read_worktree(root))
    cambiaron = sorted(set(antes) ^ set(ahora))
    cambiaron += sorted(k for k in set(antes) & set(ahora) if antes[k] != ahora[k])
    return (not cambiaron, sorted(set(cambiaron)),
            producer_hash(read_git(rev, root)), producer_hash(read_worktree(root)))
