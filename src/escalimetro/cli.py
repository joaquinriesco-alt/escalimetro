"""CLI: python -m escalimetro run --case cases/001_gps_403 [--vision manual] [--segmentation opencv_flood]

Lee cases/<id>/case.json:
{
  "case_id": "001_gps_403", "image": "original.jpg", "unit_label": "Oficina 403",
  "known_area_m2": 543, "known_area_kind": "unknown", "overrides": "overrides.json"
}
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .pipeline import PipelineConfig, run


def main(argv=None):
    ap = argparse.ArgumentParser(prog="escalimetro")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="ejecutar normalización de un caso")
    r.add_argument("--case", required=True, help="carpeta del caso")
    r.add_argument("--vision", default=None, help="manual|null|openai|anthropic|gemini")
    r.add_argument("--segmentation", default=None, help="opencv_flood|opencv_color|sam2|manual")
    r.add_argument("--out", default=None)
    r.add_argument("--eps", type=float, default=None, help="eps relativo de simplificación")
    r.add_argument("--overrides", default=None, help="archivo de overrides (relativo al caso); default: case.json.overrides")
    b = sub.add_parser("bench", help="benchmark contra ground_truth")
    b.add_argument("--case", required=True)
    b.add_argument("--out", default=None)
    b.add_argument("--pred", default=None, help="carpeta con floorplate.json a evaluar (default outputs/)")
    args = ap.parse_args(argv)

    case_dir = args.case
    with open(os.path.join(case_dir, "case.json"), encoding="utf-8") as f:
        c = json.load(f)
    if args.cmd == "run":
        cfg = PipelineConfig(
            case_id=c["case_id"], image_path=os.path.join(case_dir, c["image"]), unit_label=c["unit_label"],
            source_name=c.get("source_name", ""),          # E16.1: la fuente sale del caso
            drawing_scope=c.get("drawing_scope", "multi_unit"),   # E16.5: hecho de la fuente
            known_area_m2=c.get("known_area_m2"), known_area_kind=c.get("known_area_kind", "unknown"),
            vision=args.vision or c.get("vision", "manual"), segmentation=args.segmentation or c.get("segmentation", "opencv_flood"),
            overrides_path=os.path.join(case_dir, args.overrides or c.get("overrides")) if (args.overrides or c.get("overrides")) else None,
            out_dir=args.out or os.path.join(case_dir, "outputs"),
            simplify_eps_frac=args.eps if args.eps is not None else c.get("simplify_eps_frac", 0.004),
            snap_orthogonal=c.get("snap_orthogonal", True), mask_open_px=c.get("mask_open_px", 3),
            column_detector=c.get("column_detector", "both"), semantics=c.get("semantics", True))
        if not os.path.exists(cfg.image_path):
            print(f"[escalimetro] falta la imagen: {cfg.image_path}\n"
                  f"  Coloca el JPG original en esa ruta y vuelve a ejecutar.", file=sys.stderr)
            return 2
        fp = run(cfg)
        print(f"[escalimetro] OK {fp.unit_label}: localización={fp.target_localization}, {len(fp.perimeter.ring)} vértices, "
              f"área={fp.area_m2 and round(fp.area_m2, 1)} m², escala={fp.scale.px_per_m and round(fp.scale.px_per_m, 3)} px/m, "
              f"pilares={len(fp.columns)}, accesos={len(fp.entrances)}, core={len(fp.core)}, unknowns={[u.element for u in fp.unknowns]}")
        if fp.shell_readiness:
            r = fp.shell_readiness
            print(f"[escalimetro] shell: primary_entrance={fp.primary_entrance and tuple(round(v) for v in fp.primary_entrance.point)} "
                  f"({fp.primary_entrance and fp.primary_entrance.status}), candidatos={len(fp.entrance_candidates)}, "
                  f"pilares_cand={len(fp.column_candidates)}, daylight={[d.classification for d in fp.daylight_segments if d.index in fp.exterior_facade_segments]}, "
                  f"ready_for_layout={r.ready_for_layout}, requires={r.requires_confirmation}")
        print(f"[escalimetro] salidas en {cfg.out_dir}/")
        return 0
    if args.cmd == "bench":
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "benchmarks"))
        from run_benchmark import run_benchmark  # type: ignore
        rep = run_benchmark(case_dir, args.out, args.pred)
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    sys.exit(main())
