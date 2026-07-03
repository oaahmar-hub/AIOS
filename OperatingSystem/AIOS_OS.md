# AIOS — Operating System (Control Plane)

**Operator:** Omar · **Business:** Home Sweet Home Real Estate (HSH) · **Markets:** Dubai + Abu Dhabi
**Environment:** Claude CoWork · **Version:** OS v1.0 · **Activated:** 2026-06-23

This is the single front door to the system. Everything is driven from here. One brain, one source of truth, one command center — consistent with the existing AIOS operating canon (`KnowledgeBase/AIOS_Knowledge_Vault/category_playbooks/OPERATIONS_KNOWLEDGE.md`).

The OS does **not** replace the existing engine. It is the operating layer on top of it:

| Layer | Location | Role |
|---|---|---|
| **Operating layer (this)** | `OperatingSystem/` | What Omar drives every day: agents, workflows, SOPs, templates, planning, decisions |
| Knowledge engine | `KnowledgeBase/` | Corpus, playbooks, case library, resolver, property master DB |
| Personality engine | `PersonalityEngine/` | Omar voice, reply policy, escalation rules |
| Transport | `transport/` | WhatsApp gateway runtime |
| Proof engine | `proofs/` | Evidence-led validation artifacts |
| Deployment | `deployment/` | Hosted backend / web / native readiness |

---

## How to use this OS (every interaction)

Open a session in Claude CoWork in `/Users/hassanka/Downloads/AIOS` and use one of three entry commands:

1. **`Run daily briefing`** → executes [WF10 Daily CEO Briefing](02_Workflows/WF10_Daily_CEO_Briefing.md). Start here every morning.
2. **`Act as <agent>: <task>`** → loads a specialist agent and works the task. See [Agent Library](01_Agents/_AGENT_INDEX.md).
3. **`Run <workflow>`** → executes a defined workflow end to end. See [Workflow Library](02_Workflows/_WORKFLOW_INDEX.md).

If a request touches **legal, government, payment, banking, contracts, complaints, private documents, or an uncertain commitment**, the OS holds it for Omar review (Risk-Hold rule, from `OPERATIONS_KNOWLEDGE.md` #4). It does not auto-send.

---

## Map of the OS

| # | Section | Open |
|---|---|---|
| 1 | Agent Library (12 specialists) | [01_Agents/_AGENT_INDEX.md](01_Agents/_AGENT_INDEX.md) |
| 2 | Workflow Library (11 runnable flows) | [02_Workflows/_WORKFLOW_INDEX.md](02_Workflows/_WORKFLOW_INDEX.md) |
| 3 | SOP Library (9 Dubai RE procedures) | [03_SOPs/_SOP_INDEX.md](03_SOPs/_SOP_INDEX.md) |
| 4 | Template Library (10 reusable assets) | [04_Templates/_TEMPLATE_INDEX.md](04_Templates/_TEMPLATE_INDEX.md) |
| 5 | Daily Planning System | [05_Systems/Daily_Planning/DAILY_SYSTEM.md](05_Systems/Daily_Planning/DAILY_SYSTEM.md) |
| 6 | Weekly Review System | [05_Systems/Weekly_Review/WEEKLY_REVIEW_SYSTEM.md](05_Systems/Weekly_Review/WEEKLY_REVIEW_SYSTEM.md) |
| 7 | Decision Tracking System | [05_Systems/Decisions/DECISION_SYSTEM.md](05_Systems/Decisions/DECISION_SYSTEM.md) |
| 8 | Project Management System | [05_Systems/Projects/PROJECT_SYSTEM.md](05_Systems/Projects/PROJECT_SYSTEM.md) |
| 9 | Research System | [05_Systems/Research/RESEARCH_SYSTEM.md](05_Systems/Research/RESEARCH_SYSTEM.md) |
| 10 | Personal Assistant System | [05_Systems/Personal_Assistant/PA_SYSTEM.md](05_Systems/Personal_Assistant/PA_SYSTEM.md) |
| 11 | Knowledge Base Index | [06_KnowledgeBase_Index/KB_MASTER_INDEX.md](06_KnowledgeBase_Index/KB_MASTER_INDEX.md) |
| 12 | Command Center (live dashboard) | [07_Dashboards/COMMAND_CENTER.md](07_Dashboards/COMMAND_CENTER.md) |
| — | Verification table | [99_Meta/VERIFICATION.md](99_Meta/VERIFICATION.md) |
| — | Blockers | [99_Meta/BLOCKERS.md](99_Meta/BLOCKERS.md) |
| — | Roadmap | [99_Meta/ROADMAP.md](99_Meta/ROADMAP.md) |
| — | Maintenance | [99_Meta/MAINTENANCE.md](99_Meta/MAINTENANCE.md) |
| — | Start-here onboarding | [00_START_HERE.md](00_START_HERE.md) |

---

## Operating principles (non-negotiable, encoded into every agent)

1. **Execution over discussion.** Produce the deliverable, then summarize. Never stop at analysis.
2. **One source of truth.** One CRM (Airtable), one knowledge base (`KnowledgeBase/`), one command center (this OS).
3. **Search before guessing.** Check local corpus / DB / Drive before answering from memory (`OPERATIONS_KNOWLEDGE.md` #12).
4. **Risk-Hold.** Legal/finance/government/contract/complaint/uncertain → pause to Omar, don't auto-act.
5. **Premium, short, human voice.** Mixed Arabic/English where the contact does. No corporate filler, no AI-sounding text (`PersonalityEngine/OMAR_PERSONALITY_PROFILE_V1.md`).
6. **Prove the live path.** For any automation claim, show inbound → execution → output → CRM/log written (`OPERATIONS_KNOWLEDGE.md` #6).
7. **Patch, don't rebuild.** Extend the missing layer; never replace working workflows/providers.
8. **Every lead gets a next step.** No lead goes cold (`SALES_KNOWLEDGE.md` #3).

---

## Daily / weekly cadence (the rhythm)

- **Morning:** `Run daily briefing` → review pipeline, inbox, tasks, today's 3 priorities.
- **During day:** invoke agents/workflows per task. Log decisions as they happen.
- **End of day:** capture the daily note (5 min).
- **Friday:** `Run weekly review`.

See [00_START_HERE.md](00_START_HERE.md) for the first-run setup and the exact daily script.
