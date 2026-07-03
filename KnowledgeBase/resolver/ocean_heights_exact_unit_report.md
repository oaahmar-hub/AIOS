# Ocean Heights Exact Unit Audit

- input_url: `https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-dubai-marina-ocean-heights-84894360.html`
- final_status: LIKELY_MATCH
- exact_unit_status: UNIT_NOT_FOUND
- confidence_score: 80
- unit_found: `NOT FOUND`
- top_candidate_record_id: `raw-e6d971645320b9b2`
- top_candidate_area: `Dubai Marina`
- top_candidate_building: `ocean heights`
- top_candidate_bedrooms: `2`
- top_candidate_size: `148.64 sqm`
- top_candidate_price: `3000000.0`
- top_candidate_source_file: `raw_chat_style_dataset`
- top_candidate_score_breakdown: `["same_area:+10", "same_building:+20", "same_area_and_building_strong:+35", "same_property_type:+5", "text_overlap_50:+10"]`

## Candidate chain evidence
- similarity_candidates_logged: 1
- direct_listing_id_or_url_hits_in_db: 0
- related_identifier_rows_in_db: 0
- raw_source_cluster_rows_logged: 12
- evidence_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/ocean_heights_candidate_chain.csv`

## Exact unit resolution improvements
- Ocean Heights URL now resolves to a building-level likely match instead of unresolved.
- Price normalization upgraded the raw Ocean Heights row from `2.0` to `3000000.0`.
- Area + building + property-type signals now combine into a stable candidate chain.
- Exact unit completion failed because no linked permit/property/plot/listing record or unit-bearing companion row was found locally.

## Updated resolver statistics
- total_records_indexed: 26166
- unit_records_resolved: 6992
- remaining_unresolved_records: 19174
- listing_urls_found: 221
- listing_ids_extracted: 216
- restricted_owner_contact_rows: 23160
- confidence_distribution_90_plus: 5664
- confidence_distribution_80_89: 1921
- confidence_distribution_below_70: 18581

## Final evidence-based verdict
- exact unit was not discovered locally in the indexed resolver DB, raw chat cluster, or scanned raw XLSX corpus.
- current best local match remains building-level only.
- restricted owner/contact data remains protected because confidence is below exact-unit threshold and no unit-complete record was found.
