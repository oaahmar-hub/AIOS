# AIOS — Complete Project Inventory
**Date:** 2026-07-08 · **Owner:** Omar Ahmar / HSH · **Scope:** every tracked file in the repo

A full census of the system — pages, engines, knowledge, governance — not a weekly delta.

## At a glance
- 1,069 tracked files · 242 MB working tree
- 168 Python modules · 101 HTML pages · 242 markdown docs · 202 JSON · 62 CSV
- **What AIOS is:** a file-based business operating system for Home Sweet Home Real Estate (HSH), Dubai + Abu Dhabi. Official classification: **PARTIAL live**.

## 1. Frontend surfaces & pages
| Surface | Path | What it is |
|---|---|---|
| Public website | `AIOS-WEBSITE.html` | Marketing site — "Living Company Intelligence" / Command Deck (bilingual, live heartbeat) |
| Dashboard | `AIOS-DASHBOARD.html` | Main business operating dashboard (322 KB) |
| Mobile app | `AIOS-MOBILE-APP.html` | Mobile Command Console (PWA + webmanifest + service worker) |
| Runtime status | `AIOS-RUNTIME-STATUS.html` | Live runtime health page |
| React command center | `app/` | Built React/Vite app served at `/app/` |
| Deploy copies | `deployment/web-platform/` | Deployment set of all four + `index.html` shell |
| Offline fallback | `offline.html` | PWA offline page |

Plus **~50 generated proposal pages** in `automation/central_orchestrator/reports/client_property_proposals/` — real brain outputs (villa/office/clinic/warehouse proposals; URL/text/voice validation runs).

## 2. Operating System (`OperatingSystem/`)
Start: `00_START_HERE.md` → `AIOS_OS.md`.
- **12 agents** — A01 Chief of Staff, A02 Deal Closer, A03 Listings Manager, A04 Compliance Officer, A05 Nakheel NOC Specialist, A06 Contracts & Renewals, A07 Handover Coordinator, A08 Research/Feasibility, A09 Marketing Content Engine, A10 Knowledge Librarian, A11 Personal Assistant, A12 Unit Finder Operator.
- **11 workflows** — WF01 Lead Intake, WF02 Search/Shortlist, WF03 PF Publish, WF04 Nakheel NOC, WF05 DLD Transfer, WF06 Ejari, WF07 Renewal, WF08 Handover, WF09 Feasibility, WF10 Daily CEO Briefing, WF11 WhatsApp Reply.
- Also: `03_SOPs/`, `04_Templates/`, `05_Systems/` (Decisions/Projects/Planning), `06_KnowledgeBase_Index/`, `07_Dashboards/`, `99_Meta/` (BLOCKERS, ROADMAP, CHANGELOG, VERIFICATION).

## 3. Engine room (`automation/` · Python)
| Module | Lines | Role |
|---|---|---|
| `realty_intelligence_agent_runtime.py` | 2,700 | Core real-estate intelligence agent |
| `client_property_proposal_runtime.py` | 1,548 | Client property proposals |
| `aios_interaction_architecture_runtime.py` | 1,430 | Interaction / decision architecture |
| `aios_live_api_server.py` | 1,423 | Live API + WhatsApp reply path |
| `personality/omar_personality_engine.py` | 1,064 | Omar voice / reply generation (the brain) |
| `whatsapp_provider_gateway.py` (+ relay, state) | 701 | Wasender gateway, conversation state, response policy |
| `inventory_retrieval.py`, `aios_brain_runtime.py` | — | Verified-inventory retrieval into the reply |

Three subsystems: `central_orchestrator`, `unit_intelligence`, `whatsapp_provider_gateway`.
Live endpoints: `/api/health`, `/api/health/deep`, `/api/deployment/status`, `/api/unit/stats`, `/api/property/resolve`, `/api/unit/ingest`, `/api/command-center/data`, `/api/permission/evaluate`, `/app/`, `/webhook/whatsapp/provider/gateway`.

## 4. Knowledge base (`KnowledgeBase/`)
| Subsystem | Files | What it holds |
|---|---|---|
| `Operations_Corpus/` | 74 | 40+ scraped govt-procedure pages — DLD, RERA, GDRFA visas, ICP residency, Mortgages, NOC/Trakheesi/Oqood |
| `resolver/` | 53 | Unit resolver — 26,306 records, JVC extraction, bridge data layer + tests |
| `Bitrix24/` | 30 | CRM export raw + processed |
| `PropertyGraph/` | 24 | Canonical property master, listing bridge, verification queue, `property_graph.sqlite` |
| `AIOS_Knowledge_Vault/` | 15 | Category playbooks + case library |
| `TruthIngestion/` | 14 | Truth Bridge quality pipeline + Scorpion feed ingest |
| `BridgeInvestigation/` · `BridgeEngine/` | 12 | URL→unit bridge research + anchor engine |
| `Canonical/` | 7 | Master index + consolidation reports |
| `VectorDB/` · `KPI_Dashboard/` · `PropertyIntelligenceEngine/` | 12 | Vector store, KPIs, property-intelligence engine |

## 5. Personality, governance & evidence
- **`PersonalityEngine/`** — engine, Omar Profile V1, reply policy, EN+Arabic regression suites (WhatsApp edge cases, human-judgment library).
- **`00_FOUNDATION/`** — authority order, autonomy policy, engineering/reporting/validation standards, executive report.
- **`Agents/NakheelDesignApproval/`** — PJ-P-VP-018 audit, compliance report, golden-test validation.
- **`Engines/PropertyIntelligence/`** — property DB inventory, schema & rules.
- **`proofs/`** — 10+ evidence bundles.
- **Reports at root** — CEO reports (07-02 → 07-08), `AIOS_STATUS_REPORT.md`, `CASCADE_PROGRESS_LOG.md`, security notes.
- **`CLAUDE.md`** — session context index (new): future sessions auto-load it.

## 6. Current state & open blockers
Runtime LIVE on Railway (re-verify via `/api/health/deep`) · Truth Bridge Quality 55.5/100 · 237 quotable inventory rows · tests green.
- **B1** — CRM write-back not live (needs Airtable keys); dry-run until then.
- **B4** — URL→exact-unit bridge thin (54 exact vs 795 partial); data gap. Unit Finder frozen backlog.
- **B6** — Custom domain not attached; re-run public-beta validation without skips.

*Census taken from the tracked working tree. Counts exact; descriptions drawn from each area's README/report files. Where production could not be re-probed from this environment, it is flagged rather than asserted.*
