# Unusable Bridge Rows Audit — 2026-07-07

Question: can any of the 197 `invalid_bridge` (Unusable-bucket) rows be legitimately
promoted using data already in the corpus? **Answer: no.**

## What the 197 rows have

| field | rows with value |
| --- | ---: |
| unit | 159 |
| building | 108 |
| permit_number | 9 (2 usable) |
| plot_number | 6 (3 usable) |
| listing_url / listing_id / broker_reference | **0** |

All 197 are Unusable for exactly one reason: `missing public_bridge_reference`.

## Join-key overlap with the 1,047 public-reference rows (all zero)

- permit_number: 2 invalid vs 33 public values — **0 overlap**
- plot_number: 3 vs 1 — **0 overlap**
- property/dewa/municipality numbers: none on either side
- canonical building+unit: 91 invalid keys vs 16 public keys — **0 overlap**
- unit string vs the 221 URL-bearing source observations — **0 overlap**

## Conclusion

These rows are inventory-side fragments whose listings were never captured. No
in-corpus recovery exists; promoting any of them would require fabrication, which
is prohibited. The only legitimate paths:

1. **External feeds** (Property Finder / Bayut exports, CRM) providing fresh
   listing_url+permit/unit rows — new keys will join against these fragments.
2. **Live permit lookup**: the 2 usable permit numbers can be searched on the
   portals' permit fields when live acquisition is approved.

Until then the Unusable bucket floor is structural, not a data-quality defect.
