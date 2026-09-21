# E30 — DIRECCIÓN DE PRODUCTO: dos productos sobre una misma geometría

Este documento describe la capa **comercial** construida sobre E27 (herramienta interna) y E28
(pipeline de propiedad). El motor no cambió: `git diff 6324b1f..HEAD -- src/` sigue vacío, y hay un
test que lo comprueba en cada corrida.

---

## 1. La tesis, y por qué cambia el código

Escalímetro convierte una propiedad vacía en un activo comercial más fuerte. Eso se vende de dos
formas que **no se pueden mezclar**:

| | Pack de publicación (`ONE_OFF`) | Escalímetro Pro (`PRO`) |
|---|---|---|
| Qué es | un **entregable** | un **flujo** |
| Quién lo compra | corredor chico, listado nuevo | GPS, CBRE, Colliers, propietarios |
| Alcance | una propiedad | cartera |
| Layouts | **uno** representativo | A/B/C, y se puede regenerar |
| Prospectos | ninguno | uno por cada interesado, con su marca |
| Precio hipótesis | ~USD 100 / propiedad | cuota mensual |

La frase que resume la diferencia y que el código hace cumplir: **el cliente de una vez compra un
activo terminado; el cliente Pro compra la capacidad de seguir trabajando la propiedad**.

---

## 2. El modelo

```
PROPERTY  (E28)                          geometría preparada UNA vez
  ├── CASE                               el motor, intacto
  ├── FLOORPLAN_COMMERCIAL               plano comercial
  └── FIT REQUESTS                       ← E30
        ├── BASE        (1 por propiedad)  preset EQUILIBRADO → layout representativo → pack base
        └── PROSPECT    (N, sólo Pro)      su programa, su marca, su propuesta, su pack
```

Un fit request es **"evaluá esta propiedad para este programa"**. Produce un `BriefV1` y una
corrida; el contrato con el motor es exactamente el mismo que en E27.

`fit_runs` une fit ↔ corrida. Una corrida sin fit (las de E27/E28) sigue siendo válida.

---

## 3. Derechos de producto (`domain/entitlements.py`)

Siete capacidades, dos modos, una matriz. El modo vive en `settings` (tabla clave/valor de la
cuenta), **no** en un email ni en código.

```python
entitlements.require(entitlements.PROSPECT_FIT_REQUESTS)   # lanza EntitlementError
```

La regla que importa: **el corte ocurre en el dominio**. Las rutas traducen la excepción a un 403
con un texto de cliente, y las plantillas esconden el botón — pero si alguien escribe la URL a
mano, la operación no ocurre igual. Hay test.

El modo por defecto es `ONE_OFF` a propósito: si nadie lo configura, el sistema entrega de menos.

**No hay facturación, y §13 dice que no la haya todavía.** `mode()` es el único punto que habría que
conectar el día que exista.

---

## 4. Presets de lugar de trabajo (`domain/presets.py`)

`DENSE` · `BALANCED` · `COLLABORATIVE` · `EXECUTIVE`. El usuario dice cómo quiere que **funcione**
la oficina; no la dibuja.

Un preset produce **un `BriefV1` y nada más**: `target_headcount`, `open_workstations`, `rooms`.

### La brecha honesta

Un preset cambia **qué se pide**, no **cómo se coloca**. `COLLABORATIVE` pide más salas, más lounge
y menos puestos fijos; no le dice al motor que privilegie el encuentro sobre la luz natural, porque
hoy no existe ningún campo de contrato por el que decírselo — eso vive en `DesignPolicyV1`, que es
política interna (E24 §5) y que un preset comercial no debe mover. Si algún día se quiere que el
preset incline también el objetivo, **es un cambio de contrato del motor** y no se hace a escondidas
desde la capa de producto.

### La identidad que ningún preset rompe

```
open_workstations + private_office + reception  ≤  target_headcount
```

`_ajustar` la impone cediendo recepción → privados → puestos. Antes que fabricar ocupación, un
preset entrega menos programa. Verificado con `BriefV1.validate` del motor para los 4 presets sobre
todo el rango de headcount.

---

## 5. Express y avanzado (§10)

* **EXPRESS** — personas + forma de trabajo (+ puestos objetivo opcional). Es el camino por defecto.
* **AVANZADO** — el programa módulo por módulo, precargado con lo que el preset propone. Sólo Pro.

En ninguno de los dos hay controles de colocación: no se fija dónde va el directorio, no se anclan
recintos, no hay CAD. Eso sigue siendo del motor.

---

## 6. El layout representativo (§18)

El pack de publicación lleva **exactamente uno**, y no es "el último". El criterio, declarado y
guardado en el asset como `selected_by`:

1. `human_best_alt` — alguien de nuestro equipo marcó la mejor de la corrida. El juicio humano gana:
   es literalmente el producto que E26 construyó para medir.
2. `program_complete` — la alternativa que ubica el programa entero, según el motor.
3. `first_fit` — la primera con layout, en orden A, B, C.

**Lo que este criterio no es**: una puntuación de calidad arquitectónica. `architectural_score`
existe en `quality.json` y dice de sí mismo que es instrumentación y que ningún umbral suyo decide
si una planta sirve. Usarlo para coronar "la mejor" sería la clase de afirmación que §22 prohíbe.
Por eso la lámina se muestra con el motivo por el que es ésa.

Si ninguna alternativa tiene layout, **no se publica ninguna** y el documento lo dice.

---

## 7. Marca (§20)

| | dónde vive | dónde se usa |
|---|---|---|
| Corredora | `settings` (la cuenta) | pack de publicación de cualquier propiedad |
| Prospecto | el fit request | sólo ese fit y lo que salga de él |

**Un pack BASE nunca lleva marca de prospecto.** Mandar material con el logo de otro cliente, o
publicar un aviso con el nombre de quien todavía no arrendó, es un error comercial concreto: se
impide en el dominio y hay test.

La marca va en la portada y el pie. No entra al plano ni al layout.

---

## 8. Estilos visuales (§6)

`CORPORATE` · `CONTEMPORARY` · `CREATIVE` · `INDUSTRIAL` · `PREMIUM`.

Afectan mobiliario, materiales, luz decorativa, plantas, paleta. **No** pueden mover ventanas,
quitar pilares, alterar muros ni cambiar proporciones. Está garantizado por construcción: el estilo
sólo entra en `StagingRequest`, que no lleva ni un dato geométrico, y nunca toca el brief. Hay test.

---

## 9. La propuesta (`domain/proposal.py`)

Un HTML autocontenido, sin JavaScript y sin llamadas externas: portada con marca, el plano, las
alternativas entregadas y la procedencia. **El mismo archivo** se ve en la aplicación y va dentro
del ZIP, así que lo que el cliente mira y lo que abre su prospecto son el mismo documento.

**No es una página pública.** §2 pide una página compartible *"if already supported cleanly"* y hoy
no lo está: la aplicación tiene una sola cuenta compartida, así que una ruta sin autenticar
expondría el material de todas las propiedades, no el de una. Se entrega como archivo —reversible—
y el enlace público queda como decisión explícita, después de los roles.

---

## 10. Packs

```
BASE                                 FIT
floorplan/plano_original.*           floorplan/plano_original.*
floorplan/plano_comercial.png        floorplan/plano_comercial.png
layouts/alternativa_A.png            layouts/alternativa_A|B|C.png
photos_original/foto_NN.*            photos_original/foto_NN.*
marca/logo.*        (corredora)      marca/logo.*        (prospecto)
propuesta.html                       propuesta.html
manifest.json                        manifest.json
```

Conviven: regenerar el de un prospecto no toca el de la propiedad ni el de otro prospecto.
El manifiesto sigue diciendo la verdad sobre lo que hay dentro, incluido `photos_staged: []` y
`visuals_status: not_generated`.

---

## 11. Honestidad (§22)

* No se promete arriendo más rápido, mejor precio ni mejor conversión. No se ha medido.
* `SEARCH_EXHAUSTED` no se traduce como "no cabe" en ninguna superficie, ni en la propuesta.
* El manifiesto declara lo que falta en vez de rellenar.
* Un preset no fabrica ocupación.
* El layout representativo declara por qué fue elegido.

---

## 12. Lo que E30 NO construyó, a propósito

BIM · editor 3D · VR · tours · residencial · marketplace · CRM · brochure builder · SSO ·
facturación · Stripe · roles de organización complejos · edición CAD · controles de colocación de
recintos · llamadas a ningún proveedor de imagen.

---

## 13. Deuda declarada

1. **Roles (RBAC).** Sigue siendo una cuenta compartida. Un autenticado puede escribir una URL
   interna y llegar. Los derechos de producto cortan por capacidad, **no por identidad**. Es lo
   primero antes de que esto vea a un cliente real, y es también lo que bloquea el enlace público
   de propuesta.
2. **Una sola corredora por despliegue.** La marca es de la cuenta y la cuenta es el despliegue.
3. **El piloto de ambientación no se corrió** — requiere credenciales y decisión de gasto. Ver
   `E30_STAGING_PILOT.md`.
4. **El pack se puede exportar sin layouts.** El manifiesto avisa y la UI enumera el contenido, pero
   el estado dice `PACK_READY`.
5. **Sin selector de versión de corrida**: se publica la última del fit.
