# M01 — Evidencia: reconstrucción sin historial

Criterio 7 de [`tasks/M01.md`](../../tasks/M01.md): *un agente sin historial reconstruye el estado
del proyecto leyendo sólo el repo.*

| pasada | agente | leyó | resultado |
|---|---|---|---|
| [1](reconstruction_pass1.md) | Claude, subagente de sólo lectura, sin conversación previa | `CLAUDE.md`, `docs/ai-development/*`, `tasks/M01.md` | 7 respondidas · 4 parciales · 1 sin respuesta |
| [2](reconstruction_pass2.md) | ídem, nueva instancia | lo anterior + `reports/M01_REPORT.md`, después de corregir | 11 respondidas · 1 parcial · 0 sin respuesta |

Las transcripciones están **condensadas por Claude**, en el inglés en que respondió el agente: se
acortó la prosa de cada respuesta y se conservaron **todas** las calificaciones y **todos** los
hallazgos, con su numeración. Son salida de un modelo: su valor es mostrar qué entiende alguien que
no estuvo en la conversación, no que tenga razón en todo. Qué se corrigió a partir de cada una está en
[`reports/M01_REPORT.md`](../../reports/M01_REPORT.md) §Evidencia.
