"""E17.2 §2 — DEL LINK AL INFORME, SIN QUE NADIE TENGA QUE SUBIR NADA.

    UrlAcquirer  →  RawListingSnapshot  →  ListingExtractor  →  MediaClassifier  →  Analyzer
    (fetcher.py)     (listing_snapshots)     (extract.py)        (classify.py)      (analyzer.py)

Cada eslabón vive en su archivo y ninguno sabe del siguiente. La razón es la de siempre: mezclar
adquisición con puntaje significa que el día que un portal cambie, la falla aparezca como un score
raro en vez de como un error de red.

=================================================================================================
El estado es honesto o no sirve (§16)
=================================================================================================
    SUCCESS   trajimos datos Y material. El camino en el que Joaquín no toca un archivo.
    PARTIAL   trajimos algo pero no alcanza: hay datos sin fotos, o fotos sin datos.
    FAILED    el portal no se dejó leer, y se guarda POR QUÉ.

Un `SUCCESS` que en realidad no trajo nada arruinaría el experimento entero: la muestra de 20 mide
justamente si podemos analizar una URL casi solos, y un estado optimista haría que esa pregunta se
conteste sola y mal. Por eso el umbral de SUCCESS exige las dos cosas a la vez.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Dict, List, Optional

from ... import store
from . import classify, extract, fetcher, listings

SUCCESS, PARTIAL, FAILED = "SUCCESS", "PARTIAL", "FAILED"
STATUS_LABEL = {SUCCESS: "leímos la publicación", PARTIAL: "leímos parte de la publicación",
                FAILED: "no pudimos leer la publicación"}

#: Motivos propios de esta capa, además de los de `fetcher`.
NO_MEDIA_FOUND = "NO_MEDIA_FOUND"
PARSE_FAILED = "PARSE_FAILED"
NOT_A_LISTING = "NOT_A_LISTING"
REASON_LABEL = dict(fetcher.REASON_LABEL,
                    NO_MEDIA_FOUND="la página no expone fotos que podamos leer",
                    PARSE_FAILED="la página no tiene datos que podamos interpretar",
                    NOT_A_LISTING="eso parece la portada de un portal, no una publicación")

#: Lo que hace que una página SEA un aviso y no la portada del portal. Sin esto, una home con
#: fotos bonitas entra como SUCCESS y el experimento cuenta como "analizada" una página que no
#: describe ningún inmueble — que es la peor forma de inflar la métrica de adquisición.
LISTING_MARKERS = ("price", "area_m2", "total_area_m2", "usable_area_m2", "publication_id")


def looks_like_listing(campos: Dict[str, Dict]) -> bool:
    return any((campos.get(k) or {}).get("value") not in (None, "") for k in LISTING_MARKERS)

#: Mínimos para declarar SUCCESS. Con menos, el usuario va a tener que completar a mano y decir
#: que salió bien sería mentirle al experimento antes que a él.
MIN_FIELDS_SUCCESS = 4
MIN_PHOTOS_SUCCESS = 3
#: Tope de imágenes que se bajan de verdad. `extract` ya acota la lista; esto acota el trabajo.
MAX_DOWNLOADS = 30

#: Campos del extractor que son columnas del aviso. El resto viaja en `provenance` y en
#: `_attributes`: guardar una columna por atributo de portal sería perseguir un esquema ajeno.
COLUMNS = ("title", "description", "property_type", "operation", "price", "currency",
           "common_expenses", "location", "area_m2", "total_area_m2", "usable_area_m2",
           "bedrooms", "bathrooms", "parking", "storage", "orientation", "floor", "age_years",
           "broker", "publication_id", "source_url")


def ingest_url(url: str, listing_id: Optional[str] = None) -> Dict:
    """El camino completo. Devuelve el estado y lo que se trajo; nunca lanza por un portal
    caído: un fallo de adquisición es un resultado del producto, no una excepción."""
    lid = listing_id or listings.create(title="", source=listings.URL)
    listings.update(lid, source_url=url)
    try:
        page = fetcher.fetch_page(url)
    except fetcher.FetchError as e:
        _snapshot(lid, url, error={"reason": e.reason, "detail": e.detail})
        return _finish(lid, FAILED, e.reason, 0, 0, 0)

    try:
        datos = extract.extract(page["html"], page["final_url"])
    except Exception as e:                                     # noqa: BLE001 — una página rara no rompe el producto
        _snapshot(lid, url, page=page, error={"reason": PARSE_FAILED, "detail": type(e).__name__})
        return _finish(lid, FAILED, PARSE_FAILED, 0, 0, 0)

    campos = datos["fields"]
    _apply_fields(lid, campos)
    _snapshot(lid, url, page=page, datos=datos)

    fotos, planos = _download_media(lid, datos["images"], page["final_url"])
    n_campos = sum(1 for k, v in campos.items()
                   if not k.startswith("_") and v.get("value") not in (None, ""))
    if not looks_like_listing(campos):
        # No es un aviso: ni precio, ni superficie, ni id de publicación. Puede tener fotos y
        # título igual —una portada de portal los tiene— y por eso el marcador es lo que
        # describe un INMUEBLE, no lo que adorna una página.
        estado, motivo = PARTIAL, NOT_A_LISTING
    elif fotos and n_campos >= MIN_FIELDS_SUCCESS and len(fotos) >= MIN_PHOTOS_SUCCESS:
        estado, motivo = SUCCESS, None
    elif n_campos or fotos:
        estado, motivo = PARTIAL, (NO_MEDIA_FOUND if not fotos else None)
    else:
        estado, motivo = FAILED, PARSE_FAILED
    return _finish(lid, estado, motivo, n_campos, len(fotos), len(planos))


def _apply_fields(listing_id: str, campos: Dict[str, Dict]) -> None:
    """Escribe lo extraído SIN pisar lo que corrigió una persona: una corrección manual gana
    siempre, y un reanálisis que la borrara haría inútil corregir."""
    prev = store.js((listings.get(listing_id) or {}).get("provenance"), {}) or {}
    escribir, proc = {}, dict(prev)
    for k, v in campos.items():
        if k.startswith("_") or v.get("value") in (None, ""):
            continue
        if (prev.get(k) or {}).get("source") == extract.MANUAL_OVERRIDE:
            continue
        proc[k] = v
        if k in COLUMNS:
            escribir[k] = v["value"]
    atributos = (campos.get("_attributes") or {}).get("value")
    if atributos:
        proc["_attributes"] = campos["_attributes"]
        escribir["amenities"] = json.dumps(atributos, ensure_ascii=False)
    if escribir:
        listings.update(listing_id, **{k: v for k, v in escribir.items()
                                       if k in listings.CAMPOS})
        extra = {k: v for k, v in escribir.items() if k not in listings.CAMPOS}
        if extra:
            sets = ", ".join(f"{k}=?" for k in extra)
            store.ex(f"UPDATE listings SET {sets}, updated_at=? WHERE listing_id=?",
                     (*extra.values(), store.now(), listing_id))
    store.ex("UPDATE listings SET provenance=?, updated_at=? WHERE listing_id=?",
             (json.dumps(proc, ensure_ascii=False), store.now(), listing_id))


def _download_media(listing_id: str, urls: List[str], base: str) -> tuple:
    """Baja, valida, clasifica y deduplica. Lo que no sea foto ni plano se guarda igual pero
    clasificado, para que se vea qué trajo la galería sin que ensucie el análisis."""
    ya = {m["sha256"] for m in listings.media_of(listing_id)}
    fotos, planos = [], []
    for u in urls[:MAX_DOWNLOADS]:
        try:
            r = fetcher.fetch_image(u)
        except fetcher.FetchError:
            continue                                           # una imagen caída no frena la galería
        ext = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
               "image/webp": ".webp"}.get(r["content_type"], ".jpg")
        tmp = os.path.join(store.listing_dir(listing_id), "tmp")
        os.makedirs(tmp, exist_ok=True)
        ruta = os.path.join(tmp, uuid.uuid4().hex + ext)
        with open(ruta, "wb") as fh:
            fh.write(r["bytes"])
        try:
            cls = classify.classify(ruta, u)
            if cls["kind"] == classify.FLOORPLAN:
                kind = listings.PLAN
            elif cls["kind"] == classify.PHOTO:
                kind = listings.PHOTO
            else:
                os.remove(ruta)                                # logos y mapas no se guardan
                continue
            import hashlib                                     # noqa: PLC0415
            sha = hashlib.sha256(r["bytes"]).hexdigest()
            if sha in ya:
                os.remove(ruta)
                continue
            ya.add(sha)
            mid = listings.add_media_bytes(listing_id, kind, os.path.basename(u.split("?")[0]),
                                           r["bytes"], r["content_type"])
            store.ex("UPDATE listing_media SET source_url=?, classification=?, "
                     "classification_why=? WHERE media_id=?",
                     (u, cls["kind"], cls["why"], mid))
            (planos if kind == listings.PLAN else fotos).append(mid)
        finally:
            if os.path.exists(ruta):
                os.remove(ruta)
    if fotos and not (listings.get(listing_id) or {}).get("cover_media_id"):
        listings.set_cover(listing_id, fotos[0])               # la primera de la galería es la portada del aviso
    return fotos, planos


def _snapshot(listing_id: str, url: str, page: Optional[Dict] = None,
              datos: Optional[Dict] = None, error: Optional[Dict] = None) -> None:
    store.ex("INSERT INTO listing_snapshots(snapshot_id, listing_id, url, final_url, status, "
             "content_type, size_bytes, redirects, layers, image_urls, fields, error, created_at) "
             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
             ("sn_" + uuid.uuid4().hex[:12], listing_id, url,
              (page or {}).get("final_url"), (page or {}).get("status"),
              (page or {}).get("content_type"), (page or {}).get("size"),
              json.dumps((page or {}).get("redirects") or [], ensure_ascii=False),
              json.dumps((datos or {}).get("layers") or {}, ensure_ascii=False),
              json.dumps((datos or {}).get("images") or [], ensure_ascii=False),
              json.dumps({k: v for k, v in ((datos or {}).get("fields") or {}).items()
                          if not k.startswith("_")}, ensure_ascii=False),
              json.dumps(error, ensure_ascii=False) if error else None, store.now()))


def _finish(listing_id: str, estado: str, motivo: Optional[str], campos: int,
            fotos: int, planos: int) -> Dict:
    store.ex("UPDATE listings SET url_ingest_status=?, url_ingest_reason=?, url_ingest_at=?, "
             "fields_extracted_count=?, photos_extracted_count=?, floorplans_detected_count=?, "
             "updated_at=? WHERE listing_id=?",
             (estado, motivo, store.now(), campos, fotos, planos, store.now(), listing_id))
    return {"listing_id": listing_id, "status": estado, "reason": motivo,
            "reason_label": REASON_LABEL.get(motivo) if motivo else None,
            "status_label": STATUS_LABEL[estado], "fields": campos, "photos": fotos,
            "floorplans": planos}


def snapshots(listing_id: str) -> List[Dict]:
    return [dict(r) for r in store.q(
        "SELECT * FROM listing_snapshots WHERE listing_id=? ORDER BY created_at DESC",
        (listing_id,))]


def provenance(listing_id: str) -> Dict:
    return store.js((listings.get(listing_id) or {}).get("provenance"), {}) or {}


def manual_override(listing_id: str, campos: Dict) -> None:
    """§9 — lo que corrige una persona queda marcado como tal y no se vuelve a pisar."""
    proc = provenance(listing_id)
    limpios = {k: v for k, v in campos.items() if k in listings.CAMPOS and v not in (None, "")}
    for k, v in limpios.items():
        proc[k] = extract.field(v, extract.MANUAL_OVERRIDE)
    if limpios:
        listings.update(listing_id, **limpios)
    store.ex("UPDATE listings SET provenance=?, updated_at=? WHERE listing_id=?",
             (json.dumps(proc, ensure_ascii=False), store.now(), listing_id))
