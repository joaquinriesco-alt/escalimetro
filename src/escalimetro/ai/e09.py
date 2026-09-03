"""E09 — validación real multi-modelo.

    PYTHONPATH=src python -m escalimetro.ai.e09 --case cases/001_gps_403

Este módulo NO agrega infraestructura de proveedores: usa la de E08 tal cual. Lo que agrega es el
EXPERIMENTO: congelar el baseline, llamar de verdad a los dos proveedores, comparar las tres fuentes,
estudiar el caso de la recepción, medir legibilidad de estrategia, correr la ablación de cuatro
configuraciones, medir costo y latencia reales, y —sólo si OpenAI respondió— dirigir y renderizar la
lámina 03.

Regla que gobierna todo el módulo: **cuando un proveedor no está, el resultado es BLOCKED, no un número
inventado.** Cada bloque de salida lleva su propio `status` y ningún gráfico rellena huecos.

Estados por bloque:

    EXECUTED   — hubo llamada real y respuesta válida.
    BLOCKED    — falta la credencial o el proveedor falló; no hay dato y no se fabrica.
    N/A        — el bloque no aplica en esta corrida.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Dict, List, Optional, Tuple


from ..layout.e06.scale import scaled_shell
from ..layout.e07.strategies import build_alternatives
from ..layout.model import Layout, load_program
from ..schemas.floorplate import Floorplate
from .config import load_configs, missing_keys
from .geometry_guard import geometry_hash
from .manifest import BLOCKED, FAILED, OK, RunManifest, SKIPPED
from .orchestrator import AIOrchestrator
from .review_aggregator import BRIDGE, aggregate
from .reviewers import build_payload
from .run import presentation_context
from .svg_rasterizer import PresentationRasterizationError, available_backends, rasterize_and_write
from .telemetry import scrub

ALTS = ["A", "B", "C"]
SOURCES = ["rule_based", "anthropic", "openai_vision"]

# Dimensiones realmente comparables entre los tres schemas. No se fuerza equivalencia donde no la hay:
# `boardroom_location` y `kitchenette_dining` no tienen contraparte visual y se comparan sólo entre las
# fuentes que las puntúan.
COMPARABLE = ["arrival_sequence", "reception", "client_route", "boardroom_location",
              "meeting_accessibility", "privacy_gradient", "open_work_neighborhoods", "adjacency",
              "kitchenette_dining", "lounge", "circulation_logic", "strategy_alignment",
              "overall_plausibility"]
VISUAL_OF = dict(BRIDGE)                      # espacial → visual
SPATIAL_OF = {v: k for k, v in BRIDGE.items()}


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(scrub(obj), open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------------------------------
# E12 — logs por etapa. Una línea por transición, sin prompts ni respuestas ni credenciales.
# ---------------------------------------------------------------------------------------------------
def stage(name: str, state: str, detail: str = "") -> None:
    print(f"[e09] STAGE {name} {state}" + (f" · {detail}" if detail else ""), flush=True)


def snapshot_run(out: str, runs_dir: str) -> Optional[str]:
    """Copia la corrida terminada a `ai/runs/<run_id>/` para que la siguiente no la destruya.

    Copia, no mueve: `ai/E09/` sigue siendo la corrida actual y todo el código y los tests que ya
    dependen de esa ruta siguen funcionando."""
    import shutil
    try:
        os.makedirs(runs_dir, exist_ok=True)
        for f in sorted(os.listdir(out)):
            src = os.path.join(out, f)
            if os.path.isfile(src) and not f.startswith("."):
                shutil.copy2(src, os.path.join(runs_dir, f))
        return runs_dir
    except Exception as e:                                    # el archivo histórico nunca tumba la corrida
        print(f"[e09] snapshot FAILED · {type(e).__name__}", flush=True)
        return None


# ---------------------------------------------------------------------------------------------------
# lectura de la revisión, tolerante a los dos vocabularios
# ---------------------------------------------------------------------------------------------------
def score_of(review: Optional[Dict], aspect: str) -> Optional[float]:
    if not review:
        return None
    sc = review.get("scores") or {}
    if aspect == "overall_plausibility":
        v = review.get("architectural_plausibility", review.get("visual_plausibility"))
        return float(v) if v is not None else None
    if aspect == "strategy_alignment":
        v = review.get("strategy_alignment", review.get("strategy_readability"))
        return float(v) if v is not None else None
    if aspect in sc:
        return float(sc[aspect])
    vis = VISUAL_OF.get(aspect)
    if vis and vis in sc:
        return float(sc[vis])
    return None


def agreement_status(vals: Dict[str, float]) -> str:
    """Mismos umbrales que E08. No se recalibran aquí (§11 del brief E09)."""
    from .review_aggregator import AGREEMENT_DELTA, CRITICAL_DELTA, CRITICAL_LOW, DISAGREEMENT_DELTA
    if len(vals) < 2:
        return "BLOCKED"
    d = max(vals.values()) - min(vals.values())
    if d >= CRITICAL_DELTA and min(vals.values()) <= CRITICAL_LOW:
        return "CRITICAL_DISAGREEMENT"
    if d >= DISAGREEMENT_DELTA:
        return "DISAGREEMENT"
    if d <= AGREEMENT_DELTA:
        return "AGREEMENT"
    return "PARTIAL"


def agreement_matrix(reviews: Dict[str, Dict[str, Optional[Dict]]]) -> List[Dict]:
    rows = []
    for alt in ALTS:
        for aspect in COMPARABLE:
            vals = {}
            for s in SOURCES:
                v = score_of(reviews[alt].get(s), aspect)
                if v is not None:
                    vals[s] = round(v, 3)
            rows.append({"alternative_id": alt, "aspect": aspect,
                         "rule": vals.get("rule_based"), "anthropic": vals.get("anthropic"),
                         "openai": vals.get("openai_vision"),
                         "delta_max": (round(max(vals.values()) - min(vals.values()), 3)
                                       if len(vals) >= 2 else None),
                         "sources_present": sorted(vals),
                         "agreement_status": agreement_status(vals)})
    return rows


# ---------------------------------------------------------------------------------------------------
# §9 — caso de control: la recepción
# ---------------------------------------------------------------------------------------------------
def reception_case(reviews: Dict[str, Dict[str, Optional[Dict]]]) -> Dict:
    """El crítico por reglas da ~0.40 a la recepción en las tres. ¿Lo confirman los modelos?"""
    LOW, HIGH = 0.5, 0.65
    out = {}
    for alt in ALTS:
        rule = score_of(reviews[alt].get("rule_based"), "reception")
        anth = score_of(reviews[alt].get("anthropic"), "reception")
        oai = score_of(reviews[alt].get("openai_vision"), "reception")
        ai = [v for v in (anth, oai) if v is not None]
        if not ai:
            verdict, why = "UNCLEAR", ("sin proveedores de IA no hay contraste posible: el 0.40 del "
                                       "crítico por reglas sigue siendo una afirmación sin verificar")
        elif all(v < LOW for v in ai):
            verdict, why = "CONFIRMED_DEFECT", "los modelos disponibles coinciden con el crítico por reglas"
        elif all(v > HIGH for v in ai):
            verdict, why = "RULE_CRITIC_FALSE_POSITIVE", "los modelos ven bien lo que el crítico penaliza"
        elif len(ai) == 2 and abs(anth - oai) >= 0.30:
            verdict, why = "AI_DISAGREEMENT", "Anthropic y OpenAI no coinciden entre sí"
        else:
            verdict, why = "UNCLEAR", "las señales no son concluyentes"
        out[alt] = {"rule_based": rule, "anthropic": anth, "openai_vision": oai,
                    "classification": verdict, "reason": why,
                    "status": "EXECUTED" if ai else "BLOCKED"}
    return out


# ---------------------------------------------------------------------------------------------------
# §10 — legibilidad de la estrategia
# ---------------------------------------------------------------------------------------------------
def strategy_readability(reviews: Dict[str, Dict[str, Optional[Dict]]]) -> Dict:
    out = {}
    for alt in ALTS:
        rule = score_of(reviews[alt].get("rule_based"), "strategy_alignment")
        anth = score_of(reviews[alt].get("anthropic"), "strategy_alignment")
        oai = score_of(reviews[alt].get("openai_vision"), "strategy_alignment")
        out[alt] = {"rule_based_heuristic": rule, "anthropic_structured": anth,
                    "openai_visual": oai,
                    "status": "EXECUTED" if (anth is not None or oai is not None) else "BLOCKED",
                    "question": ("¿la estrategia declarada se expresa espacialmente, o sólo existe en "
                                 "el nombre de la alternativa?")}
    return out


# ---------------------------------------------------------------------------------------------------
# §12 — ablación de proveedores
# ---------------------------------------------------------------------------------------------------
CONFIGS = [("CONFIG_0", "rule-based sólo", ["rule_based"]),
           ("CONFIG_1", "rule-based + Anthropic", ["rule_based", "anthropic"]),
           ("CONFIG_2", "rule-based + OpenAI Vision", ["rule_based", "openai_vision"]),
           ("CONFIG_3", "rule-based + Anthropic + OpenAI Vision", SOURCES)]


def _issues(review: Optional[Dict]) -> List[Tuple[str, str]]:
    if not review:
        return []
    out = [(i["aspect"], "critical") for i in review.get("critical_issues") or []]
    out += [(i["aspect"], "warning") for i in review.get("warnings") or []]
    return out


def ablation(reviews, latencies, usage_by_source) -> List[Dict]:
    rows = []
    for cid, label, srcs in CONFIGS:
        available = [s for s in srcs if any(reviews[a].get(s) for a in ALTS)]
        blocked = [s for s in srcs if s not in available]
        if blocked:
            rows.append({"config": cid, "label": label, "sources": srcs, "status": "BLOCKED",
                         "blocked_sources": blocked,
                         "reason": "falta al menos una fuente; no se estima nada"})
            continue
        issues, by_src, agree, disagree = set(), {}, 0, 0
        for a in ALTS:
            for s in srcs:
                for asp, sev in _issues(reviews[a].get(s)):
                    key = (a, SPATIAL_OF.get(asp, asp), sev)
                    issues.add(key)
                    by_src.setdefault(s, set()).add(key)
            for aspect in COMPARABLE:
                vals = {s: score_of(reviews[a].get(s), aspect) for s in srcs}
                vals = {k: v for k, v in vals.items() if v is not None}
                st = agreement_status(vals)
                agree += st == "AGREEMENT"
                disagree += st in ("DISAGREEMENT", "CRITICAL_DISAGREEMENT")
        unique = {s: len(v - set().union(*[by_src[o] for o in by_src if o != s]) if len(by_src) > 1 else v)
                  for s, v in by_src.items()}
        confs = [float(reviews[a][s]["confidence"]) for a in ALTS for s in srcs if reviews[a].get(s)]
        lat = max((latencies[a].get(s, 0.0) for a in ALTS for s in srcs), default=0.0)
        cost = sum(usage_by_source.get(s, {}).get("estimated_cost", 0.0) for s in srcs)
        rows.append({"config": cid, "label": label, "sources": srcs, "status": "EXECUTED",
                     "issues_detected": len(issues), "unique_issues_by_source": unique,
                     "agreements": agree, "disagreements": disagree,
                     "confidence": round(sum(confs) / len(confs), 3) if confs else None,
                     "max_latency_ms": round(lat, 1), "estimated_cost_usd": round(cost, 6),
                     "actionable_signal": ("sólo lo verificable por métricas" if srcs == ["rule_based"]
                                           else "pendiente de evaluación con datos reales")})
    return rows


def value_per_provider(reviews, ablation_rows, usage_by_source, latencies) -> List[Dict]:
    out = []
    for s, role in (("rule_based", "crítico determinista E05/E07"),
                    ("anthropic", "revisión espacial estructurada"),
                    ("openai_vision", "crítica visual de la planta")):
        present = [a for a in ALTS if reviews[a].get(s)]
        if not present:
            out.append({"provider": s, "role": role, "status": "BLOCKED",
                        "unique_useful_findings": None, "duplicate_findings": None,
                        "weak_findings": None,
                        "latency_ms": None, "cost_usd": None,
                        "incremental_value": "INSUFFICIENT_EVIDENCE",
                        "reason": "no emitió ninguna revisión en esta corrida"})
            continue
        n_issues = sum(len(_issues(reviews[a][s])) for a in present)
        others = [o for o in SOURCES if o != s]
        dup = 0
        for a in present:
            mine = {SPATIAL_OF.get(k, k) for k, _ in _issues(reviews[a][s])}
            theirs = set()
            for o in others:
                theirs |= {SPATIAL_OF.get(k, k) for k, _ in _issues(reviews[a].get(o))}
            dup += len(mine & theirs)
        lat = max((latencies[a].get(s, 0.0) for a in present), default=0.0)
        cost = usage_by_source.get(s, {}).get("estimated_cost", 0.0)
        value = ("INSUFFICIENT_EVIDENCE" if len([1 for o in others if any(reviews[a].get(o) for a in ALTS)]) == 0
                 else "PENDING_JUDGEMENT")
        out.append({"provider": s, "role": role, "status": "EXECUTED",
                    "unique_useful_findings": n_issues - dup, "duplicate_findings": dup,
                    "weak_findings": None,
                    "latency_ms": round(lat, 1), "cost_usd": round(cost, 6),
                    "incremental_value": value,
                    "reason": ("única fuente presente: no hay con qué contrastar su aporte incremental"
                               if value == "INSUFFICIENT_EVIDENCE" else "")})
    return out


# ---------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--program", default="program_templates/office_balanced_48.json")
    args = ap.parse_args(argv)
    t_all = time.time()
    e07 = os.path.join(args.case, "layouts", "E07")
    out = os.path.join(args.case, "ai", "E09")          # corrida actual: ruta estable, compatible
    os.makedirs(out, exist_ok=True)
    mf = RunManifest(path=os.path.join(out, "run_manifest.json"), case=args.case)
    runs_dir = os.path.join(args.case, "ai", "runs", mf.run_id)
    mf.save()
    print(f"[e09] run_id={mf.run_id} · backends de rasterización: {', '.join(available_backends()) or 'ninguno'}",
          flush=True)

    # ---- §3 precondición ---------------------------------------------------------------------------
    cfgs = load_configs()
    miss = missing_keys(cfgs)
    # Los nombres llevan el sufijo _status a propósito: `telemetry.scrub` redacta cualquier clave que
    # se llame como una credencial, y aquí lo que se guarda es el ESTADO, nunca el valor.
    keys = {"OPENAI_API_KEY_status": "MISSING" if "OPENAI_API_KEY" in miss else "PRESENT",
            "ANTHROPIC_API_KEY_status": "MISSING" if "ANTHROPIC_API_KEY" in miss else "PRESENT"}
    models = {p: c.model for p, c in cfgs.items()}
    print(f"[e09] keys: " + " · ".join(f"{k}={v}" for k, v in keys.items()))
    print(f"[e09] modelos configurados: " + " · ".join(f"{k}={v}" for k, v in models.items()))
    mf.api_keys_status = {k.replace("_status", ""): v for k, v in keys.items()}
    mf.models = models
    mf.save()

    # ---- §4 baseline congelado ---------------------------------------------------------------------
    fp = Floorplate.load(os.path.join(args.case, "outputs", "floorplate.json"))
    shell = scaled_shell(fp, 1.0)
    prog = load_program(args.program)
    specs = {s.alt: s for s in build_alternatives(prog)}
    comp = json.load(open(os.path.join(e07, "alternative_comparison.json"), encoding="utf-8"))
    rows = {r["alt"]: r for r in comp["rows"]}
    fit = json.load(open(os.path.join(e07, "fit_verdict.json"), encoding="utf-8"))

    layouts, payloads, hash_before = {}, {}, {}
    for alt in ALTS:
        d = os.path.join(e07, "alternatives", alt)
        layouts[alt] = Layout.load(os.path.join(d, "layout.json"))
        hash_before[alt] = geometry_hash(layouts[alt], shell)
        payloads[alt] = build_payload(
            alt, specs[alt].to_dict(), layouts[alt].to_dict(),
            json.load(open(os.path.join(d, "metrics.json"), encoding="utf-8")),
            json.load(open(os.path.join(d, "critique.json"), encoding="utf-8")),
            json.load(open(os.path.join(e07, "alternatives", f"spatial_graph_{alt}.json"), encoding="utf-8")),
            fit, rows[alt])
    dump({"geometry_hash_before": hash_before, "note": "baseline congelado; no se regeneró ningún layout"},
         os.path.join(out, "baseline.json"))

    # ---- §5 §6 llamadas reales, en paralelo, sin contaminación cruzada -----------------------------
    orch = AIOrchestrator(project=os.path.basename(args.case), shell=shell)
    reviews: Dict[str, Dict[str, Optional[Dict]]] = {}
    latencies: Dict[str, Dict[str, float]] = {}
    errors: Dict[str, Dict[str, str]] = {}
    t_par = time.time()
    mf.set_stage("providers")
    for alt in ALTS:
        for src in SOURCES:
            stage(f"{src} {alt}", "START")
        r = orch.review_alternative(alt, layouts[alt], payloads[alt],
                                    image_paths=[os.path.join(e07, "alternatives", alt,
                                                              "layout_commercial.png")])
        reviews[alt] = {s: r.reviews.get(s) for s in SOURCES}
        latencies[alt] = r.latencies_ms
        errors[alt] = r.errors
        for src in SOURCES:
            rv = reviews[alt][src]
            if rv:
                mf.set_provider(src, alt, OK)
                stage(f"{src} {alt}", "OK", f'model={rv.get("model", "?")} · '
                                            f'{latencies[alt].get(src, 0):.0f} ms')
            else:
                err = errors[alt].get(src, "unknown")
                mf.set_provider(src, alt, BLOCKED if err == "provider_unavailable" else FAILED)
                stage(f"{src} {alt}", "BLOCKED" if err == "provider_unavailable" else "FAILED", err)
        # E12: la evidencia de proveedores se persiste APENAS existe, no al final. Si una etapa
        # posterior explota, esto ya está en disco.
        dump({a: {s: reviews[a][s] for s in SOURCES} for a in reviews},
             os.path.join(out, "real_reviews_abc.json"))
    parallel_wall_ms = round((time.time() - t_par) * 1000, 1)
    stage("providers", "DONE", f"wall={parallel_wall_ms:.0f} ms")

    # ---- §17 geometry guard ------------------------------------------------------------------------
    mf.set_stage("geometry_guard")
    hash_after = {a: geometry_hash(layouts[a], shell) for a in ALTS}
    geometry_ok = hash_before == hash_after
    dump({"geometry_hash_before": hash_before, "geometry_hash_after": hash_after,
          "identical": geometry_ok}, os.path.join(out, "geometry_hash_check.json"))
    for a in ALTS:
        print(f'[e09] GeometryHash {a} {"PASS" if hash_before[a] == hash_after[a] else "FAIL"}', flush=True)
    mf.set_status("geometry_guard", OK if geometry_ok else FAILED)
    if not geometry_ok:
        mf.add_error("geometry_guard", {"reason": "geometry hash cambió"})
        mf.finish(FAILED)
        raise SystemExit("E09 FAIL: geometry hash cambió")

    # ---- §8 §9 §10 §11 -----------------------------------------------------------------------------
    mf.set_stage("aggregator")
    stage("aggregator", "START")
    matrix = agreement_matrix(reviews)
    recep = reception_case(reviews)
    strat = strategy_readability(reviews)
    agg = {a: aggregate(a, reviews[a], {s: ("unavailable" if s in errors[a] else "present")
                                        for s in SOURCES}).to_dict() for a in ALTS}
    dump(matrix, os.path.join(out, "provider_agreement_matrix.json"))
    dump(recep, os.path.join(out, "reception_case_study.json"))
    dump(strat, os.path.join(out, "strategy_readability.json"))
    dump(agg, os.path.join(out, "aggregated_reviews.json"))
    mf.set_status("aggregator", OK)
    stage("aggregator", "OK")

    # ---- §14 §15 telemetría ------------------------------------------------------------------------
    usage = orch.ledger.summary()
    by_source = {}
    for rec in usage["records"]:
        s = {"anthropic": "anthropic", "openai": "openai_vision"}.get(rec["provider"], "rule_based")
        g = by_source.setdefault(s, {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                     "estimated_cost": 0.0, "latency_ms": 0.0, "success": 0})
        g["calls"] += 1
        g["success"] += int(bool(rec.get("success")))
        g["input_tokens"] += int(rec.get("input_tokens") or 0)
        g["output_tokens"] += int(rec.get("output_tokens") or 0)
        g["estimated_cost"] += float(rec.get("estimated_cost") or 0.0)
        g["latency_ms"] += float(rec.get("latency_ms") or 0.0)
    seq_ms = round(sum(sum(v.values()) for v in latencies.values()), 1)
    saved = round(100.0 * (1 - parallel_wall_ms / seq_ms), 1) if seq_ms else 0.0

    dump({"by_source": by_source, "totals": usage["total_cost"], "calls": usage["calls"],
          "parallel_wall_ms": parallel_wall_ms, "sequential_equivalent_ms": seq_ms,
          "latency_saved_pct": saved, "latencies_ms": latencies},
         os.path.join(out, "real_cost_latency.json"))

    # ---- §12 §13 ablación y valor -------------------------------------------------------------------
    abl = ablation(reviews, latencies, by_source)
    value = value_per_provider(reviews, abl, by_source, latencies)
    dump(abl, os.path.join(out, "provider_ablation.json"))
    dump(value, os.path.join(out, "provider_value_summary.json"))

    # ---- §16 fiabilidad de prompts -----------------------------------------------------------------
    reliability = []
    for s, purpose in (("anthropic", "spatial_review"), ("openai_vision", "visual_review")):
        recs = [r for r in usage["records"] if r["purpose"] == purpose and r["provider"] != "deterministic"]
        if not recs:
            reliability.append({"source": s, "purpose": purpose, "status": "BLOCKED",
                                "reason": "no hubo llamada real; nada que medir"})
            continue
        vals = [v for a in ALTS if reviews[a].get(s)
                for v in (reviews[a][s]["scores"] or {}).values()]
        spread = round(max(vals) - min(vals), 3) if vals else None
        near07 = (sum(1 for v in vals if 0.65 <= v <= 0.75) / len(vals)) if vals else None
        reliability.append({
            "source": s, "purpose": purpose, "status": "EXECUTED",
            "valid_json_first_attempt": all(r["attempts"] == 1 for r in recs if r["success"]),
            "schema_pass_first_attempt": all(r["attempts"] == 1 for r in recs if r["success"]),
            "retries": sum(max(0, r["attempts"] - 1) for r in recs),
            "score_spread": spread, "fraction_near_0.7": round(near07, 3) if near07 is not None else None,
            "flag": ("PROMPT_CALIBRATION_NEEDED" if (near07 or 0) > 0.6 or (spread or 1) < 0.15 else "OK"),
        })

    # ---- §18 §19 dirección de lámina real ----------------------------------------------------------
    mf.set_stage("presentation_director")
    ctx = presentation_context([specs[a] for a in ALTS], list(rows.values()), fit)
    ctx["aggregated_reviews"] = {a: {"status": agg[a]["status"],
                                     "consensus_scores": agg[a]["consensus_scores"]} for a in ALTS}
    spec, spec_status = None, "BLOCKED"
    if cfgs["presentation"].available:
        stage("presentation_director", "START")
        try:
            spec = orch.presentation_spec(ctx)
            spec_status = "EXECUTED" if spec.get("provider") == "openai" else "BLOCKED"
        except Exception as e:                                       # pragma: no cover
            spec_status = f"BLOCKED ({type(e).__name__})"
            mf.add_error("presentation_director", {"reason": type(e).__name__})
    else:
        stage("presentation_director", "BLOCKED", "sin credencial de OpenAI")
    if spec_status == "EXECUTED":
        dump(spec, os.path.join(out, "presentation_spec_openai.json"))
        mf.set_status("presentation_director", OK)
        stage("presentation_director", "OK", f'model={spec.get("model", "?")}')
    else:
        mf.set_status("presentation_director", BLOCKED)

    # ---- §19 render de la lámina 03 — etapa PROPIA -------------------------------------------------
    # E12: aquí murió la primera corrida de Railway. Ahora el render es su propia etapa, con su propio
    # estado, y un fallo NO destruye ni oculta la evidencia de proveedores obtenida antes.
    render_status, render_error = SKIPPED, None
    if spec_status == "EXECUTED":
        mf.set_stage("presentation_render")
        stage("presentation_render", "START")
        try:
            from .board02 import build_board02      # 03 reusa el renderer; sólo cambia la spec
            board_alts = [{"alt": a, "layout": layouts[a], "row": rows[a],
                           "metrics": json.load(open(os.path.join(e07, "alternatives", a, "metrics.json"),
                                                     encoding="utf-8")), "critique": {}} for a in ALTS]
            svg = build_board02(board_alts, shell, spec, fit).replace("STANDARD 02", "STANDARD 03")
            svg_path = os.path.join(out, "ESCALIMETRO_PRESENTATION_STANDARD_03.svg")
            open(svg_path, "w", encoding="utf-8").write(svg)
            mf.add_artifact("standard_03_svg", svg_path)
            png = rasterize_and_write(svg, 3600,
                                      os.path.join(out, "ESCALIMETRO_PRESENTATION_STANDARD_03.png"),
                                      what="Presentation Standard 03")
            mf.add_artifact("standard_03_png", png)
            render_status = OK
            mf.set_status("presentation_render", OK)
            stage("presentation_render", "OK")
            assert {a: geometry_hash(layouts[a], shell) for a in ALTS} == hash_before
        except PresentationRasterizationError as e:
            render_status, render_error = FAILED, e.to_dict()
            mf.set_status("presentation_render", FAILED)
            mf.add_error("presentation_render", e.to_dict())
            stage("presentation_render", "FAILED", f"PresentationRasterizationError · {e.reason}")
        except Exception as e:                                       # cualquier otro fallo del board
            render_status = FAILED
            render_error = {"error": type(e).__name__, "reason": str(e)[:200]}
            mf.set_status("presentation_render", FAILED)
            mf.add_error("presentation_render", render_error)
            stage("presentation_render", "FAILED", type(e).__name__)
    else:
        mf.set_status("presentation_render", SKIPPED)
        stage("presentation_render", "SKIPPED", "no hay PresentationSpec real que renderizar")

    # ---- salidas -----------------------------------------------------------------------------------
    # Los JSON de proveedores, agregador, telemetría y geometría YA se escribieron en su etapa. Aquí
    # sólo quedan los que dependen de todo lo anterior.
    dump({"keys": keys, "models": models, "provider_status": orch.provider_status(),
          "rasterizer_backends": available_backends()}, os.path.join(out, "precondition.json"))
    dump(reliability, os.path.join(out, "prompt_reliability.json"))

    mf.set_stage("visuals")
    try:
        from .visuals09 import render_all
        render_all(out, {"keys": keys, "models": models, "reviews": reviews, "matrix": matrix,
                         "reception": recep, "strategy": strat, "aggregated": agg, "ablation": abl,
                         "value": value, "reliability": reliability, "latencies": latencies,
                         "by_source": by_source, "usage": usage, "parallel_wall_ms": parallel_wall_ms,
                         "sequential_equivalent_ms": seq_ms, "latency_saved_pct": saved,
                         "hash_before": hash_before, "hash_after": hash_after, "geometry_ok": geometry_ok,
                         "spec_status": spec_status, "errors": errors, "case": args.case})
        stage("visuals", "OK")
    except Exception as e:                       # las visuales tampoco pueden tumbar la evidencia
        mf.add_error("visuals", {"error": type(e).__name__, "reason": str(e)[:200]})
        stage("visuals", "FAILED", type(e).__name__)

    executed = any(reviews[a].get(s) for a in ALTS for s in ("anthropic", "openai_vision"))
    all_executed = all(reviews[a].get(s) for a in ALTS for s in ("anthropic", "openai_vision"))
    summary = {
        "run_id": mf.run_id,
        "runtime_s": round(time.time() - t_all, 1),
        # --- GATE DE EJECUCIÓN DE API: depende SÓLO de los proveedores y de la geometría -----------
        "api_execution_status": ("EXECUTED" if all_executed else
                                 "PARTIAL" if executed else "BLOCKED — API KEY MISSING"),
        "gate_api": "PASS" if all_executed and geometry_ok else ("PARTIAL" if executed else "BLOCKED"),
        # --- GATE DE ARTEFACTO DE PRESENTACIÓN: independiente del anterior --------------------------
        "presentation_spec_status": spec_status,
        "presentation_render_status": render_status,
        "presentation_render_error": render_error,
        "standard_03": ("PRODUCED" if render_status == OK else
                        "SVG_AVAILABLE_PNG_FAILED" if render_status == FAILED else
                        "NOT PRODUCED — sin PresentationSpec real de OpenAI"),
        "keys": keys, "models": models,
        "gate_multi_model_value": ("INSUFFICIENT_EVIDENCE" if not executed else "PENDING_JUDGEMENT"),
        "geometry_locked": geometry_ok,
        "rasterizer_backends": available_backends(),
        "errors": errors,
    }
    dump(summary, os.path.join(out, "summary.json"))

    # --- archivo histórico: la corrida siguiente no destruye ésta -----------------------------------
    snap = snapshot_run(out, runs_dir)
    if snap:
        mf.add_artifact("run_snapshot", snap)
        print(f"[e09] snapshot · {snap}", flush=True)

    final = OK if (geometry_ok and render_status in (OK, SKIPPED)) else FAILED
    mf.set_status("report", OK)
    mf.finish(final)
    print(f'[e09] API {summary["api_execution_status"]} · gate API {summary["gate_api"]} · '
          f'presentation_render={render_status} · valor multi-modelo '
          f'{summary["gate_multi_model_value"]} · geometry_locked={geometry_ok} · '
          f'{summary["runtime_s"]} s', flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
