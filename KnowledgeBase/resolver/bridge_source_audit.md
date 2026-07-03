# Bridge Source Audit

- total rows with listing URL + unit: 0
- total rows with listing URL + permit/property/plot: 8
- total rows with broker reference + unit: 0
- total WhatsApp messages containing link + unit number: 0
- strongest bridge source found: area+project likely-only bridge
- exact URL -> unit possible internally: NO

## Bridge source availability
- listing screenshots: missing | 0 OCR-indexed screenshot bridge rows in resolver outputs
- broker reference databases: missing | 0 rows with broker-reference-like text + unit
- agent/company inventory exports: partially available | 24,357 local unit rows exist, but 0 contain listing URL + unit
- Property Finder reports/export files: partially available | Property Finder URLs present in corpus; 0 meaningful listing URL + unit rows
- Bayut/Dubizzle saved listing exports: partially available | 82 listing URL + identifier rows exist, but 0 meaningful identifier bridges
- DLD/Dubai REST/permit datasets: partially available | Permit/plot fields exist in corpus pockets, but 0 benchmark listings bridge through meaningful identifiers
- CRM records: missing | No local CRM-shaped listing URL + unit dataset detected
- WhatsApp messages that include both listing link and unit number: missing | 0 WhatsApp messages with link + unit
- old Excel files with listing URL + unit number: missing | 0 resolver rows with listing URL + unit
- owner/unit databases: available now | Large local owner/unit corpus exists but without listing-link bridge

## Bridge candidate summary
- exact bridge possible rows: 0
- likely bridge possible rows: 2
- no local bridge rows: 48

## Strongest internal examples
- https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html | bridge=area+project | evidence=direct_listing_rows=1;same_area_project_units=3
- https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78182876.html | bridge=area+project | evidence=direct_listing_rows=1;same_area_project_units=3

## Verdict
- Internal corpus contains listing rows and a large unit corpus, but no exact bridge rows joining live listing URLs to unit-bearing records.
- The only internal bridge found is area/project overlap, which stays likely-only rather than exact.

- audit_csv: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/bridge_source_audit.csv`
