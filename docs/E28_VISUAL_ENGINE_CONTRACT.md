# E28 — CONTRATO DEL MOTOR VISUAL

E28 **no integra ningún proveedor de ambientación**. Deja escrita la conversación que E29 va a
tener con quien sea, y el vocabulario para decidir si una imagen devuelta sirve.

## Por qué el contrato antes que el proveedor

La pregunta difícil de virtual staging no es *"¿qué API uso?"* sino *"¿cómo sé que la imagen que me
devolvieron sigue siendo ESTA oficina?"*. Si eso no está escrito antes de integrar, se elige
proveedor por la calidad del render y se descubre después que mueve las ventanas de lugar — y una
imagen que miente sobre un inmueble no es material comercial, es un problema legal.

## Invariantes arquitectónicos

Lo que **no puede cambiar** entre la foto original y la ambientada. Es la definición operativa de
"sigue siendo la misma oficina":

`perspective` · `windows` · `columns` · `walls` · `ceiling` · `floor` · `structure` ·
`exterior_views`

## Elementos editables

Lo que sí puede cambiar, porque es la propuesta y no el edificio:

`furniture` · `decoration` · `decorative_lighting` · `plants` · `occupancy` ·
`proposed_partitions` (sólo si la salida las presenta explícitamente como propuesta)

## Interfaz

```python
class VisualStagingProvider(Protocol):
    name: str
    def available(self) -> bool: ...
    def stage_photo(self, request: StagingRequest) -> StagingResult: ...
```

`StagingRequest` lleva `property_id`, `source_asset_id`, `style_preset`, `context`, y las listas
`must_preserve` / `may_edit`. `StagingResult` exige `provider`, `model`, `cost_usd`, `latency_s`,
`seed` y la `request` completa: sin eso un output es irreproducible y no se puede auditar.

## Advertencia honesta

Este contrato **declara** los invariantes; **no los verifica**. Nada en E28 comprueba que una imagen
conserve la perspectiva. `StagingResult.invariants_verified` es `None` y se queda en `None` hasta
que exista una verificación de verdad. Rellenarlo con optimismo sería exactamente el tipo de
promesa que este documento existe para evitar.

## Proveedor actual

`NotConfiguredProvider`. `available()` devuelve `False` y `stage_photo()` lanza
`ProviderNotConfigured`. **Deliberadamente no existe un modo degradado** que devuelva la foto
original haciéndola pasar por ambientada: un pack que miente sobre su contenido es peor que un pack
incompleto.

## Por qué E28 no elige proveedor

Elegir exige medir, y medir exige el experimento de E29: la misma foto, ambientada, evaluada contra
fidelidad, calidad, repetibilidad, costo y latencia. Elegir antes de medir es elegir por el demo
reel del proveedor.
