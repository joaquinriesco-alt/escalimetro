"""E37 — INTERNAL RECONSTRUCTION LAB: el instrumento para aprender CREAR PLANO (D-001).

No es el motor que reconstruye plantas: es el banco de pruebas donde se comparan motores. Un
proyecto junta fotos, video y datos declarados, y un plano real opcional que queda oculto; cada
motor registrado produce una corrida inmutable con una representación estructurada del plano; una
persona la califica, la corrige en lenguaje natural —lo que crea una corrida hija— y sólo al final
revela el plano real para compararlo.

Módulos:

* `contract`     el contrato v1 de la representación estructurada, y su validación;
* `render`       el SVG que se dibuja DESDE esa representación, nunca desde una imagen generada;
* `projects`     proyectos, inputs, datos declarados, cierre y bitácora;
* `groundtruth`  el plano real oculto. Ningún módulo que arme la entrada de un motor lo importa;
* `runs`         corridas, cola, calificaciones, comparación y métricas;
* `engines`      el registro de motores y sus adaptadores.
"""
