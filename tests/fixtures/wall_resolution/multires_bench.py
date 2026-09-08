"""Banco multi-resolución: métricas de invarianza y discriminación (E16.16 §5)."""
import sys, cv2, numpy as np
sys.path.insert(0,"/home/claude/escalimetro/src")
sys.path.insert(0,"/tmp/claude-0/-home-claude/b193d4db-92b4-58be-84f5-d337bcc70127/scratchpad/e1616")
import scene
from escalimetro.geometry import core_geometry as CG
from escalimetro.segmentation.structural import stroke_scale_px

RES = (600, 800, 1000, 1400, 1800, 2400)

def metricas(wall, gt):
    """dos preguntas distintas: ¿conserva muros? ¿rechaza tinta no estructural?"""
    W = wall > 0
    gw = gt["wall"] > 0
    tol = max(1, stroke_scale_px((gt["height"], gt["side"])) // 3)
    gw_tol = cv2.dilate((gw * 255).astype(np.uint8),
                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tol | 1, tol | 1))) > 0
    rec = float((W & gw).sum()) / max(1.0, float(gw.sum()))
    pre = float((W & gw_tol).sum()) / max(1.0, float(W.sum()))
    fp = {}
    for k in ("furniture", "text", "grid"):
        g = (gt[k] > 0) & ~gw_tol
        fp[k] = float((W & g).sum()) / max(1.0, float(g.sum()))
    return rec, pre, fp

def anclas_del_recinto(img, fp_mask, gt):
    a, n = CG.enclosed_cell_anchors(img, fp_mask)
    x, y, w, h = gt["room"]; S = gt["side"]
    caja = np.zeros(a.shape[:2], bool)
    caja[int(y*S)+2:int((y+h)*S)-2, int(x*S)+2:int((x+w)*S)-2] = True
    return int(((a > 0) & caja).sum() > 0), n

def correr(wall_fn, etiqueta):
    print(f"\n### {etiqueta}")
    print(f"{'lado':>6s} {'k':>3s} {'recall':>7s} {'prec':>6s} {'FPmob':>7s} {'FPtxt':>7s} {'FPgrid':>7s} {'recinto':>8s} {'anclas':>7s}")
    filas=[]
    for side in RES:
        img, gt = scene.render(side)
        w = wall_fn(img)
        rec, pre, fp = metricas(w, gt)
        rec_ok, n_anch = anclas_del_recinto(img, gt["footprint"], gt)
        k = stroke_scale_px((gt["height"], side))
        print(f"{side:>6d} {k:>3d} {rec:>7.3f} {pre:>6.3f} {fp['furniture']:>7.3f} {fp['text']:>7.3f} {fp['grid']:>7.3f} {rec_ok:>8d} {n_anch:>7d}")
        filas.append((side,k,rec,pre,fp['furniture'],fp['text'],fp['grid'],rec_ok,n_anch))
    r=[f[2] for f in filas]; p=[f[3] for f in filas]; fm=[f[4] for f in filas]
    print(f"  INVARIANZA: recall {min(r):.3f}–{max(r):.3f} (Δ={max(r)-min(r):.3f}) | "
          f"precisión {min(p):.3f}–{max(p):.3f} (Δ={max(p)-min(p):.3f}) | FPmob {min(fm):.3f}–{max(fm):.3f}")
    print(f"  recinto detectado en {sum(f[7] for f in filas)}/{len(filas)} resoluciones")
    return filas

if __name__ == "__main__":
    correr(lambda im: CG.wall_map(im), "BASELINE E16.15 (motor vigente)")

def comparar():
    import wall_v2
    a = correr(lambda im: CG.wall_map(im), "BASELINE E16.15 (motor vigente)")
    b = correr(lambda im: wall_v2.wall_map_v2(im), "CANDIDATO E16.16 (escala de trazo canónica)")
    return a, b
