"""E28 §25 — tests de CONTRATO de la capa de propiedad.

Lo que se protege acá no es "que la UI abra", sino las fronteras nuevas:

  · una PROPIEDAD existe por encima de un CASE y no lo reemplaza;
  · los assets de una propiedad no se pueden leer desde otra;
  · el adaptador no confirma nada por su cuenta ni se salta las compuertas del motor;
  · el plano comercial NO es la alternativa A;
  · el pack no presenta como real lo que no existe;
  · la superficie de cliente no habla el idioma del motor.
"""
from __future__ import annotations

import importlib
import io
import json
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))


def _png(w: int = 12, h: int = 9) -> bytes:
    import struct
    import zlib
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
    for m in ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine",
              "webapp.domain.properties", "webapp.domain.assets", "webapp.domain.floorplan",
              "webapp.domain.packs", "webapp.domain.visual", "webapp.customer", "webapp.app"):
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def dom():
    from webapp.domain import assets, floorplan, packs, properties, visual
    return {"properties": properties, "assets": assets, "floorplan": floorplan,
            "packs": packs, "visual": visual}


def _prop(dom, titulo="Oficina de prueba"):
    return dom["properties"].create(titulo, "OFFICE", city="Santiago", published_area_m2=543.0)


def _subir(dom, pid, kind, nombre="x.png", blob=None):
    from werkzeug.datastructures import FileStorage
    return dom["assets"].save_upload(
        pid, FileStorage(stream=io.BytesIO(blob or _png()), filename=nombre), kind)


def _pack_exportable(dom, pid):
    """E31 §21 — el pack BASE ya no se exporta con lo que haya: exige plano comercial y, si falta
    layout o imagen ambientada, un motivo interno escrito. Los tests que sólo prueban la mecánica
    del ZIP (rutas, aislamiento) declaran ese motivo en vez de fingir que el producto está entero."""
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_COMMERCIAL, "plano_comercial.png",
                             _png(), "image/png")
    dom["packs"].set_override(pid, "test: sin motor de ambientación en el entorno de pruebas")


def _case_listo(store, case_id="c_test", estado="READY"):
    """Un CASE con geometría declarada lista, sin correr el motor."""
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES (?,?,?,?,?,?,?,'DEVELOPMENT')",
             (case_id, "Caso", "a.png", "a.png", "image/png", store.now(), estado))
    d = os.path.join(store.case_dir(case_id), "outputs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
        json.dump({"shell_readiness": {"ready_for_layout": estado == "READY",
                                       "requires_confirmation": []
                                       if estado == "READY" else ["columns"]}}, fh)
    return case_id


# ===================================================================================================
# A — PROPERTY
# ===================================================================================================
def test_crear_propiedad_y_leerla(client, dom):
    pid = _prop(dom)
    p = dom["properties"].get(pid)
    assert p["title"] == "Oficina de prueba"
    assert p["asset_type"] == "OFFICE"
    assert p["schema_version"] == "property_v1"
    assert p["floorplan_case_id"] is None


def test_solo_office_es_funcional_en_v1(dom):
    with pytest.raises(ValueError):
        dom["properties"].create("Local", "RETAIL")


def test_una_propiedad_sin_caso_es_valida(client, dom):
    pid = _prop(dom)
    v = dom["properties"].view(pid)
    assert v["status"] == "DRAFT"
    assert v["case"] is None


def test_vincular_un_caso_existente(client, dom):
    from webapp import store
    pid = _prop(dom)
    cid = _case_listo(store)
    dom["properties"].link_case(pid, cid)
    assert dom["properties"].get(pid)["floorplan_case_id"] == cid


def test_un_caso_no_puede_pertenecer_a_dos_propiedades(client, dom):
    from webapp import store
    cid = _case_listo(store)
    dom["properties"].link_case(_prop(dom, "A"), cid)
    with pytest.raises(ValueError):
        dom["properties"].link_case(_prop(dom, "B"), cid)


def test_los_casos_viejos_siguen_funcionando_sin_propiedad(client, dom):
    """§20 — no hay retro-migración: un caso sin propiedad es normal, no un error."""
    from webapp import store
    cid = _case_listo(store)
    assert store.q1("SELECT property_id FROM properties WHERE floorplan_case_id=?", (cid,)) is None
    assert client.get(f"/case/{cid}").status_code == 200


# ===================================================================================================
# B — ASSETS
# ===================================================================================================
def test_subir_plano_y_varias_fotos(client, dom):
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    for i in range(3):
        _subir(dom, pid, dom["assets"].PHOTO_ORIGINAL, f"foto{i}.png")
    assert dom["assets"].first_of_kind(pid, dom["assets"].FLOORPLAN_ORIGINAL) is not None
    fotos = dom["assets"].list_of_kind(pid, dom["assets"].PHOTO_ORIGINAL)
    assert len(fotos) == 3
    assert [f["sort_order"] for f in fotos] == [0, 1, 2]


def test_el_nombre_del_usuario_no_llega_al_filesystem(client, dom):
    """§24 — path traversal: el nombre subido es un dato, no una ruta."""
    pid = _prop(dom)
    aid = _subir(dom, pid, dom["assets"].PHOTO_ORIGINAL, "../../../../etc/passwd.png")
    a = dom["assets"].get(aid, pid)
    assert a["original_filename"] == "../../../../etc/passwd.png"      # se conserva como dato
    assert "/" not in a["stored_name"] and ".." not in a["stored_name"]
    from webapp import store
    ruta = os.path.realpath(dom["assets"].path_of(a))
    assert ruta.startswith(os.path.realpath(store.property_dir(pid)))


def test_el_contenido_tiene_que_coincidir_con_la_extension(client, dom):
    pid = _prop(dom)
    with pytest.raises(dom["assets"].AssetError):
        _subir(dom, pid, dom["assets"].PHOTO_ORIGINAL, "falso.png", b"%PDF-1.4 no soy png")


def test_una_foto_no_puede_ser_un_pdf(client, dom):
    pid = _prop(dom)
    with pytest.raises(dom["assets"].AssetError):
        _subir(dom, pid, dom["assets"].PHOTO_ORIGINAL, "doc.pdf", b"%PDF-1.4 hola")


def test_todo_asset_lleva_hash_y_tamano(client, dom):
    pid = _prop(dom)
    a = dom["assets"].get(_subir(dom, pid, dom["assets"].PHOTO_ORIGINAL), pid)
    assert len(a["sha256"]) == 64 and a["size_bytes"] > 0
    assert a["width_px"] == 12 and a["height_px"] == 9


def test_no_se_puede_leer_un_asset_de_otra_propiedad(client, dom):
    """La barrera que importa: pasar un asset_id ajeno no devuelve nada."""
    a_pid, b_pid = _prop(dom, "A"), _prop(dom, "B")
    aid = _subir(dom, a_pid, dom["assets"].PHOTO_ORIGINAL)
    assert dom["assets"].get(aid, a_pid) is not None
    assert dom["assets"].get(aid, b_pid) is None
    assert client.get(f"/properties/{b_pid}/asset/{aid}").status_code == 404
    assert client.get(f"/properties/{a_pid}/asset/{aid}").status_code == 200


def test_borrar_un_asset_de_otra_propiedad_no_hace_nada(client, dom):
    a_pid, b_pid = _prop(dom, "A"), _prop(dom, "B")
    aid = _subir(dom, a_pid, dom["assets"].PHOTO_ORIGINAL)
    assert dom["assets"].delete(aid, b_pid) is False
    assert dom["assets"].get(aid, a_pid) is not None


def test_no_se_pueden_crear_tipos_reservados(client, dom):
    """Los tipos futuros existen en el vocabulario pero nada los produce. (PHOTO_STAGED dejó de ser
    reservado en E31: lo crea la aprobación humana, y hay tests de que un rechazo nunca lo crea.)"""
    pid = _prop(dom)
    with pytest.raises(dom["assets"].AssetError):
        dom["assets"].save_bytes(pid, dom["assets"].VIDEO, "x.mp4", b"\x00" * 64, "video/mp4")


# ===================================================================================================
# C — FLOORPLAN ADAPTER
# ===================================================================================================
def test_la_propiedad_crea_su_caso_sin_duplicar_el_motor(client, dom):
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    cid = dom["floorplan"].ensure_case(pid)
    assert cid == dom["floorplan"].ensure_case(pid)                    # idempotente
    from webapp import store
    assert store.q1("SELECT case_id FROM cases WHERE case_id=?", (cid,)) is not None
    assert dom["properties"].get(pid)["floorplan_case_id"] == cid


def test_sin_plano_no_hay_caso(client, dom):
    with pytest.raises(dom["floorplan"].FloorplanError):
        dom["floorplan"].ensure_case(_prop(dom))


def test_un_caso_por_confirmar_pone_la_propiedad_en_revision_interna(client, dom):
    from webapp import store
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    cid = _case_listo(store, "c_pend", estado="NEEDS_CONFIRMATION")
    dom["properties"].link_case(pid, cid)
    v = dom["properties"].view(pid)
    assert v["status"] == "PREPARING"
    assert v["needs_internal_review"] is True
    assert v["customer_label"] == "Estamos preparando la planta"
    assert pid in [x["property"]["property_id"] for x in dom["properties"].needing_review()]


def test_un_caso_listo_habilita_el_plano_comercial(client, dom):
    from webapp import store
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    dom["properties"].link_case(pid, _case_listo(store, "c_ok"))
    v = dom["properties"].view(pid)
    assert v["status"] == "FLOORPLAN_READY" and v["needs_internal_review"] is False


def test_el_adaptador_no_autoconfirma_ni_falsea_ready(client, dom):
    """§10 — un caso a medias NO produce plano comercial, y nadie toca su artefacto."""
    from webapp import store
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    cid = _case_listo(store, "c_medias", estado="NEEDS_CONFIRMATION")
    dom["properties"].link_case(pid, cid)
    antes = open(os.path.join(store.case_dir(cid), "outputs", "floorplate.json"),
                 encoding="utf-8").read()
    assert dom["floorplan"].publish_commercial_floorplan(pid) is None
    assert open(os.path.join(store.case_dir(cid), "outputs", "floorplate.json"),
                encoding="utf-8").read() == antes
    assert store.q1("SELECT status FROM cases WHERE case_id=?", (cid,))["status"] == "NEEDS_CONFIRMATION"


def test_el_dominio_de_producto_no_importa_el_solver(client):
    """§3/§28 — la capa comercial orquesta el motor; no lo ejecuta en proceso ni lo copia."""
    import ast
    import pathlib
    prohibidos = ("ortools", "escalimetro.layout.e06.freeplace", "escalimetro.layout.solver",
                  "escalimetro.layout.e05.bands", "escalimetro.layout.scoring",
                  "escalimetro.layout.e07.strategies")
    for py in pathlib.Path(ROOT, "webapp", "domain").rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for m in mods:
                assert not any(m.startswith(p) for p in prohibidos), f"{py.name} importa {m}"


# ===================================================================================================
# D — OUTPUTS
# ===================================================================================================
def test_el_plano_comercial_no_es_la_alternativa_a(client, dom):
    """§11 — son dos objetos distintos y el manifiesto los separa."""
    from webapp.domain import assets as A
    assert A.FLOORPLAN_COMMERCIAL != A.LAYOUT_RENDER
    man_keys = ("floorplan_commercial", "layouts")
    pid = _prop(dom)
    man = dom["packs"].build_manifest(pid)
    assert all(k in man for k in man_keys)
    assert man["floorplan_commercial"] is None and man["layouts"] == []


def test_los_layouts_publicados_llevan_su_procedencia(client, dom):
    """§21 — un output huérfano no sirve: tiene que saber de dónde viene."""
    from webapp import store
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    cid = _case_listo(store, "c_lay")
    dom["properties"].link_case(pid, cid)
    store.ex("INSERT INTO briefs(brief_id,case_id,name,headcount,workstations,rooms,brief_sha256,"
             "created_at) VALUES ('b','c_lay','b',10,5,'[]','sha','t')")
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,engine_commit,created_at) "
             "VALUES ('r1','c_lay','b','DONE','commit123','t')")
    store.ex("INSERT INTO alternatives(run_id,alt,name,status,layout_sha256) "
             "VALUES ('r1','A','EFICIENTE','FIT','sha_a')")
    from webapp import engine
    d = os.path.join(engine.run_dir(cid, "r1"), "alternatives", "A")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "layout_commercial.png"), "wb") as fh:
        fh.write(_png())
    ids = dom["floorplan"].publish_layouts(pid)
    assert len(ids) == 1
    m = store.js(dom["assets"].get(ids[0], pid)["metadata"], {})
    for campo in ("alt", "case_id", "run_id", "brief_id", "engine_commit", "layout_sha256"):
        assert m.get(campo), f"falta procedencia: {campo}"
    assert dom["properties"].view(pid)["status"] == "LAYOUTS_READY"


def test_no_se_sirve_un_layout_de_otro_caso(client, dom):
    from webapp import store
    pid = _prop(dom)
    dom["properties"].link_case(pid, _case_listo(store, "c_mio"))
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('c_otro','O','a.png','a.png','image/png','t','READY','DEVELOPMENT')")
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,created_at) "
             "VALUES ('r_otro','c_otro','b','DONE','t')")
    assert dom["floorplan"].layout_asset_path(pid, "r_otro", "A") is None


# ===================================================================================================
# E — CONTRATO VISUAL
# ===================================================================================================
def test_el_proveedor_visual_falla_explicitamente(dom):
    v = dom["visual"]
    p = v.get_provider()
    assert p.available() is False
    with pytest.raises(v.ProviderNotConfigured):
        p.stage_photo(v.StagingRequest("p_1", "a_1"))


def test_el_contrato_declara_invariantes_y_editables(dom):
    v = dom["visual"]
    req = v.StagingRequest("p_1", "a_1")
    assert "perspective" in req.must_preserve and "windows" in req.must_preserve
    assert "furniture" in req.may_edit
    assert "windows" not in req.may_edit
    assert v.StagingResult("a_2", "x", "m", None, None, None, req.to_dict()).invariants_verified is None


def test_el_estado_visual_no_promete_lo_que_no_existe(dom):
    st = dom["visual"].staging_status()
    assert st["available"] is False and st["status"] == "not_generated"


# ===================================================================================================
# F — PACK
# ===================================================================================================
def test_el_manifiesto_declara_pendientes_las_imagenes_ambientadas(client, dom):
    pid = _prop(dom)
    man = dom["packs"].build_manifest(pid)
    assert man["photos_staged"] == [] and man["before_after"] == [] and man["video"] == []
    assert man["visuals_status"]["status"] in ("not_generated", "not_requested")
    assert man["visuals_status"]["status"] != "approved"
    assert man["schema_version"] == "marketing_pack_v1"


def test_el_export_contiene_lo_que_existe_y_solo_eso(client, dom):
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    _subir(dom, pid, dom["assets"].PHOTO_ORIGINAL, "f1.png")
    _subir(dom, pid, dom["assets"].PHOTO_ORIGINAL, "f2.png")
    # E31 §21 — incompleto y sin motivo: NO se exporta, y dice exactamente qué falta
    with pytest.raises(dom["packs"].PackNotReady) as e:
        dom["packs"].export_zip(pid)
    assert "imagen ambientada" in str(e.value)
    assert dom["properties"].view(pid)["status"] != "PACK_READY"
    _pack_exportable(dom, pid)
    res = dom["packs"].export_zip(pid)
    z = dom["assets"].get(res["asset_id"], pid)
    with zipfile.ZipFile(dom["assets"].path_of(z)) as zf:
        nombres = sorted(zf.namelist())
        man = json.loads(zf.read("manifest.json"))
    assert "manifest.json" in nombres
    assert any(n.startswith("floorplan/plano_original") for n in nombres)
    assert len([n for n in nombres if n.startswith("photos_original/")]) == 2
    assert not any("staged" in n for n in nombres)                 # nada inventado
    assert man["visuals_status"]["status"] != "approved"
    assert man["readiness"]["state"] == "DEGRADED" and man["readiness"]["override_reason"]
    assert dom["properties"].view(pid)["status"] == "PACK_READY"


def test_el_manifiesto_no_filtra_rutas_del_servidor(client, dom):
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    texto = json.dumps(dom["packs"].build_manifest(pid))
    from webapp import store
    assert store.DATA_DIR not in texto and "/properties/" not in texto


def test_el_zip_no_contiene_rutas_que_escapen(client, dom):
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].PHOTO_ORIGINAL, "../../evil.png")
    _pack_exportable(dom, pid)
    res = dom["packs"].export_zip(pid)
    z = dom["assets"].get(res["asset_id"], pid)
    with zipfile.ZipFile(dom["assets"].path_of(z)) as zf:
        for n in zf.namelist():
            assert not n.startswith("/") and ".." not in n


def test_no_se_descarga_el_pack_de_otra_propiedad(client, dom):
    a_pid, b_pid = _prop(dom, "A"), _prop(dom, "B")
    _subir(dom, a_pid, dom["assets"].PHOTO_ORIGINAL)
    _pack_exportable(dom, a_pid)
    dom["packs"].export_zip(a_pid)
    assert client.get(f"/properties/{a_pid}/pack.zip").status_code == 200
    assert client.get(f"/properties/{b_pid}/pack.zip").status_code == 404


# ===================================================================================================
# G — SUPERFICIE DE CLIENTE
# ===================================================================================================
VOCABULARIO_INTERNO = ("shell", "floorplate", "requires_confirmation", "primary_entrance",
                       "ready_for_layout", "CP-SAT", "px/m", "case_id", "run_id", "traceback",
                       "geometry_ready", "columns_ready", "daylight_ready", "shell_adapter")


def test_el_cliente_no_ve_vocabulario_interno(client, dom):
    from webapp import store
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    dom["properties"].link_case(pid, _case_listo(store, "c_cx", estado="NEEDS_CONFIRMATION"))
    for url in ("/properties/", "/properties/new", f"/properties/{pid}"):
        html = client.get(url).get_data(as_text=True)
        for palabra in VOCABULARIO_INTERNO:
            assert palabra not in html, f"{url} muestra «{palabra}»"


def test_el_cliente_no_recibe_enlaces_a_la_interfaz_interna(client, dom):
    pid = _prop(dom)
    html = client.get(f"/properties/{pid}").get_data(as_text=True)
    for ruta in ('href="/case/', 'href="/run/', 'href="/review'):
        assert ruta not in html


def test_un_fallo_tecnico_no_le_muestra_un_traceback_al_cliente(client, dom):
    from webapp import store
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    dom["properties"].link_case(pid, _case_listo(store, "c_roto", estado="FAILED"))
    v = dom["properties"].view(pid)
    assert v["status"] == "BLOCKED"
    assert v["customer_label"] == "Necesitamos revisar esta propiedad"
    html = client.get(f"/properties/{pid}").get_data(as_text=True)
    assert "Traceback" not in html and "FAILED" not in html


def test_la_cola_interna_existe_y_enlaza_al_caso_tecnico(client, dom):
    from webapp import store
    pid = _prop(dom)
    _subir(dom, pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png")
    dom["properties"].link_case(pid, _case_listo(store, "c_cola", estado="NEEDS_CONFIRMATION"))
    html = client.get("/review").get_data(as_text=True)
    assert "c_cola" in html and "/case/c_cola" in html


def test_una_propiedad_inexistente_da_404(client):
    assert client.get("/properties/p_noexiste").status_code == 404
    assert client.get("/properties/p_noexiste/pack.zip").status_code == 404
    assert client.post("/properties/p_noexiste/assets").status_code == 404


# ===================================================================================================
# H — REGRESIÓN
# ===================================================================================================
def test_la_app_interna_de_e273_sigue_respondiendo(client):
    for url in ("/", "/healthz", "/review"):
        assert client.get(url).status_code == 200


def test_el_motor_no_fue_tocado():
    """§28 — el hash del motor no se mueve por E28: nada bajo src/ cambió."""
    import subprocess
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"E28 tocó el motor: {out.stdout}"
