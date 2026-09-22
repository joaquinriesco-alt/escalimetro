"""E35 §11 — GENERA EL DATASET DE CALIBRACIÓN DE AUTOACEPTACIÓN.

No vive en la suite de tests porque corre el pipeline de verdad (unos segundos por lámina) y porque
su salida es un HECHO MEDIDO que hay que poder auditar línea por línea, no un cálculo que se rehace
en cada `pytest`. El resultado se escribe en `docs/E35_CALIBRATION_DATASET.json` y de ahí lo lee
`webapp.domain.calibration`.

Cada fila lleva su procedencia: de qué artefacto salió la confianza del motor y de qué archivo salió
la etiqueta humana. Quien audite esto tiene que poder abrir esos dos archivos y ver los mismos
números sin creerle nada a este script.

    PYTHONPATH=src python scripts/e35_calibrate.py
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

OUT = os.path.join(ROOT, "docs", "E35_CALIBRATION_DATASET.json")

#: Cada caso: cómo se corre el pase AUTOMÁTICO puro y dónde están sus etiquetas humanas.
#: El seed de la 401 no es una marca humana: es lo que produce el modelo de candidatos de E35 sobre
#: esa lámina (u2). Sin él la 401 no corre en absoluto — ver webapp/domain/units.py.
CASOS = [
    {"case": "001_gps_403", "overrides": {}, "vision": "ocr",
     "labels": ["overrides_assisted.json", "overrides_shell.json"]},
    {"case": "002_gps_401", "vision": "null",
     "overrides": {"seed_points": [[621, 226]], "segmentation_params": {"mode": "color"}},
     "labels": ["overrides_assisted.json"]},
    {"case": "003_res_unknown", "overrides": {}, "vision": "ocr", "labels": []},
]


def _correr(case_id: str, vision: str, overrides: dict, dest: str) -> dict:
    src = os.path.join(ROOT, "cases", case_id)
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(src, "case.json"), encoding="utf-8") as fh:
        case = json.load(fh)
    case["vision"] = vision
    for nombre in os.listdir(src):
        if nombre.startswith("original."):
            shutil.copy2(os.path.join(src, nombre), os.path.join(dest, nombre))
    with open(os.path.join(dest, "case.json"), "w", encoding="utf-8") as fh:
        json.dump(case, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(dest, "overrides.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(overrides, _doc="E35 calibración: pase automático"), fh, indent=2)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), MPLBACKEND="Agg")
    p = subprocess.run([sys.executable, "-m", "escalimetro", "run", "--case", dest],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
    fp_path = os.path.join(dest, "outputs", "floorplate.json")
    if not os.path.exists(fp_path):
        return {"error": (p.stdout + p.stderr)[-400:]}
    with open(fp_path, encoding="utf-8") as fh:
        return json.load(fh)


def _labels(case_id: str, archivos) -> dict:
    """Lee las marcas humanas que ya existen en el repositorio. No se inventa ninguna."""
    conf, correcciones, origen = set(), {}, {}
    for a in archivos:
        p = os.path.join(ROOT, "cases", case_id, a)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            o = json.load(fh)
        for k in o.get("confirm", []):
            conf.add(k)
            origen.setdefault(k, []).append(f"{a}:confirm")
        if o.get("entrances"):
            correcciones["entrance"] = o["entrances"]
            origen.setdefault("entrance", []).append(f"{a}:entrances")
        add = (o.get("columns") or {}).get("add") or []
        if add:
            correcciones["columns"] = correcciones.get("columns", []) + add
            origen.setdefault("columns", []).append(f"{a}:columns.add")
        if o.get("daylight_confirm"):
            correcciones["daylight"] = o["daylight_confirm"]
            origen.setdefault("daylight", []).append(f"{a}:daylight_confirm")
    return {"confirm": sorted(conf), "corrections": correcciones, "provenance": origen}


def main() -> None:
    from webapp.domain import ingest                            # noqa: PLC0415
    filas = []
    tmp = tempfile.mkdtemp(prefix="e35cal_")
    try:
        for c in CASOS:
            fp = _correr(c["case"], c["vision"], c["overrides"], os.path.join(tmp, c["case"]))
            lab = _labels(c["case"], c["labels"])
            if "error" in fp:
                filas.append({"case_id": c["case"], "error": fp["error"]})
                continue
            confs = ingest.element_confidences(fp)
            pe = fp.get("primary_entrance") or {}
            humano = (lab["corrections"].get("entrance") or [{}])[0].get("point")
            dist = (round(math.dist(pe["point"], humano), 1)
                    if pe.get("point") and humano else None)
            for comp, conf in confs.items():
                if comp == "primary_entrance":
                    if conf is None:
                        v, nota = "UNLABELLED", "el motor no propuso acceso"
                    elif humano is None:
                        v, nota = "UNLABELLED", "no hay acceso marcado por una persona"
                    elif dist is not None and dist <= 10:
                        v, nota = "CONFIRMED", f"coincide con la marca humana ({dist} px)"
                    else:
                        v, nota = "DISAGREES_WITH_HUMAN", (
                            f"la persona marcó otro vano: {dist} px de distancia")
                elif comp in ("columns", "daylight") and comp in lab["corrections"]:
                    n = len(lab["corrections"][comp])
                    v, nota = "CORRECTED_INCOMPLETE", f"una persona agregó/reclasificó {n}"
                elif comp in lab["confirm"]:
                    v, nota = "CONFIRMED", "confirmado sin corregir"
                else:
                    v, nota = "UNLABELLED", "sin etiqueta humana registrada"
                filas.append({
                    "case_id": c["case"], "component": comp, "engine_confidence": conf,
                    "human_verdict": v, "note": nota,
                    "confidence_provenance": f"pase automático de {c['case']} "
                                             f"(vision={c['vision']}, overrides={c['overrides']})",
                    "label_provenance": lab["provenance"].get(
                        {"primary_entrance": "entrance"}.get(comp, comp), []),
                })
            esc = fp.get("scale") or {}
            filas.append({
                "case_id": c["case"], "component": "scale",
                "engine_confidence": (None if not esc.get("px_per_m") else
                                      float((esc.get("meta") or {}).get("confidence") or 0.4)),
                "human_verdict": ("CONFIRMED" if "scale_assumption" in lab["confirm"] else
                                  "UNLABELLED"),
                "note": f"method={esc.get('method')} px_per_m={esc.get('px_per_m')}",
                "confidence_provenance": f"scale.meta.confidence del pase automático de {c['case']}",
                "label_provenance": lab["provenance"].get("scale_assumption", []),
            })
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    doc = {"_doc": "E35 §11 — dataset de calibración de autoaceptación. Generado por "
                   "scripts/e35_calibrate.py sobre los casos reales del repositorio y las marcas "
                   "humanas que ya existían en ellos. NINGUNA etiqueta fue creada para este "
                   "ejercicio.",
           "cases": [c["case"] for c in CASOS], "rows": filas}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    print(f"{len(filas)} filas escritas en {OUT}")


if __name__ == "__main__":
    main()
