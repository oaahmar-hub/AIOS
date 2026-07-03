# Bridge Data Investigation Report

## Scope

Read-only investigation of existing internal datasets for exact public listing URL to unit mapping.

No Unit Finder algorithm, scoring, matching, resolver, or production logic was changed.

## Executive Result

- records_scanned: 89585
- url_rows_found: 790
- unique_listing_urls_found: 221
- direct_url_plus_unit_rows: 0
- direct_url_plus_identifier_rows_without_unit_link: 196
- direct_exact_url_to_unit_rows: 0
- combined_exact_url_count_supported: 0
- recommendation: `permanently_freeze_url_mapping_until_bridge_data`

## Source Coverage

| Source | Records | URL rows | Exact URL-to-unit rows | Exact coverage of URL rows | URL+unit | URL+identifier only | Broker ref rows | Broker ref+unit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| acquisition_index | 6256 | 0 | 0 | 0.00% | 0 | 0 | 0 | 0 |
| bitrix_crm | 81 | 0 | 0 | 0.00% | 0 | 0 | 1 | 0 |
| canonical_index | 2495 | 0 | 0 | 0.00% | 0 | 0 | 0 | 0 |
| hsh_internal | 35 | 0 | 0 | 0.00% | 0 | 0 | 0 | 0 |
| live_benchmark | 50 | 50 | 0 | 0.00% | 0 | 0 | 0 | 0 |
| other | 364 | 0 | 0 | 0.00% | 0 | 0 | 0 | 0 |
| raw_csv | 1049 | 0 | 0 | 0.00% | 0 | 0 | 0 | 0 |
| raw_pdf | 361 | 0 | 0 | 0.00% | 0 | 0 | 3 | 1 |
| raw_txt | 63 | 0 | 0 | 0.00% | 0 | 0 | 4 | 2 |
| raw_xlsx | 205 | 0 | 0 | 0.00% | 0 | 0 | 2 | 0 |
| resolver_csv | 52460 | 519 | 0 | 0.00% | 0 | 131 | 0 | 0 |
| resolver_database | 26166 | 221 | 0 | 0.00% | 0 | 65 | 0 | 0 |

## Combined-Source Feasibility

- combined bridge paths found: 0
- unique URL values that can be exactly bridged through shared listing ID, identifier, or broker reference: 0

- No combined-source exact bridge path found.

## Interpretation

- URL rows exist across resolver outputs, WhatsApp-derived rows, and raw/corpus files.
- Unit rows exist in large volume, especially inventory/owner/unit style datasets.
- Existing internal data does not show a reliable exact bridge from listing URL/listing ID/broker reference to a unit number.
- URL plus identifier rows exist, but no current source connects those URL-side identifiers to unit-bearing rows.
- Area/project/building similarity can support likely candidate matching, but it is not exact URL-to-unit evidence.

## Recommendation

Permanently freeze URL mapping until new bridge data is provided. Do not continue Unit Finder URL-to-unit work from current datasets.

Required future data remains:

- Listing reference, broker reference, or CRM export linked to unit number, permit, property number, plot, or land number.

## Evidence Files

- source_inventory_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeInvestigation/bridge_source_inventory.csv`
- candidate_evidence_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeInvestigation/bridge_candidate_evidence.csv`
- combined_paths_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeInvestigation/combined_bridge_paths.csv`
- summary_json: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeInvestigation/bridge_data_investigation_summary.json`
