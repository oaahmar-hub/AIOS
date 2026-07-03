# Decision Tracking System

**Purpose:** Record every consequential decision with its reasoning, so the business has memory and decisions can be reviewed against outcomes. This is how judgment compounds.

## What counts as a decision to log
- Money: pricing, offers accepted/declined, commission terms, spend.
- Deals: pursue/drop a lead, negotiation stance, walk-away points.
- Compliance: how an ambiguous rule was handled (and the source relied on).
- Strategy: areas/developers to focus on, marketing bets, hiring.
- Operations: process/provider changes, tool decisions.

Skip trivial/reversible choices. Log anything you'd want to remember the *why* of in 3 months.

## How to log
Append a row to [decision_log.csv](decision_log.csv). Fields:

`id, date, area, decision, options_considered, reasoning, decided_by, risk_hold, expected_outcome, review_date, actual_outcome, status`

- **area:** Sales / Compliance / Strategy / Operations / Marketing / Finance
- **risk_hold:** yes if it passed through the Risk-Hold gate
- **review_date:** when to check if it worked
- **status:** open / reviewed / superseded

## Review loop
- The [Weekly Review](../Weekly_Review/WEEKLY_REVIEW_SYSTEM.md) checks decisions whose `review_date` has passed and fills `actual_outcome`.
- Decisions that worked → consider promoting the reasoning into a playbook/SOP (via [A10](../../01_Agents/A10_Knowledge_Librarian.md)).
- Decisions that failed → capture the lesson as a [case](../../../KnowledgeBase/AIOS_Knowledge_Vault/case_library/).

## Invoke
```
Log decision: {{decision}}, options were {{...}}, chose because {{...}}, review in {{2 weeks}}.
```
