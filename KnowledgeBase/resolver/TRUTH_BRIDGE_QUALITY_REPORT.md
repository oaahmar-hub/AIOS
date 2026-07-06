# Truth Bridge Quality Report

Date: 2026-07-06
Source CSV: `KnowledgeBase/PropertyGraph/listing_bridge_master.csv`

## Architecture Terminology

1. Truth Acquisition
2. Truth Ingestion
3. Truth Bridge
4. Resolver
5. Unit Finder
6. Property Intelligence

## Summary

- Truth Bridge Quality score: `56.0/100`
- Exact bridge percentage: `3.5%` of all bridge rows
- Exact bridge percentage on rows with a public reference: `4.1%`
- High-confidence percentage: `55.5%` of all bridge rows
- Total bridge rows audited: `1244`
- Public-reference bridge rows: `1047`

## Quality Buckets

- `Exact`: `43` rows (3.5%)
- `High-confidence`: `691` rows (55.5%)
- `Partial`: `293` rows (23.6%)
- `Weak`: `20` rows (1.6%)
- `Unusable`: `197` rows (15.8%)

## Remaining Data Gaps

- `missing_unit_number`: `1011`
- `missing_hard_property_identifier`: `691`
- `missing_broker_or_building_anchor`: `293`
- `no_public_bridge_reference`: `197`
- `missing_cpid_link_or_hard_identifier`: `20`

## Highest-Value Source Uplift

- `BAYUT OVER ALL LEAD.xlsx`: uplift `651.3`, Exact `0`, High-confidence `616`, Partial `44`, Weak `19`, Unusable `1`
- `WhatsApp ChatStorage.sqlite`: uplift `105.0`, Exact `1`, High-confidence `0`, Partial `210`, Weak `0`, Unusable `11`
- `Listings (1).xlsx`: uplift `78.5`, Exact `42`, High-confidence `75`, Partial `7`, Weak `0`, Unusable `0`
- `Secondary Listings LINKS EXCEL.xlsx`: uplift `16.7`, Exact `0`, High-confidence `0`, Partial `32`, Weak `1`, Unusable `0`
- `HSHObject1__ab20a7e9-9ee0-4f16-910a-3e6399317a74__dda2658d56.xlsx`: uplift `0.0`, Exact `0`, High-confidence `0`, Partial `0`, Weak `0`, Unusable `1`

## Reading

- The bridge problem is now quality and completeness, not missing bridge infrastructure.
- Exact closure remains small because hard property identifiers are sparse across the largest imported listing feeds.
- The fastest exact-bridge gain is to enrich the strongest High-confidence rows with permit, property, or plot identifiers rather than adding more weak rows.
