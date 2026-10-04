"""E45.2 — endurecimiento de la carga móvil del piloto: HEIC/HEIF, límites explícitos, lectura
acotada, rechazo sin residuos y ceguera intacta.

Todo el material es sintético; ningún test sale a la red ni gasta. Reutiliza el arnés de E45.
"""
from __future__ import annotations

import io
import os
import re

import pytest

from test_e37_reconstruction_lab import _foto, _plano_real
from test_e45_web_pilot import BASE, GT_NOMBRE, _cid, _html, _subir_crear, env  # noqa: F401

PIL = pytest.importorskip("PIL.Image")
pillow_heif = pytest.importorskip("pillow_heif")
from PIL import Image  # noqa: E402

from webapp import mobile_upload as mu  # noqa: E402


def _heic(w=80, h=40, orientacion=None, ext="HEIF") -> bytes:
    pillow_heif.register_heif_opener()
    im = Image.new("RGB", (w, h), (255, 0, 0))
    im.paste((0, 0, 255), (w // 2, 0, w, h))                  # mitad izquierda roja, derecha azul
    kw = {}
    if orientacion:
        ex = Image.Exif()
        ex[0x0112] = orientacion
        kw["exif"] = ex.tobytes()
    b = io.BytesIO()
    im.save(b, ext, **kw)
    return b.getvalue()


def _jpg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 200)).save(b, "JPEG")
    return b.getvalue()


def _webp() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 10)).save(b, "WEBP")
    return b.getvalue()


def _post(c, fotos, gt=None, gt_nombre=GT_NOMBRE):
    data = {"fotos": [(io.BytesIO(b), n) for n, b in fotos],
            "plano_real": (io.BytesIO(gt if gt is not None else _plano_real()), gt_nombre)}
    return c.post(f"{BASE}/crear", data=data, content_type="multipart/form-data")


def _sin_residuos(camp):
    """Ni caso E44, ni proyecto E37 (con su GT), ni carpetas de caso, ni eventos."""
    from webapp.domain.reconstruction import projects
    assert camp.load()["cases"] == []
    assert projects.listing() == []
    raiz = camp.root()
    assert not [d for d in (os.listdir(raiz) if os.path.isdir(raiz) else []) if d.startswith("e44-")]
    assert camp.count("CREATE")["captured"] == 0


# ---- HEIC / HEIF ------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", ["IMG_0001.HEIC", "IMG_0002.heif", "foto.heic"])
def test_heic_y_heif_validos_se_aceptan_y_entran_como_jpg(env, nombre):
    c, camp, tmp = env
    cid = _cid(_post(c, [(nombre, _heic())]))
    caso = camp.get(cid)
    assert [a["file"] for a in caso["assets"]] == ["foto_01.jpg"]
    ev = os.path.join(camp.case_dir(cid), "evidence", "foto_01.jpg")
    assert open(ev, "rb").read(3) == b"\xff\xd8\xff"          # JPEG real, el motor no ve HEIC
    # y ninguna carpeta del proyecto E37 guarda un HEIC
    for _r, _d, archivos in os.walk(tmp / "data"):
        assert not [f for f in archivos if f.lower().endswith((".heic", ".heif"))]


def test_heic_corrupto_o_renombrado_se_rechaza_sin_residuos(env):
    c, camp, _ = env
    bueno = _heic()
    for nombre, blob in [("a.heic", b"esto no es una imagen"), ("a.jpg", b"%PDF-1.4 falso"),
                         ("a.heic", bueno[:40]),                      # cabecera ok, contenido truncado
                         ("a.jpg", bueno),                            # HEIC disfrazado de JPG
                         ("a.heic", _jpg()),                          # JPG disfrazado de HEIC
                         ("a.png", _jpg()), ("a.webp", b"RIFF\x00\x00\x00\x00WEBPjunk")]:
        r = _post(c, [("ok.png", _foto(1)), (nombre, blob)])
        assert r.status_code == 400, nombre
        assert re.search(r"no es una foto|No pudimos leer", r.get_data(as_text=True)), nombre
        _sin_residuos(camp)


def test_heic_conserva_la_orientacion_visual(env):
    # EXIF/irot 6 = girar 90° en sentido horario al mostrar: 80×40 pasa a 40×80 y la mitad
    # izquierda (roja) queda ARRIBA
    nombre, jpg = mu.normalizar_foto("a.heic", _heic(80, 40, orientacion=6))
    assert nombre == "a.jpg"
    im = Image.open(io.BytesIO(jpg))
    assert im.size == (40, 80)
    assert im.getexif().get(0x0112) in (None, 1)               # no queda orientación pendiente
    r, g, b = im.getpixel((20, 10))
    assert r > 200 and b < 60
    r, g, b = im.getpixel((20, 70))
    assert b > 200 and r < 60
    # sin orientación no rota
    assert Image.open(io.BytesIO(mu.normalizar_foto("a.heic", _heic(80, 40))[1])).size == (80, 40)


# ---- regresión de los formatos que ya andaban -------------------------------------------------
def test_jpg_png_y_webp_siguen_entrando_intactos(env):
    c, camp, _ = env
    fotos = [("a.jpg", _jpg()), ("b.JPEG", _jpg() + b"\x00"), ("c.png", _foto(3)), ("d.webp", _webp())]
    # los dos JPG con bytes distintos para que no se deduplique el material
    cid = _cid(_post(c, fotos))
    assert [a["file"] for a in camp.get(cid)["assets"]] == [
        "foto_01.jpg", "foto_02.jpeg", "foto_03.png", "foto_04.webp"]
    ev = os.path.join(camp.case_dir(cid), "evidence")
    assert open(os.path.join(ev, "foto_03.png"), "rb").read() == _foto(3)   # byte a byte
    assert mu.normalizar_foto("x.png", _foto(3)) == ("x.png", _foto(3))


# ---- límites: cantidad, individual y total ----------------------------------------------------
def test_limite_de_cantidad_en_el_borde(env):
    c, camp, _ = env
    n = mu.MAX_FOTOS
    sobran = [(f"i{i}.png", _foto(i)) for i in range(n + 1)]
    r = _post(c, sobran)
    h = r.get_data(as_text=True)
    assert r.status_code == 400 and f"el máximo por propiedad es {n}" in h
    _sin_residuos(camp)
    assert _cid(_post(c, sobran[:n])).startswith("e44-cre-")      # exactamente el máximo, entra


def test_cantidad_se_revisa_antes_de_leer_ningun_byte():
    class Falso:
        filename = "a.png"

        class stream:                                          # noqa: N801
            @staticmethod
            def read(_n=-1):
                raise AssertionError("se leyó un archivo antes de validar la cantidad")
    with pytest.raises(mu.UploadError, match="máximo por propiedad"):
        mu.leer_fotos([Falso()] * (mu.MAX_FOTOS + 1))


def test_limite_individual_en_el_borde(monkeypatch):
    monkeypatch.setattr(mu, "MAX_FOTO_MB", 1)
    tope = 1024 * 1024

    class S:
        def __init__(self, n):
            self.stream, self.filename = io.BytesIO(b"x" * n), "a.png"
    assert len(mu.leer_fotos([S(tope)])[0][1]) == tope           # justo en el tope: pasa
    with pytest.raises(mu.UploadError, match=r"pesa demasiado.*1 MB"):
        mu.leer_fotos([S(tope + 1)])


def test_limite_total_del_lote_en_el_borde(monkeypatch):
    monkeypatch.setattr(mu, "MAX_FOTO_MB", 1)
    monkeypatch.setattr(mu, "MAX_LOTE_MB", 2)
    tope = 1024 * 1024

    class S:
        def __init__(self, n):
            self.stream, self.filename = io.BytesIO(b"x" * n), "a.png"
    assert sum(len(b) for _n, b in mu.leer_fotos([S(tope), S(tope)])) == 2 * tope
    with pytest.raises(mu.UploadError, match=r"lote de fotos pesa demasiado.*2 MB"):
        mu.leer_fotos([S(tope), S(tope), S(1)])


def test_la_lectura_se_corta_durante_la_ingestion_y_no_al_final(monkeypatch):
    """El archivo gigante no se lee entero: se aborta apenas pasa el tope, con un lector que cuenta."""
    monkeypatch.setattr(mu, "MAX_FOTO_MB", 1)
    leido = []

    class Infinito:
        def read(self, n=-1):
            leido.append(n)
            return b"x" * n                                    # nunca termina
    with pytest.raises(mu.UploadError):
        mu.leer_limitado(Infinito(), 1024 * 1024, "g.png", presupuesto=[10 * 1024 * 1024])
    assert len(leido) * mu.CHUNK <= 1024 * 1024 + mu.CHUNK
    assert all(n == mu.CHUNK for n in leido)                   # siempre trozos, nunca read() sin tope


def test_el_codigo_de_la_ruta_no_hace_read_sin_limite():
    fuente = open(os.path.join(os.path.dirname(__file__), "..", "webapp", "pilot.py"),
                  encoding="utf-8").read()
    cuerpo = fuente[fuente.index("def crear_post"):fuente.index("def caso(")]
    assert ".read()" not in cuerpo and "mobile_upload.leer_fotos" in cuerpo


def test_http_foto_pesada_y_lote_pesado_se_rechazan_con_mensaje_humano(env, monkeypatch):
    c, camp, _ = env
    monkeypatch.setattr(mu, "MAX_FOTO_MB", 1)
    monkeypatch.setattr(mu, "MAX_LOTE_MB", 2)
    grande = _jpg() + b"\x00" * (1024 * 1024 + 10)
    r = _post(c, [("ok.png", _foto(1)), ("grande.jpg", grande)])
    h = r.get_data(as_text=True)
    assert r.status_code == 400 and "grande.jpg" in h and "máximo por archivo es 1 MB" in h
    _sin_residuos(camp)
    medio = _jpg() + b"\x00" * (800 * 1024)
    r = _post(c, [(f"f{i}.jpg", medio + bytes([i])) for i in range(3)])
    assert r.status_code == 400 and "máximo total es 2 MB" in r.get_data(as_text=True)
    _sin_residuos(camp)


def test_el_cuerpo_del_post_de_crear_tiene_tope_propio(env, monkeypatch):
    c, camp, _ = env
    monkeypatch.setattr(mu, "MAX_ENVIO_BYTES", 200 * 1024)
    r = _post(c, [("a.jpg", _jpg() + b"\x00" * (300 * 1024))])
    h = r.get_data(as_text=True)
    assert r.status_code == 413 and "demasiado grande" in h and f"{mu.MAX_FOTOS} fotos" in h
    _sin_residuos(camp)


# ---- plano real -------------------------------------------------------------------------------
def test_plano_real_demasiado_grande_corrupto_o_disfrazado_se_rechaza(env, monkeypatch):
    c, camp, _ = env
    fotos = [("a.png", _foto(1))]
    for gt, nombre, esperado in [
            (b"no soy un pdf", "plano.pdf", "no es un PDF válido"),
            (b"%PDF-1.4\n garbage", "plano.pdf", "PDF está dañado"),
            (_foto(9), "plano.pdf", "no es un PDF válido"),
            (b"\x89PNG\r\n\x1a\ntruncado", "plano.png", "No pudimos leer"),
            (_plano_real()[:60], "plano.png", "No pudimos leer"),
            (b"hola", "plano.jpg", "no es un JPG válido")]:
        r = _post(c, fotos, gt=gt, gt_nombre=nombre)
        assert r.status_code == 400 and esperado in r.get_data(as_text=True), (nombre, esperado)
        _sin_residuos(camp)
    monkeypatch.setattr(mu, "MAX_PLANO_REAL_MB", 1)
    r = _post(c, fotos, gt=_plano_real() + b"\x00" * (1024 * 1024 + 5), gt_nombre="plano.png")
    assert r.status_code == 400 and "máximo por archivo es 1 MB" in r.get_data(as_text=True)
    _sin_residuos(camp)


def test_plano_real_valido_pdf_o_png_entra_y_sigue_oculto(env):
    c, camp, _ = env
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    pdf = doc.tobytes()
    for i, (gt, nombre) in enumerate([(_plano_real(), "plano.png"), (pdf, "plano.pdf")]):
        r = _post(c, [("a.heic", _heic(40 + 2 * i, 40))], gt=gt, gt_nombre=nombre)
        assert r.status_code == 303, re.search(r'class="err[^>]*>(.*?)</', r.get_data(as_text=True), re.S)
        cid = _cid(r)
        caso = camp.get(cid)
        assert "plano_real" not in str(caso["assets"]) and nombre not in str(caso["assets"])
        h = _html(c, f"{BASE}/caso/{cid}")
        assert nombre not in h and "plano_real" not in h and GT_NOMBRE not in h
        assert c.get(f"{BASE}/caso/{cid}/archivo/plano_real").status_code in (403, 404)


# ---- ceguera ----------------------------------------------------------------------------------
def test_la_ceguera_del_plano_real_sigue_intacta_con_fotos_heic(env):
    c, camp, _ = env
    cid = _cid(_post(c, [("IMG_1.HEIC", _heic()), ("IMG_2.png", _foto(2))]))
    caso = camp.get(cid)
    assert caso["has_ground_truth"] is True
    # el plano real no está entre los inputs del caso ni en la evidencia visible al motor
    ev = os.listdir(os.path.join(camp.case_dir(cid), "evidence"))
    assert sorted(ev) == ["foto_01.jpg", "foto_02.png"]
    assert not any("heic" in a["file"].lower() or "IMG_" in a["file"] for a in caso["assets"])
    h = _html(c, f"{BASE}/caso/{cid}")
    assert "IMG_1" not in h and GT_NOMBRE not in h               # ni nombres originales ni el GT
    assert c.get(f"{BASE}/caso/{cid}/archivo/plano_real").status_code in (403, 404)


# ---- formulario móvil -------------------------------------------------------------------------
def test_el_formulario_declara_heic_y_los_limites(env):
    c, _, _ = env
    h = _html(c, BASE + "/crear")
    accept = re.search(r'name="fotos" accept="([^"]+)"', h).group(1)
    for t in ("image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", ".heic", ".heif"):
        assert t in accept
    assert "HEIC" in h and f"Hasta {mu.MAX_FOTOS} fotos" in h
    assert f"{mu.MAX_FOTO_MB} MB cada una" in h and f"{mu.MAX_LOTE_MB} MB en total" in h
    assert f"máx. {mu.MAX_PLANO_REAL_MB} MB" in h
    assert 'name="fotos"' in h and "multiple" in h


def test_formato_no_aceptado_mensaje_accionable(env):
    c, camp, _ = env
    r = _post(c, [("doc.gif", b"GIF89a")])
    h = r.get_data(as_text=True)
    assert r.status_code == 400 and "Formato no aceptado" in h and "JPG, PNG, WEBP, HEIC o HEIF" in h
    _sin_residuos(camp)


def test_mejorar_conserva_su_comportamiento(env):
    """MEJORAR no se tocó: un solo plano, el mismo límite de E44 y el mismo accept."""
    c, camp, _ = env
    h = _html(c, BASE + "/mejorar")
    assert ".pdf,.png,.jpg,.jpeg" in h and "heic" not in h.lower()
    r = c.post(f"{BASE}/mejorar", data={"plano": (io.BytesIO(_jpg()), "a.heic")},
               content_type="multipart/form-data")
    assert r.status_code == 400


def test_la_dependencia_heic_esta_declarada_para_el_build():
    raiz = os.path.join(os.path.dirname(__file__), "..")
    assert re.search(r"^pillow-heif", open(os.path.join(raiz, "requirements.txt")).read(), re.M)
