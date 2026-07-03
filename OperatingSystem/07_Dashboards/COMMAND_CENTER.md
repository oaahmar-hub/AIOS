# Command Center

The live operating dashboard. Refreshed by the [Daily CEO Briefing](../02_Workflows/WF10_Daily_CEO_Briefing.md). This is the one screen to glance at.

> Values below are placeholders until the first live briefing run populates them from CRM/Calendar/Gmail.

## Today
- **Date:** `{{auto}}`
- **Top 3 priorities:** `{{from WF10}}`
- **Calendar:** `{{viewings / meetings}}`
- **Needs you (🔒 Risk-Hold):** `{{count + items}}`

## Pipeline snapshot (from [pipeline_tracker.csv](pipeline_tracker.csv))
| Stage | Count | Value (AED) |
|---|---|---|
| New | `{{}}` | `{{}}` |
| Qualified | `{{}}` | `{{}}` |
| Viewing | `{{}}` | `{{}}` |
| Offer / Negotiation | `{{}}` | `{{}}` |
| Transfer / Closing | `{{}}` | `{{}}` |
| **Closed (MTD)** | `{{}}` | `{{}}` |

## Compliance radar (danger window)
| Item | Unit/Client | Deadline | Days left |
|---|---|---|---|
| Ejari (30d) | `{{}}` | `{{}}` | `{{}}` |
| Renewal/Notice (90d) | `{{}}` | `{{}}` | `{{}}` |
| NOC follow-up | `{{}}` | `{{}}` | `{{}}` |

## Active listings
- Live: `{{n}}` · Stale (>30d): `{{n}}` · Missing permit: `{{n}}` 🔒

## Projects (from [project_register.csv](../05_Systems/Projects/project_register.csv))
- Active: `{{n}}` · Blocked: `{{n}}` (see [BLOCKERS](../99_Meta/BLOCKERS.md))

## System health
- CRM write-back: `{{live/blocked — B1}}`
- WhatsApp gateway: `{{stable/partial}}`
- Unit Finder URL→unit: **blocked (B4)** — general resolution OK
- Last proof bundle: `{{date}}`

## Quick commands
- `Run daily briefing` · `Run weekly review` · `Show active projects` · `Show Risk-Hold queue` · `Act as Chief of Staff: plan my day`
