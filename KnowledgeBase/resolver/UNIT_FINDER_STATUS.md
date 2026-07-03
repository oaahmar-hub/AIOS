# AIOS Unit Finder Status

Status date: 2026-06-26

## Classification

PARTIAL

## Roadmap Decision

Unit Finder is not Product Ready.

It remains part of the AIOS brain backlog, not the active construction track.

Do not continue:

- URL-to-unit optimization
- Bayut extraction work
- public listing bridge investigation
- further resolver tuning for certification

Reopen only after higher-priority construction work is complete and a stronger bridge dataset is available.

## Architecture Freeze

The current resolver architecture is frozen for this closeout.

No new resolver features are included in this status package. The production-readiness review covers the current implementation only:

- Final resolver entry point: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/final_unit_finder.py`
- Test evidence: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/final_unit_finder_tests.csv`
- Test report: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/final_unit_finder_report.md`
- Resolver database: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/unit_resolver_database.sqlite`

## Current Validation Result

Latest generated report:

- Total tests: 100
- Exact matches: 40
- Likely matches: 46
- Partial matches: 3
- Unresolved: 11
- 90+ confidence: 83
- 80-89 confidence: 3
- 65-79 confidence: 3
- Below 65 confidence: 11

## What Works

- Exact identifier search works for permit, property, plot, land, municipality, and DEWA-style identifiers when those identifiers exist in the local resolver index.
- Building plus unit search works when the input includes a usable building/project name and unit number.
- Multi-signal matching works for structured property clues such as area, building/project, bedrooms, size, price, and status.
- Live listing detail/link matching works at likely-match level against local corpus records.
- Owner/contact data is not exposed in public resolver output. Public output uses `owner_contact_available` as `YES` or `NO`.

## What Does Not Work

- URL to exact unit does not work reliably.
- Property Finder, Bayut, and Dubizzle URLs usually do not expose the internal unit, permit, property, plot, or land bridge required for exact unit resolution.
- Noisy descriptions without enough property-specific details often remain unresolved.
- Area-only or building-only clues are not enough for same-unit resolution.

## Supported Input Types

- Permit number
- Property number
- Plot number
- Land number
- Municipality number
- DEWA number when present in local data
- Building plus unit number
- Area plus building/project plus bedrooms plus size plus price
- Furnishing/status text when combined with stronger clues
- Description text when it includes enough comparable property fields
- Property Finder, Bayut, and Dubizzle links for likely-match lookup

## Unsupported Input Types

- URL-only exact unit resolution when no bridge dataset exists
- Image/photo-only lookup without extracted text
- Area-only lookup
- Building-only lookup
- Agent/company-only lookup
- Broker reference-only lookup when broker references are not present in the local corpus
- Vague request text without unit, identifier, size, price, bedroom, or building details

## Current Outcome

Unit Finder is usable today for limited internal broker workflow support when the broker provides at least one strong clue.

It is not Product Ready and it is not an approved active construction priority.
