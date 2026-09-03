"""Ground truth manual del Caso 001 — Oficina 403.

Coordenadas leídas por un humano sobre crops ampliados ×4 con grilla de 10 px de original.png
(escalimetro annotate → outputs/original_grid.png sirve igual). Anotado DESPUÉS del pase
automático, pero leyendo la imagen, no el floorplate.json. Precisión de lectura: ±2 px.

Convención: perímetro = borde interior de la zona pintada de la unidad (la pintura de GPS
termina en la cara interior del muro/fachada). Core = bloque achurado central (ascensores,
escaleras, baños), sin los arcos del lobby superior (ambiguos a esta resolución).
Pilares = rectángulos huecos dentro o sobre el borde de la unidad. Accesos = símbolos de puerta
(arco) visibles en el borde núcleo/403.

Uso: python cases/001_gps_403/ground_truth/make_gt.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
from shapely.geometry import Polygon  # noqa: E402

from escalimetro.schemas.floorplate import (SCHEMA_VERSION, Column, Core, CoordinateSystem, Entrance,  # noqa: E402
                                             FacadeSegment, Floorplate, Meta, Perimeter, Provenance, Scale,
                                             SourceImage, Status)

M = Meta(1.0, Provenance.MANUAL.value, Status.CONFIRMED.value, "GT manual, lectura ±2 px")

RING = [(321, 238), (427, 238), (427, 331), (570, 331), (570, 289), (678, 289), (678, 376), (660, 376),
        (660, 402), (536, 402), (536, 399), (464, 399), (464, 404), (341, 404), (341, 379), (321, 379)]
KINDS = ["party_wall", "core_wall", "core_wall", "core_wall", "party_wall", "facade", "facade", "facade",
         "facade", "facade", "facade", "facade", "facade", "facade", "facade", "facade"]
CORE = [(430, 207), (566, 207), (566, 331), (430, 331)]
COLUMNS = [(345, 242), (344, 292), (415, 240), (415, 291), (340, 372), (414, 372),
           (582, 287), (652, 287), (582, 370), (655, 370)]
# E03: GT de accesos RE-ANOTADO tras inspección ×8 de los muros del núcleo (ver notes.md).
# El GT de E02 ((500,331) "arco en el eje central") era una lectura errónea: la línea inferior del
# núcleo es continua. Las puertas reales son huecos en los muros OESTE y ESTE del núcleo (con hoja
# dibujada), simétricas: no hay base gráfica para preferir una como principal.
ENTRANCES = [((567, 301), "main", "hueco en muro este del núcleo y=298–303 con hoja de puerta; simétrico con el oeste"),
             ((429, 302), "main", "hueco en muro oeste del núcleo y=298–307 con hoja de puerta; simétrico con el este")]
# GT de luz natural por lado del GT (índice de RING): montantes/ticks repetidos visibles en la banda exterior
GLAZING_OBSERVED = {5: True, 6: None, 7: None, 8: True, 9: None, 10: True, 11: None, 12: True, 13: None, 14: None, 15: True}
#   True = patrón de montantes visible (likely_glazing es lo máximo afirmable desde un JPG);
#   None = lado corto/escalón, no evaluable. Lados interiores (0–4): sin luz.


def main():
    ring = [tuple(map(float, p)) for p in RING]
    segs = [FacadeSegment(i, ring[i], ring[(i + 1) % len(ring)], KINDS[i], M) for i in range(len(ring))]
    fp = Floorplate(SCHEMA_VERSION, "001_gps_403", "Oficina 403", SourceImage("original.png", 800, 424), CoordinateSystem(),
                    Scale(None, "unknown", None, Meta(0, Provenance.UNKNOWN.value, Status.UNKNOWN.value,
                                                      "sin referencia independiente de escala en la imagen")),
                    Perimeter(ring, [], M),
                    core=[Core([tuple(map(float, p)) for p in CORE], "core", M)],
                    columns=[Column((float(x), float(y)), 9.0, "rect", M) for x, y in COLUMNS],
                    entrances=[Entrance((float(p[0]), float(p[1])), None, k, Meta(0.7 if k == "main" else 0.5, Provenance.MANUAL.value,
                                                                                  Status.CONFIRMED.value, n)) for p, k, n in ENTRANCES],
                    facade_segments=segs, area_m2=None, area_px2=Polygon(ring).area, area_meta=M,
                    published_area_m2=543.0, published_area_kind="unknown", target_localization="manual")
    from escalimetro.schemas.floorplate import DaylightSegment
    fp.daylight_segments = []
    for i in range(len(ring)):
        g = GLAZING_OBSERVED.get(i)
        if KINDS[i] != "facade":
            cls, conf = "opaque", 1.0
        elif g is True:
            cls, conf = "likely_glazing", 0.8
        else:
            cls, conf = "exterior_unknown", 0.5
        fp.daylight_segments.append(DaylightSegment(i, ring[i], ring[(i + 1) % len(ring)], cls, conf,
                                                    {"likely_glazing": 0.75, "exterior_unknown": 0.4, "opaque": 0.0}[cls],
                                                    ["GT manual: montantes visibles" if g else "GT manual"], "confirmed", "manual"))
    out = os.path.join(os.path.dirname(__file__), "floorplate_gt.json")
    fp.save(out)
    print("GT:", out, f"área={Polygon(ring).area:.0f} px², {len(ring)} vértices, {len(COLUMNS)} pilares")


if __name__ == "__main__":
    main()
