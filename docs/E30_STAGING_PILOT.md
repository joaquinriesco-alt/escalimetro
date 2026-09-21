# E30 — PILOTO DE AMBIENTACIÓN: qué hay que hacer antes de integrar a nadie

## Estado: NO SE CORRIÓ

No hay proveedor integrado y ninguna imagen se generó. Correr este piloto exige credenciales de
proveedores externos y una decisión de gasto, que son dos de las cosas que no se toman sin que
Joaquín las tome. Lo que sí está listo es el contrato, el vocabulario y la ficha para anotar el
resultado — para que cuando se corra, se corra sobre criterios escritos de antes y no sobre la
impresión que dejaron las imágenes bonitas.

## Por qué la ambientación no es el foso

La investigación de mercado fue clara: el staging está comoditizado. Eso significa dos cosas a la
vez, y ambas importan:

* **no es el foso.** Cualquiera lo compra. El activo escaso es la geometría: entender un plano,
  reutilizarlo, planificar determinísticamente y poder trazar lo que se entregó.
* **sí es producto.** Alto valor percibido, costo marginal bajo. Una imagen ambientada es lo que
  hace que un corredor gane el mandato.

Conclusión operativa: se integra **un** proveedor detrás de la abstracción que ya existe
(`domain/visual.py`), y se conserva la capacidad de cambiarlo. No se integran varios como
complejidad de producto.

## Dónde se usa

1. **Pack de publicación** — UNA imagen hero. Sirve para ganar el listado y para mostrarle al
   propietario cómo se va a comercializar su espacio.
2. **Fit request (Pro)** — ambientación repetida, con el estilo visual elegido, para enseñar cómo
   se vería para ese prospecto.

## Las compuertas

Están en `visual.PILOT_CRITERIA`, en este orden, y la primera es eliminatoria.

| # | Criterio | Qué se mide |
|---|---|---|
| 1 | **FIDELIDAD ARQUITECTÓNICA** | ¿Sigue siendo ESTA oficina? |
| 2 | Calidad de imagen | resolución, luz, mobiliario creíble, artefactos |
| 3 | Repetibilidad | la misma foto y el mismo estilo dos veces |
| 4 | Latencia | segundos por imagen, medidos |
| 5 | Costo | USD por imagen, con la tarifa real del plan |
| 6 | Derechos comerciales | ¿podemos usarlo en material de venta de un tercero? Por escrito |
| 7 | Tasa de fallo | de N intentos, cuántos hubo que descartar |

### La compuerta 1 decide, y no admite matices

Invariantes (`visual.ARCHITECTURAL_INVARIANTS`): perspectiva, ventanas, pilares, muros, cielo,
piso, estructura, vistas al exterior.
Editables (`visual.EDITABLE_ELEMENTS`): mobiliario, decoración, luz decorativa, plantas, ocupación,
tabiques propuestos — y sólo si la salida los presenta explícitamente como propuesta.

> **Una imagen preciosa que movió una ventana está reprobada, no "casi bien".**

Esto no es purismo: el producto entero se sostiene en que lo que entregamos corresponde a la
propiedad real. Una foto ambientada que inventa un ventanal destruye exactamente la confianza que
se está vendiendo, y la destruye en el momento en que el prospecto visita el espacio.

## Protocolo

1. Elegir **el mismo** conjunto de 5–8 fotos reales de oficina vacía, con casos difíciles: pilares
   a la vista, contraluz de fachada, cielo técnico expuesto, planta profunda sin ventanas.
2. Comparar **2 o 3** proveedores. Ni uno (no hay comparación) ni cinco (no se termina).
3. Cada foto × cada estilo × 2 repeticiones. Registrar proveedor, modelo, semilla, latencia y costo
   — `StagingResult` ya tiene los campos.
4. Puntuar la compuerta 1 **antes** de mirar las otras, y por alguien que conozca las fotos
   originales.
5. Anotar en `visual.pilot_sheet()` y decidir.

## Lo que falta construir después de elegir

* el proveedor concreto detrás de `VisualStagingProvider` (una operación: `stage_photo`);
* `PHOTO_STAGED` y `BEFORE_AFTER` en `assets.IMPLEMENTED_KINDS` — hoy están declarados y
  **rechazados**, porque declarar un tipo no es tener la capacidad;
* la **verificación** de invariantes. `StagingResult.invariants_verified` es `None` y no se rellena
  con optimismo. Verificar de verdad es el trabajo difícil y probablemente el más importante:
  hoy el sistema declara los invariantes, no los comprueba;
* el tope por producto: `ONE_OFF` una imagen, Pro varias (`entitlements.LIMITS`, ya escrito).

## Lo que NO hay que hacer

* integrar un proveedor "para probar" y dejarlo en producción sin las compuertas;
* un modo degradado que devuelva la foto original haciéndola pasar por ambientada — hoy es
  imposible por construcción: `NotConfiguredProvider` lanza, y el pack dice `not_generated`;
* alinear la imagen con el layout elegido. Es deseable, es caro y no está agendado. Primero una
  imagen honesta del espacio.
