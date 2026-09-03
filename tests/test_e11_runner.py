"""E11 — tests del wrapper de Railway.

Sólo lo que el wrapper introduce (§23): que no filtra secretos, que genera el HTML, que el HTML es
autocontenido, que /health no expone entorno, que el GeometryGuard sigue en pie y que el renderer del
informe tolera un fallo de proveedor sin derribar el servidor.

No se testea de nuevo la lógica de E09: ya está cubierta por `test_e09.py`."""
import json
import os
import re
import threading
import urllib.request

import pytest

from escalimetro.ai import railway_e09_runner as R

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
FAKE = "sk-" + "ant-" + "q" * 30          # forma de credencial, construida en runtime


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    """Genera el HTML una vez, con el experimento YA corrido (no se vuelve a ejecutar E09)."""
    env = R.env_report()
    data = R.load_outputs(CASE)
    run = {"ok": True, "return_code": 0, "error": None, "seconds": 1.0}
    return R.build_html(CASE, env, run, data)


# ---------------------------------------------------------------------------------------------------
# 1 — el runner no imprime secretos
# ---------------------------------------------------------------------------------------------------
def test_env_report_solo_reporta_presencia(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    e = R.env_report()
    assert e["keys"]["OPENAI_API_KEY"] == "PRESENT"
    assert e["keys"]["ANTHROPIC_API_KEY"] == "MISSING"
    assert FAKE not in json.dumps(e)          # ni el valor ni parte de él


def test_el_log_del_runner_no_filtra_la_clave(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE)
    e = R.env_report()
    for k, v in e["keys"].items():
        R.log(f"{k}={v}")
    out = capsys.readouterr().out
    assert "ANTHROPIC_API_KEY=PRESENT" in out
    assert FAKE not in out
    assert FAKE[:12] not in out               # tampoco un prefijo


def test_el_html_no_contiene_la_clave(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE)
    h = R.build_html(CASE, R.env_report(), {"ok": True, "return_code": 0, "error": None, "seconds": 1.0},
                     R.load_outputs(CASE))
    assert FAKE not in h and FAKE[:14] not in h
    assert "PRESENT" in h


# ---------------------------------------------------------------------------------------------------
# 2 y 3 — el informe se genera y es autocontenido
# ---------------------------------------------------------------------------------------------------
def test_el_html_se_genera(report):
    assert report.startswith("<!doctype html>")
    assert report.rstrip().endswith("</html>")
    assert len(report) > 100_000              # lleva imágenes embebidas


def test_el_html_es_autocontenido(report):
    """Ni una sola referencia a un archivo local: todo va como data URI."""
    assert "data:image/png;base64," in report
    srcs = re.findall(r'src="([^"]{0,40})', report)
    assert srcs and all(s.startswith("data:") for s in srcs), [s for s in srcs if not s.startswith("data:")]
    for bad in ('href="img/', 'src="img/', "file://", "../"):
        assert bad not in report, bad


def test_el_html_declara_los_bloques_obligatorios(report):
    for section in ("Executive verdict", "API status", "Revisiones por proveedor", "la recepción",
                    "Legibilidad de la estrategia", "Acuerdos y desacuerdos", "Ablación de proveedores",
                    "Valor por proveedor", "Costo y latencia", "Fiabilidad de prompts",
                    "Geometry guard", "PresentationSpec", "Standard 03", "Gates"):
        assert section in report, section


# ---------------------------------------------------------------------------------------------------
# 4 — /health y /status no exponen entorno
# ---------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def server():
    from http.server import ThreadingHTTPServer
    R._State.report_html = "<html><body>informe de prueba</body></html>"
    R._State.status = {"api_execution": "BLOCKED", "gate_api": "BLOCKED",
                       "gate_multi_model_value": "INSUFFICIENT_EVIDENCE", "report_ready": True}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), R.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read().decode()


def test_health_devuelve_ok_y_nada_mas(server):
    code, body = _get(server + "/health")
    assert code == 200 and json.loads(body) == {"status": "ok"}


def test_status_no_expone_entorno(server, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE)
    code, body = _get(server + "/status")
    d = json.loads(body)
    assert set(d) == {"api_execution", "gate_api", "gate_multi_model_value", "report_ready"}
    assert FAKE not in body and "KEY" not in body.upper()


def test_no_hay_rutas_que_expongan_filesystem_ni_env(server):
    import urllib.error
    for path in ("/env", "/config", "/logs", "/../pyproject.toml", "/cases"):
        try:
            code, _ = _get(server + path)
        except urllib.error.HTTPError as e:
            code = e.code
        assert code == 404, path


def test_la_raiz_sirve_el_informe(server):
    code, body = _get(server + "/")
    assert code == 200 and "informe de prueba" in body


# ---------------------------------------------------------------------------------------------------
# 5 — el GeometryGuard sigue en pie
# ---------------------------------------------------------------------------------------------------
def test_el_wrapper_conserva_los_hashes_esperados():
    assert R.EXPECTED_HASH_PREFIX == {"A": "df6b86058ebb", "B": "5c5c276923dd", "C": "e12cc722485b"}
    g = R.load_outputs(CASE).get("geometry_hash_check")
    if not g:
        pytest.skip("requiere una corrida E09")
    for a, pre in R.EXPECTED_HASH_PREFIX.items():
        assert g["geometry_hash_before"][a].startswith(pre)
        assert g["geometry_hash_before"][a] == g["geometry_hash_after"][a]


def test_el_wrapper_no_reimplementa_e09():
    """Debe importar el experimento, no copiarlo."""
    src = open(os.path.join(ROOT, "src", "escalimetro", "ai", "railway_e09_runner.py"),
               encoding="utf-8").read()
    assert "from . import e09" in src and "e09.main(" in src
    for copied in ("def agreement_matrix", "def reception_case", "def ablation", "AIOrchestrator("):
        assert copied not in src, copied


# ---------------------------------------------------------------------------------------------------
# 6 — un fallo del experimento no derriba el servidor
# ---------------------------------------------------------------------------------------------------
def test_el_informe_tolera_un_experimento_fallido():
    run = {"ok": False, "return_code": None, "error": "ProviderError: timeout", "seconds": 3.2}
    h = R.build_html(CASE, R.env_report(), run, R.load_outputs(CASE))
    assert "EL EXPERIMENTO NO TERMINÓ" in h and "ProviderError: timeout" in h
    assert h.rstrip().endswith("</html>")           # el informe se completa igual


def test_el_informe_tolera_datos_ausentes():
    """Sin ningún JSON de salida el HTML se arma igual, con huecos declarados."""
    h = R.build_html(CASE, R.env_report(), {"ok": True, "return_code": 0, "error": None, "seconds": 0.1}, {})
    assert h.rstrip().endswith("</html>") and "NO PRODUCIDA" in h


def test_run_experiment_no_propaga_excepciones(monkeypatch):
    from escalimetro.ai import e09
    monkeypatch.setattr(e09, "main", lambda argv: (_ for _ in ()).throw(RuntimeError("boom")))
    r = R.run_experiment(CASE)
    assert r["ok"] is False and "boom" in r["error"]
