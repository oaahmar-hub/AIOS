# WF02 — Property Search & Shortlist

**Flow:** Client brief → Property Master DB → ranked matches → shortlist
**Trigger:** A qualified buying intent (area/budget/beds/type known).
**Lead agent:** [A12 Unit Finder](../01_Agents/A12_Unit_Finder_Operator.md) + [A02 Deal Closer](../01_Agents/A02_Deal_Closer.md)

## Steps
1. **Normalize the brief** — aliases (JVC → Jumeirah Village Circle), strip false areas, set search dimensions: area, project, developer, beds, type, price range (`PROPERTY_KNOWLEDGE.md` #5).
2. **Search** the Property Master DB (e.g. "2BR Yas Island under 2M", "Villa Yas Acres under 5M").
3. **Resolve units** via the resolver; attach confidence band per match. 🔒 Any URL-only match → label "likely, needs confirmation" (see [A12](../01_Agents/A12_Unit_Finder_Operator.md)).
4. **Rank** by fit (budget, beds, area, readiness) and dedupe same-unit/different-listing.
5. **Build the shortlist** — top 3–6 with the facts that matter (price, beds, size, status, payment terms).
6. **Package for the client** — short premium message + the shortlist; offer viewings.
7. **Log** the search + shortlist against the lead in CRM; set the viewing/follow-up task.

## Outputs
- Ranked shortlist (3–6) with confidence bands, client-ready message, CRM update, follow-up task.

## Done when
- Shortlist delivered, viewings offered, follow-up dated, units' confidence stated.
