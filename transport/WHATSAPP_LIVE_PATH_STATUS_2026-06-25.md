# WhatsApp Live Path Status - 2026-06-25

## Verified Working

- Local AIOS gateway is running on `http://127.0.0.1:9010`.
- Local health endpoint returns `200`.
- Airtable CRM writeback is working.
- Wasender outbound send API is reachable from this Mac through the Keychain send token.
- Local inbound test reaches:
  - inbound parser
  - state session init
  - memory/history path
  - retrieval audit
  - Omar personality context
  - outbound safety controller
  - Airtable inbound/outbound CRM writeback

## Verified Not Live

- Old Cloudflare quick tunnel URL is expired.
- New Cloudflare quick tunnel registered briefly, then returned `530 origin unregistered`.
- localhost.run reverse tunnel generated a URL, but returned `503 no tunnel here`.
- Existing hosted backend candidates are not live:
  - Render candidate returned `404`.
  - lhr.life previous tunnels returned `503`.
  - Vercel candidate returned `DEPLOYMENT_NOT_FOUND`.
  - custom domain DNS did not resolve.
- n8n cloud workflows are currently blocked by account status:
  - `/webhook/whatsapp/provider/gateway` creates an execution, then fails.
  - `/webhook/wa-simple-openai-reply-v4` creates an execution, then fails.
  - Error: n8n trial ended, upgrade required.

## Current Exact Blockers

1. n8n cloud account execution is blocked because the trial ended.
2. Wasender session-management API returned `401` with the available Keychain token, so the current token can send messages but cannot update session/webhook settings.
3. Chrome extension browser control is unavailable from this Codex session, so the Wasender dashboard could not be updated automatically.
4. There is no stable public webhook endpoint currently available for Wasender to call directly into the local gateway.
5. The current outbound controller is correctly blocking weak fallback replies as `DRAFT_FOR_OMAR`, so even a received message may not auto-send unless the generated reply passes quality rules.

## Current Required Human/External Action

- Upgrade/reactivate n8n cloud, or provide a permanent hosted backend URL.
- Update Wasender HSH Main webhook to a stable endpoint:
  - preferred: hosted backend `/webhook/whatsapp/simple`
  - temporary only if stable: live tunnel `/webhook/whatsapp/simple`
- If using Wasender API instead of dashboard, provide a valid Wasender personal access token with session-management permissions.

## Status

LOCAL AIOS: WORKING

CRM WRITEBACK: WORKING

WASENDER OUTBOUND SEND API: WORKING

N8N EXECUTION: BLOCKED - TRIAL ENDED

PUBLIC INBOUND WEBHOOK: NOT LIVE

WHATSAPP LIVE ONLINE: NOT LIVE
