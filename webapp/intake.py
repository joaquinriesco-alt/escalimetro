"""E27 §5/§6/§17 — subida de plantas, preview y preparación del shell.

Frontera de producto (§2): V1 es SHELL-ONLY. Este módulo NO limpia plantas amobladas y no lo
finge. Lo que hace es (a) guardar el original intacto, (b) producir una imagen que el navegador
pueda mostrar siempre, y (c) traducir cuatro confirmaciones humanas al vocabulario de
`overrides.json` que el pipeline de normalización ya entiende.

Lo que NO hace, a propósito: inventar geometría. Si el pipeline no logra leer la planta, se
muestra lo que el propio motor dice que falta (`shell_readiness.requires_confirmation`), no una
suposición nuestra.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from typing import Dict, List, Optional, Tuple

from . import store

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: §4 — formatos aceptados. La extensión se decide aquí, nunca la que venga en el nombre subido.
ALLOWED = {".pdf": "application/pdf", ".png": "image/png",
           ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MAX_UPLOAD_MB = int(os.environ.get("ESCALIMETRO_MAX_UPLOAD_MB", "40"))
PREVIEW_MAX_PX = 2200


class IntakeError(ValueError):
    pass


def new_case_id() -> str:
    """Identificador interno. No deriva del nombre subido: así no hay path traversal posible
    (§17) y dos archivos con el mismo nombre no se pisan."""
    return "c_" + uuid.uuid4().hex[:12]


def ext_of(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED:
        raise IntakeError(f"Formato no aceptado: {ext or '(sin extensión)'}. Sólo PDF, PNG o JPG.")
    return ext


def sniff_ok(path: str, ext: str) -> bool:
    """Comprobación de contenido, no sólo de extensión: un .png que empieza con %PDF no entra."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    if ext == ".pdf":
        return head.startswith(b"%PDF")
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    return head.startswith(b"\xff\xd8\xff")                   # JPEG


def save_upload(file_storage, title: str = "") -> str:
    """Guarda el original tal cual y crea el CASE. El original NUNCA se modifica (§5)."""
    original = file_storage.filename or "planta"
    ext = ext_of(original)
    case_id = new_case_id()
    cdir = store.case_dir(case_id)
    os.makedirs(cdir, exist_ok=True)
    src = os.path.join(cdir, "original" + ext)
    file_storage.save(src)
    size_mb = os.path.getsize(src) / 1e6
    if size_mb > MAX_UPLOAD_MB:
        shutil.rmtree(cdir, ignore_errors=True)
        raise IntakeError(f"El archivo pesa {size_mb:.1f} MB; el máximo es {MAX_UPLOAD_MB} MB.")
    if not sniff_ok(src, ext):
        shutil.rmtree(cdir, ignore_errors=True)
        raise IntakeError("El contenido del archivo no coincide con su extensión.")
    make_preview(case_id, src, ext)
    store.ex("INSERT INTO cases(case_id, title, original_filename, source_file, mime, "
             "uploaded_at, status, track) VALUES (?,?,?,?,?,?,?,?)",
             (case_id, (title or os.path.splitext(os.path.basename(original))[0])[:120],
              original, os.path.basename(src), ALLOWED[ext], store.now(),
              "UPLOADED", "DEVELOPMENT"))
    store.ex("INSERT INTO intake(case_id, updated_at) VALUES (?,?)", (case_id, store.now()))
    return case_id


def make_preview(case_id: str, src: str, ext: str) -> str:
    """PNG que el navegador siempre puede mostrar. Para PDF: primera página rasterizada (§5).

    El preview es DERIVADO y regenerable; el original queda al lado, intacto."""
    import cv2                                                # noqa: PLC0415
    import numpy as np                                        # noqa: PLC0415
    out = os.path.join(store.case_dir(case_id), "preview.png")
    if ext == ".pdf":
        import pymupdf                                        # noqa: PLC0415
        doc = pymupdf.open(src)
        if doc.page_count < 1:
            raise IntakeError("El PDF no tiene páginas.")
        page = doc.load_page(0)
        zoom = min(3.0, PREVIEW_MAX_PX / max(page.rect.width, page.rect.height))
        page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(out)
        doc.close()
        return out
    img = cv2.imread(src, cv2.IMREAD_COLOR)
    if img is None:
        raise IntakeError("No se pudo leer la imagen.")
    h, w = img.shape[:2]
    if max(h, w) > PREVIEW_MAX_PX:
        s = PREVIEW_MAX_PX / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(out, img)
    return out


def preview_size(case_id: str) -> Tuple[int, int]:
    import cv2                                                # noqa: PLC0415
    p = os.path.join(store.case_dir(case_id), "preview.png")
    img = cv2.imread(p, cv2.IMREAD_COLOR)
    return (0, 0) if img is None else (img.shape[1], img.shape[0])


def px_per_m_from_two_points(p1, p2, metres: float) -> float:
    """§6.2 — escala por dos puntos sobre el plano + una distancia real conocida.

    Es la forma más honesta que tiene V1 de fijar escala: una medición declarada por un humano,
    no un área publicada dividida por un área de píxeles."""
    if not metres or metres <= 0:
        raise IntakeError("La distancia real debe ser mayor que cero.")
    d = math.dist(p1, p2)
    if d < 2:
        raise IntakeError("Los dos puntos están demasiado juntos para medir escala.")
    return d / float(metres)


def write_case_json(case_id: str) -> str:
    """`case.json` con el MISMO contrato que consumen `cli.run` y `case_context.from_case_dir`.
    Sólo hechos de entrada; ningún resultado (contrato E15.1)."""
    c = store.q1("SELECT * FROM cases WHERE case_id=?", (case_id,))
    it = store.q1("SELECT * FROM intake WHERE case_id=?", (case_id,)) or {}
    cdir = store.case_dir(case_id)
    payload = {
        "case_id": case_id,
        "image": c["source_file"],
        "unit_label": c["title"],
        "known_area_m2": c["published_area_m2"],
        "known_area_kind": "unknown",
        "overrides": "overrides.json",
        "vision": "ocr", "segmentation": "auto",
        "simplify_eps_frac": 0.004, "mask_open_px": 5,
        "source_name": c["source_name"] or "",
        "shell_declared_clean": {"yes": "yes", "no": "no"}.get(
            (it["declared_clean"] if it else None) or "", "unknown"),
        "_contract": "E27 — generado por la web app desde el intake. Sólo hechos de entrada.",
    }
    p = os.path.join(cdir, "case.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return p


def write_overrides(case_id: str) -> str:
    """Intake → `overrides.json`, el vocabulario HITL que el pipeline ya entiende (seed_points,
    scale, entrances, confirm). No se inventa ninguna clave nueva."""
    it = store.q1("SELECT * FROM intake WHERE case_id=?", (case_id,))
    o: Dict = {"_doc": "E27 — confirmaciones humanas capturadas en la web app."}
    if it:
        seed = store.js(it["seed_point"])
        ent = store.js(it["entrance_point"])
        conf = store.js(it["confirmed"], []) or []
        if seed:
            o["seed_points"] = [[int(seed[0]), int(seed[1])]]
        if it["scale_px_per_m"]:
            o["scale"] = {"px_per_m": float(it["scale_px_per_m"])}
        if ent:
            o["entrances"] = [{"point": [int(ent[0]), int(ent[1])], "kind": "main"}]
        if conf:
            o["confirm"] = conf
    p = os.path.join(store.case_dir(case_id), "overrides.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(o, fh, indent=2, ensure_ascii=False)
    return p


def normalize(case_id: str) -> Dict:
    """Corre el pipeline de normalización EXISTENTE (`python -m escalimetro run`) y devuelve
    qué falta, según el propio motor. No se corrige nada a mano."""
    write_case_json(case_id)
    write_overrides(case_id)
    cdir = store.case_dir(case_id)
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "src"), MPLBACKEND="Agg")
    p = subprocess.run([sys.executable, "-m", "escalimetro", "run", "--case", cdir],
                       cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=900)
    log = (p.stdout or "") + (p.stderr or "")
    fp_path = os.path.join(cdir, "outputs", "floorplate.json")
    missing: List[str] = []
    ready = False
    if os.path.exists(fp_path):
        try:
            with open(fp_path, encoding="utf-8") as fh:
                fp = json.load(fh)
            sr = fp.get("shell_readiness") or {}
            missing = list(sr.get("requires_confirmation") or [])
            ready = bool(sr.get("ready_for_layout"))
        except (OSError, ValueError):
            missing = ["floorplate ilegible"]
    else:
        missing = ["no se pudo leer la geometría de esta planta"]
    store.ex("UPDATE intake SET missing=?, updated_at=? WHERE case_id=?",
             (json.dumps(missing, ensure_ascii=False), store.now(), case_id))
    store.ex("UPDATE cases SET status=? WHERE case_id=?",
             ("READY" if ready else "NEEDS_INPUT", case_id))
    return {"ready": ready, "missing": missing, "log": log[-8000:], "returncode": p.returncode}


def existing_scale(case_id: str) -> Optional[Dict]:
    """§6.2 — si el artefacto ya trae una escala, se MUESTRA con su método y confianza en vez de
    pedirla de nuevo. El humano la confirma; no se la da por buena en silencio."""
    p = os.path.join(store.case_dir(case_id), "outputs", "floorplate.json")
    try:
        with open(p, encoding="utf-8") as fh:
            sc = (json.load(fh).get("scale") or {})
    except (OSError, ValueError):
        return None
    if not sc.get("px_per_m"):
        return None
    meta = sc.get("meta") or {}
    return {"px_per_m": float(sc["px_per_m"]), "method": sc.get("method") or meta.get("method") or "",
            "status": meta.get("status") or "", "confidence": meta.get("confidence") or ""}


def shell_svg_for(case_id: str) -> Optional[str]:
    """§20 — el shell se dibuja desde `floorplate.json` en cada request. Sin PNG intermedio,
    sin dependencia de un archivo que `.gitignore` pueda excluir del deploy."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
    from escalimetro.case_context import from_case_dir        # noqa: PLC0415
    from escalimetro.layout.e06.scale import scaled_shell     # noqa: PLC0415
    from .shellview import shell_svg                          # noqa: PLC0415
    from escalimetro.schemas.floorplate import Floorplate     # noqa: PLC0415
    try:
        ctx = from_case_dir(store.case_dir(case_id))
        shell = scaled_shell(Floorplate.load(ctx.require_floorplate()), 1.0)
        return shell_svg(shell)
    except Exception:                                         # noqa: BLE001
        return None


# ===================================================================================================
# E27.2 §5 — QUÉ ES OBLIGATORIO, Y POR QUÉ
# ===================================================================================================
# Nada de esto se inventó para la UI: cada obligatorio existe porque el runtime lo exige y falla sin
# él. La prueba está en `layout/shell_adapter.py`, que es la puerta de entrada al motor:
#
#   :18  ValueError("El shell no está listo para layout (ready_for_layout = false)")
#   :27  ValueError("sin escala")
#   :42  ValueError("primary_entrance no confirmado")
#
# y `ready_for_layout` es `requires_confirmation == []`, que `semantics/shell.py:131-153` arma con
# perimeter/core, primary_entrance, columns, daylight y scale_assumption.
#
# Lo que NO está acá es tan importante como lo que está: el punto semilla no aparece en
# `requires_confirmation`, así que es OPCIONAL aunque ayude a la segmentación.

#: Confirmaciones de elementos fijos que el runtime exige. Clave = valor en `overrides.confirm`
#: (consumido por `pipeline.py:272` y `semantics/shell.py`); valor = etiqueta humana.
REQUIRED_CONFIRMS = {
    "perimeter": "Perímetro",
    "core": "Núcleo",
    "columns": "Pilares",
    "daylight": "Fachada / ventanas",
    "scale_assumption": "Supuesto de escala",
}

#: Traducción de los códigos que devuelve el runtime a algo que una persona pueda accionar.
MISSING_LABELS = {
    "perimeter/core": "Confirmá el perímetro y el núcleo.",
    "primary_entrance": "Marcá el acceso principal sobre el plano.",
    "columns": "Confirmá los pilares.",
    "daylight": "Confirmá la fachada / ventanas.",
    "scale_assumption": "Confirmá el supuesto de escala.",
    "scale_semantics": ("La escala no es utilizable: la superficie publicada no corresponde a la "
                        "región segmentada. No se arregla confirmando; hay que corregir el dato."),
}


def humanize_missing(codes: List[str]) -> List[str]:
    return [MISSING_LABELS.get(c, c) for c in (codes or [])]


def validate_intake_form(form) -> Dict[str, str]:
    """§4 — validación de servidor del formulario de intake. Devuelve {campo: mensaje}.

    Se ejecuta ANTES de tocar el pipeline: un intake incompleto no llega nunca al motor, así que no
    puede terminar en un traceback disfrazado de FAILED."""
    errs: Dict[str, str] = {}

    if (form.get("declared_clean") or "") not in ("yes", "no"):
        errs["declared_clean"] = "Debes confirmar si la planta está limpia."
    elif form.get("declared_clean") == "no":
        errs["declared_clean"] = ("V1 sólo acepta plantas libres. Una planta con mobiliario o layout "
                                  "previo queda fuera de contrato: la limpieza automática es V2.")

    # Escala: vale por dos puntos + distancia real, o por superficie publicada. Una de las dos.
    p1 = _pair_of(form, "scale_x1", "scale_y1")
    p2 = _pair_of(form, "scale_x2", "scale_y2")
    metres = (form.get("scale_m") or "").strip()
    area = (form.get("published_area_m2") or "").strip()
    if p1 and p2 and metres:
        try:
            px_per_m_from_two_points(p1, p2, float(metres))
        except (IntakeError, ValueError) as e:
            errs["scale"] = str(e)
    elif area:
        try:
            if float(area) <= 0:
                errs["scale"] = "La superficie publicada debe ser mayor que cero."
        except ValueError:
            errs["scale"] = "La superficie publicada debe ser un número."
    else:
        errs["scale"] = ("Falta definir la escala: marcá dos puntos y su distancia real, o escribí "
                         "la superficie publicada.")

    if not _pair_of(form, "entrance_x", "entrance_y"):
        errs["entrance"] = "Marca el acceso principal sobre el plano."

    faltan = [lbl for k, lbl in REQUIRED_CONFIRMS.items() if k not in form.getlist("confirm")]
    if faltan:
        errs["confirm"] = "Falta confirmar: " + ", ".join(faltan) + "."
    return errs


def _pair_of(form, kx: str, ky: str):
    x, y = form.get(kx), form.get(ky)
    try:
        return [float(x), float(y)] if x not in (None, "") and y not in (None, "") else None
    except (TypeError, ValueError):
        return None


def blockers_for_generate(case_id: str) -> List[str]:
    """§3/§4 — por qué NO se puede generar todavía. Lista vacía = adelante.

    La fuente de verdad es el ARTEFACTO, no el estado en la base: se lee el mismo
    `shell_readiness.ready_for_layout` que `layout/shell_adapter.py:18` exige antes de construir un
    shell. Así la regla de la UI y la del motor no pueden separarse nunca, y un caso que ya produjo
    layouts (COMPLETE / PARTIAL) puede volver a generar con otro brief sin pelearse con el estado."""
    if store.q1("SELECT case_id FROM cases WHERE case_id=?", (case_id,)) is None:
        return ["El caso no existe."]
    fp = os.path.join(case_dir_of(case_id), "outputs", "floorplate.json")
    if not os.path.exists(fp):
        return ["Todavía no preparaste el shell. Completá los campos obligatorios y pulsá "
                "«Preparar shell»."]
    try:
        with open(fp, encoding="utf-8") as fh:
            sr = (json.load(fh).get("shell_readiness") or {})
    except (OSError, ValueError):
        return ["No se puede leer la geometría de esta planta. Volvé a preparar el shell."]
    if sr.get("ready_for_layout"):
        return []
    return (humanize_missing(sr.get("requires_confirmation") or [])
            or ["El shell todavía no está listo para generar layouts."])


def case_dir_of(case_id: str) -> str:
    return store.case_dir(case_id)
