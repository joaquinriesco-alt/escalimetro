"""E46 (A, C, H, I) — auditoría adversarial de la campaña E44 y su web piloto E45: integridad del
manifiesto (provenance, duplicados, PII, conteo), máquina de estados de CREAR y MEJORAR con
transiciones inválidas o repetidas, DEMO contra real y evaluaciones de sólo inserción.

Tests de CARACTERIZACIÓN del comportamiento actual (no imponen features). Los que documentan un
defecto llevan `DEFECTO E46-Hxx`: afirman el comportamiento defectuoso y fallarán el día que se
corrija (ver `reports/E46_REPORT.md`). Material sintético; sin red ni gasto.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from test_e37_reconstruction_lab import _foto, _plano_de_galeria, _plano_real
from test_e45_web_pilot import (BASE, _cid, _eval_plano, _eval_ux, _html, _subir_crear,  # noqa: F401
                                _subir_mejorar, env, planta_lista, planta_no_lista)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _bundle(tmp, casos, nombre="bundle"):
    b = tmp / nombre
    b.mkdir(exist_ok=True)
    spec = []
    for track, url, files, extra in casos:
        assets = []
        for fn, (blob, role) in files.items():
            (b / fn).write_bytes(blob)
            assets.append({"file": fn, "role": role, "sha256": _sha(blob), "origin_url": url + "/" + fn})
        spec.append({"track": track, "source_urls": [url], "captured_on": "2026-10-03",
                     "source": "corredora de prueba", "property_type": "OFFICE",
                     "published_m2": 120, "assets": assets, **extra})
    (b / "bundle.json").write_text(json.dumps({"cases": spec}))
    return str(b)


def _mejorar_lib(camp, tmp, url, blob=None, extra=None, nombre="b"):
    return camp.import_bundle(_bundle(tmp, [("IMPROVE", url, {
        "plano.png": (blob or _plano_de_galeria(), "published_plan")}, extra or {})], nombre))


# =============================================================================================
# A · integridad de E44
# =============================================================================================
def test_A1_la_clave_de_duplicados_ignora_esquema_www_query_fragmento_y_barra(env):
    c, camp, tmp = env
    base = camp.canonical_url("https://portal.cl/aviso/123")
    for variante in ("http://www.Portal.CL/aviso/123/", "https://portal.cl/aviso/123?utm=1#x",
                     "  HTTP://PORTAL.CL/Aviso/123  ".lower()):
        assert camp.canonical_url(variante) == base


def test_A1b_evasiones_conocidas_de_la_clave_de_duplicados_LIMITACION(env):
    """Variantes que apuntan al mismo aviso y que la clave NO unifica (la deduplicación fuerte es la
    de sha256 de los assets). Y el caso inverso: la query se descarta, así que dos avisos distintos
    que se distinguen sólo por `?id=` chocan como «duplicados»."""
    c, camp, tmp = env
    base = camp.canonical_url("https://portal.cl/aviso/123")
    for evasion in ("https://m.portal.cl/aviso/123", "https://portal.cl/aviso/123/index.html",
                    "https://portal.cl:443/aviso/123", "https://portal.cl//aviso/123",
                    "https://portal.cl/aviso/%31%32%33"):
        assert camp.canonical_url(evasion) != base, evasion
    assert camp.canonical_url("https://x.cl/ficha?id=1") == camp.canonical_url("https://x.cl/ficha?id=2")


def test_A1c_dos_avisos_distintos_que_solo_difieren_en_la_query_chocan_por_la_web(env):
    c, camp, tmp = env
    r1 = _subir_crear(c, n=2, referencia="https://x.cl/ficha?id=1")
    assert r1.status_code == 303
    r2 = c.post(f"{BASE}/crear", data={
        "fotos": [(__import__("io").BytesIO(_foto(50 + i)), f"f{i}.png") for i in range(2)],
        "plano_real": (__import__("io").BytesIO(_plano_real() + b"x"), "gt2.png"),
        "referencia": "https://x.cl/ficha?id=2"}, content_type="multipart/form-data")
    assert r2.status_code == 400 and "duplicado" in r2.get_data(as_text=True)


def test_A2_el_mismo_material_en_otra_url_o_en_la_otra_pista_se_rechaza_salvo_doble_motivo(env):
    c, camp, tmp = env
    plano = _plano_de_galeria()
    assert _mejorar_lib(camp, tmp, "https://example.com/a", plano)["accepted"]
    otra_url = _mejorar_lib(camp, tmp, "https://example.com/otra", plano, nombre="b2")
    assert otra_url["rejected"] and "duplicado" in otra_url["rejected"][0]["reason"]
    # la misma propiedad en la otra pista exige `both_tracks_reason` en AMBOS casos
    files = {f"f{i}.png": (_foto(i), "photo") for i in range(2)}
    files["gt.png"] = (_plano_real(), "ground_truth_plan")
    rechazado = camp.import_bundle(_bundle(tmp, [("CREATE", "https://example.com/a", files, {})], "c1"))
    assert rechazado["rejected"] and "both_tracks_reason" in rechazado["rejected"][0]["reason"]
    # con motivo sólo en el nuevo: sigue rechazado; el viejo no lo declaró
    solo_nuevo = camp.import_bundle(_bundle(tmp, [("CREATE", "https://example.com/a", files,
                                                   {"both_tracks_reason": "estudio"})], "c2"))
    assert solo_nuevo["rejected"]


def test_A3_pii_se_rechaza_en_notas_declarados_y_comentarios_pero_no_en_las_urls_DEFECTO_H09(env):
    c, camp, tmp = env
    for campo in ({"notes": "contacto juan@correo.cl"}, {"notes": "llamar al +56 9 1234 5678"},
                  {"declared": {"description": "tel 912345678"}}, {"source": "maria@x.cl"}):
        out = _mejorar_lib(camp, tmp, "https://example.com/p" + str(abs(hash(str(campo)))), extra=campo,
                           nombre="pii")
        assert out["rejected"] and "email o teléfono" in out["rejected"][0]["reason"], campo
    # DEFECTO H09: el enlace de origen se guarda tal cual aunque lleve un email o un teléfono
    url = "https://portal.cl/aviso/1?contacto=juan@correo.cl&tel=+56912345678"
    out = _mejorar_lib(camp, tmp, url, nombre="pii2")
    assert out["accepted"] and camp.get(out["accepted"][0]["case_id"])["source_urls"] == [url]
    assert "juan@correo.cl" in open(camp.build_index()).read()      # y sale en el índice de revisión


def test_A3b_pii_limites_del_detector_LIMITACION(env):
    c, camp, tmp = env
    # no se detecta lo ofuscado
    camp._no_pii("escribir a juan arroba correo punto cl", "llamar al nueve uno dos tres")
    # falso positivo: tipologías en m² separadas por espacios suman 9+ dígitos y parecen un teléfono
    with pytest.raises(camp.CampaignError):
        camp._no_pii("tipologías 85 90 95 100 m2")


def test_A4_conteo_honesto_con_todos_los_estados_a_la_vez(env):
    c, camp, tmp = env
    ids = {}
    for i, k in enumerate(("sola", "captado", "ejecutado", "completo", "bloqueado", "excluido")):
        ids[k] = _mejorar_lib(camp, tmp, f"https://example.com/{k}", _plano_de_galeria() + bytes([i + 1]),
                              nombre=k)["accepted"][0]["case_id"] if k != "sola" else camp.register_url_only(
            {"track": "IMPROVE", "source_urls": ["https://example.com/sola"], "captured_on": "2026-10-04",
             "source": "x", "property_type": "OFFICE"})
    camp.record(ids["ejecutado"], "pipeline", {"reached_output": True})
    camp.record(ids["completo"], "pipeline", {"reached_output": True})
    camp.record(ids["completo"], "evaluation", {
        "reached_output": True, "errors": [], "fidelity": "OK", "legibility": "OK",
        "publishability": "ALTA", "human_interventions": 0, "needs_cad": False})
    camp.blocked(ids["bloqueado"], camp.BLOCKED_MATERIAL, "sin plano")
    camp.exclude(ids["excluido"], "duplicado manual")
    n = camp.count("IMPROVE")
    assert (n["listed"], n["captured"], n["executed"], n["completed"], n["blocked"], n["url_only"],
            n["excluded"]) == (6, 4, 2, 1, 1, 1, 1)
    # captured ⊇ executed ⊇ completed
    assert n["captured"] >= n["executed"] >= n["completed"]


def test_A5_el_material_alterado_o_perdido_saca_al_caso_de_todo_N(env):
    c, camp, tmp = env
    cid = _mejorar_lib(camp, tmp, "https://example.com/x")["accepted"][0]["case_id"]
    camp.record(cid, "pipeline", {"reached_output": True})
    assert camp.count("IMPROVE")["executed"] == 1
    ev = os.path.join(camp.case_dir(cid), "evidence", "plano.png")
    os.chmod(ev, 0o644)
    open(ev, "ab").write(b"alterado")                    # bytes distintos, mismo nombre
    assert camp.status(camp.get(cid)) == camp.URL_ONLY
    assert camp.count("IMPROVE")["executed"] == 0 and camp.count("IMPROVE")["url_only"] == 1
    with pytest.raises(camp.CampaignError):
        camp.record(cid, "evaluation", {})


@pytest.mark.parametrize("mutar,motivo", [
    (lambda a, d: a.__setitem__("file", "../fuera.png"), "falta el archivo"),
    (lambda a, d: a.__setitem__("file", "/etc/passwd"), "falta el archivo"),
    (lambda a, d: a.__setitem__("sha256", "0" * 64), "sha256 no coincide"),
    (lambda a, d: a.__setitem__("sha256", "ABC"), "sha256"),
    (lambda a, d: a.__setitem__("role", "ground_truth_plan"), "rol"),
    (lambda a, d: a.pop("origin_url"), "origin_url"),
    (lambda a, d: d.__setitem__("captured_on", "03/10/2026"), "AAAA-MM-DD"),
    (lambda a, d: d.__setitem__("property_type", "RESIDENTIAL"), "población objetivo"),
    (lambda a, d: d.__setitem__("published_m2", -5), "published_m2"),
    (lambda a, d: d.__setitem__("published_m2", "120"), "published_m2"),
    (lambda a, d: d.__setitem__("source_urls", ["javascript:alert(1)"]), "http"),
    (lambda a, d: d.__setitem__("track", "BOTH"), "track"),
    (lambda a, d: d.__setitem__("assets", []), "exactamente un plano"),
])
def test_A6_un_bundle_hostil_se_rechaza_por_caso_con_motivo_y_sin_residuos(env, mutar, motivo):
    c, camp, tmp = env
    b = _bundle(tmp, [("IMPROVE", "https://example.com/h", {"plano.png": (_plano_de_galeria(),
                                                                          "published_plan")}, {})])
    spec = json.load(open(os.path.join(b, "bundle.json")))
    caso = spec["cases"][0]
    mutar(caso["assets"][0] if caso["assets"] else {}, caso)
    json.dump(spec, open(os.path.join(b, "bundle.json"), "w"))
    out = camp.import_bundle(b)
    assert out["accepted"] == [] and motivo in out["rejected"][0]["reason"], out
    assert camp.load()["cases"] == []
    assert not os.path.isdir(os.path.join(camp.root(), "cases")) or not os.listdir(
        os.path.join(camp.root(), "cases"))


def test_A6b_un_symlink_del_bundle_que_apunta_afuera_no_entra(env):
    c, camp, tmp = env
    fuera = tmp / "secreto.png"
    fuera.write_bytes(_plano_de_galeria())
    b = _bundle(tmp, [("IMPROVE", "https://example.com/s", {"plano.png": (_plano_de_galeria(),
                                                                          "published_plan")}, {})])
    os.remove(os.path.join(b, "plano.png"))
    os.symlink(str(fuera), os.path.join(b, "plano.png"))
    out = camp.import_bundle(b)
    assert out["accepted"] == [] and "falta el archivo" in out["rejected"][0]["reason"]


def test_A6c_el_plano_real_identico_a_un_input_no_es_ciego(env):
    c, camp, tmp = env
    gt = _plano_real()
    files = {"f0.png": (gt, "photo"), "gt.png": (gt, "ground_truth_plan")}
    out = camp.import_bundle(_bundle(tmp, [("CREATE", "https://example.com/g", files, {})]))
    assert out["rejected"] and "no es ciego" in out["rejected"][0]["reason"]


def test_A7_la_regex_de_id_acepta_un_salto_de_linea_final_pero_ninguna_ruta_lo_sirve(env):
    """`$` casa antes de un `\\n` final: `case_dir` arma una ruta con salto de línea. No hay efecto
    (el caso no existe y las rutas devuelven 404), pero la validación es más laxa de lo que parece."""
    c, camp, tmp = env
    assert camp._ID.match("e44-imp-0123456789\n")
    assert camp.case_dir("e44-imp-0123456789\n").endswith("e44-imp-0123456789\n")
    assert c.get(f"{BASE}/caso/e44-imp-0123456789%0A").status_code == 404
    assert c.get(f"{BASE}/caso/e44-imp-0123456789/archivo/real").status_code == 404


def test_A8_excluir_reescribe_el_manifiesto_sin_evento_y_saca_del_N_incluso_a_un_completo(env):
    """`exclude` no es de sólo inserción: cambia el manifiesto en el sitio y no deja evento que diga
    cuándo ni desde qué estado. Sólo existe por CLI (no hay ruta web)."""
    c, camp, tmp = env
    cid = _mejorar_lib(camp, tmp, "https://example.com/e")["accepted"][0]["case_id"]
    camp.record(cid, "pipeline", {"reached_output": True})
    camp.record(cid, "evaluation", {"reached_output": True, "errors": [], "fidelity": "OK",
                                    "legibility": "OK", "publishability": "ALTA",
                                    "human_interventions": 0, "needs_cad": False})
    assert camp.count("IMPROVE")["completed"] == 1
    antes = sorted(os.listdir(os.path.join(camp.case_dir(cid), "results")))
    camp.exclude(cid, "motivo")
    assert camp.count("IMPROVE")["completed"] == 0 and camp.status(camp.get(cid)) == camp.EXCLUDED
    assert sorted(os.listdir(os.path.join(camp.case_dir(cid), "results"))) == antes   # sin evento nuevo
    assert not any(r.rule.endswith("/excluir") for r in c.application.url_map.iter_rules())


def test_A9_un_caso_excluido_libera_la_re_carga_de_la_misma_propiedad_H20_CERRADO(env):
    """E47.8 (cierra E46-H20): `_find_duplicate` ignora los excluidos. La recarga recibe id, carpeta
    y proyecto E37 propios; el excluido queda intacto con su motivo."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    camp.exclude(cid, "la corrida falló por un error transitorio")
    antes = camp.get(cid)
    r = _subir_crear(c, n=2)
    assert r.status_code == 303
    nuevo = _cid(r)
    assert nuevo != cid and camp.case_dir(nuevo) != camp.case_dir(cid)
    n = camp.get(nuevo)
    assert n["recon_project_id"] != antes["recon_project_id"]
    assert camp.get(cid) == antes and camp.status(camp.get(cid)) == camp.EXCLUDED
    assert camp.count("CREATE")["excluded"] == 1 and camp.count("CREATE")["captured"] == 1
    with pytest.raises(camp.CampaignError, match="duplicado"):           # el activo sigue deduplicando
        camp.import_upload(camp.CREATE, [("f0.png", _foto(0)), ("f1.png", _foto(1))],
                           ground_truth=("g.png", _plano_real()))


def test_A11_el_detector_de_PII_es_cuadratico_y_corre_antes_del_tope_de_largo_DEFECTO_H22(env):
    """`_EMAIL = [\\w.+-]+@…` se reintenta desde cada posición: un texto de N caracteres sin «@» cuesta
    O(N²) y la regex no suelta el GIL (se congelan TODOS los hilos del proceso). Medido: 80 000
    caracteres ≈ 20 s. En `_check_payload` el detector corre ANTES de `_text` (tope de 2000) y el
    formulario de evaluación no recorta el texto: un comentario pegado de 500 KB (el tope de
    formulario de werkzeug) bloquearía el servicio ~13 minutos. Aquí sólo se fija el crecimiento
    con tamaños chicos."""
    import time
    c, camp, tmp = env
    t = {}
    for n in (4000, 16000):
        s = "a" * n
        t0 = time.perf_counter()
        camp._no_pii(s)
        t[n] = time.perf_counter() - t0
    assert t[16000] / max(t[4000], 1e-6) > 6, t                       # 4× largo ⇒ ~16× tiempo
    fuente = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp",
                               "campaign.py"), encoding="utf-8").read()
    chequeo = fuente.split("def _check_payload")[1]
    assert chequeo.index("_no_pii(") < chequeo.index("_text(d, \"comment\")")


def test_A10_todo_caso_cargado_por_la_web_se_etiqueta_OFFICE_y_con_origen_minimo_LIMITACION(env):
    """`import_upload` fija `property_type = "OFFICE"` y una fuente constante: el filtro de población
    objetivo de E44 y el «provenance» no distinguen nada en los casos de la web (un piso residencial
    queda como oficina)."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2, referencia="Departamento de 3 dormitorios en Ñuñoa"))
    caso = camp.get(cid)
    assert caso["property_type"] == "OFFICE" and caso["origin"] == camp.WEB_UPLOAD
    assert caso["source"] == "carga web del piloto (E45)"
    assert all(a["origin_url"].startswith("upload://web/") for a in caso["assets"])


# =============================================================================================
# C · máquina de estados (por HTTP) · transiciones inválidas y repetidas
# =============================================================================================
def _tipos(camp, cid):
    return [e["kind"] for e in camp.events(cid)]


def test_C1_crear_recorrido_valido_y_cada_transicion_invalida_deja_el_registro_intacto(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    # antes de procesar
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "x"}).status_code == 400
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 409
    assert _eval_plano(c, cid).status_code == 409
    assert _eval_ux(c, cid).status_code == 409
    assert _tipos(camp, cid) == []
    # procesar, y procesar de nuevo (ya lanzada / ya hay resultado)
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    assert _tipos(camp, cid) == ["create_started", "pipeline"]
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409
    assert _tipos(camp, cid) == ["create_started", "pipeline"]
    # cerrar exige confirmación explícita
    assert c.post(f"{BASE}/caso/{cid}/cerrar").status_code == 400
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "0"}).status_code == 400
    assert camp._of(cid, "closure") == []
    # antes del reveal no se evalúa
    assert _eval_plano(c, cid).status_code == 409 and _eval_ux(c, cid).status_code == 409
    # cerrar → reveal; cerrar otra vez es idempotente y no agrega eventos
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    n = len(camp.events(cid))
    assert _tipos(camp, cid)[-2:] == ["closure", "reveal"]
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert len(camp.events(cid)) == n
    # tras el cierre no se procesa ni se corrige
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "tarde"}).status_code == 400
    assert len(camp.events(cid)) == n
    # evaluar sí; evaluar de nuevo agrega (historial), no reemplaza
    assert _eval_plano(c, cid).status_code == 303
    assert _eval_plano(c, cid, rating="MALO").status_code == 303
    evs = camp._of(cid, "evaluation")
    assert [e["data"]["rating"] for e in evs] == ["BUENO", "MALO"]
    assert evs[1]["data"]["supersedes_seq"] == evs[0]["seq"] and evs[0]["data"]["supersedes_seq"] is None
    assert camp.status(camp.get(cid)) == camp.COMPLETED


def test_C2_los_singletons_son_inmutables_tambien_por_la_api(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"})
    for kind, data in (("pipeline", {}), ("closure", {"final_run_id": "x"}), ("reveal", {})):
        with pytest.raises(camp.CampaignError, match="inmutable"):
            camp.record(cid, kind, data)


def test_C3_orden_ciego_de_la_api_cierre_antes_de_reveal_y_reveal_antes_de_evaluar(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    for kind in ("closure", "reveal", "evaluation"):
        with pytest.raises(camp.CampaignError):
            camp.record(cid, kind, {"final_run_id": "x"})
    with pytest.raises(camp.CampaignError):
        camp.reveal(cid)                                       # sin cierre no hay reveal
    with pytest.raises(camp.CampaignError):
        camp.close_blind(cid)                                  # sin corrida no hay cierre


def test_C4_mejorar_recorrido_y_transiciones_repetidas(env, planta_lista):
    c, camp, tmp = env
    cid = _cid(_subir_mejorar(c))
    assert _eval_plano(c, cid).status_code == 409 and _eval_ux(c, cid).status_code == 409
    # «dar por no resuelto» antes de procesar no inventa nada
    assert c.post(f"{BASE}/caso/{cid}/sin-resultado").status_code == 303
    assert _tipos(camp, cid) == []
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert _tipos(camp, cid) == ["improve_started", "pipeline"]
    assert len(planta_lista) == 1
    # repetir procesar o dar por no resuelto después del éxito no repite nada
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert c.post(f"{BASE}/caso/{cid}/sin-resultado").status_code == 303
    assert _tipos(camp, cid) == ["improve_started", "pipeline"] and len(planta_lista) == 1
    from webapp import store
    assert store.q1("SELECT COUNT(*) n FROM properties")["n"] == 1
    assert camp.events(cid)[1]["data"]["reached_output"] is True
    # las pistas no se mezclan
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "x"}).status_code == 404
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 404
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404
    with pytest.raises(camp.CampaignError, match="sólo existe en CREAR"):
        camp.record(cid, "closure", {"final_run_id": "x"})


def test_C5_mejorar_sin_planta_lista_queda_en_revision_y_dar_por_no_resuelto_es_definitivo(env, planta_no_lista):
    c, camp, tmp = env
    cid = _cid(_subir_mejorar(c))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert _tipos(camp, cid) == ["improve_started"]            # no hay resultado inventado
    assert "NECESITA REVISIÓN" in _html(c, f"{BASE}/caso/{cid}")
    assert c.post(f"{BASE}/caso/{cid}/sin-resultado").status_code == 303
    p = camp._of(cid, "pipeline")
    assert len(p) == 1 and p[0]["data"]["reached_output"] is False
    assert c.post(f"{BASE}/caso/{cid}/sin-resultado").status_code == 303
    assert len(camp._of(cid, "pipeline")) == 1                 # no se reescribe


@pytest.mark.parametrize("ruta", ["procesar", "corregir", "cerrar", "evaluar/plano", "evaluar/ux",
                                  "sin-resultado"])
@pytest.mark.parametrize("cid", ["e44-cre-zzzzzzzzzz", "e44-imp-0123456789", "..", "e44-cre-0123456789/x",
                                 "E44-IMP-0123456789", "e44-imp-0123456789%00"])
def test_C6_ids_mal_formados_o_inexistentes_dan_404_sin_efectos(env, ruta, cid):
    c, camp, tmp = env
    r = c.post(f"{BASE}/caso/{cid}/{ruta}", data={"confirmo": "1", "texto": "x"})
    assert r.status_code == 404
    assert not os.path.isdir(os.path.join(camp.root(), "cases")) or not os.listdir(
        os.path.join(camp.root(), "cases"))


@pytest.mark.parametrize("campos,codigo", [
    ({"rating": "ESPLENDIDO", "publicaria": "si", "correccion_humana": "no"}, 400),
    ({"rating": "BUENO", "publicaria": "tal vez", "correccion_humana": "no"}, 400),
    ({"rating": "BUENO", "publicaria": "si"}, 400),
    ({"rating": "BUENO", "publicaria": "si", "correccion_humana": "no", "minutos": "abc"}, 400),
    ({"rating": "BUENO", "publicaria": "si", "correccion_humana": "no", "minutos": "nan"}, 400),
    ({"rating": "BUENO", "publicaria": "si", "correccion_humana": "no", "minutos": "-3"}, 400),
    ({"rating": "BUENO", "publicaria": "si", "correccion_humana": "no", "comentario": "x" * 2001}, 400),
    ({"rating": "BUENO", "publicaria": "si", "correccion_humana": "no",
      "comentario": "mi correo es ana@casa.cl"}, 400),
    ({"rating": "BUENO", "publicaria": "si", "correccion_humana": "no",
      "comentario": "<script>alert(1)</script>"}, 303),
])
def test_C7_la_evaluacion_de_plano_valida_cada_campo(env, planta_lista, campos, codigo):
    c, camp, tmp = env
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    r = c.post(f"{BASE}/caso/{cid}/evaluar/plano", data=campos)
    assert r.status_code == codigo
    assert len(camp._of(cid, "evaluation")) == (1 if codigo == 303 else 0)
    if codigo == 303:                                            # el HTML se escapa al mostrarlo
        pagina = _html(c, f"{BASE}/caso/{cid}")
        assert "<script>alert(1)</script>" not in pagina and "&lt;script&gt;" in pagina


_ALFA = ["a", "Z", "ñ", "😀", "‮", "\x00", "\x01", "\x7f", "\n", "\r", "\t", " ", "%", "%00", "<", ">",
         "\"", "'", "&", ";", "\\", "/", "..", "0", "9", "١", "e", "-", "+", ".", ",", "{{7*7}}", "${7*7}",
         "' OR 1=1 --", "�", "http://x.cl/a?b=1"]


def test_C9_fuzz_sembrado_de_los_formularios_del_piloto_no_produce_500_ni_eventos_invalidos(env, planta_lista):
    """500 envíos con basura (NUL, controles, RTL, emoji, inyección, plantillas) a evaluar, corregir,
    cerrar y a las dos altas: ninguna respuesta 5xx, y todo lo que quedó guardado es válido."""
    import random
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    rng = random.Random(46)

    def basura(n=40):
        return "".join(rng.choice(_ALFA) for _ in range(rng.randint(0, n)))
    cid_m = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid_m}/procesar")
    cid_c = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid_c}/procesar")
    c.get(f"{BASE}/caso/{cid_c}")
    codigos = []
    for i in range(300):
        ruta, datos = rng.choice([
            (f"{BASE}/caso/{cid_m}/evaluar/plano", {
                "rating": rng.choice(["BUENO", basura()]), "publicaria": rng.choice(["si", "no", basura(5)]),
                "correccion_humana": rng.choice(["si", "no", basura(5)]), "minutos": basura(12),
                "comentario": basura()}),
            (f"{BASE}/caso/{cid_m}/evaluar/ux", {
                "rating": rng.choice(["MALO", basura()]), "entendi": rng.choice(["si", "no", basura(5)]),
                "comentario": basura(), "sobraba": basura(), "faltaba": basura()}),
            (f"{BASE}/caso/{cid_c}/corregir", {"texto": basura(80)}),
            (f"{BASE}/caso/{cid_c}/cerrar", {"confirmo": rng.choice(["1", "0", basura(4)])}),
            (f"{BASE}/caso/{cid_c}/evaluar/plano", {"rating": "BUENO", "publicaria": "si",
                                                    "correccion_humana": "no", "minutos": basura(6)})])
        codigos.append(c.post(ruta, data=datos).status_code)
    for i in range(100):
        r = c.post(f"{BASE}/crear", data={
            "m2": basura(10), "referencia": basura(60), "fotos": [(__import__("io").BytesIO(_foto(100 + i)), "f.png")],
            "plano_real": (__import__("io").BytesIO(_plano_real() + bytes([i])), "g.png")},
            content_type="multipart/form-data")
        codigos.append(r.status_code)
    assert max(codigos) < 500, sorted(set(codigos))
    for cid in (cid_m, cid_c):                                     # todo lo guardado es legible y válido
        for e in camp.events(cid):
            if e["kind"] in ("evaluation", "ux_evaluation"):
                assert e["data"]["rating"] in camp.RATINGS or e["data"]["rating"] is None
                for k in ("comment", "extra_step_comment", "missing_comment"):
                    assert e["data"].get(k) is None or len(e["data"][k]) <= 2000
    assert camp.summary()["status"] in ("PARTIAL", "BLOCKED", "PASS")


def test_C10_fuzz_sembrado_de_las_rutas_de_E37_que_el_operador_puede_tocar_no_produce_500(env):
    """Las rutas de `/lab/reconstruction/*` siguen vivas para los proyectos de la campaña (H04). 500
    envíos de basura (ids, formularios, archivos, parámetros de consulta) a nuevo/datos/calificar/
    corregir/cierre/comparar/generar/retirar/asset/plano-real: ninguna respuesta 5xx."""
    import io
    import random
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    rng = random.Random(37)
    alfa = _ALFA + ["1e999", "nan", "inf", "-1", "999999999999"]

    def basura(n=30):
        return "".join(rng.choice(alfa) for _ in range(rng.randint(0, n)))
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    c.get(f"{BASE}/caso/{cid}")
    pid = camp.get(cid)["recon_project_id"]
    from webapp.domain.reconstruction import runs
    rid = runs.of_project(pid)[0]["run_id"]
    R = "/lab/reconstruction"
    codigos = []
    for _ in range(500):
        k = rng.choice(["nuevo", "datos", "calificar", "corregir", "cierre", "comparar", "get_p", "generar",
                        "retirar", "asset", "gt"])
        if k == "nuevo":
            r = c.post(f"{R}/nuevo", data={"name": basura(), "total_area_m2": basura(8), "usable_area_m2": basura(8),
                                          "bedrooms": basura(4), "bathrooms": basura(4), "levels": basura(4),
                                          "address_context": basura(), "description": basura(200)})
        elif k == "datos":
            r = c.post(f"{R}/p/{pid}/datos", data={"total_area_m2": basura(8), "bedrooms": basura(4),
                                                    "description": basura(100)})
        elif k == "calificar":
            r = c.post(f"{R}/p/{pid}/r/{rid}/calificar", data={"rating": rng.choice(["BUENO", basura(6)]),
                                                                "comment": basura(100)})
        elif k == "corregir":
            r = c.post(f"{R}/p/{pid}/r/{rid}/corregir", data={"instruction": basura(100),
                                                                "confirm_paid": rng.choice(["1", "0", basura(3)])})
        elif k == "cierre":
            r = c.post(f"{R}/p/{pid}/cierre", data={"verdict": basura(5), "comment": basura(100),
                                                     "minutes": basura(6), "needs_cad": basura(3)})
        elif k == "comparar":
            r = c.get(f"{R}/p/{pid}/comparar", query_string={"r": [rid, basura(12), rid][: rng.randint(0, 3)]})
        elif k == "get_p":
            r = c.get(f"{R}/p/{pid}", query_string={"avisos": basura(3)})
        elif k == "generar":
            r = c.post(f"{R}/p/{pid}/generar", data={"engine_id": basura(12), "confirm_paid": rng.choice(["1", "0"])})
        elif k == "retirar":
            r = c.post(f"{R}/p/{pid}/asset/{basura(10)}/retirar")
        elif k == "asset":
            r = c.get(f"{R}/p/{pid}/asset/{basura(10)}")
        else:
            r = c.post(f"{R}/p/{pid}/plano-real", data={"ground_truth": (
                io.BytesIO(rng.choice([b"", b"x", _foto(3), b"%PDF" + b"x" * 30])),
                rng.choice(["a.png", "b.pdf", "c", "d.exe", basura(8) + ".png"]))}, content_type="multipart/form-data")
        codigos.append(r.status_code)
    assert max(codigos) < 500, sorted(set(codigos))


def test_I1_las_evaluaciones_son_de_solo_insercion_pero_un_archivo_editado_a_mano_no_se_detecta_LIMITACION(env, planta_lista):
    """`record` abre con `'x'` (nunca reescribe) y numera por conteo de archivos, pero no hay hash ni
    cadena: editar `00N_evaluation.json` a mano cambia el resumen sin dejar rastro."""
    c, camp, tmp = env
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    assert _eval_plano(c, cid, rating="PESIMO").status_code == 303
    d = os.path.join(camp.case_dir(cid), "results")
    antes = {n: open(os.path.join(d, n), "rb").read() for n in sorted(os.listdir(d))}
    assert _eval_plano(c, cid, rating="EXCELENTE").status_code == 303   # agregar no toca lo anterior
    assert all(open(os.path.join(d, n), "rb").read() == b for n, b in antes.items())
    # editar a mano el archivo más reciente cambia el resumen sin ninguna señal
    ruta = os.path.join(d, sorted(os.listdir(d))[-1])
    datos = camp.json.load(open(ruta))
    datos["data"]["rating"] = "MALO"
    open(ruta, "w").write(camp.json.dumps(datos))
    assert camp.summary()["tracks"]["IMPROVE"]["ratings"]["MALO"] == 1
    # y `record` lo deja pasar en cualquier momento: no hay candado tras el cierre en la API
    cid2 = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid2}/procesar")
    _html(c, f"{BASE}/caso/{cid2}")
    c.post(f"{BASE}/caso/{cid2}/cerrar", data={"confirmo": "1"})
    camp.record(cid2, "correction", {"run_id": "x", "seq_correction": 99, "prompt": "tarde"})
    assert len(camp._of(cid2, "correction")) == 1                      # la API lo acepta tras el cierre


def test_C8_los_minutos_infinitos_se_aceptan_y_contaminan_el_total_DEFECTO_H12(env, planta_lista):
    c, camp, tmp = env
    cid = _cid(_subir_mejorar(c))
    c.post(f"{BASE}/caso/{cid}/procesar")
    assert _eval_plano(c, cid, minutos="1e999").status_code == 303
    assert camp._of(cid, "evaluation")[0]["data"]["human_minutes"] == float("inf")
    assert camp.summary()["tracks"]["IMPROVE"]["human_minutes"]["total"] == float("inf")


# =============================================================================================
# H · DEMO contra real
# =============================================================================================
def _demo_crear(camp, n=2, sem=0):
    return camp.import_upload(camp.CREATE, [(f"f{i}.png", _foto(80 + sem * 10 + i)) for i in range(n)],
                              ground_truth=("gt.png", _plano_real() + bytes([sem])), demo=True)


def test_H1_un_caso_demo_no_cuenta_en_ningun_n_ni_en_el_resumen_ni_en_las_evaluaciones(env):
    c, camp, tmp = env
    demo = _demo_crear(camp)
    assert camp.get(demo)["demo"] is True
    for t in camp.TRACKS:
        assert camp.count(t)["listed"] == 0 and camp.count(t)["captured"] == 0
    s = camp.summary()
    assert s["status"] == "BLOCKED" and s["tracks"]["CREATE"]["counts"]["listed"] == 0
    # procesarlo, cerrarlo y evaluarlo por la web no mueve nada
    assert c.post(f"{BASE}/caso/{demo}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{demo}")
    assert c.post(f"{BASE}/caso/{demo}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert _eval_plano(c, demo).status_code == 303 and _eval_ux(c, demo).status_code == 303
    assert camp.status(camp.get(demo)) == camp.COMPLETED
    s = camp.summary()
    assert s["status"] == "BLOCKED"
    assert s["tracks"]["CREATE"]["pilot"]["plan_evaluations"] == 0
    assert s["tracks"]["CREATE"]["pilot"]["ux_evaluations"] == 0
    assert s["tracks"]["CREATE"]["counts"]["completed"] == 0


def test_H2_demo_y_real_con_el_mismo_material_conviven_sin_bloquearse(env):
    c, camp, tmp = env
    fotos = [(f"f{i}.png", _foto(90 + i)) for i in range(2)]
    gt = ("gt.png", _plano_real())
    demo = camp.import_upload(camp.CREATE, fotos, ground_truth=gt, demo=True)
    real = camp.import_upload(camp.CREATE, fotos, ground_truth=gt)
    assert demo != real and camp.get(demo)["demo"] and not camp.get(real)["demo"]
    assert camp.count("CREATE")["listed"] == 1
    # y un segundo real igual sí choca (el demo no lo ampara)
    with pytest.raises(camp.CampaignError, match="duplicado"):
        camp.import_upload(camp.CREATE, fotos, ground_truth=gt)


def test_H3_la_web_no_permite_crear_un_demo_ni_cambiar_la_bandera(env):
    c, camp, tmp = env
    r = c.post(f"{BASE}/crear", data={
        "fotos": [(__import__("io").BytesIO(_foto(1)), "a.png")],
        "plano_real": (__import__("io").BytesIO(_plano_real()), "gt.png"),
        "demo": "1", "origin": "WEB_UPLOAD", "track": "IMPROVE"}, content_type="multipart/form-data")
    caso = camp.get(_cid(r))
    assert caso["demo"] is False and caso["track"] == "CREATE"


def test_H4_un_caso_real_no_puede_correr_el_motor_fixture_ni_por_la_api(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    for motor in ("fixture_replay", "fixture", "fixture_x"):
        with pytest.raises(camp.CampaignError):
            camp.start_create(cid, motor, confirm_paid=True)
        with pytest.raises(camp.CampaignError):
            camp.run_create(cid, motor, confirm_paid=True)
    assert _tipos(camp, cid) == []


def test_H5_el_panel_separa_reales_y_demos_pero_el_indice_los_mezcla_sin_rotulo_LIMITACION(env):
    c, camp, tmp = env
    real = _cid(_subir_crear(c, n=2))
    demo = _demo_crear(camp, sem=1)
    panel = _html(c, f"{BASE}/panel")
    assert panel.count(real) >= 1 and panel.count(demo) >= 1
    idx = open(camp.build_index()).read()
    assert demo in idx and real in idx
    assert "DEMO" not in idx.upper().split("</UL>")[1]          # los demos no llevan rótulo en las secciones


def test_H6_el_borde_de_20_mas_20_y_los_demos_no_empujan_el_N(env):
    c, camp, tmp = env
    ev = {"reached_output": True, "errors": [], "fidelity": "OK", "legibility": "OK",
          "publishability": "ALTA", "human_interventions": 0, "needs_cad": False}
    for i in range(20):
        cid = _mejorar_lib(camp, tmp, f"https://example.com/m{i}", _plano_de_galeria() + bytes([i + 1]),
                           nombre=f"m{i}")["accepted"][0]["case_id"]
        camp.record(cid, "pipeline", {"reached_output": True})
        camp.record(cid, "evaluation", ev)
    dims = {k: "BIEN" for k in camp.CREATE_DIMS}

    def crear_completo(i):
        cid = camp.import_upload(camp.CREATE, [(f"f{j}.png", _foto(100 + i * 5 + j)) for j in range(2)],
                                 ground_truth=("g.png", _plano_real() + bytes([i + 1])))
        camp.record(cid, "pipeline", {"status": "DONE"})
        camp.record(cid, "closure", {"final_run_id": "x"})
        camp.record(cid, "reveal", {"project_gt_state": "REVEALED"})
        camp.record(cid, "evaluation", {**dims, "needs_cad": False})
        return cid
    ids = [crear_completo(i) for i in range(19)]
    for sem in range(5):                       # los demos no empujan el N en ninguna dirección
        _demo_crear(camp, sem=10 + sem)
    s = camp.summary()
    assert s["status"] == "PARTIAL"            # 20 + 19
    assert s["tracks"]["IMPROVE"]["counts"]["completed"] == 20
    assert s["tracks"]["CREATE"]["counts"]["completed"] == 19
    ids.append(crear_completo(19))
    assert camp.summary()["status"] == "PASS"  # 20 + 20: el borde exacto
    camp.exclude(ids[0], "motivo")             # excluir uno lo baja otra vez a PARTIAL
    assert camp.summary()["status"] == "PARTIAL"
