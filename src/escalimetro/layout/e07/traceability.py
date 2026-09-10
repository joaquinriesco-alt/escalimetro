"""E26 §6/§7 — IDENTIDAD y CALIDAD de cada layout entregado.

Por qué existe: la crítica arquitectónica de un humano tiene que quedar pegada a UN layout concreto,
no al nombre de un archivo. Un `alternatives/A/layout.json` se sobrescribe en cada corrida; su
`layout_sha256` no. La revisión humana se asocia al hash.

`quality.json` es INSTRUMENTACIÓN, no verdad arquitectónica: son las cifras que acompañan la revisión
para que el revisor no tenga que medirlas a mano. Ninguna de ellas dice si la planta es buena.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Dict, Optional


def sha256_file(path: str) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def traceability(run_prov: Dict, alt: str, layout_path: str) -> Dict:
    """Identidad mínima que exige §6, más lo que hace falta para reproducir la corrida."""
    return {
        "contract_version": "layout_traceability_v1",
        "case_id": run_prov.get("case_id"),
        "brief_id": run_prov.get("brief_id"),
        "strategy": alt,
        "layout_sha256": sha256_file(layout_path),
        "engine_commit": run_prov.get("engine_commit"),
        "brief_sha256": run_prov.get("brief_sha256"),
        "generated_at": run_prov.get("generated_at") or
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # contexto para reproducir, no exigido por §6
        "engine_hash": run_prov.get("engine_hash"),
        "engine_baseline": run_prov.get("engine_baseline"),
        "program_sha256": run_prov.get("program_sha256"),
        "floorplate_sha256": run_prov.get("floorplate_sha256"),
        "modules_sha256": run_prov.get("modules_sha256"),
        "out_name": run_prov.get("out_name"),
        "run_dir": run_prov.get("run_dir"),
        "seed": run_prov.get("seed"),
    }


def _num(t: str) -> float:
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", t or "")
    return float(m.group(1)) if m else 0.0


def quality(run_prov: Dict, alt: str, layout_path: str, metrics: Dict, critique: Dict,
            previous: Optional[Dict] = None) -> Dict:
    """Métricas de acompañamiento. Todas salen de artefactos ya computados; ninguna se inventa."""
    usable = float(metrics.get("usable_area_m2") or 0.0) or None
    unalloc = float(metrics.get("unallocated_area_m2") or 0.0)
    circ = float(metrics.get("circulation_area_m2") or 0.0)
    waste = float(metrics.get("wasted_area_m2") or 0.0)
    sc = critique.get("scores", {}) or {}
    vd = critique.get("verdicts", {}) or {}

    def pct(v):
        return round(100.0 * v / usable, 2) if usable else None

    q = {
        "contract_version": "layout_quality_v1",
        "_contract": "INSTRUMENTACIÓN para acompañar la revisión humana. NO es una evaluación "
                     "arquitectónica ni sustituye una. Ningún umbral aquí decide si la planta sirve.",
        "case_id": run_prov.get("case_id"), "brief_id": run_prov.get("brief_id"), "strategy": alt,
        "layout_sha256": sha256_file(layout_path),
        "engine_commit": run_prov.get("engine_commit"),
        "brief_sha256": run_prov.get("brief_sha256"),
        "generated_at": run_prov.get("generated_at"),
        "usable_area_m2": usable,
        "unallocated_area_m2": round(unalloc, 1), "unallocated_pct": pct(unalloc),
        "residual_spaces_m2": round(waste, 1),
        "residual_spaces_score": sc.get("residual_spaces"),
        "residual_spaces_verdict": vd.get("residual_spaces"),
        "daylight_score": metrics.get("daylight_score"),
        "fragmentation": sc.get("fragmentation"), "fragmentation_verdict": vd.get("fragmentation"),
        "facade_use": sc.get("facade_use"), "facade_use_pct": _num(vd.get("facade_use", "")),
        "architectural_score": critique.get("architectural_score"),
        "circulation_area_m2": round(circ, 1), "circulation_pct": pct(circ),
        "waste_area_m2": round(waste, 1), "waste_pct": pct(waste),
        "net_programmed_area_m2": metrics.get("net_programmed_area_m2"),
        "open_seats": (metrics.get("program_completeness") or {}).get("open_seats"),
        "program_complete": bool((metrics.get("program_completeness") or {}).get("complete")),
    }
    if previous:
        campos = ("unallocated_pct", "residual_spaces_m2", "daylight_score", "fragmentation",
                  "facade_use", "architectural_score", "circulation_pct", "waste_pct")
        delta = {}
        for k in campos:
            a, b = previous.get(k), q.get(k)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                delta[k] = round(b - a, 4)
        q["previous"] = {"layout_sha256": previous.get("layout_sha256"),
                         "engine_commit": previous.get("engine_commit"),
                         "generated_at": previous.get("generated_at"),
                         "source": previous.get("_source_path")}
        q["delta_vs_previous"] = delta
        q["_delta_note"] = ("comparación entre corridas del MISMO case/brief/strategy. Un delta no dice "
                            "que una planta sea mejor: dice que cambió.")
    return q


def load_previous_quality(case_dir: str, brief_id: str, alt: str, exclude_run: str) -> Optional[Dict]:
    """Busca un quality.json anterior del MISMO case/brief/strategy, fuera de esta corrida."""
    import glob
    mejores = []
    for p in glob.glob(os.path.join(case_dir, "layouts", "*", "alternatives", alt, "quality.json")):
        if os.path.dirname(os.path.dirname(os.path.dirname(p))) == exclude_run:
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if d.get("brief_id") == brief_id and d.get("strategy") == alt:
            d["_source_path"] = p.replace(os.sep, "/")
            mejores.append((d.get("generated_at") or "", d))
    if not mejores:
        return None
    return sorted(mejores, key=lambda x: x[0])[-1][1]
