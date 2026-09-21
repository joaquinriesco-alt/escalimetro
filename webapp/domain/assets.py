"""E28.2 — assets de una propiedad: el plano original y las fotos.

Tres reglas de seguridad que este módulo hace cumplir por construcción (§7, §24):

1. **El nombre que sube el usuario nunca toca el filesystem.** Se guarda en la base como dato, y
   el archivo se escribe con un nombre interno derivado de un UUID. Un `../../etc/passwd.png` es
   simplemente una cadena en una columna.
2. **Todo archivo se sirve por asset_id, y el asset_id se valida contra la propiedad.** No hay
   ninguna ruta que acepte un path; pedir un asset de otra propiedad da 404.
3. **Se mira el contenido, no sólo la extensión.** Un `.png` cuyos primeros bytes son `%PDF` no
   entra.

Lo que E28 NO hace: transformar las fotos. Se guardan, se listan, se ordenan y se pueden borrar.
El contrato para derivarlas está en `visual.py` y no tiene implementación.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from typing import Dict, List, Optional

from .. import store

#: Tipos vivos en E28.
FLOORPLAN_ORIGINAL = "FLOORPLAN_ORIGINAL"
PHOTO_ORIGINAL = "PHOTO_ORIGINAL"
FLOORPLAN_COMMERCIAL = "FLOORPLAN_COMMERCIAL"
LAYOUT_RENDER = "LAYOUT_RENDER"
#: Tipos RESERVADOS: existen en el vocabulario para que E29 no tenga que migrar, pero nada en E28
#: los produce. Que un tipo esté declarado no significa que la capacidad exista.
PHOTO_STAGED = "PHOTO_STAGED"
BEFORE_AFTER = "BEFORE_AFTER"
VIDEO = "VIDEO"
BROCHURE = "BROCHURE"
PACK_EXPORT = "PACK_EXPORT"

KINDS = (FLOORPLAN_ORIGINAL, PHOTO_ORIGINAL, FLOORPLAN_COMMERCIAL, LAYOUT_RENDER,
         PHOTO_STAGED, BEFORE_AFTER, VIDEO, BROCHURE, PACK_EXPORT)
#: Los únicos que E28 sabe producir. El resto se rechaza si alguien intenta crearlos a mano.
IMPLEMENTED_KINDS = (FLOORPLAN_ORIGINAL, PHOTO_ORIGINAL, FLOORPLAN_COMMERCIAL, LAYOUT_RENDER,
                     PACK_EXPORT)

ALLOWED_UPLOAD = {".pdf": "application/pdf", ".png": "image/png",
                  ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
PHOTO_EXT = {".png", ".jpg", ".jpeg"}
MAX_MB = int(os.environ.get("ESCALIMETRO_MAX_UPLOAD_MB", "40"))


class AssetError(ValueError):
    """Un problema con el archivo que el usuario puede entender y corregir."""


def _dir(property_id: str, kind: str) -> str:
    sub = {FLOORPLAN_ORIGINAL: "floorplan", PHOTO_ORIGINAL: "photos",
           FLOORPLAN_COMMERCIAL: "floorplan", LAYOUT_RENDER: "layouts",
           PACK_EXPORT: "pack"}.get(kind, "other")
    return os.path.join(store.property_dir(property_id), sub)


def path_of(asset: Dict) -> str:
    return os.path.join(_dir(asset["property_id"], asset["kind"]), asset["stored_name"])


def _sniff(path: str, ext: str) -> bool:
    with open(path, "rb") as fh:
        head = fh.read(8)
    if ext == ".pdf":
        return head.startswith(b"%PDF")
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    return head.startswith(b"\xff\xd8\xff")


def _dims(path: str, ext: str):
    if ext not in PHOTO_EXT:
        return (None, None)
    try:
        import cv2                                            # noqa: PLC0415
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        return (int(img.shape[1]), int(img.shape[0])) if img is not None else (None, None)
    except Exception:                                         # noqa: BLE001
        return (None, None)


def save_upload(property_id: str, file_storage, kind: str, metadata: Optional[Dict] = None) -> str:
    """Guarda un archivo subido y devuelve su asset_id."""
    if kind not in IMPLEMENTED_KINDS:
        raise AssetError(f"tipo de asset no soportado todavía: {kind}")
    original = file_storage.filename or "archivo"
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_UPLOAD:
        raise AssetError(f"Formato no aceptado: {ext or '(sin extensión)'}. Sólo PDF, PNG o JPG.")
    if kind == PHOTO_ORIGINAL and ext not in PHOTO_EXT:
        raise AssetError("Las fotos tienen que ser PNG o JPG.")
    d = _dir(property_id, kind)
    os.makedirs(d, exist_ok=True)
    stored = uuid.uuid4().hex + ext                           # el nombre del usuario no llega acá
    dest = os.path.join(d, stored)
    file_storage.save(dest)
    size = os.path.getsize(dest)
    if size > MAX_MB * 1_000_000:
        os.remove(dest)
        raise AssetError(f"El archivo pesa {size / 1e6:.1f} MB; el máximo es {MAX_MB} MB.")
    if not _sniff(dest, ext):
        os.remove(dest)
        raise AssetError("El contenido del archivo no coincide con su extensión.")
    return _register(property_id, kind, original, stored, ALLOWED_UPLOAD[ext], size,
                     _sha(dest), *_dims(dest, ext), metadata=metadata)


def save_bytes(property_id: str, kind: str, filename: str, blob: bytes, mime: str,
               source_asset_id: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
    """Registra un asset que produjimos nosotros (plano comercial, render de layout, ZIP)."""
    if kind not in IMPLEMENTED_KINDS:
        raise AssetError(f"tipo de asset no soportado todavía: {kind}")
    d = _dir(property_id, kind)
    os.makedirs(d, exist_ok=True)
    stored = uuid.uuid4().hex + os.path.splitext(filename)[1].lower()
    dest = os.path.join(d, stored)
    with open(dest, "wb") as fh:
        fh.write(blob)
    ext = os.path.splitext(filename)[1].lower()
    return _register(property_id, kind, filename, stored, mime, len(blob), _sha(dest),
                     *_dims(dest, ext), source_asset_id=source_asset_id, metadata=metadata)


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _register(property_id, kind, original, stored, mime, size, sha, w, h,
              source_asset_id=None, metadata=None) -> str:
    aid = "a_" + uuid.uuid4().hex[:12]
    orden = (store.q1("SELECT COALESCE(MAX(sort_order), -1) m FROM property_assets "
                      "WHERE property_id=? AND kind=?", (property_id, kind))["m"]) + 1
    store.ex("INSERT INTO property_assets(asset_id, property_id, kind, original_filename, "
             "stored_name, mime_type, size_bytes, sha256, width_px, height_px, sort_order, "
             "source_asset_id, metadata, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (aid, property_id, kind, original[:255], stored, mime, size, sha, w, h, orden,
              source_asset_id, json.dumps(metadata or {}, ensure_ascii=False), store.now()))
    return aid


# ---------------------------------------------------------------------------------------------
# lectura
# ---------------------------------------------------------------------------------------------
def get(asset_id: str, property_id: Optional[str] = None) -> Optional[Dict]:
    """Con `property_id`, el asset SÓLO se devuelve si pertenece a esa propiedad. Es la barrera
    contra leer los archivos de otro cliente pasando un id ajeno."""
    row = store.q1("SELECT * FROM property_assets WHERE asset_id=?", (asset_id,))
    if row is None:
        return None
    a = dict(row)
    if property_id is not None and a["property_id"] != property_id:
        return None
    return a


def list_of_kind(property_id: str, kind: str) -> List[Dict]:
    return [dict(r) for r in store.q(
        "SELECT * FROM property_assets WHERE property_id=? AND kind=? ORDER BY sort_order, created_at",
        (property_id, kind))]


def first_of_kind(property_id: str, kind: str) -> Optional[Dict]:
    rows = list_of_kind(property_id, kind)
    return rows[0] if rows else None


def all_of(property_id: str) -> List[Dict]:
    return [dict(r) for r in store.q(
        "SELECT * FROM property_assets WHERE property_id=? ORDER BY kind, sort_order", (property_id,))]


def delete(asset_id: str, property_id: str) -> bool:
    """Borra un asset propio. Devuelve False si no existe o es de otra propiedad — nunca borra
    a ciegas por id."""
    a = get(asset_id, property_id)
    if a is None:
        return False
    try:
        os.remove(path_of(a))
    except OSError:
        pass                                                  # el registro manda; el archivo puede faltar
    store.ex("DELETE FROM property_assets WHERE asset_id=?", (asset_id,))
    return True


def reorder(property_id: str, kind: str, asset_ids: List[str]) -> None:
    for i, aid in enumerate(asset_ids):
        store.ex("UPDATE property_assets SET sort_order=? WHERE asset_id=? AND property_id=? "
                 "AND kind=?", (i, aid, property_id, kind))


def purge_kind(property_id: str, kind: str) -> None:
    """Borra los derivados de un tipo antes de regenerarlos (plano comercial, renders)."""
    for a in list_of_kind(property_id, kind):
        delete(a["asset_id"], property_id)


def drop_property_files(property_id: str) -> None:
    shutil.rmtree(store.property_dir(property_id), ignore_errors=True)
