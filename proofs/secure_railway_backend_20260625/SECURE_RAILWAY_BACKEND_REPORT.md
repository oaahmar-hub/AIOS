# AIOS Secure Railway Backend Validation

Validated: 2026-06-25T15:08:46+04:00

Result: PASS

## Scope

This validation covers the hosted backend at:

`/Users/hassanka/Downloads/AIOS/deployment/hosted-backend`

The purpose was to verify the backend no longer falls open when auth variables are missing, and that the Railway deployment instructions now preserve the hardened posture.

## Verification Matrix

| Check | Expected | Actual | Result |
|---|---:|---:|---|
| `GET /api/status` with no auth env | 401 | 401 | PASS |
| `GET /api/runtime/status` with no auth env | 401 | 401 | PASS |
| `POST /api/ask` with no auth env | 401 | 401 | PASS |
| `GET /health` | 200 | 200 | PASS |
| `GET /api/health` | 200 | 200 | PASS |
| `/api/runtime-truth` absolute path exposure | no `aios_root` | no `aios_root` | PASS |
| Startup warnings | 3 | 3 | PASS |
| Oversized request body | 413 | 413 | PASS |
| `AIOS_REQUIRE_AUTH=0` local opt-out | 200 | 200 | PASS |
| Configured auth missing header | 401 | 401 | PASS |
| Configured auth valid Basic header | 200 | 200 | PASS |
| 500 error body | generic `internal_error` | generic `internal_error` | PASS |
| `python3 -m py_compile app.py` | pass | pass | PASS |

## Corrected Security Contract

- Protected routes fail closed by default: `/api/ask`, `/api/status`, `/api/runtime/status`.
- Public health routes remain public for Railway health checks: `/health`, `/api/health`.
- Runtime truth no longer exposes the absolute `AIOS_ROOT` path.
- Error responses no longer return traceback or local filesystem paths.
- Request bodies above `AIOS_MAX_BODY_BYTES` return 413.
- `AIOS_REQUIRE_AUTH=0` is allowed only for local development smoke tests.

## Corrected Deployment Rule

Railway deploys must set:

```bash
railway variables --set "WASENDER_API_KEY=<your_wasender_key>"
railway variables --set "WA_SIMPLE_OPENAI_ENDPOINT=https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4"
railway variables --set "AIOS_ALLOWED_ORIGIN=https://<your-frontend-domain>"
railway variables --set "AIOS_BASIC_AUTH_USER=<private_beta_user>"
railway variables --set "AIOS_BASIC_AUTH_PASSWORD=<private_beta_password>"
railway variables --set "AIOS_WEBHOOK_SECRET=<provider_webhook_secret>"
```

`AIOS_WEBHOOK_SECRET` is recommended when the provider can send it. Without it, the webhook remains open by design.

## Remaining Live Deployment Blockers

- Railway CLI is installed and verified as `railway 5.23.0`.
- Railway login is already available in this environment.
- Public Railway service exists at `https://aios-runtime-production.up.railway.app`.
- Live read-only check: `/health` returns 200 and `/api/status` without auth returns 401.
- Live read-only check: `/api/runtime-truth` still exposes `aios_root`, so the live deployment is not yet running the latest local redaction build.
- Next correction requires publish approval: run `railway up`, then re-check `/api/runtime-truth`.
- Wasender webhook registration and frontend `AIOS_API_BASE` still need the live deployment pass.
