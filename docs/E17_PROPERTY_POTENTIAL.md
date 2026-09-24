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

## 8.1 E17.1 — potencial, no puntaje

**El informe empieza por las oportunidades.** `67/100` dejó de encabezar: el puntaje y sus 21
criterios siguen existiendo, detrás de «Ver diagnóstico completo», como instrumentación interna.
Lo primero que se lee es *Oportunidades para mostrar mejor esta propiedad*, partido en dos:

| clase | qué significa | ejemplo |
|---|---|---|
| **Escalímetro puede resolverlo** | hay una intervención nuestra detrás | demostrar cabida con el plano |
| **Recomendación para la publicación** | lo arregla quien publica | no dice el precio |

La oportunidad principal es la mayor **de las que podemos resolver**. Si la mayor carencia del
aviso es que no declara el precio, eso no es nuestra oportunidad: encabezar con ella convertiría
el informe en una lista de reproches.

**No se finge lo que no existe.** Cada intervención declara qué podemos entregar hoy:

| intervención | soporte |
|---|---|
| `COVER_SELECTION` | **AVAILABLE** — elegir entre fotos que ya existen; esta pantalla lo hace |
| `SPATIAL_LAYOUT` | **AVAILABLE** — el motor corre y produce layouts desde E28 |
| `VIRTUAL_STAGE`, `SPACE_REIMAGINATION`, `RENOVATION_VISUALIZATION` | **PENDING_PROVIDER** — bloqueadas por E31.1; se ofrecen como prueba interna, nunca como entrega |
| `PHOTO_ENHANCE` | **NOT_BUILT** — no hay implementación, así que sus hallazgos son recomendación |

**El blocker multiunidad, resuelto.** `/property` importa `domain/units.py` —el mismo modelo de
candidatos de E35— y llama a sus funciones puras. Se extrajeron dos helpers para no duplicar nada:
`overrides_for_candidate()` (la traducción al vocabulario del motor) y `draw_candidates()` (el
overlay). Dos paletas distintas habrían hecho que el número del plano dejara de coincidir con el
del botón el día que alguien tocara una.

El clic se guarda en `listing_unit_selection`, no en `unit_selection`: esa tabla referencia
`properties`, y crear una propiedad sólo para poder guardar un clic arrastraría concesiones de
pack y conteos de piloto. Medido sobre el aviso de Apoquindo: 3 candidatos → un clic → el motor
lee **543,0 m²** y escala 8,358 px/m, con `properties = 0` y `pack_grants = 0`.

## 9. Deuda conocida

1. ~~Un plano multiunidad no se puede resolver desde `/property`.~~ **Resuelto en E17.1**: un
   clic inline, reutilizando el modelo de candidatos de E35.
2. Ninguno de los umbrales está calibrado sobre avisos reales; van con nombre y valor visibles.
3. `emptiness_proxy` es un proxy y se comporta como tal: una foto de un ambiente amoblado pero
   plano puede leerse vacía.
4. La cobertura de recintos —«¿están todos los ambientes fotografiados?»— no se mide: requeriría
   clasificar escenas.
5. Sin pagos, sin funnel, sin outbound. El experimento se registra a mano.
6. **`PHOTO_ENHANCE` no está construido.** Un aviso cuyo único problema sean fotos oscuras no
   muestra ninguna oportunidad resoluble. Si la muestra de 20 dice que los defectos visuales
   dominan, es lo primero que hay que escribir — y es corto.
7. Después de elegir la unidad, el motor deja la planta en `NEEDS_REVIEW`: las compuertas de E35
   siguen pidiendo confirmación y esa pantalla vive en el LAB. Para demostrar cabida de verdad
   habría que confirmarlas, y eso todavía no está en `/property`.

## 8.2 E17.2 — el link es el input

**Pegar una URL basta.** El sistema trae datos, fotos y plano, y corre el análisis solo. La carga
manual sigue existiendo, colapsada, y deja de ser el camino.

### Extracción por capas, de menor a mayor fragilidad

| capa | qué da | por qué en ese orden |
|---|---|---|
| **A.** JSON-LD (`schema.org`) | nombre, precio, moneda, id | el portal lo publica PARA ser leído |
| **B.** Open Graph / `<meta>` | título, descripción, imagen | idem, para buscadores y redes |
| **C.** estado embebido | 12 atributos y la galería completa | es el JSON del portal, no su CSS |
| **D.** adaptador por dominio | *no hizo falta* | las tres anteriores alcanzaron |
| **E.** navegador headless | **no construido** | ver abajo |

Lo que **no** se hace es leer el DOM con selectores de clases. Un selector visual se rompe la
semana que el portal cambia una hoja de estilos. Medido sobre una publicación real de Portal
Inmobiliario: **18 campos y 29 fotos sin tocar una sola clase de CSS**.

La capa E queda declarada y sin implementar: §3.E la admite sólo si lo estructurado no alcanza, y
no fue el caso. Meter un navegador headless en el servidor «por si acaso» es infraestructura
grande para un problema que hoy no existe.

### SSRF: la superficie de riesgo real

Pegar una URL hace que **el servidor** se conecte a donde diga esa URL. Desde adentro de una red
el servidor alcanza lo que el atacante no: el endpoint de metadatos de nube (credenciales en texto
plano), bases que escuchan en loopback, paneles internos.

| defensa | ataque que cierra |
|---|---|
| sólo `http`/`https` | `file:///etc/passwd`, `gopher://` contra Redis, `data:` |
| resolución previa de **todas** las IP | un nombre que resuelve a pública **y** a `127.0.0.1` |
| redirecciones seguidas a mano, revalidando | `302` → `http://169.254.169.254` |
| tope por bytes **leídos** | un `Content-Length` que miente |
| tipo de contenido validado | un binario servido como página |

Riesgo residual escrito en el código: *DNS rebinding* entre resolver y conectar. Cerrarlo exige
conectar por IP con `Host` a mano, lo que rompe TLS con SNI. Para una URL que pega un operador
interno la ventana es aceptable; para una superficie pública no lo sería.

### Las fotos buenas no son un problema

El informe sabía nombrar defectos y eso lo empujaba a encontrar uno siempre. Ahora guarda también
**señales positivas** —`good_cover`, `good_exposure`, `good_verticals`, `sufficient_gallery`,
`visual_presentation_strong`— y admite un tercer estado comercial:

```
RESOLVABLE_OPPORTUNITY   hay algo concreto que podemos producir
RECOMMENDATION_ONLY      hay mejoras, pero hoy no las entregamos nosotros
ALREADY_STRONG           el aviso ya presenta bien la propiedad
```

Rebajar una publicación buena para crear mercado arruinaría la única pregunta que la muestra
contesta. **De las cuatro publicaciones reales del dogfood, las cuatro salieron `ALREADY_STRONG`
con cero oportunidades resolubles** — y ninguna traía plano en la galería, así que
`SPATIAL_LAYOUT`, nuestra capacidad más fuerte, nunca se activó. Ése es el hallazgo comercial de
E17.2 y no se maquilla.

### Clasificación de media

`FLOORPLAN` se separa de `PHOTO` por una señal trivial de medir: un plano es tinta sobre papel.
Medido sobre el material real del repositorio —planos 0.649–0.772 de blanco, fotos 0.000–0.243— el
corte va en 0.45 con un margen amplio. `MAP` se clasifica **sólo por la URL**: un mapa estático se
parece demasiado a una foto aérea como para separarlos con tres estadísticos, y adivinar mal
significaría tirar una foto buena.
