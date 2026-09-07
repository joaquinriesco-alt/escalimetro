"""E16.6 — de la semántica del problema a la estrategia de segmentación.

`drawing_scope` describe el DOMINIO: qué es la lámina. El proveedor de segmentación es
IMPLEMENTACIÓN: cómo se saca una máscara. Meterlos en el mismo `if` dentro del pipeline
convertiría un hecho del inmueble en un interruptor de código, que es justo lo que E16.5 evitó al
introducir `drawing_scope`. Esta capa los mantiene separados y explica la correspondencia.

    MULTI_UNIT   hay que encontrar UNA unidad dentro de la lámina, y algo externo —el rótulo
                 leído por OCR— dice dónde está. El problema es *crecer desde un punto conocido*:
                 `opencv_color` si el rótulo venía sobre relleno de color, `opencv_flood` si no.

    WHOLE_SHELL  la lámina describe el espacio completo. No hay punto conocido ni lo puede haber,
                 porque no hay unidad interna que señalar. El problema es *qué encierran los muros
                 exteriores*, y se resuelve por conectividad con el exterior de la hoja.

Son dos problemas distintos, no dos parámetros del mismo. Reusar la técnica del primero para el
segundo fue lo que E16.6 encontró roto."""
from __future__ import annotations

from typing import Optional

#: nombres de proveedor; el registro vive en `providers.py`
SEEDED_COLOR = "opencv_color"
SEEDED_FLOOD = "opencv_flood"
WHOLE_SHELL_PROVIDER = "whole_shell"


def strategy_for(scope: str, has_color_hint: bool = False, explicit: Optional[str] = None) -> str:
    """Qué proveedor corresponde al problema. `explicit` (config del caso) manda si no es "auto"."""
    if explicit and explicit != "auto":
        return explicit
    from ..localization import WHOLE_SHELL
    if scope == WHOLE_SHELL:
        return WHOLE_SHELL_PROVIDER
    return SEEDED_COLOR if has_color_hint else SEEDED_FLOOD
