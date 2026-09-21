"""E32 §A/§H — EL PILOTO DE AMBIENTACIÓN: qué hay configurado y quién decide.

Este módulo existe para separar tres cosas que se confunden con facilidad y cuya confusión sería
cara:

    CREDENCIAL PRESENTE   hay una clave en el entorno. No significa nada más.
    SMOKE TEST OK         ese proveedor respondió una vez con una imagen. Tampoco significa nada más.
    PROVEEDOR APROBADO    una PERSONA miró las tasas del bake-off y decidió. Sólo esto habilita
                          que una imagen llegue a un cliente.

§H del encargo es explícito: "Key presence must NEVER select the provider". Por eso `approved()`
lee una decisión guardada —con su evidencia: muestra, tasas, costo, latencia— y no el entorno. La
variable `ESCALIMETRO_STAGING_PROVIDER` ya no elige nada; se conserva sólo para poder decir en la
consola que está puesta y que no manda.

Las credenciales no salen de acá jamás. `readiness()` devuelve booleanos y nombres de variable;
nunca un valor, ni un fragmento, ni una longitud.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Dict, List, Optional

from .. import store
from . import settings

APPROVAL_KEY = "staging_approved_provider"
SCHEMA_VERSION = "pilot_approval_v1"

#: §2 de E31.1 — BFL queda fuera hasta que el dueño del producto decida sobre la cláusula de
#: licencia que le da a BFL derechos perpetuos sobre las fotos que le mandemos. El adaptador no se
#: borra; simplemente no participa.
EXCLUDED = {"bfl": "DESHABILITADO — requiere decisión de licencia (derechos perpetuos de BFL "
                   "sobre Inputs y Outputs)"}
#: Los que participan del bake-off de E31.1.
PILOT_PROVIDERS = ("openai", "gemini")


class ApprovalError(ValueError):
    """No se puede aprobar un proveedor así."""


# ---------------------------------------------------------------------------------------------
# aprobación
# ---------------------------------------------------------------------------------------------
def approved() -> Optional[Dict]:
    """La decisión humana vigente, o None. Es la única cosa que habilita staging de producto."""
    raw = settings.get(APPROVAL_KEY)
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    return d if d.get("provider") else None


def approved_provider_name() -> Optional[str]:
    a = approved()
    return a["provider"] if a else None


def approve(provider: str, model: str, evidence: Dict, reviewer: str = "",
            override_reason: str = "") -> Dict:
    """Aprueba un proveedor para el piloto. Exige EVIDENCIA, no entusiasmo.

    `evidence` es el bloque de métricas del bake-off (muestra, tasas, costo, latencia). Si la
    compuerta no se cumple, sólo se puede aprobar con un motivo escrito, y queda marcado como
    OVERRIDE para siempre: nadie que lea esto después puede confundir una excepción con un
    resultado."""
    from .. import providers                                  # noqa: PLC0415
    if provider in EXCLUDED:
        raise ApprovalError(EXCLUDED[provider])
    if not providers.known(provider):
        raise ApprovalError(f"proveedor desconocido: {provider}")
    paso = bool((evidence or {}).get("gate", {}).get("passes"))
    if not paso and not override_reason.strip():
        raise ApprovalError("Este proveedor no cumple la compuerta. Para aprobarlo igual hace "
                            "falta un motivo escrito, y quedará marcado como OVERRIDE.")
    d = {"schema_version": SCHEMA_VERSION, "provider": provider, "model": model,
         "approved_at": store.now(), "reviewer": (reviewer or "")[:80],
         "evidence": evidence or {}, "gate_passed": paso,
         "override_reason": override_reason.strip()[:500] or None}
    settings.put(APPROVAL_KEY, json.dumps(d, ensure_ascii=False))
    log_event("PROVIDER_APPROVED", detail={"provider": provider, "model": model,
                                           "gate_passed": paso,
                                           "override": bool(d["override_reason"])},
              author=reviewer)
    return d


def revoke(reason: str = "", reviewer: str = "") -> None:
    a = approved()
    settings.put(APPROVAL_KEY, None)
    log_event("PROVIDER_REVOKED", detail={"provider": (a or {}).get("provider"),
                                          "reason": reason[:300]}, author=reviewer)


# ---------------------------------------------------------------------------------------------
# §A — panel de preparación
# ---------------------------------------------------------------------------------------------
def readiness() -> Dict:
    """Todo lo que la consola necesita mostrar, sin un solo secreto.

    Devuelve booleanos (`credential`), nombres de variable (`env`) y estados. Nunca el valor, ni
    parte de él, ni su longitud: una longitud también es información sobre una clave."""
    from .. import benchmark, providers                       # noqa: PLC0415
    from . import assets                                      # noqa: PLC0415

    fotos = store.q("SELECT property_id, COUNT(*) n FROM property_assets "
                    "WHERE kind='PHOTO_ORIGINAL' GROUP BY property_id")
    total_fotos = sum(r["n"] for r in fotos)
    ds = benchmark.dataset()
    ap = approved()

    provs: List[Dict] = []
    for p in providers.catalog():
        smoke = last_smoke(p["name"])
        provs.append({
            "name": p["name"], "model": p["model"], "env": p["env"],
            "credential": p["available"],
            "excluded": p["name"] in EXCLUDED,
            "excluded_reason": EXCLUDED.get(p["name"]),
            "in_pilot": p["name"] in PILOT_PROVIDERS,
            "smoke": smoke,
            "approved": bool(ap and ap["provider"] == p["name"]),
        })
    listos = [p for p in provs if p["in_pilot"] and p["credential"]]
    return {
        "photos": {"total": total_fotos, "properties": len(fotos),
                   "benchmark_eligible": len(ds["photos"]),
                   "benchmark_properties": len({f["property_id"] for f in ds["photos"]}),
                   "min_photos": benchmark.MIN_PHOTOS, "min_spaces": benchmark.MIN_SPACES},
        "providers": provs,
        "pilot_ready": len(listos) >= 2 and len(ds["photos"]) >= benchmark.MIN_PHOTOS,
        "credentials_present": len(listos),
        "approved": ap,
        "approved_label": (f'{ap["provider"]} · {ap["model"]}' if ap else "NINGUNO"),
        "env_select_set": bool((os.environ.get(providers.ENV_SELECT) or "").strip()),
        "blockers": _blockers(provs, ds, ap),
    }


def _blockers(provs: List[Dict], ds: Dict, ap: Optional[Dict]) -> List[str]:
    """Lo que falta, dicho como lo diría alguien que quiere resolverlo. E32 §34: no esconder."""
    from .. import benchmark                                  # noqa: PLC0415
    out = []
    n = len(ds["photos"])
    espacios = len({f["property_id"] for f in ds["photos"]})
    if n < benchmark.MIN_PHOTOS:
        out.append(f"faltan fotos reales en el dataset: hay {n}, el mínimo es {benchmark.MIN_PHOTOS}")
    if espacios < benchmark.MIN_SPACES:
        out.append(f"faltan espacios distintos: hay {espacios}, el mínimo es {benchmark.MIN_SPACES}")
    sin = [p["name"] for p in provs if p["in_pilot"] and not p["credential"]]
    for s in sin:
        env = next(p["env"] for p in provs if p["name"] == s)
        out.append(f"falta la credencial de {s} ({env}) en el entorno")
    if len(sin) == 1:
        out.append("con un solo proveedor no se puede declarar ganador: el bake-off compara dos")
    if not ap:
        out.append("ningún proveedor aprobado: la ambientación de producto está deshabilitada")
    return out


# ---------------------------------------------------------------------------------------------
# eventos humanos (lo único que no se puede derivar)
# ---------------------------------------------------------------------------------------------
def log_event(kind: str, property_id: Optional[str] = None, detail: Optional[Dict] = None,
              author: str = "") -> str:
    """Registra una acción humana. `detail` se sanea contra credenciales antes de guardarse."""
    from ..providers import base                              # noqa: PLC0415
    eid = "ev_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO lab_events(event_id, kind, property_id, detail, author, created_at) "
             "VALUES (?,?,?,?,?,?)",
             (eid, kind, property_id,
              json.dumps(base.sanitize(detail or {}), ensure_ascii=False),
              (author or "")[:80], store.now()))
    return eid


def events(kind: Optional[str] = None, property_id: Optional[str] = None,
           limit: int = 50) -> List[Dict]:
    sql, args = "SELECT * FROM lab_events WHERE 1=1", []
    if kind:
        sql += " AND kind=?"; args.append(kind)
    if property_id:
        sql += " AND property_id=?"; args.append(property_id)
    sql += " ORDER BY created_at DESC LIMIT ?"; args.append(int(limit))
    out = []
    for r in store.q(sql, tuple(args)):
        d = dict(r)
        d["detail_obj"] = store.js(d["detail"], {}) or {}
        out.append(d)
    return out


def last_smoke(provider: str) -> Optional[Dict]:
    """El último smoke test de un proveedor: éxito, latencia, costo, error saneado."""
    for e in events("PROVIDER_SMOKE", limit=100):
        if e["detail_obj"].get("provider") == provider:
            return dict(e["detail_obj"], at=e["created_at"])
    return None
