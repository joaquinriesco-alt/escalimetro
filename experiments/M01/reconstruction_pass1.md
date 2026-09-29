# M01 — Reconstrucción, pasada 1

- **Fecha:** 2026-09-29
- **Agente:** subagente `Explore` (sólo lectura), sin historial de conversación.
- **Leyó:** `CLAUDE.md`, `docs/ai-development/{CURRENT_STATE,PRODUCT_DOCTRINE,DEVELOPMENT_PROTOCOL,DECISIONS}.md`, `tasks/M01.md`.
- **No leyó:** código, historial de git, otros docs, el REPORT (todavía no existía).
- **Pregunta:** las 12 de M01 («¿qué es ESCALÍMETRO hoy?», … «¿qué NO puede decidir Claude?»), con cita del archivo y calificación ANSWERED / PARTIAL / NOT_ANSWERED.

---

**Score: 7 ANSWERED, 4 PARTIAL, 1 NOT_ANSWERED.**

1. **What is ESCALÍMETRO today? PARTIAL.** The declared core is CREAR PLANO + MEJORAR PLANO. In practice, MEJORAR PLANO exists only in part, inside the LAB, and CREAR PLANO does not exist. The code is a frozen engine (plan → floorplate.json → CP-SAT layouts) plus a Flask webapp with `/case`, `/lab` and `/property`. The files never say in plain words who the product is for or what market it serves. Whether production is live is unknown.
2. **What is the current core? ANSWERED.** CREAR PLANO and MEJORAR PLANO. Sources: `PRODUCT_DOCTRINE.md`, D-001, `CLAUDE.md`.
3. **What is actually built? ANSWERED.** CREAR PLANO: 0 lines. MEJORAR PLANO: partial, quality unmeasured. URL ingest works (4/4; Zillow blocks). CP-SAT layouts work. Ambientación blocked. Listing scoring works, not core.
4. **What is frozen? ANSWERED.** `src/escalimetro/`, enforced by a test; branch `e36_real_property_pilot`. No file says why, who decided it, or who can lift it.
5. **What experiments are active? ANSWERED.** E36 active, waiting on Joaquín (1/10 plans, 0 human labels, 7 provisional). E17 sample paused until DR-4.
6. **What was the last task? ANSWERED.** M01; before it, E17.2 at `4c0934a`.
7. **What changed in it? PARTIAL.** Only "este sistema de handoff. Sin cambios de funcionalidad." No file list, no commit hash.
8. **What tests passed? PARTIAL.** `2036 passed · 2 failed · 8 skipped · 7 xfailed` at `4c0934a` — the before-M01 number. No after-M01 run.
9. **What evidence did it produce? NOT_ANSWERED.** Only points to `reports/M01_REPORT.md`.
10. **What decisions does Joaquín need to make? ANSWERED.** DR-1 to DR-5, plus writing the Reconstruction Lab task.
11. **What should Claude do next? ANSWERED.** Nothing; next step belongs to Joaquín and ChatGPT.
12. **What is Claude NOT authorized to decide? ANSWERED.**

**Contradictions, ambiguities and gaps**

1. Ingest is core or not: D-001 says URL ingest "sí lo es"; `PRODUCT_DOCTRINE.md` lists it under "Lo que NO es core".
2. Decision provenance points outside the repo: D-001 to D-004 cite "M01 §N", which are sections of a document kept outside the repo. The Reconstruction Lab is approved but never defined in the repo.
3. Freeze scope: `CLAUDE.md` says `src/escalimetro/` but the command diffs `src/`. `6324b1f` is never explained. No D-entry. Nothing says how CREAR PLANO can be built while the engine is frozen.
4. ID ordering: protocol says E-numbers are "en orden", yet E17.x came after E36.
5. DR-2 against the protocol: the protocol depends on the repo being public.
6. E36 "activo, congelado" unclear; "1/10 planos" vs "7 provisionales" unclear; D-005 `MIN_SAMPLE = 10` vs E36's 10 plans.
7. M01 closure not checkable: evidence, commit, report status missing.
8. Pending decisions missing from the DR list: BFL licence, ambientación credentials.
9. Ambientación: "piloto" in D-006 vs "Bloqueos" in `CURRENT_STATE.md`.
10. Branch table missing `e17_property_potential`; `e36` without date; "107 commits atrás" relative to which branch; production unknown and nobody asked to resolve it.
11. Who commits TASK files, if ChatGPT doesn't write to the repo.
12. `CLAUDE.md` not in the canonical-source ranking.
13. Terms never defined: ambientación, LAB, lámina, segmentador, multiunidad, floorplate, cabida, PRO, `THRESHOLD_UNCALIBRATED`, E27.3; "plano comercial" vs "Plano Esquemático Comercial".
14. D-001's reason is circular ("declarado como nuevo North Star aprobado").
