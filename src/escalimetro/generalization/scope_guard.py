"""E16.14 §6 — la frontera INVERTIDA: ahora lo que se protege es el CONTRATO.

E16.13.1 congeló el productor con un hash del texto de sus funciones, para poder demostrar que el
único cambio era el contrato. E16.14 mueve la otra variable, así que la protección se da vuelta: lo
que no puede cambiar es el juez —contrato, representación, completitud, procedencia— y la evidencia
de la que el productor se alimenta —tinta estructural, mapa de muros, celdas cerradas, pista
semántica—, más todo lo que está aguas abajo.

    El productor propone. El contrato juzga. El productor no puede editar el examen.

Un test compara estos hashes contra la revisión base y falla nombrando la función que cambió."""
from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple

from .producer_freeze import _segments, read_git, read_worktree

#: EL JUEZ. Contrato de aceptación, medición, representación, completitud y procedencia.
CONTRACT_SPEC: Dict[str, List[str]] = {
    "src/escalimetro/geometry/core_geometry.py": [
        "CORE_ACCEPTANCE", "accept_core", "evaluate_candidate", "component_metrics",
        "_geometry_metrics", "_scope_mask", "cores_from_candidate",
    ],
    "src/escalimetro/geometry/core_components.py": ["*"],
    "src/escalimetro/geometry/core_completeness.py": ["*"],
    "src/escalimetro/schemas/floorplate.py": ["*"],
}

#: LA EVIDENCIA. De aquí se alimenta el productor, y en este ciclo es una entrada fija: si cambia,
#: el experimento vuelve a tener dos variables y la conclusión sobre wall evidence (§23) no vale.
WALL_EVIDENCE_SPEC: Dict[str, List[str]] = {
    "src/escalimetro/segmentation/structural.py": ["*"],
    "src/escalimetro/geometry/core_geometry.py": [
        "wall_map", "enclosed_cell_anchors", "open_floor",
        "SEARCH_MARGIN_FRAC", "LINK_MIN_OVERLAP", "ANCHOR_MAX_FRAC",
    ],
}

#: LA PISTA. Contrato y proveedor de la pista semántica.
HINT_SPEC: Dict[str, List[str]] = {"src/escalimetro/semantic_hint.py": ["*"]}

#: AGUAS ABAJO. Nada de esto puede moverse para que el núcleo "encaje".
DOWNSTREAM_SPEC: Dict[str, List[str]] = {
    "src/escalimetro/layout/shell_adapter.py": ["*"],
    "src/escalimetro/geometry/scale.py": ["*"],
    "src/escalimetro/area_semantics.py": ["*"],
}

#: LO ÚNICO QUE PUEDE CAMBIAR EN E16.14.
PRODUCER_SURFACE = [
    "src/escalimetro/geometry/core_producer.py",          # productor nuevo
    "src/escalimetro/geometry/core_geometry.py::build_core",
]

SPECS = {"CONTRACT": CONTRACT_SPEC, "WALL_EVIDENCE": WALL_EVIDENCE_SPEC,
         "SEMANTIC_HINT": HINT_SPEC, "DOWNSTREAM": DOWNSTREAM_SPEC}


def _hash(spec: Dict[str, List[str]], read) -> str:
    h = hashlib.sha256()
    for path, names in sorted(spec.items()):
        for name, txt in sorted(_segments(read(path), names).items()):
            h.update(f"{path}::{name}".encode()); h.update(hashlib.sha256(txt.encode()).digest())
    return h.hexdigest()


def hashes(read) -> Dict[str, str]:
    return {k: _hash(v, read) for k, v in SPECS.items()}


def compare(rev: str, root: str = ".") -> Tuple[bool, Dict[str, Tuple[str, str]], List[str]]:
    """(todo igual, {ámbito: (antes, después)}, segmentos que cambiaron)."""
    antes_r, ahora_r = read_git(rev, root), read_worktree(root)
    out, cambios = {}, []
    for k, spec in SPECS.items():
        a, b = _hash(spec, antes_r), _hash(spec, ahora_r)
        out[k] = (a, b)
        if a != b:
            for path, names in sorted(spec.items()):
                sa, sb = _segments(antes_r(path), names), _segments(ahora_r(path), names)
                cambios += [f"{k}:{path}::{n}" for n in set(sa) | set(sb) if sa.get(n) != sb.get(n)]
    return (not cambios), out, sorted(cambios)
