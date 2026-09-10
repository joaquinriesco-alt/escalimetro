# PLAN CLEANING / OCCUPIED PLAN INTERPRETATION

```
STATUS: DEFERRED AFTER MVP V1
```

Interpretar automáticamente una planta **amoblada** —separar arquitectura de mobiliario, borrar un
layout previo, decidir si un rectángulo es un escritorio o un recinto— queda **fuera del camino
crítico de V1** y se retoma, si corresponde, en V2.

## Qué se aprendió (E17–E22)

Seis ciclos atacaron el problema desde ángulos distintos, con banco contrafactual, pre-registro
hasheado y gates congelados antes de mirar resultados. Ninguno se borra: son la razón documentada
por la que esto se difiere.

| ciclo | variable movida | resultado |
|---|---|---|
| E17 | representación de **ancho de trazo** | spike de representación; no se conectó al runtime |
| E18 | representación de **topología estructural** | spike; no se conectó al runtime |
| E19 | **contexto** visual como información semántica | el contexto SÍ aporta: +0.625 sobre el target aislado, IC95 [0.500, 0.750] |
| E19.1 | **una imagen por evaluador** | la señal replica; la **calibración no**: recall ARCH 0.750 → 0.472 |
| E20 | **contrato set-valued** (`possible_roles`) | cobertura 0.986, selectividad 0.250; 34 de 36 recintos reciben el conjunto completo |
| E21 | **contrato QA-critic** (juzgar una afirmación) | `ERROR_CATCH_RATE` 0.5694 vs gate 0.80; veredicto E21-D, asimetría por rol |
| E22 | **evaluador** (opus → sonnet) | invalidado por desviación de protocolo (7/144 usaron Bash); reclasificado E22-E |

**El hallazgo que importa para producto:** en E19.1, E20 y E21 el mismo sesgo direccional
ARCH → FURN aparece con tres contratos de salida distintos. Frente a un rectángulo sin sillas, el
evaluador contesta *mobiliario*. Las sillas fueron la única señal visual tratada como decisiva en
los tres ciclos.

**Lo que NUNCA se varió** en los seis ciclos: la representación visual. El banco de tres tonos y
ancho único es idéntico desde E19. Si V2 retoma esta línea, ésa es la variable pendiente.

## Reglas mientras esté diferido

- **No borrar** código, tests, ramas ni documentación de E17–E22.
- **No integrar** sus salidas experimentales en runtime. Hoy `src/escalimetro/` no importa nada de
  `cases/generalization/`, y así debe seguir.
- **No continuar** la línea: sin E22.1, sin otro evaluador, sin otro prompt semántico, sin otro
  contrato QA, sin otro banco equivalente.
- Se puede **referenciar históricamente**. No debe condicionar la entrega de V1.

## Herramientas candidatas para V2

visión, ancho de línea, topología, contexto semántico, OCR, vectorización, métodos híbridos.
Ninguna está en el camino crítico de V1.
