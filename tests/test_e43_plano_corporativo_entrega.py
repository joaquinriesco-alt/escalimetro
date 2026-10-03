"""E43 — Plano Corporativo revisable + enlace público de entrega.

La generación real necesita un shell confirmado del motor; acá se sustituye sólo el render
(`_shell_of` + `commercial_svg`) para ejercitar `publish_commercial_floorplan` de verdad —incluida su
purga del comercial anterior— sin correr el motor. Datos de prueba: example.com y bytes mínimos.
"""
from __future__ import annotations

import base64
import importlib
import io
import json
import os
import re
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
AUTH = {"Authorization": "Basic " + base64.b64encode(b"joaquin:secreta").decode()}
EMAIL = "cliente.privado@example.com"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    data = tmp_path / "d"
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(data))
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "secreta")
    monkeypatch.setenv("ESCALIMETRO_USER", "joaquin")
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for m in ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.entrega",
              "webapp.public", "webapp.domain.assets", "webapp.domain.properties",
              "webapp.domain.grants", "webapp.domain.entitlements", "webapp.domain.floorplan",
              "webapp.pedidos", "webapp.lab", "webapp.app"):
        importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app().test_client(), data


def _db(data, sql, args=()):
    con = sqlite3.connect(str(data / "escalimetro.db"))
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def _pedido(c, email=EMAIL):
    r = c.post("/planos/solicitar", data={"email": email, "plano": (io.BytesIO(PNG), "plano.png")},
               content_type="multipart/form-data")
    return r.headers["Location"].rsplit("/", 1)[1]


def _preparado(c, **kw):
    rid = _pedido(c, **kw)
    r = c.post(f"/lab/pedidos/{rid}/preparar", headers=AUTH)
    assert r.status_code == 303
    pid = r.headers["Location"].rsplit("/", 1)[1]
    return rid, pid


def _geometria(pid, listo=True):
    """Floorplate guardado que declara (o no) `ready_for_layout`; no corre el motor."""
    from webapp import store
    from webapp.domain import properties
    cid = "c_" + pid
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,status,"
             "track) VALUES (?,?,?,?,?,?,'READY','DEVELOPMENT')",
             (cid, "Caso", "a.png", "a.png", "image/png", store.now()))
    d = os.path.join(store.case_dir(cid), "outputs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
        json.dump({"shell_readiness": {"ready_for_layout": listo,
                                       "requires_confirmation": [] if listo else ["scale"]}}, fh)
    properties.link_case(pid, cid)


@pytest.fixture()
def render_falso(monkeypatch):
    """Sustituye sólo el trazado de la planta (necesita un shell real del motor). Cada llamada
    produce bytes distintos, para distinguir un candidato regenerado."""
    from webapp.domain import commercial, floorplan
    llamadas = []

    class _Area:
        area = 50.0

    class _Shell:
        usable = _Area()

    monkeypatch.setattr(floorplan, "_shell_of", lambda cid: _Shell())
    monkeypatch.setattr(commercial, "commercial_svg", lambda *a, **k: (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        f'<rect width="{len(llamadas)}" height="10"/></svg>'))
    original = floorplan.publish_commercial_floorplan

    def espia(pid):
        llamadas.append(pid)
        return original(pid)
    monkeypatch.setattr(floorplan, "publish_commercial_floorplan", espia)
    return llamadas


def _listo(c):
    rid, pid = _preparado(c)
    _geometria(pid)
    return rid, pid


def _generar(c, rid):
    return c.post(f"/lab/pedidos/{rid}/generar", headers=AUTH)


def _aprobar(c, rid, pid):
    from webapp.domain import assets
    cand = assets.first_of_kind(pid, assets.FLOORPLAN_COMMERCIAL)
    return c.post(f"/lab/pedidos/{rid}/aprobar", headers=AUTH, data={"asset_id": cand["asset_id"]})


def _token(data, rid):
    return _db(data, "SELECT delivery_token t FROM plano_requests WHERE request_id=?", (rid,))[0]["t"]


# ---- auth ----------------------------------------------------------------------------------------
def test_toda_la_operacion_interna_exige_basic_auth(env):
    c, _ = env
    rid, _pid = _preparado(c)
    for metodo, url in (("get", f"/lab/pedidos/{rid}"), ("post", f"/lab/pedidos/{rid}/generar"),
                        ("get", f"/lab/pedidos/{rid}/candidato.png"),
                        ("post", f"/lab/pedidos/{rid}/aprobar")):
        assert getattr(c, metodo)(url).status_code == 401, url


# ---- readiness -----------------------------------------------------------------------------------
def test_sin_geometria_lista_generar_falla_controlado_y_no_crea_nada(env, render_falso):
    c, data = env
    rid, pid = _preparado(c)                      # sin caso: planta aún no lista
    html = c.get(f"/lab/pedidos/{rid}", headers=AUTH).get_data(as_text=True)
    assert "requiere revisión" in html and "GENERAR PLANO CORPORATIVO" not in html
    r = _generar(c, rid)
    assert r.status_code == 409
    assert render_falso == []                     # ni siquiera se llamó a la salida existente
    assert _db(data, "SELECT 1 FROM property_assets WHERE kind='FLOORPLAN_COMMERCIAL'") == []
    assert _token(data, rid) is None


def test_con_geometria_no_confirmada_tampoco_genera(env, render_falso):
    c, data = env
    rid, pid = _preparado(c)
    _geometria(pid, listo=False)
    assert _generar(c, rid).status_code == 409
    assert render_falso == []
    assert _db(data, "SELECT 1 FROM property_assets WHERE kind='FLOORPLAN_COMMERCIAL'") == []


def test_publish_commercial_floorplan_real_devuelve_none_si_no_esta_lista(env):
    c, _ = env
    _rid, pid = _preparado(c)
    _geometria(pid, listo=False)
    from webapp.domain import floorplan
    assert floorplan.publish_commercial_floorplan(pid) is None


def test_el_pedido_preparado_conserva_su_propiedad(env):
    c, data = env
    rid, pid = _preparado(c)
    assert _db(data, "SELECT property_id p FROM plano_requests WHERE request_id=?",
               (rid,))[0]["p"] == pid


# ---- generación + vista previa -------------------------------------------------------------------
def test_generar_usa_publish_commercial_floorplan_y_deja_un_unico_candidato(env, render_falso):
    c, data = env
    rid, pid = _listo(c)
    html = c.get(f"/lab/pedidos/{rid}", headers=AUTH).get_data(as_text=True)
    assert "lista para producir" in html and "GENERAR PLANO CORPORATIVO" in html
    assert _generar(c, rid).status_code == 303
    assert _generar(c, rid).status_code == 303    # regenerar: sigue habiendo uno solo
    assert render_falso == [pid, pid]
    filas = _db(data, "SELECT asset_id FROM property_assets WHERE property_id=? AND "
                      "kind='FLOORPLAN_COMMERCIAL'", (pid,))
    assert len(filas) == 1


def test_el_candidato_se_previsualiza_internamente_y_no_hay_enlace(env, render_falso):
    c, data = env
    rid, pid = _listo(c)
    _generar(c, rid)
    r = c.get(f"/lab/pedidos/{rid}/candidato.png", headers=AUTH)
    assert r.status_code == 200 and r.data.startswith(b"\x89PNG")
    html = c.get(f"/lab/pedidos/{rid}", headers=AUTH).get_data(as_text=True)
    assert "APROBAR PARA ENTREGA" in html and "/planos/entrega/" not in html
    assert _token(data, rid) is None              # ningún link antes de aprobar
    assert _db(data, "SELECT status s FROM plano_requests")[0]["s"] == "IN_PROGRESS"


def test_sin_candidato_no_hay_preview_ni_se_puede_aprobar(env, render_falso):
    c, data = env
    rid, pid = _listo(c)
    assert c.get(f"/lab/pedidos/{rid}/candidato.png", headers=AUTH).status_code == 404
    r = c.post(f"/lab/pedidos/{rid}/aprobar", headers=AUTH, data={"asset_id": "a_inventado"})
    assert r.status_code == 409 and _token(data, rid) is None


# ---- aprobación + token --------------------------------------------------------------------------
def test_aprobar_persiste_asset_token_timestamp_y_estado(env, render_falso):
    c, data = env
    rid, pid = _listo(c)
    _generar(c, rid)
    assert _aprobar(c, rid, pid).status_code == 303
    f = _db(data, "SELECT * FROM plano_requests WHERE request_id=?", (rid,))[0]
    assert f["status"] == "READY_FOR_DELIVERY" and f["status"] != "DELIVERED"
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", f["delivery_token"])
    assert f["approved_at"] and f["delivery_asset_id"]
    a = _db(data, "SELECT kind, property_id FROM property_assets WHERE asset_id=?",
            (f["delivery_asset_id"],))[0]
    assert a["kind"] == "FLOORPLAN_DELIVERED" and a["property_id"] == pid
    html = c.get(f"/lab/pedidos/{rid}", headers=AUTH).get_data(as_text=True)
    assert f"/planos/entrega/{f['delivery_token']}" in html     # el operador puede copiarlo


def test_los_tokens_son_distintos_entre_pedidos(env, render_falso):
    c, data = env
    tokens = set()
    for i in range(2):
        rid, pid = _preparado(c, email=f"x{i}@example.com")
        _geometria(pid)
        _generar(c, rid)
        _aprobar(c, rid, pid)
        tokens.add(_token(data, rid))
    assert len(tokens) == 2


def test_aprobar_un_asset_que_no_es_el_candidato_actual_falla(env, render_falso):
    c, data = env
    rid, pid = _listo(c)
    _generar(c, rid)
    r = c.post(f"/lab/pedidos/{rid}/aprobar", headers=AUTH, data={"asset_id": "a_ajeno"})
    assert r.status_code == 409 and _token(data, rid) is None


def test_repetir_la_aprobacion_es_idempotente(env, render_falso):
    c, data = env
    rid, pid = _listo(c)
    _generar(c, rid)
    _aprobar(c, rid, pid)
    antes = _db(data, "SELECT delivery_token, delivery_asset_id, approved_at FROM plano_requests")[0]
    assert _aprobar(c, rid, pid).status_code == 303
    despues = _db(data, "SELECT delivery_token, delivery_asset_id, approved_at FROM plano_requests")[0]
    assert tuple(antes) == tuple(despues)
    assert len(_db(data, "SELECT 1 FROM property_assets WHERE kind='FLOORPLAN_DELIVERED'")) == 1


def test_el_reclamo_de_aprobacion_es_atomico(env, render_falso):
    """Dos aprobaciones que pasaron el chequeo previo: sólo una fija el token y la otra no deja
    copias huérfanas."""
    c, data = env
    rid, pid = _listo(c)
    _generar(c, rid)
    from webapp import entrega, store
    from webapp.domain import assets
    cand = assets.first_of_kind(pid, assets.FLOORPLAN_COMMERCIAL)
    real = entrega.store.connect

    class Conn:                                    # la otra aprobación gana justo antes del CAS
        def __init__(self, inner):
            self.inner = inner

        def execute(self, sql, args=()):
            if sql.startswith("UPDATE plano_requests SET delivery_token"):
                self.inner.execute("UPDATE plano_requests SET delivery_token='ganador' "
                                   "WHERE request_id=?", (rid,))
            return self.inner.execute(sql, args)

        def __getattr__(self, n):
            return getattr(self.inner, n)
    entrega.store.connect = lambda: Conn(real())
    try:
        assert entrega.aprobar(rid, cand["asset_id"]) is None
    finally:
        entrega.store.connect = real
    assert _token(data, rid) == "ganador"
    assert _db(data, "SELECT 1 FROM property_assets WHERE kind='FLOORPLAN_DELIVERED'") == []


# ---- ruta pública --------------------------------------------------------------------------------
def _aprobado(c, data):
    rid, pid = _listo(c)
    _generar(c, rid)
    _aprobar(c, rid, pid)
    return rid, pid, _token(data, rid)


def test_la_ruta_publica_responde_sin_auth_y_sirve_solo_el_plano_aprobado(env, render_falso):
    c, data = env
    rid, pid, tok = _aprobado(c, data)
    r = c.get(f"/planos/entrega/{tok}")
    assert r.status_code == 200 and "Plano Corporativo listo" in r.get_data(as_text=True)
    img = c.get(f"/planos/entrega/{tok}/plano.png")
    assert img.status_code == 200 and img.mimetype == "image/png" and img.data.startswith(b"\x89PNG")
    from webapp.domain import assets
    delivered = assets.first_of_kind(pid, assets.FLOORPLAN_DELIVERED)
    assert img.data == open(assets.path_of(delivered), "rb").read()
    d = c.get(f"/planos/entrega/{tok}/plano.png?descargar=1")
    assert "attachment" in d.headers["Content-Disposition"]


def test_la_pagina_publica_no_expone_pii_ids_paths_ni_navegacion(env, render_falso):
    c, data = env
    rid, pid, tok = _aprobado(c, data)
    from webapp import store
    from webapp.domain import assets
    cand = assets.first_of_kind(pid, assets.FLOORPLAN_COMMERCIAL)
    cuerpos = [c.get(f"/planos/entrega/{tok}").get_data(as_text=True)]
    h = c.get(f"/planos/entrega/{tok}/plano.png")
    cuerpos.append(" ".join(f"{k}:{v}" for k, v in h.headers.items()))
    for cuerpo in cuerpos:
        for secreto in (EMAIL, "cliente.privado", rid, pid, cand["asset_id"], str(data),
                        store.DATA_DIR, "/lab", "case_id", "FLOORPLAN", "ORIGINAL"):
            assert secreto not in cuerpo, secreto
    assert "noindex" in c.get(f"/planos/entrega/{tok}").get_data(as_text=True)


def test_tokens_inexistentes_o_malformados_dan_404(env, render_falso):
    c, data = env
    _rid, _pid, tok = _aprobado(c, data)
    malos = ["x", "a" * 43, tok[:-1], tok + "a", "../" + tok[3:], tok.upper(), "%00" * 14]
    for m in malos:
        assert c.get(f"/planos/entrega/{m}").status_code == 404, m
        assert c.get(f"/planos/entrega/{m}/plano.png").status_code == 404, m


def test_un_pedido_sin_aprobar_no_tiene_ruta_publica(env, render_falso):
    c, data = env
    rid, pid = _listo(c)
    _generar(c, rid)
    assert c.get(f"/planos/entrega/{rid}").status_code == 404
    assert c.get(f"/planos/entrega/{pid}").status_code == 404


def test_un_token_nunca_sirve_el_asset_de_otro_pedido(env, render_falso):
    """Aunque la base quedara apuntando a un asset de OTRA propiedad, la barrera por propiedad lo
    niega; y cada token sirve sus propios bytes."""
    c, data = env
    ridA, pidA, tokA = _aprobado(c, data)
    ridB, pidB = _preparado(c, email="otro@example.com")
    _geometria(pidB)
    _generar(c, ridB)
    _aprobar(c, ridB, pidB)
    tokB = _token(data, ridB)
    a = c.get(f"/planos/entrega/{tokA}/plano.png").data
    b = c.get(f"/planos/entrega/{tokB}/plano.png").data
    assert a != b
    # corrupción simulada: el pedido B apunta al asset entregado de A
    from webapp import store
    from webapp.domain import assets
    aidA = assets.first_of_kind(pidA, assets.FLOORPLAN_DELIVERED)["asset_id"]
    store.ex("UPDATE plano_requests SET delivery_asset_id=? WHERE request_id=?", (aidA, ridB))
    assert c.get(f"/planos/entrega/{tokB}/plano.png").status_code == 404
    assert c.get(f"/planos/entrega/{tokA}/plano.png").data == a
    # y un asset que no es FLOORPLAN_DELIVERED tampoco se sirve
    ori = assets.first_of_kind(pidA, assets.FLOORPLAN_ORIGINAL)["asset_id"]
    store.ex("UPDATE plano_requests SET delivery_asset_id=? WHERE request_id=?", (ori, ridA))
    assert c.get(f"/planos/entrega/{tokA}/plano.png").status_code == 404


def test_regenerar_no_cambia_el_plano_detras_del_enlace_aprobado(env, render_falso):
    c, data = env
    rid, pid, tok = _aprobado(c, data)
    antes = c.get(f"/planos/entrega/{tok}/plano.png").data
    assert _generar(c, rid).status_code == 303                 # nuevo candidato, bytes distintos
    from webapp.domain import assets
    cand = assets.first_of_kind(pid, assets.FLOORPLAN_COMMERCIAL)
    assert open(assets.path_of(cand), "rb").read() != antes
    assert c.get(f"/planos/entrega/{tok}/plano.png").data == antes
    assert _token(data, rid) == tok
    # y aprobar de nuevo no rota ni sustituye nada
    _aprobar(c, rid, pid)
    assert _token(data, rid) == tok
    assert c.get(f"/planos/entrega/{tok}/plano.png").data == antes


def test_abrir_el_enlace_no_cambia_el_estado_ni_escribe(env, render_falso):
    c, data = env
    _rid, _pid, tok = _aprobado(c, data)
    antes = [tuple(r) for r in _db(data, "SELECT * FROM plano_requests")]
    n = len(_db(data, "SELECT 1 FROM property_assets"))
    for _ in range(3):
        c.get(f"/planos/entrega/{tok}")
        c.get(f"/planos/entrega/{tok}/plano.png")
    assert [tuple(r) for r in _db(data, "SELECT * FROM plano_requests")] == antes
    assert len(_db(data, "SELECT 1 FROM property_assets")) == n
    assert _db(data, "SELECT status s FROM plano_requests")[0]["s"] != "DELIVERED"


def test_el_email_nunca_llega_al_titulo_dibujado_en_el_plano(env, render_falso, monkeypatch):
    """`commercial_svg` imprime el título de la propiedad en la imagen entregada."""
    from webapp import store
    from webapp.domain import commercial
    vistos = []
    base = commercial.commercial_svg
    monkeypatch.setattr(commercial, "commercial_svg",
                        lambda shell, titulo="", *a, **k: (vistos.append(titulo), base(shell, titulo))[1])
    c, data = env
    rid, pid = _listo(c)
    # propiedad preparada antes del arreglo: el título trae el email
    store.ex("UPDATE properties SET title=? WHERE property_id=?", ("Plano Corporativo · " + EMAIL, pid))
    assert _generar(c, rid).status_code == 303
    assert vistos and all(EMAIL not in t for t in vistos)
    # y una propiedad nueva ya nace sin él
    rid2, pid2 = _preparado(c, email="nuevo@example.com")
    assert "nuevo@example.com" not in store.q1("SELECT title FROM properties WHERE property_id=?",
                                               (pid2,))["title"]


# ---- sin red ni motor ----------------------------------------------------------------------------
def test_generar_aprobar_y_abrir_el_enlace_no_abren_red_ni_ejecutan_motor(env, render_falso, monkeypatch):
    c, data = env
    rid, pid = _listo(c)
    import socket
    import subprocess

    from webapp import engine

    def prohibido(*a, **k):
        raise AssertionError("no debe abrir red ni ejecutar motor")
    monkeypatch.setattr(socket.socket, "connect", prohibido)
    monkeypatch.setattr(subprocess, "Popen", prohibido)
    monkeypatch.setattr(engine, "submit", prohibido, raising=False)
    monkeypatch.setattr(engine, "enqueue", prohibido, raising=False)
    _generar(c, rid)
    _aprobar(c, rid, pid)
    tok = _token(data, rid)
    assert c.get(f"/planos/entrega/{tok}").status_code == 200
    assert _db(data, "SELECT 1 FROM runs") == []
    for mod in ("entrega.py", "public.py"):
        src = open(os.path.join(ROOT, "webapp", mod), encoding="utf-8").read()
        for ajeno in ("engine", "requests", "urllib", "httpx", "subprocess", "socket", "layouts",
                      "staging", "providers"):
            assert f"import {ajeno}" not in src and f"from . import {ajeno}" not in src


# ---- E41/E42 siguen ------------------------------------------------------------------------------
def test_el_formulario_e41_y_la_preparacion_e42_siguen_funcionando(env):
    c, data = env
    assert c.get("/planos/solicitar").status_code == 200
    rid, pid = _preparado(c)
    assert c.get(f"/lab/p/{pid}", headers=AUTH).status_code == 200
    html = c.get("/lab/pedidos/", headers=AUTH).get_data(as_text=True)
    assert rid in html and "Entrega" in html


def test_la_migracion_agrega_las_columnas_a_bases_de_e42(tmp_path, monkeypatch):
    data = tmp_path / "d"
    data.mkdir()
    con = sqlite3.connect(str(data / "escalimetro.db"))
    con.execute("CREATE TABLE plano_requests (request_id TEXT PRIMARY KEY, email TEXT NOT NULL, "
                "plan_file TEXT NOT NULL, original_filename TEXT, mime TEXT NOT NULL, "
                "size_bytes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'RECEIVED', "
                "created_at TEXT NOT NULL, property_id TEXT, prepared_at TEXT)")
    con.commit()
    con.close()
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(data))
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    from webapp import store
    importlib.reload(store)
    store.init()
    cols = {r["name"] for r in _db(data, "PRAGMA table_info(plano_requests)")}
    assert {"delivery_token", "delivery_asset_id", "approved_at"} <= cols
