# E30 — QUÉ SIGUE

Por orden de lo que desbloquea más, no de lo que es más entretenido.

## 1. Roles (RBAC) — bloquea todo lo demás

Hoy hay **una cuenta compartida**. Los derechos de producto (`entitlements`) cortan por
**capacidad**, no por **identidad**: responden "¿este producto incluye esto?", no "¿quién sos?".
Mientras eso siga así:

* un cliente autenticado puede escribir `/review` o `/case/<id>` y ver la cocina;
* no puede haber enlace público de propuesta, porque no hay forma de exponer una propiedad sin
  exponerlas todas;
* no puede haber dos corredoras en el mismo despliegue.

Mínimo honesto: usuarios, una organización, dos roles (`operator` / `customer`), y los blueprints
separados que ya existen colgando de ellos. Nada de SSO ni jerarquías.

## 2. Correr el piloto de ambientación

Ver `E30_STAGING_PILOT.md`. Es lo que le falta al pack para estar completo — hoy siempre le falta
la imagen hero del §8. Necesita credenciales y decisión de gasto.

## 3. Medir antes de prometer

Nada del producto promete arriendo más rápido ni mejor precio, y así debe seguir hasta que exista
el dato. Lo barato de medir primero, porque ya se registra:

* cuántos fit requests genera una propiedad preparada (la tesis de Pro entera está ahí);
* cuántas veces el motor devuelve `SEARCH_EXHAUSTED` y con qué programas;
* cuál de los cuatro presets se elige, y cuál se cambia después.

## 4. Seleccionar corrida al publicar

Hoy se publica la última del fit. Con regeneración habilitada en Pro, hace falta poder decir "andá
a la del martes".

## 5. Facturación

`entitlements.mode()` es el único punto a conectar. Deliberadamente no se construyó: §13.
