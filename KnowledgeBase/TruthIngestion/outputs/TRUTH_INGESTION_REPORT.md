# AIOS Truth Ingestion Report

- generated_at: `2026-06-27T02:46:08+00:00`
- truth_bridge_classification: `PARTIAL`
- imported_rows: `912`

## Coverage Delta

- bridge_rows_before: `332`
- bridge_rows_after: `1244`
- exact_bridge_before: `12`
- exact_bridge_after: `54`
- public_listing_cpid_before: `1`
- public_listing_cpid_after: `1`
- url_records_before: `221`
- url_records_after: `221`
- listing_reference_before: `220`
- listing_reference_after: `220`
- permit_records_before: `15`
- permit_records_after: `15`
- property_number_before: `149`
- property_number_after: `149`

## Source Status

| priority | source | available | imported_rows | exact_bridge | partial_bridge | candidate_bridge | invalid_bridge | resolver_links | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Active Listings.xlsx | YES | 16 | 0 | 0 | 0 | 16 | 0 | units=16 |
| 2 | Listings.xlsx | YES | 17 | 0 | 17 | 0 | 0 | 0 | listing_ids=17; broker_refs=17 |
| 3 | Listings (1).xlsx | YES | 124 | 42 | 82 | 0 | 0 | 0 | listing_ids=124; broker_refs=124; permits=42; units=16 |
| 4 | BAYUT OVER ALL LEAD.xlsx | YES | 855 | 0 | 746 | 0 | 109 | 12 | urls=575; listing_ids=746; broker_refs=703; resolver_links=12 |
| 5 | Secondary Listings LINKS EXCEL.xlsx | YES | 34 | 0 | 33 | 0 | 1 | 3 | urls=33; listing_ids=33; resolver_links=3 |
| 6 | Dubai_brokers | YES | 95 | 0 | 0 | 0 | 95 | 0 | units=87 |
| 7 | Bitrix24/raw | YES | 0 | 0 | 0 | 0 | 0 | 0 | available but no bridge-usable rows detected |
| 8 | Runtime Memory Ledger | YES | 0 | 0 | 0 | 0 | 0 | 0 | available but no bridge-usable rows detected |

## Remaining Unindexed Truth

- `Bitrix24/raw`: available but no bridge-usable rows detected
- `Runtime Memory Ledger`: available but no bridge-usable rows detected

## Evidence

- normalized_rows_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/TruthIngestion/outputs/truth_ingestion_normalized_bridge_rows.csv`
- source_status_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/TruthIngestion/outputs/truth_ingestion_source_status.csv`
- summary_json: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/TruthIngestion/outputs/truth_ingestion_summary.json`
- bridge_export_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/bridge_records_export.csv`
- property_graph_summary: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/PropertyGraph/property_graph_summary.json`
- bridge_engine_manifest: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeEngine/bridge_engine_manifest.json`
