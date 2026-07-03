# Weekly Review System

**Purpose:** Close the week with a true picture of pipeline, money, deadlines, and what to fix — then set next week's focus. Run Fridays (default 16:00): `Run weekly review`.

## What it pulls
- Pipeline movement (stage changes, new leads, closed, lost) from CRM + [pipeline tracker](../../07_Dashboards/pipeline_tracker.csv).
- Revenue: deals closed, commission booked, deals at risk.
- Compliance radar: anything due in the next 2–4 weeks (Ejari, renewals/notices, NOC follow-ups).
- Decisions logged this week ([decision_log.csv](../Decisions/decision_log.csv)) + their outcomes.
- Projects status ([project_register.csv](../Projects/project_register.csv)).
- The week's [daily notes](../Daily_Planning/) — wins, slips, recurring blockers.

## The seven questions (answer each)
1. What moved the business this week?
2. What money came in / is closest to closing?
3. What slipped or went cold — and why?
4. Which deadlines are now inside the danger window?
5. What decision is overdue?
6. What broke or repeated — what's the systemic fix? (→ file to [A10](../../01_Agents/A10_Knowledge_Librarian.md))
7. What are next week's top 3?

## Output
- A one-page review saved as `Weekly_Reviews/{{YYYY-Www}}.md` (template: [Weekly_Review_Template.md](Weekly_Review_Template.md)).
- Next week's 3 focuses seeded into Monday's briefing.
- Any systemic fix turned into a workflow/SOP update or a knowledge entry.

## Cadence ladder
- Daily note → Weekly review → (Monthly) pipeline + commission roll-up → (Quarterly) strategy + [Roadmap](../../99_Meta/ROADMAP.md) review.
