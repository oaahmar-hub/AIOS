# AIOS Hosted Backend

Purpose: move AIOS gateway/router/API off Omar's Mac.

Endpoints:
- `GET /health`
- `GET /api/health`
- `GET /api/status`
- `GET /api/runtime/status`
- `POST /api/ask`
- `POST /webhook/whatsapp/simple`

Required env (the API is **fail-closed** — without the auth pair, `/api/ask`, `/api/status`, `/api/runtime/status` return 401):
- `WASENDER_API_KEY`
- `AIOS_BASIC_AUTH_USER`
- `AIOS_BASIC_AUTH_PASSWORD`
- `AIOS_ALLOWED_ORIGIN` (your frontend origin; default `*` is smoke-test only)
- `AIOS_WEBHOOK_SECRET` if provider-side webhook secret is enabled
- Local/dev only: `AIOS_REQUIRE_AUTH=0` to allow an open API

Recommended host:
- Render, Railway, Fly.io, or any Docker web service. Railway: see [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md).

After deploy:
1. Set `WASENDER_API_KEY`.
2. Set `AIOS_BASIC_AUTH_USER` and `AIOS_BASIC_AUTH_PASSWORD` for private beta API/status protection.
3. Set `AIOS_WEBHOOK_SECRET` only if the provider can send the matching header/payload field.
4. Set provider webhook to `https://<backend-domain>/webhook/whatsapp/simple`.
5. Set web frontend `AIOS_API_BASE` to `https://<backend-domain>`.
6. Confirm `GET /health` returns online.
