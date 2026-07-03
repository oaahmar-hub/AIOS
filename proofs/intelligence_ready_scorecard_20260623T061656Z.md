# AIOS Intelligence Ready Scorecard

Generated: 2026-06-23T06:16:57.122697+00:00

Runtime Ready: PARTIAL PASS
Production Ready: UNPROVEN
Intelligence Ready: FAIL

Evidence:
- Regression replay: regression_replay_validation_20260623T061656Z.json
- CRM write-back: crm_writeback_validation_20260623T061656Z.json
- Persistent context: persistent_context_restore_20260623T061656Z.json
- Unit resolver: unit_resolver_validation_20260623T061656Z.json

Notes:
- Runtime replay no longer crashes on local path or missing state session.
- CRM write-back remains not live without connector configuration.
- Relationship memory restores from persisted store, but persisted DNA/weather sources are not present.
- General unit coverage is strong; URL-linked completeness is still part-live only.
