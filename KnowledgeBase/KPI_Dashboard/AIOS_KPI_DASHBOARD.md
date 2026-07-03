# AIOS KPI Dashboard

- generated_at: `2026-06-27T04:09:32+00:00`
- strongest_metric: `Knowledge Health`
- weakest_metric: `Truth Health`

| Metric | Score | Status | Trend | Biggest bottleneck | Highest-impact improvement |
| --- | --- | --- | --- | --- | --- |
| Truth Health | 56.19 | PARTIAL | BASELINE | Public listing rows still rarely carry same-row unit number, property number, or permit number. | BAYUT OVER ALL LEAD.xlsx: highest volume of URL/listing-id/broker-reference rows; needs same-row or linked permit/property/unit enrichment. |
| Memory Health | 75.0 | STABLE | BASELINE | Runtime memory ledger is present but not producing structured trusted memory rows. | Convert runtime memory and Bitrix raw history into structured, source-linked memory packets with entity-level provenance. |
| Knowledge Health | 84.38 | STRONG | BASELINE | Knowledge provenance is concentrated in a small set of explicit vault sources relative to the wider canonical corpus. | Expand source-indexed Knowledge Vault ingestion and attach stronger provenance links from canonical files into reusable case/playbook knowledge. |
| Decision Health | 57.22 | PARTIAL | BASELINE | identifier present but no matching complete record:379 | Promote exact bridge sources into canonical property links and reduce the verification queue by resolving bridge rows with hard identifiers. |

## Notes

- Scores optimize for trusted intelligence, not raw row volume.
- `BASELINE` trend means this is the first permanent snapshot for that metric in the KPI history.

## Evidence

- current_json: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/KPI_Dashboard/aios_kpi_current.json`
- history_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/KPI_Dashboard/aios_kpi_history.csv`
