"""E45 — web piloto de la campaña E44: rutas, auth, subida, integración con E44, ceguera, reveal,
evaluaciones con historial, conteo honesto y humo responsive.

Todo el material es de PRUEBA (PNG sintéticos). Los casos DEMO existen sólo para fotografiar la
interfaz y jamás cuentan. Ningún test sale a la red ni gasta: el motor «real» de CREAR es un
adaptador de prueba que hereda del fixture (la campaña rechaza el fixture como motor de un caso real).
"""
from __future__ import annotations

import base64
import importlib
import io
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_e37_reconstruction_lab import (MODULOS, _foto, _plano_de_galeria,  # noqa: E402
                                         _plano_real)

BASE = "/lab/campaign/e44"
AUTH = {"Authorization": "Basic " + base64.b64encode(b"joaquin:secreta").decode()}
GT_NOMBRE = "SECRETO_GT_7781.png"
MODS = tuple(m for m in MODULOS if m != "webapp.app") + ("webapp.campaign", "webapp.pilot",
                                                         "webapp.app")
JERGA = ("motor", "adapter", "readiness", "sha256", "hash", "pipeline", "ground truth",
         "ground_truth", "benchmark", "heurística", "heuristica", "contrato", "openai", "hidden_from",
         "fixture", "e44", "e37")


def _arrancar(tmp_path, monkeypatch, *, password: str = ""):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ESCALIMETRO_DEV", "1" if not password else "")
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", password)
    monkeypatch.setenv("ESCALIMETRO_USER", "joaquin")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    monkeypatch.setenv("ESCALIMETRO_RECON_FIXTURE", "1")
    for v in ("GEMINI_API_KEY", "OPENAI_API_KEY", "BFL_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    for m in MODS:
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    c = create_app().test_client()
    c.environ_base["HTTP_ORIGIN"] = "http://localhost"      # como un navegador
    return c


@pytest.fixture()
def env(tmp_path, monkeypatch):
    c = _arrancar(tmp_path, monkeypatch)
    from webapp import campaign, pilot
    from webapp.domain.reconstruction import engines, runs
    from webapp.domain.reconstruction.engines import fixture

    class MotorDePrueba(fixture.FixtureReplay):
        """Se comporta como el fixture pero NO se llama fixture: es el motor «real» de los tests."""
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

    engines.register(MotorDePrueba())
    monkeypatch.setattr(pilot, "CREATE_ENGINE", "motor_de_prueba")
    # la cola de E37 corre en un hilo: en los tests se ejecuta en el acto, y el caso se asienta al ver la página
    monkeypatch.setattr(runs, "enqueue", lambda rid: runs.execute(rid))
    yield c, campaign, tmp_path
    engines.unregister("motor_de_prueba")


@pytest.fixture()
def planta_lista(monkeypatch):
    """Sustituye SÓLO el análisis de la planta (necesita el motor y una lámina real) y el trazado:
    el resto —ensure_case, technical_state, publish_commercial_floorplan, assets— corre de verdad."""
    from webapp import store
    from webapp.domain import commercial, floorplan, ingest, properties

    llamadas = []

    def auto_prepare(pid):
        cid = properties.require(pid)["floorplan_case_id"]
        d = os.path.join(store.case_dir(cid), "outputs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
            json.dump({"shell_readiness": {"ready_for_layout": True, "requires_confirmation": []}}, fh)
        return {"ready": True}

    class _A:
        area = 50.0

    class _S:
        usable = _A()

    monkeypatch.setattr(ingest, "auto_prepare", auto_prepare)
    monkeypatch.setattr(floorplan, "_shell_of", lambda cid: _S())
    monkeypatch.setattr(commercial, "commercial_svg", lambda *a, **k: (
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30">'
        '<rect width="40" height="30" fill="#fff" stroke="#000"/></svg>'))
    orig = floorplan.publish_commercial_floorplan

    def espia(pid):
        llamadas.append(pid)
        return orig(pid)
    monkeypatch.setattr(floorplan, "publish_commercial_floorplan", espia)
    return llamadas


@pytest.fixture()
def planta_no_lista(monkeypatch):
    """El análisis corre y deja pendiente la confirmación humana (lo habitual en una lámina real)."""
    from webapp.domain import ingest
    monkeypatch.setattr(ingest, "auto_prepare", lambda pid: {"ready": False})


def _plano():
    return _plano_de_galeria()


def _subir_mejorar(c, blob=None, nombre="plano.png"):
    return c.post(f"{BASE}/mejorar", data={"plano": (io.BytesIO(blob or _plano()), nombre)},
                  content_type="multipart/form-data")


def _subir_crear(c, n=3, gt=None, gt_nombre=GT_NOMBRE, **extra):
    data = {"fotos": [(io.BytesIO(_foto(i)), f"IMG_{i}.png") for i in range(n)],
            "plano_real": (io.BytesIO(gt if gt is not None else _plano_real()), gt_nombre), **extra}
    return c.post(f"{BASE}/crear", data=data, content_type="multipart/form-data")


def _cid(r):
    assert r.status_code == 303, r.get_data(as_text=True)[:400]
    return r.headers["Location"].rsplit("/", 1)[1]


def _html(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def _eval_plano(c, cid, **kw):
    d = {"rating": "BUENO", "publicaria": "si", "correccion_humana": "no", "minutos": "4",
         "comentario": "limpio"}
    return c.post(f"{BASE}/caso/{cid}/evaluar/plano", data={**d, **kw})


def _eval_ux(c, cid, **kw):
    d = {"rating": "MALO", "entendi": "no", "comentario": "no sabía dónde subir",
         "sobraba": "el aviso", "faltaba": "un ejemplo"}
    return c.post(f"{BASE}/caso/{cid}/evaluar/ux", data={**d, **kw})


# ---- rutas y auth ------------------------------------------------------------------------------
def test_toda_la_superficie_exige_basic_auth(tmp_path, monkeypatch):
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    cid = "e44-imp-0123456789"
    for metodo, url in (("get", "/"), ("get", "/panel"), ("get", "/mejorar"),
                        ("get", "/crear"), ("post", "/mejorar"), ("post", "/crear"),
                        ("get", f"/caso/{cid}"), ("post", f"/caso/{cid}/procesar"),
                        ("post", f"/caso/{cid}/corregir"), ("post", f"/caso/{cid}/cerrar"),
                        ("post", f"/caso/{cid}/evaluar/plano"), ("post", f"/caso/{cid}/evaluar/ux"),
                        ("get", f"/caso/{cid}/archivo/real"), ("get", f"/caso/{cid}/archivo/despues")):
        assert getattr(c, metodo)(BASE + url).status_code == 401, (metodo, url)
    assert c.get(BASE + "/", headers=AUTH).status_code == 200
    assert c.get(BASE + "/panel", headers=AUTH).status_code == 200


def test_la_superficie_publica_no_cambia(tmp_path, monkeypatch):
    """/planos/ sigue abierta y /healthz también; la web piloto no la contamina."""
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    assert c.get("/planos/").status_code == 200
    assert "pilot" not in c.get("/planos/").get_data(as_text=True).lower()


def test_un_post_sin_origen_se_rechaza(env):
    c, _camp, _ = env
    c.environ_base.pop("HTTP_ORIGIN")
    r = c.post(f"{BASE}/mejorar", data={"plano": (io.BytesIO(_plano()), "p.png")},
               content_type="multipart/form-data")
    assert r.status_code == 403


def test_caso_inexistente_o_malformado_da_404(env):
    c, _camp, _ = env
    for cid in ("e44-imp-0000000000", "../../etc/passwd", "x"):
        assert c.get(f"{BASE}/caso/{cid}").status_code == 404


# ---- primera pantalla --------------------------------------------------------------------------
def test_la_primera_pantalla_distingue_mejorar_y_crear_sin_jerga(env):
    c, _camp, _ = env
    h = _html(c, BASE + "/")
    assert "¿Qué necesitas hacer?" in h
    assert "MEJORAR UN PLANO" in h and "CREAR UN PLANO" in h
    assert "Ya tengo un plano. Quiero dejarlo limpio y listo para publicar." in h
    assert "No tengo un plano útil. Quiero crear uno a partir de fotos e información de la propiedad." in h
    assert 'href="/lab/campaign/e44/mejorar"' in h and 'href="/lab/campaign/e44/crear"' in h
    bajo = h.lower()
    visible = re.sub(r"<[^>]+>", " ", bajo)                  # las URL sí llevan el id de la campaña
    for palabra in tuple(p for p in JERGA if p != "e44") + ("benchmark", "pipeline"):
        assert palabra not in visible, palabra
    assert "e44" not in visible


# ---- MEJORAR: subida y alta del caso E44 -------------------------------------------------------
def test_mejorar_crea_un_caso_e44_con_provenance(env):
    c, camp, _ = env
    cid = _cid(_subir_mejorar(c, nombre="Mi Plano Final (1).PNG"))
    caso = camp.get(cid)
    assert caso["track"] == "IMPROVE" and caso["origin"] == "WEB_UPLOAD" and not caso["demo"]
    assert caso["source"] and caso["captured_on"] and caso["property_type"] == "OFFICE"
    a = caso["assets"]
    assert len(a) == 1 and a[0]["role"] == "published_plan" and len(a[0]["sha256"]) == 64
    assert a[0]["file"] == "plano.png"                      # el nombre del usuario no se conserva
    assert camp.materials_ok(caso)
    assert camp.status(caso) == camp.CAPTURED
    ev = os.path.join(camp.case_dir(cid), "evidence", "plano.png")
    assert os.stat(ev).st_mode & 0o222 == 0                  # evidencia inmutable
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "MATERIAL CARGADO" in h and "PROCESAR" in h
    assert "Mi Plano Final" not in h


def test_mejorar_rechaza_sin_dejar_caso(env):
    c, camp, _ = env
    assert _subir_mejorar(c, _plano(), "x.pdf").status_code == 400       # un PNG que dice ser PDF
    assert _subir_mejorar(c, _plano(), "plano.docx").status_code == 400
    assert c.post(f"{BASE}/mejorar", data={"plano": (io.BytesIO(b""), "vacio.png")},
                  content_type="multipart/form-data").status_code == 400
    assert c.post(f"{BASE}/mejorar", data={}, content_type="multipart/form-data").status_code == 400
    assert camp.load()["cases"] == []
    assert camp.count("IMPROVE")["captured"] == 0


def test_subir_dos_veces_el_mismo_plano_es_duplicado_y_apunta_al_existente(env):
    c, camp, _ = env
    cid = _cid(_subir_mejorar(c))
    r = _subir_mejorar(c, nombre="otro-nombre.png")
    assert r.status_code == 400
    h = r.get_data(as_text=True)
    assert "duplicado" in h and cid in h and "ABRIR EL CASO EXISTENTE" in h
    assert len(camp.load()["cases"]) == 1


# ---- MEJORAR: integración con el camino real ---------------------------------------------------
def test_mejorar_procesa_por_el_camino_real_y_muestra_antes_despues(env, planta_lista):
    c, camp, _ = env
    cid = _cid(_subir_mejorar(c))
    r = c.post(f"{BASE}/caso/{cid}/procesar")
    assert r.status_code == 303
    assert len(planta_lista) == 1                            # publish_commercial_floorplan de verdad
    caso = camp.get(cid)
    assert camp.status(caso) == camp.EXECUTED
    p = camp.events(cid)[-1]
    assert p["kind"] == "pipeline" and p["data"]["reached_output"] is True
    assert "ingest.auto_prepare" in p["data"]["path"] and "publish_commercial_floorplan" in p["data"]["path"]
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "RESULTADO LISTO" in h and ">ANTES<" in h and "DESPUÉS" in h
    assert "ABRIR PLANO CORPORATIVO" in h and "DESCARGAR" in h
    antes = c.get(f"{BASE}/caso/{cid}/archivo/entrada")
    despues = c.get(f"{BASE}/caso/{cid}/archivo/despues")
    assert antes.status_code == despues.status_code == 200
    assert despues.mimetype == "image/png" and despues.get_data()[:4] == b"\x89PNG"
    assert "no-store" in despues.headers["Cache-Control"]
    dl = c.get(f"{BASE}/caso/{cid}/archivo/despues?descargar=1")
    assert "attachment" in dl.headers["Content-Disposition"]
    # procesar de nuevo no duplica la propiedad ni reescribe el resultado
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code in (303, 409)
    assert len(camp.events(cid)) == 2                        # improve_started + pipeline


def test_mejorar_sin_planta_lista_pide_revision_y_no_finge_resultado(env, planta_no_lista):
    c, camp, _ = env
    cid = _cid(_subir_mejorar(c))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "NECESITA REVISIÓN" in h and "REVISAR EN EL LAB" in h and "VOLVER A INTENTAR" in h
    assert "DESPUÉS" not in h
    assert c.get(f"{BASE}/caso/{cid}/archivo/despues").status_code == 404
    assert [e["kind"] for e in camp.events(cid)] == ["improve_started"]
    assert camp.count("IMPROVE")["executed"] == 0
    # darlo por no resuelto queda escrito como NO resultado, y se puede evaluar
    assert c.post(f"{BASE}/caso/{cid}/sin-resultado").status_code == 303
    p = camp.events(cid)[-1]
    assert p["kind"] == "pipeline" and p["data"]["reached_output"] is False and p["data"]["error"]
    assert "SIN RESULTADO" in _html(c, f"{BASE}/caso/{cid}")
    assert camp.summary()["tracks"]["IMPROVE"]["pipeline_success"] == {"reached_output": 0,
                                                                       "executed": 1}
    assert c.post(f"{BASE}/caso/{cid}/sin-resultado").status_code in (303, 409)


def test_reintentar_recoge_la_confirmacion_hecha_en_el_lab(env, planta_no_lista, monkeypatch):
    c, camp, _ = env
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    assert "NECESITA REVISIÓN" in _html(c, f"{BASE}/caso/{cid}")
    # una persona confirma en el LAB: ahora el análisis deja la planta lista
    from webapp import store
    from webapp.domain import commercial, floorplan, ingest, properties
    pid = camp.events(cid)[0]["data"]["property_id"]
    mc = properties.require(pid)["floorplan_case_id"]
    d = os.path.join(store.case_dir(mc), "outputs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
        json.dump({"shell_readiness": {"ready_for_layout": True, "requires_confirmation": []}}, fh)

    class _S:
        class usable:
            area = 40.0
    monkeypatch.setattr(floorplan, "_shell_of", lambda cid_: _S())
    monkeypatch.setattr(commercial, "commercial_svg", lambda *a, **k: (
        '<svg xmlns="http://www.w3.org/2000/svg" width="9" height="9"><rect width="9" height="9"/></svg>'))
    monkeypatch.setattr(ingest, "auto_prepare", lambda p: (_ for _ in ()).throw(AssertionError))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert camp.status(camp.get(cid)) == camp.EXECUTED
    assert "ANTES" in _html(c, f"{BASE}/caso/{cid}")


def test_el_analisis_real_de_una_lamina_sin_unidad_clara_no_inventa_resultado(env):
    """Sin sustituir nada: el camino real sobre una lámina sintética. Sea cual sea su desenlace
    (revisión o no resuelto), nunca aparece un Plano Corporativo que el motor no produjo."""
    c, camp, _ = env
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    ev = [e["kind"] for e in camp.events(cid)]
    assert ev[0] == "improve_started"
    pip = [e for e in camp.events(cid) if e["kind"] == "pipeline"]
    if pip:
        assert pip[0]["data"]["reached_output"] == (pip[0]["data"].get("output_asset_id") is not None)
    else:
        assert c.get(f"{BASE}/caso/{cid}/archivo/despues").status_code == 404


# ---- CREAR: subida, plano real separado y oculto -----------------------------------------------
def test_crear_acepta_varias_fotos_y_deja_el_plano_real_oculto(env):
    c, camp, _ = env
    cid = _cid(_subir_crear(c, n=4, m2="118,5", referencia="Oficina luminosa en piso 5"))
    caso = camp.get(cid)
    assert caso["track"] == "CREATE" and caso["origin"] == "WEB_UPLOAD"
    assert [a["role"] for a in caso["assets"]] == ["photo"] * 4
    assert [a["file"] for a in caso["assets"]] == [f"foto_0{i}.png" for i in range(1, 5)]
    assert caso["published_m2"] == 118.5 and caso["declared"]["description"].startswith("Oficina")
    assert caso["has_ground_truth"] and caso["source_urls"] == []
    from webapp.domain.reconstruction import groundtruth, projects
    pid = caso["recon_project_id"]
    assert projects.get(pid)["gt_state"] == "HIDDEN_FROM_ENGINE" == groundtruth.HIDDEN
    p = projects.get(pid)
    assert p["declared"] if "declared" in p else True
    assert len(projects.assets_of(pid, projects.PHOTO)) == 4
    # el plano real no está entre los inputs ni en la evidencia ni en el manifiesto
    from webapp import store
    gt = store.q1("SELECT sha256 FROM recon_ground_truth WHERE project_id=?", (pid,))
    assert all(a["sha256"] != gt["sha256"] for a in projects.assets_of(pid, include_retired=True))
    assert gt["sha256"] not in json.dumps(camp.load())
    assert camp.blind_audit(cid)["ok"]
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "MODO PILOTO — NO SE ENVÍA AL MOTOR" in h
    assert "únicamente para comparar al final" in h
    assert "esquemático y referencial" in h
    assert "MATERIAL CARGADO" in h and "4 fotos" in h


def test_el_formulario_de_crear_separa_el_plano_real_en_modo_piloto(env):
    c, _camp, _ = env
    h = _html(c, BASE + "/crear")
    pil = h.index("MODO PILOTO — NO SE ENVÍA AL MOTOR")
    assert h.index('name="fotos"') < pil < h.index('name="plano_real"')
    assert "únicamente para comparar al final" in h
    assert 'class="piloto"' in h
    # nada de campos de negocio no aprobados
    for campo in ('name="telefono"', 'name="empresa"', 'name="nombre"', 'name="programa"',
                  'name="estilo"', 'name="email"'):
        assert campo not in h


def test_crear_rechaza_material_incompleto_o_no_ciego_sin_dejar_caso(env):
    c, camp, _ = env
    # sin plano real
    r = c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(_foto(1)), "a.png")]},
               content_type="multipart/form-data")
    assert r.status_code == 400 and "plano real" in r.get_data(as_text=True)
    # sin fotos
    r = c.post(f"{BASE}/crear", data={"plano_real": (io.BytesIO(_plano_real()), "gt.png")},
               content_type="multipart/form-data")
    assert r.status_code == 400
    # plano real idéntico a una foto: no es ciego
    foto = _foto(2)
    r = c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(foto), "a.png")],
                                      "plano_real": (io.BytesIO(foto), "g.png")},
               content_type="multipart/form-data")
    assert r.status_code == 400 and "no es ciego" in r.get_data(as_text=True)
    # formato no aceptado, m² inválidos, teléfono en la referencia
    assert _subir_crear(c, gt_nombre="plano.docx").status_code == 400
    assert _subir_crear(c, m2="mucho").status_code == 400
    assert _subir_crear(c, m2="-3").status_code == 400
    r = _subir_crear(c, referencia="llamar al +56 9 8765 4321")
    assert r.status_code == 400 and "teléfono" in r.get_data(as_text=True)
    assert camp.load()["cases"] == []
    assert camp.count("CREATE")["captured"] == 0
    # y un reintento válido del mismo material después de un rechazo sí entra (sin evidencia huérfana)
    assert _subir_crear(c, n=2).status_code == 303


def test_una_referencia_con_enlace_queda_como_fuente(env):
    c, camp, _ = env
    cid = _cid(_subir_crear(c, referencia="https://www.example.com/ficha/55?x=1"))
    caso = camp.get(cid)
    assert caso["source_urls"] == ["https://www.example.com/ficha/55?x=1"]
    assert caso["property_key"] == "example.com/ficha/55"
    assert caso["declared"] == {}


# ---- ceguera: pruebas adversariales ------------------------------------------------------------
def _superficie_visible(c, camp, cid):
    """Todo lo que un navegador (o un motor) alcanza del caso, antes del reveal."""
    caso = camp.get(cid)
    urls = [f"{BASE}/", f"{BASE}/panel", f"{BASE}/crear", f"{BASE}/caso/{cid}"]
    urls += [f"{BASE}/caso/{cid}/archivo/foto-{i}" for i in range(1, 6)]
    urls += [f"{BASE}/caso/{cid}/archivo/reconstruccion"]
    return caso, [(u, c.get(u)) for u in urls]


def test_el_plano_real_no_aparece_en_ninguna_pantalla_antes_del_reveal(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=3))
    caso = camp.get(cid)
    from webapp import store
    pid = caso["recon_project_id"]
    gt = store.q1("SELECT sha256, original_filename, stored_name FROM recon_ground_truth "
                  "WHERE project_id=?", (pid,))
    huellas = [gt["sha256"], gt["stored_name"], "reconstruction_gt", GT_NOMBRE, "SECRETO_GT"]
    # recorrer el caso entero hasta antes del cierre
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "el living-comedor más grande"})
    _, vistas = _superficie_visible(c, camp, cid)
    for url, r in vistas:
        cuerpo = r.get_data(as_text=True) if r.mimetype.startswith(("text", "image/svg")) else ""
        for h in huellas:
            assert h not in cuerpo, (url, h)
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404
    # el laboratorio de E37 tampoco lo sirve
    assert c.get(f"/lab/reconstruction/p/{pid}/plano-real").status_code == 404
    # ni lo que el motor recibió ni lo que se guardó de cada corrida
    from webapp.domain.reconstruction import runs
    for r in runs.of_project(pid):
        visto = json.dumps(r["inputs"], default=str) + json.dumps(r["params"], default=str)
        visto += repr(runs.build_request(r))
        for h in huellas:
            assert h not in visto, h
    assert camp.blind_audit(cid)["ok"]


@pytest.mark.parametrize("cual", ["real", "plano_real", "REAL", "../real", "real/", "foto-0",
                                  "foto-99", "foto-x", "..%2Freal", "gt", "despues", "entrada"])
def test_el_selector_de_archivo_no_permite_llegar_al_plano_real(env, cual):
    c, camp, _ = env
    cid = _cid(_subir_crear(c, n=2))
    r = c.get(f"{BASE}/caso/{cid}/archivo/{cual}")
    assert r.status_code == 404
    # y en el reveal tampoco se cuela por otro nombre: sólo `real`
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404


def test_no_se_puede_revelar_ni_cerrar_sin_el_orden_ciego(env):
    c, camp, _ = env
    cid = _cid(_subir_crear(c))
    # cerrar sin corrida
    r = c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"})
    assert r.status_code == 409
    with pytest.raises(camp.CampaignError):
        camp.reveal(cid)
    assert not [e for e in camp.events(cid) if e["kind"] in ("closure", "reveal")]
    c.post(f"{BASE}/caso/{cid}/procesar")
    # sin confirmar no se cierra
    assert c.post(f"{BASE}/caso/{cid}/cerrar").status_code == 400
    assert not [e for e in camp.events(cid) if e["kind"] == "closure"]
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404
    # no hay ruta GET que revele
    for u in (f"{BASE}/caso/{cid}/cerrar", f"{BASE}/caso/{cid}/revelar"):
        assert c.get(u).status_code in (404, 405)
    # y la evaluación del plano exige el reveal
    assert _eval_plano(c, cid).status_code == 409


def test_una_auditoria_de_ceguera_fallida_bloquea_el_cierre(env, monkeypatch):
    c, camp, _ = env
    cid = _cid(_subir_crear(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    monkeypatch.setattr(camp, "blind_audit", lambda case_id: {"ok": False, "violations": ["x"]})
    r = c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"})
    assert r.status_code == 409 and "ceguera" in r.get_data(as_text=True)
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404
    from webapp.domain.reconstruction import groundtruth
    assert groundtruth.revealed_info(camp.get(cid)["recon_project_id"]) is None


# ---- CREAR: ejecución real, corrección hija, cierre y comparación -----------------------------
def test_crear_corre_corrige_cierra_y_recien_ahi_muestra_el_plano_real(env):
    c, camp, _ = env
    cid = _cid(_subir_crear(c))
    from webapp.domain.reconstruction import groundtruth, runs
    pid = camp.get(cid)["recon_project_id"]
    # procesar → corrida real del laboratorio E37, asentada en la campaña al ver la página
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "RESULTADO LISTO" in h and "ESQUEMÁTICO · REFERENCIAL" in h and ">RECONSTRUCCIÓN<" in h
    assert "PLANO REAL" not in h and "CERRAR RECONSTRUCCIÓN Y COMPARAR" in h
    ev = camp.events(cid)
    assert [e["kind"] for e in ev] == ["create_started", "pipeline"]
    assert ev[1]["data"]["engine_id"] == "motor_de_prueba" and ev[1]["data"]["status"] == "DONE"
    primera = ev[1]["data"]["run_id"]
    svg = c.get(f"{BASE}/caso/{cid}/archivo/reconstruccion")
    assert svg.status_code == 200 and svg.mimetype == "image/svg+xml"
    # corrección en lenguaje natural → corrida HIJA; la madre queda intacta
    sha_madre = runs.get(primera)["output_sha256"]
    r = c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "el dormitorio principal más grande"})
    assert r.status_code == 303
    h = _html(c, f"{BASE}/caso/{cid}")
    corr = [e for e in camp.events(cid) if e["kind"] == "correction"]
    assert len(corr) == 1
    hija = runs.get(corr[0]["data"]["run_id"])
    assert hija["parent_run_id"] == primera and hija["origin"] == runs.CORRECTION
    assert runs.get(primera)["output_sha256"] == sha_madre
    assert "Correcciones hechas: 1" in h
    # sin el botón de cierre no hay reveal; con el cierre explícito, sí
    assert camp.status(camp.get(cid)) == camp.EXECUTED
    r = c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"})
    assert r.status_code == 303 and r.headers["Location"].endswith("#comparacion")
    kinds = [e["kind"] for e in camp.events(cid)]
    assert kinds.index("closure") < kinds.index("reveal")
    cierre = next(e for e in camp.events(cid) if e["kind"] == "closure")
    assert cierre["data"]["final_run_id"] == hija["run_id"] and cierre["data"]["prompts_humanos"] == 1
    assert cierre["data"]["blind_audit"]["ok"] and cierre["data"]["gt_state_at_closure"] == "HIDDEN_FROM_ENGINE"
    h = _html(c, f"{BASE}/caso/{cid}")
    assert ">RECONSTRUCCIÓN<" in h and ">PLANO REAL<" in h
    real = c.get(f"{BASE}/caso/{cid}/archivo/real")
    assert real.status_code == 200 and real.mimetype == "image/png"
    assert groundtruth.revealed_info(pid) is not None
    # cerrada: ya no se corrige ni se vuelve a cerrar
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "otro"}).status_code == 400
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code in (303, 409)
    assert [e["kind"] for e in camp.events(cid)].count("closure") == 1


def test_mientras_corre_el_caso_esta_procesando_y_no_se_puede_cerrar(env, monkeypatch):
    c, camp, _ = env
    from webapp.domain.reconstruction import runs
    cola = []
    monkeypatch.setattr(runs, "enqueue", lambda rid: cola.append(rid))
    cid = _cid(_subir_crear(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "PROCESANDO" in h and 'http-equiv="refresh"' in h
    assert "CERRAR RECONSTRUCCIÓN" not in h
    assert [e["kind"] for e in camp.events(cid)] == ["create_started"]   # no hay pipeline inventado
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 409
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409        # no se lanza dos veces
    runs.execute(cola[0])
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "RESULTADO LISTO" in h and 'http-equiv="refresh"' not in h


def test_una_instruccion_que_el_motor_no_entiende_pide_aclaracion(env):
    c, camp, _ = env
    cid = _cid(_subir_crear(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "hazlo mejor"})
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "Pide una aclaración" in h


def test_una_correccion_con_telefono_se_rechaza_sin_crear_corrida(env):
    c, camp, _ = env
    from webapp.domain.reconstruction import runs
    cid = _cid(_subir_crear(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    n = len(runs.of_project(camp.get(cid)["recon_project_id"]))
    r = c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "llámame al +56 9 8765 4321"})
    assert r.status_code == 400
    assert len(runs.of_project(camp.get(cid)["recon_project_id"])) == n


# ---- sin credencial ----------------------------------------------------------------------------
def test_sin_credencial_crear_se_bloquea_de_forma_accionable_y_no_finge_exito(env, monkeypatch):
    c, camp, _ = env
    from webapp import pilot
    monkeypatch.setattr(pilot, "CREATE_ENGINE", "openai_direct")      # el motor real, sin clave
    cid = _cid(_subir_crear(c))
    r = c.post(f"{BASE}/caso/{cid}/procesar")
    assert r.status_code == 303
    caso = camp.get(cid)
    assert camp.status(caso) == camp.BLOCKED_CRED
    assert [e["kind"] for e in camp.events(cid)] == ["blocked"]
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "BLOQUEADO" in h and "No se pudo procesar todavía" in h and "operador" in h
    assert "VOLVER A INTENTAR" in h
    assert "RECONSTRUCCIÓN<" not in h and "RESULTADO LISTO" not in h
    assert c.get(f"{BASE}/caso/{cid}/archivo/reconstruccion").status_code == 404
    assert camp.count("CREATE")["completed"] == 0 and camp.count("CREATE")["blocked"] == 1
    from webapp.domain.reconstruction import runs
    assert runs.of_project(caso["recon_project_id"]) == []            # ni siquiera se creó una corrida
    # reintentar sin clave no duplica el bloqueo
    c.post(f"{BASE}/caso/{cid}/procesar")
    assert [e["kind"] for e in camp.events(cid)] == ["blocked"]
    # la clave nunca viaja por la web: ni su nombre completo de variable aparece como valor
    assert "sk-" not in h


def test_con_la_credencial_presente_el_caso_bloqueado_se_puede_reintentar(env, monkeypatch):
    c, camp, _ = env
    from webapp import pilot
    monkeypatch.setattr(pilot, "CREATE_ENGINE", "openai_direct")
    cid = _cid(_subir_crear(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    assert camp.status(camp.get(cid)) == camp.BLOCKED_CRED
    monkeypatch.setattr(pilot, "CREATE_ENGINE", "motor_de_prueba")    # «se configuró la clave»
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    assert camp.status(camp.get(cid)) == camp.EXECUTED


# ---- evaluaciones: resultado y UX/UI separados, con historial ----------------------------------
def _caso_mejorar_listo(c, planta_lista):
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    return cid


def test_resultado_y_ux_se_evaluan_por_separado_y_no_hay_score(env, planta_lista):
    c, camp, _ = env
    cid = _caso_mejorar_listo(c, planta_lista)
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "1 · RESULTADO DEL PLANO" in h and "2 · UX / UI" in h
    assert h.index("DESPUÉS") < h.index("PANEL PILOTO — EVALUACIÓN")       # la crítica va al final
    assert _eval_plano(c, cid).status_code == 303
    assert camp.status(camp.get(cid)) == camp.COMPLETED
    assert _eval_ux(c, cid).status_code == 303
    ev = {e["kind"]: e for e in camp.events(cid)}
    plano, ux = ev["evaluation"]["data"], ev["ux_evaluation"]["data"]
    assert plano["schema"] == "e45_pilot_v1" and plano["rating"] == "BUENO"
    assert plano["would_publish"] is True and plano["needed_human_correction"] is False
    assert plano["human_minutes"] == 4.0 and plano["comment"] == "limpio"
    assert ux["rating"] == "MALO" and ux["understood_immediately"] is False
    assert ux["extra_step_comment"] == "el aviso" and ux["missing_comment"] == "un ejemplo"
    # dos juicios distintos, ninguno derivado del otro, y ningún puntaje compuesto
    assert plano["rating"] != ux["rating"]
    for d in (plano, ux):
        assert not any("score" in k or "total" in k or "promedio" in k for k in d)
    s = camp.summary()["tracks"]["IMPROVE"]
    assert not any("score" in k for k in s)
    assert s["pilot"]["ux_ratings"]["MALO"] == 1 and s["pilot"]["ux_ratings"]["BUENO"] == 0
    assert s["ratings"]["BUENO"] == 1
    assert s["pilot"]["would_publish"] == {"si": 1, "no": 0}
    assert s["pilot"]["ux_understood_immediately"] == {"si": 0, "no": 1}
    # una evaluación de UX sola no completa el caso
    cid2 = _caso_mejorar_listo_otro(c)
    assert _eval_ux(c, cid2).status_code == 303
    assert camp.status(camp.get(cid2)) == camp.EXECUTED


def _caso_mejorar_listo_otro(c):
    cid = _cid(_subir_mejorar(c, _plano_de_galeria_distinto()))
    c.post(f"{BASE}/caso/{cid}/procesar")
    return cid


def _plano_de_galeria_distinto():
    import cv2
    import numpy as np
    img = np.full((300, 400, 3), 250, np.uint8)
    for x in range(30, 400, 70):
        cv2.line(img, (x, 20), (x, 280), (30, 30, 30), 3)
    for y in range(20, 300, 40):
        cv2.line(img, (20, y), (380, y), (30, 30, 30), 3)
    return cv2.imencode(".png", img)[1].tobytes()


def test_una_evaluacion_nueva_no_pierde_la_anterior(env, planta_lista):
    c, camp, _ = env
    cid = _caso_mejorar_listo(c, planta_lista)
    _eval_plano(c, cid, rating="MALO", comentario="primera impresión")
    antes = open(os.path.join(camp.case_dir(cid), "results", "003_evaluation.json")).read()
    _eval_plano(c, cid, rating="EXCELENTE", comentario="después de mirar mejor", minutos="")
    _eval_ux(c, cid, rating="PESIMO")
    _eval_ux(c, cid, rating="BUENO", entendi="si")
    evs = [e for e in camp.events(cid) if e["kind"] == "evaluation"]
    assert [e["data"]["rating"] for e in evs] == ["MALO", "EXCELENTE"]
    assert evs[1]["data"]["supersedes_seq"] == evs[0]["seq"]
    assert open(os.path.join(camp.case_dir(cid), "results", "003_evaluation.json")).read() == antes
    uxs = [e for e in camp.events(cid) if e["kind"] == "ux_evaluation"]
    assert [e["data"]["rating"] for e in uxs] == ["PESIMO", "BUENO"]
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "primera impresión" in h and "después de mirar mejor" in h        # historial visible
    assert "AGREGAR NUEVA EVALUACIÓN" in h and "vigente" in h
    # lo vigente para el resumen es la última del plano; la UX no la pisa
    assert camp.summary()["tracks"]["IMPROVE"]["ratings"]["EXCELENTE"] == 1
    assert camp.summary()["tracks"]["IMPROVE"]["ratings"]["MALO"] == 0
    assert camp.status(camp.get(cid)) == camp.COMPLETED


def test_validacion_de_evaluaciones(env, planta_lista):
    c, camp, _ = env
    cid = _caso_mejorar_listo(c, planta_lista)
    for kw in ({"rating": "10/10"}, {"rating": ""}, {"publicaria": ""}, {"correccion_humana": "tal vez"},
               {"minutos": "mucho"}, {"minutos": "-4"}, {"comentario": "escríbeme a juan@example.com"}):
        assert _eval_plano(c, cid, **kw).status_code == 400, kw
    for kw in ({"rating": "GENIAL"}, {"entendi": ""}, {"sobraba": "llama al +56 9 8765 4321"}):
        assert _eval_ux(c, cid, **kw).status_code == 400, kw
    assert [e["kind"] for e in camp.events(cid)] == ["improve_started", "pipeline"]


def test_no_se_ofrece_evaluar_antes_de_tener_resultado(env, planta_no_lista):
    c, camp, _ = env
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "PANEL PILOTO — EVALUACIÓN" not in h and "GUARDAR EVALUACIÓN" not in h
    assert _eval_plano(c, cid).status_code == 409
    assert _eval_ux(c, cid).status_code == 409                  # la UX sólo vale con un recorrido hecho
    assert not [e for e in camp.events(cid) if e["kind"] == "evaluation"]


def test_en_crear_la_evaluacion_llega_despues_de_la_comparacion(env):
    c, camp, _ = env
    cid = _cid(_subir_crear(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "GUARDAR EVALUACIÓN" not in h
    assert _eval_plano(c, cid).status_code == 409 and _eval_ux(c, cid).status_code == 409
    c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"})
    h = _html(c, f"{BASE}/caso/{cid}")
    assert h.index(">PLANO REAL<") < h.index("PANEL PILOTO — EVALUACIÓN")
    assert _eval_plano(c, cid, publicaria="no", correccion_humana="si").status_code == 303
    assert _eval_ux(c, cid).status_code == 303
    assert camp.status(camp.get(cid)) == camp.COMPLETED
    s = camp.summary()["tracks"]["CREATE"]
    assert s["pilot"]["would_publish"] == {"si": 0, "no": 1}
    assert s["pilot"]["needed_human_correction"] == {"si": 1, "no": 0}


# ---- panel: progreso honesto, DEMO fuera de los N ---------------------------------------------
def test_el_panel_muestra_progreso_honesto_y_estados(env, planta_lista, planta_no_lista=None):
    c, camp, _ = env
    h = _html(c, BASE + "/panel")
    assert "MEJORAR" in h and "CREAR" in h and ">0<span>/20<" in h.replace(" ", "").replace("\n", "") \
        or "0<span>/20</span>" in h
    assert "NUEVO MEJORAR" in h and "NUEVO CREAR" in h
    assert "Todavía no hay casos" in h
    cid = _caso_mejorar_listo(c, planta_lista)
    cid_c = _cid(_subir_crear(c))
    h = _html(c, BASE + "/panel")
    assert "ABRIR CASO" in h and "RESULTADO LISTO" in h and "MATERIAL CARGADO" in h
    assert "0<span>/20</span>" in h                           # nada evaluado todavía
    n = camp.count("IMPROVE"), camp.count("CREATE")
    assert (n[0]["captured"], n[0]["completed"]) == (1, 0)
    assert (n[1]["captured"], n[1]["completed"]) == (1, 0)
    _eval_plano(c, cid)
    h = _html(c, BASE + "/panel")
    assert "1<span>/20</span>" in h and "EVALUADO" in h and "BUENO" in h
    assert f"/caso/{cid_c}" in h and f"/caso/{cid}" in h


def test_los_casos_incompletos_no_cuentan_como_completados(env, planta_no_lista):
    c, camp, _ = env
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")                      # en revisión
    _subir_crear(c, gt=b"")                                    # incompleto: no entra
    assert camp.count("IMPROVE") == {"listed": 1, "captured": 1, "executed": 0, "completed": 0,
                                     "blocked": 0, "url_only": 0, "excluded": 0}
    assert camp.count("CREATE")["listed"] == 0
    assert "0<span>/20</span>" in _html(c, BASE + "/panel")
    # un asset que desaparece del disco saca al caso del conteo
    os.chmod(os.path.join(camp.case_dir(cid), "evidence", "plano.png"), 0o644)
    open(os.path.join(camp.case_dir(cid), "evidence", "plano.png"), "wb").write(b"otro")
    assert camp.count("IMPROVE")["captured"] == 0


def test_los_demo_no_cuentan_ni_chocan_con_casos_reales(env):
    c, camp, _ = env
    d1 = camp.import_upload("IMPROVE", [("p.png", _plano())], demo=True)
    d2 = camp.import_upload("CREATE", [("f.png", _foto(1))], ground_truth=("g.png", _plano_real()),
                            demo=True)
    for d in (d1, d2):
        camp.record(d, "pipeline", {"reached_output": True, "status": "DONE"}) \
            if d == d1 else None
    camp.record(d1, "evaluation", {"schema": "e45_pilot_v1", "rating": "EXCELENTE",
                                   "would_publish": True, "needed_human_correction": False})
    assert camp.status(camp.get(d1)) == camp.COMPLETED
    for t in camp.TRACKS:
        n = camp.count(t)
        assert n == {"listed": 0, "captured": 0, "executed": 0, "completed": 0, "blocked": 0,
                     "url_only": 0, "excluded": 0}, t
        assert camp.summary()["tracks"][t]["counts"]["completed"] == 0
    assert camp.summary()["status"] == "BLOCKED"              # nada real capturado
    # el mismo material como caso REAL no es «duplicado» de la demo, y suma sólo él
    real = _cid(_subir_mejorar(c))
    assert real != d1 and camp.count("IMPROVE")["captured"] == 1
    h = _html(c, BASE + "/panel")
    assert "DEMO — EJEMPLOS PARA VER LA INTERFAZ" in h and "NO CUENTAN EN LA CAMPAÑA" in h
    assert "0<span>/20</span>" in h
    assert "DEMO" in _html(c, f"{BASE}/caso/{d1}")


def test_los_demo_crear_pueden_usar_el_fixture_pero_los_reales_no(env, monkeypatch):
    c, camp, _ = env
    from webapp import pilot
    d = camp.import_upload("CREATE", [("f.png", _foto(1))], ground_truth=("g.png", _plano_real()),
                           demo=True)
    real = _cid(_subir_crear(c, n=2))
    with pytest.raises(camp.CampaignError, match="fixture"):
        camp.start_create(real, "fixture_replay")
    monkeypatch.setattr(pilot, "CREATE_ENGINE", "fixture_replay")
    assert c.post(f"{BASE}/caso/{real}/procesar").status_code == 409
    assert camp.start_create(d, "fixture_replay")["status"] == "QUEUED"


# ---- E44 sigue siendo la fuente de verdad ------------------------------------------------------
def test_e44_summary_acepta_evaluaciones_de_la_web_y_del_bundle_mezcladas(env, planta_lista):
    c, camp, _ = env
    cid = _caso_mejorar_listo(c, planta_lista)
    _eval_plano(c, cid)
    s = camp.summary()["tracks"]["IMPROVE"]
    assert s["fidelity"]["NO_EVALUADO"] == 0 and sum(s["fidelity"].values()) == 0   # no se inventa
    assert s["counts"]["completed"] == 1 and s["human_minutes"] == {"registered_in": 1, "total": 4.0}
    assert camp.build_index() and "E44" in open(camp.build_index()).read()


def test_el_estado_se_deriva_de_los_eventos(env, planta_lista):
    c, camp, _ = env
    cid = _caso_mejorar_listo(c, planta_lista)
    d = camp.case_dir(cid)
    antes = sorted(os.listdir(os.path.join(d, "results")))
    assert antes == ["001_improve_started.json", "002_pipeline.json"]
    # los eventos son de sólo inserción: no existe ninguna ruta que los edite
    rutas = {r.rule for r in c.application.url_map.iter_rules() if r.rule.startswith(BASE)}
    assert not any("editar" in r or "borrar" in r or "eliminar" in r for r in rutas)


# ---- responsive y humo visual ------------------------------------------------------------------
def test_humo_responsive_todas_las_pantallas_traen_viewport_y_css_movil(env, planta_lista):
    c, camp, _ = env
    cm = _caso_mejorar_listo(c, planta_lista)
    cc = _cid(_subir_crear(c))
    c.post(f"{BASE}/caso/{cc}/procesar")
    urls = [BASE + "/", BASE + "/panel", BASE + "/mejorar", BASE + "/crear", f"{BASE}/caso/{cm}",
            f"{BASE}/caso/{cc}"]
    c.post(f"{BASE}/caso/{cc}/cerrar", data={"confirmo": "1"})
    for u in urls:
        h = _html(c, u)
        assert 'name="viewport" content="width=device-width,initial-scale=1"' in h, u
        assert "pilot.css" in h and "<table" not in h, u          # sin tablas densas
        assert 'lang="es"' in h
    css = c.get("/static/pilot.css").get_data(as_text=True)
    assert "@media(max-width:820px)" in css
    assert "grid-template-columns:1fr;" in css.split("@media(max-width:820px)")[1]
    assert "max-height:78vh" in css and "aspect-ratio" in css


def test_las_pantallas_de_producto_no_exponen_jerga_tecnica(env, planta_lista):
    c, camp, _ = env
    cm = _caso_mejorar_listo(c, planta_lista)
    cc = _cid(_subir_crear(c))
    c.post(f"{BASE}/caso/{cc}/procesar")
    c.post(f"{BASE}/caso/{cc}/cerrar", data={"confirmo": "1"})
    for u in (BASE + "/", BASE + "/mejorar", BASE + "/crear", f"{BASE}/caso/{cm}",
              f"{BASE}/caso/{cc}", BASE + "/panel"):
        h = _html(c, u)
        visible = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h, flags=re.S)
        visible = re.sub(r"<[^>]+>", " ", visible).lower()
        for palabra in ("adapter", "readiness", "sha256", "hidden_from", "benchmark", "heurística",
                        "contrato", "fixture", "openai", "e44", "e37", "floorplate", "svg"):
            assert palabra not in visible, (u, palabra)
