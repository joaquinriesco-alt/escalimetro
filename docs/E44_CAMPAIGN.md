# E44 — Cómo correr la campaña (20 MEJORAR + 20 CREAR) sin abrir Internet al ejecutor

El ejecutor de GitHub/Claude no tiene red a propósito y E44 no lo cambia. La captura online la hace
una persona (o un script suyo) **fuera del ejecutor**; lo que entra a ESCALÍMETRO es un **bundle**
verificable. Código: `webapp/campaign.py`, CLI `scripts/e44_campaign.py`. Estado en
`DATA_DIR/e44/` (fuera del repo, que es público).

## Formato del bundle

```
bundle/
  bundle.json
  <archivos…>
```

```json
{"cases": [{
  "track": "IMPROVE | CREATE",
  "source_urls": ["https://…"],
  "captured_on": "AAAA-MM-DD",
  "source": "portal o corredora (nombre, no personas)",
  "property_type": "OFFICE | OFFICE_FLOOR | COMMERCIAL_UNIT",
  "published_m2": 120,
  "declared": {"total_area_m2": 120, "description": "…"},
  "notes": "sin emails ni teléfonos",
  "both_tracks_reason": null,
  "assets": [{"file": "plano.png", "role": "published_plan", "sha256": "<64 hex>",
              "origin_url": "https://…"}]
}]}
```

* IMPROVE: exactamente un asset `published_plan` (el plano tal como lo publica el corredor).
* CREATE: uno o más `photo` + exactamente un `ground_truth_plan`. El plano real **no** se copia a
  `evidence/` ni entra al manifiesto: se carga en la zona oculta de E37.
* Cada caso se acepta o se rechaza por separado, con motivo: sha256 distinto, falta de provenance,
  PII (email/teléfono), tipo fuera de oficinas, duplicado (misma URL canónica, mismo sha, o misma
  propiedad en la otra pista sin `both_tracks_reason` en ambos).
* Una URL sin material (`register_url_only`) queda `URL_ONLY` y **no suma a ningún N**.

## Pasos

```bash
export ESCALIMETRO_DATA_DIR=./.data-e44
python scripts/e44_campaign.py import <bundle>
python scripts/e44_campaign.py run-improve <case_id>        # camino real de Plano Corporativo
python scripts/e44_campaign.py run-create  <case_id> --confirm-paid   # requiere OPENAI_API_KEY
python scripts/e44_campaign.py correct <case_id> "texto"    # corrida HIJA (E37), sólo antes del cierre
python scripts/e44_campaign.py close   <case_id> --minutes N # cierre blind + auditoría de ceguera
python scripts/e44_campaign.py reveal  <case_id>             # recién ahora aparece el plano real
python scripts/e44_campaign.py status | index
```

La evaluación (dimensiones separadas, rating de Joaquín) se agrega con `campaign.record(case_id,
"evaluation" | "rating", {...})`; los valores válidos están en las constantes de `webapp/campaign.py`.
Sin `OPENAI_API_KEY`, `run-create` deja el caso en `BLOCKED_MISSING_CREDENTIAL`: nunca simula.
`index` escribe `DATA_DIR/e44/index.html`, una sección por caso.

## Reglas

* El estado se deriva de artefactos; los resultados son eventos de sólo inserción.
* `pipeline`, `closure` y `reveal` ocurren una sola vez por caso; el reveal exige el cierre; la
  evaluación CREAR exige el reveal. Una corrida ciega no se reescribe.
* El motor `fixture_replay` no puede ser el motor de un caso.
* PASS de la campaña = 20 + 20 **completados**; cualquier otra cosa es PARTIAL o BLOCKED.
