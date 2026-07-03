# WF09 — Feasibility Study

**Flow:** Question → local data → model → scenarios → call → file
**Trigger:** A buy / hold / develop / price decision needs a numbers-backed answer.
**Lead agent:** [A08 Research & Feasibility Analyst](../01_Agents/A08_Research_Feasibility_Analyst.md)

## Steps
1. **Frame** the decision and the horizon; collect inputs: price, costs, expected rent/exit, finance terms.
2. **Local data first** — comparables + area data from Property Master DB / `KnowledgeBase`; normalize aliases, strip false areas.
3. **Build the model** ([T05](../04_Templates/T05_Feasibility_Report.md)): acquisition cost (price + 4% DLD + fees), holding costs, gross + net yield, ROI, payback.
4. **Scenarios** — base / best / worst on the 2–3 sensitive variables (rent, vacancy, exit price).
5. **External fill** — only where local is thin; label every external figure with source + date.
6. **Call** — one-line recommendation + the driving numbers + the key risk.
7. **File** durable findings to the [Research System](../05_Systems/Research/RESEARCH_SYSTEM.md); propose a KB entry to [A10](../01_Agents/A10_Knowledge_Librarian.md).

## Outputs
- Feasibility model (base/best/worst), one-line recommendation, sourced assumptions, filed research note.

## Done when
- Model complete with scenarios, recommendation stated, assumptions sourced, findings filed.
