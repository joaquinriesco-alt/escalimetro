"""E36 §27 — tests de CONTRATO del piloto real.

E36 no agrega inteligencia: agrega realidad. Lo que se protege acá es que el instrumento de
medición no mienta —ni inflando la muestra, ni confundiendo dos juicios distintos, ni dando por
calibrado un umbral que nunca llegó a discriminar— y que el operador no tenga que salir de la
página para hacer el QA que el flujo necesita.
"""
from __future__ import annotations

import importlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import zlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

MODULOS = ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.briefs",
           "webapp.detected", "webapp.domain.settings", "webapp.domain.entitlements",
           "webapp.domain.grants", "webapp.domain.presets", "webapp.domain.properties",
           "webapp.domain.assets", "webapp.domain.branding", "webapp.domain.fits",
           "webapp.domain.floorplan", "webapp.domain.proposal", "webapp.domain.visual",
           "webapp.domain.pilot", "webapp.providers.base", "webapp.providers.gemini",
           "webapp.providers.openai_images", "webapp.providers.bfl", "webapp.providers",
           "webapp.domain.staging", "webapp.domain.packs", "webapp.domain.reviews",
           "webapp.domain.units", "webapp.domain.interventions", "webapp.domain.ingest",
           "webapp.domain.calibration", "webapp.domain.gold", "webapp.domain.realpilot",
           "webapp.domain.lab", "webapp.benchmark", "webapp.customer", "webapp.staging_ui",
           "webapp.lab", "webapp.app")

PLANO_403 = os.path.join(ROOT, "cases", "001_gps_403", "original.png")


def _png(w: int = 64, h: int = 48, tinte: bytes = b"\x80\x90\xa0") -> bytes:
    raw = b"".join(b"\x00" + tinte * w for _ in range(h))

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
    from webapp.domain import (assets, calibration, gold, ingest, interventions, lab, properties,
                               realpilot, reviews, units)
    return {"assets": assets, "calibration": calibration, "gold": gold, "ingest": ingest,
            "interventions": interventions, "lab": lab, "properties": properties,
            "realpilot": realpilot, "reviews": reviews, "units": units}


def _prop(dom, titulo, *, plano=PLANO_403, area=543.0, real=True, pilot=True, contenido=None):
    pid = dom["properties"].create(title=titulo, city="Santiago", published_area_m2=area)
    datos = contenido if contenido is not None else open(plano, "rb").read()
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_ORIGINAL, "p.png", datos, "image/png")
    dom["realpilot"].mark(pid, in_pilot=pilot,
                          source_type=dom["realpilot"].REAL_BROKER if real
                          else dom["realpilot"].FIXTURE)
    return pid


def _listo(dom, pid):
    """Deja la propiedad con geometría lista: unidad elegida y compuertas confirmadas."""
    from webapp.domain import floorplan
    cid = floorplan.ensure_case(pid)
    dom["units"].resolve(pid, cid)
    if dom["units"].get(pid)["status"] != dom["units"].RESOLVED:
        dom["units"].pick(pid, "u1")
    dom["ingest"].auto_prepare(pid)
    dom["ingest"].confirm_pending(pid)
    return cid


# ===================================================================================================
# 1–2 — QA INLINE (§3)
# ===================================================================================================
def test_la_pregunta_de_unidad_no_saca_de_la_pagina(client, dom):
    """§27.1 — «¿Cuál es la oficina?» se resuelve donde está el operador."""
    pid = _prop(dom, "Apoquindo 3000")
    r = client.post(f"/lab/p/{pid}/pack1", data={"headcount": "40"})
    assert r.status_code == 302
    assert r.headers["Location"] == f"/lab/p/{pid}#oficina"
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    assert "¿Cuál es la oficina?" in html


def test_la_confirmacion_de_geometria_no_saca_de_la_pagina(client, dom):
    """§27.2 / §3.B — el último salto de UX que E35 reportó. La confirmación del contorno ocurre
    INLINE, con el dibujo a la vista, y su botón apunta a esta misma página."""
    from webapp.domain import floorplan
    pid = _prop(dom, "Apoquindo 3000")
    cid = floorplan.ensure_case(pid)
    dom["units"].resolve(pid, cid)
    dom["units"].pick(pid, "u1")
    dom["ingest"].auto_prepare(pid)
    qa = dom["lab"].qa_state(pid)
    assert qa["kind"] == "GEOMETRY"
    r = client.post(f"/lab/p/{pid}/pack1", data={"headcount": "40"})
    assert r.headers["Location"] == f"/lab/p/{pid}#revision"
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    assert "¿Esto corresponde a la oficina?" in html
    assert f"/lab/p/{pid}/confirmar-geometria" in html
    assert client.get(f"/lab/p/{pid}/deteccion.svg").status_code == 200
    r2 = client.post(f"/lab/p/{pid}/confirmar-geometria")
    assert r2.headers["Location"] == f"/lab/p/{pid}#pack1"
    assert dom["lab"].qa_state(pid) is None


def test_el_qa_interno_no_se_presenta_como_datos_del_cliente(client, dom):
    """§4 — «Necesitamos revisar el plano», no «complete los siguientes campos». La unidad, la
    geometría y la escala son trabajo nuestro, no un formulario para quien publica la oficina."""
    pid = _prop(dom, "Apoquindo 3000")
    client.post(f"/lab/p/{pid}/pack1", data={"headcount": "40"})
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True).lower()
    for prohibido in ("complet", "campos obligatorios", "ingrese", "unit id"):
        assert prohibido not in html, prohibido
    assert "necesitamos" in html


def test_el_flujo_completo_ocurre_en_un_solo_shell(client, dom):
    """§25 — objetivo: 1 shell. Se cuentan los destinos por los que pasa el operador."""
    pid = _prop(dom, "Apoquindo 3000")
    destinos = []
    r = client.post(f"/lab/p/{pid}/pack1", data={"headcount": "40"})
    destinos.append(r.headers["Location"])
    r = client.post(f"/lab/p/{pid}/elegir-oficina", data={"candidate_id": "u1"})
    destinos.append(r.headers["Location"])
    r = client.post(f"/lab/p/{pid}/confirmar-geometria")
    destinos.append(r.headers["Location"])
    assert all(d.split("#")[0] == f"/lab/p/{pid}" for d in destinos), destinos


# ===================================================================================================
# 3–4 — QUÉ CUENTA COMO N (§6, §23, §24)
# ===================================================================================================
def test_el_piloto_real_excluye_fixtures(client, dom):
    """§27.3 / §6 — un fixture sintético no es evidencia sobre planos reales."""
    rp = dom["realpilot"]
    _prop(dom, "Real", real=True)
    _prop(dom, "Fixture", real=False, contenido=_png(tinte=b"\x10\x20\x30"))
    sin_declarar = dom["properties"].create(title="Heredada", city="Santiago")
    dom["assets"].save_bytes(sin_declarar, dom["assets"].FLOORPLAN_ORIGINAL, "p.png",
                             _png(tinte=b"\x40\x50\x60"), "image/png")
    rp.mark(sin_declarar, in_pilot=True)                       # sin procedencia declarada
    titulos = {m["title"] for m in rp.members()}
    assert titulos == {"Real"}, "entró material que no es real"
    assert rp.is_real(None) is False and rp.is_real("FIXTURE") is False
    assert rp.is_real("REAL_PUBLIC_LISTING") is True


def test_el_mismo_plano_cuenta_una_vez(client, dom):
    """§27.4 / §23 / §24 — «Oficina 403», «Mi oficina» y «X» son la misma planta vista tres veces.
    Contarlas como tres daría por calibrado algo que no lo está."""
    rp = dom["realpilot"]
    ids = [_prop(dom, t) for t in ("Oficina 403", "Mi oficina", "X")]
    otro = _prop(dom, "Otra planta", contenido=_png(tinte=b"\x11\x22\x33"))
    assert len(rp.members()) == 4
    unicas = rp.unique_members()
    assert len(unicas) == 2, [m["title"] for m in unicas]
    assert sum(1 for n in rp.duplicates().values() if n > 1) == 1
    assert {m["property_id"] for m in unicas} <= set(ids + [otro])


def test_el_representante_del_grupo_es_el_que_tiene_etiquetas(client, dom):
    """Determinista y no arbitrario: representa al grupo la propiedad con juicio humano; a
    igualdad, la más antigua. Si dos lecturas del panel eligieran distinto, el panel mentiría."""
    rp, g = dom["realpilot"], dom["gold"]
    a = _prop(dom, "Primera")
    b = _prop(dom, "Segunda")
    assert rp.unique_members()[0]["property_id"] == a
    _listo(dom, b)
    g.save(b, g.PERIMETER, g.CORRECTO)
    assert rp.unique_members()[0]["property_id"] == b


# ===================================================================================================
# 5–6 — ETIQUETAS DE VERDAD (§8, §9)
# ===================================================================================================
def test_las_etiquetas_de_verdad_se_guardan(client, dom):
    """§27.5 — persisten con la confianza que el motor tenía al etiquetar."""
    g = dom["gold"]
    pid = _prop(dom, "Apoquindo 3000")
    _listo(dom, pid)
    r = client.post(f"/lab/p/{pid}/gold",
                    data={"component": "core", "verdict": "CORRECTO", "note": "se ve bien"})
    assert r.status_code == 302
    fila = g.of_property(pid)["core"]
    assert fila["verdict"] == g.CORRECTO and fila["note"] == "se ve bien"
    assert fila["engine_confidence"] == 0.5 and fila["engine_version"]
    g.save(pid, g.CORE, g.INCORRECTO)                          # la última mirada es la válida
    assert g.of_property(pid)["core"]["verdict"] == g.INCORRECTO
    with pytest.raises(g.GoldError):
        g.save(pid, "lo_que_sea", g.CORRECTO)
    with pytest.raises(g.GoldError):
        g.save(pid, g.CORE, "MAS_O_MENOS")


def test_la_etiqueta_de_verdad_es_distinta_de_la_calificacion_de_producto(client, dom):
    """§27.6 / §9 — «Pack bueno» NO es prueba de que el núcleo estuviera bien recortado. Dos
    vocabularios, dos tablas, y ninguno contamina al otro."""
    from webapp import store
    g, rev = dom["gold"], dom["reviews"]
    pid = _prop(dom, "Apoquindo 3000")
    _listo(dom, pid)
    rev.save(pid, "PACK1", "EXCELENTE")
    g.save(pid, g.CORE, g.INCORRECTO)
    assert set(g.VERDICTS).isdisjoint(set(rev.RATINGS))
    assert store.q1("SELECT COUNT(*) n FROM product_reviews WHERE property_id=?", (pid,))["n"] == 1
    assert store.q1("SELECT COUNT(*) n FROM gold_labels WHERE property_id=?", (pid,))["n"] == 1
    # y el dataset de calibración NO toma nada de las calificaciones de producto
    filas = g.rows_for_calibration([pid])
    assert [f["component"] for f in filas] == ["core"]
    assert filas[0]["human_verdict"] == "DISAGREES_WITH_HUMAN"


def test_solo_se_pide_juicio_sobre_lo_que_el_motor_decidio(client, dom):
    """§8 — pedir juicio sobre un componente que nadie emitió no produce evidencia, sólo fricción.
    Y `NO_APLICA` no entra a calibrar: una planta sin núcleo no tiene un núcleo mal detectado."""
    g = dom["gold"]
    pid = _prop(dom, "Apoquindo 3000")
    _listo(dom, pid)
    est = g.review_state(pid)
    assert set(est["judgeable"]) <= set(g.COMPONENTS) and est["judgeable"]
    assert not est["complete"]
    for c in est["judgeable"]:
        g.save(pid, c, g.NO_APLICA)
    assert g.complete(pid) is True
    assert g.rows_for_calibration([pid]) == []


# ===================================================================================================
# 7–11 — CALIBRACIÓN (§10, §11, §12)
# ===================================================================================================
def _filas(comp, pares):
    return [{"component": comp, "engine_confidence": c, "human_verdict": v} for c, v in pares]


def test_los_falsos_aceptos_se_calculan(client, dom):
    """§27.7 — aceptar por regla algo que un humano marcó incorrecto."""
    cal = dom["calibration"]
    m = cal.metrics(_filas("primary_entrance",
                           [(0.95, cal.DISAGREES), (0.90, cal.CONFIRMED), (0.50, cal.CONFIRMED)]))
    c = m["components"][0]
    assert c["would_accept"] == 2 and c["false_accept"] == 1 and c["true_accept"] == 1
    assert m["false_accept_count"] == 1


def test_los_falsos_rechazos_se_calculan(client, dom):
    """§27.8 — mandar a revisión algo que el humano acabó confirmando tal cual. Es el error
    barato, y se cuenta igual: sin él no se puede ver el costo de una vara demasiado alta."""
    cal = dom["calibration"]
    m = cal.metrics(_filas("core", [(0.50, cal.CONFIRMED), (0.85, cal.CONFIRMED)]))
    c = m["components"][0]
    assert c["effective_threshold"] == 0.60                    # 0.50 + banda 0.10
    assert c["false_review"] == 1 and c["would_accept"] == 1
    assert m["false_review_count"] == 1


def test_precision_y_cobertura_por_componente(client, dom):
    """§27.9 / §10 — por componente, nunca un accuracy global."""
    cal = dom["calibration"]
    m = cal.metrics(_filas("perimeter", [(0.90, cal.CONFIRMED), (0.70, cal.DISAGREES),
                                         (0.10, cal.DISAGREES)]))
    c = m["components"][0]
    assert c["auto_accept_precision"] == 0.5 and c["auto_accept_coverage"] == round(2 / 3, 3)
    assert "accuracy" not in m and "accuracy" not in c


def test_no_se_propone_umbral_con_muestra_chica(client, dom):
    """§27.10 / §11 — MIN_SAMPLE = 10 para siquiera PROPONER."""
    cal = dom["calibration"]
    pocas = _filas("perimeter", [(0.90, cal.CONFIRMED)] * 4 + [(0.10, cal.DISAGREES)] * 4)
    p = cal.proposal(cal.metrics(pocas))
    assert p["status"] == "THRESHOLD_UNCALIBRATED" and p["proposed"] is None


def test_no_se_propone_umbral_si_nunca_discrimino(client, dom):
    """§27.11 / §11 — «Si n >= 10 pero todos están de un lado: sigue UNCALIBRATED.»"""
    cal = dom["calibration"]
    de_un_lado = _filas("perimeter", [(0.90, cal.CONFIRMED)] * 12)
    m = cal.metrics(de_un_lado)
    c = m["components"][0]
    assert c["sample_count"] == 12 >= cal.MIN_SAMPLE
    assert c["threshold_exercised"] is False
    assert c["status"] == "THRESHOLD_UNCALIBRATED"
    assert cal.proposal(m)["proposed"] is None


def test_con_muestra_y_discriminacion_el_componente_queda_calibrado(client, dom):
    """El otro lado del contrato: si la evidencia alcanza, el estado lo dice. Y aun así E36 no
    mueve ningún número solo (§12): la propuesta es para que una persona decida."""
    cal = dom["calibration"]
    m = cal.metrics(_filas("perimeter", [(0.90, cal.CONFIRMED)] * 8
                           + [(0.20, cal.DISAGREES)] * 4))
    c = m["components"][0]
    assert c["sample_count"] == 12 and c["threshold_exercised"] is True
    assert c["status"] == "CALIBRATED"
    p = cal.proposal(m)
    assert p["proposed"] == cal.AUTO_CONFIRM_THRESHOLDS, "E36 no cambia umbrales solo"


def test_la_calibracion_del_piloto_sale_de_etiquetas_reales(client, dom):
    """§10 — el panel se alimenta de las etiquetas de verdad de propiedades reales, no del archivo
    histórico de E35."""
    g, rp = dom["gold"], dom["realpilot"]
    pid = _prop(dom, "Apoquindo 3000")
    _listo(dom, pid)
    for c in g.review_state(pid)["judgeable"]:
        g.save(pid, c, g.CORRECTO)
    panel = rp.dashboard()
    assert panel["gold_complete"] == 1
    comps = {c["component"] for c in panel["calibration"]["components"]}
    assert "perimeter" in comps
    assert panel["calibration"]["labelled_rows"] > 0


# ===================================================================================================
# 12–13 — INTERVENCIONES Y TIEMPOS (§14, §15)
# ===================================================================================================
def test_metricas_de_intervencion_manual(client, dom):
    """§27.12 / §14 — la métrica de producto: ¿«automático» es verdad?"""
    rp, iv = dom["realpilot"], dom["interventions"]
    a = _prop(dom, "Sin ayuda")
    b = _prop(dom, "Con ayuda", contenido=_png(tinte=b"\x11\x22\x33"))
    iv.record(b, iv.UNIT_SELECTION, "eligió la oficina")
    iv.record(b, iv.ACCESS, "corrigió el acceso")
    m = rp.intervention_metrics()
    assert m["properties"] == 2 and m["fully_automatic"] == 1
    assert m["fully_automatic_pct"] == 50.0 and m["median_interventions"] == 1
    assert m["by_reason"]["ACCESS"] == 1
    assert "ACCESS" in iv.REASONS, "§14 pide el acceso como motivo propio"
    assert m["distribution"] == {"0": 1, "2": 1}


def test_metricas_de_tiempo(client, dom):
    """§27.13 / §15 — seis marcas, ningún tracking. Y lo que no se midió sale None, no cero: un
    cero se promedia y miente."""
    rp = dom["realpilot"]
    pid = _prop(dom, "Apoquindo 3000")
    t0 = rp.timing_metrics()
    assert t0["median_seconds"]["created_to_pack1_ready"] is None
    assert t0["sample"]["created_to_pack1_ready"] == 0
    rp.stamp(pid, "pack1_started_at")
    rp.stamp(pid, "geometry_ready_at")
    t1 = rp.timing_metrics()
    assert t1["sample"]["pack1_started_to_geometry"] == 1
    assert t1["median_seconds"]["pack1_started_to_geometry"] is not None
    primera = dom["properties"].require(pid)["pack1_started_at"]
    rp.stamp(pid, "pack1_started_at")                          # idempotente: el hito es la PRIMERA
    assert dom["properties"].require(pid)["pack1_started_at"] == primera
    # la nota tiene que DECIR que no es tiempo de atención humana, no callarlo
    assert "no es tiempo de atención humana" in t1["_note"]


def test_los_hitos_se_marcan_en_el_flujo_real(client, dom):
    """No sirve un contador que nadie incrementa: el botón real tiene que dejar las marcas."""
    pid = _prop(dom, "Apoquindo 3000")
    client.post(f"/lab/p/{pid}/pack1", data={"headcount": "40"})
    p = dom["properties"].require(pid)
    assert p["pack1_started_at"] and p["geometry_ready_at"] is None
    client.post(f"/lab/p/{pid}/elegir-oficina", data={"candidate_id": "u1"})
    client.post(f"/lab/p/{pid}/confirmar-geometria")
    assert dom["properties"].require(pid)["geometry_ready_at"]


# ===================================================================================================
# 14–15 — AGREGADOS DE PRODUCTO (§16, §17)
# ===================================================================================================
def test_agregado_de_calificaciones_de_pack1(client, dom):
    """§27.14 / §16 — % bueno, % malo y los motivos negativos más frecuentes."""
    rp, rev = dom["realpilot"], dom["reviews"]
    pid = _prop(dom, "Apoquindo 3000")
    rev.save(pid, "PLANO", "EXCELENTE")
    rev.save(pid, "LAYOUT", "MALO", reason_tags=["Distribución"])
    rev.save(pid, "PACK1", "BUENO")
    a = rp.pack1_ratings()
    assert a["overall"]["total"] == 3 and a["overall"]["good"] == 2
    assert a["overall"]["good_pct"] == round(200 / 3, 1)
    assert a["by_artifact"]["LAYOUT"]["bad"] == 1
    assert "Distribución" in a["overall"]["top_negative"]


def test_agregado_de_calificaciones_de_pack2(client, dom):
    """§27.15 / §17 — de cada propuesta A/B/C, ¿se salvó alguna? Es el layout engine como
    producto, no como motor."""
    from webapp.domain import fits
    rp, rev = dom["realpilot"], dom["reviews"]
    from webapp.domain import entitlements
    pid = _prop(dom, "Apoquindo 3000")
    entitlements.set_product(pid, "PRO")                       # las propuestas son de Pro (E32.2)
    f1 = fits.create_prospect(pid, "Falabella", 80)
    f2 = fits.create_prospect(pid, "Cencosud", 50)
    rev.save(pid, "ALTERNATIVA", "BUENO", artifact_id="A", fit_id=f1)
    rev.save(pid, "ALTERNATIVA", "MALO", artifact_id="B", fit_id=f1)
    rev.save(pid, "ALTERNATIVA", "PESIMO", artifact_id="A", fit_id=f2)
    a = rp.pack2_ratings()
    assert a["proposals"] == 2 and a["with_good_alternative"] == 1
    assert a["with_good_pct"] == 50.0 and a["all_bad"] == 1 and a["all_bad_pct"] == 50.0


# ===================================================================================================
# 16–17 — CORPUS DE AMBIENTACIÓN Y EXPORT (§18, §19, §22)
# ===================================================================================================
def test_el_corpus_de_ambientacion_solo_cuenta_fotos_reales(client, dom):
    """§27.16 / §18 — una foto de fixture no dice nada sobre cómo responde un proveedor con
    material de un cliente."""
    rp = dom["realpilot"]
    real = _prop(dom, "Real")
    falsa = _prop(dom, "Fixture", real=False, contenido=_png(tinte=b"\x11\x22\x33"))
    dom["assets"].save_bytes(real, dom["assets"].PHOTO_ORIGINAL, "f1.png", _png(), "image/png")
    dom["assets"].save_bytes(falsa, dom["assets"].PHOTO_ORIGINAL, "f2.png",
                             _png(tinte=b"\x44\x55\x66"), "image/png")
    c = rp.staging_corpus()
    assert c["photo_count"] == 1 and c["properties"] == 1
    assert all(f["property_id"] == real for f in c["photos"])
    assert all(f["source_type"].startswith("REAL_") for f in c["photos"])
    assert c["ready"] is False and c["min_photos"] == 8 and c["min_properties"] == 3


def test_la_preparacion_del_bakeoff_no_muestra_secretos(client, dom):
    """§19/§20 — presencia, nunca el valor. Y no se ejecuta nada sin una acción explícita."""
    r = dom["realpilot"].staging_readiness()
    assert r["ready"] is False and r["blockers"]
    for c in r["credentials"]:
        assert set(c) == {"name", "env", "configured", "in_pilot", "excluded"}
        assert isinstance(c["configured"], bool)
    html = client.get("/lab/ajustes/evaluaciones").get_data(as_text=True)
    assert "LISTO PARA BAKE-OFF" not in html
    assert "sk-" not in html and "AIza" not in html


def test_el_export_no_lleva_datos_sensibles(client, dom):
    """§27.17 / §22 — un export que arrastra datos «por si acaso» es una fuga esperando ocurrir."""
    g = dom["gold"]
    pid = _prop(dom, "Apoquindo 3000 · piso 4")
    dom["realpilot"].mark(pid, source_reference="corredora X, contacto interno")
    _listo(dom, pid)
    g.save(pid, g.PERIMETER, g.CORRECTO)
    dom["reviews"].save(pid, "PACK1", "MALO", reason_tags=["Incompleto"], comment="feo")
    r = client.get("/lab/pilot/export.json")
    assert r.status_code == 200
    crudo = r.get_data(as_text=True)
    d = json.loads(crudo)
    assert d["schema_version"] == "e36_pilot_export_v1" and len(d["properties"]) == 1
    fila = d["properties"][0]
    assert fila["floorplan_sha256"] and fila["gold_labels"]["perimeter"]["verdict"] == "CORRECTO"
    assert fila["timings"]["created_at"] and "Incompleto" in fila["negative_tags"]
    for prohibido in ("Apoquindo 3000 · piso 4", "corredora X", "feo", ROOT, "/Users/",
                      "original_filename", "source_reference"):
        assert prohibido not in crudo, prohibido


def test_el_panel_del_piloto_se_ve_solo_en_ajustes(client, dom):
    """§21 — el panel es interno. A quien publica una oficina no le sirve."""
    pid = _prop(dom, "Apoquindo 3000")
    assert "Piloto real" not in client.get("/lab/").get_data(as_text=True)
    assert "Piloto real" not in client.get(f"/lab/p/{pid}").get_data(as_text=True)
    html = client.get("/lab/ajustes/evaluaciones").get_data(as_text=True)
    assert "Piloto real" in html and "Corpus de ambientación" in html


# ===================================================================================================
# 18–20 — NO ROMPER NADA (§26)
# ===================================================================================================
def test_la_independencia_del_nombre_sigue(client, dom):
    """§27.18 — E35 no se deshace: mismo archivo, nombres distintos, mismos candidatos."""
    import hashlib
    from webapp.domain import floorplan
    huellas = set()
    for t in ("Oficina 403 Apoquindo", "Mi oficina", "X"):
        pid = _prop(dom, t)
        sel = dom["units"].resolve(pid, floorplan.ensure_case(pid))
        huellas.add(hashlib.sha256(
            json.dumps(sel["candidates"], sort_keys=True).encode()).hexdigest())
    assert len(huellas) == 1


def test_el_camino_sin_friccion_sigue(client, dom):
    """§27.19 — al crear una propiedad se sigue pidiendo lo mínimo, y nada del QA interno."""
    html = client.get("/lab/new").get_data(as_text=True).lower()
    for prohibido in ("escala", "acceso", "pilar", "núcleo", "source_type", "gold", "piloto"):
        assert prohibido not in html, prohibido
    r = client.post("/lab/new", data={"title": "Mi oficina", "city": "Santiago"},
                    follow_redirects=True)
    pid = re.search(rb"p_[0-9a-f]{12}", r.data).group().decode()
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_ORIGINAL, "p.png", _png(), "image/png")
    for u in ("/lab/", "/lab/new", "/lab/ajustes", "/lab/ajustes/evaluaciones", "/lab/debug",
              "/lab/pilot/export.json", f"/lab/p/{pid}", f"/lab/p/{pid}/revisar-plano"):
        assert client.get(u).status_code == 200, u


def test_la_navegacion_no_crecio(client, dom):
    """§2 / §26 — «Mis propiedades» y «Ajustes». Nada más."""
    html = client.get("/lab/").get_data(as_text=True)
    nav = html.split("</nav>")[0] if "</nav>" in html else html
    assert nav.count('href="/lab/ajustes"') == 1
    for ruta in ("/lab/pilot", "/lab/gold", "/lab/piloto"):
        assert f'href="{ruta}' not in nav, ruta


def test_el_motor_no_se_toco(client, dom):
    """§27.20 — E36 mide; no cambia el motor ni una heurística (§26)."""
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"el motor cambió: {out.stdout}"


def test_no_se_toco_ninguna_heuristica(client, dom):
    """§26 — los umbrales, la banda y el modelo de candidatos quedan donde E35 los dejó."""
    assert dom["ingest"].AUTO_CONFIRM_THRESHOLDS == {"perimeter": 0.60, "core": 0.50,
                                                     "primary_entrance": 0.70, "columns": 0.55,
                                                     "daylight": 0.45}
    assert dom["ingest"].UNCERTAINTY_BAND == {"core": 0.10}
    assert dom["units"].MIN_RELATIVE_AREA == 0.15 and dom["units"].MIN_DRAWING_FRAC == 0.02
    assert dom["calibration"].MIN_SAMPLE == 10
