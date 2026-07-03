# Project Management System

**Purpose:** Track every multi-step thing in motion — deals, NOC packages, listings campaigns, handovers, build tasks — in one register, each with an owner, status, next action, and due date.

## What is a "project"
Anything that takes more than one session and has a finish line:
- A live deal through to close (links to its [Deal Summary](../../04_Templates/T09_Deal_Summary.md)).
- An NOC / approval package (REV-tracked).
- A listing campaign.
- A unit handover.
- An internal build (e.g. "wire Airtable write-back", "build URL→unit bridge").

## Register
Append to [project_register.csv](project_register.csv). Fields:

`id, name, type, owner_agent, status, priority, next_action, due_date, blocked_by, linked, updated`

- **type:** Deal / NOC / Listing / Handover / Renewal / Research / Build
- **status:** active / blocked / waiting / done
- **owner_agent:** the A0x that drives it
- **blocked_by:** the blocker id from [BLOCKERS](../../99_Meta/BLOCKERS.md) if stuck
- **linked:** CRM rec id / Drive path / WF used

## Operating rules
- Every active project has a `next_action` and `due_date`. A project with neither is either done or being neglected — the [daily briefing](../Daily_Planning/DAILY_SYSTEM.md) surfaces both.
- Blocked projects must name their blocker; the [Weekly Review](../Weekly_Review/WEEKLY_REVIEW_SYSTEM.md) chases blockers.
- Closing a project: set status `done`, capture any reusable lesson via [A10](../../01_Agents/A10_Knowledge_Librarian.md).

## Invoke
```
Add project: {{name}}, type {{}}, owner {{agent}}, next action {{}}, due {{date}}.
Show me active projects and what's blocked.
```
