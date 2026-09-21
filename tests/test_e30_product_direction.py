"""E30 §24 — tests de CONTRATO de la capa comercial.

Lo que se protege acá no es que la UI abra, sino las fronteras que hacen que esto sea un producto
y no una demo:

  · un preset produce un BriefV1 que el MOTOR acepta, para cualquier headcount, y nunca inventa gente;
  · el límite entre el pack de publicación y Pro corta en el DOMINIO, no escondiendo un botón;
  · el layout representativo se elige con un criterio declarado, no "el último";
  · la marca de un prospecto jamás aparece en el material de la propiedad;
  · un estilo visual no puede tocar la geometría;
  · cuando el motor no encuentra nada, el documento que se manda lo dice.
"""
from __future__ import annotations

import importlib
import io
import json
import os
import struct
import sys
import zipfile
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

MODULOS = ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.briefs",
           "webapp.domain.settings", "webapp.domain.entitlements", "webapp.domain.presets",
           "webapp.domain.properties", "webapp.domain.assets", "webapp.domain.branding",
           "webapp.domain.fits", "webapp.domain.floorplan", "webapp.domain.proposal",
           "webapp.domain.packs", "webapp.domain.visual", "webapp.customer", "webapp.app")


def _png(w: int = 12, h: int = 9) -> bytes:
    raw = b"".join(b"\x00" + b"\xcc\xdd\xee" * w for _ in range(h))

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
    for m in MODULOS:
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def dom():
    from webapp.domain import (assets, branding, entitlements, fits, floorplan, packs, presets,
                               properties, proposal, visual)
    return {"assets": assets, "branding": branding, "entitlements": entitlements, "fits": fits,
            "floorplan": floorplan, "packs": packs, "presets": presets, "properties": properties,
            "proposal": proposal, "visual": visual}


def _prop(dom, titulo="Oficina de prueba"):
    return dom["properties"].create(titulo, "OFFICE", city="Santiago", published_area_m2=543.0)


def _subir(dom, pid, kind, nombre="x.png", blob=None):
    from werkzeug.datastructures import FileStorage
    return dom["assets"].save_upload(
        pid, FileStorage(stream=io.BytesIO(blob or _png()), filename=nombre), kind)


def _case_listo(store, case_id="c_test", estado="READY"):
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES (?,?,?,?,?,?,?,'DEVELOPMENT')",
             (case_id, "Caso", "a.png", "a.png", "image/png", store.now(), estado))
    d = os.path.join(store.case_dir(case_id), "outputs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
        json.dump({"shell_readiness": {"ready_for_layout": estado == "READY",
                                       "requires_confirmation": []}}, fh)
    return case_id


def _run_con_alternativas(store, case_id, run_id="r1", alts=(("A", "FIT", True),),
                          best_alt=None):
    """Una corrida con sus láminas en disco, sin invocar al motor."""
    from webapp import engine
    store.ex("INSERT OR REPLACE INTO briefs(brief_id,case_id,name,headcount,workstations,rooms,"
             "brief_sha256,created_at) VALUES ('b',?,'b',40,36,'[]','sha','t')", (case_id,))
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,engine_commit,created_at,best_alt) "
             "VALUES (?,?,'b','DONE','commit123','t',?)", (run_id, case_id, best_alt))
    for alt, estado, completo in alts:
        store.ex("INSERT OR REPLACE INTO alternatives(run_id,alt,name,status,layout_sha256,quality)"
                 " VALUES (?,?,?,?,?,?)",
                 (run_id, alt, f"NOMBRE_{alt}", estado, f"sha_{alt}",
                  json.dumps({"program_complete": completo})))
        if estado != "FIT":
            continue
        d = os.path.join(engine.run_dir(case_id, run_id), "alternatives", alt)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "layout_commercial.png"), "wb") as fh:
            fh.write(_png())
    return run_id


def _propiedad_con_layouts(dom, store, alts=(("A", "FIT", True),), best_alt=None, cid="c_lay"):
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    _case_listo(store, cid)
    dom["properties"].link_case(pid, cid)
    _run_con_alternativas(store, cid, "r1", alts, best_alt)
    return pid, cid


# ===================================================================================================
# A — PRESETS DE LUGAR DE TRABAJO (§5)
# ===================================================================================================
def test_todo_preset_produce_un_brief_que_el_motor_acepta(dom):
    """La prueba que importa: el juez es `BriefV1.validate` del MOTOR, no una copia nuestra."""
    from escalimetro.brief import BriefV1
    from escalimetro.layout.model import load_modules
    from webapp import briefs as briefmod
    mods, _ = load_modules(briefmod.MODULES_PATH)
    for preset in dom["presets"].WORKPLACE_PRESETS:
        for h in (1, 2, 3, 5, 12, 25, 40, 77, 120, 300, 999):
            b = dom["presets"].brief_for(preset, h, "T")
            assert BriefV1.from_dict(b).validate(mods) == [], f"{preset} con {h} personas: {b}"


def test_un_preset_nunca_fabrica_ocupacion(dom):
    """§22 — antes de inventar una persona, el preset entrega menos programa."""
    from escalimetro.brief import BriefV1
    for preset in dom["presets"].WORKPLACE_PRESETS:
        for h in (1, 2, 4, 9, 40, 150):
            b = BriefV1.from_dict(dom["presets"].brief_for(preset, h, "T"))
            privados = b.room_count("private_office") + b.room_count("reception")
            assert b.open_workstations + privados <= h


def test_los_presets_se_diferencian_en_la_direccion_declarada(dom):
    """Si DENSA y COLABORATIVA dieran el mismo programa, el preset sería decorativo."""
    p = dom["presets"]
    densa = p.brief_for(p.DENSE, 60, "T")
    colab = p.brief_for(p.COLLABORATIVE, 60, "T")
    ejec = p.brief_for(p.EXECUTIVE, 60, "T")
    salas = lambda b: sum(r["count"] for r in b["rooms"]                    # noqa: E731
                          if r["module"].startswith(("meeting", "boardroom")))
    priv = lambda b: sum(r["count"] for r in b["rooms"]                     # noqa: E731
                         if r["module"] == "private_office")
    assert densa["open_workstations"] > colab["open_workstations"]
    assert salas(colab) > salas(densa)
    assert priv(ejec) > priv(densa)


def test_un_preset_solo_toca_campos_de_briefv1(dom):
    """§5 — no inventar semántica del motor. Un preset no puede colar pesos ni zonificación."""
    b = dom["presets"].brief_for(dom["presets"].BALANCED, 40, "T")
    assert set(b) == {"contract_version", "brief_id", "target_headcount", "open_workstations",
                      "rooms"}
    texto = json.dumps(b)
    for prohibido in ("objective_weights", "zoning", "adjacency", "neighborhood", "strategy",
                      "design_policy"):
        assert prohibido not in texto


def test_pedir_mas_puestos_que_personas_se_rechaza(dom):
    with pytest.raises(dom["presets"].PresetError):
        dom["presets"].program_for(dom["presets"].BALANCED, 10, target_seats=20)


def test_un_preset_desconocido_no_se_inventa(dom):
    with pytest.raises(dom["presets"].PresetError):
        dom["presets"].brief_for("HOT_DESK_EXTREMO", 40, "T")


# ===================================================================================================
# B — DERECHOS DE PRODUCTO (§17)
# ===================================================================================================
def test_el_modo_por_defecto_entrega_de_menos_no_de_mas(client, dom):
    """Si alguien olvida configurar el producto, se entrega el pack, no Pro."""
    e = dom["entitlements"]
    assert e.mode() == "ONE_OFF"
    assert e.allows(e.PROSPECT_FIT_REQUESTS) is False


def test_la_matriz_cubre_todas_las_capacidades(client, dom):
    e = dom["entitlements"]
    for modo in e.PRODUCT_MODES:
        assert set(e.GRANTS[modo]) == set(e.CAPABILITIES), modo
        assert modo in e.MODE_LABEL and modo in e.MODE_PITCH


def test_el_limite_corta_en_el_dominio_no_en_la_plantilla(client, dom):
    """El punto del §17: aunque alguien escriba la URL a mano, la operación no ocurre."""
    pid = _prop(dom)
    with pytest.raises(dom["entitlements"].EntitlementError):
        dom["fits"].create_prospect(pid, "Falabella", 30)


def test_el_pack_de_publicacion_cubre_una_sola_propiedad(client, dom):
    _prop(dom)
    r = client.post("/properties/new", data={"title": "Otra"})
    assert r.status_code == 403
    assert "Escalímetro Pro" in r.get_data(as_text=True)


def test_en_pro_se_pueden_crear_varias_propiedades(client, dom):
    dom["entitlements"].set_mode("PRO")
    _prop(dom)
    assert client.post("/properties/new", data={"title": "Otra"},
                       follow_redirects=True).status_code == 200


def test_one_off_entrega_una_alternativa_y_pro_las_tres(client, dom):
    """§4 — la diferencia comercial, medida sobre el mismo resultado del motor."""
    from webapp import store
    pid, _ = _propiedad_con_layouts(
        dom, store, alts=(("A", "FIT", True), ("B", "FIT", True), ("C", "FIT", True)))
    assert len(dom["floorplan"].publish_layouts(pid)) == 1
    dom["entitlements"].set_mode("PRO")
    assert len(dom["floorplan"].publish_layouts(pid)) == 3


def test_regenerar_esta_fuera_del_pack_de_publicacion(client, dom):
    from webapp import store
    pid, cid = _propiedad_con_layouts(dom, store)
    fid = dom["fits"].ensure_base(pid, 40)
    store.ex("INSERT INTO fit_runs(fit_id,run_id,created_at) VALUES (?,?,?)",
             (fid, "r1", store.now()))
    with pytest.raises(dom["entitlements"].EntitlementError):
        dom["fits"].generate(fid)


# ===================================================================================================
# C — FIT REQUESTS (§9)
# ===================================================================================================
def test_el_fit_base_es_idempotente(client, dom):
    pid = _prop(dom)
    assert dom["fits"].ensure_base(pid, 40) == dom["fits"].ensure_base(pid, 55)
    assert dom["fits"].base_of(pid)["headcount"] == 55


def test_un_fit_nuevo_no_destruye_los_anteriores(client, dom):
    """§9 — literal: 'Do not destroy previous fit requests when creating new ones'."""
    dom["entitlements"].set_mode("PRO")
    pid = _prop(dom)
    a = dom["fits"].create_prospect(pid, "Falabella", 40)
    b = dom["fits"].create_prospect(pid, "Cencosud", 25)
    ids = [f["fit_id"] for f in dom["fits"].list_for(pid, include_base=False)]
    assert a in ids and b in ids


def test_archivar_no_borra(client, dom):
    dom["entitlements"].set_mode("PRO")
    pid = _prop(dom)
    fid = dom["fits"].create_prospect(pid, "Falabella", 40)
    dom["fits"].archive(fid)
    assert dom["fits"].get(fid) is not None
    assert fid not in [f["fit_id"] for f in dom["fits"].list_for(pid)]
    assert fid in [f["fit_id"] for f in dom["fits"].list_for(pid, include_archived=True)]


def test_un_fit_de_otra_propiedad_no_existe(client, dom):
    dom["entitlements"].set_mode("PRO")
    a, b = _prop(dom, "A"), _prop(dom, "B")
    fid = dom["fits"].create_prospect(a, "Falabella", 40)
    assert dom["fits"].get(fid, b) is None
    assert client.get(f"/properties/{b}/fits/{fid}").status_code == 404


def test_sin_personas_no_se_genera_nada(client, dom):
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    with pytest.raises(dom["fits"].FitError):
        dom["fits"].ensure_base(pid, "")


def test_sin_planta_lista_no_se_genera(client, dom):
    from webapp import store
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    _case_listo(store, "c_no", estado="NEEDS_CONFIRMATION")
    dom["properties"].link_case(pid, "c_no")
    fid = dom["fits"].ensure_base(pid, 40)
    with pytest.raises(dom["fits"].FitError):
        dom["fits"].generate(fid)
    assert store.q1("SELECT COUNT(*) n FROM runs")["n"] == 0


# ===================================================================================================
# D — LAYOUT REPRESENTATIVO (§18)
# ===================================================================================================
def test_el_juicio_humano_gana_sobre_el_criterio_automatico(client, dom):
    from webapp import store
    pid, _ = _propiedad_con_layouts(
        dom, store, alts=(("A", "FIT", True), ("B", "FIT", True)), best_alt="B")
    rep = dom["fits"].pick_representative(
        dict(store.q1("SELECT * FROM runs WHERE run_id='r1'")),
        [dict(a) for a in store.q("SELECT * FROM alternatives WHERE run_id='r1'")])
    assert rep["alt"]["alt"] == "B" and rep["selected_by"] == "human_best_alt"


def test_sin_juicio_humano_gana_el_programa_completo(client, dom):
    from webapp import store
    _propiedad_con_layouts(dom, store, alts=(("A", "FIT", False), ("B", "FIT", True)))
    rep = dom["fits"].pick_representative(
        dict(store.q1("SELECT * FROM runs WHERE run_id='r1'")),
        [dict(a) for a in store.q("SELECT * FROM alternatives WHERE run_id='r1'")])
    assert rep["alt"]["alt"] == "B" and rep["selected_by"] == "program_complete"


def test_si_ninguna_ubica_el_programa_se_dice_cual_es_el_criterio(client, dom):
    from webapp import store
    _propiedad_con_layouts(dom, store, alts=(("A", "FIT", False), ("B", "FIT", False)))
    rep = dom["fits"].pick_representative(
        dict(store.q1("SELECT * FROM runs WHERE run_id='r1'")),
        [dict(a) for a in store.q("SELECT * FROM alternatives WHERE run_id='r1'")])
    assert rep["selected_by"] == "first_fit"


def test_sin_alternativas_no_se_inventa_una_representativa(client, dom):
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store, alts=(("A", "SEARCH_EXHAUSTED", False),))
    assert dom["fits"].pick_representative(
        dict(store.q1("SELECT * FROM runs WHERE run_id='r1'")),
        [dict(a) for a in store.q("SELECT * FROM alternatives WHERE run_id='r1'")]) is None
    assert dom["floorplan"].publish_layouts(pid) == []


def test_la_lamina_publicada_dice_por_que_es_la_representativa(client, dom):
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store, alts=(("A", "FIT", True), ("B", "FIT", True)))
    ids = dom["floorplan"].publish_layouts(pid)
    m = store.js(dom["assets"].get(ids[0], pid)["metadata"], {})
    assert m["representative"] is True
    assert m["selected_by"] in dom["fits"].SELECTED_BY_LABEL


# ===================================================================================================
# E — MARCA (§20)
# ===================================================================================================
def test_el_material_de_la_propiedad_nunca_lleva_marca_del_prospecto(client, dom):
    """El error comercial que esto impide: mandar un aviso con el logo de quien no arrendó."""
    dom["entitlements"].set_mode("PRO")
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    dom["branding"].set_brokerage("GPS Property", "#0b5d3b")
    fid = dom["fits"].create_prospect(pid, "Falabella", 40, prospect_color="#1f4fd8")
    base = dom["packs"].build_manifest(pid)
    assert base["branding"]["prospect"] is None
    assert base["branding"]["brokerage"]["name"] == "GPS Property"
    delfit = dom["packs"].build_manifest(pid, fid)
    assert delfit["branding"]["prospect"]["name"] == "Falabella"


def test_un_color_de_marca_invalido_se_rechaza_en_la_puerta(dom):
    with pytest.raises(dom["branding"].BrandError):
        dom["branding"].normalize_color("rojo; </style><script>")
    assert dom["branding"].normalize_color("#ABC") == "#aabbcc"


def test_el_logo_de_un_prospecto_no_se_sirve_desde_otro_ambito(client, dom):
    from werkzeug.datastructures import FileStorage
    lid = dom["branding"].save_logo(
        FileStorage(stream=io.BytesIO(_png()), filename="l.png"), dom["branding"].PROSPECT)
    assert dom["branding"].logo(lid, dom["branding"].BROKERAGE) is None
    assert dom["branding"].logo(lid, dom["branding"].PROSPECT) is not None


# ===================================================================================================
# F — ESTILO VISUAL Y AMBIENTACIÓN (§6, §11, §12, §19)
# ===================================================================================================
def test_un_estilo_visual_no_puede_tocar_la_geometria(dom):
    """§6 — separar FUNCIÓN de ASPECTO. El mismo programa con dos estilos es el MISMO brief."""
    p = dom["presets"]
    a = p.brief_for(p.BALANCED, 40, "T")
    b = p.brief_for(p.BALANCED, 40, "T")
    assert a == b
    for estilo in p.VISUAL_STYLES:
        datos = p.style_brief(estilo)
        for prohibido in ("m2", "area", "window", "column", "wall", "shell", "geometry"):
            assert prohibido not in json.dumps(datos).lower()


def test_no_hay_modo_degradado_que_haga_pasar_la_foto_por_ambientada(dom):
    v = dom["visual"]
    prov = v.get_provider()
    assert prov.available() is False
    with pytest.raises(v.ProviderNotConfigured):
        prov.stage_photo(v.StagingRequest("p", "a"))


def test_la_ficha_del_piloto_pone_la_fidelidad_primero_y_eliminatoria(dom):
    f = dom["visual"].pilot_sheet()
    assert f["criteria"][0]["key"] == "fidelity" and f["eliminatory"] == "fidelity"
    assert f["decision"] is None and f["providers"] == []
    assert f["min_providers"] >= 2


def test_los_invariantes_se_declaran_pero_no_se_dan_por_verificados(dom):
    r = dom["visual"].StagingResult("a", "p", "m", None, None, None, {})
    assert r.invariants_verified is None


# ===================================================================================================
# G — PACK Y PROPUESTA (§8, §16)
# ===================================================================================================
def test_la_propuesta_de_un_prospecto_lleva_su_nombre(client, dom):
    dom["entitlements"].set_mode("PRO")
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    dom["branding"].set_brokerage("GPS Property", "#0b5d3b")
    fid = dom["fits"].create_prospect(pid, "Falabella", 40)
    html = dom["packs"].proposal_html(pid, fid)
    assert "Falabella" in html and "GPS Property" in html


def test_la_propuesta_dice_la_verdad_cuando_no_hay_alternativas(client, dom):
    """§22 — no se omite el resultado incómodo para que el documento se vea mejor."""
    dom["entitlements"].set_mode("PRO")
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store, alts=(("A", "SEARCH_EXHAUSTED", False),))
    fid = dom["fits"].create_prospect(pid, "Falabella", 40)
    html = dom["packs"].proposal_html(pid, fid)
    assert "Todavía no hay alternativas" in html
    assert "no cabe" not in html.lower()


def test_la_propuesta_escapa_lo_que_escribe_el_usuario(client, dom):
    dom["entitlements"].set_mode("PRO")
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    fid = dom["fits"].create_prospect(pid, "<script>alert(1)</script>", 40)
    html = dom["packs"].proposal_html(pid, fid)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_el_pack_base_y_el_de_un_prospecto_conviven(client, dom):
    dom["entitlements"].set_mode("PRO")
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    fid = dom["fits"].create_prospect(pid, "Falabella", 40)
    dom["floorplan"].publish_layouts(pid)
    dom["packs"].export_zip(pid)
    dom["packs"].export_zip(pid, fid)
    assert dom["packs"].get(pid)["kind"] == "BASE"
    assert dom["packs"].get(pid, fid)["fit_id"] == fid
    assert store.q1("SELECT COUNT(*) n FROM packs WHERE property_id=?", (pid,))["n"] == 2


def test_el_zip_trae_la_propuesta_y_dice_que_trae(client, dom):
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    dom["floorplan"].publish_layouts(pid)
    z = dom["packs"].export_zip(pid)
    blob = open(dom["assets"].path_of(dom["assets"].get(z["asset_id"], pid)), "rb").read()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        nombres = zf.namelist()
        assert "propuesta.html" in nombres and "manifest.json" in nombres
        man = json.loads(zf.read("manifest.json"))
    assert set(man["export"]["contents"]) <= set(nombres)
    assert all(not n.startswith("/") and ".." not in n for n in nombres)


def test_el_manifiesto_no_filtra_rutas_del_servidor(client, dom):
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    dom["floorplan"].publish_layouts(pid)
    texto = json.dumps(dom["packs"].build_manifest(pid))
    assert store.DATA_DIR not in texto and "/Users/" not in texto


def test_regenerar_el_pack_de_un_prospecto_no_borra_el_de_la_propiedad(client, dom):
    dom["entitlements"].set_mode("PRO")
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    fid = dom["fits"].create_prospect(pid, "Falabella", 40)
    dom["floorplan"].publish_layouts(pid)
    base = dom["packs"].export_zip(pid)["asset_id"]
    dom["packs"].export_zip(pid, fid)
    dom["packs"].export_zip(pid, fid)
    assert dom["assets"].get(base, pid) is not None
    assert os.path.exists(dom["assets"].path_of(dom["assets"].get(base, pid)))


# ===================================================================================================
# H — LENGUAJE DE CLIENTE (§21)
# ===================================================================================================
def test_el_cliente_no_ve_vocabulario_del_motor(client, dom):
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    dom["fits"].ensure_base(pid, 40)
    for url in ("/properties/", f"/properties/{pid}", "/properties/brand"):
        texto = client.get(url).get_data(as_text=True).lower()
        for palabra in ("shell", "floorplate", "cp-sat", "solver", "search_exhausted",
                        "design_policy", "ortools"):
            assert palabra not in texto, f"{url} dice «{palabra}»"


def test_la_pantalla_de_producto_no_promete_resultados_comerciales(client, dom):
    """§22 — nada de 'arrienda más rápido' ni 'mejor conversión' mientras no se mida."""
    texto = client.get("/properties/").get_data(as_text=True).lower()
    for promesa in ("más rápido", "mejor precio", "más caro", "conversión", "garantiza"):
        assert promesa not in texto


def test_el_limite_de_producto_se_explica_en_lenguaje_de_cliente(client, dom):
    _prop(dom)
    texto = client.post("/properties/new", data={"title": "Otra"}).get_data(as_text=True)
    assert "Escalímetro Pro" in texto
    assert "EntitlementError" not in texto and "Traceback" not in texto


# ===================================================================================================
# I — REGRESIÓN
# ===================================================================================================
def test_el_dominio_de_producto_no_importa_el_solver(client):
    """Ningún módulo de producto puede depender del motor: si lo hiciera, cambiar el producto
    obligaría a tocar el motor, que es exactamente lo que este proyecto evita."""
    import ast
    base = os.path.join(ROOT, "webapp", "domain")
    for archivo in os.listdir(base):
        if not archivo.endswith(".py"):
            continue
        arbol = ast.parse(open(os.path.join(base, archivo), encoding="utf-8").read())
        for nodo in ast.walk(arbol):
            mods = []
            if isinstance(nodo, ast.Import):
                mods = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                mods = [nodo.module or ""]
            for m in mods:
                assert not m.startswith("ortools"), f"{archivo} importa {m}"
                assert "layout.solver" not in m, f"{archivo} importa {m}"


def test_las_superficies_de_e27_y_e28_siguen_respondiendo(client):
    for url in ("/", "/healthz", "/review", "/settings", "/properties/"):
        assert client.get(url).status_code == 200, url


def test_una_corrida_sin_fit_sigue_siendo_valida(client, dom):
    """Los casos de E27 no nacieron de un fit request y tienen que seguir publicándose."""
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    assert store.q1("SELECT COUNT(*) n FROM fit_runs")["n"] == 0
    assert len(dom["floorplan"].publish_layouts(pid)) == 1


def test_el_motor_no_fue_tocado():
    """§14 — la geometría es el activo. E30 es producto: el hash del motor no se mueve."""
    import subprocess
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"E30 tocó el motor: {out.stdout}"


def test_el_fit_base_puede_publicar_la_corrida_de_un_caso_vinculado(client, dom):
    """Una propiedad conectada a mano a un caso que YA tenía corridas (el camino de E27/E28) sigue
    publicando. La lámina no miente: `fit_id` queda vacío porque no salió de ese programa."""
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    fid = dom["fits"].ensure_base(pid, 40)
    ids = dom["floorplan"].publish_layouts(pid, fit_id=fid)
    assert len(ids) == 1
    assert store.js(dom["assets"].get(ids[0], pid)["metadata"], {})["fit_id"] is None


def test_un_prospecto_no_hereda_el_layout_de_otro_programa(client, dom):
    """La otra mitad de la regla, y la que protege la confianza: mostrarle a un prospecto una
    lámina generada para otro programa sería exactamente la mentira que este sistema no comete."""
    dom["entitlements"].set_mode("PRO")
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    fid = dom["fits"].create_prospect(pid, "Falabella", 40)
    assert dom["floorplan"].publish_layouts(pid, fit_id=fid) == []
    assert "Todavía no hay alternativas" in dom["packs"].proposal_html(pid, fid)


def test_el_directorio_de_datos_es_absoluto(client):
    """Con una ruta relativa el mismo archivo se resuelve contra dos bases distintas: `open()`
    desde el directorio de trabajo y `flask.send_file` desde el del paquete. El ZIP se armaba bien
    y la imagen daba 500 — un fallo que sólo aparece desplegado."""
    from webapp import store
    assert os.path.isabs(store.DATA_DIR)


def test_las_imagenes_de_una_propiedad_se_sirven_de_verdad(client, dom):
    """No basta con que el asset exista en la base: la ruta tiene que abrir."""
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    dom["fits"].ensure_base(pid, 40)
    aid = dom["floorplan"].publish_layouts(pid)[0]
    r = client.get(f"/properties/{pid}/asset/{aid}")
    assert r.status_code == 200 and r.data[:4] == b"\x89PNG"


def test_la_propuesta_del_programa_base_muestra_su_lamina(client, dom):
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    fid = dom["fits"].ensure_base(pid, 40)
    dom["floorplan"].publish_layouts(pid, fit_id=fid)
    assert len(dom["packs"].layout_assets(pid, fid)) == 1
    assert "Todavía no hay alternativas" not in dom["packs"].proposal_html(pid, fid)


def test_la_propuesta_dice_por_que_esa_es_la_representativa(client, dom):
    """El motivo se lee de la lámina publicada, así que sigue siendo cierto aunque la corrida haya
    venido de un caso vinculado a mano."""
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store, alts=(("A", "FIT", True), ("B", "FIT", True)))
    fid = dom["fits"].ensure_base(pid, 40)
    dom["floorplan"].publish_layouts(pid, fit_id=fid)
    html = dom["packs"].proposal_html(pid, fid)
    assert dom["fits"].SELECTED_BY_LABEL["program_complete"] in html


def test_la_propuesta_describe_el_estilo_sin_hablar_de_geometria(client, dom):
    dom["entitlements"].set_mode("PRO")
    from webapp import store
    pid, _ = _propiedad_con_layouts(dom, store)
    fid = dom["fits"].create_prospect(pid, "Falabella", 40, style="PREMIUM")
    html = dom["packs"].proposal_html(pid, fid)
    assert "Premium" in html and "materiales nobles" in html
