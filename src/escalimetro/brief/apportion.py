"""E24 §7 — reparto entero de puestos entre barrios de trabajo.

Método del mayor resto (Hare/Hamilton) sobre proporciones declaradas por la estrategia. Propiedades
que E24 exige y que los tests verifican:

  * la suma de los enteros repartidos es EXACTAMENTE `total` (nunca ±1);
  * el reparto es determinista (empates de resto se rompen por índice ascendente);
  * conserva la intención relativa: la proporción declarada manda, no una tabla por tamaño.

No hay tablas por headcount. `apportion(40, [0.6, 0.4])` da [24, 16] porque 0.6·40 = 24, no porque
alguien haya escrito 24 en alguna parte.
"""
from __future__ import annotations

import math
from typing import List, Sequence


def apportion(total: int, proportions: Sequence[float]) -> List[int]:
    total = int(total)
    if total < 0:
        raise ValueError(f"total negativo: {total}")
    if not proportions:
        raise ValueError("proporciones vacías")
    if any(p < 0 for p in proportions):
        raise ValueError(f"proporción negativa: {list(proportions)}")
    s = float(sum(proportions))
    if s <= 0:
        raise ValueError("las proporciones suman 0")
    quotas = [total * (p / s) for p in proportions]
    base = [int(math.floor(q)) for q in quotas]
    resto = total - sum(base)
    if resto:
        # mayor resto primero; empate → índice menor primero (determinista)
        orden = sorted(range(len(quotas)), key=lambda i: (-(quotas[i] - base[i]), i))
        for i in orden[:resto]:
            base[i] += 1
    assert sum(base) == total, (total, proportions, base)
    return base
