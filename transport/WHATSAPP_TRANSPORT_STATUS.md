# AIOS WhatsApp Transport Status

Updated: 2026-06-23 02:52 GST

## Active Session

- Provider: Wasender
- Session: HSH Main
- Session ID: 94234
- Phone: +971555593714
- Status: Connected

## Current Webhook Binding

- Active public gateway URL:
  `https://specification-accompanying-adjustable-defined.trycloudflare.com/webhook/whatsapp/simple`

- Previous Wasender webhook URL, now expired:
  `https://quilt-chair-convention-organisations.trycloudflare.com/webhook/whatsapp/provider/gateway`

## Relay

- Local gateway:
  `http://127.0.0.1:9010/webhook/whatsapp/simple`
- Public tunnel:
  `https://specification-accompanying-adjustable-defined.trycloudflare.com`
- Tunnel process:
  `cloudflared tunnel --url http://127.0.0.1:9010 --no-autoupdate`

## Proof

- Public tunnel health:
  `{"ok": true, "service": "wasender-live-relay"}`
- Public patched gateway health:
  `{"ok": true, "service": "simple-whatsapp-openai-gateway"}`
- Controlled provider-shaped POST through tunnel:
  PASS
- Relay result:
  `ok=true`, `send_status=sent`
- Wasender send API result:
  `success=true`

## Remaining Production Hardening

This quick Cloudflare tunnel is live now but is not a permanent 24/7 production tunnel.
For durable production, replace it with either:

1. A named Cloudflare Tunnel with stable hostname.
2. A secure n8n Wasender credential and send node inside the existing production workflow.
