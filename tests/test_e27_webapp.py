"""E27 §22 — pruebas de la web app interna.

Sólo se prueba lo que importa que no se rompa: que un upload válido entre y uno inválido no, que
el caso sobreviva a un reinicio, que el formulario produzca un BriefV1 que el motor acepte, que el
job invoque AL MOTOR EXISTENTE (y no a una reimplementación), que los estados se muestren tal cual
los devuelve el motor, que una revisión quede atada a la geometría que se juzgó, que la app no
quede abierta sin contraseña, y que la imagen del shell se sirva.

No se prueba el algoritmo de layout: eso ya está cubierto por E04–E26 y E27 no lo tocó.
"""
from __future__ import annotations

import importlib
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

def _png(w: int = 8, h: int = 8) -> bytes:
    """PNG mínimo pero VÁLIDO. Se construye en vez de pegarse en hex: un blob corrupto haría
    fallar los tests por una razón que no es la que se está probando."""
    import struct, zlib
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


PNG_1PX = _png()


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """App aislada: DATA_DIR propio, sin migración y sin contraseña (modo dev)."""
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ESCALIMETRO_DEV", "1")
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for m in ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine",
              "webapp.migrate", "webapp.app"):
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()


def _upload(client, name, blob):
    return client.post("/upload", data={"plantas": (io.BytesIO(blob), name)},
                       content_type="multipart/form-data", follow_redirects=False)


# ===================================================================================================
# 1 — uploads (§4, §17)
# ===================================================================================================
def test_upload_valido_crea_un_case(client):
    from webapp import store
    r = _upload(client, "planta.png", PNG_1PX)
    assert r.status_code == 302
    rows = store.q("SELECT * FROM cases")
    assert len(rows) == 1
    assert rows[0]["status"] == "UPLOADED"
    assert rows[0]["original_filename"] == "planta.png"


def test_upload_con_extension_prohibida_se_rechaza(client):
    from webapp import store
    r = _upload(client, "malicioso.exe", b"MZ\x00\x00")
    assert r.status_code == 200
    assert "Formato no aceptado" in r.get_data(as_text=True)
    assert store.q("SELECT * FROM cases") == []


def test_upload_con_contenido_que_no_coincide_se_rechaza(client):
    """Un .png cuyo contenido es un PDF no entra: se mira el archivo, no sólo el nombre."""
    from webapp import store
    r = _upload(client, "disfrazado.png", b"%PDF-1.4 no soy un png")
    assert "no coincide con su extensi" in r.get_data(as_text=True)
    assert store.q("SELECT * FROM cases") == []


def test_el_nombre_subido_no_decide_la_ruta_en_disco(client):
    """§17 — path traversal: el case_id es interno, el nombre del usuario nunca es una ruta."""
    from webapp import store
    _upload(client, "../../../../etc/passwd.png", PNG_1PX)
    row = store.q1("SELECT * FROM cases")
    assert row is not None
    assert row["case_id"].startswith("c_")
    assert os.path.realpath(store.case_dir(row["case_id"])).startswith(
        os.path.realpath(store.DATA_DIR))


# ===================================================================================================
# 2 — persistencia (§13, §15)
# ===================================================================================================
def test_el_case_sobrevive_a_un_reinicio_del_proceso(client, app):
    from webapp import store
    _upload(client, "planta.png", PNG_1PX)
    case_id = store.q1("SELECT case_id FROM cases")["case_id"]
    store.connect().close()
    store._local.conn = None                      # simula proceso nuevo contra el mismo volumen
    store.init()
    assert store.q1("SELECT case_id FROM cases WHERE case_id=?", (case_id,)) is not None


def test_una_corrida_interrumpida_no_queda_diciendo_que_genera(client):
    """Honestidad de estado: si el proceso murió, la corrida no puede seguir en RUNNING."""
    from webapp import store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','GENERATING','DEVELOPMENT')")
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,created_at) "
             "VALUES ('r1','x','b','RUNNING','t')")
    store.ex("INSERT INTO alternatives(run_id,alt,status) VALUES ('r1','A','GENERATING')")
    store.init()
    assert store.q1("SELECT status FROM runs WHERE run_id='r1'")["status"] == "FAILED"
    assert store.q1("SELECT status FROM alternatives WHERE run_id='r1'")["status"] == "FAILED"


# ===================================================================================================
# 3 — brief (§8)
# ===================================================================================================
def test_el_formulario_produce_un_briefv1_que_el_motor_acepta():
    from escalimetro.brief import BriefV1
    from webapp import briefs
    b = briefs.build("Mi brief", 48, 40, briefs.DEFAULT_ROOMS)
    assert b["contract_version"] == "brief_v1"
    BriefV1.from_dict(b).require_valid()          # el juez es el motor, no una copia


def test_el_brief_no_puede_declarar_modulos_derivados():
    from webapp import briefs
    with pytest.raises(briefs.BriefFormError):
        briefs.build("X", 10, 5, {"workstation_cluster": 2})


def test_el_formulario_rechaza_un_brief_incoherente():
    from webapp import briefs
    with pytest.raises(briefs.BriefFormError):
        briefs.validate_against_engine(
            briefs.build("X", 5, 40, {"private_office": 4}),
            os.path.join(ROOT, "program_templates", "modules_office.json"))


def test_la_ui_no_expone_design_policy(client):
    """§8 — el usuario declara QUÉ necesita. Pesos, barrios y adyacencias no se muestran."""
    from webapp import store
    _upload(client, "planta.png", PNG_1PX)
    cid = store.q1("SELECT case_id FROM cases")["case_id"]
    html = client.get(f"/case/{cid}").get_data(as_text=True)
    for prohibido in ("objective_weights", "neighborhood", "design_policy", "module_max_path",
                      "bench_blocks", "spine"):
        assert prohibido not in html


# ===================================================================================================
# 4 — el job llama AL MOTOR EXISTENTE (§7)
# ===================================================================================================
def _shell_listo(store, case_id="x"):
    """Deja un floorplate que declara `ready_for_layout`, que es la puerta que abre el motor."""
    d = os.path.join(store.case_dir(case_id), "outputs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
        json.dump({"shell_readiness": {"ready_for_layout": True, "requires_confirmation": []}}, fh)


def test_el_job_invoca_el_modulo_del_motor_y_no_una_reimplementacion(monkeypatch, client):
    from webapp import engine, store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','READY','DEVELOPMENT')")
    _shell_listo(store)
    store.ex("INSERT INTO briefs(brief_id,case_id,name,headcount,workstations,rooms,brief_sha256,"
             "created_at) VALUES ('b','x','b',10,5,'[]','sha','t')")
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,created_at) "
             "VALUES ('r','x','b','QUEUED','t')")
    seen = {}

    class R:
        returncode, stdout, stderr = 0, "ok", ""

    def fake_run(cmd, **kw):
        seen["cmd"], seen["cwd"] = cmd, kw.get("cwd")
        return R()

    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    engine._execute("r")
    assert "escalimetro.layout.e07.run" in seen["cmd"], seen["cmd"]
    assert "--brief" in seen["cmd"] and "--out-name" in seen["cmd"]
    assert seen["cwd"] == engine.REPO_ROOT


def test_el_puente_no_reimplementa_el_motor():
    """§7 — la web orquesta el motor; no importa su geometría ni su solver.

    Se miran los IMPORTS (AST), no el texto: un docstring que NOMBRA una restricción para explicar
    que no se toca es exactamente lo contrario de duplicar lógica."""
    import ast
    import pathlib
    prohibidos = ("ortools", "escalimetro.layout.e06.freeplace", "escalimetro.layout.solver",
                  "escalimetro.layout.e05.bands", "escalimetro.layout.scoring",
                  "escalimetro.layout.e07.strategies")
    for py in pathlib.Path(ROOT, "webapp").rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                assert not any(m.startswith(p) for p in prohibidos), \
                    f"{py.name} importa {m}: la web no debe ejecutar el motor en proceso"


# ===================================================================================================
# 5 — estados honestos (§9)
# ===================================================================================================
def test_los_estados_del_motor_se_leen_de_los_artefactos(tmp_path, monkeypatch, client):
    from webapp import engine, store
    d = os.path.join(store.case_dir("x"), "layouts", "r", "alternatives")
    for alt, art, payload in (("A", "metrics.json", {"program_completeness": {"complete": True}}),
                              ("B", "no_fit.json", {"status": "SEARCH_EXHAUSTED"}),
                              ("C", "no_fit.json", {"status": "TIMEOUT_NO_SOLUTION"})):
        os.makedirs(os.path.join(d, alt), exist_ok=True)
        with open(os.path.join(d, alt, art), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    got = {r["alt"]: r["status"] for r in engine.collect("x", "r")}
    assert got == {"A": "FIT", "B": "SEARCH_EXHAUSTED", "C": "TIMEOUT_NO_SOLUTION"}


def test_sin_artefacto_la_alternativa_es_failed_y_no_se_inventa_un_estado(client):
    from webapp import engine
    assert [r["status"] for r in engine.collect("no_existe", "tampoco")] == ["FAILED"] * 3


def test_search_exhausted_nunca_se_traduce_como_no_cabe():
    """§9 — la regla de producto, verificada sobre las plantillas que ve el usuario."""
    import pathlib
    for tpl in pathlib.Path(ROOT, "webapp", "templates").glob("*.html"):
        txt = tpl.read_text(encoding="utf-8").lower()
        assert "no cabe" not in txt or "autoriza decir" in txt, tpl.name


# ===================================================================================================
# 6 — revisión humana (§12)
# ===================================================================================================
def _seed_run_with_layout(store, sha="a" * 64):
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','COMPLETE','DEVELOPMENT')")
    store.ex("INSERT INTO briefs(brief_id,case_id,name,headcount,workstations,rooms,brief_sha256,"
             "created_at) VALUES ('b','x','b',10,5,'[]','briefsha','t')")
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,engine_commit,created_at) "
             "VALUES ('r','x','b','DONE','commitsha','t')")
    store.ex("INSERT INTO alternatives(run_id,alt,name,status,layout_sha256) "
             "VALUES ('r','A','EFICIENTE','FIT',?)", (sha,))


def test_la_revision_queda_ligada_al_layout_al_motor_y_al_brief(client):
    from webapp import store
    _seed_run_with_layout(store)
    r = client.post("/run/r/review", data={"alt": "A", "grade": "B_CORRECTABLE",
                                           "tags": ["circulacion", "espacio_desperdiciado"],
                                           "note": "falta pasillo", "minutes": "3"})
    assert r.status_code == 302
    rev = store.q1("SELECT * FROM reviews")
    assert rev["layout_sha256"] == "a" * 64
    assert rev["engine_commit"] == "commitsha"
    assert rev["brief_sha256"] == "briefsha"
    assert json.loads(rev["reason_tags"]) == ["circulacion", "espacio_desperdiciado"]


def test_solo_se_aceptan_grados_y_tags_del_contrato(client):
    from webapp import store
    _seed_run_with_layout(store)
    assert client.post("/run/r/review", data={"alt": "A", "grade": "EXCELENTE"}).status_code == 400
    client.post("/run/r/review", data={"alt": "A", "grade": "A_GOOD",
                                       "tags": ["circulacion", "inventada_por_mi"]})
    assert json.loads(store.q1("SELECT * FROM reviews")["reason_tags"]) == ["circulacion"]


def test_la_evaluacion_no_viene_prellenada(client):
    """§12/§23 — Claude no evalúa arquitectura. Ningún radio de veredicto llega marcado."""
    from webapp import store
    _seed_run_with_layout(store)
    html = client.get("/run/r").get_data(as_text=True)
    i = html.find("Tu evaluación")
    assert i > 0, "no se encontró el bloque de evaluación"
    bloque = html[i:]
    assert 'name="grade"' in bloque
    assert 'name="grade" value="A_GOOD" checked' not in html
    assert "checked" not in bloque.split("Qué está mal")[0]


def test_el_export_respeta_el_contrato_human_review_v1(client):
    from webapp import store
    _seed_run_with_layout(store)
    client.post("/run/r/review", data={"alt": "A", "grade": "A_GOOD", "note": "ok"})
    data = client.get("/reviews.json").get_json()
    assert data[0]["contract_version"] == "human_layout_review_v1"
    with open(os.path.join(ROOT, "contracts", "human_review_v1.schema.json"), encoding="utf-8") as f:
        schema = json.load(f)
    import jsonschema
    jsonschema.validate({k: v for k, v in data[0].items() if not k.startswith("_")}, schema)


# ===================================================================================================
# 7 — acceso (§16)
# ===================================================================================================
def test_sin_password_y_sin_modo_dev_la_app_no_arranca(monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "")
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    import webapp.auth as auth
    importlib.reload(auth)
    with pytest.raises(auth.MissingPassword):
        auth.check_config()


def test_con_password_las_rutas_piden_credenciales(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "secreta")
    monkeypatch.setenv("ESCALIMETRO_USER", "joaquin")
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for m in ("webapp.store", "webapp.auth", "webapp.intake", "webapp.engine", "webapp.app"):
        importlib.reload(importlib.import_module(m))
    from webapp.app import create_app
    c = create_app().test_client()
    assert c.get("/").status_code == 401
    assert c.post("/upload").status_code == 401
    import base64
    tok = base64.b64encode(b"joaquin:secreta").decode()
    assert c.get("/", headers={"Authorization": f"Basic {tok}"}).status_code == 200
    bad = base64.b64encode(b"joaquin:otra").decode()
    assert c.get("/", headers={"Authorization": f"Basic {bad}"}).status_code == 401


# ===================================================================================================
# 8 — imagen del shell (§20)
# ===================================================================================================
def test_el_shell_se_dibuja_desde_el_floorplate_no_desde_un_png():
    """La regresión de E26: `cases/*/outputs/*.png` está en .gitignore, así que el PNG del shell
    no viaja con el repo ni con un deploy. El render se hace desde `floorplate.json`."""
    from escalimetro.case_context import from_case_dir
    from escalimetro.layout.e06.scale import scaled_shell
    from webapp.shellview import shell_svg
    from escalimetro.schemas.floorplate import Floorplate
    for case in ("cases/001_gps_403", "cases/002_gps_401"):
        d = os.path.join(ROOT, case)
        if not os.path.exists(os.path.join(d, "outputs", "floorplate.json")):
            pytest.skip("caso no disponible")
        svg = shell_svg(scaled_shell(Floorplate.load(from_case_dir(d).require_floorplate()), 1.0))
        assert svg.startswith("<svg") and "ACCESO" in svg


def test_el_lienzo_del_shell_no_recorta_el_nucleo():
    """E26.1 — segundo defecto, distinto del PNG ausente: el encuadre salía de
    `perimeter.bounds`, y en los dos casos el núcleo cae ENTERO fuera del perímetro (403: 210.6 m²
    de 543.0; 401: 206.9 m² de 252.0). Con ese encuadre el núcleo se dibujaba cortado contra el
    borde; en el 401 quedaban fuera tres de sus cuatro esquinas. El lienzo debe cubrir todo lo
    que se dibuja."""
    import re as _re

    from shapely.geometry import Point
    from shapely.ops import unary_union

    from escalimetro.case_context import from_case_dir
    from escalimetro.layout.e06.scale import scaled_shell
    from escalimetro.schemas.floorplate import Floorplate
    from webapp.shellview import shell_svg
    for case in ("cases/001_gps_403", "cases/002_gps_401"):
        d = os.path.join(ROOT, case)
        if not os.path.exists(os.path.join(d, "outputs", "floorplate.json")):
            pytest.skip("caso no disponible")
        sh = scaled_shell(Floorplate.load(from_case_dir(d).require_floorplate()), 1.0)
        svg = shell_svg(sh)
        W = int(_re.search(r'width="(\d+)"', svg).group(1))
        H = int(_re.search(r'height="(\d+)"', svg).group(1))
        todo = unary_union([sh.perimeter, *sh.core, *sh.columns, Point(sh.entrance).buffer(0.4)])
        minx, miny, maxx, maxy = todo.bounds
        assert sh.perimeter.bounds != todo.bounds, f"{case}: el test sólo aplica si algo cae fuera"
        margin, s = 60, (W - 120) / (maxx - minx)
        for x, y in ((minx, miny), (maxx, maxy), (minx, maxy), (maxx, miny)):
            px, py = margin + (x - minx) * s, margin + (maxy - y) * s
            assert 0 <= px <= W and 0 <= py <= H, f"{case}: el lienzo recorta ({x:.1f},{y:.1f})"


def test_el_png_del_shell_sigue_ignorado_por_git():
    """Deja constancia de la CAUSA: si alguien vuelve a depender de ese PNG, este test lo explica."""
    import subprocess
    out = subprocess.run(["git", "check-ignore", "-v", "cases/001_gps_403/outputs/shell_clean.png"],
                         cwd=ROOT, capture_output=True, text=True)
    assert "cases/*/outputs/*.png" in out.stdout, \
        "si este patrón cambió, revisar por qué el shell dejó de verse en E26"


def test_la_ruta_del_shell_responde_svg(client, monkeypatch):
    from webapp import intake, store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','READY','DEVELOPMENT')")
    monkeypatch.setattr(intake, "shell_svg_for", lambda cid: "<svg xmlns='x'>ACCESO</svg>")
    r = client.get("/case/x/shell.svg")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("image/svg+xml")


def test_sin_geometria_el_shell_da_404_y_no_una_imagen_rota(client):
    from webapp import store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('y','Y','a.png','a.png','image/png','t','UPLOADED','DEVELOPMENT')")
    assert client.get("/case/y/shell.svg").status_code == 404


# ===================================================================================================
# 9 — biblioteca (§14)
# ===================================================================================================
def test_las_plantas_se_pueden_marcar_como_reservadas(client):
    from webapp import store
    _upload(client, "planta.png", PNG_1PX)
    cid = store.q1("SELECT case_id FROM cases")["case_id"]
    client.post(f"/case/{cid}/track", data={"track": "RESERVED"})
    assert store.q1("SELECT track FROM cases WHERE case_id=?", (cid,))["track"] == "RESERVED"
    assert client.post(f"/case/{cid}/track", data={"track": "LO_QUE_SEA"}).status_code == 400


def test_subir_no_dispara_el_motor(client, monkeypatch):
    """§4/§14 — 50 plantas se suben sin que se generen 150 layouts."""
    from webapp import engine, store
    llamado = []
    monkeypatch.setattr(engine, "enqueue", lambda r: llamado.append(r))
    for i in range(3):
        _upload(client, f"p{i}.png", PNG_1PX)
    assert len(store.q("SELECT * FROM cases")) == 3
    assert llamado == []
    assert {r["status"] for r in store.q("SELECT status FROM cases")} == {"UPLOADED"}


# ===================================================================================================
# 10 — E27.2: inputs obligatorios, bloqueo del avance y fallas de usuario vs técnicas
# ===================================================================================================
INTAKE_COMPLETO = {
    "title": "Unidad X", "declared_clean": "yes",
    "scale_x1": "100", "scale_y1": "100", "scale_x2": "200", "scale_y2": "100", "scale_m": "12",
    "entrance_x": "150", "entrance_y": "300",
    "confirm": ["perimeter", "core", "columns", "daylight", "scale_assumption"],
}


def test_los_obligatorios_estan_marcados_con_asterisco(client):
    """§1 — sin el `*` visible el usuario no puede saber qué le falta antes de intentarlo."""
    from webapp import store
    _upload(client, "planta.png", PNG_1PX)
    cid = store.q1("SELECT case_id FROM cases")["case_id"]
    html = client.get(f"/case/{cid}").get_data(as_text=True)
    for obligatorio in ("¿Esta planta está limpia", "Escala", "Nombre del brief",
                        "Personas (headcount)", "Puestos open"):
        i = html.find(obligatorio)
        assert i > 0, obligatorio
        assert '<span class="req">*</span>' in html[i:i + 400], f"falta el * en: {obligatorio}"
    # y los opcionales NO llevan asterisco
    i = html.find("Fuente")
    assert '<span class="opt">' in html[i:i + 120]


def test_el_backend_rechaza_un_intake_incompleto_con_mensajes_por_campo(client):
    """§2/§4 — no alcanza con deshabilitar el botón: un POST directo también se rechaza."""
    from webapp import store
    _upload(client, "planta.png", PNG_1PX)
    cid = store.q1("SELECT case_id FROM cases")["case_id"]
    r = client.post(f"/case/{cid}/intake", data={"title": "X"})
    assert r.status_code == 400
    html = r.get_data(as_text=True)
    for msg in ("Debes confirmar si la planta está limpia.",
                "Falta definir la escala",
                "Marca el acceso principal",
                "Falta confirmar:"):
        assert msg in html, msg
    # el color no es la única señal: hay texto para cada uno
    assert html.count('class="err"') >= 4


def test_un_intake_incompleto_no_deja_el_caso_en_failed(client):
    """§6 — que falte un dato del usuario NO es un fallo técnico."""
    from webapp import store
    _upload(client, "planta.png", PNG_1PX)
    cid = store.q1("SELECT case_id FROM cases")["case_id"]
    client.post(f"/case/{cid}/intake", data={"title": "X"})
    assert store.q1("SELECT status FROM cases WHERE case_id=?", (cid,))["status"] != "FAILED"


def test_un_shell_sin_preparar_bloquea_la_generacion(client):
    """§3 — la regresión concreta de E27: esto terminaba en FAILED con un traceback."""
    from webapp import store
    _upload(client, "planta.png", PNG_1PX)
    cid = store.q1("SELECT case_id FROM cases")["case_id"]
    r = client.post(f"/case/{cid}/brief", data={"brief_name": "B", "headcount": "48",
                                                "workstations": "40", "generate": "1"})
    assert r.status_code == 400
    assert "Todavía no preparaste el shell" in r.get_data(as_text=True)
    assert store.q("SELECT * FROM runs") == []        # no se creó una corrida condenada
    assert store.q1("SELECT status FROM cases WHERE case_id=?", (cid,))["status"] != "FAILED"


def test_un_shell_incompleto_lista_exactamente_lo_que_el_runtime_pide(client):
    """Los bloqueos salen de `shell_readiness.requires_confirmation`, no de una lista inventada."""
    from webapp import intake, store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','NEEDS_INPUT','DEVELOPMENT')")
    d = os.path.join(store.case_dir("x"), "outputs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "floorplate.json"), "w", encoding="utf-8") as fh:
        json.dump({"shell_readiness": {"ready_for_layout": False,
                                       "requires_confirmation": ["primary_entrance", "columns"]}}, fh)
    faltan = intake.blockers_for_generate("x")
    assert faltan == ["Marcá el acceso principal sobre el plano.", "Confirmá los pilares."]


def test_un_brief_invalido_bloquea_la_generacion_y_no_se_guarda(client):
    """§7 — el juez sigue siendo `BriefV1.validate` del motor; acá sólo se marca el campo."""
    from webapp import store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','READY','DEVELOPMENT')")
    _shell_listo(store)
    r = client.post("/case/x/brief", data={"brief_name": "B", "headcount": "5",
                                           "workstations": "40", "room_private_office": "4",
                                           "generate": "1"})
    assert r.status_code == 400
    assert "target_headcount" in r.get_data(as_text=True)
    assert store.q("SELECT * FROM briefs") == []
    assert store.q("SELECT * FROM runs") == []


def test_el_job_no_llama_al_motor_si_faltan_datos_y_no_dice_failed_del_caso(monkeypatch, client):
    """§4/§6 — cinturón: aunque un job quede encolado, no se gasta CPU ni se miente el estado."""
    from webapp import engine, store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','UPLOADED','DEVELOPMENT')")
    store.ex("INSERT INTO briefs(brief_id,case_id,name,headcount,workstations,rooms,brief_sha256,"
             "created_at) VALUES ('b','x','b',10,5,'[]','sha','t')")
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,created_at) "
             "VALUES ('r','x','b','QUEUED','t')")
    llamadas = []
    monkeypatch.setattr(engine.subprocess, "run", lambda *a, **k: llamadas.append(a))
    engine._execute("r")
    assert llamadas == [], "no se debe invocar el motor con el intake incompleto"
    assert store.q1("SELECT status FROM cases WHERE case_id='x'")["status"] == "NEEDS_INPUT"
    assert "faltan datos del intake" in store.q1("SELECT log FROM runs WHERE run_id='r'")["log"]


def test_una_falla_tecnica_no_arrastra_al_caso(monkeypatch, client):
    """§6 — si el motor revienta por un motivo técnico, la corrida falla; el caso sigue listo."""
    from webapp import engine, store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','READY','DEVELOPMENT')")
    store.ex("INSERT INTO briefs(brief_id,case_id,name,headcount,workstations,rooms,brief_sha256,"
             "created_at) VALUES ('b','x','b',10,5,'[]','sha','t')")
    store.ex("INSERT INTO runs(run_id,case_id,brief_id,status,created_at) "
             "VALUES ('r','x','b','QUEUED','t')")
    _shell_listo(store)

    class R:
        returncode, stdout, stderr = 1, "", "boom: el proceso murió"

    monkeypatch.setattr(engine.subprocess, "run", lambda *a, **k: R())
    engine._execute("r")
    assert store.q1("SELECT status FROM runs WHERE run_id='r'")["status"] == "FAILED"
    assert store.q1("SELECT status FROM cases WHERE case_id='x'")["status"] == "READY"


def test_el_flujo_valido_sigue_pasando(client):
    """§11 — la contracara: con todo completo, nada bloquea."""
    from webapp import briefs, intake, store
    store.ex("INSERT INTO cases(case_id,title,original_filename,source_file,mime,uploaded_at,"
             "status,track) VALUES ('x','X','a.png','a.png','image/png','t','READY','DEVELOPMENT')")
    _shell_listo(store)
    assert intake.blockers_for_generate("x") == []
    assert briefs.field_errors("Brief X", 48, 40, briefs.DEFAULT_ROOMS,
                               os.path.join(ROOT, "program_templates", "modules_office.json")) == {}


def test_un_intake_completo_pasa_la_validacion_de_formulario():
    """El validador no puede ser tan estricto que nada pase: el caso bueno debe dar cero errores."""
    from werkzeug.datastructures import MultiDict

    from webapp import intake
    assert intake.validate_intake_form(MultiDict(
        [(k, x) for k, v in INTAKE_COMPLETO.items()
         for x in (v if isinstance(v, list) else [v])])) == {}


def test_la_escala_acepta_superficie_publicada_como_alternativa():
    """Escala = dos puntos O superficie publicada. Exigir ambas sería inventar un requisito."""
    from werkzeug.datastructures import MultiDict

    from webapp import intake
    datos = {k: v for k, v in INTAKE_COMPLETO.items()
             if not k.startswith("scale_") or k == "scale_assumption"}
    datos["published_area_m2"] = "543"
    errs = intake.validate_intake_form(MultiDict(
        [(k, x) for k, v in datos.items() for x in (v if isinstance(v, list) else [v])]))
    assert "scale" not in errs, errs


def test_una_planta_no_limpia_se_rechaza_con_su_razon():
    """§2 de E27: V1 es shell-only y lo dice, en vez de fallar más adelante sin explicación."""
    from werkzeug.datastructures import MultiDict

    from webapp import intake
    datos = dict(INTAKE_COMPLETO, declared_clean="no")
    errs = intake.validate_intake_form(MultiDict(
        [(k, x) for k, v in datos.items() for x in (v if isinstance(v, list) else [v])]))
    assert "V1 sólo acepta plantas libres" in errs["declared_clean"]
