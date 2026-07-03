# AIOS Bridge Engine Architecture Report

## Scope

This is a modular Bridge Engine framework. It does not modify Unit Finder scoring, matching, resolver logic, or production WhatsApp logic.

The current deterministic URL-to-unit bridge remains frozen because current data does not provide exact URL-to-unit coverage. The Unit Finder product remains extensible through bridge strategies marked AVAILABLE or WAITING_FOR_DATA.

## Current Bridge Investigation Evidence

- records_scanned: 89585
- unique_listing_urls_found: 221
- direct_url_plus_unit_rows: 0
- direct_exact_url_to_unit_rows: 0
- combined_exact_url_count_supported: 0

## Supported Bridges

| Bridge | Current Availability | Current Evidence | Result Semantics | Future Data Required |
|---|---|---|---|---|
| direct_url_to_unit | WAITING_FOR_DATA | 0 direct URL+unit rows | EXACT only when same row has listing URL and unit | Listing URL row containing a real unit number or linked hard identifier that resolves to a unit. |
| listing_reference_to_unit | WAITING_FOR_DATA | Listing IDs exist, but no reliable listing ref to unit dataset | EXACT only when listing reference row contains unit | Listing ID/reference export linked to unit number or hard property identifier. |
| broker_reference_to_unit | WAITING_FOR_DATA | No structured broker reference index in current resolver data | EXACT only when broker reference row contains unit | Broker reference export linked to unit number or hard property identifier. |
| permit_to_unit | PARTIAL_AVAILABLE | Permit records exist, current unit-bearing permit rows are 0 | HIGH_CONFIDENCE for identifier exists; EXACT only if unit attached | Permit dataset linked to unit-bearing property rows. |
| property_number_to_unit | AVAILABLE | Property number records include unit-bearing rows | EXACT when property number row contains unit | Property number records linked to unit numbers. |
| plot_land_to_unit | PARTIAL_AVAILABLE | Plot/land records exist; unit-bearing coverage is limited | EXACT when plot/land row contains unit | Plot/land records linked to unit-bearing inventory rows. |
| ai_similarity_candidate_matching | AVAILABLE | Candidate matching available from area/project/building/unit clues | Never exact by itself; returns HIGH_CONFIDENCE or CANDIDATE_MATCHES | No mandatory new data. Higher quality area/building/size/price text improves ranking. |

## Outcome Contract

- `EXACT_MATCH`: the bridge has hard same-row or indexed evidence connecting input to a unit-bearing record.
- `HIGH_CONFIDENCE`: a hard identifier exists or strong strategy evidence exists, but the exact unit bridge is incomplete.
- `CANDIDATE_MATCHES`: usable candidate records exist, but exact identity is not proven.
- `NO_MATCH`: the strategy is available but found no matching data.
- `WAITING_FOR_DATA`: the capability exists, but required source data is unavailable in current datasets.

## Strategy Test Output

- tests_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeEngine/bridge_engine_strategy_tests.csv`
- manifest_json: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeEngine/bridge_engine_manifest.json`

## Recommendation

Build and keep the modular Bridge Engine. Do not continue deterministic URL-to-unit mapping until new bridge data arrives. Connect future Property Finder, Bayut, CRM, broker export, or DLD datasets by adding adapters into the existing bridge strategies rather than redesigning Unit Finder.
