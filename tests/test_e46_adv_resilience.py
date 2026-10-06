"""E46 (E, F) — persistencia ante fallos simulados, reintentos, doble clic y concurrencia razonable
del piloto (E44 + E45 + E45.2).

La app corre con `gunicorn --workers 1 --threads 8` (Dockerfile): las peticiones SÍ se atienden en
paralelo dentro de un proceso. Las condiciones de carrera se fuerzan de forma determinista con una
barrera en el punto exacto de la ventana (se dice en cada test); los tests marcados «natural» no
fuerzan nada salvo que ambos hilos arranquen juntos.

Tests de CARACTERIZACIÓN: los marcados `DEFECTO E46-Hxx` afirman el comportamiento defectuoso actual
y fallarán el día que se corrija (ver `reports/E46_REPORT.md`). Material sintético; sin red ni gasto.
"""
from __future__ import annotations

import io
import os
import threading
import time
from collections import Counter

import pytest

from test_e37_reconstruction_lab import _foto, _png, _plano_real
from test_e45_web_pilot import (BASE, _cid, _eval_plano, _eval_ux, _html, _subir_crear,  # noqa: F401
                                _subir_mejorar, env, planta_lista, planta_no_lista)


def _tipos(camp, cid):
    return [e["kind"] for e in camp.events(cid)]


def _cliente(c):
    cl = c.application.test_client()
    cl.environ_base["HTTP_ORIGIN"] = "http://localhost"
    return cl


def _material(semilla: int, n: int = 2):
    """Fotos y plano real ÚNICOS por semilla (mismos bytes = duplicado)."""
    fotos = [(f"f{i}.png", _png(64, 48, bytes([(semilla * 7 + i * 31) % 256, (semilla * 13 + i) % 256,
                                                (semilla // 3 + i * 5) % 256]))) for i in range(n)]
    return fotos, ("gt.png", _plano_real() + semilla.to_bytes(3, "big"))


def _importar(camp, semilla=1, **kw):
    fotos, gt = _material(semilla)
    return camp.import_upload(camp.CREATE, fotos, ground_truth=gt, **kw)


def _huerfanos_e37():
    from webapp.domain.reconstruction import projects
    return projects.listing()


# =============================================================================================
# E · persistencia y atomicidad ante fallos simulados
# =============================================================================================
def test_E1_si_falla_el_guardado_del_manifiesto_quedan_huerfanos_y_el_primer_reintento_tambien_falla_DEFECTO_H08(
        env, monkeypatch):
    """`_save` es lo último que ocurre; antes ya se creó el proyecto E37 (con el plano real) y se
    copió la evidencia (de sólo lectura). Un fallo ahí deja un proyecto huérfano y una carpeta de
    caso que hace fallar el primer reintento (copiar sobre un archivo 0444); sólo el segundo entra,
    y deja el proyecto huérfano del primer intento para siempre."""
    c, camp, tmp = env
    real_save = camp._save
    monkeypatch.setattr(camp, "_save", lambda m: (_ for _ in ()).throw(OSError("disco lleno")))
    assert _subir_crear(c, n=2).status_code == 500
    monkeypatch.setattr(camp, "_save", real_save)
    assert camp.load()["cases"] == []
    assert len(_huerfanos_e37()) == 1                              # el proyecto con su GT quedó
    assert os.listdir(os.path.join(camp.root(), "cases"))          # y la carpeta de evidencia
    assert _subir_crear(c, n=2).status_code == 500                 # 1.er reintento: PermissionError
    r = _subir_crear(c, n=2)
    assert r.status_code == 303                                    # 2.º reintento: entra
    assert len(camp.load()["cases"]) == 1 and len(_huerfanos_e37()) == 2


def test_E2_si_E37_rechaza_el_material_a_mitad_de_camino_el_proyecto_E37_queda_huerfano_DEFECTO_H08(
        env, monkeypatch):
    """La campaña limpia la evidencia (`rmtree`) pero no el proyecto ni el plano real que ya creó E37."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import groundtruth, projects

    def rechaza(*a, **k):
        raise projects.ReconError("simulado")
    monkeypatch.setattr(groundtruth, "upload", rechaza)
    r = _subir_crear(c, n=2)
    assert r.status_code == 400 and "E37 rechazó" in r.get_data(as_text=True)
    assert camp.load()["cases"] == []
    assert not os.listdir(os.path.join(camp.root(), "cases"))      # evidencia limpiada
    assert len(_huerfanos_e37()) == 1                              # proyecto huérfano, sin GT ni caso


def test_E3_un_evento_truncado_envenena_todas_las_paginas_DEFECTO_H06(env):
    """`events()` no tolera un archivo ilegible: un solo evento truncado (corte de proceso o disco
    lleno a mitad de escritura) hace caer la portada, el panel y el caso, y `count()`/`summary()`
    para TODOS los casos. Se recupera borrando el archivo a mano."""
    c, camp, tmp = env
    ok = _cid(_subir_crear(c, n=2))
    otro = _importar(camp, semilla=9)
    c.post(f"{BASE}/caso/{ok}/procesar")
    d = os.path.join(camp.case_dir(ok), "results")
    roto = os.path.join(d, "099_ux_evaluation.json")
    open(roto, "w").write('{"seq": 99, "kind": "ux_')
    for url in ("/", "/panel", f"/caso/{ok}"):
        assert c.get(BASE + url).status_code == 500, url
    assert c.get(f"{BASE}/caso/{otro}").status_code == 200        # la página de OTRO caso sí abre
    with pytest.raises(ValueError):
        camp.count("CREATE")
    with pytest.raises(ValueError):
        camp.summary()
    os.remove(roto)                                                # recuperación manual
    assert c.get(BASE + "/panel").status_code == 200


def test_E3b_una_escritura_de_evento_que_falla_a_mitad_deja_el_archivo_parcial_DEFECTO_H06(env, monkeypatch):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))

    def escribe_a_medias(obj, fh, **k):
        fh.write('{"seq": 1, "kin')
        raise OSError("disco lleno")
    real_dump = camp.json.dump
    monkeypatch.setattr(camp.json, "dump", escribe_a_medias)
    with pytest.raises(OSError):
        camp.record(cid, "blocked", {"status": camp.BLOCKED_MATERIAL})
    monkeypatch.setattr(camp.json, "dump", real_dump)
    archivos = os.listdir(os.path.join(camp.case_dir(cid), "results"))
    assert archivos == ["001_blocked.json"]                        # quedó el archivo truncado
    with pytest.raises(ValueError):
        camp.events(cid)


def test_E4_un_manifiesto_ilegible_tumba_la_campania_entera_LIMITACION(env):
    """`_save` es atómico (tmp + os.replace), así que sólo una corrupción externa lo trunca."""
    c, camp, tmp = env
    _cid(_subir_crear(c, n=2))
    open(camp._manifest_path(), "w").write('{"cases": [{"case_id": "e44-cre')
    for url in ("/", "/panel", "/crear"):
        r = c.get(BASE + url)
        assert r.status_code == (500 if url != "/crear" else 200), url


def test_E5_un_corte_entre_el_cierre_y_el_reveal_se_recupera_sin_filtrar(env, monkeypatch):
    """INVARIANTE CONFIRMADO: si el proceso muere después de registrar el cierre y antes de revelar,
    el plano real sigue oculto y repetir «cerrar» completa el reveal sin duplicar el cierre."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import groundtruth
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    real = groundtruth.reveal

    def muere(*a, **k):
        raise RuntimeError("proceso muerto")
    monkeypatch.setattr(groundtruth, "reveal", muere)
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 500
    assert [k for k in _tipos(camp, cid) if k in ("closure", "reveal")] == ["closure"]
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404      # sigue oculto
    monkeypatch.setattr(groundtruth, "reveal", real)
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert [k for k in _tipos(camp, cid) if k in ("closure", "reveal")] == ["closure", "reveal"]
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 200


def test_E5b_un_corte_despues_del_reveal_de_E37_y_antes_del_evento_falla_cerrado(env, monkeypatch):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    real = camp.record

    def record_sin_reveal(case_id, kind, data):
        if kind == "reveal":
            raise RuntimeError("proceso muerto")
        return real(case_id, kind, data)
    monkeypatch.setattr(camp, "record", record_sin_reveal)
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 500
    pid = camp.get(cid)["recon_project_id"]
    from webapp.domain.reconstruction import projects
    assert projects.get(pid)["gt_state"] == "REVEALED" and not camp._of(cid, "reveal")
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404      # la web no lo sirve
    monkeypatch.setattr(camp, "record", real)
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert _tipos(camp, cid).count("reveal") == 1 and _tipos(camp, cid).count("closure") == 1


def test_E6_un_reinicio_con_la_corrida_en_cola_se_puede_reintentar_H05_CERRADO(env, monkeypatch):
    """Redeploy de Railway durante el procesamiento: `reset_orphans` pasa la corrida a FAILED («no se
    reanuda»). E47.8 (cierra E46-H05): el FAILED queda asentado e inmutable, NO cuenta como ejecutado
    y la web ofrece VOLVER A INTENTAR; el reintento crea una corrida nueva."""
    c, camp, tmp = env
    from webapp import store
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)          # la corrida queda QUEUED
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert "PROCESANDO" in _html(c, f"{BASE}/caso/{cid}")
    store.reset_orphans()                                          # el arranque tras el redeploy
    pagina = _html(c, f"{BASE}/caso/{cid}")
    assert _tipos(camp, cid) == ["create_started", "pipeline"]
    assert camp._of(cid, "pipeline")[0]["data"]["status"] == "FAILED"
    assert "VOLVER A INTENTAR" in pagina
    assert camp.count("CREATE")["executed"] == 0 and camp.count("CREATE")["captured"] == 1
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303   # el reintento entra
    assert _tipos(camp, cid).count("create_started") == 2


def test_E6b_una_falla_del_motor_se_puede_reintentar_H05_CERRADO(env):
    """Un timeout o un 429 del proveedor (EngineError) es un intento fallido, no el resultado del
    caso: se reintenta desde la web y el intento previo queda en el historial."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture

    class Roto(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

        def reconstruct(self, req):
            raise engines.EngineError("PROVIDER_TIMEOUT", "timeout transitorio")
    engines.register(Roto())
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    pagina = _html(c, f"{BASE}/caso/{cid}")
    assert camp.status(camp.get(cid)) == camp.CAPTURED
    assert "VOLVER A INTENTAR" in pagina
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    assert [p["data"]["attempt"] for p in camp._of(cid, "pipeline")] == [1, 2]
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "x"}).status_code == 400   # sin DONE no hay qué corregir


def test_E7_si_la_cola_no_arranca_el_caso_queda_PROCESANDO_hasta_un_reinicio(env, monkeypatch):
    c, camp, tmp = env
    from webapp import store
    from webapp.domain.reconstruction import runs

    def sin_hilos(rid):
        raise RuntimeError("no se pudo crear el hilo")
    monkeypatch.setattr(runs, "enqueue", sin_hilos)
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 500
    assert _tipos(camp, cid) == ["create_started"]
    assert "PROCESANDO" in _html(c, f"{BASE}/caso/{cid}")
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409       # «ya fue lanzada»
    store.reset_orphans()
    assert "SIN RESULTADO" in _html(c, f"{BASE}/caso/{cid}")


def test_E8_un_fallo_de_E37_al_cerrar_la_corrida_no_deja_la_base_trabada(env, monkeypatch):
    """Resiliencia: si el motor revienta con una excepción cualquiera, la corrida queda FAILED y la
    base sigue aceptando escrituras de otros casos."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture

    class Explota(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

        def reconstruct(self, req):
            raise ZeroDivisionError("boom")
    engines.register(Explota())
    a = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{a}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{a}")
    assert camp._of(a, "pipeline")[0]["data"]["status"] == "FAILED"
    assert "ZeroDivisionError" in camp._of(a, "pipeline")[0]["data"]["error"]
    assert camp.status(camp.get(_importar(camp, semilla=77))) == camp.CAPTURED     # la base sigue escribible


@pytest.mark.parametrize("variante", ["engine_error", "excepcion_generica", "error_con_parcial"])
def test_E8b_la_clave_del_proveedor_no_sobrevive_en_ningun_artefacto_si_el_motor_la_repite(env, monkeypatch,
                                                                                         variante):
    """Un proveedor (o su cliente HTTP) puede devolver la credencial dentro de un mensaje de error. Se
    simula con una clave falsa que el motor de prueba repite en el error, en una excepción cualquiera
    y en el `partial` de la corrida; luego se busca en TODO: archivos, tablas, páginas y eventos."""
    c, camp, tmp = env
    clave = "sk" + "-FALSA-E46-0123456789abcdefghijkl"        # partida: que el escáner de secretos no la tome por real
    monkeypatch.setenv("OPENAI_API_KEY", clave)
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture

    class Delata(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

        def reconstruct(self, req):
            if variante == "excepcion_generica":
                raise RuntimeError(f"401 Unauthorized: Bearer {clave}")
            parcial = {"request_summary": {"authorization": f"Bearer {clave}"},
                       "raw": {"echo": f"clave {clave}"}, "usage": {"input_tokens": 3, "nota": clave}}
            raise engines.EngineError("PROVIDER_401", f"clave rechazada: {clave}",
                                      parcial if variante == "error_con_parcial" else None)
    engines.register(Delata())
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    paginas = [_html(c, f"{BASE}/caso/{cid}"), _html(c, f"{BASE}/panel"), _html(c, f"{BASE}/")]
    pid = camp.get(cid)["recon_project_id"]
    from webapp.domain.reconstruction import runs
    for r in runs.of_project(pid):
        paginas.append(_html(c, f"/lab/reconstruction/p/{pid}/r/{r['run_id']}"))
    assert not [p for p in paginas if clave in p]
    camp.build_index()
    for d, _s, fs in os.walk(str(tmp / "data")):
        for f in fs:
            if f.endswith((".db-shm",)):
                continue
            ruta = os.path.join(d, f)
            if f.endswith((".db", ".db-wal")):
                continue                                         # la base se audita por tabla
            assert clave.encode() not in open(ruta, "rb").read(), ruta
    import sqlite3
    db = sqlite3.connect(str(tmp / "data" / "escalimetro.db"))
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        volcado = str(db.execute(f'SELECT * FROM "{t}"').fetchall())
        assert clave not in volcado, t


def _motor_que_falla_con(mensaje):
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture

    class Roto(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

        def reconstruct(self, req):
            raise engines.EngineError("PROVIDER_500", mensaje)
    engines.register(Roto())


def test_E11_un_error_del_proveedor_con_9_digitos_seguidos_mata_el_panel_y_el_caso_DEFECTO_H21(env):
    """`record()` pasa el texto libre `error` por el detector de PII (`_no_pii`, teléfonos = 9+ dígitos
    con separadores). El mensaje de un fallo del proveedor (un timestamp, un id de petición con una
    racha de dígitos, una cifra larga) lo dispara: `settle()` —que corre en CADA GET del caso y del
    panel— lanza `CampaignError`, el `pipeline` nunca se registra y la corrida FAILED queda sin
    asentar. Resultado: la página del caso y `/panel` dan 500 para toda la campaña, y el caso queda
    PROCESANDO para siempre. No hay salida desde la web."""
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    _motor_que_falla_con("HTTP 500 del proveedor: {'created': 1700000000, 'detail': 'internal'}")
    otro = _importar(camp, semilla=61)                              # un caso ajeno e intacto
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert c.get(f"{BASE}/caso/{cid}").status_code == 500
    assert c.get(f"{BASE}/panel").status_code == 500                 # el panel de TODOS los casos
    assert c.get(f"{BASE}/caso/{otro}").status_code == 200           # la página de otro caso sí abre
    assert c.get(f"{BASE}/").status_code == 200
    assert _tipos(camp, cid) == ["create_started"]                   # nunca se asentó
    from webapp.domain.reconstruction import runs
    run = runs.of_project(camp.get(cid)["recon_project_id"])[0]
    assert run["status"] == "FAILED" and "1700000000" in run["error"]
    with pytest.raises(camp.CampaignError, match="email o teléfono"):
        camp.settle(cid)


@pytest.mark.parametrize("mensaje,rompe", [
    ("HTTP 500: {'created': 1700000000}", True),
    ("The server had an error. Request ID req_0123456789abcdef0123456789abcdef", True),
    ("Contact support, ticket 123-456-7890", True),                   # guiones: parece un teléfono
    ("timed out after 600 s", False),
    ("Request ID req_a1b2c3d4e5f60718293a4b5c6d7e8f90", False),
    ("Limit 30000, Used 22345, Requested 9000.", False),
])
def test_E11b_que_mensajes_de_error_realistas_rompen_y_cuales_no(env, mensaje, rompe):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    _motor_que_falla_con(mensaje)
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    assert (c.get(f"{BASE}/caso/{cid}").status_code == 500) is rompe


def test_E11c_en_MEJORAR_el_mismo_detector_borra_el_motivo_del_fallo_y_deja_una_propiedad_huerfana_DEFECTO_H21(
        env, monkeypatch):
    """El texto de un fallo de `auto_prepare` incluye rutas del servidor (ids con racha de dígitos):
    de forma esporádica (≈ 1 de cada 20 con ids aleatorios) `record(improve_started)` lanza, el
    `procesar` responde 409 «el caso contiene un email o teléfono» y la propiedad ya creada queda sin
    caso. Se fuerza con un mensaje determinista."""
    c, camp, tmp = env
    from webapp import store
    from webapp.domain import ingest
    monkeypatch.setattr(ingest, "auto_prepare",
                        lambda pid: (_ for _ in ()).throw(RuntimeError("No se pudo abrir /data/cases/c_1234567890/plano.png")))
    cid = _cid(_subir_mejorar(c))
    r = c.post(f"{BASE}/caso/{cid}/procesar")
    assert r.status_code == 409 and "email o teléfono" in r.get_data(as_text=True)
    assert _tipos(camp, cid) == [] and store.q1("SELECT COUNT(*) n FROM properties")["n"] == 1
    r = c.post(f"{BASE}/caso/{cid}/procesar")                        # reintentar: otra propiedad huérfana
    assert r.status_code == 409 and store.q1("SELECT COUNT(*) n FROM properties")["n"] == 2


_MATAR = r'''
import os, sys
sys.path.insert(0, %(raiz)r); sys.path.insert(0, %(raiz)r + "/src"); sys.path.insert(0, %(raiz)r + "/tests")
os.environ.update(ESCALIMETRO_DATA_DIR=%(datos)r, ESCALIMETRO_DEV="1", ESCALIMETRO_PASSWORD="",
                  ESCALIMETRO_MIGRATE="0")
from webapp import campaign, store
store.init()
from test_e37_reconstruction_lab import _foto, _plano_real
original = campaign._save
def muere(m):
    os._exit(9)                       # kill -9 / corte de energía justo antes de escribir el manifiesto
campaign._save = muere
campaign.import_upload(campaign.CREATE, [("a.png", _foto(1)), ("b.png", _foto(2))],
                       ground_truth=("secreto_GT.png", _plano_real()))
'''


def test_E12_un_kill_a_mitad_de_la_carga_deja_el_plano_real_en_un_temporal_y_un_caso_sin_manifiesto(env):
    """Un corte duro (redeploy de Railway, OOM) entre el trabajo de `_import_case` y el `_save`: no
    hay caso, pero quedan (1) el proyecto E37 con su plano real, (2) la evidencia de sólo lectura y
    (3) —sólo si el corte ocurre antes de salir del `with`— el directorio temporal con el plano real
    bajo el nombre `plano_real.png` dentro de `DATA_DIR/e44/`. Ninguna ruta lo sirve y nada lo limpia."""
    import subprocess
    import sys
    c, camp, tmp = env
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    datos = str(tmp / "data")
    out = subprocess.run([sys.executable, "-c", _MATAR % {"raiz": raiz, "datos": datos}],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 9, out.stderr[-600:]
    assert camp.load()["cases"] == []
    temporales = [d for d in os.listdir(camp.root()) if d.startswith("tmp")]
    assert len(temporales) == 1
    residuo = os.listdir(os.path.join(camp.root(), temporales[0]))
    assert "plano_real.png" in residuo and "bundle.json" in residuo        # el plano real, en claro, junto al caso
    assert len(_huerfanos_e37()) == 1 and os.listdir(os.path.join(camp.root(), "cases"))
    # el índice y el rastreador de superficies no lo ven; tampoco lo limpia ningún arranque
    assert "plano_real" not in open(camp.build_index(), encoding="utf-8").read()
    from webapp import store
    store.reset_orphans()
    assert [d for d in os.listdir(camp.root()) if d.startswith("tmp")] == temporales


def test_E9_un_corte_en_MEJORAR_antes_de_registrar_improve_started_duplica_la_propiedad(env, planta_lista,
                                                                                       monkeypatch):
    c, camp, tmp = env
    from webapp import store
    cid = _cid(_subir_mejorar(c))
    real = camp.record
    estado = {"cae": True}

    def record_cae(case_id, kind, data):
        if kind == "improve_started" and estado["cae"]:
            estado["cae"] = False
            raise RuntimeError("proceso muerto")
        return real(case_id, kind, data)
    monkeypatch.setattr(camp, "record", record_cae)
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 500
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 1 and _tipos(camp, cid) == []
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 2          # la primera quedó huérfana
    assert _tipos(camp, cid) == ["improve_started", "pipeline"]


# ---- cuerpos de petición: tope efectivo por ruta --------------------------------------------------
def test_E10_el_tope_de_cuerpo_de_MEJORAR_es_el_de_E37_no_el_de_la_app_DEFECTO_H07(env):
    """`_guardas` (E37) sube `max_content_length` a 1200 MB para TODO POST del blueprint del piloto; el
    de CREAR se baja después a ~147 MB (E45.2), pero MEJORAR conserva los 1200 MB y lo lee entero en
    memoria (`f.read()`) antes de medirlo."""
    c, camp, tmp = env
    from webapp import mobile_upload, reconstruction
    app = c.application
    topes = {}
    for ruta in ("mejorar", "crear"):
        with app.test_request_context(f"{BASE}/{ruta}", method="POST",
                                      headers={"Origin": "http://localhost"}):
            app.preprocess_request()
            from flask import request
            topes[ruta] = request.max_content_length
    assert topes["mejorar"] == reconstruction.max_request_mb() * 1024 * 1024 == 1200 * 1024 * 1024
    assert topes["crear"] == mobile_upload.MAX_ENVIO_BYTES
    assert app.config["MAX_CONTENT_LENGTH"] == 160 * 1024 * 1024            # el tope «general» que no rige


def test_E10b_un_plano_de_MEJORAR_de_45_MB_se_lee_entero_y_recien_despues_se_rechaza_DEFECTO_H07(env):
    c, camp, tmp = env
    blob = b"%PDF-1.4\n" + b"0" * (45 * 1024 * 1024)
    r = _subir_mejorar(c, blob, "grande.pdf")
    assert r.status_code == 400 and "40 MB" in r.get_data(as_text=True)
    assert camp.load()["cases"] == []
    assert not os.listdir(camp.root()) or not [d for d in os.listdir(camp.root()) if d.startswith("e44-")]


# =============================================================================================
# F · doble clic, repetición y concurrencia
# =============================================================================================
def test_F1_dos_cargas_distintas_a_la_vez_conservan_ambas_H02_CERRADO(env, monkeypatch):
    """Ventana FORZADA: las dos cargas llegan juntas a la validación (barrera) y compiten por la
    sección crítica. Desde E47.5 `_import_case` lee, crea y escribe el manifiesto bajo un candado:
    ambos casos quedan en el manifiesto, con su evidencia, y sus URLs abren."""
    c, camp, tmp = env
    original = camp._validate_entry
    barrera = threading.Barrier(2, timeout=15)

    def sincronizado(*a, **k):
        barrera.wait()
        return original(*a, **k)
    monkeypatch.setattr(camp, "_validate_entry", sincronizado)
    res = {}

    def sube(k):
        try:
            res[k] = _importar(camp, semilla=k)
        except Exception as e:                                       # noqa: BLE001
            res[k] = e
    hilos = [threading.Thread(target=sube, args=(k,)) for k in (11, 12)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert all(isinstance(v, str) for v in res.values()), res
    en_manifiesto = sorted(x["case_id"] for x in camp.load()["cases"])
    assert en_manifiesto == sorted(res.values())
    for cid in en_manifiesto:
        assert camp.status(camp.get(cid)) == camp.CAPTURED
        assert os.path.isdir(os.path.join(camp.case_dir(cid), "evidence"))
        assert c.get(f"{BASE}/caso/{cid}").status_code == 200
    assert len(_huerfanos_e37()) == 2


def test_F1b_natural_dos_cargas_distintas_a_la_vez_no_pierden_casos_H02_CERRADO(env):
    """Sin barrera propia (sólo arrancan juntas), varias rondas: ninguna carga se pierde."""
    c, camp, tmp = env
    for ronda in range(8):
        res = {}
        arranque = threading.Barrier(2, timeout=15)

        def sube(k, ronda=ronda):
            arranque.wait()
            try:
                res[k] = _importar(camp, semilla=1000 + ronda * 10 + k)
            except Exception as e:                                   # noqa: BLE001
                res[k] = e
        hilos = [threading.Thread(target=sube, args=(k,)) for k in (1, 2)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        assert all(isinstance(v, str) for v in res.values()), res
    ids = {x["case_id"] for x in camp.load()["cases"]}
    assert len(ids) == 16


def test_F2_un_envio_que_falla_no_borra_la_evidencia_del_ganador_H02_CERRADO(env, monkeypatch):
    """Intercalado FORZADO: el chequeo de duplicados del 2.º envío «ya había pasado» (se anula).
    Copiar sobre la evidencia 0444 del ganador falla, pero el cleanup sólo retira lo que esa
    invocación creó: el caso del 1.º conserva su material y su estado."""
    c, camp, tmp = env
    primero = _importar(camp, semilla=5)
    antes = sorted(os.listdir(os.path.join(camp.case_dir(primero), "evidence")))
    assert camp.status(camp.get(primero)) == camp.CAPTURED
    monkeypatch.setattr(camp, "_find_duplicate", lambda *a, **k: None)
    with pytest.raises(OSError):
        _importar(camp, semilla=5)
    assert camp.status(camp.get(primero)) == camp.CAPTURED
    assert sorted(os.listdir(os.path.join(camp.case_dir(primero), "evidence"))) == antes
    assert camp.count("CREATE")["captured"] == 1 and camp.count("CREATE")["url_only"] == 0


def test_F2b_fallo_a_mitad_de_importacion_limpia_solo_lo_propio_H02_CERRADO(env, monkeypatch):
    """Una carpeta de caso creada por la invocación desaparece al fallar, sin tocar el caso previo."""
    c, camp, tmp = env
    previo = _importar(camp, semilla=76)
    fotos, gt = _material(77)

    def falla(*a, **k):
        raise RuntimeError("proveedor caído")
    monkeypatch.setattr(camp, "_prepare_create", falla)
    with pytest.raises(RuntimeError):
        camp.import_upload(camp.CREATE, fotos, ground_truth=gt)
    assert os.listdir(os.path.join(camp.root(), "cases")) == [previo]
    assert camp.status(camp.get(previo)) == camp.CAPTURED


def test_F3_natural_doble_envio_identico_deja_un_caso_y_ningun_500_H02_CERRADO(env):
    """Doble toque en SUBIR MATERIAL: el primero entra (303), el segundo ve el duplicado ya
    publicado y recibe un 400 limpio. Nunca 500, siempre un único caso con su evidencia."""
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    for ronda in range(10):
        fotos, gt = _material(2000 + ronda)
        arranque = threading.Barrier(2, timeout=15)
        codigos = []

        def go():
            cl = _cliente(c)
            data = {"fotos": [(io.BytesIO(b), n) for n, b in fotos],
                    "plano_real": (io.BytesIO(gt[1]), gt[0])}
            arranque.wait()
            codigos.append(cl.post(f"{BASE}/crear", data=data, content_type="multipart/form-data").status_code)
        hilos = [threading.Thread(target=go) for _ in range(2)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        assert sorted(codigos) == [303, 400], (ronda, codigos)
    casos = camp.load()["cases"]
    assert len({x["case_id"] for x in casos}) == len(casos) == 10
    for x in casos:
        assert camp.status(x) == camp.CAPTURED


def test_F3b_el_manifiesto_se_guarda_atomicamente(env, monkeypatch):
    """Si la escritura falla a medias, el manifiesto anterior sigue íntegro y no queda temporal."""
    c, camp, tmp = env
    _importar(camp, semilla=3)
    antes = camp.load()
    monkeypatch.setattr(camp.json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disco lleno")))
    with pytest.raises(OSError):
        camp._save({"version": "x", "cases": []})
    monkeypatch.undo()
    assert camp.load() == antes
    assert not [n for n in os.listdir(camp.root()) if n.endswith(".tmp")]


def _sincronizar_en_el_reclamo(camp, monkeypatch):
    """Fuerza la ventana de H03: las dos peticiones llegan JUNTAS al reclamo (barrera justo antes de
    pedirlo). Sin reclamo atómico las dos pasaban; con él, una sola lo obtiene."""
    original = camp._claim
    barrera = threading.Barrier(2, timeout=15)

    def sincronizado(case_id, name):
        if name != "improve_publish":                                # ése sólo lo pide el ganador
            barrera.wait()
        return original(case_id, name)
    monkeypatch.setattr(camp, "_claim", sincronizado)


def test_F4_doble_procesar_de_CREAR_lanza_una_sola_corrida_H03_CERRADO(env, monkeypatch):
    """Ventana FORZADA (E46 mostraba dos corridas y dos llamadas pagas). Desde E47.3 el reclamo
    atómico va antes de `create_initial`: una corrida, una llamada, y la segunda petición recibe 409
    sin error ni gasto."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines, runs
    llamadas = []
    adaptador = engines.get("motor_de_prueba")
    real_reconstruct = type(adaptador).reconstruct

    def cuenta(self, req):
        llamadas.append(1)
        return real_reconstruct(self, req)
    monkeypatch.setattr(type(adaptador), "reconstruct", cuenta)
    cid = _cid(_subir_crear(c, n=2))
    _sincronizar_en_el_reclamo(camp, monkeypatch)
    codigos = []

    def go():
        codigos.append(_cliente(c).post(f"{BASE}/caso/{cid}/procesar").status_code)
    hilos = [threading.Thread(target=go) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(codigos) == [303, 409]
    pid = camp.get(cid)["recon_project_id"]
    assert len(runs.of_project(pid)) == 1 and len(llamadas) <= 1
    assert _tipos(camp, cid).count("create_started") == 1
    _html(c, f"{BASE}/caso/{cid}")
    assert len(llamadas) == 1                                        # una sola llamada simulada


def test_F4b_natural_doble_procesar_de_CREAR_cuantas_corridas_se_crean(env, monkeypatch):
    """Sin barrera (sólo arrancan juntas): la ventana real es de milisegundos. El test fija lo único
    que no puede violarse (1 ó 2 corridas, nunca 0 ni más de 2); la tasa observada va en el REPORT."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import runs
    cuentas = Counter()
    for ronda in range(10):
        cid = _cid(c.post(f"{BASE}/crear", data={
            "fotos": [(io.BytesIO(b), n) for n, b in _material(3000 + ronda)[0]],
            "plano_real": (io.BytesIO(_material(3000 + ronda)[1][1]), "gt.png")},
            content_type="multipart/form-data"))
        arranque = threading.Barrier(2, timeout=15)

        def go():
            arranque.wait()
            _cliente(c).post(f"{BASE}/caso/{cid}/procesar")
        hilos = [threading.Thread(target=go) for _ in range(2)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        cuentas[len(runs.of_project(camp.get(cid)["recon_project_id"]))] += 1
    assert set(cuentas) <= {1, 2}, cuentas


def test_F5_dos_vistas_de_la_pagina_a_la_vez_registran_dos_pipeline_DEFECTO_H17(env, monkeypatch):
    """`settle()` (que ejecuta cualquier GET del caso o del panel) hace «ya está asentada?» y luego
    `record`, sin candado: con la corrida recién terminada, dos pestañas o el auto-refresco a la vez
    escriben el «singleton» `pipeline` dos veces. Ventana FORZADA con una barrera en `runs.get`."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import runs
    cid = _cid(_subir_crear(c, n=2))
    encolar = runs.enqueue
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)           # lanzada pero sin asentar
    c.post(f"{BASE}/caso/{cid}/procesar")
    rid = camp._of(cid, "create_started")[0]["data"]["run_id"]
    runs.execute(rid)                                                # la corrida termina
    original = camp._check_payload
    barrera = threading.Barrier(2, timeout=15)

    def sincronizado(*a, **k):
        # ambos ya pasaron el chequeo de singleton y aún no escribieron; B espera a que A escriba
        # para que no choquen en el número de secuencia (eso es F6)
        barrera.wait()
        if threading.current_thread().name == "B":
            time.sleep(0.4)
        return original(*a, **k)
    monkeypatch.setattr(camp, "_check_payload", sincronizado)
    errores = []

    def go():
        try:
            camp.settle(cid)
        except Exception as e:                                       # noqa: BLE001
            errores.append(e)
    hilos = [threading.Thread(target=go, name=n) for n in ("A", "B")]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert errores == [] and _tipos(camp, cid).count("pipeline") == 2


def test_F6_la_numeracion_de_eventos_colisiona_bajo_concurrencia_DEFECTO_H17(env, monkeypatch):
    """`seq = len(listdir) + 1` y luego `open(..., 'x')`: dos `record` simultáneos calculan el mismo
    número. Del MISMO tipo el segundo revienta (`FileExistsError`, sin pérdida); de DISTINTO tipo
    ambos se guardan con el mismo `seq` y el orden se decide por el nombre de archivo, no por el tiempo."""
    c, camp, tmp = env
    from webapp import store
    cid = _cid(_subir_crear(c, n=2))
    original = store.now
    suelta, dentro = threading.Event(), threading.Event()

    def lento():
        if threading.current_thread().name == "A":
            dentro.set()
            suelta.wait(10)
        return original()
    monkeypatch.setattr(store, "now", lento)
    res = {}

    def a(kind, datos):
        try:
            res["A"] = camp.record(cid, kind, datos)["seq"]
        except Exception as e:                                       # noqa: BLE001
            res["A"] = type(e).__name__

    def b(kind, datos):
        try:
            res["B"] = camp.record(cid, kind, datos)["seq"]
        except Exception as e:                                       # noqa: BLE001
            res["B"] = type(e).__name__
    # mismo tipo
    ta = threading.Thread(target=a, name="A", args=("blocked", {"status": camp.BLOCKED_CRED}))
    ta.start()
    dentro.wait(10)
    tb = threading.Thread(target=b, name="B", args=("blocked", {"status": camp.BLOCKED_MATERIAL}))
    tb.start()
    tb.join()
    suelta.set()
    ta.join()
    assert res["B"] == 1 and res["A"] == "FileExistsError"
    # distinto tipo, mismo número
    suelta.clear()
    dentro.clear()
    res.clear()
    d = os.path.join(camp.case_dir(cid), "results")
    n0 = len(os.listdir(d))
    ta = threading.Thread(target=a, name="A", args=("ux_evaluation", {
        "rating": "BUENO", "understood_immediately": True}))
    ta.start()
    dentro.wait(10)
    tb = threading.Thread(target=b, name="B", args=("blocked", {"status": camp.BLOCKED_MATERIAL}))
    tb.start()
    tb.join()
    suelta.set()
    ta.join()
    assert res["A"] == res["B"] == n0 + 1                            # el mismo seq para dos eventos
    assert len(os.listdir(d)) == n0 + 2


def test_F7_dos_procesar_de_MEJORAR_a_la_vez_crean_una_sola_propiedad_H03_CERRADO(env, planta_lista, monkeypatch):
    c, camp, tmp = env
    from webapp import store
    from webapp.domain import properties
    cid = _cid(_subir_mejorar(c))
    _sincronizar_en_el_reclamo(camp, monkeypatch)
    codigos = []

    def go():
        codigos.append(_cliente(c).post(f"{BASE}/caso/{cid}/procesar").status_code)
    hilos = [threading.Thread(target=go) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(codigos) == [303, 409]
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 1
    assert _tipos(camp, cid).count("improve_started") == 1
    assert _tipos(camp, cid).count("pipeline") == 1


def test_F4c_dos_CORREGIR_a_la_vez_crean_una_sola_corrida_hija_H03_CERRADO(env, monkeypatch):
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines, runs
    llamadas = []
    adaptador = engines.get("motor_de_prueba")
    real = type(adaptador).reconstruct
    monkeypatch.setattr(type(adaptador), "reconstruct",
                        lambda self, req: llamadas.append(1) or real(self, req))
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")                                   # settle: la madre queda asentada
    pid = camp.get(cid)["recon_project_id"]
    n0, llamadas_madre = len(runs.of_project(pid)), len(llamadas)
    _sincronizar_en_el_reclamo(camp, monkeypatch)
    codigos = []

    def go():
        codigos.append(_cliente(c).post(f"{BASE}/caso/{cid}/corregir",
                                        data={"texto": "mover la puerta"}).status_code)
    hilos = [threading.Thread(target=go) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(codigos) == [303, 400]                             # la segunda: rechazo limpio, no 500
    assert len(runs.of_project(pid)) == n0 + 1
    assert _tipos(camp, cid).count("correction_started") == 1
    _html(c, f"{BASE}/caso/{cid}")
    assert len(llamadas) == llamadas_madre + 1                       # una sola llamada hija


def test_F9_no_hay_tope_de_correcciones_ni_de_gasto_por_caso_LIMITACION(env, monkeypatch):
    """Cada «CORREGIR» de la web es una corrida hija con `confirm_paid=True` (una llamada paga). El
    código no limita cuántas por caso ni el gasto total: 8 correcciones seguidas se aceptan."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines
    adaptador = engines.get("motor_de_prueba")
    llamadas = []
    real = type(adaptador).reconstruct
    monkeypatch.setattr(type(adaptador), "reconstruct", lambda self, req: llamadas.append(1) or real(self, req))
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    for i in range(8):
        assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": f"corrección {i}"}).status_code == 303
        _html(c, f"{BASE}/caso/{cid}")
    assert len(llamadas) == 9 and len(camp._of(cid, "correction")) == 8
    fuente = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp",
                               "campaign.py"), encoding="utf-8").read()
    assert not any(t in fuente.lower() for t in ("max_corrections", "budget", "presupuesto", "max_runs"))


def test_F8_evaluar_dos_veces_en_secuencia_conserva_ambas_y_el_resumen_usa_la_ultima(env, planta_lista):
    c, camp, tmp = env
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    assert _eval_plano(c, cid, rating="EXCELENTE").status_code == 303
    assert _eval_plano(c, cid, rating="PESIMO").status_code == 303     # «doble clic» con otro valor
    assert _eval_ux(c, cid).status_code == 303 and _eval_ux(c, cid).status_code == 303
    assert [e["data"]["rating"] for e in camp._of(cid, "evaluation")] == ["EXCELENTE", "PESIMO"]
    s = camp.summary()["tracks"]["IMPROVE"]
    assert s["pilot"]["plan_evaluations"] == 1 and s["pilot"]["ux_evaluations"] == 1   # un caso, un voto
    assert s["ratings"]["PESIMO"] == 1 and s["ratings"]["EXCELENTE"] == 0       # vale la ÚLTIMA evaluación
    # los archivos de evento anteriores no se tocaron
    d = os.path.join(camp.case_dir(cid), "results")
    assert sorted(os.listdir(d)) == [f"{i:03d}_{k}.json" for i, k in enumerate(
        ["improve_started", "pipeline", "evaluation", "evaluation", "ux_evaluation", "ux_evaluation"], 1)]
