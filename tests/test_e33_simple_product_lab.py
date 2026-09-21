"""E33 §28 — tests de CONTRATO de la experiencia simple.

Lo que se protege acá no es que las páginas abran, sino la promesa que E33 hace:

    «Subo una propiedad, veo Pack 1, hago Pack 2 para un cliente y califico si el resultado fue
     excelente, bueno, malo o pésimo.»

Es decir: UNA navegación de dos ítems, UNA página por propiedad, cero vocabulario técnico en el
camino principal, y las cuatro calificaciones guardadas con la procedencia que el usuario no ve.
"""
from __future__ import annotations

import importlib
import io
import json
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
           "webapp.domain.packs", "webapp.domain.reviews", "webapp.domain.lab",
           "webapp.benchmark", "webapp.customer", "webapp.staging_ui", "webapp.lab", "webapp.app")

#: Vocabulario que el flujo principal NO puede usar (§23/§24).
JERGA = ("case_id", "run_id", "SEARCH_EXHAUSTED", "LAYOUTS_READY", "NEEDS_CONFIRMATION",
         "PACK_READY", "PROVIDER_NOT_APPROVED", "entitlement", "manifest", "asset_type",
         "benchmark", "staging_attempt", "solver", "CP-SAT")


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
    from webapp.domain import (assets, entitlements, fits, lab, packs, properties, reviews,
                               staging)
    return {"assets": assets, "entitlements": entitlements, "fits": fits, "lab": lab,
            "packs": packs, "properties": properties, "reviews": reviews, "staging": staging}


def _nueva(client, titulo="Oficina 403"):
    r = client.post("/lab/new", data={"title": titulo, "city": "Santiago",
                                      "published_area_m2": "543"}, follow_redirects=True)
    return re.search(rb"p_[0-9a-f]{12}", r.data).group().decode()


def _foto(dom, pid, nombre="sala.png"):
    from werkzeug.datastructures import FileStorage
    return dom["assets"].save_upload(
        pid, FileStorage(stream=io.BytesIO(_png()), filename=nombre),
        dom["assets"].PHOTO_ORIGINAL)


def _plano_listo(dom, pid, case_id="c_ok"):
    """Una propiedad con su plano preparado y su material base, sin correr el motor."""
    from webapp import store
    from werkzeug.datastructures import FileStorage
    dom["assets"].save_upload(pid, FileStorage(stream=io.BytesIO(_png()), filename="plano.png"),
                              dom["assets"].FLOORPLAN_ORIGINAL)
    store.ex("INSERT OR IGNORE INTO cases(case_id,title,original_filename,source_file,mime,"
             "uploaded_at,status,track) VALUES (?,?,?,?,?,?,'READY','DEVELOPMENT')",
             (case_id, "Caso", "a.png", "a.png", "image/png", store.now()))
    d = os.path.join(store.case_dir(case_id), "outputs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
        json.dump({"shell_readiness": {"ready_for_layout": True, "requires_confirmation": []}}, fh)
    dom["properties"].link_case(pid, case_id)
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_COMMERCIAL, "pc.png", _png(), "image/png")
    dom["assets"].save_bytes(pid, dom["assets"].LAYOUT_RENDER, "alt_A.png", _png(), "image/png",
                             metadata={"alt": "A", "representative": True,
                                       "selected_by": "first_fit"})
    return case_id


# ===================================================================================================
# A — UNA SOLA NAVEGACIÓN
# ===================================================================================================
def test_la_navegacion_principal_tiene_dos_items(client, dom):
    """§2 — «Mis propiedades» y «Ajustes». Nada más."""
    html = client.get("/lab/").get_data(as_text=True)
    nav = re.search(r"<nav>(.*?)</nav>", html, re.S).group(1)
    enlaces = re.findall(r">([^<>]+)</a>", nav)
    assert enlaces == ["Mis propiedades", "Ajustes"]
    for prohibido in ("Plantas", "Revisión", "Revisiones", "Ambientación", "Benchmark",
                      "Producto", "Herramienta técnica", "Prospectos", "Staging"):
        assert prohibido not in nav, prohibido


def test_la_misma_navegacion_en_todas_las_pantallas_principales(client, dom):
    pid = _nueva(client)
    for url in ("/lab/", "/lab/new", f"/lab/p/{pid}", "/lab/ajustes"):
        nav = re.search(r"<nav>(.*?)</nav>", client.get(url).get_data(as_text=True), re.S).group(1)
        assert re.findall(r">([^<>]+)</a>", nav) == ["Mis propiedades", "Ajustes"], url


def test_el_flujo_principal_no_habla_en_tecnico(client, dom):
    """§23 — si para operar hay que entender case, run o entitlement, la UX falló."""
    pid = _nueva(client)
    _foto(dom, pid)
    for url in ("/lab/", f"/lab/p/{pid}"):
        html = client.get(url).get_data(as_text=True)
        visible = html.split("Ver detalle")[0]          # lo técnico vive tras ese resumen
        for palabra in JERGA:
            assert palabra not in visible, f"{url} dice «{palabra}»"


# ===================================================================================================
# B — PORTADA
# ===================================================================================================
def test_la_portada_solo_muestra_propiedades(client, dom):
    pid = _nueva(client, "Oficina 403")
    html = client.get("/lab/").get_data(as_text=True)
    assert "Mis propiedades" in html and "Nueva propiedad" in html
    assert "Oficina 403" in html and f"/lab/p/{pid}" in html
    assert "Pack 1" in html
    for tecnico in ("case", "run_id", "benchmark", "provider", "entitlement"):
        assert tecnico not in html.lower()


def test_crear_una_propiedad_lleva_directo_a_su_ficha(client, dom):
    r = client.post("/lab/new", data={"title": "Oficina 403", "city": "Santiago"},
                    follow_redirects=True)
    txt = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Pack 1 — Publicación" in txt and "Pack 2 — Propuesta para un cliente" in txt


def test_la_marca_no_se_pide_en_cada_propiedad(client, dom):
    """§4.D — se usa la ya configurada."""
    html = client.get("/lab/new").get_data(as_text=True)
    assert "Se usa tu marca" in html
    assert "logo" not in html.split("Se usa tu marca")[0].lower()


# ===================================================================================================
# C — UNA SOLA PÁGINA POR PROPIEDAD
# ===================================================================================================
def test_la_propiedad_es_una_sola_pagina_con_todo(client, dom):
    """§6 — insumos, Pack 1, Pack 2 y evaluaciones en orden vertical. Sin pestañas."""
    pid = _nueva(client)
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    for seccion in ('id="insumos"', 'id="pack1"', 'id="pack2"', 'id="evaluaciones"'):
        assert seccion in html, seccion
    assert 'class="tabs"' not in html


def test_las_rutas_viejas_de_pestanas_redirigen_a_la_pagina_unica(client, dom):
    pid = _nueva(client)
    for vieja in ("resumen", "plano", "fotos", "material", "prospectos", "pack", "actividad"):
        r = client.get(f"/lab/p/{pid}/{vieja}")
        assert r.status_code == 302 and f"/lab/p/{pid}" in r.headers["Location"], vieja


def test_los_estados_estan_en_lenguaje_humano(client, dom):
    """§24 — Pendiente / Preparando / Necesita revisión / Listo / No pudimos generarlo."""
    pid = _nueva(client)
    estados = {s["state"] for s in dom["lab"].pack1(pid)["steps"]}
    assert estados <= {"Pendiente", "Preparando", "Necesita revisión", "Listo",
                       "No pudimos generarlo"}
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    assert "Pendiente" in html


# ===================================================================================================
# D — PACK 1
# ===================================================================================================
def test_pack1_tiene_exactamente_tres_pasos(client, dom):
    """§7 — plano comercial, UN layout tipo y UNA ambientación. Ni tres layouts ni prospectos."""
    pid = _nueva(client)
    pasos = dom["lab"].pack1(pid)["steps"]
    assert [s["name"] for s in pasos] == ["Plano comercial", "Layout tipo", "Ambientación"]
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    seccion = html.split('id="pack1"')[1].split('id="pack2"')[0]
    assert "Alternativa B" not in seccion and "Alternativa C" not in seccion


def test_pack1_muestra_los_resultados_y_deja_descargar(client, dom):
    pid = _nueva(client)
    _plano_listo(dom, pid)
    p1 = dom["lab"].pack1(pid)
    assert p1["floorplan"] is not None and p1["layout"] is not None
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    assert "Plano comercial" in html and "Layout tipo" in html
    assert p1["floorplan"]["asset_id"] in html and p1["layout"]["asset_id"] in html


def test_sin_ambientacion_pack1_lo_dice_sin_jerga(client, dom):
    pid = _nueva(client)
    _plano_listo(dom, pid)
    _foto(dom, pid)
    paso = [s for s in dom["lab"].pack1(pid)["steps"] if s["name"] == "Ambientación"][0]
    assert paso["state"] == "Pendiente"
    assert "proveedor" in paso["detail"] or "fotos" in paso["detail"]
    assert "PROVIDER" not in paso["detail"]


def test_un_solo_boton_avanza_todo_lo_que_puede(client, dom):
    """§7 — «GENERAR PACK 1» hace lo que puede y se detiene donde hace falta una persona."""
    pid = _nueva(client)
    from werkzeug.datastructures import FileStorage
    dom["assets"].save_upload(pid, FileStorage(stream=io.BytesIO(_png()), filename="plano.png"),
                              dom["assets"].FLOORPLAN_ORIGINAL)
    r = client.post(f"/lab/p/{pid}/pack1", data={"headcount": "40"})
    assert r.status_code == 302
    assert "revisar-plano" in r.headers["Location"]     # se detiene donde hace falta un humano
    assert dom["properties"].require(pid)["floorplan_case_id"]   # pero ya preparó el caso


def test_la_revision_del_plano_avisa_y_marca_la_vuelta(client, dom):
    """§5 — se puede abrir la herramienta técnica, pero con la vuelta clara."""
    pid = _nueva(client)
    from werkzeug.datastructures import FileStorage
    dom["assets"].save_upload(pid, FileStorage(stream=io.BytesIO(_png()), filename="p.png"),
                              dom["assets"].FLOORPLAN_ORIGINAL)
    html = client.get(f"/lab/p/{pid}/revisar-plano").get_data(as_text=True)
    assert "Volver a la propiedad" in html and f"/lab/p/{pid}" in html
    nav = re.search(r"<nav>(.*?)</nav>", html, re.S).group(1)
    assert re.findall(r">([^<>]+)</a>", nav) == ["Mis propiedades", "Ajustes"]


# ===================================================================================================
# E — PACK 2
# ===================================================================================================
def test_pack2_es_un_formulario_simple_en_la_misma_pagina(client, dom):
    """§9 — cliente, personas, forma de trabajo y estilo. Lo avanzado, escondido."""
    pid = _nueva(client)
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    sec = html.split('id="pack2"')[1]
    for campo in ("prospect_name", "headcount", "workplace_preset", "visual_style"):
        assert campo in sec, campo
    assert "Más opciones" in sec
    # el programa detallado no está visible por defecto
    assert sec.index("Más opciones") < sec.index("room_private_office")


def test_pack2_no_obliga_a_cambiar_una_configuracion_global(client, dom):
    """§9/§21 — nada de ir a Ajustes a poner Pro."""
    from webapp import store
    pid = _nueva(client)
    _plano_listo(dom, pid)
    assert dom["entitlements"].product_of(pid) == "ONE_OFF"
    r = client.post(f"/lab/p/{pid}/pack2", data={"prospect_name": "Falabella", "headcount": "80",
                                                 "workplace_preset": "EXECUTIVE",
                                                 "visual_style": "CORPORATE"},
                    follow_redirects=True)
    assert r.status_code == 200
    fits = dom["fits"].list_for(pid, include_base=False)
    assert len(fits) == 1 and fits[0]["label"] == "Falabella"
    assert fits[0]["workplace_preset"] == "EXECUTIVE"


def test_varias_propuestas_conviven(client, dom):
    """§11 — una propiedad puede tener Falabella, NotCo y Banco X sin pisarse."""
    pid = _nueva(client)
    _plano_listo(dom, pid)
    for n in ("Falabella", "NotCo", "Banco X"):
        client.post(f"/lab/p/{pid}/pack2", data={"prospect_name": n, "headcount": "40"},
                    follow_redirects=True)
    etiquetas = [x["fit"]["label"] for x in dom["lab"].pack2_list(pid)]
    assert set(etiquetas) == {"Falabella", "NotCo", "Banco X"}
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    for n in ("Falabella", "NotCo", "Banco X"):
        assert n in html


def test_una_propuesta_sin_plano_no_se_crea_a_medias(client, dom):
    pid = _nueva(client)
    r = client.post(f"/lab/p/{pid}/pack2", data={"prospect_name": "Falabella", "headcount": "40"})
    assert r.status_code == 400
    assert "plano preparado" in r.get_data(as_text=True)
    assert dom["fits"].list_for(pid, include_base=False) == []


# ===================================================================================================
# F — EVALUACIÓN: la razón de ser del laboratorio
# ===================================================================================================
@pytest.mark.parametrize("rating", ["EXCELENTE", "BUENO", "MALO", "PESIMO"])
def test_las_cuatro_calificaciones(client, dom, rating):
    pid = _nueva(client)
    r = client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "PACK1", "rating": rating})
    assert r.status_code == 302
    assert dom["reviews"].latest(pid, "PACK1")["rating"] == rating


def test_no_hay_estrellas_ni_escalas_numericas(client, dom):
    """§12 — exactamente cuatro categorías, en español."""
    assert dom["reviews"].RATINGS == ("EXCELENTE", "BUENO", "MALO", "PESIMO")
    pid = _nueva(client)
    _plano_listo(dom, pid)          # los botones aparecen donde hay algo que calificar
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    for k in ("Excelente", "Bueno", "Malo", "Pésimo"):
        assert k in html, k
    assert 'type="range"' not in html and "★" not in html


def test_una_calificacion_invalida_se_rechaza(client, dom):
    pid = _nueva(client)
    assert client.post(f"/lab/p/{pid}/evaluar",
                       data={"artifact_type": "PACK1", "rating": "REGULAR"}).status_code == 400
    with pytest.raises(ValueError):
        dom["reviews"].save(pid, "PACK1", "10/10")


def test_los_motivos_dependen_del_artefacto_y_del_signo(client, dom):
    """§14/§15 — «¿Qué falló?» para malo, «¿Qué funcionó?» para bueno."""
    r = dom["reviews"]
    assert "Cambió arquitectura" in r.tags_for("STAGING", "MALO")
    assert "Circulación" in r.tags_for("LAYOUT", "PESIMO")
    assert "Legibilidad" in r.tags_for("PLANO", "MALO")
    assert r.tags_for("LAYOUT", "EXCELENTE") == r.GOOD_TAGS
    assert "Circulación" not in r.tags_for("LAYOUT", "BUENO")


def test_los_motivos_y_el_comentario_son_opcionales(client, dom):
    pid = _nueva(client)
    client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "PACK1", "rating": "MALO"})
    rev = dom["reviews"].latest(pid, "PACK1")
    assert rev["tags"] == [] and rev["comment"] == ""


def test_un_motivo_que_no_corresponde_se_descarta(client, dom):
    pid = _nueva(client)
    dom["reviews"].save(pid, "STAGING", "MALO", reason_tags=["Circulación", "Mobiliario"])
    assert dom["reviews"].latest(pid, "STAGING")["tags"] == ["Mobiliario"]


def test_se_puede_calificar_cada_pieza_por_separado(client, dom):
    """§13 — plano, layout, ambientación, Pack 1, cada alternativa y la propuesta."""
    pid = _nueva(client)
    _plano_listo(dom, pid)
    p1 = dom["lab"].pack1(pid)
    client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "PLANO", "rating": "BUENO",
                                               "artifact_id": p1["floorplan"]["asset_id"]})
    client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "LAYOUT", "rating": "MALO",
                                               "artifact_id": p1["layout"]["asset_id"],
                                               "tags": ["Circulación"]})
    hist = dom["reviews"].history(pid)
    assert {h["artifact_type"] for h in hist} == {"PLANO", "LAYOUT"}
    assert [h for h in hist if h["artifact_type"] == "LAYOUT"][0]["tags"] == ["Circulación"]


def test_la_procedencia_se_guarda_y_no_se_muestra(client, dom):
    """§16 — el usuario no ve estos campos, pero se puede correlacionar con la versión exacta."""
    pid = _nueva(client)
    _plano_listo(dom, pid)
    aid = dom["lab"].pack1(pid)["layout"]["asset_id"]
    client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "LAYOUT", "rating": "MALO",
                                               "artifact_id": aid})
    rev = dom["reviews"].latest(pid, "LAYOUT", aid)
    assert rev["engine_version"] and rev["artifact_sha256"]
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    visible = html.split("Ver detalle")[0]
    assert rev["artifact_sha256"] not in visible
    assert (rev["engine_version"] or "")[:10] not in visible


def test_recalificar_conserva_la_historia_y_manda_la_ultima(client, dom):
    pid = _nueva(client)
    client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "PACK1", "rating": "MALO"})
    client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "PACK1", "rating": "BUENO"})
    assert dom["reviews"].latest(pid, "PACK1")["rating"] == "BUENO"
    assert len(dom["reviews"].for_property(pid)) == 2
    assert len(dom["reviews"].history(pid)) == 1


def test_el_feedback_no_sale_en_lo_que_ve_un_cliente(client, dom):
    pid = _nueva(client)
    _plano_listo(dom, pid)
    dom["reviews"].save(pid, "PACK1", "PESIMO", reason_tags=["No lo mandaría"],
                        comment="NO-MOSTRAR-ESTO")
    man = json.dumps(dom["packs"].build_manifest(pid))
    assert "NO-MOSTRAR-ESTO" not in man and "PESIMO" not in man
    assert "NO-MOSTRAR-ESTO" not in client.get(f"/properties/{pid}").get_data(as_text=True)


# ===================================================================================================
# G — APRENDIZAJE Y BACKSTAGE
# ===================================================================================================
def test_el_resumen_de_evaluaciones_esta_en_ajustes(client, dom):
    """§18 — no en la navegación principal."""
    pid = _nueva(client)
    dom["reviews"].save(pid, "LAYOUT", "MALO", reason_tags=["Densidad"])
    dom["reviews"].save(pid, "PLANO", "EXCELENTE")
    s = dom["reviews"].stats()
    assert s["total"] == 2 and s["by_rating"]["MALO"] == 1
    assert s["top_failures"] == {"Densidad": 1}
    html = client.get("/lab/ajustes/evaluaciones").get_data(as_text=True)
    assert "Densidad" in html and "Excelente" in html
    assert "Evaluaciones" not in re.search(
        r"<nav>(.*?)</nav>", client.get("/lab/").get_data(as_text=True), re.S).group(1)


def test_el_tooling_tecnico_sigue_existiendo_detras_de_ajustes(client, dom):
    """§26 — nada se borró: se sacó del camino."""
    html = client.get("/lab/debug").get_data(as_text=True)
    for destino in ("/staging/", "/review", "/properties/", "/lab/benchmark", "/reviews.json"):
        assert destino in html, destino
    assert "/lab/debug" in client.get("/lab/ajustes").get_data(as_text=True)
    for url in ("/", "/review", "/staging/", "/staging/benchmark", "/lab/benchmark",
                "/properties/", "/settings"):
        assert client.get(url).status_code == 200, url


def test_ajustes_muestra_credenciales_sin_revelarlas(client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRETO-E33")
    html = client.get("/lab/ajustes").get_data(as_text=True)
    assert "configurado" in html and "SECRETO" not in html
    assert "Proveedor aprobado" in html


# ===================================================================================================
# H — REGRESIÓN
# ===================================================================================================
def test_el_motor_no_fue_tocado():
    import subprocess
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"E33 tocó el motor: {out.stdout}"


def test_los_derechos_de_e32_2_siguen_vivos_en_el_cliente(client, dom):
    """El LAB simplifica la evaluación; el tope comercial sigue donde importa."""
    from webapp.domain import grants
    _nueva(client, "A")
    assert client.post("/properties/new", data={"title": "B"}).status_code == 403
    assert "otro Pack" in client.get("/properties/new").get_data(as_text=True)
    grants.create("ONE_OFF", "PURCHASE")
    assert client.post("/properties/new", data={"title": "B"},
                       follow_redirects=True).status_code == 200


def test_la_calificacion_guardada_se_ve_en_la_pantalla(client, dom):
    """Se veía en la base y no en pantalla: un `{% set %}` dentro de un `{% for %}` de Jinja no
    sale del bucle. Sólo lo mostró abrir el navegador, así que queda cubierto."""
    pid = _nueva(client)
    _plano_listo(dom, pid)
    aid = dom["lab"].pack1(pid)["layout"]["asset_id"]
    client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "LAYOUT", "rating": "MALO",
                                               "artifact_id": aid, "tags": ["Circulación"]})
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    assert "rate r-malo on" in html                    # el botón queda marcado
    assert "¿Qué falló?" in html                       # y aparecen los motivos
    assert "Circulación" in html
    assert dom["lab"].property_view(pid)["revs"][f"LAYOUT|{aid}|"]["rating"] == "MALO"


def test_abrir_la_base_desde_otro_proceso_no_mata_las_corridas(client, dom):
    """`store.init()` marcaba como fallida toda corrida en vuelo. Cualquier CLI que abriera la
    misma base mataba el trabajo del servidor y mostraba un fallo que nunca ocurrió. Lo descubrí
    matando una corrida real con mi propio script de diagnóstico."""
    from webapp import store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('c1','C','a.png','a.png','image/png',?,'READY','DEVELOPMENT')",
             (store.now(),))
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,created_at) "
             "VALUES ('r_vivo','c1','b','RUNNING',?)", (store.now(),))
    store.init()                                     # lo que hace otro proceso al abrir la base
    assert store.q1("SELECT status FROM runs WHERE run_id='r_vivo'")["status"] == "RUNNING"
    store.reset_orphans()                            # lo que hace el servidor al arrancar
    assert store.q1("SELECT status FROM runs WHERE run_id='r_vivo'")["status"] == "FAILED"
