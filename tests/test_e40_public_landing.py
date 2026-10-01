"""E40 — la landing pública es pública, y sólo ella.

Se prueba con contraseña puesta (como en producción): el modo dev abre todo y no probaría nada.
"""
from __future__ import annotations

import importlib
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

LANDING = "/planos/"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "secreta")
    monkeypatch.setenv("ESCALIMETRO_USER", "joaquin")
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for m in ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.app"):
        importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app().test_client()


def _texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_landing_200_sin_auth(client):
    r = client.get(LANDING)
    assert r.status_code == 200
    assert "WWW-Authenticate" not in r.headers


def test_solicitar_200_sin_auth_y_no_finge_un_pedido(client):
    r = client.get("/planos/solicitar")
    assert r.status_code == 200
    t = _texto(r.get_data(as_text=True))
    assert "próximamente" in t.lower()
    assert "<form" not in r.get_data(as_text=True)
    # el CTA no crea nada: ni POST ni estado
    assert client.post("/planos/solicitar").status_code == 405


@pytest.mark.parametrize("ruta", ["/", "/settings", "/lab/", "/properties/", "/property/",
                                  "/staging/", "/review/queue", "/lab/reconstruction/"])
def test_rutas_internas_siguen_rechazando_sin_auth(client, ruta):
    assert client.get(ruta).status_code in (401, 404, 308), ruta
    # las que existen deben ser 401, no un 200 ni un redirect hacia contenido
    assert client.get(ruta).status_code != 200


@pytest.mark.parametrize("ruta", ["/", "/lab/", "/properties/", "/settings"])
def test_rutas_internas_representativas_dan_401(client, ruta):
    r = client.get(ruta)
    assert r.status_code == 401
    assert "Basic" in r.headers["WWW-Authenticate"]


def test_post_interno_sigue_protegido(client):
    assert client.post("/upload").status_code == 401


def test_healthz_se_comporta_como_antes(client):
    # E40 no cambia /healthz: sigue sin auth y con el mismo contrato
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_hero_tres_productos_en_orden_y_cta(client):
    t = _texto(client.get(LANDING).get_data(as_text=True))
    assert "PLANOS QUE AYUDAN A VENDER" in t
    assert "SUBIR PROPIEDAD" in t
    i = [t.index(x) for x in ("Plano Corporativo", "Crear Plano", "PRO Layouts")]
    assert i == sorted(i)
    assert "PRODUCTO DE ENTRADA" in t
    assert "PLANTA + PROGRAMA" in t


def test_cta_apunta_a_la_pagina_honesta(client):
    html = client.get(LANDING).get_data(as_text=True)
    assert 'href="/planos/solicitar"' in html


def test_sin_precios_ni_ofertas_prohibidas(client):
    for ruta in (LANDING, "/planos/solicitar"):
        t = _texto(client.get(ruta).get_data(as_text=True))
        low = t.lower()
        assert not re.search(r"\$|\bclp\b|\busd\b|\buf\b|\bdesde\b|\d+\s?%", low), ruta
        for palabra in ("staging", "video", "vídeo", "scoring", "benchmark", "lab", "debug",
                        "ambientaci", "floorplate", "cp-sat", "herramienta interna"):
            assert not re.search(rf"\b{palabra}", low), (ruta, palabra)


def test_sin_fuga_de_contenido_interno(client):
    html = client.get(LANDING).get_data(as_text=True)
    for rastro in ("/lab", "/properties", "/case/", "/run/", "/review", "/upload", "/staging",
                   "/settings", "/healthz", "/property/", "uploads", "case_id", "base.html"):
        assert rastro not in html, rastro


def test_crear_plano_no_afirma_exactitud(client):
    t = _texto(client.get(LANDING).get_data(as_text=True)).lower()
    assert "esquemático" in t and "referencial" in t
    assert "exact" in t and "no un levantamiento" in t   # sólo para negarla
