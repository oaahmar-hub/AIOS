# CLAUDE.md — AIOS session context

Auto-loaded at the start of every Claude Code session in this repo. Read it first, then
work from the linked files. Keep it short and current; it is an **index**, not the source of truth.

## What AIOS is
HSH AI OS — a file-based **business operating system** for **Omar Ahmar / Home Sweet Home
Real Estate (HSH)**, Dubai + Abu Dhabi. Not a CRM or chatbot: a command center you drive in
plain language while Claude executes against live tools (Airtable, Gmail, Calendar, Drive,
WhatsApp gateway, n8n) and a local knowledge engine.
Official classification today: **PARTIAL live** (see `00_FOUNDATION/AIOS_EXECUTIVE_REPORT.md`).

## The two rules that govern everything here
1. **Honesty over impressiveness** (the "Truth Bridge" discipline). Never state a specific
   unit, price, size, availability, owner, or link that isn't in verified context. Report real
   status — flag what is unverified rather than asserting it. Never report a likely/partial
   match as exact.
2. **Patch and cross-reference — never delete or overwrite originals.** If a file is
   superseded, point to the newer canonical path and preserve the original as evidence.
   Authority order: live runtime proof > official memory/validation reports > OS
   agents/workflows/SOPs > canonical indexes > archives.

## Repo layout (where things live)
| Area | Path | What's there |
|---|---|---|
| Governance / standards | `00_FOUNDATION/` | Autonomy policy, engineering/reporting/validation standards, executive report |
| Operating System | `OperatingSystem/` | Start here: `00_START_HERE.md` → `AIOS_OS.md`. 12 agents (`01_Agents/` A01 Chief of Staff → A12 Unit Finder), workflows, Dubai RE SOPs, templates, dashboards, `99_Meta/BLOCKERS.md` |
| Personality (the brain) | `PersonalityEngine/` | `omar_personality_engine.py`, Omar profile V1, reply policy, EN+AR regression suites |
| Live API + reply path | `automation/central_orchestrator/runtime/` | `aios_live_api_server.py` (~1.4k lines), `aios_brain_runtime.py`, `inventory_retrieval.py` |
| Unit intelligence | `automation/unit_intelligence/runtime/` | URL parsers, ingestion queue, bridge enrichment, feed adapters, CRM write-back (dry-run) |
| Knowledge / Truth Bridge | `KnowledgeBase/` | Resolver (`resolver/`, ~26.3k records), `PropertyGraph/`, `TruthIngestion/` quality pipeline, memory layer |
| Reports / status | repo root | `CEO_REPORT_YYYY-MM-DD.md`, `AIOS_STATUS_REPORT.md`, `CASCADE_PROGRESS_LOG.md` |
| Full system census | repo root | `AIOS_PROJECT_INVENTORY.md` — every page, agent, engine, and KB subsystem in one map |

## Live runtime
- Backend on Railway: `https://aios-runtime-production.up.railway.app` (LIVE per last deploy; re-verify — see below).
- Key endpoints: `/api/health`, **`/api/health/deep`** (end-to-end reply-chain check, returns
  `healthy|degraded|down` + `reply_chain_live`), `/api/deployment/status`, `/api/unit/stats`,
  `/api/property/resolve`, `/api/unit/ingest`, `/app/` (React command center),
  `/webhook/whatsapp/provider/gateway` (Wasender). `/api/*` sits behind basic auth.
- Note: from a sandboxed web session, outbound is proxied and Railway may not be reachable —
  that is an environment limit, **not** proof production is down. Confirm via `/api/health/deep`.

## How the WhatsApp brain answers (current, honest)
Message → `inventory_retrieval.py` parses area/building/bedrooms/budget (EN + AR) → searches
resolver for **quotable** rows (real area + building + unit + price-or-size) → injects a
VERIFIED context block into the Omar personality prompt → reply. No anchor found → no results →
no-fabrication rule keeps the reply at "I'll check and confirm." Delivery loop: send + dedupe
(by `message_id`) + graceful fallback so a failing brain never means silence.

## Tests (run before deploy)
```bash
# self-running suites (have a __main__ runner)
python3 test_smoke.py
python3 automation/unit_intelligence/runtime/test_unit_intelligence.py
python3 automation/unit_intelligence/runtime/test_unit_intelligence_api.py
# pytest-style suites — MUST run under pytest. `python3 <file>.py` on these
# runs ZERO tests and exits 0 (false green). `pip install pytest` if missing.
python3 -m pytest \
  automation/central_orchestrator/runtime/test_inventory_retrieval.py \
  automation/central_orchestrator/runtime/test_whatsapp_reply_delivery.py \
  automation/central_orchestrator/runtime/test_deep_health.py -q
```
Last full run (2026-07-08): all green — smoke ok · unit_intelligence 13 · api integration ok · inventory_retrieval 6 · whatsapp_reply_delivery 7 · deep_health 3.

## Autonomy (from `00_FOUNDATION/AUTONOMY_POLICY.md`)
Proceed autonomously when the action is **reversible, local, and evidence-building** (read/index
files; create reports, scripts, validation outputs; run local diagnostics). **Pause for Omar's
approval** when it binds the owner, spends money, changes a live external system, deletes
evidence, or touches credentials/security — e.g. portal submission, payment, CRM go-live,
production deploy/domain, secret rotation.

## Open blockers (owned by Omar) — see `OperatingSystem/99_Meta/BLOCKERS.md`
- **B1** CRM write-back not live — needs Airtable keys (`AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`,
  `AIRTABLE_LEADS_TABLE`, `AIRTABLE_CONTACTS_TABLE`). Write-back code is dry-run until then.
- **B4** URL → exact-unit bridge thin (54 exact vs 795 partial) — a **data** gap; needs an
  authorized CRM/portal export carrying unit + permit + listing reference in one row. Unit
  Finder is **frozen backlog** until website/WhatsApp/app priorities are done.
- **B6** Production: custom domain not attached; re-run public-beta validation without skips.
- Truth Bridge Quality: **55.5/100** (was 48.3). 237 quotable rows feeding the brain today.

## Working conventions
- PDFs are `.gitignore`d — deliver report PDFs to the user directly, don't commit them.
- The paths inside older logs referencing `/Users/hassanka/...` are from the author's local Mac;
  in this environment the repo root is the current working directory.
