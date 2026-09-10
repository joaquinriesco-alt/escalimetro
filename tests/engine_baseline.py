"""Baseline VIGENTE del motor — una sola fuente para todos los ciclos.

Por qué existe (E24): varios tests de ciclos anteriores pinchaban el hash del motor a un literal.
Ese literal expresaba dos cosas distintas mezcladas:

  1. "el ciclo N no tocó el motor"        — una afirmación HISTÓRICA, verificable en la cadena;
  2. "el motor de hoy es el del ciclo N"  — que deja de ser cierta en cuanto un ciclo posterior
                                            cambia el motor A PROPÓSITO, como hace E24 (§6).

Al mezclarlas, cualquier cambio legítimo hacía caer siete tests de ciclos que no tenían nada que ver.
Aquí se separan: el baseline vigente se lee del disco (mismo mecanismo que ya usaba E16.4) y el hash
de cada ciclo se comprueba contra la CADENA, que es donde está su registro histórico.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Dict, List

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _todos() -> List[Dict]:
    out = []
    for p in glob.glob(os.path.join(RAIZ, "cases", "generalization", "*", "GENERIC_ENGINE_BASELINE.json")):
        d = json.load(open(p, encoding="utf-8"))
        d["_path"] = p
        out.append(d)
    return out


def vigente() -> Dict:
    """El baseline con la cadena más larga. Determinista y sin depender de mtime."""
    b = _todos()
    assert b, "no hay ningún GENERIC_ENGINE_BASELINE.json declarado"
    return max(b, key=lambda d: (len(d.get("chain", [])), d.get("created_by", "")))


def engine_hash() -> str:
    return vigente()["engine_hash"]


def cadena() -> Dict[str, str]:
    """{experimento: engine_hash} de toda la cadena declarada, incluido el vigente."""
    v = vigente()
    c = {e["experiment"]: e["engine_hash"] for e in v.get("chain", [])}
    c[v["created_by"]] = v["engine_hash"]
    return c


def esta_en_la_cadena(h: str) -> bool:
    return h in set(cadena().values())
