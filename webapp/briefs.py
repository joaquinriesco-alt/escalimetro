"""E27 §8 — formulario → BriefV1 válido. Joaquín no escribe JSON nunca más.

Regla de producto que este módulo hace cumplir: el usuario declara QUÉ necesita; DesignPolicyV1
—pesos, zonificación, adyacencias, barrios— no se expone ni se insinúa en la UI. El motor decide
CÓMO. Por eso aquí sólo hay nombres humanos de módulos y cantidades.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Dict, List, Tuple

#: Nombre humano por módulo de la biblioteca OFFICE. El orden es el del formulario.
#: `workstation*` no aparece: se DERIVA de open_workstations y el brief no puede declararlo.
MODULE_LABELS: List[Tuple[str, str]] = [
    ("private_office", "Oficina privada"),
    ("meeting_4", "Sala de 4"),
    ("meeting_8", "Sala de 8"),
    ("boardroom_12", "Directorio (12)"),
    ("phone_booth", "Phone booth"),
    ("reception", "Recepción"),
    ("kitchenette", "Kitchenette"),
    ("dining", "Comedor"),
    ("lounge", "Lounge"),
]
LABEL_OF = dict(MODULE_LABELS)
VALID_MODULES = [m for m, _ in MODULE_LABELS]

#: Punto de partida del formulario: el brief EQUILIBRADO, que es el que el motor resuelve hoy.
#: Es un DEFAULT DE UI, no una política: el usuario lo edita entero.
DEFAULT_ROOMS = {"private_office": 4, "meeting_4": 3, "meeting_8": 1, "boardroom_12": 1,
                 "phone_booth": 3, "reception": 1, "kitchenette": 1, "dining": 1, "lounge": 1}


class BriefFormError(ValueError):
    """El formulario es inconsistente. Se muestra al usuario; no se corrige en silencio."""


def slug(s: str, fallback: str = "BRIEF") -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (s or "").strip().upper()).strip("_")
    return s[:48] or fallback


def build(name: str, headcount, workstations, rooms: Dict[str, int]) -> Dict:
    """Formulario → dict BriefV1. Valida ANTES de tocar el motor: un brief incoherente se
    rechaza con un mensaje en castellano, no con un stacktrace a los tres minutos."""
    try:
        headcount = int(headcount)
        workstations = int(workstations)
    except (TypeError, ValueError):
        raise BriefFormError("Headcount y puestos open deben ser números enteros.")
    if workstations < 1:
        raise BriefFormError("Los puestos open deben ser al menos 1.")
    if headcount < 1:
        raise BriefFormError("El headcount debe ser al menos 1.")
    clean: List[Dict] = []
    for mod, n in (rooms or {}).items():
        if mod not in VALID_MODULES:
            raise BriefFormError(f"Módulo desconocido: {mod}")
        try:
            n = int(n)
        except (TypeError, ValueError):
            raise BriefFormError(f"Cantidad inválida para {LABEL_OF[mod]}.")
        if n < 0:
            raise BriefFormError(f"Cantidad negativa para {LABEL_OF[mod]}.")
        if n:
            clean.append({"module": mod, "count": n})
    return {"contract_version": "brief_v1", "brief_id": slug(name),
            "target_headcount": headcount, "open_workstations": workstations, "rooms": clean}


def validate_against_engine(brief_dict: Dict, modules_path: str) -> None:
    """Valida con el MISMO `BriefV1.validate` del motor, no con una copia. Si el motor considera
    el brief inconsistente (p. ej. headcount < puestos permanentes), el usuario se entera aquí."""
    from escalimetro.brief import BriefV1                      # noqa: PLC0415  (import diferido)
    from escalimetro.layout.model import load_modules          # noqa: PLC0415
    mods, _ = load_modules(modules_path)
    errs = BriefV1.from_dict(brief_dict).validate(mods)
    if errs:
        raise BriefFormError("; ".join(errs))


def write(brief_dict: Dict, path: str) -> str:
    """Escribe el JSON y devuelve su sha256 — el mismo que el motor pincha en traceability.json."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    blob = json.dumps(brief_dict, indent=2, ensure_ascii=False).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(blob)
    return hashlib.sha256(blob).hexdigest()


def summary(brief_dict: Dict) -> str:
    """Una línea legible para las tarjetas: '40 puestos · 4 privados · 5 salas'."""
    rooms = {r["module"]: r["count"] for r in brief_dict.get("rooms", [])}
    salas = sum(rooms.get(m, 0) for m in ("meeting_4", "meeting_8", "boardroom_12"))
    bits = [f'{brief_dict["open_workstations"]} puestos']
    if rooms.get("private_office"):
        bits.append(f'{rooms["private_office"]} privados')
    if salas:
        bits.append(f"{salas} salas")
    return " · ".join(bits)


# ===================================================================================================
# E27.2 §7 — errores POR CAMPO, para poder marcar el input que está mal
# ===================================================================================================
#: Campos obligatorios del BriefV1 (los que `BriefV1.from_dict` exige y `validate` juzga).
#: `rooms` no es obligatorio como conjunto: un brief de sólo open space es legítimo.
REQUIRED_BRIEF_FIELDS = ("brief_name", "headcount", "workstations")


def field_errors(name, headcount, workstations, rooms: Dict[str, int],
                 modules_path: str) -> Dict[str, str]:
    """Devuelve {campo: mensaje}. Vacío = el brief es válido para el motor.

    La última palabra la tiene `BriefV1.validate` del motor: acá sólo se traduce a qué input
    pertenece cada queja para poder pintarlo en rojo."""
    errs: Dict[str, str] = {}
    if not (name or "").strip():
        errs["brief_name"] = "Ponle un nombre al brief."
    for campo, valor, etiqueta in (("headcount", headcount, "personas"),
                                   ("workstations", workstations, "puestos open")):
        try:
            if int(valor) < 1:
                errs[campo] = f"El número de {etiqueta} debe ser al menos 1."
        except (TypeError, ValueError):
            errs[campo] = f"Indica el número de {etiqueta}."
    for mod, n in (rooms or {}).items():
        try:
            if int(n or 0) < 0:
                errs[f"room_{mod}"] = "No puede ser negativo."
        except (TypeError, ValueError):
            errs[f"room_{mod}"] = "Tiene que ser un número."
    if errs:
        return errs
    try:
        b = build(name, headcount, workstations, rooms)
        validate_against_engine(b, modules_path)
    except BriefFormError as e:
        msg = str(e)
        # `target_headcount < puestos permanentes` es la única incoherencia cruzada que el motor
        # reporta hoy; pertenece al campo de personas, que es el que hay que subir.
        errs["headcount" if "target_headcount" in msg else "brief_name"] = msg
    return errs
