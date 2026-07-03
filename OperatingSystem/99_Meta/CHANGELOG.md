# Changelog

## OS v1.2 — 2026-06-25
**Production-grade security verification + documentation defect fix.**
- Found and fixed one documentation defect: `RAILWAY_DEPLOY.md` incorrectly described the webhook as "open unless a secret is set"; live test confirmed it is **fail-closed (401) when `AIOS_WEBHOOK_SECRET` is unset**. Fixed lines 31–32, 60, 71, 85. `AIOS_WEBHOOK_SECRET` now marked **Required** in the env table.
- All 7 security sections verified from current source code with live evidence (no reliance on prior reports).
- Zero code changes required — all 7 sections PASS; one documentation defect resolved.

## OS v1.1 — 2026-06-23
**Backend security hardening + secure deploy asset.**
- [app.py](../../deployment/hosted-backend/app.py): API now **fail-closed** (401 without `AIOS_BASIC_AUTH_*`; was open by default), stack traces no longer returned to clients (logged only), request body capped (`AIOS_MAX_BODY_BYTES`, 413), `/api/runtime-truth` no longer leaks the absolute path, startup logs security posture + warnings. `AIOS_REQUIRE_AUTH=0` opt-out for local dev. All verified by test (fail-closed 401, opt-out 200, good/bad creds, 413, no trace leak).
- Docs: [RAILWAY_DEPLOY.md](../../deployment/hosted-backend/RAILWAY_DEPLOY.md) + [README.md](../../deployment/hosted-backend/README.md) mark auth/origin **Required**, add a Security-posture section, fix the `/api/ask` smoke test to use `-u`, correct the endpoint list.
- Added [SOP10 Backend Deploy (Railway)](../03_SOPs/SOP10_Backend_Deploy_Railway.md) as a reusable OS asset. Decision [D003](../05_Systems/Decisions/decision_log.csv). Projects P005 updated, P006 done.

## OS v1.0 — 2026-06-23
**Built the operating layer (control plane) on top of the existing AIOS engine.**

Added `OperatingSystem/`:
- Master control file + Start-Here onboarding.
- 12 specialist agents (A01–A12) + index + template.
- 11 workflows (WF01–WF11) + index.
- 9 SOPs (SOP01–SOP09) + index.
- 10 templates (T01–T10) + index.
- 6 systems: Daily Planning, Weekly Review, Decisions (+log), Projects (+register), Research, Personal Assistant.
- KB Master Index mapping the existing `KnowledgeBase/` engine.
- Command Center dashboard + pipeline tracker.
- Meta: Verification table, Blockers, Roadmap, Maintenance, this changelog.

Design decisions: [D001, D002 in decision_log.csv](../05_Systems/Decisions/decision_log.csv).
Honored existing canon: one brain / one source of truth / patch-don't-rebuild / Risk-Hold / Omar voice.

Known blockers carried from engine status: B1 CRM write-back, B2/B3 persistence, B4 URL→unit bridge, B5 WhatsApp replay, B6 production. See [BLOCKERS](BLOCKERS.md).
