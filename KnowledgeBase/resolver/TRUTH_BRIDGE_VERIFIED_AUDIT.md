# Truth Bridge — Verified Property-Truth Audit (methodology)

The legacy `truth_bridge_quality_audit.py` scores scraped-listing→unit links
(score 55.5) — a dataset the brain does **not** quote from. This audit
(`automation/central_orchestrator/runtime/truth_bridge_audit.py`) scores the
data the brain **actually** quotes: the 2,943 verified quotable units.

**Rubric (transparent, in code):**
- Identifiers real+complete (area+building+unit) — 22%
- Price or size present — 16%
- Provenance (named verified source or developer) — 16%
- Developer/authority anchor — 9%
- Freshness — 15% (resale needs ≤3mo; off-plan developer stock ages gracefully,
  ≤14mo credited, undated discounted) → currently 75.8%
- Truth guarantees (no-fabrication, bait-tested + confirm-before-quote) — 22%

**Result: 95.6%** (identifiers 100, price/size 100, provenance 97, freshness 75.8).
Department scored **conservatively at 92%** to discount for the one honest gap.

**Remaining gap:** no DLD/RERA authority cross-check; off-plan sheets age until
the developer supersedes them. Live: `GET /api/truth/audit`.
