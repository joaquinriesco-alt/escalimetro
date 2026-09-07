# CONTRATO DE SEGMENTACIÓN — ESCALÍMETRO E16.6

## Qué es la máscara

`GeometryExtractor.extract(mask)` hace `cv2.findContours(mask, RETR_EXTERNAL)` y toma el contorno
mayor. **Ese contorno es el perímetro del inmueble.** De ahí que la máscara sea, sin ambigüedad:

> **C — la huella LLENA delimitada por el perímetro exterior.**

No es el área interior arrendable, no es el espacio libre, no es la superficie útil. El núcleo, los
baños y las exclusiones se extraen aguas abajo por su cuenta y se restan después
(`shell_adapter`: `usable = perímetro − core`). Un agujero en la máscara no llega a la geometría:
`RETR_EXTERNAL` lo ignora.

Entender esto era el requisito de §11 y condiciona todo lo demás: cualquier método de segmentación
whole-shell tiene que producir una huella cerrada y llena, no una silueta del espacio vacío.

## Dos problemas, no dos parámetros

| | MULTI_UNIT | WHOLE_SHELL |
|---|---|---|
| pregunta | ¿dónde está la unidad dentro de la lámina? | ¿qué encierran los muros exteriores? |
| punto de partida | el rótulo leído por OCR | no existe, y no puede existir |
| técnica | crecer región desde una semilla | conectividad con el exterior de la hoja |
| proveedor | `opencv_color` / `opencv_flood` | `whole_shell` |
| robusto frente al interior | no: el relleno debe ser uniforme | **sí, por construcción** |

`opencv_flood` resuelve el primero y lo resuelve bien. Reusarlo para el segundo fue el error que
E16.6 corrigió: sobre un plano en blanco y negro no hay "un píxel interior conocido", y elegir uno
—a mano o por heurística— reintroduce la intervención que E16.5 acababa de eliminar.

## Cómo funciona el método whole-shell

```
1. tinta        = gris < wall_thresh          (no se distingue muro de mueble: no hace falta)
2. cierre       = dilatar gap_px/2            (para que el exterior no se filtre por una puerta)
3. exterior     = flood desde los bordes de la imagen, sin cruzar tinta
4. interior     = NOT exterior                (tinta + todo lo que la tinta encierra)
5. huella       = componente mayor de interior
6. rellenar contorno externo, erosionar gap_px/2 para deshacer el cierre
7. acotar a la región de interés que entregó la localización
8. aceptar o rechazar según el contrato de abajo
```

**Por qué es genérico y no un parche.** La propiedad que usa —"el fondo de la hoja es alcanzable
desde el borde; el edificio no"— no depende del color, ni del contenido interior, ni de qué
anotaciones traiga la lámina. Mobiliario, textos, marcas de agua, núcleo y baños quedan adentro **por
construcción**: no hay que reconocerlos, ni clasificarlos, ni borrarlos. Es exactamente lo que §12
pedía: robustez frente a CLASES de anotación gráfica, no frente a instancias concretas.

## Contrato de aceptación

Declarado **antes** de correr ningún caso real, y validado sobre fixtures sintéticos:

| métrica | criterio | qué descarta |
|---|---|---|
| `mask_pixels` | > 0 | nada encerrado por tinta |
| componentes conexas | exactamente 1 | huella partida en pedazos |
| `roi_frac` = área / área de la ROI | 0,10 ≤ x ≤ 1,0 | una mota de tinta encerrada |
| `fill` = área / área de su propio recuadro | ≥ 0,30 | marcos delgados y formas dispersas |

Si no se cumple, **la máscara se descarta y se devuelve vacía con `confidence 0.0`** — no se entrega
una máscara dudosa con confianza baja para que alguien la use igual.

`max_roi_frac` vale 1,0 a propósito. Un primer borrador puso 0,98 y un fixture genérico lo desmintió
—una planta sola en la hoja, sin título, ocupa el 100 % de la extensión de tinta— **antes** de que
este código viera ningún caso real. Ése es el valor de probar en fixtures primero.

## Procedencia

La máscara registra `provider`, `provenance`, y en `notes` los parámetros y las cuatro métricas de
aceptación con su veredicto. No se finge `opencv_flood` cuando corrió otro método.

## Qué NO resuelve este ciclo

Geometría, escala, semántica de superficie útil, acceso, solver, programa. Si la segmentación pasa y
lo siguiente falla, ése es el resultado del ciclo, no una invitación a seguir arreglando.
