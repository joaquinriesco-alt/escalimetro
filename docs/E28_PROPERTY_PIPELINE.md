# E28 — PROPERTY PIPELINE

## Por qué PROPERTY está por encima de CASE

Hasta E27.3 el objeto central de Escalímetro era el **CASE**: una planta que el motor sabe
interpretar. Un corredor no piensa en plantas: piensa en **una propiedad que tiene que arrendar**,
y esa propiedad tiene un plano, fotos, y eventualmente material para publicar.

E28 agrega ese objeto superior **sin tocar el de abajo**:

```
DOMINIO DE CLIENTE                 DOMINIO TÉCNICO DEL MOTOR
PROPERTY ─── floorplan_case_id ──► CASE ──► floorplate ──► layouts A/B/C
```

La relación es de un solo sentido. El motor no sabe que existen propiedades y no debe saberlo:
nada de `webapp/domain/` se importa desde `src/escalimetro/`, y un test lo verifica por AST.

**Por qué no se migró CASE → PROPERTY.** Un CASE puede existir sin propiedad —los tres que ya viven
en el volumen lo hacen— y una propiedad puede existir sin caso, recién creada. Fusionarlos habría
sido una migración destructiva a cambio de nada. Los casos antiguos siguen abriéndose igual y no se
les inventó una propiedad.

## Frontera cliente / interno

| | superficie de CLIENTE | superficie INTERNA |
|---|---|---|
| rutas | `/properties/**` | `/`, `/case/**`, `/run/**`, `/review` |
| plantillas | `templates/customer/` | `templates/` |
| código | `webapp/customer.py` (Blueprint) | `webapp/app.py` |
| vocabulario | plano, alternativas, fotos, pack | shell, núcleo, pilares, corridas, briefs |

El cliente ve **estado**, no mecanismo. Si el motor necesita que un humano nuestro mire la planta,
el cliente lee *"Estamos preparando la planta"* y la propiedad aparece en `/review`. Hay tests que
verifican que ninguna página de cliente contiene vocabulario interno ni enlaza a rutas internas.

> **DEUDA DECLARADA.** La autenticación sigue siendo una sola cuenta compartida (Basic Auth de
> E27). Esto **no es** un sistema de roles: alguien autenticado puede escribir a mano una URL
> interna y llegar. §9 del encargo pedía explícitamente no inventar un RBAC grande, así que la
> separación por ahora es de rutas, plantillas y capas. **Resolver esto es el primer requisito antes
> de que un cliente real entre al sistema.**

## Assets

Todo archivo de una propiedad es un `property_assets`. Tres reglas por construcción:

1. **El nombre que sube el usuario nunca toca el filesystem.** Se guarda como dato; el archivo se
   escribe con un UUID. Un `../../etc/passwd.png` es una cadena en una columna.
2. **Se sirve por identidad, no por ruta.** `assets.get(asset_id, property_id)` devuelve `None` si
   el asset es de otra propiedad; no existe ninguna ruta que acepte un path.
3. **Se mira el contenido, no la extensión.** Un `.png` que empieza con `%PDF` no entra.

Tipos vivos: `FLOORPLAN_ORIGINAL`, `PHOTO_ORIGINAL`, `FLOORPLAN_COMMERCIAL`, `LAYOUT_RENDER`,
`PACK_EXPORT`. Tipos **reservados** (declarados para que E29 no migre, pero que nada produce y que
`save_bytes` rechaza): `PHOTO_STAGED`, `BEFORE_AFTER`, `VIDEO`, `BROCHURE`.

## Estados

El estado de una propiedad **no se declara: se deriva de hechos** (hay plano, qué dice el artefacto
del caso, hay layouts, hay export). La columna existe para listar rápido y se recalcula en cada
lectura, así que no puede desincronizarse del motor.

| estado | significa | el cliente lee |
|---|---|---|
| `DRAFT` | sin plano | Falta subir el plano |
| `PREPARING` | hay plano; el caso aún no está listo | Estamos preparando la planta |
| `FLOORPLAN_READY` | planta confirmada, sin layouts | Plano listo |
| `LAYOUTS_READY` | hay alternativas con layout | Alternativas listas |
| `PACK_READY` | hay pack exportado | Pack listo |
| `BLOCKED` | planta fuera de contrato V1, o el caso falló | Necesitamos revisar esta propiedad |
| `FAILED` | falla técnica de **esta** capa | Necesitamos revisar esta propiedad |

`needs_internal_review` es aparte y sólo se usa hacia adentro: es verdadero cuando el CASE está en
`UPLOADED`, `NEEDS_INPUT`, `NEEDS_CONFIRMATION`, `INPUT_NOT_READY` o `FAILED`.

## Floorplan adapter

`webapp/domain/floorplan.py` es el **único** lugar del dominio de producto que sabe que existe un
CASE. Lo que no hace, y es el punto:

* no confirma nada por su cuenta;
* no escribe en `floorplate.json` ni en ningún artefacto del motor (hay test que compara el archivo
  antes y después);
* no se salta `shell_adapter` — si el caso no está listo, `publish_commercial_floorplan` devuelve
  `None` y no hay plano comercial;
* no marca READY para que una demo funcione.

## Plano comercial

`FLOORPLAN_COMMERCIAL` es **la planta base**: perímetro, núcleo, pilares, fachada con luz, acceso,
barra de escala. **No es la Alternativa A.** Es la pieza que falta entre "el plano que recibimos" y
"el layout que proponemos"; sin ella un before/after no tiene *before*. Se dibuja desde la geometría
que el motor interpretó y un humano confirmó — no hay limpieza automática de planos.

## Marketing pack

Un pack es un manifiesto más un ZIP, y lo gobierna una sola regla: **el manifiesto dice la verdad
sobre lo que hay dentro.** Si no hay fotos ambientadas, dice `not_generated` y el ZIP no las trae.
No se incluyen marcadores de posición presentados como material real.

```
/floorplan        plano original + plano comercial
/layouts          alternativas publicadas
/photos_original  las fotos tal como se subieron
manifest.json
```

Los assets aparecen en el manifiesto por identidad y hash, nunca por ruta absoluta: no se filtra el
path del volumen y el manifiesto sigue siendo válido si el almacenamiento cambia.

## Qué NO existe todavía

- ambientación virtual de fotos (sólo el contrato: ver `E28_VISUAL_ENGINE_CONTRACT.md`);
- before/after, video, brochure;
- limpieza automática de planos sucios;
- roles reales (ver deuda arriba);
- pagos, checkout, multi-tenant;
- cualquier tipo de propiedad que no sea OFFICE.
