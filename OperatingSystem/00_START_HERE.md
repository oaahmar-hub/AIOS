# START HERE — Activating and Running the AIOS Operating System

Read once. Then operate from [AIOS_OS.md](AIOS_OS.md).

---

## What this is

A file-based operating system you drive by talking to Claude inside CoWork, rooted at `/Users/hassanka/Downloads/AIOS`. The files in `OperatingSystem/` are the substrate: agents (specialist operating briefs), workflows (step sequences), SOPs (Dubai RE procedures), templates (fill-in assets), and the planning/decision/project systems. You invoke them in plain language; Claude executes against the live tools (Airtable, Gmail, Calendar, Drive, WhatsApp gateway, n8n) and the local knowledge engine.

---

## First-run setup (one time, ~15 min)

1. **Confirm identity defaults.** Edit the header of [AIOS_OS.md](AIOS_OS.md) if any of these are wrong: Operator = Omar, Business = Home Sweet Home Real Estate (HSH), Markets = Dubai + Abu Dhabi.
2. **Connect the live tools** (see [99_Meta/BLOCKERS.md](99_Meta/BLOCKERS.md) for what's missing). Minimum to unlock the daily briefing:
   - Airtable CRM: `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `AIRTABLE_LEADS_TABLE`, `AIRTABLE_CONTACTS_TABLE`, tasks table.
   - Google Workspace (Gmail, Calendar, Drive) — already live per existing proofs.
3. **Seed the registers** (start tracking from today):
   - [Pipeline tracker](07_Dashboards/pipeline_tracker.csv)
   - [Decision log](05_Systems/Decisions/decision_log.csv)
   - [Project register](05_Systems/Projects/project_register.csv)
4. **Set the cadence.** Decide your daily briefing time (default 08:00) and Friday review time (default 16:00).

---

## The daily script (copy/paste each morning)

```
Run daily briefing.
Pull: today's calendar, unread priority email, open CRM tasks due today/overdue,
hot leads with no next step, and any Risk-Hold items waiting on me.
Give me today's 3 priorities and the first action for each.
```

That triggers [WF10 Daily CEO Briefing](02_Workflows/WF10_Daily_CEO_Briefing.md).

---

## The three ways to operate

### 1. Invoke an agent (for a role/skill)
```
Act as the Compliance Officer agent.
Client wants to transfer a Palm villa with an existing mortgage. Give me the exact
fee breakdown, document checklist, and the order of steps.
```

### 2. Run a workflow (for a defined process)
```
Run WF04 Nakheel NOC Submission for unit PJ-P-VP-018.
```

### 3. Ask the knowledge engine (for a fact/lookup)
```
Search the knowledge base: Ejari registration deadline and the penalty for late filing.
```

---

## What the OS will and won't do without asking

**Does autonomously** (autopilot scope, `OPERATIONS_KNOWLEDGE.md` #9): low-risk inquiries, lead qualification, scheduling, follow-up drafting, daily reports, property search, document retrieval, internal drafts.

**Holds for Omar** (Risk-Hold): legal positions, price/commission commitments, government filings, payments/banking, signed contracts, complaints, releasing private owner/client data, anything uncertain.

---

## Glossary of the stack

| Term | Meaning |
|---|---|
| AIOS | Your AI Operating System (this whole repo) |
| Engine | The backend: KnowledgeBase, PersonalityEngine, transport, proofs |
| OS / Control plane | This `OperatingSystem/` folder — what you drive daily |
| Agent | A specialist operating brief you load by name |
| Workflow (WF) | A numbered, repeatable step sequence |
| SOP | A Dubai RE procedure (regulatory/operational) |
| Risk-Hold | The escalation gate that pauses risky actions for Omar |
| Property Master DB | `KnowledgeBase` inventory used for property search |
| Unit Finder / Resolver | `KnowledgeBase/resolver` — maps listings/units (URL→unit currently blocked, see BLOCKERS) |

Next: open [AIOS_OS.md](AIOS_OS.md) and run your first daily briefing.
