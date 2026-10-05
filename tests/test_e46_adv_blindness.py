"""E46 (B) — auditoría adversarial de la ceguera de CREAR: que el plano real (GT) no se filtre ANTES
del reveal por ninguna superficie observable del repo, y dónde la ceguera sólo se sostiene por
identidad byte a byte.

Son tests de CARACTERIZACIÓN: fijan el comportamiento actual del piloto (E37+E44+E45+E45.2). Los que
documentan un defecto llevan `DEFECTO E46-Hxx` y afirman el comportamiento defectuoso; si algún día
se corrige, el test fallará y quien lo corrija debe actualizarlo (ver `reports/E46_REPORT.md`).

Todo es sintético, sin red ni gasto. No se usa ningún plano real.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3

import pytest

from test_e37_reconstruction_lab import _foto, _plano_de_galeria, _plano_real
from test_e45_web_pilot import (BASE, GT_NOMBRE, _cid, _html, _subir_crear, env)  # noqa: F401

GT_BYTES_MARCA = b"GT-ESCONDIDO"                        # va dentro del PNG de `_plano_real`


def _marcas(camp, cid, gt_nombre=GT_NOMBRE):
    """Todo lo que identificaría al plano real: su nombre, su sha, el nombre con que se guardó, la
    carpeta oculta y una cadena que sólo existe dentro de sus bytes."""
    from webapp import store
    pid = camp.get(cid)["recon_project_id"]
    fila = store.q1("SELECT sha256, stored_name FROM recon_ground_truth WHERE project_id=?", (pid,))
    stem = os.path.splitext(gt_nombre)[0]
    return {"nombre": gt_nombre.lower(), "stem": stem.lower(), "sha": fila["sha256"],
            "guardado": fila["stored_name"].lower(), "carpeta": "reconstruction_gt",
            "bytes": GT_BYTES_MARCA.decode().lower()}


def _buscar(texto: str, marcas: dict) -> list:
    t = texto.lower()
    return [k for k, v in marcas.items() if v and v in t]


def _texto_de_archivos(raiz: str, excluir=("reconstruction_gt",)) -> dict:
    """{ruta relativa: texto} de todo archivo bajo `raiz`, menos las carpetas excluidas. Las
    imágenes se leen como latin-1 para poder buscar bytes (sirve también para el nombre)."""
    out = {}
    for d, subs, fs in os.walk(raiz):
        subs[:] = [s for s in subs if s not in excluir]
        for f in fs:
            p = os.path.join(d, f)
            if f.endswith((".db", ".db-wal", ".db-shm")):
                continue                                  # la base se audita por tabla, aparte
            out[os.path.relpath(p, raiz)] = (os.path.relpath(p, raiz) + "\n"
                                             + open(p, "rb").read().decode("latin-1"))
    return out


def _tablas_sin_gt(tmp_path) -> dict:
    """Volcado de texto de TODAS las tablas de la base salvo `recon_ground_truth`."""
    db = sqlite3.connect(str(tmp_path / "data" / "escalimetro.db"))
    out = {}
    for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        if t == "recon_ground_truth" or t.startswith("sqlite_"):
            continue
        out[t] = json.dumps(db.execute(f'SELECT * FROM "{t}"').fetchall(), default=str,
                            ensure_ascii=False)
    return out


def _rastrear_superficie(c, camp, tmp_path, cid, etapa):
    """Visita cada superficie GET observable del caso (piloto + laboratorio E37) y revisa archivos,
    base y petición al proveedor. Devuelve las filtraciones encontradas como lista de textos."""
    marcas = _marcas(camp, cid)
    pid = camp.get(cid)["recon_project_id"]
    hallazgos = []
    # 1) páginas y JSON, con sus cabeceras
    urls = [f"{BASE}/", f"{BASE}/panel", f"{BASE}/caso/{cid}", f"{BASE}/mejorar", f"{BASE}/crear",
            "/lab/reconstruction/", f"/lab/reconstruction/p/{pid}",
            f"/lab/reconstruction/p/{pid}/comparar",
            f"{BASE}/caso/{cid}/archivo/real", f"{BASE}/caso/{cid}/archivo/foto-1",
            f"{BASE}/caso/{cid}/archivo/reconstruccion", f"{BASE}/caso/{cid}/archivo/entrada",
            f"/lab/reconstruction/p/{pid}/plano-real"]
    from webapp.domain.reconstruction import projects, runs
    for a in projects.assets_of(pid, include_retired=True):
        urls.append(f"/lab/reconstruction/p/{pid}/asset/{a['asset_id']}")
    for r in runs.of_project(pid):
        urls += [f"/lab/reconstruction/p/{pid}/r/{r['run_id']}",
                 f"/lab/reconstruction/p/{pid}/r/{r['run_id']}/status.json",
                 f"/lab/reconstruction/p/{pid}/r/{r['run_id']}/plano.svg"]
    visitadas_ok = 0
    for u in urls:
        r = c.get(u)
        visitadas_ok += r.status_code == 200
        cuerpo = r.get_data()
        if r.mimetype.startswith("image/") and not r.mimetype.endswith("svg+xml"):
            continue                                       # una foto de entrada: se audita por sha abajo
        texto = cuerpo.decode("utf-8", "replace") + "\n" + str(dict(r.headers))
        for m in _buscar(texto, marcas):
            hallazgos.append(f"[{etapa}] {u} -> {m}")
    # 2) archivos bajo DATA_DIR (menos la carpeta oculta) y el índice HTML de la campaña
    camp.build_index()
    for ruta, texto in _texto_de_archivos(str(tmp_path / "data")).items():
        for m in _buscar(texto, marcas):
            hallazgos.append(f"[{etapa}] archivo {ruta} -> {m}")
    # 3) todas las tablas salvo la del plano real
    for t, texto in _tablas_sin_gt(tmp_path).items():
        for m in _buscar(texto, marcas):
            hallazgos.append(f"[{etapa}] tabla {t} -> {m}")
    assert visitadas_ok >= 8, "el rastreo no visitó la superficie: la prueba no probaría nada"
    return hallazgos


def _cuerpo_al_proveedor(camp, cid):
    """La petición que `openai_direct` armaría para la primera corrida (sin red): el texto va tal
    cual; de las imágenes sólo se conserva el sha de los bytes que viajarían."""
    from webapp.domain.reconstruction import engines, runs
    pid = camp.get(cid)["recon_project_id"]
    # una corrida real de la cola (motor de prueba) congela los mismos inputs que congelaría el real
    corridas = runs.of_project(pid)
    rid = corridas[0]["run_id"] if corridas else runs.create_initial(
        pid, "motor_de_prueba", "e46", confirm_paid=True)
    req = runs.build_request(runs.get(rid))
    cuerpo = engines.get("openai_direct").build_body(req)
    return cuerpo, req


# ---- B1 · ninguna superficie delata el plano real antes del reveal -----------------------------
def test_B1_ninguna_superficie_filtra_el_gt_antes_del_reveal(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=3, referencia="Oficina en Providencia, piso 5"))
    hallazgos = _rastrear_superficie(c, camp, tmp, cid, "recien-subido")
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    _html(c, f"{BASE}/caso/{cid}")                          # asienta la corrida
    hallazgos += _rastrear_superficie(c, camp, tmp, cid, "procesado")
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "la cocina va al fondo"}).status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    hallazgos += _rastrear_superficie(c, camp, tmp, cid, "corregido")
    assert hallazgos == []


def test_B2_el_estado_posterior_al_reveal_si_muestra_el_gt_y_solo_por_la_ruta_del_reveal(env):
    """Control positivo: la búsqueda de B1 SÍ detecta el GT cuando corresponde (si no, B1 no
    probaría nada). Tras el reveal el plano real se sirve, y sólo por `archivo/real`."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    assert c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    r = c.get(f"{BASE}/caso/{cid}/archivo/real")
    assert r.status_code == 200 and GT_BYTES_MARCA in r.get_data()
    assert r.headers["Cache-Control"] == "private, no-store"
    marcas = _marcas(camp, cid)
    pid = camp.get(cid)["recon_project_id"]
    # el índice de revisión post-reveal incluye la copia del plano real: la búsqueda lo encuentra
    camp.build_index()
    en_archivos = [k for k, t in _texto_de_archivos(str(tmp / "data")).items()
                   if "bytes" in _buscar(t, marcas)]
    assert any("plano_real_post_reveal" in k for k in en_archivos)
    assert pid


# ---- B3 · lo que ve el motor ------------------------------------------------------------------
def test_B3_la_peticion_al_proveedor_no_lleva_el_gt_ni_sus_huellas(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=3, referencia="Oficina, 120 m2 útiles"))
    marcas = _marcas(camp, cid)
    cuerpo, req = _cuerpo_al_proveedor(camp, cid)
    # el texto (sin el base64 de las fotos) no contiene ninguna marca…
    sin_imagenes = json.dumps(cuerpo, ensure_ascii=False, default=str)
    sin_imagenes = re.sub(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+", "<img>", sin_imagenes)
    assert _buscar(sin_imagenes, marcas) == []
    # …y ninguna imagen que viaja es el plano real byte a byte ni lo contiene
    gt = hashlib.sha256(_plano_real()).hexdigest()
    for im in req.images:
        assert hashlib.sha256(im.data).hexdigest() != gt
        assert GT_BYTES_MARCA not in im.data
    # los ids que sí viajan son los de los inputs, no el del plano real
    assert all(a["asset_id"].startswith("rca_") for a in
               [{"asset_id": i.asset_id} for i in req.images])


def test_B4_los_nombres_del_usuario_no_sobreviven_en_ningun_artefacto(env):
    """El nombre de las fotos y del plano real (con unicode, traversal y marcas) no llega a disco, a
    la base de E37 ni al manifiesto: se guardan como `foto_NN.ext` / `plano_real.ext`."""
    c, camp, tmp = env
    raros = ["../../../etc/passwd_FOTO.png", "ÑANDÚ_marca_ÚNICA_77.png", "a b\tc_TAB.png"]
    data = {"fotos": [(io.BytesIO(_foto(i)), n) for i, n in enumerate(raros)],
            "plano_real": (io.BytesIO(_plano_real()), "../GT_NOMBRE_RARO_9921.png")}
    r = c.post(f"{BASE}/crear", data=data, content_type="multipart/form-data")
    cid = _cid(r)
    for marca in ("passwd_foto", "ñandú_marca", "marca_única_77", "a b\tc_tab", "gt_nombre_raro_9921"):
        for ruta, texto in _texto_de_archivos(str(tmp / "data"), excluir=()).items():
            if "reconstruction_gt" in ruta:
                continue
            assert marca not in texto.lower(), (marca, ruta)
        for t, texto in _tablas_sin_gt(tmp).items():
            assert marca not in texto.lower(), (marca, t)
    assert [a["file"] for a in camp.get(cid)["assets"]] == ["foto_01.png", "foto_02.png", "foto_03.png"]


# ---- B5 · el GT sólo existe en su carpeta y en su tabla ------------------------------------------
def test_B5_el_gt_vive_solo_en_reconstruction_gt_y_en_su_tabla(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    donde = [ruta for ruta, t in _texto_de_archivos(str(tmp / "data"), excluir=()).items()
             if GT_BYTES_MARCA.decode().lower() in t.lower()]
    assert donde, "el control debe encontrar el GT en su lugar"
    assert all(d.replace("\\", "/").startswith("reconstruction_gt/") or d.endswith(".db")
               for d in donde), donde


# ---- B6 · mensajes de error ----------------------------------------------------------------------
@pytest.mark.parametrize("gt_nombre,gt_bytes", [
    ("SECRETO_GT_7781.exe", b"MZ" + b"\x00" * 40),             # extensión no permitida
    ("SECRETO_GT_7781.png", b"%PDF-1.4 no soy png"),           # contenido que no corresponde
    ("SECRETO_GT_7781.pdf", b"%PDF-1.4 vacio"),                # PDF sin páginas
])
def test_B6_un_plano_real_rechazado_no_deja_rastro_ni_en_el_error(env, gt_nombre, gt_bytes):
    """El mensaje de error sí nombra el archivo que el propio usuario acaba de subir (es su pantalla),
    pero nada queda guardado: ni caso, ni proyecto, ni carpeta."""
    c, camp, tmp = env
    r = _subir_crear(c, n=2, gt=gt_bytes, gt_nombre=gt_nombre)
    assert r.status_code == 400
    from webapp.domain.reconstruction import projects
    assert camp.load()["cases"] == [] and projects.listing() == []
    assert not os.path.isdir(os.path.join(camp.root(), "cases")) or not os.listdir(
        os.path.join(camp.root(), "cases"))


# ---- DEFECTO E46-H01 · el plano como «foto» entra al motor sin aviso ----------------------------
def test_DEFECTO_H01_un_plano_re_guardado_como_foto_entra_al_motor_y_la_auditoria_de_ceguera_pasa(env):
    """La ceguera se hace cumplir por identidad byte a byte (sha256). Si el operador sube, como foto,
    el MISMO plano en otra codificación —lo habitual en una galería de portal, donde el plano es una
    imagen más—, E37 lo marca `looks_like_plan`, pero la nota se descarta en `_prepare_create`, el
    caso se acepta, `blind_audit` da ok y el motor recibe el dibujo.

    Si esto se corrige (rechazar o avisar), este test fallará: actualizarlo."""
    import cv2
    import numpy as np
    c, camp, tmp = env
    plano = _plano_de_galeria()                                   # el «plano real» de la propiedad
    img = cv2.imdecode(np.frombuffer(plano, np.uint8), cv2.IMREAD_COLOR)
    como_foto = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
    assert como_foto != plano and hashlib.sha256(como_foto).digest() != hashlib.sha256(plano).digest()
    data = {"fotos": [(io.BytesIO(como_foto), "IMG_plano.jpg"), (io.BytesIO(_foto(1)), "IMG_2.png")],
            "plano_real": (io.BytesIO(plano), "plano_real.png")}
    r = c.post(f"{BASE}/crear", data=data, content_type="multipart/form-data")
    cid = _cid(r)                                                 # se acepta
    pid = camp.get(cid)["recon_project_id"]
    from webapp import store
    marcadas = [dict(a)["looks_like_plan"] for a in store.q(
        "SELECT looks_like_plan FROM recon_assets WHERE project_id=? ORDER BY sort_order", (pid,))]
    assert marcadas == [1, 0]                                     # E37 lo detectó…
    assert camp.blind_audit(cid) == {"ok": True, "violations": []}  # …y la auditoría no lo ve
    _cuerpo, req = _cuerpo_al_proveedor(camp, cid)
    assert any(im.data == como_foto for im in req.images)         # el dibujo viaja al proveedor
    assert "parece un plano" not in _html(c, f"{BASE}/caso/{cid}")  # y el piloto no lo avisa


# ---- DEFECTO E46-H04 · reveal fuera de banda --------------------------------------------------
def test_DEFECTO_H04_el_reveal_de_E37_por_fuera_del_piloto_no_frena_correcciones_ni_el_cierre(env):
    """El laboratorio de E37 (`/lab/reconstruction/…/revelar`) sigue accesible para un proyecto de la
    campaña. Si se revela por ahí, la campaña no se entera: se puede seguir corrigiendo «a ciegas» y
    el cierre ciego se acepta (el único rastro es `gt_state_at_closure == REVEALED` dentro del evento).

    Si esto se corrige (negarse a corregir/cerrar con el GT ya revelado), actualizar el test."""
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    c.post(f"{BASE}/caso/{cid}/procesar")
    _html(c, f"{BASE}/caso/{cid}")
    pid = camp.get(cid)["recon_project_id"]
    assert c.post(f"/lab/reconstruction/p/{pid}/revelar", data={"confirm": "1"}).status_code == 302
    # la campaña sigue creyendo que el plano real está oculto…
    assert not camp._of(cid, "reveal") and c.get(f"{BASE}/caso/{cid}/archivo/real").status_code == 404
    # …y deja corregir con el GT ya a la vista del operador…
    assert c.post(f"{BASE}/caso/{cid}/corregir", data={"texto": "ahora que vi el plano"}).status_code == 303
    _html(c, f"{BASE}/caso/{cid}")
    # …y cerrar «a ciegas»: la auditoría pasa; sólo el evento guarda el estado real
    assert c.post(f"{BASE}/caso/{cid}/cerrar", data={"confirmo": "1"}).status_code == 303
    cierre = camp._of(cid, "closure")[-1]["data"]
    assert cierre["gt_state_at_closure"] == "REVEALED" and cierre["blind_audit"]["ok"] is True
    from webapp.domain.reconstruction import runs
    hijas = [r for r in runs.of_project(pid) if r["origin"] == "CORRECTION"]
    assert hijas and hijas[-1]["gt_state_at_creation"] == "REVEALED"   # E37 sí lo marca en la corrida


# ---- la auditoría de ceguera detecta lo que dice detectar ----------------------------------------
def test_B7_blind_audit_detecta_huellas_del_gt_en_lo_visible_al_motor(env):
    c, camp, tmp = env
    cid = _cid(_subir_crear(c, n=2))
    assert camp.blind_audit(cid)["ok"] is True
    from webapp import store
    pid = camp.get(cid)["recon_project_id"]
    nombre = store.q1("SELECT original_filename n FROM recon_ground_truth WHERE project_id=?",
                      (pid,))["n"]
    # contaminar a propósito el manifiesto con el nombre del GT: la auditoría lo ve
    m = camp.load()
    m["cases"][0]["notes"] = "ver " + nombre
    camp._save(m)
    a = camp.blind_audit(cid)
    assert a["ok"] is False and any("nombre" in v for v in a["violations"])


def test_B8_blind_audit_no_ve_el_gt_si_viaja_re_codificado_como_foto(env):
    """Límite conocido (misma raíz que H01): la auditoría compara sha256, no contenido."""
    import cv2
    import numpy as np
    c, camp, tmp = env
    plano = _plano_de_galeria()
    img = cv2.imdecode(np.frombuffer(plano, np.uint8), cv2.IMREAD_COLOR)
    otra = cv2.imencode(".png", cv2.resize(img, (200, 150)))[1].tobytes()   # mismo dibujo, otro tamaño
    r = c.post(f"{BASE}/crear", data={"fotos": [(io.BytesIO(otra), "x.png")],
                                       "plano_real": (io.BytesIO(plano), "p.png")},
               content_type="multipart/form-data")
    cid = _cid(r)
    assert camp.blind_audit(cid)["ok"] is True


def test_B9_el_camino_bloqueado_por_credencial_tampoco_filtra_y_no_simula(env, monkeypatch):
    """Con el motor real (`openai_direct`) y sin `OPENAI_API_KEY`: BLOQUEADO, nunca un resultado
    simulado, y ni el detalle del bloqueo ni las pantallas delatan el plano real."""
    c, camp, tmp = env
    from webapp import pilot
    monkeypatch.setattr(pilot, "CREATE_ENGINE", "openai_direct")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cid = _cid(_subir_crear(c, n=2))
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert camp.status(camp.get(cid)) == camp.BLOCKED_CRED
    assert not camp._of(cid, "pipeline")                        # nada simulado
    assert _rastrear_superficie(c, camp, tmp, cid, "bloqueado") == []
    # reintentar sigue bloqueado y no duplica el evento
    assert c.post(f"{BASE}/caso/{cid}/procesar").status_code == 303
    assert len(camp._of(cid, "blocked")) == 1
