#!/usr/bin/env python3
"""E45 — fotografía la web piloto con datos DEMO y deja las capturas en `reports/E45_screens/`.

Todo lo que aparece en las capturas es sintético y está marcado DEMO en la propia interfaz: los
casos se crean con `demo=True`, viven en un directorio temporal (nunca en `.data-*` ni en el
manifiesto real) y la campaña no los cuenta en ningún N. El «motor» de CREAR es el FIXTURE de E37 y
el análisis/trazado de MEJORAR se sustituye por dibujos de ejemplo: las capturas sirven para juzgar
la INTERFAZ, no la calidad de ningún resultado.

Uso:  .venv/bin/python scripts/e45_demo_screens.py [directorio_de_salida]
Necesita Chromium (`chromium` en el PATH, o CHROMIUM_BIN).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "reports", "E45_screens")
DATA = tempfile.mkdtemp(prefix="e45-demo-")
os.environ.update(ESCALIMETRO_DATA_DIR=DATA, ESCALIMETRO_DEV="1", ESCALIMETRO_PASSWORD="",
                  ESCALIMETRO_MIGRATE="0", ESCALIMETRO_RECON_FIXTURE="1")
for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "BFL_API_KEY"):
    os.environ.pop(k, None)                      # el caso BLOQUEADO es real: sin credencial
sys.path[:0] = [ROOT, os.path.join(ROOT, "src")]

import cv2                                       # noqa: E402
import numpy as np                               # noqa: E402

from webapp import campaign, store               # noqa: E402
from webapp.app import create_app                # noqa: E402
from webapp.domain import commercial, floorplan, ingest, properties   # noqa: E402

LISTA = {"v": False}


# --------------------------------------------------------------------------------------------
# material de ejemplo (sintético)
# --------------------------------------------------------------------------------------------
def _png(img) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


def plano_tecnico(seed: int = 0) -> bytes:
    """Un plano «feo»: papel amarillento, trazo fino, cotas y rótulos de arquitectura."""
    rng = np.random.default_rng(seed)
    img = np.full((620, 900, 3), (232, 238, 244), np.uint8)
    img += rng.integers(0, 10, img.shape, dtype=np.uint8)
    c = (60, 60, 70)
    cv2.rectangle(img, (60, 60), (840, 560), c, 5)
    for (x1, y1, x2, y2) in ((300, 60, 300, 330), (60, 330, 520, 330), (520, 330, 520, 560),
                             (520, 200, 840, 200), (680, 200, 680, 330)):
        cv2.line(img, (x1, y1), (x2, y2), c, 4)
    for x in range(60, 840, 40):
        cv2.line(img, (x, 585), (x, 595), c, 1)
    cv2.line(img, (60, 590), (840, 590), c, 1)
    for i, (txt, org) in enumerate((("OF. 301", (110, 200)), ("SALA REUN.", (360, 140)),
                                    ("OPEN SPACE", (170, 460)), ("CORE", (590, 470)),
                                    ("BAÑO", (560, 270)), ("%.1f m2" % (118 + seed), (720, 130)))):
        cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (90, 60, 40), 1, cv2.LINE_AA)
    cv2.putText(img, "PLANTA NIVEL 3 · ESC 1:100", (60, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (120, 120, 130), 1, cv2.LINE_AA)
    return _png(img)


def foto(i: int) -> bytes:
    """Una «foto» de ejemplo: un ambiente plano con ventana y mueble, rotulado DEMO."""
    pal = [(214, 226, 236), (205, 218, 205), (232, 222, 208), (222, 212, 226), (210, 226, 226)]
    img = np.full((540, 720, 3), pal[i % len(pal)], np.uint8)
    img[400:] = (150 + 8 * (i % 4), 140, 132)
    cv2.rectangle(img, (80 + 30 * (i % 3), 70), (330 + 30 * (i % 3), 300), (240, 246, 250), -1)
    cv2.rectangle(img, (80 + 30 * (i % 3), 70), (330 + 30 * (i % 3), 300), (120, 120, 120), 6)
    cv2.rectangle(img, (420, 250 + 8 * (i % 3)), (640, 420), (80, 70, 60), -1)
    cv2.putText(img, "FOTO DEMO %d" % (i + 1), (24, 515), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (255, 255, 255), 2, cv2.LINE_AA)
    return _png(img)


def plano_real(seed: int = 0) -> bytes:
    img = np.full((600, 860, 3), 255, np.uint8)
    c = (35, 35, 35)
    cv2.rectangle(img, (50, 50), (810, 550), c, 6)
    for (x1, y1, x2, y2) in ((330, 50, 330, 330), (50, 330, 540, 330), (540, 330, 540, 550),
                             (540, 200, 810, 200)):
        cv2.line(img, (x1, y1), (x2, y2), c, 4)
    for txt, org in (("Living", (120, 190)), ("Cocina", (400, 190)), ("Dormitorio", (150, 450)),
                     ("Bano", (610, 270)), ("Dormitorio 2", (590, 450))):
        cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7, c, 2, cv2.LINE_AA)
    cv2.putText(img, "PLANO REAL DEMO %d" % seed, (60, 590), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1,
                cv2.LINE_AA)
    return _png(img)


def svg_corporativo() -> str:
    """El «después» de ejemplo: blanco, muros limpios, zonas suaves. Sólo ilustra la interfaz."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 640" width="900" height="640">'
            '<rect width="900" height="640" fill="#fff"/>'
            '<rect x="70" y="70" width="760" height="500" fill="#fff" stroke="#1d2430" stroke-width="10"/>'
            '<path d="M310 70V330M70 330H530M530 330V570M530 210H830" stroke="#1d2430" stroke-width="6" fill="none"/>'
            '<rect x="82" y="82" width="216" height="236" fill="#f3e3de"/>'
            '<rect x="322" y="82" width="496" height="116" fill="#e8edf2"/>'
            '<rect x="542" y="222" width="276" height="336" fill="#e8f0ea"/>'
            '<rect x="82" y="342" width="436" height="216" fill="#f4f1e6"/>'
            '<g fill="#1d2430" font-family="system-ui,sans-serif" font-size="22" text-anchor="middle">'
            '<text x="190" y="205">Sala</text><text x="570" y="150">Puestos</text>'
            '<text x="680" y="400">Reunión</text><text x="300" y="460">Open space</text></g>'
            '<text x="70" y="615" font-family="system-ui,sans-serif" font-size="18" fill="#667080">'
            'EJEMPLO DEMO · Plano Corporativo</text></svg>')


# --------------------------------------------------------------------------------------------
# sustitutos (sólo para fotografiar): el análisis del motor y el trazado
# --------------------------------------------------------------------------------------------
def _auto_prepare(pid):
    cid = properties.require(pid)["floorplan_case_id"]
    if LISTA["v"]:
        d = os.path.join(store.case_dir(cid), "outputs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
            json.dump({"shell_readiness": {"ready_for_layout": True,
                                           "requires_confirmation": []}}, fh)
    return {"ready": LISTA["v"]}


class _A:
    area = 118.0


class _S:
    usable = _A()


ingest.auto_prepare = _auto_prepare
floorplan._shell_of = lambda cid: _S()
commercial.commercial_svg = lambda *a, **k: svg_corporativo()


# --------------------------------------------------------------------------------------------
# casos DEMO en distintos estados
# --------------------------------------------------------------------------------------------
def _esperar(case_id: str) -> None:
    for _ in range(120):
        campaign.settle(case_id)
        if campaign.pending_run(case_id) is None:
            return
        time.sleep(0.25)
    raise RuntimeError("la corrida demo no terminó")


def _eval(cid, plano, ux):
    campaign.record(cid, "evaluation", {"schema": campaign.PILOT_SCHEMA, **plano})
    campaign.record(cid, "ux_evaluation", ux)


def sembrar() -> dict:
    ids = {}
    up = lambda *a, **k: campaign.import_upload(*a, demo=True, author="demo", **k)   # noqa: E731
    # MEJORAR
    ids["imp_cargado"] = up("IMPROVE", [("plano.png", plano_tecnico(1))])
    ids["imp_revision"] = up("IMPROVE", [("plano.png", plano_tecnico(2))])
    LISTA["v"] = False
    campaign.start_improve(ids["imp_revision"])
    ids["imp_resultado"] = up("IMPROVE", [("plano.png", plano_tecnico(3))])
    LISTA["v"] = True
    campaign.start_improve(ids["imp_resultado"])
    campaign.finish_improve(ids["imp_resultado"])
    ids["imp_evaluado"] = up("IMPROVE", [("plano.png", plano_tecnico(4))])
    campaign.start_improve(ids["imp_evaluado"])
    campaign.finish_improve(ids["imp_evaluado"])
    _eval(ids["imp_evaluado"],
          {"rating": "MALO", "would_publish": False, "needed_human_correction": True,
           "human_minutes": 6.0, "comment": "Los muros quedaron limpios pero falta el núcleo."},
          {"rating": "BUENO", "understood_immediately": True, "comment": "Se entiende rápido.",
           "extra_step_comment": None, "missing_comment": "Un ejemplo de plano antes de subir."})
    campaign.record(ids["imp_evaluado"], "evaluation", {
        "schema": campaign.PILOT_SCHEMA, "rating": "BUENO", "would_publish": True,
        "needed_human_correction": True, "human_minutes": 3.0,
        "comment": "Revisado de nuevo: sirve para publicar.", "supersedes_seq": 3})
    # CREAR
    fotos = [("f%d.png" % i, foto(i)) for i in range(6)]
    ids["cre_cargado"] = up("CREATE", fotos, ground_truth=("gt.png", plano_real(1)), published_m2=118,
                            reference="Oficina en piso 5, luminosa, con vista al parque.")
    ids["cre_prereveal"] = up("CREATE", [("g%d.png" % i, foto(i + 10)) for i in range(5)],
                              ground_truth=("gt.png", plano_real(2)), published_m2=96)
    campaign.start_create(ids["cre_prereveal"], "fixture_replay", confirm_paid=True)
    _esperar(ids["cre_prereveal"])
    campaign.start_correction(ids["cre_prereveal"], "el living-comedor más grande", confirm_paid=True)
    _esperar(ids["cre_prereveal"])
    ids["cre_comparacion"] = up("CREATE", [("h%d.png" % i, foto(i + 20)) for i in range(5)],
                                ground_truth=("gt.png", plano_real(3)), published_m2=104)
    campaign.start_create(ids["cre_comparacion"], "fixture_replay", confirm_paid=True)
    _esperar(ids["cre_comparacion"])
    campaign.close_blind(ids["cre_comparacion"], campaign.last_done_run(ids["cre_comparacion"]))
    campaign.reveal(ids["cre_comparacion"], author="demo")
    ids["cre_evaluado"] = up("CREATE", [("k%d.png" % i, foto(i + 30)) for i in range(4)],
                             ground_truth=("gt.png", plano_real(4)), published_m2=88)
    campaign.start_create(ids["cre_evaluado"], "fixture_replay", confirm_paid=True)
    _esperar(ids["cre_evaluado"])
    campaign.close_blind(ids["cre_evaluado"], campaign.last_done_run(ids["cre_evaluado"]))
    campaign.reveal(ids["cre_evaluado"], author="demo")
    _eval(ids["cre_evaluado"],
          {"rating": "BUENO", "would_publish": True, "needed_human_correction": False,
           "human_minutes": 2.0, "comment": "Esquema razonable, referencial."},
          {"rating": "EXCELENTE", "understood_immediately": True, "comment": "Claro y sin fricción.",
           "extra_step_comment": None, "missing_comment": None})
    ids["cre_bloqueado"] = up("CREATE", [("b%d.png" % i, foto(i + 40)) for i in range(3)],
                              ground_truth=("gt.png", plano_real(5)))
    campaign.start_create(ids["cre_bloqueado"], "openai_direct", confirm_paid=True)   # sin clave
    return ids


def sembrar_masa() -> None:
    """20 + 20 casos DEMO: sólo para ver el panel a escala. Siguen sin contar."""
    for i in range(20):
        c = campaign.import_upload("IMPROVE", [("p.png", plano_tecnico(100 + i))], demo=True,
                                   author="demo")
        if i % 3:
            campaign.start_improve(c)
            campaign.finish_improve(c)
        d = campaign.import_upload("CREATE", [("f.png", foto(i + 100))], demo=True, author="demo",
                                   ground_truth=("g.png", plano_real(100 + i)))
        if i % 4 == 0:
            campaign.start_create(d, "fixture_replay", confirm_paid=True)
            _esperar(d)


# --------------------------------------------------------------------------------------------
# capturas
# --------------------------------------------------------------------------------------------
def _chromium() -> str:
    return os.environ.get("CHROMIUM_BIN") or shutil.which("chromium") or shutil.which(
        "chromium-browser") or shutil.which("google-chrome") or "chromium"


def _recortar(path: str, relleno: int = 48) -> None:
    """Quita el blanco sobrante de abajo: se pide una ventana alta para que entre la página entera."""
    img = cv2.imread(path)
    if img is None:
        return
    filas = np.where((img < 250).any(axis=(1, 2)))[0]
    fin = min(img.shape[0], (int(filas.max()) if len(filas) else img.shape[0]) + relleno)
    cv2.imwrite(path, img[:fin])


def foto_de(base: str, ruta: str, nombre: str, ancho: int, alto: int = 3600) -> str:
    os.makedirs(OUT, exist_ok=True)
    destino = os.path.join(OUT, nombre + ".png")
    cmd = [_chromium(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
           "--force-device-scale-factor=1", "--virtual-time-budget=4000",
           f"--window-size={ancho},{alto}", f"--screenshot={destino}", base + ruta]
    subprocess.run(cmd, check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _recortar(destino)
    return destino


def main() -> None:
    app = create_app()
    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}/lab/campaign/e44"
    try:
        with app.app_context():
            ids = sembrar()
        caso = lambda k: f"/caso/{ids[k]}"                                 # noqa: E731
        escritorio = [
            ("01_elegir", "/"), ("02_mejorar_subir", "/mejorar"), ("03_mejorar_cargado", caso("imp_cargado")),
            ("04_mejorar_revision", caso("imp_revision")), ("05_mejorar_antes_despues", caso("imp_resultado")),
            ("06_crear_subir_y_plano_real", "/crear"), ("07_crear_cargado", caso("cre_cargado")),
            ("08_crear_reconstruccion_pre_reveal", caso("cre_prereveal")),
            ("09_crear_comparacion_post_reveal", caso("cre_comparacion")),
            ("10_crear_bloqueado_sin_credencial", caso("cre_bloqueado")),
            ("11_evaluacion_resultado_y_ux_mejorar", caso("imp_evaluado")),
            ("12_evaluacion_resultado_y_ux_crear", caso("cre_evaluado")),
            ("13_panel", "/panel")]
        movil = [("m01_elegir", "/"), ("m02_mejorar_antes_despues", caso("imp_resultado")),
                 ("m03_crear_subir", "/crear"), ("m04_crear_comparacion", caso("cre_comparacion")),
                 ("m05_evaluacion", caso("imp_evaluado")), ("m06_panel", "/panel")]
        hechos = []
        for nombre, ruta in escritorio:
            hechos.append(foto_de(base, ruta, "desktop_" + nombre, 1280))
        for nombre, ruta in movil:
            hechos.append(foto_de(base, ruta, nombre.replace("m", "mobile_", 1), 390, 4200))
        with app.app_context():
            sembrar_masa()
        hechos.append(foto_de(base, "/panel", "desktop_14_panel_con_40_demo", 1280, 6000))
        n = {t: campaign.count(t) for t in campaign.TRACKS}
        print(json.dumps({"capturas": [os.path.basename(h) for h in hechos],
                          "conteos_reales_despues_de_sembrar_demo": n}, indent=1, ensure_ascii=False))
        assert all(v["listed"] == 0 and v["completed"] == 0 for v in n.values()), "una DEMO contó"
    finally:
        srv.shutdown()
        shutil.rmtree(DATA, ignore_errors=True)


if __name__ == "__main__":
    main()
