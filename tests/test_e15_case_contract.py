"""E15 — tests del contrato genérico de caso.

Lo que se vigila: que la identidad del inmueble viaje como DATO y no como constante del motor, que
ningún caso herede en silencio los valores de otro, y que el congelamiento histórico de E14 siga
siendo un hecho del pasado en vez de una cárcel para el desarrollo futuro."""
import json
import os
import re

import pytest

from escalimetro.case_context import (MISSING_PUBLISHED_AREA, MissingCaseMetadata, CaseContext,
                                      UNKNOWN_AREA_LABEL, UNKNOWN_SOURCE_LABEL, from_case_dir,
                                      unit_slug)
from escalimetro.generalization.metadata_preview import presentation_strings

ROOT = os.path.dirname(os.path.dirname(__file__))
C403 = os.path.join(ROOT, "cases", "001_gps_403")
C401 = os.path.join(ROOT, "cases", "002_gps_401")
GENERIC = os.path.join(ROOT, "tests", "fixtures", "generalization", "TEST_GENERIC_CASE.json")
E14 = os.path.join(ROOT, "cases", "generalization", "E14")
ENGINE_403 = ("403", "543", "GPS Property", "001_gps_403", "shell_semantics_403",
              "fit_robustness_403", "OFFICE_403")


@pytest.fixture(scope="module")
def generic():
    d = json.load(open(GENERIC, encoding="utf-8"))
    return CaseContext(case_id=d["case_id"], unit_label=d["unit_label"],
                       source_name=d["source_name"], published_area_m2=d["known_area_m2"],
                       published_area_kind=d["known_area_kind"])


# ---------------------------------------------------------------------------------------------------
# 1-3 · los tres contextos cargan
# ---------------------------------------------------------------------------------------------------
def test_403_metadata_carga_desde_el_caso():
    c = from_case_dir(C403)
    assert c.case_id == "001_gps_403" and c.unit_label == "Oficina 403"
    assert c.source_name == "GPS Property" and c.published_area_m2 == 543.0
    assert c.title() == "OFICINA 403 · GPS PROPERTY"
    assert c.published_area_label() == "543 m²"


def test_401_metadata_carga_desde_el_caso():
    c = from_case_dir(C401)
    assert c.case_id == "002_gps_401" and c.unit_label == "Oficina 401"
    assert c.source_name == "GPS Property" and c.published_area_m2 == 252.0
    assert c.title() == "OFICINA 401 · GPS PROPERTY"
    assert c.published_area_label() == "252 m²"


def test_metadata_sintetica_generica_carga(generic):
    assert generic.title() == "801 · EXAMPLE BROKER"
    assert generic.published_area_label() == "610 m²"
    assert generic.slug == "801"


# ---------------------------------------------------------------------------------------------------
# 4 · nunca 543 por defecto
# ---------------------------------------------------------------------------------------------------
def test_un_caso_sin_area_publicada_no_se_convierte_en_543():
    c = CaseContext(case_id="X", unit_label="Oficina 999")
    assert c.published_area_m2 is None
    assert c.published_area_label() == UNKNOWN_AREA_LABEL
    assert "543" not in c.published_area_label()
    with pytest.raises(MissingCaseMetadata) as e:
        c.require_published_area("el barrido de escala")
    assert MISSING_PUBLISHED_AREA in str(e.value) and "543" not in str(e.value)


def test_make_scenario_ya_no_tiene_543_por_defecto():
    import inspect
    from escalimetro.layout.e06.scale import make_scenario
    sig = inspect.signature(make_scenario)
    assert sig.parameters["published_m2"].default is None


def test_el_escenario_de_escala_usa_el_area_del_propio_caso():
    """El defecto que E14 no vio: el barrido de la 401 reportaba equivalentes calculados sobre 543."""
    from escalimetro.layout.e06.scale import make_scenario
    from escalimetro.schemas.floorplate import Floorplate
    f401 = Floorplate.load(os.path.join(C401, "outputs", "floorplate.json"))
    f403 = Floorplate.load(os.path.join(C403, "outputs", "floorplate.json"))
    assert make_scenario(f401, 0.95).implied_published_equiv_m2 == round(252 * 0.95 ** 2, 1)
    assert make_scenario(f403, 0.95).implied_published_equiv_m2 == round(543 * 0.95 ** 2, 1)


def test_sin_area_el_equivalente_publicado_es_none():
    from escalimetro.layout.e06.scale import make_scenario
    from escalimetro.schemas.floorplate import Floorplate
    fp = Floorplate.load(os.path.join(C401, "outputs", "floorplate.json"))
    fp.published_area_m2 = None
    assert make_scenario(fp, 1.0).implied_published_equiv_m2 is None


# ---------------------------------------------------------------------------------------------------
# 5-7 · ningún caso hereda la identidad de otro
# ---------------------------------------------------------------------------------------------------
def test_el_titulo_de_401_nunca_dice_403():
    s = presentation_strings(from_case_dir(C401))
    blob = json.dumps(s, ensure_ascii=False)
    assert "403" not in blob and "543" not in blob


def test_la_superficie_de_401_nunca_dice_543():
    assert from_case_dir(C401).published_area_label() == "252 m²"


def test_el_caso_generico_nunca_dice_gps(generic):
    blob = json.dumps(presentation_strings(generic), ensure_ascii=False)
    for term in ("GPS", "403", "543", "Oficina"):
        assert term not in blob, term
    assert "EXAMPLE BROKER" in blob and "801" in blob and "610" in blob


def test_sin_fuente_declarada_no_se_inventa_una():
    c = CaseContext(case_id="X", unit_label="Oficina 999")
    assert c.title() == "OFICINA 999"                 # sin ' · ' ni fuente
    assert c.source_label() == UNKNOWN_SOURCE_LABEL
    assert "GPS" not in c.title() and "GPS" not in c.source_label()


# ---------------------------------------------------------------------------------------------------
# 8-9 · identificadores y artefactos derivados del caso
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label,slug", [("Oficina 403", "403"), ("Oficina 401", "401"),
                                        ("801", "801"), ("OF. 12-B", "12"),
                                        ("Piso Ejecutivo", "PISO_EJECUTIVO")])
def test_el_slug_es_determinista_y_legible(label, slug):
    assert unit_slug(label) == slug
    assert unit_slug(label) == unit_slug(label)


def test_el_layout_id_se_deriva_del_caso():
    assert from_case_dir(C403).layout_id("A", "EFICIENTE") == "OFFICE_403_A_EFICIENTE"
    assert from_case_dir(C401).layout_id("A", "EFICIENTE") == "OFFICE_401_A_EFICIENTE"


def test_el_engine_recibe_el_prefijo_no_lo_conoce():
    import inspect
    from escalimetro.layout.e07.engine import Engine
    assert "layout_id_prefix" in inspect.signature(Engine.__init__).parameters
    src = inspect.getsource(Engine)
    assert "OFFICE_403" not in src


def test_las_rutas_de_artefactos_se_derivan_del_caso():
    a403, a401 = from_case_dir(C403).artifacts, from_case_dir(C401).artifacts
    assert a403.robustness_png.endswith("fit_robustness.png")
    assert "403" not in os.path.basename(a403.robustness_png)
    assert any(p.endswith("shell_semantics_403.png") for p in a403.semantics_png_candidates)
    assert any(p.endswith("shell_semantics_401.png") for p in a401.semantics_png_candidates)
    assert a403.resolve_semantics_png() is not None       # el artefacto histórico sigue encontrándose
    assert a401.resolve_semantics_png() is not None


def test_el_board_exige_contexto_y_no_inventa_uno():
    import inspect
    from escalimetro.layout.e07.board import build_board
    assert "ctx" in inspect.signature(build_board).parameters
    with pytest.raises(ValueError):
        build_board([], None, {}, ctx=None)


# ---------------------------------------------------------------------------------------------------
# 10 · sin degradación silenciosa
# ---------------------------------------------------------------------------------------------------
def test_el_artefacto_semantico_ausente_emite_diagnostico(tmp_path, capsys):
    from escalimetro.case_context import SEMANTICS_ARTIFACT_MISSING
    src = open(os.path.join(ROOT, "src", "escalimetro", "layout", "run.py"), encoding="utf-8").read()
    assert SEMANTICS_ARTIFACT_MISSING in src, "un artefacto ausente debe reportarse, no omitirse"
    assert "shell_semantics_403.png" not in src
    c = CaseContext(case_id="X", unit_label="Oficina 999", case_dir=str(tmp_path))
    assert c.artifacts.resolve_semantics_png() is None


# ---------------------------------------------------------------------------------------------------
# 11-12 · semántica del freeze de E14
# ---------------------------------------------------------------------------------------------------
def test_el_congelamiento_historico_de_e14_sigue_siendo_valido():
    before = json.load(open(os.path.join(E14, "FROZEN_ENGINE_MANIFEST_BEFORE.json"), encoding="utf-8"))
    after = json.load(open(os.path.join(E14, "FROZEN_ENGINE_MANIFEST_AFTER.json"), encoding="utf-8"))
    assert before["engine_hash"] == after["engine_hash"]
    assert before["engine_hash"].startswith("5ce5f6a1f4e3dd17")
    assert json.load(open(os.path.join(E14, "engine_freeze_check.json"), encoding="utf-8"))["identical"]


def test_e14_ya_no_congela_el_desarrollo_futuro():
    """Ningún test puede exigir que el motor de hoy sea idéntico al de E14."""
    t = open(os.path.join(ROOT, "tests", "test_e14_generalization.py"), encoding="utf-8").read()
    assert "test_el_motor_congelado_sigue_igual_hoy" not in t
    assert "test_el_freeze_de_e14_no_congela_el_desarrollo_futuro" in t


def test_el_motor_de_hoy_puede_diferir_del_de_e14():
    from escalimetro.generalization.freeze import compare, manifest
    hist = json.load(open(os.path.join(E14, "FROZEN_ENGINE_MANIFEST_BEFORE.json"), encoding="utf-8"))
    c = compare(hist, manifest(ROOT, "", ""))
    assert isinstance(c["identical"], bool)          # se mide, no se exige


# ---------------------------------------------------------------------------------------------------
# 13 · regresión de la 403
# ---------------------------------------------------------------------------------------------------
def test_los_hashes_de_geometria_de_403_no_cambiaron():
    g = json.load(open(os.path.join(C403, "ai", "E09", "geometry_hash_check.json"), encoding="utf-8"))
    assert g["identical"] is True
    for a, pref in (("A", "df6b86058ebb"), ("B", "5c5c276923dd"), ("C", "e12cc722485b")):
        assert g["geometry_hash_before"][a].startswith(pref)


def test_el_layout_id_no_entra_en_el_hash_de_geometria():
    """§12 — el hash describe geometría, no nombres. Si entrara, renombrar rompería los hashes."""
    from escalimetro.ai.geometry_guard import canonical_geometry
    from escalimetro.layout.model import Layout
    lay = Layout.load(os.path.join(C403, "layouts", "E07", "alternatives", "A", "layout.json"))
    before = json.dumps(canonical_geometry(lay), sort_keys=True, default=str)
    lay.layout_id = "OFFICE_999_CUALQUIER_COSA"
    assert json.dumps(canonical_geometry(lay), sort_keys=True, default=str) == before


def test_la_lamina_de_403_sigue_siendo_byte_identica():
    """§26 — no es comparación de píxeles: el SVG regenerado con el código de E15 es el mismo archivo."""
    import types
    from escalimetro.schemas.floorplate import Floorplate
    from escalimetro.layout.model import Layout, load_program
    from escalimetro.layout.e06.scale import scaled_shell
    from escalimetro.layout.e07.board import build_board
    from escalimetro.layout.e07.run import fit_verdict_for
    from escalimetro.layout.e07.strategies import build_alternatives
    e07 = os.path.join(C403, "layouts", "E07")
    ctx = from_case_dir(C403)
    shell = scaled_shell(Floorplate.load(os.path.join(C403, "outputs", "floorplate.json")), 1.0)
    prog = load_program(os.path.join(ROOT, "program_templates", "office_balanced_48.json"))
    specs = {s.alt: s for s in build_alternatives(prog)}
    alts = []
    for a in "ABC":
        d = os.path.join(e07, "alternatives", a)
        alts.append({"spec": specs[a], "result": types.SimpleNamespace(
            layout=Layout.load(os.path.join(d, "layout.json")),
            metrics=json.load(open(os.path.join(d, "metrics.json"), encoding="utf-8")),
            critique=json.load(open(os.path.join(d, "critique.json"), encoding="utf-8")))})
    new = build_board(alts, shell, fit_verdict_for(ctx), ctx=ctx)
    old = open(os.path.join(e07, "ESCALIMETRO_PRESENTATION_STANDARD_01.svg"), encoding="utf-8").read()
    assert new == old


# ---------------------------------------------------------------------------------------------------
# 14 · auditoría de literales — cero acoplamiento del motor genérico
# ---------------------------------------------------------------------------------------------------
#: módulos del motor genérico de layouts y presentación. Ninguno puede contener identidad de un caso.
GENERIC_ENGINE = [
    os.path.join("layout", "run.py"),
    os.path.join("layout", "e06", "run.py"),
    os.path.join("layout", "e06", "scale.py"),
    os.path.join("layout", "e07", "run.py"),
    os.path.join("layout", "e07", "board.py"),
    os.path.join("layout", "e07", "engine.py"),
    os.path.join("layout", "e07", "pipeline.py"),
    os.path.join("layout", "e06", "verdict.py"),
    "case_context.py",
]


def _code_lines(path: str):
    """Lineas de CODIGO: sin docstrings ni comentarios. Ahi la historia si puede nombrar a la 403;
    lo que no puede es que el motor la conozca en tiempo de ejecucion."""
    import ast
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    skip = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            skip.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    out = []
    for i, ln in enumerate(src.splitlines(), 1):
        if i in skip or ln.strip().startswith("#"):
            continue
        out.append((i, ln))
    return out


@pytest.mark.parametrize("rel", GENERIC_ENGINE)
def test_el_motor_generico_no_contiene_identidad_de_ningun_caso(rel):
    path = os.path.join(ROOT, "src", "escalimetro", rel)
    bad = [(i, ln.strip(), t) for i, ln in _code_lines(path) for t in ENGINE_403 if t in ln]
    assert bad == [], f"GENERIC_ENGINE_COUPLING en {rel}: {bad}"


def test_la_auditoria_de_literales_esta_documentada():
    doc = open(os.path.join(ROOT, "docs", "E15_CASE_COUPLING_AUDIT.md"), encoding="utf-8").read()
    assert "GENERIC_ENGINE_COUPLING" in doc
    for cat in ("HISTORICAL_FIXTURE", "TEST_EXPECTATION", "EXPERIMENT_SPECIFIC",
                "DOCUMENTATION_HISTORY", "CASE_METADATA"):
        assert cat in doc, cat
