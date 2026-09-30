"""E37 — FIXTURE: una salida grabada a mano, para ver el flujo sin gastar. NO reconstruye nada.

Existe para una sola cosa: poder recorrer y fotografiar el flujo interno —resultado, calificación,
corrección, comparación, reveal— con datos de prueba, sin credenciales y sin pagar. Por eso:

* **sólo aparece si `ESCALIMETRO_RECON_FIXTURE=1`** en el entorno del servidor. En cualquier otro
  caso no está en el catálogo, ni se puede elegir, ni se puede ejecutar;
* **se llama FIXTURE y lo dice en todas partes.** No es «Motor A»: E37 prohíbe llenar la pantalla
  con motores ficticios que parezcan reales. La UI muestra su aviso junto a cada corrida;
* **no mira las fotos.** Devuelve siempre la misma planta de un departamento 2D/2B, citando como
  evidencia las primeras fotos que recibió sólo para que el contrato sea válido;
* **la corrección es una regla de texto, no IA.** Si la instrucción nombra un recinto y dice «más
  grande» o «más chico», lo escala un 15 % sobre su centro. Si no nombra ninguno, pide aclaración:
  así se ejercita `CLARIFICATION_REQUIRED` de verdad.
"""
from __future__ import annotations

import copy
import hashlib
import os
import unicodedata
from typing import Any, Dict, List

from .. import contract
from .base import (AVAILABLE, CORRECTION, DISABLED, UNAVAILABLE, Availability, EngineAdapter,
                   EngineRequest, EngineResult)

ENGINE_ID = "fixture_replay"
FLAG_ENV = "ESCALIMETRO_RECON_FIXTURE"
PROMPT_VERSION = "fixture_replay_v1"
SCALE = 0.15


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return s.lower()


def _room(rid: str, label: str, rtype: str, poly, area, conf, fotos, unc=None) -> Dict[str, Any]:
    return {"id": rid, "label": label, "room_type": rtype, "level": 1, "polygon": poly,
            "area_m2": area, "confidence": conf,
            "evidence": [{"asset_ids": fotos, "observation": "salida fija de demostración"}],
            "uncertainty": unc}


def canned_plan(asset_ids: List[str]) -> Dict[str, Any]:
    """La planta fija. Rectángulos simples en el marco normalizado; dos recintos a propósito con
    confianza baja o sin ubicar, para que el render muestre cómo se ve la incertidumbre."""
    f = asset_ids[:2] or []
    rooms = [
        _room("r1", "Living-comedor", "LIVING_DINING", [[0.0, 0.0], [0.55, 0.0], [0.55, 0.5], [0.0, 0.5]], 28, 0.8, f),
        _room("r2", "Cocina", "KITCHEN", [[0.55, 0.0], [0.8, 0.0], [0.8, 0.3], [0.55, 0.3]], 8, 0.7, f),
        _room("r3", "Logia", "LAUNDRY", [[0.8, 0.0], [1.0, 0.0], [1.0, 0.3], [0.8, 0.3]], 3, 0.45, f,
              "no se ve en ninguna foto; se supone junto a la cocina"),
        _room("r4", "Pasillo", "HALLWAY", [[0.55, 0.3], [1.0, 0.3], [1.0, 0.45], [0.55, 0.45]], 5, 0.6, f),
        _room("r5", "Dormitorio principal", "BEDROOM", [[0.0, 0.5], [0.45, 0.5], [0.45, 1.0], [0.0, 1.0]], 14, 0.75, f),
        _room("r6", "Dormitorio 2", "BEDROOM", [[0.65, 0.45], [1.0, 0.45], [1.0, 1.0], [0.65, 1.0]], 10, 0.55, f),
        _room("r7", "Baño principal", "BATHROOM", [[0.45, 0.5], [0.65, 0.5], [0.65, 0.75], [0.45, 0.75]], 4.5, 0.6, f),
        _room("r8", "Baño 2", "BATHROOM", [[0.45, 0.75], [0.65, 0.75], [0.65, 1.0], [0.45, 1.0]], 4, 0.4, f,
              "la franja de baños es la parte menos clara"),
        _room("r9", "Walk-in closet", "WALK_IN_CLOSET", None, None, 0.3, f,
              "aparece en una foto pero no se sabe a qué dormitorio da"),
    ]
    conexiones = [
        ("c1", "r1", "r2", "OPENING", 0.7), ("c2", "r2", "r3", "DOOR", 0.5),
        ("c3", "r1", "r4", "OPENING", 0.6), ("c4", "r4", "r6", "DOOR", 0.55),
        ("c5", "r4", "r7", "DOOR", 0.5), ("c6", "r5", "r7", "ADJACENT", 0.4),
        ("c7", "r5", "r1", "DOOR", 0.6), ("c8", "r6", "r8", "UNKNOWN", 0.3),
    ]
    return {
        "contract": contract.CONTRACT_ID, "outcome": contract.RECONSTRUCTED,
        "summary": "FIXTURE: planta fija de un departamento 2D/2B. No se miraron las fotos.",
        "levels": 1,
        "footprint": {"width_m": 11.0, "depth_m": 8.0,
                      "basis": "fija de demostración; no sale de ninguna evidencia"},
        "rooms": rooms,
        "connections": [{"id": i, "from_room": a, "to_room": b, "kind": k, "confidence": c,
                         "evidence": [{"asset_ids": f, "observation": "salida fija"}]}
                        for i, a, b, k, c in conexiones],
        "relations": [{"room": "r9", "relation": "NEXT_TO", "other_room": "r5",
                       "confidence": 0.3,
                       "evidence": [{"asset_ids": f, "observation": "salida fija"}]}],
        "uncertainties": [
            {"subject": "r8", "issue": "la franja de baños no se distingue", "impact": "HIGH"},
            {"subject": "global", "issue": "salida fija: no hay reconstrucción real",
             "impact": "HIGH"}],
        "missing_evidence": ["una foto que muestre el acceso a los baños"],
        "clarification": None, "correction": None,
    }


def _scale(poly: List[List[float]], factor: float) -> List[List[float]]:
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    return [[min(1.0, max(0.0, round(cx + (x - cx) * factor, 4))),
             min(1.0, max(0.0, round(cy + (y - cy) * factor, 4)))] for x, y in poly]


def correct(previous: Dict[str, Any], instruction: str) -> Dict[str, Any]:
    """La regla de texto. No entiende nada: busca el nombre de un recinto y dos verbos."""
    plan = copy.deepcopy(previous)
    txt = _plain(instruction)
    candidatos = [r for r in plan["rooms"] if r.get("polygon")
                  and _plain(r["label"]) in txt]
    # el nombre más largo gana: «dormitorio principal» antes que «dormitorio»
    candidatos.sort(key=lambda r: -len(r["label"]))
    grande = "mas grande" in txt or "mayor" in txt
    chico = "mas chico" in txt or "mas pequeno" in txt or "menor" in txt
    if not candidatos or grande == chico:
        plan["outcome"] = contract.CLARIFICATION_REQUIRED
        plan["clarification"] = {
            "question": "¿Qué recinto hay que cambiar, y hacerlo más grande o más chico?",
            "options": [r["label"] for r in plan["rooms"] if r.get("polygon")][:6]}
        plan["correction"] = None
        plan["summary"] = "FIXTURE: la instrucción no nombra un recinto o no dice hacia dónde."
        return plan
    r = candidatos[0]
    factor = 1.0 + SCALE if grande else 1.0 - SCALE
    r["polygon"] = _scale(r["polygon"], factor)
    if r.get("area_m2"):
        r["area_m2"] = round(r["area_m2"] * factor * factor, 1)
    plan["outcome"] = contract.RECONSTRUCTED
    plan["clarification"] = None
    plan["correction"] = {
        "understood_as": f"{r['label']}: {'más grande' if grande else 'más chico'}",
        "changes": [f"{r['label']} escalado un {int(SCALE * 100)} % sobre su centro "
                    "(regla de texto del fixture; puede superponerse con vecinos)"]}
    plan["summary"] = "FIXTURE: la planta fija, con la corrección aplicada por regla de texto."
    return plan


class FixtureReplay(EngineAdapter):
    engine_id = ENGINE_ID
    name = "FIXTURE — salida grabada"
    version = "1"
    provider = "ninguno"
    pipeline = "planta fija escrita a mano; corrección por regla de texto"
    capabilities = ("photos", "correction", "clarification")
    paid = False
    notice = ("No es una reconstrucción: devuelve siempre la misma planta y no mira las fotos. "
              "Sirve para recorrer el flujo sin gastar.")

    def enabled(self) -> bool:
        return os.environ.get(FLAG_ENV, "") == "1"

    def model(self) -> str:
        return "fixture"

    def availability(self) -> Availability:
        if not self.enabled():
            return Availability(UNAVAILABLE, DISABLED, f"se habilita con {FLAG_ENV}=1")
        return Availability(AVAILABLE)

    def reconstruct(self, req: EngineRequest) -> EngineResult:
        ids = [im.asset_id for im in req.images]
        if req.mode == CORRECTION:
            salida = correct(req.previous or canned_plan(ids), req.instruction or "")
        elif not ids:
            salida = canned_plan([])
            salida.update({"outcome": contract.INSUFFICIENT_EVIDENCE, "rooms": [],
                           "connections": [], "relations": [], "uncertainties": [],
                           "summary": "FIXTURE: sin fotos no hay nada que simular.",
                           "missing_evidence": ["al menos una foto"]})
        else:
            salida = canned_plan(ids)
        # el «prompt» del fixture es su versión más la instrucción: no hay otro texto que mandar
        sha = hashlib.sha256((PROMPT_VERSION + "\n" + (req.instruction or ""))
                             .encode("utf-8")).hexdigest()
        return EngineResult(output=salida, model="fixture", latency_ms=0,
                            prompt_version=PROMPT_VERSION, prompt_sha256=sha,
                            request_summary={"images_received": len(ids), "mode": req.mode,
                                             "instruction": req.instruction,
                                             "ignored_inputs": list(req.ignored_inputs)},
                            raw={}, usage={}, cost_usd=0.0, cost_basis="measured")
