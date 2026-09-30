"""E37 §5, §9–§14 — corridas inmutables, calificación, corrección por prompt, comparación, métricas.

Una corrida congela, al CREARSE, todo lo que la define: motor y versión, parámetros (con el modelo
ya resuelto), los ids y sha256 de los inputs que el motor va a recibir, los datos declarados, el
commit del código y si el plano real estaba oculto. Al TERMINAR guarda su salida validada, el SVG
dibujado desde ella, lo que se mandó, latencia y costo. Después no cambia: lo impiden triggers en
la base, no sólo este código. Corregir o volver a generar crea OTRA corrida.

Este módulo arma la entrada de los motores, y por eso NO importa `groundtruth`: la entrada sale
exclusivamente de los ids de inputs congelados en la corrida (E37 §4). Un test lo verifica.

La ejecución corre en un hilo de fondo, como el motor y la ambientación: una llamada con 34 fotos
puede tardar minutos y no debe colgar una request. Al reiniciar, lo que quedó en vuelo se cierra
como FAILED (`store.reset_orphans`) y no se reanuda: reanudar sería volver a pagar sin que nadie lo
pidiera.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import uuid
from typing import Any, Dict, List, Optional

from ... import store
from ...providers import base as http
from . import contract, engines, projects, render

QUEUED, RUNNING, DONE, FAILED = "QUEUED", "RUNNING", "DONE", "FAILED"
INITIAL, CORRECTION = engines.INITIAL, engines.CORRECTION
RATINGS = ("EXCELENTE", "BUENO", "MALO", "PESIMO")
RATING_LABEL = {"EXCELENTE": "Excelente", "BUENO": "Bueno", "MALO": "Malo", "PESIMO": "Pésimo"}
OUTCOME_LABEL = {contract.RECONSTRUCTED: "Plano esquemático",
                 contract.INSUFFICIENT_EVIDENCE: "Evidencia insuficiente",
                 contract.CLARIFICATION_REQUIRED: "Pide una aclaración"}
#: El contrato habla en códigos; la pantalla, en castellano.
CONNECTION_LABEL = {"DOOR": "puerta", "OPENING": "abertura", "ADJACENT": "contiguos",
                    "UNKNOWN": "conexión incierta"}
RELATION_LABEL = {"LEFT_OF": "a la izquierda de", "RIGHT_OF": "a la derecha de",
                  "ABOVE": "arriba de", "BELOW": "abajo de", "NEXT_TO": "junto a"}
IMPACT_LABEL = {"HIGH": "alta", "MEDIUM": "media", "LOW": "baja"}
ROOM_TYPE_LABEL = {"LIVING": "living", "DINING": "comedor", "LIVING_DINING": "living-comedor",
                   "KITCHEN": "cocina", "BEDROOM": "dormitorio", "BATHROOM": "baño",
                   "TOILET": "baño de visitas", "WALK_IN_CLOSET": "walk-in closet",
                   "CLOSET": "clóset", "HALLWAY": "pasillo", "ENTRY": "acceso",
                   "LAUNDRY": "logia", "TERRACE": "terraza", "BALCONY": "balcón",
                   "STUDY": "escritorio", "STORAGE": "bodega", "OTHER": "otro"}
MAX_CORRECTION = 2000
COMPARE_MIN, COMPARE_MAX = 2, 3


def _id() -> str:
    return "rcr_" + uuid.uuid4().hex[:12]


def _row(r) -> Optional[Dict]:
    if r is None:
        return None
    d = dict(r)
    for k in ("engine_meta", "inputs", "params", "output", "warnings", "request_summary",
              "artifacts", "usage"):
        d[k] = store.js(d.get(k), None)
    return d


def get(run_id: str) -> Optional[Dict]:
    return _row(store.q1("SELECT * FROM recon_runs WHERE run_id=?", (run_id,)))


def get_in_project(project_id: str, run_id: str) -> Optional[Dict]:
    return _row(store.q1("SELECT * FROM recon_runs WHERE run_id=? AND project_id=?",
                         (run_id, project_id)))


def of_project(project_id: str) -> List[Dict]:
    return [_row(r) for r in store.q("SELECT * FROM recon_runs WHERE project_id=? ORDER BY seq",
                                     (project_id,))]


def children(run_id: str) -> List[Dict]:
    return [_row(r) for r in store.q("SELECT * FROM recon_runs WHERE parent_run_id=? ORDER BY seq",
                                     (run_id,))]


def lineage(run: Dict) -> List[Dict]:
    """De la corrida raíz hasta ésta, en orden."""
    cadena, actual, vistos = [], run, set()
    while actual is not None and actual["run_id"] not in vistos:
        vistos.add(actual["run_id"])
        cadena.append(actual)
        actual = get(actual["parent_run_id"]) if actual["parent_run_id"] else None
    return list(reversed(cadena))


def prompts_in_lineage(run: Dict) -> int:
    return sum(1 for r in lineage(run) if r["origin"] == CORRECTION)


def _plan_ancestor(run: Dict) -> Optional[Dict]:
    """La representación que una corrección toma como punto de partida: el plano más cercano del
    linaje o, si nunca hubo uno, la salida de esta misma corrida. Una generación que terminó en
    INSUFFICIENT_EVIDENCE o que pidió una aclaración también se puede responder: es justo el
    momento en que la persona tiene algo que decir."""
    for r in reversed(lineage(run)):
        if r["status"] == DONE and r["outcome"] == contract.RECONSTRUCTED and r["output"]:
            return r
    if run["status"] == DONE and run["output"]:
        return run
    return None


def correctable(run: Dict) -> bool:
    return run["status"] == DONE and _plan_ancestor(run) is not None


# ---------------------------------------------------------------------------------------------
# crear
# ---------------------------------------------------------------------------------------------
def _inputs_snapshot(project_id: str, adapter: engines.EngineAdapter) -> Dict[str, Any]:
    """Lo que el motor va a recibir, congelado. SÓLO inputs del proyecto y datos declarados: el
    plano real no está en `recon_assets` y esta función no mira ninguna otra tabla."""
    caps = set(adapter.capabilities)
    fotos = projects.assets_of(project_id, projects.PHOTO)
    videos = projects.assets_of(project_id, projects.VIDEO)
    docs = projects.assets_of(project_id, projects.DOCUMENT)
    p = projects.get(project_id) or {}
    ignorados = []
    if videos and "video" not in caps:
        ignorados.append(f"{len(videos)} video(s)")      # se guardan; este motor no los consume
    if docs:
        ignorados.append(f"{len(docs)} documento(s)")
    declarados = p.get("declared") or {}
    if declarados and "declared_data" not in caps:
        ignorados.append("datos declarados")
    return {
        "photos": [{"asset_id": a["asset_id"], "sha256": a["sha256"], "mime_type": a["mime_type"],
                    "width_px": a["width_px"], "height_px": a["height_px"]} for a in fotos]
        if "photos" in caps else [],
        "videos": [{"asset_id": a["asset_id"], "sha256": a["sha256"],
                    "sent": "video" in caps} for a in videos],
        "documents": [{"asset_id": a["asset_id"], "sha256": a["sha256"], "sent": False}
                      for a in docs],
        "declared": declarados if "declared_data" in caps else {},
        "declared_all": declarados,
        "ignored": ignorados,
    }


def _insert(project_id: str, adapter: engines.EngineAdapter, *, origin: str,
            parent_run_id: Optional[str], correction_text: Optional[str], inputs: Dict,
            params: Dict, author: Optional[str]) -> str:
    from ... import engine as motor                            # noqa: PLC0415 — sólo por el commit
    p = projects.get(project_id)
    rid = _id()
    meta = {"name": adapter.name, "provider": adapter.provider, "model": params.get("model")
            or adapter.model(), "pipeline": adapter.pipeline,
            "capabilities": list(adapter.capabilities), "paid": adapter.paid,
            "notice": adapter.notice}
    # `seq` se calcula en la MISMA sentencia que inserta: dos clics seguidos no chocan.
    store.ex("INSERT INTO recon_runs(run_id, project_id, seq, parent_run_id, origin, "
             "correction_text, engine_id, engine_version, engine_meta, inputs, params, code_commit, "
             "gt_state_at_creation, status, author, created_at) "
             "SELECT ?, ?, COALESCE(MAX(seq), 0) + 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? "
             "FROM recon_runs WHERE project_id=?",
             (rid, project_id, parent_run_id, origin, correction_text, adapter.engine_id,
              adapter.version, json.dumps(meta, ensure_ascii=False),
              json.dumps(inputs, ensure_ascii=False), json.dumps(params, ensure_ascii=False),
              motor.engine_commit(), p["gt_state"], QUEUED, author, store.now(), project_id))
    return rid


def _check_engine(engine_id: str, confirm_paid: bool) -> engines.EngineAdapter:
    adapter = engines.get(engine_id)
    if adapter is None:
        raise projects.ReconError("Ese motor no está registrado.")
    disp = adapter.availability()
    if disp.status != engines.AVAILABLE:
        raise projects.ReconError(f"{adapter.name} no está disponible: {disp.reason}"
                                  + (f" ({disp.detail})" if disp.detail else ""))
    if adapter.paid and not confirm_paid:
        raise projects.ReconError(f"{adapter.name} cuesta dinero en cada corrida: hay que "
                                  "confirmar el gasto antes de generar.")
    return adapter


def create_initial(project_id: str, engine_id: str, author: Optional[str], *,
                   confirm_paid: bool = False) -> str:
    if projects.get(project_id) is None:
        raise projects.ReconError("Proyecto inexistente.")
    adapter = _check_engine(engine_id, confirm_paid)
    inputs = _inputs_snapshot(project_id, adapter)
    if "photos" in adapter.capabilities and not inputs["photos"]:
        raise projects.ReconError("No hay fotos cargadas: no hay nada que reconstruir.")
    rid = _insert(project_id, adapter, origin=INITIAL, parent_run_id=None, correction_text=None,
                  inputs=inputs, params=adapter.default_params(), author=author)
    projects.log(project_id, "RUN_REQUESTED", {"engine_id": engine_id}, run_id=rid, author=author)
    return rid


def create_correction(project_id: str, parent_run_id: str, text: str, author: Optional[str], *,
                      confirm_paid: bool = False) -> str:
    """Una corrección es una corrida HIJA: mismo motor, mismos parámetros, mismos inputs que la
    madre; lo único nuevo es la instrucción. La madre no se toca."""
    madre = get_in_project(project_id, parent_run_id)
    if madre is None:
        raise projects.ReconError("Esa corrida no es de este proyecto.")
    text = (text or "").strip()
    if not text:
        raise projects.ReconError("Escribe la corrección.")
    if len(text) > MAX_CORRECTION:
        raise projects.ReconError(f"La corrección es muy larga (máximo {MAX_CORRECTION} caracteres).")
    if madre["status"] != DONE:
        raise projects.ReconError("Sólo se corrige una corrida terminada.")
    if not correctable(madre):
        raise projects.ReconError("Esta corrida no tiene una salida que corregir.")
    adapter = _check_engine(madre["engine_id"], confirm_paid)
    if "correction" not in adapter.capabilities:
        raise projects.ReconError(f"{adapter.name} no acepta correcciones.")
    rid = _insert(project_id, adapter, origin=CORRECTION, parent_run_id=parent_run_id,
                  correction_text=text, inputs=madre["inputs"], params=madre["params"],
                  author=author)
    projects.log(project_id, "CORRECTION_REQUESTED", {"parent_run_id": parent_run_id},
                 run_id=rid, author=author)
    return rid


# ---------------------------------------------------------------------------------------------
# ejecutar
# ---------------------------------------------------------------------------------------------
def _read_input(run: Dict, f: Dict) -> Dict:
    """Los bytes de un input congelado, comprobados. Tres barreras antes de dárselos a un motor:
    que exista, que no haya cambiado en disco, y que no sea el plano real oculto (si alguien lo
    cargó como plano real DESPUÉS de que esta corrida lo citara, la corrida no se ejecuta)."""
    a = projects.get_asset(run["project_id"], f["asset_id"])
    if a is None:
        raise engines.EngineError("INPUT_MISSING", f"falta el input {f['asset_id']}")
    with open(projects.asset_path(a), "rb") as fh:
        data = fh.read()
    sha = hashlib.sha256(data).hexdigest()
    if sha != f["sha256"]:
        raise engines.EngineError("INPUT_CHANGED", f"el input {f['asset_id']} cambió en disco")
    if not projects.input_allowed(run["project_id"], sha):
        raise engines.EngineError("INPUT_IS_GROUND_TRUTH",
                                  f"el input {f['asset_id']} es idéntico al plano real oculto")
    return {"asset": a, "data": data}


_SIN_PLANO = (contract.CLARIFICATION_REQUIRED, contract.INSUFFICIENT_EVIDENCE)


def _dialogue(madre: Dict, texto: str) -> Dict[str, Optional[str]]:
    """Una corrección que responde a una o varias salidas sin plano nuevo —una pregunta del motor,
    o «evidencia insuficiente»— es UNA sola instrucción: lo que se pidió primero, lo que el motor
    contestó cada vez (la pregunta con sus opciones, o lo que dijo que faltaba) y cada respuesta.
    Si sólo se mandara la última respuesta, «la de la izquierda» no significaría nada."""
    turnos, contexto, r = [texto], [], madre
    while r is not None and r["status"] == DONE and r["outcome"] in _SIN_PLANO:
        out = r["output"] or {}
        cl = out.get("clarification") or {}
        if r["outcome"] == contract.CLARIFICATION_REQUIRED and cl.get("question"):
            ops = cl.get("options") or []
            contexto.append(cl["question"] + (" Opciones: " + "; ".join(map(str, ops))
                                              if ops else ""))
        elif r["outcome"] == contract.INSUFFICIENT_EVIDENCE:
            falta = "; ".join(map(str, out.get("missing_evidence") or []))
            contexto.append("Dijiste que la evidencia no alcanzaba"
                            + (f" (falta: {falta})" if falta else "")
                            + (f": {out.get('summary')}" if out.get("summary") else ""))
        if r["correction_text"]:
            turnos.append(r["correction_text"])
        r = get(r["parent_run_id"]) if r["parent_run_id"] else None
    turnos.reverse()
    contexto.reverse()
    return {"instruction": " — respuesta del operador: ".join(turnos),
            "clarification_context": "\n".join(contexto) or None}


def build_request(run: Dict) -> engines.EngineRequest:
    """La entrada del motor. Sale SÓLO de `run.inputs` (congelado al crear) y de las corridas
    madre. Si un input cambió en disco desde entonces, la corrida no se ejecuta: no sería la misma."""
    snap = run["inputs"] or {}
    imagenes, videos = [], []
    for f in snap.get("photos") or []:
        x = _read_input(run, f)
        a = x["asset"]
        imagenes.append(engines.InputImage(asset_id=a["asset_id"], mime_type=a["mime_type"],
                                           data=x["data"], width_px=a["width_px"],
                                           height_px=a["height_px"]))
    for f in snap.get("videos") or []:
        if f.get("sent"):
            x = _read_input(run, f)
            videos.append(engines.InputVideo(asset_id=x["asset"]["asset_id"],
                                             mime_type=x["asset"]["mime_type"], data=x["data"]))
    previo = None
    dialogo: Dict[str, Optional[str]] = {"instruction": None, "clarification_context": None}
    modo = run["origin"]
    if modo == CORRECTION:
        madre = get(run["parent_run_id"])
        base = _plan_ancestor(madre) if madre else None
        if base is None:
            raise engines.EngineError("NO_PREVIOUS_PLAN", "no hay una salida anterior que corregir")
        previo = base["output"]
        dialogo = _dialogue(madre, run["correction_text"] or "")
    return engines.EngineRequest(mode=modo, images=tuple(imagenes),
                                 declared=dict(snap.get("declared") or {}),
                                 params=dict(run["params"] or {}), previous=previo,
                                 instruction=dialogo["instruction"],
                                 clarification_context=dialogo["clarification_context"],
                                 ignored_inputs=tuple(snap.get("ignored") or ()),
                                 videos=tuple(videos))


def _write_one(sql: str, args: tuple) -> int:
    """Una escritura con su rollback si falla. Un trigger que aborta deja abierta la transacción
    implícita de sqlite3, y con ella el candado de escritura de TODA la app hasta reiniciar."""
    conn = store.connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        raise


def _claim(run_id: str) -> bool:
    """QUEUED → RUNNING, una sola vez. Dos workers o dos llamadas no ejecutan la misma corrida."""
    return _write_one("UPDATE recon_runs SET status=?, started_at=? WHERE run_id=? AND status=?",
                      (RUNNING, store.now(), run_id, QUEUED)) == 1


def _still_mine(run_id: str) -> bool:
    r = store.q1("SELECT status, finished_at FROM recon_runs WHERE run_id=?", (run_id,))
    return bool(r and r["status"] == RUNNING and r["finished_at"] is None)


def _partial_artifacts(run: Dict, partial: Dict[str, Any]) -> Dict[str, str]:
    """Lo que el proveedor devolvió en una corrida que falla igual queda en disco: se pagó."""
    d = projects.runs_dir(run["project_id"], run["run_id"])
    os.makedirs(d, exist_ok=True)
    out = {}
    if partial.get("request_summary"):
        out["request.json"] = _write(d, "request.json", json.dumps(
            http.sanitize(partial["request_summary"]), ensure_ascii=False, indent=1, default=str))
    if partial.get("raw"):
        out["response.json"] = _write(d, "response.json", json.dumps(
            http.sanitize(partial["raw"]), ensure_ascii=False, indent=1, default=str))
    return out


def _numbers(uso: Any) -> Dict[str, Any]:
    """El uso que reporta un proveedor, reducido a números. Es lo único que se necesita, y un campo
    de texto ahí es un lugar más por donde un proveedor podría devolver una credencial."""
    if not isinstance(uso, dict):
        return {}
    return {str(k): v for k, v in uso.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _fail(run_id: str, msg: str, partial: Optional[Dict[str, Any]] = None) -> None:
    """Cierra la corrida como FAILED en UNA sentencia —después el trigger no deja escribir más—,
    con todo lo que se alcanzó a saber: si hubo llamada, cuánto tardó, cuántos tokens y qué se mandó.

    No puede fallar: si armar lo parcial revienta, cierra igual con el mensaje. Y si otro proceso ya
    cerró la corrida (un reinicio la dio por muerta), no escribe nada en ella: deja constancia del
    resultado tardío y de lo que costó en la bitácora."""
    mensaje = http.sanitize(str(msg))[:2000]
    try:
        p = dict(partial or {})
        run = get(run_id)
        if run is None:
            return
        if not _still_mine(run_id):
            if p:
                projects.log(run["project_id"], "LATE_RESULT_DISCARDED",
                             {"usage": _numbers(p.get("usage")), "latency_ms": p.get("latency_ms"),
                              "error": mensaje[:300]}, run_id=run_id)
            return
        artefactos = {}
        if p.get("request_summary") or p.get("raw"):
            try:
                artefactos = _partial_artifacts(run, p)
            except Exception:                                 # noqa: BLE001
                artefactos = {}
        resumen = dict(http.sanitize(p.get("request_summary") or {}))
        if p.get("model_reported"):
            resumen["model_reported"] = http.sanitize(str(p["model_reported"]))
        uso = _numbers(p.get("usage"))
        cerradas = _write_one(
            "UPDATE recon_runs SET status=?, error=?, prompt_version=?, prompt_sha256=?, "
            "request_summary=?, usage=?, latency_ms=?, cost_usd=?, cost_basis=?, artifacts=?, "
            "finished_at=? WHERE run_id=? AND finished_at IS NULL",
            (FAILED, mensaje, p.get("prompt_version"), p.get("prompt_sha256"),
             _dumps(resumen) if resumen else None, _dumps(uso) if uso else None,
             p.get("latency_ms"), p.get("cost_usd"), p.get("cost_basis"),
             _dumps(artefactos) if artefactos else None, store.now(), run_id))
        if cerradas != 1 and p:
            projects.log(run["project_id"], "LATE_RESULT_DISCARDED",
                         {"usage": uso, "latency_ms": p.get("latency_ms"),
                          "error": mensaje[:300]}, run_id=run_id)
    except Exception:                                         # noqa: BLE001 — último recurso
        _write_one("UPDATE recon_runs SET status=?, error=?, finished_at=? WHERE run_id=? "
                   "AND finished_at IS NULL", (FAILED, mensaje, store.now(), run_id))


def _partial_of(res: "engines.EngineResult") -> Dict[str, Any]:
    crudo = res.raw if isinstance(res.raw, dict) else {"raw": str(res.raw)[:2000]}
    return {"prompt_version": res.prompt_version, "prompt_sha256": res.prompt_sha256,
            "request_summary": res.request_summary if isinstance(res.request_summary, dict) else {},
            "usage": _numbers(res.usage), "latency_ms": res.latency_ms, "cost_usd": res.cost_usd,
            "cost_basis": res.cost_basis, "raw": dict(crudo, output=res.output),
            "model_reported": res.model}


def _write(d: str, nombre: str, contenido: str) -> str:
    ruta = os.path.join(d, nombre)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(contenido)
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def execute(run_id: str) -> Optional[Dict]:
    """Ejecuta una corrida QUEUED. Idempotente: una corrida que ya empezó o terminó no se toca."""
    if not _claim(run_id):
        return get(run_id)
    run = get(run_id)
    adapter = engines.get(run["engine_id"])
    if adapter is None:
        _fail(run_id, "el motor ya no está registrado")
        return get(run_id)
    etiqueta = f"[{run['engine_id']}]"
    # 1 — hablar con el motor. Si falla después de la llamada, `e.partial` trae lo que costó.
    try:
        req = build_request(run)
        res = adapter.reconstruct(req)
    except engines.EngineError as e:
        _fail(run_id, f"{etiqueta} {e}", e.partial)
        return get(run_id)
    except Exception as e:                                    # noqa: BLE001 — el hilo no se cae
        _fail(run_id, f"{etiqueta} {type(e).__name__}: {e}")
        return get(run_id)
    parcial: Optional[Dict[str, Any]] = None
    try:
        if not isinstance(res, engines.EngineResult):
            raise TypeError(f"el motor devolvió {type(res).__name__}, no un EngineResult")
        # lo que viene del proveedor se enmascara antes de guardarlo o dibujarlo, sea cual sea el
        # motor; del uso sólo quedan números
        res.output = http.sanitize(res.output)
        res.model = http.sanitize(str(res.model))
        res.usage = _numbers(res.usage)
        parcial = _partial_of(res)
    except Exception as e:                                    # noqa: BLE001
        _fail(run_id, f"{etiqueta} POSTPROCESO {type(e).__name__}: {e}", parcial)
        return get(run_id)
    # 2 — juzgar la salida. Un contrato inválido no se maquilla, pero lo pagado queda registrado.
    try:
        avisos = contract.validate(res.output,
                                   known_asset_ids=tuple(im.asset_id for im in req.images))
    except contract.ContractError as e:
        _fail(run_id, f"{etiqueta} CONTRACT_INVALID: {e}", parcial)
        return get(run_id)
    except Exception as e:                                    # noqa: BLE001
        _fail(run_id, f"{etiqueta} CONTRACT_INVALID: {type(e).__name__}: {e}", parcial)
        return get(run_id)
    # 3 — guardar. Si otro proceso ya cerró esta corrida mientras el motor trabajaba (un reinicio
    # la dio por muerta), no queda nada escrito en una corrida ajena: se deja constancia del
    # resultado tardío en la bitácora, con lo que costó, y nada más.
    escritos: List[str] = []
    try:
        if not _still_mine(run_id):
            projects.log(run["project_id"], "LATE_RESULT_DISCARDED",
                         {"usage": res.usage, "latency_ms": res.latency_ms, "model": res.model},
                         run_id=run_id)
            return get(run_id)
        d = projects.runs_dir(run["project_id"], run_id)
        os.makedirs(d, exist_ok=True)
        salida = json.dumps(res.output, ensure_ascii=False, sort_keys=True)
        caption = f"{adapter.name} · {res.model} · corrida #{run['seq']}"
        dibujo = render.svg(res.output, caption=caption)
        escritos = [os.path.join(d, n) for n in ("output.json", "plan.svg", "request.json",
                                                 "response.json")]
        artefactos = {
            "output.json": _write(d, "output.json", salida),
            "plan.svg": _write(d, "plan.svg", dibujo),
            "request.json": _write(d, "request.json", json.dumps(
                http.sanitize(res.request_summary), ensure_ascii=False, indent=1, default=str)),
            "response.json": _write(d, "response.json", json.dumps(
                http.sanitize(res.raw), ensure_ascii=False, indent=1, default=str)),
            "renderer": render.RENDERER_VERSION,
        }
        resumen = dict(http.sanitize(res.request_summary) or {})
        resumen["model_reported"] = res.model
        cerradas = _write_one(
            "UPDATE recon_runs SET status=?, outcome=?, output=?, output_sha256=?, warnings=?, "
            "prompt_version=?, prompt_sha256=?, request_summary=?, artifacts=?, usage=?, "
            "latency_ms=?, cost_usd=?, cost_basis=?, finished_at=? "
            "WHERE run_id=? AND status=? AND finished_at IS NULL",
            (DONE, res.output["outcome"], salida,
             hashlib.sha256(salida.encode("utf-8")).hexdigest(),
             json.dumps(avisos, ensure_ascii=False), res.prompt_version, res.prompt_sha256,
             json.dumps(resumen, ensure_ascii=False), json.dumps(artefactos),
             json.dumps(res.usage or {}), res.latency_ms, res.cost_usd, res.cost_basis,
             store.now(), run_id, RUNNING))
    except Exception as e:                                    # noqa: BLE001 — lo pagado se registra
        _fail(run_id, f"{etiqueta} POSTPROCESO {type(e).__name__}: {e}", parcial)
        return get(run_id)
    if cerradas != 1:
        # la corrida se cerró entre la comprobación y la escritura: los archivos no son de nadie
        for ruta in escritos:
            try:
                os.remove(ruta)
            except OSError:
                pass
        projects.log(run["project_id"], "LATE_RESULT_DISCARDED",
                     {"usage": res.usage, "latency_ms": res.latency_ms, "model": res.model},
                     run_id=run_id)
    return get(run_id)


def svg_path(run: Dict) -> Optional[str]:
    if run["status"] != DONE:
        return None
    ruta = os.path.join(projects.runs_dir(run["project_id"], run["run_id"]), "plan.svg")
    return ruta if os.path.exists(ruta) else None


# ---- cola: un hilo, como el motor y la ambientación ------------------------------------------
_jobs: "queue.Queue[str]" = queue.Queue()
_worker: Optional[threading.Thread] = None
_lock = threading.Lock()


def _loop() -> None:
    while True:
        rid = _jobs.get()
        try:
            execute(rid)
        except Exception as e:                                # noqa: BLE001
            # Lo único que no puede quedar es una transacción abierta con el candado de escritura,
            # ni una corrida reclamada que diga «generando» hasta el próximo reinicio.
            try:
                store.connect().rollback()
                _write_one("UPDATE recon_runs SET status=?, error=?, finished_at=? WHERE run_id=? "
                           "AND status=? AND finished_at IS NULL",
                           (FAILED, http.sanitize(f"[worker] {type(e).__name__}: {e}")[:2000],
                            store.now(), rid, RUNNING))
            except Exception:                                 # noqa: BLE001
                pass                                         # la base cambió debajo del hilo
        finally:
            try:
                _jobs.task_done()
            except ValueError:
                pass


def enqueue(run_id: str) -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, name="escalimetro-recon", daemon=True)
            _worker.start()
    _jobs.put(run_id)


def pending() -> int:
    return _jobs.qsize()


# ---------------------------------------------------------------------------------------------
# calificar
# ---------------------------------------------------------------------------------------------
def rate(project_id: str, run_id: str, rating: str, comment: str, author: Optional[str]) -> None:
    """Una calificación vigente por corrida —la última—, con todo el historial conservado."""
    r = get_in_project(project_id, run_id)
    if r is None:
        raise projects.ReconError("Esa corrida no es de este proyecto.")
    if rating not in RATINGS:
        raise projects.ReconError("La calificación es Excelente, Bueno, Malo o Pésimo.")
    if r["status"] != DONE:
        raise projects.ReconError("Sólo se califica una corrida terminada.")
    nuevo = (comment or "").strip()[:projects.MAX_TEXT]
    vigente = current_rating(run_id)
    if vigente and vigente["rating"] == rating and (vigente["comment"] or "") == nuevo:
        return                                               # volver a apretar lo mismo no es un juicio nuevo
    store.ex("INSERT INTO recon_ratings(run_id, rating, comment, output_sha256, author, created_at) "
             "VALUES (?,?,?,?,?,?)", (run_id, rating, nuevo, r["output_sha256"], author,
                                      store.now()))
    projects.log(project_id, "RATED", {"rating": rating}, run_id=run_id, author=author)


def current_rating(run_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM recon_ratings WHERE run_id=? ORDER BY id DESC LIMIT 1", (run_id,))
    return dict(r) if r else None


def rating_history(run_id: str) -> List[Dict]:
    return [dict(r) for r in store.q("SELECT * FROM recon_ratings WHERE run_id=? ORDER BY id DESC",
                                     (run_id,))]


# ---------------------------------------------------------------------------------------------
# comparar y medir
# ---------------------------------------------------------------------------------------------
def card(run: Dict, project: Optional[Dict] = None) -> Dict:
    """Lo que una columna de la comparación (o una fila de la lista) necesita saber.

    «A ciegas» es toda corrida creada antes del reveal de un proyecto que tiene plano real, también
    las que se hicieron antes de cargarlo: el operador tampoco lo había mostrado entonces."""
    out = run["output"] or {}
    cal = current_rating(run["run_id"])
    p = project or projects.get(run["project_id"]) or {}
    tiene_gt = p.get("gt_state", "NONE") != "NONE"
    creada = run["gt_state_at_creation"]
    return {
        "run": run, "rating": cal, "outcome_label": OUTCOME_LABEL.get(run["outcome"] or "", ""),
        "rooms": out.get("rooms") or [], "rooms_placed": len(contract.placed(out)),
        "prompts": prompts_in_lineage(run), "has_svg": svg_path(run) is not None,
        "blind": tiene_gt and creada != "REVEALED",
        "blind_before_gt": tiene_gt and creada == "NONE",
        "after_reveal": creada == "REVEALED",
    }


def compare(project_id: str, run_ids: List[str]) -> List[Dict]:
    ids = list(dict.fromkeys(i for i in run_ids if i))
    if not (COMPARE_MIN <= len(ids) <= COMPARE_MAX):
        raise projects.ReconError(f"Se comparan de {COMPARE_MIN} a {COMPARE_MAX} corridas; "
                                  f"llegaron {len(ids)}.")
    corridas = [get_in_project(project_id, i) for i in ids]
    if any(r is None for r in corridas):
        raise projects.ReconError("Alguna corrida no es de este proyecto.")
    return [card(r) for r in corridas]


def metrics(project_id: str) -> Dict[str, Any]:
    """E37 §14 — lo que el proyecto sabe medir de la meta 90/10, sin inventar nada.

    No hay un puntaje compuesto: cada dato va por separado y dice si falta. Recintos esperados y
    los juicios de adyacencia, posición y geometría los pone una persona; no hay métrica automática
    fiable para eso todavía."""
    p = projects.get(project_id)
    corridas = of_project(project_id)
    j = projects.current_judgment(project_id)
    final = get(j["final_run_id"]) if j and j["final_run_id"] else None
    revelado = bool(p and p["gt_state"] == "REVEALED")
    fin = None
    if final:
        out = final["output"] or {}
        cal = current_rating(final["run_id"])
        fin = {"run_id": final["run_id"], "seq": final["seq"],
               "rating": cal["rating"] if cal else None,
               "prompts_in_lineage": prompts_in_lineage(final),
               "rooms_detected": len(out.get("rooms") or []),
               "rooms_placed": len(contract.placed(out))}
    return {
        "runs": len(corridas),
        "runs_done": sum(1 for r in corridas if r["status"] == DONE),
        "runs_failed": sum(1 for r in corridas if r["status"] == FAILED),
        "human_prompts": sum(1 for r in corridas if r["origin"] == CORRECTION),
        "final": fin,
        "human_minutes": j["human_minutes"] if j else None,
        "needed_manual_cad": j["needed_manual_cad"] if j else None,
        # con un plano real OCULTO no se anotan; sin plano real son una etiqueta humana
        "expected_rooms": (j["expected_rooms"] if (j and p and p["gt_state"] != "HIDDEN_FROM_ENGINE")
                           else None),
        "expected_rooms_source": (("plano real" if j["gt_state_at_creation"] == "REVEALED"
                                   else "etiqueta") if j and j["expected_rooms"] else None),
        "adjacency": j["adjacency"] if j else None,
        "relative_position": j["relative_position"] if j else None,
        "geometry": j["geometry"] if j else None,
        "gt_revealed": revelado,
    }
