# Daily Planning System

**Purpose:** Run each day from one briefing, three priorities, and a closing note. Low ceremony, high signal.

## The daily loop
1. **Morning (5 min):** `Run daily briefing` → [WF10](../../02_Workflows/WF10_Daily_CEO_Briefing.md). Produces today's 3 priorities + slipping list + needs-you list.
2. **Set the 3.** Today succeeds if the 3 priorities move. Everything else is secondary.
3. **Work the agents/workflows** through the day. Log decisions as they happen ([Decision System](../Decisions/DECISION_SYSTEM.md)).
4. **Evening (5 min):** capture the daily note (below). Roll incompletes to tomorrow.

## Today's 3 rule
- Max 3 priorities. Compliance deadlines auto-qualify even if small.
- Each priority has one next action + an owner agent.
- If a priority can't move today, say why and reschedule it — don't silently drop it.

## Daily note (capture each evening)
Save as `Daily_Notes/{{YYYY-MM-DD}}.md` (create folder on first use). Template: [Daily_Note_Template.md](Daily_Note_Template.md).

## Inputs the briefing pulls
- Google Calendar (today) · Gmail (priority unread) · Airtable tasks (due/overdue) · hot leads with no next step · Risk-Hold queue · compliance radar (Ejari 30d / notice 90d / NOC follow-ups).

## Connection
- Feeds and is fed by the [Command Center](../../07_Dashboards/COMMAND_CENTER.md).
- Weekly, the [Weekly Review](../Weekly_Review/WEEKLY_REVIEW_SYSTEM.md) reads the week's daily notes.
