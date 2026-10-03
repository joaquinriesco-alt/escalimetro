"""E44 — campaña de benchmark con propiedades reales: 20 MEJORAR + 20 CREAR.

Esto MIDE; no construye otro motor. Reutiliza lo que existe: MEJORAR pasa por `floorplan`
(`ensure_case` + `publish_commercial_floorplan`, el camino de Plano Corporativo) y CREAR por el
Reconstruction Lab de E37 (proyecto, corridas hijas, plano real oculto, reveal).

Reglas que el código hace cumplir, no que se confían a quien opera:

* una URL no es un caso: sin assets verificados por sha256 el caso es `URL_ONLY` y no suma a ningún N;
* el estado se DERIVA de los artefactos (assets + eventos), nunca se declara;
* los fallos de red/credencial/material quedan como `BLOCKED_*`, jamás como éxito;
* el plano real de CREAR no entra al manifiesto ni a `evidence/`: sólo vive en el lugar oculto de E37;
* los resultados son eventos de sólo inserción (`open(..., "x")`); tras el reveal la corrida ciega
  no se reescribe;
* no hay score compuesto: cada dimensión se guarda y se cuenta por separado.

Estado en `DATA_DIR/e44/` (fuera del repo, que es público). Formato del bundle: `docs/E44_CAMPAIGN.md`.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from . import store

IMPROVE, CREATE = "IMPROVE", "CREATE"
TRACKS = (IMPROVE, CREATE)
TARGET = 20

# estados derivados
URL_ONLY, CAPTURED, EXECUTED, COMPLETED = "URL_ONLY", "CAPTURED", "EXECUTED", "COMPLETED"
BLOCKED_CRED, BLOCKED_MATERIAL, EXCLUDED = ("BLOCKED_MISSING_CREDENTIAL", "BLOCKED_NO_MATERIAL",
                                            "EXCLUDED")

ROLE_PLAN, ROLE_PHOTO, ROLE_GT = "published_plan", "photo", "ground_truth_plan"
RATINGS = ("EXCELENTE", "BUENO", "MALO", "PESIMO")
IMPROVE_ERRORS = ("ESCALA", "PERIMETRO", "NUCLEO", "ACCESO", "PILARES", "FACHADA_LUZ", "OTRO")
LEVEL = ("OK", "PARCIAL", "MAL", "NO_EVALUADO")
CREATE_DIMS = ("inventario_recintos", "adyacencias", "posiciones_relativas", "forma_global",
               "proporciones_areas", "puertas_conexiones")
CREATE_LEVEL = ("BIEN", "PARCIAL", "MAL", "NO_COMPARABLE")
PUBLISHABILITY = ("ALTA", "MEDIA", "BAJA", "NO_EVALUADO")
#: Sólo se acepta lo que cae en la comercialización de oficinas (North Star vigente, E44 §A.4).
PROPERTY_TYPES = ("OFFICE", "OFFICE_FLOOR", "COMMERCIAL_UNIT")
#: E45 — casos cargados a mano desde la web piloto (sin bundle, y con enlace de origen opcional).
WEB_UPLOAD = "WEB_UPLOAD"
#: Marca de las evaluaciones de la web piloto: resultado y UX/UI por separado. No traen las
#: dimensiones de E44 y no se inventan: quedan ausentes, no «NO_EVALUADO» disfrazado de dato.
PILOT_SCHEMA = "e45_pilot_v1"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){9,}(?!\d)")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^e44-(?:imp|cre)-[0-9a-f]{10}$")


class CampaignError(ValueError):
    pass


# --------------------------------------------------------------------------------------------
# rutas
# --------------------------------------------------------------------------------------------
def root() -> str:
    return os.path.join(store.DATA_DIR, "e44")


def _manifest_path() -> str:
    return os.path.join(root(), "manifest.json")


def case_dir(case_id: str) -> str:
    if not _ID.match(case_id or ""):
        raise CampaignError("case_id inválido")
    return os.path.join(root(), "cases", case_id)


def _results_dir(case_id: str) -> str:
    return os.path.join(case_dir(case_id), "results")


# --------------------------------------------------------------------------------------------
# manifiesto
# --------------------------------------------------------------------------------------------
def load() -> Dict[str, Any]:
    try:
        with open(_manifest_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {"version": "e44_manifest_v1", "cases": []}


def _save(m: Dict[str, Any]) -> None:
    os.makedirs(root(), exist_ok=True)
    tmp = _manifest_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, _manifest_path())


def canonical_url(url: str) -> str:
    """Clave de duplicados: sin esquema, `www.`, query, fragmento ni barra final."""
    s = urlsplit((url or "").strip().lower())
    host = s.netloc[4:] if s.netloc.startswith("www.") else s.netloc
    return f"{host}{s.path.rstrip('/')}"


def property_key(case: Dict[str, Any]) -> str:
    """Identidad de la propiedad/unidad: la declarada, o la URL canónica de la primera fuente."""
    return (case.get("property_key") or "").strip().lower() or canonical_url(
        (case.get("source_urls") or [""])[0])


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _no_pii(*valores: Any) -> None:
    for v in valores:
        t = json.dumps(v, ensure_ascii=False)
        if _EMAIL.search(t) or _PHONE.search(t):
            raise CampaignError("el caso contiene un email o teléfono: el benchmark estudia "
                                "propiedades, no personas")


def _validate_entry(c: Dict[str, Any]) -> None:
    if c.get("track") not in TRACKS:
        raise CampaignError("track debe ser IMPROVE o CREATE")
    urls = c.get("source_urls")
    if urls or c.get("origin") != WEB_UPLOAD:        # una carga web puede no tener enlace de origen
        if not urls or not all(isinstance(u, str) and u.startswith("http") for u in urls):
            raise CampaignError("source_urls: al menos una URL http(s)")
    for k in ("captured_on", "source"):
        if not c.get(k):
            raise CampaignError(f"falta {k} (provenance)")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", c["captured_on"]):
        raise CampaignError("captured_on debe ser AAAA-MM-DD")
    if c.get("property_type") not in PROPERTY_TYPES:
        raise CampaignError(f"property_type fuera de la población objetivo: {PROPERTY_TYPES}")
    m2 = c.get("published_m2")
    if m2 is not None and not (isinstance(m2, (int, float)) and m2 > 0):
        raise CampaignError("published_m2 debe ser un número > 0 o ausente")
    _no_pii(c.get("notes"), c.get("declared"), c.get("source"))


def _roles(track: str) -> Tuple[str, ...]:
    return (ROLE_PLAN,) if track == IMPROVE else (ROLE_PHOTO, ROLE_GT)


def _find_duplicate(m: Dict[str, Any], case: Dict[str, Any], shas: List[str]) -> Optional[str]:
    key = property_key(case)
    for o in m["cases"]:
        if bool(o.get("demo")) != bool(case.get("demo")):
            continue                              # una demo nunca bloquea (ni es bloqueada por) un caso real
        mismo = property_key(o) == key or bool(set(shas) & set(o.get("asset_shas", [])))
        if not mismo:
            continue
        if o["track"] == case["track"]:
            return f"duplicado dentro de la pista {o['track']}: {o['case_id']}"
        if not (case.get("both_tracks_reason") and o.get("both_tracks_reason")):
            return (f"la misma propiedad ya está en la pista {o['track']} ({o['case_id']}); "
                    "usarla en ambas exige `both_tracks_reason` en los dos casos")
    return None


# --------------------------------------------------------------------------------------------
# importación de un bundle capturado FUERA del ejecutor (sin red)
# --------------------------------------------------------------------------------------------
class _Upload:
    """Lo mínimo de un FileStorage para pasar por las validaciones de E37."""

    def __init__(self, path: str, filename: str):
        self._p, self.filename = path, filename

    def save(self, dest: str) -> None:
        shutil.copyfile(self._p, dest)


def import_bundle(bundle_dir: str, author: str = "e44-importer") -> Dict[str, List[Dict[str, str]]]:
    """Importa `bundle.json` + sus archivos. Cada caso se acepta o se rechaza POR SEPARADO y con
    motivo; nada se corrige en silencio. Devuelve {accepted, rejected}."""
    with open(os.path.join(bundle_dir, "bundle.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    out: Dict[str, List[Dict[str, str]]] = {"accepted": [], "rejected": []}
    for raw in spec.get("cases", []):
        label = (raw.get("source_urls") or ["?"])[0]
        try:
            cid = _import_case(bundle_dir, raw, author)
            out["accepted"].append({"case_id": cid, "source": label})
        except CampaignError as e:
            out["rejected"].append({"source": label, "reason": str(e)})
    return out


def _import_case(bundle_dir: str, raw: Dict[str, Any], author: str) -> str:
    _validate_entry(raw)
    track = raw["track"]
    specs = raw.get("assets") or []
    ok_roles = _roles(track)
    for a in specs:
        if a.get("role") not in ok_roles:
            raise CampaignError(f"rol {a.get('role')!r} no válido en {track}")
        if not _SHA.match(a.get("sha256", "")):
            raise CampaignError("cada asset declara su sha256")
        if not a.get("origin_url"):
            raise CampaignError("cada asset declara origin_url (provenance)")
    roles = [a["role"] for a in specs]
    if track == IMPROVE and roles.count(ROLE_PLAN) != 1:
        raise CampaignError("MEJORAR: exactamente un plano publicado")
    if track == CREATE and (not roles.count(ROLE_PHOTO) or roles.count(ROLE_GT) != 1):
        raise CampaignError("CREAR: fotos + exactamente un plano real (ground truth)")
    files: List[Tuple[Dict[str, Any], str]] = []
    for a in specs:
        rel = a.get("file", "")
        p = os.path.realpath(os.path.join(bundle_dir, rel))
        if not p.startswith(os.path.realpath(bundle_dir) + os.sep) or not os.path.isfile(p):
            raise CampaignError(f"falta el archivo {rel!r} del bundle")
        if _sha_file(p) != a["sha256"]:
            raise CampaignError(f"{rel}: el sha256 no coincide (archivo alterado o mal capturado)")
        files.append((a, p))
    gt_sha = next((a["sha256"] for a in specs if a["role"] == ROLE_GT), None)
    if gt_sha and any(a["sha256"] == gt_sha for a in specs if a["role"] != ROLE_GT):
        raise CampaignError("el plano real es byte a byte uno de los inputs: no es ciego")
    inputs = [a for a in specs if a["role"] != ROLE_GT]
    m = load()
    dup = _find_duplicate(m, raw, [a["sha256"] for a in inputs])
    if dup:
        raise CampaignError(dup)
    cid = "e44-%s-%s" % ("imp" if track == IMPROVE else "cre",
                         hashlib.sha256(json.dumps(
                             [property_key(raw), track], sort_keys=True).encode()).hexdigest()[:10])
    case: Dict[str, Any] = {
        "case_id": cid, "track": track, "source_urls": list(raw.get("source_urls") or []),
        "captured_on": raw["captured_on"], "source": raw["source"],
        "origin": raw.get("origin") or "BUNDLE", "demo": bool(raw.get("demo")),
        "property_type": raw["property_type"], "published_m2": raw.get("published_m2"),
        "declared": raw.get("declared") or {}, "notes": raw.get("notes", ""),
        "property_key": property_key(raw), "both_tracks_reason": raw.get("both_tracks_reason"),
        "excluded_reason": None,
        # sha de los inputs: sirve para duplicados. El del plano real NO se guarda acá.
        "asset_shas": [a["sha256"] for a in inputs],
        "assets": [{"file": os.path.basename(a["file"]), "role": a["role"],
                    "sha256": a["sha256"], "origin_url": a["origin_url"]} for a in inputs],
        "has_ground_truth": track == CREATE,
    }
    ev = os.path.join(case_dir(cid), "evidence")
    os.makedirs(ev, exist_ok=True)
    try:
        for a, p in files:
            if a["role"] == ROLE_GT:
                continue
            dest = os.path.join(ev, os.path.basename(a["file"]))
            shutil.copyfile(p, dest)
            os.chmod(dest, 0o444)                  # el original capturado es evidencia inmutable
        if track == CREATE:
            gt = next(p for a, p in files if a["role"] == ROLE_GT)
            case["recon_project_id"] = _prepare_create(case, ev, gt, author)
    except Exception:
        # un rechazo a mitad de camino no deja evidencia huérfana: reintentar el mismo material
        # chocaría con los archivos de sólo lectura y el caso nunca entraría
        shutil.rmtree(case_dir(cid), ignore_errors=True)
        raise
    m["cases"].append(case)
    _save(m)
    return cid


def _prepare_create(case: Dict[str, Any], ev: str, gt_path: str, author: str) -> str:
    """Proyecto E37 con las fotos como únicos inputs y el plano real en la zona oculta."""
    from .domain.reconstruction import groundtruth, projects      # noqa: PLC0415
    declared = {k: v for k, v in (case["declared"] or {}).items()
                if k in {f[0] for f in projects.DECLARED_FIELDS}}
    if case.get("published_m2") and "total_area_m2" not in declared:
        declared["total_area_m2"] = case["published_m2"]
    pid = projects.create("E44 " + case["case_id"], declared, author)
    try:
        for a in case["assets"]:
            projects.add_asset(pid, _Upload(os.path.join(ev, a["file"]), a["file"]),
                               projects.PHOTO)
        groundtruth.upload(pid, _Upload(gt_path, "plano_real" + os.path.splitext(gt_path)[1]),
                           author)
    except projects.ReconError as e:
        raise CampaignError(f"E37 rechazó el material: {e}") from e
    return pid


PLAN_EXTS = (".pdf", ".png", ".jpg", ".jpeg")
PHOTO_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_URL_RE = re.compile(r"^https?://\S+$", re.I)


def import_upload(track: str, files: List[Tuple[str, bytes]], *, reference: str = "",
                  published_m2: Optional[float] = None,
                  ground_truth: Optional[Tuple[str, bytes]] = None,
                  author: str = "web-piloto", demo: bool = False) -> str:
    """E45 — un caso cargado desde la web, por el MISMO camino de validación que un bundle
    (`_import_case`): sha256, provenance, PII, duplicados y, en CREAR, plano real sólo en la zona
    oculta de E37. No hay segundo sistema de campaña: esto sólo arma el bundle en un directorio
    temporal. Los nombres que puso el usuario no se conservan (`plano.ext`, `foto_NN.ext`): ni el
    nombre de una foto ni el del plano real pueden delatar nada al motor ni a la pantalla.

    `reference`: un enlace (queda como fuente) o un texto (queda como descripción declarada)."""
    from . import intake                                           # noqa: PLC0415
    if track not in TRACKS:
        raise CampaignError("track debe ser IMPROVE o CREATE")
    files = [(n, b) for n, b in files if n and b]
    if track == IMPROVE:
        if len(files) != 1:
            raise CampaignError("MEJORAR: sube un solo plano.")
        if ground_truth:
            raise CampaignError("MEJORAR no lleva plano real aparte.")
        oks = PLAN_EXTS
    else:
        if not files:
            raise CampaignError("CREAR: sube al menos una foto de la propiedad.")
        if not ground_truth or not ground_truth[1]:
            raise CampaignError("CREAR: falta el plano real (modo piloto), para comparar al final.")
        oks = PHOTO_EXTS
    revisar = [(n, oks) for n, _b in files] + ([(ground_truth[0], PLAN_EXTS)] if ground_truth else [])
    for n, permitidas in revisar:
        if os.path.splitext(n)[1].lower() not in permitidas:
            raise CampaignError(f"Formato no aceptado: {os.path.basename(n)[:60]}. "
                                + ("Fotos: JPG, PNG o WEBP; plano real: PDF, JPG o PNG."
                                   if track == CREATE else "Sólo PDF, JPG o PNG."))
    reference = (reference or "").strip()
    link = reference if _URL_RE.match(reference) else ""
    text = "" if link else reference[:2000]
    specs: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(dir=_tmp_root()) as tmp:
        def put(name: str, blob: bytes, role: str) -> None:
            with open(os.path.join(tmp, name), "wb") as fh:
                fh.write(blob)
            specs.append({"file": name, "role": role, "sha256": hashlib.sha256(blob).hexdigest(),
                          "origin_url": "upload://web/" + name})
        if track == IMPROVE:
            n, b = files[0]
            ext = os.path.splitext(n)[1].lower()
            put("plano" + ext, b, ROLE_PLAN)
            if len(b) > intake.MAX_UPLOAD_MB * 1024 * 1024:
                raise CampaignError(f"El archivo pesa más de {intake.MAX_UPLOAD_MB} MB.")
            if not intake.sniff_ok(os.path.join(tmp, "plano" + ext), ext):
                raise CampaignError("El contenido del archivo no coincide con su formato.")
        else:
            for i, (n, b) in enumerate(files, 1):
                put("foto_%02d%s" % (i, os.path.splitext(n)[1].lower()), b, ROLE_PHOTO)
            gn, gb = ground_truth
            put("plano_real" + os.path.splitext(gn)[1].lower(), gb, ROLE_GT)
        shas = sorted(a["sha256"] for a in specs if a["role"] != ROLE_GT)
        key = (canonical_url(link) if link
               else "upload:" + hashlib.sha256("|".join(shas).encode()).hexdigest()[:16])
        if demo:
            key = "demo:" + key           # el id del caso sale de esta clave: una demo no pisa a un real
        raw: Dict[str, Any] = {
            "track": track, "origin": WEB_UPLOAD, "demo": demo, "source_urls": [link] if link else [],
            "captured_on": store.now()[:10], "source": "carga web del piloto (E45)",
            "property_type": "OFFICE", "published_m2": published_m2, "property_key": key,
            "declared": {"description": text} if text else {}, "notes": "", "assets": specs}
        with open(os.path.join(tmp, "bundle.json"), "w", encoding="utf-8") as fh:
            json.dump({"cases": [raw]}, fh)
        return _import_case(tmp, raw, author)


def _tmp_root() -> str:
    os.makedirs(root(), exist_ok=True)
    return root()


def exclude(case_id: str, reason: str) -> None:
    m = load()
    c = next((c for c in m["cases"] if c["case_id"] == case_id), None)
    if c is None or not reason.strip():
        raise CampaignError("caso inexistente o sin motivo")
    c["excluded_reason"] = reason.strip()
    _save(m)


def register_url_only(raw: Dict[str, Any]) -> str:
    """Anota una URL encontrada sin material. Existe para que NO infle ningún N: queda URL_ONLY."""
    _validate_entry({**raw, "assets": None})
    m = load()
    if _find_duplicate(m, raw, []):
        raise CampaignError("duplicado")
    cid = "e44-%s-%s" % ("imp" if raw["track"] == IMPROVE else "cre", hashlib.sha256(
        json.dumps([property_key(raw), raw["track"]], sort_keys=True).encode()).hexdigest()[:10])
    m["cases"].append({
        "case_id": cid, "track": raw["track"], "source_urls": raw["source_urls"],
        "captured_on": raw["captured_on"], "source": raw["source"],
        "property_type": raw["property_type"], "published_m2": raw.get("published_m2"),
        "declared": {}, "notes": raw.get("notes", ""), "property_key": property_key(raw),
        "both_tracks_reason": raw.get("both_tracks_reason"), "excluded_reason": None,
        "asset_shas": [], "assets": [], "has_ground_truth": False})
    _save(m)
    return cid


# --------------------------------------------------------------------------------------------
# resultados: eventos de sólo inserción
# --------------------------------------------------------------------------------------------
SINGLETONS = ("pipeline", "closure", "reveal")


def events(case_id: str) -> List[Dict[str, Any]]:
    d = _results_dir(case_id)
    if not os.path.isdir(d):
        return []
    out = []
    for n in sorted(os.listdir(d)):
        with open(os.path.join(d, n), encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def _of(case_id: str, kind: str) -> List[Dict[str, Any]]:
    return [e for e in events(case_id) if e["kind"] == kind]


def record(case_id: str, kind: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Agrega un evento. Nunca reescribe: los singletons no se repiten y el orden del
    experimento ciego se hace cumplir (cierre antes de reveal, reveal antes de evaluar)."""
    case = get(case_id)
    if case is None:
        raise CampaignError("caso inexistente")
    if case["excluded_reason"]:
        raise CampaignError("caso excluido")
    if status(case) == URL_ONLY:
        raise CampaignError("una URL sin assets verificados no se ejecuta ni se evalúa")
    if kind in SINGLETONS and _of(case_id, kind):
        raise CampaignError(f"{kind} ya fue registrado: es inmutable")
    if case["track"] == CREATE:
        if kind == "pipeline" and _of(case_id, "closure"):
            raise CampaignError("la reconstrucción ciega ya está cerrada")
        if kind == "closure" and not _of(case_id, "pipeline"):
            raise CampaignError("no hay corrida que cerrar")
        if kind == "reveal" and not _of(case_id, "closure"):
            raise CampaignError("el reveal exige cerrar antes la reconstrucción ciega")
        if kind == "evaluation" and not _of(case_id, "reveal"):
            raise CampaignError("la comparación con el plano real exige el reveal")
    elif kind in ("closure", "reveal"):
        raise CampaignError(f"{kind} sólo existe en CREAR")
    if kind == "evaluation" and not _of(case_id, "pipeline") and not _of(case_id, "blocked"):
        raise CampaignError("no hay ejecución que evaluar")
    _check_payload(case["track"], kind, data)
    d = _results_dir(case_id)
    os.makedirs(d, exist_ok=True)
    n = len(os.listdir(d)) + 1
    ev = {"seq": n, "kind": kind, "at": store.now(), "data": data}
    with open(os.path.join(d, f"{n:03d}_{kind}.json"), "x", encoding="utf-8") as fh:
        json.dump(ev, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return ev


def _enum(v: Any, opts: Tuple[str, ...], name: str) -> None:
    if v not in opts:
        raise CampaignError(f"{name}: {v!r} no está en {opts}")


#: sólo texto libre: los hashes y costos de una corrida son largos y numéricos, y no son personas
_FREE_TEXT = ("comment", "prompt", "detail", "error", "uncertainties", "dominant_errors", "main_failure",
              "extra_step_comment", "missing_comment")


def _bool(d: Dict[str, Any], k: str) -> None:
    if not isinstance(d.get(k), bool):
        raise CampaignError(f"{k} debe ser sí o no")


def _text(d: Dict[str, Any], k: str) -> None:
    if d.get(k) is not None and (not isinstance(d[k], str) or len(d[k]) > 2000):
        raise CampaignError(f"{k}: texto de hasta 2000 caracteres")


def _check_payload(track: str, kind: str, d: Dict[str, Any]) -> None:
    _no_pii({k: d[k] for k in _FREE_TEXT if k in d})
    if kind == "evaluation" and d.get("schema") == PILOT_SCHEMA:
        # E45: el juicio sobre el PLANO, sin mezclar la experiencia (esa va en `ux_evaluation`)
        _enum(d.get("rating"), RATINGS, "rating")
        _bool(d, "would_publish")
        _bool(d, "needed_human_correction")
        _text(d, "comment")
        m = d.get("human_minutes")
        if m is not None and not (isinstance(m, (int, float)) and not isinstance(m, bool) and m >= 0):
            raise CampaignError("human_minutes: un número >= 0 o ausente")
    elif kind == "ux_evaluation":
        _enum(d.get("rating"), RATINGS, "rating")
        _bool(d, "understood_immediately")
        for k in ("comment", "extra_step_comment", "missing_comment"):
            _text(d, k)
    elif kind == "rating":
        _enum(d.get("rating"), RATINGS, "rating")
    elif kind == "blocked":
        _enum(d.get("status"), (BLOCKED_CRED, BLOCKED_MATERIAL), "status")
    elif kind == "evaluation" and track == IMPROVE:
        for k in ("reached_output", "needs_cad"):
            if not isinstance(d.get(k), bool):
                raise CampaignError(f"{k} debe ser true/false")
        for e in d.get("errors", []):
            _enum(e, IMPROVE_ERRORS, "errors")
        for k in ("fidelity", "legibility"):
            _enum(d.get(k), LEVEL, k)
        _enum(d.get("publishability"), PUBLISHABILITY, "publishability")
        if not isinstance(d.get("human_interventions"), int) or d["human_interventions"] < 0:
            raise CampaignError("human_interventions: entero >= 0")
        if d.get("rating") is not None:
            _enum(d["rating"], RATINGS, "rating")
    elif kind == "evaluation":
        for k in CREATE_DIMS:
            _enum(d.get(k), CREATE_LEVEL, k)
        if not isinstance(d.get("needs_cad"), bool):
            raise CampaignError("needs_cad debe ser true/false")
        if d.get("rating") is not None:
            _enum(d["rating"], RATINGS, "rating")
    elif kind == "closure":
        if not d.get("final_run_id"):
            raise CampaignError("closure: falta final_run_id")


def blocked(case_id: str, why: str, detail: str = "") -> None:
    _enum(why, (BLOCKED_CRED, BLOCKED_MATERIAL), "status")
    record(case_id, "blocked", {"status": why, "detail": detail[:300]})


# --------------------------------------------------------------------------------------------
# estado DERIVADO
# --------------------------------------------------------------------------------------------
def get(case_id: str) -> Optional[Dict[str, Any]]:
    return next((c for c in load()["cases"] if c["case_id"] == case_id), None)


def materials_ok(case: Dict[str, Any]) -> bool:
    """Los assets siguen en disco con el sha que se capturó (no se cuenta lo que ya no está)."""
    if not case["assets"]:
        return False
    ev = os.path.join(case_dir(case["case_id"]), "evidence")
    for a in case["assets"]:
        p = os.path.join(ev, a["file"])
        if not os.path.isfile(p) or _sha_file(p) != a["sha256"]:
            return False
    return True


def status(case: Dict[str, Any]) -> str:
    if case.get("excluded_reason"):
        return EXCLUDED
    if not materials_ok(case):
        return URL_ONLY
    cid = case["case_id"]
    ev = {e["kind"] for e in events(cid)}
    if "evaluation" in ev:
        return COMPLETED
    if "pipeline" in ev:
        return EXECUTED
    if "blocked" in ev:
        return _of(cid, "blocked")[-1]["data"]["status"]
    return CAPTURED


def count(track: str, m: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """N por pista. captured ⊇ executed ⊇ completed; URL_ONLY, bloqueados y excluidos no suman.
    Los casos DEMO (E45, sólo para fotografiar la interfaz) no entran en ningún N."""
    cases = [c for c in (m or load())["cases"] if c["track"] == track and not c.get("demo")]
    st = [status(c) for c in cases]
    return {"listed": len(cases),
            "captured": sum(s in (CAPTURED, EXECUTED, COMPLETED, BLOCKED_CRED, BLOCKED_MATERIAL)
                            for s in st),
            "executed": sum(s in (EXECUTED, COMPLETED) for s in st),
            "completed": sum(s == COMPLETED for s in st),
            "blocked": sum(s in (BLOCKED_CRED, BLOCKED_MATERIAL) for s in st),
            "url_only": st.count(URL_ONLY), "excluded": st.count(EXCLUDED)}


# --------------------------------------------------------------------------------------------
# ejecución real (necesita el entorno con DB; en el ejecutor sin red no hay casos que correr)
# --------------------------------------------------------------------------------------------
def run_improve(case_id: str, author: str = "e44") -> Dict[str, Any]:
    """MEJORAR por el camino real: propiedad → plano original → caso del motor → Plano Corporativo.
    No confirma nada ni corrige geometría: si la planta no queda lista, eso es el resultado."""
    case = get(case_id)
    if case is None or case["track"] != IMPROVE or status(case) != CAPTURED:
        raise CampaignError("el caso no está CAPTURED en la pista MEJORAR")
    started = start_improve(case_id)
    info = finish_improve(case_id, give_up_reason=started.get("error") or "la planta no quedó lista")
    return info or {}


def start_improve(case_id: str) -> Dict[str, Any]:
    """Primera mitad de MEJORAR (E45): propiedad → plano original → caso del motor → análisis
    automático de la planta (`ingest.auto_prepare`, lo que hace el LAB sin preguntar nada). Se
    registra UNA vez (`improve_started`); no confirma nada ni toca la geometría. Lo que quede
    pendiente lo resuelve una persona en el LAB, y `finish_improve` lo recoge después."""
    from .domain import assets, entitlements, floorplan, grants, ingest, properties   # noqa: PLC0415
    from werkzeug.datastructures import FileStorage                                   # noqa: PLC0415
    case = get(case_id)
    if case is None or case["track"] != IMPROVE or status(case) != CAPTURED:
        raise CampaignError("el caso no está CAPTURED en la pista MEJORAR")
    prev = _of(case_id, "improve_started")
    if prev:
        return prev[-1]["data"]
    a = case["assets"][0]
    src = os.path.join(case_dir(case_id), "evidence", a["file"])
    pid = properties.create("Plano Corporativo", "OFFICE", reference=case_id,
                            notes="E44 benchmark")
    grants.grant_and_assign(entitlements.default_product(), pid, source="SIMULATED_LAB",
                            note="E44 benchmark")
    with open(src, "rb") as fh:
        assets.save_upload(pid, FileStorage(stream=fh, filename=a["file"]),
                           assets.FLOORPLAN_ORIGINAL)
    info: Dict[str, Any] = {"property_id": pid, "path": "floorplan.ensure_case + ingest.auto_prepare "
                            "+ publish_commercial_floorplan", "error": None}
    try:
        floorplan.ensure_case(pid)
        ingest.auto_prepare(pid)
    except Exception as e:                                    # noqa: BLE001 — se registra, no se oculta
        info["error"] = f"{type(e).__name__}: {e}"[:300]
    record(case_id, "improve_started", info)
    return info


def improve_state(case_id: str) -> Optional[Dict[str, Any]]:
    """Lo que el motor dice HOY de la planta (se relee: una persona pudo confirmarla en el LAB)."""
    from .domain import floorplan                                 # noqa: PLC0415
    st = _of(case_id, "improve_started")
    if not st:
        return None
    t = floorplan.technical_state(st[-1]["data"]["property_id"])
    return {"property_id": st[-1]["data"]["property_id"], "ready": t["ready"],
            "pending": t["pending"], "error": st[-1]["data"].get("error")}


def finish_improve(case_id: str, give_up_reason: Optional[str] = None,
                   retry_prepare: bool = False) -> Optional[Dict[str, Any]]:
    """Segunda mitad: si la planta ya está lista, publica el Plano Corporativo por el camino real
    (`publish_commercial_floorplan`) y registra `pipeline`. Si no está lista devuelve None y no
    registra nada, salvo que se pida `give_up_reason`: entonces queda escrito que NO hubo resultado
    (nunca un éxito, y no se puede reescribir)."""
    from .domain import floorplan, ingest                         # noqa: PLC0415
    st = _of(case_id, "improve_started")
    if not st or _of(case_id, "pipeline"):
        return None
    pid = st[-1]["data"]["property_id"]
    info: Dict[str, Any] = {"property_id": pid, "path": st[-1]["data"]["path"],
                            "error": st[-1]["data"].get("error")}
    out_id = None
    try:
        t = floorplan.technical_state(pid)
        if not t["ready"] and retry_prepare:
            ingest.auto_prepare(pid)
            t = floorplan.technical_state(pid)
        info.update(case_status=t.get("case_status"), ready=t["ready"], pending=t["pending"])
        if t["ready"]:
            out_id = floorplan.publish_commercial_floorplan(pid)
            info["error"] = None
        elif give_up_reason is None:
            return None
    except Exception as e:                                    # noqa: BLE001 — se registra, no se oculta
        info["error"] = f"{type(e).__name__}: {e}"[:300]
        if give_up_reason is None:
            raise CampaignError(info["error"]) from e
    if out_id is None and give_up_reason:
        info["error"] = info["error"] or give_up_reason[:300]
    info["output_asset_id"] = out_id
    info["reached_output"] = out_id is not None
    record(case_id, "pipeline", info)
    return info


def run_create(case_id: str, engine_id: str = "openai_direct", author: str = "e44",
               confirm_paid: bool = False) -> Dict[str, Any]:
    """Primera corrida ciega con un motor real registrado. Sin credencial: BLOCKED, no simulación."""
    from .domain.reconstruction import engines, runs               # noqa: PLC0415
    case = get(case_id)
    if case is None or case["track"] != CREATE or status(case) not in (CAPTURED, BLOCKED_CRED):
        raise CampaignError("el caso no está listo para correr en la pista CREAR")
    rid = _begin_create(case, engine_id, author, confirm_paid)
    if isinstance(rid, dict):
        return rid
    run = runs.execute(rid)
    return _record_run(case_id, run)


def _begin_create(case: Dict[str, Any], engine_id: str, author: str, confirm_paid: bool):
    """Valida el motor y crea la corrida inicial. Devuelve su id, o el dict de bloqueo si falta la
    credencial (queda registrado `BLOCKED_*`, nunca un resultado simulado)."""
    from .domain.reconstruction import engines, runs               # noqa: PLC0415
    case_id = case["case_id"]
    adapter = engines.get(engine_id)
    # el motor fixture no reconstruye nada: sólo sirve para fotografiar la interfaz con casos DEMO
    if adapter is None or (engine_id.startswith("fixture") and not case.get("demo")):
        raise CampaignError("motor no registrado, o fixture (no cuenta para N)")
    disp = adapter.availability()
    if disp.status != engines.AVAILABLE:
        if disp.reason == engines.MISSING_CREDENTIAL:
            if status(case) != BLOCKED_CRED:
                blocked(case_id, BLOCKED_CRED, disp.detail or "")
            return {"status": BLOCKED_CRED, "detail": disp.detail}
        raise CampaignError(f"{adapter.name} no disponible: {disp.reason}")
    return runs.create_initial(case["recon_project_id"], engine_id, author,
                               confirm_paid=confirm_paid)


def start_create(case_id: str, engine_id: str = "openai_direct", author: str = "web-piloto",
                 confirm_paid: bool = False) -> Dict[str, Any]:
    """E45: arranca la primera corrida SIN esperarla (la cola de E37 la ejecuta). Queda
    `create_started`; `settle` registra `pipeline` cuando la corrida termina."""
    from .domain.reconstruction import runs                        # noqa: PLC0415
    case = get(case_id)
    if case is None or case["track"] != CREATE or status(case) not in (CAPTURED, BLOCKED_CRED):
        raise CampaignError("el caso no está listo para correr en la pista CREAR")
    if _of(case_id, "create_started"):
        raise CampaignError("la reconstrucción ya fue lanzada")
    rid = _begin_create(case, engine_id, author, confirm_paid)
    if isinstance(rid, dict):
        return rid
    record(case_id, "create_started", {"run_id": rid})
    runs.enqueue(rid)
    return {"status": "QUEUED", "run_id": rid}


def start_correction(case_id: str, text: str, author: str = "web-piloto",
                     confirm_paid: bool = False) -> Dict[str, Any]:
    """E45: corrección en lenguaje natural = corrida HIJA de E37, sin esperarla. Sólo sobre una
    corrida terminada, sin otra en curso y antes del cierre."""
    from .domain.reconstruction import runs                         # noqa: PLC0415
    case = get(case_id)
    _no_pii(text)                          # antes de crear la corrida: un rechazo no deja una huérfana
    settle(case_id)
    pip = _of(case_id, "pipeline") + _of(case_id, "correction")
    if case is None or not pip or _of(case_id, "closure"):
        raise CampaignError("sin reconstrucción abierta: no hay qué corregir")
    if pending_run(case_id):
        raise CampaignError("hay una reconstrucción en curso: espera a que termine")
    last = last_done_run(case_id)
    if last is None:
        raise CampaignError("ninguna reconstrucción terminó bien: no hay qué corregir")
    rid = runs.create_correction(case["recon_project_id"], last, text, author,
                                 confirm_paid=confirm_paid)
    record(case_id, "correction_started", {"run_id": rid, "prompt": text[:2000]})
    runs.enqueue(rid)
    return {"status": "QUEUED", "run_id": rid}


def last_done_run(case_id: str) -> Optional[str]:
    """La última corrida de la cadena que terminó bien: una corrección fallida no se corrige ni
    se cierra, se vuelve a la anterior."""
    from .domain.reconstruction import runs                         # noqa: PLC0415
    for e in reversed(_of(case_id, "pipeline") + _of(case_id, "correction")):
        r = runs.get(e["data"]["run_id"])
        if r is not None and r["status"] == runs.DONE:
            return r["run_id"]
    return None


def pending_run(case_id: str) -> Optional[Dict[str, Any]]:
    """La corrida lanzada y todavía no asentada en el registro, o None."""
    from .domain.reconstruction import runs                         # noqa: PLC0415
    done = {e["data"].get("run_id") for e in events(case_id) if e["kind"] in ("pipeline", "correction")}
    for e in reversed(events(case_id)):
        if e["kind"] in ("create_started", "correction_started") and e["data"]["run_id"] not in done:
            return runs.get(e["data"]["run_id"])
    return None


def settle(case_id: str) -> None:
    """Asienta en el registro de la campaña las corridas lanzadas por `start_*` que ya terminaron
    (DONE o FAILED). El estado de la campaña se deriva de eventos, no de la cola: esto es lo que
    los convierte en `pipeline`/`correction`. Una corrida en curso no se toca."""
    from .domain.reconstruction import runs                         # noqa: PLC0415
    for e in list(events(case_id)):
        if e["kind"] not in ("create_started", "correction_started"):
            continue
        rid = e["data"]["run_id"]
        if any(x["data"].get("run_id") == rid for x in events(case_id)
               if x["kind"] in ("pipeline", "correction")):
            continue
        run = runs.get(rid)
        if run is None or run["status"] not in (runs.DONE, runs.FAILED):
            continue
        if e["kind"] == "create_started":
            _record_run(case_id, run)
        else:
            n = len(_of(case_id, "correction")) + 1
            record(case_id, "correction", {**_summary_of_run(run), "seq_correction": n,
                                           "prompt": e["data"].get("prompt", "")})


def correct_create(case_id: str, text: str, author: str = "e44",
                   confirm_paid: bool = False) -> Dict[str, Any]:
    """Corrección humana estructurada: corrida HIJA de E37, la madre no se toca. Sólo antes del cierre."""
    from .domain.reconstruction import runs                         # noqa: PLC0415
    case = get(case_id)
    pip = _of(case_id, "pipeline")
    if case is None or not pip or _of(case_id, "closure"):
        raise CampaignError("sin corrida abierta: no hay qué corregir")
    last = pip[-1]["data"]["run_id"]
    rid = runs.create_correction(case["recon_project_id"], last, text, author,
                                 confirm_paid=confirm_paid)
    run = runs.execute(rid)
    d = _summary_of_run(run)
    n = len(_of(case_id, "correction")) + 1
    record(case_id, "correction", {**d, "seq_correction": n, "prompt": text[:2000]})
    return d


def _summary_of_run(run: Dict[str, Any]) -> Dict[str, Any]:
    meta = run.get("engine_meta") or {}
    return {"run_id": run["run_id"], "engine_id": run["engine_id"],
            "engine_version": run["engine_version"], "provider": meta.get("provider"),
            "model": meta.get("model"), "prompt_version": run.get("prompt_version"),
            "prompt_sha256": run.get("prompt_sha256"), "status": run["status"],
            "outcome": run.get("outcome"), "latency_ms": run.get("latency_ms"),
            "cost_usd": run.get("cost_usd"), "cost_basis": run.get("cost_basis"),
            "error": run.get("error"), "output_sha256": run.get("output_sha256")}


def _record_run(case_id: str, run: Dict[str, Any]) -> Dict[str, Any]:
    d = _summary_of_run(run)
    record(case_id, "pipeline", d)
    return d


def close_blind(case_id: str, final_run_id: Optional[str] = None, *, human_minutes: Optional[float]
                = None, uncertainties: Optional[List[str]] = None) -> Dict[str, Any]:
    """Punto de cierre: desde acá la reconstrucción queda fija y puede revelarse el plano real."""
    from .domain.reconstruction import runs                         # noqa: PLC0415
    case = get(case_id)
    if case is None or case["track"] != CREATE:
        raise CampaignError("sólo CREAR tiene cierre")
    chain = _of(case_id, "pipeline") + _of(case_id, "correction")
    if not chain:
        raise CampaignError("no hay corrida que cerrar")
    final = final_run_id or chain[-1]["data"]["run_id"]
    run = runs.get(final)
    if run is None or run["project_id"] != case["recon_project_id"]:
        raise CampaignError("la corrida final no es de este caso")
    audit = blind_audit(case_id)
    if not audit["ok"]:
        raise CampaignError("auditoría de ceguera fallida: " + "; ".join(audit["violations"]))
    ev = record(case_id, "closure", {
        "final_run_id": final, "output_sha256": run.get("output_sha256"),
        "prompts_humanos": runs.prompts_in_lineage(run), "human_minutes": human_minutes,
        "uncertainties": uncertainties or [], "gt_state_at_closure":
        projects_gt_state(case["recon_project_id"]), "blind_audit": audit})
    svg = runs.svg_path(run)
    if svg:                                    # copia congelada para el índice, antes del reveal
        rv = os.path.join(case_dir(case_id), "review")
        os.makedirs(rv, exist_ok=True)
        shutil.copyfile(svg, os.path.join(rv, "reconstruccion_pre_reveal.svg"))
    return ev


def projects_gt_state(project_id: str) -> str:
    from .domain.reconstruction import projects                      # noqa: PLC0415
    return projects.get(project_id)["gt_state"]


def reveal(case_id: str, author: str = "e44") -> Dict[str, Any]:
    from .domain.reconstruction import groundtruth                   # noqa: PLC0415
    case = get(case_id)
    if case is None or case["track"] != CREATE:
        raise CampaignError("sólo CREAR tiene reveal")
    if not _of(case_id, "closure"):
        raise CampaignError("el reveal exige cerrar antes la reconstrucción ciega")
    groundtruth.reveal(case["recon_project_id"], author)
    ev = record(case_id, "reveal", {"project_gt_state": "REVEALED"})
    sp = groundtruth.serving_path(case["recon_project_id"])
    if sp:
        rv = os.path.join(case_dir(case_id), "review")
        os.makedirs(rv, exist_ok=True)
        shutil.copyfile(sp["path"], os.path.join(
            rv, "plano_real_post_reveal" + os.path.splitext(sp["path"])[1]))
    return ev


# --------------------------------------------------------------------------------------------
# prueba de ceguera
# --------------------------------------------------------------------------------------------
def blind_audit(case_id: str) -> Dict[str, Any]:
    """Busca, en TODO lo que un motor o su entrada podrían ver, rastros del plano real: su hash, su
    nombre, su carpeta. Si encuentra uno, la corrida no es ciega."""
    from .domain.reconstruction import projects                      # noqa: PLC0415
    case = get(case_id)
    if case is None or case["track"] != CREATE:
        raise CampaignError("sólo CREAR tiene ceguera que auditar")
    pid = case["recon_project_id"]
    gt = store.q1("SELECT sha256, original_filename, stored_name FROM recon_ground_truth "
                  "WHERE project_id=?", (pid,))
    v: List[str] = []
    if gt is None:
        v.append("el caso no tiene plano real cargado")
        return {"ok": False, "violations": v}
    huellas = {"sha256": gt["sha256"], "nombre": gt["original_filename"],
               "archivo": gt["stored_name"], "carpeta": "reconstruction_gt"}
    visible = [json.dumps(case, ensure_ascii=False)]
    ev = os.path.join(case_dir(case_id), "evidence")
    visible.append(" ".join(sorted(os.listdir(ev))))
    for a in projects.assets_of(pid, include_retired=True):
        visible.append(json.dumps({k: a[k] for k in a.keys()}, default=str))
        if a["sha256"] == gt["sha256"]:
            v.append("un input del motor es byte a byte el plano real")
    for r in store.q("SELECT inputs, params FROM recon_runs WHERE project_id=?", (pid,)):
        visible.append(r["inputs"] + r["params"])
    texto = "\n".join(visible)
    for k, h in huellas.items():
        if h and h in texto:
            v.append(f"rastro del plano real en lo visible al motor ({k})")
    for root_, _d, fs in os.walk(ev):
        for f in fs:
            if _sha_file(os.path.join(root_, f)) == gt["sha256"]:
                v.append("evidence/ contiene el plano real")
    return {"ok": not v, "violations": v}


# --------------------------------------------------------------------------------------------
# resumen e índice de revisión
# --------------------------------------------------------------------------------------------
def _dist(items: List[Optional[str]]) -> Dict[str, int]:
    return {r: sum(1 for i in items if i == r) for r in RATINGS} | {
        "SIN_RATING": sum(1 for i in items if i is None)}


def _rating(cid: str, ev: Dict[str, Any]) -> Optional[str]:
    r = _of(cid, "rating")
    return r[-1]["data"]["rating"] if r else ev.get("rating")


def summary() -> Dict[str, Any]:
    m = load()
    res: Dict[str, Any] = {"tracks": {}, "target": TARGET}
    for t in TRACKS:
        cs = [c for c in m["cases"] if c["track"] == t and not c.get("demo")]
        done = [c for c in cs if status(c) == COMPLETED]
        evs = {c["case_id"]: _of(c["case_id"], "evaluation")[-1]["data"] for c in done}
        errs: Dict[str, int] = {}
        for c in done:
            e = evs[c["case_id"]]
            for x in (e.get("errors") or e.get("dominant_errors") or []):
                errs[x] = errs.get(x, 0) + 1
        mins = []
        for c in done:
            e = evs[c["case_id"]]
            cl = _of(c["case_id"], "closure")
            v = e.get("human_minutes")
            if v is None and cl:
                v = cl[-1]["data"].get("human_minutes")
            if v is not None:
                mins.append(v)
        d: Dict[str, Any] = {
            "counts": count(t, m), "ratings": _dist([_rating(c["case_id"], evs[c["case_id"]])
                                                    for c in done]),
            "human_minutes": {"registered_in": len(mins), "total": sum(mins) if mins else None},
            "error_frequency": errs,
            "excluded": [{"case_id": c["case_id"], "reason": c["excluded_reason"]}
                         for c in cs if c.get("excluded_reason")],
            "blocked": [{"case_id": c["case_id"], "status": status(c)} for c in cs
                        if status(c) in (BLOCKED_CRED, BLOCKED_MATERIAL)]}
        if t == IMPROVE:
            ex = [c for c in cs if status(c) in (EXECUTED, COMPLETED)]
            ok = sum(1 for c in ex if _of(c["case_id"], "pipeline")[0]["data"].get("reached_output"))
            d["pipeline_success"] = {"reached_output": ok, "executed": len(ex)}
            # las evaluaciones de la web piloto (E45) no traen estas dimensiones: no cuentan en ellas
            d["human_interventions"] = sum(evs[c["case_id"]].get("human_interventions") or 0
                                           for c in done)
            d["fidelity"] = {k: sum(1 for e in evs.values() if e.get("fidelity") == k) for k in LEVEL}
            d["legibility"] = {k: sum(1 for e in evs.values() if e.get("legibility") == k)
                               for k in LEVEL}
            d["publishability"] = {k: sum(1 for e in evs.values() if e.get("publishability") == k)
                                   for k in PUBLISHABILITY}
            d["needs_cad"] = sum(1 for e in evs.values() if e.get("needs_cad"))
            d["pretty_but_wrong_geometry"] = [c["case_id"] for c in done
                                              if evs[c["case_id"]].get("fidelity") == "MAL"
                                              and evs[c["case_id"]].get("publishability")
                                              in ("ALTA", "MEDIA")]
        else:
            ex = [c for c in cs if status(c) in (EXECUTED, COMPLETED)]
            ok = sum(1 for c in ex if _of(c["case_id"], "pipeline")[0]["data"].get("status") == "DONE")
            d["pipeline_success"] = {"reached_output": ok, "executed": len(ex)}
            d["human_prompts"] = sum(len(_of(c["case_id"], "correction")) for c in done)
            d["dimensions"] = {k: {x: sum(1 for e in evs.values() if e.get(k) == x)
                                   for x in CREATE_LEVEL} for k in CREATE_DIMS}
            d["needs_cad"] = sum(1 for e in evs.values() if e.get("needs_cad"))
        # E45: dos juicios que no se mezclan ni se promedian — el plano y la experiencia
        pil = [evs[c["case_id"]] for c in done if evs[c["case_id"]].get("schema") == PILOT_SCHEMA]
        ux = [u[-1]["data"] for c in cs if (u := _of(c["case_id"], "ux_evaluation"))]
        d["pilot"] = {
            "plan_evaluations": len(pil),
            "would_publish": {"si": sum(1 for e in pil if e["would_publish"]),
                              "no": sum(1 for e in pil if not e["would_publish"])},
            "needed_human_correction": {"si": sum(1 for e in pil if e["needed_human_correction"]),
                                        "no": sum(1 for e in pil if not e["needed_human_correction"])},
            "ux_evaluations": len(ux), "ux_ratings": _dist([u["rating"] for u in ux]),
            "ux_understood_immediately": {"si": sum(1 for u in ux if u["understood_immediately"]),
                                          "no": sum(1 for u in ux if not u["understood_immediately"])}}
        res["tracks"][t] = d
    completos = all(res["tracks"][t]["counts"]["completed"] >= TARGET for t in TRACKS)
    capt = sum(res["tracks"][t]["counts"]["captured"] for t in TRACKS)
    res["status"] = "PASS" if completos else ("PARTIAL" if capt else "BLOCKED")
    res["note"] = ("PASS exige 20 + 20 completados." if not completos else
                   "40 completados; la calidad la decide Joaquín mirando la evidencia.")
    return res


def _e(x: Any) -> str:
    return html.escape(str(x))


def build_index() -> str:
    """`index.html`: una sección por caso, para revisar uno por uno sin tablas técnicas."""
    m = load()
    s = summary()
    partes = ["<!doctype html><meta charset=utf-8><title>E44 — revisión</title>"
              "<style>body{font:15px system-ui;max-width:1100px;margin:2em auto}"
              "section{border-top:2px solid #444;margin-top:2em}img{max-width:46%;border:1px solid #bbb}"
              ".b{background:#fee;padding:.3em}</style><h1>E44 — benchmark online</h1>",
              f"<p><b>Estado: {_e(s['status'])}</b> — {_e(s['note'])}</p><ul>"]
    for t in TRACKS:
        c = s["tracks"][t]["counts"]
        partes.append(f"<li>{t}: listados {c['listed']} · capturados {c['captured']} · "
                      f"ejecutados {c['executed']} · completados {c['completed']} / {TARGET}"
                      f" (URL sin material {c['url_only']}, bloqueados {c['blocked']}, "
                      f"excluidos {c['excluded']})</li>")
    partes.append("</ul>")
    for c in m["cases"]:
        cid, st = c["case_id"], status(c)
        base = os.path.join(case_dir(cid))
        partes.append(f"<section><h2>{_e(cid)} · {_e(c['track'])} · {_e(st)}</h2>")
        partes.append(f"<p>Fuente: {_e(c['source'])} · capturado {_e(c['captured_on'])} · "
                      f"{_e(c['property_type'])} · m² publicados: {_e(c['published_m2'] or 'no declarado')}</p>")
        partes.append("<p>URLs: " + ", ".join(_e(u) for u in c["source_urls"]) + "</p>")
        if st == URL_ONLY:
            partes.append("<p class=b>Sólo URL: no hay material capturado, no cuenta como caso.</p>"
                          "</section>")
            continue
        partes.append("<p>Input permitido: " + ", ".join(
            f"{_e(a['file'])} ({_e(a['role'])}, {_e(a['origin_url'])})" for a in c["assets"]) + "</p>")
        for a in c["assets"][:6]:
            if a["file"].lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                partes.append(f"<img src='cases/{_e(cid)}/evidence/{_e(a['file'])}' alt='input'>")
        rv = os.path.join(base, "review")
        if os.path.isdir(rv):
            for f in sorted(os.listdir(rv)):
                partes.append(f"<p>{_e(f)}</p><img src='cases/{_e(cid)}/review/{_e(f)}'>")
        for e in events(cid):
            partes.append(f"<details><summary>{_e(e['kind'])} · {_e(e['at'])}</summary><pre>"
                          f"{_e(json.dumps(e['data'], ensure_ascii=False, indent=1))}</pre></details>")
        partes.append("<p>Rating / comentario Joaquín: ____________________</p></section>")
    out = os.path.join(root(), "index.html")
    os.makedirs(root(), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(partes))
    return out
