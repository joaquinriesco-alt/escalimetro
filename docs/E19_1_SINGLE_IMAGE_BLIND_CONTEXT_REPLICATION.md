# E19.1 — REPLICACIÓN CON UNA IMAGEN POR EVALUADOR

> Replicación, no optimización. **Nada del banco de E19 se tocó.** Variable única: `BATCH_SIZE`, de 6 a 1.
> Veredicto: **B — SINGLE-IMAGE CONTEXT REPLICATION PARTIAL**.

## 1. Qué se probó

E19 evaluaba seis imágenes por llamada. E19.1 repite las **mismas 108 imágenes** con **un evaluador
nuevo por imagen**, sin memoria entre llamadas. Banco, prompt, IDs, ground truth y scoring
byte-idénticos: `bench 2b3e2eb0…`, `prompt 2ac0dac6…`, 108/108 imágenes con el mismo SHA, 36/36
crops byte-idénticos dentro del par, 0 px de fuga.

## 2. Resultado

| | E19 · batch 6 | E19.1 · batch 1 | Δ |
|---|---|---|---|
| BA FULL_CONTEXT | 0,764 | **0,681** | **−0,083** |
| recall recinto | 0,750 | **0,472** | **−0,278** |
| recall mueble | 0,778 | **0,889** | +0,111 |
| abstención FULL_CONTEXT | 5,6 % | **0,0 %** | −5,6 pp |
| BA TARGET_ONLY | 0,000 | 0,056 | +0,056 |
| abstención TARGET_ONLY | 100 % | **88,9 %** | −11,1 pp |
| acuerdo intra-imagen | 1,00 | **0,67** | −0,33 |

IC 95 % de BA FULL_CONTEXT: **[0,569 · 0,792]**.
Mejora sobre TARGET_ONLY: **0,625**, IC 95 % **[0,500 · 0,750]**.
IC 95 % del Δ contra E19: **[−0,208 · +0,042]** — incluye el cero.

## 3. Gates

```
A1  BA_FULL >= 0.80          FAIL   (0.681)
A2  recall recinto >= 0.70   FAIL   (0.472)
A3  recall mueble >= 0.70    PASS   (0.889)
A4  abstención <= 0.10       PASS   (0.000)
A5  IC95 inferior >= 0.70    FAIL   (0.569)
C   |ΔBA| >= 0.10            NO     (0.083, umbral pre-registrado 0.10)
```

**No se declara C.** El umbral de materialidad estaba pre-registrado en 0,10 sobre la BA y el Δ
observado es 0,083, con un intervalo que cruza el cero.

## 4. Lo que sí cambió, y es lo interesante

23 de las 72 respuestas con contexto cambiaron. **16 de esas 23 son ARCH → FURN.** Todas las recetas
que perdieron exactitud son de recinto; todas las que ganaron son de mueble:

```
junto_al_núcleo         0,75 → 0,00        contra_partición    0,50 → 1,00
batería_de_recintos     0,75 → 0,25        junto_a_puestos     0,50 → 1,00
dentro_de_una_sala      1,00 → 0,50        junto_a_circulación 0,75 → 1,00
entre_corredores        0,75 → 0,25        mueble_contra_fachada 0,75 → 1,00
```

La evidencia textual dice por qué: sin lote, el evaluador razona *"closed single-line rectangle with
no door opening, no wall poché"* y concluye mueble. Con lote podía calibrar el grosor y la convención
de puertas comparando imágenes entre sí. **El batching no inflaba la BA agregada de forma material;
sostenía la calibración.**

Dos señales secundarias apuntan a lo mismo: la abstención cae de 5,6 % a 0 % (el evaluador ya no
declara duda), y el acuerdo intra-imagen en los recortes aislados cae de 1,00 a 0,67 (la misma imagen
recibe respuestas distintas en llamadas distintas).

## 5. Consecuencia

La señal contextual **se replica**: la mejora sobre el objeto aislado sigue siendo 0,625 con
IC 95 % [0,500 · 0,750]. Lo que no se replica es la calibración. Una señal semántica que, evaluada
imagen por imagen, tiene recall de recinto 0,47 y **nunca dice que no sabe** no puede entrar como
propuesta detrás de un contrato: el contrato tendría que vetar la mitad de sus recintos.

`STOP` antes de integración, como manda el §10 del prompt para el veredicto B. La decisión siguiente
es de arquitectura, no de experimento.
