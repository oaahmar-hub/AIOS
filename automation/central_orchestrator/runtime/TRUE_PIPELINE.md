# AIOS — The One True WhatsApp Pipeline (as-built, 2026-07-08)

This is the single flow that actually runs in production. Everything else in the
repo that touches WhatsApp is legacy/scaffolding and should be treated as dead
until deliberately revived. Written after a full trace so the sprawl can be
collapsed safely.

## Live flow (the only one that matters)

```
Customer WhatsApp message
   │
   ▼
Wasender session "HSH Main" (#94234, +971555593714)
   │  POST, signed with X-Webhook-Signature = <shared secret>
   ▼
https://aios-runtime-production.up.railway.app/webhook/whatsapp/provider/gateway
   │  served by: aios_runtime_production_up → aios_runtime.start()
   │           → automation/central_orchestrator/runtime/aios_live_api_server.py
   │  auth: X-Webhook-Signature == AIOS_WEBHOOK_SECRET  (or ?verify_token=…)
   ▼
evaluate_whatsapp_provider_webhook(payload)
   │  1. parse via whatsapp_provider_gateway (from_phone, message_text)
   │  2. permission engine gate (blocks legal/payment/contract/unknown-sender)
   │  3. if AIOS_WHATSAPP_REPLY_MODE == "auto" and not blocked:
   ▼
_generate_reply_text()  → POST to WA_SIMPLE_OPENAI_ENDPOINT (n8n)
   │  n8n "WA Simple OpenAI Reply v4" → OpenAI (gpt-5-mini) → returns {reply}
   │  (fallback holding line if this fails, when AIOS_WHATSAPP_FALLBACK_REPLY set)
   ▼
_send_whatsapp_reply()  → POST https://www.wasenderapi.com/api/send-message
   │  auth: Bearer WASENDER_API_KEY
   ▼
Customer receives the reply
```

## The env vars this depends on (Railway)

| Var | Purpose | Failure if wrong |
| --- | --- | --- |
| `AIOS_WEBHOOK_SECRET` | must equal Wasender's Webhook Secret | inbound 401, nothing received |
| `AIOS_WHATSAPP_REPLY_MODE` | `auto` to reply, `hold` to only log | `hold` = received but never answered |
| `WA_SIMPLE_OPENAI_ENDPOINT` | n8n brain URL | no reply text generated |
| `WASENDER_API_KEY` | outbound send auth | reply generated but never delivered |
| `AIOS_WHATSAPP_FALLBACK_REPLY` | holding line on brain failure | silent drop on brain error |
| (n8n) OpenAI credential `FLspVfmy11sMqfV4` | the brain's OpenAI key | n8n 500, no reply |

## Check it in one call

`GET /api/health/deep` runs every link above and returns green/red per component
with a plain-English list of what's broken. `?brain=0` skips the live n8n call.
This is the first thing to hit when "nothing happens" — it turns silent failures
into a named cause.

## Legacy / not in the live path (candidates for deletion)

- `transport/simple_whatsapp_openai_gateway.py` — separate port-9010 gateway,
  path `/webhook/whatsapp/simple`. NOT deployed. Superseded by the in-runtime
  send wired into `evaluate_whatsapp_provider_webhook`.
- `automation/whatsapp_provider_gateway/runtime/wasender_live_relay_server.py` —
  standalone relay/sender. Its `_send_reply` format was reused inline; the server
  itself does not run in production.
- n8n workflows v1–v3, v5 — only v4 is referenced by `WA_SIMPLE_OPENAI_ENDPOINT`.
- `deployment/hosted-backend/app.py` — a second app with `/webhook/whatsapp/simple`;
  the Railway start command runs `aios_runtime_production_up`, not this.

Before deleting any of the above, confirm nothing else imports it and that the
`/api/health/deep` reply chain stays green.
