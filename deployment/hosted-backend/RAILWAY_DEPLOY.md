# Deploy the AIOS Backend to Railway

Gets the hosted backend (command API + WhatsApp gateway) off the Mac and onto a public URL — clears blocker **B6**. The service is Docker-based, stdlib-only (no `requirements.txt`), and binds to Railway's injected `$PORT`.

**Build context = this folder** (`deployment/hosted-backend/`). The Dockerfile does `COPY app.py` and `COPY AIOS` — both live here, so Railway must build from here, not the repo root.

Files that make this ready: [`railway.json`](railway.json) (Dockerfile builder + `/health` healthcheck), [`Dockerfile`](Dockerfile), [`.dockerignore`](.dockerignore), [`app.py`](app.py).

---

## Path A — Railway CLI (fastest, deploys this folder directly)

```bash
# 1. Install + log in (interactive browser auth — you do this)
bash <(curl -fsSL https://railway.com/install.sh) -y
source "$HOME/.railway/env"
# Alternate if npm/brew exists: npm i -g @railway/cli or brew install railway
railway login

# 2. From THIS folder
cd /Users/hassanka/Downloads/AIOS/deployment/hosted-backend
railway init                     # create/select a project

# 3. Set variables. The API is FAIL-CLOSED: without the two AIOS_BASIC_AUTH_* vars,
#    /api/ask, /api/status, /api/runtime/status return 401 (they are NOT public).
railway variables --set "WASENDER_API_KEY=<your_wasender_key>"
railway variables --set "WA_SIMPLE_OPENAI_ENDPOINT=https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4"
railway variables --set "AIOS_ALLOWED_ORIGIN=https://<your-frontend-domain>"   # required: do not ship "*"
railway variables --set "AIOS_BASIC_AUTH_USER=<private_beta_user>"             # required to enable the API
railway variables --set "AIOS_BASIC_AUTH_PASSWORD=<private_beta_password>"     # required to enable the API
# Required: without this, /webhook/whatsapp/simple returns 401.
# Provider must send it in X-AIOS-Webhook-Secret header, X-Webhook-Secret header, or webhook_secret payload field.
railway variables --set "AIOS_WEBHOOK_SECRET=<provider_webhook_secret>"

# 4. Deploy (uploads this dir as the build context)
railway up

# 5. Get a public URL
railway domain
```

## Path B — GitHub (auto-deploy on push)

1. Put this repo on GitHub (it isn't a git repo yet — `git init`, commit, push).
2. Railway → New Project → Deploy from GitHub repo.
3. **Service → Settings → Root Directory = `deployment/hosted-backend`** (critical — sets the Docker build context).
4. Railway auto-detects `railway.json` + `Dockerfile`.
5. Add variables (below) → Deploy → **Settings → Networking → Generate Domain**.

---

## Environment variables

| Variable | Required | Value |
|---|---|---|
| `WASENDER_API_KEY` | **Yes** | your Wasender token (outbound WhatsApp send) |
| `WA_SIMPLE_OPENAI_ENDPOINT` | No | n8n reply webhook (default already in code) |
| `AIOS_BASIC_AUTH_USER` | **Yes** | enables protected API routes; without it the API is fail-closed (401) |
| `AIOS_BASIC_AUTH_PASSWORD` | **Yes** | pairs with the user; both required to serve `/api/ask`, `/api/status` |
| `AIOS_ALLOWED_ORIGIN` | **Yes** | your frontend origin; default `*` is for local smoke tests only |
| `AIOS_WEBHOOK_SECRET` | **Yes** | webhook shared secret; without it `/webhook/whatsapp/simple` returns 401 (fail-closed) |
| `AIOS_REQUIRE_AUTH` | No | default `1` (fail-closed). Set `0` only for local/dev to allow an open API |
| `AIOS_MAX_BODY_BYTES` | No | request body cap; default `1048576` (1 MiB) |
| `PORT` | No | **Do not set** — Railway injects it; the app reads it |
| `AIOS_ROOT` | No | defaults to `/app/AIOS` (matches the Dockerfile) |

---

## Security posture (read before going live)

- **API is fail-closed.** `/api/ask`, `/api/status`, `/api/runtime/status` return **401** unless `AIOS_BASIC_AUTH_USER` + `AIOS_BASIC_AUTH_PASSWORD` are set — they are never public. (`AIOS_REQUIRE_AUTH=0` disables this for local dev only.) Verified by test.
- **Webhook is fail-closed.** `/webhook/whatsapp/simple` returns **401** when `AIOS_WEBHOOK_SECRET` is unset — the secret is required to activate the webhook. The provider must send the secret in `X-AIOS-Webhook-Secret` header, `X-Webhook-Secret` header, or a `webhook_secret` payload field. The server emits `security_warning` log events at startup for every gap (no API auth, no webhook secret, `AIOS_ALLOWED_ORIGIN=*`).
- **No internal details leak.** Errors return a generic message; stack traces and paths go to logs only. Bodies over `AIOS_MAX_BODY_BYTES` are rejected with 413.

## After deploy — wire it up

1. **Health:** `curl https://<backend-domain>/health` → `{"ok": true, "status": "online", ...}`
2. **Status:** `curl -u <user>:<password> https://<backend-domain>/api/status` → `backend: online, mac_dependency: false`
3. **WhatsApp webhook:** point the provider (Wasender/n8n) to `https://<backend-domain>/webhook/whatsapp/simple`
4. **Frontend:** set the web app's `AIOS_API_BASE` to `https://<backend-domain>` ([../web-platform/app.js](../web-platform/app.js); the web app deploys separately to Vercel via [../web-platform/vercel.json](../web-platform/vercel.json)).
5. **Smoke test the API (needs Basic auth):** `curl -u <user>:<password> -X POST https://<backend-domain>/api/ask -H 'Content-Type: application/json' -d '{"request":"Find me 2BR Yas Island under 2M"}'`

## Endpoints
- Public (no auth): `GET /health` · `GET /api/health` · `GET /api/runtime-truth` · `GET /api/runtime-report`
- Protected (Basic auth): `GET /api/status` · `GET /api/runtime/status` · `POST /api/ask`
- Webhook (fail-closed; requires `AIOS_WEBHOOK_SECRET`): `POST /webhook/whatsapp/simple`

## Notes & gotchas
- **No `requirements.txt`** — the app is pure Python stdlib; the Dockerfile is the source of truth.
- **Build context matters** — if you see `COPY AIOS ... not found`, the root directory/context is wrong (must be `deployment/hosted-backend`).
- **Persistence** — Railway containers have ephemeral disk; the WhatsApp replay used a read-only `/app` previously (fixed in the gateway). For stateful stores (relationship memory, logs), attach a Railway Volume or point writes to `/data` and mount a volume there.
- **Webhook health depends on the n8n endpoint** + `WASENDER_API_KEY`; if either is down, `/webhook/whatsapp/simple` returns a generic `{"error":"internal_error"}` (500) — the full trace is in the Railway logs, not the response.
- This deploy is **outward-facing** (public URL, live WhatsApp). Run it when you're ready to take the gateway live; the `railway login` + final `railway up`/Generate-Domain steps are yours to execute.
