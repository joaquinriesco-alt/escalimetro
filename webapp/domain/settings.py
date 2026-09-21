"""E30 — configuración de la cuenta. Un par clave/valor y nada más.

Existe por una razón concreta: el modo de producto (ONE_OFF / PRO) y la marca de la corredora son
hechos de la CUENTA, no de una propiedad ni de un usuario. Hoy la cuenta es una sola —el
despliegue— y por eso esto es una tabla de dos columnas en vez de un modelo de organizaciones.

§17 del encargo es explícito en las dos direcciones: que exista una comprobación de capacidad
limpia y que NO se ate a emails ni se construya facturación. Esto es el mínimo que cumple ambas y
que mañana se conecta a un billing sin tocar a quien lo consulta.
"""
from __future__ import annotations

from typing import Optional

from .. import store


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    row = store.q1("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row is not None else default


def put(key: str, value: Optional[str]) -> None:
    store.ex("INSERT INTO settings(key, value, updated_at) VALUES (?,?,?) "
             "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
             (key, value, store.now()))


def all_of(prefix: str = "") -> dict:
    rows = store.q("SELECT key, value FROM settings WHERE key LIKE ? ORDER BY key",
                   (f"{prefix}%",))
    return {r["key"]: r["value"] for r in rows}
