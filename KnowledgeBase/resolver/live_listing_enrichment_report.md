# Live Listing Enrichment Report

- input_url: `https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-dubai-marina-ocean-heights-84894360.html`
- fetch_bridge: `snapshot_cache_used_after_http_block`
- http_fetch_status: `blocked_cloudfront`

## Enriched public fields
- source_platform: `propertyfinder.ae`
- listing_id: `84894360`
- title: `Sea View | Huge Layout | Furnished | Upgraded`
- price_aed: `2200000`
- bedrooms: `2`
- bathrooms: `3`
- size_sqft: `1565`
- size_sqm: `145.0`
- building: `Ocean Heights`
- area: `Dubai Marina`
- developer: `Damac Properties`
- agent_name: `Jackson David Williams`
- agency_name: `YHU PROPERTIES L.L.C`
- broker_reference: `1038401677055`
- broker_license: `44204`
- agent_license: `64966`
- permit_number: `NOT VISIBLE`
- property_number: `NOT VISIBLE`
- plot_number: `NOT VISIBLE`
- land_number: `NOT VISIBLE`
- floorplan_urls_visible: `0`
- photo_urls_visible: `0`

## Matched local candidates
- url_only_top_status: `LIKELY_MATCH`
- enriched_top_status: `RESOLVED`
- top_candidate_record_id: `raw-e6d971645320b9b2`
- top_candidate_area: `Dubai Marina`
- top_candidate_project: ``
- top_candidate_building: `ocean heights`
- top_candidate_unit: `NOT FOUND`
- top_candidate_bedrooms: `2`
- top_candidate_size: `148.64 sqm`
- top_candidate_price: `3000000.0`
- top_candidate_source_file: `raw_chat_style_dataset`
- top_candidate_score: `98`
- top_candidate_score_breakdown: `["same_area:+10", "same_building:+20", "same_area_and_building_strong:+35", "same_property_type:+5", "same_bedrooms:+10", "size_within_5%:+15", "text_low:+3"]`

## Exact resolution
- exact_unit_found: `NOT FOUND`
- confidence_score: `98`

## Failure chain
- live listing did not expose a text permit number in the fetched page content
- no public property number was visible
- no local candidate contains a unit field linked to the live listing identifiers
- local best candidate is chat-derived text, not a direct public-listing record

- candidates_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/live_listing_enrichment_candidates.csv`
