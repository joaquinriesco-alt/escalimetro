"""E35 — QUÉ REGIÓN DE LA LÁMINA ES LA OFICINA, SIN PREGUNTARLE SU NOMBRE A NADIE.

=================================================================================================
El defecto que este módulo existe para corregir
=================================================================================================
Hasta E34 la localización de la unidad funcionaba así, medido sobre la lámina real de GPS Property:

    property.title  →  cases.title  →  case.json["unit_label"]  →  pipeline.cfg.unit_label
                    →  OCRVisionInterpreter.interpret(img, target_unit)
                    →  _digits("Oficina 403") == "403"
                    →  se busca ese número impreso SOBRE el dibujo
                    →  si cae dentro de un relleno saturado, ahí empieza la segmentación.

Es decir: **el nombre comercial que escribe el usuario era un input geométrico**. Dos medidas sobre
esa misma lámina, tomadas en este repositorio, muestran lo frágil que es:

* con el título "Oficina 403" el OCR lee `403` en (481,367) con confianza 95 y todo funciona;
* con el título "Oficina 401" —el número correcto de otra unidad de la MISMA lámina— el pipeline
  termina en `RuntimeError: Sin localización`. El rótulo "OFICINA 401" está impreso en blanco sobre
  azul saturado y tesseract no lo lee a ninguna confianza útil; lo único que encuentra es el `401`
  de la leyenda, que queda fuera del plano y se clasifica como `legend_swatch`.

O sea que la dependencia del nombre no era sólo indeseable como producto: **ya estaba rota** para
una de las dos propiedades reales del repositorio. Con un título sin números ("Mi oficina") no hay
siquiera un intento: `_digits` devuelve vacío y el intérprete retorna cero hints.

=================================================================================================
Qué usa este módulo en su lugar
=================================================================================================
Señales del propio dibujo, ninguna del título:

    relleno de color   una lámina que publica varias unidades las demarca pintándolas. Cada color
                       distinto es una unidad candidata. Es la convención del medio, no un truco de
                       este plano: la leyenda existe justamente porque el color es el identificador.
    superficie         área en píxeles, y su proporción respecto del resto de candidatos.
    densidad de tinta  un relleno de unidad tiene líneas encima (muros, mobiliario, pilares); una
                       muestra de leyenda es color plano. Separa candidatos de claves de color.
    rótulos OCR        el texto que cae DENTRO de un candidato. Es evidencia, no llave de selección:
                       en esta misma lámina sólo uno de los tres rótulos es legible.
    fachada            qué proporción del borde del candidato da al exterior del dibujo.
    núcleo             qué proporción del borde da a un vacío interior encerrado (el núcleo común).

=================================================================================================
Por qué NO se autoselecciona el candidato más grande
=================================================================================================
Sería cómodo y está medido que funcionaría para la 403 (39.011 px, el doble que el siguiente). Pero
`cases/002_gps_401` es una propiedad real de este repositorio sobre **la misma lámina**, y su unidad
es la segunda en tamaño. Autoseleccionar por área produciría, sin avisar, un plano comercial de la
oficina equivocada. Eso es exactamente el "false accept" que E35 §12 pone por encima de cualquier
cobertura. Con dos unidades de muestra no hay forma de calibrar una regla de dominancia, así que
no se inventa: **si hay más de un candidato, se pide un clic** (E35 §6).

Ese clic no es una regresión de E34. Está en el registro HITL de este repositorio desde E14:
`cases/002_gps_401/overrides_assisted.json` → `op 1: confirm_target, "click dentro de la Oficina
401", estimated_human_seconds: 4`. Lo que E35 elimina es tener que abrir la herramienta técnica
para darlo.

=================================================================================================
Cómo se le entrega el resultado al motor sin tocar `src/`
=================================================================================================
No hace falta ningún contrato nuevo: el pipeline ya acepta una localización humana por
`overrides.json → seed_points`, y esa rama tiene prioridad sobre el hint de OCR. Escribir ahí el
punto del candidato elegido deja el título fuera del camino geométrico por construcción.

Se escribe además `segmentation_params.mode = "color"` cuando el candidato es una región de color:
sin eso, la estrategia de segmentación dependería de si el OCR encontró o no el número del título
(`strategy_for(has_color_hint=...)`), que es la misma dependencia por otra puerta.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

from .. import store

# -------------------------------------------------------------------------------------------------
# Umbrales de detección. NINGUNO está calibrado: la muestra son 3 dibujos. Se anota al lado de cada
# uno el margen medido, para que se vea qué tan lejos del borde quedó la decisión y no haya que
# volver a medirlo desde cero cuando entren más planos.
# -------------------------------------------------------------------------------------------------
#: "Relleno de color" con los mismos valores que ya usa el motor para decidir que un rótulo está
#: dentro de una región pintada (src/escalimetro/vision/ocr_localizer.py). No se inventan otros.
SAT_MIN, VAL_MIN = 20, 80
#: Cuantización de color y radio de fusión. Un plano usa colores planos; los vecinos a un paso son
#: el antialias del mismo relleno, no otra unidad.
COLOR_STEP, COLOR_MERGE = 16, 16
#: Una unidad ocupa una parte sustantiva del dibujo. Medido: unidades reales 4.7 %–12.7 % del área
#: dibujada; el ruido saturado del plano RES (marca de agua, achurado) llega a 0.21 %.
MIN_DRAWING_FRAC = 0.02
#: Respecto del mayor candidato. Medido: unidades reales 0.37–1.00; flecos de antialias ≤ 0.04;
#: muestras de la leyenda 0.02.
MIN_RELATIVE_AREA = 0.15
#: Un relleno de unidad es color con líneas encima. Medido: rellenos reales 0.003–0.049 de tinta;
#: manchas de texto/achurado 0.72–1.00.
MAX_INK_DENSITY = 0.35
#: Área mínima absoluta para que la morfología signifique algo.
MIN_ABS_AREA_PX = 300

#: De dónde salió la selección. Viaja con el resultado y se guarda: es la diferencia entre
#: "lo dedujo el sistema" y "lo dijo una persona", y no se debe poder confundir después.
AUTO = "AUTO"                     # una sola región posible, elegida por regla
HUMAN_PICK = "HUMAN_PICK"         # un clic del operador sobre un candidato
DECLARED = "DECLARED"             # la fuente declaró `drawing_scope`; no hay nada que elegir
PRE_EXISTING = "PRE_EXISTING"     # ya había marca humana en overrides: no se toca

#: Estado de la selección.
RESOLVED = "RESOLVED"
NEEDS_INTERNAL_REVIEW = "NEEDS_INTERNAL_REVIEW"
NO_DRAWING = "NO_DRAWING"

#: Códigos de razón. Son parte del contrato: explican una decisión sin obligar a leer el código.
R_DECLARED_WHOLE_SHELL = "DECLARED_WHOLE_SHELL"
R_NO_DEMARCATION = "NO_UNIT_DEMARCATION_FOUND"
R_SINGLE_REGION = "SINGLE_UNIT_REGION"
R_MULTIPLE_REGIONS = "MULTIPLE_UNIT_REGIONS"
R_DOMINANCE_UNCALIBRATED = "DOMINANCE_RULE_UNCALIBRATED"
R_HUMAN_OVERRIDE = "HUMAN_OVERRIDE_PRESENT"
R_OCR_LABEL_INSIDE = "OCR_LABEL_INSIDE"
R_TOUCHES_FACADE = "TOUCHES_FACADE"
R_TOUCHES_CORE = "TOUCHES_CORE"

#: Paleta del overlay de candidatos. Fija y en este orden para que dos ejecuciones pinten igual.
PALETTE = ((0, 90, 220), (0, 170, 90), (200, 70, 0), (150, 0, 180), (0, 160, 200), (90, 90, 90))


class UnitError(RuntimeError):
    """No se pudo construir el modelo de candidatos."""


# =================================================================================================
# detección
# =================================================================================================
def _drawing_bounds(img):
    """Extensión de lo dibujado. Se reutiliza la definición del motor en vez de escribir otra:
    tener dos respuestas distintas a "dónde hay dibujo" es peor que depender del import."""
    from escalimetro.localization import drawing_bounds       # noqa: PLC0415
    return drawing_bounds(img)


def _color_clusters(img, sat) -> List[Tuple[int, int, int]]:
    """Colores de relleno presentes, de más a menos superficie, fusionando los vecinos.

    Sin la fusión, el antialias de cada relleno aparece como colores propios y produce candidatos
    fantasma pegados al borde de los buenos."""
    import numpy as np                                        # noqa: PLC0415
    q = (img.astype(int) // COLOR_STEP) * COLOR_STEP
    vals, counts = np.unique(q[sat].reshape(-1, 3), axis=0, return_counts=True)
    centros: List[Dict] = []
    for i in np.argsort(-counts):
        c, n = vals[i].astype(int), int(counts[i])
        if n < MIN_ABS_AREA_PX:
            break
        for k in centros:
            if int(np.abs(np.array(k["c"]) - c).max()) <= COLOR_MERGE:
                k["n"] += n
                break
        else:
            centros.append({"c": tuple(int(v) for v in c), "n": n})
    return [k["c"] for k in centros]


def _ocr_tokens(img) -> List[Dict]:
    """Texto legible sobre la lámina. Es EVIDENCIA de un candidato, nunca la llave para elegirlo.

    Devuelve lista vacía si no hay tesseract: el modelo tiene que seguir funcionando sin OCR, y de
    hecho funciona —en esta lámina sólo uno de los tres rótulos de unidad es legible."""
    try:
        import cv2                                            # noqa: PLC0415
        import pytesseract                                    # noqa: PLC0415
    except ImportError:
        return []
    try:
        big = cv2.resize(img, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
        d = pytesseract.image_to_data(gray, config="--psm 11",
                                      output_type=pytesseract.Output.DICT)
    except Exception:                                          # noqa: BLE001 — tesseract ausente o roto
        return []
    out = []
    for i, t in enumerate(d["text"]):
        try:
            conf = float(d["conf"][i])
        except (TypeError, ValueError):
            continue
        txt = (t or "").strip()
        # Un token de una sola letra o de pura puntuación no es un rótulo: es ruido de tesseract
        # sobre las líneas del dibujo. Mostrarlo como "rótulo encontrado" le daría al operador una
        # evidencia que no existe.
        if len(txt) < 2 or conf < 60 or not any(ch.isalnum() for ch in txt):
            continue
        x, y = d["left"][i] / 3.0, d["top"][i] / 3.0
        w, h = d["width"][i] / 3.0, d["height"][i] / 3.0
        out.append({"text": txt, "confidence": round(conf / 100.0, 2),
                    "center": [round(x + w / 2, 1), round(y + h / 2, 1)]})
    return out


def candidates(image_path: str) -> List[Dict]:
    """Regiones de la lámina que podrían ser la unidad, ordenadas de forma determinista.

    El orden es `(-área, y, x, color)`: un orden total sobre datos de la imagen, de modo que la
    misma lámina produce la misma lista y los mismos `candidate_id` en cualquier ejecución y con
    cualquier título. Esa determinación es la que hace testeable la independencia del nombre."""
    import cv2                                                # noqa: PLC0415
    import numpy as np                                        # noqa: PLC0415
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise UnitError(f"no se pudo leer la lámina: {image_path}")
    h, w = img.shape[:2]
    roi = _drawing_bounds(img) or (0, 0, w, h)
    area_dibujo = max(1, (roi[2] - roi[0]) * (roi[3] - roi[1]))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = (hsv[..., 1].astype(int) > SAT_MIN) & (hsv[..., 2].astype(int) > VAL_MIN)
    ink = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < 140
    centros = _color_clusters(img, sat)
    if not centros:
        return []
    C = np.array(centros, dtype=int)
    dist = np.abs(img.reshape(-1, 3).astype(int)[:, None, :] - C[None, :, :]).max(axis=2)
    cerca, dmin = dist.argmin(axis=1).reshape(h, w), dist.min(axis=1).reshape(h, w)
    kernel = np.ones((7, 7), np.uint8)
    crudos: List[Dict] = []
    for j in range(len(C)):
        m = ((cerca == j) & sat & (dmin <= 2 * COLOR_MERGE)).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
        for i in range(1, n):
            a = int(st[i, cv2.CC_STAT_AREA])
            if a < MIN_ABS_AREA_PX or a < MIN_DRAWING_FRAC * area_dibujo:
                continue
            comp = lab == i
            densidad = float(ink[comp].mean())
            if densidad > MAX_INK_DENSITY:
                continue                                       # texto o achurado, no un relleno
            x, y, bw, bh = (int(st[i, k]) for k in range(4))
            crudos.append({"area": a, "bbox": [x, y, bw, bh], "ink": round(densidad, 4),
                           "color": [int(v) for v in C[j]], "mask": comp})
    if not crudos:
        return []
    mayor = max(c["area"] for c in crudos)
    crudos = [c for c in crudos if c["area"] >= MIN_RELATIVE_AREA * mayor]
    crudos.sort(key=lambda c: (-c["area"], c["bbox"][1], c["bbox"][0], tuple(c["color"])))
    tokens = _ocr_tokens(img)
    total = sum(c["area"] for c in crudos) or 1
    fuera = ~sat                                               # papel y trazo, no relleno de unidad
    out: List[Dict] = []
    for rank, c in enumerate(crudos, start=1):
        comp = c.pop("mask")
        # punto SIEMPRE interior: el centroide de una planta en L o en U cae sobre el núcleo.
        dt = cv2.distanceTransform(comp.astype(np.uint8), cv2.DIST_L2, 5)
        py, px = np.unravel_index(int(dt.argmax()), dt.shape)
        # El CONTORNO real, no el rectángulo. Una planta en L o en U tiene un bounding box que se
        # come a sus vecinas: pintado como rectángulo, el operador no distingue una zona de otra y
        # la pregunta de un clic deja de ser de un clic. Se simplifica para que quepa en el JSON
        # sin dejar de ser la forma que se está señalando.
        cs, _ = cv2.findContours(comp.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mayor_c = max(cs, key=cv2.contourArea) if cs else None
        contorno = ([] if mayor_c is None else
                    [[int(q[0][0]), int(q[0][1])] for q in
                     cv2.approxPolyDP(mayor_c, 0.004 * cv2.arcLength(mayor_c, True), True)])
        borde = cv2.dilate(comp.astype(np.uint8), kernel, iterations=1).astype(bool) & ~comp
        vecino_fuera = int((borde & fuera).sum()) or 1
        exterior = np.zeros((h, w), np.uint8)
        exterior[roi[1]:roi[3], roi[0]:roi[2]] = 1
        # fachada = borde del candidato que mira al papel fuera del dibujo o al límite de la lámina
        libre = (~sat) & (~ink)
        fachada = float((borde & libre & (exterior == 0)).sum()) / vecino_fuera
        nucleo = float((borde & libre & (exterior == 1)).sum()) / vecino_fuera
        dentro = [t for t in tokens
                  if c["bbox"][0] <= t["center"][0] <= c["bbox"][0] + c["bbox"][2]
                  and c["bbox"][1] <= t["center"][1] <= c["bbox"][1] + c["bbox"][3]
                  and comp[min(h - 1, int(t["center"][1])), min(w - 1, int(t["center"][0]))]]
        razones = []
        if dentro:
            razones.append(R_OCR_LABEL_INSIDE)
        if fachada > 0.05:
            razones.append(R_TOUCHES_FACADE)
        if nucleo > 0.05:
            razones.append(R_TOUCHES_CORE)
        out.append({
            "candidate_id": f"u{rank}",
            "rank": rank,
            "pixel_area": c["area"],
            "relative_area": round(c["area"] / total, 4),
            "bbox": c["bbox"],
            "seed_point": [int(px), int(py)],
            "fill_color_bgr": c["color"],
            "ink_density": c["ink"],
            "ocr_labels": [t["text"] for t in dentro],
            "access_evidence": {"free_boundary_fraction": round(fachada, 3)},
            "core_relationship": {"enclosed_boundary_fraction": round(nucleo, 3)},
            "geometry_evidence": {"kind": "COLOR_FILL_REGION",
                                  "inscribed_radius_px": round(float(dt.max()), 1),
                                  "contour": contorno},
            "reason_codes": razones,
        })
    return out


def _whole_drawing_candidate(image_path: str, motivo: str) -> Dict:
    """El dibujo entero como único candidato. No es una inferencia sobre `drawing_scope` (E16.5 se
    niega a eso y hace bien): es dónde empezar a mirar cuando la lámina no demarca unidades."""
    import cv2                                                # noqa: PLC0415
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise UnitError(f"no se pudo leer la lámina: {image_path}")
    h, w = img.shape[:2]
    x0, y0, x1, y1 = _drawing_bounds(img) or (0, 0, w, h)
    return {"candidate_id": "u1", "rank": 1, "pixel_area": int((x1 - x0) * (y1 - y0)),
            "relative_area": 1.0, "bbox": [x0, y0, x1 - x0, y1 - y0],
            "seed_point": [int((x0 + x1) / 2), int((y0 + y1) / 2)],
            "fill_color_bgr": None, "ink_density": None, "ocr_labels": [],
            "access_evidence": {"free_boundary_fraction": None},
            "core_relationship": {"enclosed_boundary_fraction": None},
            "geometry_evidence": {"kind": "WHOLE_DRAWING", "inscribed_radius_px": None,
                                  "contour": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]},
            "reason_codes": [motivo]}


# =================================================================================================
# decisión
# =================================================================================================
def analyze(image_path: str, *, declared_scope: Optional[str] = None,
            human_override: bool = False) -> Dict:
    """El modelo completo: candidatos, decisión y por qué.

    Precedencia, de más fuerte a más débil, y ninguna la decide el nombre de la propiedad:

    1. **marca humana previa** en overrides — alguien ya respondió; no se le lleva la contraria;
    2. **declaración de la fuente** (`drawing_scope=whole_shell`) — hecho de entrada (E16.5);
    3. **un solo candidato de color** — no hay entre qué elegir;
    4. **ninguna demarcación** — la lámina no separa unidades: se mira el dibujo entero;
    5. **varios candidatos** — ambigüedad real: un clic. Nunca se adivina.
    """
    if human_override:
        return {"status": RESOLVED, "source": PRE_EXISTING, "confidence": 1.0,
                "candidate_count": 0, "selected_candidate_id": None, "candidates": [],
                "reason_codes": [R_HUMAN_OVERRIDE],
                "evidence_summary": "ya hay una marca humana en overrides.json; no se toca"}
    if (declared_scope or "").strip() == "whole_shell":
        c = _whole_drawing_candidate(image_path, R_DECLARED_WHOLE_SHELL)
        return {"status": RESOLVED, "source": DECLARED, "confidence": 1.0, "candidate_count": 1,
                "selected_candidate_id": c["candidate_id"], "candidates": [c],
                "reason_codes": [R_DECLARED_WHOLE_SHELL],
                "evidence_summary": "la fuente declara que el dibujo completo es el espacio"}
    cands = candidates(image_path)
    if not cands:
        c = _whole_drawing_candidate(image_path, R_NO_DEMARCATION)
        return {"status": RESOLVED, "source": AUTO, "confidence": 0.70, "candidate_count": 1,
                "selected_candidate_id": c["candidate_id"], "candidates": [c],
                "reason_codes": [R_NO_DEMARCATION],
                "evidence_summary": "la lámina no demarca unidades por color: se mira el dibujo "
                                    "completo"}
    if len(cands) == 1:
        c = cands[0]
        return {"status": RESOLVED, "source": AUTO, "confidence": 0.85, "candidate_count": 1,
                "selected_candidate_id": c["candidate_id"], "candidates": cands,
                "reason_codes": [R_SINGLE_REGION] + c["reason_codes"],
                "evidence_summary": f"una sola región demarcada, {c['pixel_area']} px"}
    # §12 — con más de un candidato NO se elige por área. Ver el encabezado: la 401 de este mismo
    # repositorio es la segunda en tamaño sobre esta misma lámina.
    return {"status": NEEDS_INTERNAL_REVIEW, "source": None, "confidence": None,
            "candidate_count": len(cands), "selected_candidate_id": None, "candidates": cands,
            "reason_codes": [R_MULTIPLE_REGIONS, R_DOMINANCE_UNCALIBRATED],
            "evidence_summary": f"{len(cands)} regiones demarcadas de tamaño comparable "
                                f"({', '.join(str(c['pixel_area']) for c in cands)} px)"}


# =================================================================================================
# persistencia
# =================================================================================================
def _case_image(case_id: str) -> str:
    c = store.q1("SELECT source_file FROM cases WHERE case_id=?", (case_id,))
    if not c:
        raise UnitError(f"caso desconocido: {case_id}")
    return os.path.join(store.case_dir(case_id), c["source_file"])


def _human_override(case_id: str) -> bool:
    """¿Ya hay una localización puesta por una persona? `seed_point` del intake o un perímetro
    manual en overrides. Si la hay, este módulo no opina."""
    it = store.q1("SELECT seed_point FROM intake WHERE case_id=?", (case_id,))
    if it and store.js(it["seed_point"]):
        return True
    p = os.path.join(store.case_dir(case_id), "overrides.json")
    try:
        with open(p, encoding="utf-8") as fh:
            o = json.load(fh)
    except (OSError, ValueError):
        return False
    return bool(o.get("perimeter"))


def save(property_id: str, case_id: str, d: Dict) -> None:
    store.ex("INSERT INTO unit_selection(property_id, case_id, status, source, confidence, "
             "candidate_count, selected_candidate_id, candidates, evidence_summary, reason_codes, "
             "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(property_id) DO UPDATE SET "
             "case_id=excluded.case_id, status=excluded.status, source=excluded.source, "
             "confidence=excluded.confidence, candidate_count=excluded.candidate_count, "
             "selected_candidate_id=excluded.selected_candidate_id, "
             "candidates=excluded.candidates, evidence_summary=excluded.evidence_summary, "
             "reason_codes=excluded.reason_codes, updated_at=excluded.updated_at",
             (property_id, case_id, d["status"], d.get("source"), d.get("confidence"),
              d.get("candidate_count"), d.get("selected_candidate_id"),
              json.dumps(d.get("candidates") or [], ensure_ascii=False),
              d.get("evidence_summary") or "",
              json.dumps(d.get("reason_codes") or [], ensure_ascii=False), store.now()))


def get(property_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM unit_selection WHERE property_id=?", (property_id,))
    if not r:
        return None
    d = dict(r)
    d["candidates"] = store.js(r["candidates"]) or []
    d["reason_codes"] = store.js(r["reason_codes"]) or []
    return d


def selected(property_id: str) -> Optional[Dict]:
    """El candidato elegido, o None si todavía no hay decisión."""
    d = get(property_id)
    if not d or d["status"] != RESOLVED or not d["selected_candidate_id"]:
        return None
    for c in d["candidates"]:
        if c["candidate_id"] == d["selected_candidate_id"]:
            return c
    return None


def resolve(property_id: str, case_id: str) -> Dict:
    """Analiza la lámina de la propiedad y guarda la decisión. Idempotente y sin efectos sobre una
    selección ya tomada por una persona: un reanálisis no debe borrar un clic."""
    ya = get(property_id)
    if ya and ya.get("source") == HUMAN_PICK and ya["status"] == RESOLVED:
        return ya
    it = store.q1("SELECT drawing_scope FROM intake WHERE case_id=?", (case_id,))
    d = analyze(_case_image(case_id),
                declared_scope=(it["drawing_scope"] if it else None),
                human_override=_human_override(case_id))
    save(property_id, case_id, d)
    return get(property_id)


def pick(property_id: str, candidate_id: str) -> Dict:
    """UN clic del operador (§6). No se le pide ni un nombre, ni un id técnico, ni coordenadas."""
    d = get(property_id)
    if not d:
        raise UnitError("esta propiedad todavía no tiene candidatos analizados")
    ids = [c["candidate_id"] for c in d["candidates"]]
    if candidate_id not in ids:
        raise UnitError(f"candidato desconocido: {candidate_id}")
    d.update({"status": RESOLVED, "source": HUMAN_PICK, "confidence": 1.0,
              "selected_candidate_id": candidate_id,
              "reason_codes": ["HUMAN_PICK"],
              "evidence_summary": f"elegido por una persona entre {len(ids)} candidatos"})
    save(property_id, d["case_id"], d)
    return get(property_id)


# =================================================================================================
# entrega al motor
# =================================================================================================
def overrides_for(property_id: str) -> Dict:
    """Lo que la selección aporta a `overrides.json`, en el vocabulario HITL que el motor ya
    entiende. Ninguna clave nueva.

    `segmentation_params.mode` va explícito a propósito: sin él, `strategy_for` decidiría la
    estrategia según si el OCR encontró el número del título, que es la dependencia que E35 elimina.
    Con él, la misma lámina se segmenta igual se llame como se llame la propiedad."""
    c = selected(property_id)
    if not c:
        return {}
    if c["geometry_evidence"]["kind"] == "WHOLE_DRAWING":
        x, y, w, h = c["bbox"]
        return {"seed_points": [c["seed_point"]], "bbox": [x, y, x + w, y + h]}
    return {"seed_points": [c["seed_point"]], "segmentation_params": {"mode": "color"}}


def overlay(property_id: str, out_path: str) -> Optional[str]:
    """La lámina con los candidatos pintados y numerados: es toda la interfaz de la pregunta.

    El operador no lee un id ni un nombre técnico; ve la planta y hace clic sobre la zona."""
    import cv2                                                # noqa: PLC0415
    import numpy as np                                        # noqa: PLC0415
    d = get(property_id)
    if not d or not d["candidates"]:
        return None
    img = cv2.imread(_case_image(d["case_id"]), cv2.IMREAD_COLOR)
    if img is None:
        return None
    vis = img.copy()
    for i, c in enumerate(d["candidates"]):
        col = PALETTE[i % len(PALETTE)]
        cont = (c.get("geometry_evidence") or {}).get("contour") or []
        if cont:
            poly = np.array(cont, dtype=np.int32).reshape(-1, 1, 2)
            capa = vis.copy()
            cv2.fillPoly(capa, [poly], col)
            vis = cv2.addWeighted(capa, 0.32, vis, 0.68, 0)
            cv2.polylines(vis, [poly], True, col, 2)
        else:
            x, y, w, h = c["bbox"]
            cv2.rectangle(vis, (x, y), (x + w, y + h), col, 2)
        sx, sy = c["seed_point"]
        cv2.circle(vis, (int(sx), int(sy)), 16, col, -1)
        cv2.putText(vis, str(i + 1), (int(sx) - 6, int(sy) + 7), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 2, cv2.LINE_AA)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, vis)
    return out_path
