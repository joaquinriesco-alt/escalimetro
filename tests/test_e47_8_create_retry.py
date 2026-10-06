"""E47.8 — cierra E46-H05 (reintento de CREAR) y E46-H20 (excluir libera la propiedad).

Material sintético; el motor es un fixture que falla las veces que se le pide. Sin red ni gasto.
"""
from __future__ import annotations

import threading

import pytest

from test_e37_reconstruction_lab import _foto, _plano_real
from test_e45_web_pilot import BASE, _cid, _html, _subir_crear, env  # noqa: F401


def _tipos(camp, cid):
    return [e["kind"] for e in camp.events(cid)]


@pytest.fixture()
def flaky(env):
    """Motor de prueba que lanza EngineError mientras `fallos[0] > 0` y después reconstruye."""
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture
    fallos = [0]

    class Intermitente(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

        def reconstruct(self, req):
            if fallos[0] > 0:
                fallos[0] -= 1
                raise engines.EngineError("PROVIDER_TIMEOUT", "timeout transitorio")
            return super().reconstruct(req)
    engines.register(Intermitente())
    return fallos


def _procesar(c, cid):
    r = c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")                      # la vista asienta la corrida (settle)
    return r.status_code


def test_FAILED_retry_FAILED_retry_DONE_cuenta_una_sola_vez(env, flaky):
    c, camp, tmp = env
    flaky[0] = 2
    cid = _cid(_subir_crear(c, n=2))
    assert _procesar(c, cid) == 303
    n = camp.count("CREATE")
    assert (n["captured"], n["executed"], n["completed"]) == (1, 0, 0)       # FAILED no consume el N
    assert "VOLVER A INTENTAR" in _html(c, f"{BASE}/caso/{cid}")
    assert _procesar(c, cid) == 303                                           # 2.º intento: FAILED
    n = camp.count("CREATE")
    assert (n["captured"], n["executed"]) == (1, 0)
    assert _procesar(c, cid) == 303                                           # 3.º: DONE
    pip = camp._of(cid, "pipeline")
    assert [(p["data"]["attempt"], p["data"]["status"]) for p in pip] == \
        [(1, "FAILED"), (2, "FAILED"), (3, "DONE")]
    assert len({p["data"]["run_id"] for p in pip}) == 3                       # identidad propia
    n = camp.count("CREATE")
    assert (n["captured"], n["executed"], n["completed"]) == (1, 1, 0)        # cuenta UNA vez
    assert camp.status(camp.get(cid)) == camp.EXECUTED
    # después de un DONE no hay otra corrida inicial
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409
    assert len(camp._of(cid, "create_started")) == 3
    # y las correcciones siguen su flujo, aparte de los intentos iniciales
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "el living es más grande"}
                  ).status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    assert len(camp._of(cid, "correction")) == 1 and len(camp._of(cid, "pipeline")) == 3
    s = camp.summary()["tracks"]["CREATE"]
    assert s["pipeline_success"] == {"reached_output": 1, "executed": 1}


def test_un_caso_con_solo_FAILED_no_se_cierra_ni_se_evalua(env, flaky):
    c, camp, tmp = env
    flaky[0] = 1
    cid = _cid(_subir_crear(c, n=2))
    _procesar(c, cid)
    with pytest.raises(camp.CampaignError, match="ningún intento terminó bien"):
        camp.close_blind(cid)
    assert camp._of(cid, "closure") == []
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code >= 400


def test_no_hay_reintento_con_una_corrida_pendiente(env, monkeypatch):
    c, camp, tmp = env
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409
    assert _tipos(camp, cid) == ["create_started"]


def test_reintento_concurrente_crea_como_maximo_una_corrida_nueva(env, monkeypatch):
    c, camp, tmp = env
    from webapp import store
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)
    cid = _cid(_subir_crear(c, n=2))
    camp.start_create(cid, "motor_de_prueba", confirm_paid=True)
    store.reset_orphans()                                       # intento 1 → FAILED
    camp.settle(cid)
    assert [p["data"]["status"] for p in camp._of(cid, "pipeline")] == ["FAILED"]
    creadas = []
    real = runs.create_initial

    def espia(*a, **k):
        rid = real(*a, **k)
        creadas.append(rid)
        return rid
    monkeypatch.setattr(runs, "create_initial", espia)
    barrera = threading.Barrier(8)
    res = []

    def disparar():
        barrera.wait()
        try:
            res.append(camp.start_create(cid, "motor_de_prueba", confirm_paid=True)["status"])
        except camp.CampaignError as e:
            res.append(str(e))
    hilos = [threading.Thread(target=disparar) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert res.count("QUEUED") == 1 and len(creadas) == 1
    assert _tipos(camp, cid).count("create_started") == 2


def test_settle_es_idempotente_con_varios_intentos(env, flaky):
    c, camp, tmp = env
    flaky[0] = 1
    cid = _cid(_subir_crear(c, n=2))
    _procesar(c, cid)
    _procesar(c, cid)
    antes = [(e["seq"], e["kind"]) for e in camp.events(cid)]
    cuentas = camp.count("CREATE")
    for _ in range(3):
        camp.settle(cid)
    assert [(e["seq"], e["kind"]) for e in camp.events(cid)] == antes
    assert camp.count("CREATE") == cuentas
    with pytest.raises(camp.CampaignError):                      # un asiento manual duplicado se rechaza
        camp.record(cid, "pipeline", dict(camp._of(cid, "pipeline")[0]["data"]))


def test_BLOCKED_CRED_no_es_un_intento_FAILED(env, monkeypatch):
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines
    monkeypatch.setattr(engines.get("motor_de_prueba").__class__, "availability",
                        lambda self: engines.Availability(engines.UNAVAILABLE, engines.MISSING_CREDENTIAL,
                                                          "sin clave"), raising=False)
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert camp.status(camp.get(cid)) == camp.BLOCKED_CRED
    assert camp._of(cid, "pipeline") == [] and camp._of(cid, "create_started") == []
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303   # recuperable como antes


def test_excluir_y_recargar_da_identidad_separada_y_respeta_a_los_activos(env, flaky):
    c, camp, tmp = env
    flaky[0] = 1
    viejo = _cid(_subir_crear(c, n=2))
    _procesar(c, viejo)
    eventos_viejo = camp.events(viejo)
    camp.exclude(viejo, "falló")
    nuevo = _cid(_subir_crear(c, n=2))
    assert nuevo != viejo
    assert camp.case_dir(nuevo) != camp.case_dir(viejo)
    assert camp.get(nuevo)["recon_project_id"] != camp.get(viejo)["recon_project_id"]
    assert camp.events(nuevo) == []                              # no hereda resultados
    assert camp.events(viejo) == eventos_viejo                   # el excluido, intacto
    assert _procesar(c, nuevo) == 303 and camp.status(camp.get(nuevo)) == camp.EXECUTED
    assert camp.status(camp.get(viejo)) == camp.EXCLUDED
    assert camp.get(viejo)["excluded_reason"] == "falló"
    # otra recarga: el activo bloquea y, si se excluye también, el id vuelve a ser nuevo
    assert _subir_crear(c, n=2).status_code == 400
    camp.exclude(nuevo, "otra vez")
    tercero = _cid(_subir_crear(c, n=2))
    assert len({viejo, nuevo, tercero}) == 3


# --- E47.9: la ventana «terminó pero todavía no se asentó» -----------------------------------

def _espiar_create_initial(monkeypatch):
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)
    creadas = []
    real = runs.create_initial

    def espia(*a, **k):
        rid = real(*a, **k)
        creadas.append(rid)
        return rid
    monkeypatch.setattr(runs, "create_initial", espia)
    return runs, creadas


def test_DONE_no_asentado_rechaza_el_segundo_POST_sin_nueva_corrida(env, flaky, monkeypatch):
    c, camp, tmp = env
    runs, creadas = _espiar_create_initial(monkeypatch)
    cid = _cid(_subir_crear(c, n=2))
    camp.start_create(cid, "motor_de_prueba", confirm_paid=True)
    assert len(creadas) == 1
    assert runs.execute(creadas[0])["status"] == runs.DONE        # terminó, sin `pipeline` todavía
    assert camp._of(cid, "pipeline") == []
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409
    assert len(creadas) == 1                                      # 0 llamadas nuevas a create_initial
    assert _tipos(camp, cid).count("create_started") == 1
    assert [p["data"]["status"] for p in camp._of(cid, "pipeline")] == ["DONE"]


def test_FAILED_no_asentado_permite_exactamente_un_reintento(env, flaky, monkeypatch):
    c, camp, tmp = env
    runs, creadas = _espiar_create_initial(monkeypatch)
    cid = _cid(_subir_crear(c, n=2))
    flaky[0] = 1
    camp.start_create(cid, "motor_de_prueba", confirm_paid=True)
    assert runs.execute(creadas[0])["status"] == runs.FAILED     # terminó, sin `pipeline` todavía
    assert camp._of(cid, "pipeline") == []
    assert camp.start_create(cid, "motor_de_prueba", confirm_paid=True)["status"] == "QUEUED"
    assert len(creadas) == 2                                      # exactamente un reintento
    with pytest.raises(camp.CampaignError):                       # el segundo queda pendiente
        camp.start_create(cid, "motor_de_prueba", confirm_paid=True)
    assert len(creadas) == 2
    pip = camp._of(cid, "pipeline")
    assert [(p["data"]["attempt"], p["data"]["status"]) for p in pip] == [(1, "FAILED")]
    assert _tipos(camp, cid).count("create_started") == 2
