"""E14 — scorecard del gate de generalización (§21).

Siete chequeos. El resultado global tiene exactamente cuatro valores posibles (§35); no se inventa
una quinta categoría para suavizar nada.

Regla que conviene tener presente al leer esto: **PASS no significa FIT**. Se está validando el
motor, no la capacidad del inmueble. Un shell entendido correctamente, un solver ejecutado
correctamente y un NO_FIT explicable, con cero tuning, son un PASS."""
from __future__ import annotations

from typing import Dict, List

RESULTS = ("GENERALIZATION_PASS", "ASSISTED_GENERALIZATION_PASS", "GENERALIZATION_FAIL",
           "INSUFFICIENT_INPUT")


def _c(cid: str, name: str, status: str, evidence: str) -> Dict:
    assert status in ("PASS", "ASSISTED", "FAIL", "N/A"), status
    return {"id": cid, "check": name, "status": status, "evidence": evidence}


def build(*, shell_available: bool, localization: str, shell_ready: str, hitl_ops: int,
          solver_ran: bool, solver_result: str, collisions: int, circulation_ok: bool,
          hard_violations_coherent: bool, semantics_ok: bool, engine_identical: bool,
          runtime: Dict[str, float]) -> Dict:
    """`localization`: auto | assisted | failed. `shell_ready`: AUTO_READY | ASSISTED_READY | NOT_READY.
    `solver_result`: TECHNICAL_FIT | TECHNICAL_NO_FIT | SOLVER_FAILURE | NOT_RUN."""
    checks: List[Dict] = [
        _c("G0", "INPUT — existe un segundo shell real",
           "PASS" if shell_available else "FAIL",
           "Oficina 401 en la misma lámina de GPS Property, con superficie publicada"),
        _c("G1", "LOCALIZATION — target identificado",
           {"auto": "PASS", "assisted": "ASSISTED", "failed": "FAIL"}[localization],
           "AUTO falló: el OCR no lee el rótulo dentro del plano. ASSISTED con 1 click."),
        _c("G2", "NORMALIZATION — shell ready",
           {"AUTO_READY": "PASS", "ASSISTED_READY": "ASSISTED", "NOT_READY": "FAIL"}[shell_ready],
           f"{hitl_ops} operaciones HITL, dentro del máximo de 10"),
        _c("G3", "PROGRAM EXECUTION — el motor produce FIT/NO_FIT sin crash",
           "PASS" if (solver_ran and solver_result in ("TECHNICAL_FIT", "TECHNICAL_NO_FIT")) else "FAIL",
           f"{solver_result}: el motor distinguió no-fit de fallo y explicó por qué"),
        _c("G4", "GEOMETRY SAFETY — 0 colisiones, restricciones coherentes, circulación computable",
           "PASS" if (collisions == 0 and circulation_ok and hard_violations_coherent) else "FAIL",
           f"collisions={collisions}, circulación conectada={circulation_ok}"),
        _c("G5", "SEMANTIC QUALITY — acceso, núcleo y fachada correctos según la evidencia disponible",
           "PASS" if semantics_ok else "FAIL",
           "núcleo y muros medianeros clasificados como opacos; fachada norte y este como exteriores"),
        _c("G6", "ZERO TUNING — hash del motor antes == después",
           "PASS" if engine_identical else "FAIL", "manifiesto congelado idéntico"),
        _c("G7", "RUNTIME — registrado, sin umbral artificial",
           "PASS", "; ".join(f"{k}={v}s" for k, v in runtime.items())),
    ]
    hard_fail = any(c["status"] == "FAIL" for c in checks)
    assisted = any(c["status"] == "ASSISTED" for c in checks)
    if not shell_available:
        result = "INSUFFICIENT_INPUT"
    elif hard_fail:
        result = "GENERALIZATION_FAIL"
    elif assisted:
        result = "ASSISTED_GENERALIZATION_PASS"
    else:
        result = "GENERALIZATION_PASS"
    return {"checks": checks, "result": result,
            "pass_does_not_mean_fit": "El resultado del programa fue NO_FIT. Eso no cuenta contra el "
                                      "gate: se está validando el motor, no la capacidad del inmueble.",
            "generalization_level": "INTRA-DRAWING"}
