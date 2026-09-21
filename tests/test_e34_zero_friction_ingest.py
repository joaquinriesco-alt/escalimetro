"""E34 §21 — tests de CONTRATO del ingreso sin fricción.

La regla de producto: **el usuario entrega el inmueble, Escalímetro resuelve el resto.** Lo que se
protege acá es que la aplicación no vuelva a pedir lo que puede deducir, y que cuando NO pueda
deducirlo lo diga en vez de inventarlo.
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
           "webapp.domain.packs", "webapp.domain.reviews", "webapp.domain.ingest",
           "webapp.domain.lab", "webapp.benchmark", "webapp.customer", "webapp.staging_ui",
           "webapp.lab", "webapp.app")

FLOORPLATE_403 = os.path.join(ROOT, "cases", "001_gps_403", "outputs", "floorplate.json")


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
    from webapp.domain import assets, ingest, lab, properties, reviews, staging
    return {"assets": assets, "ingest": ingest, "lab": lab, "properties": properties,
            "reviews": reviews, "staging": staging}


def _nueva(client, titulo="Oficina 403", area=None):
    data = {"title": titulo, "city": "Santiago"}
    if area:
        data["published_area_m2"] = str(area)
    r = client.post("/lab/new", data=data, follow_redirects=True)
    return re.search(rb"p_[0-9a-f]{12}", r.data).group().decode()


def _fp403():
    with open(FLOORPLATE_403, encoding="utf-8") as fh:
        return json.load(fh)


# ===================================================================================================
# A — PRIORIDAD 0: NINGUNA PANTALLA DEL LAB PUEDE DAR 500
# ===================================================================================================
def test_lab_new_no_devuelve_500(client, dom):
    assert client.get("/lab/new").status_code == 200


def test_todas_las_pantallas_del_lab_renderizan(client, dom):
    """El 500 que vio Joaquín salió de una plantilla que esperaba variables que su ruta ya no
    pasaba (un servidor viejo sirviendo plantillas nuevas del disco). Ninguna ruta GET del LAB
    puede romperse al renderizar, con datos y sin datos."""
    vacias = ["/lab/", "/lab/new", "/lab/ajustes", "/lab/ajustes/evaluaciones", "/lab/debug",
              "/lab/benchmark", "/lab/feedback.json"]
    for u in vacias:
        assert client.get(u).status_code == 200, f"{u} sin datos"
    pid = _nueva(client)
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_ORIGINAL, "p.png", _png(), "image/png")
    for u in vacias + [f"/lab/p/{pid}", f"/lab/p/{pid}/status.json",
                       f"/lab/p/{pid}/revisar-plano"]:
        assert client.get(u).status_code == 200, f"{u} con datos"


# ===================================================================================================
# B — LO QUE SE PIDE AL CREAR
# ===================================================================================================
def test_crear_una_propiedad_pide_lo_minimo(client, dom):
    """§2 — nombre, plano y fotos. Nada de escala, acceso, pilares ni «¿está limpia la planta?»."""
    html = client.get("/lab/new").get_data(as_text=True)
    for prohibido in ("escala", "acceso", "pilar", "núcleo", "limpia", "declared_clean",
                      "scale_m", "orientación", "programa detallado"):
        assert prohibido not in html.lower(), prohibido
    for campo in ("title", "floorplan", "photos"):
        assert f'name="{campo}"' in html, campo
    assert _nueva(client, "Oficina 403")


def test_el_formulario_no_pregunta_por_el_producto_ni_el_estilo(client, dom):
    html = client.get("/lab/new").get_data(as_text=True)
    assert "workplace_preset" not in html and "visual_style" not in html
    assert "product" not in html


# ===================================================================================================
# C — ESCALA POR PUERTAS
# ===================================================================================================
def test_varios_vanos_producen_una_hipotesis_de_escala(dom):
    fp = {"entrance_candidates": [{"width_px": 7.0}, {"width_px": 8.0}, {"width_px": 7.5}]}
    h = dom["ingest"].scale_from_doors(fp)
    assert h["source"] == "AUTO_DOOR" and h["evidence_count"] == 3
    assert h["px_per_m"] == pytest.approx(7.5 / 0.90, rel=1e-3)
    assert 0 < h["confidence"] <= 1


def test_un_vano_atipico_se_descarta(dom):
    """Mediana + desviación absoluta mediana: una entrada doble no puede arrastrar la escala."""
    fp = {"entrance_candidates": [{"width_px": w} for w in (7.0, 7.2, 7.1, 7.3, 40.0)]}
    h = dom["ingest"].scale_from_doors(fp)
    assert 40.0 not in h["widths_px"]
    assert h["px_per_m"] == pytest.approx(7.15 / 0.90, rel=0.05)


def test_un_solo_vano_da_confianza_baja(dom):
    uno = dom["ingest"].scale_from_doors({"entrance_candidates": [{"width_px": 7.0}]})
    varios = dom["ingest"].scale_from_doors(
        {"entrance_candidates": [{"width_px": w} for w in (7.0, 7.1, 6.9, 7.05)]})
    assert uno["confidence"] < varios["confidence"]
    assert uno["confidence"] < dom["ingest"].MIN_AUTO_CONFIDENCE


def test_vanos_demasiado_finos_no_son_evidencia(dom):
    assert dom["ingest"].scale_from_doors({"entrance_candidates": [{"width_px": 2.0}]}) is None
    assert dom["ingest"].scale_from_doors({"entrance_candidates": []}) is None


def test_la_cuantizacion_baja_la_confianza(dom):
    """A pocos píxeles por metro, medio píxel de error ya es mucho: el número lo refleja."""
    fino = dom["ingest"].scale_from_doors(
        {"entrance_candidates": [{"width_px": w} for w in (5.0, 5.0, 5.0)]})
    grueso = dom["ingest"].scale_from_doors(
        {"entrance_candidates": [{"width_px": w} for w in (50.0, 50.0, 50.0)]})
    assert fino["confidence"] < grueso["confidence"]


# ===================================================================================================
# D — CONTRASTE CONTRA LA SUPERFICIE PUBLICADA
# ===================================================================================================
def test_el_contraste_de_area_se_calcula_y_se_guarda(client, dom):
    fp = _fp403()
    d = dom["ingest"].decide(fp)
    cc = d["cross_checks"]
    assert cc["published_area_m2"] == 543.0
    assert "door_derived_area_m2" in cc and "area_relative_difference" in cc
    assert cc["scale_agrees"] is False          # los vanos del 403 son accesos, no puertas de 0.90


def test_el_contraste_no_deforma_la_geometria(dom):
    """§5 — la diferencia es una señal, no una corrección: la escala elegida no se toca."""
    fp = _fp403()
    d = dom["ingest"].decide(fp)
    assert d["scale_value"] == fp["scale"]["px_per_m"]


def test_el_acuerdo_con_las_puertas_sube_la_confianza(dom):
    """Si ambas fuentes coinciden, la escala publicada vale más."""
    fp = _fp403()
    ppm = fp["scale"]["px_per_m"]
    base = dom["ingest"].decide(fp)["scale_confidence"]
    fp["entrance_candidates"] = [{"width_px": ppm * 0.90}] * 4      # vanos de 0.90 m exactos
    fp["primary_entrance"] = dict(fp["primary_entrance"], width_px=ppm * 0.90)
    mejor = dom["ingest"].decide(fp)
    assert mejor["cross_checks"]["scale_agrees"] is True
    assert mejor["scale_confidence"] > base


# ===================================================================================================
# E — LA DECISIÓN Y EL FALLBACK
# ===================================================================================================
def test_con_superficie_publicada_manda_la_superficie(dom):
    """§4 — el orden importa: las puertas son la evidencia más débil de las dos."""
    d = dom["ingest"].decide(_fp403())
    assert d["scale_source"] == "PUBLISHED_AREA"
    assert d["needs_review"] is False


def test_sin_ninguna_evidencia_no_se_inventa_una_escala(dom):
    d = dom["ingest"].decide({"scale": {"method": "unknown"}, "shell_readiness": {}})
    assert d["scale_source"] == "UNKNOWN" and d["scale_value"] is None
    assert d["needs_review"] is True


def test_una_escala_por_puertas_floja_va_a_revision(dom):
    fp = {"scale": {"method": "unknown"}, "area_px2": 40000,
          "entrance_candidates": [{"width_px": 6.0}],
          "shell_readiness": {"ready_for_layout": True}}
    d = dom["ingest"].decide(fp)
    assert d["scale_source"] == "AUTO_DOOR"
    assert d["scale_confidence"] < dom["ingest"].MIN_AUTO_CONFIDENCE
    assert d["needs_review"] is True


def test_una_escala_medida_a_mano_sigue_valiendo(dom):
    """§20 — la medición manual no se elimina: deja de ser el primer paso."""
    fp = {"scale": {"method": "manual", "px_per_m": 9.0, "meta": {"confidence": 1.0}},
          "shell_readiness": {"ready_for_layout": True}}
    d = dom["ingest"].decide(fp)
    assert d["scale_source"] == "MANUAL" and d["scale_confidence"] == 1.0
    assert d["needs_review"] is False


def test_la_autoridad_sobre_seguir_es_del_motor(dom):
    """Si el motor dice que no está listo, no hay confianza propia que lo anule."""
    fp = _fp403()
    fp["shell_readiness"] = dict(fp["shell_readiness"], ready_for_layout=False)
    assert dom["ingest"].decide(fp)["needs_review"] is True


# ===================================================================================================
# F — ACEPTACIÓN AUTOMÁTICA POR REGLA
# ===================================================================================================
def test_las_claves_de_confirmacion_se_traducen_al_vocabulario_del_motor(dom):
    """`requires_confirmation` y `overrides.confirm` NO usan los mismos nombres. Pasarlos sin
    traducir no da error: simplemente no confirma nada."""
    i = dom["ingest"]
    assert i.CONFIRM_KEYS["perimeter/core"] == ["perimeter", "core"]
    assert i.CONFIRM_KEYS["primary_entrance"] == ["entrance"]
    fp = dict(_fp403(), shell_readiness={"requires_confirmation":
                                         ["perimeter/core", "primary_entrance", "columns"]})
    auto = i.auto_confirmations(fp)
    assert "perimeter" in auto["confirm_keys"] and "entrance" in auto["confirm_keys"]
    assert "perimeter/core" not in auto["confirm_keys"]


def test_lo_que_no_llega_a_la_vara_queda_pendiente_con_nombre(dom):
    fp = _fp403()
    fp["perimeter"] = {"meta": {"confidence": 0.2}}
    fp["shell_readiness"] = {"requires_confirmation": ["perimeter/core"]}
    auto = dom["ingest"].auto_confirmations(fp)
    assert auto["accept"] == [] and auto["pending"] == ["perimeter/core"]
    assert "contorno" in auto["pending_labels"][0]


def test_aceptado_por_regla_no_es_lo_mismo_que_confirmado_por_humano(dom):
    """§8 — se distinguen, y la diferencia viaja en la procedencia."""
    i = dom["ingest"]
    assert i.AUTO_ACCEPTED_BY_RULE != i.HUMAN_CONFIRMED
    d = i.decide(_fp403())
    assert d["geometry_source"] == i.AUTO_ACCEPTED_BY_RULE


# ===================================================================================================
# G — ACCESO
# ===================================================================================================
def test_el_acceso_se_infiere_con_su_procedencia(dom):
    d = dom["ingest"].decide(_fp403())
    assert d["access_source"] == "AUTO"
    assert d["access_confidence"] == pytest.approx(0.95, abs=0.01)


def test_sin_acceso_detectado_se_dice(dom):
    fp = dict(_fp403(), primary_entrance=None)
    assert dom["ingest"].decide(fp)["access_source"] == "NONE"


# ===================================================================================================
# H — PACK 1 Y PACK 2
# ===================================================================================================
def test_sin_plano_el_boton_lo_dice_y_no_falla(client, dom):
    pid = _nueva(client)
    res = dom["lab"].pack1_advance(pid)
    assert "plano" in (res["blocked"] or "").lower()


def test_la_foto_principal_se_elige_sola(client, dom):
    """§10 — heurística simple: la más grande y sin repetir. El usuario puede cambiarla."""
    from werkzeug.datastructures import FileStorage
    pid = _nueva(client)
    for w in (400, 1200, 800):
        dom["assets"].save_upload(pid, FileStorage(stream=io.BytesIO(_png(w, 300)),
                                                   filename=f"f{w}.png"),
                                  dom["assets"].PHOTO_ORIGINAL)
    dom["lab"].pack1_advance(pid)
    h = dom["staging"].hero(pid)
    assert h is not None and h["width_px"] == 1200
    otra = [f for f in dom["assets"].list_of_kind(pid, dom["assets"].PHOTO_ORIGINAL)
            if f["width_px"] == 400][0]
    client.post(f"/lab/p/{pid}/hero", data={"asset_id": otra["asset_id"]})
    assert dom["staging"].hero(pid)["asset_id"] == otra["asset_id"]


def test_pack2_express_pide_cliente_y_personas(client, dom):
    """§13 — eso es todo. Estilo visual, logo y programa detallado, escondidos."""
    pid = _nueva(client)
    sec = client.get(f"/lab/p/{pid}").get_data(as_text=True).split('id="pack2"')[1]
    formulario = sec.split("Más opciones")[0]
    assert 'name="prospect_name"' in formulario and 'name="headcount"' in formulario
    assert 'name="visual_style"' not in formulario
    assert 'name="prospect_logo"' not in formulario
    assert 'name="workstations"' not in formulario
    assert 'name="visual_style"' in sec                 # existe, detrás de «Más opciones»


def test_los_valores_por_defecto_son_balanceado_y_contemporaneo(client, dom):
    from webapp.domain import presets
    assert presets.DEFAULT_PRESET == "BALANCED"
    assert presets.DEFAULT_STYLE == "CONTEMPORARY"
    pid = _nueva(client)
    sec = client.get(f"/lab/p/{pid}").get_data(as_text=True).split('id="pack2"')[1]
    assert 'value="BALANCED" selected' in sec
    assert 'value="CONTEMPORARY" selected' in sec


# ===================================================================================================
# I — EL FEEDBACK SE PUEDE CORRELACIONAR CON LO QUE SE DEDUJO
# ===================================================================================================
def test_la_inferencia_queda_guardada_junto_a_la_propiedad(client, dom):
    pid = _nueva(client, area=543)
    dom["ingest"].save(pid, "c1", dom["ingest"].decide(_fp403()))
    g = dom["ingest"].get(pid)
    assert g["scale_source"] == "PUBLISHED_AREA" and g["scale_value"]
    assert g["access_source"] == "AUTO" and g["geometry_source"] == "AUTO_ACCEPTED_BY_RULE"
    assert g["cross_checks_obj"]["published_area_m2"] == 543.0


def test_el_usuario_no_ve_la_inferencia_pero_queda_registrada(client, dom):
    """§16 — se guarda para poder correlacionar «layout malo» con «escala deducida flojamente».
    No se le muestra a nadie fuera del detalle técnico."""
    pid = _nueva(client, area=543)
    dom["ingest"].save(pid, "c1", dom["ingest"].decide(_fp403()))
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    visible = html.split("Ver detalle")[0]
    for termino in ("AUTO_ACCEPTED_BY_RULE", "PUBLISHED_AREA", "px_per_m", "confidence",
                    "cross_check"):
        assert termino not in visible, termino
    assert "PUBLISHED_AREA" in html                     # sí en el detalle técnico


def test_una_calificacion_sigue_guardando_su_procedencia(client, dom):
    pid = _nueva(client)
    client.post(f"/lab/p/{pid}/evaluar", data={"artifact_type": "PACK1", "rating": "MALO"})
    r = dom["reviews"].latest(pid, "PACK1")
    assert r["engine_version"]


# ===================================================================================================
# J — REGRESIÓN
# ===================================================================================================
def test_el_shell_simple_de_e33_sigue_en_pie(client, dom):
    nav = re.search(r"<nav>(.*?)</nav>",
                    client.get("/lab/").get_data(as_text=True), re.S).group(1)
    assert re.findall(r">([^<>]+)</a>", nav) == ["Mis propiedades", "Ajustes"]


def test_las_herramientas_tecnicas_siguen_accesibles(client, dom):
    html = client.get("/lab/debug").get_data(as_text=True)
    for destino in ("/staging/", "/review", "/properties/", "/lab/benchmark"):
        assert destino in html


def test_el_motor_no_fue_tocado():
    import subprocess
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"E34 tocó el motor: {out.stdout}"
