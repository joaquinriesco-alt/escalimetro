"""E42 — pedido público de Plano Corporativo → propiedad interna del LAB.

Con contraseña puesta (como en producción). Datos de prueba: example.com y bytes mínimos.
"""
from __future__ import annotations

import base64
import importlib
import io
import os
import sqlite3
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

# PNG 1x1 válido: pasa el sniff y las dimensiones de la capa de assets.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
AUTH = {"Authorization": "Basic " + base64.b64encode(b"joaquin:secreta").decode()}
BANDEJA = "/lab/pedidos/"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data = tmp_path / "d"
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(data))
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "secreta")
    monkeypatch.setenv("ESCALIMETRO_USER", "joaquin")
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for m in ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.public",
              "webapp.domain.assets", "webapp.domain.properties", "webapp.domain.grants",
              "webapp.domain.entitlements", "webapp.pedidos", "webapp.lab", "webapp.app"):
        importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app().test_client(), data


def _pedido(client, email="cliente@example.com", nombre="plano.png"):
    r = client.post("/planos/solicitar", data={"email": email, "plano": (io.BytesIO(PNG), nombre)},
                    content_type="multipart/form-data")
    assert r.status_code == 303
    return r.headers["Location"].rsplit("/", 1)[1]


def _db(data, sql, args=()):
    con = sqlite3.connect(str(data / "escalimetro.db"))
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def _preparar(client, rid):
    return client.post(f"/lab/pedidos/{rid}/preparar", headers=AUTH)


def test_la_bandeja_y_la_accion_exigen_basic_auth(env):
    c, _ = env
    rid = _pedido(c)
    assert c.get(BANDEJA).status_code == 401
    assert c.post(f"/lab/pedidos/{rid}/preparar").status_code == 401
    mala = {"Authorization": "Basic " + base64.b64encode(b"joaquin:otra").decode()}
    assert c.get(BANDEJA, headers=mala).status_code == 401


def test_el_listado_muestra_referencia_fecha_email_archivo_y_estado(env):
    c, _ = env
    rid = _pedido(c, "ana@example.com", "mi_plano.png")
    html = c.get(BANDEJA, headers=AUTH).get_data(as_text=True)
    for esperado in (rid, "ana@example.com", "mi_plano.png", "RECEIVED", "PREPARAR EN LAB"):
        assert esperado in html


def test_preparar_crea_una_propiedad_con_el_plano_y_redirige(env):
    c, data = env
    rid = _pedido(c)
    r = _preparar(c, rid)
    assert r.status_code == 303
    ped = _db(data, "SELECT * FROM plano_requests WHERE request_id=?", (rid,))[0]
    assert ped["status"] == "IN_PROGRESS" and ped["property_id"] and ped["prepared_at"]
    assert r.headers["Location"].endswith(f"/lab/p/{ped['property_id']}")
    props = _db(data, "SELECT * FROM properties")
    assert len(props) == 1 and props[0]["property_id"] == ped["property_id"]
    a = _db(data, "SELECT * FROM property_assets WHERE property_id=?", (ped["property_id"],))
    assert len(a) == 1 and a[0]["kind"] == "FLOORPLAN_ORIGINAL"
    from webapp.domain import assets
    assert open(assets.path_of(dict(a[0])), "rb").read() == PNG
    # la propiedad tiene su concesión, como cualquiera del LAB
    assert _db(data, "SELECT * FROM pack_grants WHERE property_id=?", (ped["property_id"],))
    # y la página existente del LAB la abre
    assert c.get(r.headers["Location"], headers=AUTH).status_code == 200
    # el pedido original sigue intacto en su directorio
    assert os.listdir(data / "plano_requests" / rid)


def test_repetir_el_post_no_crea_otra_propiedad(env):
    c, data = env
    rid = _pedido(c)
    r1 = _preparar(c, rid)
    r2 = _preparar(c, rid)
    assert r2.status_code == 303 and r2.headers["Location"] == r1.headers["Location"]
    assert len(_db(data, "SELECT 1 FROM properties")) == 1
    assert len(_db(data, "SELECT 1 FROM property_assets")) == 1


def test_el_reclamo_atomico_gana_uno_solo(env):
    c, data = env
    rid = _pedido(c)
    from webapp import pedidos
    assert pedidos._reclamar(rid) is True
    assert pedidos._reclamar(rid) is False
    # mientras está reclamado, un segundo preparar no crea nada
    assert pedidos.preparar(rid) is None
    assert _db(data, "SELECT 1 FROM properties") == []


def test_un_pedido_preparado_enlaza_la_propiedad_y_no_ofrece_otro_boton(env):
    c, data = env
    rid = _pedido(c)
    _preparar(c, rid)
    pid = _db(data, "SELECT property_id FROM plano_requests")[0]["property_id"]
    html = c.get(BANDEJA, headers=AUTH).get_data(as_text=True)
    assert f"/lab/p/{pid}" in html and "IN_PROGRESS" in html
    assert "PREPARAR EN LAB" not in html


def test_si_falla_a_mitad_el_pedido_vuelve_a_received_sin_propiedad(env, monkeypatch):
    c, data = env
    rid = _pedido(c)
    from webapp.domain import assets

    def roto(*a, **k):
        raise assets.AssetError("falla simulada")
    monkeypatch.setattr(assets, "save_upload", roto)
    with pytest.raises(assets.AssetError):
        from webapp import pedidos
        pedidos.preparar(rid)
    ped = _db(data, "SELECT * FROM plano_requests")[0]
    assert ped["status"] == "RECEIVED" and ped["property_id"] is None
    assert _db(data, "SELECT 1 FROM properties") == []
    assert _db(data, "SELECT 1 FROM pack_grants") == []
    assert _db(data, "SELECT 1 FROM property_assets") == []
    assert not (data / "properties").exists() or not os.listdir(data / "properties")
    # reintentar después de arreglar la falla funciona y deja una sola propiedad
    monkeypatch.undo()
    assert _preparar(c, rid).status_code == 303
    assert len(_db(data, "SELECT 1 FROM properties")) == 1


def test_un_archivo_faltante_no_declara_el_pedido_preparado(env):
    c, data = env
    rid = _pedido(c)
    for f in os.listdir(data / "plano_requests" / rid):
        os.remove(data / "plano_requests" / rid / f)
    from webapp import pedidos
    with pytest.raises(pedidos.PrepararError):
        pedidos.preparar(rid)
    assert _db(data, "SELECT status FROM plano_requests")[0]["status"] == "RECEIVED"
    assert _db(data, "SELECT 1 FROM properties") == []


def test_el_contenido_invalido_no_entra_a_la_capa_de_dominio(env):
    """La copia pasa por `assets.save_upload`: un archivo cuyo contenido no coincide se rechaza."""
    c, data = env
    rid = _pedido(c)
    d = data / "plano_requests" / rid
    f = d / os.listdir(d)[0]
    f.write_bytes(b"esto no es un png")
    from webapp import pedidos
    from webapp.domain import assets
    with pytest.raises(assets.AssetError):
        pedidos.preparar(rid)
    assert _db(data, "SELECT status FROM plano_requests")[0]["status"] == "RECEIVED"
    assert _db(data, "SELECT 1 FROM properties") == []


def test_id_invalido_o_inexistente_da_404(env):
    c, _ = env
    assert c.post("/lab/pedidos/../preparar", headers=AUTH).status_code == 404
    assert c.post("/lab/pedidos/x/preparar", headers=AUTH).status_code == 404
    assert c.post("/lab/pedidos/pc_" + "0" * 32 + "/preparar", headers=AUTH).status_code == 404


def test_preparar_no_ejecuta_motor_ni_abre_red(env, monkeypatch):
    c, data = env
    rid = _pedido(c)
    import socket
    from webapp import engine

    def prohibido(*a, **k):
        raise AssertionError("no debe ejecutar motor ni abrir red")
    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(engine, "submit", prohibido, raising=False)
    monkeypatch.setattr(engine, "enqueue", prohibido, raising=False)
    assert _preparar(c, rid).status_code == 303
    assert _db(data, "SELECT 1 FROM cases") == []
    assert _db(data, "SELECT 1 FROM runs") == []
    src = open(os.path.join(ROOT, "webapp", "pedidos.py"), encoding="utf-8").read()
    for ajeno in ("engine", "requests", "urllib", "httpx", "subprocess", "socket"):
        assert f"import {ajeno}" not in src and f"from . import {ajeno}" not in src


def test_el_formulario_publico_de_e41_sigue_sin_auth(env):
    c, _ = env
    assert c.get("/planos/solicitar").status_code == 200
    assert c.get("/planos/").status_code == 200
    _pedido(c)


def test_migracion_agrega_columnas_a_una_base_de_e41(tmp_path, monkeypatch):
    data = tmp_path / "d"
    data.mkdir()
    con = sqlite3.connect(str(data / "escalimetro.db"))
    con.execute("CREATE TABLE plano_requests (request_id TEXT PRIMARY KEY, email TEXT NOT NULL, "
                "plan_file TEXT NOT NULL, original_filename TEXT, mime TEXT NOT NULL, "
                "size_bytes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'RECEIVED', "
                "created_at TEXT NOT NULL)")
    con.commit()
    con.close()
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(data))
    from webapp import store
    importlib.reload(store)
    store.init()
    cols = {r["name"] for r in _db(data, "PRAGMA table_info(plano_requests)")}
    assert {"property_id", "prepared_at"} <= cols


def test_src_sigue_congelado():
    out = subprocess.run(["git", "diff", "6324b1f", "HEAD", "--", "src/"], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout == ""
