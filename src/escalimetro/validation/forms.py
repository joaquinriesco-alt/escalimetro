"""E13 — HTML autocontenido: formulario de entrevista, scorecard y pack maestro.

Todo se genera desde `schema.py` y `scorecard.py`, de modo que el vocabulario del formulario y el
del cálculo no puedan divergir: si mañana se agrega una categoría de defecto, aparece en los dos
lados o en ninguno. Sin backend, sin auth, sin base de datos, sin CDN: los archivos abren con
doble clic y funcionan sin red (§32, §34, §54)."""
from __future__ import annotations

import base64
import json
import os
from typing import Dict

from . import schema as S
from .blind import ORDERS
from .scorecard import THRESHOLDS

CSS = """
:root{--ink:#1d2430;--mut:#6b7480;--line:#d9dce2;--panel:#f6f6f4;--warn:#8a1f1f;--ok:#2f6d4f;--bad:#a4342a}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
     color:var(--ink);background:#fff}
.wrap{max-width:1100px;margin:0 auto;padding:28px 22px 80px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:34px 0 10px;padding-top:14px;
   border-top:1px solid var(--line)}h3{font-size:16px;margin:18px 0 8px}
.sub{color:var(--mut);margin:0 0 18px}
.warn{color:var(--warn);font-weight:600}
.card{border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin:14px 0;background:#fff}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:820px){.grid3{grid-template-columns:1fr}}
label{display:block;margin:6px 0 3px;font-size:13px;color:var(--mut)}
select,input,textarea{width:100%;padding:7px 8px;border:1px solid var(--line);border-radius:6px;
                      font:inherit;background:#fff}
textarea{min-height:56px}
.opt{display:inline-block;margin:2px 6px 2px 0;font-size:13px;color:var(--ink)}
.opt input{width:auto;margin-right:5px}
.chip{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:20px;
      padding:3px 11px;font-size:12px;color:var(--mut);margin-right:6px}
button{font:inherit;padding:9px 16px;border:1px solid var(--ink);background:var(--ink);color:#fff;
       border-radius:6px;cursor:pointer}
button.ghost{background:#fff;color:var(--ink)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left}
th{background:var(--panel);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.PASS{color:var(--ok);font-weight:700}.FAIL{color:var(--bad);font-weight:700}
.INSUFFICIENT_DATA,.NO_DATA{color:var(--mut);font-weight:700}
.BROKER_READY{color:var(--ok);font-weight:700}.REJECTED{color:var(--bad);font-weight:700}
.BORDERLINE{color:#8a6d1f;font-weight:700}
pre{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px;
    overflow:auto;font-size:12px;white-space:pre-wrap;word-break:break-all}
.note{background:var(--panel);border-left:3px solid var(--line);padding:10px 14px;font-size:14px;
      color:var(--mut);margin:12px 0}
img.board{width:100%;border:1px solid var(--line);border-radius:6px}
"""


def _radios(name: str, opts, prefix: str = "") -> str:
    return "".join(f'<span class="opt"><input type="radio" name="{prefix}{name}" value="{o}">'
                   f'{o}</span>' for o in opts)


def _checks(name: str, opts, prefix: str = "") -> str:
    return "".join(f'<span class="opt"><input type="checkbox" name="{prefix}{name}" value="{o}">'
                   f'{o}</span>' for o in opts)


def _select(name: str, opts, prefix: str = "") -> str:
    o = "".join(f'<option value="{x}">{x or "—"}</option>' for x in [""] + list(opts))
    return f'<select name="{prefix}{name}">{o}</select>'


# ---------------------------------------------------------------------------------------------------
def form_html() -> str:
    cfg = json.dumps({"columns": S.COLUMNS, "orders": [list(o) for o in ORDERS],
                      "perRespondent": S.PER_RESPONDENT}, ensure_ascii=False)

    per_opt = []
    for b in ("X", "Y", "Z"):
        per_opt.append(f"""
    <div class="card">
      <h3>OPTION {b}</h3>
      <label>Q1 · ¿Mandarías este test-fit al cliente SIN pedir antes que un arquitecto lo redibuje?</label>
      {_radios("send_to_client", S.YN, b + "_")}
      <label>Q3 · ¿Cuánta confianza te daría enviarla? (1 no la enviaría — 5 la enviaría tranquilo)</label>
      {_radios("confidence", list("12345"), b + "_")}
      <label>Q4 · ¿Ves algún error que te impediría enviarla?</label>
      {_radios("blocking_error", S.YN, b + "_")}
      <label>Si sí — categorías (máximo 3)</label>
      {_checks("defect_categories", S.DEFECTS, b + "_")}
      <label>§40 · ¿Qué cambiarías antes de enviarlo?</label>
      {_radios("change_magnitude", S.CHANGE_MAGNITUDE, b + "_")}
      <label>§15 · ¿Cómo describirías esta alternativa? (máximo 2)</label>
      {_checks("strategy_tags", S.STRATEGY_TAGS, b + "_")}
      <label>§14 · ¿Te parece correctamente resuelta la llegada y recepción?</label>
      {_radios("reception_ok", S.YN, b + "_")}
      <label>§14 · ¿Cambiarías su ubicación?</label>
      {_radios("move_reception", S.YN, b + "_")}
    </div>""")

    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESCALÍMETRO · Formulario de validación con brokers</title><style>{CSS}</style></head><body>
<div class="wrap">
<h1>Formulario de validación</h1>
<p class="sub">Una sesión por evaluador. Lo llena el <b>entrevistador</b>, no el evaluador.
<span class="warn">No muestres esta pantalla al evaluador: contiene el orden de presentación.</span></p>

<div class="note">El mapping entre OPTION X/Y/Z y las alternativas reales se calcula solo a partir del
número de evaluador y sólo aparece en el CSV exportado. Nunca se muestra aquí.</div>

<h2>0 · Sesión</h2>
<div class="card">
  <div class="grid3">
    <div><label>respondent_id (R01, R02, …)</label><input name="respondent_id" placeholder="R01"></div>
    <div><label>índice de evaluador (0, 1, 2, …) — define el orden de presentación</label>
         <input name="respondent_index" type="number" min="0" value="0"></div>
    <div><label>fecha</label><input name="session_date" type="date"></div>
  </div>
  <div class="grid3">
    <div><label>rol</label>{_select("role", S.ROLES)}</div>
    <div><label>años de experiencia</label><input name="years_experience" type="number" min="0"></div>
    <div><label>§39 · segundos hasta la primera decisión (Q1 de la primera opción)</label>
         <input name="time_to_first_decision_s" type="number" min="0"></div>
  </div>
  <p class="chip" id="orderChip">orden: —</p>
</div>

<h2>1 · Por alternativa <span class="chip">cegado — el evaluador sólo ve X / Y / Z</span></h2>
{''.join(per_opt)}

<h2>2 · Comparación</h2>
<div class="card">
  <label>Q2 · Si tuvieras que mandar UNA sola alternativa, ¿cuál mandarías?</label>
  {_radios("preferred_option", S.PREFERRED)}
  <label>§16 · ¿Las tres opciones te parecen suficientemente distintas entre sí?</label>
  {_radios("options_distinct", S.YN)}
  <label>Si no — ¿qué dos se parecen demasiado?</label>
  {_select("similar_pair", [x for x in S.SIMILAR_PAIR if x])}
</div>

<h2>3 · Trabajo actual <span class="chip">§18 — valida el problema, no la solución</span></h2>
<div class="card">
  <label>Hoy, cuando necesitas saber si un programa cabe en una oficina, ¿qué haces?</label>
  {_select("current_testfit_method", S.METHODS)}
  <label>¿Cuánto suele tardar?</label>{_select("current_turnaround", S.TURNAROUND)}
  <label>¿Con qué frecuencia necesitas esto?</label>{_select("frequency", S.FREQUENCY)}
</div>

<h2>4 · Después de la revelación</h2>
<div class="card">
  <label>§17 · ¿Esto sería útil en tu trabajo?</label>{_radios("useful_generated", S.YN)}
  <label>§17 · ¿En qué momento de tu proceso usarías algo así?</label>{_select("use_case", S.USE_CASES)}
  <label>§19 · Si pudieras generar algo de esta calidad en menos de 2 minutos, ¿lo usarías en un caso real?</label>
  {_radios("would_use_under_2min", S.YN)}
  <label>§19 · ¿Para qué porcentaje aproximado de tus búsquedas podría servir?</label>
  {_select("share_of_searches", S.SHARE)}
  <label>§20 · ¿Necesitarías que un arquitecto revise el test-fit antes de enviarlo?</label>
  {_select("human_qa_need", S.QA_NEED)}
  <label>§41 · sólo arquitectos — ¿cuánto tiempo necesitarías para dejarla enviable?</label>
  {_select("qa_time_minutes", S.QA_TIME)}
  <label>§38 · opcional — ¿cómo lo compararías con un test-fit inicial hecho por un arquitecto?</label>
  {_select("comparison_vs_architect", [x for x in S.COMPARISON if x])}
  <label>§21 · opcional — mostrado el nombre y la frase: ¿entiende qué hace?</label>
  {_radios("brand_understood", S.YN)}
  <label>§45 · nivel 2 — ¿redactó el correo con que la mandaría?</label>
  {_radios("level2_done", S.YN)}
</div>

<h2>5 · Observación del entrevistador <span class="chip">§24 — conducta, no declaración</span></h2>
<div class="card">
  <label>marcar lo que ocurrió</label>{_checks("observations", S.OBSERVATIONS)}
  <label>primera opción que miró</label>{_radios("first_looked", ["X", "Y", "Z"])}
  <label>notas (sin nombre, empresa, email ni teléfono)</label><textarea name="notes"></textarea>
</div>

<h2>6 · Exportar</h2>
<div class="card">
  <p>Genera tres filas — una por opción — con el esquema de <code>broker_validation_responses.csv</code>.
  Pega el resultado al final de ese archivo.</p>
  <button onclick="gen()">Generar filas CSV</button>
  <button class="ghost" onclick="copyOut()">Copiar</button>
  <button class="ghost" onclick="dl()">Descargar .csv</button>
  <pre id="out">—</pre>
</div>
</div>

<script>
const CFG = {cfg};
const $ = s => document.querySelector(s);
function val(n){{const e=document.querySelector(`[name="${{n}}"]`);
  if(!e) return "";
  if(e.type==="radio"){{const c=document.querySelector(`[name="${{n}}"]:checked`);return c?c.value:"";}}
  return e.value.trim();}}
function radio(n){{const c=document.querySelector(`[name="${{n}}"]:checked`);return c?c.value:"";}}
function multi(n){{return [...document.querySelectorAll(`[name="${{n}}"]:checked`)]
  .map(e=>e.value).join("|");}}
function mapping(idx){{const o=CFG.orders[idx % CFG.orders.length];
  return {{X:o[0],Y:o[1],Z:o[2],label:`SET ${{idx % CFG.orders.length + 1}} · ${{o.join("-")}}`}};}}
function refresh(){{const i=parseInt(val("respondent_index")||"0",10)||0;
  $("#orderChip").textContent="orden de presentación: "+mapping(i).label.split(" · ")[0]
    +" (el mapping queda sólo en el CSV)";}}
document.querySelector('[name="respondent_index"]').addEventListener("input",refresh);refresh();

function esc(v){{v=(v==null?"":String(v));
  return /[",\\n]/.test(v) ? '"'+v.replace(/"/g,'""')+'"' : v;}}

function gen(){{
  const idx=parseInt(val("respondent_index")||"0",10)||0, mp=mapping(idx);
  const rid=val("respondent_id")||("R"+String(idx+1).padStart(2,"0"));
  const obs=multi("observations"), first=radio("first_looked");
  const observations=[first?("FIRST_OPTION_LOOKED_AT:"+first):"",obs].filter(Boolean).join("|");
  const rows=["X","Y","Z"].map(b=>{{
    const r={{}};
    r.respondent_id=rid; r.role=val("role"); r.years_experience=val("years_experience");
    r.session_date=val("session_date");
    r.option_blind=b; r.option_real=mp[b]; r.display_order=mp.label;
    r.send_to_client=radio(b+"_send_to_client"); r.confidence=radio(b+"_confidence");
    r.blocking_error=radio(b+"_blocking_error"); r.defect_categories=multi(b+"_defect_categories");
    r.change_magnitude=radio(b+"_change_magnitude"); r.strategy_tags=multi(b+"_strategy_tags");
    r.reception_ok=radio(b+"_reception_ok"); r.move_reception=radio(b+"_move_reception");
    r.preferred_option=radio("preferred_option"); r.options_distinct=radio("options_distinct");
    r.similar_pair=val("similar_pair"); r.current_testfit_method=val("current_testfit_method");
    r.current_turnaround=val("current_turnaround"); r.frequency=val("frequency");
    r.useful_generated=radio("useful_generated");
    r.would_use_under_2min=radio("would_use_under_2min"); r.use_case=val("use_case");
    r.share_of_searches=val("share_of_searches"); r.human_qa_need=val("human_qa_need");
    r.qa_time_minutes=val("qa_time_minutes");
    r.time_to_first_decision_s=val("time_to_first_decision_s");
    r.observations=observations; r.level2_done=radio("level2_done");
    r.comparison_vs_architect=val("comparison_vs_architect");
    r.brand_understood=radio("brand_understood"); r.notes=val("notes");
    return CFG.columns.map(c=>esc(r[c])).join(",");
  }});
  $("#out").textContent=rows.join("\\n");
}}
function copyOut(){{navigator.clipboard.writeText($("#out").textContent);}}
function dl(){{const b=new Blob([$("#out").textContent+"\\n"],{{type:"text/csv"}});
  const a=document.createElement("a");a.href=URL.createObjectURL(b);
  a.download=(val("respondent_id")||"respondent")+"_rows.csv";a.click();}}
</script></body></html>"""


# ---------------------------------------------------------------------------------------------------
def scorecard_html() -> str:
    """Scorecard vacía. No trae ningún resultado inventado (§52): hasta que se cargue un CSV real
    muestra INSUFFICIENT_DATA en todo. Los umbrales están escritos en el HTML porque están fijados
    antes de ver datos y deben ser auditables por quien lea el archivo."""
    cfg = json.dumps({
        "columns": S.COLUMNS, "thresholds": THRESHOLDS, "defects": S.DEFECTS,
        "commercialRoles": S.COMMERCIAL_ROLES, "changeOk": S.CHANGE_OK,
        "slowTurnaround": S.SLOW_TURNAROUND, "frequent": S.FREQUENT,
        "shareMeaningful": S.SHARE_MEANINGFUL, "intendedTag": S.INTENDED_TAG,
    }, ensure_ascii=False)
    T = THRESHOLDS
    thr_rows = "".join(
        f"<tr><td>{k}</td><td class='n'>{v}</td></tr>" for k, v in T.items())
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESCALÍMETRO · Scorecard de validación comercial</title><style>{CSS}</style></head><body>
<div class="wrap">
<h1>Scorecard de validación comercial</h1>
<p class="sub">Carga <code>broker_validation_responses.csv</code>. Sin datos no muestra nada:
esta scorecard nace vacía a propósito.</p>

<div class="card">
  <input type="file" id="file" accept=".csv,text/csv">
  <label>o pega el CSV completo (con cabecera)</label>
  <textarea id="paste" placeholder="respondent_id,role,..."></textarea>
  <button onclick="run()">Calcular</button>
  <label>segmento</label>
  <select id="seg"><option>COMMERCIAL</option><option>ARCHITECT</option><option>ALL</option></select>
</div>

<div id="err"></div>
<h2>Resultado</h2><div id="gate"><p class="INSUFFICIENT_DATA">INSUFFICIENT_DATA — aún no hay entrevistas.</p></div>
<h2>Métricas</h2><div id="metrics"><p class="sub">—</p></div>
<h2>Por alternativa</h2><div id="alts"><p class="sub">—</p></div>
<h2>Umbrales fijados antes de ver datos</h2>
<table><tr><th>parámetro</th><th>valor</th></tr>{thr_rows}</table>
<div class="note">Los umbrales no se modifican después de ver resultados. Si al leer los datos parecen
mal calibrados, eso se anota como aprendizaje para la siguiente ronda; no se reescribe esta tabla.</div>
</div>

<script>
const CFG = {cfg};
const $ = s => document.querySelector(s);
document.getElementById("file").addEventListener("change", e => {{
  const f = e.target.files[0]; if(!f) return;
  const r = new FileReader(); r.onload = () => {{ $("#paste").value = r.result; run(); }};
  r.readAsText(f);
}});

function parseCSV(t){{
  const rows=[]; let row=[], cur="", q=false;
  for(let i=0;i<t.length;i++){{const c=t[i];
    if(q){{ if(c==='"'){{ if(t[i+1]==='"'){{cur+='"';i++;}} else q=false; }} else cur+=c; }}
    else if(c==='"') q=true;
    else if(c===","){{row.push(cur);cur="";}}
    else if(c==="\\n"){{row.push(cur);rows.push(row);row=[];cur="";}}
    else if(c!=="\\r") cur+=c;}}
  if(cur!==""||row.length){{row.push(cur);rows.push(row);}}
  const head=rows.shift()||[];
  return rows.filter(r=>r.some(v=>v!=="")).map(r=>Object.fromEntries(head.map((h,i)=>[h.trim(),(r[i]||"").trim()])));
}}
const pct=(n,d)=>d?Math.round(1000*n/d)/10:null;
const split=v=>(v||"").split("|").map(x=>x.trim()).filter(Boolean);

function preferredReal(rs){{
  const p=rs[0].preferred_option;
  if(!p||p==="NONE") return "";
  const m=rs.find(r=>r.option_blind===p); return m?m.option_real:"";
}}

function compute(rows, seg){{
  const byId={{}}; rows.forEach(r=>{{(byId[r.respondent_id]=byId[r.respondent_id]||[]).push(r);}});
  const all=Object.values(byId);
  const nComm=all.filter(v=>CFG.commercialRoles.includes(v[0].role)).length;
  let people=all;
  if(seg==="COMMERCIAL") people=all.filter(v=>CFG.commercialRoles.includes(v[0].role));
  if(seg==="ARCHITECT")  people=all.filter(v=>v[0].role==="ARCHITECT");
  const n=people.length;

  let send=0,conf4=0,chg=0; const blockers={{}};
  people.forEach(rs=>{{
    const alt=preferredReal(rs); const row=rs.find(r=>r.option_real===alt);
    if(!row) return;
    if(row.send_to_client==="YES") send++;
    if(+row.confidence>=4) conf4++;
    if(CFG.changeOk.includes(row.change_magnitude)) chg++;
    if(row.blocking_error==="YES") split(row.defect_categories).forEach(d=>blockers[d]=(blockers[d]||0)+1);
  }});
  const wb=Object.entries(blockers).sort((a,b)=>b[1]-a[1])[0]||["",0];

  const perAlt={{}};
  ["A","B","C"].forEach(a=>{{
    const rs=people.flat().filter(r=>r.option_real===a);
    const yes=rs.filter(r=>r.send_to_client==="YES").length;
    const cs=rs.map(r=>+r.confidence).filter(x=>x>=1&&x<=5);
    const blk=rs.filter(r=>r.blocking_error==="YES").length;
    const sr=pct(yes,rs.length), cr=pct(cs.filter(x=>x>=4).length,cs.length), br=pct(blk,rs.length);
    perAlt[a]={{n:rs.length, send_rate:sr,
      preferred_n:people.filter(v=>preferredReal(v)===a).length,
      mean_confidence: cs.length?Math.round(100*cs.reduce((x,y)=>x+y,0)/cs.length)/100:null,
      conf4_rate:cr, blocking_error_rate:br,
      strategy_recognition: pct(rs.filter(r=>split(r.strategy_tags).includes(CFG.intendedTag[a])).length, rs.length),
      reception_acceptance: pct(rs.filter(r=>r.reception_ok==="YES").length, rs.length),
      move_reception_rate: pct(rs.filter(r=>r.move_reception==="YES").length, rs.length),
      classification: sr===null?"NO_DATA":(sr>=70&&(cr||0)>=60&&(br||0)<30?"BROKER_READY":(sr<50?"REJECTED":"BORDERLINE"))}};
  }});

  const f=people.map(v=>v[0]);
  const m={{segment:seg,n,nComm,
    send_rate_preferred:pct(send,n), conf4_rate_preferred:pct(conf4,n),
    change_ok_rate_preferred:pct(chg,n),
    worst_shared_blocker:wb[0], worst_shared_blocker_rate:pct(wb[1],n),
    distinctness_rate:pct(f.filter(r=>r.options_distinct==="YES").length,n),
    pain_rate:pct(f.filter(r=>CFG.slowTurnaround.includes(r.current_turnaround)||r.current_testfit_method==="NO_TESTFIT").length,n),
    frequency_rate:pct(f.filter(r=>CFG.frequent.includes(r.frequency)).length,n),
    would_use_rate:pct(f.filter(r=>r.would_use_under_2min==="YES").length,n),
    share_rate:pct(f.filter(r=>CFG.shareMeaningful.includes(r.share_of_searches)).length,n),
    qa:{{ALWAYS:f.filter(r=>r.human_qa_need==="ALWAYS").length,
        SOMETIMES:f.filter(r=>r.human_qa_need==="SOMETIMES").length,
        IMPORTANT_CLIENTS_ONLY:f.filter(r=>r.human_qa_need==="IMPORTANT_CLIENTS_ONLY").length,
        NO:f.filter(r=>r.human_qa_need==="NO").length}},
    perAlt}};
  const T=CFG.thresholds;
  const chk=(name,val,thr,ok)=>({{name,val,thr,status:ok?"PASS":"FAIL"}});
  if(n<T.MIN_RESPONDENTS){{
    m.layout={{result:"INSUFFICIENT_DATA",checks:[]}}; m.product={{result:"INSUFFICIENT_DATA",checks:[]}};
  }} else {{
    m.layout={{checks:[
      chk("G0 muestra",`${{n}} evaluadores · ${{nComm}} comerciales`,`>= ${{T.MIN_RESPONDENTS}} y >= ${{T.MIN_COMMERCIAL}} comerciales`, n>=T.MIN_RESPONDENTS&&nComm>=T.MIN_COMMERCIAL),
      chk("G1 send rate sobre la preferida",m.send_rate_preferred,`>= ${{T.G1_SEND_PREFERRED*100}}%`,(m.send_rate_preferred||0)>=T.G1_SEND_PREFERRED*100),
      chk("G2 confianza >= 4 sobre la preferida",m.conf4_rate_preferred,`>= ${{T.G2_CONF4_PREFERRED*100}}%`,(m.conf4_rate_preferred||0)>=T.G2_CONF4_PREFERRED*100),
      chk("G3 defecto bloqueante compartido",`${{m.worst_shared_blocker||"—"}} ${{m.worst_shared_blocker_rate||0}}%`,`< ${{T.G3_SHARED_BLOCKER*100}}%`,(m.worst_shared_blocker_rate||0)<T.G3_SHARED_BLOCKER*100),
      chk("G4 cambio NO_CHANGE o MINOR",m.change_ok_rate_preferred,`>= ${{T.G4_CHANGE_OK*100}}%`,(m.change_ok_rate_preferred||0)>=T.G4_CHANGE_OK*100)]}};
    m.layout.result=m.layout.checks.every(c=>c.status==="PASS")?"PASS":"FAIL";
    m.product={{checks:[
      chk("P1 dolor real",m.pain_rate,`>= ${{T.P1_PAIN*100}}%`,(m.pain_rate||0)>=T.P1_PAIN*100),
      chk("P2 frecuencia",m.frequency_rate,`>= ${{T.P2_FREQUENCY*100}}%`,(m.frequency_rate||0)>=T.P2_FREQUENCY*100),
      chk("P3 lo usaría en < 2 min",m.would_use_rate,`>= ${{T.P3_WOULD_USE*100}}%`,(m.would_use_rate||0)>=T.P3_WOULD_USE*100),
      chk("P4 cubre >= 26% de sus búsquedas",m.share_rate,`>= ${{T.P4_SHARE*100}}%`,(m.share_rate||0)>=T.P4_SHARE*100)]}};
    m.product.result=m.product.checks.every(c=>c.status==="PASS")?"PASS":"FAIL";
  }}
  m.gate=(m.layout.result==="PASS"&&m.product.result==="PASS")?"PASS":
         (n<T.MIN_RESPONDENTS?"INSUFFICIENT_DATA":"FAIL");
  return m;
}}

function tbl(rows,head){{return "<table><tr>"+head.map(h=>`<th>${{h}}</th>`).join("")+"</tr>"+
  rows.map(r=>"<tr>"+r.map((c,i)=>i?`<td class="n">${{c==null?"—":c}}</td>`:`<td>${{c}}</td>`).join("")+"</tr>").join("")+"</table>";}}

function run(){{
  const rows=parseCSV($("#paste").value||"");
  if(!rows.length){{ $("#err").innerHTML='<p class="warn">CSV vacío o sin filas.</p>'; return; }}
  $("#err").innerHTML="";
  const m=compute(rows,$("#seg").value);
  $("#gate").innerHTML=
    `<p>GATE GLOBAL: <span class="${{m.gate}}">${{m.gate}}</span> &nbsp;·&nbsp;
      LAYOUT QUALITY: <span class="${{m.layout.result}}">${{m.layout.result}}</span> &nbsp;·&nbsp;
      PRODUCT VALUE: <span class="${{m.product.result}}">${{m.product.result}}</span></p>`+
    "<h3>Layout quality gate</h3>"+
    tbl(m.layout.checks.map(c=>[c.name,c.val,c.thr,`<span class="${{c.status}}">${{c.status}}</span>`]),
        ["chequeo","valor","umbral","estado"]).replace(/<td class="n">(<span)/g,'<td>$1')+
    "<h3>Product value gate</h3>"+
    tbl(m.product.checks.map(c=>[c.name,c.val,c.thr,`<span class="${{c.status}}">${{c.status}}</span>`]),
        ["chequeo","valor","umbral","estado"]).replace(/<td class="n">(<span)/g,'<td>$1');
  $("#metrics").innerHTML=tbl([
    ["evaluadores en el segmento",m.n],["comerciales en el dataset",m.nComm],
    ["SEND RATE (preferida)",m.send_rate_preferred],["CONFIANZA >=4 (preferida)",m.conf4_rate_preferred],
    ["CAMBIO NO_CHANGE/MINOR (preferida)",m.change_ok_rate_preferred],
    ["defecto bloqueante más repetido",`${{m.worst_shared_blocker||"—"}} (${{m.worst_shared_blocker_rate||0}}%)`],
    ["DISTINCTNESS",m.distinctness_rate],["DOLOR",m.pain_rate],["FRECUENCIA",m.frequency_rate],
    ["WOULD USE < 2 min",m.would_use_rate],["COBERTURA >=26%",m.share_rate],
    ["QA: ALWAYS / SOMETIMES / IMPORTANT / NO",
     `${{m.qa.ALWAYS}} / ${{m.qa.SOMETIMES}} / ${{m.qa.IMPORTANT_CLIENTS_ONLY}} / ${{m.qa.NO}}`]],
    ["métrica","valor"]);
  $("#alts").innerHTML=tbl(["A","B","C"].map(a=>{{const p=m.perAlt[a];return [a,p.n,p.send_rate,
    p.preferred_n,p.mean_confidence,p.blocking_error_rate,p.strategy_recognition,
    p.reception_acceptance,`<span class="${{p.classification}}">${{p.classification}}</span>`];}}),
    ["alt","n","send rate","preferida","confianza media","bloqueantes","estrategia reconocida",
     "recepción OK","clasificación"]).replace(/<td class="n">(<span)/g,'<td>$1');
}}
</script></body></html>"""


def pack_html(case: str) -> str:
    """§54 — un solo HTML con todo lo necesario para correr una entrevista, sin servidor.
    Las láminas van incrustadas como data URI: el archivo funciona sin red y sin archivos vecinos."""
    d = os.path.join(case, "validation", "E13")

    def b64(name: str) -> str:
        with open(os.path.join(d, name), "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()

    blind, reveal = b64("BROKER_VALIDATION_BLIND_BOARD.png"), b64("BROKER_VALIDATION_REVEAL_BOARD.png")
    interviewer = open(os.path.join("docs", "BROKER_VALIDATION_INTERVIEWER.md"), encoding="utf-8").read()
    protocol = open(os.path.join("docs", "BROKER_VALIDATION_PROTOCOL.md"), encoding="utf-8").read()
    form = form_html()
    score = scorecard_html()

    def frame(name: str, html: str) -> str:
        return (f'<iframe title="{name}" style="width:100%;height:78vh;border:1px solid #d9dce2;'
                f'border-radius:6px" srcdoc="{html.replace("&", "&amp;").replace(chr(34), "&quot;")}">'
                f"</iframe>")

    def md(t: str) -> str:
        return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESCALÍMETRO · Broker Validation Pack</title><style>{CSS}
nav{{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:10px 0;z-index:9}}
nav a{{color:var(--ink);text-decoration:none;margin-right:16px;font-size:14px}}
nav a:hover{{text-decoration:underline}}
</style></head><body><div class="wrap">
<nav><a href="#instr">1 Instrucciones</a><a href="#blind">2 Lámina ciega</a>
<a href="#form">3 Formulario</a><a href="#reveal">4 Lámina revelada</a>
<a href="#script">5 Guion</a><a href="#proto">6 Protocolo</a><a href="#score">7 Scorecard</a></nav>

<h1>Broker Validation Pack</h1>
<p class="sub">Todo lo necesario para una entrevista de 10–15 minutos. Abre sin servidor y sin red.</p>

<h2 id="instr">1 · Instrucciones</h2>
<div class="card">
<ol>
<li>Abre este archivo en pantalla completa. <b class="warn">No muestres el formulario ni el guion al
evaluador</b>: contienen el orden de presentación y el propósito del test.</li>
<li>Muestra <b>sólo la sección 2, lámina ciega</b>. Idealmente impresa o en una pantalla aparte.</li>
<li>Pon el cronómetro cuando aparezca la lámina. Detenlo cuando responda la primera pregunta Q1.</li>
<li>Sigue el guion de la sección 5 palabra por palabra. No expliques, no defiendas, no vendas.</li>
<li>Llena el formulario de la sección 3 mientras habla.</li>
<li>Sólo al final, después de todas las preguntas ciegas, muestra la sección 4.</li>
<li>Exporta las tres filas CSV y pégalas en <code>broker_validation_responses.csv</code>.</li>
</ol>
</div>

<h2 id="blind">2 · Lámina ciega — esto es lo único que ve el evaluador</h2>
<img class="board" src="{blind}" alt="Blind validation board">

<h2 id="form">3 · Formulario de captura</h2>
{frame("formulario", form)}

<h2 id="reveal">4 · Lámina revelada — sólo DESPUÉS de la evaluación ciega</h2>
<img class="board" src="{reveal}" alt="Reveal validation board">

<h2 id="script">5 · Guion del entrevistador</h2>
<pre>{md(interviewer)}</pre>

<h2 id="proto">6 · Protocolo completo</h2>
<pre>{md(protocol)}</pre>

<h2 id="score">7 · Scorecard</h2>
{frame("scorecard", score)}
</div></body></html>"""
