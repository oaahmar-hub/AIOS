# AIOS — CEO Report (Late Update)
**Date:** 2026-07-02  
**Product:** HSH AI OS — AI-powered real estate business operating system  
**Owner:** Omar Ahmar (o.a.ahmar@gmail.com)  
**Prepared by:** Cascade, Lead Autonomous Engineer

---

## FEATURE
AIOS

## PURPOSE
Build a premium business operating system for HSH, not a normal CRM, chatbot, or dashboard.

## USER BENEFIT
One system receives requests, understands who the user is, decides what is allowed, retrieves the right knowledge, responds in Omar’s style, and stages the next action.

## WHAT THE PROJECT IS
AIOS is mainly:
- a business operating system
- a command center
- a decision platform
- an intelligence layer across property, operations, documents, CRM, and follow-up

## WHAT WE ARE BUILDING
- Unified inbound flow for WhatsApp, web, mobile, Gmail, and future channels
- Relationship + identity detection across Airtable CRM
- Centralized permission runtime (who can do what)
- Unified memory and retrieval layer across property data and knowledge assets
- Omar personality response layer
- Command center / Eye experience
- Action staging for tasks, follow-ups, documents, and workflows
- n8n lead intake + AI draft reply automation
- Autonomous unit intelligence (Property Finder, Bayut, WhatsApp agent links)
- Marketing automation triggered by identified inventory
- Cross-platform sync into SQLite/Railway with full audit logging

## CURRENT TECHNOLOGY STACK
- **Backend:** Python (80+ runtime modules)
- **Frontend:** HTML/CSS/JS static pages + React/Vite scaffold
- **Data layer:** SQLite property database, Airtable CRM
- **AI:** Claude (Anthropic API)
- **Automation:** n8n workflows
- **WhatsApp:** Wasender gateway, hosted webhook on Railway
- **Deployment:** Docker + Railway
- **App style:** web platform with PWA support

## CURRENT STATUS
- ✅ Backend runtime live on Railway: `https://aios-runtime-production.up.railway.app`
- ✅ `/api/health` returning 200, runtime 100% ready
- ✅ Auth credentials generated and deployed (basic auth + webhook secret + admin secret)
- ✅ Airtable PAT rotated and wired to Railway
- ✅ Airtable table IDs connected (Leads, Contacts, Comms)
- ✅ Wasender API key set in Railway
- ✅ n8n lead intake workflow built and fully connected
- ✅ Cascade appointed as Lead Autonomous Engineer under HSH LIFE FOREVER protocol
- ✅ Architecture mapped; top 3 unit-retrieval bottlenecks identified
- 🟡 WhatsApp hosted webhook route exists but verification returns 403 — verify token not set
- 🟡 `web-platform/` static frontend ready but not deployed to a public domain
- 🟡 React/Vite frontend scaffold exists but has no code
- 🟡 Unit Finder resolver is PARTIAL: 24,357 unit-bearing records, but URL→exact unit is not yet reliable
- 🔴 Public domain not attached (`aios.hshglobaldubai.com` planned)
- 🔴 Meta Business verification for WhatsApp not started
- 🔴 Google Drive / Google Calendar not connected
- 🔴 No autonomous ingestion pipeline for Property Finder / Bayut / WhatsApp listing links
- 🔴 Unit bridge data is sparse: 0 direct URL→unit rows, only 4.3% exact bridge rows

## MAIN GOAL
When someone opens AIOS, they should feel they entered the operating system of a modern company.

## NEXT 3 PRIORITIES
1. **Build the autonomous unit-intelligence ingestion layer** so Property Finder, Bayut, and WhatsApp agent links can feed the bridge dataset and resolve to exact units.
2. **Fix WhatsApp webhook verification** so Wasender can cut over to the hosted Railway URL.
3. **Deploy the static frontend** to Vercel/Cloudflare and attach the custom domain.

## BLOCKERS OWNED BY OMAR
- Approve frontend domain deploy (A3).
- Start Meta Business verification for WhatsApp production tier.
- Switch Wasender webhook URL to the hosted Railway endpoint once verification is fixed.
- Provide authorized portal data feeds or exports (Property Finder / Bayut / CRM) to enrich the unit bridge dataset.

## TOP 3 UNIT-RETRIEVAL BOTTLENECKS (NEW FINDINGS)
1. **Missing public URL → exact unit bridge dataset.** 221 URLs exist, but 0 direct URL+unit rows. URL-only inputs can only return likely candidates.
2. **Sparse hard-identifier coverage.** Truth Bridge Quality score is 52.8/100; only 4.3% exact rows. 711 rows lack hard property identifiers.
3. **No autonomous acquisition pipeline.** Unit Finder is currently a static resolver. Live scraping/polling and continuous ingestion do not exist yet.

---

*Lead engineer: Cascade | Protocol: HSH LIFE FOREVER*
