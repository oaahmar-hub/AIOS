# AIOS Validation Standards

## Minimum validation gates

- File existence and non-empty content.
- Extractability for PDFs and spreadsheets where possible.
- Duplicate/fingerprint check.
- Cross-reference check against canonical inventory.
- Module-specific functional test.
- Evidence path recorded in the report.

## AI/RAG validation gates

- Retrieval coverage: can the system find the right evidence?
- Answer grounding: does the output cite or link evidence?
- Rule coverage: are validation rules explicit and reusable?
- Regression set: does a golden project produce stable results?
