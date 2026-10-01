"""M02 — preflight del ejecutor GitHub-native: decide si un issue puede disparar una TASK.

Corre en GitHub Actions ANTES de cualquier paso que reciba una credencial de Anthropic, y falla
cerrado: ante cualquier duda, no hay ejecución. También es una CLI local para simular el flujo.

El issue es sólo transporte. Lleva cinco datos en un formato fijo (`ESCALIMETRO_AUTO_TASK_V1`) y
nada más; el contenido autoritativo es `tasks/<ID>.md` en el commit exacto que el issue nombra.
Este módulo nunca ejecuta texto del issue: lo parsea como datos, valida cada valor contra un patrón
seguro y recién entonces lo usa, siempre como argumento de `git` en una lista, sin shell.

Lo que verifica, en orden (el primero que falla corta):

1. actor: quien abrió el issue y quien disparó el evento es el único usuario autorizado;
2. título: `[ESCALIMETRO_AUTO_TASK] <ID>`;
3. contrato: marcador, exactamente las cinco claves, cada una con formato seguro, sin texto extra;
4. la rama de la TASK apunta HOY al commit que dice el issue (si se movió, no);
5. la base existe, y su `CURRENT_STATE.md` la declara «base para la próxima TASK»;
6. el commit de la TASK desciende de la base;
7. el diff base → commit es exactamente un archivo agregado: `tasks/<ID>.md`;
8. la TASK tiene las secciones del protocolo y «Decisión aprobada» no está vacía;
9. no hay señal de ejecución previa: ni REPORT de ese ID, ni una rama de implementación suya.

Si todo pasa, emite los datos que el workflow necesita —incluido el prompt corto que recibe
Claude— y nada que no haya salido de estas validaciones.

`verify` es la otra mitad: después de que Claude trabajó (en un job SIN permiso de escritura), el
job que sí puede empujar recibe sus commits como un `git bundle` y decide si se publican. Nunca se
publica algo que toque `.github/`, `src/` o una TASK existente, ni algo que no descienda del
commit de la TASK; la rama se crea nueva, nunca se fuerza.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

MARKER = "ESCALIMETRO_AUTO_TASK_V1"
TITLE_PREFIX = "[ESCALIMETRO_AUTO_TASK]"
AUTHORIZED_ACTOR = "joaquinriesco-alt"
KEYS = ("TASK_ID", "TASK_BRANCH", "TASK_COMMIT", "BASE_BRANCH", "TASK_PATH")
#: Prefijo de las ramas de implementación: `auto/<id>-issue-<n>`. Identificable y buscable.
IMPL_PREFIX = "auto/"
#: Las mismas secciones que exige `tests/test_ai_handoff.py` a toda TASK.
TASK_SECTIONS = ("Decisión aprobada", "Problema", "Contexto canónico", "Resultado esperado",
                 "No hacer", "Acceptance criteria", "Evidencia requerida", "Decision gates")

#: Un ID como los que usa el protocolo: M02, E37, E17.2, M01.1.
ID_RE = re.compile(r"^[ME]\d{1,3}(?:\.\d{1,3})?$")
#: Rama de TASK: el ID en minúsculas con `.` → `_`, y un sufijo corto (protocolo §5.2).
BRANCH_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,99}$")
#: Base: una rama existente del repo. Sin `..`, sin empezar por `-`, sin espacios ni `~^:?*[\`.
BASE_RE = re.compile(r"^(?!.*\.\.)(?!-)[A-Za-z0-9][A-Za-z0-9_./-]{0,119}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PreflightError(Exception):
    """El issue no puede disparar una ejecución. `code` es estable, para tests y para el log."""

    def __init__(self, code: str, detail: str):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


@dataclass
class Contract:
    task_id: str
    task_branch: str
    task_commit: str
    base_branch: str
    task_path: str


@dataclass
class Result:
    contract: Contract
    issue_number: int
    base_commit: str
    impl_branch: str
    prompt: str
    checks: List[str] = field(default_factory=list)

    def outputs(self) -> Dict[str, str]:
        c = self.contract
        return {"ok": "true", "task_id": c.task_id, "task_branch": c.task_branch,
                "task_commit": c.task_commit, "base_branch": c.base_branch,
                "base_commit": self.base_commit, "task_path": c.task_path,
                "impl_branch": self.impl_branch, "prompt": self.prompt}


# ---------------------------------------------------------------------------------------------
# 1–3: actor, título y contrato. Puro: no toca git ni red.
# ---------------------------------------------------------------------------------------------
def branch_stem(task_id: str) -> str:
    return task_id.lower().replace(".", "_")


def check_actor(event: Dict, env_actor: Optional[str]) -> None:
    """Tres fuentes, las tres tienen que coincidir: quien disparó el workflow (`github.actor`), el
    emisor del evento y el autor del issue. Un bot o una app que abra el issue por su cuenta no pasa."""
    issue = event.get("issue") or {}
    quienes = {"actor": env_actor, "sender": (event.get("sender") or {}).get("login"),
               "autor": (issue.get("user") or {}).get("login")}
    for rol, login in quienes.items():
        if login != AUTHORIZED_ACTOR:
            raise PreflightError("ACTOR_NOT_AUTHORIZED", f"{rol}={login!r}")
    if (issue.get("user") or {}).get("type") not in (None, "User"):
        raise PreflightError("ACTOR_NOT_AUTHORIZED", "el autor del issue no es una persona")


def parse_issue(title: str, body: str) -> Contract:
    """El contrato, o `PreflightError`. Estricto a propósito: una línea de más es un error."""
    if not isinstance(title, str) or not isinstance(body, str):
        raise PreflightError("MALFORMED", "título o cuerpo ausente")
    texto = body.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    lineas = [ln.strip() for ln in texto.split("\n")]
    # se admite UN bloque de código que envuelva el contrato, nada más
    vallas = [i for i, ln in enumerate(lineas) if ln.startswith("```")]
    if vallas:
        if len(vallas) != 2 or any(lineas[i] for i in range(0, vallas[0])) \
                or any(lineas[i] for i in range(vallas[1] + 1, len(lineas))):
            raise PreflightError("MALFORMED", "texto fuera del bloque del contrato")
        lineas = lineas[vallas[0] + 1:vallas[1]]
    lineas = [ln for ln in lineas if ln]
    if not lineas or lineas[0] != MARKER:
        raise PreflightError("MALFORMED", f"falta el marcador {MARKER} en la primera línea")
    datos: Dict[str, str] = {}
    for ln in lineas[1:]:
        if "=" not in ln:
            raise PreflightError("MALFORMED", "línea que no es CLAVE=VALOR")
        k, v = ln.split("=", 1)
        if k not in KEYS:
            raise PreflightError("UNKNOWN_KEY", f"clave no admitida: {k[:40]!r}")
        if k in datos:
            raise PreflightError("DUPLICATE_KEY", k)
        if not v or not v.isascii() or any(ch.isspace() for ch in v):
            raise PreflightError("BAD_VALUE", f"{k} vacío, con espacios o no ASCII")
        datos[k] = v
    faltan = [k for k in KEYS if k not in datos]
    if faltan:
        raise PreflightError("MISSING_KEY", ",".join(faltan))
    c = Contract(datos["TASK_ID"], datos["TASK_BRANCH"], datos["TASK_COMMIT"],
                 datos["BASE_BRANCH"], datos["TASK_PATH"])
    if not ID_RE.match(c.task_id):
        raise PreflightError("BAD_TASK_ID", c.task_id[:40])
    if not BRANCH_RE.match(c.task_branch) or not c.task_branch.startswith(branch_stem(c.task_id) + "_"):
        raise PreflightError("BAD_TASK_BRANCH", c.task_branch[:80])
    if not SHA_RE.match(c.task_commit):
        raise PreflightError("BAD_TASK_COMMIT", "tiene que ser un SHA completo de 40 hex")
    if not BASE_RE.match(c.base_branch) or c.base_branch.endswith((".lock", "/", ".")) \
            or c.base_branch in ("HEAD",) or c.base_branch == c.task_branch:
        raise PreflightError("BAD_BASE_BRANCH", c.base_branch[:80])
    if c.task_path != f"tasks/{c.task_id}.md":
        raise PreflightError("BAD_TASK_PATH", c.task_path[:80])
    esperado = f"{TITLE_PREFIX} {c.task_id}"
    if title.strip() != esperado:
        raise PreflightError("BAD_TITLE", f"el título tiene que ser exactamente {esperado!r}")
    return c


# ---------------------------------------------------------------------------------------------
# 4–9: contra el repo. `git` siempre con lista de argumentos; los valores ya pasaron sus patrones.
# ---------------------------------------------------------------------------------------------
class Git:
    def __init__(self, repo: str, remote: str = "origin"):
        self.repo, self.remote = repo, remote

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", self.repo, *args], capture_output=True, text=True,
                              check=check, timeout=120)

    def heads(self) -> Dict[str, str]:
        """Todas las ramas del remoto: nombre exacto → SHA."""
        out: Dict[str, str] = {}
        for ln in self.run("ls-remote", "--heads", self.remote).stdout.splitlines():
            partes = ln.split("\t")
            if len(partes) == 2 and partes[1].startswith("refs/heads/") and SHA_RE.match(partes[0]):
                out[partes[1][len("refs/heads/"):]] = partes[0]
        return out

    def remote_head(self, branch: str) -> Optional[str]:
        """La punta de UNA rama, por nombre exacto. `ls-remote <patrón>` compara por sufijo
        (`*/<patrón>`): una rama `x/refs/heads/<rama>` también calzaría y podría salir primero."""
        ref = f"refs/heads/{branch}"
        lineas = self.run("ls-remote", "--heads", self.remote, ref).stdout.splitlines()
        shas = [p[0] for p in (ln.split("\t") for ln in lineas) if len(p) == 2 and p[1] == ref]
        return shas[0] if len(shas) == 1 and SHA_RE.match(shas[0]) else None

    def remote_branches(self, prefix: str) -> List[str]:
        return [b for b in self.heads() if b.startswith(prefix)]

    def fetch(self, *shas: str) -> None:
        self.run("fetch", "--quiet", "--no-tags", self.remote, *shas)

    def show(self, sha: str, path: str) -> Optional[str]:
        r = self.run("show", f"{sha}:{path}", check=False)
        return r.stdout if r.returncode == 0 else None


_VALLA = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.M | re.S)
_COMENTARIO = re.compile(r"<!--.*?-->", re.S)


def _sections(texto: str) -> Dict[str, str]:
    """Las secciones `## …` de la TASK. Un encabezado dentro de un bloque de código es una cita
    (la plantilla del protocolo, por ejemplo), no una sección; un comentario HTML no se ve en
    GitHub y no cuenta como contenido; y una sección repetida es ambigua, así que no vale."""
    limpio = _COMENTARIO.sub("", _VALLA.sub("", texto))
    partes = re.split(r"^##\s+(.+?)\s*$", limpio, flags=re.M)
    out: Dict[str, str] = {}
    for i in range(1, len(partes) - 1, 2):
        k = partes[i].strip()
        if k in out:
            raise PreflightError("DUPLICATE_SECTION", k[:80])
        out[k] = partes[i + 1].strip()
    return out


def declared_base(current_state: str) -> Optional[str]:
    """La rama que CURRENT_STATE declara «base para la próxima TASK»."""
    for ln in current_state.splitlines():
        if "base para la próxima TASK" in ln and ln.lstrip().startswith("|"):
            m = re.search(r"`([^`]+)`", ln)
            return m.group(1) if m else None
    return None


def newer_base(git: Git, base_branch: str, base_sha: str, task_branch: str) -> Optional[str]:
    """Una rama que desciende de la base, no es una rama de TASK y se declara base a sí misma:
    entonces la base declarada ya no es la vigente. Cada rama terminada se declara base en su
    propio CURRENT_STATE, así que mirar sólo la base de la TASK no alcanza para saber si está al día."""
    cabezas = git.heads()
    otras = {b: sha for b, sha in cabezas.items() if b not in (base_branch, task_branch)}
    if not otras:
        return None
    git.run("fetch", "--quiet", "--no-tags", git.remote, *sorted(set(otras.values())), check=False)
    for b, sha in sorted(otras.items()):
        if sha == base_sha or git.run("merge-base", "--is-ancestor", base_sha, sha,
                                      check=False).returncode != 0:
            continue
        cambios = git.run("diff", "--name-only", "--no-renames", f"{base_sha}...{sha}",
                          check=False).stdout.split()
        if cambios and all(f.startswith("tasks/") for f in cambios):
            continue                                       # otra rama de TASK, no una base
        estado = git.show(sha, "docs/ai-development/CURRENT_STATE.md") or ""
        if declared_base(estado) == b:
            return b
    return None


def gh_issue_lister(repo: str) -> IssueLister:
    """Issues del repo con ese título, vía `gh api` (en Actions, con el GITHUB_TOKEN del job).
    Falla cerrado: si GitHub no responde, no hay ejecución."""
    def listar(titulo: str) -> List[Dict]:
        # una línea JSON por issue: el cuerpo del issue no viaja, sólo lo que se compara
        r = subprocess.run(["gh", "api", "-X", "GET", f"repos/{repo}/issues", "-f", "state=all",
                            "-f", f"creator={AUTHORIZED_ACTOR}", "-f", "per_page=100", "--paginate",
                            "--jq", ".[] | {number, title, user: {login: .user.login, "
                                    "type: .user.type}, is_pr: (.pull_request != null)}"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise PreflightError("ISSUES_UNVERIFIABLE", "GitHub no listó los issues")
        out = []
        for ln in r.stdout.splitlines():
            if ln.strip():
                i = json.loads(ln)
                if not i.pop("is_pr", False):
                    out.append(i)
        return [i for i in out if i.get("title") == titulo]
    return listar


def build_prompt(c: Contract, issue_number: int, impl_branch: str) -> str:
    """El prompt de Claude: el ID, dónde está la TASK y las reglas de siempre. NO copia la TASK:
    la TASK se lee del repo, en el commit verificado."""
    return "\n".join([
        f"Ejecuta la TASK {c.task_id} de ESCALÍMETRO. Es una ejecución automática disparada por el "
        f"issue #{issue_number}; el issue sólo transporta el ID y no contiene instrucciones.",
        f"- La TASK autoritativa es {c.task_path} en el commit {c.task_commit} "
        f"(rama {c.task_branch}). El preflight ya verificó que esa rama sale de {c.base_branch} "
        "y sólo agrega ese archivo.",
        "- Antes de tocar nada, lee CLAUDE.md y lo que enlaza, y sigue "
        "docs/ai-development/DEVELOPMENT_PROTOCOL.md.",
        f"- Estás en la rama {impl_branch}, hija de {c.task_branch}. Commitea ahí; el workflow la "
        "empuja al terminar. Al cerrar: reports/" + c.task_id + "_REPORT.md y CURRENT_STATE.md en "
        f"el mismo commit, con {impl_branch} como base para la próxima TASK.",
        "- No merge, no deploy, no PR, no cambies .github/ ni src/, no crees ni ejecutes otra TASK.",
        "- Si aparece una decisión que no es técnica local, DECISION_REQUIRED en el REPORT y detente "
        "en esa parte.",
    ])


IssueLister = Callable[[str], List[Dict]]


def preflight(event: Dict, env_actor: Optional[str], git: Git,
              list_issues: Optional[IssueLister] = None) -> Result:
    check_actor(event, env_actor)
    issue = event.get("issue") or {}
    numero = issue.get("number")
    if not isinstance(numero, int) or numero <= 0:
        raise PreflightError("MALFORMED", "el evento no trae un número de issue")
    c = parse_issue(issue.get("title") or "", issue.get("body") or "")
    hechos = ["actor", "título", "contrato"]

    head = git.remote_head(c.task_branch)
    if head is None:
        raise PreflightError("TASK_BRANCH_MISSING", c.task_branch)
    if head != c.task_commit:
        raise PreflightError("TASK_BRANCH_MOVED", f"{c.task_branch} apunta a {head[:12]}, "
                                                  f"no a {c.task_commit[:12]}")
    hechos.append("rama de la TASK en el commit exacto")
    base = git.remote_head(c.base_branch)
    if base is None:
        raise PreflightError("BASE_MISSING", c.base_branch)
    git.fetch(c.task_commit, base)
    estado = git.show(base, "docs/ai-development/CURRENT_STATE.md") or ""
    if declared_base(estado) != c.base_branch:
        raise PreflightError("BASE_NOT_DECLARED", f"CURRENT_STATE de {c.base_branch} declara "
                                                  f"{declared_base(estado)!r} como base")
    if git.run("merge-base", "--is-ancestor", base, c.task_commit, check=False).returncode != 0:
        raise PreflightError("NOT_DESCENDANT", f"{c.task_branch} no sale de {c.base_branch}")
    nueva = newer_base(git, c.base_branch, base, c.task_branch)
    if nueva:
        raise PreflightError("BASE_SUPERSEDED", f"{nueva} es más nueva que {c.base_branch} y se "
                                                "declara base: la TASK salió de una base vieja")
    hechos.append("base declarada, vigente y ancestro")
    diff = [ln.split("\t") for ln in git.run("diff", "--name-status", "--no-renames",
                                            f"{base}...{c.task_commit}").stdout.splitlines() if ln]
    if diff != [["A", c.task_path]]:
        raise PreflightError("DIFF_NOT_ONLY_TASK", "; ".join("\t".join(d) for d in diff)[:300]
                             or "sin cambios")
    hechos.append("diff = sólo la TASK")
    modo = git.run("ls-tree", c.task_commit, "--", c.task_path).stdout.split()
    if not modo or modo[0] != "100644" or modo[1] != "blob":
        raise PreflightError("TASK_NOT_REGULAR_FILE", "la TASK tiene que ser un archivo normal")
    texto = git.show(c.task_commit, c.task_path)
    if texto is None:
        raise PreflightError("TASK_FILE_MISSING", c.task_path)
    secciones = _sections(texto)
    faltan = [s for s in TASK_SECTIONS if s not in secciones]
    if faltan:
        raise PreflightError("TASK_SECTIONS_MISSING", ", ".join(faltan))
    if not secciones["Decisión aprobada"]:
        raise PreflightError("NOT_APPROVED", "«Decisión aprobada» está vacía")
    hechos.append("TASK con formato y aprobación")
    if git.show(c.task_commit, f"reports/{c.task_id}_REPORT.md") is not None:
        raise PreflightError("ALREADY_REPORTED", f"reports/{c.task_id}_REPORT.md ya existe")
    previas = git.remote_branches(f"{IMPL_PREFIX}{branch_stem(c.task_id)}-")
    if previas:
        raise PreflightError("ALREADY_EXECUTED", ", ".join(previas)[:200])
    # Dos issues para la misma TASK (un reintento del conector, una confusión) correrían dos veces:
    # gana el primero. Sólo cuentan los del usuario autorizado; si no, cualquiera que adivine el
    # título podría bloquear una TASK abriendo antes un issue igual.
    if list_issues is None:
        raise PreflightError("ISSUES_UNVERIFIABLE", "no hay cómo listar issues previos")
    titulo = f"{TITLE_PREFIX} {c.task_id}"
    anteriores = [i.get("number") for i in list_issues(titulo)
                  if i.get("title") == titulo and isinstance(i.get("number"), int)
                  and i["number"] < numero and (i.get("user") or {}).get("login") == AUTHORIZED_ACTOR
                  and (i.get("user") or {}).get("type") == "User" and "pull_request" not in i]
    if anteriores:
        raise PreflightError("DUPLICATE_ISSUE", f"ya hubo un issue para {c.task_id}: "
                                                f"#{min(anteriores)}")
    hechos.append("sin ejecución previa ni issue duplicado")
    impl = f"{IMPL_PREFIX}{branch_stem(c.task_id)}-issue-{numero}"
    return Result(contract=c, issue_number=numero, base_commit=base, impl_branch=impl,
                  prompt=build_prompt(c, numero, impl), checks=hechos)


# ---------------------------------------------------------------------------------------------
# verify: qué se publica de lo que hizo Claude
# ---------------------------------------------------------------------------------------------
#: Lo que una ejecución automática nunca puede tocar. `.github/` porque es el ejecutor mismo;
#: `src/` porque el motor está congelado (D-008); `tasks/` porque la TASK es el contrato.
FORBIDDEN_PREFIXES = (".github/", "src/", "tasks/", ".claude/", ".mcp.json",
                      "scripts/auto_task.py")
#: Se compara la ruta normalizada (NFKC) y plegada (casefold): `Src/`, `SRC/` o `ſrc/` caen dentro
#: de `src/` en un disco que no distingue mayúsculas, como el del Mac de Joaquín.


def _norm(path: str) -> str:
    return unicodedata.normalize("NFKC", path).casefold()


def forbidden(path: str) -> bool:
    p = _norm(path)
    while p.startswith(("./", "/")):                          # un prefijo, no un juego de caracteres
        p = p[2:] if p.startswith("./") else p[1:]
    return any(p == f.rstrip("/") or p.startswith(f) for f in FORBIDDEN_PREFIXES)


def _secret_patterns() -> List:
    """Los mismos patrones de valor que `scripts/secret_scan.py`: una sola regla. Si no se pueden
    cargar, la verificación no puede afirmar que no hay secretos, y rechaza."""
    import importlib.util                                    # noqa: PLC0415
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secret_scan.py")
    spec = importlib.util.spec_from_file_location("escalimetro_secret_scan", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [p for _, p in mod.VALUE_PATTERNS]
PUBLISH, PUBLISH_INCOMPLETE, REJECT, NOTHING = ("PUBLISH", "PUBLISH_INCOMPLETE", "REJECT",
                                                "NOTHING")


@dataclass
class Verdict:
    verdict: str
    detail: str
    head: Optional[str] = None
    commits: int = 0
    files: List[str] = field(default_factory=list)
    report: bool = False


def verify_impl(git: Git, bundle: Optional[str], task_commit: str, task_id: str,
                impl_branch: str, ref: str = "refs/auto/impl") -> Verdict:
    """Juzga los commits de Claude, que llegan en `bundle`. No empuja nada: eso lo hace el workflow
    con el veredicto en la mano. Falla cerrado ante cualquier sorpresa."""
    if not SHA_RE.match(task_commit) or not ID_RE.match(task_id) \
            or not re.match(r"^auto/[a-z0-9_]+-issue-\d+$", impl_branch):
        return Verdict(REJECT, "argumentos con formato inválido")
    if not bundle or not os.path.exists(bundle):
        return Verdict(NOTHING, "Claude no dejó commits")
    if git.run("bundle", "verify", bundle, check=False).returncode != 0:
        return Verdict(REJECT, "el bundle no es válido")
    cabezas = [ln.split()[0] for ln in git.run("bundle", "list-heads", bundle).stdout.splitlines()
               if ln.strip()]
    if len(set(cabezas)) != 1 or not SHA_RE.match(cabezas[0]):
        return Verdict(REJECT, "el bundle tiene que traer exactamente una punta")
    head = cabezas[0]
    git.fetch(task_commit)
    if git.run("fetch", "--quiet", "--no-tags", bundle, f"{head}:{ref}", check=False).returncode:
        return Verdict(REJECT, "no se pudo leer el bundle")
    if git.run("cat-file", "-t", head, check=False).stdout.strip() != "commit":
        return Verdict(REJECT, "la punta del bundle no es un commit", head)
    if git.run("merge-base", "--is-ancestor", task_commit, head, check=False).returncode != 0:
        return Verdict(REJECT, "los commits no salen del commit de la TASK", head)
    commits = int(git.run("rev-list", "--count", f"{task_commit}..{head}").stdout.strip() or 0)
    if commits == 0:
        return Verdict(NOTHING, "Claude no dejó commits", head)
    # Rutas tocadas por CUALQUIER commit, no sólo por el árbol final, y sin comillas: con
    # core.quotePath, git escribe «"src/\303\261.py"» y eso no empieza por «src/».
    crudo = git.run("-c", "core.quotePath=false", "log", "--no-renames", "--name-only", "-z",
                    "--format=", f"{task_commit}..{head}").stdout
    archivos = sorted({f.strip("\n") for f in crudo.split("\0") if f.strip("\n")})
    prohibidos = [f for f in archivos if forbidden(f)]
    if prohibidos:
        return Verdict(REJECT, "toca rutas prohibidas: " + ", ".join(prohibidos)[:300], head,
                       commits, archivos)
    diff = git.run("-c", "core.quotePath=false", "log", "-p", "--no-renames", "--format=",
                   f"{task_commit}..{head}").stdout
    agregadas = "\n".join(ln[1:] for ln in diff.splitlines()
                           if ln.startswith("+") and not ln.startswith("+++"))
    try:
        patrones = _secret_patterns()
    except Exception:                                         # noqa: BLE001
        return Verdict(REJECT, "no se pudieron cargar los patrones de secretos", head, commits,
                       archivos)
    if not patrones or any(p.search(agregadas) for p in patrones):
        return Verdict(REJECT, "algo con forma de credencial en lo agregado: no se publica en un "
                       "repo público", head, commits, archivos)
    previas = git.remote_branches(f"{IMPL_PREFIX}{branch_stem(task_id)}-")
    if previas:
        return Verdict(REJECT, "ya hay una rama de implementación de esta TASK: "
                       + ", ".join(previas)[:200], head, commits, archivos)
    reporte = git.show(head, f"reports/{task_id}_REPORT.md") is not None
    if not reporte:
        return Verdict(PUBLISH_INCOMPLETE, f"falta reports/{task_id}_REPORT.md: se publica para "
                       "auditar, no como entrega", head, commits, archivos)
    return Verdict(PUBLISH, "listo para auditar", head, commits, archivos, True)


# ---------------------------------------------------------------------------------------------
# CLI: lo que corre el workflow, y lo que usa la simulación local
# ---------------------------------------------------------------------------------------------
def write_outputs(path: str, outputs: Dict[str, str]) -> None:
    """Formato de GITHUB_OUTPUT. Los valores multilínea van con un delimitador que no puede
    aparecer en ellos: el prompt lo armamos nosotros y no contiene esa marca."""
    with open(path, "a", encoding="utf-8") as fh:
        for k, v in outputs.items():
            if "\n" in v:
                delim = "EOF_ESCALIMETRO_AUTO_TASK"
                assert delim not in v
                fh.write(f"{k}<<{delim}\n{v}\n{delim}\n")
            else:
                fh.write(f"{k}={v}\n")


def main_verify(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(description="verify: decide si se publica lo que hizo Claude")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--bundle")
    ap.add_argument("--task-commit", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--impl-branch", required=True)
    ap.add_argument("--output", default=os.environ.get("GITHUB_OUTPUT"))
    a = ap.parse_args(argv)
    v = verify_impl(Git(a.repo, a.remote), a.bundle, a.task_commit, a.task_id, a.impl_branch)
    print(f"VERIFY {v.verdict}: {v.detail} · commits={v.commits} · archivos={len(v.files)}")
    if a.output:
        write_outputs(a.output, {"verdict": v.verdict, "head": v.head or "",
                                 "commits": str(v.commits), "report": "true" if v.report else "false"})
    return 0 if v.verdict in (PUBLISH, PUBLISH_INCOMPLETE, NOTHING) else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "verify":
        return main_verify(argv[1:])
    if argv and argv[0] == "preflight":
        argv = argv[1:]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"),
                    help="JSON del evento (en Actions: GITHUB_EVENT_PATH)")
    ap.add_argument("--repo", default=".", help="clon con el remoto a verificar")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--output", default=os.environ.get("GITHUB_OUTPUT"),
                    help="archivo de salidas (en Actions: GITHUB_OUTPUT)")
    ap.add_argument("--issues-json", help="issues previos (simulación local, sin GitHub)")
    a = ap.parse_args(argv)
    if not a.event:
        print("PREFLIGHT FAIL MALFORMED: falta el evento", file=sys.stderr)
        return 2
    with open(a.event, encoding="utf-8") as fh:
        event = json.load(fh)
    lister: Optional[IssueLister] = None
    if a.issues_json:
        with open(a.issues_json, encoding="utf-8") as fh:
            previos = json.load(fh)
        lister = lambda titulo: [i for i in previos if i.get("title") == titulo]   # noqa: E731
    elif os.environ.get("GITHUB_REPOSITORY"):
        lister = gh_issue_lister(os.environ["GITHUB_REPOSITORY"])
    try:
        r = preflight(event, os.environ.get("GITHUB_ACTOR"), Git(a.repo, a.remote), lister)
    except PreflightError as e:
        # sólo el código y un detalle acotado: nunca el cuerpo del issue
        print(f"PREFLIGHT FAIL {e.code}: {e.detail}", file=sys.stderr)
        if a.output:
            write_outputs(a.output, {"ok": "false", "reason": e.code})
        return 1
    for h in r.checks:
        print(f"PREFLIGHT OK · {h}")
    print(f"PREFLIGHT PASS {r.contract.task_id} → {r.impl_branch}")
    if a.output:
        write_outputs(a.output, r.outputs())
    return 0


if __name__ == "__main__":
    sys.exit(main())
