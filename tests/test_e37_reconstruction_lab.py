"""E37 — Internal Reconstruction Lab. Un bloque por criterio de aceptación de `tasks/E37.md`.

Ningún test sale a la red ni gasta: la clave de OpenAI se borra del entorno en el fixture, y los
que ejercitan el adaptador real reemplazan `providers.base.TRANSPORT` por una grabadora. La cola de
fondo se neutraliza: los tests ejecutan cada corrida a mano con `runs.execute()`.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import importlib
import io
import json
import os
import re
import sqlite3
import struct
import subprocess
import sys
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

MODULOS = ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.briefs",
           "webapp.detected", "webapp.domain.settings", "webapp.domain.entitlements",
           "webapp.domain.grants", "webapp.domain.presets", "webapp.domain.properties",
           "webapp.domain.assets", "webapp.domain.branding", "webapp.domain.fits",
           "webapp.domain.floorplan", "webapp.domain.proposal", "webapp.domain.visual",
           "webapp.domain.pilot", "webapp.providers.base", "webapp.providers.gemini",
           "webapp.providers.openai_images", "webapp.providers.bfl", "webapp.providers",
           "webapp.domain.staging", "webapp.domain.packs", "webapp.domain.reviews",
           "webapp.domain.units", "webapp.domain.interventions", "webapp.domain.ingest",
           "webapp.domain.calibration", "webapp.domain.gold", "webapp.domain.realpilot",
           "webapp.domain.lab", "webapp.benchmark", "webapp.customer", "webapp.staging_ui",
           "webapp.lab",
           "webapp.domain.reconstruction.contract", "webapp.domain.reconstruction.render",
           "webapp.domain.reconstruction.engines.base",
           "webapp.domain.reconstruction.engines.openai_direct",
           "webapp.domain.reconstruction.engines.fixture",
           "webapp.domain.reconstruction.engines",
           "webapp.domain.reconstruction.projects", "webapp.domain.reconstruction.groundtruth",
           "webapp.domain.reconstruction.runs", "webapp.reconstruction", "webapp.app")

BASE = "/lab/reconstruction"
CLAVE_FALSA = "x-prueba-e37"                  # corta a propósito: no parece una clave real


def _png(w: int = 64, h: int = 48, tinte: bytes = b"\x80\x90\xa0") -> bytes:
    raw = b"".join(b"\x00" + tinte * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _foto(i: int) -> bytes:
    """Una foto distinta por índice, con color: no parece plano y no se deduplica."""
    return _png(64, 48, bytes([(i * 37) % 200 + 20, (i * 11) % 150 + 60, 180]))


def _plano_real() -> bytes:
    """El ground truth de prueba: papel blanco con tinta. Bytes únicos para poder buscarlos."""
    raw = bytearray()
    for y in range(120):
        raw += b"\x00" + b"".join((b"\x10\x10\x10" if (x % 40 == 0 or y % 30 == 0) else b"\xff\xff\xff")
                                  for x in range(160))
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 120, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"tEXt", b"GT-ESCONDIDO\x00e37")
            + chunk(b"IEND", b""))


def _plano_de_galeria() -> bytes:
    """Un plano como los que traen las galerías de portales: papel con muros. Suficientemente
    grande y con trazo para que el clasificador no lo tome por logo."""
    import cv2
    import numpy as np
    img = np.full((300, 400, 3), 250, np.uint8)
    for x in range(20, 400, 60):
        cv2.line(img, (x, 20), (x, 280), (30, 30, 30), 3)
    for y in range(20, 300, 50):
        cv2.line(img, (20, y), (380, y), (30, 30, 30), 3)
    return cv2.imencode(".png", img)[1].tobytes()


def _mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 64


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ESCALIMETRO_DEV", "1")
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for v in ("GEMINI_API_KEY", "OPENAI_API_KEY", "BFL_API_KEY", "ESCALIMETRO_RECON_FIXTURE",
              "ESCALIMETRO_RECON_OPENAI_MODEL"):
        monkeypatch.delenv(v, raising=False)
    for m in MODULOS:
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app()


@pytest.fixture()
def client(app):
    """Como un navegador: todo POST lleva `Origin`. La guardia de la superficie falla cerrada."""
    c = app.test_client()
    c.environ_base["HTTP_ORIGIN"] = "http://localhost"
    return c


@pytest.fixture()
def dom(app, monkeypatch):
    from webapp import store
    from webapp.domain.reconstruction import (contract, engines, groundtruth, projects, render,
                                              runs)
    from webapp.domain.reconstruction.engines import fixture, openai_direct
    from webapp.providers import base as http
    encolados = []
    monkeypatch.setattr(runs, "enqueue", lambda rid: encolados.append(rid))
    return {"store": store, "contract": contract, "engines": engines, "groundtruth": groundtruth,
            "projects": projects, "render": render, "runs": runs, "fixture": fixture,
            "openai": openai_direct, "http": http, "encolados": encolados}


@pytest.fixture()
def fixture_on(monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_RECON_FIXTURE", "1")


def _crear(client, n_fotos: int = 3, gt: bool = True, extra=None) -> str:
    data = {"name": "Piso de prueba", "total_area_m2": "87", "usable_area_m2": "76",
            "bedrooms": "2", "bathrooms": "2", "levels": "1",
            "photos": [(io.BytesIO(_foto(i)), f"foto_{i:02d}.png") for i in range(n_fotos)]}
    if gt:
        data["ground_truth"] = (io.BytesIO(_plano_real()), "PLANO-REAL-SECRETO.png")
    data.update(extra or {})
    r = client.post(f"{BASE}/nuevo", data=data, content_type="multipart/form-data")
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    return re.search(r"/p/(rcp_[0-9a-f]+)", r.location).group(1)


def _generar(client, dom, pid: str, engine_id: str = "fixture_replay", **extra) -> str:
    r = client.post(f"{BASE}/p/{pid}/generar", data={"engine_id": engine_id, **extra})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    rid = r.location.rsplit("/", 1)[1]
    assert rid in dom["encolados"]
    return rid


def _corregir(client, pid: str, rid: str, texto: str, **extra) -> str:
    r = client.post(f"{BASE}/p/{pid}/r/{rid}/corregir", data={"instruction": texto, **extra})
    assert r.status_code == 302, r.get_data(as_text=True)[:800]
    return r.location.rsplit("/", 1)[1]


class Espia:
    """Un motor que anota TODO lo que recibe. Para buscar el ground truth donde no debe estar."""

    def __init__(self, dom, fixture_mod):
        base = dom["engines"].EngineAdapter
        recibidas = self.recibidas = []

        class _Espia(base):
            engine_id = "espia"
            name = "Espía de pruebas"
            capabilities = ("photos", "video", "declared_data", "correction", "clarification")

            def reconstruct(self, req):
                recibidas.append(req)
                ids = [im.asset_id for im in req.images]
                if req.mode == "CORRECTION":
                    salida = fixture_mod.correct(req.previous, req.instruction or "")
                else:
                    salida = fixture_mod.canned_plan(ids)
                return dom["engines"].EngineResult(
                    output=salida, model="espia", latency_ms=1, prompt_version="espia_v1",
                    prompt_sha256="0" * 64, request_summary={"n": len(ids)})

        self.adapter = _Espia()
        dom["engines"].register(self.adapter)


def _todo_lo_que_recibio(obj, acc=None):
    """Recorre un EngineRequest entero —dataclasses, dicts, listas, bytes, textos— y junta todo."""
    acc = [] if acc is None else acc
    if dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            _todo_lo_que_recibio(getattr(obj, f.name), acc)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            acc.append(str(k))
            _todo_lo_que_recibio(v, acc)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _todo_lo_que_recibio(v, acc)
    elif isinstance(obj, (bytes, bytearray)):
        acc.append(bytes(obj))
    elif obj is not None:
        acc.append(str(obj))
    return acc


# =================================================================================================
# 2 — aislamiento del motor histórico
# =================================================================================================
def test_el_motor_no_se_toco(client, dom):
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"el motor cambió: {out.stdout}"


def test_e37_no_importa_nada_del_motor_historico():
    carpeta = os.path.join(ROOT, "webapp", "domain", "reconstruction")
    for raiz, _, archivos in os.walk(carpeta):
        for a in archivos:
            if a.endswith(".py"):
                with open(os.path.join(raiz, a), encoding="utf-8") as fh:
                    assert "escalimetro." not in fh.read().replace("escalimetro.reconstruction", ""), a


# =================================================================================================
# 3 — proyecto persistente con inputs
# =================================================================================================
def test_un_proyecto_acepta_34_fotos_video_documentos_y_datos(client, dom):
    pid = _crear(client, n_fotos=34, extra={
        "videos": [(io.BytesIO(_mp4()), "recorrido.mp4")],
        "documents": [(io.BytesIO("Aviso original: 2D 2B, 76/87 m²".encode()), "aviso.txt")]})
    pr = dom["projects"]
    assert len(pr.assets_of(pid, pr.PHOTO)) == 34
    assert len(pr.assets_of(pid, pr.VIDEO)) == 1
    assert len(pr.assets_of(pid, pr.DOCUMENT)) == 1
    p = pr.get(pid)
    assert p["declared"] == {"total_area_m2": 87.0, "usable_area_m2": 76.0, "bedrooms": 2,
                             "bathrooms": 2, "levels": 1}
    html = client.get(f"{BASE}/p/{pid}").get_data(as_text=True)
    assert "34 foto(s)" in html and "1 video(s)" in html


def test_formatos_invalidos_se_rechazan_sin_tumbar_el_lote(client, dom):
    pid = _crear(client, n_fotos=1, gt=False)
    r = client.post(f"{BASE}/p/{pid}/inputs", content_type="multipart/form-data", data={
        "photos": [(io.BytesIO(b"no es una imagen"), "mala.png"),
                   (io.BytesIO(b"x"), "iphone.heic"),
                   (io.BytesIO(_foto(7)), "buena.png")]})
    assert r.status_code == 302
    pr = dom["projects"]
    assert len(pr.assets_of(pid, pr.PHOTO)) == 2
    html = client.get(r.location).get_data(as_text=True)
    assert "no coincide con su extensión" in html and "HEIC" in html


def test_webp_se_normaliza_y_las_fotos_repetidas_no_se_duplican(client, dom):
    import cv2
    import numpy as np
    img = np.zeros((40, 50, 3), np.uint8)
    img[:, :] = (30, 120, 200)
    webp = cv2.imencode(".webp", img)[1].tobytes()
    pid = _crear(client, n_fotos=1, gt=False)
    client.post(f"{BASE}/p/{pid}/inputs", content_type="multipart/form-data", data={
        "photos": [(io.BytesIO(webp), "portal.webp"), (io.BytesIO(_foto(0)), "otra-vez.png")]})
    fotos = dom["projects"].assets_of(pid, dom["projects"].PHOTO)
    assert len(fotos) == 2
    assert any(f["mime_type"] == "image/png" and f["original_filename"] == "portal.webp"
               for f in fotos)


def test_el_nombre_del_usuario_nunca_llega_al_disco(client, dom):
    pid = _crear(client, n_fotos=0, gt=False, extra={
        "photos": [(io.BytesIO(_foto(1)), "../../../../etc/passwd.png")]})
    a = dom["projects"].assets_of(pid)[0]
    assert "/" not in a["stored_name"] and ".." not in a["stored_name"]
    ruta = os.path.realpath(dom["projects"].asset_path(a))
    assert ruta.startswith(os.path.realpath(dom["store"].recon_dir(pid)))


def test_una_foto_que_parece_plano_se_marca(client, dom):
    pid = _crear(client, n_fotos=1, gt=False)
    blanco = _plano_de_galeria()
    client.post(f"{BASE}/p/{pid}/inputs", content_type="multipart/form-data",
                data={"photos": [(io.BytesIO(blanco), "galeria_07.png")]})
    marcadas = [a for a in dom["projects"].assets_of(pid) if a["looks_like_plan"]]
    assert len(marcadas) == 1
    assert "parece un plano" in client.get(f"{BASE}/p/{pid}").get_data(as_text=True)


def test_retirar_un_input_no_lo_borra(client, dom, fixture_on):
    pid = _crear(client, n_fotos=2)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    a = dom["projects"].assets_of(pid)[0]
    client.post(f"{BASE}/p/{pid}/asset/{a['asset_id']}/retirar")
    assert len(dom["projects"].assets_of(pid)) == 1
    assert os.path.exists(dom["projects"].asset_path(a))              # la corrida vieja lo cita
    assert a["asset_id"] in json.dumps(dom["runs"].get(rid)["inputs"])


# =================================================================================================
# 4 — el ground truth es ciego
# =================================================================================================
def test_el_ground_truth_vive_fuera_del_proyecto_y_de_sus_inputs(client, dom):
    pid = _crear(client)
    store = dom["store"]
    gt = store.q1("SELECT * FROM recon_ground_truth WHERE project_id=?", (pid,))
    assert gt and dom["projects"].get(pid)["gt_state"] == "HIDDEN_FROM_ENGINE"
    ruta = os.path.join(store.recon_gt_dir(pid), gt["stored_name"])
    assert os.path.exists(ruta)
    assert not os.path.realpath(ruta).startswith(os.path.realpath(store.recon_dir(pid)) + os.sep)
    for raiz, _, archivos in os.walk(store.recon_dir(pid)):
        for a in archivos:
            with open(os.path.join(raiz, a), "rb") as fh:
                assert fh.read() != _plano_real()
    assert all(a["sha256"] != gt["sha256"] for a in dom["projects"].assets_of(pid,
                                                                            include_retired=True))


def _secretos_del_gt(dom, pid):
    gt = dom["store"].q1("SELECT * FROM recon_ground_truth WHERE project_id=?", (pid,))
    crudo = _plano_real()
    return {
        "bytes": crudo, "b64": base64.b64encode(crudo).decode(), "sha": gt["sha256"],
        "sha16": gt["sha256"][:16], "md5": hashlib.md5(crudo).hexdigest(),     # noqa: S324
        "nombre": gt["original_filename"], "guardado": gt["stored_name"],
        "dir": dom["store"].recon_gt_dir(pid), "raiz": "reconstruction_gt",
        "marca": "GT-ESCONDIDO",
    }


def test_adversarial_ningun_motor_recibe_nada_del_ground_truth(client, dom, fixture_on):
    """Un motor espía corre una generación, una corrección ambigua, su respuesta y una segunda
    generación con video. Se busca el ground truth en todo lo que recibió: bytes, base64, sha256,
    prefijo del sha, md5, nombre, nombre guardado, carpeta y la marca embebida en el PNG."""
    espia = Espia(dom, dom["fixture"])
    pid = _crear(client, n_fotos=5, extra={"videos": [(io.BytesIO(_mp4()), "v.mp4")]})
    r1 = _generar(client, dom, pid, "espia")
    dom["runs"].execute(r1)
    r2 = _corregir(client, pid, r1, "cambia algo")                  # ambigua → pide aclaración
    dom["runs"].execute(r2)
    assert dom["runs"].get(r2)["outcome"] == "CLARIFICATION_REQUIRED"
    r3 = _corregir(client, pid, r2, "el dormitorio principal era más grande")
    dom["runs"].execute(r3)
    r4 = _generar(client, dom, pid, "espia")
    dom["runs"].execute(r4)
    assert len(espia.recibidas) == 4
    s = _secretos_del_gt(dom, pid)
    for req in espia.recibidas:
        todo = _todo_lo_que_recibio(req)
        blobs = [x for x in todo if isinstance(x, bytes)]
        textos = [x for x in todo if isinstance(x, str)]
        assert blobs, "el motor tenía que recibir fotos"
        for b in blobs:
            assert b != s["bytes"] and s["bytes"] not in b and b"GT-ESCONDIDO" not in b
        texto = "\n".join(textos)
        for k in ("b64", "sha", "sha16", "md5", "nombre", "guardado", "dir", "raiz", "marca"):
            assert s[k] not in texto, f"el motor recibió {k} del ground truth"
        # y ninguna ruta: nada que permita volver al disco
        assert dom["store"].DATA_DIR not in texto
        assert "PLANO-REAL" not in texto
    # tampoco queda en lo que la corrida guardó como su entrada
    for rid in (r1, r2, r3, r4):
        fila = dict(dom["store"].q1("SELECT * FROM recon_runs WHERE run_id=?", (rid,)))
        crudo = json.dumps(fila, default=str)
        for k in ("sha", "sha16", "nombre", "guardado", "dir", "raiz"):
            assert s[k] not in crudo, f"la corrida guardó {k} del ground truth"
    dom["engines"].unregister("espia")


def test_adversarial_la_peticion_http_de_openai_no_lleva_el_ground_truth(client, dom,
                                                                         monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    pid = _crear(client, n_fotos=3)
    llamadas = _grabar(dom, monkeypatch, dom["fixture"].canned_plan)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    assert dom["runs"].execute(rid)["status"] == "DONE"
    assert len(llamadas) == 1
    cuerpo = llamadas[0]["body"].decode("utf-8")
    s = _secretos_del_gt(dom, pid)
    for k in ("b64", "sha", "sha16", "md5", "nombre", "guardado", "dir", "raiz", "marca"):
        assert s[k] not in cuerpo, f"la petición a OpenAI llevó {k} del ground truth"
    assert cuerpo.count('"input_image"') == 3


def test_antes_del_reveal_la_ui_no_muestra_nada_del_ground_truth(client, dom, fixture_on):
    pid = _crear(client, n_fotos=3)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    r2 = _generar(client, dom, pid)
    dom["runs"].execute(r2)
    s = _secretos_del_gt(dom, pid)
    paginas = [f"{BASE}/", f"{BASE}/p/{pid}", f"{BASE}/p/{pid}/r/{rid}",
               f"{BASE}/p/{pid}/r/{rid}/status.json", f"{BASE}/p/{pid}/r/{rid}/plano.svg",
               f"{BASE}/p/{pid}/comparar?r={rid}&r={r2}"]
    for url in paginas:
        cuerpo = client.get(url).get_data(as_text=True)
        for k in ("sha", "sha16", "nombre", "guardado", "raiz"):
            assert s[k] not in cuerpo, f"{url} muestra {k} del ground truth"
        # ni una imagen ni un enlace que lo sirva (el formulario para reemplazarlo sí está)
        assert not re.search(r'(src|href)="[^"]*/plano-real"', cuerpo), url
    assert client.get(f"{BASE}/p/{pid}/plano-real").status_code == 404


def test_un_input_identico_al_ground_truth_se_rechaza_en_los_dos_sentidos(client, dom):
    pid = _crear(client, n_fotos=1)
    r = client.post(f"{BASE}/p/{pid}/inputs", content_type="multipart/form-data",
                    data={"photos": [(io.BytesIO(_plano_real()), "foto_inocente.png")]})
    assert "idéntico al ground truth" in client.get(r.location).get_data(as_text=True)
    assert len(dom["projects"].assets_of(pid)) == 1
    otro = _crear(client, n_fotos=0, gt=False, extra={
        "photos": [(io.BytesIO(_plano_real()), "galeria.png")]})
    r = client.post(f"{BASE}/p/{otro}/plano-real", content_type="multipart/form-data",
                    data={"ground_truth": (io.BytesIO(_plano_real()), "plano.png")})
    assert r.status_code == 400 and "ya está cargado como input" in r.get_data(as_text=True)


def test_runs_y_motores_no_importan_el_modulo_del_ground_truth():
    """La ceguera por construcción: lo que arma la entrada de un motor no conoce el ground truth."""
    base = os.path.join(ROOT, "webapp", "domain", "reconstruction")
    archivos = [os.path.join(base, "runs.py")] + [
        os.path.join(base, "engines", f) for f in os.listdir(os.path.join(base, "engines"))
        if f.endswith(".py")]
    for ruta in archivos:
        with open(ruta, encoding="utf-8") as fh:
            src = fh.read()
        codigo = re.sub(r'""".*?"""', "", src, flags=re.S)        # sin docstrings
        assert not re.search(r"^\s*(from|import)\s.*groundtruth", codigo, re.M), ruta
        for prohibido in ("recon_ground_truth", "recon_gt_dir", "reconstruction_gt"):
            assert prohibido not in codigo, f"{os.path.basename(ruta)} menciona {prohibido}"


# =================================================================================================
# 5 — corridas inmutables
# =================================================================================================
def test_una_corrida_guarda_su_procedencia_completa(client, dom, fixture_on):
    pid = _crear(client, n_fotos=3)
    rid = _generar(client, dom, pid)
    r = dom["runs"].execute(rid)
    assert r["status"] == "DONE" and r["outcome"] == "RECONSTRUCTED"
    for campo in ("run_id", "project_id", "engine_id", "engine_version", "engine_meta", "inputs",
                  "params", "prompt_version", "prompt_sha256", "code_commit", "created_at",
                  "started_at", "finished_at", "output", "output_sha256", "artifacts",
                  "latency_ms", "cost_basis"):
        assert r[campo] not in (None, ""), campo
    assert r["parent_run_id"] is None and r["origin"] == "INITIAL"
    assert len(r["inputs"]["photos"]) == 3
    assert all(set(f) >= {"asset_id", "sha256"} for f in r["inputs"]["photos"])
    d = dom["projects"].runs_dir(pid, rid)
    for nombre in ("output.json", "plan.svg", "request.json", "response.json"):
        with open(os.path.join(d, nombre), encoding="utf-8") as fh:
            assert hashlib.sha256(fh.read().encode("utf-8")).hexdigest() == r["artifacts"][nombre]


def test_la_base_no_deja_tocar_una_corrida_terminada(client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    conn = dom["store"].connect()
    for sql in ("UPDATE recon_runs SET output='{}' WHERE run_id=?",
                "UPDATE recon_runs SET status='FAILED' WHERE run_id=?",
                "DELETE FROM recon_runs WHERE run_id=?"):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql, (rid,))
        conn.rollback()


def test_la_identidad_de_una_corrida_no_cambia_ni_en_cola(client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    conn = dom["store"].connect()
    for sql in ("UPDATE recon_runs SET inputs='{}' WHERE run_id=?",
                "UPDATE recon_runs SET engine_id='otro' WHERE run_id=?",
                "UPDATE recon_runs SET params='{\"model\": \"otro\"}' WHERE run_id=?",
                "UPDATE recon_runs SET parent_run_id='x' WHERE run_id=?"):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql, (rid,))
        conn.rollback()


def test_ejecutar_otra_vez_no_cambia_nada_y_regenerar_crea_otra_corrida(client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    a = dom["runs"].execute(rid)
    b = dom["runs"].execute(rid)
    assert a == b
    rid2 = _generar(client, dom, pid)
    dom["runs"].execute(rid2)
    corridas = dom["runs"].of_project(pid)
    assert [c["seq"] for c in corridas] == [1, 2]
    assert corridas[0]["run_id"] == rid


def test_el_plano_guardado_no_cambia_aunque_cambie_el_dibujo(client, dom, fixture_on,
                                                              monkeypatch):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    antes = client.get(f"{BASE}/p/{pid}/r/{rid}/plano.svg").data
    monkeypatch.setattr(dom["render"], "svg", lambda *a, **k: "<svg>OTRO</svg>")
    assert client.get(f"{BASE}/p/{pid}/r/{rid}/plano.svg").data == antes
    assert hashlib.sha256(antes).hexdigest() == dom["runs"].get(rid)["artifacts"]["plan.svg"]


def test_un_motor_que_falla_deja_la_corrida_failed_sin_resultado(client, dom, fixture_on,
                                                                 monkeypatch):
    pid = _crear(client)
    rid = _generar(client, dom, pid)

    def roto(self, req):
        raise dom["engines"].EngineError("PROVIDER", "se cayó la red")
    monkeypatch.setattr(type(dom["engines"].get("fixture_replay")), "reconstruct", roto)
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and r["output"] is None and "se cayó la red" in r["error"]
    html = client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)
    assert "La corrida falló" in html and "no se inventa" in html


def test_una_salida_que_no_cumple_el_contrato_no_se_maquilla(client, dom, fixture_on,
                                                              monkeypatch):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    malo = dom["fixture"].canned_plan(["x"])
    malo["connections"][0]["to_room"] = "no-existe"

    def devuelve(self, req):
        return dom["engines"].EngineResult(output=malo, model="m", latency_ms=1,
                                           prompt_version="v", prompt_sha256="0",
                                           request_summary={})
    monkeypatch.setattr(type(dom["engines"].get("fixture_replay")), "reconstruct", devuelve)
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and "CONTRACT_INVALID" in r["error"] and r["output"] is None


# =================================================================================================
# 6 — registro de motores
# =================================================================================================
def test_la_ui_lista_lo_que_esta_registrado_sin_conocer_ningun_motor(client, dom):
    class Nuevo(dom["engines"].EngineAdapter):
        engine_id, name, pipeline = "motor_nuevo_e37", "Motor recién llegado", "colmap + vlm"
        capabilities = ("photos",)
    dom["engines"].register(Nuevo())
    pid = _crear(client, n_fotos=1, gt=False)
    for url in (f"{BASE}/", f"{BASE}/p/{pid}"):
        assert "Motor recién llegado" in client.get(url).get_data(as_text=True)
    dom["engines"].unregister("motor_nuevo_e37")
    assert "Motor recién llegado" not in client.get(f"{BASE}/").get_data(as_text=True)
    plantillas = os.path.join(ROOT, "webapp", "templates", "recon")
    for f in os.listdir(plantillas):
        with open(os.path.join(plantillas, f), encoding="utf-8") as fh:
            src = fh.read()
        assert "openai_direct" not in src and "fixture_replay" not in src, f


def test_sin_clave_openai_aparece_no_disponible_y_no_toca_la_red(client, dom, monkeypatch):
    llamadas = _grabar(dom, monkeypatch, dom["fixture"].canned_plan)
    cat = {m["engine_id"]: m for m in dom["engines"].catalog()}
    assert cat["openai_direct"]["status"] == "UNAVAILABLE"
    assert cat["openai_direct"]["reason"] == "MISSING_CREDENTIAL"
    pid = _crear(client, n_fotos=2, gt=False)
    html = client.get(f"{BASE}/p/{pid}").get_data(as_text=True)
    assert "no disponible" in html and "MISSING_CREDENTIAL" in html
    r = client.post(f"{BASE}/p/{pid}/generar",
                    data={"engine_id": "openai_direct", "confirm_paid": "1"})
    assert r.status_code == 400 and dom["runs"].of_project(pid) == [] and llamadas == []


def test_el_fixture_no_existe_sin_su_bandera(client, dom):
    assert "fixture_replay" not in [m["engine_id"] for m in dom["engines"].catalog()]
    pid = _crear(client, n_fotos=1, gt=False)
    r = client.post(f"{BASE}/p/{pid}/generar", data={"engine_id": "fixture_replay"})
    assert r.status_code == 400 and "no está registrado" in r.get_data(as_text=True)


def test_el_fixture_dice_que_no_reconstruye(client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    html = client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)
    assert "No es una reconstrucción" in html and "FIXTURE" in html


def test_el_registro_de_reconstruccion_no_se_mezcla_con_el_de_ambientacion(app):
    from webapp import providers
    assert "openai_direct" not in providers.NAMES and "fixture_replay" not in providers.NAMES


# =================================================================================================
# 7 — baseline multimodal OpenAI, sin gastar
# =================================================================================================
def _respuesta_openai(plan: dict, **extra) -> bytes:
    cuerpo = {"id": "resp_x", "model": "gpt-5.6-sol-2026-01-01", "status": "completed",
              "output": [{"type": "reasoning", "summary": []},
                         {"type": "message", "role": "assistant",
                          "content": [{"type": "output_text", "text": json.dumps(plan)}]}],
              "usage": {"input_tokens": 1234, "output_tokens": 567, "total_tokens": 1801}}
    cuerpo.update(extra)
    return json.dumps(cuerpo).encode("utf-8")


def _grabar(dom, monkeypatch, plan_fn, status: int = 200, cuerpo=None):
    llamadas = []

    def transporte(method, url, headers, body, timeout):
        llamadas.append({"method": method, "url": url, "headers": headers, "body": body,
                         "timeout": timeout})
        if cuerpo is not None:
            return status, {}, cuerpo
        pedido = json.loads(body)
        ids = [p["text"].split("id ")[1] for p in pedido["input"][0]["content"]
               if p["type"] == "input_text" and p["text"].startswith("Foto ")]
        return status, {}, _respuesta_openai(plan_fn(ids))
    monkeypatch.setattr(dom["http"], "TRANSPORT", transporte)
    return llamadas


def test_openai_arma_la_peticion_y_guarda_la_procedencia(client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    llamadas = _grabar(dom, monkeypatch, dom["fixture"].canned_plan)
    pid = _crear(client, n_fotos=4)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    r = dom["runs"].execute(rid)
    assert r["status"] == "DONE" and r["outcome"] == "RECONSTRUCTED", r["error"]
    (ll,) = llamadas
    assert ll["url"] == "https://api.openai.com/v1/responses" and ll["method"] == "POST"
    assert ll["headers"]["Authorization"] == f"Bearer {CLAVE_FALSA}"
    body = json.loads(ll["body"])
    assert body["model"] == "gpt-5.6-sol" and body["store"] is False
    assert body["text"]["format"]["type"] == "json_schema" and body["text"]["format"]["strict"]
    assert body["text"]["format"]["schema"] == dom["contract"].SCHEMA
    imagenes = [p for p in body["input"][0]["content"] if p["type"] == "input_image"]
    assert len(imagenes) == 4 and all(i["image_url"].startswith("data:image/jpeg;base64,")
                                      for i in imagenes)
    assert "87" in body["input"][0]["content"][0]["text"]             # los datos declarados
    assert r["engine_meta"]["model"] == "gpt-5.6-sol"
    assert r["request_summary"]["model_reported"] == "gpt-5.6-sol-2026-01-01"
    assert r["prompt_version"] == dom["openai"].PROMPT_VERSION and len(r["prompt_sha256"]) == 64
    assert r["usage"] == {"input_tokens": 1234, "output_tokens": 567, "total_tokens": 1801}
    assert r["cost_usd"] is None and r["cost_basis"] == "unknown"
    assert r["latency_ms"] is not None
    # la clave no queda en ningún lado
    fila = json.dumps(dict(dom["store"].q1("SELECT * FROM recon_runs WHERE run_id=?", (rid,))),
                      default=str)
    assert CLAVE_FALSA not in fila
    for raiz, _, archivos in os.walk(dom["store"].recon_dir(pid)):
        for a in archivos:
            if a.endswith((".json", ".svg")):
                with open(os.path.join(raiz, a), encoding="utf-8") as fh:
                    assert CLAVE_FALSA not in fh.read(), a
    for url in (f"{BASE}/", f"{BASE}/p/{pid}", f"{BASE}/p/{pid}/r/{rid}"):
        assert CLAVE_FALSA not in client.get(url).get_data(as_text=True)


def test_el_modelo_se_configura_por_entorno_y_queda_congelado(client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    monkeypatch.setenv("ESCALIMETRO_RECON_OPENAI_MODEL", "gpt-otro-modelo")
    llamadas = _grabar(dom, monkeypatch, dom["fixture"].canned_plan)
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    monkeypatch.setenv("ESCALIMETRO_RECON_OPENAI_MODEL", "gpt-cambiado-despues")
    dom["runs"].execute(rid)
    assert json.loads(llamadas[0]["body"])["model"] == "gpt-otro-modelo"
    assert dom["runs"].get(rid)["params"]["model"] == "gpt-otro-modelo"


def test_sin_confirmar_el_gasto_no_hay_corrida(client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    llamadas = _grabar(dom, monkeypatch, dom["fixture"].canned_plan)
    pid = _crear(client, n_fotos=1)
    r = client.post(f"{BASE}/p/{pid}/generar", data={"engine_id": "openai_direct"})
    assert r.status_code == 400 and "confirmar el gasto" in r.get_data(as_text=True)
    assert dom["runs"].of_project(pid) == [] and llamadas == []


def test_si_la_clave_desaparece_antes_de_ejecutar_no_hay_red(client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    llamadas = _grabar(dom, monkeypatch, dom["fixture"].canned_plan)
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    monkeypatch.delenv("OPENAI_API_KEY")
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and "MISSING_CREDENTIAL" in r["error"] and llamadas == []


@pytest.mark.parametrize("caso", ["incompleta", "negativa", "no_json", "http_500"])
def test_respuestas_malas_del_proveedor_dejan_la_corrida_failed(client, dom, monkeypatch, caso):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    cuerpos = {
        "incompleta": (200, json.dumps({"status": "incomplete", "incomplete_details":
                                        {"reason": "max_output_tokens"}, "output": []})),
        "negativa": (200, json.dumps({"status": "completed", "output": [{"type": "message",
                     "content": [{"type": "refusal", "refusal": "no puedo"}]}]})),
        "no_json": (200, json.dumps({"status": "completed", "output": [{"type": "message",
                    "content": [{"type": "output_text", "text": "esto no es json"}]}]})),
        # el proveedor refleja la clave en el error: tiene que quedar tapada
        "http_500": (500, json.dumps({"error": {"message": f"clave {CLAVE_FALSA} rechazada"}})),
    }
    st, cuerpo = cuerpos[caso]
    _grabar(dom, monkeypatch, None, status=st, cuerpo=cuerpo.encode())
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and r["output"] is None
    assert CLAVE_FALSA not in (r["error"] or "")


def test_las_fotos_se_reducen_antes_de_mandarse(client, dom, monkeypatch):
    import cv2
    import numpy as np
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    grande = np.zeros((2400, 3200, 3), np.uint8)
    grande[:] = (40, 90, 160)
    pid = _crear(client, n_fotos=0, extra={
        "photos": [(io.BytesIO(cv2.imencode(".jpg", grande)[1].tobytes()), "grande.jpg")]})
    llamadas = _grabar(dom, monkeypatch, dom["fixture"].canned_plan)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    r = dom["runs"].execute(rid)
    (img,) = r["request_summary"]["images"]
    assert max(img["width"], img["height"]) == 1600
    assert r["request_summary"]["images_sent"] == 1 and llamadas


# =================================================================================================
# 8 — salida útil
# =================================================================================================
def test_una_corrida_muestra_plano_recintos_conexiones_incertidumbre_y_procedencia(
        client, dom, fixture_on):
    pid = _crear(client, n_fotos=3)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    html = client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)
    assert f"{BASE}/p/{pid}/r/{rid}/plano.svg" in html
    for texto in ("Recintos (9 · 8 ubicados)", "Dormitorio principal", "Conexiones",
                  "Incertidumbres", "la franja de baños", "sin ubicar", "Procedencia técnica",
                  "fixture_replay_v1", "evidencia: foto 1, foto 2"):
        assert texto in html, texto
    svg = client.get(f"{BASE}/p/{pid}/r/{rid}/plano.svg").get_data(as_text=True)
    assert svg.startswith("<svg") and "Sin ubicar (1)" in svg and "no es un levantamiento" in svg


def test_evidencia_insuficiente_es_un_resultado_valido(client, dom, fixture_on, monkeypatch):
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid)
    nada = dom["fixture"].canned_plan([])
    nada.update({"outcome": "INSUFFICIENT_EVIDENCE", "rooms": [], "connections": [],
                 "relations": [], "summary": "Dos fotos del living no alcanzan.",
                 "missing_evidence": ["fotos de dormitorios", "fotos de baños"]})

    def devuelve(self, req):
        return dom["engines"].EngineResult(output=nada, model="m", latency_ms=1,
                                           prompt_version="v", prompt_sha256="0",
                                           request_summary={})
    monkeypatch.setattr(type(dom["engines"].get("fixture_replay")), "reconstruct", devuelve)
    r = dom["runs"].execute(rid)
    assert r["status"] == "DONE" and r["outcome"] == "INSUFFICIENT_EVIDENCE"
    html = client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)
    assert "Evidencia insuficiente" in html and "fotos de dormitorios" in html


def test_el_svg_escapa_lo_que_escribe_el_motor(dom):
    plan = dom["fixture"].canned_plan(["a"])
    plan["rooms"][0]["label"] = '<script>alert("x")</script>'
    plan["rooms"][8]["uncertainty"] = '"><img src=x onerror=alert(1)>'
    svg = dom["render"].svg(plan, caption="<b>pie</b>")
    assert "<script>" not in svg and "<img" not in svg and "<b>" not in svg
    assert "&lt;script&gt;" in svg


def test_el_contrato_rechaza_lo_que_no_es_honesto(dom):
    c, plan = dom["contract"], dom["fixture"].canned_plan
    malos = []
    p = plan(["a"]); p["rooms"][0]["confidence"] = 1.4; malos.append(p)
    p = plan(["a"]); p["rooms"][0]["polygon"] = [[0, 0], [2, 0], [2, 2]]; malos.append(p)
    p = plan(["a"]); p["rooms"][1]["id"] = "r1"; malos.append(p)
    p = plan(["a"])
    for r in p["rooms"]:
        r["polygon"] = None
    malos.append(p)                                        # RECONSTRUCTED sin nada ubicado
    p = plan(["a"]); p["outcome"] = "CLARIFICATION_REQUIRED"; malos.append(p)
    p = plan(["a"]); p["extra"] = 1; malos.append(p)
    for m in malos:
        with pytest.raises(c.ContractError):
            c.validate(m)
    avisos = c.validate(plan(["a"]), known_asset_ids=("b",))
    assert any("no recibió" in a for a in avisos)


# =================================================================================================
# 9 — evaluación humana con historial
# =================================================================================================
def test_una_calificacion_vigente_y_el_historial_completo(client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    assert client.post(f"{BASE}/p/{pid}/r/{rid}/calificar",
                       data={"rating": "BUENO"}).status_code == 400          # todavía en cola
    dom["runs"].execute(rid)
    client.post(f"{BASE}/p/{pid}/r/{rid}/calificar", data={"rating": "BUENO"})
    client.post(f"{BASE}/p/{pid}/r/{rid}/calificar",
                data={"rating": "MALO", "comment": "la franja de baños no existe"})
    assert client.post(f"{BASE}/p/{pid}/r/{rid}/calificar",
                       data={"rating": "GENIAL"}).status_code == 400
    runs = dom["runs"]
    assert runs.current_rating(rid)["rating"] == "MALO"
    assert [h["rating"] for h in runs.rating_history(rid)] == ["MALO", "BUENO"]
    assert runs.current_rating(rid)["output_sha256"] == runs.get(rid)["output_sha256"]
    with pytest.raises(sqlite3.DatabaseError):
        dom["store"].connect().execute("UPDATE recon_ratings SET rating='EXCELENTE'")
    dom["store"].connect().rollback()


# =================================================================================================
# 10 y 11 — corrección por prompt y ambigüedad
# =================================================================================================
def test_corregir_crea_una_hija_y_no_toca_a_la_madre(client, dom, fixture_on):
    espia = Espia(dom, dom["fixture"])
    pid = _crear(client)
    rid = _generar(client, dom, pid, "espia")
    dom["runs"].execute(rid)
    madre_antes = dict(dom["store"].q1("SELECT * FROM recon_runs WHERE run_id=?", (rid,)))
    hija = _corregir(client, pid, rid, "el dormitorio principal era más grande")
    h = dom["runs"].execute(hija)
    madre_despues = dict(dom["store"].q1("SELECT * FROM recon_runs WHERE run_id=?", (rid,)))
    assert madre_antes == madre_despues
    assert h["parent_run_id"] == rid and h["origin"] == "CORRECTION"
    assert h["correction_text"] == "el dormitorio principal era más grande"
    assert h["inputs"] == dom["runs"].get(rid)["inputs"]
    req = espia.recibidas[-1]
    assert req.mode == "CORRECTION" and req.previous == dom["runs"].get(rid)["output"]
    assert req.instruction == "el dormitorio principal era más grande"
    grande = {r["id"]: r for r in h["output"]["rooms"]}["r5"]
    chico = {r["id"]: r for r in dom["runs"].get(rid)["output"]["rooms"]}["r5"]
    assert grande["area_m2"] > chico["area_m2"]
    html = client.get(f"{BASE}/p/{pid}/r/{hija}").get_data(as_text=True)
    assert "Entendió" in html and "Linaje" in html
    dom["engines"].unregister("espia")


def test_una_correccion_ambigua_pide_aclaracion_y_la_respuesta_es_otra_hija(
        client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    duda = _corregir(client, pid, rid, "arregla eso")
    d = dom["runs"].execute(duda)
    assert d["status"] == "DONE" and d["outcome"] == "CLARIFICATION_REQUIRED"
    html = client.get(f"{BASE}/p/{pid}/r/{duda}").get_data(as_text=True)
    assert "El motor pregunta" in html and "Crear corrida hija" in html
    respuesta = _corregir(client, pid, duda, "el baño principal, más chico")
    r = dom["runs"].execute(respuesta)
    assert r["outcome"] == "RECONSTRUCTED" and r["parent_run_id"] == duda
    assert dom["runs"].prompts_in_lineage(r) == 2


def test_corregir_exige_texto_confirmacion_y_una_corrida_terminada(client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    llamadas = _grabar(dom, monkeypatch, dom["fixture"].canned_plan)
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    assert client.post(f"{BASE}/p/{pid}/r/{rid}/corregir",
                       data={"instruction": "más grande", "confirm_paid": "1"}).status_code == 400
    dom["runs"].execute(rid)
    assert client.post(f"{BASE}/p/{pid}/r/{rid}/corregir",
                       data={"instruction": "  "}).status_code == 400
    r = client.post(f"{BASE}/p/{pid}/r/{rid}/corregir",
                    data={"instruction": "el dormitorio principal era más grande"})
    assert r.status_code == 400 and "confirmar el gasto" in r.get_data(as_text=True)
    assert len(dom["runs"].of_project(pid)) == 1 and len(llamadas) == 1


# =================================================================================================
# 12 — comparación
# =================================================================================================
def test_se_comparan_de_dos_a_tres_corridas_del_mismo_proyecto(client, dom, fixture_on):
    pid = _crear(client)
    ids = []
    for _ in range(4):
        rid = _generar(client, dom, pid)
        dom["runs"].execute(rid)
        ids.append(rid)
    client.post(f"{BASE}/p/{pid}/r/{ids[0]}/calificar", data={"rating": "BUENO"})
    hija = _corregir(client, pid, ids[0], "el dormitorio principal era más grande")
    dom["runs"].execute(hija)
    q = lambda xs: "&".join(f"r={x}" for x in xs)
    html = client.get(f"{BASE}/p/{pid}/comparar?{q([ids[0], hija, ids[2]])}").get_data(
        as_text=True)
    assert html.count("/plano.svg") == 3
    for texto in ("Corrida #1", "Corrida #5", "Bueno", "Prompts humanos", "Latencia", "Costo",
                  "a ciegas", "FIXTURE"):
        assert texto in html, texto
    assert client.get(f"{BASE}/p/{pid}/comparar?{q(ids[:1])}").status_code == 400
    assert client.get(f"{BASE}/p/{pid}/comparar?{q(ids)}").status_code == 400
    otro = _crear(client, n_fotos=1, gt=False)
    assert client.get(f"{BASE}/p/{otro}/comparar?{q(ids[:2])}").status_code == 400


# =================================================================================================
# 13 — reveal explícito
# =================================================================================================
def test_solo_un_post_confirmado_revela_y_no_se_deshace(client, dom, fixture_on):
    pid = _crear(client)
    antes = _generar(client, dom, pid)
    dom["runs"].execute(antes)
    assert client.get(f"{BASE}/p/{pid}/revelar").status_code == 405
    assert client.post(f"{BASE}/p/{pid}/revelar").status_code == 400
    assert dom["projects"].get(pid)["gt_state"] == "HIDDEN_FROM_ENGINE"
    assert client.get(f"{BASE}/p/{pid}/plano-real").status_code == 404
    assert client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"}).status_code == 302
    p = dom["projects"].get(pid)
    assert p["gt_state"] == "REVEALED" and p["revealed_at"] and p["revealed_by"]
    r = client.get(f"{BASE}/p/{pid}/plano-real")
    assert r.status_code == 200 and r.data == _plano_real()
    despues = _generar(client, dom, pid)
    dom["runs"].execute(despues)
    assert dom["runs"].get(antes)["gt_state_at_creation"] == "HIDDEN_FROM_ENGINE"
    assert dom["runs"].get(despues)["gt_state_at_creation"] == "REVEALED"
    html = client.get(f"{BASE}/p/{pid}/comparar?r={antes}&r={despues}").get_data(as_text=True)
    assert "Plano real" in html and "a ciegas" in html and "tras revelar" in html
    r = client.post(f"{BASE}/p/{pid}/plano-real", content_type="multipart/form-data",
                    data={"ground_truth": (io.BytesIO(_foto(99)), "otro.png")})
    assert r.status_code == 400 and "no se reemplaza" in r.get_data(as_text=True)
    conn = dom["store"].connect()
    for sql in ("UPDATE recon_projects SET gt_state='HIDDEN_FROM_ENGINE' WHERE project_id=?",
                "UPDATE recon_ground_truth SET sha256='x' WHERE project_id=?",
                "DELETE FROM recon_ground_truth WHERE project_id=?"):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql, (pid,))
        conn.rollback()
    kinds = [e["kind"] for e in dom["projects"].events(pid)]
    assert "GT_REVEALED" in kinds


def test_sin_plano_real_no_hay_nada_que_revelar(client, dom):
    pid = _crear(client, n_fotos=1, gt=False)
    r = client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"})
    assert r.status_code == 400 and dom["projects"].get(pid)["gt_state"] == "NONE"


def test_un_plano_real_en_pdf_se_previsualiza_recien_al_revelar(client, dom):
    import pymupdf
    doc = pymupdf.open()
    pag = doc.new_page(width=300, height=200)
    pag.insert_text((40, 100), "PLANO REAL")
    pdf = doc.tobytes()
    pid = _crear(client, n_fotos=1, gt=False)
    client.post(f"{BASE}/p/{pid}/plano-real", content_type="multipart/form-data",
                data={"ground_truth": (io.BytesIO(pdf), "plano.pdf")})
    gt = dom["store"].q1("SELECT * FROM recon_ground_truth WHERE project_id=?", (pid,))
    assert gt["mime_type"] == "application/pdf" and gt["preview_name"] is None
    client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"})
    r = client.get(f"{BASE}/p/{pid}/plano-real")
    assert r.status_code == 200 and r.mimetype == "image/png"


# =================================================================================================
# 14 — métricas 90/10, sin puntaje compuesto
# =================================================================================================
def test_las_metricas_no_inventan_nada(client, dom, fixture_on):
    pid = _crear(client)
    m = dom["runs"].metrics(pid)
    assert m["runs"] == 0 and m["final"] is None and m["human_minutes"] is None
    assert not any("score" in k or "puntaje" in k for k in m)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    hija = _corregir(client, pid, rid, "el dormitorio principal era más grande")
    dom["runs"].execute(hija)
    client.post(f"{BASE}/p/{pid}/r/{hija}/calificar", data={"rating": "BUENO"})
    r = client.post(f"{BASE}/p/{pid}/cierre", data={"final_run_id": hija, "expected_rooms": "8"})
    assert r.status_code == 400 and "después de revelar" in r.get_data(as_text=True)
    client.post(f"{BASE}/p/{pid}/cierre", data={
        "final_run_id": hija, "human_minutes": "18", "needed_manual_cad": "NO",
        "adjacency": "BIEN", "relative_position": "PARCIAL", "geometry": "MAL"})
    client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"})
    client.post(f"{BASE}/p/{pid}/cierre", data={
        "final_run_id": hija, "human_minutes": "18", "needed_manual_cad": "NO",
        "expected_rooms": "10", "adjacency": "BIEN", "relative_position": "PARCIAL",
        "geometry": "MAL"})
    m = dom["runs"].metrics(pid)
    assert m["human_prompts"] == 1
    assert m["final"] == {"run_id": hija, "seq": 2, "rating": "BUENO", "prompts_in_lineage": 1,
                          "rooms_detected": 9, "rooms_placed": 8}
    assert (m["human_minutes"], m["needed_manual_cad"], m["expected_rooms"]) == (18.0, "NO", 10)
    assert (m["adjacency"], m["relative_position"], m["geometry"]) == ("BIEN", "PARCIAL", "MAL")
    assert not any("score" in k or "puntaje" in k for k in m)
    assert len(dom["projects"].judgment_history(pid)) == 2
    html = client.get(f"{BASE}/p/{pid}").get_data(as_text=True)
    assert "18.0 min" in html and "10</b> esperados" in html


# =================================================================================================
# 16 — persistencia
# =================================================================================================
def test_reiniciar_no_borra_nada(client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    client.post(f"{BASE}/p/{pid}/r/{rid}/calificar", data={"rating": "BUENO"})
    client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"})
    store = dom["store"]
    antes = dict(store.q1("SELECT * FROM recon_runs WHERE run_id=?", (rid,)))
    store.connect().close()
    store._local.conn = None                                # proceso nuevo, mismo volumen
    store.init()
    store.reset_orphans()
    assert dict(store.q1("SELECT * FROM recon_runs WHERE run_id=?", (rid,))) == antes
    assert dom["projects"].get(pid)["gt_state"] == "REVEALED"
    assert dom["runs"].current_rating(rid)["rating"] == "BUENO"
    assert client.get(f"{BASE}/p/{pid}/r/{rid}/plano.svg").status_code == 200


def test_una_corrida_en_vuelo_al_reiniciar_queda_failed_y_no_se_reanuda(client, dom, fixture_on):
    pid = _crear(client)
    en_cola = _generar(client, dom, pid)
    corriendo = _generar(client, dom, pid)
    terminada = _generar(client, dom, pid)
    dom["runs"].execute(terminada)
    assert dom["runs"]._claim(corriendo)                   # noqa: SLF001
    dom["store"].reset_orphans()
    for rid in (en_cola, corriendo):
        r = dom["runs"].get(rid)
        assert r["status"] == "FAILED" and "[reinicio]" in r["error"]
    assert dom["runs"].get(terminada)["status"] == "DONE"
    assert dom["runs"].execute(en_cola)["status"] == "FAILED"          # no revive


# =================================================================================================
# 17 — no contaminación
# =================================================================================================
def test_e37_no_toca_nada_de_e36_ni_de_e17(client, dom, fixture_on):
    pid = _crear(client, n_fotos=4, extra={"videos": [(io.BytesIO(_mp4()), "v.mp4")]})
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    client.post(f"{BASE}/p/{pid}/r/{rid}/calificar", data={"rating": "BUENO"})
    hija = _corregir(client, pid, rid, "el dormitorio principal era más grande")
    dom["runs"].execute(hija)
    client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"})
    client.post(f"{BASE}/p/{pid}/cierre", data={"final_run_id": hija, "expected_rooms": "9"})
    store = dom["store"]
    for tabla in ("properties", "property_assets", "product_reviews", "gold_labels",
                  "manual_interventions", "pack_grants", "lab_events", "lab_notes", "listings",
                  "listing_media", "listing_reviews", "cases", "runs", "staging_attempts",
                  "benchmark_photos"):
        assert store.q1(f"SELECT COUNT(*) n FROM {tabla}")["n"] == 0, tabla
    from webapp.domain import interventions, properties, realpilot, reviews
    from webapp.domain.potential import reviews as previews
    assert properties.listing() == [] and realpilot.members() == []
    assert reviews.stats()["total"] == 0
    assert interventions.summary()["properties"] == 0
    assert previews.dashboard()["listings"] == 0
    html = client.get("/lab/").get_data(as_text=True)
    nav = re.search(r"<nav>(.*?)</nav>", html, re.S).group(1)
    assert re.findall(r">([^<>]+)</a>", nav) == ["Mis propiedades", "Ajustes"]
    assert html.count('href="/lab/ajustes"') == 1


def test_se_llega_desde_herramientas_tecnicas_y_ajustes_sin_tocar_el_menu(client, dom):
    for url in ("/lab/debug", "/lab/ajustes"):
        html = client.get(url).get_data(as_text=True)
        assert 'href="/lab/reconstruction/"' in html, url
        nav = re.search(r"<nav>(.*?)</nav>", html, re.S).group(1)
        assert "reconstruction" not in nav


# =================================================================================================
# 18 — UX y seguridad de la superficie
# =================================================================================================
def test_el_flujo_visible_es_el_de_la_task(client, dom, fixture_on):
    pid = _crear(client)
    html = client.get(f"{BASE}/p/{pid}").get_data(as_text=True)
    pasos = ("PROYECTOS", "NUEVO PROYECTO", "INPUTS / PLANO REAL OCULTO", "MOTOR", "GENERAR",
             "RESULTADO", "CALIFICAR", "CORREGIR", "NUEVA CORRIDA", "COMPARAR", "REVELAR")
    posiciones = [html.index(p) for p in pasos]
    assert posiciones == sorted(posiciones)
    for texto in ("OCULTO PARA LOS MOTORES", "Generar", "Métricas 90/10"):
        assert texto in html


def test_un_post_desde_otro_origen_se_rechaza(client, dom, fixture_on):
    pid = _crear(client)
    for cabecera in ({"Origin": "https://otro-sitio.example"},
                     {"Referer": "https://otro-sitio.example/pagina"}):
        r = client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"}, headers=cabecera)
        assert r.status_code == 403
        r = client.post(f"{BASE}/p/{pid}/generar", data={"engine_id": "fixture_replay"},
                        headers=cabecera)
        assert r.status_code == 403
    assert dom["projects"].get(pid)["gt_state"] == "HIDDEN_FROM_ENGINE"
    assert dom["runs"].of_project(pid) == []
    r = client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"},
                    headers={"Origin": "http://localhost"})
    assert r.status_code == 302


def test_ninguna_ruta_nueva_usa_palabras_vetadas_del_lab(app):
    reglas = [r.rule for r in app.url_map.iter_rules() if r.rule.startswith(BASE)]
    assert len(reglas) >= 15
    assert not any(x in r for r in reglas for x in ("/paso", "/step", "/progress", "/avance"))


def test_todas_las_rutas_piden_credenciales(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "clave-de-prueba")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    monkeypatch.delenv("ESCALIMETRO_DEV", raising=False)
    for m in MODULOS:
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    app = create_app()
    c = app.test_client()
    c.environ_base["HTTP_ORIGIN"] = "http://localhost"
    for regla in app.url_map.iter_rules():
        if not regla.rule.startswith(BASE):
            continue
        url = re.sub(r"<[^>]+>", "x", regla.rule)
        for metodo in regla.methods - {"HEAD", "OPTIONS"}:
            assert c.open(url, method=metodo).status_code == 401, (metodo, url)


# =================================================================================================
# Regresiones de la revisión adversarial de E37 (un test por hallazgo confirmado)
# =================================================================================================
def test_rev_una_foto_ya_usada_por_un_motor_no_puede_volverse_el_plano_real(client, dom,
                                                                           fixture_on):
    """El camino que la propia UI sugería: foto que parece plano → retirarla → subirla como
    plano real. Si una corrida ya la usó, sus hijas la seguirían mandando al motor."""
    plano = _plano_de_galeria()
    pid = _crear(client, n_fotos=1, gt=False, extra={
        "photos": [(io.BytesIO(_foto(0)), "a.png"), (io.BytesIO(plano), "galeria.png")]})
    r1 = _generar(client, dom, pid)
    dom["runs"].execute(r1)
    sospechosa = [a for a in dom["projects"].assets_of(pid) if a["looks_like_plan"]][0]
    client.post(f"{BASE}/p/{pid}/asset/{sospechosa['asset_id']}/retirar")
    r = client.post(f"{BASE}/p/{pid}/plano-real", content_type="multipart/form-data",
                    data={"ground_truth": (io.BytesIO(plano), "plano.png")})
    assert r.status_code == 400 and "ya lo recibió un motor" in r.get_data(as_text=True)
    assert dom["projects"].get(pid)["gt_state"] == "NONE"
    # retirada ANTES de que ninguna corrida la use, sí puede ser el plano real
    otro = _crear(client, n_fotos=1, gt=False, extra={
        "photos": [(io.BytesIO(_foto(3)), "b.png"), (io.BytesIO(plano), "galeria.png")]})
    s2 = [a for a in dom["projects"].assets_of(otro) if a["looks_like_plan"]][0]
    client.post(f"{BASE}/p/{otro}/asset/{s2['asset_id']}/retirar")
    r = client.post(f"{BASE}/p/{otro}/plano-real", content_type="multipart/form-data",
                    data={"ground_truth": (io.BytesIO(plano), "plano.png")})
    assert r.status_code == 302
    # y ese input retirado, idéntico al plano real oculto, tampoco se sirve por su ruta
    assert client.get(f"{BASE}/p/{otro}/asset/{s2['asset_id']}").status_code == 404


def test_rev_segunda_barrera_un_input_igual_al_plano_real_no_llega_al_motor(client, dom,
                                                                            fixture_on):
    espia = Espia(dom, dom["fixture"])
    pid = _crear(client, n_fotos=2, gt=False)
    rid = _generar(client, dom, pid, "espia")                 # en cola, cita las dos fotos
    foto = dom["projects"].assets_of(pid)[0]
    # alguien fuerza el plano real con los bytes de un input (saltándose la validación de carga)
    store = dom["store"]
    store.ex("INSERT INTO recon_ground_truth(project_id, stored_name, mime_type, size_bytes, "
             "sha256, uploaded_at) VALUES (?,?,?,?,?,?)",
             (pid, "x.png", "image/png", 1, foto["sha256"], store.now()))
    store.ex("UPDATE recon_projects SET gt_state='HIDDEN_FROM_ENGINE' WHERE project_id=?", (pid,))
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and "INPUT_IS_GROUND_TRUTH" in r["error"]
    assert espia.recibidas == []
    dom["engines"].unregister("espia")


def test_rev_un_error_de_sqlite_no_deja_la_base_trabada(client, dom, fixture_on):
    import threading
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    store = dom["store"]
    with pytest.raises(sqlite3.DatabaseError):
        store.ex("UPDATE recon_runs SET error='x' WHERE run_id=?", (rid,))
    resultado = {}

    def otro_hilo():
        c = sqlite3.connect(store.DB_PATH, timeout=2)
        try:
            c.execute("INSERT INTO recon_events(project_id, kind, created_at) VALUES (?,?,?)",
                      (pid, "PRUEBA", store.now()))
            c.commit()
            resultado["ok"] = True
        except sqlite3.OperationalError as e:
            resultado["ok"] = str(e)
        finally:
            c.close()
    t = threading.Thread(target=otro_hilo)
    t.start()
    t.join(10)
    assert resultado.get("ok") is True, resultado


@pytest.mark.parametrize("caso", ["contrato_invalido", "incompleta", "http_500"])
def test_rev_una_llamada_paga_que_falla_deja_registrado_lo_que_costo(client, dom, monkeypatch,
                                                                    caso):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    uso = {"input_tokens": 50000, "output_tokens": 9000, "total_tokens": 59000}
    if caso == "contrato_invalido":
        malo = dom["fixture"].canned_plan(["x"])
        malo["connections"][0]["to_room"] = "no-existe"
        cuerpo, st = _respuesta_openai(malo, usage=uso), 200
    elif caso == "incompleta":
        cuerpo, st = json.dumps({"status": "incomplete", "usage": uso, "output": [],
                                 "incomplete_details": {"reason": "max_output_tokens"}}).encode(), 200
    else:
        cuerpo, st = json.dumps({"error": {"message": "caída"}}).encode(), 500
    _grabar(dom, monkeypatch, None, status=st, cuerpo=cuerpo)
    pid = _crear(client, n_fotos=2)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and r["output"] is None
    assert r["prompt_version"] == dom["openai"].PROMPT_VERSION and r["latency_ms"] is not None
    assert r["request_summary"]["images_sent"] == 2
    assert r["artifacts"] and "request.json" in r["artifacts"]
    if caso != "http_500":
        assert r["usage"] == uso
        with open(os.path.join(dom["projects"].runs_dir(pid, rid), "response.json"),
                  encoding="utf-8") as fh:
            assert "usage" in fh.read()
    html = client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)
    assert "La corrida falló" in html and "Procedencia técnica" in html


def test_rev_un_error_despues_del_motor_cierra_la_corrida_como_failed(client, dom, fixture_on,
                                                                      monkeypatch):
    pid = _crear(client)
    rid = _generar(client, dom, pid)

    def revienta(*a, **k):
        raise OverflowError("cannot convert float infinity to integer")
    monkeypatch.setattr(dom["render"], "svg", revienta)
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and "POSTPROCESO" in r["error"] and r["finished_at"]
    assert r["prompt_version"] == "fixture_replay_v1"


def test_rev_un_numero_infinito_es_contrato_invalido(dom):
    plan = dom["fixture"].canned_plan(["a"])
    plan["footprint"]["depth_m"] = float("inf")
    with pytest.raises(dom["contract"].ContractError):
        dom["contract"].validate(plan)
    plan = dom["fixture"].canned_plan(["a"])
    plan["rooms"][0]["polygon"][0][0] = float("nan")
    with pytest.raises(dom["contract"].ContractError):
        dom["contract"].validate(plan)


def test_rev_un_resultado_tardio_no_escribe_en_una_corrida_ajena(client, dom, fixture_on,
                                                                 monkeypatch):
    """Otro proceso (un segundo `wsgi.py` contra el mismo volumen) da la corrida por muerta
    mientras el motor trabaja. El resultado llega tarde: no se escribe, pero queda en la bitácora."""
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    motor = dom["engines"].get("fixture_replay")
    original = type(motor).reconstruct

    def lento(self, req):
        dom["store"].reset_orphans()
        return original(self, req)
    monkeypatch.setattr(type(motor), "reconstruct", lento)
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and "[reinicio]" in r["error"]
    assert not os.path.exists(os.path.join(dom["projects"].runs_dir(pid, rid), "plan.svg"))
    assert "LATE_RESULT_DISCARDED" in [e["kind"] for e in dom["projects"].events(pid)]
    store = dom["store"]
    store.ex("INSERT INTO recon_events(project_id, kind, created_at) VALUES (?,?,?)",
             (pid, "SIGUE_ESCRIBIENDO", store.now()))


def test_rev_recalificar_no_borra_el_comentario_vigente(client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    client.post(f"{BASE}/p/{pid}/r/{rid}/calificar",
                data={"rating": "BUENO", "comment": "falta la terraza"})
    html = client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)
    ocultos = re.findall(r'name="comment" value="([^"]*)"', html)
    assert ocultos and all(v == "falta la terraza" for v in ocultos)
    client.post(f"{BASE}/p/{pid}/r/{rid}/calificar",
                data={"rating": "MALO", "comment": ocultos[0]})
    assert dom["runs"].current_rating(rid)["comment"] == "falta la terraza"
    antes = len(dom["runs"].rating_history(rid))
    client.post(f"{BASE}/p/{pid}/r/{rid}/calificar",
                data={"rating": "MALO", "comment": "falta la terraza"})
    assert len(dom["runs"].rating_history(rid)) == antes


@pytest.mark.parametrize("cabeceras", [{"Origin": "null"}, {"Origin": ""},
                                       {"Origin": "file://"}, {},
                                       {"Origin": "http://localhost", "Referer": "https://mal.example/x"}])
def test_rev_la_guardia_de_origen_falla_cerrada(app, dom, fixture_on, cabeceras):
    c = app.test_client()                                     # sin el Origin por defecto
    r = c.post(f"{BASE}/nuevo", data={"name": "x"}, headers=cabeceras)
    assert r.status_code == 403
    assert dom["store"].q1("SELECT COUNT(*) n FROM recon_projects")["n"] == 0


def test_rev_la_clave_no_sobrevive_aunque_el_proveedor_la_parta(client, dom, monkeypatch):
    clave = "x-prueba-clave-bastante-larga-e37"
    monkeypatch.setenv("OPENAI_API_KEY", clave)
    relleno = "y" * 480
    _grabar(dom, monkeypatch, None, status=401,
            cuerpo=json.dumps({"error": relleno + " " + clave}).encode())
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED"
    for n in range(8, len(clave) + 1):
        assert clave[:n] not in (r["error"] or ""), n
    assert clave[:12] not in client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)


def test_rev_las_corridas_previas_al_plano_real_tambien_son_a_ciegas(client, dom, fixture_on):
    pid = _crear(client, n_fotos=2, gt=False)
    a = _generar(client, dom, pid)
    dom["runs"].execute(a)
    client.post(f"{BASE}/p/{pid}/plano-real", content_type="multipart/form-data",
                data={"ground_truth": (io.BytesIO(_plano_real()), "p.png")})
    b = _generar(client, dom, pid)
    dom["runs"].execute(b)
    client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"})
    html = client.get(f"{BASE}/p/{pid}/comparar?r={a}&r={b}").get_data(as_text=True)
    assert "a ciegas (antes de cargarlo)" in html and "sin plano real" not in html
    t = dom["runs"].card(dom["runs"].get(a))
    assert t["blind"] and t["blind_before_gt"]


def test_rev_una_aclaracion_inicial_o_evidencia_insuficiente_se_pueden_responder(
        client, dom, fixture_on, monkeypatch):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    plan = dom["fixture"].canned_plan([])
    plan.update({"outcome": "CLARIFICATION_REQUIRED",
                 "clarification": {"question": "¿Las fotos 1 y 2 son del mismo depto?",
                                   "options": ["sí", "no"]}})
    motor = dom["engines"].get("fixture_replay")
    original = type(motor).reconstruct

    def pregunta(self, req):
        if req.mode == "INITIAL":
            return dom["engines"].EngineResult(output=plan, model="m", latency_ms=1,
                                               prompt_version="v", prompt_sha256="0",
                                               request_summary={})
        return original(self, req)
    monkeypatch.setattr(type(motor), "reconstruct", pregunta)
    r = dom["runs"].execute(rid)
    assert r["outcome"] == "CLARIFICATION_REQUIRED"
    html = client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)
    assert "Crear corrida hija" in html
    hija = _corregir(client, pid, rid, "sí, el dormitorio principal era más grande")
    req = dom["runs"].build_request(dom["runs"].get(hija))
    assert "mismo depto" in req.clarification_context and "Opciones: sí; no" in req.clarification_context
    assert dom["runs"].execute(hija)["status"] == "DONE"


def test_rev_varias_aclaraciones_seguidas_no_pierden_la_instruccion_original(client, dom,
                                                                            fixture_on):
    espia = Espia(dom, dom["fixture"])
    pid = _crear(client)
    r0 = _generar(client, dom, pid, "espia")
    dom["runs"].execute(r0)
    c1 = _corregir(client, pid, r0, "agrandar algo")
    dom["runs"].execute(c1)
    c2 = _corregir(client, pid, c1, "lo de la izquierda")
    dom["runs"].execute(c2)
    assert dom["runs"].get(c2)["outcome"] == "CLARIFICATION_REQUIRED"
    c3 = _corregir(client, pid, c2, "el dormitorio principal, más grande")
    dom["runs"].execute(c3)
    req = espia.recibidas[-1]
    assert "agrandar algo" in req.instruction and "lo de la izquierda" in req.instruction
    assert "el dormitorio principal, más grande" in req.instruction
    assert req.clarification_context and "Opciones:" in req.clarification_context
    assert req.previous == dom["runs"].get(r0)["output"]
    dom["engines"].unregister("espia")


def test_rev_un_motor_de_video_recibe_el_video_y_los_demas_lo_declaran_ignorado(client, dom,
                                                                               fixture_on):
    espia = Espia(dom, dom["fixture"])                        # declara la capacidad "video"
    pid = _crear(client, n_fotos=2, extra={"videos": [(io.BytesIO(_mp4()), "v.mp4")]})
    rv = _generar(client, dom, pid, "espia")
    dom["runs"].execute(rv)
    (video,) = espia.recibidas[-1].videos
    assert video.data == _mp4()
    rf = _generar(client, dom, pid)                           # el fixture no consume video
    r = dom["runs"].execute(rf)
    assert r["inputs"]["videos"][0]["sent"] is False and "1 video(s)" in r["inputs"]["ignored"]
    dom["engines"].unregister("espia")


def test_rev_recintos_esperados_como_etiqueta_sin_plano_real(client, dom, fixture_on):
    pid = _crear(client, gt=False)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    r = client.post(f"{BASE}/p/{pid}/cierre", data={"final_run_id": rid, "expected_rooms": "8"})
    assert r.status_code == 302
    m = dom["runs"].metrics(pid)
    assert m["expected_rooms"] == 8 and m["expected_rooms_source"] == "etiqueta"
    oculto = _crear(client)
    r2 = _generar(client, dom, oculto)
    dom["runs"].execute(r2)
    assert client.post(f"{BASE}/p/{oculto}/cierre", data={"expected_rooms": "8"}).status_code == 400


def test_rev_el_resultado_habla_en_castellano_y_con_nombres_de_recintos(client, dom, fixture_on):
    pid = _crear(client)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    html = client.get(f"{BASE}/p/{pid}/r/{rid}").get_data(as_text=True)
    seccion = html.split('id="resultado"')[1].split('id="calificar"')[0]
    for codigo in ("OPENING", "NEXT_TO", ">HIGH<", "r1 ↔", "r9 "):
        assert codigo not in seccion, codigo
    assert "Living-comedor ↔ Cocina · abertura" in seccion
    assert "Walk-in closet junto a Dormitorio principal" in seccion
    assert "Impacto <b>alta</b>" in seccion


def test_rev_las_relaciones_citan_evidencia(dom):
    esquema = dom["contract"].SCHEMA["properties"]["relations"]["items"]
    assert "evidence" in esquema["required"]
    plan = dom["fixture"].canned_plan(["a"])
    plan["relations"][0]["evidence"] = [{"asset_ids": ["b"], "observation": "o"}]
    assert any("relación" in a for a in dom["contract"].validate(plan, known_asset_ids=("a",)))


@pytest.mark.parametrize("cuerpo,esperado", [
    (json.dumps({"status": "failed", "error": {"code": "server_error",
                                               "message": "The model failed"}, "output": []}),
     "server_error"),
    ("<html>proxy error</html>", "NOT_JSON"),
    ("[1, 2, 3]", "NOT_JSON"),
    (json.dumps({"status": "completed", "output": [None, {"type": "message", "content": [None]}]}),
     "EMPTY"),
])
def test_rev_cada_forma_de_fallar_del_proveedor_tiene_nombre(client, dom, monkeypatch, cuerpo,
                                                             esperado):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    _grabar(dom, monkeypatch, None, status=200, cuerpo=cuerpo.encode())
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and esperado in r["error"], r["error"]


# =================================================================================================
# Regresiones de la segunda ronda de revisión
# =================================================================================================
class _Roto:
    """Un motor futuro con errores de programación: el laboratorio no puede quedar colgado."""

    def __init__(self, dom, devuelve):
        base = dom["engines"].EngineAdapter

        class _M(base):
            engine_id, name, capabilities = "roto", "Motor roto", ("photos", "correction")

            def reconstruct(self, req):
                return devuelve(dom, req)
        dom["engines"].register(_M())


@pytest.mark.parametrize("devuelve", [
    lambda dom, req: None,
    lambda dom, req: dom["engines"].EngineResult(
        output=dom["fixture"].canned_plan([]), model="m", latency_ms=1, prompt_version="v",
        prompt_sha256="0", request_summary={}, raw=[1, 2, 3]),
    lambda dom, req: dom["engines"].EngineResult(
        output=dom["fixture"].canned_plan([]), model="m", latency_ms=1, prompt_version="v",
        prompt_sha256="0", request_summary={"s": {1, 2}}, usage={"n": __import__("numpy").int64(5)}),
])
def test_r2_un_motor_que_devuelve_cualquier_cosa_no_deja_la_corrida_colgada(client, dom,
                                                                           devuelve):
    _Roto(dom, devuelve)
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "roto")
    r = dom["runs"].execute(rid)
    assert r["finished_at"] is not None and r["status"] in ("DONE", "FAILED")
    assert json.loads(client.get(f"{BASE}/p/{pid}/r/{rid}/status.json").data)["finished"]
    dom["engines"].unregister("roto")


def test_r2_una_falla_tardia_no_escribe_en_una_corrida_ajena_y_deja_lo_que_costo(
        client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    uso = {"input_tokens": 50000, "output_tokens": 9000, "total_tokens": 59000}
    malo = dom["fixture"].canned_plan(["x"])
    malo["levels"] = 0
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")

    def transporte(method, url, headers, body, timeout):
        dom["store"].reset_orphans()                          # otro proceso da la corrida por muerta
        return 200, {}, _respuesta_openai(malo, usage=uso)
    monkeypatch.setattr(dom["http"], "TRANSPORT", transporte)
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and "[reinicio]" in r["error"]
    assert not os.path.exists(dom["projects"].runs_dir(pid, rid))
    tardios = [e for e in dom["projects"].events(pid) if e["kind"] == "LATE_RESULT_DISCARDED"]
    assert tardios and tardios[0]["detail"]["usage"] == uso


def test_r2_del_uso_del_proveedor_solo_quedan_numeros(client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    raro = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
            "input_tokens_details": {"eco": CLAVE_FALSA}}

    def transporte(method, url, headers, body, timeout):
        ids = [p["text"].split("id ")[1] for p in json.loads(body)["input"][0]["content"]
               if p["type"] == "input_text" and p["text"].startswith("Foto ")]
        return 200, {}, _respuesta_openai(dom["fixture"].canned_plan(ids), usage=raro)
    monkeypatch.setattr(dom["http"], "TRANSPORT", transporte)
    r = dom["runs"].execute(rid)
    assert r["status"] == "DONE" and r["usage"] == {"input_tokens": 10, "output_tokens": 5,
                                                    "total_tokens": 15}
    fila = json.dumps(dict(dom["store"].q1("SELECT * FROM recon_runs WHERE run_id=?", (rid,))),
                      default=str)
    assert CLAVE_FALSA not in fila


@pytest.mark.parametrize("cuerpo,esperado", [
    ({"status": "completed", "output": {"no": "lista"}}, "MALFORMED"),
    ({"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": {"no": "texto"}}]}]}, "MALFORMED"),
    ({"error": {"code": "rate_limit", "message": "espera"}, "output": []}, "rate_limit"),
    ({"status": "incomplete", "incomplete_details": "max_output_tokens"}, "INCOMPLETE"),
])
def test_r2_cuerpos_malformados_del_proveedor(client, dom, monkeypatch, cuerpo, esperado):
    monkeypatch.setenv("OPENAI_API_KEY", CLAVE_FALSA)
    _grabar(dom, monkeypatch, None, status=200, cuerpo=json.dumps(cuerpo).encode())
    pid = _crear(client, n_fotos=1)
    rid = _generar(client, dom, pid, "openai_direct", confirm_paid="1")
    r = dom["runs"].execute(rid)
    assert r["status"] == "FAILED" and esperado in r["error"], r["error"]


def test_r2_numeros_absurdos_son_contrato_invalido_y_no_revientan_el_dibujo(dom):
    c, plan = dom["contract"], dom["fixture"].canned_plan
    for mutar in (lambda p: p["footprint"].update(width_m=10 ** 400),
                  lambda p: p["footprint"].update(width_m=0.001, depth_m=1000),
                  lambda p: p["rooms"][0].update(area_m2=10 ** 30),
                  lambda p: p.update(levels=10 ** 50)):
        p = plan(["a"])
        mutar(p)
        with pytest.raises(c.ContractError):
            c.validate(p)


def test_r2_la_etiqueta_de_recintos_esperados_no_se_pierde_al_cargar_el_plano_real(client, dom,
                                                                                  fixture_on):
    pid = _crear(client, gt=False)
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    client.post(f"{BASE}/p/{pid}/cierre", data={"final_run_id": rid, "expected_rooms": "8"})
    client.post(f"{BASE}/p/{pid}/plano-real", content_type="multipart/form-data",
                data={"ground_truth": (io.BytesIO(_plano_real()), "p.png")})
    client.post(f"{BASE}/p/{pid}/cierre", data={"final_run_id": rid, "human_minutes": "12"})
    assert dom["projects"].current_judgment(pid)["expected_rooms"] == 8
    client.post(f"{BASE}/p/{pid}/revelar", data={"confirm": "1"})
    assert dom["runs"].metrics(pid)["expected_rooms"] == 8


def test_r2_responder_a_evidencia_insuficiente_conserva_lo_pedido(client, dom, fixture_on,
                                                                 monkeypatch):
    espia = Espia(dom, dom["fixture"])
    pid = _crear(client)
    r0 = _generar(client, dom, pid, "espia")
    dom["runs"].execute(r0)
    nada = dom["fixture"].canned_plan([])
    nada.update({"outcome": "INSUFFICIENT_EVIDENCE", "missing_evidence": ["foto del fondo"]})
    original = type(espia.adapter).reconstruct
    llamadas = {"n": 0}

    def una_vez_insuficiente(self, req):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            espia.recibidas.append(req)
            return dom["engines"].EngineResult(output=nada, model="m", latency_ms=1,
                                               prompt_version="v", prompt_sha256="0",
                                               request_summary={})
        return original(self, req)
    monkeypatch.setattr(type(espia.adapter), "reconstruct", una_vez_insuficiente)
    c1 = _corregir(client, pid, r0, "el baño está al fondo")
    assert dom["runs"].execute(c1)["outcome"] == "INSUFFICIENT_EVIDENCE"
    c2 = _corregir(client, pid, c1, "detrás de la cocina")
    dom["runs"].execute(c2)
    req = espia.recibidas[-1]
    assert "el baño está al fondo" in req.instruction and "detrás de la cocina" in req.instruction
    assert "foto del fondo" in req.clarification_context
    dom["engines"].unregister("espia")


@pytest.mark.parametrize("cabeceras,esperado", [
    ({"Origin": "https://localhost"}, 403),
    ({"Origin": "ftp://localhost"}, 403),
    ({"Origin": "https://localhost", "X-Forwarded-Proto": "https"}, 302),
])
def test_r2_la_guardia_compara_tambien_el_esquema(app, dom, cabeceras, esperado):
    c = app.test_client()
    r = c.post(f"{BASE}/nuevo", data={"name": "x"}, headers=cabeceras)
    assert r.status_code == esperado


def test_r2_un_documento_que_ningun_motor_recibio_puede_ser_el_plano_real(client, dom,
                                                                         fixture_on):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=200, height=150).insert_text((20, 70), "PLANO")
    pdf = doc.tobytes()
    pid = _crear(client, n_fotos=1, gt=False, extra={
        "documents": [(io.BytesIO(pdf), "plano_corredor.pdf")]})
    rid = _generar(client, dom, pid)
    dom["runs"].execute(rid)
    documento = dom["projects"].assets_of(pid, dom["projects"].DOCUMENT)[0]
    client.post(f"{BASE}/p/{pid}/asset/{documento['asset_id']}/retirar")
    r = client.post(f"{BASE}/p/{pid}/plano-real", content_type="multipart/form-data",
                    data={"ground_truth": (io.BytesIO(pdf), "plano.pdf")})
    assert r.status_code == 302 and dom["projects"].get(pid)["gt_state"] == "HIDDEN_FROM_ENGINE"


def test_r2_el_mismo_archivo_como_foto_y_como_plano_real_queda_como_plano_real(client, dom):
    pid = _crear(client, n_fotos=0, extra={
        "photos": [(io.BytesIO(_foto(1)), "a.png"),
                   (io.BytesIO(_plano_real()), "galeria_plano.png")]})
    assert dom["projects"].get(pid)["gt_state"] == "HIDDEN_FROM_ENGINE"
    fotos = dom["projects"].assets_of(pid, dom["projects"].PHOTO)
    assert len(fotos) == 1 and fotos[0]["original_filename"] == "a.png"


@pytest.mark.parametrize("campo,valor", [("bedrooms", "inf"), ("bedrooms", "1e400"),
                                         ("total_area_m2", "nan"), ("usable_area_m2", "inf")])
def test_r2_datos_declarados_no_finitos_se_rechazan_sin_500(client, dom, campo, valor):
    r = client.post(f"{BASE}/nuevo", data={"name": "x", campo: valor})
    assert r.status_code == 400 and "no es un número" in r.get_data(as_text=True)
