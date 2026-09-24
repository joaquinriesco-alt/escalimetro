# E17.0 — ESCALÍMETRO VENDE POTENCIAL

Nueva capa de producto sobre una pregunta nueva: **¿qué potencial de esta propiedad no está
mostrando su publicación?** El sujeto ya no es una oficina que preparamos nosotros, sino un aviso
que alguien ya publicó. El motor de layouts no se elimina: pasa de ser *el producto* a ser una
**capacidad** que se invoca cuando el material la habilita.

---

## 1. Arquitectura encontrada

| capa | dónde vive | qué hace |
|---|---|---|
| motor de plantas y layouts | `src/escalimetro/` | localización, segmentación, geometría, CP-SAT. **Intocable**: hay un test desde E28 que verifica `git diff 6324b1f HEAD -- src/` vacío. |
| alta de casos | `webapp/intake.py` | `create_case_from_path` + `analyze` — la única puerta al motor, y no requiere una `property`. |
| LAB (producto E28–E36) | `webapp/lab.py`, `webapp/domain/` | prepara material para publicar una oficina. Congelado para el piloto humano en `ae64d35`. |
| assets | `webapp/domain/assets.py` | guardado de archivos con validación de formato, tamaño y contenido. |

## 2. Por qué tablas separadas y no `properties`

Reutilizar `properties` habría dado assets y plano gratis, y habría roto tres cosas del producto
congelado: cada aviso analizado aparecería en la portada del LAB, entraría en el conteo del piloto
y recibiría una concesión de pack —la migración de E32.2 le crea una a toda propiedad sin ella—.
Un aviso publicado por un tercero tampoco tiene producto, ni entitlements, ni `asset_type` de
oficina.

Así que: **tablas propias** (`listings`, `listing_media`, `potential_reports`,
`potential_findings`, `intervention_demos`) y **reutilización de lo que sí es común**: las reglas
de validación de archivos se importan de `domain.assets` en vez de reescribirse, y el plano entra
al motor por el mismo `intake.create_case_from_path` que usa el resto del sistema.

## 3. El score es trazable

Cuatro dimensiones con peso fijo (Portada 30 · Presentación 30 · Información 25 · Potencial 15) y
**21 criterios con nombre**. Cada criterio declara su peso, mide algo concreto y devuelve un valor
entre 0 y 1; sus puntos son `peso × valor`. El informe muestra la aritmética completa y
`/property/l/<id>/report.json` la sirve entera.

Un criterio que **no aplica** —dormitorios en una bodega, portada sin fotos— vale `NO_APLICA`, no
cero, y su peso se reparte entre los que sí aplican. Contarlo como cero castigaría al aviso por
algo que no puede tener.

**La atribución usa el peso intrínseco, no el redistribuido.** Sin fotos, un solo criterio de la
dimensión visual aplica y absorbería sus 30 puntos: el hallazgo prometería recuperar 30 subiendo
fotos, lo cual es falso porque al subirlas los demás criterios vuelven a aplicar. El delta de un
hallazgo es su parte intrínseca, que no se mueve cuando cambia qué aplica.

## 4. Lo que se mide de verdad, y lo que es un proxy

`vision.py` mide propiedades **ópticas**: luminancia, contraste, varianza del laplaciano,
densidad de bordes, recortes de altas y bajas, inclinación mediana de las líneas casi verticales,
y una huella perceptual dHash para duplicados. Todo eso es aritmética sobre píxeles y se puede
recalcular para comprobarlo.

**No clasifica escenas.** No dice "esto es un living", no dice "esto está vacío". Donde hace falta
una señal no óptica se usa un proxy declarado: `emptiness_proxy` mide densidad de bordes en la
mitad inferior del cuadro. Nunca decide solo un criterio —hacen falta dos señales: espacio que se
lee vacío **y** ninguna visualización publicada— y la evidencia que se muestra es la medición, no
una conclusión sobre el ambiente.

## 5. El score NO predice ventas

Mide qué tan bien la publicación muestra el potencial, que es una propiedad del **aviso**. La
pantalla lo dice con esas palabras, el JSON lleva la aclaración, y hay un test que verifica que en
la UI no aparezcan «probabilidad de vender», «más leads» ni «garantiza».

## 6. Regla de veracidad

Cada intervención del catálogo declara qué **preserva** y qué **puede cambiar**; muros, ventanas,
pilares, dimensiones, vistas y terrazas están en la lista prohibida de todas. Lo generativo se
etiqueta `CONCEPTUAL_VISUALIZATION` y se muestra como «Visualización referencial de potencial.».

`RENOVATION_VISUALIZATION` **no se recomienda sola**: el ejemplo del encargo —«la cocina domina
negativamente»— exige reconocer y juzgar un recinto, y no tenemos con qué. El tipo existe y se
puede elegir a mano; proponerlo con una excusa inventada sería el «score diseñado para vender
features» que el encargo prohíbe.

## 7. Demostración antes / después

El contrato existe; la generación **no está conectada**. Una demo nace `NOT_AVAILABLE` con el
motivo escrito, y `attach_result` —único camino a `READY` para algo generativo— exige el medio
resultante: no hay forma de marcar lista una demo sin resultado. El contrato de veracidad se
**copia** dentro de la demo al crearse, para que una demo vieja siga diciendo bajo qué reglas se
hizo aunque el catálogo cambie.

## 8. Ingesta desacoplada

`ListingSource` con dos implementaciones: `ManualSource` y `UrlSource`. La de URL lee `<title>` y
Open Graph —metadatos que existen para ser leídos— y **ningún selector de ningún portal**: un
scraper específico se rompe cuando el portal cambia una clase, y al romperse se lleva puesto el
producto. Lo que no se pueda leer queda vacío y la dimensión INFORMATION lo cuenta como faltante,
que es la verdad sobre lo que sabemos. **El flujo nunca se detiene por un fallo de la fuente.**

## 9. Deuda conocida

1. Un plano multiunidad no se puede resolver desde `/property`: el motor falla la localización y
   la pantalla lo dice, pero el selector de unidad de E35 vive en el LAB y no está conectado acá.
2. Ninguno de los umbrales está calibrado sobre avisos reales; van con nombre y valor visibles.
3. `emptiness_proxy` es un proxy y se comporta como tal: una foto de un ambiente amoblado pero
   plano puede leerse vacía.
4. La cobertura de recintos —«¿están todos los ambientes fotografiados?»— no se mide: requeriría
   clasificar escenas.
5. Sin pagos, sin funnel, sin outbound. El experimento de 100 corredores se registra a mano.
