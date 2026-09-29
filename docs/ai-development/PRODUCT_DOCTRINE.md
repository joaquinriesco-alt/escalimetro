# ESCALÍMETRO — Doctrina de producto

> Principios estables. No es changelog ni lista de features.
> Cambiar este archivo es una decisión de producto de Joaquín: se registra en
> [`DECISIONS.md`](DECISIONS.md) y nunca lo cambia un agente por su cuenta.

---

## El core

```
1. CREAR PLANO      No tienes plano → lo inferimos.
2. MEJORAR PLANO    Ya tienes plano → lo convertimos en plano comercial.
```

Todo lo demás es **aplicación sobre el plano** o **infraestructura** que sirve a uno de estos dos.

### CORE 1 — CREAR PLANO

**Entrada:** URL o publicación, fotos, video, superficie, dirección y contexto, descripción,
antecedentes públicos verificables.

**Salida:** *Plano Esquemático Comercial*. Referencial, comercial, trazable, honesto sobre la
incertidumbre y corregible por lenguaje natural. **No** se presenta como levantamiento
arquitectónico.

**Corrección:** el humano corrige la *interpretación*, no redibuja en CAD.

```
IA genera v1 → humano revisa → «el dormitorio principal es más grande»
            → IA modifica el modelo espacial → v2 → aprobación
```

### CORE 2 — MEJORAR PLANO

**Entrada:** PDF, JPG/PNG, escaneo, plano técnico, planta poco publicable.

**Salida:** *Plano Comercial*. Limpio, claro, consistente, entendible, publicable. Este flujo
tiende a ser extremadamente automático y barato.

---

## Principios

1. **90 % IA / 10 % humano** es la meta de producto. Es un objetivo medible, **no** un claim
   comercial todavía.
2. **La corrección humana es por instrucción, no por CAD.**
3. **La salida de CREAR PLANO es esquemática y referencial.** Nunca se finge certeza geométrica.
4. **Producto 100 % remoto** como dirección. Evitar la dependencia de una visita física.
5. **Honestidad de la evidencia por encima de la métrica.** Un fallo no se oculta para mejorar un
   número; un estado optimista arruina el experimento que lo mide.

## Lo que NO es core

| categoría | ejemplos |
|---|---|
| aplicaciones sobre el plano | cabida, layouts, ESCALÍMETRO PRO, test-fit, staging, renders, video, reels |
| infraestructura / adquisición | ingest de URL (E17.2), análisis y scoring de publicaciones, búsqueda de oportunidades |

El ingest de URL **no es core**: es infraestructura. La parte que alimenta
`URL → fotos / video / datos → CREAR PLANO` es una **dependencia directa del core** y se trata con
esa prioridad; el scoring general de publicaciones no sirve al core y queda como aplicación.

## Roles

| rol | quién | hace |
|---|---|---|
| **Product owner y autoridad final** | Joaquín | decide qué es ESCALÍMETRO, para quién, prioridades, pricing, UX relevante, experimentos, qué congelar o eliminar, qué es calidad suficiente, cuándo cambiar de dirección, vender o desplegar |
| **Producto y auditoría** | ChatGPT, con Joaquín | estrategia, hipótesis, diseño de experimentos y acceptance gates, auditoría independiente, crítica, detección de drift y sobreconstrucción. **No implementa el repo.** |
| **Implementación técnica** | Claude Code | inspecciona, implementa, prueba, experimenta, guarda evidencia, reporta. **No redefine el producto.** |

Ningún agente reemplaza la autoridad de Joaquín.
