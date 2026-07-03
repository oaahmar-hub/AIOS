# AIOS Engineering Standards

## Core standards

- Preserve working implementations; patch the missing layer instead of rebuilding.
- Use reproducible scripts for indexes, reports, and validation outputs.
- Keep configuration, credentials, and secrets outside committed documents.
- Every engine must expose input schema, output schema, validation rules, and proof paths.
- Every user-facing status must be evidence-backed: LIVE, PARTIAL, BLOCKED, FAIL, or UNPROVEN.

## Interoperability requirements

- Shared project identifiers must be normalized across modules.
- Reports must link to source evidence, not only summaries.
- Validation outputs must be machine-readable when practical: CSV, JSON, SQLite, or structured Markdown.
- Duplicate logic must be consolidated into shared rules rather than copied into each agent.
