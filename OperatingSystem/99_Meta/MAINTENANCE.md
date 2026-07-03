# Maintenance & Update Procedures

Keep the OS accurate, lean, and compounding. One source of truth — update in place, never fork.

## Cadence
| When | Do | Owner |
|---|---|---|
| **Daily** | Capture daily note; log decisions; update project `next_action`s | A01/A11 |
| **Weekly (Fri)** | Run weekly review; clear stale leads/listings; re-check [BLOCKERS](BLOCKERS.md); file ≥1 durable lesson | A01/A10 |
| **Monthly** | Pipeline + commission roll-up; archive closed projects; prune dead entries | A01 |
| **Quarterly** | Re-verify all SOP fees/deadlines vs live DLD/RERA; review [ROADMAP](ROADMAP.md) + [VERIFICATION](VERIFICATION.md); regenerate engine proof bundle | A04/Engine |

## How to change each asset
- **Agent** — edit its file in `01_Agents/`; keep the brief format ([AGENT_TEMPLATE](../01_Agents/AGENT_TEMPLATE.md)); update `_AGENT_INDEX.md` if scope changes.
- **Workflow / SOP / Template** — edit in place; bump the meaning, not the number, unless you're adding a new one (next free number); update the section index.
- **Knowledge** — only [A10](../01_Agents/A10_Knowledge_Librarian.md) files durable knowledge into the engine playbooks/cases; update [KB_MASTER_INDEX](../06_KnowledgeBase_Index/KB_MASTER_INDEX.md).
- **Registers (CSV)** — append rows; don't rewrite history; mark superseded.

## Adding a new capability
1. Decide the layer: is it a role (agent), a process (workflow), a procedure (SOP), or an asset (template)?
2. Create it from the relevant template/format; give it the next free ID.
3. Wire it into the indexes + routing rules ([_AGENT_INDEX](../01_Agents/_AGENT_INDEX.md)).
4. Add a [CHANGELOG](CHANGELOG.md) entry.

## Hygiene rules
- No duplicates. Update the canonical file; delete forks.
- Every figure used for money/filings carries a "verify-before-contract" flag.
- Anything containing client/owner PII stays in approved systems only.
- If a workflow keeps breaking, fix the system, not the instance — then capture the fix as knowledge.

## Self-verification before presenting any deliverable
Every agent runs a final check: Is it executed (not just advised)? Sourced? Risk-gated? Does it end on a next action? (Mirrors the [VERIFICATION](VERIFICATION.md) standard.)
