"""Banco de diagnóstico E16.12 — clases A–H del §9, ejecutando el productor real.

No entra al motor: vive en cases/generalization/E16_12/ como evidencia del ciclo.
Lámina 1300×860, planta propia. Ninguna medida viene de un caso real.
"""
import json, os
import cv2, numpy as np
W,H=1300,860
OUT=os.path.dirname(os.path.abspath(__file__))
PAPEL,MURO,FINO=255,40,120
RING=[(90,90),(1210,90),(1210,540),(1090,540),(1090,770),(90,770)]
def hoja(): return np.full((H,W),PAPEL,np.uint8)
def planta(img,t=10): cv2.polylines(img,[np.array(RING,np.int32)],True,MURO,t)
def celdas(img,x,y,n,cw=75,ch=115,gap=13):
    cv2.rectangle(img,(x-15,y-15),(x+n*(cw+gap)+2,y+ch+15),MURO,9)
    for i in range(n):
        x0=x+i*(cw+gap); cv2.rectangle(img,(x0,y),(x0+cw,y+ch),MURO,7)
def escalera(img,x,y,w=200,h=140):
    cv2.rectangle(img,(x,y),(x+w,y+h),MURO,9)
    for i in range(1,10): cv2.line(img,(x+8,y+int(i*h/10)),(x+w-8,y+int(i*h/10)),FINO,2)
def sala(img,x,y,w,h,t=9): cv2.rectangle(img,(x,y),(x+w,y+h),MURO,t)
def tabique(img,x0,y0,x1,y1,t=9): cv2.line(img,(x0,y0),(x1,y1),MURO,t)
def muebles(img,seed=7,n=70):
    rng=np.random.default_rng(seed)
    for _ in range(n):
        x=int(rng.integers(130,1060)); y=int(rng.integers(130,700))
        if 380<x<980 and 190<y<650: continue
        cv2.rectangle(img,(x,y),(x+int(rng.integers(35,70)),y+int(rng.integers(25,50))),FINO,3)
def guardar(n,img,hint,nota):
    cv2.imwrite(os.path.join(OUT,n+".png"),cv2.cvtColor(img,cv2.COLOR_GRAY2BGR))
    json.dump({"hint_region":hint,"footprint_ring":RING,"clase":nota},
              open(os.path.join(OUT,n+".json"),"w"),indent=1,ensure_ascii=False)
    return n
def main():
    hs=[]; HINT=[400,180,1000,660]
    # A — conjunto conectado completo: tres bloques unidos por tabiques reales
    img=hoja(); planta(img); escalera(img,430,220); celdas(img,430,480,4); sala(img,800,220,150,180)
    tabique(img,430,360,430,480); tabique(img,950,300,950,480); tabique(img,430,480,950,480)
    muebles(img)
    hs.append(guardar("A_COMPLETE_CONNECTED_CLUSTER",img,HINT,"conjunto conectado por tabiques"))
    # B — tentación de subpieza: el bloque de celdas es plausible por sí solo
    hs.append(guardar("B_PARTIAL_CLUSTER_TEMPTATION",img.copy(),HINT,"misma lámina que A; el juez debe exigir el conjunto"))
    # C — conexión estructural angosta
    img=hoja(); planta(img); escalera(img,430,220); celdas(img,430,500,4)
    tabique(img,530,360,530,500,4)     # tabique fino: conexión real pero angosta
    muebles(img)
    hs.append(guardar("C_NARROW_STRUCTURAL_CONNECTION",img,HINT,"dos masas unidas por un tabique fino"))
    # D — recinto cerrado ajeno dentro de un hint amplio
    img=hoja(); planta(img); escalera(img,430,220); celdas(img,430,480,4); sala(img,800,220,150,180)
    tabique(img,430,360,430,480); tabique(img,950,300,950,480); tabique(img,430,480,950,480)
    sala(img,180,600,110,95); muebles(img)
    hs.append(guardar("D_UNRELATED_CLOSED_ROOM",img,[150,170,1010,730],"recinto ordinario ajeno dentro del alcance"))
    # E — componentes de servicio distribuidos, sin conexión estructural entre ellos
    img=hoja(); planta(img); escalera(img,420,220); celdas(img,420,520,3); sala(img,880,240,150,170)
    muebles(img)
    hs.append(guardar("E_DISTRIBUTED_SERVICE_COMPONENTS",img,[390,190,1050,680],"tres masas permanentes SIN tabique entre ellas"))
    # F — negativo de puente por espacio abierto
    img=hoja(); planta(img); celdas(img,420,230,3); celdas(img,760,560,3); muebles(img)
    hs.append(guardar("F_OPEN_FLOOR_BRIDGE_NEGATIVE",img,[390,200,1060,720],"dos bloques separados por piso abierto"))
    # G — falso core compacto: un bloque sólido y un conjunto mayor alrededor
    img=hoja(); planta(img); sala(img,600,330,190,170,12); escalera(img,420,220); celdas(img,420,520,3)
    muebles(img)
    hs.append(guardar("G_COMPACT_FALSE_CORE",img,HINT,"masa compacta que no es todo el conjunto"))
    # H — sin evidencia estructural fiable
    img=hoja(); planta(img); muebles(img,seed=3,n=120)
    hs.append(guardar("H_NO_RELIABLE_STRUCTURAL_EVIDENCE",img,HINT,"sólo mobiliario"))
    for n in hs: print(n)
if __name__=="__main__": main()
