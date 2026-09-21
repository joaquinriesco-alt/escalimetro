"""E32.2 §1 — QUÉ SE COMPRÓ Y QUÉ HABILITA. Modelo de derechos, no de cobro.

=================================================================================================
El error que este módulo corrige
=================================================================================================
E30 modeló ONE_OFF como una propiedad de la CUENTA, con un tope de "1 propiedad". Eso decía, sin
querer, que un corredor que quiere preparar una segunda oficina tiene que pasarse a Pro. No es el
negocio:

    PACK ONE_OFF   una COMPRA cubre UNA propiedad. La misma cuenta puede comprar tres Packs para
                   tres propiedades sin ser Pro nunca.
    PRO            un derecho RECURRENTE sobre el trabajo: muchos prospectos, A/B/C, regeneración,
                   marca del prospecto, ambientación repetida.

Pro no existe para permitirte tener una segunda propiedad. Existe para que puedas seguir trabajando
las que ya tenés. Vender Pro como "la forma de tener dos propiedades" era vender mal y cobrar mal.

=================================================================================================
Tres cosas que este módulo separa y no vuelve a mezclar
=================================================================================================
    OPERADOR    qué puede hacer Joaquín en el LAB. No tiene topes: es un laboratorio.
    COMPRA      qué habilita una concesión (`grants.py`). Una concesión, una propiedad.
    PROPIEDAD   qué producto cubre a ESTA propiedad, y por lo tanto qué se puede hacer con ella.

Por eso las capacidades se preguntan **por propiedad**: `allows(property_id, cap)`. Preguntar por
la cuenta era justamente lo que producía el efecto global equivocado — cambiar una propiedad a Pro
no puede convertir a las otras en Pro, y hay test de eso.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .. import store
from . import settings

#: Lo que cubre una propiedad. Antes se llamaba "modo de la cuenta"; era el error.
PRODUCTS = ("ONE_OFF", "PRO")
DEFAULT_PRODUCT = "ONE_OFF"
#: Producto que recibe una propiedad nueva creada desde el LAB. Es un DEFAULT DE PRUEBA, no el
#: derecho de nadie: no decide lo que puede hacer ninguna propiedad ya creada.
DEFAULT_KEY = "default_product"
#: Compatibilidad: E30/E31 llamaban a esto `product_mode`.
LEGACY_MODE_KEY = "product_mode"

PRODUCT_LABEL = {"ONE_OFF": "Pack de publicación", "PRO": "Escalímetro Pro"}
PRODUCT_PITCH = {
    "ONE_OFF": "Un Pack prepara una propiedad para salir al mercado.",
    "PRO": "Trabajá cada propiedad con tantos prospectos como aparezcan.",
}
# Nombres que el resto del código y las plantillas ya usaban.
PRODUCT_MODES = PRODUCTS
MODE_LABEL = PRODUCT_LABEL
MODE_PITCH = PRODUCT_PITCH

# --------------------------------------------------------------------------------------------
# capacidades
# --------------------------------------------------------------------------------------------
PROSPECT_FIT_REQUESTS = "PROSPECT_FIT_REQUESTS"
ABC_ALTERNATIVES = "ABC_ALTERNATIVES"
REGENERATE = "REGENERATE"
PROSPECT_BRANDING = "PROSPECT_BRANDING"
MULTIPLE_STAGING = "MULTIPLE_STAGING"
ADVANCED_BRIEF = "ADVANCED_BRIEF"

CAPABILITIES = (PROSPECT_FIT_REQUESTS, ABC_ALTERNATIVES, REGENERATE, PROSPECT_BRANDING,
                MULTIPLE_STAGING, ADVANCED_BRIEF)

#: La matriz entera, por PRODUCTO DE LA PROPIEDAD. Nótese qué ya no está: `MULTIPLE_PROPERTIES`.
#: Tener otra propiedad no es una capacidad de producto, es otra compra — vive en `grants.py`.
GRANTS: Dict[str, Dict[str, bool]] = {
    "ONE_OFF": {c: False for c in CAPABILITIES},
    "PRO": {c: True for c in CAPABILITIES},
}

LIMITS: Dict[str, Dict[str, Optional[int]]] = {
    "ONE_OFF": {"fit_requests_per_property": 1, "layouts_per_pack": 1,
                "staged_images_per_property": 1,
                # reintentos INTERNOS para cumplir esa única imagen: mecánica de producción, no
                # créditos del cliente.
                "staging_attempts_per_hero": 3},
    "PRO": {"fit_requests_per_property": None, "layouts_per_pack": 3,
            "staged_images_per_property": None, "staging_attempts_per_hero": None},
}

DENIAL = {
    PROSPECT_FIT_REQUESTS: "Las propuestas por prospecto son parte de Escalímetro Pro. El Pack "
                           "prepara la propiedad para publicarla; Pro sirve para trabajarla con "
                           "cada interesado que aparezca.",
    ABC_ALTERNATIVES: "El Pack incluye una alternativa representativa. Las tres alternativas son "
                      "parte de Escalímetro Pro.",
    REGENERATE: "Volver a generar alternativas es parte de Escalímetro Pro.",
    PROSPECT_BRANDING: "La marca del prospecto se aplica en las propuestas de Escalímetro Pro.",
    MULTIPLE_STAGING: "El Pack incluye una imagen ambientada de la foto principal. Ambientar más "
                      "fotos, o una por prospecto, es parte de Escalímetro Pro.",
    ADVANCED_BRIEF: "El programa detallado es parte de Escalímetro Pro. El Pack usa un programa "
                    "equilibrado a partir del número de personas.",
}


class EntitlementError(PermissionError):
    """Esta PROPIEDAD no tiene derecho a esto con el producto que la cubre.

    Es un límite de producto, no un fallo: el mensaje dice qué producto lo incluye. Distinto de
    `grants.PackRequired`, que es "hace falta otra compra" y no tiene nada que ver con Pro."""

    def __init__(self, capability: str, msg: str = ""):
        self.capability = capability
        super().__init__(msg or DENIAL.get(capability, "No disponible con este producto."))


# --------------------------------------------------------------------------------------------
# el producto de UNA propiedad
# --------------------------------------------------------------------------------------------
def product_of(property_id: str) -> str:
    row = store.q1("SELECT product FROM properties WHERE property_id=?", (property_id,))
    p = (row["product"] if row else None) or DEFAULT_PRODUCT
    return p if p in PRODUCTS else DEFAULT_PRODUCT


def set_product(property_id: str, product: str) -> None:
    """Cambia el producto de UNA propiedad. No toca a ninguna otra, y hay test de eso."""
    if product not in PRODUCTS:
        raise ValueError(f"producto desconocido: {product}")
    if store.q1("SELECT property_id FROM properties WHERE property_id=?", (property_id,)) is None:
        raise LookupError(property_id)
    store.ex("UPDATE properties SET product=?, updated_at=? WHERE property_id=?",
             (product, store.now(), property_id))
    store.ex("UPDATE pack_grants SET product=? WHERE property_id=?", (product, property_id))


def allows(property_id: str, capability: str) -> bool:
    if capability not in CAPABILITIES:
        raise KeyError(f"capacidad desconocida: {capability}")
    return GRANTS[product_of(property_id)][capability]


def require(property_id: str, capability: str) -> None:
    """La forma de usar esto desde el dominio: lanza, no devuelve un booleano que se pueda ignorar
    por accidente en una plantilla."""
    if not allows(property_id, capability):
        raise EntitlementError(capability)


def limit(property_id: str, name: str) -> Optional[int]:
    return LIMITS[product_of(property_id)].get(name)


def max_layouts_in_pack(property_id: str) -> Optional[int]:
    """Cuántas alternativas entran en el pack de esta propiedad. Pack: 1."""
    return LIMITS[product_of(property_id)]["layouts_per_pack"]


def granted(property_id: str) -> List[str]:
    p = product_of(property_id)
    return [c for c in CAPABILITIES if GRANTS[p][c]]


def summary(property_id: Optional[str] = None) -> Dict:
    """Con `property_id`, lo que cubre a esa propiedad. Sin él, el default para propiedades nuevas
    —útil para la cabecera del LAB, que no está mirando ninguna propiedad en particular."""
    p = product_of(property_id) if property_id else default_product()
    return {"product": p, "mode": p, "label": PRODUCT_LABEL[p], "pitch": PRODUCT_PITCH[p],
            "scoped": property_id is not None,
            "capabilities": {c: GRANTS[p][c] for c in CAPABILITIES},
            "limits": dict(LIMITS[p])}


# --------------------------------------------------------------------------------------------
# default de la cuenta (sólo para propiedades NUEVAS del LAB)
# --------------------------------------------------------------------------------------------
def default_product() -> str:
    d = settings.get(DEFAULT_KEY) or settings.get(LEGACY_MODE_KEY) or DEFAULT_PRODUCT
    return d if d in PRODUCTS else DEFAULT_PRODUCT


def set_default_product(p: str) -> None:
    if p not in PRODUCTS:
        raise ValueError(f"producto desconocido: {p}")
    settings.put(DEFAULT_KEY, p)


#: Alias históricos. `mode()` ya NO decide las capacidades de ninguna propiedad: sólo dice qué
#: producto recibirá la próxima propiedad de prueba.
mode = default_product
set_mode = set_default_product
