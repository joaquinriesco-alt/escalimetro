"""E30 §17 — QUÉ PUEDE HACER ESTA CUENTA. Modelo de derechos, no de cobro.

Dos productos que el encargo prohíbe mezclar (§4):

    ONE_OFF   una propiedad preparada y entregada. Es un ENTREGABLE.
              Un pack base, UN layout representativo, una imagen ambientada.
    PRO       la propiedad se sigue trabajando. Es un FLUJO.
              Muchos fit requests, A/B/C, regeneración, marca del prospecto.

Tres cosas que este módulo NO hace, cada una porque el encargo lo dice:

* **no cobra** (§13: "Do not implement billing yet"). Acá sólo se responde "¿puede?"; quién paga y
  cómo es una capa que todavía no existe y que se enchufa en `mode()` sin tocar a los que preguntan;
* **no mira emails** (§17: "Do not tie product mode to hardcoded user emails");
* **no decora**. Una capacidad negada corta la operación en el dominio, no sólo esconde un botón.
  `require()` lanza y quien lo llama devuelve 403. Si sólo ocultáramos el botón, el límite del
  producto sería una sugerencia.

El modo por defecto es ONE_OFF a propósito: si alguien olvida configurarlo, el sistema entrega de
menos, no de más.
"""
from __future__ import annotations

from typing import Dict, List

from . import settings

PRODUCT_MODES = ("ONE_OFF", "PRO")
DEFAULT_MODE = "ONE_OFF"
MODE_KEY = "product_mode"

MODE_LABEL = {
    "ONE_OFF": "Pack de publicación",
    "PRO": "Escalímetro Pro",
}
#: Cómo se le cuenta cada producto a quien lo compra (§21: lenguaje de cliente).
MODE_PITCH = {
    "ONE_OFF": "Prepará esta propiedad para salir al mercado.",
    "PRO": "Convertí un plano en propuestas para cada prospecto.",
}

# --------------------------------------------------------------------------------------------
# capacidades
# --------------------------------------------------------------------------------------------
MULTIPLE_PROPERTIES = "MULTIPLE_PROPERTIES"
PROSPECT_FIT_REQUESTS = "PROSPECT_FIT_REQUESTS"
ABC_ALTERNATIVES = "ABC_ALTERNATIVES"
REGENERATE = "REGENERATE"
PROSPECT_BRANDING = "PROSPECT_BRANDING"
MULTIPLE_STAGING = "MULTIPLE_STAGING"
ADVANCED_BRIEF = "ADVANCED_BRIEF"

CAPABILITIES = (MULTIPLE_PROPERTIES, PROSPECT_FIT_REQUESTS, ABC_ALTERNATIVES, REGENERATE,
                PROSPECT_BRANDING, MULTIPLE_STAGING, ADVANCED_BRIEF)

#: La matriz entera, en un solo lugar. Leerla es leer la diferencia comercial del §4.
GRANTS: Dict[str, Dict[str, bool]] = {
    "ONE_OFF": {
        MULTIPLE_PROPERTIES: False,
        PROSPECT_FIT_REQUESTS: False,
        ABC_ALTERNATIVES: False,
        REGENERATE: False,
        PROSPECT_BRANDING: False,
        MULTIPLE_STAGING: False,
        ADVANCED_BRIEF: False,
    },
    "PRO": {c: True for c in CAPABILITIES},
}

#: Cuántas de cada cosa. `None` = sin tope.
LIMITS: Dict[str, Dict[str, int]] = {
    "ONE_OFF": {"properties": 1, "fit_requests_per_property": 1, "layouts_per_pack": 1,
                "staged_images_per_property": 1,
                # E31 §20 — reintentos INTERNOS para cumplir esa única imagen. Son mecánica de
                # producción, no créditos del cliente: el cliente no ve un botón "probar de nuevo".
                "staging_attempts_per_hero": 3},
    "PRO": {"properties": None, "fit_requests_per_property": None, "layouts_per_pack": 3,
            "staged_images_per_property": None, "staging_attempts_per_hero": None},
}

#: Por qué se niega cada cosa, en castellano y sin culpar al usuario.
DENIAL = {
    MULTIPLE_PROPERTIES: "El pack de publicación cubre una propiedad. Para trabajar varias a la "
                         "vez hace falta Escalímetro Pro.",
    PROSPECT_FIT_REQUESTS: "Las propuestas por prospecto son parte de Escalímetro Pro.",
    ABC_ALTERNATIVES: "El pack de publicación incluye una alternativa representativa. Las tres "
                      "alternativas son parte de Escalímetro Pro.",
    REGENERATE: "Volver a generar alternativas es parte de Escalímetro Pro.",
    PROSPECT_BRANDING: "La marca del prospecto se aplica en las propuestas de Escalímetro Pro.",
    MULTIPLE_STAGING: "El pack de publicación incluye una imagen ambientada de la foto principal. "
                      "Ambientar más fotos, o una por prospecto, es parte de Escalímetro Pro.",
    ADVANCED_BRIEF: "El programa detallado es parte de Escalímetro Pro. El pack de publicación "
                    "usa un programa equilibrado a partir del número de personas.",
}


class EntitlementError(PermissionError):
    """La cuenta no tiene derecho a esto. Es un límite de PRODUCTO, no un error técnico ni un
    fallo del usuario: el mensaje dice qué producto lo incluye."""

    def __init__(self, capability: str, msg: str = ""):
        self.capability = capability
        super().__init__(msg or DENIAL.get(capability, "No disponible en este producto."))


def mode() -> str:
    """El modo vigente. Punto único: el día que haya facturación, se cambia esta función."""
    m = settings.get(MODE_KEY, DEFAULT_MODE)
    return m if m in PRODUCT_MODES else DEFAULT_MODE


def set_mode(m: str) -> None:
    if m not in PRODUCT_MODES:
        raise ValueError(f"modo de producto desconocido: {m}")
    settings.put(MODE_KEY, m)


def allows(capability: str) -> bool:
    if capability not in CAPABILITIES:
        raise KeyError(f"capacidad desconocida: {capability}")
    return GRANTS[mode()][capability]


def require(capability: str) -> None:
    """La forma de usar esto desde el dominio. Lanza; no devuelve un booleano que se pueda ignorar
    por accidente en una plantilla."""
    if not allows(capability):
        raise EntitlementError(capability)


def limit(name: str):
    return LIMITS[mode()].get(name)


def max_layouts_in_pack() -> int:
    """Cuántas alternativas entran en un pack. ONE_OFF: 1 (§8 «ONE representative layout»)."""
    return LIMITS[mode()]["layouts_per_pack"]


def granted() -> List[str]:
    return [c for c in CAPABILITIES if GRANTS[mode()][c]]


def summary() -> Dict:
    m = mode()
    return {"mode": m, "label": MODE_LABEL[m], "pitch": MODE_PITCH[m],
            "capabilities": {c: GRANTS[m][c] for c in CAPABILITIES},
            "limits": dict(LIMITS[m])}
