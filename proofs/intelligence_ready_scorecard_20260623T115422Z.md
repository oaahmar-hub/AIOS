# AIOS Intelligence Ready Scorecard

Generated: 2026-06-23T11:54:25.011893+00:00

Runtime Ready: PASS
Production Ready: UNPROVEN
Intelligence Ready: FAIL

Evidence:
- Regression replay: regression_replay_validation_20260623T115422Z.json
- CRM write-back: crm_writeback_validation_20260623T115422Z.json
- Persistent context: persistent_context_restore_20260623T115422Z.json
- Unit resolver: unit_resolver_validation_20260623T115422Z.json

Notes:
- Runtime replay no longer crashes on local path or missing state session.
- CRM write-back remains not live without connector configuration.
- Relationship memory restores from persisted store, but persisted DNA/weather sources are not present.
- General unit coverage is strong; URL-linked completeness is still part-live only.
