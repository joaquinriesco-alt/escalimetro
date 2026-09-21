# E33 — ESCALÍMETRO LAB: la experiencia simple

## El problema

E32 construyó una herramienta para un ingeniero, no un producto. Once entradas de menú —Plantas,
Revisión, Propiedades, Revisiones JSON, Ambientación, Producto, Mis propiedades, Mi marca, Pack de
publicación, Benchmark, Configuración— y siete pestañas por propiedad, para una aplicación cuyo
flujo real es: **subo una propiedad, miro el resultado, digo si sirve.**

Eran varias aplicaciones dentro de una aplicación.

## La regla

> Subo una propiedad, veo Pack 1, hago Pack 2 para un cliente y califico si el resultado fue
> excelente, bueno, malo o pésimo.

Si para una operación normal hay que entender *case*, *run*, *asset type*, *entitlement*,
*provider*, *benchmark* o *manifest*, la UX falló.

## Navegación

| Antes | Ahora |
|---|---|
| Plantas · Revisión · Propiedades · Revisiones (JSON) · Ambientación · Producto · Herramienta técnica · chip de plan · cola | **Mis propiedades · Ajustes** |

Y dentro de una propiedad: siete pestañas → **una página**.

## Rutas

| Ruta | Qué es |
|---|---|
| `/lab/` | Mis propiedades: tarjetas con foto, nombre y estado |
| `/lab/new` | Crear: datos, plano, fotos. La marca ya está configurada |
| `/lab/p/<id>` | **La** página: insumos · Pack 1 · Pack 2 · evaluaciones |
| `/lab/p/<id>/revisar-plano` | Puente a la herramienta de medición, con la vuelta marcada |
| `/lab/ajustes` | Marca, evaluaciones, ambientación, herramientas técnicas |
| `/lab/ajustes/evaluaciones` | El resumen de aprendizaje |
| `/lab/debug` | **Backstage**: todo el tooling de E27–E32 |

Las rutas de pestañas de E32 (`/material`, `/prospectos`, `/pack`, `/actividad`…) redirigen a la
página única para no romper enlaces guardados.

## Pack 1 — Publicación

Tres pasos y nada más:

```
✓ Plano comercial     Listo        listo para presentar
✓ Layout tipo         Listo        una distribución representativa
○ Ambientación        Pendiente    pendiente de validar proveedor
```

**Un solo botón**, «Generar Pack 1», hace todo lo que puede hacer solo y se detiene donde hace
falta una persona — por ejemplo a medir la escala, que no se puede automatizar. Nunca falla
ruidosamente en el medio: dice qué hizo y qué quedó.

## Pack 2 — Propuesta para un cliente

Formulario en la misma página: cliente, personas, forma de trabajo, estilo visual. El programa
detallado, el logo y el color viven detrás de **«Más opciones»**.

No hay que ir a Ajustes a poner Pro: pedir una propuesta habilita el producto que la permite. El
tope comercial de verdad sigue vivo en la superficie de cliente, que es donde corresponde.

Varias propuestas conviven (Falabella, NotCo, Banco X) sin pisarse.

## Estados

| Sí | No |
|---|---|
| Pendiente · Preparando · Necesita revisión · Listo · No pudimos generarlo | `SEARCH_EXHAUSTED` · `LAYOUTS_READY` · `NEEDS_CONFIRMATION` · `PACK_READY` · `PROVIDER_NOT_APPROVED` |

Los códigos técnicos existen y viven en **«Ver detalle técnico»**, colapsado al final.

## Evaluaciones

Cuatro botones bajo cada resultado: **Excelente · Bueno · Malo · Pésimo**. Ni estrellas, ni 1–10,
ni deslizadores: una escala de diez puntos parece más información y es menos, porque nadie
distingue un 6 de un 7 de forma reproducible.

Se puede calificar cada pieza por separado —plano, layout tipo, ambientación, Pack 1 en conjunto,
cada alternativa A/B/C y la propuesta— y **nada es obligatorio**.

Al calificar aparece, opcional, «¿Qué falló?» (o «¿Qué funcionó?») con motivos que dependen del
artefacto: *Cambió arquitectura* para una ambientación, *Circulación* para un layout, *Legibilidad*
para un plano.

### Lo que se guarda y no se ve

Cada evaluación se ata a `engine_version`, `artifact_sha256`, `provider`, `model` y `run_id`. El
usuario no ve nada de eso. Sin ello, «el layout quedó mal» es una opinión sobre nada: no se sabe
qué versión hay que arreglar.

`Ajustes → Evaluaciones` resume: totales, porcentajes por categoría, desglose por tipo de material
y los motivos de rechazo más frecuentes.

## Backstage

Nada se borró. `Ajustes → Herramientas técnicas` (`/lab/debug`) lleva a: el intake de plantas de
E27.3, la cola de revisión, el laboratorio de ambientación de E31, el benchmark de proveedores, la
superficie de cliente con sus topes de compra, los exports JSON y el producto simulado por
propiedad.

## Cómo ejecutarlo

```bash
cd ~/escalimetro-repo && git checkout e33_simple_product_lab
ESCALIMETRO_DEV=1 ESCALIMETRO_DATA_DIR=./.data-lab PYTHONPATH=src PORT=8030 .venv/bin/python wsgi.py
```

**http://127.0.0.1:8030/lab/**

Los datos existentes de `.data-lab` se conservan: no se reseteó nada.

## Limitaciones

1. **Sin roles** — la deuda de siempre: quien entra ve todo.
2. **La medición del plano sigue en otra pantalla.** Funciona, está enlazada y vuelve, pero no está
   embebida. Unificarla de verdad es rehacer el intake, y no era el objetivo de E33.
3. **La ambientación sigue bloqueada** hasta que haya un proveedor aprobado (E31.1 sigue esperando
   credenciales y fotos reales). Pack 1 lo dice como «pendiente de validar proveedor».
4. El sondeo recarga la página cuando el motor termina; no hay actualización parcial.
