"""E12 — manifiesto de corrida con escritura atómica.

En la primera corrida real de Railway el experimento corrió 139 segundos y después una excepción de
rasterización dejó el informe sin decir qué había terminado bien. Qué alcanzaron a hacer los proveedores
en esos 139 segundos es UNKNOWN / UNVERIFIED: no se preservó evidencia suficiente para determinarlo, ni
para afirmar que ejecutaron ni para afirmar que no. Ésa es exactamente la carencia que este manifiesto
corrige: se escribe en disco después de CADA etapa, así que si el proceso muere se conserva exactamente
hasta dónde llegó.

Escritura atómica (temp + `os.replace`) para que un proceso caído a medias nunca deje un JSON corrupto.
Nunca contiene credenciales: de las keys sólo el estado PRESENT/MISSING."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

NOT_STARTED, RUNNING, OK, FAILED, BLOCKED, SKIPPED = \
    "NOT_STARTED", "RUNNING", "OK", "FAILED", "BLOCKED", "SKIPPED"
STATES = (NOT_STARTED, RUNNING, OK, FAILED, BLOCKED, SKIPPED)
ALTS = ("A", "B", "C")

# Etapas del experimento, en el orden en que ocurren. El nombre es el que aparece en los logs de Railway.
STAGES = ("rule_based", "anthropic", "openai_visual", "aggregator", "presentation_director",
          "presentation_render", "geometry_guard", "report")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def atomic_write_json(path: str, payload: Dict) -> None:
    """temp + rename en el MISMO directorio: `os.replace` es atómico dentro de un filesystem."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".manifest-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@dataclass
class RunManifest:
    """Estado vivo de una corrida. Cada `set_*` persiste inmediatamente."""
    path: str
    run_id: str = field(default_factory=new_run_id)
    case: str = ""
    started_at: str = field(default_factory=utcnow)
    finished_at: Optional[str] = None
    stage: str = NOT_STARTED
    api_keys_status: Dict[str, str] = field(default_factory=dict)     # sólo PRESENT / MISSING
    models: Dict[str, str] = field(default_factory=dict)
    rule_based: Dict[str, str] = field(default_factory=lambda: {a: NOT_STARTED for a in ALTS})
    anthropic: Dict[str, str] = field(default_factory=lambda: {a: NOT_STARTED for a in ALTS})
    openai_visual: Dict[str, str] = field(default_factory=lambda: {a: NOT_STARTED for a in ALTS})
    aggregator_status: str = NOT_STARTED
    presentation_director_status: str = NOT_STARTED
    presentation_render_status: str = NOT_STARTED
    geometry_guard_status: str = NOT_STARTED
    report_status: str = NOT_STARTED
    final_status: str = RUNNING
    errors: List[Dict] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)

    # -----------------------------------------------------------------------------------------------
    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id, "case": self.case,
            "started_at": self.started_at, "finished_at": self.finished_at, "stage": self.stage,
            "api_keys_status": self.api_keys_status, "models": self.models,
            "rule_based": self.rule_based, "anthropic": self.anthropic,
            "openai_visual": self.openai_visual,
            "aggregator_status": self.aggregator_status,
            "presentation_director_status": self.presentation_director_status,
            "presentation_render_status": self.presentation_render_status,
            "geometry_guard_status": self.geometry_guard_status,
            "report_status": self.report_status, "final_status": self.final_status,
            "errors": self.errors, "artifacts": self.artifacts,
        }

    def save(self) -> None:
        atomic_write_json(self.path, self.to_dict())

    # -----------------------------------------------------------------------------------------------
    def set_stage(self, stage: str) -> None:
        self.stage = stage
        self.save()

    # El experimento llama a la fuente `openai_vision`; el manifiesto la nombra `openai_visual`
    # (§11 del brief). Se traduce aquí en vez de renombrar la fuente en todo el pipeline.
    FIELD_OF_SOURCE = {"rule_based": "rule_based", "anthropic": "anthropic",
                       "openai_vision": "openai_visual", "openai_visual": "openai_visual"}

    def set_provider(self, source: str, alt: str, status: str) -> None:
        assert status in STATES, status
        getattr(self, self.FIELD_OF_SOURCE[source])[alt] = status
        self.save()

    def set_status(self, field_name: str, status: str) -> None:
        assert status in STATES, status
        setattr(self, f"{field_name}_status", status)
        self.save()

    def add_error(self, stage: str, error: Dict) -> None:
        """El error se guarda como dict diagnóstico, sin payloads ni credenciales."""
        self.errors.append({"stage": stage, "at": utcnow(), **error})
        self.save()

    def add_artifact(self, name: str, path: str) -> None:
        self.artifacts[name] = path
        self.save()

    def finish(self, final_status: str) -> None:
        assert final_status in STATES, final_status
        self.final_status = final_status
        self.finished_at = utcnow()
        self.stage = "done"
        self.save()

    # -----------------------------------------------------------------------------------------------
    @property
    def providers_ok(self) -> bool:
        """¿Terminó al menos una familia de IA en las tres alternativas?"""
        return any(all(getattr(self, s)[a] == OK for a in ALTS) for s in ("anthropic", "openai_visual"))

    @property
    def api_execution(self) -> str:
        """Estado del GATE DE EJECUCIÓN DE API, independiente del render de la lámina."""
        states = [getattr(self, s)[a] for s in ("anthropic", "openai_visual") for a in ALTS]
        if all(s == OK for s in states):
            return OK
        if any(s == OK for s in states):
            return "PARTIAL"
        return BLOCKED if all(s in (BLOCKED, NOT_STARTED, SKIPPED) for s in states) else FAILED

    @classmethod
    def load(cls, path: str) -> Optional[Dict]:
        if not os.path.exists(path):
            return None
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return None
