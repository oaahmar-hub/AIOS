# Blockers

Only blockers that stop progress. Each names the impact, the exact fix, and what is unblocked meanwhile. Sourced from `AIOS_STATUS_REPORT.md` and the resolver reports.

| ID | Blocker | Impact | Exact fix | Owner | Workaround (in use now) |
|---|---|---|---|---|---|
| **B1** | CRM write-back not live — Airtable config missing | OS can read CRM context but can't auto-create/update leads/tasks in Airtable | Supply `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_TABLE_ID`, `AIRTABLE_LEADS_TABLE`, `AIRTABLE_CONTACTS_TABLE` | Omar | Mirror leads/tasks to [pipeline_tracker.csv](../07_Dashboards/pipeline_tracker.csv); push to Airtable once live |
| **B2** | Persisted DNA source absent | Client "DNA"/profile doesn't restore across sessions | Add a real persisted DNA store; rerun `persistent_context_restore` proof | Engine | Capture client type in CRM + [T02](../04_Templates/T02_Client_Qualification.md) manually |
| **B3** | Persisted weather/context source absent | Contextual restore incomplete | Add a real persisted context store; rerun proof | Engine | Not blocking daily ops |
| **B4** | **URL→unit bridge dataset missing** (resolver) | Property Finder **URL/listing-ID → exact unit** is unprovable; benchmark exact = 0% | Add a real bridge source linking `listing_url`/`listing_id` → unit-bearing inventory rows (PF export or licensed feed), rebuild resolver outputs, rerun strict benchmark | A12 + Engine | [A12](../01_Agents/A12_Unit_Finder_Operator.md) returns "likely + confirm"; never reports URL match as exact; logs unresolved URLs to the bridge backlog |
| **B5** | WhatsApp replay 1/4 assertions passing | Gateway behavioral validation not fully passing (runtime is stable, no crash) | Fix the remaining 3 replay assertions; rerun regression replay | Engine | Manual/assisted WhatsApp replies via [WF11](../02_Workflows/WF11_WhatsApp_Reply.md) under Risk-Hold |
| **B6** | Production readiness unproven | No hosted backend/frontend/public URL/prod auth proof | **Railway config ready, backend hardened (fail-closed auth, no trace leak, body cap) + verified** ([SOP10](../03_SOPs/SOP10_Backend_Deploy_Railway.md), [RAILWAY_DEPLOY.md](../../deployment/hosted-backend/RAILWAY_DEPLOY.md)). Remaining: install Railway CLI, `railway login` + `up` + Generate Domain, set required auth/origin vars, wire webhook + frontend (Omar executes — outward-facing), then regenerate scorecard | Omar/Engine | OS runs locally in Claude CoWork today |

## Current Execution Order

1. **B6 Production hosting / website functional completion**
2. **B5 WhatsApp replay completion**
3. App completion priorities
4. Remaining approved construction work
5. **B4 Unit Finder remains brain backlog only**

## Unit Finder Decision

Unit Finder investigation is complete for this cycle.

- Freeze status: saved and frozen
- Status: not Product Ready
- Root issue: insufficient bridge/data acquisition and insufficient public listing resolution for V1 certification
- Action: do not spend more engineering time on Unit Finder, Bayut extraction, or URL bridge work until website, WhatsApp, app, and current construction priorities are complete

## What is NOT blocked (proceed now)
- Daily briefing, lead intake, qualification, property search, shortlists, listings prep, compliance answers, NOC package prep, contracts/renewals drafting, handover checklists, feasibility/CMA, marketing content, knowledge retrieval, daily/weekly/decision/project systems.

## Rule
A blocker blocks **one capability**, not the OS. Every blocked item above has a workaround so the business keeps moving. Re-check this list in the [Weekly Review](../05_Systems/Weekly_Review/WEEKLY_REVIEW_SYSTEM.md).
