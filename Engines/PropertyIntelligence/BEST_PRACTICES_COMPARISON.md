# Property Intelligence Best Practices Comparison

## Industry benchmark themes

- Property-level information should include ownership/management, unit mix, rent/sales history, comparable data, pipeline status, and location ratings.
- RAG and search systems should evaluate retrieval and generation separately, maintain test sets, and monitor quality over time.
- Knowledge systems need governance, metadata, ownership, duplicate detection, and stale-content controls.

## AIOS comparison

- Strength: AIOS already has raw inventory, resolver databases, aliases, matching scripts, and validation evidence.
- Strength: AIOS has duplicate indexes and relationship maps after this consolidation.
- Gap: URL-to-unit bridge remains incomplete.
- Gap: property schemas need a stable canonical database contract across inventory, floor plans, listings, and recommendations.
- Gap: recommendation quality needs benchmark test cases with expected answers.

## Improvement plan

1. Promote the schema in `SCHEMA_AND_RULES.md` into a single SQLite schema.
2. Build an importer per source type: spreadsheet, PDF floor plan, listing URL, owner record.
3. Add validation tests for exact identifier, building-unit, floor-plan, and recommendation queries.
4. Keep URL-only resolution classified as PARTIAL until exact bridge evidence exists.
