"""E17.0 §TESTS — contrato de la capa de POTENCIAL.

Lo que se protege acá son dos promesas y un aislamiento:

    el score es TRAZABLE      cada punto sale de un criterio con nombre, peso y medición;
    el score NO predice ventas mide el aviso, no el mercado, y el producto lo dice;
    nada de esto toca el LAB  ni su navegación, ni sus tablas, ni el motor de layouts.
"""
from __future__ import annotations

import importlib
import io
import json
import os
import shutil
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
           "webapp.domain.potential.vision", "webapp.domain.potential.plans",
           "webapp.domain.potential.interventions", "webapp.domain.potential.analyzer",
           "webapp.domain.potential.demos", "webapp.potential", "webapp.app")

PLANO_403 = os.path.join(ROOT, "cases", "001_gps_403", "original.png")


def _png(w=1200, h=900, tinte=(150, 150, 150), ruido=False) -> bytes:
    """Un PNG real, con tamaño y color controlados, para mover las mediciones a voluntad."""
    import random
    random.seed(7)
    filas = []
    for y in range(h):
        fila = bytearray([0])
        for x in range(w):
            if ruido and (x + y) % 3 == 0:
                fila += bytes((random.randrange(256), random.randrange(256),
                               random.randrange(256)))
            else:
                fila += bytes(tinte)
        filas.append(bytes(fila))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(filas))) + chunk(b"IEND", b""))


class FS:
    """Un archivo subido, sin depender de werkzeug."""

    def __init__(self, blob: bytes, filename: str = "f.png"):
        self.filename, self._blob = filename, blob

    def save(self, dest):
        with open(dest, "wb") as fh:
            fh.write(self._blob)


class FSPath(FS):
    def __init__(self, path):
        self.filename, self._path = os.path.basename(path), path

    def save(self, dest):
        shutil.copy2(self._path, dest)


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
    from webapp.domain.potential import (analyzer, demos, interventions, listings, plans, vision)
    return {"analyzer": analyzer, "demos": demos, "iv": interventions, "listings": listings,
            "plans": plans, "vision": vision}


def _listing(dom, **kw):
    kw.setdefault("title", "Oficina Apoquindo")
    kw.setdefault("property_type", dom["listings"].OFFICE)
    return dom["listings"].create(source=dom["listings"].MANUAL, **kw)


# ===================================================================================================
# A — ENTRADA: pegar una publicación
# ===================================================================================================
def test_la_pantalla_inicial_pide_una_sola_cosa(client):
    """E17.2 §1 — el LINK es el input principal. Arriba del pliegue: una pregunta, un campo y un
    botón. La carga manual existe, colapsada, y deja de ser el camino."""
    html = client.get("/property/").get_data(as_text=True)
    assert "¿Cuánto potencial está dejando sin mostrar tu propiedad?" in html
    assert "Pega el link de la publicación" in html
    assert 'name="url"' in html and ">Analizar<" in html
    i_url = html.index('name="url"')
    i_manual = html.index("También puedes cargar archivos manualmente")
    assert i_url < i_manual, "lo manual tiene que ir DESPUÉS del link"
    assert "<details" in html.split("También puedes")[0][-120:], "y tiene que ir colapsado"


def test_sin_url_el_flujo_sigue_igual(client, dom):
    """§FLUJO — «Si la URL no puede importarse de forma robusta, el MVP debe poder continuar con
    carga manual.» Sin URL tampoco se detiene."""
    r = client.post("/property/analizar", data={"title": "Depto Providencia"})
    assert r.status_code == 302
    lid = r.headers["Location"].rsplit("/", 1)[-1]
    assert dom["listings"].get(lid)["source"] == dom["listings"].MANUAL
    assert dom["analyzer"].latest(lid) is not None


def test_una_url_que_no_se_deja_leer_no_rompe_nada(client, dom):
    """El adaptador de URL puede fallar; el producto no. Se guarda el enlace y se sigue a mano."""
    r = client.post("/property/analizar",
                    data={"url": "http://127.0.0.1:9/no-existe"})
    assert r.status_code == 302
    lid = r.headers["Location"].rsplit("/", 1)[-1]
    l = dom["listings"].get(lid)
    assert l["source"] == dom["listings"].URL
    assert l["source_url"] == "http://127.0.0.1:9/no-existe"
    assert client.get(f"/property/l/{lid}").status_code == 200


def test_la_fuente_url_no_inventa_campos(dom):
    """Un adaptador que rellena «3 dormitorios porque es lo normal» contaminaría justo la
    dimensión que mide qué falta."""
    res = dom["listings"].UrlSource().fetch("no-es-una-url")
    assert res["ok"] is False and res["fields"] == {}
    assert res["confidence"] == dom["listings"].CONFIDENCE_NONE


# ===================================================================================================
# B — EL SCORE ES TRAZABLE
# ===================================================================================================
def test_cada_punto_viene_de_un_criterio_con_nombre(client, dom):
    lid = _listing(dom, area_m2=100, price=200)
    dom["listings"].add_media(lid, FS(_png(), "a.png"))
    r = dom["analyzer"].run(lid)
    for dim, d in r["dimensions"].items():
        assert d["criteria"], dim
        for c in d["criteria"]:
            assert c["code"] and c["label"] and c["weight"] > 0
            if c["applies"]:
                assert c["measured"] is not None and 0.0 <= c["value"] <= 1.0
                assert c["points"] is not None and c["max_points"] is not None
            else:
                assert c["why"], "un criterio que no aplica tiene que decir por qué"


def test_la_aritmetica_del_score_cuadra(client, dom):
    """Si la suma de los puntos no da el score, el informe no se puede auditar."""
    lid = _listing(dom, area_m2=100, price=200, description="x" * 300)
    dom["listings"].add_media(lid, FS(_png(ruido=True), "a.png"))
    r = dom["analyzer"].run(lid)
    for d in r["dimensions"].values():
        suma = sum(c["points"] for c in d["criteria"] if c["applies"])
        assert abs(suma - d["score"]) < 0.2, d["label"]
    assert abs(sum(d["score"] for d in r["dimensions"].values()) - r["score"]) < 0.6
    assert r["max_score"] == sum(dom["analyzer"].DIMENSIONS.values()) == 100


def test_un_criterio_que_no_aplica_no_resta(client, dom):
    """Contar «dormitorios» como faltante en una bodega castigaría al aviso por algo que no puede
    tener. El peso se reparte entre lo que sí aplica."""
    a = _listing(dom, property_type=dom["listings"].WAREHOUSE, area_m2=500, price=1,
                 description="x" * 300)
    b = _listing(dom, property_type=dom["listings"].APARTMENT, area_m2=500, price=1,
                 description="x" * 300)
    ra, rb = dom["analyzer"].analyze(a), dom["analyzer"].analyze(b)
    dorm_a = next(c for c in ra["dimensions"]["INFORMATION"]["criteria"]
                  if c["code"] == "INFO_BEDROOMS")
    dorm_b = next(c for c in rb["dimensions"]["INFORMATION"]["criteria"]
                  if c["code"] == "INFO_BEDROOMS")
    assert dorm_a["applies"] is False and dorm_b["applies"] is True
    # la bodega, con los mismos datos, no puede salir peor por no tener dormitorios
    assert ra["dimensions"]["INFORMATION"]["score"] > rb["dimensions"]["INFORMATION"]["score"]


def test_el_delta_de_un_hallazgo_no_depende_de_lo_que_no_aplica(client, dom):
    """Sin fotos, un solo criterio de la dimensión aplica. Si el delta usara el peso
    redistribuido, ese criterio prometería los 30 puntos enteros de la dimensión, que es falso:
    al subir fotos los demás vuelven a aplicar y se reparten."""
    lid = _listing(dom)
    r = dom["analyzer"].analyze(lid)
    f = next(x for x in r["findings"] if x["code"] == "SET_PHOTO_COUNT")
    peso = next(c.weight for c in dom["analyzer"].CRITERIA if c.code == "SET_PHOTO_COUNT")
    total = sum(c.weight for c in dom["analyzer"].CRITERIA if c.dimension == "VISUAL")
    assert f["score_delta"] <= dom["analyzer"].DIMENSIONS["VISUAL"] * peso / total + 0.01


def test_el_informe_se_puede_auditar_en_json(client, dom):
    lid = _listing(dom, area_m2=100)
    dom["listings"].add_media(lid, FS(_png(), "a.png"))
    dom["analyzer"].run(lid)
    j = client.get(f"/property/l/{lid}/report.json").get_json()
    assert j["score"] >= 0 and j["analyzer_version"] and j["dimensions"]
    assert "no es una predicción de venta" in j["_note"].lower()
    for f in j["findings"]:
        assert f["evidence"] is not None and f["explanation"]


def test_el_producto_no_promete_conversion(client, dom):
    """§IMPORTANTÍSIMO — en la UI tiene que quedar claro QUÉ mide el score."""
    lid = _listing(dom, area_m2=100)
    dom["analyzer"].run(lid)
    html = client.get(f"/property/l/{lid}").get_data(as_text=True).lower()
    assert "no es una probabilidad de venta" in html
    for prohibido in ("probabilidad de vender", "más leads", "garantiza", "vas a vender"):
        assert prohibido not in html, prohibido


# ===================================================================================================
# C — LAS MEDICIONES SON MEDICIONES
# ===================================================================================================
def test_las_fotos_se_miden_y_la_medicion_se_guarda(client, dom):
    lid = _listing(dom)
    mid = dom["listings"].add_media(lid, FS(_png(ruido=True), "a.png"))
    dom["analyzer"].measure_media(lid)
    a = dom["listings"].media(mid, lid)["analysis_obj"]
    assert a["ok"] and a["width"] == 1200 and a["height"] == 900
    for k in ("brightness", "sharpness", "edge_density", "emptiness_proxy", "dhash"):
        assert k in a, k


def test_una_foto_oscura_se_detecta_como_oscura(client, dom):
    lid = _listing(dom)
    dom["listings"].add_media(lid, FS(_png(tinte=(20, 20, 20)), "oscura.png"))
    dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), "clara.png"))
    r = dom["analyzer"].analyze(lid)
    c = next(x for x in r["dimensions"]["VISUAL"]["criteria"] if x["code"] == "SET_NO_DARK")
    assert len(c["measured"]["dark"]) == 1 and c["value"] == 0.5


def test_las_fotos_repetidas_se_detectan_por_huella(client, dom):
    lid = _listing(dom)
    blob = _png(ruido=True)
    dom["listings"].add_media(lid, FS(blob, "a.png"))
    dom["listings"].add_media(lid, FS(blob, "b.png"))
    dom["listings"].add_media(lid, FS(_png(tinte=(90, 180, 90), ruido=True), "c.png"))
    r = dom["analyzer"].analyze(lid)
    c = next(x for x in r["dimensions"]["VISUAL"]["criteria"] if x["code"] == "SET_NO_DUPLICATES")
    assert c["measured"]["redundant_photos"] == 1
    assert len(c["measured"]["duplicate_groups"]) == 1


def test_la_portada_se_compara_con_la_mejor_foto(client, dom):
    """El hallazgo más barato de arreglar del informe: no cuesta producir nada, sólo elegir."""
    lid = _listing(dom)
    mala = dom["listings"].add_media(lid, FS(_png(w=400, h=300, tinte=(25, 25, 25)), "mala.png"))
    dom["listings"].add_media(lid, FS(_png(ruido=True), "buena.png"))
    dom["listings"].set_cover(lid, mala)
    r = dom["analyzer"].analyze(lid)
    c = next(x for x in r["dimensions"]["COVER"]["criteria"]
             if x["code"] == "COVER_IS_BEST_AVAILABLE")
    assert c["measured"]["is_best"] is False
    f = next(x for x in r["findings"] if x["code"] == "COVER_IS_BEST_AVAILABLE")
    assert f["intervention"] == dom["iv"].COVER_SELECTION


# ===================================================================================================
# D — LA DIMENSIÓN DIFERENCIAL
# ===================================================================================================
def test_un_espacio_vacio_comercial_propone_mostrar_usos(client, dom):
    lid = _listing(dom, property_type=dom["listings"].RETAIL)
    for i in range(3):
        dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    r = dom["analyzer"].analyze(lid)
    f = next(x for x in r["findings"] if x["code"] == "POT_EMPTY_SPACE_SHOWN")
    assert f["intervention"] == dom["iv"].SPACE_REIMAGINATION
    assert f["evidence"]["proxy"].startswith("densidad de bordes")


def test_un_espacio_vacio_residencial_propone_amoblar(client, dom):
    """La misma carencia, dos conversaciones distintas según qué se está vendiendo."""
    lid = _listing(dom, property_type=dom["listings"].APARTMENT)
    for i in range(3):
        dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    r = dom["analyzer"].analyze(lid)
    f = next(x for x in r["findings"] if x["code"] == "POT_EMPTY_SPACE_SHOWN")
    assert f["intervention"] == dom["iv"].VIRTUAL_STAGE


def test_el_proxy_de_vacio_no_penaliza_si_ya_hay_una_visualizacion(client, dom):
    """El proxy nunca decide solo: hacen falta las dos señales, espacio que se lee vacío Y ninguna
    visualización que muestre un uso."""
    lid = _listing(dom, property_type=dom["listings"].APARTMENT)
    for i in range(3):
        dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    antes = dom["analyzer"].analyze(lid)
    dom["listings"].add_media(lid, FS(_png(ruido=True), "idea.png"),
                              dom["listings"].CONCEPTUAL)
    despues = dom["analyzer"].analyze(lid)
    def _v(r):
        return next(c["value"] for c in r["dimensions"]["POTENTIAL"]["criteria"]
                    if c["code"] == "POT_EMPTY_SPACE_SHOWN")
    assert _v(antes) < 1.0 and _v(despues) == 1.0


# ===================================================================================================
# E — CAPACIDAD ESPACIAL: el motor existente, invocado, no copiado
# ===================================================================================================
def test_se_detecta_el_plano_y_se_ofrece_la_capacidad(client, dom):
    lid = _listing(dom, area_m2=543)
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    cap = dom["plans"].capability(lid)
    assert cap["available"] is True and cap["commercial"] is True
    assert "Detectamos un plano" in cap["headline"]
    assert cap["plan"]["status"] == dom["plans"].LOOKS_MULTI_UNIT
    r = dom["analyzer"].analyze(lid)
    assert r["capabilities"][dom["iv"].SPATIAL_LAYOUT] is True
    f = next(x for x in r["findings"] if x["code"] == "POT_PLAN_DEMONSTRATED")
    assert f["intervention"] == dom["iv"].SPATIAL_LAYOUT


def test_la_mirada_barata_no_corre_el_motor(client, dom):
    """`inspect()` contesta en milisegundos y NO deja caso creado: hacer esperar el pipeline a
    quien sólo quería su score sería cobrarle una capacidad que no pidió."""
    lid = _listing(dom)
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    st = dom["plans"].inspect(lid)
    assert st["analyzed"] is False
    assert dom["listings"].get(lid)["plan_case_id"] is None


def test_analizar_el_plano_usa_el_pipeline_existente(client, dom):
    """El plano entra al motor por el MISMO alta de caso que usa el resto del sistema."""
    from webapp import store
    lid = _listing(dom, area_m2=543)
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    case_id = dom["plans"].ensure_case(lid)
    assert store.q1("SELECT 1 FROM cases WHERE case_id=?", (case_id,))
    assert dom["listings"].get(lid)["plan_case_id"] == case_id
    assert store.q1("SELECT published_area_m2 FROM cases WHERE case_id=?",
                    (case_id,))["published_area_m2"] == 543
    assert dom["plans"].ensure_case(lid) == case_id            # idempotente


def test_sin_plano_no_se_ofrece_capacidad_espacial(client, dom):
    lid = _listing(dom)
    assert dom["plans"].inspect(lid)["status"] == dom["plans"].NO_PLAN
    assert dom["plans"].capability(lid)["available"] is False
    assert dom["analyzer"].analyze(lid)["capabilities"][dom["iv"].SPATIAL_LAYOUT] is False


# ===================================================================================================
# F — REGLA DE VERACIDAD
# ===================================================================================================
def test_toda_intervencion_generativa_declara_que_preserva(client, dom):
    for code in dom["iv"].TYPES:
        c = dom["iv"].contract(code)
        assert c["preserve"] and c["forbidden"]
        for prohibido in ("muros", "ventanas", "pilares", "dimensiones"):
            assert prohibido in c["forbidden"], (code, prohibido)
        if c["generative"]:
            assert c["visualization_class"] == "CONCEPTUAL_VISUALIZATION"
            assert c["disclosure"] == "Visualización referencial de potencial."


def test_la_remodelacion_no_se_recomienda_sola(client, dom):
    """No hay clasificador de recintos. Proponerla igual sería el «score diseñado para vender
    features» que el encargo prohíbe."""
    assert dom["iv"].auto_recommendable(dom["iv"].RENOVATION_VISUALIZATION) is False
    assert dom["iv"].CATALOG[dom["iv"].RENOVATION_VISUALIZATION]["why_not_auto"]
    lid = _listing(dom, property_type=dom["listings"].APARTMENT)
    for i in range(3):
        dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    r = dom["analyzer"].analyze(lid)
    assert all(f["intervention"] != dom["iv"].RENOVATION_VISUALIZATION for f in r["findings"])


def test_una_demo_sin_proveedor_no_se_finge_lista(client, dom):
    """§ENTREGA — «Prefiero contracts honestos y placeholders explícitos antes que features
    simuladas.»"""
    lid = _listing(dom, property_type=dom["listings"].APARTMENT)
    mid = dom["listings"].add_media(lid, FS(_png(), "a.png"))
    did = dom["demos"].request(lid, dom["iv"].VIRTUAL_STAGE, mid)
    d = dom["demos"].get(did)
    assert d["status"] == dom["demos"].NOT_AVAILABLE
    assert d["visualization_class"] == "CONCEPTUAL_VISUALIZATION"
    assert d["disclosure"] == dom["iv"].DISCLOSURE
    assert "proveedor" in d["notes_obj"]["note"]
    # el contrato de veracidad queda COPIADO con la demo, no referenciado
    assert d["notes_obj"]["contract"]["forbidden"]
    assert dom["demos"].before_after(did) is None, "sin resultado no hay antes/después"


def test_una_demo_no_generativa_si_puede_quedar_lista(client, dom):
    """Elegir mejor portada no requiere generar nada: es una decisión sobre lo que ya existe."""
    lid = _listing(dom)
    did = dom["demos"].request(lid, dom["iv"].COVER_SELECTION)
    assert dom["demos"].get(did)["status"] == dom["demos"].READY


def test_no_se_puede_marcar_lista_una_demo_sin_resultado(client, dom):
    lid = _listing(dom)
    mid = dom["listings"].add_media(lid, FS(_png(), "a.png"))
    did = dom["demos"].request(lid, dom["iv"].VIRTUAL_STAGE, mid)
    with pytest.raises(dom["demos"].DemoError):
        dom["demos"].attach_result(did, "m_inexistente")


# ===================================================================================================
# G — AISLAMIENTO: no romper lo que ya existe
# ===================================================================================================
def test_un_aviso_no_aparece_en_el_lab(client, dom):
    """El aislamiento que justifica tablas separadas: un aviso analizado NO puede aparecer en la
    portada del LAB, ni en el contador del piloto, ni crear concesiones de pack."""
    from webapp import store
    from webapp.domain import properties, realpilot
    lid = _listing(dom)
    dom["listings"].add_media(lid, FS(_png(), "a.png"))
    dom["analyzer"].run(lid)
    assert properties.listing() == []
    assert realpilot.members() == []
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 0
    assert store.q1("SELECT COUNT(*) n FROM pack_grants")["n"] == 0
    assert "Mis propiedades" not in client.get("/property/").get_data(as_text=True)


def test_la_navegacion_del_lab_no_cambio(client, dom):
    html = client.get("/lab/").get_data(as_text=True)
    assert "/property" not in html
    assert html.count('href="/lab/ajustes"') == 1


def test_las_pantallas_nuevas_no_dan_500(client, dom):
    lid = _listing(dom)
    dom["analyzer"].run(lid)
    for u in ("/property/", f"/property/l/{lid}", f"/property/l/{lid}/report.json"):
        assert client.get(u).status_code == 200, u
    dom["listings"].add_media(lid, FS(_png(), "a.png"))
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    dom["analyzer"].run(lid)
    assert client.get(f"/property/l/{lid}").status_code == 200


def test_el_material_de_un_aviso_no_se_sirve_desde_otro(client, dom):
    """La misma barrera que protege los assets del LAB: un id ajeno no abre un archivo."""
    a, b = _listing(dom), _listing(dom)
    mid = dom["listings"].add_media(a, FS(_png(), "a.png"))
    assert client.get(f"/property/l/{a}/m/{mid}").status_code == 200
    assert client.get(f"/property/l/{b}/m/{mid}").status_code == 404
    assert dom["listings"].media(mid, b) is None


def test_el_motor_no_se_toco(client, dom):
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"el motor cambió: {out.stdout}"


def test_las_heuristicas_del_motor_siguen_donde_estaban(client, dom):
    from webapp.domain import calibration, ingest, units
    assert ingest.AUTO_CONFIRM_THRESHOLDS == {"perimeter": 0.60, "core": 0.50,
                                              "primary_entrance": 0.70, "columns": 0.55,
                                              "daylight": 0.45}
    assert ingest.UNCERTAINTY_BAND == {"core": 0.10}
    assert units.MIN_RELATIVE_AREA == 0.15 and calibration.MIN_SAMPLE == 10


# ===================================================================================================
# E17.1 — MULTIUNIDAD, JERARQUÍA DEL INFORME Y REVISIÓN HUMANA
# ===================================================================================================
def test_el_selector_de_unidades_reutiliza_e35_y_no_lo_copia(client, dom):
    """§1 / §7 — el algoritmo de candidatos es UNO SOLO. `/property` importa `domain.units` y
    llama a sus funciones; si alguien copiara el ranking, las dos superficies empezarían a
    responder distinto sobre la misma lámina el día que una cambie."""
    import inspect as _i
    from webapp.domain import units
    from webapp.domain.potential import plans
    fuente = _i.getsource(plans)
    assert "from .. import units" in fuente
    for propio in ("def candidates(", "def _color_clusters(", "PALETTE ="):
        assert propio not in fuente, f"{propio} está duplicado en plans.py"
    # y las funciones puras que usa son las de E35, no copias
    assert plans.unit_overrides.__module__ == "webapp.domain.potential.plans"
    assert callable(units.overrides_for_candidate) and callable(units.draw_candidates)


def test_una_lamina_multiunidad_pide_un_clic_dentro_de_property(client, dom):
    """§1 — la pregunta aparece INLINE en `/property`, con los candidatos visuales de E35."""
    lid = _listing(dom, area_m2=543)
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    sel = dom["plans"].resolve_units(lid)
    assert sel["candidate_count"] == 3
    assert dom["plans"].needs_unit_pick(lid) is True
    assert dom["plans"].state(lid)["status"] == dom["plans"].NEEDS_UNIT_PICK
    html = client.get(f"/property/l/{lid}").get_data(as_text=True)
    assert "¿Cuál es la oficina de este aviso?" in html
    assert f"/property/l/{lid}/unidad" in html
    assert client.get(f"/property/l/{lid}/unidades.png").status_code == 200


def test_el_clic_desbloquea_el_motor_y_no_crea_nada_del_lab(client, dom):
    """§1 / §8 — un clic: persiste, vuelve a correr el motor, sigue en `/property`, y NO crea
    `property`, ni `pack_grant`, ni fila en la tabla de selección del LAB."""
    from webapp import store
    from webapp.domain import units
    lid = _listing(dom, area_m2=543)
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    dom["plans"].resolve_units(lid)
    r = client.post(f"/property/l/{lid}/unidad", data={"candidate_id": "u1"})
    assert r.status_code == 302 and r.headers["Location"].startswith(f"/property/l/{lid}")
    sel = dom["plans"].unit_state(lid)
    assert sel["source"] == units.HUMAN_PICK and sel["selected_candidate_id"] == "u1"
    st = dom["plans"].state(lid)
    assert st["status"] == dom["plans"].NEEDS_REVIEW and round(st["area_m2"]) == 543
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 0
    assert store.q1("SELECT COUNT(*) n FROM pack_grants")["n"] == 0
    assert store.q1("SELECT COUNT(*) n FROM unit_selection")["n"] == 0


def test_un_reanalisis_no_borra_el_clic(client, dom):
    from webapp.domain import units
    lid = _listing(dom, area_m2=543)
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    dom["plans"].resolve_units(lid)
    dom["plans"].pick_unit(lid, "u2")
    de_nuevo = dom["plans"].resolve_units(lid)
    assert de_nuevo["source"] == units.HUMAN_PICK
    assert de_nuevo["selected_candidate_id"] == "u2"


def test_el_motor_no_corre_antes_de_saber_cual_es_la_unidad(client, dom):
    """§1 — correr el pipeline sobre una lámina multiunidad sin elegir no falla de forma
    interesante: falla siempre. Y el mensaje «no pudimos leerlo» sería falso: se puede leer,
    falta saber cuál."""
    lid = _listing(dom, area_m2=543)
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    r = dom["plans"].analyze(lid)
    assert r["status"] == dom["plans"].NEEDS_UNIT_PICK
    assert dom["listings"].get(lid)["plan_case_id"] is None, "no se creó caso al pedo"


def test_el_informe_empieza_por_las_oportunidades_no_por_el_puntaje(client, dom):
    """§2 — ESCALÍMETRO no vende un score. El puntaje sigue existiendo, detrás de un resumen."""
    lid = _listing(dom, area_m2=543)
    for i in range(3):
        dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    dom["analyzer"].run(lid)
    html = client.get(f"/property/l/{lid}").get_data(as_text=True)
    i_oport = html.index("Oportunidades para mostrar mejor esta propiedad")
    i_score = html.index("Ver diagnóstico completo")
    assert i_oport < i_score, "el puntaje aparece antes que las oportunidades"
    assert "scorecard" in html.split("Ver diagnóstico completo")[1], \
        "el puntaje tiene que estar DENTRO del detalle"


def test_los_hallazgos_se_separan_en_dos_clases(client, dom):
    """§2 — lo que resolvemos nosotros y lo que resuelve quien publica son dos conversaciones."""
    a = dom["analyzer"]
    lid = _listing(dom, property_type=dom["listings"].RETAIL)
    for i in range(3):
        dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    r = a.analyze(lid)
    assert r["resolvable"] and r["recommendations"]
    assert all(f["intervention"] for f in r["resolvable"])
    assert all(f["intervention"] is None for f in r["recommendations"])
    # y lo resoluble va primero
    assert r["findings"][0]["kind"] == a.RESOLVABLE
    # la oportunidad principal es una que podamos resolver, no la mayor carencia del aviso
    assert r["primary"]["kind"] == a.RESOLVABLE


def test_no_se_ofrece_lo_que_no_existe(client, dom):
    """§3 — un hallazgo sólo dice «Escalímetro puede resolverlo» si hay algo detrás. La mejora de
    imagen no está implementada en ningún lado, así que no se ofrece."""
    iv = dom["iv"]
    assert iv.support(iv.PHOTO_ENHANCE) == iv.NOT_BUILT
    assert iv.resolvable(iv.PHOTO_ENHANCE) is False
    lid = _listing(dom)
    dom["listings"].add_media(lid, FS(_png(tinte=(20, 20, 20)), "oscura.png"))
    dom["listings"].add_media(lid, FS(_png(ruido=True), "buena.png"))
    r = dom["analyzer"].analyze(lid)
    oscura = next(f for f in r["findings"] if f["code"] == "SET_NO_DARK")
    assert oscura["kind"] == dom["analyzer"].RECOMMENDATION
    assert oscura["intervention"] is None


def test_lo_pendiente_de_proveedor_se_ofrece_pero_no_se_entrega(client, dom):
    """§3 — «disponible para prueba interna / pendiente de proveedor aprobado» es una respuesta
    válida. Un resultado ficticio, no."""
    iv = dom["iv"]
    assert iv.support(iv.SPACE_REIMAGINATION) == iv.PENDING_PROVIDER
    assert iv.resolvable(iv.SPACE_REIMAGINATION) is True
    assert iv.deliverable_today(iv.SPACE_REIMAGINATION) is False
    lid = _listing(dom, property_type=dom["listings"].RETAIL)
    for i in range(3):
        dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    dom["analyzer"].run(lid)
    html = client.get(f"/property/l/{lid}").get_data(as_text=True)
    assert "pendiente de proveedor aprobado" in html
    vacio = next(f for f in dom["analyzer"].latest(lid)["resolvable"]
                 if f["code"] == "POT_EMPTY_SPACE_SHOWN")
    assert vacio["deliverable_today"] is False


def test_demostrar_cabida_si_se_puede_entregar_hoy(client, dom):
    """El motor de layouts existe y corre desde E28: es la capacidad más fuerte que tenemos."""
    iv = dom["iv"]
    assert iv.deliverable_today(iv.SPATIAL_LAYOUT) is True
    assert iv.deliverable_today(iv.COVER_SELECTION) is True
    lid = _listing(dom, area_m2=543)
    dom["listings"].add_media(lid, FSPath(PLANO_403), dom["listings"].PLAN)
    dom["plans"].resolve_units(lid)
    dom["plans"].pick_unit(lid, "u1")
    r = dom["analyzer"].analyze(lid)
    plano = next(f for f in r["resolvable"] if f["code"] == "POT_PLAN_DEMONSTRATED")
    assert plano["intervention"] == iv.SPATIAL_LAYOUT and plano["deliverable_today"] is True


# ---- revisión humana y tablero ------------------------------------------------------------------
def test_la_revision_humana_guarda_los_tres_juicios(client, dom):
    """§4 — tres juicios cerrados y un comentario. Ningún score nuevo."""
    from webapp.domain.potential import reviews as pr
    lid = _listing(dom)
    dom["analyzer"].run(lid)
    assert pr.get(lid) is None and pr.complete(lid) is False
    r = client.post(f"/property/l/{lid}/revision",
                    data={"diagnosis": "ACERTADO", "opportunity": pr.HAY_OPORTUNIDAD,
                          "worth_contacting": "SI", "comment": "el plano vale oro"})
    assert r.status_code == 302
    d = pr.get(lid)
    assert d["diagnosis"] == "ACERTADO" and d["worth_contacting"] == "SI"
    assert d["comment"] == "el plano vale oro" and d["report_id"]
    assert pr.complete(lid) is True
    with pytest.raises(pr.ReviewError):
        pr.save(lid, diagnosis="MAS_O_MENOS")


def test_los_tres_juicios_son_independientes(client, dom):
    """Pueden discrepar, y esa discrepancia es lo más valioso de la muestra: un diagnóstico
    acertado sin oportunidad dice que el instrumento anda y el negocio no está ahí."""
    from webapp.domain.potential import reviews as pr
    lid = _listing(dom)
    dom["analyzer"].run(lid)
    pr.save(lid, diagnosis="ACERTADO")
    assert pr.complete(lid) is False
    pr.save(lid, opportunity=pr.SIN_OPORTUNIDAD)
    assert pr.get(lid)["diagnosis"] == "ACERTADO", "guardar uno no borra el otro"
    pr.save(lid, worth_contacting="NO")
    d = pr.get(lid)
    assert (d["diagnosis"], d["opportunity"], d["worth_contacting"]) == (
        "ACERTADO", pr.SIN_OPORTUNIDAD, "NO")


def test_el_tablero_de_la_muestra(client, dom):
    """§5 — secundario y simple: cuántos avisos, cuántos revisados, cuántos con oportunidad,
    cuántos vale la pena contactar, y qué propuso el sistema."""
    from webapp.domain.potential import reviews as pr
    a = _listing(dom, property_type=dom["listings"].RETAIL)
    for i in range(3):
        dom["listings"].add_media(a, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    dom["analyzer"].run(a)
    b = _listing(dom, title="Otro")
    dom["analyzer"].run(b)
    pr.save(a, diagnosis="ACERTADO", opportunity=pr.HAY_OPORTUNIDAD, worth_contacting="SI")
    pr.save(b, diagnosis="PARCIAL", opportunity=pr.SIN_OPORTUNIDAD, worth_contacting="NO")
    p = pr.dashboard()
    assert p["listings"] == 2 and p["reviewed"] == 2 and p["target"] == 20
    assert p["by_diagnosis"]["ACERTADO"] == 1 and p["by_diagnosis"]["PARCIAL"] == 1
    assert p["with_opportunity"] == 1 and p["with_opportunity_pct"] == 50.0
    assert p["worth_contacting"] == 1 and p["worth_contacting_pct"] == 50.0
    assert dom["iv"].SPACE_REIMAGINATION in p["by_intervention"]
    assert client.get("/property/dogfood").status_code == 200


def test_el_tablero_separa_lo_propuesto_de_lo_validado(client, dom):
    """Lo que proponemos no es lo que un humano validó. Confundirlos haría que el instrumento se
    auto-confirme: contaríamos como oportunidad cada cosa que el sistema quiso vender."""
    from webapp.domain.potential import reviews as pr
    lid = _listing(dom, property_type=dom["listings"].RETAIL)
    for i in range(3):
        dom["listings"].add_media(lid, FS(_png(tinte=(150, 150, 150)), f"{i}.png"))
    dom["analyzer"].run(lid)
    p = pr.dashboard()
    assert p["proposed_any"] == 1, "el sistema propuso algo"
    assert p["with_opportunity"] == 0, "pero nadie lo validó todavía"
    assert p["reviewed"] == 0


def test_el_tablero_no_tapa_el_producto(client, dom):
    """§5 — el tablero es secundario. El informe es el producto."""
    lid = _listing(dom)
    dom["analyzer"].run(lid)
    home = client.get("/property/").get_data(as_text=True)
    assert "Muestra de 20" not in home
    assert "¿Cuánto potencial está dejando sin mostrar tu propiedad?" in home
