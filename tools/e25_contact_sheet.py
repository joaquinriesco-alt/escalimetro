"""E25 §16 — UNA lámina de contacto 3×3.

Filas = briefs (DENSO / EQUILIBRADO / EJECUTIVO). Columnas = alternativas (A / B / C).
Una celda sin layout dice NO_FIT y por qué. No se fabrica ningún layout para llenar la grilla."""
from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

CASE = os.path.join(ROOT, "cases", "001_gps_403")
FILAS = ["DENSO", "EQUILIBRADO", "EJECUTIVO"]
COLS = ["A", "B", "C"]
CW, CH = 1180, 820                       # celda
PADL, PADT = 300, 150                    # rótulos de fila / cabecera
INK, MUTED, LINE, BAD = (48, 36, 29), (128, 116, 107), (212, 204, 200), (47, 69, 181)
GOOD = (79, 109, 47)


def _ascii(t: str) -> str:
    """Las fuentes Hershey de OpenCV no tienen acentos ni ·: se translitera para que la lámina se lea.
    Es SÓLO tipografía de esta lámina; los artefactos JSON conservan el texto íntegro."""
    import unicodedata
    t = (t.replace("·", "-").replace("—", "-").replace("≥", ">=").replace("≤", "<=")
          .replace("²", "2").replace("§", "S").replace("“", '"').replace("”", '"'))
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")


def _txt(img, t, org, sz=0.8, col=INK, w=2):
    cv2.putText(img, _ascii(t), org, cv2.FONT_HERSHEY_DUPLEX, sz, col, w, cv2.LINE_AA)


def _fit(im, w, h):
    k = min(w / im.shape[1], h / im.shape[0])
    r = cv2.resize(im, (max(1, int(im.shape[1] * k)), max(1, int(im.shape[0] * k))),
                   interpolation=cv2.INTER_AREA)
    out = np.full((h, w, 3), 255, np.uint8)
    y, x = (h - r.shape[0]) // 2, (w - r.shape[1]) // 2
    out[y:y + r.shape[0], x:x + r.shape[1]] = r
    return out


def _wrap(t, n):
    out, line = [], ""
    for w in t.split():
        if len(line) + len(w) + 1 > n:
            out.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def celda(brief, alt):
    d = os.path.join(CASE, "layouts", f"E25_{brief}", "alternatives", alt)
    png = os.path.join(d, "layout_commercial.png")
    nf = os.path.join(d, "no_fit.json")
    if os.path.exists(png):
        im = _fit(cv2.imread(png), CW - 24, CH - 96)
        met = json.load(open(os.path.join(d, "metrics.json"), encoding="utf-8"))
        pc = met["program_completeness"]
        cell = np.full((CH, CW, 3), 255, np.uint8)
        cell[70:70 + im.shape[0], 12:12 + im.shape[1]] = im
        _txt(cell, f"FIT · puestos {pc['open_seats']} · programa "
                   f"{'completo' if pc['complete'] else 'INCOMPLETO'}", (16, 40), 0.72,
             GOOD if pc["complete"] else BAD, 2)
        _txt(cell, f"violaciones {met['hard_constraint_violations']} · colisiones {met['collisions']} · "
                   f"circulación {'conectada' if met['circulation_connectivity'] else 'ROTA'}",
             (16, CH - 20), 0.6, MUTED, 1)
        return cell
    cell = np.full((CH, CW, 3), 250, np.uint8)
    cv2.rectangle(cell, (12, 12), (CW - 12, CH - 12), LINE, 2)
    razon = "no se ejecutó esta combinación"
    nota = ""
    titulo, sub = "NO EJECUTADO", ""
    if os.path.exists(nf):
        j = json.load(open(nf, encoding="utf-8"))
        titulo = j.get("status", "NO EJECUTADO")
        sub = ""
        razon = j.get("explicacion", "") + f"   [solver: {j.get('solver_status')}]"
        nota = ("Espacio de candidatos INCOMPLETO: " + (j.get("candidate_space") or {}).get(
            "por_que_incompleto", "") + ". Por eso este estado NO autoriza decir que el programa no cabe."
        ) if not (j.get("candidate_space") or {}).get("complete") else nota
    _txt(cell, titulo, (34, 96), 1.15, BAD, 3)
    if sub:
        _txt(cell, sub, (34, 126), 0.55, MUTED, 1)
    y = 176
    for ln in _wrap(razon, 52):
        _txt(cell, ln, (34, y), 0.68, INK, 1); y += 34
    y += 14
    for ln in _wrap(nota, 58):
        _txt(cell, ln, (34, y), 0.56, MUTED, 1); y += 28
    y += 20
    _txt(cell, "No se fabrica un layout para llenar la grilla (E25 §16).", (34, y), 0.56, MUTED, 1)
    return cell


def main():
    W = PADL + 3 * CW
    H = PADT + 3 * CH
    board = np.full((H, W, 3), 255, np.uint8)
    _txt(board, "ESCALIMETRO  E25  ·  TRES BRIEFS x TRES ALTERNATIVAS  ·  OFICINA 403 (GPS PROPERTY)",
         (40, 58), 1.0, INK, 2)
    _txt(board, "Mismo shell, mismo motor, misma politica de diseno. Lo unico que cambia por fila es "
                "el BRIEF DEL CLIENTE. Escala asumida, sin confirmar.", (40, 100), 0.62, MUTED, 1)
    for j, alt in enumerate(COLS):
        _txt(board, f"{alt}", (PADL + j * CW + 16, PADT - 18), 1.1, INK, 2)
        _txt(board, {"A": "EFICIENTE", "B": "BALANCEADO", "C": "COLABORATIVO"}[alt],
             (PADL + j * CW + 60, PADT - 18), 0.75, MUTED, 1)
    for i, b in enumerate(FILAS):
        info = ""
        p = os.path.join(CASE, "layouts", f"E25_{b}", "program_compiled.json")
        if os.path.exists(p):
            pr = json.load(open(p, encoding="utf-8"))
            s = pr["brief_semantics"]
            info = f"{s['open_workstations']} puestos · {s['rooms'].get('private_office', 0)} privados"
        y = PADT + i * CH + 60
        _txt(board, b, (28, y), 0.95, INK, 2)
        _txt(board, info, (28, y + 34), 0.55, MUTED, 1)
        if os.path.exists(p):
            _txt(board, f"{pr['target_headcount']} personas decl.", (28, y + 62), 0.55, MUTED, 1)
        for j, alt in enumerate(COLS):
            c = celda(b, alt)
            board[PADT + i * CH:PADT + (i + 1) * CH, PADL + j * CW:PADL + (j + 1) * CW] = c
    for i in range(4):
        cv2.line(board, (PADL, PADT + i * CH), (W, PADT + i * CH), LINE, 2)
    for j in range(4):
        cv2.line(board, (PADL + j * CW, PADT), (PADL + j * CW, H), LINE, 2)
    out = os.path.join(ROOT, "cases", "E25", "E25_CONTACT_SHEET_3x3.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cv2.imwrite(out, board)
    print(out, board.shape)
    return 0


if __name__ == "__main__":
    sys.exit(main())
