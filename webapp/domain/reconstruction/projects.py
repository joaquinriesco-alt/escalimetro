"""E37 §3 — proyectos de reconstrucción: inputs, datos declarados, cierre y bitácora.

Un proyecto NO es una propiedad del piloto: vive en sus propias tablas (`recon_*`) y en su propia
carpeta, para que nada de lo que se prueba acá cambie los conteos de E36 ni la portada del LAB.

Los inputs se validan como en el resto de la app —extensión permitida, contenido que coincide con
la extensión, nombre del usuario que nunca llega al disco— y se agregan dos reglas propias:

* **una foto idéntica al ground truth no entra.** Si el operador sube el plano real como foto, el
  experimento deja de ser ciego sin que nadie lo note. Se compara por sha256 en los dos sentidos;
* **una foto que PARECE un plano se marca**, con el mismo clasificador que usa el ingest de avisos.
  Es un aviso, no un filtro: el operador decide si la retira.

Los inputs se RETIRAN, no se borran: una corrida vieja los cita por id y sha256, y tiene que poder
reabrirse sabiendo exactamente con qué se hizo.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ... import store
from .. import assets as lab_assets

PHOTO, VIDEO, DOCUMENT = "PHOTO", "VIDEO", "DOCUMENT"
KINDS = (PHOTO, VIDEO, DOCUMENT)
KIND_LABEL = {PHOTO: "foto", VIDEO: "video", DOCUMENT: "documento"}

PHOTO_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
             ".webp": "image/webp"}
VIDEO_EXT = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/x-m4v",
             ".webm": "video/webm"}
DOC_EXT = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
           ".json": "application/json"}
_EXT = {PHOTO: PHOTO_EXT, VIDEO: VIDEO_EXT, DOCUMENT: DOC_EXT}
_UNSUPPORTED_HINT = {".heic": "HEIC no se lee todavía: exporta la foto a JPG.",
                     ".heif": "HEIF no se lee todavía: exporta la foto a JPG."}

#: Lo que el operador puede declarar. Clave, rótulo, tipo. Son los mismos hechos que el ingest de
#: avisos ya reconoce (superficies, dormitorios, baños), más niveles, contexto y descripción.
DECLARED_FIELDS: Tuple[Tuple[str, str, type], ...] = (
    ("total_area_m2", "Superficie total (m²)", float),
    ("usable_area_m2", "Superficie útil (m²)", float),
    ("bedrooms", "Dormitorios", int),
    ("bathrooms", "Baños", int),
    ("levels", "Niveles", int),
    ("address_context", "Dirección o contexto", str),
    ("description", "Descripción", str),
)

JUDGMENT_SCALE = ("BIEN", "PARCIAL", "MAL")
JUDGMENT_LABEL = {"BIEN": "Bien", "PARCIAL": "Parcial", "MAL": "Mal"}
CAD_ANSWERS = ("SI", "NO")

MAX_NAME = 120
MAX_TEXT = 4000


class ReconError(ValueError):
    """Algo que el operador puede entender y corregir."""


def max_video_mb() -> int:
    return int(os.environ.get("ESCALIMETRO_RECON_MAX_VIDEO_MB", "500"))


def _id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:12]


def inputs_dir(project_id: str) -> str:
    return os.path.join(store.recon_dir(project_id), "inputs")


def runs_dir(project_id: str, run_id: str) -> str:
    return os.path.join(store.recon_dir(project_id), "runs", run_id)


# ---------------------------------------------------------------------------------------------
# bitácora
# ---------------------------------------------------------------------------------------------
def log(project_id: str, kind: str, detail: Optional[Dict] = None, *, run_id: Optional[str] = None,
        author: Optional[str] = None) -> None:
    store.ex("INSERT INTO recon_events(project_id, kind, run_id, detail, author, created_at) "
             "VALUES (?,?,?,?,?,?)",
             (project_id, kind, run_id, json.dumps(detail or {}, ensure_ascii=False), author,
              store.now()))


def events(project_id: str, limit: int = 200) -> List[Dict]:
    return [dict(r) | {"detail": store.js(r["detail"], {})} for r in store.q(
        "SELECT * FROM recon_events WHERE project_id=? ORDER BY id DESC LIMIT ?",
        (project_id, limit))]


# ---------------------------------------------------------------------------------------------
# datos declarados
# ---------------------------------------------------------------------------------------------
def parse_declared(form) -> Dict[str, Any]:
    """Lee los datos declarados de un formulario. Vacío es «no declarado», no cero."""
    out: Dict[str, Any] = {}
    errores: List[str] = []
    for key, label, tipo in DECLARED_FIELDS:
        raw = (form.get(key) or "").strip()
        if not raw:
            continue
        if tipo is str:
            out[key] = raw[:MAX_TEXT]
            continue
        try:
            x = float(raw.replace(",", "."))
            if not math.isfinite(x):
                raise ValueError
            v = int(x) if tipo is int else x
        except (ValueError, OverflowError):
            errores.append(f"{label}: «{raw[:30]}» no es un número")
            continue
        if v <= 0:
            errores.append(f"{label}: tiene que ser mayor que cero")
            continue
        out[key] = v
    if errores:
        raise ReconError("; ".join(errores))
    return out


# ---------------------------------------------------------------------------------------------
# proyectos
# ---------------------------------------------------------------------------------------------
def create(name: str, declared: Dict[str, Any], author: Optional[str]) -> str:
    name = (name or "").strip()
    if not name:
        raise ReconError("El proyecto necesita un nombre.")
    pid = _id("rcp_")
    ahora = store.now()
    store.ex("INSERT INTO recon_projects(project_id, name, declared, author, created_at, "
             "updated_at) VALUES (?,?,?,?,?,?)",
             (pid, name[:MAX_NAME], json.dumps(declared, ensure_ascii=False), author, ahora, ahora))
    os.makedirs(inputs_dir(pid), exist_ok=True)
    log(pid, "PROJECT_CREATED", {"declared_fields": sorted(declared)}, author=author)
    return pid


def get(project_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM recon_projects WHERE project_id=?", (project_id,))
    if r is None:
        return None
    return dict(r) | {"declared": store.js(r["declared"], {}) or {}}


def listing() -> List[Dict]:
    filas = []
    for r in store.q("SELECT * FROM recon_projects ORDER BY created_at DESC, project_id"):
        pid = r["project_id"]
        cuenta = {k: store.q1("SELECT COUNT(*) n FROM recon_assets WHERE project_id=? AND kind=? "
                              "AND retired_at IS NULL", (pid, k))["n"] for k in KINDS}
        corridas = store.q1("SELECT COUNT(*) n FROM recon_runs WHERE project_id=?", (pid,))["n"]
        filas.append(dict(r) | {"assets": cuenta, "runs": corridas})
    return filas


def update_declared(project_id: str, declared: Dict[str, Any], author: Optional[str]) -> None:
    store.ex("UPDATE recon_projects SET declared=?, updated_at=? WHERE project_id=?",
             (json.dumps(declared, ensure_ascii=False), store.now(), project_id))
    log(project_id, "DECLARED_UPDATED", {"declared_fields": sorted(declared)}, author=author)


# ---------------------------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------------------------
def _sniff(path: str, ext: str) -> bool:
    with open(path, "rb") as fh:
        head = fh.read(16)
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext in (".mp4", ".mov", ".m4v"):
        return head[4:8] == b"ftyp"                          # ISO-BMFF
    if ext == ".webm":
        return head[:4] == b"\x1a\x45\xdf\xa3"                 # EBML
    if ext == ".pdf":
        return head.startswith(b"%PDF")
    if ext in (".txt", ".md", ".json"):
        try:
            with open(path, "rb") as fh:
                fh.read(1 << 20).decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _webp_to_png(path: str) -> Optional[str]:
    """WebP → PNG, como en el ingest de avisos: el resto de la app y los motores no leen WebP."""
    try:
        import cv2                                            # noqa: PLC0415
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            return None
        nuevo = os.path.splitext(path)[0] + ".png"
        if not cv2.imwrite(nuevo, img):
            return None
        os.remove(path)
        return nuevo
    except Exception:                                         # noqa: BLE001
        return None


def _looks_like_plan(path: str, img=None) -> Tuple[bool, Optional[str]]:
    try:
        from ..potential import classify                     # noqa: PLC0415
        c = classify.classify(path, img=img)
    except Exception:                                         # noqa: BLE001
        return False, None
    if c.get("kind") == classify.FLOORPLAN:
        return True, c.get("why")
    return False, None


def add_asset(project_id: str, file_storage, kind: str) -> Tuple[str, Optional[str]]:
    """Guarda un input y devuelve (asset_id, nota). La nota dice si era repetido o si parece un
    plano. Lanza `ReconError` si el archivo no sirve."""
    if kind not in KINDS:
        raise ReconError(f"tipo de input desconocido: {kind}")
    original = (file_storage.filename or "archivo").strip()
    ext = os.path.splitext(original)[1].lower()
    if ext in _UNSUPPORTED_HINT:
        raise ReconError(_UNSUPPORTED_HINT[ext])
    permitidas = _EXT[kind]
    if ext not in permitidas:
        raise ReconError(f"Formato no aceptado para {KIND_LABEL[kind]}: {ext or '(sin extensión)'}. "
                         f"Sirve: {', '.join(sorted(permitidas))}.")
    d = inputs_dir(project_id)
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, uuid.uuid4().hex + ext)            # el nombre del usuario no llega acá
    file_storage.save(dest)
    size = os.path.getsize(dest)
    tope = max_video_mb() if kind == VIDEO else lab_assets.MAX_MB
    if size > tope * 1_000_000:
        os.remove(dest)
        raise ReconError(f"{original}: pesa {size / 1e6:.1f} MB; el máximo es {tope} MB.")
    if size == 0 or not _sniff(dest, ext):
        os.remove(dest)
        raise ReconError(f"{original}: el contenido no coincide con su extensión.")
    mime = permitidas[ext]
    if ext == ".webp":
        nuevo = _webp_to_png(dest)
        if nuevo is None:
            os.remove(dest)
            raise ReconError(f"{original}: no se pudo leer el WebP.")
        dest, mime, size = nuevo, "image/png", os.path.getsize(nuevo)
    sha = _sha(dest)
    ya = store.q1("SELECT asset_id FROM recon_assets WHERE project_id=? AND sha256=? "
                  "AND retired_at IS NULL", (project_id, sha))
    if ya:
        os.remove(dest)
        return ya["asset_id"], f"{original}: ya estaba cargado; no se duplicó"
    from . import groundtruth                                 # noqa: PLC0415
    if groundtruth.matches_sha(project_id, sha):
        os.remove(dest)
        raise ReconError(f"{original}: es idéntico al ground truth oculto; no puede ser un input.")
    w = h = None
    plano, porque = False, None
    if kind == PHOTO:
        try:
            import cv2                                        # noqa: PLC0415
            img = cv2.imread(dest, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError
            h, w = int(img.shape[0]), int(img.shape[1])
        except Exception:                                     # noqa: BLE001
            os.remove(dest)
            raise ReconError(f"{original}: la imagen no se pudo leer.") from None
        plano, porque = _looks_like_plan(dest, img)           # la misma decodificación, no otra
    aid = _id("rca_")
    orden = store.q1("SELECT COALESCE(MAX(sort_order), 0) + 1 n FROM recon_assets "
                     "WHERE project_id=?", (project_id,))["n"]
    store.ex("INSERT INTO recon_assets(asset_id, project_id, kind, original_filename, stored_name, "
             "mime_type, size_bytes, sha256, width_px, height_px, sort_order, looks_like_plan, "
             "looks_like_plan_why, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (aid, project_id, kind, original[:255], os.path.basename(dest), mime, size, sha, w, h,
              orden, 1 if plano else 0, porque, store.now()))
    nota = (f"{original}: parece un plano ({porque}). Si es el plano real, retira esta foto antes "
            "de generar y súbela como plano real; si una corrida ya la usó, ese proyecto dejó de ser "
            "ciego para ella: crea uno nuevo sin esta foto." if plano else None)
    return aid, nota


def add_many(project_id: str, files, kind: str, author: Optional[str]) -> Tuple[List[str], List[str]]:
    """Carga varios archivos. Un archivo malo no tumba el lote: se junta su error y se sigue."""
    ok, mensajes = [], []
    for f in files:
        if not f or not f.filename:
            continue
        try:
            aid, nota = add_asset(project_id, f, kind)
            ok.append(aid)
            if nota:
                mensajes.append(nota)
        except ReconError as e:
            mensajes.append(str(e))
    if ok:
        log(project_id, "ASSETS_ADDED", {"kind": kind, "n": len(ok)}, author=author)
    return ok, mensajes


def assets_of(project_id: str, kind: Optional[str] = None, *, include_retired: bool = False
              ) -> List[Dict]:
    sql = "SELECT * FROM recon_assets WHERE project_id=?"
    args: List[Any] = [project_id]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if not include_retired:
        sql += " AND retired_at IS NULL"
    return [dict(r) for r in store.q(sql + " ORDER BY sort_order, created_at", tuple(args))]


def get_asset(project_id: str, asset_id: str) -> Optional[Dict]:
    """Por id Y proyecto: un id de otro proyecto no sirve para pedir un archivo."""
    r = store.q1("SELECT * FROM recon_assets WHERE asset_id=? AND project_id=?",
                 (asset_id, project_id))
    return dict(r) if r else None


def asset_path(a: Dict) -> str:
    return os.path.join(inputs_dir(a["project_id"]), a["stored_name"])


def input_allowed(project_id: str, sha: str) -> bool:
    """Si un input se le puede dar a un motor (o mostrar) hoy: no, si es byte a byte el plano real
    oculto. Responde sólo sí o no; quien pregunta no se entera de nada más del plano real."""
    from . import groundtruth                                 # noqa: PLC0415
    p = get(project_id)
    if p is None or p["gt_state"] != groundtruth.HIDDEN:
        return True
    return not groundtruth.matches_sha(project_id, sha)


def used_by_a_run(project_id: str, asset_id: str) -> bool:
    """Si alguna corrida —terminada, en cola o hija futura de una terminada— le MANDA este input a
    un motor. Un documento o un video que el motor no consume queda citado como «no enviado» y
    no cuenta: nunca lo vio."""
    for r in store.q("SELECT inputs FROM recon_runs WHERE project_id=?", (project_id,)):
        snap = store.js(r["inputs"], {}) or {}
        if any(f.get("asset_id") == asset_id for f in snap.get("photos") or []):
            return True
        if any(f.get("asset_id") == asset_id and f.get("sent")
               for f in snap.get("videos") or []):
            return True
    return False


def retire_asset(project_id: str, asset_id: str, author: Optional[str]) -> None:
    a = get_asset(project_id, asset_id)
    if a is None:
        raise ReconError("Ese input no es de este proyecto.")
    if a["retired_at"]:
        return
    store.ex("UPDATE recon_assets SET retired_at=? WHERE asset_id=?", (store.now(), asset_id))
    log(project_id, "ASSET_RETIRED", {"asset_id": asset_id, "kind": a["kind"]}, author=author)


# ---------------------------------------------------------------------------------------------
# cierre del proyecto: el juicio humano que E37 §14 pide medir, sin puntaje compuesto
# ---------------------------------------------------------------------------------------------
def save_judgment(project_id: str, form, author: Optional[str]) -> None:
    from . import runs as recon_runs                          # noqa: PLC0415
    p = get(project_id)
    if p is None:
        raise ReconError("Proyecto inexistente.")
    final = (form.get("final_run_id") or "").strip() or None
    if final:
        r = recon_runs.get_in_project(project_id, final)
        if r is None or r["status"] != "DONE":
            raise ReconError("La corrida final tiene que ser una corrida terminada de este proyecto.")
    minutos = (form.get("human_minutes") or "").strip()
    try:
        minutos_v = float(minutos.replace(",", ".")) if minutos else None
        if minutos_v is not None and not math.isfinite(minutos_v):
            raise ValueError
    except ValueError:
        raise ReconError("Los minutos humanos tienen que ser un número.") from None
    if minutos_v is not None and minutos_v < 0:
        raise ReconError("Los minutos humanos no pueden ser negativos.")
    cad = (form.get("needed_manual_cad") or "").strip() or None
    if cad and cad not in CAD_ANSWERS:
        raise ReconError("¿Hizo falta CAD manual? se responde SI o NO.")
    esperados = (form.get("expected_rooms") or "").strip()
    esperados_v = None
    if not esperados and p["gt_state"] == "HIDDEN_FROM_ENGINE":
        # el campo va deshabilitado mientras el plano real está oculto y el navegador no lo manda:
        # una etiqueta anotada antes de cargarlo se conserva, no se borra en silencio
        previo = current_judgment(project_id)
        esperados_v = previo["expected_rooms"] if previo else None
    if esperados:
        # Con el plano real oculto, anotarlos sería mirarlo antes de tiempo. Sin plano real, son una
        # etiqueta humana (E37 §14: «cuando GT fue revelado o etiquetado»).
        if p["gt_state"] == "HIDDEN_FROM_ENGINE":
            raise ReconError("Con un plano real oculto, los recintos esperados se anotan después "
                             "de revelarlo.")
        try:
            esperados_v = int(esperados)
        except ValueError:
            raise ReconError("Los recintos esperados son un número entero.") from None
        if esperados_v <= 0:
            raise ReconError("Los recintos esperados tienen que ser más que cero.")
    juicios = {}
    for k in ("adjacency", "relative_position", "geometry"):
        v = (form.get(k) or "").strip() or None
        if v and v not in JUDGMENT_SCALE:
            raise ReconError(f"{k}: valor no válido")
        juicios[k] = v
    store.ex("INSERT INTO recon_judgments(project_id, final_run_id, human_minutes, "
             "needed_manual_cad, expected_rooms, adjacency, relative_position, geometry, comment, "
             "gt_state_at_creation, author, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
             (project_id, final, minutos_v, cad, esperados_v, juicios["adjacency"],
              juicios["relative_position"], juicios["geometry"],
              (form.get("comment") or "").strip()[:MAX_TEXT], p["gt_state"], author, store.now()))
    log(project_id, "JUDGMENT_SAVED", {"final_run_id": final}, author=author)


def current_judgment(project_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM recon_judgments WHERE project_id=? ORDER BY id DESC LIMIT 1",
                 (project_id,))
    return dict(r) if r else None


def judgment_history(project_id: str) -> List[Dict]:
    return [dict(r) for r in store.q("SELECT * FROM recon_judgments WHERE project_id=? "
                                     "ORDER BY id DESC", (project_id,))]
