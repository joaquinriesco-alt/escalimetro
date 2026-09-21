# E34 — INGRESO SIN FRICCIÓN: plano + fotos → Pack 1

## La regla

> **El usuario entrega el inmueble. Escalímetro resuelve el resto.**

Nadie que quiera publicar una oficina debería marcar dos puntos sobre un plano para declarar la
escala, ni señalar por dónde se entra.

## Lo que se pide, antes y después

| Antes (E33) | Ahora |
|---|---|
| nombre · ciudad · m² · plano · fotos, y después: ¿planta limpia? · escala (dos puntos + metros) · acceso · confirmar perímetro, núcleo, pilares, luz | **nombre · plano · fotos** (ciudad y m² opcionales) |

## Dónde estaba la fricción

No en el motor. El pipeline **ya** deducía la escala desde la superficie publicada, **ya** infería
el acceso principal con su propia confianza, y **ya** decidía si eso alcanzaba
(`shell_readiness.ready_for_layout`). En las dos plantas reales del repo ese campo sale en `true`
sin una sola confirmación humana.

La fricción era un formulario de esta aplicación que pedía todo eso *antes* de dejar mirar nada.

## Estrategia de escala

1. **Superficie publicada** — cuando la hay. Es lo que el motor ya aplica y lo que funciona.
2. **Puertas** — último recurso, cuando no hay superficie publicada.
3. **Manual** — fallback interno, en la herramienta técnica. No se eliminó; dejó de ser el primer paso.

### Escala por puertas: lo que da de verdad

Implementada con mediana, descarte de atípicos por desviación absoluta mediana y confianza derivada
de tres cosas medibles: cuántas evidencias hay, cuánto se parecen entre sí y cuánto pesa el error de
cuantización.

**Medido sobre nuestras plantas reales:**

| Plano | Vanos detectados (px) | Escala por puertas | Escala real | Error | Confianza |
|---|---|---|---|---|---|
| 403 | 4, 6, 10, 16 | 6.67 px/m | 8.357 px/m | **20 %** | 0.31 |
| 401 (dibujo completo) | ninguno | — | — | — | — |

Por qué: lo que el motor expone son `entrance_candidates`, es decir **vanos del perímetro**
(accesos de 1.2–2.0 m), no puertas interiores de 0.90 m. Y a 8 px/m **un píxel son 12 cm**, así que
medio píxel de error en un vano de 7 px ya es un 7 % de escala.

**Conclusión honesta: en las plantas que tenemos, la escala por puertas nunca llega a ser la fuente
aceptada.** Está implementada, probada y es correcta; simplemente su confianza nace por debajo de la
vara (0.55) y el contraste contra el área publicada la desmiente. Eso es el resultado, no un fallo.

## Contraste

Con superficie publicada, se compara el área derivada contra la publicada y se guarda la diferencia.
**Es una señal, nunca una corrección**: la geometría no se deforma para que el área dé. Si las dos
fuentes coinciden, la confianza sube. Un desacuerdo sólo escala a revisión si la hipótesis de
puertas era creíble — si no, el estimador más flojo mandaría todo a revisión, que es al revés.

## Aceptación automática por regla

El motor pide confirmar lo que detectó. Cada grupo se acepta **sólo** si la confianza que el propio
motor publicó supera una vara escrita:

| Grupo | Vara | 403 real |
|---|---|---|
| perímetro | 0.60 | 0.70 ✓ |
| núcleo | 0.50 | 0.50 ✓ (al filo) |
| acceso | 0.70 | 0.95 ✓ |
| pilares | 0.55 | 0.70 ✓ |
| luz natural | 0.45 | 0.60 ✓ |

Lo aceptado queda marcado `AUTO_ACCEPTED_BY_RULE`, **nunca** `HUMAN_CONFIRMED`. La diferencia viaja
en la procedencia y se ve en el detalle técnico: quien lea un layout puede saber que su planta nunca
la miró nadie.

## El fallback

Cuando la deducción no alcanza, Pack 1 dice *«Necesitamos revisar el plano antes de continuar»* y el
botón **Revisar** abre una pantalla que ofrece primero lo único que una persona resuelve en un clic:
**¿la lámina es de una sola oficina?** (`drawing_scope`, que el motor se niega a deducir de la
ausencia de datos — E16.5, y hace bien). La medición manual sigue detrás.

## Un hallazgo que conviene saber

**La localización automática usa el nombre de la propiedad.** El motor busca esa etiqueta sobre el
dibujo por OCR. «Oficina 403» encuentra la unidad 403 en una lámina de varias; «Mi oficina» no
encuentra nada y cae al fallback.

## Observabilidad

Se guarda por propiedad: `scale_source`, `scale_value`, `scale_confidence`, `evidence_count`,
`cross_checks`, `access_source`, `access_confidence`, `geometry_source`. **Nada de eso se le muestra
al usuario** — vive en «Ver detalle técnico» — y existe para poder correlacionar *«este layout quedó
malo»* con *«la escala salió de la superficie publicada con confianza 0.4»*.

## Limitaciones

1. La escala por puertas no alcanza confianza útil en nuestras plantas: haría falta detección de
   **puertas interiores**, que hoy el motor no expone.
2. La aceptación del núcleo en la 403 pasa **exactamente** en el límite (0.50 contra 0.50): una
   décima de ruido de detección la manda a revisión. El camino automático no es robusto todavía
   para núcleos.
3. Sin superficie publicada y sin puertas medibles no hay escala: revisión humana.
4. La ambientación sigue esperando proveedor aprobado (E31.1).
