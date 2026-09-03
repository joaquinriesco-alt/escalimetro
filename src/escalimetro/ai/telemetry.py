"""E08 — telemetría de uso, costo y latencia.

Registra por PROYECTO, por ALTERNATIVA y por PROVEEDOR. Nunca escribe credenciales: los registros pasan
por `scrub` antes de tocar disco, que es la última barrera además de que la clave nunca entra al objeto."""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

# Formas de clave conocidas. La defensa real es no ponerlas nunca en el objeto; esto es el cinturón.
SECRET_PATTERNS = [re.compile(p) for p in (r"sk-[A-Za-z0-9_\-]{16,}", r"sk-ant-[A-Za-z0-9_\-]{16,}",
                                           r"Bearer\s+[A-Za-z0-9._\-]{16,}")]
SECRET_KEYS = {"api_key", "apikey", "authorization", "openai_api_key", "anthropic_api_key", "_api_key"}


def scrub(obj):
    """Elimina cualquier cosa que parezca una credencial, por clave o por forma."""
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if str(k).lower() in SECRET_KEYS else scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        out = obj
        for p in SECRET_PATTERNS:
            out = p.sub("[REDACTED]", out)
        return out
    return obj


@dataclass
class UsageLedger:
    project: str
    records: List[Dict] = field(default_factory=list)

    def add(self, rec: Dict) -> None:
        self.records.append(scrub(dict(rec)))

    def _group(self, key: str) -> Dict[str, Dict]:
        out: Dict[str, Dict] = defaultdict(lambda: {"calls": 0, "success": 0, "input_tokens": 0,
                                                    "output_tokens": 0, "latency_ms": 0.0,
                                                    "estimated_cost": 0.0, "cost_unknown": 0})
        for r in self.records:
            k = str(r.get(key))
            g = out[k]
            g["calls"] += 1
            g["success"] += int(bool(r.get("success")))
            g["input_tokens"] += int(r.get("input_tokens") or 0)
            g["output_tokens"] += int(r.get("output_tokens") or 0)
            g["latency_ms"] += float(r.get("latency_ms") or 0.0)
            if r.get("cost_status") == "unknown" or r.get("estimated_cost") is None:
                g["cost_unknown"] += 1
            else:
                g["estimated_cost"] += float(r.get("estimated_cost") or 0.0)
        for g in out.values():
            g["latency_ms"] = round(g["latency_ms"], 1)
            g["estimated_cost"] = round(g["estimated_cost"], 6)
        return dict(out)

    def summary(self) -> Dict:
        known = [r for r in self.records if r.get("cost_status") in ("estimated", "reported")]
        total = round(sum(float(r.get("estimated_cost") or 0.0) for r in known), 6)
        statuses = {r.get("cost_status") for r in known}
        status = "unknown" if not known else ("reported" if statuses == {"reported"} else "estimated")
        return {
            "project": self.project,
            "calls": len(self.records),
            "successful_calls": sum(1 for r in self.records if r.get("success")),
            "total_cost": {"value_usd": total, "status": status,
                           "records_with_unknown_cost": len(self.records) - len(known),
                           "note": "reported = costo real (el proveedor determinista no cuesta nada); estimated = calculado con la tabla de precios; unknown = sin precio para ese modelo."},
            "by_provider": self._group("provider"),
            "by_purpose": self._group("purpose"),
            "by_alternative": self._group("alternative_id"),
            "records": self.records,
        }

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(scrub(self.summary()), open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def contains_secret(text: str) -> bool:
    return any(p.search(text or "") for p in SECRET_PATTERNS)
