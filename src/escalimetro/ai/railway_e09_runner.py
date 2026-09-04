"""E11 — wrapper mínimo para ejecutar el experimento E09 dentro de un servicio de Railway.

    PYTHONPATH=src python -m escalimetro.ai.railway_e09_runner

Un servicio de Railway necesita un proceso HTTP vivo; el experimento E09 termina. Este módulo hace
exactamente tres cosas, en ese orden, y ninguna más:

    run    → ejecuta UNA vez `escalimetro.ai.e09.main(...)`, la fuente de verdad del experimento;
    report → arma un único HTML autocontenido con las imágenes embebidas como data URI;
    serve  → levanta un servidor HTTP mínimo que sirve ese HTML.

NO duplica la lógica de E09: la importa y la llama. NO es una app SaaS: no hay auth, base de datos,
colas, workers ni frontend. Si el experimento falla, el servidor se levanta igual y el informe explica
qué falló — un despliegue que muere sin decir por qué no sirve para nada.

Nada de lo que este módulo imprime o sirve contiene credenciales: de las variables sólo se reporta
PRESENT/MISSING, y los model IDs son configuración, no secretos."""
from __future__ import annotations

import base64
import html
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple

REPORT_NAME = "ESCALIMETRO_E09_REAL_REPORT.html"
#: E16.1 §14, §17 — NO hay caso por defecto. Antes esto era `"cases/001_gps_403"`: un runner
#: genérico que, si nadie decía nada, procesaba la Oficina 403. El caso se declara por
#: `--case` o por la variable de entorno `ESCALIMETRO_CASE`; si falta, el runner se detiene.
CASE_ENV_VAR = "ESCALIMETRO_CASE"
MISSING_CASE = ("no se declaró el caso a procesar: pasa --case <ruta> o define la variable de "
                "entorno ESCALIMETRO_CASE. Este runner no tiene un caso por defecto.")
EXPECTED_HASHES_FILE = os.path.join("ai", "E09", "EXPECTED_GEOMETRY_HASHES.json")
KEY_VARS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
MODEL_VARS = ["OPENAI_MODEL_VISION", "OPENAI_MODEL_PRESENTATION", "ANTHROPIC_MODEL_REVIEWER"]
TUNING_VARS = ["AI_PROVIDER_TIMEOUT", "AI_PROVIDER_MAX_RETRIES"]


def expected_hash_prefix(case: str) -> Dict[str, str]:
    """E16.1 §16 — la expectativa de regresión de geometría es un DATO DEL CASO.

    Antes era una constante del runner con los hashes de la 403, o sea una expectativa universal:
    cualquier inmueble procesado aquí se comparaba contra la geometría de la Oficina 403. Ahora se
    lee de `cases/<caso>/ai/E09/EXPECTED_GEOMETRY_HASHES.json`. Un caso que no la declare no tiene
    expectativa —devuelve {}— y eso se reporta como tal; no se hereda la de otro caso."""
    try:
        with open(os.path.join(case, EXPECTED_HASHES_FILE), encoding="utf-8") as fh:
            return dict((json.load(fh).get("geometry_hash_prefix") or {}))
    except (OSError, ValueError):
        return {}


def log(msg: str) -> None:
    print(f"[e11] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------------
# B / C — presencia de variables y modelos configurados, SIN valores
# ---------------------------------------------------------------------------------------------------
def env_report() -> Dict:
    keys = {k: ("PRESENT" if os.getenv(k) else "MISSING") for k in KEY_VARS}
    models = {k: (os.getenv(k) or "(no configurado — se usa el default de config.py)") for k in MODEL_VARS}
    tuning = {k: (os.getenv(k) or "(default)") for k in TUNING_VARS}
    return {"keys": keys, "models": models, "tuning": tuning}


# ---------------------------------------------------------------------------------------------------
# D — ejecutar el experimento existente
# ---------------------------------------------------------------------------------------------------
def run_experiment(case: str) -> Dict:
    """Llama a e09.main. No reimplementa nada. Un fallo aquí no derriba el servidor."""
    from . import e09
    t0 = time.time()
    log("E09 START")
    try:
        rc = e09.main(["--case", case])
        ok, err = rc == 0, None
    except Exception as exc:                      # noqa: BLE001 - se reporta, no se propaga
        ok, err, rc = False, f"{type(exc).__name__}: {exc}", None
        log("E09 EXCEPTION:\n" + traceback.format_exc(limit=6))
    dt = round(time.time() - t0, 1)
    log(f"E09 END · ok={ok} · {dt} s")
    return {"ok": ok, "return_code": rc, "error": err, "seconds": dt}


def load_outputs(case: str) -> Dict:
    out = os.path.join(case, "ai", "E09")
    data: Dict[str, object] = {}
    for name in ("summary", "real_reviews_abc", "provider_agreement_matrix", "reception_case_study",
                 "strategy_readability", "aggregated_reviews", "provider_ablation",
                 "provider_value_summary", "prompt_reliability", "geometry_hash_check",
                 "real_cost_latency", "precondition", "presentation_spec_openai", "run_manifest"):
        p = os.path.join(out, f"{name}.json")
        if os.path.exists(p):
            try:
                data[name] = json.load(open(p, encoding="utf-8"))
            except Exception:
                data[name] = None
    return data


# ---------------------------------------------------------------------------------------------------
# F — informe HTML autocontenido
# ---------------------------------------------------------------------------------------------------
def _data_uri(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")
    except Exception:
        return None


def _img(path: str, caption: str) -> str:
    uri = _data_uri(path)
    if not uri:
        return (f'<figure class="missing"><div class="ph">NO PRODUCIDA</div>'
                f'<figcaption>{html.escape(caption)}</figcaption></figure>')
    return (f'<figure><img src="{uri}" alt="{html.escape(caption)}"/>'
            f'<figcaption>{html.escape(caption)}</figcaption></figure>')


def _svg_fallback(path: str, caption: str) -> str:
    """§15 — si el PNG falló pero el SVG existe, se embebe el SVG para poder inspeccionar el resultado.

    Esto NO convierte el gate del PNG en PASS: el bloque lo dice explícitamente."""
    if not os.path.exists(path):
        return ""
    try:
        svg = open(path, encoding="utf-8").read()
    except Exception:
        return ""
    uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (f'<div class="verdict bad"><div class="k">SVG AVAILABLE · PNG RASTERIZATION FAILED</div>'
            f'<p>La lámina existe como SVG y se muestra abajo para inspección visual. '
            f'El artefacto PNG NO se produjo: el gate de render sigue en FAILED.</p></div>'
            f'<figure><img src="{uri}" alt="{html.escape(caption)}"/>'
            f'<figcaption>{html.escape(caption)} — fallback SVG</figcaption></figure>')


def _table(headers: List[str], rows: List[List[str]]) -> str:
    h = "".join(f"<th>{html.escape(str(c))}</th>" for c in headers)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


def _badge(text: str) -> str:
    t = str(text).upper()
    cls = ("ok" if any(k in t for k in ("PASS", "EXECUTED", "PRESENT", "CONSENSUS_GOOD", "TRUE"))
           else "bad" if any(k in t for k in ("FAIL", "BLOCKED", "MISSING", "CRITICAL", "NOT PRODUCED"))
           else "warn")
    return f'<span class="badge {cls}">{html.escape(str(text))}</span>'


def _fmt(v) -> str:
    if v is None:
        return '<span class="na">—</span>'
    if isinstance(v, bool):
        return _badge("true" if v else "false")
    if isinstance(v, float):
        return f"{v:.3f}"
    return html.escape(str(v))


CSS = """
:root{--ink:#141a23;--muted:#69727e;--line:#e3e6ea;--bg:#ffffff;--panel:#f7f7f5;
--ok:#2f6d4f;--bad:#b5452f;--warn:#9a7b1f;--a:#2a78d6;--b:#eb6834;--c:#1baf7a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Helvetica Neue",Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:48px 28px 96px}
header{border-bottom:2px solid var(--line);padding-bottom:22px;margin-bottom:34px}
.brand{font-size:13px;letter-spacing:3px;color:var(--muted);font-weight:700}
h1{font-size:34px;margin:12px 0 6px;letter-spacing:-.4px}
.sub{color:var(--muted);font-size:15px}
h2{font-size:20px;margin:44px 0 12px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:26px 0 8px;color:var(--muted);letter-spacing:.4px;text-transform:uppercase}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:14px}
th{text-align:left;color:var(--muted);font-size:11.5px;letter-spacing:1.2px;text-transform:uppercase;
padding:8px 10px;border-bottom:1.5px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid #f1f2f4;vertical-align:top}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.badge{display:inline-block;padding:2px 9px;border-radius:11px;font-size:12px;font-weight:700}
.badge.ok{background:#e6f2ea;color:var(--ok)}
.badge.bad{background:#fbe9e5;color:var(--bad)}
.badge.warn{background:#fbf3dd;color:var(--warn)}
.na{color:#b6bcc4}
figure{margin:20px 0 8px}
img{width:100%;height:auto;border:1px solid var(--line);border-radius:6px}
figcaption{color:var(--muted);font-size:12.5px;margin-top:7px}
.missing .ph{border:2px dashed var(--line);border-radius:6px;padding:52px;text-align:center;
color:var(--bad);font-weight:700;letter-spacing:2px;background:var(--panel)}
.verdict{background:var(--panel);border-left:5px solid var(--a);padding:20px 24px;border-radius:6px;margin:20px 0}
.verdict.bad{border-left-color:var(--bad)}
.verdict.ok{border-left-color:var(--ok)}
.k{font-size:12px;color:var(--muted);letter-spacing:1.4px;font-weight:700}
pre{background:var(--panel);padding:14px 16px;border-radius:6px;overflow-x:auto;font-size:13px}
footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px}
"""


def build_html(case: str, env: Dict, run: Dict, data: Dict) -> str:
    out_dir = os.path.join(case, "ai", "E09")
    e07 = os.path.join(case, "layouts", "E07")
    e08 = os.path.join(case, "ai", "E08")
    summary = data.get("summary") or {}
    executed = str(summary.get("api_execution_status", "UNKNOWN")).startswith("EXECUTED")
    gate_api = summary.get("gate_api", "BLOCKED")
    gate_value = summary.get("gate_multi_model_value", "INSUFFICIENT_EVIDENCE")
    geo = data.get("geometry_hash_check") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    P: List[str] = []
    A = P.append

    A(f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
      f'<meta name="viewport" content="width=device-width,initial-scale=1">'
      f'<title>ESCALÍMETRO — informe real E09</title><style>{CSS}</style></head><body><div class="wrap">')
    A('<header><div class="brand">ESCALÍMETRO</div>'
      '<h1>Informe real del experimento E09</h1>'
      f'<div class="sub">Ejecutado en el runtime de Railway · {now}</div></header>')

    # 1 — veredicto
    A('<h2>1 · Executive verdict</h2>')
    A(f'<div class="verdict {"ok" if executed else "bad"}">'
      f'<div class="k">API EXECUTION</div><div style="font-size:22px;font-weight:700">'
      f'{html.escape(str(summary.get("api_execution_status", "—")))}</div>'
      f'<p>GATE API {_badge(gate_api)} &nbsp; GATE MULTI-MODEL VALUE {_badge(gate_value)} &nbsp; '
      f'GEOMETRY LOCKED {_badge(summary.get("geometry_locked"))}</p>'
      f'<p class="sub">PRESENTATION RENDER {_badge(summary.get("presentation_render_status", "—"))} — '
      f'estado independiente del anterior: un fallo de rasterización no invalida las llamadas a los '
      f'proveedores que sí terminaron.</p></div>')
    if not run["ok"]:
        A(f'<div class="verdict bad"><div class="k">EL EXPERIMENTO NO TERMINÓ</div>'
          f'<p class="mono">{html.escape(str(run.get("error") or "return code " + str(run.get("return_code"))))}</p>'
          f'<p>El servidor se levantó igual para que este diagnóstico sea visible.</p></div>')

    # 1b — etapas de la corrida, desde el manifiesto
    man = data.get("run_manifest") or {}
    if man:
        A('<h2>1b · Etapas de la corrida</h2>')
        A(f'<p class="sub">run_id <code>{html.escape(str(man.get("run_id", "—")))}</code> · '
          f'inicio {html.escape(str(man.get("started_at", "—")))} · '
          f'fin {html.escape(str(man.get("finished_at") or "—"))}</p>')
        prov_rows = []
        for src, label in (("rule_based", "rule-based"), ("anthropic", "Anthropic"),
                           ("openai_visual", "OpenAI Vision")):
            d_ = man.get(src) or {}
            prov_rows.append([label] + [_badge(d_.get(a, "—")) for a in ("A", "B", "C")])
        A(_table(["fuente", "A", "B", "C"], prov_rows))
        A(_table(["etapa", "estado"],
                 [["aggregator", _badge(man.get("aggregator_status", "—"))],
                  ["presentation_director", _badge(man.get("presentation_director_status", "—"))],
                  ["presentation_render", _badge(man.get("presentation_render_status", "—"))],
                  ["geometry_guard", _badge(man.get("geometry_guard_status", "—"))],
                  ["final", _badge(man.get("final_status", "—"))]]))
        if man.get("errors"):
            A('<h3>Errores registrados</h3>')
            A(_table(["etapa", "detalle"],
                     [[html.escape(str(e.get("stage", "—"))),
                       f'<code>{html.escape(json.dumps({k: v for k, v in e.items() if k not in ("stage", "at")}, ensure_ascii=False))[:300]}</code>']
                      for e in man["errors"]]))

    # 2 — estado de API y variables
    A('<h2>2 · API status y variables</h2>')
    A(_table(["variable", "estado"], [[f'<code>{k}</code>', _badge(v)] for k, v in env["keys"].items()]))
    A('<h3>Modelos configurados</h3>')
    A(_table(["variable", "valor configurado"],
             [[f'<code>{k}</code>', f'<code>{html.escape(v)}</code>'] for k, v in env["models"].items()]))
    A(_table(["ajuste", "valor"], [[f'<code>{k}</code>', html.escape(v)] for k, v in env["tuning"].items()]))
    A('<p class="sub">Los valores de las credenciales nunca se leen, imprimen ni sirven: sólo su presencia.</p>')

    # 3 — revisiones
    A('<h2>3 · Revisiones por proveedor</h2>')
    A(_img(os.path.join(out_dir, "real_reviews_abc.png"), "real_reviews_abc — tres fuentes por alternativa"))
    reviews = data.get("real_reviews_abc") or {}
    rows = []
    for alt in ("A", "B", "C"):
        r = reviews.get(alt) or {}
        for src in ("rule_based", "anthropic", "openai_vision"):
            rv = r.get(src)
            rows.append([alt, src,
                         _badge("EXECUTED" if rv else "BLOCKED"),
                         _fmt((rv or {}).get("model")),
                         _fmt((rv or {}).get("confidence")),
                         html.escape(((rv or {}).get("summary") or "—"))[:220]])
    A(_table(["alt", "fuente", "estado", "modelo", "confianza", "resumen"], rows))

    # 4 — recepción
    A('<h2>4 · Caso de control — la recepción</h2>')
    A(_img(os.path.join(out_dir, "reception_case_study.png"), "reception_case_study"))
    rec = data.get("reception_case_study") or {}
    A(_table(["alt", "rule-based", "Anthropic", "OpenAI Vision", "clasificación", "razón"],
             [[a, _fmt((rec.get(a) or {}).get("rule_based")), _fmt((rec.get(a) or {}).get("anthropic")),
               _fmt((rec.get(a) or {}).get("openai_vision")),
               _badge((rec.get(a) or {}).get("classification", "—")),
               html.escape(str((rec.get(a) or {}).get("reason", "")))] for a in ("A", "B", "C")]))

    # 5 — legibilidad de estrategia
    A('<h2>5 · Legibilidad de la estrategia</h2>')
    A(_img(os.path.join(out_dir, "strategy_readability_comparison.png"), "strategy_readability_comparison"))
    st = data.get("strategy_readability") or {}
    A(_table(["alt", "heurística rule-based", "Anthropic", "OpenAI Vision", "estado"],
             [[a, _fmt((st.get(a) or {}).get("rule_based_heuristic")),
               _fmt((st.get(a) or {}).get("anthropic_structured")),
               _fmt((st.get(a) or {}).get("openai_visual")),
               _badge((st.get(a) or {}).get("status", "—"))] for a in ("A", "B", "C")]))

    # 6 — acuerdos y desacuerdos
    A('<h2>6 · Acuerdos y desacuerdos</h2>')
    A(_img(os.path.join(out_dir, "provider_agreement_matrix.png"), "provider_agreement_matrix"))
    agg = data.get("aggregated_reviews") or {}
    A(_table(["alt", "status", "readiness", "acuerdos", "desacuerdos", "críticos", "razón"],
             [[a, _badge((agg.get(a) or {}).get("status", "—")),
               _badge((agg.get(a) or {}).get("external_review_readiness", "—")),
               len((agg.get(a) or {}).get("agreements") or []),
               len((agg.get(a) or {}).get("disagreements") or []),
               len((agg.get(a) or {}).get("critical_disagreements") or []),
               html.escape(str((agg.get(a) or {}).get("reason", "")))] for a in ("A", "B", "C")]))

    # 7 — ablación y valor
    A('<h2>7 · Ablación de proveedores</h2>')
    A(_img(os.path.join(out_dir, "provider_ablation.png"), "provider_ablation"))
    abl = data.get("provider_ablation") or []
    A(_table(["config", "fuentes", "estado", "issues", "acuerdos", "desacuerdos", "confianza", "costo USD"],
             [[r.get("config"), ", ".join(r.get("sources", [])), _badge(r.get("status", "—")),
               _fmt(r.get("issues_detected")), _fmt(r.get("agreements")), _fmt(r.get("disagreements")),
               _fmt(r.get("confidence")), _fmt(r.get("estimated_cost_usd"))] for r in abl]))
    A('<h2>8 · Valor por proveedor</h2>')
    A(_img(os.path.join(out_dir, "provider_value_summary.png"), "provider_value_summary"))
    val = data.get("provider_value_summary") or []
    A(_table(["proveedor", "rol", "hallazgos únicos", "duplicados", "valor incremental"],
             [[r.get("provider"), html.escape(str(r.get("role", ""))),
               _fmt(r.get("unique_useful_findings")), _fmt(r.get("duplicate_findings")),
               _badge(r.get("incremental_value", "—"))] for r in val]))

    # 9 — costo y latencia
    A('<h2>9 · Costo y latencia reales</h2>')
    A(_img(os.path.join(out_dir, "real_cost_latency.png"), "real_cost_latency"))
    cl = data.get("real_cost_latency") or {}
    by = cl.get("by_source") or {}
    A(_table(["fuente", "llamadas", "tokens in", "tokens out", "costo estimado USD"],
             [[s, _fmt(g.get("calls")), _fmt(g.get("input_tokens")), _fmt(g.get("output_tokens")),
               _fmt(g.get("estimated_cost"))] for s, g in by.items()]))
    A(_table(["métrica", "valor"],
             [["latencia real en paralelo", _fmt(cl.get("parallel_wall_ms")) + " ms"],
              ["equivalente secuencial", _fmt(cl.get("sequential_equivalent_ms")) + " ms"],
              ["ahorro por paralelismo", _fmt(cl.get("latency_saved_pct")) + " %"],
              ["costo total", html.escape(json.dumps(cl.get("totals", {}), ensure_ascii=False))]]))

    # 10 — fiabilidad de prompts
    A('<h2>10 · Fiabilidad de prompts</h2>')
    rel = data.get("prompt_reliability") or []
    A(_table(["fuente", "propósito", "estado", "JSON 1er intento", "schema 1er intento", "reintentos",
              "dispersión", "≈0.7", "flag"],
             [[r.get("source"), r.get("purpose"), _badge(r.get("status", "—")),
               _fmt(r.get("valid_json_first_attempt")), _fmt(r.get("schema_pass_first_attempt")),
               _fmt(r.get("retries")), _fmt(r.get("score_spread")), _fmt(r.get("fraction_near_0.7")),
               _badge(r.get("flag", "—")) if r.get("flag") else _fmt(r.get("reason"))] for r in rel]))

    # 11 — geometría
    A('<h2>11 · Geometry guard</h2>')
    A(_img(os.path.join(out_dir, "geometry_hash_check.png"), "geometry_hash_check"))
    hb, ha = geo.get("geometry_hash_before", {}), geo.get("geometry_hash_after", {})
    exp = expected_hash_prefix(case)                       # E16.1: expectativa declarada por el caso
    A(_table(["alt", "esperado (declarado por el caso)", "antes", "después", "idéntico"],
             [[a, f'<code>{exp[a]}…</code>' if a in exp else "sin expectativa declarada",
               f'<code>{html.escape(str(hb.get(a, "—"))[:16])}…</code>',
               f'<code>{html.escape(str(ha.get(a, "—"))[:16])}…</code>',
               _badge(hb.get(a) == ha.get(a)
                      and (a not in exp or str(hb.get(a, "")).startswith(exp[a])))]
              for a in ("A", "B", "C")]))

    # 12 — presentación
    A('<h2>12 · PresentationSpec de OpenAI</h2>')
    spec = data.get("presentation_spec_openai")
    if spec:
        A(_table(["campo", "valor"],
                 [["provider", _fmt(spec.get("provider"))], ["model", _fmt(spec.get("model"))],
                  ["prompt_version", _fmt(spec.get("prompt_version"))],
                  ["headline", _fmt(spec.get("headline"))], ["subtitle", _fmt(spec.get("subtitle"))],
                  ["orden", _fmt(", ".join(spec.get("alternative_order", [])))]]))
    else:
        A('<div class="verdict bad"><div class="k">SIN PRESENTATIONSPEC REAL</div>'
          '<p>OpenAI no produjo especificación en esta corrida, así que la lámina 03 no se renderizó. '
          'Dirigirla de otra forma invalidaría la comparación 02 vs 03.</p></div>')
    A('<h2>13 · Presentation Standard 03</h2>')
    png03 = os.path.join(out_dir, "ESCALIMETRO_PRESENTATION_STANDARD_03.png")
    svg03 = os.path.join(out_dir, "ESCALIMETRO_PRESENTATION_STANDARD_03.svg")
    if os.path.exists(png03):
        A(_img(png03, "ESCALIMETRO_PRESENTATION_STANDARD_03 — geometría de E07, dirección de OpenAI"))
    elif os.path.exists(svg03):
        err = summary.get("presentation_render_error") or {}
        A(f'<p class="sub">Causa técnica: <code>{html.escape(json.dumps(err, ensure_ascii=False))[:400]}</code></p>'
          if err else "")
        A(_svg_fallback(svg03, "ESCALIMETRO_PRESENTATION_STANDARD_03"))
    else:
        A('<div class="verdict bad"><div class="k">PRESENTATION STANDARD 03 · NO PRODUCIDA</div>'
          f'<p>{html.escape(str(summary.get("standard_03", "sin PresentationSpec real de OpenAI")))}</p></div>')
    A('<h2>14 · Standard 01 vs 02 vs 03</h2>')
    A(_img(os.path.join(out_dir, "presentation_01_02_03.png"), "presentation_01_02_03"))
    A(_img(os.path.join(e07, "ESCALIMETRO_PRESENTATION_STANDARD_01.png"), "STANDARD 01 (E07)"))
    A(_img(os.path.join(e08, "ESCALIMETRO_PRESENTATION_STANDARD_02.png"), "STANDARD 02 (E08)"))

    # 15 — gates
    A('<h2>15 · Gates</h2>')
    A(_table(["gate", "estado"],
             [["GATE API (ejecución de proveedores)", _badge(gate_api)],
              ["PRESENTATION RENDER (artefacto PNG)", _badge(summary.get("presentation_render_status", "—"))],
              ["GATE MULTI-MODEL VALUE", _badge(gate_value)],
              ["E1-C comercial", _badge("READY_FOR_BROKER_REVIEW — el software nunca lo marca PASS")]]))
    A(f'<footer>Test-fit conceptual para evaluación de espacio. No constituye proyecto de arquitectura. '
      f'Dimensiones sujetas a confirmación de escala (SCALE: UNCONFIRMED, confianza LOW). '
      f'Geometría de E07 verificada por hash antes y después de la capa de IA. '
      f'Ninguna credencial fue leída, impresa ni servida.<br>'
      f'Informe generado por <code>escalimetro.ai.railway_e09_runner</code> · caso '
      f'<code>{html.escape(case)}</code> · experimento en {run["seconds"]} s.</footer>')
    A('</div></body></html>')
    return "\n".join(P)


# ---------------------------------------------------------------------------------------------------
# G — servidor HTTP mínimo
# ---------------------------------------------------------------------------------------------------
class _State:
    report_html: str = "<h1>Informe no generado</h1>"
    report_path: str = ""
    status: Dict = {"api_execution": "unknown", "gate_api": "unknown",
                    "gate_multi_model_value": "unknown", "report_ready": False}


class Handler(BaseHTTPRequestHandler):
    server_version = "escalimetro-e09"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                        # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/health":
            self._send(200, b'{"status":"ok"}', "application/json; charset=utf-8")
        elif path == "/status":
            self._send(200, json.dumps(_State.status, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
        elif path == "/":
            self._send(200, _State.report_html.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b'{"error":"not found"}', "application/json; charset=utf-8")

    def log_message(self, fmt, *args):                        # silencio salvo lo nuestro
        log("http " + (fmt % args))


def serve(port: int) -> None:
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log(f"HTTP server listening on {port}")
    srv.serve_forever()


# ---------------------------------------------------------------------------------------------------
def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    case = os.getenv(CASE_ENV_VAR, "")
    if "--case" in argv:                                     # E12: útil para ensayar sin tocar el caso real
        case = argv[argv.index("--case") + 1]
    if not case:                                             # E16.1: sin caso no se procesa nada
        log(MISSING_CASE)
        return 2
    serve_after = "--no-serve" not in argv
    unknown = [a for a in argv if a.startswith("--") and a not in ("--no-serve", "--case")]
    if unknown:                                              # nunca ignorar en silencio un argumento
        log("argumentos no reconocidos, se ignoran: " + " ".join(unknown))
    log(f"case={case}")

    env = env_report()
    from .svg_rasterizer import available_backends
    log("svg rasterizer backends: " + (", ".join(available_backends()) or "NINGUNO — la lámina 03 fallará"))
    for k, v in env["keys"].items():
        log(f"{k}={v}")
    for k, v in env["models"].items():
        log(f"{k}={v}")

    run = run_experiment(case)
    data = load_outputs(case)
    summary = data.get("summary") or {}
    _State.status = {
        "api_execution": summary.get("api_execution_status", "unknown"),
        "gate_api": summary.get("gate_api", "unknown"),
        "gate_multi_model_value": summary.get("gate_multi_model_value", "unknown"),
        "report_ready": False,
    }
    geo = data.get("geometry_hash_check") or {}
    exp = expected_hash_prefix(case)                         # E16.1: la declara el caso, no el runner
    for a in ("A", "B", "C"):
        hb = str((geo.get("geometry_hash_before") or {}).get(a, ""))
        estable = hb == str((geo.get("geometry_hash_after") or {}).get(a, ""))
        if a not in exp:
            log(f"GeometryHash {a} {'STABLE' if estable else 'CHANGED'} · el caso no declara "
                f"expectativa de regresión")
            continue
        ok = estable and hb.startswith(exp[a])
        log(f"GeometryHash {a} {'PASS' if ok else 'FAIL'}")

    try:
        _State.report_html = build_html(case, env, run, data)
        _State.report_path = os.path.join(case, "ai", "E09", REPORT_NAME)
        os.makedirs(os.path.dirname(_State.report_path), exist_ok=True)
        with open(_State.report_path, "w", encoding="utf-8") as fh:
            fh.write(_State.report_html)
        _State.status["report_ready"] = True
        log(f"Report generated · {len(_State.report_html) // 1024} KB · {_State.report_path}")
    except Exception:                                        # noqa: BLE001
        log("REPORT FAILED:\n" + traceback.format_exc(limit=6))
        _State.report_html = ("<h1>El informe no se pudo generar</h1>"
                              "<p>El servidor sigue en pie para que el fallo sea visible en logs.</p>")

    if not serve_after:
        return 0
    serve(int(os.getenv("PORT", "8080")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
