# AIOS Unit Finder Production Readiness

Status date: 2026-06-23

## Readiness Classification

PARTIAL

## Usability Decision

Is Unit Finder usable today?

YES.

Can brokers use it today?

YES, with clear confidence labels and with no claim that URL-only searches return exact units.

## Production Scope Approved Today

Unit Finder can be used today for:

- Internal broker lookup from permit/property/plot/land identifiers
- Internal broker lookup from building plus unit number
- Candidate matching from area/building/bedrooms/size/price/status clues
- Live listing/link candidate search at likely-match level
- Public-safe output showing owner/contact availability only

## Production Scope Not Approved Today

Unit Finder is not approved today for:

- Exact URL to unit claims
- Public exposure of owner/contact records
- Automated outreach based on restricted owner/contact data
- Treating LIKELY or PARTIAL matches as exact
- Replacing manual broker confirmation for high-value transactions

## Confidence Model

### EXACT

Use when a hard identifier or building plus unit match exists.

Examples:

- Exact permit number match
- Exact property number match
- Exact plot/land number match
- Exact building/project plus unit number match

Current test result:

- Exact identifier: 20/20 EXACT
- Building plus unit: 20/20 EXACT

### LIKELY

Use when multiple strong non-identifier signals match, but there is no hard bridge to prove exact unit identity.

Examples:

- Same area
- Same building/project
- Same bedrooms
- Size within tolerance
- Price within tolerance
- Matching status/furnishing text
- Similar listing/description text

Current test result:

- Multi-signal: 20 LIKELY
- Noisy description: 9 LIKELY
- Live listing detail: 17 LIKELY

### PARTIAL

Use when some signals match but confidence is not strong enough for likely-match treatment.

Current test result:

- Live listing detail: 3 PARTIAL

### UNRESOLVED

Use when the input does not contain enough property identity or no reliable candidate exists.

Current test result:

- Noisy description: 11 UNRESOLVED

## Owner/Contact Protection Rules

Public resolver output must show only:

- `owner_contact_available`: `YES` or `NO`

Public resolver output must not show:

- Owner name
- Phone number
- WhatsApp number
- Email
- Restricted source reference
- Any direct contact field

If confidence is below exact/likely threshold, owner/contact details must remain hidden even internally in user-facing output.

## Evidence Summary

Latest generated evidence:

- Total tests: 100
- Exact matches: 40
- Likely matches: 46
- Partial matches: 3
- Unresolved: 11
- 90+ confidence: 83
- 80-89 confidence: 3
- 65-79 confidence: 3
- Below 65 confidence: 11

Evidence files:

- `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/final_unit_finder.py`
- `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/final_unit_finder_tests.csv`
- `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/final_unit_finder_report.md`

## Biggest Remaining Blocker

The biggest blocker is missing bridge data connecting public listing URLs/listing IDs to exact unit identifiers.

The missing bridge is:

Public listing URL/listing ID to unit number, permit number, property number, plot number, or land number.

## Exact Next Future Improvement

Acquire or extract bridge data that contains both:

- Listing URL/listing ID/broker reference
- Unit number or permit/property/plot/land number

Priority bridge source:

- Broker/CRM/listing export containing listing references and unit identifiers.

