# AIOS — CEO Report
**Date:** 2026-07-02  
**Product:** HSH AI OS — AI-powered real estate business operating system  
**Owner:** Omar Ahmar (o.a.ahmar@gmail.com)  
**Prepared by:** Cascade

---

## FEATURE
AIOS

## PURPOSE
Build a premium business operating system for HSH, not a normal CRM, chatbot, or dashboard.

## USER BENEFIT
One system can receive requests, understand who the user is, decide what is allowed, retrieve the right knowledge, respond in Omar’s style, and stage the next action.

## WHAT THE PROJECT IS
AIOS is mainly:
- a business operating system
- a command center
- a decision platform
- an intelligence layer across property, operations, documents, CRM, and follow-up

## WHAT WE ARE BUILDING
- unified inbound flow for WhatsApp, web, mobile, Gmail, and future channels
- relationship + identity detection across Airtable CRM
- centralized permission runtime (who can do what)
- unified memory and retrieval layer across property data and knowledge assets
- Omar personality response layer
- command center / Eye experience
- action staging for tasks, follow-ups, documents, and workflows
- n8n lead intake + AI draft reply automation

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
- 🟡 WhatsApp hosted webhook route exists but verification is returning 403 — code bug under investigation
- 🟡 `web-platform/` static frontend ready but not deployed to a public domain
- 🟡 React/Vite frontend scaffold exists but has no code
- 🔴 Public domain not attached (`aios.hshglobaldubai.com` planned)
- 🔴 Meta Business verification for WhatsApp not started
- 🔴 Google Drive / Google Calendar not connected

## MAIN GOAL
When someone opens AIOS, they should feel they entered the operating system of a modern company.

## NEXT 3 PRIORITIES
1. **Fix WhatsApp webhook verification** so Wasender can cut over to the hosted URL.
2. **Deploy the static frontend** to Vercel/Cloudflare and attach the custom domain.
3. **Build the React command center** so the dashboard is a real application, not just HTML pages.

## BLOCKERS OWNED BY OMAR
- Approve frontend domain deploy (A3).
- Start Meta Business verification for WhatsApp production tier.
- Switch Wasender webhook URL to the hosted Railway endpoint once verification is fixed.
