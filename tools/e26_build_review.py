"""E26 §10/§11 — arma el índice de revisión y la hoja visual desde los artefactos de la corrida.

NO rellena ninguna evaluación. El índice sólo dice QUÉ hay que revisar y con qué identidad.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CASOS = [
    {"case_id": "001_gps_403", "case_dir": "cases/001_gps_403", "run": "E26_403",
     "titulo": "OFICINA 403 · GPS PROPERTY", "brief": "BRIEF_EQUILIBRADO"},
    {"case_id": "002_gps_401", "case_dir": "cases/002_gps_401", "run": "E26_401",
     "titulo": "OFICINA 401 · GPS PROPERTY", "brief": "BRIEF_401_V1"},
]
ALTS = ["A", "B", "C"]
NOMBRE = {"A": "EFICIENTE", "B": "BALANCEADO", "C": "COLABORATIVO"}


def _j(p):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def indice():
    schema = _j(os.path.join(ROOT, "contracts/human_review_v1.schema.json")) or {}
    tags = (((schema.get("properties") or {}).get("reason_tags") or {}).get("items") or {}).get("enum") or []
    out = {"contract": "human_review_v1", "reason_tags": tags, "casos": []}
    for c in CASOS:
        base = os.path.join(ROOT, c["case_dir"], "layouts", c["run"])
        prov = _j(os.path.join(base, "run_provenance.json")) or {}
        prog = _j(os.path.join(base, "program_compiled.json")) or {}
        sem = prog.get("brief_semantics", {})
        fila = {"case_id": c["case_id"], "titulo": c["titulo"], "brief_id": prov.get("brief_id") or c["brief"],
                "brief_sha256": prov.get("brief_sha256"), "engine_commit": prov.get("engine_commit"),
                "generated_at": prov.get("generated_at"),
                "shell_png": f'{c["case_dir"]}/outputs/shell_clean.png',
                "programa": {"open_workstations": sem.get("open_workstations"),
                             "target_headcount": sem.get("target_headcount"),
                             "rooms": sem.get("rooms")},
                "alternativas": []}
        for a in ALTS:
            d = os.path.join(base, "alternatives", a)
            tr, q, nf = _j(os.path.join(d, "traceability.json")), _j(os.path.join(d, "quality.json")), \
                _j(os.path.join(d, "no_fit.json"))
            png = f'{c["case_dir"]}/layouts/{c["run"]}/alternatives/{a}/layout_commercial.png'
            tec = f'{c["case_dir"]}/layouts/{c["run"]}/alternatives/{a}/layout_geometry.png'
            fila["alternativas"].append({
                "alt": a, "nombre": NOMBRE[a],
                "status": "FIT" if tr else (nf or {}).get("status", "NO_EJECUTADO"),
                "layout_sha256": (tr or {}).get("layout_sha256"),
                "png": png if os.path.exists(os.path.join(ROOT, png)) else None,
                "png_tecnica": tec if os.path.exists(os.path.join(ROOT, tec)) else None,
                "quality": {k: (q or {}).get(k) for k in
                            ("open_seats", "program_complete", "unallocated_pct", "residual_spaces_m2",
                             "daylight_score", "fragmentation", "facade_use", "architectural_score",
                             "circulation_pct", "waste_pct")} if q else None,
                "explicacion": (nf or {}).get("explicacion"),
            })
        out["casos"].append(fila)
    return out


def hoja(idx):
    import cv2
    import numpy as np
    import unicodedata

    def asc(t):
        t = (t or "").replace("·", "-").replace("²", "2").replace("—", "-")
        return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")

    CW, CH, PADT, PADL = 1000, 720, 130, 40
    INK, MUTED, LINE, BAD, GOOD = (48, 36, 29), (128, 116, 107), (212, 204, 200), (47, 69, 181), (79, 109, 47)
    filas = len(idx["casos"])
    W, H = PADL * 2 + 4 * CW, PADT + filas * (CH + 96)
    b = np.full((H, W, 3), 255, np.uint8)

    def txt(t, org, sz=0.7, col=INK, w=2):
        cv2.putText(b, asc(t), org, cv2.FONT_HERSHEY_DUPLEX, sz, col, w, cv2.LINE_AA)

    def fit(im, w, h):
        k = min(w / im.shape[1], h / im.shape[0])
        r = cv2.resize(im, (max(1, int(im.shape[1] * k)), max(1, int(im.shape[0] * k))), interpolation=cv2.INTER_AREA)
        o = np.full((h, w, 3), 255, np.uint8)
        y, x = (h - r.shape[0]) // 2, (w - r.shape[1]) // 2
        o[y:y + r.shape[0], x:x + r.shape[1]] = r
        return o

    txt("ESCALIMETRO E26 - HOJA DE REVISION ARQUITECTONICA", (PADL, 52), 1.1, INK, 2)
    txt("Dos casos, tres alternativas cada uno. Escala asumida, sin confirmar. Test-fit conceptual, "
        "no proyecto de arquitectura.", (PADL, 92), 0.6, MUTED, 1)
    for i, c in enumerate(idx["casos"]):
        y0 = PADT + i * (CH + 96)
        p = c["programa"]
        txt(c["titulo"], (PADL, y0 + 30), 0.85, INK, 2)
        txt(f'{c["brief_id"]} - {p.get("open_workstations")} puestos - '
            f'{(p.get("rooms") or {}).get("private_office", 0)} privados - '
            f'{sum((p.get("rooms") or {}).values())} recintos', (PADL, y0 + 60), 0.55, MUTED, 1)
        cols = [("SHELL", c["shell_png"], None)] + [(f'{a["alt"]} {a["nombre"]}', a["png"], a) for a in c["alternativas"]]
        for j, (lab, png, alt) in enumerate(cols):
            x = PADL + j * CW
            yy = y0 + 78
            txt(lab, (x + 10, yy + 22), 0.72, INK, 2)
            if alt:
                st = alt["status"]
                txt(st, (x + 260, yy + 22), 0.62, GOOD if st == "FIT" else BAD, 2)
            if png and os.path.exists(os.path.join(ROOT, png)):
                b[yy + 34:yy + 34 + CH - 130, x + 8:x + 8 + CW - 24] = fit(
                    cv2.imread(os.path.join(ROOT, png)), CW - 24, CH - 130)
            else:
                cv2.rectangle(b, (x + 8, yy + 34), (x + CW - 16, yy + CH - 96), LINE, 2)
                if alt:
                    yl = yy + 90
                    for ln in _wrap(alt.get("explicacion") or "sin layout", 44):
                        txt(ln, (x + 24, yl), 0.5, MUTED, 1); yl += 26
            if alt and alt.get("quality"):
                q = alt["quality"]
                txt(f'sin asignar {q["unallocated_pct"]}% - residual {q["residual_spaces_m2"]}m2 - '
                    f'circ {q["circulation_pct"]}% - arq {q["architectural_score"]}',
                    (x + 10, y0 + CH + 42), 0.45, MUTED, 1)
                txt(f'sha {(alt["layout_sha256"] or "")[:16]}', (x + 10, y0 + CH + 66), 0.45, MUTED, 1)
        cv2.line(b, (PADL, y0 + CH + 80), (W - PADL, y0 + CH + 80), LINE, 1)
    p = os.path.join(ROOT, "cases", "E26", "E26_REVIEW_SHEET.png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    cv2.imwrite(p, b)
    return p, b.shape


def _wrap(t, n):
    out, line = [], ""
    for w in (t or "").split():
        if len(line) + len(w) + 1 > n:
            out.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def main():
    idx = indice()
    os.makedirs(os.path.join(ROOT, "review"), exist_ok=True)
    p = os.path.join(ROOT, "review", "review_index.json")
    json.dump(idx, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("escrito", p)
    for c in idx["casos"]:
        for a in c["alternativas"]:
            print(f'  {c["case_id"]} {a["alt"]}: {a["status"]} · sha {(a["layout_sha256"] or "-")[:16]}')
    print(hoja(idx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
