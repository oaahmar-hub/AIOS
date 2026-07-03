# AIOS Knowledge Source Verification for Unit Finder

Bridge coverage classification: **PARTIAL: direct identifier coverage exists in current resolver data, but verified bridge-source coverage is incomplete because multiple high-value Google Drive bridge datasets are available and not indexed.**

## Verified Sources

| Source | Available | Indexed UF | Indexed Bridge | Searchable UF | Searchable Bridge | Key Evidence |
|---|---|---|---|---|---|---|
| 126 acquired property datasets (acquisition_index + raw_data) | AVAILABLE | YES | PARTIAL | YES | PARTIAL | acquisition_index=6256 files; unit_resolver_index=26166 rows; 25945 rows sourced from raw_data; bridge manifest shows 221 url records / 217 listing ids / 15 permit / 149 property / 317 plot-land. |
| Home Sweet Home inventory (local HSHObject1 raw) | AVAILABLE | YES | PARTIAL | YES | PARTIAL | resolver rows matching HSHObject1=748; sampled workbook shows District=JVC with columns unique name, floor, unit number, bedrooms, area, price. |
| Google Drive synchronized knowledge - Listings.xlsx / Listings (1).xlsx | AVAILABLE_VIA_CONNECTOR | NO | NO | NO | NO | Drive fetch shows columns ID, Reference, Transaction Number, Permit Number, Location 1-6, Beds, Baths, Area, Unit No, Portals; overlap checks for refs/listing_ids/permits in current resolver+bridge returned false. |
| Google Drive synchronized knowledge - Active Listings.xlsx | AVAILABLE_VIA_CONNECTOR | NO | NO | NO | NO | Drive fetch shows Listing ID, Reference No., Unit Number, Permit Number, Portal=Bayut, area/building/unit/price rows; not present in current resolver/bridge tables. |
| Google Drive synchronized knowledge - Secondary Listings LINKS EXCEL.xlsx | AVAILABLE_VIA_CONNECTOR | NO | NO | NO | NO | Drive fetch shows Property Link with Property Finder URLs, listing IDs inside URLs, bed/size/price/location, but no unit/permit columns. |
| Google Drive synchronized knowledge - BAYUT OVER ALL LEAD.xlsx | AVAILABLE_VIA_CONNECTOR | NO | NO | NO | NO | Drive fetch shows Listing ID, Reference No., location/sub-location, Bayut links embedded in message text, agent and lead context; no unit column observed. |
| Local AIOS Knowledge Base root | AVAILABLE | PARTIAL | PARTIAL | PARTIAL | PARTIAL | KnowledgeBase contains raw_data, organized_master, resolver, BridgeEngine, PropertyGraph, Bitrix24, Operations_Corpus; current engines mainly ingest resolver/unit_resolver_index plus graph derivatives, not the full root. |
| Reportage datasets | AVAILABLE | YES | PARTIAL | YES | PARTIAL | 72 raw files; resolver rows matching Reportage_Inventory=20506; bridge rows matching Reportage=60; sampled workbook is availability list style, mostly unit/building/inventory data. |
| TIGER datasets | AVAILABLE | YES | PARTIAL | YES | PARTIAL | 5 raw files; resolver rows matching TIGER=330; bridge rows matching TIGER=6; sampled workbook contains Unit, Type, Net(sqft), Original Price, Status across project sheets. |
| Dubai Brokers datasets | AVAILABLE | NO | NO | NO | NO | 1 raw file; resolver rows matching Dubai_brokers=0; sampled workbook has Project, Floor Number, Flat No., Unit Number, Price, Location/View, Unit Status. |
| Bitrix exports / CRM-style raw data | AVAILABLE | NO | NO | NO | NO | Bitrix24/raw exists with messages.csv and metadata exports, but current local raw scan found no verified listing bridge fields and resolver/bridge rows matching Bitrix=0. |
| Runtime Memory Ledger / AIOS memory archives | AVAILABLE | NO | NO | NO | NO | Files exist: OPENAI_MEMORY_ARCHIVE_MANIFEST.txt, OPENAI_MEMORY_MASTER_ARCHIVE.zip, unified memory runtime/report files. They are not part of current property indexing. |
| Previously indexed property graph data | AVAILABLE | N/A_DERIVED_LAYER | YES | INDIRECT | YES | PropertyGraph summary: resolver_records=26166, canonical_properties=83, bridge_rows=332, public_listing_cpid_count=1, bridge_status waiting_for_data=209; current graph is searchable but under-connected. |
| Mac local AIOS folders outside KnowledgeBase (AIOS_KNOWLEDGE_CONTROL, AIOS_MAC_TRANSFER, outputs/AIOS) | AVAILABLE | NO | NO | NO | NO | Sampled files are status/control docs and transfer notes, not property bridge datasets. |

## A. Data Exists but Is NOT Indexed

- **Google Drive synchronized knowledge - Listings.xlsx / Listings (1).xlsx**: Drive fetch shows columns ID, Reference, Transaction Number, Permit Number, Location 1-6, Beds, Baths, Area, Unit No, Portals; overlap checks for refs/listing_ids/permits in current resolver+bridge returned false.
- **Google Drive synchronized knowledge - Active Listings.xlsx**: Drive fetch shows Listing ID, Reference No., Unit Number, Permit Number, Portal=Bayut, area/building/unit/price rows; not present in current resolver/bridge tables.
- **Google Drive synchronized knowledge - Secondary Listings LINKS EXCEL.xlsx**: Drive fetch shows Property Link with Property Finder URLs, listing IDs inside URLs, bed/size/price/location, but no unit/permit columns.
- **Google Drive synchronized knowledge - BAYUT OVER ALL LEAD.xlsx**: Drive fetch shows Listing ID, Reference No., location/sub-location, Bayut links embedded in message text, agent and lead context; no unit column observed.
- **Dubai Brokers datasets**: 1 raw file; resolver rows matching Dubai_brokers=0; sampled workbook has Project, Floor Number, Flat No., Unit Number, Price, Location/View, Unit Status.
- **Runtime Memory Ledger / AIOS memory archives**: Files exist: OPENAI_MEMORY_ARCHIVE_MANIFEST.txt, OPENAI_MEMORY_MASTER_ARCHIVE.zip, unified memory runtime/report files. They are not part of current property indexing.

## B. Data Does NOT Exist (verified current state)

- No verified local Google Drive sync folder containing the bridge spreadsheets. Drive access exists via connector, but local sync path was not found.
- No verified structured broker-reference index in current resolver/property-graph outputs.
- No verified local raw Bitrix bridge rows linking listing URL or broker reference directly to unit/permit/property identifiers.

## C. Data Exists but Cannot Currently Be Connected

- Secondary Listings LINKS EXCEL has URLs and listing IDs but no unit or permit on the same rows, so it cannot resolve exact units alone.
- BAYUT OVER ALL LEAD has listing IDs and references with lead context, but no verified unit column in sampled output.
- Runtime memory archives may contain clues in text, but they are not indexed into a structured property bridge layer.
- PropertyGraph exists and is searchable, but public_listing_cpid_count=1 proves bridge coverage is still thin.

## Recommended Indexing Order

- 1. Import Google Drive Active Listings.xlsx and Listings.xlsx / Listings (1).xlsx into the bridge layer first. They contain the strongest structured combination of listing id/reference + permit + building + unit.
- 2. Import BAYUT OVER ALL LEAD.xlsx second. It provides listing id/reference plus live lead context and can connect portal activity to bridge rows.
- 3. Import Secondary Listings LINKS EXCEL.xlsx third. It supplies Property Finder URLs and listing IDs that can attach to the structured Drive listing references.
- 4. Index Dubai_brokers local workbook next. It has explicit unit numbers and building/project structure that are currently absent from resolver rows.
- 5. Re-scan Bitrix24/raw and memory archives only after the structured bridge imports. They are lower-authority and harder to normalize.

## Key Findings

- Earlier missing-data conclusions were too broad. Some bridge data does exist, especially in Google Drive exports, but it is outside the current resolver/bridge ingestion path.
- Current Unit Finder and Bridge Engine are dominated by `resolver/unit_resolver_index.csv` and PropertyGraph derivatives, not the full AIOS knowledge source universe.
- The strongest verified unindexed bridge sources are `Listings.xlsx`, `Listings (1).xlsx`, `Active Listings.xlsx`, `Secondary Listings LINKS EXCEL.xlsx`, and `BAYUT OVER ALL LEAD.xlsx` from Google Drive.
- The strongest verified local indexed sources remain Reportage, TIGER, HSHObject1, and the broader raw-data acquisition corpus.

## Output Files

- CSV: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeInvestigation/knowledge_source_verification.csv`
- Report: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeInvestigation/knowledge_source_verification_report.md`