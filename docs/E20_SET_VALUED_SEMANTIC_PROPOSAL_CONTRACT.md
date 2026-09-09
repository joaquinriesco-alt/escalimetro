# E20 — CONTRATO DE PROPUESTA SEMÁNTICA SET-VALUED

> Variable única: el **contrato de salida**. Banco, imágenes, IDs y ground truth byte-idénticos a
> E19/E19.1. Una imagen por evaluador. **El motor no cambia.**
> Veredicto: **E20-B — HIGH COVERAGE / LOW SELECTIVITY**. `STOP PRODUCT PATH`.

## 1. Qué se cambió

E19.1 obligaba a elegir una clase. E20 permite responder un **conjunto**: sólo recinto, sólo mueble,
ambas, o ninguna. Nada más se movió.

## 2. Resultado

| métrica | valor | gate | |
|---|---|---|---|
| TRUE_ROLE_COVERAGE overall | **0,986** | ≥ 0,95 | PASS |
| TRUE_ROLE_COVERAGE ARCH | **0,972** | ≥ 0,90 | PASS |
| TRUE_ROLE_COVERAGE FURN | **1,000** | ≥ 0,90 | PASS |
| DANGEROUS_OMISSION overall | **0,014** | ≤ 0,05 | PASS |
| SINGLETON_PRECISION | **0,944** | ≥ 0,80 | PASS |
| EMPTY_RATE | **0,000** | ≤ 0,10 | PASS |
| **SINGLETON_RATE** | **0,250** | ≥ 0,60 | **FAIL** |
| **BOTH_RATE** | **0,750** | ≤ 0,40 | **FAIL** |

MEAN_SET_SIZE 1,75. IC 95 % (bootstrap por par): cobertura [0,958 · 1,000], BOTH [0,667 · 0,833].

## 3. Por qué la cobertura es alta

Porque el evaluador casi siempre responde "ambas".

```
                 sólo ARCH   sólo FURN   ambas   vacío
es recinto            1          1        34       0
es mueble             0         16        20       0
```

**34 de 36 recintos reciben el conjunto completo.** De los 18 singletons, **16 son mueble** y sólo 2
son recinto —uno de ellos equivocado, el único fallo de cobertura del ciclo (`PAR28`,
`junto_al_núcleo`, leído como mueble a secas)—.

La asimetría es el hallazgo: el evaluador **se compromete a decir "mueble"**, y **nunca se compromete
a decir "recinto"**. Es el mismo sesgo de E19.1, ahora visible sin que la métrica agregada lo oculte.

## 4. Qué contexto sí decide

Acierto por receta: `mesa_con_sillas` es la única con **0,00 de BOTH y 8/8 singletons**. Ocho de las
dieciséis recetas dan **BOTH en el 100 %** de sus casos. Las sillas son prácticamente el único signo
que basta para descartar una hipótesis; todo lo demás —corredor al lado, banda de recintos, núcleo,
fachada— deja las dos vivas.

## 5. Interpretación permitida

> El contrato set-valued **preserva** el rol verdadero (0,986) y **no reduce** la incertidumbre lo
> suficiente para ser operativamente útil: pide revisar las dos hipótesis en tres de cada cuatro
> objetos.

Es exactamente el sistema trivial contra el que advertía el §9 del prompt, atenuado: no responde
"ambas" siempre, pero sí el 75 % de las veces. `STOP PRODUCT PATH`. GPS y RES no se abrieron.
El tercer plano sigue cerrado.
