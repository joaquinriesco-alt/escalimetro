"""M02.1 — el aislamiento de subprocesos del ejecutor se prepara y se prueba antes de la credencial.

La primera ejecución real (run 36864248192, issue #2, TASK M03) murió en la instalación de Claude
Code: con `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`, Claude Code exige bubblewrap, y la action fijada sólo
lo instala cuando hay `allowed_non_write_users`, que el ejecutor no usa a propósito. La reparación
no apaga el scrub: prepara bubblewrap y apaga docker en el job `claude`, prueba un sandbox de
verdad —su propio PID namespace, sin sudo, sin docker— y falla cerrado antes de que la credencial
llegue a la action.

Estos tests no corren bubblewrap: la máquina de desarrollo no es Linux y no se dispara ningún
workflow. Prueban el texto del workflow y ejecutan sus dos scripts con binarios falsos —y el script
de adentro del sandbox con un sandbox simulado—, para que cada forma de fallar termine el paso con
un error que diga por qué.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows", "escalimetro-auto-task.yml")

PREPARAR = "Aislamiento de subprocesos (bubblewrap)"
VERIFICAR = "Aislamiento verificado (antes de la credencial)"
APPARMOR = "/proc/sys/kernel/apparmor_restrict_unprivileged_userns"
NS_RUNNER = "pid:[4026531836]"
NS_SANDBOX = "pid:[4026532999]"


def _wf():
    with open(WF, encoding="utf-8") as fh:
        return fh.read()


def _codigo(texto):
    """Sin comentarios, con el mismo criterio que tests/test_m02_auto_task.py."""
    return "\n".join(ln.split(" #")[0] if not ln.lstrip().startswith("#") else ""
                     for ln in texto.splitlines())


def _job(nombre):
    m = re.search(rf"^  {nombre}:\n(.*?)(?=^  [a-z_]+:\n|\Z)", _wf(), re.M | re.S)
    assert m, nombre
    return m.group(1)


def _partes(job_texto):
    """Lo que hay antes del primer paso, y cada paso. Se corta en cualquier `- ` de paso, no sólo
    en `- name:`: un paso sin nombre tiene que hacer fallar a quien espera un orden, no
    desaparecer pegado al anterior o antes del primero."""
    cuerpo = job_texto.split("    steps:\n", 1)[1]
    trozos = re.split(r"^(?=      - )", cuerpo, flags=re.M)
    pasos = []
    for paso in trozos[1:]:
        m = re.search(r"^(?:      - |        )name: (.+)$", paso, re.M)
        pasos.append((m.group(1).strip() if m else None, paso))
    return trozos[0], pasos


def _pasos(job_texto):
    return _partes(job_texto)[1]


def _script(paso):
    """El `run: |` de un paso del job `claude`, tal como lo recibe bash."""
    texto = dict(_pasos(_job("claude")))[paso]
    m = re.search(r"^        run: \|\n((?:          .*\n)+)", texto, re.M)
    assert m, paso
    return textwrap.dedent(m.group(1))


# =================================================================================================
# El workflow
# =================================================================================================
def test_el_scrub_sigue_activo_y_no_hay_forma_de_apagarlo():
    t = _wf()
    # todas las asignaciones, también las de un paso o una expresión, valen "1"
    valores = re.findall(r"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB\s*[:=]\s*(\S+)", t)
    assert valores and set(valores) == {'"1"'}, valores
    claude = _codigo(_job("claude"))
    assert 'CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"' in claude.split("    steps:\n", 1)[0]  # el job
    accion = dict(_pasos(claude))["Claude ejecuta la TASK"]
    assert 'CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"' in accion                             # la action
    # ni siquiera citado: un SCRUB=0 copiado de un comentario no puede quedar a mano
    assert not re.search(r"SUBPROCESS_ENV_SCRUB\W{0,4}0", t)
    assert "bwrapPath" not in t


def test_el_aislamiento_se_prepara_y_se_prueba_antes_de_todo_lo_demas():
    antes, pasos = _partes(_job("claude"))
    assert not _codigo(antes).strip(), antes          # antes del primer paso, sólo comentarios
    nombres = [n for n, _ in pasos]
    assert None not in nombres, nombres
    # primero que el checkout: ningún código del repo corre antes
    assert nombres[:2] == [PREPARAR, VERIFICAR], nombres
    credencial = next(i for i, (_, p) in enumerate(pasos) if "secrets." in _codigo(p))
    accion = next(i for i, (_, p) in enumerate(pasos) if "anthropics/claude-code-action@" in p)
    assert 1 < credencial < accion


def test_un_paso_sin_nombre_antes_del_aislamiento_no_pasa_desapercibido():
    """Regresión de la revisión de M02.1: cortar sólo por `- name:` dejaba invisible un paso sin
    nombre puesto antes del primero, y la credencial podía usarse antes del sandbox."""
    mutado = _job("claude").replace(
        f"      - name: {PREPARAR}\n",
        "      - env:\n          T: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}\n        run: echo x\n"
        f"      - name: {PREPARAR}\n", 1)
    nombres = [n for n, _ in _partes(mutado)[1]]
    assert nombres[0] is None and nombres[1] == PREPARAR


def test_el_job_claude_corre_fijo_en_ubuntu_24_04():
    """`ubuntu-latest` pasa a 26.04 desde el 2026-10-19 (actions/runner-images#14748), y 26.04 carga
    un perfil de AppArmor que deja sin capacidades a los hijos de bwrap. Los otros jobs no usan
    bubblewrap y quedan como estaban."""
    assert re.search(r"^    runs-on: ubuntu-24\.04$", _job("claude"), re.M)


def test_una_falla_del_aislamiento_detiene_el_job_antes_de_la_credencial():
    """Un paso que falla saltea los siguientes sólo si nadie lo pide de otra forma: un
    `continue-on-error` o un `if: always()` entregarían la credencial con el sandbox roto."""
    pasos = _pasos(_job("claude"))
    assert "continue-on-error" not in _codigo(_job("claude"))
    accion = next(i for i, (_, p) in enumerate(pasos) if "anthropics/claude-code-action@" in p)
    for nombre, paso in pasos[: accion + 1]:
        assert not re.search(r"^\s+if:", _codigo(paso), re.M), nombre


def test_sudo_solo_para_preparar_el_runner():
    t = _codigo(_wf())
    assert len(re.findall(r"\bsudo\b", t)) == 4
    preparar = _codigo(_script(PREPARAR))
    assert re.findall(r"\bsudo (\S+)", preparar) == ["timeout", "timeout", "systemctl", "sysctl"]
    assert re.findall(r"\bsudo timeout \d+ (\S+)", preparar) == ["apt-get", "apt-get"]
    assert "sudo" not in _codigo(_script(VERIFICAR))   # la prueba corre como la correrá Claude


def test_la_preparacion_instala_bubblewrap_apaga_docker_y_contempla_apparmor():
    preparar = _script(PREPARAR)
    assert "apt-get install -y --no-install-recommends bubblewrap socat" in preparar
    assert "sudo systemctl stop docker.socket docker.service" in preparar
    assert f"if [ -e {APPARMOR} ]; then" in preparar
    assert "sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0" in preparar
    # y se relee: un sysctl que no tomó deja el sandbox sin capacidades
    assert '"$(sysctl -n kernel.apparmor_restrict_unprivileged_userns)" != 0' in preparar
    assert re.search(r'::error::AppArmor sigue restringiendo los user namespaces"\n\s+exit 1\n',
                     preparar)
    for paso in (PREPARAR, VERIFICAR):
        assert "${{" not in _script(paso), paso          # nada interpolado: sólo texto fijo


def test_la_prueba_es_funcional_no_de_presencia():
    verificar = _script(VERIFICAR)
    for necesario in ("command -v bwrap", "--unshare-user", "--unshare-pid", "--unshare-net",
                      "--cap-drop ALL", "--proc /proc", "readlink /proc/self/ns/pid", '"$$"',
                      "NoNewPrivs", "UNIX-CONNECT:/run/docker.sock", "AISLAMIENTO: OK"):
        assert necesario in verificar, necesario


def test_los_dos_pasos_corren_con_bash_estricto():
    """Sin `shell:`, GitHub usa `bash -e` sin pipefail; los tests corren con los dos."""
    pasos = dict(_pasos(_job("claude")))
    for paso in (PREPARAR, VERIFICAR):
        assert re.search(r"^        shell: bash$", pasos[paso], re.M), paso
        assert re.search(r"^        timeout-minutes: \d+$", pasos[paso], re.M), paso


def test_los_dos_scripts_son_bash_valido():
    for paso in (PREPARAR, VERIFICAR):
        r = subprocess.run(["bash", "-n"], input=_script(paso), capture_output=True, text=True)
        assert r.returncode == 0, (paso, r.stderr)


# =================================================================================================
# Los scripts, con binarios falsos
# =================================================================================================
def _correr(tmp_path, paso, version=True, reemplazos=None, **falsos):
    """Corre el script como lo hace GitHub (bash -eo pipefail) con un PATH cerrado: los falsos y
    sólo las utilidades de base que el script usa. Sin el /usr/bin del host, que en Linux podría
    traer un bwrap de verdad. `reemplazos` cambia rutas del sistema por otras del test; el ancla
    tiene que existir, o el test probaría otra cosa."""
    falsos_dir = tmp_path / "falsos"
    base_dir = tmp_path / "base"
    falsos_dir.mkdir(exist_ok=True)
    base_dir.mkdir(exist_ok=True)
    for nombre, cuerpo in falsos.items():
        if nombre == "bwrap" and version:      # responde --version como el real
            cuerpo = '[ "$1" = --version ] && { echo "bubblewrap 0.9.0"; exit 0; }\n' + cuerpo
        p = falsos_dir / nombre
        p.write_text("#!/bin/sh\n" + cuerpo + "\n")
        p.chmod(0o755)
    for util in ("sed", "wc", "cat", "grep", "mkdir"):
        if not (base_dir / util).exists():
            (base_dir / util).symlink_to(shutil.which(util))
    texto = _script(paso)
    for viejo, nuevo in (reemplazos or {}).items():
        assert viejo in texto, viejo
        texto = texto.replace(viejo, nuevo)
    script = tmp_path / "paso.sh"
    script.write_text(texto)
    env = {"PATH": f"{falsos_dir}:{base_dir}", "HOME": str(tmp_path),
           "REGISTRO": str(tmp_path / "registro")}
    return subprocess.run([shutil.which("bash"), "--noprofile", "--norc", "-e", "-o", "pipefail",
                           str(script)], capture_output=True, text=True, env=env, timeout=60)


def _falla(r, motivo):
    assert r.returncode != 0
    assert "AISLAMIENTO: OK" not in r.stdout
    assert f"::error::aislamiento no disponible: {motivo}" in r.stdout, r.stdout + r.stderr


READLINK = f'case "$1" in */self/ns/pid) echo "{NS_RUNNER}" ;; *) exit 1 ;; esac'
SOCAT = "exit 0"


# --- la prueba del sandbox, con un sandbox simulado: el script de adentro corre de verdad --------
def _sandbox(tmp_path, propio_ns=True, ve_runner=False, nnp=1, docker=False, **otros):
    """Un bwrap falso que ejecuta el script de adentro tal cual, sobre un /proc de mentira: su
    PID namespace, si el PID del runner aparece, su NoNewPrivs y si docker responde son los que
    dice el caso. Así cada detector de adentro se ejerce, no sólo la lectura de su salida."""
    proc = tmp_path / "proc"
    (proc / "self").mkdir(parents=True, exist_ok=True)
    (proc / "self" / "status").write_text(f"Name:\tsh\nNoNewPrivs:\t{nnp}\n")
    bwrap = ('while [ "$1" != /bin/sh ]; do shift; done\n'
             + (f'mkdir -p "{proc}/$5"\n' if ve_runner else "")
             + f"DENTRO={1 if propio_ns else 0}; export DENTRO\n"
             'exec "$@"')
    readlink = ('case "$1" in */self/ns/pid) '
                f'if [ "$DENTRO" = 1 ]; then echo "{NS_SANDBOX}"; else echo "{NS_RUNNER}"; fi ;; '
                '*) exit 1 ;; esac')
    socat = ('case "$*" in *UNIX-CONNECT*) exit ' + ("0" if docker else "1") + " ;; esac")
    return _correr(tmp_path, VERIFICAR, reemplazos={"/proc/": f"{proc}/"},
                   bwrap=bwrap, readlink=readlink, socat=socat, **otros)


def test_verificar_pasa_con_un_sandbox_aislado_sin_privilegios_y_sin_docker(tmp_path):
    r = _sandbox(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (f"AISLAMIENTO: OK · PID namespace propio {NS_SANDBOX}, distinto del runner {NS_RUNNER}"
            in r.stdout)


def test_verificar_falla_si_el_runner_se_ve_desde_el_sandbox(tmp_path):
    _falla(_sandbox(tmp_path, ve_runner=True), "el runner es visible desde el sandbox")


def test_verificar_falla_si_el_sandbox_comparte_el_pid_namespace(tmp_path):
    _falla(_sandbox(tmp_path, propio_ns=False), "el sandbox comparte el PID namespace del runner")


def test_verificar_falla_si_el_sandbox_puede_ganar_privilegios(tmp_path):
    _falla(_sandbox(tmp_path, nnp=0), "el sandbox puede ganar privilegios (sin no_new_privs)")


def test_verificar_falla_si_docker_responde_desde_el_sandbox(tmp_path):
    """docker equivale a root en el runner: un contenedor con el PID namespace del host lee la
    credencial. bubblewrap no bloquea sockets Unix; por eso se apaga y se comprueba."""
    _falla(_sandbox(tmp_path, docker=True), "el sandbox llega al socket de docker")


# --- la prueba del sandbox, el resto de las fallas ----------------------------------------------
def test_verificar_falla_sin_bwrap(tmp_path):
    _falla(_correr(tmp_path, VERIFICAR, readlink=READLINK, socat=SOCAT), "falta bwrap")


def test_verificar_falla_si_bwrap_no_arranca(tmp_path):
    _falla(_correr(tmp_path, VERIFICAR, version=False, readlink=READLINK, socat=SOCAT,
                   bwrap="exit 127"), "bwrap no arranca")


def test_verificar_falla_sin_socat(tmp_path):
    _falla(_correr(tmp_path, VERIFICAR, readlink=READLINK, bwrap="exit 0"), "falta socat")


def test_verificar_falla_si_apparmor_no_deja_crear_el_namespace(tmp_path):
    """El binario existe pero el sandbox no puede operar: lo que pide el criterio 4 de la TASK.
    Es el error exacto de bwrap 0.9.0 en ubuntu-24.04 con la restricción activa."""
    restringido = 'echo "bwrap: setting up uid map: Permission denied" >&2; exit 1'
    _falla(_correr(tmp_path, VERIFICAR, readlink=READLINK, socat=SOCAT, bwrap=restringido),
           "bwrap no pudo crear el sandbox")


def test_verificar_falla_si_no_puede_leer_el_namespace_del_runner(tmp_path):
    _falla(_correr(tmp_path, VERIFICAR, readlink="exit 1", socat=SOCAT, bwrap="exit 0"),
           "no se pudo leer el PID namespace del runner")


@pytest.mark.parametrize("salida, motivo", [
    ("AISLADO", "salida inesperada del sandbox"),
    (f"{NS_SANDBOX}\\nAISLADO\\nSIN_PRIVILEGIOS", "salida inesperada del sandbox"),
    (f"{NS_SANDBOX}\\nVISIBLE\\nSIN_PRIVILEGIOS\\nSIN_DOCKER", "el runner es visible desde el sandbox"),
    ("algo\\nAISLADO\\nSIN_PRIVILEGIOS\\nSIN_DOCKER", "el sandbox no informó su PID namespace"),
    (f"{NS_RUNNER}\\nAISLADO\\nSIN_PRIVILEGIOS\\nSIN_DOCKER",
     "el sandbox comparte el PID namespace del runner"),
    (f"{NS_SANDBOX}\\nAISLADO\\nCON_PRIVILEGIOS\\nSIN_DOCKER",
     "el sandbox puede ganar privilegios (sin no_new_privs)"),
    (f"{NS_SANDBOX}\\nAISLADO\\nSIN_PRIVILEGIOS\\nDOCKER", "el sandbox llega al socket de docker"),
    ("", "salida inesperada del sandbox"),
])
def test_verificar_no_acepta_una_salida_que_no_pruebe_el_aislamiento(tmp_path, salida, motivo):
    r = _correr(tmp_path, VERIFICAR, readlink=READLINK, socat=SOCAT,
                bwrap=f'printf "{salida}\\n"' if salida else "exit 0")
    _falla(r, motivo)


# --- la preparación -------------------------------------------------------------------------------
UPDATE = "timeout 180 apt-get update -qq"
INSTALL = "timeout 180 apt-get install -y --no-install-recommends bubblewrap socat"
DOCKER = "systemctl stop docker.socket docker.service"
SYSCTL = "sysctl -w kernel.apparmor_restrict_unprivileged_userns=0"


def _sudo(fallan=(), una_vez=()):
    """Un sudo falso que anota cada llamada; `fallan` siempre fallan, `una_vez` sólo la primera."""
    cuerpo = 'echo "$*" >> "$REGISTRO"\n'
    for patron in fallan:
        cuerpo += f'case "$*" in *"{patron}"*) exit 1 ;; esac\n'
    for i, patron in enumerate(una_vez):
        marca = f'"$REGISTRO.una_vez{i}"'
        cuerpo += (f'case "$*" in *"{patron}"*) if [ ! -e {marca} ]; then : > {marca}; exit 1; fi'
                   " ;; esac\n")
    return cuerpo


def _preparar(tmp_path, apparmor=True, sysctl="echo 0", **falsos):
    """Corre la preparación con la ruta de AppArmor apuntando a un archivo del test: presente o
    ausente según el caso, en cualquier sistema."""
    ruta = tmp_path / "apparmor_restrict_unprivileged_userns"
    if apparmor:
        ruta.write_text("1\n")
    falsos.setdefault("sudo", _sudo())
    return _correr(tmp_path, PREPARAR, reemplazos={APPARMOR: str(ruta)}, sleep="exit 0",
                   sysctl=sysctl, **falsos)


def _registro(tmp_path):
    p = tmp_path / "registro"
    return p.read_text().splitlines() if p.exists() else []


def test_preparar_instala_apaga_docker_y_libera_apparmor(tmp_path):
    r = _preparar(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _registro(tmp_path) == [UPDATE, INSTALL, DOCKER, SYSCTL]


def test_preparar_sin_la_restriccion_no_toca_el_sysctl(tmp_path):
    r = _preparar(tmp_path, apparmor=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _registro(tmp_path) == [UPDATE, INSTALL, DOCKER]


def test_preparar_falla_si_no_puede_liberar_apparmor(tmp_path):
    r = _preparar(tmp_path, sudo=_sudo(fallan=["sysctl"]))
    assert r.returncode != 0
    assert "AISLAMIENTO" not in r.stdout


def test_preparar_falla_si_el_sysctl_no_tomo(tmp_path):
    r = _preparar(tmp_path, sysctl="echo 1")
    assert r.returncode != 0
    assert "::error::AppArmor sigue restringiendo los user namespaces" in r.stdout


def test_preparar_reintenta_y_falla_cerrado_si_apt_no_instala(tmp_path):
    r = _correr(tmp_path, PREPARAR, sudo=_sudo(fallan=["apt-get"]),
                sleep='echo "sleep $*" >> "$REGISTRO"', sysctl="echo 0")
    assert r.returncode != 0
    assert "::error::no se pudo instalar bubblewrap" in r.stdout
    reg = _registro(tmp_path)
    assert reg.count(UPDATE) == 3 and reg.count(INSTALL) == 3 and reg.count("sleep 5") == 2
    assert DOCKER not in reg and SYSCTL not in reg


def test_preparar_instala_aunque_el_update_tenga_errores(tmp_path):
    """Un repositorio de terceros caído hace fallar `apt-get update`, no la instalación desde
    Ubuntu: decide el install, y si bubblewrap no opera lo detiene el paso siguiente."""
    r = _preparar(tmp_path, sudo=_sudo(fallan=["apt-get update"]))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "::warning::apt-get update terminó con errores" in r.stdout
    assert _registro(tmp_path).count(INSTALL) == 1


def test_preparar_se_recupera_de_un_install_que_falla_una_vez(tmp_path):
    r = _preparar(tmp_path, sudo=_sudo(una_vez=["apt-get install"]))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _registro(tmp_path).count(INSTALL) == 2


def test_preparar_sigue_si_docker_no_se_puede_detener(tmp_path):
    """Un runner sin docker no es un error. Si docker sigue respondiendo, lo detiene la prueba
    del paso siguiente, que lo mira desde adentro del sandbox."""
    r = _preparar(tmp_path, sudo=_sudo(fallan=["systemctl"]))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "::warning::docker no se detuvo" in r.stdout
