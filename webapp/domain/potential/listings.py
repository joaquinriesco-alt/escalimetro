"""E17.0 — EL AVISO: entidad, medios e ingesta.

=================================================================================================
Por qué la ingesta está desacoplada de cualquier portal
=================================================================================================
El encargo lo pide explícitamente y la razón es buena: un scraper de un portal concreto se rompe
la semana que el portal cambia una clase de CSS, y cuando se rompe se lleva puesto todo el
producto. Así que la URL entra por un **adaptador** que puede fallar, y cuando falla el flujo
sigue por carga manual en vez de detenerse.

`ListingSource` tiene una sola obligación: devolver lo que pudo extraer y decir con qué confianza,
sin inventar campos. Un adaptador que rellena `bedrooms=3` porque "es lo normal" contaminaría la
dimensión INFORMATION, que justamente mide qué falta.

En esta iteración hay dos fuentes: `MANUAL` (el operador escribe lo que ve) y `URL`, que guarda el
enlace y extrae sólo lo que se puede leer de forma robusta de cualquier página —título y metadatos
Open Graph— sin pretender entender ningún portal. Lo que no se pueda leer queda vacío y la
dimensión INFORMATION lo contará como faltante, que es la verdad.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Dict, List, Optional
from urllib.parse import urlparse

from ... import store
from .. import assets as lab_assets

#: Tipos de inmueble. `UNKNOWN` existe y no es un error: un aviso puede no decirlo, y forzar una
#: categoría cambiaría qué criterios se consideran aplicables.
APARTMENT, HOUSE, OFFICE, RETAIL, WAREHOUSE, LAND, UNKNOWN = (
    "APARTMENT", "HOUSE", "OFFICE", "RETAIL", "WAREHOUSE", "LAND", "UNKNOWN")
PROPERTY_TYPES = (APARTMENT, HOUSE, OFFICE, RETAIL, WAREHOUSE, LAND, UNKNOWN)
TYPE_LABEL = {APARTMENT: "Departamento", HOUSE: "Casa", OFFICE: "Oficina", RETAIL: "Local",
              WAREHOUSE: "Bodega", LAND: "Terreno", UNKNOWN: "Sin especificar"}
#: Los que se habitan. Distinguirlos no es cosmético: en una bodega, "dormitorios" no es un dato
#: faltante, es un dato que no existe, y contarlo como faltante castigaría al aviso por algo que
#: no puede tener.
RESIDENTIAL = (APARTMENT, HOUSE)
COMMERCIAL = (OFFICE, RETAIL, WAREHOUSE)

SALE, RENT = "SALE", "RENT"
OPERATIONS = (SALE, RENT)

MANUAL, URL = "MANUAL", "URL"
SOURCES = (MANUAL, URL)

PHOTO, PLAN, CONCEPTUAL = "PHOTO", "PLAN", "CONCEPTUAL"
MEDIA_KINDS = (PHOTO, PLAN, CONCEPTUAL)


class ListingError(ValueError):
    """Un problema con el aviso que quien lo carga puede entender y corregir."""


# =================================================================================================
# entidad
# =================================================================================================
CAMPOS = ("title", "property_type", "operation", "source_url", "location", "price", "currency",
          "area_m2", "bedrooms", "bathrooms", "parking", "storage", "orientation",
          "common_expenses", "description", "notes",
          # E17.2 — lo que la extracción por capas sabe leer de una publicación real.
          "total_area_m2", "usable_area_m2", "broker", "publication_id", "floor", "age_years",
          "amenities")


def _num(v, entero=False):
    """Un número o None. Nunca 0 por defecto: 0 estacionamientos y «no lo dice» son cosas
    distintas, y la dimensión INFORMATION mide exactamente esa diferencia."""
    if v is None:
        return None
    s = str(v).strip().replace(".", "").replace(",", ".") if isinstance(v, str) else v
    if s == "" or s is None:
        return None
    try:
        return int(float(s)) if entero else float(s)
    except (TypeError, ValueError):
        return None


def create(*, title: str = "", property_type: str = UNKNOWN, source: str = MANUAL,
           **campos) -> str:
    if property_type not in PROPERTY_TYPES:
        raise ListingError(f"tipo de inmueble desconocido: {property_type}")
    if source not in SOURCES:
        raise ListingError(f"origen desconocido: {source}")
    lid = "l_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO listings(listing_id, title, property_type, source, created_at, "
             "updated_at) VALUES (?,?,?,?,?,?)",
             (lid, (title or "").strip()[:200], property_type, source, store.now(), store.now()))
    if campos:
        update(lid, **campos)
    return lid


def update(listing_id: str, **campos) -> None:
    sets, args = [], []
    for k, v in campos.items():
        if k not in CAMPOS:
            continue
        if k in ("price", "area_m2", "common_expenses", "total_area_m2", "usable_area_m2"):
            v = _num(v)
        elif k in ("bedrooms", "bathrooms", "parking", "storage", "floor", "age_years"):
            v = _num(v, entero=True)
        elif k == "property_type" and v not in PROPERTY_TYPES:
            raise ListingError(f"tipo de inmueble desconocido: {v}")
        elif k == "operation" and v and v not in OPERATIONS:
            raise ListingError(f"operación desconocida: {v}")
        elif isinstance(v, str):
            v = v.strip() or None
        sets.append(f"{k}=?")
        args.append(v)
    if not sets:
        return
    args += [store.now(), listing_id]
    store.ex(f"UPDATE listings SET {', '.join(sets)}, updated_at=? WHERE listing_id=?", tuple(args))


def get(listing_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM listings WHERE listing_id=?", (listing_id,))
    return dict(r) if r else None


def require(listing_id: str) -> Dict:
    d = get(listing_id)
    if not d:
        raise ListingError("ese aviso no existe")
    return d


def listing_rows(limit: int = 50) -> List[Dict]:
    return [dict(r) for r in store.q(
        "SELECT * FROM listings ORDER BY created_at DESC LIMIT ?", (limit,))]


def delete(listing_id: str) -> None:
    import shutil                                              # noqa: PLC0415
    shutil.rmtree(store.listing_dir(listing_id), ignore_errors=True)
    store.ex("DELETE FROM listings WHERE listing_id=?", (listing_id,))


def set_cover(listing_id: str, media_id: Optional[str]) -> None:
    if media_id and not media(media_id, listing_id):
        raise ListingError("esa imagen no es de este aviso")
    store.ex("UPDATE listings SET cover_media_id=?, updated_at=? WHERE listing_id=?",
             (media_id, store.now(), listing_id))


# =================================================================================================
# medios
# =================================================================================================
def _media_dir(listing_id: str, kind: str) -> str:
    return os.path.join(store.listing_dir(listing_id),
                        {PHOTO: "photos", PLAN: "plan", CONCEPTUAL: "conceptual"}.get(kind, "other"))


def media_path(m: Dict) -> str:
    return os.path.join(_media_dir(m["listing_id"], m["kind"]), m["stored_name"])


def add_media(listing_id: str, file_storage, kind: str = PHOTO) -> str:
    """Guarda un archivo del aviso.

    La validación —extensiones admitidas, tamaño, que el contenido coincida con la extensión— se
    REUTILIZA de `domain.assets` en vez de reescribirse: son las mismas reglas sobre los mismos
    formatos, y tener dos definiciones de "archivo aceptable" sería tener dos productos con dos
    criterios de seguridad. Lo único propio es dónde se guarda y en qué tabla se registra."""
    if kind not in MEDIA_KINDS:
        raise ListingError(f"tipo de medio desconocido: {kind}")
    original = getattr(file_storage, "filename", "") or "archivo"
    ext = os.path.splitext(original)[1].lower()
    if ext not in lab_assets.ALLOWED_UPLOAD:
        raise ListingError(f"Formato no aceptado: {ext or '(sin extensión)'}. Sólo PDF, PNG o JPG.")
    if kind == PHOTO and ext not in lab_assets.PHOTO_EXT:
        raise ListingError("Las fotos tienen que ser PNG o JPG.")
    d = _media_dir(listing_id, kind)
    os.makedirs(d, exist_ok=True)
    stored = uuid.uuid4().hex + ext
    dest = os.path.join(d, stored)
    file_storage.save(dest)
    size = os.path.getsize(dest)
    if size > lab_assets.MAX_MB * 1_000_000:
        os.remove(dest)
        raise ListingError(f"El archivo pesa {size / 1e6:.1f} MB; el máximo es "
                           f"{lab_assets.MAX_MB} MB.")
    if not lab_assets._sniff(dest, ext):                       # noqa: SLF001 — misma regla, una sola
        os.remove(dest)
        raise ListingError("El contenido del archivo no coincide con su extensión.")
    w, h = lab_assets._dims(dest, ext)                         # noqa: SLF001
    return _register(listing_id, kind, original, stored, lab_assets.ALLOWED_UPLOAD[ext], size,
                     dest, w, h)


def add_media_bytes(listing_id: str, kind: str, filename: str, blob: bytes, mime: str) -> str:
    """Para material que producimos nosotros o que llega ya en memoria."""
    d = _media_dir(listing_id, kind)
    os.makedirs(d, exist_ok=True)
    stored = uuid.uuid4().hex + os.path.splitext(filename)[1].lower()
    dest = os.path.join(d, stored)
    with open(dest, "wb") as fh:
        fh.write(blob)
    w, h = lab_assets._dims(dest, os.path.splitext(filename)[1].lower())   # noqa: SLF001
    return _register(listing_id, kind, filename, stored, mime, len(blob), dest, w, h)


def _register(listing_id, kind, original, stored, mime, size, dest, w, h) -> str:
    import hashlib                                             # noqa: PLC0415
    h_ = hashlib.sha256()
    with open(dest, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h_.update(chunk)
    mid = "m_" + uuid.uuid4().hex[:12]
    orden = (store.q1("SELECT COALESCE(MAX(sort_order), -1) m FROM listing_media "
                      "WHERE listing_id=? AND kind=?", (listing_id, kind))["m"]) + 1
    store.ex("INSERT INTO listing_media(media_id, listing_id, kind, original_filename, "
             "stored_name, mime_type, size_bytes, sha256, width_px, height_px, sort_order, "
             "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
             (mid, listing_id, kind, original[:255], stored, mime, size, h_.hexdigest(), w, h,
              orden, store.now()))
    return mid


def media(media_id: str, listing_id: Optional[str] = None) -> Optional[Dict]:
    """Con `listing_id`, el medio SÓLO se devuelve si pertenece a ese aviso: la barrera contra
    leer el material de otro pasando un id ajeno."""
    if listing_id:
        r = store.q1("SELECT * FROM listing_media WHERE media_id=? AND listing_id=?",
                     (media_id, listing_id))
    else:
        r = store.q1("SELECT * FROM listing_media WHERE media_id=?", (media_id,))
    if not r:
        return None
    d = dict(r)
    d["analysis_obj"] = store.js(d["analysis"], {}) or {}
    return d


def media_of(listing_id: str, kind: Optional[str] = None) -> List[Dict]:
    if kind:
        filas = store.q("SELECT * FROM listing_media WHERE listing_id=? AND kind=? "
                        "ORDER BY sort_order, created_at", (listing_id, kind))
    else:
        filas = store.q("SELECT * FROM listing_media WHERE listing_id=? "
                        "ORDER BY kind, sort_order, created_at", (listing_id,))
    out = []
    for r in filas:
        d = dict(r)
        d["analysis_obj"] = store.js(d["analysis"], {}) or {}
        out.append(d)
    return out


def save_analysis(media_id: str, datos: Dict) -> None:
    store.ex("UPDATE listing_media SET analysis=? WHERE media_id=?",
             (json.dumps(datos, ensure_ascii=False), media_id))


def delete_media(media_id: str, listing_id: str) -> bool:
    m = media(media_id, listing_id)
    if not m:
        return False
    try:
        os.remove(media_path(m))
    except OSError:
        pass
    store.ex("DELETE FROM listing_media WHERE media_id=?", (media_id,))
    if (get(listing_id) or {}).get("cover_media_id") == media_id:
        set_cover(listing_id, None)
    return True


# =================================================================================================
# ingesta desde URL — deliberadamente poco ambiciosa
# =================================================================================================
#: Qué tan confiable es lo que se extrajo. Viaja con el resultado para que nada aguas abajo trate
#: un título leído de un `<meta>` como si fuera un dato declarado por una persona.
CONFIDENCE_DECLARED = "DECLARED"      # lo escribió una persona
CONFIDENCE_EXTRACTED = "EXTRACTED"    # se leyó de la página
CONFIDENCE_NONE = "NONE"              # no se pudo


class ListingSource:
    """Contrato de cualquier fuente de avisos. Una implementación puede fallar; lo que no puede
    es inventar. `fields` sólo lleva lo que realmente se extrajo."""

    name = "base"

    def fetch(self, reference: str) -> Dict:
        raise NotImplementedError


class ManualSource(ListingSource):
    """Lo que escribe el operador. Es la fuente de referencia, y la que siempre funciona."""

    name = MANUAL

    def fetch(self, reference: str) -> Dict:
        return {"ok": True, "source": MANUAL, "fields": {}, "confidence": CONFIDENCE_DECLARED,
                "notes": "carga manual"}


class UrlSource(ListingSource):
    """Guarda el enlace y extrae SÓLO lo que se puede leer de cualquier página sin entender su
    portal: `<title>` y los metadatos Open Graph, que existen justamente para ser leídos.

    No hay selectores de ningún portal a propósito. Un scraper específico se rompe cuando el
    portal cambia una clase, y al romperse se lleva puesto el producto entero. Lo que esta fuente
    NO pueda leer queda vacío y la dimensión INFORMATION lo contará como faltante, que es la
    verdad sobre lo que sabemos del aviso."""

    name = URL
    timeout = 8

    def fetch(self, reference: str) -> Dict:
        url = (reference or "").strip()
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            return {"ok": False, "source": URL, "fields": {}, "confidence": CONFIDENCE_NONE,
                    "notes": "eso no parece una dirección web"}
        campos: Dict[str, object] = {"source_url": url}
        try:
            import urllib.request                              # noqa: PLC0415
            req = urllib.request.Request(url, headers={"User-Agent": "Escalimetro/0.1"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:   # noqa: S310
                html = r.read(400_000).decode("utf-8", "ignore")
        except Exception as e:                                 # noqa: BLE001 — la red falla y punto
            return {"ok": False, "source": URL, "fields": campos, "confidence": CONFIDENCE_NONE,
                    "notes": f"no pudimos abrir la publicación ({type(e).__name__}). "
                             f"Se puede seguir cargando el material a mano."}
        og = dict(re.findall(
            r'<meta[^>]+property=["\']og:([a-z:]+)["\'][^>]+content=["\']([^"\']{1,400})["\']',
            html, re.I))
        titulo = og.get("title") or ""
        if not titulo:
            m = re.search(r"<title[^>]*>(.{1,300}?)</title>", html, re.I | re.S)
            titulo = m.group(1).strip() if m else ""
        if titulo:
            campos["title"] = re.sub(r"\s+", " ", titulo)[:200]
        if og.get("description"):
            campos["description"] = re.sub(r"\s+", " ", og["description"])[:4000]
        imagenes = re.findall(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']{1,600})["\']',
            html, re.I)
        return {"ok": True, "source": URL, "fields": campos,
                "confidence": CONFIDENCE_EXTRACTED,
                "images": imagenes[:12],
                "notes": ("leímos el título y la descripción de la página; el resto hay que "
                          "completarlo a mano" if campos.get("title") else
                          "la página no expone datos legibles: hay que cargar el material a mano")}


REGISTRY = {MANUAL: ManualSource(), URL: UrlSource()}


def ingest(reference: str = "", source: str = MANUAL, **campos) -> Dict:
    """Crea un aviso desde la fuente indicada. **Nunca se detiene por un fallo de la fuente**: si
    la URL no se puede leer, el aviso se crea igual con el enlace guardado y el flujo sigue por
    carga manual, que es el requisito explícito de esta fase."""
    src = REGISTRY.get(source)
    if src is None:
        raise ListingError(f"fuente desconocida: {source}")
    res = src.fetch(reference)
    datos = dict(res.get("fields") or {})
    datos.update({k: v for k, v in campos.items() if v not in (None, "")})
    lid = create(title=str(datos.pop("title", "") or ""),
                 property_type=str(datos.pop("property_type", UNKNOWN) or UNKNOWN),
                 source=source, **datos)
    return {"listing_id": lid, "ingestion": res}
