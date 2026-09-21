"""E30 §7/§16 — la PROPUESTA: una lámina de lectura, con marca, para mandar.

Qué es: un HTML autocontenido —sin JavaScript, sin dependencias, sin llamadas a ninguna parte—
con la portada del prospecto, el plano comercial, las alternativas entregadas y la procedencia.
El mismo archivo se muestra en la aplicación y se mete en el ZIP, así que lo que el cliente ve en
pantalla y lo que abre su prospecto son el mismo documento. No hay dos verdades.

Qué NO es, y conviene que quede escrito:

* **no es una página pública.** No hay enlace anónimo ni token. §2 pide una página compartible
  "if already supported cleanly" y hoy no lo está: la aplicación tiene una sola cuenta compartida
  (la deuda que E28 ya declaró), así que abrir una ruta sin autenticar sería abrir el material de
  todas las propiedades, no el de ésta. Se entrega como archivo, que es reversible, y el enlace
  público queda como decisión explícita con dueño.
* **no promete nada.** §22: no hay "arrienda más rápido" ni "mejor conversión". Dice qué se evaluó,
  con qué programa y qué encontró el motor — incluido cuando no encontró nada.
* **la marca no toca el contenido arquitectónico** (§7). Va en la portada y en el pie. El plano y
  los layouts entran tal cual salieron del motor.
"""
from __future__ import annotations

import html
from typing import Callable, Dict, List, Optional

from . import presets

SCHEMA_VERSION = "proposal_v1"


def _e(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


CSS = """
:root{--tinta:#1f2430;--suave:#6b7280;--linea:#e5e7eb;--marca:%COLOR%;}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
     color:var(--tinta);background:#fff}
.hoja{max-width:940px;margin:0 auto;padding:40px 28px 72px}
header{border-top:6px solid var(--marca);padding-top:22px;margin-bottom:34px;
       display:flex;gap:20px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
header img.logo{max-height:52px;max-width:210px;object-fit:contain}
h1{font-size:27px;margin:0 0 4px;letter-spacing:-.4px}
h2{font-size:17px;margin:38px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--linea)}
.sub{color:var(--suave);font-size:14px;margin:0}
.para{font-size:13px;letter-spacing:.09em;text-transform:uppercase;color:var(--marca);
      font-weight:600;margin:0 0 6px}
figure{margin:0 0 26px}
figure img{width:100%;border:1px solid var(--linea);border-radius:5px;display:block}
figcaption{font-size:13px;color:var(--suave);margin-top:7px}
.grid{display:grid;gap:20px;grid-template-columns:repeat(auto-fit,minmax(270px,1fr))}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{text-align:left;padding:7px 10px;border-bottom:1px solid var(--linea);vertical-align:top}
th{color:var(--suave);font-weight:500;width:38%}
.nota{background:#fbfbfc;border:1px solid var(--linea);border-left:3px solid var(--marca);
      border-radius:4px;padding:13px 15px;font-size:14px;margin:18px 0}
footer{margin-top:52px;padding-top:16px;border-top:1px solid var(--linea);
       font-size:12px;color:var(--suave)}
code{font-size:11px;color:var(--suave);word-break:break-all}
@media print{.hoja{padding:0}body{font-size:13px}}
"""


def render(prop: Dict, fitv: Dict, brokerage: Dict, floorplan_url: Optional[str],
           layout_urls: List[Dict], logo_url: Optional[str] = None,
           technical: Optional[Dict] = None, staged: Optional[Dict] = None) -> str:
    """Devuelve el HTML completo de la propuesta.

    `layout_urls` es [{"url","alt","name","representative","why","metrics"}] — ya filtrado por lo
    que el producto entrega. Esta función no decide cuántas alternativas mostrar: muestra las que
    le pasan."""
    f = fitv["fit"]
    es_prospecto = f["kind"] == "PROSPECT"
    marca = fitv["brand"]
    color = marca.get("color") or "#1f2430"
    titular = marca["name"] if (es_prospecto and marca["name"]) else (brokerage.get("name") or "")

    cab = [f'<div><p class="para">{"Propuesta para" if es_prospecto else "Propiedad"}</p>',
           f'<h1>{_e(f["prospect_name"] or prop["title"])}</h1>']
    linea = " · ".join(x for x in [prop["title"] if es_prospecto else "",
                                   prop["city"], prop["reference"],
                                   f'{prop["published_area_m2"]:.0f} m²'
                                   if prop["published_area_m2"] else ""] if x)
    cab.append(f'<p class="sub">{_e(linea)}</p></div>')
    if logo_url:
        cab.append(f'<img class="logo" src="{_e(logo_url)}" alt="{_e(titular)}">')
    elif titular:
        cab.append(f'<div class="sub"><strong>{_e(titular)}</strong></div>')

    partes = [f'<header>{"".join(cab)}</header>']

    b = fitv.get("brief") or {}
    partes.append("<h2>El programa que se evaluó</h2><table>")
    filas = [("Personas", f.get("headcount")),
             ("Forma de trabajo", fitv.get("preset_label")),
             ("Puestos fijos", b.get("open_workstations")),
             ("Programa", fitv.get("brief_summary")),
             ("Estilo visual", style_note(f.get("visual_style") or ""))]
    for k, v in filas:
        if v:
            partes.append(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>")
    partes.append("</table>")
    if f.get("notes"):
        partes.append(f'<div class="nota">{_e(f["notes"])}</div>')

    if floorplan_url:
        partes.append("<h2>La planta</h2><figure>"
                      f'<img src="{_e(floorplan_url)}" alt="Plano comercial">'
                      "<figcaption>Planta preparada a partir del plano original de la "
                      "propiedad.</figcaption></figure>")

    if layout_urls:
        titulo = "Alternativas" if len(layout_urls) > 1 else "Alternativa representativa"
        partes.append(f"<h2>{titulo}</h2><div class='grid'>")
        for lay in layout_urls:
            pie = _e(lay.get("name") or f'Alternativa {lay["alt"]}')
            if lay.get("why"):
                pie += f' — {_e(lay["why"])}'
            partes.append(f'<figure><img src="{_e(lay["url"])}" alt="Alternativa {_e(lay["alt"])}">'
                          f"<figcaption>{pie}</figcaption></figure>")
        partes.append("</div>")
    else:
        # §22 — el estado honesto se escribe en la propuesta, no se omite para que se vea mejor.
        partes.append('<h2>Alternativas</h2><div class="nota">Todavía no hay alternativas de '
                      'layout para este programa. Cuando el motor no encuentra una distribución '
                      'válida con la búsqueda hecha, este documento lo dice en vez de mostrar '
                      'otra cosa.</div>')

    if staged:
        # §23 — la imagen ambientada SIEMPRE va con su foto real al lado y con la leyenda visible.
        # No es una marca de agua gigante; es una frase que no se puede no ver.
        partes.append("<h2>La imagen ambientada</h2><div class='grid'>")
        if staged.get("original_url"):
            partes.append(f'<figure><img src="{_e(staged["original_url"])}" alt="Foto real">'
                          "<figcaption>Foto real de la propiedad</figcaption></figure>")
        partes.append(f'<figure><img src="{_e(staged["staged_url"])}" alt="Ambientación referencial">'
                      f'<figcaption><strong>{_e(staged["disclosure"])}</strong></figcaption></figure>')
        partes.append("</div>")

    if technical:
        partes.append("<h2>Procedencia</h2><table>")
        for k, v in technical.items():
            if v:
                partes.append(f"<tr><th>{_e(k)}</th><td><code>{_e(v)}</code></td></tr>")
        partes.append("</table>")

    pie_marca = brokerage.get("name") or "Escalímetro"
    partes.append(f"<footer>{_e(pie_marca)} · documento generado por Escalímetro · "
                  f"{_e(SCHEMA_VERSION)}<br>Las alternativas son estudios de distribución sobre la "
                  "geometría del plano entregado. No son proyecto de arquitectura ni "
                  "documentación de construcción.</footer>")

    return ("<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_e(f['prospect_name'] or prop['title'])} · Escalímetro</title>"
            f"<style>{CSS.replace('%COLOR%', color)}</style></head><body>"
            f'<div class="hoja">{"".join(partes)}</div></body></html>')


def style_note(style_key: str) -> str:  # noqa: E302
    """Una línea sobre el estilo elegido, para la propuesta. Descriptiva, nunca una promesa."""
    s = presets.VISUAL_STYLES.get(style_key)
    return f"{s.label}: {s.mood}. Materiales: {s.materials}." if s else ""
