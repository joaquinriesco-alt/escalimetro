"""E46 (G, J, K, M) — superficie del piloto: autenticación, mismo origen, acceso directo a artefactos,
enumeración de ids, cabeceras; compatibilidad móvil inferible del HTML/backend; dependencias y runtime
Python 3.12 inferibles sin Docker; y contradicciones entre documentos y código.

Tests de CARACTERIZACIÓN: los marcados `DEFECTO E46-Hxx` afirman el comportamiento defectuoso actual
y fallarán el día que se corrija (ver `reports/E46_REPORT.md`). Nada sale a la red ni gasta.
"""
from __future__ import annotations

import ast
import base64
import io
import os
import re
import sys
import tomllib

import pytest

from test_e37_reconstruction_lab import _foto, _plano_real
from test_e45_web_pilot import BASE, _arrancar, _cid, _html, _subir_crear, env  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH = {"Authorization": "Basic " + base64.b64encode(b"joaquin:secreta").decode()}


def _url_para(rule: str) -> str:
    """Rellena una regla de Flask con valores inventados (el primer valor de un `any(...)`)."""
    rule = re.sub(r"<any\(([^,)]*)[^)]*\):\w+>", r"\1", rule)
    return re.sub(r"<[^>]+>", "x1", rule)


def _reglas(app, prefijos=None):
    out = []
    for r in app.url_map.iter_rules():
        if r.endpoint == "static" or (prefijos and not r.rule.startswith(prefijos)):
            continue
        out += [(m, r.rule, r.endpoint) for m in sorted(r.methods - {"HEAD", "OPTIONS"})]
    return out


# =============================================================================================
# G · autenticación
# =============================================================================================
PUBLICAS = {("GET", "/planos/"), ("GET", "/planos/solicitar"), ("POST", "/planos/solicitar"),
            ("GET", "/planos/entrega/<token>"), ("GET", "/planos/entrega/<token>/plano.png"),
            ("GET", "/planos/recibido/<request_id>"), ("GET", "/healthz")}


def test_G1_la_superficie_publica_es_exactamente_el_conjunto_esperado(tmp_path, monkeypatch):
    """Toda ruta del app, sin credenciales: 401 salvo las públicas de E40/E41/E43 y /healthz."""
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    abiertas = set()
    for m, regla, _ep in _reglas(c.application):
        r = c.open(_url_para(regla), method=m, headers={"Origin": "http://localhost"})
        if r.status_code != 401:
            abiertas.add((m, regla))
    assert abiertas == PUBLICAS


def test_G2_credenciales_malas_o_incompletas_dan_401_en_las_rutas_del_piloto_y_de_E37(tmp_path, monkeypatch):
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    malas = [None, {"Authorization": "Basic " + base64.b64encode(b"joaquin:otra").decode()},
             {"Authorization": "Basic " + base64.b64encode(b"otro:secreta").decode()},
             {"Authorization": "Basic " + base64.b64encode(b":").decode()},
             {"Authorization": "Basic " + base64.b64encode(b"joaquin:").decode()},
             {"Authorization": "Basic !!!no-es-base64!!!"}, {"Authorization": "Bearer secreta"},
             {"Authorization": "Basic"}]
    for m, regla, _ep in _reglas(c.application, ("/lab/campaign/e44", "/lab/reconstruction")):
        for h in malas:
            r = c.open(_url_para(regla), method=m, headers={**(h or {}), "Origin": "http://localhost"})
            assert r.status_code == 401, (m, regla, h)
    assert c.get(BASE + "/", headers=AUTH).status_code == 200


def test_G2b_con_ESCALIMETRO_DEV_y_sin_clave_la_app_queda_abierta_pero_con_clave_NO(tmp_path, monkeypatch):
    """DEV sólo abre la puerta si NO hay contraseña; en producción `check_config` impide arrancar sin ella."""
    c = _arrancar(tmp_path, monkeypatch, password="")
    assert c.get(BASE + "/").status_code == 200                      # DEV=1 y sin clave: abierto (local)
    c = _arrancar(tmp_path / "otra", monkeypatch, password="secreta")
    monkeypatch.setenv("ESCALIMETRO_DEV", "1")                       # DEV prendido por error en producción…
    import importlib
    from webapp import auth
    try:
        importlib.reload(auth)                                       # (los globals de `auth` se leen en cada request)
        assert c.get(BASE + "/").status_code == 401                  # …no saltea la contraseña si existe
        assert c.get(BASE + "/", headers=AUTH).status_code == 200
    finally:
        monkeypatch.delenv("ESCALIMETRO_DEV", raising=False)
        importlib.reload(auth)                                       # no dejar el estado de `auth` al resto de la suite


def test_G2f_no_hay_limite_de_intentos_de_contrasena_LIMITACION(tmp_path, monkeypatch):
    """Una sola cuenta, expuesta a Internet, sin freno ni demora por intento fallido: 300 intentos
    seguidos dan 300 veces 401 (sin 429 ni `Retry-After`). El secreto es la única defensa."""
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    codigos, cabeceras = set(), set()
    for i in range(300):
        h = {"Authorization": "Basic " + base64.b64encode(f"joaquin:intento{i}".encode()).decode()}
        r = c.get(BASE + "/", headers=h)
        codigos.add(r.status_code)
        cabeceras |= {k for k in r.headers.keys() if k.lower() in ("retry-after", "x-ratelimit-limit")}
    assert codigos == {401} and not cabeceras
    assert c.get(BASE + "/", headers=AUTH).status_code == 200          # y el correcto sigue entrando


def test_G2c_sin_clave_y_sin_DEV_la_app_no_arranca(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "")
    import importlib
    from webapp import auth
    try:
        importlib.reload(auth)
        with pytest.raises(auth.MissingPassword):
            auth.check_config()
    finally:
        monkeypatch.undo()
        importlib.reload(auth)                                       # no dejar el estado de `auth` al resto de la suite


@pytest.mark.parametrize("usuario,clave", [("josé", "x"), ("joaquin", "ñandú"), ("joaquin", "contraseña")])
def test_G2d_credenciales_con_caracteres_no_ASCII_dan_500_y_no_401_DEFECTO_H11(tmp_path, monkeypatch, usuario, clave):
    """`hmac.compare_digest` sobre `str` no ASCII lanza `TypeError`. Falla cerrado (no hay bypass),
    pero (a) un cliente puede provocar 500 sin credenciales, y (b) una `ESCALIMETRO_PASSWORD` con
    `ñ` o tilde haría imposible entrar: ni siquiera la clave correcta autentica."""
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    h = {"Authorization": "Basic " + base64.b64encode(f"{usuario}:{clave}".encode()).decode()}
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    assert c.get(BASE + "/", headers=h).status_code == 500


def test_G2e_una_clave_con_ñ_configurada_en_el_servidor_nunca_autentica_DEFECTO_H11(tmp_path, monkeypatch):
    c = _arrancar(tmp_path, monkeypatch, password="contraseña")
    h = {"Authorization": "Basic " + base64.b64encode("joaquin:contraseña".encode()).decode()}
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    assert c.get(BASE + "/", headers=h).status_code == 500


# =============================================================================================
# G · mismo origen
# =============================================================================================
_POST_PROTEGIDOS = None


def _posts_guardados(app):
    return [(r, ep) for (m, r, ep) in _reglas(app, ("/lab/campaign/e44", "/lab/reconstruction")) if m == "POST"]


def _cliente_sin_origen(c):
    cl = c.application.test_client()
    return cl


CASO = "/lab/campaign/e44/caso/e44-cre-0123456789/procesar"


@pytest.mark.parametrize("cabeceras,bloqueado", [
    ({}, True),
    ({"Origin": "http://evil.example"}, True),
    ({"Origin": "null"}, True),
    ({"Origin": "https://localhost"}, True),                       # esquema distinto del que ve la app
    ({"Origin": "http://localhost:8030"}, True),                   # puerto distinto
    ({"Origin": "http://localhost.evil.example"}, True),
    ({"Origin": "http://evil.example/http://localhost"}, True),
    ({"Origin": "http://localhost", "Referer": "http://evil.example/x"}, True),
    ({"Referer": "http://evil.example/http://localhost/"}, True),
    ({"Origin": "http://localhost"}, False),
    ({"Referer": "http://localhost/lab/campaign/e44/"}, False),
    ({"Origin": "http://localhost", "Referer": "http://localhost/x"}, False),
    ({"Origin": "https://localhost", "X-Forwarded-Proto": "https"}, False),
    ({"Origin": "https://localhost", "X-Forwarded-Proto": "https, http"}, False),
    ({"Origin": "http://localhost", "X-Forwarded-Proto": "https"}, True),
])
def test_G3_la_guarda_de_mismo_origen_del_piloto_y_E37_en_cada_variante(env, cabeceras, bloqueado):
    c, camp, tmp = env
    sin = _cliente_sin_origen(c)
    r = sin.post(CASO, headers=cabeceras)
    assert (r.status_code == 403) is bloqueado, (cabeceras, r.status_code)


def test_G3b_todas_las_rutas_POST_del_piloto_y_E37_estan_guardadas(env):
    c, camp, tmp = env
    sin = _cliente_sin_origen(c)
    posts = _posts_guardados(c.application)
    assert len(posts) >= 15
    for regla, ep in posts:
        assert sin.post(_url_para(regla), headers={"Origin": "http://evil.example"}).status_code == 403, regla
        assert sin.post(_url_para(regla)).status_code == 403, regla
        assert sin.post(_url_para(regla), headers={"Origin": "http://localhost"}).status_code != 403, regla


def test_G3c_ningun_GET_del_piloto_escribe_por_el_camino_de_un_POST_pero_el_GET_del_caso_asienta_corridas(env):
    """`GET /caso/<id>` ejecuta `settle()`: registra `pipeline`. No es peligroso (sólo asienta lo que ya
    terminó) pero un GET —y por lo tanto un `<img src>` ajeno o un prefetch— escribe en el registro."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import runs
    monkey_enqueue = runs.enqueue
    runs.enqueue = lambda rid: None
    try:
        cid = _cid(_subir_crear(c, n=2))
        c.post(f"{BASE}/caso/{cid}/procesar")
    finally:
        runs.enqueue = monkey_enqueue
    rid = camp._of(cid, "create_started")[0]["data"]["run_id"]
    runs.execute(rid)
    assert [e["kind"] for e in camp.events(cid)] == ["create_started"]
    sin = _cliente_sin_origen(c)
    assert sin.get(f"{BASE}/caso/{cid}").status_code == 200           # un GET sin Origin ni Referer
    assert [e["kind"] for e in camp.events(cid)] == ["create_started", "pipeline"]


# ---- DEFECTO E46-H10 · el resto de la app no tiene guarda de origen --------------------------------
def test_DEFECTO_H10_las_demas_rutas_POST_de_la_app_aceptan_un_Origin_ajeno(env):
    """Sólo `/lab/reconstruction` y `/lab/campaign/e44` filtran por origen. Las otras ~65 rutas POST
    (staging, LAB, benchmark, propiedad del cliente, pedidos, /upload…) dependen únicamente de HTTP
    Basic, que el navegador reenvía solo (la razón por la que E37 puso la guarda). Una página ajena
    puede mandar un formulario con la sesión del operador."""
    c, camp, tmp = env
    sin = _cliente_sin_origen(c)
    sin_guarda, guardadas = [], []
    for m, regla, ep in _reglas(c.application):
        if m != "POST" or regla.startswith("/planos/"):          # /planos es público a propósito
            continue
        r = sin.post(_url_para(regla), headers={"Origin": "http://evil.example"})
        if r.status_code == 403:
            # un 403 que también ocurre con el origen correcto no viene de la guarda (p. ej. el
            # corte por producto/entitlement de /properties/new): no es una ruta guardada
            if sin.post(_url_para(regla), headers={"Origin": "http://localhost"}).status_code == 403:
                continue
            guardadas.append(regla)
        else:
            sin_guarda.append(regla)
    assert len(guardadas) >= 15 and all(g.startswith(("/lab/campaign/e44", "/lab/reconstruction")) for g in guardadas)
    assert len(sin_guarda) >= 60
    for sensible in ("/staging/<property_id>/generate", "/staging/attempt/<attempt_id>/retry",
                     "/lab/benchmark/smoke/<provider>", "/lab/benchmark/run", "/lab/benchmark/approve",
                     "/lab/pedidos/<request_id>/generar", "/property/analizar", "/upload",
                     "/properties/<property_id>/fits/<fit_id>/generate"):
        assert sensible in sin_guarda, sensible


def test_DEFECTO_H10b_con_OPENAI_API_KEY_presente_un_POST_ajeno_llega_a_la_llamada_de_proveedor(env, monkeypatch):
    """El piloto de CREAR exige `OPENAI_API_KEY` en el servidor. Con ella, el proveedor `openai` del
    LAB queda «con credencial» y `POST /lab/benchmark/smoke/openai` («UNA llamada real», sin pedir
    confirmación) llega a `staging.smoke_test` con un Origin ajeno. La llamada está sustituida por un
    registro: NO se hace ninguna llamada real."""
    c, camp, tmp = env
    monkeypatch.setenv("OPENAI_API_KEY", "sk-FALSA-de-prueba")
    from webapp import lab
    llamadas = []
    monkeypatch.setattr(lab.bench, "dataset", lambda: {"photos": [{"asset_id": "a_x", "property_id": "p_x"}]})
    monkeypatch.setattr(lab.staging, "smoke_test",
                        lambda prov, aid, pid: llamadas.append(prov) or {"attempt_id": "att_x"})
    sin = _cliente_sin_origen(c)
    r = sin.post("/lab/benchmark/smoke/openai", headers={"Origin": "http://evil.example"})
    assert r.status_code == 302 and llamadas == ["openai"]
    # las rutas guardadas, en cambio, ni siquiera ejecutan la vista
    assert sin.post("/lab/reconstruction/nuevo", headers={"Origin": "http://evil.example"}).status_code == 403


# =============================================================================================
# G · acceso directo a artefactos
# =============================================================================================
@pytest.mark.parametrize("cual", [
    "real", "REAL", "real/", "real.png", "real%00", "%72eal", "..%2freal", "..", "foto-0", "foto-99", "foto--1",
    "foto-1.5", "foto-", "foto-%20", "despues", "entrada", "reconstruccion", "evidence", "manifest.json",
    "plano_real", "gt", "ground_truth", "preview_plano.png", "index.html", "results"])
def test_G4_ninguna_variante_de_archivo_entrega_el_plano_real_ni_nada_fuera_de_los_roles(env, cual):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    r = c.get(f"{BASE}/caso/{cid}/archivo/{cual}")
    assert r.status_code == 404, (cual, r.status_code)


def test_G4b_foto_1_se_sirve_y_las_cifras_unicode_se_interpretan_o_revientan_DEFECTO_H18(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    assert c.get(f"{BASE}/caso/{cid}/archivo/foto-1").status_code == 200
    assert c.get(f"{BASE}/caso/{cid}/archivo/foto-%EF%BC%91").status_code == 200       # «１» fullwidth = 1
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    assert c.get(f"{BASE}/caso/{cid}/archivo/foto-%C2%B2").status_code == 500          # «²».isdigit() y int() falla


def test_G4c_los_datos_no_se_sirven_por_ninguna_ruta_estatica_ni_de_directorio(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    for u in ("/static/../webapp/campaign.py", "/static/%2e%2e/webapp/campaign.py", "/static/..%2fwebapp/pilot.py",
              "/e44/manifest.json", "/data/e44/manifest.json", f"/e44/cases/{cid}/evidence/foto_01.png",
              "/reconstruction_gt/", "/escalimetro.db", f"{BASE}/../../../etc/passwd", f"{BASE}/caso/..%2f..%2fx",
              f"{BASE}/archivo/real", "/lab/campaign/e44/static/pilot.css"):
        assert c.get(u).status_code in (404, 308, 301), u


def test_G4d_un_id_de_otro_proyecto_o_corrida_no_abre_el_recurso_ajeno(env):
    from webapp.domain.reconstruction import projects, runs
    c, camp, tmp = env
    a = _cid(_subir_crear(c, n=2))
    b = camp.import_upload(camp.CREATE, [("f.png", _foto(40)), ("g.png", _foto(41))],
                           ground_truth=("g.png", _plano_real() + b"b"))
    pa, pb = camp.get(a)["recon_project_id"], camp.get(b)["recon_project_id"]
    aset_b = projects.assets_of(pb)[0]["asset_id"]
    assert c.get(f"/lab/reconstruction/p/{pb}/asset/{aset_b}").status_code == 200
    assert c.get(f"/lab/reconstruction/p/{pa}/asset/{aset_b}").status_code == 404
    c.post(f"{BASE}/caso/{a}/procesar")
    rid = runs.of_project(pa)[0]["run_id"]
    assert c.get(f"/lab/reconstruction/p/{pa}/r/{rid}").status_code == 200
    assert c.get(f"/lab/reconstruction/p/{pb}/r/{rid}").status_code == 404
    assert c.get(f"/lab/reconstruction/p/{pb}/r/{rid}/plano.svg").status_code == 404


def test_G5_el_oraculo_de_existencia_del_plano_real_no_existe_antes_del_reveal(env):
    """`archivo/real` antes del reveal es indistinguible de un archivo que no existe."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    real = c.get(f"{BASE}/caso/{cid}/archivo/real")
    nada = c.get(f"{BASE}/caso/{cid}/archivo/zzzz")
    assert (real.status_code, real.get_data(), real.mimetype) == (nada.status_code, nada.get_data(), nada.mimetype)
    pid = camp.get(cid)["recon_project_id"]
    gt1 = c.get(f"/lab/reconstruction/p/{pid}/plano-real")
    gt2 = c.get(f"/lab/reconstruction/p/{pid}/plano-realx")
    assert gt1.status_code == gt2.status_code == 404


def test_G6_los_ids_de_caso_se_derivan_de_la_propiedad_no_son_secretos_pero_el_404_es_uniforme(env):
    """El id de un caso es `e44-<imp|cre>-sha256(json[propiedad, pista])[:10]`: 40 bits determinísticos.
    No es un secreto (todo está tras Basic Auth) pero tampoco hay forma de distinguir «no existe» de
    «mal formado» por la respuesta."""
    import hashlib
    import json
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    caso = camp.get(cid)
    esperado = "e44-cre-" + hashlib.sha256(json.dumps([caso["property_key"], "CREATE"],
                                                       sort_keys=True).encode()).hexdigest()[:10]
    assert cid == esperado
    inexistente = c.get(f"{BASE}/caso/e44-cre-0000000000")
    malformado = c.get(f"{BASE}/caso/no-es-un-id")
    assert (inexistente.status_code, inexistente.get_data()) == (malformado.status_code, malformado.get_data())


def test_G6b_tokens_e_ids_publicos_salen_de_secrets_o_uuid4():
    for rel, patron in (("webapp/entrega.py", r"secrets\.token_urlsafe\((\d+)\)"),
                        ("webapp/public.py", r"uuid\.uuid4\(\)\.hex")):
        fuente = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        m = re.search(patron, fuente)
        assert m, rel
        if m.groups():
            assert int(m.group(1)) >= 32                              # ≥ 256 bits


def test_G6c_la_entrega_publica_responde_404_igual_a_un_token_mal_formado_o_desconocido(tmp_path, monkeypatch):
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    cuerpos = {(r.status_code, r.get_data()) for r in (
        c.get("/planos/entrega/x"), c.get("/planos/entrega/" + "A" * 43), c.get("/planos/entrega/%00"),
        c.get("/planos/entrega/" + "A" * 43 + "/plano.png"), c.get("/planos/entrega/../x"))}
    assert len({s for s, _ in cuerpos}) == 1 and list({s for s, _ in cuerpos})[0] == 404


def test_DEFECTO_H13_el_formulario_publico_de_pedidos_escribe_hasta_40_MB_sin_cuenta_ni_freno(tmp_path, monkeypatch):
    """`POST /planos/solicitar` no pide credenciales (es la landing de E40/E41) y guarda en el MISMO
    volumen que el piloto. Valida sólo los 8 primeros bytes: un «PDF» de 30 MB de basura se acepta y
    queda en disco; y no hay límite de frecuencia ni de espacio. Documentado en E41 como «sin freno
    contra abuso»; aquí se mide que sigue así con la web piloto desplegada al lado."""
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    grande = b"%PDF-1.4\n" + b"\x00" * (30 * 1024 * 1024)
    r = c.post("/planos/solicitar", data={"email": "x@example.com", "plano": (io.BytesIO(grande), "p.pdf")},
               content_type="multipart/form-data")
    assert r.status_code == 303
    for i in range(12):                                             # y sin freno por repetición
        r = c.post("/planos/solicitar", data={"email": f"x{i}@example.com",
                                              "plano": (io.BytesIO(b"%PDF-1.4\n" + bytes([i]) * 64), "p.pdf")},
                   content_type="multipart/form-data")
        assert r.status_code == 303, i
    base = tmp_path / "data" / "plano_requests"
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _s, fs in os.walk(base) for f in fs)
    assert total > 30 * 1024 * 1024
    fuente = open(os.path.join(ROOT, "webapp", "public.py"), encoding="utf-8").read()
    assert "statvfs" not in fuente and "disk_usage" not in fuente


# ---- cabeceras ------------------------------------------------------------------------------------
def test_DEFECTO_H14_ninguna_respuesta_lleva_cabeceras_de_seguridad(env):
    """Sin `X-Frame-Options`/CSP `frame-ancestors`: la web piloto (con botones que gastan o revelan)
    puede enmarcarse en otro sitio; la guarda de Origin no lo detiene porque el clic se origina
    dentro de nuestra propia página. Sin `nosniff` en los archivos servidos."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    for u in (f"{BASE}/", f"{BASE}/caso/{cid}", f"{BASE}/caso/{cid}/archivo/foto-1"):
        h = c.get(u).headers
        for nombre in ("X-Frame-Options", "Content-Security-Policy", "X-Content-Type-Options",
                       "Referrer-Policy", "Strict-Transport-Security"):
            assert nombre not in h, (u, nombre)
    fuente = open(os.path.join(ROOT, "webapp", "app.py"), encoding="utf-8").read()
    assert "after_request" not in fuente


# =============================================================================================
# J · compatibilidad móvil inferible desde el HTML y el backend
# =============================================================================================
def _campos(html: str, etiqueta: str):
    return [m.group(0) for m in re.finditer(rf"<{etiqueta}\b[^>]*>", html)]


def test_J1_el_formulario_de_CREAR_es_usable_desde_un_iPhone(env):
    from webapp import mobile_upload as mu
    c, camp, tmp = env
    h = _html(c, f"{BASE}/crear")
    assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in h and '<html lang="es">' in h
    form = re.search(r"<form\b[^>]*>", h).group(0)
    assert 'method="post"' in form and 'enctype="multipart/form-data"' in form
    entradas = {re.search(r'name="(\w+)"', i).group(1): i for i in _campos(h, "input") + _campos(h, "textarea")
                if 'name="' in i}
    # los nombres que el HTML manda son los que el backend lee
    fuente = open(os.path.join(ROOT, "webapp", "pilot.py"), encoding="utf-8").read()
    for nombre in ("fotos", "plano_real", "m2", "referencia"):
        assert nombre in entradas and re.search(rf'"{nombre}"', fuente)
    fotos = entradas["fotos"]
    assert "multiple" in fotos and "required" in fotos and 'type="file"' in fotos
    for ext in (".heic", ".heif", "image/heic", "image/heif", "image/jpeg", "image/png", "image/webp"):
        assert ext in fotos
    assert f'accept="{mu.ACCEPT_FOTOS}"' in fotos
    assert 'inputmode="decimal"' in entradas["m2"]
    assert "capture" not in fotos                                    # no fuerza la cámara: deja la fototeca
    for n, valor in ((mu.MAX_FOTOS, "fotos"), (mu.MAX_FOTO_MB, "MB cada una"), (mu.MAX_LOTE_MB, "MB en total"),
                     (mu.MAX_PLANO_REAL_MB, "MB")):
        assert str(n) in h
    assert "NO SE ENVÍA AL MOTOR" in h


def test_J2_el_CSS_cumple_lo_que_iOS_necesita_inferido_de_las_reglas(env):
    css = open(os.path.join(ROOT, "webapp", "static", "pilot.css"), encoding="utf-8").read()
    assert "-webkit-text-size-adjust:100%" in css
    # los campos heredan 17 px (>= 16 px): iOS Safari no hace zoom al enfocar
    assert re.search(r"input\[type=text\][^{]*\{[^}]*font:inherit", css)
    assert re.search(r"body\{[^}]*font:17px", css)
    # botón: 14 px de relleno vertical + línea de ~24 px ⇒ ≥ 44 px de alto táctil
    assert re.search(r"\.btn\{[^}]*padding:14px 26px", css)
    assert "@media(max-width:820px)" in css                            # hay reglas de pantalla chica
    # sin anchos fijos en px por encima de 400 salvo max-width
    for m in re.finditer(r"(?<!max-)(?<!min-)width:(\d+)px", css):
        assert int(m.group(1)) <= 400, m.group(0)


def test_J3_todas_las_paginas_del_piloto_declaran_viewport_y_ninguna_usa_JS_externo(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    for u in ("/", "/panel", "/mejorar", "/crear", f"/caso/{cid}"):
        h = _html(c, BASE + u)
        assert 'name="viewport"' in h, u
        assert "<script" not in h.lower(), u                           # sin JS: tampoco guardia de doble envío
        assert "http://" not in h and "https://" not in h.replace("https://www.w3.org", ""), u


def test_J4_no_hay_proteccion_de_doble_envio_en_el_cliente(env):
    """Ningún `<form>` del piloto deshabilita su botón al enviar ni lleva token de un solo uso: la
    única defensa contra el doble toque es el servidor (y el servidor falla: H02, H03)."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    for u in ("/crear", "/mejorar", f"/caso/{cid}"):
        h = _html(c, BASE + u)
        assert "onsubmit" not in h and "disabled" not in re.sub(r"\.btn\[disabled\]", "", h)
    assert not [f for f in os.listdir(os.path.join(ROOT, "webapp", "static")) if f.endswith(".js")]


def test_J5_los_servicios_no_dependen_de_un_navegador_para_la_conversion_HEIC():
    """Safari iOS puede entregar HEIC o JPEG según el ajuste «Originales»: el backend acepta ambos."""
    from webapp import mobile_upload as mu
    assert ".heic" in mu.FOTO_EXTS and ".heif" in mu.FOTO_EXTS and ".jpg" in mu.FOTO_EXTS


# =============================================================================================
# K · dependencias y runtime (inferibles sin Docker)
# =============================================================================================
def _req_nombres(path):
    out = set()
    for linea in open(path, encoding="utf-8"):
        linea = linea.split("#")[0].strip()
        if linea:
            out.add(re.split(r"[<>=!~\[;]", linea)[0].strip().lower().replace("_", "-"))
    return out


def test_K1_el_runtime_es_Python_3_12_en_Dockerfile_venv_y_requisito_de_pyproject():
    dockerfile = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    assert re.search(r"^FROM python:3\.12-slim", dockerfile, re.M)
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
        py = tomllib.load(fh)
    assert py["project"]["requires-python"] == ">=3.10"            # más laxo que la imagen real (3.12)
    assert "--workers 1 --threads 8 --timeout 180" in dockerfile
    if sys.version_info[:2] != (3, 12):
        pytest.skip(f"el intérprete de esta máquina es {sys.version_info[:2]}, no el 3.12 de la imagen")


def test_K2_requirements_dice_ser_espejo_de_pyproject_pero_no_lo_es_DEFECTO_H15():
    req = _req_nombres(os.path.join(ROOT, "requirements.txt"))
    py = tomllib.load(open(os.path.join(ROOT, "pyproject.toml"), "rb"))
    declarado = {re.split(r"[<>=!~\[;]", d)[0].strip().lower().replace("_", "-") for d in py["project"]["dependencies"]}
    assert "Espejo de [project.dependencies]" in open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read()
    assert declarado <= req
    assert req - declarado == {"flask", "gunicorn", "pillow-heif"}


def test_K3_importaciones_de_terceros_del_runtime_que_ninguna_dependencia_declara_DEFECTO_H15():
    """Recorre `webapp/`, `src/` y `scripts/` y compara con requirements.txt. `skimage` (staging) no se
    declara en ningún lado: su import está en un `try/except Exception: pass`, así que en producción el
    chequeo SSIM de ambientación se omite en silencio. `PIL` llega sólo como dependencia transitiva."""
    declaradas = _req_nombres(os.path.join(ROOT, "requirements.txt"))
    distribucion = {"cv2": "opencv-python-headless", "PIL": "pillow", "pillow_heif": "pillow-heif",
                    "resvg_py": "resvg-py", "skimage": "scikit-image", "google": "google-genai",
                    "flask": "flask", "werkzeug": "werkzeug"}
    internos = {"webapp", "escalimetro", "scripts", "__future__", "run_benchmark", "sam2"}
    usados = {}
    for base in ("webapp", "src", "scripts"):
        for d, _s, fs in os.walk(os.path.join(ROOT, base)):
            for f in fs:
                if not f.endswith(".py"):
                    continue
                ruta = os.path.join(d, f)
                for n in ast.walk(ast.parse(open(ruta, encoding="utf-8").read())):
                    mods = ([a.name.split(".")[0] for a in n.names] if isinstance(n, ast.Import)
                            else [n.module.split(".")[0]] if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module
                            else [])
                    for m in mods:
                        if m not in sys.stdlib_module_names and m not in internos:
                            usados.setdefault(m, set()).add(os.path.relpath(ruta, ROOT))
    sin_declarar = {m for m in usados if distribucion.get(m, m).lower().replace("_", "-") not in declaradas}
    assert sin_declarar == {"PIL", "skimage", "google", "werkzeug"}
    assert usados["skimage"] == {os.path.join("webapp", "domain", "staging.py")}


def test_K4_pillow_heif_funciona_aqui_con_libheif_y_el_decodificador_HEVC():
    import pillow_heif
    info = pillow_heif.libheif_info()
    assert info["decoders"] and "AVIF" in info
    assert tuple(int(x) for x in pillow_heif.__version__.split(".")[:2]) >= (0, 18)


def test_K5_el_baseline_del_motor_depende_de_las_versiones_de_las_librerias_LIMITACION():
    """`requirements.txt` sólo pone cotas inferiores (`>=`): dos instalaciones válidas pueden dar un
    motor distinto. En esta máquina (opencv 5.x / numpy 2.x) el test de baseline de E16.4 falla con
    `src/` idéntico: la suite lo registra como fallo de entorno, no de código."""
    lineas = [l.split("#")[0].strip() for l in open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8")]
    reales = [l for l in lineas if l]
    assert reales and all(">=" in l for l in reales)
    assert not any("==" in l for l in reales)
    assert not os.path.exists(os.path.join(ROOT, "requirements.lock")) and not os.path.exists(
        os.path.join(ROOT, "constraints.txt"))


def test_K7_todo_el_codigo_de_runtime_compila_en_3_12_sin_SyntaxWarning_y_la_app_se_importa():
    """Compila (sin escribir .pyc) `webapp/`, `src/`, `scripts/` y `wsgi.py` con las advertencias
    como error —en 3.12 un escape inválido en un string ya es `SyntaxWarning`— y crea la app como lo
    hace `gunicorn wsgi:app`."""
    import warnings
    n = 0
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for base in ("webapp", "src", "scripts"):
            for d, _s, fs in os.walk(os.path.join(ROOT, base)):
                for f in fs:
                    if f.endswith(".py"):
                        ruta = os.path.join(d, f)
                        with open(ruta, encoding="utf-8") as fh:
                            compile(fh.read(), ruta, "exec")
                        n += 1
        with open(os.path.join(ROOT, "wsgi.py"), encoding="utf-8") as fh:
            compile(fh.read(), "wsgi.py", "exec")
    assert n > 100


def test_K7b_gunicorn_arranca_el_modulo_wsgi_con_clave_y_sirve_healthz(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "secreta")
    monkeypatch.setenv("ESCALIMETRO_DEV", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    for m in ("webapp.store", "webapp.auth", "webapp.app"):
        importlib.reload(importlib.import_module(m))
    sys.modules.pop("wsgi", None)
    sys.path.insert(0, ROOT)
    try:
        wsgi = importlib.import_module("wsgi")
    finally:
        sys.path.remove(ROOT)
        sys.modules.pop("wsgi", None)
    r = wsgi.app.test_client().get("/healthz")
    assert r.status_code == 200


def test_K8_el_dockerignore_no_cubre_lo_que_el_gitignore_si_DEFECTO_H24():
    """`.gitignore` excluye `.data-*/` (donde viven los datos de trabajo, según CLAUDE.md) y `.env*`;
    `.dockerignore` sólo excluye `.data`. Un `docker build .` o un `railway up` desde una máquina de
    desarrollo (no desde un clon limpio de GitHub) copiaría `.data-lab/`, `.env*` y `node_modules/` a
    la imagen con `COPY . .`. Riesgo plausible no reproducido (sin Docker)."""
    with open(os.path.join(ROOT, ".dockerignore"), encoding="utf-8") as fh:
        docker = {l.strip() for l in fh if l.strip() and not l.startswith("#")}
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        git = {l.strip() for l in fh if l.strip() and not l.startswith("#")}
    assert ".data-*/" in git and ".env" in git and ".env.*" in git
    assert ".data" in docker
    assert not ({".data-*", ".data-*/", ".env", ".env.*", "node_modules"} & docker)
    assert "COPY . ." in open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()


def test_K6_el_Dockerfile_instala_las_librerias_de_sistema_que_el_runtime_necesita():
    d = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    for paquete in ("tesseract-ocr", "libgl1", "libglib2.0-0", "libcairo2"):
        assert paquete in d
    assert "libheif" not in d                                          # va dentro de la wheel de pillow-heif


# =============================================================================================
# M · contradicciones entre documentos y código
# =============================================================================================
def test_M1_las_constantes_de_E45_2_son_las_que_dice_su_REPORT_y_su_docstring():
    from webapp import mobile_upload as mu
    rep = open(os.path.join(ROOT, "reports", "E45.2_REPORT.md"), encoding="utf-8").read()
    assert (mu.MAX_FOTOS, mu.MAX_FOTO_MB, mu.MAX_LOTE_MB, mu.MAX_PLANO_REAL_MB) == (20, 15, 120, 25)
    assert (mu.MAX_PIXELES, mu.MAX_LADO_PX) == (80_000_000, 12_000)
    assert "**147 MB** (120 + 25 + 2)" in rep and mu.MAX_ENVIO_BYTES == 147 * 1024 * 1024


def test_M2_el_REPORT_de_E45_2_afirma_que_una_imagen_pequena_en_bytes_no_agota_memoria_CONTRADICCION():
    """«una imagen pequeña en bytes pero enorme en píxeles no agota memoria»: cierto para lo que
    excede 80 Mpx; pero una de 79 Mpx y ~95 KB sí cuesta cientos de MB (ver D4d en
    `test_e46_adv_uploads.py`). Se fija sólo el texto de la afirmación para que la contradicción
    quede trazada."""
    rep = open(os.path.join(ROOT, "reports", "E45.2_REPORT.md"), encoding="utf-8").read()
    assert "una imagen pequeña en bytes pero\n   enorme en píxeles no agota memoria" in rep


def test_M4_el_REPORT_de_E45_2_reconoce_que_MEJORAR_sigue_sin_cota_de_lectura():
    rep = open(os.path.join(ROOT, "reports", "E45.2_REPORT.md"), encoding="utf-8").read()
    assert "`mejorar_post` sigue usando `f.read()`" in rep
    fuente = open(os.path.join(ROOT, "webapp", "pilot.py"), encoding="utf-8").read()
    assert "f.read()" in fuente
