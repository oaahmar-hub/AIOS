# Truth Bridge Quality Report

- generated_at: `2026-06-27T02:55:02+00:00`
- truth_bridge_quality_score: `48.28/100`
- total_bridge_rows: `1247`

## Quality Distribution

- Exact: `42` (3.37%)
- High-confidence: `72` (5.77%)
- Partial: `738` (59.18%)
- Weak: `386` (30.95%)
- Unusable: `9` (0.72%)

## Highest-Value Improvement Sources

- BAYUT OVER ALL LEAD.xlsx: highest volume of URL/listing-id/broker-reference rows; needs same-row or linked permit/property/unit enrichment.
- Listings (1).xlsx and files with the same schema: currently the strongest exact bridge source.
- Secondary Listings LINKS EXCEL.xlsx joined with inventory/unit sheets: already has URLs and listing IDs, but lacks exact unit linkage.
- Active Listings.xlsx combined with portal export fields: has unit/building truth, but needs listing reference or permit linkage.
- CRM / Bitrix structured exports with broker reference, permit, property number, and unit in one row: highest-value missing bridge source.

## Remaining Data Gaps

- Public listing rows still rarely carry same-row unit number, property number, or permit number.
- Broker reference rows exist, but most are not yet linked to exact unit-bearing inventory records.
- Active Listings and Dubai_brokers contribute unit/building truth but weak public-bridge linkage.
- Bitrix24/raw sample and Runtime Memory Ledger did not contribute bridge-usable rows in current import.
- Only one public listing CPID is currently visible in PropertyGraph despite the higher bridge row count.

## Source Pressure

- `BAYUT OVER ALL LEAD.xlsx`: partial_like=`668`, exact_like=`11`, notes=`urls=575; listing_ids=746; broker_refs=703; resolver_links=12`
- `WhatsApp ChatStorage.sqlite`: partial_like=`220`, exact_like=`0`, notes=``
- `Dubai_brokers__Project__5d39d16462.xlsx`: partial_like=`53`, exact_like=`0`, notes=``
- `Listings (1).xlsx`: partial_like=`82`, exact_like=`42`, notes=`listing_ids=124; broker_refs=124; permits=42; units=16`
- `Secondary Listings LINKS EXCEL.xlsx`: partial_like=`30`, exact_like=`3`, notes=`urls=33; listing_ids=33; resolver_links=3`
- `Active Listings.xlsx`: partial_like=`16`, exact_like=`0`, notes=`units=16`
- `Reportage_Inventory__3014__39097fe6b2.xlsx`: partial_like=`2`, exact_like=`0`, notes=``
- `Reportage_Inventory__3014__69038f24c0.xlsx`: partial_like=`2`, exact_like=`0`, notes=``
- `Reportage_Inventory__3014__6ea2d12d01.xlsx`: partial_like=`2`, exact_like=`0`, notes=``
- `Reportage_Inventory__3014__abd925a1c4.xlsx`: partial_like=`2`, exact_like=`0`, notes=``

## Evidence

- rows_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/TruthIngestion/outputs/truth_bridge_quality_rows.csv`
- summary_json: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/TruthIngestion/outputs/truth_bridge_quality_summary.json`
