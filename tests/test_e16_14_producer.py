"""E16.14 — el productor propone 1..N regiones. UNA variable: el productor.

El contrato de E16.13.1 queda congelado y protegido por `scope_guard`, igual que E16.13.1 congeló el
productor: si alguien toca el juez, la evidencia estructural, la pista o aguas abajo, el primer test
de este módulo falla y nombra la función.

Los fixtures P1–P12 NO declaran el candidato: entregan dibujo, huella y pista, y el productor tiene
que proponer. Las expectativas se escribieron antes de implementar; las desviaciones medidas están
declaradas una por una en `DESVIACIONES`, con su causa, y ningún test las convierte en verde."""
import json
import os
import subprocess

import ast

import cv2
import numpy as np
import pytest

from escalimetro.generalization import scope_guard as SG
from escalimetro.geometry import core_geometry as CG
from escalimetro.geometry import core_producer as CP

ROOT = os.path.dirname(os.path.dirname(__file__))
FX = os.path.join(ROOT, "tests", "fixtures", "core_producer")
SRC = os.path.join(ROOT, "src", "escalimetro")
BASE = "6c5142d"          # E16.13.1: contrato vigente

#: expectativa declarada en el JSON del fixture, escrita ANTES de implementar
def _meta(n):
    return json.load(open(os.path.join(FX, n + ".json"), encoding="utf-8"))


#: Desviaciones MEDIDAS, con su causa. No se "arreglan" moviendo la expectativa: quedan aquí, y el
#: informe del ciclo las reporta como lo que son.
DESVIACIONES = {
    "P1_SINGLE_COMPACT": "propone 2 regiones en vez de 1: una pieza de mobiliario entra porque el "
                         "mapa de muros congelado la admite como muro a esta escala de lámina",
    "P12_NARROW_REAL_STRUCTURE": "la pieza angosta SÍ se conserva (lo que el fixture prueba), pero "
                                 "entra además una pieza de mobiliario por la misma razón que P1",
    "P6_OVERBROAD_HINT": "con la pista abarcando casi la planta, una oficina cerrada encadenada por "
                         "mobiliario entra como región: precisión 0,51",
    "P8_FACADE_TOUCH": "la pieza pegada al perímetro se fusiona con la envolvente y la exclusión de "
                       "envolvente la descarta: recall 0,51. El contrato lo rechaza",
    "P10_AMBIGUOUS_TWO_CLUSTERS": "no hay abstención: propone los cuatro bloques de los dos grupos y "
                                  "el contrato los acepta. Falso positivo declarado",
    "P11_NO_RELIABLE_STRUCTURE": "no hay abstención del productor: la significancia es relativa y con "
                                 "sólo mobiliario el propio ruido pasa a ser la referencia. El "
                                 "contrato sí rechaza (CORE_REJECTED_IMPLAUSIBLE)",
}
EXACTOS = ["P2_TWO_COMPONENT_CORE", "P3_THREE_COMPONENT_CORE", "P4_PARTIAL_CLUSTER_TRAP",
           "P5_UNRELATED_CLOSED_ROOM", "P7_OPEN_FLOOR_SEPARATION", "P9_NOISE_AND_WATERMARK"]


def _codigo(path):
    """El fuente SIN docstrings: lo que se audita es lo que el módulo hace, no lo que explica."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def _fx(n):
    img = cv2.imread(os.path.join(FX, n + ".png"))
    meta = _meta(n)
    fp = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(fp, [np.array(meta["footprint_ring"], np.int32)], 255)
    return img, fp, meta


def _core(n):
    img, fp, meta = _fx(n)
    return CG.core_from_hint(img, fp, tuple(meta["hint_region"]))


def _hay_base():
    return subprocess.run(["git", "-C", ROOT, "cat-file", "-e", BASE + "^{commit}"],
                          capture_output=True).returncode == 0


# ---------------------------------------------------------------------------------------------------
# 0 · LA FRONTERA INVERTIDA: el productor no puede editar el examen
# ---------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not _hay_base(), reason="la base E16.13.1 no está en este clon")
def test_el_contrato_la_evidencia_y_aguas_abajo_no_cambiaron():
    igual, hashes, cambios = SG.compare(BASE, ROOT)
    assert igual, f"E16.14 sólo puede mover el productor; cambió: {cambios}"
    for ambito, (antes, ahora) in hashes.items():
        assert antes == ahora, ambito


def test_el_productor_no_lee_el_veredicto_del_contrato():
    """§16: prohibido el lazo cerrado. El productor propone una vez; no consulta aceptación ni
    completitud, y no las puede consultar porque no las importa. Reutiliza UNA constante congelada
    —la definición de ancla significativa de E16.11— y eso no es leer un veredicto: es usar una
    definición ya calibrada en vez de inventar un tamaño mínimo propio."""
    src = _codigo(os.path.join(SRC, "geometry", "core_producer.py"))
    for prohibido in ("accept_core", "CORE_ACCEPTANCE", "evaluate_completeness", "overall_status",
                      "CORE_ACCEPTED", "mass_coverage", "fabricated", "while "):
        assert prohibido not in src, prohibido
    assert "COMPLETENESS_CONTRACT[" in src and "significant_min_ratio" in src
    build = open(os.path.join(SRC, "geometry", "core_geometry.py"), encoding="utf-8").read()
    i = build.index("def build_core"); j = build.index("\ndef ", i + 1)
    for prohibido in ("accept_core", "evaluate_completeness", "overall_status"):
        assert prohibido not in build[i:j], prohibido


# ---------------------------------------------------------------------------------------------------
# 1 · el productor propone 1..N y la cantidad sale de la evidencia
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", EXACTOS)
def test_las_clases_limpias_dan_exactamente_las_regiones_del_dibujo(nombre):
    c = _core(nombre)
    assert c.metrics["components"] == _meta(nombre)["expected"], (nombre, c.metrics["components"])
    assert c.metrics["structural_components_selected"] == c.metrics["components"]
    assert c.metrics["structural_components_discovered"] > c.metrics["components"], \
        "descubrir tiene que ver más piezas de las que selecciona; si no, no está seleccionando"


def test_dos_bloques_separados_no_se_unen_con_un_puente():
    """P7: la franja de circulación entre las dos piezas no puede quedar dentro del candidato."""
    c = _core("P7_OPEN_FLOOR_SEPARATION")
    x0, y0, x1, y1 = _meta("P7_OPEN_FLOOR_SEPARATION")["gap_box"]
    assert c.metrics["components"] == 2
    assert int((c.mask[y0:y1, x0:x1] > 0).sum()) == 0, "hay geometría fabricada en la circulación"


def test_no_gana_la_componente_mayor():
    """P4: una pieza domina en superficie y las otras dos son legítimas. La regla de E16.10 habría
    devuelto una sola región."""
    c = _core("P4_PARTIAL_CLUSTER_TRAP")
    assert c.metrics["components"] == 3
    areas = c.metrics["component_areas_px"]
    assert max(areas) > 3 * min(areas), "el fixture debe tener una pieza claramente dominante"


def test_un_recinto_ordinario_del_alcance_no_es_nucleo():
    """P5: la sala cerrada está dentro del alcance semántico y no entra, porque su celda supera el
    tope de ancla congelado: una sala no es un ancla."""
    c = _core("P5_UNRELATED_CLOSED_ROOM")
    assert c.metrics["components"] == 2
    for r in c.components:
        cx, cy = np.array(r).mean(0)
        assert not (980 < cx < 1240 and 620 < cy < 840), "entró el recinto ajeno"


def test_una_pieza_angosta_con_recinto_cerrado_no_se_filtra_por_chica():
    """P12: el shaft angosto se conserva. (Que además entre una pieza de mobiliario está declarado
    en DESVIACIONES y se comprueba abajo.)"""
    c = _core("P12_NARROW_REAL_STRUCTURE")
    cajas = _meta("P12_NARROW_REAL_STRUCTURE")["truth_boxes"]
    x0, y0, x1, y1 = cajas[1]
    dentro = [r for r in c.components
              if x0 - 20 < np.array(r).mean(0)[0] < x1 + 20 and y0 - 20 < np.array(r).mean(0)[1] < y1 + 20]
    assert dentro, "la pieza angosta desapareció"


def test_la_marca_de_agua_y_el_mobiliario_no_se_vuelven_regiones():
    c = _core("P9_NOISE_AND_WATERMARK")
    assert c.metrics["components"] == 2
    assert c.metrics["structural_components_discovered"] >= 20, "el fixture tiene mucha tinta ajena"


def test_no_se_absorbe_la_envolvente_del_piso():
    """P8: la pieza toca el perímetro. Pase lo que pase con esa pieza, el candidato NO puede volverse
    la planta entera."""
    c = _core("P8_FACADE_TOUCH")
    assert c.metrics["footprint_frac"] < 0.35
    assert any("envolvente" in r["why"] for r in c.metrics["rejected_components"])


# ---------------------------------------------------------------------------------------------------
# 2 · desviaciones declaradas: medidas, no maquilladas
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", sorted(DESVIACIONES))
def test_las_desviaciones_declaradas_siguen_siendo_las_declaradas(nombre):
    """Si una desviación cambia de forma, este test lo dice en vez de dejarla pasar como 'la conocida'."""
    c = _core(nombre)
    esperado = _meta(nombre)["expected"]
    if esperado == "ABSTAIN":
        assert c.metrics.get("components", 0) > 0, "si empezara a abstenerse, hay que actualizar"
        if nombre == "P11_NO_RELIABLE_STRUCTURE":
            assert not c.accepted, "sin estructura fiable el contrato tiene que rechazar"
    elif nombre == "P8_FACADE_TOUCH":
        # aquí la desviación no es una región de más sino recall parcial: la pieza pegada al
        # perímetro se fusiona con la envolvente y queda descartada por la exclusión de envolvente.
        assert c.metrics["components"] == esperado
        assert not c.accepted, "el contrato tiene que rechazar este candidato"
    else:
        assert c.metrics["components"] == esperado + 1, (nombre, c.metrics["components"])


def test_el_recall_de_las_clases_limpias_es_total():
    """Ninguna región legítima se pierde en las clases sin ruido: es la mitad que E16.10 no tenía."""
    for nombre in ("P2_TWO_COMPONENT_CORE", "P3_THREE_COMPONENT_CORE", "P4_PARTIAL_CLUSTER_TRAP"):
        img, fp, meta = _fx(nombre)
        c = CG.core_from_hint(img, fp, tuple(meta["hint_region"]))
        for x0, y0, x1, y1 in meta["truth_boxes"]:
            caja = np.zeros(fp.shape[:2], bool)
            caja[y0:y1, x0:x1] = True
            cubierta = float(((c.mask > 0) & caja).sum()) / float(caja.sum())
            assert cubierta > 0.7, (nombre, cubierta)


# ---------------------------------------------------------------------------------------------------
# 3 · traza y procedencia
# ---------------------------------------------------------------------------------------------------
def test_cada_descarte_queda_con_su_motivo():
    c = _core("P5_UNRELATED_CLOSED_ROOM")
    assert c.metrics["rejected_components"], "descartar en silencio no es auditable"
    for r in c.metrics["rejected_components"]:
        assert r["why"] and "structural_px" in r and "scope_overlap" in r


def test_la_version_del_productor_viaja_en_las_metricas():
    c = _core("P2_TWO_COMPONENT_CORE")
    assert c.metrics["producer_version"].startswith("core-producer/2.")
    assert CP.PRODUCER_VERSION != "core-producer/1.0.0"


def test_no_hay_ninguna_distancia_en_el_criterio_de_pertenencia():
    """§11: la proximidad no define pertenencia. Ninguna constante de distancia en el productor."""
    src = _codigo(os.path.join(SRC, "geometry", "core_producer.py"))
    for prohibido in ("LINK_FRAC", "link_frac", "dist", "proximity", "cercan", "hypot", "norm("):
        assert prohibido not in src, prohibido


def test_las_anclas_no_afirman_circulacion_vertical():
    src = _codigo(os.path.join(SRC, "geometry", "core_producer.py")).lower()
    for falso in ("ascensor", "elevator", "escalera", "stair", "vertical_circulation"):
        assert falso not in src, falso
