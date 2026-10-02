"""E41 — pedido público de Plano Corporativo: email + plano, recepción y persistencia honestas.

Con contraseña puesta (como en producción). Los datos son de prueba: example.com y bytes mínimos.
"""
from __future__ import annotations

import importlib
import io
import os
import re
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

URL = "/planos/solicitar"
PDF = b"%PDF-1.4\n% plano de prueba\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
JPG = b"\xff\xd8\xff\xe0" + b"0" * 16


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data = tmp_path / "d"
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(data))
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "secreta")
    monkeypatch.setenv("ESCALIMETRO_USER", "joaquin")
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for m in ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.public",
              "webapp.app"):
        importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app().test_client(), data


def _filas(data):
    con = sqlite3.connect(str(data / "escalimetro.db"))
    con.row_factory = sqlite3.Row
    try:
        return con.execute("SELECT * FROM plano_requests").fetchall()
    finally:
        con.close()


def _archivos(data):
    base = data / "plano_requests"
    if not base.exists():
        return []
    return [os.path.join(d, f) for d, _, fs in os.walk(base) for f in fs]


def _post(client, email="cliente@example.com", contenido=PDF, nombre="plano.pdf"):
    datos = {}
    if email is not None:
        datos["email"] = email
    if contenido is not None:
        datos["plano"] = (io.BytesIO(contenido), nombre)
    return client.post(URL, data=datos, content_type="multipart/form-data")


def test_get_200_sin_auth_con_exactamente_dos_inputs(env):
    client, _ = env
    r = client.get(URL)
    assert r.status_code == 200
    assert "WWW-Authenticate" not in r.headers
    html = r.get_data(as_text=True)
    assert len(re.findall(r"<input\b", html)) == 2
    assert 'name="email"' in html and 'name="plano"' in html
    assert 'enctype="multipart/form-data"' in html
    low = html.lower()
    for prohibido in ("teléfono", "telefono", "nombre completo", "empresa", "dirección", "fotos",
                      "programa", "personas", "estilo", "precio", "textarea", "<select"):
        assert prohibido not in low, prohibido


@pytest.mark.parametrize("contenido,nombre,mime", [(PDF, "a.pdf", "application/pdf"),
                                                    (PNG, "a.PNG", "image/png"),
                                                    (JPG, "a.jpg", "image/jpeg"),
                                                    (JPG, "a.jpeg", "image/jpeg")])
def test_post_valido_crea_un_pedido_y_guarda_el_archivo(env, contenido, nombre, mime):
    client, data = env
    r = _post(client, email="  Cliente@Example.com ", contenido=contenido, nombre=nombre)
    assert r.status_code == 303
    filas = _filas(data)
    assert len(filas) == 1
    f = filas[0]
    assert re.fullmatch(r"pc_[0-9a-f]{32}", f["request_id"])           # opaco, no secuencial
    assert f["email"] == "Cliente@Example.com"
    assert f["status"] == "RECEIVED"
    assert f["mime"] == mime and f["size_bytes"] == len(contenido)
    assert f["created_at"]
    archivos = _archivos(data)
    assert len(archivos) == 1
    assert archivos[0].startswith(str(data / "plano_requests" / f["request_id"]))
    assert os.path.basename(archivos[0]) == f["plan_file"]
    with open(archivos[0], "rb") as fh:
        assert fh.read() == contenido


def test_prg_confirmacion_y_refresh_no_duplica(env):
    client, data = env
    r = _post(client)
    assert r.status_code == 303
    destino = r.headers["Location"]
    assert "/planos/recibido/pc_" in destino
    for _ in range(3):                                                   # refrescar la confirmación
        c = client.get(destino)
        assert c.status_code == 200
        assert "WWW-Authenticate" not in c.headers
        t = c.get_data(as_text=True)
        assert "Pedido recibido" in t
        assert "cliente@example.com" not in t                            # no se refleja el email
    assert len(_filas(data)) == 1 and len(_archivos(data)) == 1


def test_confirmacion_de_id_desconocido_o_malformado_es_404(env):
    client, _ = env
    assert client.get("/planos/recibido/pc_" + "0" * 32).status_code == 404
    assert client.get("/planos/recibido/1").status_code == 404
    assert client.get("/planos/recibido/..%2Fescalimetro.db").status_code == 404


@pytest.mark.parametrize("email", [None, "", "   ", "sin-arroba", "a@b", "a b@c.cl",
                                   "a@b.cl " + "x" * 300])
def test_email_ausente_o_invalido_no_deja_nada(env, email):
    client, data = env
    r = _post(client, email=email)
    assert r.status_code == 400
    assert "No se recibió el pedido" in r.get_data(as_text=True)
    assert _filas(data) == [] and _archivos(data) == []


def test_error_conserva_el_email_tipeado(env):
    client, _ = env
    r = _post(client, email="cliente@example.com", contenido=None)
    assert r.status_code == 400
    assert 'value="cliente@example.com"' in r.get_data(as_text=True)


@pytest.mark.parametrize("contenido,nombre", [
    (None, None),                                  # sin archivo
    (PDF, "plano.exe"), (PDF, "plano.svg"), (PDF, "plano"),   # formato no permitido
    (b"MZ nada que ver", "plano.pdf"),             # extensión PDF, contenido no
    (PDF, "plano.png"), (PNG, "plano.jpg"),        # contenido y extensión no coinciden
    (b"", "plano.pdf"),                            # vacío
])
def test_archivo_ausente_o_no_permitido_no_deja_nada(env, contenido, nombre):
    client, data = env
    r = _post(client, contenido=contenido, nombre=nombre)
    assert r.status_code == 400
    assert "No se recibió el pedido" in r.get_data(as_text=True)
    assert _filas(data) == []
    assert _archivos(data) == []                    # ni archivo huérfano
    base = data / "plano_requests"
    assert not base.exists() or os.listdir(base) == []   # ni carpeta huérfana


def test_archivo_demasiado_grande_no_deja_nada(env, monkeypatch):
    client, data = env
    from webapp import intake
    monkeypatch.setattr(intake, "MAX_UPLOAD_MB", 0)
    r = _post(client)
    assert r.status_code == 400
    assert "máximo" in r.get_data(as_text=True)
    assert _filas(data) == [] and _archivos(data) == []


@pytest.mark.parametrize("nombre", ["../../etc/passwd.pdf", "..\\..\\x.pdf", "/abs/ruta.pdf",
                                    "a/b/../../../../escape.pdf"])
def test_nombre_original_no_permite_path_traversal(env, nombre):
    client, data = env
    r = _post(client, nombre=nombre)
    assert r.status_code == 303
    f = _filas(data)[0]
    assert f["plan_file"] == "plano.pdf"             # el nombre en disco lo decidimos nosotros
    assert "/" not in f["original_filename"] and ".." not in f["plan_file"]
    (ruta,) = _archivos(data)
    assert os.path.realpath(ruta).startswith(os.path.realpath(str(data / "plano_requests")))
    assert not (data.parent / "escape.pdf").exists()


def test_fallo_al_insertar_limpia_el_archivo(env, monkeypatch):
    client, data = env
    from webapp import store

    def roto(*a, **k):
        raise RuntimeError("base caída")
    monkeypatch.setattr(store, "ex", roto)
    assert _post(client).status_code == 500
    assert _archivos(data) == []


def test_post_no_toca_motor_ni_red(env, monkeypatch):
    client, data = env
    import socket
    import subprocess

    def prohibido(*a, **k):
        raise AssertionError("el POST no debe ejecutar procesos ni abrir red")
    monkeypatch.setattr(subprocess, "run", prohibido)
    monkeypatch.setattr(subprocess, "Popen", prohibido)
    monkeypatch.setattr(socket.socket, "connect", prohibido)
    antes = set(sys.modules)
    assert _post(client).status_code == 303
    assert not {m for m in set(sys.modules) - antes if m.startswith(("escalimetro", "openai", "anthropic"))}
    # tampoco creó casos ni corridas
    assert not (data / "cases").exists() or os.listdir(data / "cases") == []
    con = sqlite3.connect(str(data / "escalimetro.db"))
    try:
        assert con.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    finally:
        con.close()


def test_landing_conserva_su_cta(env):
    client, _ = env
    assert 'href="/planos/solicitar"' in client.get("/planos/").get_data(as_text=True)


def test_la_superficie_publica_no_expone_navegacion_interna(env):
    client, _ = env
    pedido = _post(client).headers["Location"]
    for ruta in (URL, pedido):
        html = client.get(ruta).get_data(as_text=True)
        for rastro in ("/lab/", "/properties", "/case/", "/run/", "/review", "/upload", "/staging",
                       "/settings", "/healthz", "/property/", "base.html"):
            assert rastro not in html, (ruta, rastro)
        assert not re.search(r"\$|\bclp\b|\buf\b|\d+\s?%", html.lower()), ruta


@pytest.mark.parametrize("ruta", ["/", "/lab/", "/properties/", "/settings"])
def test_rutas_internas_siguen_pidiendo_basic(env, ruta):
    client, _ = env
    r = client.get(ruta)
    assert r.status_code == 401 and "Basic" in r.headers["WWW-Authenticate"]


def test_post_interno_sigue_protegido_y_los_pedidos_no_tienen_ruta_interna(env):
    client, _ = env
    assert client.post("/upload").status_code == 401
    assert client.get("/planos/pedidos").status_code == 404      # sin listado ni panel
