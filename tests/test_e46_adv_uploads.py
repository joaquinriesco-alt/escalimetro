"""E46 (D) — entradas hostiles razonables a la carga del piloto (E45 + E45.2): nombres extraños,
contenido que no corresponde a la extensión, límites en su borde exacto, bombas de descompresión,
HEIC/HEIF, lotes, y la asimetría entre CREAR (endurecido en E45.2) y MEJORAR (no).

No es un pentest destructivo: las «bombas» son archivos de decenas de KB que declaran muchos
píxeles, decodificados a una escala que el sandbox soporta (la memoria se mide en un subproceso).
Tests de CARACTERIZACIÓN; los marcados `DEFECTO E46-Hxx` afirman el comportamiento defectuoso actual.
Material sintético; sin red ni gasto.
"""
from __future__ import annotations

import base64
import io
import os
import struct
import subprocess
import sys
import zlib

import pytest

PIL = pytest.importorskip("PIL.Image")
pillow_heif = pytest.importorskip("pillow_heif")

from test_e37_reconstruction_lab import _foto, _png, _plano_de_galeria, _plano_real  # noqa: E402
from test_e45_2_mobile_upload import _heic, _jpg, _sin_residuos, _webp  # noqa: E402
from test_e45_web_pilot import BASE, _cid, _html, _subir_mejorar, env  # noqa: E402,F401

from webapp import mobile_upload as mu  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _png_dims(w: int, h: int, modo: str = "L") -> bytes:
    """PNG válido de w×h con un solo color: pesa decenas de KB y declara w·h píxeles."""
    ch, ct = {"L": (1, 0), "RGB": (3, 2)}[modo]
    comp = zlib.compressobj(9)
    fila = b"\x00" + b"\x80" * (w * ch)
    datos = b"".join(comp.compress(fila) for _ in range(h)) + comp.flush()
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0))
            + _chunk(b"IDAT", datos) + _chunk(b"IEND", b""))


def _png_con_relleno(nbytes: int) -> bytes:
    """PNG válido de 8×8 con un chunk auxiliar de relleno: pesa EXACTAMENTE `nbytes`."""
    base = _png(8, 8, b"\x10\x20\x30")
    # inserta un chunk tEXt antes de IEND; cada chunk suma 12 bytes de sobrecarga
    sin_iend, iend = base[:-12], base[-12:]
    falta = nbytes - len(base) - 12
    assert falta >= 0
    return sin_iend + _chunk(b"tEXt", b"k\x00" + b"x" * (falta - 2)) + iend


def _pdf_sin_paginas() -> bytes:
    import pymupdf
    d = pymupdf.open()
    d.new_page()
    d.delete_page(0) if d.page_count > 1 else None
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n" \
           b"trailer<</Root 1 0 R>>\n%%EOF"


def _pdf_valido() -> bytes:
    import pymupdf
    d = pymupdf.open()
    d.new_page(width=200, height=100)
    return d.tobytes()


def _crear(c, fotos, gt=None, gt_nombre="plano.png", **extra):
    data = {"fotos": [(io.BytesIO(b), n) for n, b in fotos],
            "plano_real": (io.BytesIO(gt if gt is not None else _plano_real()), gt_nombre), **extra}
    return c.post(f"{BASE}/crear", data=data, content_type="multipart/form-data")


def _guardados(camp, tmp):
    """Nombres de archivo que realmente quedaron bajo DATA_DIR (campaña + E37)."""
    out = []
    for d, _s, fs in os.walk(str(tmp / "data")):
        out += [f for f in fs if not f.endswith((".db", ".db-wal", ".db-shm"))]
    return out


# ---- D1 · nombres de archivo ---------------------------------------------------------------------
@pytest.mark.parametrize("nombre", [
    "IMG_0001.JPG", "FOTO.Png", "ÑANDÚ 🏢 oficina.jpg", "a" * 250 + ".jpg",
    "../../../../etc/passwd.jpg", "..\\..\\windows\\system32\\x.jpg", "C:\\fakepath\\IMG_9.jpg",
    # los navegadores escapan `"` y saltos de l\u00ednea del filename como %22 / %0A (HTML Standard); el
    # cliente de pruebas de werkzeug no los escapa, as\u00ed que se prueban ya escapados
    "foto con espacios y 'comillas' %22dobles%22.jpg", "\u202egpj.exe.jpg", "x%0A.jpg",
])
def test_D1_los_nombres_raros_se_aceptan_pero_nunca_llegan_a_disco(env, nombre):
    c, camp, tmp = env
    ext = os.path.splitext(nombre)[1].lower()
    blob = _jpg() if ext in (".jpg", ".jpeg") else _png(64, 48, b"\x01\x02\x03")
    r = _crear(c, [(nombre, blob)])
    cid = _cid(r)
    guardados = _guardados(camp, tmp)
    assert [a["file"] for a in camp.get(cid)["assets"]] == ["foto_01" + ext]
    # ninguna parte del nombre original sobrevive en un nombre de archivo
    assert not [g for g in guardados if any(t in g for t in ("passwd", "ÑANDÚ", "fakepath", "system32", "comillas"))]


@pytest.mark.parametrize("nombre", ["foto", ".jpg", "foto.jpg.exe", "foto.jpeg.", "foto.svg", "foto.gif",
                                    "foto.tiff", "foto.bmp", "foto.html", "foto.jpg ", "foto.JPG\t"])
def test_D1b_extensiones_no_permitidas_se_rechazan_sin_residuos(env, nombre):
    c, camp, tmp = env
    r = _crear(c, [(nombre, _jpg())])
    assert r.status_code == 400
    _sin_residuos(camp)


# ---- D2 · contenido contra extensión (matriz) ------------------------------------------------------
def _contenidos():
    return {"jpeg": _jpg(), "png": _png(64, 48, b"\x05\x06\x07"), "webp": _webp(), "heif": _heic(),
            "pdf": _pdf_valido(), "gif": b"GIF89a" + b"\x00" * 40, "bmp": b"BM" + b"\x00" * 60,
            "html": b"<html><script>alert(1)</script></html>", "svg": b"<svg xmlns='http://www.w3.org/2000/svg'/>",
            "cero": b"", "uno": b"\xff", "exe": b"MZ" + b"\x00" * 60}


_FOTO_EXT = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp", ".heic": "heif", ".heif": "heif"}


@pytest.mark.parametrize("ext", sorted(_FOTO_EXT))
@pytest.mark.parametrize("tipo", ["jpeg", "png", "webp", "heif", "pdf", "gif", "bmp", "html", "svg", "uno", "exe"])
def test_D2_una_foto_solo_entra_si_su_contenido_coincide_con_su_extension(env, ext, tipo):
    c, camp, tmp = env
    r = _crear(c, [("foto" + ext, _contenidos()[tipo])])
    if _FOTO_EXT[ext] == tipo:
        assert r.status_code == 303
    else:
        assert r.status_code == 400
        _sin_residuos(camp)


@pytest.mark.parametrize("ext,tipo,ok", [
    (".png", "png", True), (".jpg", "jpeg", True), (".jpeg", "jpeg", True), (".pdf", "pdf", True),
    (".png", "jpeg", False), (".jpg", "png", False), (".pdf", "png", False), (".png", "pdf", False),
    (".png", "html", False), (".jpg", "svg", False), (".pdf", "html", False), (".png", "cero", False),
    (".webp", "webp", False), (".heic", "heif", False), (".gif", "gif", False)])
def test_D2b_el_plano_real_se_valida_por_contenido(env, ext, tipo, ok):
    c, camp, tmp = env
    r = _crear(c, [("f.png", _png(64, 48, b"\x09\x08\x07"))], gt=_contenidos()[tipo], gt_nombre="plano" + ext)
    assert r.status_code == (303 if ok else 400)
    if not ok:
        _sin_residuos(camp)


def test_D2c_el_content_type_declarado_por_el_cliente_no_cuenta(env):
    """Se manda una foto JPEG con `Content-Type: image/png`, y un PNG con `image/jpeg`: manda el
    contenido real contra la extensión, no la cabecera."""
    c, camp, tmp = env
    data = {"fotos": [(io.BytesIO(_jpg()), "a.jpg", "image/png")],
            "plano_real": (io.BytesIO(_plano_real()), "gt.png", "application/pdf")}
    assert c.post(f"{BASE}/crear", data=data, content_type="multipart/form-data").status_code == 303


def test_D2d_un_archivo_truncado_o_corrupto_se_rechaza(env):
    c, camp, tmp = env
    jpg = _jpg()
    casos = [("a.jpg", jpg[: len(jpg) // 2]), ("b.png", _png(64, 48, b"\x01\x01\x01")[:40]),
             ("c.webp", _webp()[:30]), ("d.heic", _heic()[:60]),
             ("e.heic", b"\x00\x00\x00\x18ftypheic" + os.urandom(200))]
    for nombre, blob in casos:
        r = _crear(c, [(nombre, blob)])
        assert r.status_code == 400, nombre
    _sin_residuos(camp)


def test_D2e_un_lote_con_un_solo_archivo_malo_se_rechaza_entero_sin_residuos(env):
    c, camp, tmp = env
    r = _crear(c, [("ok1.png", _foto(1)), ("ok2.jpg", _jpg()), ("malo.png", b"no soy png"), ("ok3.png", _foto(3))])
    assert r.status_code == 400 and "malo.png" in r.get_data(as_text=True)
    _sin_residuos(camp)


def test_D2f_polyglot_jpeg_con_html_al_final_se_acepta_y_se_sirve_sin_nosniff_LIMITACION(env):
    """Un JPEG válido con un documento HTML pegado al final decodifica bien y se conserva
    byte a byte; se sirve como `image/jpeg` pero sin `X-Content-Type-Options: nosniff`."""
    c, camp, tmp = env
    poli = _jpg() + b"<html><script>alert(document.domain)</script></html>"
    cid = _cid(_crear(c, [("poli.jpg", poli)]))
    r = c.get(f"{BASE}/caso/{cid}/archivo/foto-1")
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.get_data() == poli
    assert "X-Content-Type-Options" not in r.headers


# ---- D3 · límites en su borde exacto ------------------------------------------------------------
class _Boom:
    """Un stream que explota si alguien lo lee: la validación de cantidad no debe leer nada."""
    def read(self, *_a):
        raise AssertionError("se leyó un archivo antes de validar la cantidad")


class _FS:
    def __init__(self, nombre, stream):
        self.filename, self.stream = nombre, stream


def test_D3_veintiuna_fotos_se_rechazan_sin_leer_ningun_byte_y_veinte_pasan():
    with pytest.raises(mu.UploadError, match="máximo por propiedad es 20"):
        mu.leer_fotos([_FS(f"f{i}.jpg", _Boom()) for i in range(21)])
    out = mu.leer_fotos([_FS(f"f{i}.jpg", io.BytesIO(b"x")) for i in range(20)])
    assert len(out) == 20


def test_D3b_borde_exacto_por_archivo_15_MiB_pasa_y_15_MiB_mas_uno_no():
    tope = mu.MAX_FOTO_MB * 1024 * 1024
    presupuesto = [mu.MAX_LOTE_MB * 1024 * 1024]
    assert len(mu.leer_limitado(io.BytesIO(b"x" * tope), tope, "a.jpg", presupuesto=presupuesto)) == tope
    with pytest.raises(mu.UploadError, match="pesa demasiado"):
        mu.leer_limitado(io.BytesIO(b"x" * (tope + 1)), tope, "b.jpg", presupuesto=[10 * tope])


def test_D3c_borde_exacto_del_lote_120_MiB_pasa_y_120_MiB_mas_uno_no(monkeypatch):
    monkeypatch.setattr(mu, "MAX_LOTE_MB", 2)
    monkeypatch.setattr(mu, "MAX_FOTO_MB", 2)
    lote = 2 * 1024 * 1024
    ok = mu.leer_fotos([_FS("a.jpg", io.BytesIO(b"x" * (lote // 2))), _FS("b.jpg", io.BytesIO(b"x" * (lote // 2)))])
    assert sum(len(b) for _n, b in ok) == lote
    with pytest.raises(mu.UploadError, match="El lote de fotos pesa demasiado"):
        mu.leer_fotos([_FS("a.jpg", io.BytesIO(b"x" * (lote // 2))),
                       _FS("b.jpg", io.BytesIO(b"x" * (lote // 2 + 1)))])


def test_D3d_la_lectura_se_corta_en_cuanto_se_pasa_no_al_final():
    """El stream de 1 GiB «infinito» no se lee entero: se corta apenas supera el tope."""
    leido = [0]

    class Infinito:
        def read(self, n):
            leido[0] += n
            return b"x" * n
    with pytest.raises(mu.UploadError):
        mu.leer_limitado(Infinito(), 1024 * 1024, "inf.jpg", presupuesto=[10 ** 9])
    assert leido[0] <= 1024 * 1024 + 2 * mu.CHUNK


def test_D3e_una_foto_de_exactamente_15_MiB_entra_por_la_web_y_una_de_15_MiB_mas_uno_no(env):
    c, camp, tmp = env
    tope = mu.MAX_FOTO_MB * 1024 * 1024
    assert _crear(c, [("tope.png", _png_con_relleno(tope))]).status_code == 303
    r = _crear(c, [("pasa.png", _png_con_relleno(tope + 1))], gt=_plano_real() + b"2")
    assert r.status_code == 400 and "pesa demasiado" in r.get_data(as_text=True)


def test_D3f_el_plano_real_pesa_hasta_25_MiB(env):
    c, camp, tmp = env
    tope = mu.MAX_PLANO_REAL_MB * 1024 * 1024
    assert _crear(c, [("f.png", _foto(1))], gt=_png_con_relleno(tope), gt_nombre="gt.png").status_code == 303
    r = _crear(c, [("f.png", _foto(2))], gt=_png_con_relleno(tope + 1), gt_nombre="gt.png")
    assert r.status_code == 400 and "pesa demasiado" in r.get_data(as_text=True)


def test_D3g_el_tope_total_del_envio_lo_corta_werkzeug_con_413(env):
    c, camp, tmp = env
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    cuerpo = b"x" * (mu.MAX_ENVIO_BYTES + 1024)
    r = c.post(f"{BASE}/crear", data={"fotos": (io.BytesIO(cuerpo), "enorme.jpg"),
                                      "plano_real": (io.BytesIO(b"x"), "g.png")},
               content_type="multipart/form-data")
    assert r.status_code == 413 and "demasiado grande" in r.get_data(as_text=True)
    _sin_residuos(camp)


# ---- D4 · bombas de descompresión -------------------------------------------------------------------
def test_D4_una_foto_que_declara_mas_de_80_millones_de_pixeles_se_rechaza_antes_de_decodificar(env):
    c, camp, tmp = env
    bomba = _png_dims(10000, 10000, "L")                   # 100 MP en pocos KB
    assert len(bomba) < 200_000
    r = _crear(c, [("bomba.png", bomba)])
    assert r.status_code == 400 and "resolución demasiado alta" in r.get_data(as_text=True)
    _sin_residuos(camp)


def test_D4b_mas_del_doble_del_tope_da_un_mensaje_equivocado_pero_igual_se_rechaza_LIMITACION(env):
    """Por encima de 2× `MAX_IMAGE_PIXELS` Pillow lanza `DecompressionBombError` al abrir: se
    informa «dañado» en vez de «resolución demasiado alta» (seguro, pero confuso)."""
    c, camp, tmp = env
    r = _crear(c, [("bomba.png", _png_dims(30000, 30000, "L"))])
    assert r.status_code == 400 and "dañado" in r.get_data(as_text=True)
    _sin_residuos(camp)


def test_D4c_el_lado_maximo_de_12000_px_se_aplica_aunque_los_pixeles_no_pasen(env):
    c, camp, tmp = env
    r = _crear(c, [("larga.png", _png_dims(13000, 100, "L"))])
    assert r.status_code == 400 and "resolución demasiado alta" in r.get_data(as_text=True)


_MEMORIA = r'''
import os, struct, sys, threading, time, zlib
sys.path.insert(0, %(raiz)r); sys.path.insert(0, %(raiz)r + "/src")
w, h = %(w)d, %(h)d
def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
comp = zlib.compressobj(9)
fila = b"\x00" + b"\x80" * w
datos = b"".join(comp.compress(fila) for _ in range(h)) + comp.flush()
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + chunk(b"IDAT", datos) + chunk(b"IEND", b"")
from webapp import mobile_upload as mu
import cv2, numpy as np
def rss():
    for linea in open("/proc/self/status"):
        if linea.startswith("VmRSS"):
            return int(linea.split()[1]) // 1024
antes, pico, vivo = rss(), 0, True
def muestrea():
    global pico
    while vivo:
        pico = max(pico, rss())
        time.sleep(0.002)
t = threading.Thread(target=muestrea); t.start()
mu.normalizar_foto("x.png", png)                     # lo que hace la web
img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)   # lo que hace E37 (add_asset)
vivo = False; t.join()
print(len(png), antes, pico)
'''


def test_D4d_una_foto_de_95_KB_que_pasa_los_topes_cuesta_cientos_de_MB_de_memoria_DEFECTO_H19():
    """Medido en un subproceso con RSS muestreado cada 2 ms (no `ru_maxrss`, que cuenta el pico de
    importar OpenCV): un PNG gris de 8900×8900 (79,2 MP, bajo el tope) pesa decenas de KB, se acepta,
    y entre la validación de Pillow y el `cv2.imread(IMREAD_COLOR)` de E37 el RSS sube más de 200 MB.
    Con `--threads 8`, varias cargas así a la vez multiplican esa cifra."""
    if not os.path.exists("/proc/self/status"):
        pytest.skip("mide el RSS con /proc (Linux, como el contenedor de Railway)")
    out = subprocess.run([sys.executable, "-c", _MEMORIA % {"raiz": ROOT, "w": 8900, "h": 8900}],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    nbytes, antes, pico = (int(x) for x in out.stdout.split())
    assert nbytes < 200_000
    assert pico - antes > 200, (antes, pico)


def test_D4e_la_bomba_que_CREAR_rechaza_MEJORAR_la_acepta_DEFECTO_H07(env):
    """E45.2 endureció sólo CREAR. Un plano de MEJORAR no pasa por `mobile_upload`: ni límite de
    píxeles, ni de lado, ni decodificación de comprobación. El mismo PNG de 10000×10000 (100 MP) se
    rechaza como plano real de CREAR (D4) y se acepta como plano de MEJORAR; el costo recae después en
    `assets._dims` (`cv2.imread`) y en el motor. Con 30000×30000 (≈1 MB, 900 MP) OpenCV pediría ~5 GB:
    NO se ejecuta aquí (podría matar el proceso); es riesgo plausible no reproducido en esa escala."""
    c, camp, tmp = env
    bomba = _png_dims(10000, 10000, "L")
    r_crear = _crear(c, [("f.png", _foto(1))], gt=bomba, gt_nombre="gt.png")
    assert r_crear.status_code == 400 and "resolución demasiado alta" in r_crear.get_data(as_text=True)
    r_mejorar = _subir_mejorar(c, bomba, "plano.png")
    assert r_mejorar.status_code == 303


def test_D4f_el_tope_de_pixeles_de_Pillow_queda_fijado_en_todo_el_proceso_LIMITACION(env):
    """`_abrir_imagen` asigna `Image.MAX_IMAGE_PIXELS` (global de Pillow) en cada llamada."""
    from PIL import Image
    c, camp, tmp = env
    original = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = 1
        _crear(c, [("f.png", _foto(1))])
        assert Image.MAX_IMAGE_PIXELS == mu.MAX_PIXELES
    finally:
        Image.MAX_IMAGE_PIXELS = original


def test_D4g_cada_foto_de_CREAR_paga_una_clasificacion_a_resolucion_completa_DEFECTO_H16(tmp_path):
    """`projects.add_asset` llama a `_looks_like_plan` → `classify.features`, que cuenta colores con
    `np.unique(..., axis=0)` sobre TODOS los píxeles (ordena 3 columnas × N filas): el costo crece más
    que linealmente con la resolución. Medido en esta máquina: ≈ 11–12 s por foto de 12 MP y 217 s
    para una carga de 20 fotos de 12 MP en UNA petición (ver REPORT). Aquí se fija la forma del costo
    con imágenes chicas, sin pasar de unos segundos."""
    import time
    import cv2
    import numpy as np
    from webapp.domain.potential import classify
    rng = np.random.default_rng(1)
    tiempos = {}
    for w, h in ((1000, 750), (2000, 1500)):
        img = rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)
        ruta = str(tmp_path / f"r{w}.png")
        cv2.imwrite(ruta, img)
        t = time.perf_counter()
        classify.features(ruta)
        tiempos[w * h] = time.perf_counter() - t
    assert tiempos[2000 * 1500] / tiempos[1000 * 750] > 2.5, tiempos      # 4× píxeles ⇒ >2,5× tiempo
    fuente = open(classify.__file__, encoding="utf-8").read()
    assert "np.unique(q, axis=0)" in fuente and "resize" not in fuente.split("def features")[1].split("def classify")[0]
    assert "_looks_like_plan(dest)" in open(os.path.join(ROOT, "webapp", "domain", "reconstruction",
                                                         "projects.py"), encoding="utf-8").read()


# ---- D5 · HEIC / HEIF -----------------------------------------------------------------------------
def test_D5_un_heic_se_convierte_a_jpg_y_la_web_nunca_sirve_el_original_heic(env):
    c, camp, tmp = env
    cid = _cid(_crear(c, [("IMG_1.HEIC", _heic(120, 80))]))
    r = c.get(f"{BASE}/caso/{cid}/archivo/foto-1")
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.get_data()[:3] == b"\xff\xd8\xff"
    assert not [g for g in _guardados(camp, tmp) if g.lower().endswith((".heic", ".heif"))]


def test_D5b_un_heic_grande_se_convierte_en_tiempo_razonable_y_con_la_orientacion(env):
    import time
    c, camp, tmp = env
    t = time.time()
    nombre, jpg = mu.normalizar_foto("grande.heic", _heic(4000, 3000, orientacion=6))
    assert nombre == "grande.jpg" and time.time() - t < 20
    from PIL import Image
    assert Image.open(io.BytesIO(jpg)).size == (3000, 4000)              # rotado una vez


def test_D5c_avif_con_extension_heic_se_rechaza_si_la_libheif_instalada_no_decodifica_AVIF(env):
    c, camp, tmp = env
    if pillow_heif.libheif_info().get("AVIF"):
        pytest.skip("esta libheif sí decodifica AVIF")
    falso_avif = b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00avifmif1miaf" + os.urandom(300)
    assert _crear(c, [("x.heic", falso_avif)]).status_code == 400
    _sin_residuos(camp)


def test_D5d_el_exif_de_un_jpeg_se_conserva_en_la_evidencia_pero_no_viaja_al_proveedor(env):
    """Privacidad: la evidencia guarda el JPEG original (con su EXIF/GPS) tal cual; la petición a
    OpenAI re-codifica la imagen y no lleva EXIF."""
    from PIL import Image
    c, camp, tmp = env
    ex = Image.Exif()
    ex[0x010F] = "MARCA-EXIF-UNICA"
    b = io.BytesIO()
    Image.new("RGB", (80, 60), (200, 10, 10)).save(b, "JPEG", exif=ex.tobytes())
    cid = _cid(_crear(c, [("gps.jpg", b.getvalue())]))
    ev = open(os.path.join(camp.case_dir(cid), "evidence", "foto_01.jpg"), "rb").read()
    assert b"MARCA-EXIF-UNICA" in ev
    from webapp.domain.reconstruction import engines, runs
    pid = camp.get(cid)["recon_project_id"]
    rid = runs.create_initial(pid, "motor_de_prueba", "e46", confirm_paid=True)
    cuerpo = engines.get("openai_direct").build_body(runs.build_request(runs.get(rid)))
    urls = [p["image_url"] for m in cuerpo["input"] for p in m["content"] if p.get("type") == "input_image"]
    assert urls and all(b"MARCA-EXIF-UNICA" not in base64.b64decode(u.split(",", 1)[1]) for u in urls)


# ---- D6 · lotes y bordes del formulario ------------------------------------------------------------------
def test_D6_la_misma_foto_dos_veces_en_un_lote_deja_dos_assets_en_el_manifiesto_y_uno_en_E37_LIMITACION(env):
    c, camp, tmp = env
    foto = _foto(7)
    cid = _cid(_crear(c, [("a.png", foto), ("b.png", foto), ("c.png", _foto(8))]))
    from webapp.domain.reconstruction import projects
    assert len(camp.get(cid)["assets"]) == 3
    assert len(projects.assets_of(camp.get(cid)["recon_project_id"])) == 2
    assert camp.materials_ok(camp.get(cid))


def test_D6b_sin_fotos_o_sin_plano_real_o_con_partes_vacias(env):
    c, camp, tmp = env
    assert c.post(f"{BASE}/crear", data={"plano_real": (io.BytesIO(_plano_real()), "g.png")},
                  content_type="multipart/form-data").status_code == 400
    assert c.post(f"{BASE}/crear", data={"fotos": (io.BytesIO(_foto(1)), "a.png")},
                  content_type="multipart/form-data").status_code == 400
    # el navegador manda una parte vacía (nombre vacío) cuando no se eligió nada
    assert c.post(f"{BASE}/crear", data={"fotos": (io.BytesIO(b""), ""), "plano_real": (io.BytesIO(b""), "")},
                  content_type="multipart/form-data").status_code == 400
    assert c.post(f"{BASE}/crear", data={"fotos": (io.BytesIO(b""), "vacia.png"),
                                         "plano_real": (io.BytesIO(_plano_real()), "g.png")},
                  content_type="multipart/form-data").status_code == 400
    _sin_residuos(camp)


def test_D6c_las_dos_pistas_no_aceptan_el_campo_de_la_otra(env):
    c, camp, tmp = env
    r = c.post(f"{BASE}/mejorar", data={"plano": (io.BytesIO(_plano_de_galeria()), "p.png"),
                                       "plano_real": (io.BytesIO(_plano_real()), "gt.png")},
               content_type="multipart/form-data")
    assert r.status_code == 303 and camp.get(_cid(r))["track"] == "IMPROVE"
    assert [a["role"] for a in camp.get(_cid(r))["assets"]] == ["published_plan"]
    assert camp.get(_cid(r))["has_ground_truth"] is False


@pytest.mark.parametrize("m2,esperado", [
    ("120", 120.0), ("120,5", 120.5), ("1e5", 100000.0), (" 85 ", 85.0), ("١٢٠", 120.0), ("1_0", 10.0),
    ("0", None), ("-1", None), ("nan", None), ("inf", None), ("1e400", None), ("1e6", None),
    ("120 m2", None), ("abc", None), ("0x10", None), ("", "vacio")])
def test_D6d_los_m2_publicados(env, m2, esperado):
    c, camp, tmp = env
    r = _crear(c, [("f.png", _foto(1))], m2=m2)
    if esperado is None:
        assert r.status_code == 400 and "m²" in r.get_data(as_text=True)
    else:
        caso = camp.get(_cid(r))
        assert caso["published_m2"] == (None if esperado == "vacio" else esperado)


def test_D6e_la_referencia_enlace_o_texto_se_clasifica_trunca_y_escapa(env):
    c, camp, tmp = env
    cid = _cid(_crear(c, [("f.png", _foto(1))], referencia="https://portal.cl/aviso/9"))
    assert camp.get(cid)["source_urls"] == ["https://portal.cl/aviso/9"] and camp.get(cid)["declared"] == {}
    cid2 = _cid(_crear(c, [("f.png", _foto(2))], gt=_plano_real() + b"1",
                       referencia="<script>alert(1)</script>" + "x" * 3000))
    caso = camp.get(cid2)
    assert caso["source_urls"] == [] and len(caso["declared"]["description"]) == 2000
    pagina = _html(c, f"{BASE}/caso/{cid2}")
    assert "<script>alert(1)</script>" not in pagina
    # un texto con un email o un teléfono se rechaza; un enlace con ellos, no (H09)
    r = _crear(c, [("f.png", _foto(3))], gt=_plano_real() + b"2", referencia="llamar a ana@casa.cl")
    assert r.status_code == 400 and "email o teléfono" in r.get_data(as_text=True)
    r = _crear(c, [("f.png", _foto(4))], gt=_plano_real() + b"3",
               referencia="http://usuario:clave@portal.cl/aviso/4?tel=912345678")
    assert r.status_code == 303


def test_D6f_los_errores_reflejan_el_nombre_del_archivo_escapado(env):
    c, camp, tmp = env
    r = _crear(c, [("<img src=x onerror=alert(1)>.exe", _jpg())])
    cuerpo = r.get_data(as_text=True)
    assert r.status_code == 400 and "<img src=x onerror" not in cuerpo and "&lt;img src=x" in cuerpo


# ---- D7 · MEJORAR: el lado de la carga que E45.2 no tocó -----------------------------------------------
@pytest.mark.parametrize("nombre,blob", [
    ("a.pdf", b"%PDF-1.4 basura sin estructura"), ("b.png", b"\x89PNG\r\n\x1a\n" + b"x" * 50),
    ("c.jpg", b"\xff\xd8\xff" + b"x" * 50), ("d.pdf", None)])
def test_D7_MEJORAR_acepta_archivos_con_la_cabecera_correcta_aunque_esten_rotos_DEFECTO_H07(env, nombre, blob):
    """La validación de MEJORAR es `sniff_ok`: 8 bytes de cabecera. Un PDF sin páginas, un PNG o un
    JPEG truncados entran como caso CAPTURED; la falla aparece después, registrada en
    `improve_started` y mostrada como NECESITA REVISIÓN (no se pierde ni se inventa un resultado)."""
    c, camp, tmp = env
    blob = blob if blob is not None else _pdf_sin_paginas()
    r = _subir_mejorar(c, blob, nombre)
    cid = _cid(r)                                                  # entra
    assert camp.status(camp.get(cid)) == camp.CAPTURED
    # El texto del fallo lleva rutas con ids aleatorios; de forma esporádica (≈ 1 de cada 20) una racha
    # de ≥ 9 dígitos dispara el detector de PII y el POST da 409 sin registrar nada (DEFECTO E46-H21,
    # ver `test_e46_adv_resilience.py::test_E11c`): se reintenta hasta que el id no la contenga.
    for _intento in range(15):
        codigo = c.post(f"{BASE}/caso/{cid}/procesar").status_code
        assert codigo in (303, 409)
        if codigo == 303:
            break
    assert codigo == 303
    assert [e["kind"] for e in camp.events(cid)] == ["improve_started"]
    assert camp.events(cid)[0]["data"]["error"]                    # el motivo queda escrito
    assert "NECESITA REVISIÓN" in _html(c, f"{BASE}/caso/{cid}")


@pytest.mark.parametrize("nombre,blob,ok", [
    ("p.png", _plano_de_galeria(), True), ("p.jpg", _jpg(), True), ("p.jpeg", _jpg(), True),
    ("p.pdf", _pdf_valido(), True), ("p.webp", _webp(), False), ("p.heic", _heic(), False),
    ("p.png", _jpg(), False), ("p.pdf", _plano_de_galeria(), False),
    ("p.svg", b"<svg/>", False), ("p", _plano_de_galeria(), False)])
def test_D7b_matriz_de_extension_y_contenido_de_MEJORAR(env, nombre, blob, ok):
    c, camp, tmp = env
    assert _subir_mejorar(c, blob, nombre).status_code == (303 if ok else 400)


def test_D7b2_un_plano_de_MEJORAR_vacio_se_rechaza(env):
    c, camp, tmp = env
    r = c.post(f"{BASE}/mejorar", data={"plano": (io.BytesIO(b""), "p.png")},
               content_type="multipart/form-data")
    assert r.status_code == 400 and camp.load()["cases"] == []


def test_D7c_mejorar_exige_un_unico_plano(env):
    c, camp, tmp = env
    r = c.post(f"{BASE}/mejorar", data={}, content_type="multipart/form-data")
    assert r.status_code == 400
    r = c.post(f"{BASE}/mejorar", data={"plano": [(io.BytesIO(_plano_de_galeria()), "a.png"),
                                                 (io.BytesIO(_plano_de_galeria()), "b.png")]},
               content_type="multipart/form-data")
    assert r.status_code == 303 and len(camp.load()["cases"]) == 1      # el segundo archivo se ignora
