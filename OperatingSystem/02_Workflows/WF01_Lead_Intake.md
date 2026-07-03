# WF01 — Lead Intake

**Flow:** Lead → CRM → Task → Property match (the core money workflow, `SALES_KNOWLEDGE.md` #1)
**Trigger:** New inquiry from WhatsApp, Property Finder, call, referral, or web.
**Lead agent:** [A02 Deal Closer](../01_Agents/A02_Deal_Closer.md) · **Supports:** A12, A11

## Steps
1. **Capture** the raw inquiry (source + message).
2. **Qualify** the 6 fields with [T02](../04_Templates/T02_Client_Qualification.md): area, budget, beds/type, timeline, purpose, cash/mortgage. Mark gaps.
3. **Create CRM lead** in Airtable (record the rec ID). Mirror to [pipeline tracker](../07_Dashboards/pipeline_tracker.csv).
4. **Create follow-up task** in the same step (record the task ID). Default due: +1 business day.
5. **Match inventory** — hand the brief to [A12](../01_Agents/A12_Unit_Finder_Operator.md)/Property Master DB → ranked shortlist.
6. **Draft reply** in Omar's voice acknowledging + offering shortlist/viewing, ending on a next action.
7. 🔒 If the reply quotes price/commission or makes a commitment → Risk-Hold for Omar; else send/queue.
8. **Set pipeline stage** = New/Qualified and next follow-up date.

## Outputs
- CRM lead ID + task ID, pipeline row, ranked shortlist, drafted reply, follow-up date.

## Done when
- Lead in CRM, task set, shortlist attached, reply sent/queued, next action dated. (No cold leads.)

## Proven reference
- Existing live proof: lead `rec8LMkWke6uX8Oti`, task `receFiytyzNbzVbCR` (`AIOS_Daily_Operations_Workflows.md`).
