"""E37 §4 y §13 — el plano real: se carga, queda oculto, y sólo una persona lo revela.

La ceguera no se confía a que nadie mire: está en la forma del código.

* el archivo vive en `DATA_DIR/reconstruction_gt/<proyecto>/`, FUERA de la carpeta del proyecto;
* su fila vive en `recon_ground_truth`, que ningún módulo que arme la entrada de un motor consulta;
* `runs` y `engines` NO importan este módulo (lo verifica un test), y la entrada de un motor se
  arma sólo desde los ids de inputs que la corrida congeló al crearse;
* antes del reveal, la UI sabe una sola cosa: si existe. Ni nombre, ni tamaño, ni hash, ni una
  miniatura; la ruta que lo sirve responde 404;
* revelar es un POST con confirmación, queda en la bitácora y no se deshace (lo impide un trigger).

Las corridas que se crearon antes del reveal quedan marcadas como generadas a ciegas; las
posteriores, como creadas con el plano ya visto por el operador.
"""
from __future__ import annotations

import os
import uuid
from typing import Dict, Optional

from ... import store
from . import projects

NONE, HIDDEN, REVEALED = "NONE", "HIDDEN_FROM_ENGINE", "REVEALED"
GT_EXT = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
          ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _row(project_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM recon_ground_truth WHERE project_id=?", (project_id,))
    return dict(r) if r else None


def exists(project_id: str) -> bool:
    return _row(project_id) is not None


def matches_sha(project_id: str, sha: str) -> bool:
    """Si un input candidato es byte a byte el plano real. Sólo responde sí o no."""
    r = _row(project_id)
    return bool(r and r["sha256"] == sha)


def upload(project_id: str, file_storage, author: Optional[str]) -> None:
    p = projects.get(project_id)
    if p is None:
        raise projects.ReconError("Proyecto inexistente.")
    if p["gt_state"] == REVEALED:
        raise projects.ReconError("El plano real ya se reveló: no se reemplaza.")
    original = (file_storage.filename or "plano").strip()
    ext = os.path.splitext(original)[1].lower()
    if ext not in GT_EXT:
        raise projects.ReconError(f"El plano real tiene que ser PDF, PNG, JPG o WebP; "
                                  f"llegó {ext or '(sin extensión)'}.")
    d = store.recon_gt_dir(project_id)
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, uuid.uuid4().hex + ext)
    file_storage.save(dest)
    size = os.path.getsize(dest)
    if size > projects.lab_assets.MAX_MB * 1_000_000:
        os.remove(dest)
        raise projects.ReconError(f"El plano pesa {size / 1e6:.1f} MB; el máximo es "
                                  f"{projects.lab_assets.MAX_MB} MB.")
    if size == 0 or not projects._sniff(dest, ext):           # noqa: SLF001 — misma regla
        os.remove(dest)
        raise projects.ReconError("El contenido del plano no coincide con su extensión.")
    mime = GT_EXT[ext]
    if ext == ".webp":
        nuevo = projects._webp_to_png(dest)                   # noqa: SLF001
        if nuevo is None:
            os.remove(dest)
            raise projects.ReconError("No se pudo leer el WebP del plano.")
        dest, mime, size = nuevo, "image/png", os.path.getsize(nuevo)
    sha = projects._sha(dest)                                 # noqa: SLF001
    # Un input retirado sigue citado por las corridas que lo usaron —y por sus hijas futuras—:
    # si ya lo vio un motor, no puede ser el plano real ciego de este proyecto.
    for a in store.q("SELECT asset_id, retired_at FROM recon_assets WHERE project_id=? "
                     "AND sha256=?", (project_id, sha)):
        if a["retired_at"] is None:
            os.remove(dest)
            raise projects.ReconError("Ese archivo ya está cargado como input del motor. El plano "
                                      "real no puede ser a la vez un input: retira ese input "
                                      "primero.")
        if projects.used_by_a_run(project_id, a["asset_id"]):
            os.remove(dest)
            raise projects.ReconError("Ese archivo ya lo recibió un motor en una corrida de este "
                                      "proyecto: no puede ser su plano real ciego. Crea un "
                                      "proyecto nuevo sin esa foto y súbelo ahí.")
    anterior = _row(project_id)
    ahora = store.now()
    if anterior:
        store.ex("UPDATE recon_ground_truth SET original_filename=?, stored_name=?, mime_type=?, "
                 "size_bytes=?, sha256=?, preview_name=NULL, uploaded_by=?, uploaded_at=? "
                 "WHERE project_id=?",
                 (original[:255], os.path.basename(dest), mime, size, sha, author, ahora,
                  project_id))
        viejo = os.path.join(d, anterior["stored_name"])
        if os.path.exists(viejo):
            os.remove(viejo)
    else:
        store.ex("INSERT INTO recon_ground_truth(project_id, original_filename, stored_name, "
                 "mime_type, size_bytes, sha256, uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?)",
                 (project_id, original[:255], os.path.basename(dest), mime, size, sha, author,
                  ahora))
    store.ex("UPDATE recon_projects SET gt_state=?, updated_at=? WHERE project_id=?",
             (HIDDEN, ahora, project_id))
    # la bitácora no guarda ni el nombre ni el hash: se lee antes del reveal
    projects.log(project_id, "GT_REPLACED" if anterior else "GT_UPLOADED", {}, author=author)


def _preview_pdf(src: str, d: str) -> Optional[str]:
    """Primera página del PDF a PNG. Se genera recién al revelar: antes no hay nada que mirar."""
    try:
        import pymupdf                                        # noqa: PLC0415
        doc = pymupdf.open(src)
        if doc.page_count == 0:
            return None
        page = doc[0]
        zoom = min(3.0, 2200 / max(page.rect.width, page.rect.height))
        nombre = uuid.uuid4().hex + ".png"
        page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(os.path.join(d, nombre))
        return nombre
    except Exception:                                         # noqa: BLE001
        return None


def reveal(project_id: str, author: Optional[str]) -> None:
    p = projects.get(project_id)
    if p is None:
        raise projects.ReconError("Proyecto inexistente.")
    if p["gt_state"] == REVEALED:
        return
    r = _row(project_id)
    if r is None or p["gt_state"] != HIDDEN:
        raise projects.ReconError("No hay un plano real cargado que revelar.")
    ahora = store.now()
    if r["mime_type"] == "application/pdf" and not r["preview_name"]:
        d = store.recon_gt_dir(project_id)
        prev = _preview_pdf(os.path.join(d, r["stored_name"]), d)
        if prev:
            store.ex("UPDATE recon_ground_truth SET preview_name=? WHERE project_id=?",
                     (prev, project_id))
    store.ex("UPDATE recon_projects SET gt_state=?, revealed_at=?, revealed_by=?, updated_at=? "
             "WHERE project_id=?", (REVEALED, ahora, author, ahora, project_id))
    projects.log(project_id, "GT_REVEALED", {}, author=author)


def revealed_info(project_id: str) -> Optional[Dict]:
    """Los datos del plano real, SÓLO si ya se reveló. Antes, None: la UI no tiene qué mostrar."""
    p = projects.get(project_id)
    if p is None or p["gt_state"] != REVEALED:
        return None
    return _row(project_id)


def serving_path(project_id: str) -> Optional[Dict]:
    """Ruta y tipo para servir el plano real, o None si todavía está oculto."""
    r = revealed_info(project_id)
    if r is None:
        return None
    d = store.recon_gt_dir(project_id)
    if r["preview_name"]:
        return {"path": os.path.join(d, r["preview_name"]), "mime": "image/png"}
    if r["mime_type"].startswith("image/"):
        return {"path": os.path.join(d, r["stored_name"]), "mime": r["mime_type"]}
    return {"path": os.path.join(d, r["stored_name"]), "mime": r["mime_type"]}
