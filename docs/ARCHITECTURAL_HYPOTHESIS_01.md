# ARCHITECTURAL_HYPOTHESIS_01

**STATUS: UNVALIDATED_BY_HUMAN_REVIEW**

> "Program-independent circulation may be a primary source of unallocated area and poor architectural
> quality."

## Qué dice

La espina de circulación se genera ANTES de conocer el programa. En `e07/engine.py`:

```
plan = build_spine(self.shell, self.feats, strat, self.grid)   # sólo shell + features + estrategia
els  = F.spine_elements(plan)
brs  = F.branch_candidates(...)
raw  = F.generate_candidates(..., self.program, ...)           # el programa entra DESPUÉS
```

`build_spine(shell, feats, strat, grid)` no recibe el programa. Los pasillos quedan fijados por la
geometría del shell y por el patrón de la estrategia; recién entonces los rectángulos del programa se
anclan a lo que ya existe. La hipótesis es que ese orden produce circulación que no sirve a nadie en
particular, y que el área que sobra —151.8 m² sin asignar y 65.9 m² de bolsillos en la corrida de E25
sobre GPS 403/A— es en buena parte consecuencia de eso, no de la cáscara.

## Por qué NO se corrige en E26

Porque todavía no está validada por nadie que sepa mirar una planta. Es una hipótesis derivada de leer
el código y las métricas; suena razonable y podría ser falsa. Invertir un ciclo en rediseñar la
circulación antes de que un arquitecto diga qué está mal en estas plantas sería exactamente el error
que E23-E25 vinieron corrigiendo: optimizar contra una métrica en vez de contra el problema.

E26 no la implementa. E26 pone las plantas delante de Joaquín.

## Qué la validaría o la mataría

Si en la primera revisión humana aparecen repetidamente `sin_pasillo_legible`, `espacio_desperdiciado`
o `circulacion` como `reason_tags` dominantes, y las notas libres describen pasillos que no llevan a
ninguna parte o franjas muertas junto a la espina, la hipótesis gana peso.

Si en cambio los problemas dominantes son de otro orden —`sin_espesor_de_tabique`,
`privados_mal_ubicados`, `mala_adyacencia`— entonces la circulación no es el cuello principal y este
documento queda archivado sin implementarse.

## Registro

* Detectada durante E26 leyendo el orden de llamadas del motor.
* No se modificó `build_spine`, `spine_elements`, `branch_candidates` ni ningún parámetro de
  circulación en E26 (§2 lo prohíbe explícitamente).
* Decidir después de la revisión humana, no antes.
