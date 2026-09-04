"""E13 — tests del sistema de validación comercial.

No se testea el motor: E13 no lo toca. Se testea exactamente lo que puede hacer que el experimento
mienta (§51): que el cegado sea correcto, que el material no filtre nada, que la geometría sea la de
E07 sin una coordenada movida, que el esquema atrape capturas inconsistentes, que la scorecard
calcule lo que dice calcular, y que los HTML funcionen sin red."""
import json
import os
import re

import pytest

from escalimetro.validation import blind, schema as S
from escalimetro.validation.boards import (blind_board, load_handoffs, reveal_board, strip_chrome,
                                           visible_text)
from escalimetro.validation.forms import form_html, scorecard_html
from escalimetro.validation.scorecard import THRESHOLDS, compute, load_csv

ROOT = os.path.dirname(os.path.dirname(__file__))
CASE = os.path.join(ROOT, "cases", "001_gps_403")
E13 = os.path.join(CASE, "validation", "E13")
FIX = os.path.join(ROOT, "tests", "fixtures", "validation", "SYNTHETIC_TEST_ONLY_responses.csv")
EXPECTED_HASH = {"A": "df6b86058ebb", "B": "5c5c276923dd", "C": "e12cc722485b"}


@pytest.fixture(scope="module")
def rows():
    return load_csv(open(FIX, encoding="utf-8").read())


# ---------------------------------------------------------------------------------------------------
# cegado y randomización
# ---------------------------------------------------------------------------------------------------
def test_el_mapping_ciego_es_una_biyeccion():
    for i in range(12):
        mp = blind.mapping_for(i)
        assert sorted(mp) == ["X", "Y", "Z"]
        assert sorted(mp.values()) == ["A", "B", "C"]
        inv = blind.inverse_mapping_for(i)
        assert all(inv[v] == k for k, v in mp.items())


def test_se_usan_las_seis_permutaciones_no_cinco():
    """Con cinco órdenes el sesgo de posición no se cancela; ver blind.py."""
    assert len(blind.ORDERS) == 6
    assert len(set(blind.ORDERS)) == 6


def test_cada_alternativa_ocupa_cada_posicion_el_mismo_numero_de_veces():
    assert all(v == [2, 2, 2] for v in blind.position_balance(6).values())
    assert all(v == [4, 4, 4] for v in blind.position_balance(12).values())
    # con las cinco permutaciones del prompt original el balance NO se cumple
    five = [o for o in blind.ORDERS if o != ("C", "B", "A")]
    cnt = {a: [0, 0, 0] for a in "ABC"}
    for o in five:
        for pos, alt in enumerate(o):
            cnt[alt][pos] += 1
    assert any(v != [len(five) / 3] * 3 for v in cnt.values())


def test_el_orden_se_registra_para_poder_auditar_el_sesgo():
    assert blind.display_order_label(0).startswith("SET 1 · ")
    assert blind.display_order_label(6) == blind.display_order_label(0)


@pytest.mark.parametrize("i", [-1, -5])
def test_indice_negativo_es_error(i):
    with pytest.raises(ValueError):
        blind.order_for(i)


# ---------------------------------------------------------------------------------------------------
# fugas — lo que el evaluador NO puede ver (§4, §36)
# ---------------------------------------------------------------------------------------------------
def test_la_lamina_ciega_no_nombra_las_estrategias():
    txt = visible_text(blind_board(CASE, 0))
    for term in ("EFICIENTE", "BALANCEADO", "COLABORATIVO", "OPTION A", "OPTION B", "OPTION C"):
        assert term not in txt
    assert "OPTION X" in txt and "OPTION Y" in txt and "OPTION Z" in txt


def test_la_lamina_ciega_no_filtra_ia_ni_puntajes_internos():
    assert blind.leaks(visible_text(blind_board(CASE, 0))) == []


@pytest.mark.parametrize("i", range(6))
def test_ninguna_rotacion_filtra(i):
    assert blind.leaks(visible_text(blind_board(CASE, i))) == []


def test_el_formulario_no_filtra_nada_al_evaluador():
    assert blind.leaks(form_html()) == []


def test_la_lamina_revelada_si_nombra_las_estrategias():
    """Es su propósito: se muestra DESPUÉS de la evaluación ciega."""
    txt = visible_text(reveal_board(CASE))
    for name in ("A EFICIENTE", "B BALANCEADO", "C COLABORATIVO"):
        assert name in txt


def test_las_metricas_visibles_son_identicas_entre_las_tres_opciones():
    """Si un número difiere entre opciones, es un canal de fuga sobre cuál es cuál."""
    txt = visible_text(blind_board(CASE, 0))
    assert txt.count("40 / 40") == 3 and txt.count("16 / 16") == 3 and txt.count("completo") == 3


# ---------------------------------------------------------------------------------------------------
# geometría — E13 no dibuja plantas (§7, §50)
# ---------------------------------------------------------------------------------------------------
def _geom(svg: str):
    """Primitivas de geometría, sin texto: es lo que no puede cambiar."""
    return re.findall(r'<(?:polygon|rect|circle|line|path)[^>]*>', svg)


def test_la_lamina_usa_la_geometria_exacta_de_e07():
    h = load_handoffs(CASE)
    board = blind_board(CASE, 0)
    for alt in ("A", "B", "C"):
        body, _, _ = strip_chrome(h[alt]["svg"]["commercial_base"])
        prims = _geom(body)
        assert len(prims) > 100, alt
        for p in prims:
            assert p in board, f"{alt}: primitiva de E07 ausente o alterada en la lámina"


def test_strip_chrome_solo_quita_el_pie_no_la_planta():
    h = load_handoffs(CASE)
    src = h["A"]["svg"]["commercial_base"]
    body, _, _ = strip_chrome(src)
    assert "A EFICIENTE" not in body and "OFICINA 403" not in body
    assert "ACCESO" in body                                   # el acceso es planta, no pie
    # toda primitiva del ÁREA DE PLANTA sobrevive; lo único que se pierde es el pie (barra de escala)
    def plan_prims(svg):
        out = []
        for line in svg.splitlines():
            m = re.search(r'\sy(?:1)?="([\d.]+)"', line)
            if m and float(m.group(1)) >= 1060:
                continue
            out += _geom(line)
        return out
    assert plan_prims(body) == plan_prims(src)
    assert len(_geom(src)) - len(_geom(body)) == 1            # sólo la barra de escala del pie


def test_los_hashes_de_geometria_no_cambiaron():
    g = json.load(open(os.path.join(CASE, "ai", "E09", "geometry_hash_check.json"), encoding="utf-8"))
    assert g["identical"] is True
    for a, pref in EXPECTED_HASH.items():
        assert g["geometry_hash_before"][a].startswith(pref)
        assert g["geometry_hash_before"][a] == g["geometry_hash_after"][a]


# ---------------------------------------------------------------------------------------------------
# esquema de captura
# ---------------------------------------------------------------------------------------------------
def test_el_csv_nace_vacio(tmp_path):
    csv = S.empty_csv()
    assert csv.strip() == S.HEADER
    assert "SYNTHETIC" not in csv and "R01" not in csv


def test_el_csv_entregado_esta_vacio():
    txt = open(os.path.join(E13, "broker_validation_responses.csv"), encoding="utf-8").read()
    assert txt.strip() == S.HEADER, "el CSV de captura no puede traer respuestas inventadas"


def test_el_esquema_no_pide_datos_personales():
    for forbidden in ("name", "email", "phone", "company", "nombre", "correo", "telefono"):
        assert not any(forbidden in c for c in S.COLUMNS)


def test_el_fixture_sintetico_esta_marcado(rows):
    assert all(r["respondent_id"].startswith("SYNTHETIC_TEST_ONLY") for r in rows)


def test_el_fixture_sintetico_es_valido(rows):
    assert S.validate_rows(rows) == []


def test_detecta_vocabulario_invalido(rows):
    bad = [dict(r) for r in rows]
    bad[0]["send_to_client"] = "TAL_VEZ"
    assert any("send_to_client" in e for e in S.validate_rows(bad))


def test_detecta_campos_por_evaluador_inconsistentes(rows):
    bad = [dict(r) for r in rows]
    bad[1]["preferred_option"] = "Z" if bad[1]["preferred_option"] != "Z" else "X"
    assert any("preferred_option' inconsistente" in e for e in S.validate_rows(bad))


def test_detecta_un_evaluador_sin_sus_tres_filas(rows):
    assert any("se esperan 3" in e for e in S.validate_rows([dict(r) for r in rows][:-1]))


def test_confidence_fuera_de_rango(rows):
    bad = [dict(r) for r in rows]
    bad[0]["confidence"] = "7"
    assert any("confidence" in e for e in S.validate_rows(bad))


# ---------------------------------------------------------------------------------------------------
# scorecard
# ---------------------------------------------------------------------------------------------------
def test_sin_datos_no_hay_veredicto():
    m = compute([])
    assert m["gate_result"] == "INSUFFICIENT_DATA"
    assert m["layout_gate"]["result"] == "INSUFFICIENT_DATA"
    assert m["product_gate"]["result"] == "INSUFFICIENT_DATA"


def test_calculos_sobre_el_fixture_sintetico(rows):
    m = compute(rows, "COMMERCIAL")
    assert m["n_respondents"] == 5 and m["n_commercial_total"] == 5
    assert m["send_rate_preferred"] == 80.0          # 4 de 5
    assert m["conf4_rate_preferred"] == 80.0
    assert m["change_ok_rate_preferred"] == 80.0
    assert (m["worst_shared_blocker"], m["worst_shared_blocker_rate"]) == ("RECEPTION", 20.0)


def test_los_dos_gates_son_independientes(rows):
    """El fixture está construido para que uno pase y el otro no: si se contaminaran, este test cae."""
    m = compute(rows, "COMMERCIAL")
    assert m["layout_gate"]["result"] == "PASS"
    assert m["product_gate"]["result"] == "FAIL"
    assert m["gate_result"] == "FAIL"
    assert [c["status"] for c in m["product_gate"]["checks"]] == ["PASS", "PASS", "FAIL", "PASS"]


def test_el_send_rate_se_mide_sobre_la_preferida_no_sobre_al_menos_una(rows):
    """El agujero que se cerró: 'al menos una de tres' infla el gate sin que ninguna sea enviable."""
    m = compute(rows, "COMMERCIAL")
    at_least_one = sum(1 for rid in {r["respondent_id"] for r in rows if r["role"] != "ARCHITECT"}
                       if any(r["send_to_client"] == "YES"
                              for r in rows if r["respondent_id"] == rid))
    assert at_least_one == 4                       # coincide aquí, pero no es la métrica del gate
    assert m["send_rate_preferred"] == 80.0
    assert "preferida" in m["layout_gate"]["checks"][1]["check"]


def test_ninguna_cuenta_como_no_enviable(rows):
    mod = [dict(r) for r in rows]
    for r in mod:
        if r["respondent_id"].endswith("R01"):
            r["preferred_option"] = "NONE"
    assert compute(mod, "COMMERCIAL")["send_rate_preferred"] == 60.0


def test_los_arquitectos_no_entran_en_el_segmento_comercial(rows):
    assert compute(rows, "ARCHITECT")["n_respondents"] == 1
    assert compute(rows, "ALL")["n_respondents"] == 6
    assert compute(rows, "COMMERCIAL")["n_respondents"] == 5


def test_muestra_insuficiente_no_produce_pass(rows):
    few = [r for r in rows if r["respondent_id"] <= "SYNTHETIC_TEST_ONLY_R03"]
    m = compute(few, "COMMERCIAL")
    assert m["n_respondents"] == 3
    assert m["gate_result"] == "INSUFFICIENT_DATA"


def test_clasificacion_por_alternativa_sin_puntajes_de_ia(rows):
    m = compute(rows, "COMMERCIAL")
    for a in ("A", "B", "C"):
        assert m["per_alternative"][a]["classification"] in (
            "BROKER_READY", "BORDERLINE", "REJECTED", "NO_DATA")


def test_los_umbrales_estan_fijados_y_documentados():
    assert THRESHOLDS["G1_SEND_PREFERRED"] == 0.70
    assert THRESHOLDS["G4_CHANGE_OK"] == 0.70
    assert THRESHOLDS["MIN_RESPONDENTS"] == 5 and THRESHOLDS["MIN_COMMERCIAL"] == 4
    proto = open(os.path.join(ROOT, "docs", "BROKER_VALIDATION_PROTOCOL.md"), encoding="utf-8").read()
    assert "no se modifican después de ver resultados" in proto


# ---------------------------------------------------------------------------------------------------
# HTML offline (§32, §34, §54)
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["BROKER_VALIDATION_FORM.html", "BROKER_VALIDATION_SCORECARD.html",
                                  "ESCALIMETRO_BROKER_VALIDATION_PACK.html"])
def test_los_html_funcionan_sin_red(name):
    h = open(os.path.join(E13, name), encoding="utf-8").read()
    assert "<script src=" not in h and "<link rel=\"stylesheet\"" not in h
    for remote in ("http://", "cdn.", "googleapis", "unpkg", "jsdelivr"):
        assert remote not in h, f"{name} referencia {remote}"
    for img in re.findall(r'<img[^>]*src="([^"]+)"', h):
        assert img.startswith("data:"), f"{name}: imagen no incrustada"


def test_el_pack_trae_las_siete_secciones():
    h = open(os.path.join(E13, "ESCALIMETRO_BROKER_VALIDATION_PACK.html"), encoding="utf-8").read()
    for anchor in ("instr", "blind", "form", "reveal", "script", "proto", "score"):
        assert f'id="{anchor}"' in h


def test_la_scorecard_entregada_no_trae_resultados():
    h = open(os.path.join(E13, "BROKER_VALIDATION_SCORECARD.html"), encoding="utf-8").read()
    assert "INSUFFICIENT_DATA — aún no hay entrevistas" in h
    assert "SYNTHETIC" not in h


def test_el_formulario_y_la_scorecard_comparten_vocabulario():
    f, s = form_html(), scorecard_html()
    for d in S.DEFECTS:
        assert d in f and d in s
    for c in S.CHANGE_MAGNITUDE:
        assert c in f, c
    for c in S.CHANGE_OK:                    # los que la scorecard necesita nombrar para contar
        assert c in s, c


# ---------------------------------------------------------------------------------------------------
# paridad entre las dos implementaciones del cálculo
# ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("segment", ["COMMERCIAL", "ALL"])
def test_el_javascript_de_la_scorecard_calcula_lo_mismo_que_python(rows, segment):
    """Hay dos implementaciones —Python para los tests, JS para el archivo que usa el entrevistador—
    y tienen que dar el mismo número. Si divergen, el informe y la pantalla dirían cosas distintas."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    import pathlib
    txt = open(FIX, encoding="utf-8").read()
    py = compute(rows, segment)
    page_path = pathlib.Path(os.path.join(E13, "BROKER_VALIDATION_SCORECARD.html")).resolve()
    errs = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(page_path.as_uri())
            js = pg.evaluate("([t,s])=>compute(parseCSV(t),s)", [txt, segment])
            b.close()
    except Exception as exc:                                   # noqa: BLE001
        pytest.skip(f"navegador no disponible: {exc}")
    assert errs == []
    assert js["n"] == py["n_respondents"]
    for k in ("send_rate_preferred", "conf4_rate_preferred", "change_ok_rate_preferred",
              "pain_rate", "frequency_rate", "would_use_rate", "share_rate", "distinctness_rate",
              "worst_shared_blocker", "worst_shared_blocker_rate"):
        assert js[k] == pytest.approx(py[k]) if isinstance(py[k], float) else js[k] == py[k], k
    assert js["layout"]["result"] == py["layout_gate"]["result"]
    assert js["product"]["result"] == py["product_gate"]["result"]
    assert js["gate"] == py["gate_result"]
