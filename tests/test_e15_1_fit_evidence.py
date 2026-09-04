"""E15.1 — frontera entre HECHOS DE ENTRADA y EVIDENCIA COMPUTADA.

Lo que se vigila: que ningún `case.json` declare un resultado, que el veredicto salga de los
artefactos que el motor produjo, que evidencia vieja no se presente como actual, y que la
factibilidad técnica y la robustez de escala no se colapsen en un solo string ambiguo."""
import json
import os

import pytest

from escalimetro import fit_evidence as FE
from escalimetro.case_context import CaseContext, from_case_dir

ROOT = os.path.dirname(os.path.dirname(__file__))
C403 = os.path.join(ROOT, "cases", "001_gps_403")
C401 = os.path.join(ROOT, "cases", "002_gps_401")
PROG = os.path.join(ROOT, "program_templates", "office_balanced_48.json")
GENERIC = os.path.join(ROOT, "tests", "fixtures", "generalization", "TEST_GENERIC_CASE.json")

#: nombres que, en un archivo de ENTRADA, delatan un resultado de ejecución
RESULT_FIELDS = ("fit_verdict", "technical_fit", "robustness", "robustness_result", "recommendation",
                 "hard_violations", "program_completeness", "critic_score", "layout_quality",
                 "ai_review", "broker_ready", "gate", "classification", "verdict")


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _case_files():
    base = os.path.join(ROOT, "cases")
    return [os.path.join(base, d, "case.json") for d in sorted(os.listdir(base))
            if os.path.exists(os.path.join(base, d, "case.json"))]


# ---------------------------------------------------------------------------------------------------
# pureza de la entrada (§5, §25, §31)
# ---------------------------------------------------------------------------------------------------
def test_ningun_case_json_declara_un_resultado():
    for p in _case_files():
        d = _j(p)
        for k in d:
            if k.startswith("_"):
                continue
            assert k not in RESULT_FIELDS, f"{p} declara el resultado '{k}'"


def test_el_veredicto_ya_no_esta_en_case_json():
    for p in _case_files():
        assert "fit_verdict" not in _j(p), p


def test_case_json_solo_tiene_campos_del_contrato():
    """Lista blanca explícita: si aparece un campo nuevo hay que decidir de qué lado de la frontera está."""
    allowed = {"case_id", "image", "image_note", "unit_label", "known_area_m2", "known_area_kind",
               "overrides", "vision", "segmentation", "simplify_eps_frac", "mask_open_px",
               "source_name", "display_name", "sibling_units", "scale_confidence"}
    for p in _case_files():
        extra = {k for k in _j(p) if not k.startswith("_")} - allowed
        assert not extra, f"{p}: campos fuera del contrato {extra}"


def test_el_contexto_no_transporta_veredicto():
    c = from_case_dir(C403)
    assert not hasattr(c, "fit_verdict")
    for attr in ("technical_fit", "robustness", "fit", "verdict", "recommendation"):
        assert not hasattr(c, attr), attr


def test_los_pesos_del_programa_son_entrada_no_resultado():
    """`adjacency_quality` es un PESO del objetivo, no una medición. Único hallazgo de la auditoría."""
    w = _j(PROG)["objectives_weights"]
    assert "adjacency_quality" in w and isinstance(w["adjacency_quality"], (int, float))
    assert 0 < w["adjacency_quality"] < 1


# ---------------------------------------------------------------------------------------------------
# el veredicto viene de artefactos computados (§7, §9, §10)
# ---------------------------------------------------------------------------------------------------
def test_la_evidencia_de_403_sale_de_artefactos_computados():
    ev = FE.load(C403, PROG)
    assert ev.technical == FE.FIT
    assert ev.robustness == FE.ROBUST_FIT
    assert ev.source_artifacts, "sin artefactos no hay evidencia"
    for a in ev.source_artifacts:
        assert os.path.exists(os.path.join(ROOT, a)), a
        assert "case.json" not in a, "un veredicto no puede salir de los metadatos del caso"
    assert any("E06/fit_robustness_report.json" in a for a in ev.source_artifacts)
    assert any("E07/gates.json" in a for a in ev.source_artifacts)


def test_la_robustez_de_403_coincide_con_el_reporte_de_e06():
    rob = _j(os.path.join(C403, "layouts", "E06", "fit_robustness_report.json"))
    ev = FE.load(C403, PROG)
    assert ev.robustness == rob["classification"]
    assert ev.min_scale_factor_exact_fit == rob["min_scale_factor_exact_fit"]
    assert ev.pct_scenarios_exact_fit == rob["pct_scenarios_exact_fit"]


def test_la_factibilidad_de_403_coincide_con_el_gate_e1t():
    gates = _j(os.path.join(C403, "layouts", "E07", "gates.json"))
    assert all(v["E1-T"]["status"] == "PASS" for v in gates.values())
    assert FE.load(C403, PROG).technical == FE.FIT


def test_sin_artefactos_no_hay_veredicto(tmp_path):
    ev = FE.load(str(tmp_path), PROG)
    assert ev.technical == FE.TECHNICAL_NOT_EVALUATED
    assert ev.robustness == FE.ROBUSTNESS_NOT_EVALUATED
    assert ev.evaluated is False and ev.presentable is False
    assert ev.source_artifacts == []


# ---------------------------------------------------------------------------------------------------
# dos capas, no un string ambiguo (§21, §22)
# ---------------------------------------------------------------------------------------------------
def test_401_conserva_su_no_fit_tecnico_real():
    """E15 decía 'FIT NO EVALUADO' para la 401 pese a que E14 produjo evidencia técnica de NO_FIT."""
    ev = FE.load(C401, PROG)
    assert ev.technical == FE.NO_FIT
    assert ev.program_complete is False
    assert ev.open_seats == "4/40"
    assert ev.hard_violations == 5
    assert ev.collisions == 0


def test_401_tiene_robustez_robust_no_fit():
    rob = _j(os.path.join(C401, "layouts", "E06", "fit_robustness_report.json"))
    assert rob["classification"] == "ROBUST_NO_FIT"
    assert FE.load(C401, PROG).robustness == FE.ROBUST_NO_FIT


def test_las_dos_capas_son_independientes():
    """Un NO_FIT técnico con robustez no evaluada es un estado legítimo y distinguible."""
    ev = FE.FitEvidence(technical=FE.NO_FIT, robustness=FE.ROBUSTNESS_NOT_EVALUATED,
                        freshness=FE.FRESH)
    assert ev.evaluated is True and ev.presentable is True
    ctx = CaseContext(case_id="X", unit_label="Oficina 999")
    p = FE.presentation_fit(ctx, ev)   # E15.2: PresentationFit tipado, acceso por atributo
    assert p.technical_fit == FE.NO_FIT and p.robustness == FE.ROBUSTNESS_NOT_EVALUATED
    assert p.fit_label == FE.TECHNICAL_LABEL[FE.NO_FIT]      # no colapsa en un único string


def test_la_disposicion_comercial_no_entra_en_la_evidencia_tecnica():
    """§23 — BROKER_READY y compañía pertenecen a E13, no aquí."""
    blob = json.dumps(FE.load(C403, PROG).to_dict(), ensure_ascii=False).upper()
    for term in ("BROKER_READY", "READY_FOR_BROKER_REVIEW", "COMMERCIAL_GATE", "E1-C"):
        assert term not in blob, term


# ---------------------------------------------------------------------------------------------------
# frescura (§11, §12, §24)
# ---------------------------------------------------------------------------------------------------
def test_la_evidencia_historica_esta_verificada_por_registro_explicito():
    for case in (C403, C401):
        ev = FE.load(case, PROG)
        assert ev.freshness == FE.LEGACY_VERIFIED and ev.stale_reasons == []
        reg = _j(os.path.join(case, "layouts", FE.LEGACY_REGISTRY))
        assert reg["pinned_fingerprint"]["floorplate_sha256"]
        assert {a["path"] for a in reg["artifacts"]}


def test_un_cambio_de_floorplate_vuelve_la_evidencia_stale(tmp_path):
    """§24 — el test que importa: nunca mostrar ROBUST_WITHIN… en silencio tras cambiar la geometría."""
    import shutil
    case = tmp_path / "caso"
    shutil.copytree(C403, case, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("ai", "validation", "outputs"))
    os.makedirs(case / "outputs", exist_ok=True)
    fp = _j(os.path.join(C403, "outputs", "floorplate.json"))
    fp["area_m2"] = 999.0                                   # la geometría cambió
    json.dump(fp, open(case / "outputs" / "floorplate.json", "w", encoding="utf-8"))
    ev = FE.load(str(case), PROG)
    assert ev.evaluated is True                              # los artefactos siguen ahí
    assert ev.freshness == FE.STALE
    assert any("floorplate" in r for r in ev.stale_reasons)
    assert ev.presentable is False
    p = FE.presentation_fit(from_case_dir(C403), ev)
    assert p.fit_label == FE.STALE_LABEL
    assert "ROBUST WITHIN" not in p.fit_label


def test_un_cambio_de_programa_vuelve_la_evidencia_stale(tmp_path):
    import shutil
    case = tmp_path / "caso"
    shutil.copytree(C403, case, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("ai", "validation"))
    other = tmp_path / "program.json"
    d = _j(PROG); d["target_headcount"] = 60
    json.dump(d, open(other, "w", encoding="utf-8"))
    ev = FE.load(str(case), str(other))
    assert ev.freshness == FE.STALE
    assert any("program" in r for r in ev.stale_reasons)


def test_el_registro_legado_no_es_un_comodin(tmp_path):
    """No acepta cualquier artefacto viejo: sólo los que declara, con su sha256."""
    import shutil
    case = tmp_path / "caso"
    shutil.copytree(C403, case, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("ai", "validation"))
    reg = _j(case / "layouts" / FE.LEGACY_REGISTRY)
    reg["artifacts"] = [a for a in reg["artifacts"] if "E06" not in a["path"]]
    json.dump(reg, open(case / "layouts" / FE.LEGACY_REGISTRY, "w", encoding="utf-8"))
    ev = FE.load(str(case), PROG)
    assert ev.freshness == FE.STALE
    assert any("no está declarado" in r for r in ev.stale_reasons)


def test_un_artefacto_alterado_se_detecta(tmp_path):
    import shutil
    case = tmp_path / "caso"
    shutil.copytree(C403, case, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("ai", "validation"))
    p = case / "layouts" / "E06" / "fit_robustness_report.json"
    d = _j(p); d["classification"] = "ROBUST_FIT_INVENTADO"
    json.dump(d, open(p, "w", encoding="utf-8"))
    ev = FE.load(str(case), PROG)
    assert ev.freshness == FE.STALE
    assert any("sha256" in r for r in ev.stale_reasons)


def test_la_procedencia_declarada_gana_sobre_el_registro_legado():
    """Un artefacto que declare su propia huella no necesita el registro; se compara directamente."""
    from escalimetro.fit_evidence import _freshness, current_fingerprint
    now = dict(current_fingerprint(C403, PROG))
    now["producer_engine_baseline"] = "E15.2"      # E15.2: la procedencia también declara el motor
    ok, _ = _freshness(C403, [], now, PROG)
    assert ok == FE.FRESH
    bad, reasons = _freshness(C403, [], {**now, "floorplate_sha256": "0" * 64}, PROG)
    assert bad == FE.STALE and reasons


# ---------------------------------------------------------------------------------------------------
# contrato de presentación (§16, §29)
# ---------------------------------------------------------------------------------------------------
def test_la_lamina_exige_evidencia_explicita():
    """E15.2 endureció esto: antes bastaba con que el dict tuviera las claves correctas; ahora se
    exige el TIPO PresentationFit, así que un diccionario falla con TypeError."""
    from escalimetro.layout.e07.board import build_board
    ctx = from_case_dir(C403)
    with pytest.raises((TypeError, ValueError)):
        build_board([], None, fit=None, ctx=ctx)
    with pytest.raises(TypeError):
        build_board([], None, fit={"fit_label": "ROBUST WITHIN"}, ctx=ctx)   # blob a mano


def test_el_caso_generico_no_inventa_resultados():
    d = _j(GENERIC)
    ctx = CaseContext(case_id=d["case_id"], unit_label=d["unit_label"],
                      source_name=d["source_name"], published_area_m2=d["known_area_m2"])
    p = FE.presentation_fit(ctx, FE.FitEvidence())
    assert p.technical_fit == FE.TECHNICAL_NOT_EVALUATED
    assert p.robustness == FE.ROBUSTNESS_NOT_EVALUATED
    assert p.fit_label == FE.NOT_EVALUATED_LABEL
    blob = json.dumps(p.to_dict(), ensure_ascii=False)
    for t in ("403", "543", "GPS", "ROBUST_FIT", "ROBUST WITHIN"):
        assert t not in blob, t


def test_la_copy_de_lamina_vive_en_presentacion_no_en_el_caso():
    """§18 — las etiquetas comerciales son formato, no resultado, y no están en ningún case.json."""
    for p in _case_files():
        blob = json.dumps(_j(p), ensure_ascii=False)
        for t in ("ROBUST WITHIN", "FIT NO EVALUADO", "Confirma una dimensión"):
            assert t not in blob, f"{p} contiene copy de lámina: {t}"
    assert FE.ROBUSTNESS_LABEL[FE.ROBUST_FIT] == "ROBUST WITHIN ASSUMED SCALE RANGE"


def test_e07_ya_no_deriva_el_veredicto_del_contexto():
    import inspect
    from escalimetro.layout.e07 import run as R
    assert not hasattr(R, "fit_verdict_for")
    src = inspect.getsource(R.main)
    assert "load_fit_evidence" in src and "presentation_fit" in src


# ---------------------------------------------------------------------------------------------------
# regresión de la 403 (§20, §26, §27)
# ---------------------------------------------------------------------------------------------------
def test_la_lamina_de_403_sigue_byte_identica_con_evidencia_computada():
    import types
    from escalimetro.schemas.floorplate import Floorplate
    from escalimetro.layout.model import Layout, load_program
    from escalimetro.layout.e06.scale import scaled_shell
    from escalimetro.layout.e07.board import build_board
    from escalimetro.layout.e07.strategies import build_alternatives
    e07 = os.path.join(C403, "layouts", "E07")
    ctx = from_case_dir(C403)
    fit = FE.presentation_fit(ctx, FE.load(C403, PROG))
    shell = scaled_shell(Floorplate.load(os.path.join(C403, "outputs", "floorplate.json")), 1.0)
    specs = {s.alt: s for s in build_alternatives(load_program(PROG))}
    alts = []
    for a in "ABC":
        d = os.path.join(e07, "alternatives", a)
        alts.append({"spec": specs[a], "result": types.SimpleNamespace(
            layout=Layout.load(os.path.join(d, "layout.json")),
            metrics=_j(os.path.join(d, "metrics.json")),
            critique=_j(os.path.join(d, "critique.json")))})
    new = build_board(alts, shell, fit=fit, ctx=ctx)
    assert new == open(os.path.join(e07, "ESCALIMETRO_PRESENTATION_STANDARD_01.svg"),
                       encoding="utf-8").read()


def test_los_hashes_de_403_siguen_intactos():
    g = _j(os.path.join(C403, "ai", "E09", "geometry_hash_check.json"))
    assert g["identical"] is True
    for a, pref in (("A", "df6b86058ebb"), ("B", "5c5c276923dd"), ("C", "e12cc722485b")):
        assert g["geometry_hash_before"][a].startswith(pref)
