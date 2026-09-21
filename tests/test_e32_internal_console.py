"""E32 §28 — tests de CONTRATO de la consola interna.

Lo que se protege acá no es que las páginas abran, sino las promesas que la consola hace:

  · el avance de una propiedad SALE DE HECHOS, no de casillas que alguien marca;
  · la preparación del piloto se ve sin exponer una sola credencial;
  · un candidato experimental no se convierte en entregable por haber sido aprobado;
  · aprobar un proveedor es una decisión humana con evidencia, nunca una consecuencia de tener
    una clave en el entorno;
  · las notas internas no salen en ningún pack ni propuesta;
  · lo que la vista previa del pack promete es lo que el ZIP trae.
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
           "webapp.domain.visual", "webapp.domain.pilot", "webapp.providers.base",
           "webapp.providers.gemini", "webapp.providers.openai_images", "webapp.providers.bfl",
           "webapp.providers", "webapp.domain.staging", "webapp.domain.packs",
           "webapp.domain.lab", "webapp.benchmark", "webapp.customer", "webapp.staging_ui",
           "webapp.lab", "webapp.app")
SECRETS = ("GEMINI_API_KEY", "OPENAI_API_KEY", "BFL_API_KEY", "ESCALIMETRO_STAGING_PROVIDER")


def _png(w: int = 64, h: int = 48, color: bytes = b"\x80\x90\xa0") -> bytes:
    raw = b"".join(b"\x00" + color * w for _ in range(h))

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
    for v in SECRETS:
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
    from webapp import benchmark, providers
    from webapp.domain import (assets, entitlements, fits, lab, packs, pilot, properties, staging,
                               visual)
    return {"assets": assets, "entitlements": entitlements, "fits": fits, "lab": lab,
            "packs": packs, "pilot": pilot, "properties": properties, "staging": staging,
            "visual": visual, "providers": providers, "benchmark": benchmark}


class FakeProvider:
    name = "fake"
    model = "fake-1"
    n = 0

    def available(self):
        return True

    def stage_photo(self, req, image_bytes=b"", mime_type="image/png"):
        from webapp.domain import visual
        FakeProvider.n += 1
        return visual.ProviderOutput(_png(64, 48, bytes([0x20 + FakeProvider.n, 0x30, 0x40])),
                                     "image/png", "fake", "fake-1", 900, 0.05, "list_price",
                                     None, {})


@pytest.fixture()
def fake(dom):
    dom["providers"]._FACTORIES["fake"] = FakeProvider
    FakeProvider.n = 0
    return FakeProvider


def _aprobar(dom, provider="fake", model="fake-1", passes=True):
    return dom["pilot"].approve(provider, model, {"gate": {"passes": passes}, "sample_size": 12},
                                reviewer="tests")


def _prop(dom, client, titulo="Oficina 403"):
    r = client.post("/lab/new", data={"title": titulo, "city": "Santiago",
                                      "published_area_m2": "543"}, follow_redirects=True)
    import re
    return re.search(rb"p_[0-9a-f]{12}", r.data).group().decode()


def _foto(dom, pid, nombre="sala.png"):
    from werkzeug.datastructures import FileStorage
    return dom["assets"].save_upload(
        pid, FileStorage(stream=io.BytesIO(_png()), filename=nombre),
        dom["assets"].PHOTO_ORIGINAL)


def _material_base(dom, pid):
    """Lo que promete el pack, sin correr el motor."""
    from werkzeug.datastructures import FileStorage
    dom["assets"].save_upload(pid, FileStorage(stream=io.BytesIO(_png()), filename="plano.png"),
                              dom["assets"].FLOORPLAN_ORIGINAL)
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_COMMERCIAL, "pc.png", _png(), "image/png")
    dom["assets"].save_bytes(pid, dom["assets"].LAYOUT_RENDER, "alternativa_A.png", _png(),
                             "image/png", metadata={"alt": "A", "representative": True,
                                                    "selected_by": "first_fit"})


# ===================================================================================================
# A — LA CONSOLA
# ===================================================================================================
def test_todas_las_pantallas_exigen_autenticacion(tmp_path, monkeypatch):
    """§21 — interna quiere decir interna. Sin DEV y con contraseña, nada se abre sin credencial."""
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "secreta")
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for m in MODULOS:
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    c = create_app().test_client()
    for url in ("/lab/", "/lab/new", "/lab/config", "/lab/benchmark", "/lab/feedback.json"):
        assert c.get(url).status_code == 401, url


def test_la_consola_abre_en_todas_sus_secciones(client, dom, fake):
    pid = _prop(dom, client)
    dom["entitlements"].set_mode("PRO")
    fid = dom["fits"].create_prospect(pid, "Falabella", 40)
    urls = ["/lab/", "/lab/new", "/lab/config", "/lab/benchmark", "/lab/feedback.json"]
    urls += [f"/lab/p/{pid}{t}" for t in ("", "/plano", "/fotos", "/material", "/prospectos",
                                          "/pack", "/actividad")]
    urls.append(f"/lab/p/{pid}/prospectos/{fid}")
    for u in urls:
        assert client.get(u).status_code == 200, u


def test_una_propiedad_inexistente_da_404(client, dom):
    for t in ("", "/plano", "/fotos", "/material", "/pack", "/actividad"):
        assert client.get(f"/lab/p/p_noexiste{t}").status_code == 404


# ===================================================================================================
# B — AVANCE DERIVADO DE HECHOS (§6)
# ===================================================================================================
def test_el_avance_sale_de_hechos_no_de_casillas(client, dom, fake):
    """Ningún paso se puede marcar a mano: cada uno mira un archivo o una fila."""
    pid = _prop(dom, client)
    ps = {s["key"]: s for s in dom["lab"].progress(pid)}
    assert ps["data"]["done"] and not ps["floorplan"]["done"] and not ps["photos"]["done"]
    _foto(dom, pid)
    ps = {s["key"]: s for s in dom["lab"].progress(pid)}
    assert ps["photos"]["done"] and not ps["hero"]["done"]
    dom["staging"].set_hero(pid, _foto(dom, pid, "b.png"))
    assert {s["key"]: s for s in dom["lab"].progress(pid)}["hero"]["done"]
    # no existe ninguna ruta para declarar un paso como hecho
    rutas = [r.rule for r in client.application.url_map.iter_rules() if r.rule.startswith("/lab")]
    assert not any(x in r for r in rutas for x in ("/paso", "/step", "/progress", "/avance"))


def test_el_avance_refleja_que_falta_la_ambientacion(client, dom, fake):
    pid = _prop(dom, client)
    _material_base(dom, pid)
    dom["staging"].set_hero(pid, _foto(dom, pid))
    ps = {s["key"]: s for s in dom["lab"].progress(pid)}
    assert ps["commercial"]["done"] and ps["layout"]["done"]
    assert not ps["staging"]["done"] and not ps["pack"]["done"]
    assert ps["staging"]["blocked"] is True          # sin proveedor aprobado


def test_la_portada_cuenta_lo_que_hay(client, dom, fake):
    pid = _prop(dom, client)
    o = dom["lab"].overview()
    assert o["properties"] == 1 and o["ready"] == 0
    assert dom["lab"].rows()[0]["p"]["property_id"] == pid


# ===================================================================================================
# C — PREPARACIÓN Y SECRETOS (§A, §24)
# ===================================================================================================
def test_el_panel_de_preparacion_no_expone_ninguna_credencial(client, dom, monkeypatch):
    """§A — booleanos y nombres de variable. Ni el valor, ni un fragmento, ni la longitud."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRETO-NO-DEBE-SALIR-1234567890")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-SECRETO-TAMPOCO-0987654321")
    prep = dom["pilot"].readiness()
    texto = json.dumps(prep)
    assert "SECRETO" not in texto and "sk-" not in texto and "gm-" not in texto
    assert any(p["name"] == "openai" and p["credential"] is True for p in prep["providers"])
    assert all("env" in p and p["env"].endswith("_API_KEY") for p in prep["providers"])
    for url in ("/lab/config", "/lab/benchmark"):
        html = client.get(url).get_data(as_text=True)
        assert "SECRETO" not in html
        assert "OPENAI_API_KEY" in html          # el NOMBRE sí, para saber qué configurar


def test_el_panel_dice_exactamente_que_falta(client, dom):
    b = dom["pilot"].readiness()["blockers"]
    assert any("credencial de openai" in x for x in b)
    assert any("credencial de gemini" in x for x in b)
    assert any("fotos reales" in x for x in b)
    assert any("ningún proveedor aprobado" in x for x in b)


def test_bfl_esta_excluido_del_piloto_por_licencia(client, dom):
    prep = dom["pilot"].readiness()
    bfl = next(p for p in prep["providers"] if p["name"] == "bfl")
    assert bfl["excluded"] and "licencia" in bfl["excluded_reason"].lower()
    assert "bfl" not in dom["pilot"].PILOT_PROVIDERS
    with pytest.raises(dom["pilot"].ApprovalError):
        dom["pilot"].approve("bfl", "flux-kontext-pro", {"gate": {"passes": True}})


def test_rechequear_entorno_no_revela_nada(client, dom, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-OTRO-SECRETO-XYZ")
    assert client.post("/lab/config/recheck").status_code == 302
    ev = dom["pilot"].events("ENV_RECHECK")
    assert ev and "OTRO-SECRETO" not in json.dumps(ev)
    assert ev[0]["detail_obj"]["credentials"][0]["credential"] in (True, False)


# ===================================================================================================
# D — DATASET DEL BAKE-OFF (§B)
# ===================================================================================================
def test_se_arma_el_dataset_desde_la_consola(client, dom):
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    r = client.post("/lab/benchmark/foto", data={"asset_id": foto, "property_id": pid,
                                                 "tags": ["WINDOWS", "COLUMNS"],
                                                 "reason": "gran angular"})
    assert r.status_code == 302
    ds = dom["benchmark"].dataset()
    assert len(ds["photos"]) == 1
    assert ds["photos"][0]["difficult_features"] == ["COLUMNS", "WINDOWS"]
    assert ds["photos"][0]["inclusion_reason"] == "gran angular"
    assert ds["status"] == "INSUFFICIENT_PHOTOS"
    assert os.path.exists(dom["benchmark"].manifest_path())
    client.post("/lab/benchmark/foto", data={"asset_id": foto, "action": "remove"})
    assert dom["benchmark"].dataset()["photos"] == []


def test_el_dataset_avisa_cuando_no_es_diverso(client, dom):
    pid = _prop(dom, client)
    for i in range(9):
        dom["benchmark"].add_photo(_foto(dom, pid, f"f{i}.png"), pid, ["WINDOWS"], "")
    errs = dom["benchmark"].validate_manifest(dom["benchmark"].dataset())
    assert not any("8 fotos" in e for e in errs)
    assert any("3 espacios" in e for e in errs)


def test_no_se_inventan_rasgos_dificiles(client, dom):
    pid = _prop(dom, client)
    with pytest.raises(ValueError):
        dom["benchmark"].add_photo(_foto(dom, pid), pid, ["MAGIA"], "")


def test_una_foto_de_otra_propiedad_no_entra_al_dataset(client, dom):
    a, b = _prop(dom, client, "A"), _prop(dom, client, "B")
    with pytest.raises(ValueError):
        dom["benchmark"].add_photo(_foto(dom, a), b, [], "")


# ===================================================================================================
# E — SMOKE Y BAKE-OFF (§C, §D)
# ===================================================================================================
def test_sin_credencial_no_se_puede_probar_un_proveedor(client, dom):
    pid = _prop(dom, client)
    dom["benchmark"].add_photo(_foto(dom, pid), pid, [], "")
    r = client.post("/lab/benchmark/smoke/openai")
    assert r.status_code == 400 and "OPENAI_API_KEY" in r.get_data(as_text=True)


def test_sin_fotos_no_se_puede_probar_un_proveedor(client, dom, monkeypatch, fake):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    r = client.post("/lab/benchmark/smoke/openai")
    assert r.status_code == 400 and "foto real" in r.get_data(as_text=True)


def test_el_smoke_no_aprueba_ni_selecciona_ni_publica(client, dom, fake):
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    dom["benchmark"].add_photo(foto, pid, [], "")
    res = dom["staging"].smoke_test("fake", foto, pid)
    assert res["ok"] is True
    a = dom["staging"].get(res["attempt_id"])
    assert a["purpose"] == "SMOKE" and a["experimental"] == 1
    assert dom["pilot"].approved_provider_name() is None
    dom["staging"].review(res["attempt_id"], "PASS", 5, "APPROVE")
    assert dom["assets"].list_of_kind(pid, dom["assets"].PHOTO_STAGED) == []
    assert dom["pilot"].last_smoke("fake")["ok"] is True


def test_el_bakeoff_exige_confirmar_el_gasto(client, dom, fake):
    r = client.post("/lab/benchmark/run", data={"providers": ["fake"], "runs": "2"})
    assert r.status_code == 400 and "gasto" in r.get_data(as_text=True)


def test_el_bakeoff_exige_dos_proveedores(client, dom, fake):
    for n in ("A", "B", "C"):
        pid = _prop(dom, client, n)
        for i in range(3):
            dom["benchmark"].add_photo(_foto(dom, pid, f"{n}{i}.png"), pid, [], "")
    assert dom["benchmark"].validate_manifest(dom["benchmark"].dataset()) == []
    with pytest.raises(ValueError, match="dos proveedores"):
        dom["benchmark"].start(["fake"], 2)


def test_la_estimacion_multiplica_bien(client, dom, fake):
    e = dom["benchmark"].estimate(["fake"], 10, 2)
    assert e["attempts"] == 20 and e["basis"] == "list_price"


def test_el_bakeoff_encola_y_no_publica_nada(client, dom, fake):
    """§D/§I — cada intento cuenta, y ninguno es entregable."""
    dom["providers"]._FACTORIES["fake2"] = type("F2", (FakeProvider,), {"name": "fake2",
                                                                       "model": "f2"})
    pid = _prop(dom, client)
    for i in range(8):
        dom["benchmark"].add_photo(_foto(dom, pid, f"f{i}.png"), pid, [], "")
    pid2, pid3 = _prop(dom, client, "B"), _prop(dom, client, "C")
    dom["benchmark"].add_photo(_foto(dom, pid2), pid2, [], "")
    dom["benchmark"].add_photo(_foto(dom, pid3), pid3, [], "")
    res = dom["benchmark"].start(["fake", "fake2"], 2)
    assert res["planned"] == 10 * 2 * 2
    prog = dom["benchmark"].progress(res["benchmark_id"])
    assert prog["total"] == 40
    filas = dom["benchmark"].attempts_of(res["benchmark_id"])
    assert all(a["purpose"] == "BENCHMARK" and a["experimental"] == 1 for a in filas)
    assert len({a["prompt_hash"] for a in filas}) == 1        # misma petición para todos


# ===================================================================================================
# F — LA DECISIÓN ES HUMANA (§H)
# ===================================================================================================
def test_tener_la_clave_no_selecciona_al_proveedor(client, dom, monkeypatch):
    """§H, literal: "Key presence must NEVER select the provider"."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("ESCALIMETRO_STAGING_PROVIDER", "openai")
    assert dom["pilot"].approved_provider_name() is None
    assert dom["visual"].get_provider().name == "not_configured"
    assert dom["pilot"].readiness()["approved_label"] == "NINGUNO"


def test_no_se_aprueba_un_proveedor_que_no_cumple_la_compuerta(client, dom, fake):
    with pytest.raises(dom["pilot"].ApprovalError):
        dom["pilot"].approve("fake", "fake-1", {"gate": {"passes": False}})
    a = dom["pilot"].approve("fake", "fake-1", {"gate": {"passes": False}},
                             override_reason="lo necesito para una demo")
    assert a["gate_passed"] is False and a["override_reason"]
    assert dom["pilot"].readiness()["approved"]["override_reason"]


def test_aprobar_guarda_la_evidencia(client, dom, fake):
    a = _aprobar(dom)
    assert a["evidence"]["sample_size"] == 12 and a["provider"] == "fake"
    assert dom["pilot"].events("PROVIDER_APPROVED")
    dom["pilot"].revoke("prueba")
    assert dom["pilot"].approved_provider_name() is None


# ===================================================================================================
# G — LO EXPERIMENTAL NO SE FILTRA AL PRODUCTO (§I, §J)
# ===================================================================================================
def test_sin_proveedor_aprobado_el_producto_lo_dice_con_esas_palabras(client, dom, fake):
    pid = _prop(dom, client)
    dom["staging"].set_hero(pid, _foto(dom, pid))
    st = dom["staging"].state(pid)
    assert st["state"] == "STAGING_PROVIDER_NOT_APPROVED"
    html = client.get(f"/lab/p/{pid}/material").get_data(as_text=True)
    assert "STAGING PROVIDER NOT YET APPROVED" in html


def test_un_candidato_experimental_aprobado_no_llega_al_cliente(client, dom, fake):
    """El corazón de §I: aprobar un experimental no lo convierte en entregable."""
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    dom["staging"].set_hero(pid, foto)
    a = dom["staging"].run_attempt(
        dom["staging"].create_attempt(pid, foto, "CONTEMPORARY", provider_name="fake"))
    assert a["experimental"] == 1
    dom["staging"].review(a["attempt_id"], "PASS", 5, "APPROVE")
    assert dom["assets"].list_of_kind(pid, dom["assets"].PHOTO_STAGED) == []
    assert dom["staging"].get(a["attempt_id"])["output_asset_id"] is None
    assert dom["staging"].state(pid)["state"] != "APPROVED"
    _material_base(dom, pid)
    with pytest.raises(dom["packs"].PackNotReady):
        dom["packs"].export_zip(pid)


def test_tras_aprobar_el_producto_usa_ese_proveedor_sin_preguntar(client, dom, fake):
    """§J — el flujo normal deja de preguntar qué proveedor usar."""
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    dom["staging"].set_hero(pid, foto)
    _material_base(dom, pid)
    _aprobar(dom)
    assert dom["visual"].get_provider().name == "fake"
    a = dom["staging"].run_attempt(dom["staging"].create_attempt(pid, foto, "CONTEMPORARY"))
    assert a["provider"] == "fake" and a["experimental"] == 0 and a["purpose"] == "PRODUCT"
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    assert len(dom["assets"].list_of_kind(pid, dom["assets"].PHOTO_STAGED)) == 1
    assert dom["packs"].readiness(pid)["state"] == "READY"
    # el cliente nunca elige proveedor
    html = client.get(f"/properties/{pid}").get_data(as_text=True).lower()
    for palabra in ("proveedor", "provider", "fake-1", "openai", "gemini"):
        assert palabra not in html, palabra


def test_lo_experimental_de_antes_no_revive_al_aprobar(client, dom, fake):
    """Lo que se generó antes de la decisión se generó antes de la decisión."""
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    dom["staging"].set_hero(pid, foto)
    viejo = dom["staging"].run_attempt(
        dom["staging"].create_attempt(pid, foto, "CONTEMPORARY", provider_name="fake"))
    _aprobar(dom)
    assert dom["staging"].get(viejo["attempt_id"])["experimental"] == 1
    with pytest.raises(dom["staging"].ReviewError):
        dom["staging"]._publish(viejo["attempt_id"])


# ===================================================================================================
# H — PACK Y PROSPECTOS DESDE LA CONSOLA
# ===================================================================================================
def test_la_vista_previa_del_pack_no_contradice_al_zip(client, dom, fake):
    """§25 — «No permitir que "Pack listo" contradiga su contenido»."""
    from webapp import lab as labmod
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    dom["staging"].set_hero(pid, foto)
    _material_base(dom, pid)
    _aprobar(dom)
    a = dom["staging"].run_attempt(dom["staging"].create_attempt(pid, foto, "CONTEMPORARY"))
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    with client.application.test_request_context():
        previa = {c["n"] for c in labmod._contenido(pid) if c["ok"]}
    z = dom["packs"].export_zip(pid)
    with zipfile.ZipFile(dom["assets"].path_of(dom["assets"].get(z["asset_id"], pid))) as zf:
        nombres = zf.namelist()
    if "Imagen ambientada aprobada" in previa:
        assert any("hero_ambientada" in n for n in nombres)
    if "Alternativa representativa" in previa:
        assert any(n.startswith("layouts/") for n in nombres)
    if "Antes / después" in previa:
        assert any("antes_despues" in n for n in nombres)
    assert "propuesta.html" in nombres and "manifest.json" in nombres


def test_el_pack_no_se_arma_incompleto_desde_la_consola(client, dom, fake):
    pid = _prop(dom, client)
    _material_base(dom, pid)
    r = client.post(f"/lab/p/{pid}/pack")
    assert r.status_code == 400 and "imagen ambientada" in r.get_data(as_text=True)


def test_los_prospectos_no_se_pisan_entre_si(client, dom, fake):
    dom["entitlements"].set_mode("PRO")
    pid = _prop(dom, client)
    a = client.post(f"/lab/p/{pid}/prospectos", data={"prospect_name": "Falabella",
                                                      "headcount": "40"}, follow_redirects=True)
    b = client.post(f"/lab/p/{pid}/prospectos", data={"prospect_name": "Cencosud",
                                                      "headcount": "25"}, follow_redirects=True)
    assert a.status_code == 200 and b.status_code == 200
    etiquetas = {f["label"] for f in dom["fits"].list_for(pid, include_base=False)}
    assert etiquetas == {"Falabella", "Cencosud"}


def test_en_one_off_la_consola_no_deja_crear_prospectos(client, dom, fake):
    pid = _prop(dom, client)
    r = client.post(f"/lab/p/{pid}/prospectos", data={"prospect_name": "X", "headcount": "10"})
    assert r.status_code == 403


# ===================================================================================================
# I — NOTAS, VALORACIÓN Y LÍNEA DE TIEMPO (§15, §16, §17)
# ===================================================================================================
def test_las_notas_internas_no_salen_en_ningun_entregable(client, dom, fake):
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    dom["staging"].set_hero(pid, foto)
    _material_base(dom, pid)
    _aprobar(dom)
    a = dom["staging"].run_attempt(dom["staging"].create_attempt(pid, foto, "CONTEMPORARY"))
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE", notes="NOTA-DE-REVISION")
    dom["lab"].add_note(pid, "NOTA-DE-PRUEBA-INTERNA")
    z = dom["packs"].export_zip(pid)
    texto = json.dumps(z["manifest"])
    assert "NOTA-DE-PRUEBA-INTERNA" not in texto and "NOTA-DE-REVISION" not in texto
    with zipfile.ZipFile(dom["assets"].path_of(dom["assets"].get(z["asset_id"], pid))) as zf:
        todo = b"".join(zf.read(n) for n in zf.namelist() if not n.endswith(".png"))
    assert b"NOTA-DE-PRUEBA-INTERNA" not in todo and b"NOTA-DE-REVISION" not in todo
    cliente = client.get(f"/properties/{pid}").get_data(as_text=True)
    assert "NOTA-DE-PRUEBA-INTERNA" not in cliente
    # pero adentro sí se ven
    assert "NOTA-DE-PRUEBA-INTERNA" in client.get(f"/lab/p/{pid}/actividad").get_data(as_text=True)


def test_la_linea_de_tiempo_se_deriva_de_los_artefactos(client, dom, fake):
    pid = _prop(dom, client)
    _foto(dom, pid)
    linea = dom["lab"].timeline(pid)
    tipos = {e["kind"] for e in linea}
    assert "created" in tipos and "photo_original" in tipos
    assert linea == sorted(linea, key=lambda x: x["at"], reverse=True)
    # no hay tabla de eventos que mantener para esto
    from webapp import store
    assert store.q1("SELECT COUNT(*) n FROM lab_events")["n"] == 0


def test_la_valoracion_interna_se_guarda_y_se_exporta(client, dom, fake):
    pid = _prop(dom, client)
    client.post(f"/lab/p/{pid}/feedback", data={"value": "NEEDS_WORK"})
    assert dom["properties"].require(pid)["lab_feedback"] == "NEEDS_WORK"
    with pytest.raises(ValueError):
        dom["lab"].set_feedback(pid, "EXCELENTISIMO")
    dom["lab"].add_note(pid, "el pilar quedó mal detectado")
    exp = client.get("/lab/feedback.json").get_json()
    assert exp[0]["feedback"] == "NEEDS_WORK"
    assert exp[0]["notes"][0]["body"] == "el pilar quedó mal detectado"


def test_una_nota_vacia_se_rechaza(client, dom):
    pid = _prop(dom, client)
    assert client.post(f"/lab/p/{pid}/nota", data={"body": "   "}).status_code == 400


# ===================================================================================================
# J — REVISIÓN A CIEGAS (§F)
# ===================================================================================================
def test_la_revision_de_benchmark_es_a_ciegas(client, dom, fake):
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    aid = dom["staging"].create_attempt(pid, foto, "CONTEMPORARY", provider_name="fake",
                                        benchmark_id="bm_x", purpose="BENCHMARK")
    dom["staging"].run_attempt(aid)
    html = client.get(f"/staging/attempt/{aid}").get_data(as_text=True)
    assert "REVISIÓN A CIEGAS" in html
    assert "fake-1" not in html and "0.05" not in html
    dom["staging"].review(aid, "PASS", 4, "REJECT")
    html2 = client.get(f"/staging/attempt/{aid}").get_data(as_text=True)
    assert "fake-1" in html2                       # tras el veredicto sí se revela


def test_un_intento_de_producto_no_se_revisa_a_ciegas(client, dom, fake):
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    _aprobar(dom)
    a = dom["staging"].run_attempt(dom["staging"].create_attempt(pid, foto, "CONTEMPORARY"))
    html = client.get(f"/staging/attempt/{a['attempt_id']}").get_data(as_text=True)
    assert "REVISIÓN A CIEGAS" not in html and "fake-1" in html


def test_siguiente_sin_revisar_recorre_la_cola(client, dom, fake):
    pid = _prop(dom, client)
    foto = _foto(dom, pid)
    ids = []
    for i in range(2):
        aid = dom["staging"].create_attempt(pid, foto, "CONTEMPORARY", provider_name="fake",
                                            benchmark_id="bm_y", purpose="BENCHMARK")
        dom["staging"].run_attempt(aid)
        ids.append(aid)
    r = client.get("/lab/review/next")
    assert r.status_code == 302 and ids[0] in r.headers["Location"]
    r2 = client.get(f"/lab/review/next?after={ids[0]}")
    assert ids[1] in r2.headers["Location"]
    for aid in ids:
        dom["staging"].review(aid, "FAIL", None, "REJECT", ["window_changed"])
    assert "/staging/" in client.get("/lab/review/next").headers["Location"]


# ===================================================================================================
# K — REGRESIÓN
# ===================================================================================================
def test_las_superficies_anteriores_siguen_respondiendo(client):
    for url in ("/", "/healthz", "/review", "/settings", "/properties/", "/staging/",
                "/staging/benchmark", "/lab/"):
        assert client.get(url).status_code == 200, url


def test_el_motor_no_fue_tocado():
    import subprocess
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"E32 tocó el motor: {out.stdout}"


def test_el_dominio_no_conoce_a_los_proveedores_por_nombre(client):
    """`webapp/domain` los conoce por el protocolo y por el registro, nunca por import directo."""
    import ast
    base = os.path.join(ROOT, "webapp", "domain")
    for archivo in os.listdir(base):
        if not archivo.endswith(".py"):
            continue
        arbol = ast.parse(open(os.path.join(base, archivo), encoding="utf-8").read())
        for nodo in ast.walk(arbol):
            mods = ([a.name for a in nodo.names] if isinstance(nodo, ast.Import)
                    else [nodo.module or ""] if isinstance(nodo, ast.ImportFrom) else [])
            for m in mods:
                assert not m.startswith("ortools") and "layout.solver" not in m, f"{archivo}: {m}"
                assert not any(v in m for v in ("gemini", "openai_images", "providers.bfl")), \
                    f"{archivo} importa un adaptador: {m}"


def test_sin_proveedor_aprobado_el_pack_dice_que_falta_la_ambientacion(client, dom, fake):
    """Con plano y layout listos, lo único que falta es la ambientación: el estado tiene que
    decirlo. Decir PREPARING mandaría a mirar el paso equivocado."""
    pid = _prop(dom, client)
    _material_base(dom, pid)
    dom["staging"].set_hero(pid, _foto(dom, pid))
    listo = dom["packs"].readiness(pid)
    assert listo["state"] == "NEEDS_STAGING"
    assert listo["missing"] == ["imagen ambientada aprobada"]


def test_el_tablero_cuenta_la_ambientacion_bloqueada_como_pendiente(client, dom, fake):
    pid = _prop(dom, client)
    dom["staging"].set_hero(pid, _foto(dom, pid))
    assert dom["staging"].state(pid)["state"] == "STAGING_PROVIDER_NOT_APPROVED"
    assert dom["lab"].overview()["staging_pending"] == 1
