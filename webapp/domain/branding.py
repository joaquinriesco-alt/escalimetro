"""E30 §20 — MARCA. Dos marcas que no se mezclan, y ninguna gestión de marcas.

    BROKERAGE   la corredora. Va en el pack de publicación de la propiedad.
    PROSPECT    el prospecto. Va SÓLO en su fit request y en lo que salga de ese fit.

Mezclarlas sería un error comercial concreto: mandarle a un prospecto material con el logo de otro,
o publicar un aviso con el nombre del cliente que todavía no arrienda. Por eso el logo del prospecto
cuelga del fit y no de la propiedad, y por eso el pack base NUNCA lee marca de prospecto. Hay test.

§20 también dice qué NO construir: "Do not create a full brand management SaaS". No hay biblioteca
de marcas, ni versiones, ni aprobaciones. Un nombre, un logo, un color.

Lo que la marca no puede hacer (§7): tocar el contenido arquitectónico. Se dibuja en el pie de una
lámina y en la portada de la propuesta; no entra al plano ni al layout, que son lo que se está
certificando.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from typing import Dict, Optional

from .. import store
from . import settings

BROKERAGE = "BROKERAGE"
PROSPECT = "PROSPECT"
SCOPES = (BROKERAGE, PROSPECT)

LOGO_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MAX_LOGO_MB = 4

#: Claves de la marca de la corredora en `settings`.
K_NAME = "brokerage_name"
K_COLOR = "brokerage_color"
K_LOGO = "brokerage_logo_id"

#: Color por defecto: el gris del resto de la interfaz. Sobrio a propósito (§7).
DEFAULT_COLOR = "#1f2430"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandError(ValueError):
    """Un problema con la marca que el usuario puede corregir."""


def normalize_color(value: Optional[str], default: str = DEFAULT_COLOR) -> str:
    """Un color de marca es un hex y nada más. No se acepta texto libre: este valor termina
    escrito dentro de un SVG y de un HTML, así que se valida en la puerta en vez de escaparlo
    después en cada uso."""
    v = (value or "").strip()
    if not v:
        return default
    if not v.startswith("#"):
        v = "#" + v
    if len(v) == 4 and _HEX.match("#" + v[1] * 2 + v[2] * 2 + v[3] * 2):
        v = "#" + v[1] * 2 + v[2] * 2 + v[3] * 2
    if not _HEX.match(v):
        raise BrandError("El color de marca tiene que ser un hexadecimal, por ejemplo #1f4fd8.")
    return v.lower()


# ---------------------------------------------------------------------------------------------
# logos
# ---------------------------------------------------------------------------------------------
def logo_path(logo: Dict) -> str:
    return os.path.join(store.brand_dir(), logo["stored_name"])


def save_logo(file_storage, scope: str) -> str:
    """Guarda un logo y devuelve su logo_id. Mismas tres reglas que `assets`: el nombre del
    usuario no toca el disco, se mira el contenido y se sirve por identidad."""
    if scope not in SCOPES:
        raise BrandError(f"ámbito de marca desconocido: {scope}")
    nombre = file_storage.filename or "logo"
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in LOGO_EXT:
        raise BrandError("El logo tiene que ser PNG o JPG.")
    os.makedirs(store.brand_dir(), exist_ok=True)
    stored = uuid.uuid4().hex + ext
    dest = os.path.join(store.brand_dir(), stored)
    file_storage.save(dest)
    size = os.path.getsize(dest)
    if size > MAX_LOGO_MB * 1_000_000:
        os.remove(dest)
        raise BrandError(f"El logo pesa {size / 1e6:.1f} MB; el máximo es {MAX_LOGO_MB} MB.")
    with open(dest, "rb") as fh:
        head = fh.read(8)
    ok = head.startswith(b"\x89PNG\r\n\x1a\n") if ext == ".png" else head.startswith(b"\xff\xd8\xff")
    if not ok:
        os.remove(dest)
        raise BrandError("El contenido del archivo no coincide con su extensión.")
    h = hashlib.sha256()
    with open(dest, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    lid = "lg_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO brand_logos(logo_id, scope, stored_name, mime_type, size_bytes, "
             "sha256, created_at) VALUES (?,?,?,?,?,?,?)",
             (lid, scope, stored, LOGO_EXT[ext], size, h.hexdigest(), store.now()))
    return lid


def logo(logo_id: Optional[str], scope: Optional[str] = None) -> Optional[Dict]:
    """Con `scope`, un logo del ámbito equivocado no existe: es lo que impide servir el logo de un
    prospecto desde la ruta de la corredora."""
    if not logo_id:
        return None
    row = store.q1("SELECT * FROM brand_logos WHERE logo_id=?", (logo_id,))
    if row is None:
        return None
    d = dict(row)
    if scope is not None and d["scope"] != scope:
        return None
    return d


def delete_logo(logo_id: str) -> bool:
    lg = logo(logo_id)
    if lg is None:
        return False
    try:
        os.remove(logo_path(lg))
    except OSError:
        pass
    store.ex("DELETE FROM brand_logos WHERE logo_id=?", (logo_id,))
    return True


# ---------------------------------------------------------------------------------------------
# marca de la corredora — de la cuenta, no de la propiedad
# ---------------------------------------------------------------------------------------------
def set_brokerage(name: str = "", color: str = "", logo_id: Optional[str] = None) -> None:
    settings.put(K_NAME, (name or "").strip()[:120])
    settings.put(K_COLOR, normalize_color(color))
    if logo_id is not None:
        anterior = settings.get(K_LOGO)
        settings.put(K_LOGO, logo_id or None)
        if anterior and anterior != logo_id:
            delete_logo(anterior)


def brokerage() -> Dict:
    lid = settings.get(K_LOGO)
    return {"scope": BROKERAGE, "name": settings.get(K_NAME, "") or "",
            "color": normalize_color(settings.get(K_COLOR)), "logo_id": lid,
            "has_logo": logo(lid, BROKERAGE) is not None}


def prospect(fit: Dict) -> Dict:
    """Marca de un prospecto, leída del fit request. Nunca cae a la de la corredora: si el fit no
    tiene marca, la propuesta sale sin marca de prospecto, que es lo honesto."""
    lid = fit.get("prospect_logo_id")
    return {"scope": PROSPECT, "name": (fit.get("prospect_name") or "").strip(),
            "color": normalize_color(fit.get("prospect_color")), "logo_id": lid,
            "has_logo": logo(lid, PROSPECT) is not None}
