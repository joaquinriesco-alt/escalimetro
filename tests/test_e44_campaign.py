"""E44 — campaña de benchmark: manifiesto, conteo honesto, duplicados, ceguera, reveal, inmutabilidad.

Todo el material es de PRUEBA (example.com, PNG sintéticos). Ningún test cuenta como caso real y
ninguno sale a la red ni gasta; el motor fixture sólo ejercita el cableado y la campaña lo rechaza
como motor de un caso (`run_create`).
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_e37_reconstruction_lab import MODULOS, _foto, _plano_de_galeria, _plano_real  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALIMETRO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ESCALIMETRO_DEV", "1")
    monkeypatch.setenv("ESCALIMETRO_PASSWORD", "")
    monkeypatch.setenv("ESCALIMETRO_MIGRATE", "0")
    monkeypatch.setenv("ESCALIMETRO_RECON_FIXTURE", "1")
    for v in ("GEMINI_API_KEY", "OPENAI_API_KEY", "BFL_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    for m in MODULOS + ("webapp.campaign",):
        if m in sys.modules:
            importlib.reload(importlib.import_module(m))
    from webapp import campaign, store
    store.init()
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)
    return campaign, tmp_path


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _bundle(tmp, casos):
    """Escribe un bundle: casos = [(track, url, {nombre: bytes}, roles)]"""
    b = tmp / "bundle"
    b.mkdir(exist_ok=True)
    spec = []
    for track, url, files, extra in casos:
        assets = []
        for nombre, (blob, role) in files.items():
            (b / nombre).write_bytes(blob)
            assets.append({"file": nombre, "role": role, "sha256": _sha(blob),
                           "origin_url": url + "/" + nombre})
        spec.append({"track": track, "source_urls": [url], "captured_on": "2026-10-03",
                     "source": "corredora de prueba", "property_type": "OFFICE",
                     "published_m2": 120, "assets": assets, **extra})
    (b / "bundle.json").write_text(json.dumps({"cases": spec}))
    return str(b)


def _create_case(tmp, camp, url="https://example.com/ficha/1", n=3):
    files = {f"f{i}.png": (_foto(i), "photo") for i in range(n)}
    files["gt.png"] = (_plano_real(), "ground_truth_plan")
    out = camp.import_bundle(_bundle(tmp, [("CREATE", url, files, {})]))
    assert out["accepted"], out
    return out["accepted"][0]["case_id"]


def _improve_case(tmp, camp, url="https://example.com/ficha/2"):
    out = camp.import_bundle(_bundle(tmp, [("IMPROVE", url, {
        "plano.png": (_plano_de_galeria(), "published_plan")}, {})]))
    assert out["accepted"], out
    return out["accepted"][0]["case_id"]


def _eval_improve(**kw):
    d = {"reached_output": True, "errors": [], "fidelity": "OK", "legibility": "OK",
         "publishability": "ALTA", "human_interventions": 0, "needs_cad": False}
    return {**d, **kw}


# ---- manifiesto, provenance, conteo honesto --------------------------------------------------
def test_una_url_sola_no_es_un_caso(env):
    camp, _ = env
    cid = camp.register_url_only({"track": "IMPROVE", "source_urls": ["https://example.com/a"],
                                  "captured_on": "2026-10-03", "source": "x",
                                  "property_type": "OFFICE"})
    assert camp.status(camp.get(cid)) == camp.URL_ONLY
    c = camp.count("IMPROVE")
    assert (c["listed"], c["captured"], c["executed"], c["completed"], c["url_only"]) == (1, 0, 0, 0, 1)
    with pytest.raises(camp.CampaignError):
        camp.record(cid, "pipeline", {})
    assert "Sólo URL" in open(camp.build_index()).read()


def test_estado_derivado_y_n_no_se_infla(env):
    camp, tmp = env
    cid = _improve_case(tmp, camp)
    assert camp.status(camp.get(cid)) == camp.CAPTURED
    assert camp.count("IMPROVE")["captured"] == 1 and camp.count("IMPROVE")["executed"] == 0
    camp.record(cid, "pipeline", {"reached_output": False, "error": "x"})
    assert camp.status(camp.get(cid)) == camp.EXECUTED
    camp.record(cid, "evaluation", _eval_improve(reached_output=False, fidelity="NO_EVALUADO",
                                                 publishability="NO_EVALUADO"))
    c = camp.count("IMPROVE")
    assert (c["captured"], c["executed"], c["completed"]) == (1, 1, 1)
    s = camp.summary()
    assert s["status"] == "PARTIAL" and "PASS exige" in s["note"]
    assert s["tracks"]["IMPROVE"]["pipeline_success"] == {"reached_output": 0, "executed": 1}


def test_si_el_asset_cambia_el_caso_deja_de_contar(env):
    camp, tmp = env
    cid = _improve_case(tmp, camp)
    p = os.path.join(camp.case_dir(cid), "evidence", "plano.png")
    os.chmod(p, 0o644)
    open(p, "ab").write(b"x")
    assert camp.status(camp.get(cid)) == camp.URL_ONLY


def test_evidencia_original_de_solo_lectura(env):
    camp, tmp = env
    cid = _improve_case(tmp, camp)
    assert os.stat(os.path.join(camp.case_dir(cid), "evidence", "plano.png")).st_mode & 0o222 == 0


def test_provenance_obligatoria_y_sha_verificado(env):
    camp, tmp = env
    b = _bundle(tmp, [("IMPROVE", "https://example.com/p", {
        "plano.png": (_plano_de_galeria(), "published_plan")}, {})])
    spec = json.load(open(b + "/bundle.json"))
    spec["cases"][0]["assets"][0]["sha256"] = "0" * 64
    json.dump(spec, open(b + "/bundle.json", "w"))
    out = camp.import_bundle(b)
    assert not out["accepted"] and "sha256" in out["rejected"][0]["reason"]
    spec["cases"][0]["assets"][0]["sha256"] = _sha(_plano_de_galeria())
    del spec["cases"][0]["captured_on"]
    json.dump(spec, open(b + "/bundle.json", "w"))
    assert "captured_on" in camp.import_bundle(b)["rejected"][0]["reason"]


def test_sin_pii_y_poblacion_objetivo(env):
    camp, tmp = env
    for extra, frag in (({"notes": "llamar a corredor@example.com"}, "email"),
                        ({"notes": "fono +56 9 8765 4321"}, "email o teléfono"),
                        ({"property_type": "HOUSE"}, "población objetivo")):
        b = _bundle(tmp, [("IMPROVE", "https://example.com/pii", {
            "plano.png": (_plano_de_galeria(), "published_plan")}, extra)])
        out = camp.import_bundle(b)
        assert not out["accepted"] and frag in out["rejected"][0]["reason"]


# ---- duplicados ------------------------------------------------------------------------------
def test_duplicados_misma_pista_y_entre_pistas(env):
    camp, tmp = env
    _improve_case(tmp, camp, "https://www.example.com/ficha/9?utm=1")
    out = camp.import_bundle(_bundle(tmp, [("IMPROVE", "http://example.com/ficha/9/", {
        "otro.png": (_plano_de_galeria(), "published_plan")}, {})]))
    assert "duplicado dentro de la pista" in out["rejected"][0]["reason"]
    # mismo plano (sha) bajo otra URL: también duplicado
    out = camp.import_bundle(_bundle(tmp, [("IMPROVE", "https://example.com/otra", {
        "p.png": (_plano_de_galeria(), "published_plan")}, {})]))
    assert out["rejected"]
    # misma propiedad en la otra pista: exige declararlo en ambos
    files = {"f0.png": (_foto(1), "photo"), "gt.png": (_plano_real(), "ground_truth_plan")}
    out = camp.import_bundle(_bundle(tmp, [("CREATE", "https://example.com/ficha/9", files, {})]))
    assert "both_tracks_reason" in out["rejected"][0]["reason"]


# ---- ceguera ---------------------------------------------------------------------------------
def test_el_plano_real_no_esta_en_manifiesto_ni_en_evidence(env):
    camp, tmp = env
    cid = _create_case(tmp, camp)
    texto = open(camp._manifest_path()).read()           # noqa: SLF001
    assert _sha(_plano_real()) not in texto and "gt.png" not in texto
    assert "reconstruction_gt" not in texto
    assert sorted(os.listdir(os.path.join(camp.case_dir(cid), "evidence"))) == ["f0.png", "f1.png", "f2.png"]
    a = camp.blind_audit(cid)
    assert a["ok"], a


def test_ceguera_adversarial_detecta_fuga(env):
    camp, tmp = env
    cid = _create_case(tmp, camp)
    # 1) el plano real copiado a evidence/ (como si alguien lo hubiera dejado ahí)
    ev = os.path.join(camp.case_dir(cid), "evidence")
    open(os.path.join(ev, "x.png"), "wb").write(_plano_real())
    a = camp.blind_audit(cid)
    assert not a["ok"] and any("evidence" in v for v in a["violations"])
    os.remove(os.path.join(ev, "x.png"))
    # 2) el nombre del plano real filtrado a los datos declarados del caso
    m = camp.load()
    m["cases"][0]["notes"] = "ver plano_real.png"
    camp._save(m)                                          # noqa: SLF001
    assert not camp.blind_audit(cid)["ok"]


def test_plano_real_igual_a_un_input_se_rechaza(env):
    camp, tmp = env
    foto = _foto(1)
    out = camp.import_bundle(_bundle(tmp, [("CREATE", "https://example.com/ficha/7", {
        "f.png": (foto, "photo"), "g.png": (foto, "ground_truth_plan")}, {})]))
    assert "no es ciego" in out["rejected"][0]["reason"]


def test_el_motor_no_recibe_gt_y_fixture_no_cuenta(env):
    camp, tmp = env
    cid = _create_case(tmp, camp)
    from webapp import store
    from webapp.domain.reconstruction import runs
    with pytest.raises(camp.CampaignError, match="fixture"):
        camp.run_create(cid, "fixture_replay")
    pid = camp.get(cid)["recon_project_id"]
    rid = runs.create_initial(pid, "fixture_replay", "t")
    req = runs.build_request(runs.get(rid))
    visto = repr(req) + json.dumps(runs.get(rid)["inputs"], default=str)
    gt = store.q1("SELECT sha256, original_filename FROM recon_ground_truth WHERE project_id=?", (pid,))
    assert gt["sha256"] not in visto and gt["original_filename"] not in visto
    assert "reconstruction_gt" not in visto


def test_sin_credencial_queda_blocked_no_exito(env):
    camp, tmp = env
    cid = _create_case(tmp, camp)
    r = camp.run_create(cid, "openai_direct")
    assert r["status"] == camp.BLOCKED_CRED
    assert camp.status(camp.get(cid)) == camp.BLOCKED_CRED
    c = camp.count("CREATE")
    assert (c["captured"], c["executed"], c["completed"], c["blocked"]) == (1, 0, 0, 1)
    s = camp.summary()["tracks"]["CREATE"]
    assert s["blocked"][0]["status"] == camp.BLOCKED_CRED


# ---- reveal e inmutabilidad ------------------------------------------------------------------
def _correr_fixture(camp, cid):
    from webapp.domain.reconstruction import runs
    pid = camp.get(cid)["recon_project_id"]
    run = runs.execute(runs.create_initial(pid, "fixture_replay", "t"))
    return camp._record_run(cid, run), run                  # noqa: SLF001


def test_reveal_exige_cierre_y_resultados_inmutables(env):
    camp, tmp = env
    cid = _create_case(tmp, camp)
    with pytest.raises(camp.CampaignError):                   # nada que cerrar todavía
        camp.close_blind(cid)
    _correr_fixture(camp, cid)
    with pytest.raises(camp.CampaignError, match="exige cerrar"):
        camp.reveal(cid)
    from webapp.domain.reconstruction import groundtruth
    pid = camp.get(cid)["recon_project_id"]
    assert groundtruth.revealed_info(pid) is None
    assert camp.status(camp.get(cid)) == camp.EXECUTED
    with pytest.raises(camp.CampaignError, match="posterior|comparación|reveal"):
        camp.record(cid, "evaluation", {})
    camp.close_blind(cid, human_minutes=3, uncertainties=["núcleo"])
    # cerrada: no se agregan corridas ciegas ni se reescribe el cierre
    with pytest.raises(camp.CampaignError, match="cerrada|inmutable"):
        camp.record(cid, "pipeline", {})
    with pytest.raises(camp.CampaignError, match="inmutable"):
        camp.close_blind(cid)
    with pytest.raises(camp.CampaignError, match="reveal"):
        camp.record(cid, "evaluation", {})
    antes = open(os.path.join(camp.case_dir(cid), "results", "001_pipeline.json")).read()
    camp.reveal(cid)
    with pytest.raises(camp.CampaignError, match="inmutable"):
        camp.reveal(cid)
    dims = {k: "PARCIAL" for k in camp.CREATE_DIMS}
    camp.record(cid, "evaluation", {**dims, "needs_cad": True, "dominant_errors": ["ensamblaje"],
                                    "rating": "MALO"})
    assert camp.status(camp.get(cid)) == camp.COMPLETED
    # la corrida original y su registro siguen intactos
    assert open(os.path.join(camp.case_dir(cid), "results", "001_pipeline.json")).read() == antes
    # el índice muestra el plano real SÓLO después del reveal
    assert os.path.exists(os.path.join(camp.case_dir(cid), "review", "reconstruccion_pre_reveal.svg"))
    assert any(f.startswith("plano_real_post_reveal")
               for f in os.listdir(os.path.join(camp.case_dir(cid), "review")))


def test_el_indice_no_muestra_gt_antes_del_reveal(env):
    camp, tmp = env
    cid = _create_case(tmp, camp)
    _correr_fixture(camp, cid)
    camp.close_blind(cid)
    assert not any("plano_real" in f for f in os.listdir(os.path.join(camp.case_dir(cid), "review")))
    assert "plano_real" not in open(camp.build_index()).read()


def test_correccion_es_corrida_hija(env):
    camp, tmp = env
    cid = _create_case(tmp, camp)
    _, madre = _correr_fixture(camp, cid)
    hija = camp.correct_create(cid, "el dormitorio más grande")
    from webapp.domain.reconstruction import runs
    assert runs.get(hija["run_id"])["parent_run_id"] == madre["run_id"]
    assert runs.get(madre["run_id"])["output_sha256"] == madre["output_sha256"]
    camp.close_blind(cid)
    assert camp.events(cid)[-1]["data"]["prompts_humanos"] == 1


# ---- evaluación sin score compuesto ----------------------------------------------------------
def test_evaluacion_valida_dimensiones_y_no_hay_score(env):
    camp, tmp = env
    cid = _improve_case(tmp, camp)
    camp.record(cid, "pipeline", {"reached_output": True})
    for malo in ({"fidelity": "GENIAL"}, {"errors": ["BONITO"]}, {"human_interventions": -1},
                 {"rating": "10/10"}):
        with pytest.raises(camp.CampaignError):
            camp.record(cid, "evaluation", _eval_improve(**malo))
    camp.record(cid, "evaluation", _eval_improve(fidelity="MAL", publishability="ALTA",
                                                 errors=["ESCALA"], rating="BUENO"))
    s = camp.summary()["tracks"]["IMPROVE"]
    assert s["pretty_but_wrong_geometry"] == [cid]           # bonito + geometría mala = fallo
    assert s["error_frequency"] == {"ESCALA": 1}
    assert not any("score" in k for k in s)


def test_pass_solo_con_20_mas_20(env):
    camp, _ = env
    m = {"cases": []}
    for t in camp.TRACKS:
        assert camp.count(t, m)["completed"] == 0
    assert camp.summary()["status"] == "BLOCKED"            # nada capturado: no hay PASS ni PARTIAL


def test_run_improve_registra_fallo_sin_ocultarlo(env):
    camp, tmp = env
    cid = _improve_case(tmp, camp)
    info = camp.run_improve(cid)
    # el plano sintético no produce planta lista: eso es el resultado, no un error del operador
    assert info["reached_output"] is False and info["path"].endswith("publish_commercial_floorplan")
    assert camp.status(camp.get(cid)) == camp.EXECUTED
    from webapp.domain import floorplan, assets
    assert assets.first_of_kind(info["property_id"], assets.FLOORPLAN_ORIGINAL) is not None
    assert floorplan.technical_state(info["property_id"])["ready"] is False


def test_cli_status_corre_sin_red(env, capsys):
    camp, _ = env
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import e44_campaign
    assert e44_campaign.main(["status"]) == 0
    assert '"status": "BLOCKED"' in capsys.readouterr().out


def test_src_congelado():
    import subprocess
    r = subprocess.run(["git", "diff", "--name-only", "6324b1f", "HEAD", "--", "src/"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.stdout.strip() == ""
