# E16 — QUÉ NECESITA EL PRÓXIMO CASO (CROSS-DRAWING)

**E16 no se ejecuta aquí.** Este documento sólo dice qué hace falta para poder ejecutarlo, para que
conseguir el insumo no dependa de recordar la conversación.

## Por qué otro dibujo y no otra oficina

E14 probó generalización **intra-drawing**: la Oficina 401 salía de la misma lámina que la 403, con
el mismo estilo gráfico, las mismas convenciones, la misma resolución y el mismo edificio. Es la
mitad fácil del problema, y así quedó clasificado.

Lo que sigue sin medirse es si el pipeline sobrevive a **otro dibujante**: otra paleta, otra
tipografía, otra manera de rayar el núcleo, otra convención de leyenda, otro DPI. Ahí es donde vive
el acoplamiento que ningún grep encuentra — el que está en los umbrales, no en los literales.

Un segundo caso del mismo aviso no aporta nada nuevo a esa pregunta.

## Requisitos del insumo

### Obligatorios

| | requisito | por qué |
|---|---|---|
| 1 | **Imagen original** en PDF, JPG o PNG | es el input real; no una captura recortada |
| 2 | **Otra fuente**: otro corredor, otro arquitecto, otro portal | es el punto del experimento; misma fuente = otro intra-drawing |
| 3 | **Unidad objetivo identificable** — un rótulo, un color, un número | sin eso no hay qué localizar |
| 4 | **Perímetro interpretable** — el límite de arriendo se puede leer, sea por muro o por color | si un humano no puede trazarlo, la máquina tampoco |
| 5 | **Acceso visible o corregible** — un arco de puerta, un hueco, o algo que un humano pueda marcar con un click | E14 mostró que sin acceso el shell queda NOT_READY, y esa es la respuesta correcta |
| 6 | **Núcleo y pilares visibles** | el solver los necesita como obstáculos |
| 7 | **Sin ediciones previas de Escalímetro** | un plano que ya pasó por aquí no prueba nada |

### Deseables

| | requisito | qué se pierde sin él |
|---|---|---|
| 8 | **Superficie publicada** de la unidad | sin ella la escala queda UNKNOWN y hay que confirmarla de otra forma; el pipeline lo soporta, pero el fit no será comparable |
| 9 | Una **cota, barra de escala o dimensión conocida** | sería la primera vez que la escala no fuese inferida: pasaría de LOW a MEDIUM o HIGH |
| 10 | Resolución mayor a 72 dpi | E14 falló la localización automática con un rótulo de contraste 140 a 72 dpi |
| 11 | Una unidad de **superficie comparable a la 403** (400–700 m²) | permitiría probar el camino de FIT, que E14 no llegó a recorrer |

### Qué NO hace falta

- No hace falta que sea en Chile ni de un edificio conocido.
- No hace falta que el programa quepa. Un `NO_FIT` explicable vuelve a ser un buen resultado.
- No hace falta plano CAD, BIM ni nada editable: el input es una imagen publicada.

## Cómo se ejecutará E16

El protocolo ya está escrito en `docs/E14_GENERALIZATION_PROTOCOL.md` y las herramientas existen. La
corrida es mecánica:

```bash
# 0 · congelar el motor sobre el baseline vigente de E15
#     cases/generalization/E15/GENERIC_ENGINE_BASELINE.json
# 1 · AUTO
PYTHONPATH=src python -m escalimetro.cli run --case cases/003_<fuente>_<unidad> --out <caso>/outputs/auto
# 2 · ASSISTED, máximo 10 operaciones, sólo si AUTO no alcanza
# 3 · nominal con el MISMO programa, sin adaptar
# 4 · barrido de robustez con los rangos de E06 sin tocar
# 5 · verificar el congelamiento
```

**Cambia una sola cosa respecto de E14**: el baseline congelado es el de E15, no el de E14. El hash
de E14 describe un motor anterior al contrato genérico de caso; sigue siendo el hash correcto de
aquel experimento y no debe reutilizarse como estado actual.

## Lo que E16 sí podrá afirmar y E14 no

Si el caso cumple los siete requisitos obligatorios y el pipeline lo procesa sin tuning, E16 podrá
decir **cross-drawing generalization**, que es una afirmación de otra categoría.

Si falla, fallará por una razón concreta que hoy no se puede anticipar, y esa razón vale más que el
resultado: es lo primero que este proyecto sabrá sobre el mundo fuera de un solo aviso.

## Qué NO se toca hasta entonces

- **El OCR.** Ajustarlo para que lea el rótulo de la 401 sería afinar contra otro rótulo de la misma
  lámina: intra-drawing overfit puro. La falla de localización de E14 queda como evidencia para
  contrastar con el caso nuevo.
- **El solver.** Los 166 s del nominal de la 401 son otro experimento.
- **El programa.** Que el motor proponga un programa proporcional cuando el pedido no cabe es una
  decisión de producto, no una corrección técnica. Sigue siendo hipótesis.
