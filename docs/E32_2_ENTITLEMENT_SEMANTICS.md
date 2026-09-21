# E32.2 — MODELO DE DERECHOS: una compra cubre una propiedad

## El error que esto corrige

E30 modeló ONE_OFF como una propiedad de la **cuenta**, con un tope de `properties: 1`. Sin querer,
eso afirmaba:

> «Ya tenés una propiedad. Para preparar otra, pasate a Escalímetro Pro.»

No es el negocio. Un corredor chico compra un Pack por cada oficina que quiere publicar. Tres
oficinas son tres Packs de ~USD 100, no una suscripción.

Y peor: vendía Pro por la razón equivocada. **Pro no existe para permitirte tener una segunda
propiedad.** Existe para que puedas seguir trabajando las que ya tenés — un prospecto distinto cada
semana, A/B/C, regeneración, marca del prospecto.

## Tres cosas que ahora no se mezclan

| | Qué decide | Dónde vive |
|---|---|---|
| **Operador** | qué puede hacer Joaquín en el LAB | ninguna regla: es un laboratorio |
| **Compra** | si se puede preparar otra propiedad | `pack_grants` |
| **Propiedad** | qué se puede hacer con *esta* oficina | `properties.product` |

## El modelo

```
CUENTA
  ├── PROPIEDAD A ── concesión #1 (ONE_OFF)   → plano, 1 alternativa, 1 imagen, pack
  ├── PROPIEDAD B ── concesión #2 (ONE_OFF)   → lo mismo, con otra compra
  └── PROPIEDAD C ── concesión #3 (PRO)       → prospectos, A/B/C, regeneración…
```

Una concesión (`pack_grants`) está `AVAILABLE` o `ASSIGNED`. Se usa **una** vez: reasignarla sería
dos propiedades con una sola compra, y hay test.

No hay dinero: una concesión nace `SIMULATED_LAB` (el LAB, para probar), `PURCHASE` (el día que
haya cobro) o `LEGACY` (migración).

## Capacidades por propiedad

```python
entitlements.allows(property_id, entitlements.PROSPECT_FIT_REQUESTS)
entitlements.require(property_id, capability)      # lanza EntitlementError
entitlements.limit(property_id, "layouts_per_pack")
```

Las tres exigen `property_id` — llamarlas sin él es un `TypeError`, y hay test. Preguntar por la
cuenta era exactamente lo que producía el efecto global equivocado.

`MULTIPLE_PROPERTIES` **ya no existe** como capacidad: tener otra propiedad no es una capacidad de
producto, es otra compra.

## Dos bloqueos que no son el mismo

| | Qué significa | Qué ofrecer |
|---|---|---|
| `grants.PackRequired` | no queda ningún Pack sin usar | **otro Pack** |
| `entitlements.EntitlementError` | esta propiedad está cubierta por un Pack y pedís algo de Pro | **Pro**, por lo que hace |

`PackRequired` **no** hereda de `EntitlementError`, a propósito y con test: confundirlos era el
error comercial.

## La copia del cliente

> **Necesitás otro Pack para preparar una nueva propiedad**
> Cada Pack de publicación corresponde a una propiedad. Podés preparar otra propiedad con un Pack
> nuevo, o usar Escalímetro Pro si trabajás un portafolio de manera recurrente.

Y Pro se describe por su valor: *«No es "la forma de tener otra propiedad". Sirve para seguir
trabajando las que ya preparaste.»*

## El LAB

Cada propiedad nueva del LAB crea **su propia compra simulada** y la asigna. Por eso el operador
puede crear veinte propiedades ONE_OFF: son veinte Packs, no una violación de plan. No hay tope y
tampoco hace falta una excepción que explicar.

El formulario tiene **Producto simulado** (Pack / Pro) y cada propiedad lo puede cambiar desde su
Resumen. Cambiarlo **no toca a ninguna otra**.

`/lab/config` y `/settings` ya no dicen «modo de producto»: dicen **producto por defecto de una
propiedad de prueba nueva**, y aclaran que no cambia nada de lo ya creado.

## Migración

Aditiva. `properties.product` se añade con default `ONE_OFF`; cada propiedad sin concesión recibe
una `LEGACY` ya asignada. Default conservador y documentado: **no se infiere Pro** por tener muchos
outputs históricos. Idempotente, con test. Nada se pierde: casos, assets, layouts, fotos, intentos
de ambientación y notas quedan intactos.

## Limitaciones

1. **Sin cobro.** Una concesión `PURCHASE` se crea a mano; no hay checkout ni facturas, y §16 pide
   que siga así.
2. **Pro se modela por propiedad**, no como suscripción de cartera. Alcanza para las capacidades;
   el día que haya cobro recurrente habrá que decidir qué propiedades cubre una suscripción y con
   qué tope.
3. **Sin roles** — la deuda de siempre: quien entra ve todo.
4. La superficie de cliente no puede comprar: sin Pack disponible, informa y para ahí.
