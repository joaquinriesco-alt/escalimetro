"""E17.2 §2/§3/§4 — SACARLE A UNA PÁGINA LO QUE REALMENTE DICE, POR CAPAS.

=================================================================================================
El orden importa, y el orden es de menor a mayor fragilidad
=================================================================================================
    A. JSON-LD (`schema.org`)      lo publica el portal PARA ser leído. Si cambia el diseño, sigue
                                   ahí. Es la capa más estable que existe.
    B. Open Graph y `<meta>`       también existen para ser leídos, por buscadores y por redes.
    C. Estado embebido             el JSON que el portal usa para pintar su propia página. Cambia
                                   más seguido que lo anterior, pero sigue siendo estructura.
    D. Adaptador por dominio       sólo cuando la evidencia demuestre que hace falta.
    E. Navegador                   último recurso, no construido acá (ver el final del archivo).

Lo que NO se hace primero —ni segundo— es leer el DOM con selectores de clases. Un selector visual
se rompe la semana que el portal cambia una hoja de estilos, y cuando se rompe se lleva puesto el
producto entero. Medido sobre una publicación real de Portal Inmobiliario: JSON-LD da nombre,
precio y moneda; el estado embebido da doce atributos —superficie, estacionamientos, baños,
bodegas, orientación, antigüedad— y la galería completa. Con eso alcanza sin tocar una sola clase
de CSS.

=================================================================================================
Procedencia por campo
=================================================================================================
Cada valor viaja con de dónde salió y con cuánta confianza (§4). No es burocracia: un precio leído
de un `Offer` de schema.org y un número sacado a la fuerza del título no valen lo mismo, y cuando
alguien pregunte «¿de dónde sacaron que son 543 m²?» la respuesta tiene que estar en el dato.

Lo que no se pueda leer queda en `None`. **Nunca se inventa un valor ausente**: la dimensión de
INFORMACIÓN del informe mide justamente qué falta, y rellenarla con suposiciones la haría mentir.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

#: De dónde salió un campo, de más a menos confiable.
JSON_LD = "JSON_LD"
OPEN_GRAPH = "OPEN_GRAPH"
META = "META"
EMBEDDED_STATE = "EMBEDDED_STATE"
DOM = "DOM"
MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
SOURCE_CONFIDENCE = {JSON_LD: 0.95, OPEN_GRAPH: 0.85, META: 0.8, EMBEDDED_STATE: 0.75,
                     DOM: 0.5, MANUAL_OVERRIDE: 1.0}
#: Prioridad al resolver el mismo campo desde dos capas. Una persona gana siempre.
PRIORITY = [MANUAL_OVERRIDE, JSON_LD, OPEN_GRAPH, META, EMBEDDED_STATE, DOM]


def field(value, source: str, note: str = "") -> Dict:
    return {"value": value, "source": source,
            "confidence": SOURCE_CONFIDENCE.get(source, 0.5), "note": note}


def _merge(dest: Dict[str, Dict], nuevos: Dict[str, Dict]) -> None:
    """Un campo sólo se pisa si viene de una capa más confiable. Sin esto, el orden en que corren
    los extractores decidiría el valor final, que es la peor forma de decidirlo."""
    for k, v in nuevos.items():
        if v is None or v.get("value") in (None, ""):
            continue
        prev = dest.get(k)
        if prev is None or PRIORITY.index(v["source"]) < PRIORITY.index(prev["source"]):
            dest[k] = v


# =================================================================================================
# números y unidades, en español de Chile
# =================================================================================================
def parse_number(texto) -> Optional[float]:
    """«1.052 m²» → 1052.0 · «0,63» → 0.63 · «UF 662» → 662.0

    El punto es separador de miles y la coma es decimal. Invertirlos convertiría 1.052 m² en un
    metro cuadrado, que es exactamente el tipo de error que nadie nota hasta que sale publicado."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    m = re.search(r"-?\d[\d.]*(?:,\d+)?", str(texto).replace(" ", " "))
    if not m:
        return None
    crudo = m.group().replace(".", "").replace(",", ".")
    try:
        return float(crudo)
    except ValueError:
        return None


def parse_int(texto) -> Optional[int]:
    v = parse_number(texto)
    return None if v is None else int(v)


#: Cómo se llama cada cosa en los portales de Chile → nuestro campo. Es un diccionario de
#: etiquetas, no de selectores: sobrevive a cualquier rediseño y sirve para cualquier portal que
#: use las mismas palabras, que en la práctica son todas.
ATTRIBUTE_MAP = {
    "superficie útil": ("usable_area_m2", parse_number),
    "superficie utilizable": ("usable_area_m2", parse_number),
    "superficie total": ("total_area_m2", parse_number),
    "superficie construida": ("total_area_m2", parse_number),
    "superficie terreno": ("land_area_m2", parse_number),
    "dormitorios": ("bedrooms", parse_int),
    "habitaciones": ("bedrooms", parse_int),
    "ambientes": ("rooms", parse_int),
    "baños": ("bathrooms", parse_int),
    "estacionamientos": ("parking", parse_int),
    "bodegas": ("storage", parse_int),
    "orientación": ("orientation", lambda v: str(v).strip()),
    "antigüedad": ("age_years", parse_int),
    "gastos comunes": ("common_expenses", parse_number),
    "número de piso de la unidad": ("floor", parse_int),
    "piso": ("floor", parse_int),
    "número de privados": ("private_offices", parse_int),
    "cantidad de pisos": ("building_floors", parse_int),
}

TYPE_HINTS = [
    (("oficina",), "OFFICE"), (("local", "comercial"), "RETAIL"),
    (("bodega", "galpón", "galpon"), "WAREHOUSE"), (("departamento", "depto"), "APARTMENT"),
    (("casa",), "HOUSE"), (("terreno", "sitio", "parcela"), "LAND"),
]


def guess_property_type(*textos) -> Optional[str]:
    """Del texto del aviso, no de una API. Es una pista y por eso su procedencia es la del texto
    del que salió: si el título dice «oficina», el aviso es de una oficina."""
    junto = " ".join(t for t in textos if t).lower()
    for claves, tipo in TYPE_HINTS:
        if any(k in junto for k in claves):
            return tipo
    return None


def guess_operation(*textos) -> Optional[str]:
    junto = " ".join(t for t in textos if t).lower()
    if "arriendo" in junto or "alquiler" in junto or "/rent" in junto:
        return "RENT"
    if "venta" in junto or "/sale" in junto:
        return "SALE"
    return None


# =================================================================================================
# A — JSON-LD
# =================================================================================================
def json_ld_blocks(html: str) -> List[Dict]:
    out = []
    for b in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                        html, re.S | re.I):
        try:
            d = json.loads(b.strip())
        except (ValueError, TypeError):
            continue
        out.extend(d if isinstance(d, list) else [d])
    return out


def from_json_ld(html: str) -> Tuple[Dict[str, Dict], List[str]]:
    campos: Dict[str, Dict] = {}
    imagenes: List[str] = []
    for d in json_ld_blocks(html):
        if not isinstance(d, dict):
            continue
        tipo = str(d.get("@type") or "")
        if tipo in ("Product", "Residence", "Apartment", "House", "Offer", "RealEstateListing",
                    "SingleFamilyResidence"):
            if d.get("name"):
                campos["title"] = field(str(d["name"])[:200], JSON_LD)
            if d.get("description"):
                campos["description"] = field(str(d["description"])[:4000], JSON_LD)
            if d.get("sku") or d.get("productID"):
                campos["publication_id"] = field(str(d.get("sku") or d["productID"]), JSON_LD)
            img = d.get("image")
            imagenes += ([img] if isinstance(img, str) else
                         [i for i in (img or []) if isinstance(i, str)])
            ofertas = d.get("offers")
            ofertas = ofertas if isinstance(ofertas, list) else ([ofertas] if ofertas else [])
            for o in ofertas:
                if not isinstance(o, dict):
                    continue
                if o.get("price") is not None:
                    campos["price"] = field(parse_number(o["price"]), JSON_LD)
                if o.get("priceCurrency"):
                    campos["currency"] = field(str(o["priceCurrency"]), JSON_LD)
            dire = d.get("address")
            if isinstance(dire, dict):
                partes = [dire.get(k) for k in ("streetAddress", "addressLocality",
                                                "addressRegion") if dire.get(k)]
                if partes:
                    campos["location"] = field(", ".join(map(str, partes))[:200], JSON_LD)
            elif isinstance(dire, str):
                campos["location"] = field(dire[:200], JSON_LD)
            for llave, campo, fn in (("numberOfRooms", "rooms", parse_int),
                                     ("numberOfBedrooms", "bedrooms", parse_int),
                                     ("numberOfBathroomsTotal", "bathrooms", parse_int)):
                if d.get(llave) is not None:
                    campos[campo] = field(fn(d[llave]), JSON_LD)
            sup = d.get("floorSize")
            if isinstance(sup, dict) and sup.get("value") is not None:
                campos["usable_area_m2"] = field(parse_number(sup["value"]), JSON_LD)
    return campos, imagenes


# =================================================================================================
# B — Open Graph y <meta>
# =================================================================================================
def from_meta(html: str) -> Tuple[Dict[str, Dict], List[str]]:
    campos: Dict[str, Dict] = {}
    og = {}
    for prop, cont in re.findall(
            r'<meta[^>]+property=["\']og:([a-z:]+)["\'][^>]+content=["\']([^"\']{1,1000})["\']',
            html, re.I):
        og.setdefault(prop, cont)
    if og.get("title"):
        campos["title"] = field(_limpiar(og["title"])[:200], OPEN_GRAPH)
    if og.get("description"):
        campos["description"] = field(_limpiar(og["description"])[:4000], OPEN_GRAPH)
    imagenes = re.findall(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']{1,600})["\']',
        html, re.I) or ([og["image"]] if og.get("image") else [])
    if not campos.get("description"):
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{1,1000})["\']',
                      html, re.I)
        if m:
            campos["description"] = field(_limpiar(m.group(1))[:4000], META)
    if not campos.get("title"):
        m = re.search(r"<title[^>]*>(.{1,300}?)</title>", html, re.I | re.S)
        if m:
            campos["title"] = field(_limpiar(m.group(1))[:200], META)
    return campos, imagenes


def _limpiar(s: str) -> str:
    import html as _h                                          # noqa: PLC0415
    return re.sub(r"\s+", " ", _h.unescape(s)).strip()


# =================================================================================================
# C — estado embebido
# =================================================================================================
#: Pares `{"id":"Superficie total","text":"1.052 m²"}` que los portales serializan para pintar su
#: propia ficha. No es un selector: es el JSON del portal, y sobrevive a cualquier rediseño.
_PAIR = re.compile(r'\{"id":"([^"]{2,60})","text":"([^"]{1,80})"\}')


def from_embedded(html: str) -> Dict[str, Dict]:
    campos: Dict[str, Dict] = {}
    vistos = set()
    atributos: Dict[str, str] = {}
    for etiqueta, valor in _PAIR.findall(html):
        # La ETIQUETA también viene escapada: un portal que serializa «Baños» como «Ba\u00f1os»
        # perdería el atributo entero si sólo decodificáramos el valor.
        clave = _decodificar(etiqueta).lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        atributos[clave] = _decodificar(valor)
        par = ATTRIBUTE_MAP.get(clave)
        if par:
            campo, fn = par
            v = fn(atributos[clave])
            if v is not None:
                campos[campo] = field(v, EMBEDDED_STATE, f"«{etiqueta}» = {atributos[clave]}")
    if atributos:
        campos["_attributes"] = field(atributos, EMBEDDED_STATE)
    return campos


def _decodificar(s: str) -> str:
    try:
        return _limpiar(json.loads(f'"{s}"'))
    except ValueError:
        return _limpiar(s)


def embedded_json_blobs(html: str) -> List[Dict]:
    """`__NEXT_DATA__`, `__PRELOADED_STATE__` y compañía. Se devuelven crudos para que un
    adaptador por dominio pueda mirarlos sin que esta capa tenga que entenderlos."""
    out = []
    for patron in (r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                   r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>',
                   r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>'):
        for b in re.findall(patron, html, re.S):
            try:
                out.append(json.loads(b))
            except (ValueError, TypeError):
                continue
    return out


# =================================================================================================
# imágenes de la galería
# =================================================================================================
#: Lo que NO es una foto del inmueble. Se filtra por lo que dice la propia URL, que es lo único
#: que se sabe antes de bajarla; lo que se cuele se descarta después al clasificar (§6).
_NOT_GALLERY = re.compile(
    r"(sprite|logo|icon|favicon|avatar|placeholder|banner|pixel|tracking|badge|"
    r"whatsapp|facebook|instagram|twitter|linkedin|googleapis|gstatic|"
    r"maps\.google|staticmap|/ui/|/assets/ui|vis-accounts|/storage/|/profile)", re.I)
_IMG_EXT = re.compile(r"\.(?:jpe?g|png|webp)(?:[?#]|$)", re.I)
#: §17 — tope de imágenes por aviso. Una galería real no tiene cien fotos; cien URLs significan
#: que algo se coló, y bajarlas todas sería regalarle a una página el ancho de banda del servidor.
MAX_GALLERY = 40


def gallery_urls(html: str, base_url: str, extra: Optional[List[str]] = None) -> List[str]:
    """Las URLs de la galería, de mayor resolución cuando el portal ofrece variantes.

    Se recogen de `<img src>`, de los `srcset` y de cualquier URL de imagen que aparezca en el
    JSON embebido, porque las galerías modernas cargan por JavaScript y en el HTML plano sólo
    está la primera. Después se deduplica por la identidad de la foto —no por la URL—, que es lo
    que permite quedarse con la variante grande y descartar su miniatura."""
    crudas: List[str] = list(extra or [])
    crudas += re.findall(r'<img[^>]+src=["\']([^"\']{6,600})["\']', html, re.I)
    for s in re.findall(r'<img[^>]+srcset=["\']([^"\']{6,2000})["\']', html, re.I):
        crudas += [p.strip().split(" ")[0] for p in s.split(",") if p.strip()]
    crudas += re.findall(r'https?://[^"\'\\\s]{10,300}?\.(?:jpe?g|png|webp)', html, re.I)
    vistas, out = set(), []
    for u in crudas:
        u = _limpiar(u).replace("\\u002F", "/").replace("\\/", "/")
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = urljoin(base_url, u)
        if not u.lower().startswith(("http://", "https://")) or not _IMG_EXT.search(u):
            continue
        if _NOT_GALLERY.search(u):
            continue
        if u in vistas:
            continue
        vistas.add(u)
        out.append(u)
    return _best_variants(out)


#: Marcas de variante de un mismo archivo en los CDN de imágenes. El identificador de la foto es
#: lo que queda al sacarlas; quedarse con la variante más grande es preferir `_2X_` sobre `_V_`.
_VARIANT = re.compile(r"(_(?:2X|3X|V|W|O|F|S|I|N|Q|NQ|NQ_NP|R)_?)", re.I)
_SIZE_HINT = re.compile(r"(\d{2,4})x(\d{2,4})")


_ID_DIGITS = re.compile(r"\d{6,}")


def _identity(url: str) -> str:
    """La identidad de la FOTO, ignorando la variante.

    Los CDN de imágenes nombran la misma foto con prefijos distintos según el tamaño
    (`D_NQ_NP_636450-MLC115969363171_082026-O-…` y `D_Q_NP_2X_636450-MLC115969363171_082026-R-…`
    son la misma). Lo que NO cambia entre variantes son los números largos: el id del archivo y el
    del aviso. Se usa eso como identidad en vez del nombre completo, porque quitar prefijos
    conocidos sería una lista que envejece con cada CDN nuevo."""
    nombre = url.split("/")[-1].split("?")[0]
    digitos = _ID_DIGITS.findall(nombre)
    if digitos:
        return ",".join(digitos)
    return re.sub(r"[-_]{2,}", "_", _VARIANT.sub("_", _SIZE_HINT.sub("", nombre)).lower())


def _score(url: str) -> int:
    """Cuánto promete esta variante. Sirve para elegir la mayor entre las de una misma foto."""
    s = 0
    if re.search(r"_2X_|_3X_|-O-|_O\.|/O/", url, re.I):
        s += 100
    m = _SIZE_HINT.search(url)
    if m:
        s += min(1000, int(m.group(1)) * int(m.group(2)) // 1000)
    if re.search(r"thumb|small|mini|_S_|_I_|_V_", url, re.I):
        s -= 80
    return s


def _best_variants(urls: List[str]) -> List[str]:
    mejor: Dict[str, str] = {}
    orden: List[str] = []
    for u in urls:
        k = _identity(u)
        if k not in mejor:
            mejor[k] = u
            orden.append(k)
        elif _score(u) > _score(mejor[k]):
            mejor[k] = u
    return [mejor[k] for k in orden][:MAX_GALLERY]


# =================================================================================================
# el extractor completo
# =================================================================================================
def extract(html: str, url: str) -> Dict:
    """Todas las capas, en orden, con procedencia por campo."""
    campos: Dict[str, Dict] = {}
    ld, img_ld = from_json_ld(html)
    meta, img_og = from_meta(html)
    emb = from_embedded(html)
    _merge(campos, ld)
    _merge(campos, meta)
    _merge(campos, emb)
    campos["source_url"] = field(url, JSON_LD if ld else META)

    titulo = (campos.get("title") or {}).get("value") or ""
    desc = (campos.get("description") or {}).get("value") or ""
    # Para deducir tipo y operación se mira TODO el texto de cabecera, no sólo el campo que ganó
    # la fusión. El `<title>` de la página suele decir «arriendo» aunque el nombre del JSON-LD
    # —que es el que gana por ser más confiable— no lo diga.
    m = re.search(r"<title[^>]*>(.{1,300}?)</title>", html, re.I | re.S)
    crudo = " ".join(filter(None, [titulo, desc, _limpiar(m.group(1)) if m else "",
                                   " ".join(re.findall(
                                       r'<meta[^>]+property=["\']og:(?:title|type)["\']'
                                       r'[^>]+content=["\']([^"\']{1,200})["\']', html, re.I))]))
    tipo = guess_property_type(crudo, url)
    if tipo:
        campos["property_type"] = field(tipo, META, "deducido del texto del aviso")
    op = guess_operation(crudo, url)
    if op:
        campos["operation"] = field(op, META, "deducido del texto del aviso")
    # la superficie que usa el informe: la útil si está, si no la total
    for destino, origen in (("area_m2", "usable_area_m2"), ("area_m2", "total_area_m2")):
        if destino not in campos and origen in campos:
            campos[destino] = dict(campos[origen], note=f"de «{origen}»")

    imagenes = gallery_urls(html, url, extra=img_ld + img_og)
    return {"fields": campos, "images": imagenes,
            "layers": {"json_ld": len(json_ld_blocks(html)), "open_graph": bool(img_og or meta),
                       "embedded_blobs": len(embedded_json_blobs(html)),
                       "embedded_pairs": len((emb.get("_attributes") or {}).get("value") or {})},
            "domain": urlparse(url).netloc}


# =================================================================================================
# E — navegador: la capa que NO está construida
# =================================================================================================
#: §3.E la admite «sólo si HTTP/structured extraction no puede obtener contenido útil y el repo ya
#: puede soportarlo razonablemente». Sobre una publicación real de Portal Inmobiliario el HTTP
#: plano trajo JSON-LD, doce atributos embebidos y 58 imágenes de galería: la necesidad no está
#: demostrada, y meter un navegador headless en el servidor por si acaso es infraestructura grande
#: para un problema que hoy no existe. La interfaz queda declarada para que, si aparece un portal
#: que la necesite, se enchufe detrás de este nombre y no desparramada por el extractor.
BROWSER_FALLBACK_AVAILABLE = False
BROWSER_FALLBACK_NOTE = ("no construido: la extracción estructurada alcanzó en los portales "
                         "probados. Si un portal la necesita, se implementa detrás de esta "
                         "interfaz, sin login y sólo sobre páginas públicas.")


def browser_fetch(url: str) -> Dict:
    raise NotImplementedError(BROWSER_FALLBACK_NOTE)
