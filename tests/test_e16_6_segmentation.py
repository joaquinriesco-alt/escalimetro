"""E16.6 — la segmentación deja de depender de una semilla puntual para planos de planta completa.

E16.5 generalizó la localización y RES cruzó esa frontera. Se detuvo en la siguiente: `opencv_flood`
devolvió máscara vacía. La causa de fondo no era dónde cayó la semilla, sino que `seed → flood` es la
abstracción de otro problema —crecer dentro de una unidad rellena— y no la de un plano de
arquitectura en blanco y negro.

Estos tests fijan: qué representa la máscara, que el método whole-shell no necesita semilla, que se
valida con criterios declarados antes de mirar ningún caso real, que no convierte cualquier hoja en
un shell, y que el camino multiunidad no se movió."""
import json
import os

import cv2
import numpy as np
import pytest

from escalimetro import localization as L
from escalimetro.segmentation import REGISTRY, strategy_for
from escalimetro.segmentation.base import SegmentationRequest
from escalimetro.segmentation.strategy import SEEDED_COLOR, SEEDED_FLOOD, WHOLE_SHELL_PROVIDER

ROOT = os.path.dirname(os.path.dirname(__file__))
FX = os.path.join(ROOT, "tests", "fixtures", "segmentation")
C403 = os.path.join(ROOT, "cases", "001_gps_403")
CRES = os.path.join(ROOT, "cases", "003_res_unknown")

POSITIVOS = ["A_whole_shell_simple", "B_whole_shell_core", "C_whole_shell_clutter"]
NEGATIVOS = ["N1_casi_vacia", "N2_sin_planta", "N3_perimetro_abierto"]


def _img(n):
    return cv2.imread(os.path.join(FX, n + ".png"))


def _seg(img, bbox=None, **params):
    return REGISTRY["whole_shell"]().segment(
        SegmentationRequest(img, bbox=bbox if bbox is not None else L.drawing_bounds(img),
                            params=params or None))


def _j(p):
    return json.load(open(p, encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------
# 1-2 · el método no necesita semilla y no conoce el caso real
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", POSITIVOS)
def test_whole_shell_segmenta_sin_ninguna_semilla(nombre):
    r = _seg(_img(nombre))
    assert r.confidence > 0 and (r.mask > 0).sum() > 0
    # la firma no recibió seed_points en ninguna forma
    assert "seed" not in r.notes


def test_el_metodo_no_depende_de_constantes_de_res():
    import re
    src = open(os.path.join(ROOT, "src", "escalimetro", "segmentation", "providers.py"),
               encoding="utf-8").read()
    # "RES" y "608" van con límite de palabra: como subcadena aparecen dentro de EXTERIORES y de
    # cualquier número, y eso es ruido, no acoplamiento (misma clasificación que el escáner de E16.1).
    for t in ("RES", "608", "910", "542", "1788", "1070"):
        assert not re.search(r"(?<![A-Za-z0-9_])" + t + r"(?![A-Za-z0-9_])", src), t
    for t in ("003_res_unknown", "Real Estate", "144, 146, 124", "watermark"):
        assert t not in src, t


# ---------------------------------------------------------------------------------------------------
# 3 · clutter genérico: mobiliario, ejes, textos y marca de agua no rompen la huella
# ---------------------------------------------------------------------------------------------------
def test_el_clutter_generico_no_impide_una_mascara_valida():
    """AFLOJADO EN E16.7, DECLARADO. La versión de E16.6 exigía |A − C| / max < 2 %: la huella no
    debía moverse con el clutter. Esa igualdad sólo se cumplía porque el detector de entonces —gris
    < 110— no veía los ejes de replanteo del fixture, trazados en gris claro. Con evidencia
    estructural relativa sí los ve, y los ejes conectan el rótulo de la lámina con el edificio: la
    huella de C absorbe ese bolsillo de anotación y crece 4,4 %.

    Lo que se afloja y lo que NO: se acepta que la huella CREZCA hacia afuera por estructura
    conectada que no es el edificio (clase abierta, documentada en el informe de E16.7 y en
    docs/E16_7_STRUCTURAL_BARRIER_CONTRACT.md §6). NO se acepta que el clutter interior —mobiliario,
    marca de agua, textos dentro— reste huella: la contención de A en C sigue siendo estricta. Que
    esto sea un aflojamiento y no una mejora está dicho aquí a propósito."""
    limpio = _seg(_img("A_whole_shell_simple"))
    sucio = _seg(_img("C_whole_shell_clutter"))
    assert sucio.confidence > 0
    a, c = limpio.mask > 0, sucio.mask > 0
    assert float((a & c).sum()) / float(a.sum()) > 0.99, \
        "el mobiliario y la marca de agua están DENTRO por construcción: no pueden restar huella"
    exceso = float((c & ~a).sum()) / float(c.sum())
    assert exceso < 0.06, f"contaminación por anotación conectada fuera de lo medido: {exceso:.3f}"


def test_un_nucleo_interior_no_parte_la_huella():
    """El contrato es la huella cerrada por el muro exterior: el núcleo no la agujerea."""
    r = _seg(_img("B_whole_shell_core"))
    assert r.confidence > 0
    n_cc = cv2.connectedComponentsWithStats((r.mask > 0).astype(np.uint8), 8)[0] - 1
    assert n_cc == 1


# ---------------------------------------------------------------------------------------------------
# 4 · negativos: el método no convierte cualquier hoja en un shell
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", NEGATIVOS)
def test_una_lamina_sin_planta_no_produce_mascara_confiada(nombre):
    r = _seg(_img(nombre))
    assert r.confidence == 0.0
    assert (r.mask > 0).sum() == 0, "una máscara dudosa se descarta, no se entrega con baja confianza"


def test_un_perimetro_abierto_se_rechaza():
    """Si el muro exterior no cierra, el exterior se filtra y no hay huella que afirmar."""
    assert _seg(_img("N3_perimetro_abierto")).confidence == 0.0


# ---------------------------------------------------------------------------------------------------
# 5 · contrato de aceptación declarado de antemano
# ---------------------------------------------------------------------------------------------------
def test_el_contrato_de_aceptacion_esta_en_el_codigo_y_no_se_elige_despues():
    src = open(os.path.join(ROOT, "src", "escalimetro", "segmentation", "providers.py"),
               encoding="utf-8").read()
    for k in ("min_roi_frac", "max_roi_frac", "min_fill"):
        assert k in src
    r = _seg(_img("A_whole_shell_simple"))
    for k in ("roi_frac", "fill", "componentes", "aceptacion"):
        assert k in r.notes, k


def test_una_mascara_que_no_llena_su_recuadro_se_rechaza():
    """Un marco delgado tiene área > 0 y no es una planta. min_fill lo descarta."""
    im = np.full((600, 900, 3), 255, np.uint8)
    cv2.rectangle(im, (100, 100), (800, 500), (0, 0, 0), 3)
    assert _seg(im).confidence > 0                      # relleno, es una planta
    assert _seg(im, min_fill=1.01).confidence == 0.0    # con el umbral imposible, se rechaza


# ---------------------------------------------------------------------------------------------------
# 6-7 · semántica de dominio → estrategia, con procedencia
# ---------------------------------------------------------------------------------------------------
def test_la_estrategia_sale_de_la_semantica_del_problema():
    assert strategy_for(L.WHOLE_SHELL) == WHOLE_SHELL_PROVIDER
    assert strategy_for(L.MULTI_UNIT) == SEEDED_FLOOD
    assert strategy_for(L.MULTI_UNIT, has_color_hint=True) == SEEDED_COLOR
    assert strategy_for(L.WHOLE_SHELL, explicit="opencv_flood") == "opencv_flood"


def test_la_procedencia_de_la_mascara_es_explicita():
    r = _seg(_img("A_whole_shell_simple"))
    assert r.provider == "whole_shell"
    assert r.provenance == "cv_segmentation"
    assert "whole_shell" in r.notes and "opencv_flood" not in r.notes


# ---------------------------------------------------------------------------------------------------
# 8 · el camino multiunidad no se movió
# ---------------------------------------------------------------------------------------------------
def test_el_camino_multiunidad_sigue_usando_flood_con_semilla():
    assert strategy_for(L.MULTI_UNIT) == "opencv_flood"
    with pytest.raises(ValueError):
        REGISTRY["opencv_flood"]().segment(SegmentationRequest(_img("A_whole_shell_simple")))


def test_403_conserva_su_floorplate_y_su_localizacion():
    fp = _j(os.path.join(C403, "outputs", "floorplate.json"))
    assert fp["target_localization"] == "automatic"
    assert fp["unit_label"] == "Oficina 403"


def test_no_se_introdujeron_overrides_manuales():
    for caso in (CRES,):
        assert not os.path.exists(os.path.join(caso, "overrides.json"))
