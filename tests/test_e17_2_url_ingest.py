"""E17.2 §22 — contrato del ingest URL-first.

Dos cosas se protegen acá y la primera es de seguridad: **pegar una URL hace que el servidor se
conecte a donde diga esa URL**, y eso es SSRF. La segunda es la honestidad del estado: un
`SUCCESS` optimista arruinaría el experimento, porque la muestra mide justamente si podemos
analizar una publicación casi solos.
"""
from __future__ import annotations

import importlib
import json
import os
import struct
import subprocess
import sys
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

MODULOS = ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine",
           "webapp.domain.assets", "webapp.domain.units", "webapp.domain.potential.listings",
           "webapp.domain.potential.vision", "webapp.domain.potential.classify",
           "webapp.domain.potential.fetcher", "webapp.domain.potential.extract",
           "webapp.domain.potential.urlingest", "webapp.domain.potential.plans",
           "webapp.domain.potential.interventions", "webapp.domain.potential.analyzer",
           "webapp.domain.potential.demos", "webapp.domain.potential.reviews",
           "webapp.potential", "webapp.app")

PLANO_403 = os.path.join(ROOT, "cases", "001_gps_403", "original.png")


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ESCALIMETRO_DEV", "1")
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
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
    from webapp.domain.potential import (analyzer, classify, extract, fetcher, listings, plans,
                                         urlingest)
    return {"analyzer": analyzer, "classify": classify, "extract": extract, "fetcher": fetcher,
            "listings": listings, "plans": plans, "urlingest": urlingest}


def _png(w=1200, h=900, tinte=(150, 150, 150), ruido=False) -> bytes:
    """Un PNG real con tamaño y color controlados, para mover las mediciones a voluntad.

    Se arma con numpy y no con bucles de Python: un cuadro de 1200×900 son 1,08 millones de
    píxeles, y generarlos uno por uno hacía que la suite tardara minutos por test."""
    import numpy as np
    rng = np.random.default_rng(abs(hash(tinte)) % (2 ** 32))
    img = np.empty((h, w, 3), dtype=np.uint8)
    img[:, :] = np.array(tinte, dtype=np.uint8)
    if ruido:
        mascara = ((np.arange(h)[:, None] + np.arange(w)[None, :]) % 3) == 0
        img[mascara] = rng.integers(0, 256, size=(int(mascara.sum()), 3), dtype=np.uint8)
    crudo = np.concatenate(
        [np.zeros((h, 1), dtype=np.uint8), img.reshape(h, w * 3)], axis=1).tobytes()

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(crudo, 1)) + chunk(b"IEND", b""))


HTML_AVISO = """<!doctype html><html><head>
<title>Oficina en arriendo El Golf - UF 120</title>
<meta property="og:title" content="Oficina en arriendo El Golf">
<meta property="og:description" content="Oficina habilitada en el corazon de El Golf.">
<meta property="og:image" content="https://cdn.ejemplo.cl/D_NQ_NP_111111-MLC222222_0825-O-foto.jpg">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Oficina El Golf","sku":"MLC999",
 "image":"https://cdn.ejemplo.cl/D_NQ_NP_111111-MLC222222_0825-O-foto.jpg",
 "offers":{"@type":"Offer","price":120,"priceCurrency":"CLF"}}
</script></head><body>
<script>window.__PRELOADED_STATE__ = {"a":1};</script>
<div>{"id":"Superficie total","text":"543 m\\u00b2"},{"id":"Estacionamientos","text":"5"},
     {"id":"Ba\\u00f1os","text":"3"},{"id":"Bodegas","text":"1"}</div>
<img src="https://cdn.ejemplo.cl/D_NQ_NP_2X_111111-MLC222222_0825-F-foto.jpg">
<img src="https://cdn.ejemplo.cl/D_NQ_NP_333333-MLC444444_0825-O-otra.jpg">
<img src="https://cdn.ejemplo.cl/D_NQ_NP_555555-MLC666666_0825-O-tercera.jpg">
<img src="https://cdn.ejemplo.cl/logo-corredora.png">
<img src="https://cdn.ejemplo.cl/icons/whatsapp.png">
</body></html>"""


# ===================================================================================================
# A — SSRF Y SEGURIDAD (§17). Lo primero, porque es lo que puede hacer daño.
# ===================================================================================================
@pytest.mark.parametrize("url", [
    "http://localhost/admin", "http://127.0.0.1:5000/", "http://0.0.0.0/",
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/", "http://[::1]/",
])
def test_ssrf_direcciones_internas_bloqueadas(dom, url):
    """§17 — el endpoint de metadatos de nube sirve credenciales en texto plano a cualquiera que
    pueda hacerle un GET desde adentro. Eso es lo que esta lista impide."""
    with pytest.raises(dom["fetcher"].FetchError) as e:
        dom["fetcher"].validate(url)
    assert e.value.reason == dom["fetcher"].BLOCKED_HOST


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.cl/a", "gopher://x.cl/_x",
                                 "data:text/html,<b>x", "javascript:alert(1)"])
def test_ssrf_esquemas_bloqueados(dom, url):
    with pytest.raises(dom["fetcher"].FetchError) as e:
        dom["fetcher"].validate(url)
    assert e.value.reason == dom["fetcher"].BAD_SCHEME


def test_un_dominio_que_resuelve_a_una_ip_privada_se_bloquea(dom, monkeypatch):
    """Un nombre público puede apuntar a 127.0.0.1: es la forma clásica de saltarse un filtro que
    sólo mira si la URL «parece» externa."""
    import socket
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(dom["fetcher"].FetchError) as e:
        dom["fetcher"].validate("https://parece-publico.cl/aviso")
    assert e.value.reason == dom["fetcher"].BLOCKED_HOST


def test_se_revalida_cada_redireccion(dom, monkeypatch):
    """§17 — un 302 hacia la red interna es el bypass estándar. Cada salto se vuelve a validar."""
    import socket
    vistos = []

    def fake_getaddrinfo(host, *a, **k):
        vistos.append(host)
        return [(2, 1, 6, "", ("127.0.0.1" if host == "interno.cl" else "93.184.216.34", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    class _Resp:
        code = 302
        headers = {"Location": "http://interno.cl/secreto"}

    monkeypatch.setattr(dom["fetcher"], "_open", lambda *a, **k: _Resp())
    with pytest.raises(dom["fetcher"].FetchError) as e:
        dom["fetcher"].fetch_page("https://publico.cl/aviso")
    assert e.value.reason == dom["fetcher"].BLOCKED_HOST
    assert "interno.cl" in vistos, "el destino de la redirección tiene que revalidarse"


def test_el_tamano_de_la_respuesta_esta_acotado(dom, monkeypatch):
    """El corte es por bytes LEÍDOS: el `Content-Length` lo escribe el servidor remoto."""
    class _Resp:
        code = 200
        headers = {"Content-Type": "text/html", "Content-Length": "10"}

        def read(self, n):
            return b"x" * n

    monkeypatch.setattr(dom["fetcher"], "validate", lambda u: (u, ["93.184.216.34"]))
    monkeypatch.setattr(dom["fetcher"], "_open", lambda *a, **k: _Resp())
    with pytest.raises(dom["fetcher"].FetchError) as e:
        dom["fetcher"].fetch_page("https://publico.cl/gigante")
    assert e.value.reason == dom["fetcher"].TOO_LARGE


def test_el_tipo_de_contenido_se_valida(dom, monkeypatch):
    class _Resp:
        code = 200
        headers = {"Content-Type": "application/zip"}

        def read(self, n):
            return b"PK\x03\x04"

    monkeypatch.setattr(dom["fetcher"], "validate", lambda u: (u, ["93.184.216.34"]))
    monkeypatch.setattr(dom["fetcher"], "_open", lambda *a, **k: _Resp())
    with pytest.raises(dom["fetcher"].FetchError) as e:
        dom["fetcher"].fetch_page("https://publico.cl/archivo.zip")
    assert e.value.reason == dom["fetcher"].BAD_CONTENT_TYPE


# ===================================================================================================
# B — EXTRACCIÓN POR CAPAS (§3, §4)
# ===================================================================================================
def test_extraccion_json_ld(dom):
    """§3.A — la capa más estable: el portal lo publica PARA ser leído."""
    r = dom["extract"].extract(HTML_AVISO, "https://portal.cl/aviso")
    f = r["fields"]
    assert f["price"]["value"] == 120 and f["price"]["source"] == dom["extract"].JSON_LD
    assert f["currency"]["value"] == "CLF"
    assert f["publication_id"]["value"] == "MLC999"
    assert r["layers"]["json_ld"] == 1


def test_extraccion_open_graph_como_respaldo(dom):
    """§3.B — sin JSON-LD, Open Graph sigue estando."""
    html = HTML_AVISO.split('<script type="application/ld+json">')[0] + "</head><body></body></html>"
    f = dom["extract"].extract(html, "https://portal.cl/aviso")["fields"]
    assert f["title"]["value"] == "Oficina en arriendo El Golf"
    assert f["title"]["source"] == dom["extract"].OPEN_GRAPH
    assert "El Golf" in f["description"]["value"]


def test_extraccion_de_estado_embebido(dom):
    """§3.C — los pares que el portal serializa para pintar su propia ficha."""
    f = dom["extract"].extract(HTML_AVISO, "https://portal.cl/aviso")["fields"]
    assert f["total_area_m2"]["value"] == 543.0
    assert f["total_area_m2"]["source"] == dom["extract"].EMBEDDED_STATE
    assert f["parking"]["value"] == 5 and f["bathrooms"]["value"] == 3
    assert f["storage"]["value"] == 1
    assert len(f["_attributes"]["value"]) >= 4


def test_cada_campo_lleva_su_procedencia(dom):
    """§4 — un precio de un `Offer` y un número sacado del título no valen lo mismo."""
    f = dom["extract"].extract(HTML_AVISO, "https://portal.cl/aviso")["fields"]
    for k, v in f.items():
        if k.startswith("_"):
            continue
        assert v["source"] in dom["extract"].SOURCE_CONFIDENCE, k
        assert 0 < v["confidence"] <= 1.0
    # la capa más confiable gana sobre la menos confiable
    assert f["title"]["source"] == dom["extract"].JSON_LD


def test_los_numeros_en_castellano_se_leen_bien(dom):
    """«1.052 m²» son mil cincuenta y dos, no uno. Invertirlo es el error que nadie nota hasta
    que sale publicado."""
    p = dom["extract"].parse_number
    assert p("1.052 m²") == 1052.0 and p("0,63") == 0.63
    assert p("UF 662") == 662.0 and p("$ 1.250.000") == 1250000.0
    assert p("sin datos") is None and p(None) is None


def test_no_se_inventan_campos_ausentes(dom):
    """§8 — UNKNOWN / null es válido. Rellenar lo que falta haría mentir a la dimensión que
    justamente mide qué falta."""
    f = dom["extract"].extract("<html><head><title>x</title></head><body></body></html>",
                               "https://portal.cl/x")["fields"]
    for k in ("price", "area_m2", "bedrooms", "parking"):
        assert k not in f, k


# ===================================================================================================
# C — GALERÍA (§5)
# ===================================================================================================
def test_la_galeria_se_extrae_y_se_deduplica(dom):
    """Dos URLs de la misma foto en dos tamaños son UNA foto: bajarlas las dos sería pagar dos
    veces por lo mismo."""
    urls = dom["extract"].gallery_urls(HTML_AVISO, "https://portal.cl/aviso")
    assert len(urls) == 3, urls
    assert any("111111" in u for u in urls) and any("333333" in u for u in urls)


def test_logos_e_iconos_quedan_fuera(dom):
    urls = dom["extract"].gallery_urls(HTML_AVISO, "https://portal.cl/aviso")
    assert not any("logo" in u or "whatsapp" in u for u in urls)


def test_se_prefiere_la_variante_mas_grande(dom):
    html = ('<img src="https://cdn.cl/D_NQ_NP_2X_777777-MLC1_0825-F-x.jpg">'
            '<img src="https://cdn.cl/D_NQ_NP_777777-MLC1_0825-I-x.jpg">')
    urls = dom["extract"].gallery_urls(html, "https://portal.cl/a")
    assert len(urls) == 1 and ("_2X_" in urls[0] or "-O-" in urls[0])


# ===================================================================================================
# D — CLASIFICACIÓN DE MEDIA (§6)
# ===================================================================================================
def test_un_plano_se_reconoce_como_plano(dom):
    """Medido sobre los planos reales del repositorio: 65–77 % del cuadro es papel."""
    r = dom["classify"].classify(PLANO_403)
    assert r["kind"] == dom["classify"].FLOORPLAN
    assert r["features"]["white_fraction"] >= dom["classify"].WHITE_MIN


def test_una_foto_no_se_confunde_con_un_plano(dom, tmp_path):
    p = tmp_path / "foto.png"
    p.write_bytes(_png(tinte=(90, 110, 130), ruido=True))
    assert dom["classify"].classify(str(p))["kind"] == dom["classify"].PHOTO


def test_un_icono_chico_se_clasifica_como_logo(dom, tmp_path):
    p = tmp_path / "icono.png"
    p.write_bytes(_png(w=120, h=120, tinte=(255, 255, 255)))
    assert dom["classify"].classify(str(p))["kind"] == dom["classify"].LOGO


def test_un_mapa_se_reconoce_por_su_direccion(dom, tmp_path):
    p = tmp_path / "m.png"
    p.write_bytes(_png(tinte=(200, 220, 180)))
    r = dom["classify"].classify(str(p), "https://maps.google.com/staticmap?x=1.png")
    assert r["kind"] == dom["classify"].MAP


# ===================================================================================================
# E — EL CAMINO COMPLETO, CON LA RED SIMULADA
# ===================================================================================================
def _red(dom, monkeypatch, html=HTML_AVISO, imagen=None, plano=False):
    """Simula la red: la página y las imágenes. No se toca Internet en la suite."""
    img = imagen
    with open(PLANO_403, "rb") as fh:
        plano_bytes = fh.read()
    monkeypatch.setattr(dom["fetcher"], "fetch_page", lambda u, **k: {
        "url": u, "final_url": u, "redirects": [], "ips": ["93.184.216.34"], "status": 200,
        "content_type": "text/html", "html": html, "size": len(html)})

    def fake_img(u, **k):
        if plano and "333333" in u:
            cuerpo = plano_bytes
        elif img is not None:
            cuerpo = img
        else:
            # Bytes DISTINTOS por URL: el ingest deduplica por sha256, así que devolver el mismo
            # PNG tres veces haría que tres fotos se contaran como una. Sería el fixture mintiendo,
            # no el código: el sha se calcula sobre lo que baja.
            semilla = int(''.join(c for c in u if c.isdigit())[:6] or "1") % 200
            cuerpo = _png(tinte=(60 + semilla, 110, 130), ruido=True)
        return {"url": u, "final_url": u, "redirects": [], "ips": ["93.184.216.34"],
                "status": 200, "content_type": "image/png", "bytes": cuerpo, "size": len(cuerpo)}

    monkeypatch.setattr(dom["fetcher"], "fetch_image", fake_img)


def test_una_url_sola_crea_y_completa_el_aviso(client, dom, monkeypatch):
    """§24 — el camino exitoso: pegar el link y que no haya que subir nada."""
    _red(dom, monkeypatch)
    r = dom["urlingest"].ingest_url("https://portal.cl/aviso-1")
    l = dom["listings"].get(r["listing_id"])
    assert l["title"] == "Oficina El Golf" and l["price"] == 120
    assert l["total_area_m2"] == 543.0 and l["parking"] == 5
    assert l["property_type"] == "OFFICE" and l["operation"] == "RENT"
    assert r["fields"] >= 4 and r["photos"] >= 1
    assert l["photos_extracted_count"] == r["photos"]
    assert dom["listings"].get(r["listing_id"])["cover_media_id"], "la portada se elige sola"


def test_el_estado_del_ingest_es_honesto(client, dom, monkeypatch):
    """§16 — un SUCCESS optimista arruinaría el experimento, que mide justamente si podemos
    analizar una URL casi solos."""
    u = dom["urlingest"]
    _red(dom, monkeypatch)
    assert u.ingest_url("https://portal.cl/a")["status"] == u.SUCCESS
    # una página que no describe ningún inmueble NO es un aviso, por muchas fotos que tenga
    portada = ('<html><head><title>Portal</title>'
               '<meta property="og:image" content="https://cdn.cl/D_NQ_NP_1_MLC1_0825-O-a.jpg">'
               '</head><body><img src="https://cdn.cl/D_NQ_NP_2_MLC2_0825-O-b.jpg">'
               '<img src="https://cdn.cl/D_NQ_NP_3_MLC3_0825-O-c.jpg"></body></html>')
    _red(dom, monkeypatch, html=portada)
    r = u.ingest_url("https://portal.cl/home")
    assert r["status"] == u.PARTIAL and r["reason"] == u.NOT_A_LISTING


def test_un_portal_que_bloquea_se_reporta_bloqueado(client, dom, monkeypatch):
    """§16 — «No pudimos leer automáticamente esta publicación», con el motivo guardado. No se
    finge extracción y no se evade nada."""
    u, f = dom["urlingest"], dom["fetcher"]
    monkeypatch.setattr(f, "fetch_page",
                        lambda *a, **k: (_ for _ in ()).throw(f.FetchError(f.HTTP_BLOCKED, "403")))
    r = u.ingest_url("https://portal-cerrado.cl/aviso")
    assert r["status"] == u.FAILED and r["reason"] == f.HTTP_BLOCKED
    l = dom["listings"].get(r["listing_id"])
    assert l["url_ingest_status"] == "FAILED" and l["source_url"]
    html = client.get(f"/property/l/{r['listing_id']}").get_data(as_text=True)
    assert "No pudimos leer automáticamente esta publicación" in html
    assert "Reintentar" in html
    assert u.snapshots(r["listing_id"])[0]["error"], "el motivo queda auditable"


def test_un_plano_en_la_galeria_va_al_modelo_de_candidatos(client, dom, monkeypatch):
    """§7 — si la galería trae un plano, se detecta, se guarda y se le pregunta a E35 cuál es la
    unidad. Sin crear una property ni una concesión de pack."""
    from webapp import store
    _red(dom, monkeypatch, plano=True)
    r = dom["urlingest"].ingest_url("https://portal.cl/con-plano")
    assert r["floorplans"] == 1
    lid = r["listing_id"]
    assert dom["plans"].plan_media(lid) is not None
    sel = dom["plans"].resolve_units(lid)
    assert sel["candidate_count"] == 3, "es la lámina multiunidad del 403"
    assert dom["plans"].needs_unit_pick(lid) is True
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 0
    assert store.q1("SELECT COUNT(*) n FROM pack_grants")["n"] == 0


def test_la_pregunta_de_unidad_sigue_inline(client, dom, monkeypatch):
    _red(dom, monkeypatch, plano=True)
    r = client.post("/property/analizar", data={"url": "https://portal.cl/con-plano"})
    lid = r.headers["Location"].rsplit("/", 1)[-1]
    html = client.get(f"/property/l/{lid}").get_data(as_text=True)
    assert "¿Cuál es la oficina de este aviso?" in html


def test_una_correccion_manual_no_se_pisa(client, dom, monkeypatch):
    """§9 — corregir un dato y que el siguiente análisis lo borre haría inútil corregirlo."""
    _red(dom, monkeypatch)
    r = dom["urlingest"].ingest_url("https://portal.cl/aviso-2")
    lid = r["listing_id"]
    client.post(f"/property/l/{lid}/datos", data={"area_m2": "999", "title": "Mi corrección"})
    proc = dom["urlingest"].provenance(lid)
    assert proc["area_m2"]["source"] == dom["extract"].MANUAL_OVERRIDE
    dom["urlingest"].ingest_url("https://portal.cl/aviso-2", listing_id=lid)
    l = dom["listings"].get(lid)
    assert l["area_m2"] == 999 and l["title"] == "Mi corrección"


# ===================================================================================================
# F — LAS FOTOS BUENAS NO SON UN PROBLEMA (§10, §11, §13)
# ===================================================================================================
def test_fotos_buenas_producen_senales_positivas(client, dom, monkeypatch):
    """§13 — hasta ahora el informe sólo sabía nombrar defectos, y eso lo empujaba a encontrar uno
    siempre. «14 de 20 ya tenían fotos buenas» es un dato comercial."""
    a = dom["analyzer"]
    _red(dom, monkeypatch, imagen=_png(w=1600, h=1200, tinte=(120, 130, 140), ruido=True))
    r = dom["urlingest"].ingest_url("https://portal.cl/lindo")
    rep = a.analyze(r["listing_id"])
    assert a.GOOD_COVER in rep["signals"] or a.GOOD_EXPOSURE in rep["signals"]
    for s in rep["signals"]:
        assert s in a.SIGNAL_LABEL


def test_fotos_buenas_no_generan_una_oportunidad_falsa(client, dom, monkeypatch):
    """§10 — «Fotografía sólida — no recomendamos intervenir.» No se inventa una intervención
    visual donde no hace falta."""
    a = dom["analyzer"]
    _red(dom, monkeypatch, imagen=_png(w=1600, h=1200, tinte=(120, 130, 140), ruido=True))
    rep = a.analyze(dom["urlingest"].ingest_url("https://portal.cl/lindo")["listing_id"])
    codigos = [f["code"] for f in rep["resolvable"]]
    assert not any(c.startswith("COVER_") or c.startswith("SET_") for c in codigos), codigos


def test_un_aviso_puede_terminar_ya_esta_bien(client, dom, monkeypatch):
    """§11 — NO todos los avisos son leads. Rebajar una publicación buena para crear mercado
    arruinaría la única pregunta que la muestra contesta."""
    a = dom["analyzer"]
    _red(dom, monkeypatch, imagen=_png(w=1600, h=1200, tinte=(120, 130, 140), ruido=True))
    lid = dom["urlingest"].ingest_url("https://portal.cl/lindo")["listing_id"]
    dom["listings"].update(lid, description="x" * 400, price=120, area_m2=543, parking=5)
    rep = a.analyze(lid)
    assert rep["commercial_state"] in a.COMMERCIAL_STATES
    assert a.ALREADY_STRONG in a.COMMERCIAL_STATES
    if not rep["resolvable"]:
        assert rep["commercial_state"] in (a.ALREADY_STRONG, a.RECOMMENDATION_ONLY)


def test_los_tres_estados_comerciales_existen_y_se_muestran(client, dom, monkeypatch):
    a = dom["analyzer"]
    assert set(a.COMMERCIAL_STATES) == {"RESOLVABLE_OPPORTUNITY", "RECOMMENDATION_ONLY",
                                        "ALREADY_STRONG"}
    _red(dom, monkeypatch, imagen=_png(w=1600, h=1200, tinte=(120, 130, 140), ruido=True))
    lid = dom["urlingest"].ingest_url("https://portal.cl/lindo")["listing_id"]
    dom["listings"].update(lid, description="x" * 400, price=120, area_m2=543, parking=5)
    a.run(lid)
    html = client.get(f"/property/l/{lid}").get_data(as_text=True)
    assert "Lo que ya está bien" in html


def test_el_tablero_reporta_el_ingest_y_la_calidad_visual(client, dom, monkeypatch):
    """§15 — las dos preguntas reales de la muestra, cada una con su bloque."""
    from webapp.domain.potential import reviews as pr
    _red(dom, monkeypatch)
    dom["analyzer"].run(dom["urlingest"].ingest_url("https://portal.cl/a")["listing_id"])
    p = pr.dashboard()
    assert p["ingest"]["by_status"]["SUCCESS"] == 1
    assert p["ingest"]["no_manual_pct"] == 100.0
    assert p["ingest"]["avg_photos"] is not None
    assert "strong_pct" in p["visual"] and "by_state" in p["commercial"]
    assert client.get("/property/dogfood").status_code == 200


# ===================================================================================================
# G — AISLAMIENTO Y REGRESIÓN (§7, §18, §22)
# ===================================================================================================
def test_nada_de_esto_crea_property_ni_pack_grant(client, dom, monkeypatch):
    from webapp import store
    from webapp.domain import properties, realpilot
    _red(dom, monkeypatch, plano=True)
    lid = dom["urlingest"].ingest_url("https://portal.cl/x")["listing_id"]
    dom["plans"].resolve_units(lid)
    dom["plans"].pick_unit(lid, "u1")
    dom["analyzer"].run(lid)
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 0
    assert store.q1("SELECT COUNT(*) n FROM pack_grants")["n"] == 0
    assert properties.listing() == [] and realpilot.members() == []


def test_el_material_descargado_queda_aislado_por_aviso(client, dom, monkeypatch):
    """§18 — no servir archivos de otro aviso, aunque se conozca el id."""
    _red(dom, monkeypatch)
    a = dom["urlingest"].ingest_url("https://portal.cl/a")["listing_id"]
    b = dom["urlingest"].ingest_url("https://portal.cl/b")["listing_id"]
    mid = dom["listings"].media_of(a, dom["listings"].PHOTO)[0]["media_id"]
    assert client.get(f"/property/l/{a}/m/{mid}").status_code == 200
    assert client.get(f"/property/l/{b}/m/{mid}").status_code == 404
    from webapp import store
    assert store.listing_dir(a) != store.listing_dir(b)


def test_el_motor_no_se_toco(client, dom):
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"el motor cambió: {out.stdout}"


def test_e36_intacto(client, dom):
    """§23 del encargo anterior sigue vigente: el piloto humano no se toca."""
    from webapp.domain import calibration, gold, ingest, realpilot, units
    assert ingest.AUTO_CONFIRM_THRESHOLDS == {"perimeter": 0.60, "core": 0.50,
                                              "primary_entrance": 0.70, "columns": 0.55,
                                              "daylight": 0.45}
    assert ingest.UNCERTAINTY_BAND == {"core": 0.10}
    assert calibration.MIN_SAMPLE == 10 and realpilot.TARGET_FIRST == 10
    assert gold.DEFAULT_PROVENANCE == gold.PROVISIONAL_DOGFOOD
    assert units.MIN_RELATIVE_AREA == 0.15


def test_no_hay_navegador_headless_escondido(dom):
    """§3.E / §20 — la capa de navegador está declarada y NO construida. Meter un headless en el
    servidor «por si acaso» es infraestructura grande para un problema que hoy no existe."""
    assert dom["extract"].BROWSER_FALLBACK_AVAILABLE is False
    with pytest.raises(NotImplementedError):
        dom["extract"].browser_fetch("https://x.cl")
