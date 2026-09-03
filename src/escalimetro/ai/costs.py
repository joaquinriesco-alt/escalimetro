"""E08 — costos.

Tres estados, nunca mezclados:

    reported   — el proveedor devolvió el costo. Hoy ninguno de los dos lo hace.
    estimated  — se calculó con la tabla de precios de abajo.
    unknown    — no hay precio para ese modelo, o no hubo tokens. NO se inventa un número.

La tabla es un dato de configuración, no una constante del núcleo: si un precio cambia o el modelo no está,
el resultado es `unknown` y se reporta como tal. Precios en USD por millón de tokens."""
from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

# Última referencia pública conocida al construir E08. Puede estar desactualizada: por eso el estado
# `estimated` es explícito en cada registro y nunca se presenta como costo real.
PRICING_USD_PER_MTOK: Dict[str, Dict[str, float]] = {
    "anthropic": {
        "claude-opus-4-5": {"in": 5.0, "out": 25.0},
        "claude-sonnet-4-5": {"in": 3.0, "out": 15.0},
        "claude-haiku-4-5": {"in": 1.0, "out": 5.0},
    },
    "openai": {
        "gpt-5": {"in": 1.25, "out": 10.0},
        "gpt-5-mini": {"in": 0.25, "out": 2.0},
        "gpt-4.1": {"in": 2.0, "out": 8.0},
    },
    "deterministic": {},
}
PRICING_SOURCE = "listas públicas de precios consultadas al construir E08; sujetas a cambio"


def _prices(provider: str, model: str) -> Optional[Dict[str, float]]:
    table = PRICING_USD_PER_MTOK.get(provider, {})
    if model in table:
        return table[model]
    for k, v in table.items():                  # prefijo: gpt-5-2026-01-01 → gpt-5
        if model.startswith(k):
            return v
    return None


def estimate_cost(provider: str, model: str, input_tokens: Optional[int],
                  output_tokens: Optional[int]) -> Tuple[Optional[float], str]:
    if provider == "deterministic":
        return 0.0, "reported"                  # no hay API: el costo real es cero, no una estimación
    if input_tokens is None or output_tokens is None:
        return None, "unknown"
    p = _prices(provider, model)
    if p is None:
        return None, "unknown"
    cost = input_tokens / 1e6 * p["in"] + output_tokens / 1e6 * p["out"]
    return round(cost, 6), "estimated"


def pricing_snapshot() -> Dict:
    return {"source": PRICING_SOURCE, "unit": "USD por millón de tokens",
            "table": PRICING_USD_PER_MTOK,
            "override_env": "ESCALIMETRO_PRICING_JSON (ruta a un JSON con la misma forma)"}


def load_pricing_override(path: Optional[str] = None) -> bool:
    """Permite reemplazar la tabla sin tocar código."""
    import json
    p = path or os.environ.get("ESCALIMETRO_PRICING_JSON")
    if not p or not os.path.exists(p):
        return False
    PRICING_USD_PER_MTOK.update(json.load(open(p, encoding="utf-8")))
    return True
