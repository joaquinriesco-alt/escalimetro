"""E27 — aplicación web interna de ESCALÍMETRO.

`src/` se agrega a sys.path acá y no en cada módulo: el motor se importa de forma diferida en
varios puntos (briefs, intake) y si `PYTHONPATH` no viniera puesto desde afuera, esas importaciones
fallaban con un 500 en vez de con un mensaje. El contenedor igual define PYTHONPATH; esto es el
cinturón para correr en local o desde un test sin preparar el entorno.
"""
from __future__ import annotations

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)
