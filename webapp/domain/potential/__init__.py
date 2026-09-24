"""E17.0 — ESCALÍMETRO VENDE POTENCIAL.

=================================================================================================
Qué cambia y qué NO
=================================================================================================
Hasta E36 el producto era: *tomamos tu oficina vacía y te preparamos el material para publicarla*.
E17.0 abre una capa distinta sobre una pregunta distinta:

    ¿Qué potencial de esta propiedad NO está mostrando su publicación?

El sujeto ya no es una oficina que preparamos nosotros: es un **aviso que alguien ya publicó**, del
que sólo tenemos lo que el aviso muestra. De ahí que esto viva en su propio paquete, con sus
propias tablas y su propia ruta, y que no toque ni una línea del motor de layouts.

El motor no se elimina ni se degrada: pasa de ser *el producto* a ser una **capacidad** que se
invoca cuando el material la habilita. `plans.py` es el adaptador, y su regla es una sola: no
reimplementa nada, no cambia contratos, sólo pregunta y traduce.

=================================================================================================
Las dos promesas que el código tiene que sostener
=================================================================================================
**El score es trazable.** Cada punto sale de un criterio con nombre, una medición registrada y un
peso escrito. No hay un número redondeado a ojo en ninguna parte, y el informe puede mostrar la
aritmética completa. Si un criterio no se puede medir con lo que hay, no se inventa: se marca
`NO_APLICA` y se reparte su peso entre los que sí aplican.

**El score NO predice ventas.** Mide qué tan bien la publicación muestra el potencial, que es una
propiedad del AVISO, no del mercado. No hay aprendizaje, ni correlación con leads, ni promesa de
conversión — y la interfaz lo dice con esas palabras. Prometer conversión con una heurística sobre
cuatro fotos sería vender un número que no tenemos.

=================================================================================================
Regla de veracidad
=================================================================================================
Toda visualización generativa preserva el inmueble real: no se mueven ventanas, no se borran
pilares, no se agrandan espacios, no se inventan vistas ni terrazas. Lo que se genere se etiqueta
`CONCEPTUAL_VISUALIZATION` y se muestra como «Visualización referencial de potencial.». En esta
iteración la generación **no está conectada**: el contrato existe con estado `NOT_AVAILABLE`, que
es preferible a una demo simulada que alguien pueda confundir con el inmueble.
"""
