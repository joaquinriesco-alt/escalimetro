# E19 — GANANCIA DE INFORMACIÓN POR CONTEXTO (SPIKE)

> Spike experimental. **El motor no cambia.** Ni el ancho (E17) ni la topología (E18) participan.
> Veredicto: **B — CONTEXT PROVIDES PARTIAL INFORMATION**.

## 1. La corrección conceptual que abre el ciclo

E18 no probó que la distinción muro/mueble no esté en el ráster. Probó algo más acotado: **la
geometría intrínseca local del objeto no la contiene**. E19 mide si el contexto sí.

## 2. El diseño: contrafactual con target byte-idéntico

36 pares. En cada par, la escena A dibuja el target como recinto y la escena B lo dibuja como
mueble. Los píxeles del target son **byte-idénticos** entre A y B: se dibuja el contexto, se
blanquea el recuadro objetivo y recién después se dibujan el marcador y el target.

```
crops byte-idénticos      36/36
píxeles borrados por el keep-out    0        (ningún objeto de contexto llegó a invadir el recuadro)
fondo de la escena        IDÉNTICO dentro del par; sólo cambia el anillo local
tamaño / posición / orientación / gris    idénticos por construcción
```

Un solo ancho (`W_UNICO = 0.0035`), un solo gris, sin texto.

## 3. Resultado

| | balanced accuracy | abstención | recall recinto | recall mueble |
|---|---|---|---|---|
| TARGET_ONLY | **0,000** | **100 %** | 0,000 | 0,000 |
| FULL_CONTEXT | **0,764** | 5,6 % | 0,750 | 0,778 |

Mejora pareada **0,764**, IC 95 % bootstrap **[0,653 · 0,861]** sobre 10.000 remuestreos por par.

El evaluador se abstuvo en **todos** los recortes aislados. No adivinó: dijo que no se podía decidir.

## 4. Gates pre-registrados

```
G1  BA(TARGET_ONLY)  <= 0.65     PASS   (0.000)
G2  BA(FULL_CONTEXT) >= 0.80     FAIL   (0.764)
G3  mejora           >= 0.20     PASS   (0.764)
G4  IC95 inferior     > 0.10     PASS   (0.653)
G5  recall por clase >= 0.70     PASS   (0.750 / 0.778)
```

Cuatro de cinco. **No se ajustó nada para alcanzar el quinto.**

## 5. Dónde falla

Análisis por receta de contexto, sobre las 72 inferencias con escena completa:

| receta | acierto |
|---|---|
| banda de recintos · mesa con sillas (familia crítica) | **1,00** |
| recinto contra fachada · corredor en L · mueble aislado · dentro de una sala | 1,00 |
| batería · mueble contra fachada · entre corredores · junto a circulación · junto al núcleo | 0,75 |
| recinto con puestos afuera · contra partición · junto a puestos · mesa entre mesas | 0,50 |
| **pod aislado** | **0,00** |

`pod_aislado` y `mueble_aislado` son la misma receta espejo: un rectángulo sin nada pegado. El
evaluador contesta MUEBLE en los dos casos — acierta uno y falla el otro. **Ese par aporta
exactamente cero información**: es un a priori, no una lectura.

## 6. Lo que esto justifica y lo que no

Permitido decir: *en un banco contrafactual controlado donde la geometría local es idéntica, el
contexto visual produce una mejora medible en la identificación de la función del objeto.*

No permitido: que ya se detecten muros, que el VLM generalice, ni que el motor funcione en planos
reales. `PROVIDER_IDENTITY = UNKNOWN`, `PRODUCTION_REPRODUCIBILITY = NOT_PROVEN`.

## 7. Consecuencia

La arquitectura a estudiar sigue siendo **semántica propone · geometría determinista delimita ·
contrato veta**. Con 0,764 y no 0,80, la pieza semántica no puede entrar sin abstención explícita:
tiene que poder decir *no sé*, y el contrato tiene que seguir vetando.
