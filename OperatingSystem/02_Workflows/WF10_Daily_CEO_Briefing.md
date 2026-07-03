# WF10 — Daily CEO Briefing

**Flow:** Calendar + Gmail + Airtable + Tasks → one executive view → 3 priorities
**Trigger:** Every morning (default 08:00). The first thing you run.
**Lead agent:** [A01 Chief of Staff](../01_Agents/A01_Chief_Of_Staff.md) · **Supports:** A11

## Steps
1. **Pull** today's calendar, priority unread email, CRM tasks (due today + overdue), hot leads with no next step, Risk-Hold queue.
2. **Compliance radar** — surface any deadline approaching: Ejari (30d), renewal/notice (90d), eviction (12mo), NOC follow-ups.
3. **Classify & rank** each item (Revenue / Compliance / Client-promise / Admin / Personal) by money × urgency.
4. **Pick today's 3 priorities** — each with its single next action + owner agent.
5. **Slipping list** — leads going cold, tasks overdue, deals stalled.
6. **Needs-you list** — Risk-Hold items awaiting Omar's decision.
7. **Write** the briefing to the [daily note](../05_Systems/Daily_Planning/DAILY_SYSTEM.md) and update the [Command Center](../07_Dashboards/COMMAND_CENTER.md).

## Outputs
- One-screen briefing: 3 priorities (+ first action + owner), slipping list, needs-you list, today's calendar.

## Done when
- Briefing produced, priorities set, daily note written, command center refreshed.

## Reference
- Existing CEO Briefing workflow proof (`AIOS_Daily_Operations_Workflows.md` #5): Gmail live, Airtable live, Calendar read live.
