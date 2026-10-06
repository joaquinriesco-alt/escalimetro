"""E47.11 — cierra E46-H21: un error técnico de proveedor no rompe settle(), el caso ni el panel.

Frontera: el texto HUMANO sigue protegido por `_no_pii`; el texto TÉCNICO se sanea de forma
determinista antes de persistirse. Los valores sensibles de estos tests se construyen en runtime
con fragmentos inocuos: ningún literal del repo tiene forma de credencial. Sin red ni gasto.
"""
from __future__ import annotations

import json
import os

import pytest

from test_e45_web_pilot import (BASE, _cid, _eval_plano, _html, _subir_crear,  # noqa: F401
                                _subir_mejorar, env)


def _importar(camp, semilla):
    """Caso CREAR con material único por semilla (mismos bytes = duplicado)."""
    from test_e46_adv_resilience import _material
    fotos, gt = _material(semilla)
    return camp.import_upload(camp.CREATE, fotos, ground_truth=gt)


def _tipos(camp, cid):
    return [e["kind"] for e in camp.events(cid)]


def _largo_sintetico() -> str:
    """Identificador largo alfanumérico armado al vuelo (no es una credencial real)."""
    return "".join(["Qz", "7k", "Lm", "9x"] * 8)


def _hostiles():
    """(nombre, mensaje, valor que NO debe persistir)."""
    num = "".join(str(d) for d in (4, 8, 1, 5, 9, 2, 6, 3, 7, 0, 1, 4))
    tel = "+" + "56" + " 9 " + "8765" + "-" + "4321"
    mail = "persona" + "@" + "ejemplo" + "." + "test"
    ruta = "/" + "var/tmp/" + "abc" + "/" + "salida.json"
    ident = _largo_sintetico()
    return [
        ("digitos", f"HTTP 500 detalle {num} fin", num),
        ("telefono", f"contacto {tel} soporte", tel),
        ("email", f"avisar a {mail} por favor", mail),
        ("ruta", f"no se pudo abrir {ruta}", ruta),
        ("identificador", f"request {ident} rechazado", ident),
        ("token_runtime", "auth " + "Bear" + "er " + ident + " expirado", ident),
        ("largo", "x " + "palabra " * 400 + "FIN_UNICO", "FIN_UNICO"),
    ]


def _motor_que_falla_con(mensaje):
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture

    class Roto(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

        def reconstruct(self, req):
            raise engines.EngineError("PROVIDER_500", mensaje)
    engines.register(Roto())


@pytest.mark.parametrize("nombre,mensaje,valor", _hostiles(), ids=[h[0] for h in _hostiles()])
def test_sanitize_no_conserva_el_valor_hostil(nombre, mensaje, valor):
    from webapp import campaign
    out = campaign.sanitize_technical_error(mensaje, "PROVIDER_500")
    assert valor not in out
    assert len(out) <= campaign.ERROR_MAX + 40 and out.startswith("PROVIDER_500")
    campaign._no_pii(out)                                  # lo saneado pasa el detector humano


def test_sanitize_conserva_la_descripcion_util_y_es_determinista():
    from webapp import campaign
    a = campaign.sanitize_technical_error("timed out after 600 s", "PROVIDER_TIMEOUT")
    assert a == "PROVIDER_TIMEOUT: timed out after 600 s"
    assert campaign.sanitize_technical_error("Limit 30000, Used 22345") == "Limit 30000, Used 22345"
    assert campaign.sanitize_technical_error("") == campaign.ERROR_GENERIC
    assert campaign.sanitize_technical_error(None, "X") == f"X: {campaign.ERROR_GENERIC}"
    h = "ñandú falló " + "9" * 30
    assert campaign.sanitize_technical_error(h) == campaign.sanitize_technical_error(h)


@pytest.mark.parametrize("nombre,mensaje,valor", _hostiles(), ids=[h[0] for h in _hostiles()])
def test_CREAR_FAILED_hostil_queda_asentado_reintentable_y_sin_el_valor(env, nombre, mensaje, valor):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    _motor_que_falla_con(mensaje)
    otro = _importar(camp, semilla=71)                     # un caso ajeno e intacto
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert c.get(f"{BASE}/caso/{cid}").status_code == 200
    assert c.get(f"{BASE}/panel").status_code == 200
    assert c.get(f"{BASE}/caso/{otro}").status_code == 200
    assert _tipos(camp, cid) == ["create_started", "pipeline"]
    pip = camp._of(cid, "pipeline")[0]["data"]
    assert pip["status"] == "FAILED" and pip["error"]            # queda un motivo útil, no vacío
    n = camp.count("CREATE")
    assert (n["executed"], n["completed"]) == (0, 0)
    assert camp.status(camp.get(cid)) == camp.CAPTURED     # reintentable
    assert "VOLVER A INTENTAR" in _html(c, f"{BASE}/caso/{cid}")
    # ningún archivo del registro del caso conserva el valor hostil
    base = os.path.join(camp.root(), "cases", cid)
    for d, _s, fs in os.walk(base):
        for f in fs:
            if f.endswith(".json"):
                assert valor not in open(os.path.join(d, f), encoding="utf-8").read(), f
    # settle idempotente
    camp.settle(cid)
    camp.settle(cid)
    assert _tipos(camp, cid) == ["create_started", "pipeline"]


def test_reintento_legitimo_tras_FAILED_hostil_funciona(env):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    _motor_que_falla_con("HTTP 500 detalle 4815926370 fin")
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture

    class Sano(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"
    engines.register(Sano())
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    st = [p["data"]["status"] for p in camp._of(cid, "pipeline")]
    assert st == ["FAILED", "DONE"]
    n = camp.count("CREATE")
    assert (n["executed"], n["completed"]) == (1, 0)


def test_un_caso_hostil_no_derriba_el_panel_multicaso(env):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    _motor_que_falla_con("detalle 4815926370 y soporte " + "persona" + "@" + "ejemplo.test")
    ids = [_importar(camp, semilla=80 + i) for i in range(3)]
    for cid in ids[:2]:
        assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert c.get(f"{BASE}/panel").status_code == 200
    for cid in ids:
        assert c.get(f"{BASE}/caso/{cid}").status_code == 200


def test_MEJORAR_con_excepcion_tecnica_hostil_no_da_409_ni_deja_huerfana(env, monkeypatch):
    c, camp, tmp = env
    from webapp import store
    from webapp.domain import ingest
    ident = _largo_sintetico()
    monkeypatch.setattr(ingest, "auto_prepare", lambda pid: (_ for _ in ()).throw(
        RuntimeError(f"falló {ident} en /data/cases/c_4815926370/plano.png contacto "
                     + "persona" + "@" + "ejemplo.test")))
    cid = _cid(_subir_mejorar(c))
    r = c.post(f"{BASE}/caso/{cid}/procesar")
    assert r.status_code == 303
    assert _tipos(camp, cid) == ["improve_started"]
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 1      # la propiedad tiene caso
    err = camp.events(cid)[0]["data"]["error"]
    assert err and err.startswith("RuntimeError")
    for v in (ident, "4815926370", "persona@"):
        assert v not in err
    assert c.get(f"{BASE}/caso/{cid}").status_code == 200
    assert c.get(f"{BASE}/panel").status_code == 200


def test_el_texto_humano_con_email_o_telefono_sigue_rechazado(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    from webapp import campaign
    mail = "persona" + "@" + "ejemplo" + ".test"
    with pytest.raises(campaign.CampaignError, match="email o teléfono"):
        campaign._check_payload("CREATE", "evaluation", {"comment": f"escríbeme a {mail}"})
    with pytest.raises(campaign.CampaignError, match="email o teléfono"):
        campaign._check_payload("CREATE", "correction", {"prompt": "llamar al +56 9 8765 4321"})
    # el campo `error` de un payload NO técnico (p. ej. escrito a mano) sigue pasando por el detector
    with pytest.raises(campaign.CampaignError, match="email o teléfono"):
        campaign._check_payload("CREATE", "evaluation", {"error": f"ver {mail}"})
