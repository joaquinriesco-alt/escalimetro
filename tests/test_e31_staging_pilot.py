"""E31 §31 — tests de CONTRATO del piloto de ambientación.

Lo que se protege: que ningún candidato llegue al cliente sin un humano que lo apruebe al lado de
la foto real; que la fidelidad sea una compuerta dura que la calidad no compensa; que un rechazo se
conserve y nunca se pise; que el pack de publicación no se declare completo cuando falta lo
prometido; que la clave de un proveedor no exista en ningún objeto serializable; y que el harness
del bake-off mida lo que dice medir — sin fingir que corrió.

Los adaptadores se prueban con TRANSPORTE GRABADO: se verifica la forma exacta de la petición, el
parseo de la respuesta y el manejo de errores. Eso es probar el adaptador; no es correr el
benchmark, y ningún test de este archivo pretende lo contrario.
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
           "webapp.domain.visual", "webapp.providers.base", "webapp.providers.gemini",
           "webapp.providers.openai_images", "webapp.providers.bfl", "webapp.providers",
           "webapp.domain.staging", "webapp.domain.packs", "webapp.benchmark",
           "webapp.customer", "webapp.staging_ui", "webapp.app")
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
    from webapp.domain import assets, entitlements, fits, packs, properties, staging, visual
    from webapp.providers import base, bfl, gemini, openai_images
    return {"assets": assets, "entitlements": entitlements, "fits": fits, "packs": packs,
            "properties": properties, "staging": staging, "visual": visual, "providers": providers,
            "base": base, "gemini": gemini, "openai": openai_images, "bfl": bfl,
            "benchmark": benchmark}


class FakeProvider:
    """Un proveedor que devuelve una imagen distinta cada vez y nunca sale de los tests."""
    name = "fake"
    model = "fake-1"
    calls = 0

    def available(self):
        return True

    def stage_photo(self, req, image_bytes=b"", mime_type="image/png"):
        FakeProvider.calls += 1
        assert "STRICTLY PRESERVE" in req.context["prompt"]
        tono = bytes([0x20 + FakeProvider.calls, 0x30, 0x40])
        from webapp.domain import visual
        return visual.ProviderOutput(_png(64, 48, tono), "image/png", "fake", "fake-1",
                                     1234, 0.05, "list_price", "7", {"ok": True})


class BrokenProvider(FakeProvider):
    name = "broken"

    def stage_photo(self, req, image_bytes=b"", mime_type="image/png"):
        raise RuntimeError("el proveedor explotó")


@pytest.fixture()
def fake(dom):
    """Registra el proveedor de prueba y lo APRUEBA.

    E32 §I cambió el contrato: desde que existe una decisión humana de proveedor, lo que produce un
    proveedor sin aprobar nace experimental y no puede publicarse. Estos tests hablan de la
    publicación, así que aprueban al de prueba — que es exactamente el paso que un operador tiene
    que dar hoy. El camino sin aprobar tiene sus propios tests en test_e32."""
    dom["providers"]._FACTORIES["fake"] = FakeProvider
    dom["providers"]._FACTORIES["broken"] = BrokenProvider
    FakeProvider.calls = 0
    from webapp.domain import pilot
    pilot.approve("fake", "fake-1", {"gate": {"passes": True}, "sample_size": 12},
                  reviewer="tests")
    return FakeProvider


def _prop_con_foto(dom, titulo="Oficina"):
    from werkzeug.datastructures import FileStorage
    pid = dom["properties"].create(titulo, "OFFICE", city="Santiago")
    foto = dom["assets"].save_upload(
        pid, FileStorage(stream=io.BytesIO(_png()), filename="oficina.png"), dom["assets"].PHOTO_ORIGINAL)
    dom["staging"].set_hero(pid, foto)
    return pid, foto


def _generado(dom, pid, foto, provider="fake", style="CONTEMPORARY", fit_id=None):
    aid = dom["staging"].create_attempt(pid, foto, style, fit_id=fit_id, provider_name=provider)
    return dom["staging"].run_attempt(aid)


def _con_plano_y_layout(dom, pid):
    """Lo demás que promete el pack base, sin correr el motor: el plano original que subió el
    cliente, el plano comercial y una alternativa representativa ya publicada."""
    from werkzeug.datastructures import FileStorage
    dom["assets"].save_upload(pid, FileStorage(stream=io.BytesIO(_png()), filename="plano.png"),
                              dom["assets"].FLOORPLAN_ORIGINAL)
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_COMMERCIAL, "plano_comercial.png",
                             _png(), "image/png")
    dom["assets"].save_bytes(pid, dom["assets"].LAYOUT_RENDER, "alternativa_A.png", _png(),
                             "image/png", metadata={"alt": "A", "representative": True,
                                                    "selected_by": "first_fit"})


# ===================================================================================================
# A — PROVEEDORES
# ===================================================================================================
def _grabar(dom, respuestas):
    """Instala un transporte que devuelve respuestas en orden y registra cada petición."""
    llamadas = []

    def transporte(method, url, headers, body, timeout):
        llamadas.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        st, cuerpo = respuestas.pop(0)
        return st, {}, cuerpo
    dom["base"].TRANSPORT = transporte
    return llamadas


def test_los_tres_adaptadores_obedecen_el_protocolo(dom):
    for mod, cls in ((dom["gemini"], "GeminiProvider"), (dom["openai"], "OpenAIImagesProvider"),
                     (dom["bfl"], "BFLProvider")):
        p = getattr(mod, cls)()
        assert p.name and p.model and p.available() is False
        with pytest.raises(dom["visual"].ProviderNotConfigured):
            p.stage_photo(dom["visual"].StagingRequest("p", "a"), _png())


def test_el_no_configurado_sigue_siendo_ruidoso(dom, monkeypatch):
    """Tener una clave no elige proveedor: sin aprobación humana, no hay proveedor de producto."""
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("ESCALIMETRO_STAGING_PROVIDER", "gemini")   # ya no elige nada
    p = dom["visual"].get_provider()
    assert p.name == "not_configured" and p.available() is False
    with pytest.raises(dom["visual"].ProviderNotConfigured):
        p.stage_photo(dom["visual"].StagingRequest("p", "a"))
    with pytest.raises(dom["visual"].ProviderNotConfigured):
        dom["providers"].resolve("proveedor_inventado")


def test_gemini_arma_la_peticion_y_lee_la_imagen(dom, monkeypatch):
    import base64
    monkeypatch.setenv("GEMINI_API_KEY", "gm-secreto-123")
    salida = _png(64, 48, b"\x01\x02\x03")
    llamadas = _grabar(dom, [(200, json.dumps({
        "candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {
            "mimeType": "image/png", "data": base64.b64encode(salida).decode()}}]},
            "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 1500, "candidatesTokenCount": 1120}}).encode())])
    req = dom["staging"].to_provider_request("p", "a", "CONTEMPORARY")
    out = dom["gemini"].GeminiProvider().stage_photo(req, _png(), "image/png")
    assert out.image_bytes == salida and out.provider == "gemini"
    assert out.cost_basis == "measured" and 0.05 < out.cost_usd < 0.09
    c = llamadas[0]
    assert "gemini-3.1-flash-image:generateContent" in c["url"]
    assert c["headers"]["x-goog-api-key"] == "gm-secreto-123"
    cuerpo = json.loads(c["body"])
    assert cuerpo["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert cuerpo["generationConfig"]["imageConfig"]["aspectRatio"] == "4:3"
    assert cuerpo["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/png"
    assert "gm-secreto-123" not in json.dumps(out.raw)


def test_openai_pide_fidelidad_alta_y_mide_el_costo(dom, monkeypatch):
    import base64
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secreto-456")
    salida = _png(64, 48, b"\x01\x02\x03")
    llamadas = _grabar(dom, [(200, json.dumps({
        "data": [{"b64_json": base64.b64encode(salida).decode()}],
        "usage": {"input_tokens": 1200, "output_tokens": 4160,
                  "input_tokens_details": {"image_tokens": 1000, "text_tokens": 200}}}).encode())])
    req = dom["staging"].to_provider_request("p", "a", "CONTEMPORARY")
    out = dom["openai"].OpenAIImagesProvider().stage_photo(req, _png(), "image/png")
    assert out.image_bytes == salida and out.cost_basis == "measured" and out.cost_usd > 0.1
    c = llamadas[0]
    assert c["url"].endswith("/v1/images/edits")
    assert c["headers"]["Authorization"] == "Bearer sk-secreto-456"
    assert b'name="input_fidelity"\r\n\r\nhigh' in c["body"]
    assert b'name="model"\r\n\r\ngpt-image-2.5-sunburst' in c["body"]
    assert b"STRICTLY PRESERVE" in c["body"]
    assert dom["openai"].size_for(4000, 3000) == "1536x1152"
    assert dom["openai"].size_for(100, 5000) == "auto"


def test_bfl_crea_sondea_y_descarga_sin_guardar_urls_firmadas(dom, monkeypatch):
    monkeypatch.setenv("BFL_API_KEY", "bfl-secreto-789")
    monkeypatch.setattr(dom["bfl"], "POLL_S", 0)
    salida = _png(64, 48, b"\x01\x02\x03")
    llamadas = _grabar(dom, [
        (200, json.dumps({"id": "t1", "polling_url": "https://api.bfl.ai/v1/get_result?id=t1"}).encode()),
        (200, json.dumps({"status": "Pending"}).encode()),
        (200, json.dumps({"status": "Ready", "result": {"sample": "https://signed.example/x.png",
                                                        "seed": 42}}).encode()),
        (200, salida)])
    req = dom["staging"].to_provider_request("p", "a", "CONTEMPORARY")
    out = dom["bfl"].BFLProvider().stage_photo(req, _png(), "image/png")
    assert out.image_bytes == salida and out.seed == "42"
    assert out.cost_usd == 0.04 and out.cost_basis == "list_price"
    assert llamadas[0]["url"].endswith("/v1/flux-kontext-pro")
    assert llamadas[0]["headers"]["x-key"] == "bfl-secreto-789"
    assert json.loads(llamadas[0]["body"])["prompt_upsampling"] is False
    assert "signed.example" not in json.dumps(out.raw) and "polling" not in json.dumps(out.raw)


def test_un_estado_terminal_de_bfl_es_error_no_imagen(dom, monkeypatch):
    monkeypatch.setenv("BFL_API_KEY", "k")
    monkeypatch.setattr(dom["bfl"], "POLL_S", 0)
    _grabar(dom, [(200, json.dumps({"id": "t", "polling_url": "https://x/p"}).encode()),
                  (200, json.dumps({"status": "Content Moderated"}).encode())])
    with pytest.raises(dom["base"].ProviderError):
        dom["bfl"].BFLProvider().stage_photo(
            dom["staging"].to_provider_request("p", "a", "CONTEMPORARY"), _png())


def test_un_error_del_proveedor_no_crea_candidato_ni_asset(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto, provider="broken")
    assert a["status"] == "FAILED" and "explotó" in a["error"]
    assert a["output_stored"] is None and a["output_asset_id"] is None
    assert dom["assets"].list_of_kind(pid, dom["assets"].PHOTO_STAGED) == []
    assert dom["staging"].state(pid)["approved_asset_id"] is None


def test_un_proveedor_que_devuelve_basura_falla(client, dom):
    class Basura(FakeProvider):
        name = "basura"

        def stage_photo(self, req, image_bytes=b"", mime_type="image/png"):
            from webapp.domain import visual
            return visual.ProviderOutput(b"<html>not an image</html>" * 20, "image/png", "basura",
                                         "x", 1, None, "unknown")
    dom["providers"]._FACTORIES["basura"] = Basura
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto, provider="basura")
    assert a["status"] == "FAILED" and "no es PNG" in a["error"]


def test_la_procedencia_del_intento_queda_guardada(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    assert a["status"] == "GENERATED"
    req = dom["staging"].canonical_request("CONTEMPORARY")
    assert a["request_version"] == "staging_request_v1" and a["prompt_hash"] == req["prompt_hash"]
    assert a["input_sha256"] == dom["assets"].get(foto, pid)["sha256"]
    assert a["output_sha256"] and a["model"] == "fake-1" and a["seed"] == "7"
    assert a["latency_ms"] == 1234 and a["pipeline_ms"] >= 0
    assert a["cost_usd"] == 0.05 and a["cost_basis"] == "list_price"
    assert os.path.exists(dom["staging"].candidate_path(a))


# ===================================================================================================
# B — INTENTOS
# ===================================================================================================
def test_crear_un_intento_exige_foto_propia_y_estilo_valido(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    otra, foto_ajena = _prop_con_foto(dom, "Otra")
    with pytest.raises(dom["staging"].StagingError):
        dom["staging"].create_attempt(pid, foto_ajena, "CONTEMPORARY", provider_name="fake")
    with pytest.raises(Exception):
        dom["staging"].create_attempt(pid, foto, "ART_DECO", provider_name="fake")
    aid = dom["staging"].create_attempt(pid, foto, "CONTEMPORARY", provider_name="fake")
    assert dom["staging"].get(aid)["status"] == "QUEUED"


def test_un_intento_rechazado_se_conserva(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "FAIL", None, "REJECT", ["window_changed"])
    r = dom["staging"].get(a["attempt_id"])
    assert r["review_status"] == "REJECTED" and r["fidelity_status"] == "FAIL"
    assert os.path.exists(dom["staging"].candidate_path(r))
    assert r["failure_reasons_list"] == ["window_changed"]


def test_reintentar_crea_otro_intento_y_no_pisa_el_anterior(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "FAIL", None, "REJECT", ["column_changed"])
    b = _generado(dom, pid, foto)
    assert b["attempt_id"] != a["attempt_id"]
    assert dom["staging"].candidate_path(a) != dom["staging"].candidate_path(b)
    assert os.path.exists(dom["staging"].candidate_path(dom["staging"].get(a["attempt_id"])))
    assert dom["staging"].get(a["attempt_id"])["output_sha256"] != b["output_sha256"]
    assert len(dom["staging"].list_for(pid, foto)) == 2


def test_un_intento_aprobado_enlaza_su_asset_publicado(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    r = dom["staging"].get(a["attempt_id"])
    assert r["review_status"] == "APPROVED" and r["output_asset_id"]
    pub = dom["assets"].get(r["output_asset_id"], pid)
    assert pub["kind"] == dom["assets"].PHOTO_STAGED and pub["source_asset_id"] == foto
    m = json.loads(pub["metadata"])
    assert m["attempt_id"] == a["attempt_id"] and m["provider"] == "fake"
    assert m["disclosure"] == dom["staging"].DISCLOSURE


def test_el_reinicio_marca_los_intentos_colgados_como_fallidos(client, dom, fake):
    from webapp import store
    pid, foto = _prop_con_foto(dom)
    aid = dom["staging"].create_attempt(pid, foto, "CONTEMPORARY", provider_name="fake")
    store.ex("UPDATE staging_attempts SET status='RUNNING' WHERE attempt_id=?", (aid,))
    # E33 movió esto de `init()` a `reset_orphans()`: sólo el arranque del SERVIDOR resetea lo que
    # quedó a medias. Cualquier otro proceso que abra la base ya no mata el trabajo en vuelo.
    store.reset_orphans()
    assert dom["staging"].get(aid)["status"] == "FAILED"


# ===================================================================================================
# C — QA HUMANO
# ===================================================================================================
def test_fidelidad_fail_no_se_puede_publicar(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    with pytest.raises(dom["staging"].ReviewError):
        dom["staging"].review(a["attempt_id"], "FAIL", None, "APPROVE", ["window_changed"])
    assert dom["assets"].list_of_kind(pid, dom["assets"].PHOTO_STAGED) == []
    assert dom["staging"].get(a["attempt_id"])["review_status"] == "PENDING"


def test_la_calidad_no_compensa_una_alucinacion(client, dom, fake):
    """§10 — un 5/5 precioso que corrió una ventana es FAIL, y la calidad ni se guarda."""
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    with pytest.raises(dom["staging"].ReviewError):
        dom["staging"].review(a["attempt_id"], "FAIL", 5, "APPROVE", ["window_changed"])
    dom["staging"].review(a["attempt_id"], "FAIL", 5, "REJECT", ["window_changed"])
    assert dom["staging"].get(a["attempt_id"])["quality_score"] is None


def test_fidelidad_fail_exige_motivo_y_pass_exige_calidad(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    with pytest.raises(dom["staging"].ReviewError):
        dom["staging"].review(a["attempt_id"], "FAIL", None, "REJECT", [])
    with pytest.raises(dom["staging"].ReviewError):
        dom["staging"].review(a["attempt_id"], "PASS", None, "APPROVE")
    with pytest.raises(dom["staging"].ReviewError):
        dom["staging"].review(a["attempt_id"], "PASS", 9, "APPROVE")


def test_los_avisos_automaticos_no_deciden_nada(client, dom, fake):
    """§12 — un diagnóstico sólo avisa; el intento sigue PENDING hasta que un humano lo mire."""
    from webapp import store
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    store.ex("UPDATE staging_attempts SET auto_warnings=? WHERE attempt_id=?",
             (json.dumps(["low_structural_similarity:0.10"]), a["attempt_id"]))
    r = dom["staging"].get(a["attempt_id"])
    assert r["auto_warnings_list"] and r["fidelity_status"] == "PENDING"
    assert r["review_status"] == "PENDING"
    assert "FIDELITY_VERIFIED" not in json.dumps(r)


def test_el_diagnostico_detecta_una_salida_corrupta_o_en_blanco(client, dom, tmp_path):
    o = tmp_path / "o.png"; o.write_bytes(_png(64, 48))
    b = tmp_path / "b.png"; b.write_bytes(_png(64, 48, b"\x80\x80\x80"))
    c = tmp_path / "c.png"; c.write_bytes(b"no soy una imagen")
    assert "blank_output" in dom["staging"].diagnostics(str(o), str(b))
    assert dom["staging"].diagnostics(str(o), str(c)) == ["corrupt_output"]


def test_solo_lo_aprobado_entra_al_pack(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    malo = _generado(dom, pid, foto)
    dom["staging"].review(malo["attempt_id"], "FAIL", None, "REJECT", ["view_changed"])
    bueno = _generado(dom, pid, foto)
    dom["staging"].review(bueno["attempt_id"], "PASS", 5, "APPROVE")
    _con_plano_y_layout(dom, pid)
    z = dom["packs"].export_zip(pid)
    sha_malo = dom["staging"].get(malo["attempt_id"])["output_sha256"]
    import hashlib
    with zipfile.ZipFile(dom["assets"].path_of(dom["assets"].get(z["asset_id"], pid))) as zf:
        hashes = {hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()}
        assert "photos_staged/hero_ambientada.png" in zf.namelist()
    assert sha_malo not in hashes
    assert bueno["output_sha256"] in hashes


# ===================================================================================================
# D — DERECHOS DE PRODUCTO
# ===================================================================================================
def test_one_off_entrega_una_sola_imagen_ambientada(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "PASS", 3, "APPROVE")
    b = _generado(dom, pid, foto)
    dom["staging"].review(b["attempt_id"], "PASS", 5, "APPROVE")
    assert len(dom["assets"].list_of_kind(pid, dom["assets"].PHOTO_STAGED)) == 1
    assert dom["staging"].get(a["attempt_id"])["output_asset_id"] is None
    assert dom["staging"].get(b["attempt_id"])["output_asset_id"]


def test_one_off_tiene_reintentos_internos_acotados_y_sin_boton_para_el_cliente(client, dom, fake, app):
    pid, foto = _prop_con_foto(dom)
    for _ in range(3):
        a = _generado(dom, pid, foto)
        dom["staging"].review(a["attempt_id"], "FAIL", None, "REJECT", ["other"])
    with pytest.raises(dom["entitlements"].EntitlementError):
        dom["staging"].create_attempt(pid, foto, "CONTEMPORARY", provider_name="fake")
    assert dom["staging"].state(pid)["state"] == "STAGING_NEEDS_MANUAL_REVIEW"
    # el cliente no tiene ninguna ruta para generar ni regenerar: eso es mecánica interna
    rutas = [r.rule for r in app.url_map.iter_rules() if r.rule.startswith("/properties")]
    assert not any("staging" in r or "generate_staging" in r for r in rutas)


def test_pro_permite_ambientar_por_propuesta(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    dom["entitlements"].set_product(pid, "PRO")        # el producto es de la propiedad (E32.2)
    fid = dom["fits"].create_prospect(pid, "Falabella", 30, style="PREMIUM")
    a = _generado(dom, pid, foto, style="PREMIUM", fit_id=fid)
    assert a["status"] == "GENERATED" and a["fit_id"] == fid
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    assert dom["packs"].staging_assets(pid, fid) and not dom["packs"].staging_assets(pid, None)
    dom["entitlements"].set_product(pid, "ONE_OFF")
    with pytest.raises(dom["entitlements"].EntitlementError):
        dom["staging"].create_attempt(pid, foto, "PREMIUM", fit_id=fid, provider_name="fake")


# ===================================================================================================
# E — PACK
# ===================================================================================================
def test_sin_imagen_ambientada_el_pack_base_no_esta_listo(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    _con_plano_y_layout(dom, pid)
    listo = dom["packs"].readiness(pid)
    assert listo["state"] == "NEEDS_STAGING" and "imagen ambientada aprobada" in listo["missing"]
    with pytest.raises(dom["packs"].PackNotReady):
        dom["packs"].export_zip(pid)
    assert dom["properties"].view(pid)["status"] != "PACK_READY"
    r = client.post(f"/properties/{pid}/pack")
    assert r.status_code == 400 and "imagen ambientada" in r.get_data(as_text=True)


def test_con_todo_lo_prometido_el_pack_esta_listo(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    _con_plano_y_layout(dom, pid)
    a = _generado(dom, pid, foto)
    assert dom["packs"].readiness(pid)["state"] == "STAGING_REVIEW"
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    assert dom["packs"].readiness(pid)["state"] == "READY"
    dom["packs"].export_zip(pid)
    assert dom["properties"].view(pid)["status"] == "PACK_READY"


def test_un_pack_degradado_exige_motivo_y_lo_declara(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_COMMERCIAL, "p.png", _png(), "image/png")
    assert dom["packs"].readiness(pid)["state"] != "DEGRADED"
    dom["packs"].set_override(pid, "búsqueda agotada en A/B/C; el cliente quiere igual el plano")
    assert dom["packs"].readiness(pid)["state"] == "DEGRADED"
    man = dom["packs"].export_zip(pid)["manifest"]
    assert man["readiness"]["state"] == "DEGRADED" and "búsqueda agotada" in man["readiness"]["override_reason"]
    assert any("degradado" in w for w in man["warnings"])


def test_sin_plano_comercial_no_hay_degradado_que_valga(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    dom["packs"].set_override(pid, "motivo")
    assert dom["packs"].readiness(pid)["state"] == "PREPARING"
    with pytest.raises(dom["packs"].PackNotReady):
        dom["packs"].export_zip(pid)


def test_el_disclosure_esta_en_manifiesto_zip_y_propuesta(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    _con_plano_y_layout(dom, pid)
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    z = dom["packs"].export_zip(pid)
    assert z["manifest"]["photos_staged"][0]["disclosure"] == "Ambientación referencial."
    with zipfile.ZipFile(dom["assets"].path_of(dom["assets"].get(z["asset_id"], pid))) as zf:
        assert "photos_staged/LEEME.txt" in zf.namelist()
        assert "Ambientación referencial" in zf.read("photos_staged/LEEME.txt").decode()
        assert "photos_staged/hero_original.png" in zf.namelist()
        assert "Ambientación referencial" in zf.read("propuesta.html").decode()
    assert "Ambientación referencial" in client.get(f"/properties/{pid}").get_data(as_text=True)


def test_la_procedencia_del_manifiesto_es_correcta(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    _con_plano_y_layout(dom, pid)
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    ref = dom["packs"].build_manifest(pid)["photos_staged"][0]
    assert ref["source_asset_id"] == foto and ref["attempt_id"] == a["attempt_id"]
    assert ref["provider"] == "fake" and ref["model"] == "fake-1"
    assert ref["visual_style"] == "CONTEMPORARY" and ref["request_version"] == "staging_request_v1"
    assert ref["input_sha256"] == dom["assets"].get(foto, pid)["sha256"]
    assert ref["output_sha256"] == a["output_sha256"]
    assert ref["human_review"] == {"fidelity": "PASS", "quality": 4}


def test_el_antes_despues_es_un_compuesto_con_leyenda(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    ba = dom["assets"].list_of_kind(pid, dom["assets"].BEFORE_AFTER)
    assert len(ba) == 1
    m = json.loads(ba[0]["metadata"])
    assert m["staged_asset_id"] and m["disclosure"] == "Ambientación referencial."
    assert ba[0]["source_asset_id"] == foto and ba[0]["width_px"] > ba[0]["height_px"]


# ===================================================================================================
# F — SEGURIDAD
# ===================================================================================================
def test_un_candidato_o_asset_ambientado_no_cruza_de_propiedad(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    otra, _ = _prop_con_foto(dom, "Otra")
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE")
    pub = dom["staging"].get(a["attempt_id"])["output_asset_id"]
    assert dom["staging"].get(a["attempt_id"], otra) is None
    assert client.get(f"/properties/{otra}/asset/{pub}").status_code == 404
    assert client.get(f"/properties/{pid}/asset/{pub}").status_code == 200


def test_la_clave_del_proveedor_nunca_se_serializa(client, dom, monkeypatch):
    """Un proveedor que refleja la clave en su error: el intento la guarda enmascarada."""
    monkeypatch.setenv("GEMINI_API_KEY", "gm-SECRETO-XYZ")
    monkeypatch.setenv("ESCALIMETRO_STAGING_PROVIDER", "gemini")
    _grabar(dom, [(401, json.dumps({"error": {"message": "bad key gm-SECRETO-XYZ"}}).encode())])
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto, provider="gemini")
    assert a["status"] == "FAILED" and "gm-SECRETO-XYZ" not in a["error"] and "***" in a["error"]
    assert "gm-SECRETO-XYZ" not in json.dumps(dom["staging"].get(a["attempt_id"]))
    assert "gm-SECRETO-XYZ" not in client.get(f"/staging/attempt/{a['attempt_id']}").get_data(as_text=True)


def test_el_manifiesto_no_filtra_rutas_prompt_ni_notas(client, dom, fake):
    from webapp import store
    pid, foto = _prop_con_foto(dom)
    _con_plano_y_layout(dom, pid)
    a = _generado(dom, pid, foto)
    dom["staging"].review(a["attempt_id"], "PASS", 4, "APPROVE", notes="NOTA-SECRETA-INTERNA")
    z = dom["packs"].export_zip(pid)
    texto = json.dumps(z["manifest"])
    assert store.DATA_DIR not in texto and "/Users/" not in texto
    assert "STRICTLY PRESERVE" not in texto and "NOTA-SECRETA-INTERNA" not in texto
    with zipfile.ZipFile(dom["assets"].path_of(dom["assets"].get(z["asset_id"], pid))) as zf:
        todo = b"".join(zf.read(n) for n in zf.namelist() if not n.endswith(".png"))
    assert b"NOTA-SECRETA-INTERNA" not in todo and b"STRICTLY PRESERVE" not in todo
    assert "NOTA-SECRETA-INTERNA" not in client.get(f"/properties/{pid}").get_data(as_text=True)


def test_el_cliente_no_ve_candidatos_ni_vocabulario_de_qa(client, dom, fake):
    pid, foto = _prop_con_foto(dom)
    a = _generado(dom, pid, foto)
    html = client.get(f"/properties/{pid}").get_data(as_text=True).lower()
    for palabra in ("/staging/", "fidelity", "candidato", "gemini", "openai", "bfl", "fake-1",
                    "prompt_hash"):
        assert palabra not in html, palabra
    assert "en preparación" in html or "en revisión" in html


# ===================================================================================================
# G — BENCHMARK
# ===================================================================================================
def test_todos_los_proveedores_reciben_la_misma_peticion(client, dom):
    b = dom["benchmark"]
    man = {"manifest_version": b.MANIFEST_VERSION, "photos": [
        {"photo_id": "x", "property_id": "p", "asset_id": "x"}]}
    items = b.plan(man, ["gemini", "openai", "bfl"], 2, "CONTEMPORARY")
    assert len(items) == 6
    assert len({i["prompt_hash"] for i in items}) == 1
    assert {i["request_version"] for i in items} == {"staging_request_v1"}
    assert dom["staging"].canonical_request("CONTEMPORARY")["prompt_hash"] != \
        dom["staging"].canonical_request("PREMIUM")["prompt_hash"]


def test_sin_credencial_el_benchmark_no_se_simula(client, dom):
    b = dom["benchmark"]
    pid, foto = _prop_con_foto(dom)
    man = b.manifest_from_properties([pid])
    ex = b.execute(man, ["gemini", "openai", "bfl"], 2, "CONTEMPORARY")
    assert ex["attempts"] == []
    assert all(v["status"] == "HUMAN_ACTION_REQUIRED" for v in ex["providers"].values())
    res = b.results(None, man, ["gemini", "openai", "bfl"], ex)
    assert res["status"] == "NOT_RUN" and res["sample_size"] == 0 and res["metrics"] == {}
    assert res["selection"]["verdict"] == "NOT_RUN" and res["selection"]["winner"] is None


def test_el_manifiesto_exige_fotos_reales_suficientes(client, dom):
    b = dom["benchmark"]
    pid, _ = _prop_con_foto(dom)
    man = b.manifest_from_properties([pid])
    errs = b.validate_manifest(man)
    assert any("8 fotos" in e for e in errs) and any("3 espacios" in e for e in errs)
    assert b.empty_manifest()["status"] == "AWAITING_REAL_PHOTOS"


def _filas(dom, pid, foto, provider, specs):
    """Inserta intentos de benchmark con resultados conocidos para probar la agregación.
    (Esto prueba la MATEMÁTICA; no es un resultado de proveedor y no se presenta como tal.)"""
    from webapp import store
    ids = []
    for i, (status, fid, rev, q, cost, lat, reasons) in enumerate(specs):
        aid = f"st_{provider}_{i}"
        store.ex("INSERT INTO staging_attempts(attempt_id, property_id, source_asset_id, "
                 "benchmark_id, visual_style, provider, model, request_version, prompt_hash, "
                 "input_sha256, status, review_status, fidelity_status, quality_score, cost_usd, "
                 "cost_basis, latency_ms, failure_reasons, created_at) "
                 "VALUES (?,?,?,'bm_t','CONTEMPORARY',?,'m1','staging_request_v1','h','s',?,?,?,?,?,"
                 "'measured',?,?,?)",
                 (aid, pid, foto, provider, status, rev, fid, q, cost, lat,
                  json.dumps(reasons), store.now()))
        ids.append(aid)
    return ids


def test_las_metricas_se_agregan_correctamente(client, dom, fake):
    b = dom["benchmark"]
    pid, foto = _prop_con_foto(dom)
    _filas(dom, pid, foto, "alfa", [
        ("GENERATED", "PASS", "APPROVED", 4, 0.10, 1000, []),
        ("GENERATED", "PASS", "APPROVED", 5, 0.10, 3000, []),
        ("GENERATED", "PASS", "REJECTED", 2, 0.10, 2000, []),
        ("GENERATED", "FAIL", "REJECTED", None, 0.10, 4000, ["window_changed"]),
        ("FAILED", "PENDING", "PENDING", None, 0.10, None, []),
    ])
    m = b.aggregate(b.attempts_of("bm_t"))["alfa"]
    assert m["total_generations"] == 5 and m["api_success"] == 4 and m["api_success_rate"] == 0.8
    assert m["reviewed"] == 4 and m["fidelity_pass"] == 3 and m["fidelity_pass_rate"] == 0.75
    assert m["approved"] == 2 and m["approval_rate"] == 0.5
    assert m["avg_quality_among_fidelity_pass"] == round((4 + 5 + 2) / 3, 2)
    assert m["hard_failure_reasons"] == {"window_changed": 1}
    assert m["sample_thin"] is True


def test_el_costo_por_imagen_aprobada_se_calcula_sobre_el_total(client, dom, fake):
    b = dom["benchmark"]
    pid, foto = _prop_con_foto(dom)
    _filas(dom, pid, foto, "beta", [
        ("GENERATED", "PASS", "APPROVED", 4, 0.04, 900, []),
        ("GENERATED", "FAIL", "REJECTED", None, 0.04, 900, ["other"]),
        ("GENERATED", "PASS", "REJECTED", 3, 0.04, 900, []),
        ("FAILED", "PENDING", "PENDING", None, 0.04, None, []),
    ])
    c = b.aggregate(b.attempts_of("bm_t"))["beta"]["cost"]
    assert c["total_usd"] == 0.16 and c["per_generation_usd"] == 0.04
    assert c["per_fidelity_pass_usd"] == 0.08 and c["per_approved_usd"] == 0.16


def test_la_latencia_se_agrega_con_mediana_y_p95(client, dom, fake):
    b = dom["benchmark"]
    pid, foto = _prop_con_foto(dom)
    lats = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
    _filas(dom, pid, foto, "gama", [("GENERATED", "PASS", "APPROVED", 4, 0.05, l, []) for l in lats])
    m = b.aggregate(b.attempts_of("bm_t"))["gama"]["latency_ms"]
    assert m["mean"] == 5500 and m["median"] == 5500 and m["p95"] == 10000 and m["n"] == 10


def test_la_compuerta_no_deja_pasar_sin_evidencia_ni_derechos(client, dom, fake):
    b = dom["benchmark"]
    pid, foto = _prop_con_foto(dom)
    _filas(dom, pid, foto, "delta", [("GENERATED", "PASS", "APPROVED", 5, 0.05, 900, [])] * 10)
    m = b.aggregate(b.attempts_of("bm_t"))["delta"]
    assert b.gate(m, rights_verified=False)["passes"] is False
    v = b.gate(m, rights_verified=True)
    assert v["passes"] is True and v["evidence"] == "pilot_only"
    assert b.select({"delta": m}, {"delta": True})["winner"] == "delta"
    assert b.select({"delta": m})["verdict"] == "NO_WINNER"


# ===================================================================================================
# H — REGRESIÓN
# ===================================================================================================
def test_los_derechos_de_e30_siguen_funcionando(client, dom):
    pid = dom["properties"].create("P", "OFFICE")
    with pytest.raises(dom["entitlements"].EntitlementError):
        dom["fits"].create_prospect(pid, "Falabella", 30)
    assert client.post("/properties/new", data={"title": "Otra"}).status_code == 403


def test_el_layout_representativo_y_los_fits_no_cambiaron(client, dom):
    from webapp import store
    pid = dom["properties"].create("P", "OFFICE")
    run = {"run_id": "r", "best_alt": "B"}
    alts = [{"alt": "A", "status": "FIT", "quality": json.dumps({"program_complete": True})},
            {"alt": "B", "status": "FIT", "quality": None}]
    assert dom["fits"].pick_representative(run, alts)["selected_by"] == "human_best_alt"
    fid = dom["fits"].ensure_base(pid, 40)
    assert dom["fits"].ensure_base(pid, 40) == fid and dom["fits"].base_of(pid)["kind"] == "BASE"


def test_las_superficies_siguen_respondiendo(client):
    for url in ("/", "/healthz", "/review", "/settings", "/properties/", "/staging/",
                "/staging/benchmark"):
        assert client.get(url).status_code == 200, url


def test_el_motor_no_fue_tocado():
    import subprocess
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"E31 tocó el motor: {out.stdout}"


def test_el_dominio_sigue_sin_importar_el_solver_ni_a_los_proveedores_por_nombre(client):
    """`webapp/domain` no puede nombrar a Google, OpenAI ni BFL: los conoce por el protocolo y por
    el registro. Si un módulo de dominio importara un adaptador, cambiar de proveedor sería
    cambiar el producto, que es lo que §16 prohíbe."""
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
