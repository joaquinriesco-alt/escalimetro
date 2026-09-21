# E28 — QUÉ SIGUE

## Dónde quedamos

Una propiedad en Escalímetro ya no es sólo una planta. Puede contener plano original, caso
geométrico, plano comercial, layouts A/B/C, fotos y un pack exportable. Lo que **no** contiene
todavía es lo único que justifica el precio de USD 99 frente a un corredor: **imágenes del espacio
real ambientado**.

Un pack de E28 muestra un plano y tres layouts. Eso ya es más de lo que la mayoría de los avisos
tiene, pero sigue siendo un plano. La foto ambientada es la pieza que convierte "esto es una planta
libre de 540 m²" en "así se vería tu oficina acá".

## E29 — VIRTUAL STAGING V1

**El experimento mínimo, y nada más que eso:**

```
PHOTO_ORIGINAL  ──►  PHOTO_STAGED
```

Una foto. La misma foto. Amoblada. Sin video, sin 3D, sin before/after animado, sin recorrido.

### Las cinco compuertas

Ninguna es opcional, y conviene medirlas **antes** de elegir proveedor, no después.

| compuerta | la pregunta | cómo se mide |
|---|---|---|
| **FIDELITY** | ¿sigue siendo esta oficina? | los invariantes de `E28_VISUAL_ENGINE_CONTRACT.md`, revisados por una persona sobre pares original/ambientada. Es la compuerta que decide: una imagen bonita que movió una ventana está **reprobada**, no "casi bien" |
| **QUALITY** | ¿la publicarías? | juicio de Joaquín, misma escala A/B/C de la revisión de layouts |
| **REPEATABILITY** | ¿dos corridas dan resultados comparables? | misma foto, mismo preset, N corridas; si el resultado es una lotería, no es un producto |
| **COST** | ¿cuánto cuesta un pack? | USD por foto × fotos por propiedad, contra los ~USD 99 hipotéticos |
| **LATENCY** | ¿cuánto espera el cliente? | minutos por foto; define si el flujo es síncrono o hay que avisar por mail |

### Cómo empezar sin gastar un ciclo entero

1. Juntar 10–15 fotos reales de oficinas vacías (las de Providencia sirven; hacen falta más).
2. Probar **dos o tres** proveedores sobre las **mismas** fotos, con el mismo preset.
3. Puntuar cada resultado contra las cinco compuertas. Sin adornos: una tabla.
4. Recién entonces integrar uno detrás de `VisualStagingProvider`.

El orden importa: integrar primero y evaluar después es cómo se termina casado con un proveedor
que falla en FIDELITY, que es justamente la compuerta que no se puede negociar.

### Lo que E29 **no** debe hacer

Video, 3D, NeRF, gaussian splatting, walkthrough, limpieza automática de planos, photo-to-floorplan,
residencial, retail, billing. Nada de eso antes de saber si una sola foto ambientada pasa las
compuertas.

## Lo otro que hay que resolver, y no es de IA

**Roles.** Hoy la separación cliente/interno es de rutas y plantillas, con una sola cuenta
compartida. Antes de que un cliente real entre, eso tiene que ser autenticación de verdad. Es
trabajo aburrido y es bloqueante: no depende de E29 y puede hacerse en paralelo.
