"""E48 — auditoría final de readiness pre-piloto (rama acumulada tras E47.11).

Son tests de AUDITORÍA, no de producto: no cambian nada productivo. Dos clases:

* invariantes que SÍ se sostienen (regresión integrada de H01/H02/H03/H05/H10/H16/H20/H21/E47.9, de
  las métricas del experimento y del camino feliz). Si alguno cae, el piloto perdió una garantía;
* caracterización de defectos que SIGUEN abiertos: los llamados `…_DEFECTO_E48_*` afirman el
  comportamiento defectuoso, a propósito, para que el REPORT los cite con una reproducción
  ejecutable. El día que se corrijan, ese test fallará y quien corrija deberá actualizarlo (lo dice
  cada docstring).

Todo es sintético y sin red. Los planos de prueba salen del propio repo (`cases/*/original.png`,
planos de portal ya versionados): ninguno es material de cliente. Sin llamadas pagadas.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import time

import pytest

from test_e37_reconstruction_lab import _foto, _plano_de_galeria, _plano_real
from test_e45_web_pilot import (BASE, _cid, _eval_plano, _eval_ux, _html, _plano,  # noqa: F401
                                _subir_crear, _subir_mejorar, env, planta_lista, planta_no_lista)
from test_e46_adv_resilience import _cliente, _importar, _material

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANO_A = os.path.join(ROOT, "cases", "001_gps_403", "original.png")      # plano de portal, B/N
PLANO_B = os.path.join(ROOT, "cases", "003_res_unknown", "original.png")  # otro plano de portal
FOTO_REAL = None                                                           # se resuelve abajo
for _base in ("matplotlib",):
    try:
        import matplotlib
        FOTO_REAL = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "sample_data",
                                 "grace_hopper.jpg")
    except Exception:                                                      # noqa: BLE001
        FOTO_REAL = None


# =============================================================================================
# transformaciones del plano real (B — ceguera)
# =============================================================================================
def _cv():
    import cv2
    import numpy as np
    return cv2, np


def _jpeg(img, q):
    cv2, _ = _cv()
    return cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1], 1)


def _pad(img, f, color=(255, 255, 255)):
    cv2, _ = _cv()
    p = int(max(img.shape[:2]) * f)
    return cv2.copyMakeBorder(img, p, p, p, p, cv2.BORDER_CONSTANT, value=color)


def _crop(img, f):
    h, w = img.shape[:2]
    return img[int(h * f):h - int(h * f), int(w * f):w - int(w * f)]


def _lado(img, lado):
    cv2, _ = _cv()
    k = lado / max(img.shape[:2])
    return cv2.resize(img, (max(1, int(img.shape[1] * k)), max(1, int(img.shape[0] * k))),
                      interpolation=cv2.INTER_AREA)


def _captura(img):
    """Captura de pantalla: fondo de interfaz, barra superior y el plano escalado dentro."""
    cv2, np = _cv()
    H, W = 900, 1440
    bg = np.full((H, W, 3), (235, 235, 238), np.uint8)
    cv2.rectangle(bg, (0, 0), (W, 70), (60, 60, 64), -1)
    k = min((H - 160) / img.shape[0], (W - 160) / img.shape[1])
    s = cv2.resize(img, (int(img.shape[1] * k), int(img.shape[0] * k)), interpolation=cv2.INTER_AREA)
    bg[100:100 + s.shape[0], 80:80 + s.shape[1]] = s
    return bg


def _perspectiva(img):
    cv2, np = _cv()
    h, w = img.shape[:2]
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]),
                                    np.float32([[w * .06, h * .04], [w * .95, 0], [w, h * .97],
                                                [0, h * .93]]))
    return cv2.warpPerspective(img, M, (w, h), borderValue=(200, 200, 200))


def _con_colores(img):
    """Plano con recintos rellenos de color (como los de muchas galerías): ya no hay «papel»."""
    cv2, np = _cv()
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    n, lab = cv2.connectedComponents((g > 200).astype(np.uint8))
    out = img.copy()
    rng = np.random.RandomState(3)
    for i in range(1, n):
        out[lab == i] = rng.randint(120, 230, 3)
    return out


def _rot(img, k):
    cv2, _ = _cv()
    return cv2.rotate(img, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                            270: cv2.ROTATE_90_COUNTERCLOCKWISE}[k])


#: transformaciones de un plano de papel que HOY se bloquean (por `classify` o por parecido)
BLOQUEADAS = {
    "jpeg_q90": lambda im: _jpeg(im, 90), "jpeg_q40": lambda im: _jpeg(im, 40),
    "mitad": lambda im: _lado(im, max(im.shape[:2]) // 2), "x2": lambda im: _cv()[0].resize(im, None, fx=2, fy=2),
    "rot90": lambda im: _rot(im, 90), "rot180": lambda im: _rot(im, 180), "rot270": lambda im: _rot(im, 270),
    "espejo": lambda im: _cv()[0].flip(im, 1),
    "recorte_3": lambda im: _crop(im, .03), "recorte_8": lambda im: _crop(im, .08),
    "recorte_15": lambda im: _crop(im, .15),
    "borde_blanco_5": lambda im: _pad(im, .05), "borde_blanco_20": lambda im: _pad(im, .2),
    "captura": _captura, "captura_jpeg": lambda im: _jpeg(_captura(im), 70),
    "perspectiva": _perspectiva,
    "grises": lambda im: _cv()[0].cvtColor(_cv()[0].cvtColor(im, _cv()[0].COLOR_BGR2GRAY),
                                           _cv()[0].COLOR_GRAY2BGR),
    "desenfoque": lambda im: _cv()[0].GaussianBlur(im, (0, 0), 3),
}


def _a_disco(tmp_path, img, nombre, ext=".png"):
    cv2, _ = _cv()
    p = str(tmp_path / (nombre + ext))
    assert cv2.imwrite(p, img)
    return p


def _plano_repo(ruta):
    if not os.path.isfile(ruta):
        pytest.skip("falta el plano de portal versionado en cases/")
    cv2, _ = _cv()
    return cv2.imread(ruta, cv2.IMREAD_COLOR)


@pytest.mark.parametrize("ruta", [PLANO_A, PLANO_B], ids=["plano_A", "plano_B"])
@pytest.mark.parametrize("nombre", sorted(BLOQUEADAS))
def test_B1_un_plano_de_papel_transformado_no_pasa_como_foto(tmp_path, ruta, nombre):
    """H01 cerrado para planos de papel: re-codificación, tamaño, giros, recortes, bordes BLANCOS,
    captura y perspectiva se bloquean (por `classify` o por parecido con el plano real)."""
    from webapp import plan_guard
    gt = _plano_repo(ruta)
    gt_path = _a_disco(tmp_path, gt, "gt")
    foto = _a_disco(tmp_path, BLOQUEADAS[nombre](gt), "foto")
    assert plan_guard.motivo_de_rechazo(foto, gt_path) is not None


def test_B1b_el_mismo_archivo_y_la_miniatura_diminuta_tambien_se_bloquean(tmp_path):
    from webapp import plan_guard
    gt = _plano_repo(PLANO_A)
    gt_path = _a_disco(tmp_path, gt, "gt")
    assert plan_guard.motivo_de_rechazo(gt_path, gt_path) is not None
    mini = _a_disco(tmp_path, _lado(gt, 300), "mini")                 # < 200 px de lado menor → «ícono»
    assert plan_guard.motivo_de_rechazo(mini, gt_path) is not None


def test_B2_DEFECTO_E48_B1_un_plano_con_borde_oscuro_o_gris_pasa_como_foto(tmp_path):
    """DEFECTO ABIERTO (hallazgo nuevo E48-B1, `BLOCKS_PILOT`). El borde NO blanco baja la fracción
    de «papel» bajo 0,45 (`classify` lo ve PHOTO) y la proporción cambia más de ±8 % (el parecido ni
    se calcula). Una captura de pantalla de un visor oscuro, o un plano con marco gris, llega al motor.

    Si se corrige (parecido invariante a bordes/recortes, o un clasificador que no dependa del papel
    blanco), este test fallará: actualizarlo."""
    from webapp import plan_guard
    for ruta in (PLANO_A, PLANO_B):
        gt = _plano_repo(ruta)
        gt_path = _a_disco(tmp_path, gt, "gt")
        for color in ((128, 128, 128), (0, 0, 0)):
            foto = _a_disco(tmp_path, _pad(gt, .10, color), "foto")
            if plan_guard.motivo_de_rechazo(foto, gt_path) is None:
                return                                                # al menos un bypass: reproducido
    pytest.fail("ningún borde oscuro/gris llegó al motor: el defecto E48-B1 parece corregido; "
                "actualizar este test y el REPORT")


@pytest.mark.parametrize("nombre", ["rot90", "rot180", "espejo", "recorte_8", "borde_blanco_5",
                                    "captura", "perspectiva"])
def test_B3_DEFECTO_E48_B1_un_plano_coloreado_transformado_pasa_como_foto(tmp_path, nombre):
    """DEFECTO ABIERTO (E48-B1). Cuando el plano real no es «tinta sobre papel blanco» (recintos de
    color, modo oscuro, fondo teñido), `classify` ya no lo reconoce y la única defensa es el parecido
    de miniaturas de 32×32, que exige MISMA proporción y MISMA orientación: cualquier giro, recorte,
    borde o captura lo evade. El mismo archivo re-codificado o reescalado sí se bloquea (B3b)."""
    from webapp import plan_guard
    gt = _con_colores(_plano_repo(PLANO_A))
    gt_path = _a_disco(tmp_path, gt, "gt")
    foto = _a_disco(tmp_path, BLOQUEADAS[nombre](gt), "foto")
    assert plan_guard.motivo_de_rechazo(foto, gt_path) is None


@pytest.mark.parametrize("nombre", ["jpeg_q90", "jpeg_q40", "mitad", "x2", "grises", "desenfoque"])
def test_B3b_un_plano_coloreado_recodificado_o_reescalado_si_se_bloquea(tmp_path, nombre):
    from webapp import plan_guard
    gt = _con_colores(_plano_repo(PLANO_A))
    gt_path = _a_disco(tmp_path, gt, "gt")
    foto = _a_disco(tmp_path, BLOQUEADAS[nombre](gt), "foto")
    assert plan_guard.motivo_de_rechazo(foto, gt_path) is not None


def test_B4_DEFECTO_E48_B1_extremo_a_extremo_el_plano_con_borde_oscuro_llega_a_la_peticion_al_motor(env):
    """La misma brecha, por la web: GT = plano de portal; una «foto» = ese plano con un marco gris.
    Se acepta (303), `blind_audit` da OK y los bytes viajan en la petición que armaría el motor."""
    c, camp, tmp = env
    gt = _plano_repo(PLANO_A)
    cv2, _ = _cv()
    gt_png = cv2.imencode(".png", gt)[1].tobytes()
    marco = cv2.imencode(".png", _pad(gt, .10, (128, 128, 128)))[1].tobytes()
    data = {"fotos": [(io.BytesIO(_foto(0)), "a.png"), (io.BytesIO(marco), "b.png")],
            "plano_real": (io.BytesIO(gt_png), "plano.png")}
    r = c.post(f"{BASE}/crear", data=data, content_type="multipart/form-data")
    assert r.status_code == 303, "el guardia lo bloqueó: E48-B1 parece corregido; actualizar el test"
    cid = _cid(r)
    assert camp.blind_audit(cid) == {"ok": True, "violations": []}
    from webapp.domain.reconstruction import runs
    pid = camp.get(cid)["recon_project_id"]
    rid = runs.create_initial(pid, "motor_de_prueba", "e48", confirm_paid=True)
    req = runs.build_request(runs.get(rid))
    enviados = {hashlib.sha256(im.data).hexdigest() for im in req.images}
    assert hashlib.sha256(marco).hexdigest() in enviados


def test_B5_una_foto_real_no_se_bloquea(tmp_path):
    """Falso positivo: una foto real versionada con matplotlib (única foto real disponible sin red)."""
    from webapp import plan_guard
    if not FOTO_REAL or not os.path.isfile(FOTO_REAL):
        pytest.skip("matplotlib sin sample_data")
    gt_path = _a_disco(tmp_path, _plano_repo(PLANO_A), "gt")
    assert plan_guard.motivo_de_rechazo(FOTO_REAL, gt_path) is None


def test_B5b_fotos_sinteticas_normales_no_se_bloquean(tmp_path):
    from webapp import plan_guard
    cv2, np = _cv()
    gt_path = _a_disco(tmp_path, _plano_repo(PLANO_A), "gt")
    rng = np.random.default_rng(7)
    for i in range(6):
        base = rng.integers(0, 255, size=(30, 40, 3), dtype=np.uint8)
        img = cv2.resize(base, (1200, 900), interpolation=cv2.INTER_CUBIC)
        assert plan_guard.motivo_de_rechazo(_a_disco(tmp_path, img, f"f{i}", ".jpg"), gt_path) is None


def test_B5c_un_rechazo_del_guardia_es_accionable_y_no_deja_rastro_y_se_recupera(env):
    """Si el guardia rechaza una foto (acierto, o un falso positivo que esta auditoría NO pudo
    reproducir con 1 foto real + 6 sintéticas), el operador recibe «Retira esta imagen…», no queda caso,
    proyecto E37 ni evidencia, y volver a cargar sin esa imagen entra: el costo es una recarga."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import projects
    cv2, _ = _cv()
    plano = cv2.imencode(".png", _lado(_plano_repo(PLANO_A), 600))[1].tobytes()
    fotos = [(io.BytesIO(_foto(0)), "a.png"), (io.BytesIO(plano), "sospechosa.png")]
    r = c.post(f"{BASE}/crear", data={"fotos": fotos, "plano_real": (io.BytesIO(_plano_real()), "g.png")},
               content_type="multipart/form-data")
    assert r.status_code == 400 and "Retira" in r.get_data(as_text=True)
    assert camp.load()["cases"] == [] and projects.listing() == []
    assert not os.path.isdir(os.path.join(camp.root(), "cases")) or not os.listdir(os.path.join(camp.root(), "cases"))
    assert _subir_crear(c, n=2).status_code == 303


# =============================================================================================
# B — nada del GT llega al motor ni a ninguna superficie previa al reveal (variantes nuevas)
# =============================================================================================
def _rastros(camp, cid, nombre_gt):
    from webapp import store
    pid = camp.get(cid)["recon_project_id"]
    fila = store.q1("SELECT sha256, stored_name FROM recon_ground_truth WHERE project_id=?", (pid,))
    return [x.lower() for x in (fila["sha256"], fila["stored_name"], os.path.splitext(nombre_gt)[0],
                                "reconstruction_gt", "GT-ESCONDIDO")]


def test_B6_la_peticion_al_motor_no_lleva_nombre_sha_ni_ruta_del_gt_ni_en_la_correccion(env):
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines, runs
    cid = _cid(_subir_crear(c, n=3, gt_nombre="PLANO_SECRETO_9913.png"))
    pid = camp.get(cid)["recon_project_id"]
    marcas = _rastros(camp, cid, "PLANO_SECRETO_9913.png")
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "la cocina va al fondo"}).status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    gt_bytes = _plano_real()
    for r in runs.of_project(pid):
        req = runs.build_request(runs.get(r["run_id"]))
        cuerpo = json.dumps(engines.get("openai_direct").build_body(req), default=str).lower()
        meta = json.dumps({"declared": req.declared, "params": req.params, "instr": req.instruction,
                           "prev": req.previous}, default=str).lower()
        for m in marcas:
            assert m not in meta and m not in cuerpo, m
        assert all(im.data != gt_bytes for im in req.images)


def test_B7_ninguna_via_HTTP_sirve_el_gt_antes_del_reveal(env):
    """GET/HEAD/OPTIONS, mayúsculas, barra final, `..`, doble codificación, Range, ids ajenos."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    pid = camp.get(cid)["recon_project_id"]
    urls = [f"{BASE}/caso/{cid}/archivo/real", f"{BASE}/caso/{cid}/archivo/real/",
            f"{BASE}/caso/{cid}/archivo/REAL", f"{BASE}/caso/{cid}/archivo/%72eal",
            f"{BASE}/caso/{cid}/archivo/..%2freal", f"{BASE}/caso/{cid}/archivo/../real",
            f"{BASE}/caso/{cid}/archivo/foto-0", f"{BASE}/caso/{cid}/archivo/foto-99",
            f"{BASE}/caso/{cid}/archivo/foto-1/../../real", f"/lab/reconstruction/p/{pid}/plano-real",
            f"/lab/reconstruction/p/{pid}/plano-real/", f"/lab/reconstruction/p/{pid}/plano-real.png"]
    for u in urls:
        for metodo in ("GET", "HEAD"):
            r = c.open(u, method=metodo, headers={"Range": "bytes=0-100"})
            assert r.status_code in (404, 405), (metodo, u, r.status_code)
            assert b"GT-ESCONDIDO" not in r.get_data()
    # sólo `foto-1`/`foto-2` se sirven, y son las fotos
    assert c.get(f"{BASE}/caso/{cid}/archivo/foto-1").status_code == 200


def test_B8_correccion_posterior_al_reveal_se_rechaza_en_la_banda(env):
    """Dentro del flujo del piloto no hay forma de corregir tras el reveal: ni por la web ni por la API."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "ya vi el plano"}).status_code == 400
    with pytest.raises(camp.CampaignError):
        camp.correct_create(cid, "ya vi el plano")
    assert camp._of(cid, "correction") == []


def test_B9_DEFECTO_E48_H04_el_reveal_de_E37_por_fuera_no_lo_detecta_la_campania(env):
    """E46-H04 sigue reproduciendo, y es `KNOWN_RISK_ACCEPTABLE`: exige un POST deliberado, con
    confirmación, a una pantalla del laboratorio a la que el piloto no enlaza (el HTML del piloto no
    contiene ninguna ruta de `/lab/reconstruction`). La campaña no lo marca, pero el cierre guarda
    `gt_state_at_closure == REVEALED` y E37 marca la corrida hija. El motor NUNCA recibe el plano real
    (`runs` no importa `groundtruth`): lo que se pierde es la ceguera del OPERADOR."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    for url in ("/", "/panel", f"/caso/{cid}", "/crear", "/mejorar"):
        assert "/lab/reconstruction" not in _html(c, BASE + url)
    pid = camp.get(cid)["recon_project_id"]
    assert c.post(f"/lab/reconstruction/p/{pid}/revelar", data={"confirm": "1"}).status_code == 302
    _html(c, f"{BASE}/caso/{cid}")
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "ahora que lo vi"}).status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    cierre = camp._of(cid, "closure")[-1]["data"]
    assert cierre["gt_state_at_closure"] == "REVEALED"
    s = camp.summary()                                      # la métrica no distingue el caso contaminado
    assert "gt_state_at_closure" not in json.dumps(s)


# =============================================================================================
# C — concurrencia, idempotencia y costo
# =============================================================================================
def _en_hilos(n, fn):
    barrera = threading.Barrier(n, timeout=30)
    out = []

    def go(i):
        barrera.wait()
        try:
            out.append(fn(i))
        except Exception as e:                                         # noqa: BLE001
            out.append(e)
    hs = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    [h.start() for h in hs]
    [h.join() for h in hs]
    return out


def _post_crear(c, fotos, gt):
    cl = _cliente(c)
    data = {"fotos": [(io.BytesIO(b), n) for n, b in fotos], "plano_real": (io.BytesIO(gt[1]), gt[0])}
    return cl.post(f"{BASE}/crear", data=data, content_type="multipart/form-data").status_code


def test_C1_cuatro_envios_identicos_a_la_vez_dejan_un_caso_y_ningun_500(env):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    for ronda in range(4):
        fotos, gt = _material(7000 + ronda)
        codigos = _en_hilos(4, lambda i: _post_crear(c, fotos, gt))
        assert sorted(codigos) == [303, 400, 400, 400], (ronda, codigos)
    casos = camp.load()["cases"]
    assert len(casos) == 4 and all(camp.status(x) == camp.CAPTURED for x in casos)
    assert camp.count("CREATE")["captured"] == 4


def test_C2_seis_cargas_distintas_a_la_vez_conservan_los_seis_casos_y_su_evidencia(env):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    mats = [_material(7100 + i) for i in range(6)]
    codigos = _en_hilos(6, lambda i: _post_crear(c, *mats[i]))
    assert codigos == [303] * 6
    casos = camp.load()["cases"]
    assert len({x["case_id"] for x in casos}) == 6
    for x in casos:
        assert camp.status(x) == camp.CAPTURED and camp.materials_ok(x)
        assert camp.blind_audit(x["case_id"])["ok"]
    from webapp.domain.reconstruction import projects
    assert len(projects.listing()) == 6                                       # ni huérfanos ni de más


def test_C3_carga_y_exclusion_a_la_vez_no_pierden_ni_resucitan_casos(env):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    previo = _importar(camp, semilla=7200)
    mats = [_material(7210 + i) for i in range(3)]

    def accion(i):
        if i == 0:
            camp.exclude(previo, "duplicado de prueba")
            return "excluido"
        return _post_crear(c, *mats[i - 1])
    res = _en_hilos(3, accion)
    assert "excluido" in res and not [r for r in res if isinstance(r, Exception)], res
    assert camp.status(camp.get(previo)) == camp.EXCLUDED
    assert len(camp.load()["cases"]) == 3                                     # el previo + 2 nuevos
    n = camp.count("CREATE")
    assert (n["excluded"], n["captured"]) == (1, 2)


def test_C4_doble_procesar_de_MEJORAR_publica_una_vez(env, planta_lista):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    for k in range(4):
        cid = _cid(_subir_mejorar(c, _plano_unico(k)))
        antes = len(planta_lista)
        cods = _en_hilos(2, lambda i: _cliente(c).post(f"{BASE}/caso/{cid}/procesar").status_code)
        # invariante de COSTO: nunca más de una publicación ni de una propiedad. Un 500 espurio es posible (otra
        # petición lee un evento mientras el ganador lo escribe, E46-H17) y no es un segundo lanzamiento.
        assert 303 in cods or 500 in cods, cods
        assert len(planta_lista) - antes <= 1, "se publicó más de una vez (llamada duplicada)"
        assert len(camp._of(cid, "improve_started")) <= 1 and len(camp._of(cid, "pipeline")) <= 1


def _plano_unico(k):
    cv2, np = _cv()
    img = cv2.imdecode(np.frombuffer(_plano_de_galeria(), np.uint8), cv2.IMREAD_COLOR)
    cv2.line(img, (30 + k * 7, 5), (30 + k * 7, 15), (10, 10, 10), 3)
    return cv2.imencode(".png", img)[1].tobytes()


def test_C5_doble_corregir_a_la_vez_lanza_una_sola_correccion(env, monkeypatch):
    c, camp, tmp = env
    from webapp.domain.reconstruction import runs
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    llamadas = []
    real = runs.create_correction
    monkeypatch.setattr(runs, "create_correction", lambda *a, **k: (llamadas.append(1), real(*a, **k))[1])
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)                     # la corrida queda en curso
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    cods = _en_hilos(3, lambda i: _cliente(c).post(f"{BASE}/caso/{cid}/corregir",
                                                   data={"texto": "mover la pared"}).status_code)
    # invariante de COSTO: a lo sumo una corrida hija (un 500 espurio por H17 no es un segundo lanzamiento)
    assert sorted(cods).count(303) <= 1 and set(cods) <= {303, 400, 500}, cods
    assert len(llamadas) <= 1 and len(camp._of(cid, "correction_started")) <= 1
    assert sorted(cods).count(303) == len(llamadas)                            # un 303 ⇔ una corrida


def _espiar_create_initial(monkeypatch):
    from webapp.domain.reconstruction import runs
    creadas = []
    real = runs.create_initial
    monkeypatch.setattr(runs, "create_initial", lambda *a, **k: (creadas.append(1), real(*a, **k))[1])
    return creadas


def test_C6_FAILED_asentado_mas_POST_en_el_MISMO_estado_lanza_exactamente_un_reintento(env, monkeypatch):
    """El reclamo `O_EXCL` funciona cuando las peticiones calculan su nombre sobre el mismo estado
    (barrera en `_create_claim_name`): un solo reintento. El defecto está en cuando NO es el mismo
    estado: ver C11. El FAILED se asienta antes: con `settle` simultáneo la barrera se rompe por H17
    (un lector ve un evento a medio escribir y esa petición cae con 500 antes de llegar a la barrera)."""
    c, camp, tmp = env
    from webapp import store
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)
    cid = _cid(_subir_crear(c, n=2))
    camp.start_create(cid, "motor_de_prueba", confirm_paid=True)
    store.reset_orphans()                                                      # intento 1 → FAILED
    camp.settle(cid)
    creadas = _espiar_create_initial(monkeypatch)
    real_name = camp._create_claim_name
    barrera = threading.Barrier(4, timeout=20)

    def en_barrera(case_id):
        n = real_name(case_id)
        barrera.wait()                                                         # los 4 ya calcularon el mismo nombre
        return n
    monkeypatch.setattr(camp, "_create_claim_name", en_barrera)
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    cods = _en_hilos(4, lambda i: _cliente(c).post(f"{BASE}/caso/{cid}/procesar").status_code)
    # invariante de COSTO: una sola corrida y un solo 303. Un 500 espurio es posible: otra petición lee un
    # evento mientras el ganador lo escribe (`JSONDecodeError`, E46-H17), no un segundo lanzamiento.
    assert len(creadas) == 1 and cods.count(303) <= 1 and set(cods) <= {303, 409, 500}, (creadas, cods)
    pip = camp._of(cid, "pipeline")                 # (H17 puede asentar el mismo FAILED dos veces: misma corrida)
    assert {p["data"]["status"] for p in pip} == {"FAILED"} and len({p["data"]["run_id"] for p in pip}) == 1
    assert camp.count("CREATE")["executed"] == 0


def _forzar_ventana_del_nombre(camp, monkeypatch):
    """Intercala dos PROCESAR de forma determinista: el 2.º pasa la guardia («¿ya lanzada?») ANTES de que
    el 1.º registre `create_started`, y calcula el nombre de su reclamo DESPUÉS. Es el intercalado que
    produce, sin ayuda, un doble toque cuando la guardia tarda (sha256 de toda la evidencia)."""
    real_name, real_record = camp._create_claim_name, camp.record
    primero_en_nombre, segundo_llego, registrado = threading.Event(), threading.Event(), threading.Event()
    orden, candado = [], threading.Lock()

    def nombre(case_id):
        with candado:
            primero = not orden
            orden.append(1)
        if primero:
            primero_en_nombre.set()
            segundo_llego.wait(20)                       # el 2.º ya pasó su guardia
            return real_name(case_id)
        segundo_llego.set()
        registrado.wait(20)                              # el 1.º ya registró `create_started`
        return real_name(case_id)

    def record(case_id, kind, data):
        r = real_record(case_id, kind, data)
        if kind == "create_started":
            registrado.set()
        return r
    monkeypatch.setattr(camp, "_create_claim_name", nombre)
    monkeypatch.setattr(camp, "record", record)
    return primero_en_nombre


def _dos_procesar_intercalados(c, cid, primero_en_nombre):
    cods = []

    def post():
        cods.append(_cliente(c).post(f"{BASE}/caso/{cid}/procesar").status_code)
    w = threading.Thread(target=post)
    w.start()
    assert primero_en_nombre.wait(20)
    d = threading.Thread(target=post)
    d.start()
    w.join()
    d.join()
    return sorted(cods)


def test_C11_DEFECTO_E48_C1_doble_PROCESAR_intercalado_lanza_DOS_corridas_pagadas(env, monkeypatch):
    """DEFECTO ABIERTO, `BLOCKS_PILOT` (E48-C1): E46-H03 NO quedó cerrado para el doble toque real.
    Desde E47.8 el nombre del reclamo (`create`, `create_2`, …) se calcula a partir de los eventos
    (`_create_claim_name`), y se calcula DESPUÉS de la guardia «¿ya lanzada?». Si el 1.er PROCESAR
    registra `create_started` entre la guardia y el cálculo del nombre del 2.º, el 2.º obtiene un
    nombre libre (`create_2`) y lanza OTRA corrida: dos `create_initial`, dos `create_started`, dos 303.

    La ventana ya no es de ≤ 5 ms: la guardia incluye `status()`, que recalcula el sha256 de TODA la
    evidencia en cada llamada (≈ 65 ms con 87 MB), y `record` lo repite. Medido en la auditoría con 20
    fotos de 12 MP (87 MB): dos POST separados 100 ms → 2 corridas. Ver C11b.

    Si se corrige (nombre del reclamo independiente del estado, o candado por caso), actualizar el test."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)                     # la corrida queda en curso
    cid = _cid(_subir_crear(c, n=2))
    creadas = _espiar_create_initial(monkeypatch)
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    cods = _dos_procesar_intercalados(c, cid, _forzar_ventana_del_nombre(camp, monkeypatch))
    assert len(creadas) == 2 and cods == [303, 303], (
        "ya no se duplica: E48-C1 parece corregido; actualizar el test", creadas, cods)
    assert len(camp._of(cid, "create_started")) == 2                           # dos corridas pagables


def test_C11a_DEFECTO_E48_C1_el_mismo_defecto_en_el_reintento_tras_FAILED(env, monkeypatch):
    """El reintento («VOLVER A INTENTAR») sufre lo mismo: FAILED sin asentar + dos POST intercalados."""
    c, camp, tmp = env
    from webapp import store
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)
    cid = _cid(_subir_crear(c, n=2))
    camp.start_create(cid, "motor_de_prueba", confirm_paid=True)
    store.reset_orphans()
    camp.settle(cid)                                                           # intento 1 asentado como FAILED
    creadas = _espiar_create_initial(monkeypatch)
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    cods = _dos_procesar_intercalados(c, cid, _forzar_ventana_del_nombre(camp, monkeypatch))
    assert len(creadas) == 2 and cods == [303, 303], (creadas, cods)


def test_C11b_DEFECTO_E48_C1_con_evidencia_realista_dos_POST_a_decenas_de_ms_pagan_dos_veces(env, monkeypatch):
    """Sin ganchos de intercalado: se emula el costo de `status()` con una evidencia grande (≈ 60 ms por
    llamada: 20 fotos de 12 MP pesan ≈ 87 MB y E48 midió 65 ms) y se barre la separación entre dos POST.
    Hay una banda de separaciones —del orden de un doble toque de una persona— donde se lanzan dos
    corridas. (Medición directa con 87 MB reales: 2 corridas a 100 ms; 1 a 0, 10, 30, 60, 200 y 400 ms.)"""
    c, camp, tmp = env
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)
    real_ok = camp.materials_ok

    def lento(case):
        time.sleep(0.06)
        return real_ok(case)
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    dobles, intentos = [], []
    for delta in (0, 20, 40, 60, 80, 100, 120, 140, 160, 200, 260):
        fotos, gt = _material(9000 + delta)
        cid = camp.import_upload(camp.CREATE, fotos, ground_truth=gt)
        monkeypatch.setattr(camp, "materials_ok", lento)
        creadas = _espiar_create_initial(monkeypatch)
        cods = []

        def post(espera, cods=cods, cid=cid):
            time.sleep(espera)
            cods.append(_cliente(c).post(f"{BASE}/caso/{cid}/procesar").status_code)
        hs = [threading.Thread(target=post, args=(0,)), threading.Thread(target=post, args=(delta / 1000,))]
        [h.start() for h in hs]
        [h.join() for h in hs]
        monkeypatch.setattr(camp, "materials_ok", real_ok)
        intentos.append((delta, len(creadas), sorted(cods)))
        if len(creadas) >= 2:
            dobles.append(delta)
        assert not [x for x in cods if x >= 500], (delta, cods)
    print("C11b (separación ms, create_initial, códigos):", intentos)
    assert dobles, ("ninguna separación produjo dos corridas: E48-C1 parece corregido o no se "
                    "reprodujo en esta máquina", intentos)


def test_C7_DONE_sin_asentar_mas_POST_no_lanza_otra_corrida(env, monkeypatch):
    c, camp, tmp = env
    from webapp.domain.reconstruction import runs
    cid = _cid(_subir_crear(c, n=2))
    llamadas = []
    real = runs.create_initial
    monkeypatch.setattr(runs, "create_initial", lambda *a, **k: (llamadas.append(1), real(*a, **k))[1])
    camp.start_create(cid, "motor_de_prueba", confirm_paid=True)               # cola sincrónica: DONE sin asentar
    assert not camp._of(cid, "pipeline")
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    cods = _en_hilos(3, lambda i: _cliente(c).post(f"{BASE}/caso/{cid}/procesar").status_code)
    # invariante de COSTO: ninguna corrida nueva. Un 500 intermitente es posible aquí: son los `settle`
    # simultáneos del mismo DONE (E46-H17, ver C8/C9), no un lanzamiento: nunca hay un 303.
    assert len(llamadas) == 1 and all(x in (409, 500) for x in cods), (llamadas, cods)
    pip = camp._of(cid, "pipeline")
    # el mismo H17 puede dejar el DONE asentado dos veces (misma corrida): el N no se mueve
    assert pip and {p["data"]["status"] for p in pip} == {"DONE"}
    assert len({p["data"]["run_id"] for p in pip}) == 1
    assert camp.count("CREATE")["executed"] == 1 and camp.count("CREATE")["captured"] == 1


def test_C8_DEFECTO_E48_H17_settle_simultaneo_duplica_la_correccion_y_infla_los_prompts_humanos(env, monkeypatch):
    """DEFECTO ABIERTO (E46-H17 sigue sin cerrar; aquí con consecuencia sobre la métrica).
    `settle` decide «¿ya está asentada esta corrida?» y después `record` escribe; sin candado,
    dos peticiones que ven la corrida terminada a la vez asientan DOS eventos `correction` con el
    mismo `run_id` (`record` no tiene guarda de unicidad para `correction`). `summary()` cuenta
    `human_prompts` con esos eventos: «cuántos prompts humanos requirió el caso» —métrica pedida por E44—
    sale inflada, y la página del caso muestra la instrucción dos veces. El ventana se fuerza con una
    barrera en la entrada de `record`; en estrés natural con 2 hilos, 26 de 40 correcciones se duplicaron.

    Si se corrige (candado por caso en `settle`/`record`), actualizar este test."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    camp.start_correction(cid, "mover la pared", confirm_paid=True)            # cola sincrónica: DONE sin asentar
    real = camp.record
    barrera = threading.Barrier(2, timeout=20)
    primero_listo = threading.Event()
    llegadas, candado = [], threading.Lock()

    def sincronizado(case_id, kind, data):
        if kind != "correction":
            return real(case_id, kind, data)
        with candado:
            orden = len(llegadas)
            llegadas.append(1)
        barrera.wait()                                   # las dos ya pasaron la comprobación de `settle`
        if orden == 0:
            try:
                return real(case_id, kind, data)
            finally:
                primero_listo.set()
        primero_listo.wait(20)                           # la 2.ª escribe cuando la 1.ª ya escribió
        return real(case_id, kind, data)
    monkeypatch.setattr(camp, "record", sincronizado)
    res = _en_hilos(2, lambda i: camp.settle(cid))
    monkeypatch.setattr(camp, "record", real)
    corr = camp._of(cid, "correction")
    assert len(corr) == 2 and corr[0]["data"]["run_id"] == corr[1]["data"]["run_id"], (
        "ya no se duplica: E46-H17 parece corregido; actualizar el test", res)
    # y la métrica sale inflada: una sola corrección pedida, dos contadas
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert _eval_plano(c, cid).status_code == 303
    assert camp.summary()["tracks"]["CREATE"]["human_prompts"] == 2


def test_C8b_natural_dos_settle_simultaneos_sin_ninguna_sincronizacion_duplican_correcciones(env):
    """Medición NATURAL de H17 (sin barrera propia salvo la de arranque): 2 hilos llaman `settle` a la
    vez sobre 25 correcciones recién terminadas. En la medición de la auditoría (2 hilos, 40 rondas)
    se asentaron 66 eventos para 40 correcciones (26 duplicadas); con 8 hilos, 248 para 40. Se omite
    si en esta máquina la carrera no se reproduce (como `F1b` de E46)."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    errores = 0
    for r in range(25):
        camp.start_correction(cid, f"mover pared {r}", confirm_paid=True)       # DONE sin asentar
        res = _en_hilos(2, lambda i: camp.settle(cid))
        errores += sum(isinstance(x, Exception) for x in res)
    corr = camp._of(cid, "correction")
    if len(corr) == 25 and not errores:
        pytest.skip("la carrera no se reprodujo en esta máquina")
    assert len(corr) >= 25                                  # nunca se pierde una; sobran o fallan en la ventana


def test_C9_DEFECTO_E48_H17_settle_simultaneo_del_intento_inicial_falla_o_duplica(env, monkeypatch):
    """Mismo defecto para `pipeline`: la ventana entre las comprobaciones de `record` y la escritura
    deja que dos `settle` simultáneos del mismo DONE escriban (dos archivos, mismo `run_id`) o que el
    perdedor reciba `FileExistsError` (500 en esa petición; la siguiente ya ve el caso asentado)."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    camp.start_create(cid, "motor_de_prueba", confirm_paid=True)               # DONE sin asentar
    real = camp._check_payload
    barrera = threading.Barrier(2, timeout=20)

    def sincronizado(track, kind, d):
        real(track, kind, d)
        if kind == "pipeline":
            barrera.wait()                                                     # ambas ya pasaron las comprobaciones
    monkeypatch.setattr(camp, "_check_payload", sincronizado)
    res = _en_hilos(2, lambda i: camp.settle(cid))
    monkeypatch.setattr(camp, "_check_payload", real)
    errores = [r for r in res if isinstance(r, Exception)]
    pipes = camp._of(cid, "pipeline")
    assert errores or len(pipes) != 1, "ya no hay carrera: actualizar el test"
    assert all(isinstance(e, FileExistsError) for e in errores)
    assert camp.count("CREATE")["executed"] == 1                               # el N no se contamina


def test_C10_DEFECTO_E48_doble_toque_en_CERRAR_puede_dejar_dos_cierres(env):
    """LOW / `KNOWN_RISK_ACCEPTABLE`: «los singletons son inmutables» tiene la misma ventana. Dos POST
    simultáneos de CERRAR pueden dejar dos eventos `closure` iguales (o un 500 en uno de ellos). Los
    contadores y el estado no cambian (se derivan de «existe»)."""
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    peor = 0
    for r in range(12):
        fotos, gt = _material(7300 + r)
        cid = _cid(c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(b), n) for n, b in fotos],
                                                 "plano_real": (io.BytesIO(gt[1]), gt[0])},
                          content_type="multipart/form-data"))
        c.post(f"{BASE}/caso/{cid}/procesar")
        _html(c, f"{BASE}/caso/{cid}")
        _en_hilos(2, lambda i: _cliente(c).post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code)
        peor = max(peor, len(camp._of(cid, "closure")))
        assert camp.status(camp.get(cid)) == camp.EXECUTED
    assert peor >= 1                                                           # (≥ 2 en ≈ 15 % de las rondas)
    assert camp.count("CREATE")["executed"] == 12 and camp.count("CREATE")["completed"] == 0


# =============================================================================================
# D — fallos, reinicios y corrupción
# =============================================================================================
def test_D1_un_evento_vacio_tumba_el_panel_y_la_UI_no_ofrece_recuperacion(env):
    """E46-H06 sigue abierto. Un evento de 0 bytes (corte entre `open('x')` y `json.dump`) da 500 en
    la portada, el panel y el caso, y `summary()`/`count()` fallan para TODOS los casos. Ninguna ruta
    del piloto permite repararlo ni excluir un caso (la exclusión existe sólo como API/CLI): hay que
    borrar el archivo a mano en el volumen. Clasificación: `KNOWN_RISK_ACCEPTABLE` (ver REPORT)."""
    c, camp, tmp = env
    ok = _cid(_subir_crear(c, n=2))
    otro = _importar(camp, semilla=7400)
    d = os.path.join(camp.case_dir(ok), "results")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "001_blocked.json"), "w").close()
    for url in ("/", "/panel", f"/caso/{ok}"):
        assert c.get(BASE + url).status_code == 500, url
    with pytest.raises(ValueError):
        camp.summary()
    reglas = {r.rule for r in c.application.url_map.iter_rules() if r.rule.startswith(BASE)}
    assert not [r for r in reglas if any(p in r for p in ("excluir", "exclude", "reparar", "borrar"))]
    os.remove(os.path.join(d, "001_blocked.json"))
    assert c.get(BASE + "/panel").status_code == 200 and otro


def test_D2_fallo_del_manifiesto_no_pierde_casos_aceptados_ni_borra_evidencia_ajena(env, monkeypatch):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    previo = _cid(_subir_crear(c, n=2))
    evid = sorted(os.listdir(os.path.join(camp.case_dir(previo), "evidence")))
    real = camp._save
    monkeypatch.setattr(camp, "_save", lambda m: (_ for _ in ()).throw(OSError("disco lleno")))
    fotos, gt = _material(7500)
    assert _post_crear(c, fotos, gt) == 500
    monkeypatch.setattr(camp, "_save", real)
    assert [x["case_id"] for x in camp.load()["cases"]] == [previo]            # nada a medias en el manifiesto
    assert sorted(os.listdir(os.path.join(camp.case_dir(previo), "evidence"))) == evid
    assert camp.status(camp.get(previo)) == camp.CAPTURED
    # recuperación: el 1.er reintento falla (evidencia 0444 del intento muerto, E46-H08), el 2.º entra
    codigos = [_post_crear(c, fotos, gt) for _ in range(3)]
    assert 303 in codigos and len(camp.load()["cases"]) == 2, codigos


def test_D3_caida_entre_reclamo_y_create_started_deja_el_caso_atascado_sin_gasto_y_con_salida(env, monkeypatch):
    """Si el proceso muere (o `record` falla) DESPUÉS de crear la corrida y ANTES de `create_started`,
    el reclamo `O_EXCL` queda tomado: el caso responde «ya fue lanzada» para siempre y la UI no ofrece
    salida. NO hay gasto (la corrida no llegó a la cola) y se sale con `exclude` + recarga (H20), pero
    `exclude` sólo existe como API/CLI. Ventana de milisegundos: `KNOWN_RISK_ACCEPTABLE`."""
    c, camp, tmp = env
    from webapp import store
    from webapp.domain.reconstruction import runs
    cid = _cid(_subir_crear(c, n=2))
    encoladas = []
    monkeypatch.setattr(runs, "enqueue", lambda rid: encoladas.append(rid))
    real = camp.record

    def falla(case_id, kind, data):
        if kind == "create_started":
            raise OSError("disco lleno")
        return real(case_id, kind, data)
    monkeypatch.setattr(camp, "record", falla)
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 500
    monkeypatch.setattr(camp, "record", real)
    assert encoladas == []                                                     # nada se envió al proveedor
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409            # atascado
    store.reset_orphans()
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409
    n0 = camp.count("CREATE")
    assert (n0["captured"], n0["executed"]) == (1, 0)                          # no consumió N
    camp.exclude(cid, "atascado por caída")                                    # salida: API/CLI
    fotos, gt = _material(7600)
    nuevo = camp.import_upload(camp.CREATE, fotos, ground_truth=gt)
    assert camp.status(camp.get(nuevo)) == camp.CAPTURED and nuevo != cid


def test_D4_error_hostil_del_proveedor_no_rompe_panel_ni_filtra_secretos_y_se_reintenta(env, monkeypatch):
    """H21 integrado: un mensaje con ruta, URL, email, clave y bearer con forma de credencial, racha
    de dígitos, NUL y saltos de línea se sanea antes de persistirse; el panel y el caso siguen
    abriendo, el intento FAILED no consume N y el reintento llega a DONE una sola vez."""
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture
    fallos = [1]
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ZZZ-CLAVE-REAL-0005")       # la del entorno: `sanitize` la enmascara
    HOSTIL = ("clave sk-ZZZ-CLAVE-REAL-0005 rechazada; ""req 1700000000123 en /home/runner/work/escalimetro/.data/x.png "
              "https://api.example.com/v1?key=ZZZ-SECRET-0001 ops@example.com tel +56 9 8765 4321 "
              "Authorization: Bearer ZZZ-TOKEN-0002 api_key=ZZZ-KEY-0003\x00\n\r" + "q" * 400)

    class Hostil(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

        def reconstruct(self, req):
            if fallos[0]:
                fallos[0] -= 1
                raise engines.EngineError("PROVIDER_ERROR", HOSTIL)
            return super().reconstruct(req)
    engines.register(Hostil())
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    for url in (f"/caso/{cid}", "/panel", "/"):
        assert c.get(BASE + url).status_code == 200, url
    p = camp._of(cid, "pipeline")[0]["data"]
    assert p["status"] == "FAILED"
    n = camp.count("CREATE")
    assert (n["captured"], n["executed"], n["completed"]) == (1, 0, 0)
    archivos = _archivos(tmp / "data")
    for ruta, texto in archivos.items():
        # la clave REAL del entorno no está en ningún lado, ni en la base (la enmascara `sanitize`)
        assert "ZZZ-CLAVE-REAL-0005" not in texto, ruta
        if ".db" in ruta:
            continue                  # la bitácora E37 guarda el error del proveedor (sólo lo ve el operador)
        # lo que la CAMPAÑA persiste (eventos, manifiesto, índice) va saneado
        for marca in ("ZZZ-SECRET-0001", "ZZZ-TOKEN-0002", "ZZZ-KEY-0003", "1700000000123",
                      "ops@example.com", "8765 4321", "/home/runner"):
            assert marca not in texto, (marca, ruta)
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    assert [x["data"]["status"] for x in camp._of(cid, "pipeline")] == ["FAILED", "DONE"]
    n = camp.count("CREATE")
    assert (n["executed"], n["completed"]) == (1, 0)


def _archivos(raiz):
    out = {}
    for d, _s, fs in os.walk(str(raiz)):
        for f in fs:
            p = os.path.join(d, f)
            try:
                out[os.path.relpath(p, str(raiz))] = open(p, "rb").read().decode("latin-1")
            except OSError:
                pass
    return out


def test_D5_el_error_de_MEJORAR_con_PDF_roto_no_da_409_ni_deja_huerfanas(env):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    for k in range(5):
        r = _subir_mejorar(c, b"%PDF-1.4\n" + bytes([k]) * 50 + b"\n%%EOF", "plano.pdf")
        assert r.status_code in (303, 400)
        if r.status_code == 303:
            cid = _cid(r)
            assert c.post(f"{BASE}/caso/{cid}/procesar").status_code in (303, 409)
            assert c.get(f"{BASE}/caso/{cid}").status_code == 200
    assert c.get(BASE + "/panel").status_code == 200 and c.get(BASE + "/").status_code == 200


def test_D6_reinicio_con_corrida_en_curso_FAILED_reintento_DONE_historial_inmutable(env, monkeypatch):
    c, camp, tmp = env
    from webapp import store
    from webapp.domain.reconstruction import runs
    monkeypatch.setattr(runs, "enqueue", lambda rid: None)
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303            # intento 1 en curso
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 409
    store.reset_orphans()                                                      # redeploy
    _html(c, f"{BASE}/caso/{cid}")
    primero = json.dumps(camp._of(cid, "pipeline")[0], sort_keys=True)
    monkeypatch.setattr(runs, "enqueue", lambda rid: runs.execute(rid))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    pip = camp._of(cid, "pipeline")
    assert [x["data"]["status"] for x in pip] == ["FAILED", "DONE"]
    assert json.dumps(pip[0], sort_keys=True) == primero                       # inmutable
    assert camp.count("CREATE")["executed"] == 1


# =============================================================================================
# E — cargas, móvil y recursos
# =============================================================================================
def _jpeg_12mp(semilla):
    cv2, np = _cv()
    rng = np.random.default_rng(semilla)
    base = rng.integers(0, 255, size=(75, 100, 3), dtype=np.uint8)
    img = cv2.resize(base, (4000, 3000), interpolation=cv2.INTER_CUBIC).astype(np.int16)
    img += rng.integers(-18, 18, size=img.shape, dtype=np.int16)
    return cv2.imencode(".jpg", np.clip(img, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


def test_E1_veinte_fotos_de_12_MP_entran_en_tiempo_acotado_H16_cerrado(env):
    """Una carga CREAR realista (20 fotos de 4000×3000 ≈ 3–6 MB cada una, dentro de los límites)
    por la web. E46 medía 217 s con 12 MP; con E47.7 debe ser un orden de magnitud menos."""
    c, camp, tmp = env
    fotos = [(io.BytesIO(_jpeg_12mp(i)), f"IMG_{i:04d}.jpg") for i in range(20)]
    peso = sum(len(b.getvalue()) for b, _ in fotos)
    assert peso < 120 * 1024 * 1024
    t0 = time.time()
    r = c.post(f"{BASE}/crear", data={"fotos": fotos, "plano_real": (io.BytesIO(_plano_real()), "gt.png")},
               content_type="multipart/form-data")
    dt = time.time() - t0
    assert r.status_code == 303, r.get_data(as_text=True)[:300]
    assert dt < 60, f"20 fotos de 12 MP tardaron {dt:.1f} s (presupuesto 60 s; E46: 217 s)"
    cid = _cid(r)
    assert camp.status(camp.get(cid)) == camp.CAPTURED and camp.blind_audit(cid)["ok"]


def test_E2_limites_documentados_se_rechazan_antes_de_crear_nada(env):
    c, camp, tmp = env
    fotos21 = [(io.BytesIO(_foto(i)), f"f{i}.png") for i in range(21)]
    r = c.post(f"{BASE}/crear", data={"fotos": fotos21, "plano_real": (io.BytesIO(_plano_real()), "g.png")},
               content_type="multipart/form-data")
    assert r.status_code == 400
    r = c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(b"x" * (15 * 1024 * 1024 + 1)), "f.jpg")],
                                      "plano_real": (io.BytesIO(_plano_real()), "g.png")},
               content_type="multipart/form-data")
    assert r.status_code == 400
    for nombre, blob in (("f.heic", b"no soy heic"), ("f.gif", b"GIF89a"), ("f.png", b"\x89PNG\r\n\x1a\n" + b"0" * 30)):
        r = c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(blob), nombre)],
                                          "plano_real": (io.BytesIO(_plano_real()), "g.png")},
                   content_type="multipart/form-data")
        assert r.status_code == 400, nombre
    assert camp.load()["cases"] == []
    from webapp.domain.reconstruction import projects
    assert projects.listing() == []


def test_E3_bomba_de_descompresion_pequena_se_rechaza_sin_decodificar(env):
    """Un PNG de 20 000×20 000 (400 Mpx, pocos KB) se rechaza por cabecera antes de decodificar
    (límite 80 Mpx / 12 000 px). NO se ejecuta nada capaz de agotar memoria."""
    import struct
    import zlib
    c, camp, tmp = env

    def png_declarado(w, h):
        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"\x00" * 64)) + chunk(b"IEND", b""))
    r = c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(png_declarado(20000, 20000)), "b.png")],
                                      "plano_real": (io.BytesIO(_plano_real()), "g.png")},
               content_type="multipart/form-data")
    assert r.status_code == 400 and camp.load()["cases"] == []


def test_E4_LIMITACION_MEJORAR_no_acota_los_pixeles_del_plano_H07_y_H19(env):
    """E46-H07/H19 siguen abiertos en MEJORAR (`campaign.import_upload` no llama a `validar_plano`).
    Por código: la lectura usa `f.read()` con el tope de 40 MB y `intake.sniff_ok` mira 8 bytes; no hay
    tope de píxeles antes de `cv2.imread` (PNG/JPG; el PDF sí se rasteriza con tope). Un plano de
    portal (≤ 4 000 px, ≤ 16 Mpx) cuesta decenas de MB; sólo un escaneo de ≥ 20 000 px o material
    fabricado exige GB. Se verifica la AUSENCIA del tope sin ejecutar nada pesado: una cabecera PNG
    que declara 20 000 × 20 000 y no decodifica entra a la fase de preparación en vez de rechazarse
    en la carga. `KNOWN_RISK_ACCEPTABLE` para el piloto (planos de portal), con mitigación operativa."""
    import struct
    import zlib
    c, camp, tmp = env

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 20000, 20000, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"\x00" * 64)) + chunk(b"IEND", b""))
    r = _subir_mejorar(c, png, "gigante.png")
    assert r.status_code == 303                       # se acepta en la carga: no hay tope de píxeles (CREAR sí lo tiene)


# =============================================================================================
# F — superficie del panel
# =============================================================================================
def _rutas_post(app):
    return sorted((r for r in app.url_map.iter_rules() if "POST" in r.methods), key=lambda r: r.rule)


def _relleno(rule):
    import re
    r = re.sub(r"<any\(([^,)]+)[^)]*\):\w+>", r"\1", rule.rule)    # `<any(a, b):seccion>` → `a`
    return re.sub(r"<[^<>]*>", "x1", r)


def test_F1_todo_POST_con_origen_ajeno_da_403_salvo_la_excepcion_publica(env):
    c, camp, tmp = env
    app = c.application
    cl = app.test_client()
    ajenos = [{"Origin": "http://evil.example"}, {"Origin": "null"}, {"Referer": "http://evil.example/x"},
              {"Origin": "http://localhost:81"}, {"Origin": "https://localhost"},
              {"Origin": "http://localhost.evil.example"}]
    rutas = _rutas_post(app)
    assert len(rutas) > 50
    for regla in rutas:
        url = _relleno(regla)
        for h in ajenos:
            r = cl.post(url, headers=h)
            if regla.rule == "/planos/solicitar":
                assert r.status_code != 403, (regla.rule, h)
            else:
                assert r.status_code == 403, (regla.rule, h, r.status_code)


def test_F2_no_hay_metodos_con_efecto_fuera_de_GET_y_POST(env):
    c, camp, tmp = env
    raros = [(r.rule, sorted(r.methods - {"GET", "HEAD", "OPTIONS", "POST"}))
             for r in c.application.url_map.iter_rules() if r.methods - {"GET", "HEAD", "OPTIONS", "POST"}]
    assert raros == []


def test_F3_la_unica_ruta_con_excepcion_de_origen_es_la_publica_y_nada_la_extiende(env):
    from webapp import origin_guard
    assert origin_guard.EXENTAS == frozenset({"/planos/solicitar"})
    c, camp, tmp = env
    assert c.post("/planos/solicitar/otra", headers={"Origin": "http://evil.example"}).status_code in (403, 404)


def test_F4_toda_ruta_menos_las_publicas_exige_credenciales(tmp_path, monkeypatch):
    from test_e45_web_pilot import _arrancar
    c = _arrancar(tmp_path, monkeypatch, password="secreta")
    app = c.application
    abiertas = set()
    for regla in app.url_map.iter_rules():
        if "GET" not in regla.methods or regla.rule.startswith("/static"):
            continue
        r = c.get(_relleno(regla), headers={"Origin": "http://localhost"})
        if r.status_code != 401:
            abiertas.add(regla.rule)
    # superficie pública esperada (E40/E41/E43) y la sonda de salud; todo lo demás pide credenciales
    assert all(r == "/healthz" or r.startswith("/planos") for r in abiertas), sorted(abiertas)
    assert "/healthz" in abiertas and "/planos/" in abiertas


def test_F5_el_panel_y_las_paginas_no_exponen_rutas_locales_ni_secretos(env, monkeypatch):
    c, camp, tmp = env
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ZZZ-NO-SALE-0004")
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    for url in ("/", "/panel", f"/caso/{cid}", "/crear", "/mejorar"):
        t = _html(c, BASE + url)
        assert "sk-ZZZ" not in t and str(tmp) not in t and "/home/runner" not in t, url
    assert "sk-ZZZ" not in "".join(_archivos(tmp / "data").values())


# =============================================================================================
# G — métricas del experimento: secuencias adversariales
# =============================================================================================
def _n(camp, t="CREATE"):
    n = camp.count(t)
    return n["captured"], n["executed"], n["completed"], n["excluded"]


def test_G1_secuencia_adversarial_de_CREAR_FAILED_retry_DONE_excluir_recargar(env):
    c, camp, tmp = env
    from webapp.domain.reconstruction import engines
    from webapp.domain.reconstruction.engines import fixture
    fallos = [2]

    class Intermitente(fixture.FixtureReplay):
        engine_id = "motor_de_prueba"
        name = "Motor de prueba"

        def reconstruct(self, req):
            if fallos[0]:
                fallos[0] -= 1
                raise engines.EngineError("PROVIDER_TIMEOUT", "timeout")
            return super().reconstruct(req)
    engines.register(Intermitente())
    fotos, gt = _material(8000)
    cid = _cid(c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(b), n) for n, b in fotos],
                                             "plano_real": (io.BytesIO(gt[1]), gt[0])},
                      content_type="multipart/form-data"))
    assert _n(camp) == (1, 0, 0, 0)
    for esperado in ((1, 0, 0, 0), (1, 0, 0, 0), (1, 1, 0, 0)):                 # FAILED, FAILED, DONE
        c.post(f"{BASE}/caso/{cid}/procesar")
        _html(c, f"{BASE}/caso/{cid}")
        assert _n(camp) == esperado
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert _n(camp) == (1, 1, 0, 0)                                            # cerrar no es completar
    assert _eval_ux(c, cid).status_code == 303
    assert _n(camp) == (1, 1, 0, 0)                                            # la UX sola no completa
    assert _eval_plano(c, cid).status_code == 303
    assert _eval_plano(c, cid, rating="MALO").status_code == 303               # reevaluar no suma
    assert _n(camp) == (1, 1, 1, 0)
    # excluir libera el N y la propiedad; la recarga es un caso nuevo, sin historial mezclado
    camp.exclude(cid, "prueba de recarga")
    assert _n(camp) == (0, 0, 0, 1)
    nuevo = _cid(c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(b), n) for n, b in fotos],
                                               "plano_real": (io.BytesIO(gt[1]), gt[0])},
                        content_type="multipart/form-data"))
    assert nuevo != cid and camp.events(nuevo) == [] and _n(camp) == (1, 0, 0, 1)
    assert len(camp._of(cid, "pipeline")) == 3                                 # el historial viejo, intacto
    assert camp.get(cid)["recon_project_id"] != camp.get(nuevo)["recon_project_id"]


def test_G2_los_DEMO_no_consumen_N_y_no_bloquean_casos_reales(env):
    c, camp, tmp = env
    fotos, gt = _material(8100)
    demo = camp.import_upload(camp.CREATE, fotos, ground_truth=gt, demo=True)
    real = camp.import_upload(camp.CREATE, fotos, ground_truth=gt)             # mismo material, real
    assert demo != real and _n(camp) == (1, 0, 0, 0)
    assert camp.summary()["tracks"]["CREATE"]["counts"]["listed"] == 1


def test_G4_MEJORAR_excluir_y_recargar_el_mismo_plano_no_mezcla_historial_ni_propiedad(env, planta_lista):
    c, camp, tmp = env
    blob = _plano_unico(3)
    cid = _cid(_subir_mejorar(c, blob))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert _eval_plano(c, cid).status_code == 303
    assert camp.count("IMPROVE")["completed"] == 1
    prop_vieja = camp._of(cid, "improve_started")[0]["data"]["property_id"]
    assert _subir_mejorar(c, blob).status_code == 400                           # duplicado mientras esté activo
    camp.exclude(cid, "recarga")
    assert camp.count("IMPROVE")["completed"] == 0 and camp.count("IMPROVE")["excluded"] == 1
    nuevo = _cid(_subir_mejorar(c, blob))
    assert nuevo != cid and camp.events(nuevo) == []
    assert c.post(f"{BASE}/caso/{nuevo}/procesar").status_code == 303
    assert camp._of(nuevo, "improve_started")[0]["data"]["property_id"] != prop_vieja
    assert len(camp._of(cid, "pipeline")) == 1 and len(camp._of(cid, "evaluation")) == 1   # el viejo, intacto
    assert camp.count("IMPROVE")["executed"] == 1 and camp.count("IMPROVE")["completed"] == 0


def test_G3_veinte_mas_veinte_se_calcula_bien_con_FAILED_y_una_exclusion_en_el_medio(env, planta_lista):
    """20 MEJORAR + 20 CREAR completos → PASS; excluir uno → PARTIAL; recargarlo → PASS otra vez."""
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    imp, cre = [], []
    for k in range(20):
        cid = _cid(_subir_mejorar(c, _plano_unico(k)))
        c.post(f"{BASE}/caso/{cid}/procesar")
        assert _eval_plano(c, cid).status_code == 303
        imp.append(cid)
    for k in range(20):
        fotos, gt = _material(8200 + k)
        cid = _cid(c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(b), n) for n, b in fotos],
                                                 "plano_real": (io.BytesIO(gt[1]), gt[0])},
                          content_type="multipart/form-data"))
        c.post(f"{BASE}/caso/{cid}/procesar")
        _html(c, f"{BASE}/caso/{cid}")
        assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
        assert _eval_plano(c, cid).status_code == 303
        cre.append(cid)
    s = camp.summary()
    assert s["status"] == "PASS"
    assert s["tracks"]["IMPROVE"]["counts"]["completed"] == 20 and s["tracks"]["CREATE"]["counts"]["completed"] == 20
    camp.exclude(cre[7], "motivo")
    assert camp.summary()["status"] == "PARTIAL" and camp.count("CREATE")["completed"] == 19
    fotos, gt = _material(8207)
    nuevo = _cid(c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(b), n) for n, b in fotos],
                                               "plano_real": (io.BytesIO(gt[1]), gt[0])},
                        content_type="multipart/form-data"))
    c.post(f"{BASE}/caso/{nuevo}/procesar")
    _html(c, f"{BASE}/caso/{nuevo}")
    c.post(f"{BASE}/caso/{nuevo}/cerrar", data={"confirmo": "1"})
    _eval_plano(c, nuevo)
    assert camp.summary()["status"] == "PASS"
    for t in ("IMPROVE", "CREATE"):
        assert camp.summary()["tracks"][t]["counts"]["completed"] == 20
    for cid in imp + cre + [nuevo]:                                            # ningún estado imposible
        assert c.get(f"{BASE}/caso/{cid}").status_code == 200
    assert c.get(BASE + "/panel").status_code == 200


# =============================================================================================
# I — camino feliz integrado, sin proveedor real
# =============================================================================================
def test_I1_camino_feliz_integrado_MEJORAR_y_CREAR_sin_500_ni_409_inesperados(env, planta_lista):
    c, camp, tmp = env
    # MEJORAR completo
    mid = _cid(_subir_mejorar(c, _plano()))
    assert c.post(f"{BASE}/caso/{mid}/procesar").status_code == 303
    assert "ANTES" in _html(c, f"{BASE}/caso/{mid}").upper()
    assert c.get(f"{BASE}/caso/{mid}/archivo/despues").status_code == 200
    assert _eval_plano(c, mid).status_code == 303 and _eval_ux(c, mid).status_code == 303
    # CREAR completo, con una corrección
    cid = _cid(_subir_crear(c, n=3, referencia="Oficina en Providencia", m2="85"))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert "VOLVER A INTENTAR" not in _html(c, f"{BASE}/caso/{cid}")
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "la cocina es más chica"}).status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404           # ciego hasta cerrar
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 200           # reveal
    assert _eval_plano(c, cid).status_code == 303 and _eval_ux(c, cid).status_code == 303
    # panel y resumen al final
    assert c.get(BASE + "/panel").status_code == 200 and c.get(BASE + "/").status_code == 200
    s = camp.summary()
    assert s["tracks"]["IMPROVE"]["counts"]["completed"] == 1
    assert s["tracks"]["CREATE"]["counts"]["completed"] == 1
    assert s["tracks"]["CREATE"]["human_prompts"] == 1 and s["status"] == "PARTIAL"
    assert camp.build_index() and os.path.isfile(os.path.join(camp.root(), "index.html"))


@pytest.mark.parametrize("ruta", [PLANO_A, PLANO_B], ids=["plano_A", "plano_B"])
def test_I3_MEJORAR_con_un_plano_de_portal_y_el_motor_REAL_no_cae_y_no_inventa_resultado(env, ruta):
    """Sin el sustituto `planta_lista`: corre `ensure_case` + `ingest.auto_prepare` de verdad (CPU,
    sin red ni gasto) sobre un plano de portal versionado. Con la lámina sin unidad confirmada el
    caso queda en NECESITA REVISIÓN —lo honesto— y jamás se publica un «después» inventado."""
    c, camp, tmp = env
    if not os.path.isfile(ruta):
        pytest.skip("falta el plano de portal versionado en cases/")
    cid = _cid(_subir_mejorar(c, open(ruta, "rb").read()))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    t = _html(c, f"{BASE}/caso/{cid}")
    assert c.get(BASE + "/panel").status_code == 200
    pip = camp._of(cid, "pipeline")
    if pip:                                                   # la planta quedó lista: el resultado es real
        assert pip[0]["data"].get("output_asset_id")
    else:                                                     # pendiente de confirmar en el LAB
        assert "NECESITA REVISIÓN" in t.upper() or "NECESITA REVISI" in t.upper()
        assert c.get(f"{BASE}/caso/{cid}/archivo/despues").status_code == 404
    assert camp.count("IMPROVE")["executed"] == (1 if pip else 0)


def test_I2_camino_con_FAILED_reintento_cierre_reveal_evaluacion_excluir_y_reupload(env):
    c, camp, tmp = env
    from webapp import store
    from webapp.domain.reconstruction import runs
    cid = _cid(_subir_crear(c, n=2))
    cola = {"sincrona": False}
    real = runs.enqueue
    runs.enqueue = lambda rid: None if not cola["sincrona"] else runs.execute(rid)
    try:
        assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
        store.reset_orphans()                                                    # 1.er intento muere
        assert "VOLVER A INTENTAR" in _html(c, f"{BASE}/caso/{cid}")
        cola["sincrona"] = True
        assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
        _html(c, f"{BASE}/caso/{cid}")
    finally:
        runs.enqueue = real
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    assert _eval_plano(c, cid).status_code == 303
    assert camp.count("CREATE")["completed"] == 1
    camp.exclude(cid, "recarga de prueba")
    assert camp.count("CREATE")["completed"] == 0
    nuevo = _cid(_subir_crear(c, n=2))
    assert nuevo != cid and camp.status(camp.get(nuevo)) == camp.CAPTURED
    assert c.get(BASE + "/panel").status_code == 200
