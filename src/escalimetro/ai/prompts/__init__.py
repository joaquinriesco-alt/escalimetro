"""E08 — prompts de runtime, versionados y fuera del código.

Un prompt es un artefacto con versión, no una cadena incrustada en una función. Cada salida de IA
registra `prompt_version`, así que una revisión guardada hace seis meses se puede reproducir sabiendo
exactamente qué se preguntó."""
from __future__ import annotations

import json
import os
from typing import Dict, List

DIR = os.path.dirname(__file__)

REGISTRY = {
    "spatial_review": "anthropic_spatial_review_v1",
    "visual_review": "openai_visual_critic_v1",
    "presentation": "openai_presentation_v1",
}


def versions() -> Dict[str, str]:
    return dict(REGISTRY)


def available() -> List[str]:
    return sorted(f[:-4] for f in os.listdir(DIR) if f.endswith(".txt"))


def load(version: str) -> str:
    path = os.path.join(DIR, f"{version}.txt")
    if not os.path.exists(path):
        raise FileNotFoundError(f"prompt no encontrado: {version}")
    return open(path, encoding="utf-8").read()


def render(version: str, payload: Dict, model: str, alternative_id: str = "") -> str:
    """Sustitución explícita. El payload va serializado como JSON: el modelo recibe datos, no prosa."""
    body = load(version)
    blob = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    return (body.replace("<MODEL>", model).replace("<ALT>", alternative_id or "")
                .replace("<PAYLOAD>", blob))
