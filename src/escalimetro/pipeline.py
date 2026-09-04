"""Pipeline ETAPA 1 — Normalización.

imagen → hints (OCR/VLM/manual) → máscara (segmentación) → contorno → simplificación
→ escala (área publicada, inferida) → elementos (heurísticas + overrides) → Floorplate JSON → SVG → comparaciones.

Orden de precedencia para cada elemento: override manual > heurística CV > hint VLM/OCR > unknown.

target_localization:
  automatic — el seed vino de un hint (OCR/VLM), sin humano;
  assisted  — el seed / bbox vino de overrides.json;
  manual    — el perímetro completo vino de overrides.json.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from . import __version__
from .geometry import (GeometryExtractor, classify_facade_segments, detect_columns, scale_from_known_area,
                       scale_manual, scale_unknown, snap_point_to_ring)
from .geometry.elements import detect_core_enclosed, detect_hollow_columns
from .overrides import Overrides
from .renderer import grid_image, overlay_on_original, render_svg, side_by_side
from .renderer.side_by_side import comparison_three, geometry_only, contour_svg
from .schemas.floorplate import (SCHEMA_VERSION, Column, Core, CoordinateSystem, Entrance, FixedElement, Floorplate,
                                 Meta, Perimeter, Provenance, SourceImage, Status, Unknown, Window)
from .segmentation import REGISTRY as SEG_REGISTRY, SegmentationRequest
from .vision import REGISTRY as VIS_REGISTRY, VisionResult


@dataclass
class PipelineConfig:
    case_id: str
    image_path: str
    unit_label: str
    known_area_m2: Optional[float] = None
    known_area_kind: str = "unknown"          # useful | rentable | total | unknown
    vision: str = "ocr"
    segmentation: str = "auto"                # auto | opencv_color | opencv_flood | sam2 | manual
    overrides_path: Optional[str] = None
    out_dir: str = "outputs"
    simplify_eps_frac: float = 0.004
    snap_orthogonal: bool = True
    mask_open_px: int = 3
    column_detector: str = "both"             # hollow | dark | both
    semantics: bool = True                    # E03: construir shell semántico
    source_name: str = ""                     # E16.1: la fuente/broker es dato del caso, no del renderer


def _manual_meta(note=""):
    return Meta(confidence=1.0, provenance=Provenance.MANUAL.value, status=Status.CONFIRMED.value, notes=note)


def run(cfg: PipelineConfig) -> Floorplate:
    img = cv2.imread(cfg.image_path)
    if img is None:
        raise FileNotFoundError(cfg.image_path)
    h, w = img.shape[:2]
    with open(cfg.image_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    ov = Overrides.load(cfg.overrides_path)
    unknowns = []
    os.makedirs(cfg.out_dir, exist_ok=True)
    out = lambda name: os.path.join(cfg.out_dir, name)  # noqa: E731

    # 1. hints (localización)
    vis_cls = VIS_REGISTRY[cfg.vision]
    vis = vis_cls(ov.get("vision_hints", [])) if cfg.vision == "manual" else vis_cls()
    vres: VisionResult = vis.interpret(img, cfg.unit_label, cfg.known_area_m2)
    region = vres.best("unit_region")

    # 2. segmentación
    localization = "unknown"
    if ov.has("perimeter"):
        seg = SEG_REGISTRY["manual"]().segment(SegmentationRequest(img, polygon=ov.get("perimeter")["ring"]))
        localization = "manual"
        seeds = []
    else:
        seeds = list(ov.get("seed_points", []))
        if seeds or ov.has("bbox"):
            localization = "assisted"
        elif region and (region.point or region.bbox):
            seeds = [region.point] if region.point else [((region.bbox[0] + region.bbox[2]) / 2, (region.bbox[1] + region.bbox[3]) / 2)]
            localization = "automatic"
        if not seeds:
            raise RuntimeError("Sin localización: ni hint unit_region (OCR/VLM) ni seed_points/bbox en overrides.json. "
                               "Pase B (assisted): agrega \"seed_points\": [[x, y]] en overrides.json.")
        seg_name = cfg.segmentation
        if seg_name == "auto":
            # relleno de color detectado alrededor del label → color; si no, flood por muros
            seg_name = "opencv_color" if (region and region.color_bgr) or ov.get("segmentation_params", {}).get("mode") == "color" else "opencv_flood"
        bbox = tuple(ov.get("bbox")) if ov.has("bbox") else (region.bbox if (region and seg_name != "opencv_color") else None)
        seg = SEG_REGISTRY[seg_name]().segment(SegmentationRequest(
            img, seed_points=seeds, bbox=bbox, params=ov.get("segmentation_params")))
    cv2.imwrite(out("mask.png"), seg.mask)
    cv2.imwrite(out("target_mask.png"), seg.mask)
    # evidencia intermedia de localización
    ev = img.copy()
    for hnt in vres.hints:
        if hnt.bbox:
            x0, y0, x1, y1 = map(int, hnt.bbox)
            col = (0, 0, 255) if hnt.kind == "unit_region" else (0, 160, 0) if hnt.kind == "legend_swatch" else (255, 0, 0)
            cv2.rectangle(ev, (x0 - 2, y0 - 2), (x1 + 2, y1 + 2), col, 1)
            cv2.putText(ev, hnt.kind, (x0, max(10, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1)
    for (x, y) in seeds:
        cv2.drawMarker(ev, (int(x), int(y)), (0, 0, 255), cv2.MARKER_CROSS, 14, 2)
    ys, xs = np.where(seg.mask > 0)
    if len(xs):
        cv2.rectangle(ev, (xs.min(), ys.min()), (xs.max(), ys.max()), (0, 0, 255), 1)
    cv2.imwrite(out("target_bbox.png"), ev)
    tov = img.copy()
    tov[seg.mask > 0] = (0.55 * tov[seg.mask > 0] + np.array([0, 0, 115])).astype(np.uint8)
    cv2.imwrite(out("target_overlay.png"), tov)

    # 3-5. contorno + simplificación
    geo = GeometryExtractor(cfg.simplify_eps_frac, cfg.snap_orthogonal, cfg.mask_open_px).extract(seg.mask)
    perim = Perimeter(ring=geo.ring, raw_ring=geo.raw_ring,
                      meta=Meta(confidence=seg.confidence, provenance=seg.provenance,
                                status=Status.CONFIRMED.value if seg.provenance == "manual" else Status.NEEDS_CONFIRMATION.value,
                                notes=f"{seg.notes}; {geo.notes}"))
    holes = []
    # huecos conservados por la segmentación → holes
    cnts, hier = cv2.findContours(seg.mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is not None:
        for i in range(len(cnts)):
            if hier[0][i][3] != -1 and cv2.contourArea(cnts[i]) > 0.005 * geo.area_px2:
                eps = cfg.simplify_eps_frac * cv2.arcLength(cnts[i], True)
                ring = [tuple(map(float, p)) for p in cv2.approxPolyDP(cnts[i], eps, True).reshape(-1, 2)]
                from .schemas.floorplate import Polygon as FpPolygon
                holes.append(FpPolygon(ring=ring, meta=Meta(seg.confidence, seg.provenance, Status.NEEDS_CONFIRMATION.value, "hueco en la máscara")))
    with open(out("raw_contour.svg"), "w", encoding="utf-8") as f:
        f.write(contour_svg(geo.raw_ring, w, h, stroke="#e33", title="raw contour"))
    with open(out("simplified_contour.svg"), "w", encoding="utf-8") as f:
        f.write(contour_svg(geo.ring, w, h, stroke="#111", title="simplified contour", raw=geo.raw_ring))

    # 6. escala
    published = ov.get("known_area") or ({"m2": cfg.known_area_m2, "kind": cfg.known_area_kind} if cfg.known_area_m2 else None)
    if ov.has("scale"):
        scale = scale_manual(ov.get("scale")["px_per_m"], "override")
    elif published and published.get("m2"):
        scale = scale_from_known_area(geo.area_px2, float(published["m2"]), published.get("kind", "unknown"))
        if published.get("kind", "unknown") in ("unknown", "rentable", "total"):
            unknowns.append(Unknown("scale.area_kind", f"superficie publicada de tipo '{published.get('kind', 'unknown')}': "
                                                       "la escala inferida depende de que esa cifra sea el área del polígono útil"))
    else:
        scale = scale_unknown()
        unknowns.append(Unknown("scale", "sin superficie publicada ni barra de escala ni cota"))
    area_m2 = geo.area_px2 / scale.px_per_m ** 2 if scale.px_per_m else None
    area_meta = Meta(confidence=scale.meta.confidence, provenance=Provenance.DERIVED.value, status=Status.INFERRED.value,
                     notes="área del polígono / escala². Si la escala viene del área publicada, esto es tautológico.")

    # 7. elementos
    core = [Core(ring=[tuple(p) for p in c["ring"]], kind=c.get("kind", "core"), meta=_manual_meta()) for c in ov.get("core", [])]
    if not core:
        for ring, conf, note in detect_core_enclosed(img, seg.mask):
            core.append(Core(ring=ring, kind="core", meta=Meta(conf, Provenance.CV_HEURISTIC.value, Status.NEEDS_CONFIRMATION.value, note)))
    if not core:
        hint = vres.best("core")
        if hint and hint.bbox:
            x0, y0, x1, y1 = hint.bbox
            core.append(Core(ring=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], meta=Meta(
                confidence=min(hint.confidence, 0.5), provenance=Provenance.VLM.value,
                status=Status.NEEDS_CONFIRMATION.value, notes="bbox del VLM, no polígono")))
        else:
            unknowns.append(Unknown("core", "sin override, sin vacío encerrado detectable, sin hint"))

    entrances = [Entrance(point=snap_point_to_ring(tuple(e["point"]), geo.ring), width_px=e.get("width_px"),
                          kind=e.get("kind", "main"), meta=_manual_meta(e.get("notes", "snap al perímetro"))) for e in ov.get("entrances", [])]
    if not entrances:
        for hnt in vres.of("entrance"):
            if hnt.point:
                entrances.append(Entrance(point=snap_point_to_ring(hnt.point, geo.ring), meta=Meta(
                    confidence=min(hnt.confidence, 0.5), provenance=Provenance.VLM.value, status=Status.NEEDS_CONFIRMATION.value)))
        if not entrances:
            unknowns.append(Unknown("entrances", "no hay heurística CV de puertas; sin override ni hint"))

    label_boxes = [hh.bbox for hh in vres.hints if hh.bbox]
    columns = []
    if cfg.column_detector in ("hollow", "both"):
        columns += detect_hollow_columns(img, seg.mask, scale.px_per_m, exclude_bboxes=label_boxes)
    if cfg.column_detector in ("dark", "both"):
        for c in detect_columns(img, seg.mask, scale.px_per_m):
            if all(np.hypot(c.center[0] - o.center[0], c.center[1] - o.center[1]) > 6 for o in columns) and \
               not any(bx0 - 2 <= c.center[0] <= bx1 + 2 and by0 - 2 <= c.center[1] <= by1 + 2 for bx0, by0, bx1, by1 in label_boxes):
                columns.append(c)
    colov = ov.get("columns") or {}
    if colov.get("replace"):
        columns = []
    for rm in colov.get("remove_near", []):
        columns = [c for c in columns if np.hypot(c.center[0] - rm[0], c.center[1] - rm[1]) > 15]
    for add in colov.get("add", []):
        columns.append(Column(center=tuple(add["center"]), size_px=add.get("size_px", 10.0), shape=add.get("shape", "square"),
                              meta=_manual_meta(add.get("notes", ""))))
    if not columns:
        unknowns.append(Unknown("columns", "heurística no detectó pilares; posiblemente no dibujados o ilegibles"))

    fparams = ov.get("facade_params") or {}
    facade = classify_facade_segments(img, seg.mask, geo.ring, **fparams)
    for idx, kind in (ov.get("facade_kinds") or {}).items():
        i = int(idx)
        if 0 <= i < len(facade):
            facade[i].kind = kind; facade[i].meta = _manual_meta()
    if not any(s.kind == "facade" for s in facade):
        unknowns.append(Unknown("facade", "ningún lado clasificado como fachada"))

    windows = [Window(start=tuple(wn["start"]), end=tuple(wn["end"]), meta=_manual_meta()) for wn in ov.get("windows", [])]
    if not windows:
        unknowns.append(Unknown("windows", "no distinguibles/anotadas; NO se asume ventana continua"))
    fixed = [FixedElement(ring=[tuple(p) for p in x["ring"]], kind=x["kind"], label=x.get("label", ""), meta=_manual_meta())
             for x in ov.get("fixed_elements", [])]

    # confirmaciones humanas (aceptar un elemento inferido sin redibujarlo)
    for what in ov.get("confirm", []):
        targets = {"perimeter": [perim], "core": core, "columns": columns, "facade": facade}.get(what, [])
        for t in targets:
            if t.meta.status != Status.CONFIRMED.value:
                t.meta.status = Status.CONFIRMED.value
                t.meta.notes += "; confirmado por humano"

    fp = Floorplate(
        schema_version=SCHEMA_VERSION, case_id=cfg.case_id, unit_label=cfg.unit_label,
        source_image=SourceImage(path=os.path.basename(cfg.image_path), width_px=w, height_px=h, sha256=sha),
        coordinate_system=CoordinateSystem(), scale=scale, perimeter=perim, holes=holes,
        core=core, columns=columns, entrances=entrances, windows=windows, facade_segments=facade,
        fixed_elements=fixed, area_m2=area_m2, area_px2=geo.area_px2, area_meta=area_meta,
        published_area_m2=float(published["m2"]) if published and published.get("m2") else None,
        published_area_kind=(published or {}).get("kind", "unknown"), target_localization=localization,
        unknowns=unknowns,
        pipeline={"version": __version__, "vision": vres.provider, "vision_model": vres.model,
                  "vision_hints": [{"kind": hh.kind, "confidence": hh.confidence, "point": hh.point, "bbox": hh.bbox,
                                    "text": hh.text, "color_bgr": hh.color_bgr, "notes": hh.notes} for hh in vres.hints],
                  "segmentation": seg.provider, "seeds": seeds, "simplify_eps_frac": cfg.simplify_eps_frac,
                  "snap_orthogonal": cfg.snap_orthogonal, "mask_open_px": cfg.mask_open_px, "column_detector": cfg.column_detector,
                  "overrides": os.path.basename(cfg.overrides_path or "") or None,
                  "override_keys_used": [k for k in ov.data.keys() if ov.has(k) and not k.startswith("_")]})

    # 7b. SHELL semántico (E03): accesos, luz/fachada, pilares v2, readiness
    if cfg.semantics:
        from .semantics import build_shell
        from .renderer.shell import render_shell_svg, shell_comparison, shell_semantics_png
        opened = seg.mask
        if cfg.mask_open_px and cfg.mask_open_px > 1:
            opened = cv2.morphologyEx(seg.mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (cfg.mask_open_px,) * 2))
        fp = build_shell(fp, img, seg.mask, opened, ov, label_boxes=label_boxes)
        num = "".join(ch for ch in cfg.unit_label if ch.isdigit()) or "unit"
        with open(out("shell_semantics.svg"), "w", encoding="utf-8") as f:
            f.write(render_shell_svg(fp))
        cv2.imwrite(out(f"shell_semantics_{num}.png"), shell_semantics_png(fp))
        cv2.imwrite(out(f"shell_comparison_{num}.png"), shell_comparison(img, fp))

    # 8-10. salidas
    fp.save(out("floorplate.json"))
    with open(out("planta_escalimetro.svg"), "w", encoding="utf-8") as f:
        f.write(render_svg(fp))
    with open(out("planta_escalimetro_px.svg"), "w", encoding="utf-8") as f:
        f.write(render_svg(fp, units="px", show_raw=True))
    cv2.imwrite(out("side_by_side.png"), side_by_side(img, fp))
    cv2.imwrite(out("overlay.png"), overlay_on_original(img, fp))
    cv2.imwrite(out("perimeter_overlay.png"), overlay_on_original(img, fp, only_perimeter=True))
    cv2.imwrite(out("original_grid.png"), grid_image(img))
    num = "".join(ch for ch in cfg.unit_label if ch.isdigit()) or "unit"
    cv2.imwrite(out(f"comparison_{num}.png"), comparison_three(img, fp, source_name=cfg.source_name))
    cv2.imwrite(out("geometry_only.png"), geometry_only(fp))
    return fp
