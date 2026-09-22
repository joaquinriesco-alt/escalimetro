"""E36 — EL PILOTO REAL: dejar de inventar heurísticas y empezar a medir propiedades de verdad.

E35 terminó con una conclusión que este módulo toma en serio: **no hay evidencia suficiente para
seguir afinando nada.** Dos unidades sobre una lámina no calibran un umbral, y ninguna cantidad de
razonamiento arregla eso. Lo único que lo arregla es procesar propiedades reales.

=================================================================================================
Qué cuenta como N, y por qué importa tanto
=================================================================================================
Es fácil hacer que el contador suba: subir tres veces el mismo plano con nombres distintos ya
produce "tres propiedades". El dogfood de E35 —«Oficina 403», «Mi oficina», «X»— es exactamente
eso, y fue útil para demostrar independencia del nombre. Como muestra de calibración vale **uno**.

Por eso el piloto filtra por dos cosas a la vez:

    procedencia   sólo `REAL_*`. Un fixture sintético no es evidencia sobre planos reales, y una
                  propiedad heredada sin procedencia declarada tampoco: `source_type` nace en NULL
                  y NULL no es "real".
    unicidad      el sha256 del plano original. Tres propiedades con el mismo plano son una sola
                  planta vista tres veces. Las repeticiones sirven para repetibilidad, no para N.

Contar mal aquí sería peor que no contar: daría por calibrado algo que no lo está, que es
justamente lo que E35 se negó a hacer.

=================================================================================================
Qué se mide
=================================================================================================
* **tasa de intervención manual** — cuántas propiedades pasan solas y por qué fallan las demás.
  Es la métrica de producto: dice si "automático" es verdad.
* **tiempo hasta el Pack** — seis marcas, ningún tracking fino.
* **calificación de producto** (E33) y **etiqueta de verdad geométrica** (E36 §9), separadas.
* **corpus de ambientación** — fotos reales elegibles, que es lo que bloquea E31.1.

Ninguna de estas mediciones cambia un umbral. E36 propone; una persona decide (§12).
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from .. import store

REAL_BROKER = "REAL_BROKER"
REAL_PUBLIC_LISTING = "REAL_PUBLIC_LISTING"
REAL_INTERNAL = "REAL_INTERNAL"
FIXTURE = "FIXTURE"
SYNTHETIC = "SYNTHETIC"
SOURCE_TYPES = (REAL_BROKER, REAL_PUBLIC_LISTING, REAL_INTERNAL, FIXTURE, SYNTHETIC)
SOURCE_LABEL = {REAL_BROKER: "Corredora", REAL_PUBLIC_LISTING: "Aviso público",
                REAL_INTERNAL: "Interno real", FIXTURE: "Fixture de prueba",
                SYNTHETIC: "Sintético"}

#: Metas del piloto. Primero 10, después 20 (§5). No se gamifica: sirven para saber si ya hay
#: muestra, que es la única pregunta que estos números contestan.
TARGET_FIRST, TARGET_SECOND = 10, 20


class PilotError(ValueError):
    """Procedencia fuera del vocabulario."""


def is_real(source_type: Optional[str]) -> bool:
    """`REAL_*` y nada más. NULL —"sin declarar"— no es real: una propiedad heredada no se vuelve
    evidencia porque estuviera ahí antes."""
    return bool(source_type) and source_type.startswith("REAL_")


def target(n: int) -> int:
    return TARGET_FIRST if n < TARGET_FIRST else TARGET_SECOND


# =================================================================================================
# marcar
# =================================================================================================
def mark(property_id: str, *, in_pilot: Optional[bool] = None,
         source_type: Optional[str] = None, source_reference: Optional[str] = None) -> None:
    if source_type is not None and source_type not in SOURCE_TYPES:
        raise PilotError(f"procedencia desconocida: {source_type}. "
                         f"Admitidas: {', '.join(SOURCE_TYPES)}")
    campos, args = [], []
    if in_pilot is not None:
        campos.append("in_pilot=?")
        args.append(1 if in_pilot else 0)
    if source_type is not None:
        campos.append("source_type=?")
        args.append(source_type)
    if source_reference is not None:
        campos.append("source_reference=?")
        args.append(source_reference.strip()[:200])
    if not campos:
        return
    args += [store.now(), property_id]
    store.ex(f"UPDATE properties SET {', '.join(campos)}, updated_at=? WHERE property_id=?",
             tuple(args))


def stamp(property_id: str, field: str) -> None:
    """Marca un hito de tiempo si todavía no estaba marcado. Idempotente a propósito: el hito es
    la PRIMERA vez que algo estuvo listo, no la última vez que alguien miró la página."""
    if field not in ("pack1_started_at", "geometry_ready_at", "layout_ready_at",
                     "staging_ready_at", "pack1_ready_at"):
        raise PilotError(f"hito desconocido: {field}")
    store.ex(f"UPDATE properties SET {field}=? WHERE property_id=? AND {field} IS NULL",
             (store.now(), property_id))


# =================================================================================================
# quiénes son N
# =================================================================================================
def floorplan_sha(property_id: str) -> Optional[str]:
    r = store.q1("SELECT sha256 FROM property_assets WHERE property_id=? AND kind=? "
                 "ORDER BY created_at LIMIT 1", (property_id, "FLOORPLAN_ORIGINAL"))
    return r["sha256"] if r else None


def members() -> List[Dict]:
    """Las propiedades marcadas como piloto CON procedencia real. En orden estable."""
    out = []
    for r in store.q("SELECT * FROM properties WHERE in_pilot=1 ORDER BY created_at, property_id"):
        if not is_real(r["source_type"]):
            continue
        d = dict(r)
        d["floorplan_sha256"] = floorplan_sha(r["property_id"])
        out.append(d)
    return out


def unique_members() -> List[Dict]:
    """Una propiedad por plano distinto (§23). Representa al grupo la que tenga etiquetas de verdad;
    a igualdad, la más antigua. Determinista, para que dos lecturas del panel no difieran.

    Las propiedades sin plano no se pueden deduplicar por su plano y se cuentan aparte: son piloto
    incompleto, no evidencia."""
    from . import gold                                         # noqa: PLC0415
    por_sha: Dict[str, Dict] = {}
    for m in members():
        sha = m["floorplan_sha256"]
        if not sha:
            continue
        m = dict(m, gold_labels=len(gold.of_property(m["property_id"])))
        prev = por_sha.get(sha)
        if prev is None or m["gold_labels"] > prev["gold_labels"]:
            por_sha[sha] = m
    return sorted(por_sha.values(), key=lambda m: (m["created_at"], m["property_id"]))


def duplicates() -> Dict[str, int]:
    """Cuántas veces aparece cada plano. Sirve para repetibilidad, no para tamaño de muestra."""
    cuenta: Dict[str, int] = {}
    for m in members():
        if m["floorplan_sha256"]:
            cuenta[m["floorplan_sha256"]] = cuenta.get(m["floorplan_sha256"], 0) + 1
    return cuenta


# =================================================================================================
# métricas
# =================================================================================================
def intervention_metrics(props: Optional[List[Dict]] = None) -> Dict:
    """§14 — la métrica de producto: ¿cuántas propiedades pasan solas, y cuándo no, por qué?"""
    from . import interventions                                # noqa: PLC0415
    props = unique_members() if props is None else props
    por_prop, por_motivo = [], {r: 0 for r in interventions.REASONS}
    for p in props:
        c = interventions.by_reason(p["property_id"])
        for k, v in c.items():
            por_motivo[k] += v
        por_prop.append(sum(c.values()))
    n = len(por_prop)
    solas = sum(1 for x in por_prop if x == 0)
    top = max(por_motivo.items(), key=lambda kv: (kv[1], kv[0])) if any(por_motivo.values()) else None
    return {"properties": n, "fully_automatic": solas,
            "fully_automatic_pct": None if not n else round(100.0 * solas / n, 1),
            "median_interventions": None if not n else statistics.median(por_prop),
            "distribution": {str(k): por_prop.count(k) for k in sorted(set(por_prop))},
            "by_reason": por_motivo, "labels": interventions.LABELS,
            "top_reason": top[0] if top else None}


def timing_metrics(props: Optional[List[Dict]] = None) -> Dict:
    """§15 — «¿cuánto demora realmente preparar una propiedad?»

    Se reportan medianas de tramos con marcas reales. NO se reporta tiempo de atención humana: las
    marcas miden reloj de pared, y presentar eso como "cuánto tardó la persona" sería inventar una
    medición que nadie tomó. Lo que sí se mide del humano es el lapso entre su primera y su última
    intervención, dicho con ese nombre."""
    from . import interventions                                # noqa: PLC0415
    props = unique_members() if props is None else props
    tramos = {"created_to_pack1_started": ("created_at", "pack1_started_at"),
              "pack1_started_to_geometry": ("pack1_started_at", "geometry_ready_at"),
              "geometry_to_layout": ("geometry_ready_at", "layout_ready_at"),
              "created_to_pack1_ready": ("created_at", "pack1_ready_at")}
    acum: Dict[str, List[float]] = {k: [] for k in tramos}
    lapsos: List[float] = []
    for p in props:
        for nombre, (a, b) in tramos.items():
            ta, tb = p.get(a), p.get(b)
            if ta and tb:
                d = store.seconds_between(ta, tb)
                if d is not None and d >= 0:
                    acum[nombre].append(d)
        h = interventions.history(p["property_id"])
        if len(h) >= 2:
            d = store.seconds_between(h[-1]["created_at"], h[0]["created_at"])
            if d is not None and d >= 0:
                lapsos.append(d)
    return {"properties": len(props),
            "median_seconds": {k: (round(statistics.median(v), 1) if v else None)
                               for k, v in acum.items()},
            "sample": {k: len(v) for k, v in acum.items()},
            "intervention_span_seconds": (round(statistics.median(lapsos), 1) if lapsos else None),
            "intervention_span_sample": len(lapsos),
            "_note": "reloj de pared entre hitos; no es tiempo de atención humana"}


def _rating_bucket(rows: List[Dict]) -> Dict:
    from . import reviews                                      # noqa: PLC0415
    n = len(rows)
    buenos = sum(1 for r in rows if r["rating"] in ("EXCELENTE", "BUENO"))
    malos = n - buenos
    tags: Dict[str, int] = {}
    for r in rows:
        if r["rating"] in ("MALO", "PESIMO"):
            for t in (store.js(r["reason_tags"], []) or []):
                tags[t] = tags.get(t, 0) + 1
    return {"total": n, "good": buenos, "bad": malos,
            "good_pct": None if not n else round(100.0 * buenos / n, 1),
            "bad_pct": None if not n else round(100.0 * malos / n, 1),
            "top_negative": dict(sorted(tags.items(), key=lambda kv: -kv[1])[:5]),
            "_ratings": reviews.RATINGS}


def pack1_ratings(props: Optional[List[Dict]] = None) -> Dict:
    """§16 — cómo salieron plano comercial, layout, ambientación y el Pack en conjunto."""
    props = unique_members() if props is None else props
    ids = [p["property_id"] for p in props]
    if not ids:
        return {"by_artifact": {}, "overall": _rating_bucket([])}
    marcas = ",".join("?" * len(ids))
    filas = [dict(r) for r in store.q(
        f"SELECT * FROM product_reviews WHERE property_id IN ({marcas}) "
        f"AND artifact_type IN ('PLANO','LAYOUT','STAGING','PACK1')", tuple(ids))]
    por_tipo = {t: _rating_bucket([r for r in filas if r["artifact_type"] == t])
                for t in ("PLANO", "LAYOUT", "STAGING", "PACK1")}
    return {"by_artifact": por_tipo, "overall": _rating_bucket(filas)}


def pack2_ratings(props: Optional[List[Dict]] = None) -> Dict:
    """§17 — el layout engine visto como producto: de cada propuesta A/B/C, ¿salvó alguna?"""
    from . import fits                                         # noqa: PLC0415
    props = unique_members() if props is None else props
    propuestas, mejores = [], {}
    for p in props:
        for f in fits.list_for(p["property_id"], include_base=False):
            filas = [dict(r) for r in store.q(
                "SELECT * FROM product_reviews WHERE property_id=? AND fit_id=? "
                "AND artifact_type='ALTERNATIVA'", (p["property_id"], f["fit_id"]))]
            if not filas:
                continue
            buenas = [r for r in filas if r["rating"] in ("EXCELENTE", "BUENO")]
            propuestas.append({"fit_id": f["fit_id"], "property_id": p["property_id"],
                               "headcount": f["headcount"],
                               "workplace_preset": f["workplace_preset"],
                               "rated": len(filas), "good": len(buenas),
                               "all_bad": not buenas})
            for r in sorted(filas, key=lambda x: ("EXCELENTE", "BUENO", "MALO", "PESIMO")
                            .index(x["rating"]))[:1]:
                mejores[r["artifact_id"]] = mejores.get(r["artifact_id"], 0) + 1
    n = len(propuestas)
    con_buena = sum(1 for x in propuestas if x["good"])
    return {"proposals": n, "with_good_alternative": con_buena,
            "with_good_pct": None if not n else round(100.0 * con_buena / n, 1),
            "all_bad": sum(1 for x in propuestas if x["all_bad"]),
            "all_bad_pct": None if not n else
                           round(100.0 * sum(1 for x in propuestas if x["all_bad"]) / n, 1),
            "best_alternative_distribution": dict(sorted(mejores.items())),
            "rows": propuestas}


# =================================================================================================
# corpus de ambientación
# =================================================================================================
def staging_corpus() -> Dict:
    """§18 — el corpus que E31.1 necesita, construido solo a partir del piloto.

    Sólo fotos de propiedades con procedencia REAL_*: una foto de fixture no prueba nada sobre cómo
    se comporta un proveedor con material de un cliente. No se lanza ningún proveedor (§18)."""
    from .. import benchmark                                   # noqa: PLC0415
    from . import assets, staging                              # noqa: PLC0415
    reales = [r for r in store.q("SELECT * FROM properties") if is_real(r["source_type"])]
    fotos, props = [], set()
    for p in reales:
        pid = p["property_id"]
        hero = staging.hero(pid)
        for a in assets.list_of_kind(pid, assets.PHOTO_ORIGINAL):
            fotos.append({
                "property_id": pid, "asset_id": a["asset_id"],
                "source_type": p["source_type"], "sha256": a["sha256"],
                "width": (store.js(a["metadata"], {}) or {}).get("width"),
                "height": (store.js(a["metadata"], {}) or {}).get("height"),
                "hero_candidate": bool(hero and hero["asset_id"] == a["asset_id"]),
                "difficult_features": (store.js(a["metadata"], {}) or {}).get(
                    "difficult_features", []),
                "usage_note": p["source_reference"] or "",
            })
            props.add(pid)
    unicas = {f["sha256"] for f in fotos if f["sha256"]}
    return {"photos": fotos, "photo_count": len(fotos), "unique_photos": len(unicas),
            "properties": len(props), "min_photos": benchmark.MIN_PHOTOS,
            "min_properties": benchmark.MIN_SPACES,
            "ready": len(unicas) >= benchmark.MIN_PHOTOS and len(props) >= benchmark.MIN_SPACES}


def staging_readiness() -> Dict:
    """§19/§20 — qué falta para el bake-off. Presencia de credenciales, nunca su valor."""
    from . import pilot                                        # noqa: PLC0415
    corpus = staging_corpus()
    r = pilot.readiness()
    creds = [{"name": p["name"], "env": p["env"], "configured": p["credential"],
              "in_pilot": p["in_pilot"], "excluded": p["excluded"]}
             for p in r["providers"]]
    con_cred = [c for c in creds if c["in_pilot"] and c["configured"]]
    return {"corpus": corpus, "credentials": creds, "credentials_present": len(con_cred),
            "ready": corpus["ready"] and len(con_cred) >= 2,
            "blockers": ([] if corpus["ready"] else
                         [f"faltan fotos reales: {corpus['unique_photos']}/{corpus['min_photos']} "
                          f"y propiedades {corpus['properties']}/{corpus['min_properties']}"])
                        + ([] if len(con_cred) >= 2 else
                           [f"faltan credenciales: {len(con_cred)}/2 proveedores del piloto"])}


# =================================================================================================
# panel y export
# =================================================================================================
def dashboard() -> Dict:
    """§21 — el panel compacto. Sin BI: los números que contestan «¿ya tenemos muestra?»."""
    from . import calibration, gold                            # noqa: PLC0415
    todas, unicas = members(), unique_members()
    con_gold = [m for m in unicas if gold.complete(m["property_id"])]
    calib = calibration.metrics(
        gold.rows_for_calibration([m["property_id"] for m in con_gold]))
    return {
        "properties": len(unicas), "properties_raw": len(todas),
        "target": target(len(unicas)),
        "duplicate_floorplans": sum(1 for n in duplicates().values() if n > 1),
        "gold_complete": len(con_gold),
        "interventions": intervention_metrics(unicas),
        "timings": timing_metrics(unicas),
        "pack1": pack1_ratings(unicas),
        "pack2": pack2_ratings(unicas),
        "calibration": calib,
        "proposal": calibration.proposal(calib),
        "staging": staging_readiness(),
    }


#: Campos que NUNCA salen en el export (§22). Se filtran por nombre en cada fila.
EXPORT_FORBIDDEN = ("source_reference", "notes", "path", "abs_path", "filename",
                    "original_filename", "api_key", "token", "secret", "city", "reference",
                    "author", "comment", "usage_note")


def export() -> Dict:
    """§22 — el dataset para auditar después.

    Lleva lo que permite reproducir un juicio —tiempos, intervenciones, confianzas, etiquetas,
    versión del motor, hashes— y deja fuera lo que no hace falta para auditarlo: nombres, rutas del
    sistema de archivos, referencias de origen, comentarios libres. Un export que arrastra datos
    personales "por si acaso" es una fuga esperando ocurrir."""
    from . import calibration, gold, interventions             # noqa: PLC0415
    unicas = unique_members()
    filas = []
    for m in unicas:
        pid = m["property_id"]
        g = gold.review_state(pid)
        ratings = [dict(r) for r in store.q(
            "SELECT artifact_type, rating, reason_tags, engine_version, artifact_sha256, "
            "unit_selection_source, unit_selection_confidence, scale_source, scale_confidence "
            "FROM product_reviews WHERE property_id=?", (pid,))]
        filas.append({
            "property_id": pid, "source_type": m["source_type"],
            "floorplan_sha256": m["floorplan_sha256"],
            "published_area_m2": m["published_area_m2"],
            "timings": {k: m.get(k) for k in ("created_at", "pack1_started_at",
                                              "geometry_ready_at", "layout_ready_at",
                                              "staging_ready_at", "pack1_ready_at")},
            "interventions": interventions.by_reason(pid),
            "intervention_count": interventions.count(pid),
            "engine_confidences": g["confidences"],
            "gold_labels": {c: {"verdict": v["verdict"], "engine_confidence":
                                v["engine_confidence"], "engine_version": v["engine_version"]}
                            for c, v in g["labels"].items()},
            "gold_complete": g["complete"],
            "product_ratings": [{k: v for k, v in r.items() if k not in EXPORT_FORBIDDEN}
                                for r in ratings],
            "negative_tags": sorted({t for r in ratings if r["rating"] in ("MALO", "PESIMO")
                                     for t in (store.js(r["reason_tags"], []) or [])}),
        })
    con_gold = [m["property_id"] for m in unicas if gold.complete(m["property_id"])]
    calib = calibration.metrics(gold.rows_for_calibration(con_gold))
    return {"_doc": "E36 §22 — dataset del piloto real para auditoría. Sin nombres, sin rutas, "
                    "sin credenciales, sin referencias de origen.",
            "schema_version": "e36_pilot_export_v1",
            "generated_at": store.now(),
            "properties": filas,
            "calibration": calib,
            "proposal": calibration.proposal(calib),
            "interventions": intervention_metrics(unicas),
            "timings": timing_metrics(unicas),
            "pack1": pack1_ratings(unicas), "pack2": pack2_ratings(unicas),
            "staging_corpus": {k: v for k, v in staging_corpus().items() if k != "photos"}}
