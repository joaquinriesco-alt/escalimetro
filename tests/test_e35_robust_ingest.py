"""E35 §19 — tests de CONTRATO del ingreso robusto.

Lo que se protege acá es una frase: **el nombre comercial de una propiedad no es un input
geométrico**. Y una segunda, menos vistosa y más importante: los umbrales de autoaceptación no se
dan por buenos porque estén escritos.
"""
from __future__ import annotations

import hashlib
import importlib
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
           "webapp.domain.settings", "webapp.domain.entitlements", "webapp.domain.grants",
           "webapp.domain.presets", "webapp.domain.properties", "webapp.domain.assets",
           "webapp.domain.branding", "webapp.domain.fits", "webapp.domain.floorplan",
           "webapp.domain.proposal", "webapp.domain.visual", "webapp.domain.pilot",
           "webapp.providers.base", "webapp.providers.gemini", "webapp.providers.openai_images",
           "webapp.providers.bfl", "webapp.providers", "webapp.domain.staging",
           "webapp.domain.packs", "webapp.domain.reviews", "webapp.domain.units",
           "webapp.domain.interventions", "webapp.domain.ingest", "webapp.domain.calibration",
           "webapp.domain.lab", "webapp.benchmark", "webapp.customer", "webapp.staging_ui",
           "webapp.lab", "webapp.app")

PLANO_403 = os.path.join(ROOT, "cases", "001_gps_403", "original.png")
PLANO_RES = os.path.join(ROOT, "cases", "003_res_unknown", "original.png")
FLOORPLATE_403 = os.path.join(ROOT, "cases", "001_gps_403", "outputs", "pass_a", "floorplate.json")


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
    from webapp.domain import (assets, calibration, ingest, interventions, lab, properties,
                               reviews, units)
    return {"assets": assets, "calibration": calibration, "ingest": ingest, "lab": lab,
            "interventions": interventions, "properties": properties, "reviews": reviews,
            "units": units}


def _con_plano(dom, titulo, plano=PLANO_403, area=None):
    pid = dom["properties"].create(title=titulo, city="Santiago", published_area_m2=area)
    with open(plano, "rb") as fh:
        dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_ORIGINAL, "plano.png", fh.read(),
                                 "image/png")
    return pid


def _huella(cands) -> str:
    return hashlib.sha256(json.dumps(cands, sort_keys=True).encode()).hexdigest()


# ===================================================================================================
# 1–2 — EL NOMBRE NO ES UN INPUT GEOMÉTRICO
# ===================================================================================================
def test_el_titulo_no_altera_la_geometria_seleccionada(dom):
    """§19.1 — `analyze` sólo recibe la lámina. No hay forma de pasarle el título ni por error."""
    import inspect
    firma = inspect.signature(dom["units"].analyze)
    assert set(firma.parameters) == {"image_path", "declared_scope", "human_override"}
    a = dom["units"].analyze(PLANO_403)
    b = dom["units"].analyze(PLANO_403)
    assert _huella(a["candidates"]) == _huella(b["candidates"])


def test_mismo_archivo_tres_nombres_mismo_candidato(client, dom):
    """§19.2 / §18 A-B-C — «Oficina 403 Apoquindo», «Mi oficina» y «X» sobre el MISMO archivo
    tienen que llegar a la misma lista de candidatos, con el mismo orden y la misma decisión."""
    huellas, decisiones = set(), set()
    for titulo in ("Oficina 403 Apoquindo", "Mi oficina", "X"):
        pid = _con_plano(dom, titulo, area=543.0)
        from webapp.domain import floorplan
        cid = floorplan.ensure_case(pid)
        sel = dom["units"].resolve(pid, cid)
        huellas.add(_huella(sel["candidates"]))
        decisiones.add((sel["status"], sel["candidate_count"]))
    assert len(huellas) == 1, "el nombre cambió la lista de candidatos"
    assert decisiones == {("NEEDS_INTERNAL_REVIEW", 3)}


def test_el_pipeline_no_ve_el_titulo_cuando_hay_seleccion(client, dom):
    """§7 — con la unidad resuelta se apaga el intérprete de visión. No alcanza con que
    `seed_points` tenga prioridad: mientras el OCR corra, el título sigue decidiendo la estrategia
    de segmentación por la puerta de atrás (`has_color_hint`)."""
    from webapp import intake
    from webapp.domain import floorplan
    pid = _con_plano(dom, "Oficina 403 Apoquindo", area=543.0)
    cid = floorplan.ensure_case(pid)
    dom["units"].resolve(pid, cid)
    dom["units"].pick(pid, "u1")
    intake.write_case_json(cid)
    intake.write_overrides(cid)
    with open(os.path.join(__import__("webapp").store.case_dir(cid), "case.json"),
              encoding="utf-8") as fh:
        caso = json.load(fh)
    with open(os.path.join(__import__("webapp").store.case_dir(cid), "overrides.json"),
              encoding="utf-8") as fh:
        ov = json.load(fh)
    assert caso["vision"] == "null", "el OCR por rótulo sigue encendido"
    assert caso["unit_label"] == "Oficina 403 Apoquindo", "el título se conserva como metadata"
    assert ov["seed_points"] and ov["segmentation_params"]["mode"] == "color"


# ===================================================================================================
# 3–4 — RANKING Y AMBIGÜEDAD
# ===================================================================================================
def test_el_ranking_de_candidatos_es_determinista(dom):
    """§19.3 — mismo archivo, misma lista, mismos ids, mismo orden."""
    a = dom["units"].candidates(PLANO_403)
    b = dom["units"].candidates(PLANO_403)
    assert [c["candidate_id"] for c in a] == ["u1", "u2", "u3"]
    assert [c["pixel_area"] for c in a] == sorted([c["pixel_area"] for c in a], reverse=True)
    assert _huella(a) == _huella(b)


def test_el_modelo_guarda_la_evidencia_de_cada_candidato(dom):
    """§4 — candidate_id, evidencia geométrica, rótulos OCR, área, acceso, núcleo, razones."""
    for c in dom["units"].candidates(PLANO_403):
        for k in ("candidate_id", "geometry_evidence", "ocr_labels", "pixel_area",
                  "relative_area", "access_evidence", "core_relationship", "reason_codes"):
            assert k in c, k
        assert c["geometry_evidence"]["contour"], "sin contorno no se puede pintar el candidato"


def test_varios_candidatos_van_a_revision_nunca_al_mas_grande(dom):
    """§19.4 / §12 — la lámina de GPS tiene tres unidades y la 401 (una propiedad real de este
    repositorio) NO es la más grande. Elegir por área produciría el plano de la oficina de al lado
    sin avisar: el falso acepto que §12 pone por encima de cualquier cobertura."""
    d = dom["units"].analyze(PLANO_403)
    assert d["status"] == dom["units"].NEEDS_INTERNAL_REVIEW
    assert d["selected_candidate_id"] is None and d["source"] is None
    assert dom["units"].R_DOMINANCE_UNCALIBRATED in d["reason_codes"]


def test_una_sola_region_se_autoselecciona(dom):
    """§5 — cuando no hay entre qué elegir, no se molesta a nadie. El plano de RES no demarca
    unidades por color: el objetivo es el dibujo completo."""
    d = dom["units"].analyze(PLANO_RES)
    assert d["status"] == dom["units"].RESOLVED
    assert d["source"] == dom["units"].AUTO
    assert dom["units"].R_NO_DEMARCATION in d["reason_codes"]


def test_la_declaracion_de_la_fuente_manda(dom):
    """E16.5 — `drawing_scope` es un hecho de entrada. Si la fuente ya lo declaró, no se infiere."""
    d = dom["units"].analyze(PLANO_403, declared_scope="whole_shell")
    assert d["source"] == dom["units"].DECLARED and d["candidate_count"] == 1


# ===================================================================================================
# 5–6 — EL CLIC
# ===================================================================================================
def test_el_clic_humano_se_persiste(client, dom):
    """§19.5 — un clic, y queda registrado COMO clic: `HUMAN_PICK`, no `AUTO`."""
    from webapp.domain import floorplan
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    cid = floorplan.ensure_case(pid)
    dom["units"].resolve(pid, cid)
    d = dom["units"].pick(pid, "u2")
    assert d["source"] == dom["units"].HUMAN_PICK and d["selected_candidate_id"] == "u2"
    assert dom["units"].get(pid)["status"] == dom["units"].RESOLVED
    assert dom["units"].selected(pid)["candidate_id"] == "u2"


def test_un_reanalisis_no_borra_el_clic(client, dom):
    """§19.6 — después del clic el pipeline sigue solo, y volver a analizar no deshace la decisión
    de una persona."""
    from webapp.domain import floorplan
    pid = _con_plano(dom, "X", area=543.0)
    cid = floorplan.ensure_case(pid)
    dom["units"].resolve(pid, cid)
    dom["units"].pick(pid, "u3")
    de_nuevo = dom["units"].resolve(pid, cid)
    assert de_nuevo["source"] == dom["units"].HUMAN_PICK
    assert de_nuevo["selected_candidate_id"] == "u3"


def test_el_clic_se_ofrece_en_la_pagina_y_no_en_un_menu_nuevo(client, dom):
    """§16 / §20 — la pregunta vive DENTRO de la página de la propiedad. Sin navegación nueva."""
    from webapp.domain import floorplan
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    cid = floorplan.ensure_case(pid)
    dom["units"].resolve(pid, cid)
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    assert "¿Cuál es la oficina?" in html
    assert f"/lab/p/{pid}/elegir-oficina" in html
    nav = client.get("/lab/").get_data(as_text=True)
    assert nav.count('href="/lab/ajustes"') == 1
    assert "elegir-oficina" not in nav, "la pregunta no es un ítem de navegación"


def test_la_lamina_con_candidatos_se_puede_ver(client, dom):
    """§6 — 2–N candidatos coloreados sobre la lámina: la imagen ES la interfaz."""
    from webapp.domain import floorplan
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    dom["units"].resolve(pid, floorplan.ensure_case(pid))
    r = client.get(f"/lab/p/{pid}/candidatos.png")
    assert r.status_code == 200 and r.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_el_candidato_desconocido_se_rechaza(client, dom):
    from webapp.domain import floorplan
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    dom["units"].resolve(pid, floorplan.ensure_case(pid))
    with pytest.raises(dom["units"].UnitError):
        dom["units"].pick(pid, "u99")


# ===================================================================================================
# 7–9 — ESCALA
# ===================================================================================================
def test_la_escala_espera_a_la_seleccion_de_unidad(dom):
    """§19.7 / §8 — `sqrt(área_px / área publicada)` sólo significa algo si el área en píxeles es
    la de ESTA oficina. Sin unidad elegida, la superficie publicada no se acepta."""
    with open(FLOORPLATE_403, encoding="utf-8") as fh:
        fp = json.load(fh)
    con = dom["ingest"].decide(fp, unit_resolved=True)
    sin = dom["ingest"].decide(fp, unit_resolved=False)
    assert con["scale_source"] == dom["ingest"].PUBLISHED_AREA
    assert sin["scale_source"] == dom["ingest"].UNKNOWN
    assert sin["blocked_on"] == dom["ingest"].UNIT_NOT_SELECTED
    assert sin["needs_review"] is True


def test_sin_unidad_resuelta_el_ingest_no_corre_el_motor(client, dom):
    """§8 — el orden es unidad → escala → contraste, y se cumple en el flujo real, no sólo en la
    función pura."""
    from webapp.domain import floorplan
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    floorplan.ensure_case(pid)
    d = dom["ingest"].auto_prepare(pid)
    assert d["blocked_on"] == "unit_selection"
    assert d["scale_source"] == dom["ingest"].UNKNOWN and d["scale_value"] is None


def test_la_escala_por_area_publicada_usa_el_poligono_elegido(client, dom):
    """§19.8 / §18 E — la 403 con superficie publicada da la misma escala se llame como se llame,
    y esa escala sale del polígono que se eligió."""
    from webapp import intake
    from webapp.domain import floorplan
    escalas, areas = set(), set()
    for titulo in ("Oficina 403 Apoquindo", "Mi oficina", "X"):
        pid = _con_plano(dom, titulo, area=543.0)
        cid = floorplan.ensure_case(pid)
        dom["units"].resolve(pid, cid)
        dom["units"].pick(pid, "u1")
        d = dom["ingest"].auto_prepare(pid)
        fp = intake.load_floorplate(cid)
        assert d["scale_source"] == dom["ingest"].PUBLISHED_AREA
        escalas.add(round(d["scale_value"], 6))
        areas.add(round(fp["area_m2"]))
    assert len(escalas) == 1, f"el nombre cambió la escala: {escalas}"
    assert areas == {543}, f"no se midió la unidad elegida: {areas}"


def test_la_escala_por_puertas_queda_marcada_como_no_apta(dom):
    """§19.9 / §10 — se conserva como señal débil y se dice que no es apta para producto."""
    with open(FLOORPLATE_403, encoding="utf-8") as fh:
        fp = json.load(fh)
    d = dom["ingest"].decide(fp)
    assert d["door_scale_status"] == dom["ingest"].DOOR_SCALE_NOT_PRODUCT_READY
    assert d["scale_source"] != dom["ingest"].AUTO_DOOR
    solo_puertas = dict(fp, scale={})
    dd = dom["ingest"].decide(solo_puertas)
    if dd["scale_source"] == dom["ingest"].AUTO_DOOR:
        assert dom["ingest"].DOOR_SCALE_NOT_PRODUCT_READY in dd["notes"]


# ===================================================================================================
# 10–13 — CALIBRACIÓN
# ===================================================================================================
def test_se_calculan_las_metricas_de_autoaceptacion(dom):
    """§19.10 / §12 — precisión y cobertura POR COMPONENTE. Nunca un accuracy global."""
    m = dom["calibration"].metrics()
    assert m["components"], "el dataset de calibración está vacío"
    assert "accuracy" not in m
    for c in m["components"]:
        for k in ("auto_accept_precision", "auto_accept_coverage", "sample_count",
                  "false_accept", "visibility"):
            assert k in c, k


def test_los_falsos_aceptos_se_cuentan_aparte_de_los_incompletos(dom):
    """§19.11 — que el motor se equivoque y que se quede corto no son lo mismo, y meterlos en la
    misma bolsa inflaría o desinflaría la precisión según convenga."""
    filas = [
        {"component": "primary_entrance", "engine_confidence": 0.95,
         "human_verdict": dom["calibration"].DISAGREES},
        {"component": "primary_entrance", "engine_confidence": 0.90,
         "human_verdict": dom["calibration"].CORRECTED_INCOMPLETE},
        {"component": "primary_entrance", "engine_confidence": 0.80,
         "human_verdict": dom["calibration"].CONFIRMED},
    ]
    c = dom["calibration"].metrics(filas)["components"][0]
    assert c["false_accept"] == 1 and c["accepted_incomplete"] == 1 and c["true_accept"] == 1
    assert c["auto_accept_precision"] == round(1 / 3, 3)


def test_el_acceso_principal_tiene_un_falso_acepto_medido(dom):
    """§11 — el hallazgo que no se puede tapar: el componente con la confianza MÁS ALTA del
    sistema (0.95 y 0.90) acertó una de dos sobre las marcas humanas de este repositorio."""
    acc = next(c for c in dom["calibration"].metrics()["components"]
               if c["component"] == "primary_entrance")
    assert acc["false_accept"] >= 1
    assert acc["auto_accept_precision"] is not None and acc["auto_accept_precision"] < 1.0


def test_los_umbrales_se_declaran_no_calibrados(dom):
    """§19.12 / §13 — con muestra insuficiente NO se propone ningún umbral nuevo. «La 403 sola no
    valida un threshold»."""
    p = dom["calibration"].proposal()
    assert p["status"] == dom["ingest"].THRESHOLD_UNCALIBRATED
    assert p["proposed"] is None
    assert p["current"] == dom["ingest"].AUTO_CONFIRM_THRESHOLDS
    m = dom["calibration"].metrics()
    for c in m["components"]:
        if c["effective_threshold"] is not None:
            assert c["sample_count"] < dom["calibration"].MIN_SAMPLE or not c["threshold_exercised"]


def test_el_nucleo_en_la_banda_va_a_revision(dom):
    """§19.13 / §14 — 0.50 contra un umbral de 0.50 no es una medición, es un redondeo."""
    with open(FLOORPLATE_403, encoding="utf-8") as fh:
        fp = json.load(fh)
    assert dom["ingest"].element_confidences(fp)["core"] == 0.50
    assert dom["ingest"].AUTO_CONFIRM_THRESHOLDS["core"] == 0.50
    assert dom["ingest"].UNCERTAINTY_BAND["core"] > 0
    auto = dom["ingest"].auto_confirmations(fp)
    assert "perimeter/core" in auto["pending"]
    assert auto["detail"]["perimeter/core"]["core"]["verdict"] == "IN_UNCERTAINTY_BAND"
    assert auto["detail"]["perimeter/core"]["perimeter"].get("verdict") is None


def test_un_nucleo_holgado_si_se_acepta(dom):
    """La banda no es un rechazo permanente: un núcleo que supera la vara con margen pasa."""
    with open(FLOORPLATE_403, encoding="utf-8") as fh:
        fp = json.load(fh)
    fp = dict(fp, core=[dict(c, meta=dict(c.get("meta", {}), confidence=0.85))
                        for c in fp["core"]])
    assert "perimeter/core" in dom["ingest"].auto_confirmations(fp)["accept"]


# ===================================================================================================
# 14–15 — FEEDBACK E INTERVENCIONES
# ===================================================================================================
def test_el_feedback_guarda_la_procedencia_del_ingest(client, dom):
    """§19.14 / §15 — un «PÉSIMO» tiene que poder distinguir un motor malo de una unidad mal
    elegida o de una escala supuesta."""
    from webapp.domain import floorplan
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    cid = floorplan.ensure_case(pid)
    dom["units"].resolve(pid, cid)
    dom["units"].pick(pid, "u1")
    dom["ingest"].auto_prepare(pid)
    client.post(f"/lab/p/{pid}/evaluar",
                data={"artifact_type": "PLANO", "rating": "MALO", "back": "#pack1"})
    from webapp import store
    r = store.q1("SELECT * FROM product_reviews WHERE property_id=?", (pid,))
    assert r["unit_selection_source"] == dom["units"].HUMAN_PICK
    assert r["unit_selection_confidence"] == 1.0
    assert r["scale_source"] == dom["ingest"].PUBLISHED_AREA
    assert json.loads(r["geometry_confidences"])["perimeter"] > 0


def test_las_intervenciones_manuales_se_cuentan_con_su_motivo(client, dom):
    """§19.15 / §17 — saber cuántas veces el flujo «automático» necesitó de verdad un humano."""
    iv = dom["interventions"]
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    assert iv.count(pid) == 0
    iv.record(pid, iv.UNIT_SELECTION, "eligió la oficina")
    iv.record(pid, iv.GEOMETRY, "confirmó el contorno")
    iv.record(pid, iv.GEOMETRY, "otra vez")
    assert iv.count(pid) == 3
    # Se comprueban los conteos y que NINGÚN motivo del vocabulario quede sin fila: un cero es
    # información. No se fija el diccionario completo, porque ampliar el vocabulario -E36 agrega
    # ACCESS- es una extensión legítima y no debería romper esto.
    c = iv.by_reason(pid)
    assert set(c) == set(iv.REASONS)
    assert c["UNIT_SELECTION"] == 1 and c["GEOMETRY"] == 2 and c["SCALE"] == 0
    with pytest.raises(iv.InterventionError):
        iv.record(pid, "LO_QUE_SEA")
    s = iv.summary()
    assert s["with_intervention"] == 1 and s["by_reason"]["GEOMETRY"] == 2


def test_el_clic_sobre_la_lamina_queda_contado(client, dom):
    """El contador no es decorativo: la ruta real lo escribe."""
    from webapp.domain import floorplan
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    dom["units"].resolve(pid, floorplan.ensure_case(pid))
    client.post(f"/lab/p/{pid}/elegir-oficina", data={"candidate_id": "u1"})
    assert dom["interventions"].by_reason(pid)["UNIT_SELECTION"] == 1


def test_el_contador_solo_se_ve_en_ajustes(client, dom):
    """§17 — «Mostrar sólo en Ajustes/Evaluaciones. No en UI principal.»"""
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    dom["interventions"].record(pid, dom["interventions"].UNIT_SELECTION, "x")
    assert "hizo falta una persona" not in client.get(f"/lab/p/{pid}").get_data(as_text=True)
    assert "hizo falta una persona" not in client.get("/lab/").get_data(as_text=True)
    assert "hizo falta una persona" in client.get("/lab/ajustes/evaluaciones").get_data(as_text=True)


# ===================================================================================================
# 16–18 — NO ROMPER LO QUE YA FUNCIONABA
# ===================================================================================================
def test_el_camino_sin_friccion_de_e34_sigue_en_pie(client, dom):
    """§19.16 — al crear una propiedad se sigue pidiendo lo mínimo: nombre, plano y fotos."""
    html = client.get("/lab/new").get_data(as_text=True)
    for prohibido in ("escala", "acceso", "pilar", "núcleo", "limpia", "declared_clean",
                      "unit id", "coordenada"):
        assert prohibido not in html.lower(), prohibido
    r = client.post("/lab/new", data={"title": "Mi oficina", "city": "Santiago"},
                    follow_redirects=True)
    pid = re.search(rb"p_[0-9a-f]{12}", r.data).group().decode()
    dom["assets"].save_bytes(pid, dom["assets"].FLOORPLAN_ORIGINAL, "p.png", _png(), "image/png")
    for u in ("/lab/", "/lab/new", "/lab/ajustes", "/lab/ajustes/evaluaciones", "/lab/debug",
              f"/lab/p/{pid}", f"/lab/p/{pid}/status.json", f"/lab/p/{pid}/revisar-plano"):
        assert client.get(u).status_code == 200, u


def test_pack2_no_cambia(client, dom):
    """§19.17 — Pack 2 sigue siendo el mismo: cliente + personas, sin nada de E35 encima."""
    pid = _con_plano(dom, "Mi oficina", area=543.0)
    html = client.get(f"/lab/p/{pid}").get_data(as_text=True)
    assert "Pack 2 — Propuesta para un cliente" in html
    assert "candidate_id" not in html.split("Pack 2 — Propuesta")[1]


def test_el_motor_no_se_toco(dom):
    """§19.18 / §20 — E35 no modifica `src/`. Toda la robustez vive en la aplicación y entra al
    motor por el vocabulario HITL que ya existía."""
    out = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", f"el motor cambió: {out.stdout}"


def test_el_dataset_de_calibracion_declara_su_procedencia(dom):
    """Una tabla de auditoría sin procedencia no se puede auditar: cada fila dice de qué artefacto
    salió la confianza y de qué archivo salió la etiqueta humana."""
    d = dom["calibration"].dataset()
    assert d["rows"]
    for r in d["rows"]:
        assert r.get("confidence_provenance"), r
        assert "label_provenance" in r, r
