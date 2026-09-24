"""E17.0 — EL INFORME DE POTENCIAL: cada punto con su nombre y su medición.

=================================================================================================
Qué mide el score, y qué NO
=================================================================================================
Mide **qué tan bien la publicación está mostrando el potencial del inmueble**. Es una propiedad
del AVISO, no del inmueble y no del mercado. No predice visitas, ni ofertas, ni venta: para eso
haría falta correlacionar con resultados reales, no tenemos esos datos, y prometer conversión con
una heurística sobre cuatro fotos sería vender un número inexistente.

=================================================================================================
Cómo se construye, para que sea discutible
=================================================================================================
Cuatro dimensiones con peso fijo, y dentro de cada una **criterios con nombre**. Cada criterio
declara su peso, mide algo concreto y devuelve un valor entre 0 y 1. Los puntos de un criterio son
`peso × valor`, y el score es la suma. No hay ningún número redondeado a ojo en el camino: el
informe puede mostrar la aritmética entera y cualquiera puede rehacerla.

Un criterio que **no aplica** —dormitorios en una bodega, portada cuando no hay fotos— no vale
cero: vale `NO_APLICA` y su peso se reparte entre los que sí aplican. Contarlo como cero castigaría
al aviso por algo que no puede tener, que es la forma más rápida de que un score deje de
significar algo.

=================================================================================================
Lo que no se finge
=================================================================================================
La dimensión POTENCIAL es la diferencial y la más difícil de medir sin un modelo. Se resuelve con
señales que sí existen —hay plano o no; el plano se puede leer o no; hay o no una visualización
conceptual publicada— más un **proxy declarado** de ocupación visual. El proxy nunca decide solo
un criterio, y la evidencia que se muestra es la medición, no una conclusión sobre el ambiente.
"""
from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional, Tuple

from ... import store
from . import interventions as iv, listings, plans, vision

ANALYZER_VERSION = "potential-v0"

COVER, VISUAL, INFORMATION, POTENTIAL = ("COVER", "VISUAL", "INFORMATION", "POTENTIAL")
#: Peso de cada dimensión sobre 100. La portada y el conjunto pesan más porque son lo primero y lo
#: único que la mayoría de la gente mira; la información pesa menos que las dos juntas porque un
#: aviso completo con fotos malas no muestra nada; el potencial pesa poco en V0 a propósito,
#: porque es la dimensión que peor sabemos medir y no queremos que domine un score todavía crudo.
DIMENSIONS = {COVER: 30, VISUAL: 30, INFORMATION: 25, POTENTIAL: 15}
DIMENSION_LABEL = {COVER: "Portada", VISUAL: "Presentación visual",
                   INFORMATION: "Información", POTENTIAL: "Comunicación del potencial"}

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"

#: E17.1 §2 — las dos clases de hallazgo. El informe empieza por las oportunidades, no por el
#: puntaje: ESCALÍMETRO no vende un número, vende lo que se puede hacer con esta publicación.
RESOLVABLE = "RESOLVABLE"          # hay una intervención nuestra detrás
RECOMMENDATION = "RECOMMENDATION"  # lo arregla quien publica; nosotros sólo lo señalamos
KIND_LABEL = {RESOLVABLE: "Escalímetro puede resolverlo",
              RECOMMENDATION: "Recomendación para la publicación"}

#: Mínimos de conjunto. Como todo umbral de esta fase: escritos, visibles y sin calibrar.
MIN_PHOTOS = 6
IDEAL_PHOTOS = 12
MIN_DESCRIPTION_CHARS = 200
#: Por debajo de esta densidad de bordes en la mitad inferior, el cuadro tiene poco que mirar.
#: Es un PROXY de espacio vacío, no un detector de mobiliario (ver `vision.py`).
EMPTY_PROXY_MAX = 0.035


class _C:
    """Un criterio: código, peso, y una función que lo mide sobre el contexto del aviso."""

    def __init__(self, code, dimension, weight, label, fn):
        self.code, self.dimension, self.weight, self.label, self.fn = (
            code, dimension, weight, label, fn)


# =================================================================================================
# mediciones auxiliares
# =================================================================================================
def _photos(ctx) -> List[Dict]:
    return ctx["photos"]


def _cover(ctx) -> Optional[Dict]:
    return ctx["cover"]


def _na(motivo: str) -> Dict:
    return {"applies": False, "value": None, "measured": {}, "why": motivo}


def _val(v: float, medido: Dict, nota: str = "") -> Dict:
    return {"applies": True, "value": max(0.0, min(1.0, float(v))), "measured": medido,
            "why": nota}


# ---- PORTADA -------------------------------------------------------------------------------------
def _c_exists(ctx):
    if not _photos(ctx):
        return _na("el aviso no tiene fotos")
    return _val(1.0 if _cover(ctx) else 0.0,
                {"cover_media_id": (_cover(ctx) or {}).get("media_id")},
                "una publicación sin portada elegida muestra la primera que se subió")


def _c_brightness(ctx):
    c = _cover(ctx)
    if not c or not c["analysis_obj"].get("ok"):
        return _na("sin portada medible")
    b = c["analysis_obj"]["brightness"]
    return _val(vision._banda(b, *vision.BRIGHTNESS_OK),                 # noqa: SLF001
                {"brightness": b, "band": list(vision.BRIGHTNESS_OK)},
                "luminancia media de la portada dentro de la banda legible")


def _c_sharpness(ctx):
    c = _cover(ctx)
    if not c or not c["analysis_obj"].get("ok"):
        return _na("sin portada medible")
    s = c["analysis_obj"]["sharpness"]
    return _val(min(1.0, s / (vision.SHARPNESS_MIN * 3)),
                {"sharpness": s, "min": vision.SHARPNESS_MIN},
                "varianza del laplaciano: cuán definida está la imagen")


def _c_resolution(ctx):
    c = _cover(ctx)
    if not c or not c["analysis_obj"].get("ok"):
        return _na("sin portada medible")
    lado = c["analysis_obj"]["short_side"]
    return _val(min(1.0, lado / (vision.MIN_SHORT_SIDE * 1.5)),
                {"short_side": lado, "min": vision.MIN_SHORT_SIDE},
                "lado menor en píxeles")


def _c_framing(ctx):
    c = _cover(ctx)
    if not c or not c["analysis_obj"].get("ok"):
        return _na("sin portada medible")
    t = c["analysis_obj"].get("vertical_tilt_deg")
    if t is None:
        return _na("no se encontraron verticales suficientes para medir la inclinación")
    return _val(max(0.0, 1.0 - max(0.0, t - vision.TILT_DEGREES) / 10.0),
                {"vertical_tilt_deg": t, "tolerance_deg": vision.TILT_DEGREES},
                "desviación mediana de las líneas que deberían ser verticales")


def _c_best_available(ctx):
    """¿La portada es la mejor foto que hay? Es el criterio más barato de arreglar de todo el
    informe: no cuesta producir nada, sólo elegir distinto."""
    fotos = [p for p in _photos(ctx) if p["analysis_obj"].get("ok")]
    c = _cover(ctx)
    if len(fotos) < 2 or not c or not c["analysis_obj"].get("ok"):
        return _na("hace falta más de una foto medible para comparar")
    calidades = {p["media_id"]: vision.quality(p["analysis_obj"])["score"] for p in fotos}
    actual = calidades.get(c["media_id"], 0.0)
    mejor_id = max(calidades, key=lambda k: (calidades[k], k))
    mejor = calidades[mejor_id]
    v = 1.0 if mejor <= 0 else min(1.0, actual / mejor)
    return _val(v, {"cover_quality": round(actual, 3), "best_quality": round(mejor, 3),
                    "best_media_id": mejor_id, "is_best": mejor_id == c["media_id"]},
                "calidad técnica de la portada comparada con la mejor foto del aviso")


# ---- CONJUNTO ------------------------------------------------------------------------------------
def _c_count(ctx):
    n = len(_photos(ctx))
    return _val(min(1.0, n / MIN_PHOTOS) if n < MIN_PHOTOS else
                min(1.0, 0.7 + 0.3 * min(1.0, (n - MIN_PHOTOS) / (IDEAL_PHOTOS - MIN_PHOTOS))),
                {"photos": n, "min": MIN_PHOTOS, "ideal": IDEAL_PHOTOS},
                "cantidad de fotos del aviso")


def _c_no_duplicates(ctx):
    fotos = _photos(ctx)
    if len(fotos) < 2:
        return _na("hace falta más de una foto")
    grupos = ctx["duplicates"]
    repetidas = sum(len(g) - 1 for g in grupos)
    return _val(1.0 - min(1.0, repetidas / len(fotos)),
                {"duplicate_groups": grupos, "redundant_photos": repetidas,
                 "total": len(fotos)},
                "fotos que son la misma imagen que otra")


def _c_no_dark(ctx):
    fotos = [p for p in _photos(ctx) if p["analysis_obj"].get("ok")]
    if not fotos:
        return _na("sin fotos medibles")
    oscuras = [p["media_id"] for p in fotos
               if p["analysis_obj"]["brightness"] < vision.BRIGHTNESS_DARK]
    return _val(1.0 - len(oscuras) / len(fotos),
                {"dark": oscuras, "threshold": vision.BRIGHTNESS_DARK, "total": len(fotos)},
                "fotos por debajo del piso de luminancia")


def _c_no_blurry(ctx):
    fotos = [p for p in _photos(ctx) if p["analysis_obj"].get("ok")]
    if not fotos:
        return _na("sin fotos medibles")
    blandas = [p["media_id"] for p in fotos
               if (p["analysis_obj"]["sharpness"] or 0) < vision.SHARPNESS_MIN]
    return _val(1.0 - len(blandas) / len(fotos),
                {"blurry": blandas, "threshold": vision.SHARPNESS_MIN, "total": len(fotos)},
                "fotos por debajo del piso de nitidez")


def _c_consistent(ctx):
    fotos = [p for p in _photos(ctx) if p["analysis_obj"].get("ok")]
    if len(fotos) < 3:
        return _na("hacen falta al menos tres fotos para hablar de consistencia")
    orient = [p["analysis_obj"]["orientation"] for p in fotos]
    dominante = max(set(orient), key=orient.count)
    return _val(orient.count(dominante) / len(orient),
                {"orientations": {o: orient.count(o) for o in set(orient)},
                 "dominant": dominante},
                "mezclar horizontales y verticales rompe la galería")


# ---- INFORMACIÓN ---------------------------------------------------------------------------------
def _campo(nombre, etiqueta, solo_residencial=False):
    def fn(ctx):
        l = ctx["listing"]
        if solo_residencial and l["property_type"] not in listings.RESIDENTIAL:
            return _na(f"{etiqueta} no aplica a "
                       f"{listings.TYPE_LABEL.get(l['property_type'], 'este tipo')}")
        v = l.get(nombre)
        return _val(1.0 if v not in (None, "") else 0.0, {nombre: v}, f"{etiqueta} declarado")
    return fn


def _c_description(ctx):
    d = (ctx["listing"].get("description") or "").strip()
    return _val(min(1.0, len(d) / MIN_DESCRIPTION_CHARS),
                {"chars": len(d), "min": MIN_DESCRIPTION_CHARS},
                "largo de la descripción")


def _c_title(ctx):
    t = (ctx["listing"].get("title") or "").strip()
    palabras = len(t.split())
    return _val(0.0 if palabras == 0 else min(1.0, palabras / 5),
                {"title_words": palabras},
                "un título de una palabra no dice qué se está ofreciendo")


# ---- POTENCIAL ------------------------------------------------------------------------------------
def _c_empty_shown(ctx):
    """El criterio diferencial: si hay espacios que se leen vacíos y ninguna visualización que
    muestre un uso posible, el aviso está dejando sin mostrar lo que el inmueble podría ser.

    `emptiness_proxy` es un proxy declarado, no un detector. Por eso este criterio sólo penaliza
    cuando además **no existe ninguna visualización conceptual**: se necesitan las dos señales."""
    fotos = [p for p in _photos(ctx) if p["analysis_obj"].get("ok")]
    if not fotos:
        return _na("sin fotos medibles")
    vacias = [p["media_id"] for p in fotos
              if p["analysis_obj"].get("emptiness_proxy", 1.0) < EMPTY_PROXY_MAX]
    tiene_conceptual = bool(ctx["conceptual"])
    if not vacias:
        return _val(1.0, {"empty_like": [], "threshold": EMPTY_PROXY_MAX,
                          "conceptual_media": len(ctx["conceptual"])},
                    "ninguna foto se lee como espacio vacío")
    v = 1.0 if tiene_conceptual else max(0.0, 1.0 - len(vacias) / len(fotos))
    return _val(v, {"empty_like": vacias, "threshold": EMPTY_PROXY_MAX,
                    "proxy": "densidad de bordes en la mitad inferior del cuadro",
                    "conceptual_media": len(ctx["conceptual"]), "total": len(fotos)},
                "espacios que se leen vacíos sin ninguna visualización que muestre un uso")


def _c_plan_shown(ctx):
    """Hay un plano y se puede leer: el aviso podría demostrar cabida y no lo está haciendo."""
    p = ctx["plan"]
    if p["status"] == plans.NO_PLAN:
        return _na("el aviso no incluye plano")
    if p["status"] in (plans.LOOKS_UNREADABLE, plans.NOT_USABLE):
        return _na("hay un plano pero no se puede leer")
    return _val(1.0 if ctx["conceptual"] else 0.0,
                {"plan_status": p["status"], "plan_label": p["label"],
                 "conceptual_media": len(ctx["conceptual"])},
                "existe un plano utilizable y ninguna demostración de cabida publicada")


def _c_conceptual(ctx):
    return _val(1.0 if ctx["conceptual"] else 0.0,
                {"conceptual_media": len(ctx["conceptual"])},
                "el aviso incluye alguna visualización de lo que el inmueble podría ser")


CRITERIA: List[_C] = [
    _C("COVER_EXISTS", COVER, 6, "Hay una portada elegida", _c_exists),
    _C("COVER_BRIGHTNESS", COVER, 6, "La portada tiene luz suficiente", _c_brightness),
    _C("COVER_SHARPNESS", COVER, 6, "La portada está nítida", _c_sharpness),
    _C("COVER_RESOLUTION", COVER, 4, "La portada tiene resolución suficiente", _c_resolution),
    _C("COVER_FRAMING", COVER, 4, "Las verticales de la portada están derechas", _c_framing),
    _C("COVER_IS_BEST_AVAILABLE", COVER, 8, "La portada es la mejor foto disponible",
       _c_best_available),

    _C("SET_PHOTO_COUNT", VISUAL, 8, "Hay suficientes fotos", _c_count),
    _C("SET_NO_DUPLICATES", VISUAL, 6, "No hay fotos repetidas", _c_no_duplicates),
    _C("SET_NO_DARK", VISUAL, 6, "No hay fotos oscuras", _c_no_dark),
    _C("SET_NO_BLURRY", VISUAL, 6, "No hay fotos movidas o blandas", _c_no_blurry),
    _C("SET_CONSISTENT", VISUAL, 4, "Las fotos son consistentes entre sí", _c_consistent),

    _C("INFO_AREA", INFORMATION, 5, "Declara los metros cuadrados", _campo("area_m2", "la superficie")),
    _C("INFO_PRICE", INFORMATION, 4, "Declara el precio", _campo("price", "el precio")),
    _C("INFO_DESCRIPTION", INFORMATION, 5, "Tiene una descripción con contenido", _c_description),
    _C("INFO_TITLE", INFORMATION, 3, "El título dice qué se ofrece", _c_title),
    _C("INFO_BEDROOMS", INFORMATION, 3, "Declara los dormitorios",
       _campo("bedrooms", "los dormitorios", solo_residencial=True)),
    _C("INFO_BATHROOMS", INFORMATION, 3, "Declara los baños",
       _campo("bathrooms", "los baños", solo_residencial=True)),
    _C("INFO_PARKING", INFORMATION, 2, "Declara los estacionamientos",
       _campo("parking", "los estacionamientos")),

    _C("POT_EMPTY_SPACE_SHOWN", POTENTIAL, 7, "Los espacios vacíos muestran un uso posible",
       _c_empty_shown),
    _C("POT_PLAN_DEMONSTRATED", POTENTIAL, 5, "El plano se usa para demostrar cabida",
       _c_plan_shown),
    _C("POT_HAS_VISUALIZATION", POTENTIAL, 3, "El aviso muestra lo que el inmueble podría ser",
       _c_conceptual),
]

#: Qué intervención corresponde cuando un criterio queda corto. `None` es una respuesta válida y
#: frecuente: que falte el precio es un hallazgo real y no hay nada que generar, lo arregla quien
#: publica. Inventarle una intervención a cada carencia sería convertir el diagnóstico en catálogo.
INTERVENTION_BY_CRITERION = {
    "COVER_EXISTS": iv.COVER_SELECTION,
    "COVER_IS_BEST_AVAILABLE": iv.COVER_SELECTION,
    "COVER_BRIGHTNESS": iv.PHOTO_ENHANCE,
    "COVER_SHARPNESS": iv.PHOTO_ENHANCE,
    "COVER_RESOLUTION": None,
    "COVER_FRAMING": iv.PHOTO_ENHANCE,
    "SET_PHOTO_COUNT": None,
    "SET_NO_DUPLICATES": iv.COVER_SELECTION,
    "SET_NO_DARK": iv.PHOTO_ENHANCE,
    "SET_NO_BLURRY": iv.PHOTO_ENHANCE,
    "SET_CONSISTENT": None,
    "POT_PLAN_DEMONSTRATED": iv.SPATIAL_LAYOUT,
    "POT_HAS_VISUALIZATION": None,
}


def _intervention_for(code: str, ctx: Dict) -> Optional[str]:
    """La única regla que depende del contexto: un espacio vacío se resuelve amoblándolo si es
    vivienda, y mostrando para qué sirve si es comercial. Son dos conversaciones distintas."""
    if code == "POT_EMPTY_SPACE_SHOWN":
        return (iv.SPACE_REIMAGINATION
                if ctx["listing"]["property_type"] in listings.COMMERCIAL else iv.VIRTUAL_STAGE)
    return INTERVENTION_BY_CRITERION.get(code)


# =================================================================================================
# análisis
# =================================================================================================
def measure_media(listing_id: str) -> int:
    """Mide cada foto una vez y guarda el resultado con ella. Las mediciones viven con el medio y
    no se recalculan al vuelo: el informe tiene que poder mostrar de dónde salió cada punto aunque
    el analizador cambie después."""
    n = 0
    for m in listings.media_of(listing_id, listings.PHOTO):
        if m["analysis_obj"].get("ok") and m["analysis_obj"].get("version") == \
                vision.ANALYZER_VISION_VERSION:
            continue
        listings.save_analysis(m["media_id"], vision.measure(listings.media_path(m)))
        n += 1
    return n


def _context(listing_id: str) -> Dict:
    l = listings.require(listing_id)
    fotos = listings.media_of(listing_id, listings.PHOTO)
    portada = next((p for p in fotos if p["media_id"] == l["cover_media_id"]), None)
    if portada is None and fotos:
        portada = fotos[0]                                     # la primera es la portada de facto
    return {"listing": l, "photos": fotos, "cover": portada,
            "conceptual": listings.media_of(listing_id, listings.CONCEPTUAL),
            "duplicates": vision.duplicate_groups(fotos),
            "plan": plans.state(listing_id)}


def analyze(listing_id: str) -> Dict:
    """Calcula el informe completo. No escribe: `run` es el que persiste."""
    measure_media(listing_id)
    ctx = _context(listing_id)
    por_dim: Dict[str, Dict] = {}
    for dim, peso in DIMENSIONS.items():
        crits = [c for c in CRITERIA if c.dimension == dim]
        evaluados = []
        for c in crits:
            r = c.fn(ctx)
            evaluados.append({"code": c.code, "label": c.label, "weight": c.weight, **r})
        aplican = [e for e in evaluados if e["applies"]]
        peso_aplicable = sum(e["weight"] for e in aplican)
        if peso_aplicable <= 0:
            por_dim[dim] = {"label": DIMENSION_LABEL[dim], "weight": peso, "score": 0.0,
                            "max": peso, "criteria": evaluados, "applicable_weight": 0,
                            "note": "no hay nada medible en esta dimensión todavía"}
            continue
        # el peso de lo que NO aplica se reparte entre lo que sí: un criterio inaplicable no puede
        # restar puntos, porque no es una carencia del aviso.
        logrado = sum(e["weight"] * e["value"] for e in aplican) / peso_aplicable
        peso_total = sum(c.weight for c in crits)
        for e in evaluados:
            e["points"] = (round(peso * e["weight"] / peso_aplicable * e["value"], 2)
                           if e["applies"] else None)
            e["max_points"] = (round(peso * e["weight"] / peso_aplicable, 2)
                               if e["applies"] else None)
            # Para ATRIBUIR —cuánto le falta a este criterio— se usa su parte INTRÍNSECA, la que
            # tendría si todos aplicaran, no la redistribuida. Si no: un aviso sin fotos deja
            # aplicable un solo criterio de la dimensión, ese criterio absorbe los 30 puntos
            # enteros, y el hallazgo prometería recuperar 30 subiendo fotos. Es falso: al subirlas
            # los demás criterios vuelven a aplicar y se reparten. La parte intrínseca no se mueve
            # cuando cambia qué aplica, que es lo que hace comparables los hallazgos.
            e["intrinsic_points"] = round(peso * e["weight"] / peso_total, 2)
        por_dim[dim] = {"label": DIMENSION_LABEL[dim], "weight": peso,
                        "score": round(peso * logrado, 1), "max": peso,
                        "applicable_weight": peso_aplicable, "criteria": evaluados}
    total = round(sum(d["score"] for d in por_dim.values()))
    hallazgos = _findings(por_dim, ctx)
    resolubles = [f for f in hallazgos if f["kind"] == RESOLVABLE]
    recomendaciones = [f for f in hallazgos if f["kind"] == RECOMMENDATION]
    return {"listing_id": listing_id, "score": int(total), "max_score": sum(DIMENSIONS.values()),
            "dimensions": por_dim, "findings": hallazgos,
            "resolvable": resolubles, "recommendations": recomendaciones,
            # La oportunidad PRINCIPAL es la mayor que podamos resolver nosotros. Si la mayor
            # carencia del aviso es que no dice el precio, eso no es nuestra oportunidad: es su
            # tarea. Encabezar con ella convertiría el informe en una lista de reproches.
            "primary": (resolubles or hallazgos or [None])[0],
            "capabilities": _capabilities(ctx),
            "analyzer_version": ANALYZER_VERSION,
            "context": {"photos": len(ctx["photos"]), "conceptual": len(ctx["conceptual"]),
                        "plan": ctx["plan"]["status"]}}


#: Por debajo de esto, un criterio cuenta como carencia que vale la pena contar.
FINDING_THRESHOLD = 0.85


def _findings(por_dim: Dict, ctx: Dict) -> List[Dict]:
    """Un hallazgo por criterio que queda corto, ordenado por **cuántos puntos deja sobre la
    mesa**. Ese orden no es una opinión: es la misma aritmética del score leída al revés."""
    out = []
    for dim, d in por_dim.items():
        for e in d["criteria"]:
            if not e["applies"] or e["value"] >= FINDING_THRESHOLD:
                continue
            perdidos = round(e["intrinsic_points"] * (1.0 - e["value"]), 2)
            if perdidos <= 0.05:
                continue
            code = e["code"]
            inter = _intervention_for(code, ctx)
            if inter and not iv.auto_recommendable(inter):
                inter = None
            # E17.1 §2/§3 — dos clases de oportunidad, y la diferencia no es de tono: una la
            # resolvemos nosotros y la otra la resuelve quien publica. Una intervención que no
            # está escrita (`NOT_BUILT`) no convierte un hallazgo en oferta: pasa a recomendación,
            # que es lo que honestamente es mientras nadie la implemente.
            resoluble = iv.resolvable(inter)
            out.append({
                "dimension": dim, "dimension_label": DIMENSION_LABEL[dim],
                "code": code, "headline": HEADLINES.get(code, e["label"]),
                "explanation": _explain(code, e, ctx),
                "level": HIGH if perdidos >= 5 else (MEDIUM if perdidos >= 2 else LOW),
                "evidence": e["measured"], "criterion_label": e["label"],
                "intervention": inter if resoluble else None,
                "intervention_label": iv.label(inter) if resoluble else None,
                "kind": RESOLVABLE if resoluble else RECOMMENDATION,
                "support": iv.support(inter) if resoluble else None,
                "support_label": iv.support_label(inter) if resoluble else None,
                "deliverable_today": iv.deliverable_today(inter) if resoluble else False,
                # HEURÍSTICO: los puntos que este criterio no está sumando hoy. No es una
                # predicción de nada; es cuánto le falta a este criterio para estar completo.
                "score_delta": perdidos,
            })
    # Primero lo que podemos resolver nosotros, y dentro de cada grupo por puntos. El orden del
    # informe es una decisión de producto, no un artefacto del cálculo: quien lo lee tiene que ver
    # antes lo que puede encargarnos que lo que tiene que arreglar solo.
    out.sort(key=lambda f: (0 if f["kind"] == RESOLVABLE else 1, -f["score_delta"], f["code"]))
    for i, f in enumerate(out):
        f["rank"] = i
    return out


HEADLINES = {
    "COVER_EXISTS": "La publicación no tiene una portada elegida",
    "COVER_IS_BEST_AVAILABLE": "La portada no es la mejor foto del aviso",
    "COVER_BRIGHTNESS": "La portada se ve oscura",
    "COVER_SHARPNESS": "La portada se ve blanda",
    "COVER_RESOLUTION": "La portada tiene poca resolución",
    "COVER_FRAMING": "Las verticales de la portada están caídas",
    "SET_PHOTO_COUNT": "Faltan fotos para entender la propiedad",
    "SET_NO_DUPLICATES": "Hay fotos repetidas",
    "SET_NO_DARK": "Hay fotos oscuras en el set",
    "SET_NO_BLURRY": "Hay fotos movidas o blandas",
    "SET_CONSISTENT": "Las fotos mezclan formatos",
    "INFO_AREA": "No se declaran los metros cuadrados",
    "INFO_PRICE": "No se declara el precio",
    "INFO_DESCRIPTION": "La descripción dice muy poco",
    "INFO_TITLE": "El título no dice qué se ofrece",
    "INFO_BEDROOMS": "No se declaran los dormitorios",
    "INFO_BATHROOMS": "No se declaran los baños",
    "INFO_PARKING": "No se declaran los estacionamientos",
    "POT_EMPTY_SPACE_SHOWN": "Hay espacios vacíos que cuesta imaginar en uso",
    "POT_PLAN_DEMONSTRATED": "Hay un plano y no se está usando para demostrar cabida",
    "POT_HAS_VISUALIZATION": "El aviso no muestra lo que el inmueble podría llegar a ser",
}


def _explain(code: str, e: Dict, ctx: Dict) -> str:
    """La explicación lleva la MEDICIÓN adentro. Un hallazgo que no dice de dónde salió es una
    opinión, y una opinión no se puede discutir ni corregir."""
    m = e["measured"]
    if code == "COVER_IS_BEST_AVAILABLE":
        return (f"La portada actual tiene calidad técnica {m.get('cover_quality')} y hay otra foto "
                f"del mismo aviso con {m.get('best_quality')}. Cambiar la portada no cuesta "
                f"producir nada: es elegir distinto.")
    if code == "COVER_BRIGHTNESS":
        return (f"La luminancia media de la portada es {m.get('brightness')} y la banda legible "
                f"es {m.get('band')}. Una portada fuera de esa banda se lee apagada en la grilla "
                f"del portal, que es donde se decide si alguien entra.")
    if code == "SET_NO_DUPLICATES":
        return (f"{m.get('redundant_photos')} de {m.get('total')} fotos son la misma imagen que "
                f"otra. Ocupan lugar en la galería sin agregar información.")
    if code == "SET_NO_DARK":
        return (f"{len(m.get('dark') or [])} de {m.get('total')} fotos están por debajo del piso "
                f"de luminancia ({m.get('threshold')}).")
    if code == "SET_NO_BLURRY":
        return (f"{len(m.get('blurry') or [])} de {m.get('total')} fotos no llegan al mínimo de "
                f"nitidez ({m.get('threshold')}).")
    if code == "POT_EMPTY_SPACE_SHOWN":
        n = len(m.get("empty_like") or [])
        return (f"{n} de {m.get('total')} fotos tienen muy poco detalle en la mitad inferior del "
                f"cuadro, que es lo que suele pasar cuando el espacio está vacío. El aviso no "
                f"incluye ninguna visualización que muestre un uso posible, así que quien mira "
                f"tiene que imaginarlo solo.")
    if code == "POT_PLAN_DEMONSTRATED":
        return (f"Detectamos un plano ({m.get('plan_label')}). Con él se puede demostrar cuántos "
                f"puestos y recintos caben de verdad en este espacio, que es justo lo que un "
                f"interesado no puede deducir de las fotos.")
    if code == "INFO_DESCRIPTION":
        return (f"La descripción tiene {m.get('chars')} caracteres. Con menos de "
                f"{m.get('min')} es difícil que transmita algo que las fotos no muestren.")
    if code.startswith("INFO_"):
        return ("El aviso no lo declara. Quien mira tiene que preguntarlo o suponerlo, y la "
                "mayoría no hace ninguna de las dos cosas.")
    if code == "POT_HAS_VISUALIZATION":
        return ("El aviso muestra el inmueble como está y nada más. No hay ninguna imagen que "
                "ayude a ver en qué podría convertirse.")
    if code == "SET_PHOTO_COUNT":
        return (f"Hay {m.get('photos')} foto(s). Con menos de {m.get('min')} quedan ambientes "
                f"sin mostrar, y lo que no se muestra no se imagina.")
    if code == "SET_CONSISTENT":
        return (f"Las fotos mezclan formatos ({m.get('orientations')}). En la galería del portal "
                f"eso se ve como un set armado a las apuradas.")
    if code == "COVER_SHARPNESS":
        return (f"La nitidez de la portada es {m.get('sharpness')} y el mínimo para que se vea "
                f"definida es {m.get('min')}.")
    if code == "COVER_RESOLUTION":
        return (f"El lado menor de la portada es {m.get('short_side')} px; por debajo de "
                f"{m.get('min')} se ve blanda apenas el portal la amplía.")
    if code == "COVER_FRAMING":
        return (f"Las líneas verticales de la portada están {m.get('vertical_tilt_deg')}° fuera "
                f"de la vertical. Se corrige sin cambiar nada de lo que se ve.")
    if code == "COVER_EXISTS":
        return ("Nadie eligió la portada, así que se está usando la primera foto que se subió. "
                "Es la decisión más barata de todo el aviso y está sin tomar.")
    return e.get("why") or e["label"]


def _capabilities(ctx: Dict) -> Dict:
    """Qué sabemos hacer con ESTE material. No es el catálogo completo: es lo que el aviso
    habilita, que es distinto y es lo único que tiene sentido ofrecer."""
    l = ctx["listing"]
    tiene_fotos = bool(ctx["photos"])
    cap = {
        iv.COVER_SELECTION: len(ctx["photos"]) >= 2,
        iv.PHOTO_ENHANCE: tiene_fotos,
        iv.VIRTUAL_STAGE: tiene_fotos and l["property_type"] not in listings.COMMERCIAL,
        iv.SPACE_REIMAGINATION: tiene_fotos and l["property_type"] in listings.COMMERCIAL,
        iv.RENOVATION_VISUALIZATION: tiene_fotos,
        iv.SPATIAL_LAYOUT: ctx["plan"]["status"] not in (plans.NO_PLAN, plans.LOOKS_UNREADABLE,
                                                         plans.NOT_USABLE),
    }
    return {k: bool(v) for k, v in cap.items()}


# =================================================================================================
# persistencia
# =================================================================================================
def run(listing_id: str) -> Dict:
    """Analiza y guarda. Cada corrida es una fila nueva: un informe es una foto de un momento, y
    pisarlo impediría ver si el aviso mejoró."""
    from ... import engine                                     # noqa: PLC0415
    r = analyze(listing_id)
    rid = "pr_" + uuid.uuid4().hex[:12]
    store.ex("INSERT INTO potential_reports(report_id, listing_id, score, max_score, dimensions, "
             "primary_opportunity, capabilities, analyzer_version, engine_version, created_at) "
             "VALUES (?,?,?,?,?,?,?,?,?,?)",
             (rid, listing_id, r["score"], r["max_score"],
              json.dumps(r["dimensions"], ensure_ascii=False),
              json.dumps(r["primary"], ensure_ascii=False) if r["primary"] else None,
              json.dumps(r["capabilities"], ensure_ascii=False), ANALYZER_VERSION,
              engine.engine_commit(), store.now()))
    for f in r["findings"]:
        store.ex("INSERT INTO potential_findings(finding_id, report_id, listing_id, dimension, "
                 "code, level, headline, explanation, evidence, intervention, score_delta, "
                 "media_id, rank, kind, support, created_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("pf_" + uuid.uuid4().hex[:12], rid, listing_id, f["dimension"], f["code"],
                  f["level"], f["headline"], f["explanation"],
                  json.dumps(f["evidence"], ensure_ascii=False), f["intervention"],
                  f["score_delta"], f["evidence"].get("best_media_id"), f["rank"],
                  f["kind"], f["support"], store.now()))
    r["report_id"] = rid
    return r


#: Cuántas oportunidades se muestran. El encargo pide 3–5: un informe de cuarenta hallazgos no se
#: lee, y el que lo recibe no sabe por dónde empezar.
TOP_FINDINGS = 5


def latest(listing_id: str) -> Optional[Dict]:
    r = store.q1("SELECT * FROM potential_reports WHERE listing_id=? ORDER BY created_at DESC, "
                 "rowid DESC LIMIT 1", (listing_id,))
    if not r:
        return None
    d = dict(r)
    d["dimensions_obj"] = store.js(d["dimensions"], {}) or {}
    d["primary_obj"] = store.js(d["primary_opportunity"], None)
    d["capabilities_obj"] = store.js(d["capabilities"], {}) or {}
    d["findings"] = findings_of(d["report_id"])
    d["top_findings"] = d["findings"][:TOP_FINDINGS]
    d["resolvable"] = [f for f in d["findings"] if f["kind"] == RESOLVABLE][:TOP_FINDINGS]
    d["recommendations"] = [f for f in d["findings"] if f["kind"] == RECOMMENDATION][:TOP_FINDINGS]
    return d


def findings_of(report_id: str) -> List[Dict]:
    out = []
    for r in store.q("SELECT * FROM potential_findings WHERE report_id=? ORDER BY rank",
                     (report_id,)):
        d = dict(r)
        d["evidence_obj"] = store.js(d["evidence"], {}) or {}
        d["intervention_label"] = iv.label(d["intervention"]) if d["intervention"] else None
        d["support_label"] = iv.SUPPORT_LABEL.get(d["support"]) if d["support"] else None
        d["deliverable_today"] = d["support"] == iv.AVAILABLE
        out.append(d)
    return out


def history(listing_id: str, limit: int = 10) -> List[Dict]:
    return [dict(r) for r in store.q(
        "SELECT report_id, score, max_score, created_at FROM potential_reports WHERE listing_id=? "
        "ORDER BY created_at DESC LIMIT ?", (listing_id, limit))]
