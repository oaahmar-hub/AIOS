# T05 — Feasibility Report

**Used by:** A08 · WF09. Numbers-backed buy/hold/develop decision.

---

**Subject:** `{{Project / Unit / Area}}` · **Decision:** `{{buy to rent / buy to flip / develop / hold}}` · **Date:** `{{date}}`

## Inputs
| Input | Value | Source |
|---|---|---|
| Purchase price | AED `{{price}}` | `{{}}` |
| Finance | `{{cash / LTV %, rate, term}}` | `{{}}` |
| Expected rent (yr) | AED `{{rent}}` | comps |
| Expected exit price | AED `{{exit}}` | comps |
| Holding horizon | `{{years}}` | |

## Acquisition cost
- Price: AED `{{price}}`
- DLD 4%: AED `{{}}`
- Trustee/admin + agency: AED `{{}}`
- **Total in:** AED `{{total}}`

## Returns
| Metric | Base | Best | Worst |
|---|---|---|---|
| Gross yield | `{{%}}` | `{{%}}` | `{{%}}` |
| Net yield (after service charge, mgmt, vacancy) | `{{%}}` | `{{%}}` | `{{%}}` |
| ROI (with finance) | `{{%}}` | `{{%}}` | `{{%}}` |
| Payback | `{{yrs}}` | `{{yrs}}` | `{{yrs}}` |

**Sensitive variables:** `{{rent, vacancy, exit price}}`

## Call
**`{{GO / NO-GO / CONDITIONAL}}`** — `{{one line driven by the 2–3 key numbers}}`
**Key risk:** `{{vacancy / oversupply / service charge / liquidity}}`

**External figures used:** `{{each with source + date}}`
**Filed to:** [Research System](../05_Systems/Research/RESEARCH_SYSTEM.md)
