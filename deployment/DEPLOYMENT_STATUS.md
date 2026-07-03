# AIOS Deployment Status

Generated: 2026-06-27

## Current Release Track
1. Private Web Beta
2. Public Web Release
3. PWA Release
4. Native App Preparation

## Website
Status: packaged and connected to the hosted Railway API. Public permanent frontend/domain publish remains approval-gated.

Priority: current top construction priority.

Location:
- `/Users/hassanka/Downloads/AIOS/deployment/web-platform`

Ready assets:
- `index.html`
- `app.js`
- `manifest.json`
- `sw.js`
- install icons
- `vercel.json`

Configured API:
- `https://aios-runtime-production.up.railway.app`

## Backend
Status: deployed and live on Railway.

Location:
- `/Users/hassanka/Downloads/AIOS/deployment/hosted-backend`
- Active Railway source package: `/Users/hassanka/Downloads/AIOS`

Ready endpoints:
- `/api/health`
- `/api/runtime/status`
- `/api/deployment/status`
- `/api/status`
- `/api/ask`
- `/webhook/whatsapp/provider/gateway`

Required production secret:
- `WASENDER_API_KEY`

Validated public backend:
- `https://aios-runtime-production.up.railway.app`
- Railway project: `aios-runtime`
- Railway service: `aios-runtime`
- Latest checked deployment: `cd7340f5-5a92-4764-873d-42a6bf7dbbec`
- `/api/health`: HTTP 200, `status=ready`, `runtime_ready_percent=100`
- `/api/status`: HTTP 401 without credentials, as expected for protected routes

## Mac Dependency
Runtime backend no longer depends on Omar's Mac. WhatsApp provider cutover still requires switching Wasender/provider webhook to the hosted URL and validating the live provider callback.

Target production state:
- Mac dependency: NO
- Gateway: hosted backend, provider cutover still pending
- Router/API: hosted backend + n8n webhooks
- Website: packaged frontend connected to hosted backend; permanent public frontend/domain still pending

## Fastest Release Path
1. Approve public frontend/domain publish.
2. Deploy `/web-platform` to Vercel, Cloudflare Pages, or a separate Railway static service.
3. Attach domain `aios.hshglobaldubai.com`.
4. Switch Wasender/provider webhook to hosted backend `/webhook/whatsapp/provider/gateway`.
5. Validate Basic Auth/product-session access using approved credentials.
6. Configure hosted onboarding email provider secrets.
7. Rerun hosted runtime, public beta, visual, Eye motion, and WhatsApp provider gates.

## Recommended Beta URLs
- Backend/runtime: `https://aios-runtime-production.up.railway.app`
- Frontend/domain target: `https://aios.hshglobaldubai.com`

## Production Readiness
Current: 82%

Why not 100%:
- Permanent domain not attached.
- Public frontend/domain publish needs approval.
- Production auth credentials were not available for full protected-route validation.
- Wasender/provider webhook not yet switched and validated against hosted backend.
- Hosted onboarding email provider secret is still placeholder/not validated.

## Current Construction Decision

- Unit Finder is not Product Ready and is moved to the brain backlog.
- Do not continue Bayut extraction or Unit Finder optimization in the current cycle.
- Return to Unit Finder only after website, WhatsApp, app, and current approved construction priorities are complete.
- Immediate next execution priority: Website Functional Completion.
