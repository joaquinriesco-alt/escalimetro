"""E16.1 — retirar los acoplamientos de caso conocidos ANTES del examen del segundo dibujo real.

E16 quedó BLOQUEADO por falta de un tercer plano, pero su auditoría encontró que varias rutas
genéricas llevaban la identidad de la Oficina 403 cosida: la Standard 02/03 imprimía "543 m²
publicados", la lámina ciega de brokers decía "Oficina 403", el runner traía la 403 por defecto y sus
hashes como expectativa universal, el orquestador presuponía el proyecto y el side-by-side rotulaba
"ORIGINAL GPS".

Estos tests fijan la frontera: el runtime genérico no puede depender de un caso concreto. Las
referencias en documentación, fixtures de regresión explícitos y datos dentro de `cases/**` son
legítimas y NO se persiguen aquí."""
import ast
import json
import os
import re
import types

import pytest

from escalimetro import fit_evidence as FE
from escalimetro.ai import railway_e09_runner as R
from escalimetro.ai.board02 import build_board02
from escalimetro.ai.orchestrator import AIOrchestrator
from escalimetro.case_context import CaseContext, from_case_dir
from escalimetro.fit_evidence import FitEvidence, PresentationFit
from escalimetro.generalization import freeze
from escalimetro.layout.e06.scale import scaled_shell
from escalimetro.layout.model import Layout, load_program
from escalimetro.renderer.side_by_side import comparison_three
from escalimetro.schemas.floorplate import Floorplate
from escalimetro.validation import boards as VB

ROOT = os.path.dirname(os.path.dirname(__file__))
C403 = os.path.join(ROOT, "cases", "001_gps_403")
C401 = os.path.join(ROOT, "cases", "002_gps_401")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")
E07 = os.path.join(C403, "layouts", "E07")
E08 = os.path.join(C403, "ai", "E08")

TERMS = ("403", "401", "543", "252", "GPS", "001_gps_403", "002_gps_401",
         "df6b86058ebb", "5c5c276923dd", "e12cc722485b")


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _board02_inputs():
    ctx = from_case_dir(C403)
    ev = FE.load(C403, PROG)
    shell = scaled_shell(Floorplate.load(os.path.join(C403, "outputs", "floorplate.json")), 1.0)
    spec = _j(os.path.join(E08, "presentation_spec.json"))
    rows = {r["alt"]: r for r in _j(os.path.join(E07, "alternative_comparison.json"))["rows"]}
    alts = [{"alt": a, "layout": Layout.load(os.path.join(E07, "alternatives", a, "layout.json")),
             "metrics": _j(os.path.join(E07, "alternatives", a, "metrics.json")),
             "critique": _j(os.path.join(E07, "alternatives", a, "critique.json")),
             "row": rows[a]} for a in "ABC"]
    return alts, shell, spec, ctx, ev


def _codigo_sin_comentarios(path):
    src = open(path, encoding="utf-8").read()
    if path.endswith(".json"):
        return "\n".join("" if re.match(r'\s*"_', ln) else ln for ln in src.split("\n"))
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    doc = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant) \
           and isinstance(n.value.value, str):
            doc.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
    out = []
    for i, line in enumerate(src.split("\n"), 1):
        if i in doc:
            out.append(""); continue
        q, res = None, ""
        for ch in line:
            if q:
                res += ch
                if ch == q:
                    q = None
            elif ch in "\"'":
                q = ch; res += ch
            elif ch == "#":
                break
            else:
                res += ch
        out.append(res)
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------------
# board02 — Standard 02 y 03
# ---------------------------------------------------------------------------------------------------
def test_board02_toma_la_superficie_publicada_del_contexto():
    """§9 — `543 m² publicados` era un literal. Ahora es SOURCE_FACT del caso."""
    alts, shell, spec, ctx, ev = _board02_inputs()
    assert f"{ctx.published_area_label()} publicados" in build_board02(alts, shell, spec, ctx, ev, program=load_program(PROG))
    codigo = _codigo_sin_comentarios(os.path.join(ROOT, "src", "escalimetro", "ai", "board02.py"))
    assert '"543 m² publicados"' not in codigo      # el docstring sí lo cita: es documentación


def test_board02_toma_la_superficie_del_modelo_de_las_metricas():
    """§10 — `539 m² útiles del modelo` era otro literal. Es COMPUTED_RESULT de E04, la misma
    fuente que ya usaba la Standard 01."""
    alts, shell, spec, ctx, ev = _board02_inputs()
    esperado = f'{alts[0]["metrics"]["usable_area_m2"]:.0f} m² útiles del modelo'
    assert esperado in build_board02(alts, shell, spec, ctx, ev, program=load_program(PROG))
    codigo = _codigo_sin_comentarios(os.path.join(ROOT, "src", "escalimetro", "ai", "board02.py"))
    assert '"539 m² útiles del modelo"' not in codigo


FABRICADO = {"fit": "FIT", "technical_fit": "FIT", "robustness": "ROBUST_FIT",
             "scale_confidence": "HIGH", "scale": "CONFIRMED"}


@pytest.mark.parametrize("falso", [
    FABRICADO, {}, None, "FIT", 42,
    types.SimpleNamespace(scale="CONFIRMED", scale_confidence="HIGH"),
])
def test_board02_rechaza_un_veredicto_fabricado(falso):
    """§27 — el mismo contrato que la Standard 01: un dict con las claves correctas no es evidencia."""
    alts, shell, spec, ctx, _ = _board02_inputs()
    with pytest.raises(TypeError):
        build_board02(alts, shell, spec, ctx, falso, program=load_program(PROG))


def test_board02_rechaza_un_presentationfit_construido_a_mano():
    alts, shell, spec, ctx, ev = _board02_inputs()
    forjado = PresentationFit.from_evidence(ctx, ev)
    with pytest.raises(TypeError):
        build_board02(alts, shell, spec, ctx, forjado, program=load_program(PROG))


def test_board02_exige_contexto():
    alts, shell, spec, _, ev = _board02_inputs()
    with pytest.raises(ValueError):
        build_board02(alts, shell, spec, None, ev, program=load_program(PROG))


def test_board02_rechaza_evidencia_sin_procedencia():
    """La regla de E15.3 llega también a la 02: una afirmación necesita artefactos."""
    from escalimetro.fit_evidence import EvidenceWithoutProvenance
    alts, shell, spec, ctx, _ = _board02_inputs()
    hueca = FitEvidence(technical=FE.FIT, robustness=FE.ROBUST_FIT, freshness=FE.FRESH)
    with pytest.raises(EvidenceWithoutProvenance):
        build_board02(alts, shell, spec, ctx, hueca, program=load_program(PROG))


def test_standard_02_de_403_sigue_byte_identica():
    alts, shell, spec, ctx, ev = _board02_inputs()
    disco = open(os.path.join(E08, "ESCALIMETRO_PRESENTATION_STANDARD_02.svg"), encoding="utf-8").read()
    assert build_board02(alts, shell, spec, ctx, ev, program=load_program(PROG)) == disco


def test_standard_03_usa_el_mismo_renderer_y_por_tanto_el_mismo_contrato():
    """§12 — la 03 es la 02 con otra spec. Corregir en un solo punto arregla las dos."""
    e09 = open(os.path.join(ROOT, "src", "escalimetro", "ai", "e09.py"), encoding="utf-8").read()
    assert "build_board02(board_alts, shell, spec, case_ctx, evidence, program=prog)" in e09
    assert 'STANDARD 02", "STANDARD 03' in e09


# ---------------------------------------------------------------------------------------------------
# lámina de validación de brokers
# ---------------------------------------------------------------------------------------------------
def test_la_lamina_ciega_toma_su_identidad_del_caso_y_del_programa():
    """§13 — la lámina que ve un broker real llevaba `Oficina 403 · 543 m² · 48 personas` cosido."""
    ctx = from_case_dir(C403)
    prog = _j(PROG)
    svg = VB.blind_board(C403, 0)
    assert f'{ctx.unit_label}  ·  {ctx.published_area_label()} publicados  ·  ' \
           f'{prog["target_headcount"]} personas' in svg
    codigo = _codigo_sin_comentarios(os.path.join(ROOT, "src", "escalimetro", "validation",
                                                  "boards.py"))
    assert '"Oficina 403  ·  543 m² publicados  ·  48 personas"' not in codigo


def test_la_lamina_de_validacion_exige_caso_y_programa():
    with pytest.raises(ValueError):
        VB.build_board({}, {}, [], "t", "s", ctx=None, program=_j(PROG))
    with pytest.raises(ValueError):
        VB.build_board({}, {}, [], "t", "s", ctx=from_case_dir(C403), program={})


def test_laminas_de_validacion_de_403_siguen_byte_identicas():
    import hashlib
    assert hashlib.sha256(VB.blind_board(C403, 0).encode()).hexdigest() == \
        "1998d3e46ce1156224bc7c12ead414d757c9ac3d35225b1cea2240a17b110536"
    assert hashlib.sha256(VB.reveal_board(C403).encode()).hexdigest() == \
        "3ac75ade8e79def51608f52458d2700d3e58ad6589852066b4c54acb9ab4d6e9"


# ---------------------------------------------------------------------------------------------------
# runner, orquestador, side-by-side
# ---------------------------------------------------------------------------------------------------
def test_el_runner_no_tiene_caso_por_defecto():
    """§14, §17 — antes: `DEFAULT_CASE = "cases/001_gps_403"`."""
    assert not hasattr(R, "DEFAULT_CASE")
    codigo = _codigo_sin_comentarios(os.path.join(ROOT, "src", "escalimetro", "ai",
                                                  "railway_e09_runner.py"))
    assert 'DEFAULT_CASE = "cases/001_gps_403"' not in codigo


def test_el_runner_se_detiene_si_nadie_declara_el_caso(monkeypatch):
    monkeypatch.delenv(R.CASE_ENV_VAR, raising=False)
    assert R.main(["--no-serve"]) == 2


def test_la_expectativa_de_hashes_la_declara_el_caso():
    """§16 — se preserva la regresión; cambia de dónde sale."""
    assert not hasattr(R, "EXPECTED_HASH_PREFIX"), "no debe quedar la expectativa universal"
    assert R.expected_hash_prefix(C403) == {"A": "df6b86058ebb", "B": "5c5c276923dd",
                                            "C": "e12cc722485b"}
    assert R.expected_hash_prefix(C401) == {}, "un caso que no la declara no hereda la de otro"


def test_la_expectativa_de_403_vive_dentro_del_caso():
    d = _j(os.path.join(C403, "ai", "E09", "EXPECTED_GEOMETRY_HASHES.json"))
    assert d["case_id"] == "001_gps_403"
    assert d["full_hashes"]["A"] == \
        "df6b86058ebb093f449e1054a0c65a902b7492f7986f4b8395489d63d46d7b99"
    assert d["full_hashes"]["B"] == \
        "5c5c276923dd7da69844ad3d409f4b879ac40c911144e4a11bf3cb4c6d8f066c"
    assert d["full_hashes"]["C"] == \
        "e12cc722485b9c58251621bd6f05e92fdc8633675156e8d26f2a110d6048e4c6"


def test_el_orquestador_no_presupone_un_proyecto():
    """§18 — antes: `project: str = "001_gps_403"`."""
    with pytest.raises(TypeError):
        AIOrchestrator()                      # project es obligatorio
    with pytest.raises(ValueError):
        AIOrchestrator("")                    # y no vale un vacío disfrazado de default
    assert AIOrchestrator("otro_proyecto", env={}).project == "otro_proyecto"


def test_side_by_side_no_presupone_gps():
    """§19 — el rótulo era `ORIGINAL GPS` para cualquier inmueble."""
    codigo = _codigo_sin_comentarios(os.path.join(ROOT, "src", "escalimetro", "renderer",
                                                  "side_by_side.py"))
    assert '"ORIGINAL GPS"' not in codigo
    import inspect
    assert "source_name" in inspect.signature(comparison_three).parameters


def test_la_fuente_del_side_by_side_sale_del_caso():
    from escalimetro.pipeline import PipelineConfig
    assert "source_name" in PipelineConfig.__dataclass_fields__
    assert PipelineConfig.__dataclass_fields__["source_name"].default == ""
    cli = open(os.path.join(ROOT, "src", "escalimetro", "cli.py"), encoding="utf-8").read()
    assert 'source_name=c.get("source_name", "")' in cli


# ---------------------------------------------------------------------------------------------------
# auditoría de alcance completo
# ---------------------------------------------------------------------------------------------------
def test_runtime_case_coupling_es_cero_en_alcance_completo():
    """§29 — auditoría de los 97 archivos del motor genérico, no de una subruta.

    La regla NO es 'el repo no puede mencionar 403'. Es 'el runtime genérico no puede depender de
    403'. Comentarios, docstrings y claves JSON de documentación quedan fuera a propósito."""
    hallazgos = []
    for f in sorted(freeze.engine_files()):
        for i, line in enumerate(_codigo_sin_comentarios(os.path.join(ROOT, f)).split("\n"), 1):
            if re.search(r"noqa:[^\n]*F40[13]", line):
                continue
            for t in TERMS:
                if t in line:
                    hallazgos.append(f"{f}:{i} [{t}] {line.strip()[:80]}")
    assert hallazgos == [], "RUNTIME_CASE_COUPLING debe ser 0:\n" + "\n".join(hallazgos)


# ---------------------------------------------------------------------------------------------------
# probe de binding: NO es evidencia de generalización
# ---------------------------------------------------------------------------------------------------
def test_el_probe_de_401_no_filtra_403_ni_543():
    """§26 — la 401 por las rutas que su evidencia permite. NO es un segundo dibujo: es la misma
    lámina. REAL DRAWING GENERALIZATION EVIDENCE: NO."""
    ctx = from_case_dir(C401)
    ev = FE.load(C401, PROG)
    p = PresentationFit.from_evidence(ctx, ev)
    blob = json.dumps(p.to_dict(), ensure_ascii=False)
    for t in ("403", "543", "ROBUST_FIT\"", "ROBUST WITHIN"):
        assert t not in blob, t
    assert p.technical_fit == FE.NO_FIT and p.robustness == FE.ROBUST_NO_FIT
    assert "252" in blob and "Oficina 401" in blob and "GPS Property" in blob


def test_el_probe_generico_no_filtra_nada_de_403():
    g = _j(os.path.join(ROOT, "tests", "fixtures", "generalization", "TEST_GENERIC_CASE.json"))
    ctx = CaseContext(case_id=g["case_id"], unit_label=g["unit_label"],
                      source_name=g["source_name"], published_area_m2=g["known_area_m2"])
    p = PresentationFit.from_evidence(ctx, FitEvidence())
    blob = json.dumps(p.to_dict(), ensure_ascii=False)
    for t in ("403", "543", "GPS", "ROBUST"):
        assert t not in blob, t


# ---------------------------------------------------------------------------------------------------
# regresiones duras
# ---------------------------------------------------------------------------------------------------
def test_403_standard_01_byte_identica():
    import hashlib
    from escalimetro.layout.e07.board import build_board
    from escalimetro.layout.e07.strategies import build_alternatives
    ctx = from_case_dir(C403)
    shell = scaled_shell(Floorplate.load(os.path.join(C403, "outputs", "floorplate.json")), 1.0)
    specs = {s.alt: s for s in build_alternatives(load_program(PROG))}
    alts = []
    for a in "ABC":
        d = os.path.join(E07, "alternatives", a)
        alts.append({"spec": specs[a], "result": types.SimpleNamespace(
            layout=Layout.load(os.path.join(d, "layout.json")),
            metrics=_j(os.path.join(d, "metrics.json")),
            critique=_j(os.path.join(d, "critique.json")))})
    svg = build_board(alts, shell, FE.load(C403, PROG), ctx=ctx, program=load_program(PROG))
    assert hashlib.sha256(svg.encode()).hexdigest() == \
        "175c43d48f61c91a397b4d25b89f5e2d2d645d84e0df8b8c5b19905ccedc519c"


def test_403_geometria_intacta():
    g = _j(os.path.join(C403, "ai", "E09", "geometry_hash_check.json"))
    assert g["geometry_hash_before"]["A"] == \
        "df6b86058ebb093f449e1054a0c65a902b7492f7986f4b8395489d63d46d7b99"
    assert all(g["geometry_hash_before"][a] == g["geometry_hash_after"][a] for a in "ABC")


def test_403_fit_evidence_sin_cambios():
    ev = FE.load(C403, PROG)
    assert (ev.technical, ev.robustness, ev.freshness) == (FE.FIT, FE.ROBUST_FIT, FE.LEGACY_VERIFIED)
    reg = _j(os.path.join(C403, "layouts", "EVIDENCE_LEGACY.json"))
    assert reg["producer_engine_baseline"] is None
    assert reg["producer_engine_baseline_status"] == "UNKNOWN"
    assert reg["verified_compatible_from_baseline"] == "E14"


def test_401_fit_evidence_sin_cambios():
    ev = FE.load(C401, PROG)
    assert (ev.technical, ev.robustness, ev.freshness) == (FE.NO_FIT, FE.ROBUST_NO_FIT,
                                                           FE.LEGACY_VERIFIED)
    assert ev.open_seats == "4/40" and ev.hard_violations == 5
