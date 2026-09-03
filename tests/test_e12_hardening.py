"""E12 — tests del endurecimiento del runtime.

Cubren exactamente la clase de fallo que tumbó la primera corrida real en Railway:

    SVG → rasterizador → ndarray → cv2.imwrite

y la consecuencia peor que el fallo en sí: que un error tardío de presentación borrara u ocultara la
evidencia de proveedores obtenida antes."""
import json
import os
import shutil

import cv2
import numpy as np
import pytest

from escalimetro.ai.manifest import (BLOCKED, FAILED, NOT_STARTED, OK, RunManifest, SKIPPED,
                                     atomic_write_json)
from escalimetro.ai.svg_rasterizer import (PresentationRasterizationError, available_backends,
                                           imwrite_guarded, rasterize_and_write,
                                           rasterize_svg_to_bgr, validate_bgr)

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
E09 = os.path.join(CASE, "ai", "E09")

SIMPLE = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" ' \
         'height="100" fill="#eee"/></svg>'
RICH = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240" '
        'font-family="Helvetica,Arial,sans-serif">'
        '<rect width="400" height="240" fill="#ffffff"/>'
        '<rect x="10" y="10" width="180" height="60" rx="6" fill="#dfe7f5" stroke="#2a78d6"/>'
        '<line x1="10" y1="90" x2="390" y2="90" stroke="#69727e" stroke-width="2"/>'
        '<path d="M20,120 L120,200 L220,120 Z" fill="none" stroke="#eb6834" stroke-width="3"/>'
        '<text x="20" y="46" font-size="18" fill="#141a23">ESCALÍMETRO</text>'
        '<svg x="240" y="110" width="140" height="110" viewBox="0 0 140 110">'
        '<rect width="140" height="110" fill="#dfeee2"/></svg>'
        '</svg>')


# ---------------------------------------------------------------------------------------------------
# rasterización (§18)
# ---------------------------------------------------------------------------------------------------
def test_hay_al_menos_un_backend_disponible():
    b = available_backends()
    assert b, "sin backend de rasterización la lámina 03 no se puede producir"
    assert b[0] == "resvg", f"resvg debe ser el primario (rueda autocontenida); orden actual: {b}"


def test_1_svg_simple_produce_ndarray_no_vacio():
    arr = rasterize_svg_to_bgr(SIMPLE, 400)
    assert isinstance(arr, np.ndarray) and arr.size > 0
    assert arr.ndim == 3 and arr.shape[2] == 3
    assert arr.shape[1] == 400


def test_2_svg_con_text_rect_line_path_y_svg_anidado():
    arr = rasterize_svg_to_bgr(RICH, 800)
    assert arr.shape[1] == 800
    assert arr.shape[0] == pytest.approx(480, abs=2)      # 400×240 escalado ×2
    assert len(np.unique(arr.reshape(-1, 3), axis=0)) > 5  # dibujó algo, no un lienzo plano


@pytest.mark.parametrize("backend", available_backends())
def test_2b_todos_los_backends_disponibles_rasterizan_igual_de_bien(backend):
    """El respaldo debe servir de verdad, no sólo existir."""
    arr = rasterize_svg_to_bgr(RICH, 400, backends=(backend,))
    assert arr.shape[:2] == (240, 400)


@pytest.mark.parametrize("width", [0, -100, 3, 10 ** 6, 1.5, "800", True])
def test_3_target_width_invalido_levanta_el_error_propio(width):
    with pytest.raises(PresentationRasterizationError):
        rasterize_svg_to_bgr(SIMPLE, width)


@pytest.mark.parametrize("svg", ["", "   ", None])
def test_4_svg_vacio_levanta_el_error_propio(svg):
    with pytest.raises(PresentationRasterizationError) as e:
        rasterize_svg_to_bgr(svg, 400)
    assert "vacío" in str(e.value)


def test_5_svg_invalido_levanta_el_error_propio():
    with pytest.raises(PresentationRasterizationError):
        rasterize_svg_to_bgr("esto no es un svg", 400)
    with pytest.raises(PresentationRasterizationError) as e:
        rasterize_svg_to_bgr("<svg><rect", 400)          # markup roto
    assert isinstance(e.value.to_dict(), dict)


def test_6_camino_completo_svg_a_png_en_disco(tmp_path):
    p = str(tmp_path / "board.png")
    assert rasterize_and_write(RICH, 600, p) == p
    assert os.path.exists(p) and os.path.getsize(p) > 0
    img = cv2.imread(p)
    assert img is not None and img.size > 0 and img.shape[1] == 600


def test_el_error_no_filtra_el_svg_completo():
    """El diagnóstico lleva longitudes y nombres, nunca el contenido."""
    e = PresentationRasterizationError("x", svg_length=len(RICH), target_width=800, backend="resvg")
    txt = str(e) + json.dumps(e.to_dict())
    assert "ESCALÍMETRO" not in txt and "<rect" not in txt
    assert str(len(RICH)) in txt


def test_la_lamina_real_del_proyecto_rasteriza():
    """El SVG del Presentation Standard 02 es el mismo renderer que produce el 03."""
    svg = os.path.join(CASE, "ai", "E08", "ESCALIMETRO_PRESENTATION_STANDARD_02.svg")
    if not os.path.exists(svg):
        pytest.skip("requiere la corrida E08")
    arr = rasterize_svg_to_bgr(open(svg, encoding="utf-8").read(), 2400)
    assert arr.shape[:2] == (1400, 2400)


# ---------------------------------------------------------------------------------------------------
# guard de cv2.imwrite (§9)
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, "no soy un array", np.array([]),
                                 np.zeros((0, 10, 3), np.uint8), np.zeros((10, 0, 3), np.uint8),
                                 np.zeros((2, 2, 2, 3), np.uint8), np.zeros((10, 10, 5), np.uint8)])
def test_validate_bgr_rechaza_todo_lo_que_reventaria_a_opencv(bad):
    with pytest.raises(PresentationRasterizationError):
        validate_bgr(bad)


def test_imwrite_guarded_nunca_llama_a_opencv_con_none(tmp_path):
    """Ésta es la regresión exacta de Railway: cv2.imwrite(path, None)."""
    with pytest.raises(PresentationRasterizationError) as e:
        imwrite_guarded(str(tmp_path / "x.png"), None, what="lámina")
    assert "None" in str(e.value)
    assert not os.path.exists(str(tmp_path / "x.png"))


def test_imwrite_guarded_detecta_el_false_de_opencv(tmp_path):
    """cv2.imwrite devuelve False sin lanzar cuando la extensión no se puede codificar."""
    img = np.zeros((10, 10, 3), np.uint8)
    with pytest.raises(PresentationRasterizationError) as e:
        imwrite_guarded(str(tmp_path / "x.formato-inexistente"), img)
    assert "imwrite" in str(e.value) or "no quedó escrito" in str(e.value)


def test_imwrite_guarded_crea_el_directorio(tmp_path):
    p = str(tmp_path / "a" / "b" / "c.png")
    imwrite_guarded(p, np.full((8, 8, 3), 255, np.uint8))
    assert os.path.exists(p)


# ---------------------------------------------------------------------------------------------------
# manifiesto y checkpoints (§19)
# ---------------------------------------------------------------------------------------------------
def test_el_manifiesto_se_crea_al_comienzo(tmp_path):
    m = RunManifest(path=str(tmp_path / "run_manifest.json"), case="c")
    m.save()
    d = RunManifest.load(m.path)
    assert d["run_id"] == m.run_id and d["final_status"] == "RUNNING"
    assert all(v == NOT_STARTED for v in d["anthropic"].values())


def test_el_manifiesto_progresa_por_etapa(tmp_path):
    m = RunManifest(path=str(tmp_path / "run_manifest.json"))
    m.set_stage("providers")
    m.set_provider("anthropic", "A", OK)
    m.set_provider("openai_vision", "A", OK)          # se traduce a openai_visual
    m.set_status("aggregator", OK)
    d = RunManifest.load(m.path)
    assert d["stage"] == "providers" and d["anthropic"]["A"] == OK
    assert d["openai_visual"]["A"] == OK and d["aggregator_status"] == OK


def test_la_escritura_es_atomica_y_valida_tras_un_fallo(tmp_path):
    """Un JSON a medio escribir es peor que ninguno: se escribe en temp y se renombra."""
    p = str(tmp_path / "run_manifest.json")
    m = RunManifest(path=p)
    m.set_provider("anthropic", "A", OK)
    m.add_error("presentation_render", {"error": "PresentationRasterizationError"})
    assert json.load(open(p, encoding="utf-8"))["anthropic"]["A"] == OK   # parsea, no está corrupto
    assert not [f for f in os.listdir(tmp_path) if f.startswith(".manifest-")]  # sin temporales sueltos


def test_provider_ok_sigue_ok_aunque_falle_la_presentacion(tmp_path):
    """El corazón de E12: un fallo tardío no puede degradar la evidencia previa."""
    m = RunManifest(path=str(tmp_path / "run_manifest.json"))
    for a in ("A", "B", "C"):
        m.set_provider("anthropic", a, OK)
        m.set_provider("openai_vision", a, OK)
    m.set_status("presentation_render", FAILED)
    m.finish(FAILED)
    d = RunManifest.load(m.path)
    assert all(d["anthropic"][a] == OK for a in ("A", "B", "C"))
    assert all(d["openai_visual"][a] == OK for a in ("A", "B", "C"))
    assert d["presentation_render_status"] == FAILED
    assert m.api_execution == OK and m.providers_ok is True


def test_api_execution_distingue_bloqueado_parcial_y_ok(tmp_path):
    m = RunManifest(path=str(tmp_path / "m.json"))
    assert m.api_execution == BLOCKED
    m.set_provider("anthropic", "A", OK)
    assert m.api_execution == "PARTIAL"
    for a in ("A", "B", "C"):
        m.set_provider("anthropic", a, OK)
        m.set_provider("openai_vision", a, OK)
    assert m.api_execution == OK


def test_el_manifiesto_no_contiene_secretos(tmp_path):
    m = RunManifest(path=str(tmp_path / "m.json"))
    m.api_keys_status = {"OPENAI_API_KEY": "PRESENT", "ANTHROPIC_API_KEY": "PRESENT"}
    m.save()
    blob = open(m.path, encoding="utf-8").read()
    assert "PRESENT" in blob
    for shape in ("sk-", "Bearer ", "ghp_"):
        assert shape not in blob


def test_una_excepcion_desconocida_deja_failed_sin_json_corrupto(tmp_path):
    m = RunManifest(path=str(tmp_path / "m.json"))
    try:
        raise ValueError("boom")
    except Exception as e:
        m.add_error("presentation_render", {"error": type(e).__name__, "reason": str(e)})
        m.finish(FAILED)
    d = RunManifest.load(m.path)
    assert d["final_status"] == FAILED and d["errors"][0]["error"] == "ValueError"
    assert d["finished_at"]


def test_la_corrida_real_deja_manifiesto_coherente():
    p = os.path.join(E09, "run_manifest.json")
    if not os.path.exists(p):
        pytest.skip("requiere una corrida E09")
    d = json.load(open(p, encoding="utf-8"))
    assert d["geometry_guard_status"] == OK
    assert d["stage"] == "done" and d["finished_at"]
    assert d["presentation_render_status"] in (OK, FAILED, SKIPPED)


def test_la_corrida_deja_snapshot_historico():
    runs = os.path.join(CASE, "ai", "runs")
    if not os.path.isdir(runs):
        pytest.skip("requiere una corrida E09")
    ids = [d for d in os.listdir(runs) if os.path.isdir(os.path.join(runs, d))]
    assert ids, "sin snapshot, la segunda corrida destruiría la evidencia de la primera"
    assert os.path.exists(os.path.join(runs, ids[0], "run_manifest.json"))


# ---------------------------------------------------------------------------------------------------
# informe parcial y fallback SVG (§20)
# ---------------------------------------------------------------------------------------------------
def _html(tmp_case):
    from escalimetro.ai import railway_e09_runner as R
    return R.build_html(tmp_case, R.env_report(),
                        {"ok": True, "return_code": 0, "error": None, "seconds": 1.0},
                        R.load_outputs(tmp_case))


@pytest.fixture
def case_copy(tmp_path):
    """Copia liviana del caso: sólo los JSON y el SVG que el informe necesita."""
    dst = tmp_path / "case"
    (dst / "ai" / "E09").mkdir(parents=True)
    for f in os.listdir(E09):
        if f.endswith(".json"):
            shutil.copy2(os.path.join(E09, f), dst / "ai" / "E09" / f)
    return str(dst)


def test_con_outputs_de_proveedores_y_sin_png_el_html_se_genera(case_copy):
    h = _html(case_copy)
    assert h.rstrip().endswith("</html>")
    assert "Revisiones por proveedor" in h and "Geometry guard" in h


def test_svg_presente_y_png_ausente_produce_fallback_svg(case_copy):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120">'
           '<rect width="300" height="120" fill="#dfeee2"/></svg>')
    open(os.path.join(case_copy, "ai", "E09", "ESCALIMETRO_PRESENTATION_STANDARD_03.svg"),
         "w", encoding="utf-8").write(svg)
    h = _html(case_copy)
    assert "SVG AVAILABLE · PNG RASTERIZATION FAILED" in h
    assert "data:image/svg+xml;base64," in h
    assert "PASS</span>" not in h.split("Presentation Standard 03")[1][:600]   # no se declara PASS


def test_el_html_muestra_la_etapa_que_fallo(case_copy):
    p = os.path.join(case_copy, "ai", "E09", "run_manifest.json")
    d = json.load(open(p, encoding="utf-8"))
    d["presentation_render_status"] = FAILED
    d["final_status"] = FAILED
    d["errors"] = [{"stage": "presentation_render", "at": "x",
                    "error": "PresentationRasterizationError", "reason": "ningún backend"}]
    atomic_write_json(p, d)
    h = _html(case_copy)
    assert "presentation_render" in h and "PresentationRasterizationError" in h
    assert "Errores registrados" in h


def test_el_html_separa_gate_api_de_render(case_copy):
    h = _html(case_copy)
    assert "GATE API (ejecución de proveedores)" in h
    assert "PRESENTATION RENDER (artefacto PNG)" in h


# ---------------------------------------------------------------------------------------------------
# inyección de fallo (§28) — la clase exacta de problema que ocurrió en Railway
# ---------------------------------------------------------------------------------------------------
def test_failure_injection_el_fallo_de_render_no_borra_la_evidencia(tmp_path, monkeypatch):
    """Se simula un rasterizador roto DESPUÉS de que los proveedores ya respondieron."""
    from escalimetro.ai import railway_e09_runner as R
    from escalimetro.ai import svg_rasterizer as SR

    case = tmp_path / "case"
    d = case / "ai" / "E09"
    d.mkdir(parents=True)
    # evidencia de proveedores YA persistida, como haría el pipeline real
    reviews = {a: {"rule_based": {"model": "rule_based_v1", "confidence": 0.55, "summary": "s",
                                  "scores": {"reception": 0.4}},
                   "anthropic": {"model": "claude-x", "confidence": 0.8, "summary": "s",
                                 "scores": {"reception": 0.42}},
                   "openai_vision": {"model": "gpt-x", "confidence": 0.7, "summary": "s",
                                     "scores": {"reception_convincing": 0.38}}} for a in "ABC"}
    atomic_write_json(str(d / "real_reviews_abc.json"), reviews)
    m = RunManifest(path=str(d / "run_manifest.json"), case=str(case))
    for a in "ABC":
        for s in ("rule_based", "anthropic", "openai_vision"):
            m.set_provider(s, a, OK)
    m.set_status("aggregator", OK)
    m.set_status("geometry_guard", OK)

    # ahora el rasterizador falla
    def boom(*a, **k):
        raise PresentationRasterizationError("backend caído a propósito", svg_length=10, target_width=3600)
    monkeypatch.setattr(SR, "rasterize_svg_to_bgr", boom)
    with pytest.raises(PresentationRasterizationError):
        SR.rasterize_svg_to_bgr("<svg/>", 3600)
    m.set_status("presentation_render", FAILED)
    m.add_error("presentation_render", {"error": "PresentationRasterizationError"})
    m.finish(FAILED)

    # la evidencia sigue intacta
    saved = json.load(open(d / "real_reviews_abc.json", encoding="utf-8"))
    assert all(saved[a]["anthropic"] for a in "ABC")
    man = RunManifest.load(str(d / "run_manifest.json"))
    assert all(man["anthropic"][a] == OK for a in "ABC")
    assert all(man["openai_visual"][a] == OK for a in "ABC")
    assert man["presentation_render_status"] == FAILED

    # y el informe se genera igual, mostrando ambas verdades
    h = R.build_html(str(case), R.env_report(),
                     {"ok": False, "return_code": None, "error": "PresentationRasterizationError",
                      "seconds": 139.2}, R.load_outputs(str(case)))
    assert h.rstrip().endswith("</html>")
    assert "claude-x" in h and "gpt-x" in h            # la evidencia se muestra
    assert "PresentationRasterizationError" in h        # y el fallo también
