"""E17.0 — QUÉ SE PUEDE HACER PARA MOSTRAR EL POTENCIAL QUE FALTA.

El usuario no elige de un catálogo. ESCALÍMETRO recomienda, y para recomendar hace falta un
catálogo interno con reglas claras sobre cuándo cada intervención es la correcta.

=================================================================================================
Regla de veracidad, escrita donde se decide
=================================================================================================
Toda visualización generativa preserva el inmueble real. No se mueven ventanas, no se borran
pilares, no se agrandan espacios, no se inventan vistas ni terrazas, no se representa como
existente algo que no existe. Cada tipo declara qué le está permitido cambiar (`may_change`) y qué
no (`preserve`), y esas listas son el contrato que cualquier proveedor tendrá que respetar el día
que se conecte uno.

=================================================================================================
Por qué RENOVATION_VISUALIZATION no se recomienda sola todavía
=================================================================================================
El ejemplo del encargo —«la cocina domina negativamente la percepción»— requiere reconocer una
cocina y juzgar su estado. No tenemos con qué: no hay clasificador de ambientes y no vamos a
fabricar uno con reglas de píxeles. El tipo existe en el catálogo y se puede elegir a mano, pero
el motor de recomendación no lo propone por su cuenta. Proponerlo con una excusa inventada sería
exactamente el "score diseñado para vender features" que el encargo prohíbe.
"""
from __future__ import annotations

from typing import Dict, List, Optional

PHOTO_ENHANCE = "PHOTO_ENHANCE"
COVER_SELECTION = "COVER_SELECTION"
VIRTUAL_STAGE = "VIRTUAL_STAGE"
RENOVATION_VISUALIZATION = "RENOVATION_VISUALIZATION"
SPACE_REIMAGINATION = "SPACE_REIMAGINATION"
SPATIAL_LAYOUT = "SPATIAL_LAYOUT"

#: Toda salida generativa es esto y se etiqueta así internamente.
CONCEPTUAL_VISUALIZATION = "CONCEPTUAL_VISUALIZATION"
#: Y así se muestra en producto. Una sola frase, siempre la misma.
DISCLOSURE = "Visualización referencial de potencial."

#: Lo que NINGUNA intervención puede tocar. Es la regla de veracidad hecha dato.
STRUCTURAL = ("muros", "ventanas", "puertas", "pilares", "dimensiones", "vistas por la ventana",
              "terrazas", "superficie")

CATALOG: Dict[str, Dict] = {
    PHOTO_ENHANCE: {
        "label": "Mejorar la imagen",
        "scope": "PHOTO",
        "generative": False,
        "what": "corregir exposición, contraste y verticales sin cambiar lo que se ve",
        "preserve": STRUCTURAL + ("mobiliario existente", "colores reales de materiales"),
        "may_change": ("exposición", "balance de blancos", "contraste", "corrección de perspectiva"),
        "auto_recommendable": True,
    },
    COVER_SELECTION: {
        "label": "Elegir mejor la portada y el orden",
        "scope": "SET",
        "generative": False,
        "what": "usar como portada la mejor foto disponible y ordenar el resto",
        "preserve": STRUCTURAL + ("todas las fotos originales",),
        "may_change": ("qué foto va primera", "el orden", "qué fotos repetidas se ocultan"),
        "auto_recommendable": True,
    },
    VIRTUAL_STAGE: {
        "label": "Mostrar un uso posible del espacio",
        "scope": "PHOTO",
        "generative": True,
        "what": "amoblar referencialmente un espacio vacío manteniendo la arquitectura existente",
        "preserve": STRUCTURAL + ("terminaciones", "iluminación natural"),
        "may_change": ("mobiliario", "decoración", "textiles"),
        "auto_recommendable": True,
    },
    RENOVATION_VISUALIZATION: {
        "label": "Mostrar una remodelación referencial",
        "scope": "PHOTO",
        "generative": True,
        "what": "mostrar cómo podría verse un recinto remodelado, sin cambiar su geometría",
        "preserve": STRUCTURAL,
        "may_change": ("terminaciones", "artefactos", "muebles fijos", "color"),
        # Ver el encabezado: hace falta reconocer y juzgar un recinto, y no tenemos con qué.
        "auto_recommendable": False,
        "why_not_auto": "requiere reconocer el recinto y juzgar su estado; hoy eso lo decide una "
                        "persona",
    },
    SPACE_REIMAGINATION: {
        "label": "Mostrar usos posibles del inmueble",
        "scope": "PHOTO",
        "generative": True,
        "what": "mostrar para qué podría servir un espacio vacío sin uso evidente",
        "preserve": STRUCTURAL,
        "may_change": ("mobiliario", "equipamiento", "señalética referencial"),
        "auto_recommendable": True,
    },
    SPATIAL_LAYOUT: {
        "label": "Demostrar cabida",
        "scope": "PLAN",
        "generative": False,
        "what": "usar el plano para mostrar cuántos puestos y recintos caben de verdad",
        "preserve": STRUCTURAL + ("la planta tal como está dibujada",),
        "may_change": ("la distribución propuesta sobre la planta",),
        "auto_recommendable": True,
        "engine": "capacidad existente de análisis de planta y layout",
    },
}

TYPES = tuple(CATALOG)


def label(code: str) -> str:
    return (CATALOG.get(code) or {}).get("label", code)


def is_generative(code: str) -> bool:
    return bool((CATALOG.get(code) or {}).get("generative"))


def contract(code: str) -> Dict:
    """Lo que el día de mañana habrá que pasarle a un proveedor: qué preservar, qué puede cambiar
    y con qué etiqueta sale. Existe ahora para que la regla de veracidad no dependa de que alguien
    se acuerde de escribirla cuando llegue el proveedor."""
    c = CATALOG.get(code)
    if not c:
        raise ValueError(f"intervención desconocida: {code}")
    return {"intervention": code, "label": c["label"], "generative": c["generative"],
            "preserve": list(c["preserve"]), "may_change": list(c["may_change"]),
            "forbidden": list(STRUCTURAL),
            "visualization_class": CONCEPTUAL_VISUALIZATION if c["generative"] else None,
            "disclosure": DISCLOSURE if c["generative"] else None}


def auto_recommendable(code: str) -> bool:
    return bool((CATALOG.get(code) or {}).get("auto_recommendable"))
