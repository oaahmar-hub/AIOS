# SOP10 — Backend Deploy (Railway)

**Purpose:** Take the AIOS hosted backend live on Railway **securely** — clears blocker [B6](../99_Meta/BLOCKERS.md). The app is now fail-closed: the API will not serve without auth, so the deploy can't accidentally go public.
**When:** First production deploy, or redeploy after backend changes.
**Owner:** A01 (coordinates) · **Source code:** [deployment/hosted-backend/](../../deployment/hosted-backend/) · **Full guide:** [RAILWAY_DEPLOY.md](../../deployment/hosted-backend/RAILWAY_DEPLOY.md)

## Prerequisites
- Railway CLI installed (`npm i -g @railway/cli` or `brew install railway`) — not installed by default on this machine.
- Secrets in hand: `WASENDER_API_KEY`; a chosen API user/password; your frontend domain; optional provider webhook secret.

## Steps (verified secure command set)
```bash
cd /Users/hassanka/Downloads/AIOS/deployment/hosted-backend
railway login            # interactive browser auth — Omar runs this
railway init

# REQUIRED — without the auth pair the API returns 401 (fail-closed by design)
railway variables --set "WASENDER_API_KEY=<key>"
railway variables --set "WA_SIMPLE_OPENAI_ENDPOINT=https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4"
railway variables --set "AIOS_ALLOWED_ORIGIN=https://<frontend-domain>"   # never ship "*"
railway variables --set "AIOS_BASIC_AUTH_USER=<private_user>"
railway variables --set "AIOS_BASIC_AUTH_PASSWORD=<private_password>"
# only if the provider can send it:
railway variables --set "AIOS_WEBHOOK_SECRET=<shared_secret>"

railway up               # uploads THIS folder as the Docker build context
railway domain           # public URL
```

## Post-deploy wiring (do not skip — "online" ≠ "production-routed")
1. **Health (public):** `curl https://<domain>/health` → online.
2. **Status (auth):** `curl -u <user>:<pass> https://<domain>/api/status` → `backend: online`.
3. **API smoke (auth):** `curl -u <user>:<pass> -X POST https://<domain>/api/ask -H 'Content-Type: application/json' -d '{"request":"Find me 2BR Yas Island under 2M"}'`
4. **Provider webhook:** point Wasender/n8n to `https://<domain>/webhook/whatsapp/simple`.
5. **Frontend:** set `AIOS_API_BASE` = `https://<domain>` ([web-platform/app.js](../../deployment/web-platform/app.js)).
6. **Confirm posture in logs:** the startup line shows `require_auth`, `api_auth_configured`, `webhook_secret_set`, `allowed_origin`. Resolve any `security_warning`.

## Security gates (🔒 hard rules)
- 🔒 **Never deploy with `AIOS_REQUIRE_AUTH=0` in production** — that re-opens the API. It exists for local dev only.
- 🔒 **Never set `AIOS_ALLOWED_ORIGIN=*`** for beta/production.
- 🔒 The webhook is open if `AIOS_WEBHOOK_SECRET` is unset (provider compatibility). If the provider can't send a secret, keep the URL private + monitor logs; treat outbound-send abuse as a live risk.
- 🔒 Deploy is **outward-facing** (public URL + live WhatsApp). The `railway login` / `railway up` / `railway domain` steps are Omar's to run.

## Outputs
- Live backend URL, posture confirmed in logs, webhook + frontend wired, smoke tests passing.

## Verification reference
Fail-closed behavior, trace-leak fix, and body cap were code-verified 2026-06-23 (see [VERIFICATION](../99_Meta/VERIFICATION.md) §E and [decision D003](../05_Systems/Decisions/decision_log.csv)).
