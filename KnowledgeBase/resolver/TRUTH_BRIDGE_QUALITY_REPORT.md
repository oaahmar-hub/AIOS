# Truth Bridge Quality Report

Date: 2026-06-27
Source CSV: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/PropertyGraph/listing_bridge_master.csv`

## Architecture Terminology

1. Truth Acquisition
2. Truth Ingestion
3. Truth Bridge
4. Resolver
5. Unit Finder
6. Property Intelligence

## Summary

- Truth Bridge Quality score: `52.8/100`
- Exact bridge percentage: `4.3%` of all bridge rows
- Exact bridge percentage on rows with a public reference: `5.1%`
- High-confidence percentage: `57.2%` of all bridge rows
- Total bridge rows audited: `1244`
- Public-reference bridge rows: `1058`

## Quality Buckets

- `Exact`: `54` rows (4.3%)
- `High-confidence`: `711` rows (57.2%)
- `Partial`: `84` rows (6.8%)
- `Weak`: `209` rows (16.8%)
- `Unusable`: `186` rows (15.0%)

## Remaining Data Gaps

- `missing_unit_number`: `833`
- `missing_hard_property_identifier`: `711`
- `missing_cpid_link_or_hard_identifier`: `209`
- `no_public_bridge_reference`: `186`
- `missing_broker_or_building_anchor`: `84`

## Highest-Value Source Uplift

- `BAYUT OVER ALL LEAD.xlsx`: uplift `657.5`, Exact `0`, High-confidence `636`, Partial `43`, Weak `0`, Unusable `1`
- `WhatsApp ChatStorage.sqlite`: uplift `146.8`, Exact `12`, High-confidence `0`, Partial `1`, Weak `209`, Unusable `0`
- `Listings (1).xlsx`: uplift `78.5`, Exact `42`, High-confidence `75`, Partial `7`, Weak `0`, Unusable `0`
- `Secondary Listings LINKS EXCEL.xlsx`: uplift `16.5`, Exact `0`, High-confidence `0`, Partial `33`, Weak `0`, Unusable `0`
- `HSHObject1__ab20a7e9-9ee0-4f16-910a-3e6399317a74__dda2658d56.xlsx`: uplift `0.0`, Exact `0`, High-confidence `0`, Partial `0`, Weak `0`, Unusable `1`

## Reading

- The bridge problem is now quality and completeness, not missing bridge infrastructure.
- Exact closure remains small because hard property identifiers are sparse across the largest imported listing feeds.
- The fastest exact-bridge gain is to enrich the strongest High-confidence rows with permit, property, or plot identifiers rather than adding more weak rows.
