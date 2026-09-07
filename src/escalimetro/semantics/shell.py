"""Etapa semántica (E03): Floorplate geométrico → SHELL usable por un motor de layout.

Entradas: floorplate (0.1.1+), imagen, máscara cruda y abierta, overrides.
Salidas en el mismo Floorplate (0.2.0): entrance_candidates, primary_entrance, daylight_segments,
exterior_facade_segments, column_candidates, north_arrow, shell_readiness.

Overrides que entiende (todos cuentan en HUMAN CORRECTION BURDEN):
  "confirm": ["entrance", "columns", "daylight", "scale_assumption", ...]   1 click cada uno
  "entrance_choice": {"index": 1} | {"point": [x, y]}                        1 click
  "daylight_confirm": {"3": "likely_glazing", "7": "confirmed_glazing"}     1 click por lado
  "columns": {"add": [...], "remove_near": [...]}                            1 click por pilar
  "north_angle_deg": 12.0                                                   1 click
"""
from __future__ import annotations

from typing import List, Optional

import cv2
import numpy as np

from ..area_semantics import SCALE_INCOMPATIBLE_REGION
from ..schemas.floorplate import (Column, ColumnCandidate, DaylightSegment, Entrance, EntranceCandidate, Floorplate, Meta,
                                  NorthArrow, Provenance, ShellReadiness, Status, Unknown)
from .columns_v2 import detect_columns_v2
from .daylight import PRIORITY, classify_daylight
from .entrance import choose_primary, detect_entrance_candidates


def build_shell(fp: Floorplate, image_bgr: np.ndarray, raw_mask: Optional[np.ndarray], opened_mask: Optional[np.ndarray],
                ov, label_boxes=()) -> Floorplate:
    confirm = set(ov.get("confirm", []))
    ppm = fp.scale.px_per_m

    # ---- accesos -------------------------------------------------------------
    cands = detect_entrance_candidates(image_bgr, fp.perimeter.ring, fp.facade_segments, [c.ring for c in fp.core],
                                       raw_mask, opened_mask, ppm)
    fp.entrance_candidates = [EntranceCandidate(point=c.point, kind=c.kind, confidence=c.confidence, evidence=c.evidence,
                                                width_px=c.width_px, segment_index=c.segment_index) for c in cands]
    best, status, note = choose_primary(cands)
    primary: Optional[EntranceCandidate] = None
    legacy = ov.get("entrances") or []
    if ov.has("entrance_choice") or legacy:
        ch = ov.get("entrance_choice") if ov.has("entrance_choice") else {"point": legacy[0]["point"]}   # compat E02
        if "index" in ch and 0 <= ch["index"] < len(fp.entrance_candidates):
            primary = fp.entrance_candidates[ch["index"]]
            primary.evidence = primary.evidence + ["human:elegido entre candidatos"]
        elif "point" in ch:
            primary = EntranceCandidate(point=tuple(ch["point"]), kind="primary", confidence=1.0,
                                        evidence=["human:punto indicado"], provenance=Provenance.MANUAL.value)
        if primary:
            primary.kind, primary.status = "primary", Status.CONFIRMED.value
    elif best is not None:
        primary = fp.entrance_candidates[[c.point for c in cands].index(best.point)]
        primary.status = Status.INFERRED.value if status == "inferred" else Status.NEEDS_CONFIRMATION.value
        primary.evidence = primary.evidence + [f"selection:{note}"]
        if "entrance" in confirm:
            primary.status = Status.CONFIRMED.value
            primary.evidence.append("human:confirmado")
    fp.primary_entrance = primary
    # compat: la lista legacy `entrances` refleja el primary (y secundarios con conf ≥ 0.6)
    fp.entrances = []
    if primary:
        fp.entrances.append(Entrance(point=primary.point, width_px=primary.width_px, kind="main",
                                     meta=Meta(primary.confidence, primary.provenance, primary.status, "primary_entrance")))
    for c in fp.entrance_candidates:
        if primary and c is not primary and c.confidence >= 0.6:
            fp.entrances.append(Entrance(point=c.point, width_px=c.width_px, kind="secondary",
                                         meta=Meta(c.confidence, c.provenance, c.status, "entrance_candidate")))
    fp.unknowns = [u for u in fp.unknowns if u.element != "entrances"]
    if not primary:
        fp.unknowns.append(Unknown("primary_entrance", "sin candidatos con evidencia suficiente"))

    # ---- fachada / luz ---------------------------------------------------------
    fp.exterior_facade_segments = [s.index for s in fp.facade_segments if s.kind == "facade"]
    dls = classify_daylight(image_bgr, fp.perimeter.ring, fp.facade_segments, ppm)
    fp.daylight_segments = [DaylightSegment(index=d.index, start=d.start, end=d.end, classification=d.classification,
                                            confidence=d.confidence, daylight_priority=d.daylight_priority, evidence=d.evidence)
                            for d in dls]
    for idx, cls in (ov.get("daylight_confirm") or {}).items():
        for d in fp.daylight_segments:
            if d.index == int(idx):
                d.classification, d.daylight_priority = cls, PRIORITY[cls]
                d.confidence, d.status, d.provenance = 1.0, Status.CONFIRMED.value, Provenance.MANUAL.value
                d.evidence = d.evidence + ["human:clasificación confirmada/corregida"]
    if "daylight" in confirm:
        for d in fp.daylight_segments:
            if d.status != Status.CONFIRMED.value:
                d.status = Status.CONFIRMED.value
                d.evidence = d.evidence + ["human:aceptado tal cual"]
    fp.unknowns = [u for u in fp.unknowns if u.element != "windows"]
    if not any(d.classification in ("confirmed_glazing", "likely_glazing") for d in fp.daylight_segments):
        fp.unknowns.append(Unknown("daylight", "ningún lado con evidencia de acristalamiento"))
    else:
        fp.unknowns.append(Unknown("windows.exact", "posición exacta de ventanas no extraída; sólo clasificación por lado"))

    # ---- pilares v2 -------------------------------------------------------------
    v2 = detect_columns_v2(image_bgr, raw_mask if raw_mask is not None else opened_mask, ppm, exclude_bboxes=label_boxes)
    fp.column_candidates = [ColumnCandidate(center=c.center, size_px=c.size_px, confidence=c.confidence, evidence=c.evidence) for c in v2]
    colov = ov.get("columns") or {}
    for rm in colov.get("remove_near", []):
        fp.column_candidates = [c for c in fp.column_candidates if np.hypot(c.center[0] - rm[0], c.center[1] - rm[1]) > 15]
    for add in colov.get("add", []):
        near = [c for c in fp.column_candidates if np.hypot(c.center[0] - add["center"][0], c.center[1] - add["center"][1]) <= 8]
        if near:                                   # ya detectado: el click confirma, no duplica
            near[0].status, near[0].confidence = Status.CONFIRMED.value, 1.0
            near[0].evidence = near[0].evidence + ["human:confirmado (coincide con pilar agregado)"]
            continue
        fp.column_candidates.append(ColumnCandidate(center=tuple(add["center"]), size_px=add.get("size_px", 9.0), confidence=1.0,
                                                    evidence=["human:agregado"], status=Status.CONFIRMED.value,
                                                    provenance=Provenance.MANUAL.value))
    if "columns" in confirm:
        for c in fp.column_candidates:
            if c.status != Status.CONFIRMED.value:
                c.status = Status.CONFIRMED.value
                c.evidence = c.evidence + ["human:confirmado"]
    # compat: `columns` legacy = candidatos (para renderer/benchmark)
    fp.columns = [Column(center=c.center, size_px=c.size_px, shape="rect",
                         meta=Meta(c.confidence, c.provenance, c.status, "; ".join(e for e in c.evidence if not e.startswith("rejected"))[:200]))
                  for c in fp.column_candidates]
    fp.unknowns = [u for u in fp.unknowns if u.element != "columns"]

    # ---- flecha norte ------------------------------------------------------------
    if ov.get("north_angle_deg") is not None:
        fp.north_arrow = NorthArrow(True, float(ov.get("north_angle_deg")),
                                    Meta(1.0, Provenance.MANUAL.value, Status.CONFIRMED.value, "declarada por humano; sin cálculo solar"))
    else:
        fp.north_arrow = NorthArrow(False, None, Meta(0.0, Provenance.UNKNOWN.value, Status.UNKNOWN.value,
                                                      "no detectada automáticamente; no se infiere orientación solar"))

    # ---- readiness ----------------------------------------------------------------
    req: List[str] = []
    geometry_ready = fp.perimeter.meta.status == Status.CONFIRMED.value and bool(fp.core) and \
        all(c.meta.status == Status.CONFIRMED.value for c in fp.core)
    if not geometry_ready:
        req.append("perimeter/core")
    entrance_ready = primary is not None and primary.status == Status.CONFIRMED.value
    if not entrance_ready:
        req.append("primary_entrance")
    columns_ready = bool(fp.column_candidates) and all(c.status == Status.CONFIRMED.value for c in fp.column_candidates)
    if not columns_ready:
        req.append("columns")
    ext = [d for d in fp.daylight_segments if d.index in fp.exterior_facade_segments]
    daylight_ready = bool(ext) and all(d.status == Status.CONFIRMED.value and d.classification != "unknown" for d in ext)
    if not daylight_ready:
        req.append("daylight")
    # E16.8 — una escala semánticamente incompatible NO la salva una confirmación humana genérica.
    # Confirmar "scale_assumption" acepta la INCERTIDUMBRE NUMÉRICA de un supuesto; no convierte en
    # equivalentes dos regiones que el vocabulario define como distintas. Para eso hace falta que la
    # fuente declare la equivalencia (known_area_region), que es un hecho de origen y entra antes.
    scale_incompatible = fp.scale.semantic_validity == SCALE_INCOMPATIBLE_REGION
    scale_ok = (not scale_incompatible) and (fp.scale.meta.status == Status.CONFIRMED.value
                                             or "scale_assumption" in confirm)
    if not scale_ok:
        req.append("scale_semantics" if scale_incompatible else "scale_assumption")
    notes = []
    if scale_incompatible:
        notes.append(f"ESCALA NO DISPONIBLE: {fp.scale.semantic_reason}. Ninguna medida en metros de "
                     "este shell es utilizable mientras eso no se resuelva")
    if "scale_assumption" in confirm and scale_incompatible:
        notes.append("la confirmación humana de 'scale_assumption' NO aplica: acepta incertidumbre "
                     "numérica, no una región equivocada")
    if "scale_assumption" in confirm and not scale_incompatible and fp.scale.meta.status != Status.CONFIRMED.value:
        notes.append(f"escala aceptada como SUPUESTO ({fp.scale.method}, {fp.published_area_m2} m² tipo {fp.published_area_kind}); "
                     "las dimensiones del layout heredan esa incertidumbre")
    if not fp.north_arrow.detected:
        notes.append("sin orientación: daylight_priority no considera sol")
    fp.shell_readiness = ShellReadiness(geometry_ready=geometry_ready, entrance_ready=entrance_ready, columns_ready=columns_ready,
                                        daylight_ready=daylight_ready, requires_confirmation=req,
                                        ready_for_layout=(not req), notes="; ".join(notes))
    return fp
