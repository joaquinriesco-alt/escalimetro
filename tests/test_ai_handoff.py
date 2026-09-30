"""M01 — el sistema de handoff no puede desincronizarse en silencio.

El repo es la memoria operacional entre ChatGPT y Claude (D-003). Eso sólo vale si lo que dice es
cierto y está completo. Estos tests no miden producto: impiden las tres formas en que un sistema
así se pudre sin que nadie lo note — una TASK que nunca tuvo REPORT, un enlace que apunta a un
archivo que ya no existe, y una decisión reemplazada por otra que no está escrita.

Se ejecutan con la suite normal. No requieren red, ni base de datos, ni servidor.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI = os.path.join(ROOT, "docs", "ai-development")
TASKS = os.path.join(ROOT, "tasks")
REPORTS = os.path.join(ROOT, "reports")

CORE_DOCS = ("PRODUCT_DOCTRINE.md", "CURRENT_STATE.md", "DEVELOPMENT_PROTOCOL.md", "DECISIONS.md")
REPORT_STATUSES = ("PASS", "PARTIAL", "BLOCKED", "DECISION_REQUIRED")
TASK_SECTIONS = ("Decisión aprobada", "Problema", "Contexto canónico", "Resultado esperado",
                 "No hacer", "Acceptance criteria", "Evidencia requerida", "Decision gates")
REPORT_SECTIONS = ("Status", "Qué cambió", "Tests", "Acceptance criteria", "Evidencia",
                   "Regresiones", "Limitaciones", "Decisiones requeridas", "Commit / branch / PR",
                   "Exact next action")


def _leer(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


def _secciones(texto: str):
    return {m.group(1).strip() for m in re.finditer(r"^##\s+(.+?)\s*$", texto, re.M)}


def _ids(carpeta: str, sufijo: str):
    if not os.path.isdir(carpeta):
        return set()
    return {f[: -len(sufijo)] for f in os.listdir(carpeta) if f.endswith(sufijo)}


def _todos_los_md():
    out = [os.path.join(ROOT, "CLAUDE.md")]
    for carpeta in (AI, TASKS, REPORTS):
        if os.path.isdir(carpeta):
            out += [os.path.join(carpeta, f) for f in sorted(os.listdir(carpeta)) if f.endswith(".md")]
    return out


# ===================================================================================================
# 1 — la estructura existe
# ===================================================================================================
def test_existen_los_documentos_canonicos():
    for d in CORE_DOCS:
        assert os.path.isfile(os.path.join(AI, d)), d
    assert os.path.isfile(os.path.join(ROOT, "CLAUDE.md"))
    assert os.path.isdir(TASKS) and os.path.isdir(REPORTS)


def test_claude_md_lleva_a_la_doctrina_y_al_estado():
    """CLAUDE.md es lo que se carga solo al abrir el repo. Si no apunta a lo canónico, el traspaso
    automático no traspasa nada y alguien vuelve a tener que pegar el contexto."""
    t = _leer(os.path.join(ROOT, "CLAUDE.md"))
    for d in ("CURRENT_STATE.md", "PRODUCT_DOCTRINE.md", "DEVELOPMENT_PROTOCOL.md"):
        assert d in t, d
    assert "DECISION_REQUIRED" in t and "main" in t


def test_la_doctrina_nombra_el_core():
    t = _leer(os.path.join(AI, "PRODUCT_DOCTRINE.md"))
    assert "CREAR PLANO" in t and "MEJORAR PLANO" in t


# ===================================================================================================
# 2 — toda TASK termina en un REPORT
# ===================================================================================================
def _tarea_actual() -> str:
    """El ID de la TASK en curso según CURRENT_STATE, o '' si no hay ninguna."""
    t = _leer(os.path.join(AI, "CURRENT_STATE.md"))
    m = re.search(r"^## Tarea actual\s*\n+(.+?)(?:\n## |\Z)", t, re.M | re.S)
    if not m:
        return ""
    ids = re.findall(r"\*\*([ME]\d+(?:\.\d+)?)\*\*", m.group(1))
    return ids[0] if ids else ""


def test_toda_task_tiene_su_report_salvo_la_que_esta_en_curso():
    """La forma más común de que este sistema se pudra: una tarea que se hizo y nunca se reportó.
    La única excepción legítima es la que está en curso, y tiene que estar nombrada como tal."""
    tareas, reportes = _ids(TASKS, ".md"), _ids(REPORTS, "_REPORT.md")
    en_curso = _tarea_actual()
    sin_reporte = sorted(tareas - reportes - {en_curso})
    assert not sin_reporte, f"TASKs sin REPORT: {sin_reporte}"


def test_no_hay_reports_huerfanos():
    huerfanos = sorted(_ids(REPORTS, "_REPORT.md") - _ids(TASKS, ".md"))
    assert not huerfanos, f"REPORTs sin TASK: {huerfanos}"


@pytest.mark.parametrize("tid", sorted(_ids(TASKS, ".md")))
def test_cada_task_tiene_las_secciones_del_formato(tid):
    faltan = [s for s in TASK_SECTIONS
              if s not in _secciones(_leer(os.path.join(TASKS, f"{tid}.md")))]
    assert not faltan, f"{tid}: faltan {faltan}"


@pytest.mark.parametrize("tid", sorted(_ids(REPORTS, "_REPORT.md")))
def test_cada_report_tiene_status_valido_y_sus_secciones(tid):
    t = _leer(os.path.join(REPORTS, f"{tid}_REPORT.md"))
    faltan = [s for s in REPORT_SECTIONS if s not in _secciones(t)]
    assert not faltan, f"{tid}: faltan {faltan}"
    m = re.search(r"^## Status\s*\n+\s*\**([A-Z_]+)", t, re.M)
    assert m and m.group(1) in REPORT_STATUSES, f"{tid}: status inválido"


def test_el_estado_nombra_la_ultima_tarea_y_esa_tarea_tiene_report():
    """Cerrar una TASK sin actualizar CURRENT_STATE deja al siguiente agente leyendo un estado
    viejo. Se exige que la última tarea nombrada ahí tenga su REPORT."""
    t = _leer(os.path.join(AI, "CURRENT_STATE.md"))
    m = re.search(r"^## Última tarea completada\s*\n+(.+?)(?:\n## |\Z)", t, re.M | re.S)
    assert m, "CURRENT_STATE no tiene «Última tarea completada»"
    ids = re.findall(r"\*\*([ME]\d+(?:\.\d+)?)\*\*", m.group(1))
    assert ids, "la sección no nombra ninguna tarea"
    assert ids[0] in _ids(REPORTS, "_REPORT.md"), f"{ids[0]} no tiene REPORT"


# ===================================================================================================
# 3 — los enlaces apuntan a algo
# ===================================================================================================
@pytest.mark.parametrize("ruta", _todos_los_md(), ids=lambda r: os.path.relpath(r, ROOT))
def test_los_enlaces_relativos_resuelven(ruta):
    """Un enlace roto en el estado canónico es peor que ningún enlace: el siguiente agente lo sigue,
    no encuentra nada y tiene que adivinar."""
    t = _leer(ruta)
    base = os.path.dirname(ruta)
    rotos = []
    for destino in re.findall(r"\]\(([^)\s]+)\)", t):
        if destino.startswith(("http://", "https://", "#", "mailto:")):
            continue
        archivo = destino.split("#")[0]
        if archivo and not os.path.exists(os.path.normpath(os.path.join(base, archivo))):
            rotos.append(destino)
    assert not rotos, f"enlaces rotos: {rotos}"


# ===================================================================================================
# 4 — las decisiones son coherentes
# ===================================================================================================
def _decisiones():
    return re.findall(r"^###\s+(D-\d{3})\b", _leer(os.path.join(AI, "DECISIONS.md")), re.M)


def test_los_ids_de_decision_son_unicos():
    ds = _decisiones()
    assert ds and len(ds) == len(set(ds)), ds


def test_toda_decision_reemplazada_apunta_a_una_que_existe():
    """«SUPERSEDED BY D-042» cuando D-042 no existe deja una decisión muerta sin reemplazo."""
    existentes = set(_decisiones())
    for md in _todos_los_md() + [os.path.join(ROOT, "README.md"),
                                 os.path.join(ROOT, "docs", "PRODUCT_V1_SCOPE.md"),
                                 os.path.join(ROOT, "docs", "PRODUCT_BOUNDARY.md")]:
        for ref in re.findall(r"SUPERSEDED BY (D-\d{3})", _leer(md)):
            assert ref in existentes, f"{os.path.relpath(md, ROOT)} cita {ref}, que no existe"


def test_cada_decision_cita_su_origen():
    """Si no se puede citar de dónde salió, no es una decisión: es una suposición con número."""
    t = _leer(os.path.join(AI, "DECISIONS.md"))
    bloques = re.split(r"^###\s+", t, flags=re.M)[1:]
    for b in bloques:
        assert "**Origen:**" in b, b.splitlines()[0]


def test_los_documentos_reemplazados_lo_dicen():
    """Un documento que contradice la doctrina vigente y no lo avisa se lee como vigente."""
    for doc in ("docs/PRODUCT_V1_SCOPE.md", "docs/PRODUCT_BOUNDARY.md"):
        assert "SUPERSEDED BY D-001" in _leer(os.path.join(ROOT, doc)).split("\n## ")[0], doc


# ===================================================================================================
# 5 — el estado de las ramas se declara contra el remoto (M01.1)
# ===================================================================================================
def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def test_el_main_declarado_es_el_de_origin_no_el_local():
    """M01 declaró `main` en E16.1 y «107 commits atrás» leyendo la rama local `main`, que llevaba
    trece commits de retraso porque `origin/main` se había movido con pushes desde otras ramas.
    La ref remota ya tenía el valor correcto; nadie la miró. Este test compara contra
    `refs/remotes/origin/main`, la vista más fresca del remoto sin salir a la red, y nunca contra
    `refs/heads/main`. Si falla: `git fetch origin` y reverificar (protocolo §9.1).

    Si el commit que escribió este estado ya está dentro de `origin/main`, `main` se movió por el
    merge de este mismo trabajo y el estado quedó como historia: no es un error."""
    t = _leer(os.path.join(AI, "CURRENT_STATE.md"))
    m = re.search(r"^\|\s*`main`\s*\|\s*`([0-9a-f]{7,40})`", t, re.M)
    assert m, "CURRENT_STATE no declara la punta de `main` en la tabla de ramas"
    declarado = m.group(1)
    try:
        remoto = _git("rev-parse", "--verify", "-q", "refs/remotes/origin/main")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("sin refs/remotes/origin/main: este checkout no conoce el remoto")
    if remoto.startswith(declarado):
        return
    try:
        escrito_en = _git("log", "-1", "--format=%H", "--", "docs/ai-development/CURRENT_STATE.md")
        ya_mergeado = subprocess.run(
            ["git", "-C", ROOT, "merge-base", "--is-ancestor", escrito_en, remoto]).returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        ya_mergeado = False
    assert ya_mergeado, (f"CURRENT_STATE declara main={declarado}, pero origin/main={remoto[:7]}. "
                         "Verificar contra el remoto, no contra la rama local.")


# ===================================================================================================
# 6 — el repo es público
# ===================================================================================================
def test_el_handoff_no_filtra_secretos():
    """DR-2: el repo es público. Lo que se escribe acá lo puede leer cualquiera. Se reutilizan los
    patrones de valor de `scripts/secret_scan.py` en vez de escribir otros."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_sscan_patterns", os.path.join(ROOT, "scripts", "secret_scan.py"))
    fuente = _leer(os.path.join(ROOT, "scripts", "secret_scan.py"))
    bloque = fuente.split("TEXT_EXT")[0]                       # sólo los patrones, sin ejecutar el escaneo
    ns: dict = {}
    exec(compile("import re\n" + bloque.split("import os, re, subprocess, sys", 1)[1],
                 "secret_scan_patterns", "exec"), ns)
    for md in _todos_los_md():
        t = _leer(md)
        for nombre, patron in ns["VALUE_PATTERNS"]:
            assert not patron.search(t), f"{os.path.relpath(md, ROOT)}: parece un {nombre}"
