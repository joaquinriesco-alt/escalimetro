"""E32.2 §15 — tests de CONTRATO del modelo de derechos corregido.

Lo que se protege es una distinción comercial, no una técnica:

    un PACK cubre UNA propiedad · una cuenta puede comprar MUCHOS packs
    PRO no es "la forma de tener una segunda propiedad": es trabajar las que ya tenés

Por eso los tres casos que más importan son: que tres compras ONE_OFF convivan sin Pro, que el
bloqueo por falta de Pack diga PACK_REQUIRED y no PRO_REQUIRED, y que cambiar una propiedad a Pro
no transforme a las demás.
"""
from __future__ import annotations

import importlib
import io
import os
import re
import struct
import sys
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

MODULOS = ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.briefs",
           "webapp.domain.settings", "webapp.domain.entitlements", "webapp.domain.grants",
           "webapp.domain.presets", "webapp.domain.properties", "webapp.domain.assets",
           "webapp.domain.branding", "webapp.domain.fits", "webapp.domain.floorplan",
           "webapp.domain.proposal", "webapp.domain.visual", "webapp.domain.pilot",
           "webapp.providers.base", "webapp.providers.gemini", "webapp.providers.openai_images",
           "webapp.providers.bfl", "webapp.providers", "webapp.domain.staging",
           "webapp.domain.packs", "webapp.domain.lab", "webapp.benchmark", "webapp.customer",
           "webapp.staging_ui", "webapp.lab", "webapp.app")


def _png(w: int = 64, h: int = 48) -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x90\xa0" * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ESCALIMETRO_DEV", "1")
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for v in ("GEMINI_API_KEY", "OPENAI_API_KEY", "BFL_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    for m in MODULOS:
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def dom(app):
    from webapp.domain import assets, entitlements, fits, grants, packs, properties, staging
    return {"assets": assets, "entitlements": entitlements, "fits": fits, "grants": grants,
            "packs": packs, "properties": properties, "staging": staging}


def _lab(client, titulo="Prop", product="ONE_OFF"):
    """E33 saca «producto simulado» del flujo principal: se elige desde las herramientas
    técnicas, que es donde corresponde. El derecho sigue siendo por propiedad."""
    r = client.post("/lab/new", data={"title": titulo, "city": "Santiago"}, follow_redirects=True)
    pid = re.search(rb"p_[0-9a-f]{12}", r.data).group().decode()
    if product != "ONE_OFF":
        client.post(f"/lab/debug/producto/{pid}", data={"product": product})
    return pid


# ===================================================================================================
# A — MUCHAS COMPRAS ONE_OFF
# ===================================================================================================
def test_una_cuenta_puede_tener_varias_propiedades_one_off(client, dom):
    """El caso del corredor chico: tres Packs, tres propiedades, cero Pro."""
    ids = [_lab(client, f"Pack 0{i}") for i in (1, 2, 3)]
    assert len(dom["properties"].listing()) == 3
    for pid in ids:
        assert dom["entitlements"].product_of(pid) == "ONE_OFF"
        assert dom["grants"].of_property(pid) is not None
    assert dom["grants"].summary()["assigned"] == 3


def test_cada_concesion_pertenece_a_una_sola_propiedad(client, dom):
    a, b = _lab(client, "A"), _lab(client, "B")
    ga, gb = dom["grants"].of_property(a), dom["grants"].of_property(b)
    assert ga["grant_id"] != gb["grant_id"]
    assert ga["property_id"] == a and gb["property_id"] == b


def test_una_concesion_no_se_asigna_dos_veces(client, dom):
    a, b = _lab(client, "A"), _lab(client, "B")
    g = dom["grants"].of_property(a)["grant_id"]
    with pytest.raises(dom["grants"].PackRequired):
        dom["grants"].assign(g, b)
    assert dom["grants"].of_property(a)["grant_id"] == g


def test_la_segunda_propiedad_no_requiere_pro(client, dom):
    """El corazón del bug: tener una propiedad A no puede volver a B un asunto de Pro."""
    a = _lab(client, "A")
    b = _lab(client, "B")
    assert dom["entitlements"].product_of(a) == dom["entitlements"].product_of(b) == "ONE_OFF"
    # y ninguna de las dos gana capacidades Pro por existir la otra
    for pid in (a, b):
        assert dom["entitlements"].allows(pid, dom["entitlements"].PROSPECT_FIT_REQUESTS) is False


def test_el_producto_ya_no_tiene_una_capacidad_de_varias_propiedades(dom):
    """«Tener otra propiedad» no es una capacidad de producto: es otra compra."""
    e = dom["entitlements"]
    assert not hasattr(e, "MULTIPLE_PROPERTIES")
    assert "MULTIPLE_PROPERTIES" not in e.CAPABILITIES
    for p in e.PRODUCTS:
        assert "properties" not in e.LIMITS[p]


# ===================================================================================================
# B — CREACIÓN EN LA SUPERFICIE DE CLIENTE
# ===================================================================================================
def test_con_un_pack_disponible_el_cliente_crea_su_propiedad(client, dom):
    dom["grants"].create("ONE_OFF", "PURCHASE", "compra")
    assert dom["grants"].summary()["available"] == 1
    r = client.post("/properties/new", data={"title": "Oficina 403"}, follow_redirects=True)
    assert r.status_code == 200
    assert dom["grants"].summary()["available"] == 0
    assert dom["grants"].summary()["assigned"] == 1


def test_sin_pack_disponible_el_cliente_no_crea_nada(client, dom):
    dom["grants"].create("ONE_OFF", "PURCHASE")
    client.post("/properties/new", data={"title": "A"}, follow_redirects=True)
    assert client.get("/properties/new").status_code == 403
    assert client.post("/properties/new", data={"title": "B"}).status_code == 403
    assert len(dom["properties"].listing()) == 1          # no se creó una propiedad huérfana


def test_el_motivo_del_bloqueo_es_falta_de_pack_no_falta_de_pro(client, dom):
    """§5 — `PackRequired` NO es `EntitlementError`. Confundirlos era el error comercial."""
    e = dom["entitlements"]
    assert not issubclass(dom["grants"].PackRequired, e.EntitlementError)
    assert dom["grants"].PackRequired.reason == "PACK_REQUIRED"
    _lab(client, "A")                                    # consume su propia concesión simulada
    texto = client.get("/properties/new").get_data(as_text=True)
    assert "otro Pack" in texto
    assert "Necesitas Escalímetro Pro" not in texto
    assert "hace falta Escalímetro Pro" not in texto


def test_la_pantalla_ofrece_otro_pack_y_explica_pro_por_lo_que_hace(client, dom):
    """§6 — Pro se vende por su valor real, no por «tener una segunda propiedad»."""
    _lab(client, "A")
    texto = client.get("/properties/new").get_data(as_text=True)
    assert "Cada Pack de publicación corresponde a una propiedad" in texto
    assert "seguir trabajando" in texto
    for valor in ("prospecto", "alternativas", "generar"):
        assert valor in texto.lower()


# ===================================================================================================
# C — CAPACIDADES POR PROPIEDAD
# ===================================================================================================
def test_una_propiedad_one_off_bloquea_los_prospectos(client, dom):
    pid = _lab(client, "Pack")
    with pytest.raises(dom["entitlements"].EntitlementError):
        dom["fits"].create_prospect(pid, "Falabella", 40)


def test_una_propiedad_pro_los_permite(client, dom):
    pid = _lab(client, "Portfolio", product="PRO")
    fid = dom["fits"].create_prospect(pid, "Falabella", 40)
    assert dom["fits"].get(fid, pid) is not None
    e = dom["entitlements"]
    for cap in e.CAPABILITIES:
        assert e.allows(pid, cap) is True


def test_cambiar_una_propiedad_no_muta_a_las_otras(client, dom):
    """§13 caso 4 — el aislamiento que el modelo global no tenía."""
    a, b, c = _lab(client, "A"), _lab(client, "B"), _lab(client, "C")
    dom["entitlements"].set_product(b, "PRO")
    assert dom["entitlements"].product_of(b) == "PRO"
    assert dom["entitlements"].product_of(a) == "ONE_OFF"
    assert dom["entitlements"].product_of(c) == "ONE_OFF"
    dom["fits"].create_prospect(b, "Falabella", 40)
    with pytest.raises(dom["entitlements"].EntitlementError):
        dom["fits"].create_prospect(a, "Cencosud", 30)


def test_el_default_de_la_cuenta_no_cambia_las_propiedades_existentes(client, dom):
    """El ajuste global sobrevive sólo como valor inicial de una propiedad NUEVA."""
    a = _lab(client, "A")
    dom["entitlements"].set_default_product("PRO")
    assert dom["entitlements"].product_of(a) == "ONE_OFF"   # la vieja no se transforma
    b = _lab(client, "B", product="PRO")
    assert dom["entitlements"].product_of(b) == "PRO"


def test_las_capacidades_se_preguntan_por_propiedad(dom):
    """Ninguna función de capacidad acepta ya ser llamada sin propiedad."""
    e = dom["entitlements"]
    for fn in (e.allows, e.require, e.limit):
        with pytest.raises(TypeError):
            fn(e.ABC_ALTERNATIVES)                       # falta el property_id


def test_el_pack_entrega_una_alternativa_y_pro_las_tres_por_propiedad(client, dom):
    from webapp import store
    a, b = _lab(client, "A"), _lab(client, "B", product="PRO")
    for pid in (a, b):
        for alt in ("A", "B", "C"):
            dom["assets"].save_bytes(pid, dom["assets"].LAYOUT_RENDER, f"alt_{alt}.png", _png(),
                                     "image/png", metadata={"alt": alt,
                                                            "representative": alt == "A"})
    assert len(dom["packs"].layout_assets(a)) == 1
    assert len(dom["packs"].layout_assets(b)) == 3


# ===================================================================================================
# D — EL LAB ES UN OPERADOR
# ===================================================================================================
def test_el_operador_crea_muchas_propiedades_sin_tope(client, dom):
    for i in range(6):
        _lab(client, f"Test Pack {i:02d}")
    assert len(dom["properties"].listing()) == 6
    assert dom["grants"].summary()["assigned"] == 6
    assert client.get("/lab/new").status_code == 200      # nunca hay un 403 global por cantidad


def test_cada_propiedad_del_lab_trae_su_compra_simulada(client, dom):
    pid = _lab(client, "A")
    g = dom["grants"].of_property(pid)
    assert g["source"] == "SIMULATED_LAB" and g["status"] == "ASSIGNED"
    assert "simulada" in g["note"]


def test_el_operador_cambia_el_producto_de_una_propiedad_desde_la_web(client, dom):
    a, b = _lab(client, "A"), _lab(client, "B")
    assert client.post(f"/lab/debug/producto/{a}", data={"product": "PRO"}).status_code == 302
    assert dom["entitlements"].product_of(a) == "PRO"
    assert dom["entitlements"].product_of(b) == "ONE_OFF"
    # el cambio se ve en las herramientas técnicas, no en el flujo de producto
    html = client.get("/lab/debug").get_data(as_text=True)
    assert "Escalímetro Pro" in html


def test_el_lab_conserva_su_shell(client, dom):
    pid = _lab(client, "A")
    for url in ("/lab/", "/lab/new", "/lab/ajustes", f"/lab/p/{pid}"):
        html = client.get(url).get_data(as_text=True)
        assert 'href="/lab/"' in html and "herramienta interna" not in html


# ===================================================================================================
# E — MIGRACIÓN
# ===================================================================================================
def test_una_propiedad_heredada_recibe_su_concesion_y_no_pierde_nada(client, dom):
    """§9 — aditiva y conservadora: default ONE_OFF, sin inferir Pro por tener muchos outputs."""
    from webapp import store
    pid = dom["properties"].create("Heredada", "OFFICE", city="Santiago")
    dom["assets"].save_bytes(pid, dom["assets"].LAYOUT_RENDER, "a.png", _png(), "image/png",
                             metadata={"alt": "A"})
    # estado anterior a E32.2: la propiedad existe y no hay ninguna concesión que la cubra
    store.ex("DELETE FROM pack_grants WHERE property_id=?", (pid,))
    store.init()                                                     # la migración corre al arrancar
    assert dom["entitlements"].product_of(pid) == "ONE_OFF"
    g = dom["grants"].of_property(pid)
    assert g is not None and g["source"] == "LEGACY"
    assert len(dom["assets"].list_of_kind(pid, dom["assets"].LAYOUT_RENDER)) == 1


def test_la_migracion_es_idempotente(client, dom):
    from webapp import store
    pid = _lab(client, "A")
    antes = dom["grants"].of_property(pid)["grant_id"]
    store.init(); store.init()
    assert dom["grants"].of_property(pid)["grant_id"] == antes
    assert store.q1("SELECT COUNT(*) n FROM pack_grants")["n"] == 1


# ===================================================================================================
# F — REGRESIÓN
# ===================================================================================================
def test_las_superficies_siguen_respondiendo(client, dom):
    pid = _lab(client, "A")
    for url in ("/", "/healthz", "/review", "/settings", "/properties/", "/staging/",
                "/staging/benchmark", "/lab/", f"/lab/p/{pid}", f"/properties/{pid}"):
        assert client.get(url).status_code == 200, url


def test_el_motor_no_fue_tocado():
    import subprocess
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"E32.2 tocó el motor: {out.stdout}"
