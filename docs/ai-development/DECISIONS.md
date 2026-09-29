# ESCALÍMETRO — Decisiones duraderas

> Sólo decisiones que siguen condicionando el trabajo. Una decisión reemplazada **no se borra**:
> se marca `SUPERSEDED BY D-XXX`. Las decisiones **pendientes** viven en
> [`CURRENT_STATE.md`](CURRENT_STATE.md), no acá.
>
> Cada entrada cita dónde quedó escrita. Si no se puede citar, no entra.

---

### D-001 — El core es CREAR PLANO y MEJORAR PLANO

- **Fecha:** 2026-09-29
- **Decisión:** el core de ESCALÍMETRO son dos flujos: *CREAR PLANO* (no tienes plano → lo
  inferimos) y *MEJORAR PLANO* (ya tienes → lo convertimos en plano comercial).
- **Razón:** no registrada en la fuente. M01 lo presenta como «nuevo North Star aprobado» sin
  dar el porqué; si Joaquín quiere que el porqué quede escrito, se agrega acá.
- **Consecuencia:** cabida, layouts, PRO, test-fit, staging, renders, video y reels pasan a ser
  **aplicaciones** sobre el plano. El ingest de URL es infraestructura, y la parte que alimenta
  CREAR PLANO es dependencia directa del core. El scoring general de publicaciones (E17.0–E17.2)
  queda como aplicación.
- **Reemplaza:** la promesa de [`docs/PRODUCT_V1_SCOPE.md`](../PRODUCT_V1_SCOPE.md)
  («dame una planta libre y tu programa; te devuelvo alternativas de layout») y la definición de
  [`docs/PRODUCT_BOUNDARY.md`](../PRODUCT_BOUNDARY.md) («motor de pre-diseño / factibilidad /
  test-fit»). Ambos quedan como historia, con un aviso al inicio.
- **Origen:** Joaquín + ChatGPT — [`tasks/M01.md`](../../tasks/M01.md) §Fuente · persistido en
  [`PRODUCT_DOCTRINE.md`](PRODUCT_DOCTRINE.md).

### D-002 — Roles: Joaquín decide, ChatGPT audita, Claude implementa

- **Fecha:** 2026-09-29
- **Decisión:** Joaquín es product owner y autoridad final. ChatGPT trabaja producto, estrategia,
  experimentos y auditoría, y **no implementa el repo**. Claude Code implementa y **no redefine
  el producto**; ante una decisión de producto emite `DECISION_REQUIRED` y se detiene en esa parte.
- **Origen:** Joaquín + ChatGPT — [`tasks/M01.md`](../../tasks/M01.md) §Fuente · persistido en
  [`DEVELOPMENT_PROTOCOL.md`](DEVELOPMENT_PROTOCOL.md).

### D-003 — El repo es la memoria operacional y el canal entre ChatGPT y Claude

- **Fecha:** 2026-09-29
- **Decisión:** el trabajo viaja como `tasks/<ID>.md` → implementación → `reports/<ID>_REPORT.md`
  → `CURRENT_STATE.md`. El historial de conversaciones deja de ser requisito para operar.
- **Consecuencia:** Joaquín comparte un ID y una rama en vez de reportes y estado. Mientras
  ChatGPT no pueda escribir en el repo, el **texto de la TASK** todavía se pega una vez; ver
  protocolo §5.1.
- **Origen:** Joaquín + ChatGPT — [`tasks/M01.md`](../../tasks/M01.md).

### D-004 — Sin merge a `main` ni deploy sin autorización explícita

- **Fecha:** vigente desde E30; formalizada 2026-09-29.
- **Decisión:** ninguna TASK termina en merge a `main` ni en deploy a producción salvo que Joaquín
  lo autorice explícitamente para esa entrega.
- **Consecuencia:** el trabajo vive en ramas propias. Ver la decisión pendiente sobre la topología
  de ramas en `CURRENT_STATE.md`.
- **Origen:** todas las TASKs desde E30 («NO merge. NO deploy.») ·
  [`tasks/M01.md`](../../tasks/M01.md) §Fuente.

### D-005 — Los umbrales de autoaceptación no se calibran sin muestra, y nunca solos

- **Fecha:** 2026-09-21 (E35) · ampliada 2026-09-23 (E36, E36.1)
- **Decisión:** los umbrales de autoaceptación de geometría quedan `THRESHOLD_UNCALIBRATED` hasta
  tener `MIN_SAMPLE = 10` por componente **y** evidencia de que el umbral discrimina casos a ambos
  lados. Aun así el sistema sólo **propone**; una persona decide. Sólo las etiquetas
  `HUMAN_VERIFIED` cuentan como muestra.
- **Origen:** prompts E35 §13, E36 §11–§12, E36.1 · persistido en
  [`docs/E35_ROBUST_INGEST.md`](../E35_ROBUST_INGEST.md),
  [`docs/E36_REAL_PILOT.md`](../E36_REAL_PILOT.md).

### D-006 — BFL excluido del piloto de ambientación hasta decidir su licencia

- **Fecha:** 2026-09-21 (E31)
- **Decisión:** el proveedor BFL no recibe fotos de clientes mientras su cláusula de derechos
  sobre el material no esté aprobada por Joaquín.
- **Origen:** E31 · persistido en [`docs/E31_PROVIDER_DECISION.md`](../E31_PROVIDER_DECISION.md).

### D-007 — Toda visualización generativa preserva el inmueble real

- **Fecha:** 2026-09-24 (E17.0)
- **Decisión:** ninguna salida generativa mueve ventanas, borra pilares, agranda espacios, inventa
  vistas o terrazas, ni representa como existente algo que no existe. Se etiqueta
  `CONCEPTUAL_VISUALIZATION` y se muestra como «Visualización referencial de potencial.».
- **Origen:** E17.0 §Regla de veracidad · persistido en
  [`webapp/domain/potential/interventions.py`](../../webapp/domain/potential/interventions.py).

### D-008 — El motor de `src/` está congelado desde E28

- **Fecha:** 2026-09-10 (estado congelado) · vigente desde E28 (2026-09-21)
- **Decisión:** `src/` —que contiene sólo `src/escalimetro/`, el motor de plantas y layouts— no se
  modifica. Referencia: el commit `6324b1f` («E26 — listo para la primera revisión arquitectónica
  humana»). Toda capacidad nueva se construye en `webapp/` y habla con el motor por sus contratos
  existentes.
- **Consecuencia:** un test por fase (desde E28.7) exige `git diff 6324b1f HEAD -- src/` vacío.
- **Abierto:** CREAR PLANO probablemente necesite capacidades de motor que hoy no existen. Si el
  congelamiento sigue en pie bajo D-001 es una decisión pendiente (DR-6 en `CURRENT_STATE.md`).
- **Origen:** instrucción repetida en todas las TASKs E28–E36 («NO tocar el motor») · test
  `test_el_motor_no_se_toco` en `tests/test_e28_property_pipeline.py` y siguientes.

### D-009 — Internal Reconstruction Lab: iniciativa aprobada

- **Fecha:** 2026-09-29
- **Decisión:** construir un laboratorio interno que compare motores de reconstrucción de planos:
  proyecto → inputs → Motor A / B / C → corrida inmutable → corrección por prompt → corrida hija →
  calificación → reveal del ground truth → comparación.
- **Consecuencia:** es la próxima iniciativa de producto. Todavía **no tiene TASK**; la escriben
  Joaquín + ChatGPT. Depende de DR-6 si algún motor necesita tocar `src/`.
- **Origen:** Joaquín + ChatGPT — [`tasks/M01.md`](../../tasks/M01.md) §Fuente.
