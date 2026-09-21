"""E31 §7/§13/§14/§15 — el BAKE-OFF de ambientación: mismas fotos, misma petición, varios proveedores.

Qué es: un harness que toma un manifiesto de fotos reales (`staging_benchmark_v1.json`), crea un
intento por (proveedor × foto × repetición) con la MISMA petición canónica, los ejecuta, espera la
revisión humana de cada candidato y después agrega métricas por proveedor, aplica la compuerta y
propone —o no— un ganador.

Qué NO es: una demo. Sin credencial, cada proveedor queda en HUMAN_ACTION_REQUIRED y el archivo de
resultados lo dice con esas palabras. No hay resultados sintéticos, no hay "estimados" presentados
como medidos, no se rellena una tabla para que se vea completa. §4: "NO simular que el benchmark
ocurrió".

La métrica que manda (§13) es la TASA DE IMÁGENES APROBADAS —fidelidad PASS y publicación
aprobada por un humano—, no que la API haya respondido 200.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import uuid
from typing import Dict, List, Optional

from . import store
from .domain import assets, pilot, presets, properties, staging, visual

MANIFEST_VERSION = "staging_benchmark_v1"
RESULTS_VERSION = "staging_benchmark_results_v1"
DEFAULT_STYLE = "CONTEMPORARY"
MIN_PHOTOS, IDEAL_PHOTOS = 8, 10
MIN_SPACES = 3

#: E32 §B — los rasgos que hacen difícil una foto. Los declara un humano al sumarla al dataset;
#: no se infieren ni se inventan. Sirven para leer después POR QUÉ falló un proveedor: si todos
#: sus fallos de fidelidad son fotos con COLUMNS, eso es un patrón y no mala suerte.
DIFFICULT_FEATURES = ("WINDOWS", "COLUMNS", "DOORS", "GLAZING", "CEILING", "CORNER",
                      "WIDE_ANGLE", "EXTERIOR_VIEW", "OPEN_PLAN", "OTHER_DIFFICULT")

#: §14 — la compuerta provisional. Con muestras chicas es evidencia de piloto, no prueba.
GATE = {"fidelity_pass_rate": 0.85, "approval_rate": 0.75, "max_cost_per_approved_usd": 4.0,
        "min_sample_for_confidence": 20}


# =================================================================================================
# E32 §B — EL DATASET VIVE EN LA BASE, no en un archivo que alguien tiene que editar a mano.
# El JSON se sigue escribiendo (lo lee la CLI y es el artefacto que se archiva), pero se GENERA
# desde la tabla en cada cambio: una sola fuente de verdad, editable desde el navegador.
# =================================================================================================
def manifest_path() -> str:
    """El manifiesto vivo va al VOLUMEN, no al repo: es estado de ejecución, y un deploy no puede
    borrarlo. La copia del repo queda como plantilla y documentación."""
    return os.path.join(store.DATA_DIR, "benchmarks", "staging_benchmark_v1.json")


def add_photo(asset_id: str, property_id: str, tags: Optional[List[str]] = None,
              reason: str = "") -> None:
    """Suma una foto real al dataset. Los rasgos difíciles los declara un humano: no se inventan."""
    a = assets.get(asset_id, property_id)
    if a is None or a["kind"] != assets.PHOTO_ORIGINAL:
        raise ValueError("esa foto no pertenece a la propiedad o no es una foto original")
    limpias = [(t or "").strip().upper() for t in (tags or []) if (t or "").strip()]
    malos = [t for t in limpias if t not in DIFFICULT_FEATURES]
    if malos:
        raise ValueError(f"rasgos difíciles desconocidos: {malos}")
    store.ex("INSERT INTO benchmark_photos(asset_id, property_id, tags, reason, added_at) "
             "VALUES (?,?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET tags=excluded.tags, "
             "reason=excluded.reason",
             (asset_id, property_id, json.dumps(sorted(set(limpias))), reason[:300], store.now()))
    write_manifest()


def remove_photo(asset_id: str) -> None:
    store.ex("DELETE FROM benchmark_photos WHERE asset_id=?", (asset_id,))
    write_manifest()


def dataset() -> Dict:
    """El manifiesto, generado desde la tabla. Nunca se lee de disco para decidir nada."""
    man = empty_manifest()
    for r in store.q("SELECT * FROM benchmark_photos ORDER BY added_at"):
        a = assets.get(r["asset_id"], r["property_id"])
        if a is None:
            continue                                          # la foto se borró: deja de contar
        man["photos"].append({
            "photo_id": a["asset_id"], "property_id": r["property_id"], "asset_id": a["asset_id"],
            "original_sha256": a["sha256"], "width_px": a["width_px"], "height_px": a["height_px"],
            "notes": r["reason"] or "", "inclusion_reason": r["reason"] or "",
            "difficult_features": store.js(r["tags"], []) or []})
    espacios = len({f["property_id"] for f in man["photos"]})
    man["status"] = ("READY" if len(man["photos"]) >= MIN_PHOTOS and espacios >= MIN_SPACES
                     else ("INSUFFICIENT_PHOTOS" if man["photos"] else "AWAITING_REAL_PHOTOS"))
    man["distinct_spaces"] = espacios
    if man["photos"]:
        man.pop("_nota", None)
    return man


def write_manifest() -> str:
    man = dataset()
    _write(manifest_path(), man)
    return manifest_path()


def eligible_photos() -> List[Dict]:
    """Todas las PHOTO_ORIGINAL del sistema, marcando cuáles ya están en el dataset."""
    dentro = {r["asset_id"] for r in store.q("SELECT asset_id FROM benchmark_photos")}
    tags = {r["asset_id"]: store.js(r["tags"], []) or []
            for r in store.q("SELECT asset_id, tags FROM benchmark_photos")}
    out = []
    for p in store.q("SELECT property_id, title FROM properties ORDER BY created_at"):
        for a in assets.list_of_kind(p["property_id"], assets.PHOTO_ORIGINAL):
            out.append({"asset": a, "property_id": p["property_id"], "title": p["title"],
                        "selected": a["asset_id"] in dentro,
                        "tags": tags.get(a["asset_id"], [])})
    return out


# =================================================================================================
# manifiesto
# =================================================================================================
def empty_manifest() -> Dict:
    return {"manifest_version": MANIFEST_VERSION, "created_at": store.now(),
            "style": DEFAULT_STYLE, "request_version": staging.REQUEST_VERSION,
            "status": "AWAITING_REAL_PHOTOS",
            "requirements": {"min_photos": MIN_PHOTOS, "ideal_photos": IDEAL_PHOTOS,
                             "min_spaces": MIN_SPACES, "real_photos_only": True,
                             "no_stock_without_license": True},
            "photos": [],
            "_nota": ("Sin fotos reales de oficinas vacías disponibles localmente. No se rellena con "
                      "imágenes sintéticas ni con stock sin licencia. Subir las fotos a una o más "
                      "propiedades y correr: python -m webapp.benchmark init --from-properties "
                      "p_xxx,p_yyy")}


def manifest_from_properties(property_ids: List[str], notes: Optional[Dict[str, str]] = None,
                             features: Optional[Dict[str, List[str]]] = None) -> Dict:
    """Arma el manifiesto desde las PHOTO_ORIGINAL de propiedades existentes. Las fotos entran por
    la misma puerta que las de producción: mismo sniffing, mismo hash, mismo aislamiento."""
    man = empty_manifest()
    for pid in property_ids:
        properties.require(pid)
        for a in assets.list_of_kind(pid, assets.PHOTO_ORIGINAL):
            man["photos"].append({
                "photo_id": a["asset_id"], "property_id": pid, "asset_id": a["asset_id"],
                "original_sha256": a["sha256"], "width_px": a["width_px"], "height_px": a["height_px"],
                "notes": (notes or {}).get(a["asset_id"], ""),
                "difficult_features": (features or {}).get(a["asset_id"], [])})
    man["status"] = "READY" if len(man["photos"]) >= MIN_PHOTOS else "INSUFFICIENT_PHOTOS"
    return man


def validate_manifest(man: Dict) -> List[str]:
    errs = []
    if man.get("manifest_version") != MANIFEST_VERSION:
        errs.append("manifest_version desconocida")
    fotos = man.get("photos") or []
    if len(fotos) < MIN_PHOTOS:
        errs.append(f"hacen falta al menos {MIN_PHOTOS} fotos reales (hay {len(fotos)})")
    espacios = {f.get("property_id") for f in fotos}
    if len(espacios) < MIN_SPACES:
        errs.append(f"hacen falta fotos de al menos {MIN_SPACES} espacios distintos (hay {len(espacios)})")
    for f in fotos:
        a = assets.get(f.get("asset_id", ""), f.get("property_id"))
        if a is None:
            errs.append(f"foto {f.get('photo_id')} no existe en la propiedad indicada")
        elif a["sha256"] != f.get("original_sha256"):
            errs.append(f"foto {f.get('photo_id')} cambió desde que se armó el manifiesto")
        for d in f.get("difficult_features") or []:
            if d not in DIFFICULT_FEATURES:
                errs.append(f"rasgo difícil desconocido en {f.get('photo_id')}: {d}")
    return errs


# =================================================================================================
# ejecución
# =================================================================================================
def plan(man: Dict, providers: List[str], runs_per_photo: int, style: str) -> List[Dict]:
    """Proveedor × foto × repetición. Misma petición para todos (§7)."""
    presets.require_style(style)
    req = staging.canonical_request(style)
    out = []
    for prov in providers:
        for f in man["photos"]:
            for k in range(runs_per_photo):
                out.append({"provider": prov, "photo_id": f["photo_id"],
                            "property_id": f["property_id"], "asset_id": f["asset_id"],
                            "run": k + 1, "style": style,
                            "request_version": req["request_version"],
                            "prompt_hash": req["prompt_hash"]})
    return out


def execute(man: Dict, providers: List[str], runs_per_photo: int = 2, style: str = DEFAULT_STYLE,
            benchmark_id: Optional[str] = None, dry_run: bool = False) -> Dict:
    """Crea y corre los intentos. Un proveedor sin credencial NO se simula: queda en
    HUMAN_ACTION_REQUIRED y no se crea ningún intento suyo."""
    benchmark_id = benchmark_id or ("bm_" + uuid.uuid4().hex[:10])
    estado_prov: Dict[str, Dict] = {}
    creados: List[str] = []
    for prov in providers:
        p = visual.get_provider(prov)
        estado_prov[prov] = {"model": p.model, "available": p.available(),
                             "status": "READY" if p.available() else "HUMAN_ACTION_REQUIRED",
                             "reason": None if p.available() else
                             f"falta la credencial del proveedor '{prov}' en el entorno"}
    for item in plan(man, providers, runs_per_photo, style):
        if not estado_prov[item["provider"]]["available"]:
            continue
        if dry_run:
            continue
        aid = staging.create_attempt(item["property_id"], item["asset_id"], style,
                                     provider_name=item["provider"], benchmark_id=benchmark_id)
        staging.run_attempt(aid)
        creados.append(aid)
    return {"benchmark_id": benchmark_id, "providers": estado_prov, "attempts": creados,
            "planned": len(plan(man, providers, runs_per_photo, style)), "dry_run": dry_run}


# =================================================================================================
# §13 — métricas. Sólo cuentan las revisiones HUMANAS.
# =================================================================================================
def _pct(a: int, b: int) -> Optional[float]:
    return round(a / b, 4) if b else None


def _p95(xs: List[float]) -> Optional[float]:
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, int(round(0.95 * (len(xs) - 1))))
    return xs[k]


def aggregate(attempts: List[Dict]) -> Dict[str, Dict]:
    """Por proveedor. `attempts` son filas de staging_attempts (dicts)."""
    por: Dict[str, List[Dict]] = {}
    for a in attempts:
        por.setdefault(a["provider"], []).append(a)
    out: Dict[str, Dict] = {}
    for prov, rows in por.items():
        total = len(rows)
        ok_api = [r for r in rows if r["status"] == "GENERATED"]
        revisados = [r for r in ok_api if r["review_status"] != "PENDING"]
        f_pass = [r for r in revisados if r["fidelity_status"] == "PASS"]
        aprob = [r for r in revisados if r["review_status"] == "APPROVED"]
        lat = [float(r["latency_ms"]) for r in ok_api if r.get("latency_ms") is not None]
        costos = [float(r["cost_usd"]) for r in rows if r.get("cost_usd") is not None]
        costo_total = round(sum(costos), 4) if costos else None
        razones: Dict[str, int] = {}
        for r in revisados:
            for k in (store.js(r.get("failure_reasons"), []) or []):
                razones[k] = razones.get(k, 0) + 1
        fotos = {r["source_asset_id"] for r in rows}
        reintentos = total - len(fotos) if fotos else 0
        bases = {r.get("cost_basis") for r in rows if r.get("cost_basis")}
        out[prov] = {
            "provider": prov,
            "model": sorted({r.get("model") for r in rows if r.get("model")}),
            "request_versions": sorted({r["request_version"] for r in rows}),
            "prompt_hashes": sorted({r["prompt_hash"] for r in rows}),
            "total_generations": total,
            "api_success": len(ok_api),
            "api_success_rate": _pct(len(ok_api), total),
            "reviewed": len(revisados),
            "pending_review": len(ok_api) - len(revisados),
            "fidelity_pass": len(f_pass),
            "fidelity_pass_rate": _pct(len(f_pass), len(revisados)),
            "approved": len(aprob),
            "approval_rate": _pct(len(aprob), len(revisados)),
            "avg_quality_among_fidelity_pass": (round(statistics.mean(
                [r["quality_score"] for r in f_pass if r.get("quality_score")]), 2)
                if any(r.get("quality_score") for r in f_pass) else None),
            "photos": len(fotos),
            "retry_rate": _pct(reintentos, len(fotos)) if fotos else None,
            "latency_ms": {"mean": round(statistics.mean(lat)) if lat else None,
                           "median": round(statistics.median(lat)) if lat else None,
                           "p95": round(_p95(lat)) if len(lat) >= 5 else None,
                           "n": len(lat)},
            "cost": {"total_usd": costo_total,
                     "basis": sorted(bases),
                     "per_generation_usd": round(costo_total / total, 4) if (costo_total is not None and total) else None,
                     "per_fidelity_pass_usd": round(costo_total / len(f_pass), 4) if (costo_total is not None and f_pass) else None,
                     "per_approved_usd": round(costo_total / len(aprob), 4) if (costo_total is not None and aprob) else None},
            "hard_failure_reasons": dict(sorted(razones.items(), key=lambda kv: -kv[1])),
            "provider_errors": [r.get("error") for r in rows if r["status"] == "FAILED"][:10],
            "sample_thin": len(revisados) < GATE["min_sample_for_confidence"],
        }
    return out


def gate(m: Dict, rights_verified: bool = False) -> Dict:
    """§14 — pasa o no, con motivos. Nunca 'casi'."""
    motivos = []
    if m["reviewed"] == 0:
        return {"passes": False, "reasons": ["sin revisiones humanas"], "evidence": "none"}
    if (m["fidelity_pass_rate"] or 0) < GATE["fidelity_pass_rate"]:
        motivos.append(f"fidelidad {m['fidelity_pass_rate']:.0%} < {GATE['fidelity_pass_rate']:.0%}")
    if (m["approval_rate"] or 0) < GATE["approval_rate"]:
        motivos.append(f"aprobación {m['approval_rate']:.0%} < {GATE['approval_rate']:.0%}")
    top = next(iter(m["hard_failure_reasons"].items()), None)
    if top and m["reviewed"] and top[1] / m["reviewed"] >= 0.25:
        motivos.append(f"patrón estructural recurrente: {top[0]} en {top[1]}/{m['reviewed']}")
    cpa = m["cost"]["per_approved_usd"]
    if cpa is None or cpa > GATE["max_cost_per_approved_usd"]:
        motivos.append(f"costo por imagen aprobada {'desconocido' if cpa is None else f'${cpa:.2f}'} "
                       f"incompatible con un pack de ~USD 100 (tope ${GATE['max_cost_per_approved_usd']:.2f})")
    if not rights_verified:
        motivos.append("derechos comerciales no verificados por escrito")
    return {"passes": not motivos, "reasons": motivos,
            "evidence": "pilot_only" if m["sample_thin"] else "adequate_sample"}


def select(metrics: Dict[str, Dict], rights: Optional[Dict[str, bool]] = None) -> Dict:
    """§15 — prioridad: fidelidad, aprobación, repetibilidad, costo por aprobada, latencia."""
    rights = rights or {}
    veredictos = {p: gate(m, rights.get(p, False)) for p, m in metrics.items()}
    aptos = [p for p, v in veredictos.items() if v["passes"]]
    if not aptos:
        return {"winner": None, "verdict": "NO_WINNER", "gates": veredictos}
    def clave(p):
        m = metrics[p]
        return (-(m["fidelity_pass_rate"] or 0), -(m["approval_rate"] or 0),
                -(m["retry_rate"] or 0) * -1,          # menos reintentos = más repetible
                m["cost"]["per_approved_usd"] or 1e9, m["latency_ms"]["median"] or 1e9)
    ganador = sorted(aptos, key=clave)[0]
    return {"winner": ganador, "verdict": "SELECTED", "gates": veredictos}


def estimate(providers: List[str], n_photos: int, runs: int) -> Dict:
    """Cuánto costaría el lote, según precios de lista. Para pedir confirmación ANTES de gastar."""
    from . import providers as provmod                        # noqa: PLC0415
    por: Dict[str, Optional[float]] = {}
    total = 0.0
    desconocido = False
    for p in providers:
        u = provmod.estimate_usd(p)
        por[p] = u
        if u is None:
            desconocido = True
        else:
            total += u * n_photos * runs
    return {"per_generation": por, "attempts": len(providers) * n_photos * runs,
            "total_usd": round(total, 2), "complete": not desconocido, "basis": "list_price"}


def start(providers: List[str], runs: int = 2, style: str = DEFAULT_STYLE,
          author: str = "") -> Dict:
    """Crea los intentos del bake-off y los ENCOLA. No bloquea: el worker los va tomando de a uno y
    la consola sondea el progreso.

    Cada intento cuenta. No hay reintento silencioso dentro del lote: si uno falla, falla y queda
    contado, porque una tasa de éxito que esconde los reintentos no es una tasa de éxito."""
    man = dataset()
    errs = validate_manifest(man)
    if errs:
        raise ValueError("; ".join(errs))
    excluidos = [p for p in providers if p in pilot.EXCLUDED]
    if excluidos:
        raise ValueError(f"proveedor excluido del piloto: {', '.join(excluidos)}")
    sin = [p for p in providers if not visual.get_provider(p).available()]
    if sin:
        raise ValueError(f"sin credencial para: {', '.join(sin)}")
    if len(providers) < 2:
        raise ValueError("el bake-off compara al menos dos proveedores: con uno no hay comparación")
    bid = "bm_" + uuid.uuid4().hex[:10]
    creados = []
    for item in plan(man, providers, runs, style):
        aid = staging.create_attempt(item["property_id"], item["asset_id"], style,
                                     provider_name=item["provider"], benchmark_id=bid,
                                     purpose="BENCHMARK")
        creados.append(aid)
        staging.enqueue(aid)
    pilot.log_event("BENCHMARK_RUN", detail={"benchmark_id": bid, "providers": providers,
                                             "runs": runs, "style": style,
                                             "attempts": len(creados),
                                             "estimate": estimate(providers, len(man["photos"]), runs)},
                    author=author)
    return {"benchmark_id": bid, "attempts": creados, "planned": len(creados)}


def progress(benchmark_id: str) -> Dict:
    """Para el sondeo de la consola: cuántos van, cuánto se gastó, cuánto falta por revisar."""
    filas = attempts_of(benchmark_id)
    por_estado: Dict[str, int] = {}
    for a in filas:
        por_estado[a["status"]] = por_estado.get(a["status"], 0) + 1
    gasto = sum(float(a["cost_usd"]) for a in filas if a.get("cost_usd") is not None)
    hechos = por_estado.get("GENERATED", 0) + por_estado.get("FAILED", 0)
    return {"benchmark_id": benchmark_id, "total": len(filas), "by_status": por_estado,
            "done": hechos, "running": por_estado.get("RUNNING", 0),
            "queued": por_estado.get("QUEUED", 0), "failed": por_estado.get("FAILED", 0),
            "spend_usd": round(gasto, 4),
            "pending_review": sum(1 for a in filas if a["status"] == "GENERATED"
                                  and a["review_status"] == "PENDING"),
            "finished": hechos == len(filas) and len(filas) > 0}


def latest_run() -> Optional[str]:
    r = store.q1("SELECT benchmark_id FROM staging_attempts WHERE benchmark_id IS NOT NULL "
                 "ORDER BY created_at DESC LIMIT 1")
    return r["benchmark_id"] if r else None


def attempts_of(benchmark_id: str) -> List[Dict]:
    return [staging.get(r["attempt_id"]) for r in store.q(
        "SELECT attempt_id FROM staging_attempts WHERE benchmark_id=? ORDER BY created_at",
        (benchmark_id,))]


def results(benchmark_id: Optional[str], man: Dict, providers: List[str],
            execution: Optional[Dict] = None, rights: Optional[Dict[str, bool]] = None) -> Dict:
    """El archivo `staging_benchmark_results.json`. Honesto por construcción: si no corrió, lo dice."""
    filas = attempts_of(benchmark_id) if benchmark_id else []
    met = aggregate(filas)
    sel = select(met, rights) if met else {"winner": None, "verdict": "NOT_RUN", "gates": {}}
    return {"results_version": RESULTS_VERSION, "generated_at": store.now(),
            "benchmark_id": benchmark_id, "manifest_version": man.get("manifest_version"),
            "style": man.get("style"), "request_version": staging.REQUEST_VERSION,
            "photos_in_manifest": len(man.get("photos") or []),
            "providers_requested": providers,
            "provider_status": (execution or {}).get("providers", {}),
            "sample_size": len(filas),
            "metrics": met, "selection": sel,
            "status": ("NOT_RUN" if not filas else
                       "AWAITING_HUMAN_REVIEW" if any(m["pending_review"] for m in met.values())
                       else "COMPLETE"),
            "_nota": (None if filas else
                      "El benchmark no se ejecutó: sin credenciales de proveedor y/o sin fotos "
                      "reales. Nada de lo anterior es un resultado.")}


# =================================================================================================
# CLI
# =================================================================================================
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m webapp.benchmark")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="armar el manifiesto desde propiedades existentes")
    i.add_argument("--from-properties", default="", help="ids separados por coma")
    i.add_argument("--out", default="benchmarks/staging_benchmark_v1.json")
    r = sub.add_parser("run", help="ejecutar el bake-off (sólo proveedores con credencial)")
    r.add_argument("--manifest", default="benchmarks/staging_benchmark_v1.json")
    r.add_argument("--providers", default="gemini,openai,bfl")
    r.add_argument("--runs", type=int, default=2)
    r.add_argument("--style", default=DEFAULT_STYLE)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--out", default="benchmarks/staging_benchmark_results.json")
    g = sub.add_parser("report", help="agregar métricas de un benchmark ya revisado")
    g.add_argument("--benchmark-id", required=True)
    g.add_argument("--manifest", default="benchmarks/staging_benchmark_v1.json")
    g.add_argument("--providers", default="gemini,openai,bfl")
    g.add_argument("--out", default="benchmarks/staging_benchmark_results.json")
    args = ap.parse_args(argv)

    store.init()
    if args.cmd == "init":
        ids = [x.strip() for x in args.from_properties.split(",") if x.strip()]
        if ids:
            for pid in ids:
                for a in assets.list_of_kind(pid, assets.PHOTO_ORIGINAL):
                    add_photo(a["asset_id"], pid, [], "añadida desde la CLI")
        man = dataset()
        _write(args.out, man)
        print(f"manifiesto: {args.out} · fotos: {len(man['photos'])} · estado: {man['status']}")
        return 0
    man = dataset() if not os.path.exists(args.manifest) else json.load(
        open(args.manifest, encoding="utf-8"))
    provs = [x.strip() for x in args.providers.split(",") if x.strip()]
    if args.cmd == "run":
        errs = validate_manifest(man)
        if errs:
            print("manifiesto no válido:\n  - " + "\n  - ".join(errs))
            res = results(None, man, provs, {"providers": {p: {"status": "HUMAN_ACTION_REQUIRED",
                          "reason": "manifiesto sin fotos reales suficientes"} for p in provs}})
            _write(args.out, res)
            return 2
        ex = execute(man, provs, args.runs, args.style, dry_run=args.dry_run)
        res = results(ex["benchmark_id"] if ex["attempts"] else None, man, provs, ex)
        _write(args.out, res)
        print(json.dumps({"benchmark_id": ex["benchmark_id"], "attempts": len(ex["attempts"]),
                          "providers": ex["providers"], "status": res["status"]},
                         ensure_ascii=False, indent=2))
        return 0
    res = results(args.benchmark_id, man, provs)
    _write(args.out, res)
    print(json.dumps(res["selection"], ensure_ascii=False, indent=2))
    return 0


def _write(path: str, obj: Dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
