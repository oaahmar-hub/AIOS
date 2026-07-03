# AIOS Property Intelligence Engine - Final Direction

Status date: 2026-06-26

## Classification

LIVE framework, PARTIAL data coverage.

## Roadmap Status

Unit Finder and Bridge Engine remain part of the AIOS brain layer.

They are not Product Ready and they are not the active construction priority.

Current execution order:

1. Website Functional Completion
2. WhatsApp current construction priorities
3. App completion priorities
4. Remaining approved construction items
5. Unit Finder return only after the active construction stack is complete

## Corrected Product Definition

The product is not only URL to unit lookup.

The product is:

```text
Any property clue
-> Bridge Engine
-> Canonical Property Record
-> Owner / CRM / WhatsApp / Documents / Market / Actions
```

The Unit Finder remains a resolver capability inside the broader AIOS Property Intelligence Engine.

The only frozen path is deterministic public URL to exact unit, because current data does not contain the required bridge dataset.

## Target Intelligence Chain

```text
Public URL
-> Listing ID
-> Internal Listing ID
-> Property Number
-> Exact Unit
-> Owner
-> CRM Record
```

This chain is the ideal bridge path. It is not fully available yet from current local data.

## Current Evidence

Source evidence:

- Bridge Engine report: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeEngine/BRIDGE_ENGINE_ARCHITECTURE_REPORT.md`
- Bridge Engine manifest: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/BridgeEngine/bridge_engine_manifest.json`
- Unit Finder status: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/UNIT_FINDER_STATUS.md`
- Unit Finder resolver: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/final_unit_finder.py`
- Resolver database: `/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver/unit_resolver_database.sqlite`

Current Bridge Engine counts:

- Records indexed in bridge context: 26,166
- Unit records available: 24,357
- URL records: 221
- Listing reference records: 220
- Permit records: 15
- Property number records: 149
- Plot/land records: 317
- Records scanned during bridge investigation: 89,585
- Unique listing URLs found during bridge investigation: 221
- Direct URL plus unit rows: 0
- Direct exact URL to unit rows: 0
- Combined exact URL bridge paths supported: 0

## Phase 1 - Data Layer

Current state: PARTIAL-LIVE.

Available or partially available:

- Unit database
- Owner/unit records
- Building and project knowledge
- Area and project maps
- WhatsApp-origin knowledge corpus
- Property master database
- Resolver database
- Organized raw data and acquisition indexes

Still incomplete:

- Reliable public listing URL to exact unit bridge
- Structured broker reference to unit bridge
- Structured CRM listing reference to property/unit bridge
- DLD or portal export linked directly to unit-level identifiers

## Phase 2 - Bridge Engine

Current state: LIVE framework, PARTIAL data coverage.

Supported bridge strategies:

| Bridge | Current Status | Meaning |
|---|---|---|
| Direct URL -> Unit | WAITING_FOR_DATA | Framework exists, but current data has 0 direct URL plus unit rows. |
| Listing Reference -> Unit | WAITING_FOR_DATA | Listing IDs exist, but no reliable listing ref to unit dataset exists. |
| Broker Reference -> Unit | WAITING_FOR_DATA | No structured broker reference index currently available. |
| Permit -> Unit | PARTIAL_AVAILABLE | Permit records exist, but current unit-bearing permit coverage is weak. |
| Property Number -> Unit | AVAILABLE | Property number records include unit-bearing rows. |
| Plot/Land -> Unit | PARTIAL_AVAILABLE | Plot/land records exist with limited unit-bearing coverage. |
| AI Similarity Candidate Matching | AVAILABLE | Can return likely candidates, but must not claim exact identity by itself. |

Bridge outcomes:

- `EXACT_MATCH`: hard indexed evidence connects input to a unit-bearing record.
- `HIGH_CONFIDENCE`: strong identifier or strategy evidence exists, but exact unit bridge is incomplete.
- `CANDIDATE_MATCHES`: useful candidates exist, but exact identity is not proven.
- `NO_MATCH`: bridge is available but found no matching record.
- `WAITING_FOR_DATA`: capability exists but source data is not available yet.

Rule:

Do not fabricate matches. AI similarity can support candidate ranking, not exact ownership or exact unit claims.

## Phase 3 - AI Search Engine

Current state: DESIGN DIRECTION, not final autonomous production.

Target user inputs:

- Property Finder URL
- Bayut URL
- Dubizzle URL
- Permit number
- Property number
- Plot/land number
- Unit number
- Building name
- Project name
- Area/community
- Bedrooms
- Size
- Price
- Broker reference
- Agent/company
- Owner name
- WhatsApp message
- PDF/text/photo extracted details

Target output:

- Best property/unit match
- Confidence score
- Exact / high confidence / candidate / no match classification
- Matched fields
- Missing bridge explanation
- Source record evidence
- Owner/contact availability flag only in public output

## Phase 4 - Sales Intelligence

Current state: FUTURE ENGINE LAYER.

Target property-level intelligence:

- Market value
- Comparable properties
- Price history
- Demand score
- Best selling points
- Similar inventory
- Owner motivation when supported by CRM/contact history
- Recommended selling price
- AI-generated sales pitch

Required additional data:

- Reliable recent market comparables
- Historical transaction feeds
- Asking price history
- Lead demand and inquiry data
- CRM outcome history
- Broker listing performance data

## Phase 5 - Autonomous Agent

Current state: FUTURE APPROVED-WORKFLOW LAYER.

Target workflow:

1. Detect property clue from WhatsApp or CRM.
2. Resolve clue through Bridge Engine.
3. Return exact property if hard bridge exists.
4. Return ranked candidates if exact bridge does not exist.
5. Retrieve owner/contact availability internally.
6. Retrieve CRM and WhatsApp context.
7. Find similar inventory and market support.
8. Draft quotation or reply.
9. Log approved action to CRM.
10. Notify responsible salesperson when needed.

Control rule:

Autonomous execution must require approval where business, legal, payment, publication, or customer-facing risk exists.

## Phase 6 - Company Brain

Current state: STRATEGIC AIOS DIRECTION.

The Property Intelligence Engine should become one core engine inside AIOS, alongside:

- WhatsApp Human Engine
- CRM Engine
- Marketing Engine
- NOC and Approval Engine
- Document Engine
- Management Dashboard
- Autonomous Agent Layer

All engines should share the same property knowledge base and avoid separate conflicting records.

## What Works Today

- Unit Finder can resolve strong identifier inputs when local data supports them.
- Property number to unit is available.
- Building plus unit lookup is usable in the existing Unit Finder.
- AI similarity matching can produce likely property candidates.
- Bridge Engine framework supports multiple bridge strategies without redesign.
- Owner/contact protection is preserved; public output should expose only availability flags.

## What Does Not Work Today

- Public URL to guaranteed exact unit is not reliable.
- URL-only matching usually reaches candidate/likely level unless bridge data exists.
- Listing IDs are present, but they are not reliably linked to exact units.
- Broker references are not currently structured enough for exact bridge lookup.
- Similarity alone must not be treated as exact identity.

## Required Bridge Data

To unlock exact URL/listing resolution, AIOS needs at least one dataset linking:

```text
listing URL / listing ID / broker reference / CRM listing reference
-> property number / permit number / plot number / land number / unit number
```

Best bridge source candidates:

- Property Finder export
- Bayut/Dubizzle export
- Broker reference database
- CRM export
- DLD/Dubai REST/permit dataset
- Agent/company inventory export
- WhatsApp messages containing both listing link and exact unit identifier
- Old Excel files containing listing URL plus unit/property identifier

## Final Product Vision

A user can paste anything related to a property, and AIOS should:

1. Parse every useful clue.
2. Select the strongest bridge strategy.
3. Resolve to exact property when hard identifiers exist.
4. Return high-confidence or candidate matches when hard bridge data is missing.
5. Explain missing bridge fields.
6. Retrieve connected owner, CRM, WhatsApp, document, and market context.
7. Recommend the next best action.
8. Execute approved workflows through the relevant AIOS engine.

## Current Verdict

The AIOS Property Intelligence Engine direction is valid.

The Bridge Engine is the correct middle layer.

The blocker is not product direction or resolver architecture. The blocker is missing bridge data for deterministic public URL/listing reference to exact unit mapping.
