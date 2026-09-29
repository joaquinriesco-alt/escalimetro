# M01 — Reconstrucción, pasada 2

- **Fecha:** 2026-09-29
- **Agente:** subagente `Explore` (sólo lectura), instancia nueva, sin historial.
- **Leyó:** lo mismo que la pasada 1 **más** `reports/M01_REPORT.md`, después de corregir lo que encontró la pasada 1.
- **Nota:** el REPORT tenía tres marcadores sin completar (resultado post-cambio, esta pasada, commit); se le pidió no contarlos como faltantes.

---

**Tally: 11 ANSWERED, 1 PARTIAL (Q9), 0 NOT_ANSWERED.**

1. **What is ESCALÍMETRO today? ANSWERED.** Turns real-estate material into commercial floor plans. Target user explicitly not defined, left to Joaquín; work so far on broker offices and Chilean portal listings.
2. **Core? ANSWERED.** CREAR PLANO and MEJORAR PLANO; everything else is application or infrastructure.
3. **Built? ANSWERED.** CREAR PLANO 0 lines; MEJORAR PLANO partial, unmeasured; URL ingest 4/4; layouts; scoring; staging blocked.
4. **Frozen? ANSWERED.** `src/escalimetro/` since E28 against `6324b1f`, test-enforced; `e36_real_property_pilot` frozen for development; whether the freeze survives D-001 is open (DR-6).
5. **Experiments? ANSWERED.** E36 active (1/10, 7 provisional labels); E17 paused (DR-4); Reconstruction Lab approved without TASK.
6. **Last task? ANSWERED.** M01; before, E17.2.
7. **What changed? ANSWERED.** File list; replacement notices; `webapp/` and `src/` untouched.
8. **Tests? ANSWERED (baseline only; post-change placeholder).**
9. **Evidence? PARTIAL.** Baseline, file list, pass-1 counts and fix table present. Missing: the reconstruction transcript the TASK requires; which questions were partial in pass 1; AC2 asserted without a record of the check.
10. **Decisions? ANSWERED, with count inconsistencies.** DR-1 to DR-6 with options; BFL licence; API keys and production URL.
11. **Next for Claude? ANSWERED.** Nothing until the Reconstruction Lab TASK exists.
12. **Not authorized? ANSWERED.**

**Contradictions and ambiguities**

1. Pending-decision count: report says 6, `CURRENT_STATE` table has 7 rows (BFL unnumbered, no options). Target user called Joaquín's decision but not in the table. E36 "waiting on Joaquín" without saying what he must do.
2. Whether Joaquín still pastes TASK text: D-003 and protocol §1 say only an ID and a branch; protocol §5.1 and the report say the TASK text is pasted once.
3. Where the TASK file comes from: `CLAUDE.md` says it is already in `tasks/`; §5.1 says Claude commits it first.
4. Decision citations end at `tasks/M01.md §Fuente`, a summary that doesn't say who wrote it.
5. Production vs `main`: production `e27.3`, `main` at E16.1; which commit is deployed is unexplained; DR-1 option B assumes a relationship that doesn't exist.
6. Branch table vs chain: e30–e35 missing from the table; "E17 (motor) → E36" vs a chain starting at e30.
7. E36 "activo" while its branch is frozen: where does E36 work happen?
8. E36 figures come from `.data-lab/`, outside the repo, though the file claims everything was verified against the repo.
9. AC7 and AC10 marked PASS ahead of their evidence (placeholders).
10. Two "not authorized" lists differ: `CLAUDE.md` omits "otra vertical", "redefinir CREAR/MEJORAR", "PRO/layouts/staging/video en el centro".
11. The Reconstruction Lab is "approved" but has no D-entry.
12. Protocol ranks "reports/ históricos", but there are none yet.
