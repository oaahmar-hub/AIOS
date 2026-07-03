# AIOS Secure Railway Deployment SOP

Purpose: deploy the AIOS hosted backend without exposing private API routes.

Owner: AIOS deployment operator

Source backend:

`/Users/hassanka/Downloads/AIOS/deployment/hosted-backend`

## Non-Negotiable Security Rule

The backend must fail closed.

If `AIOS_BASIC_AUTH_USER` or `AIOS_BASIC_AUTH_PASSWORD` is missing, these routes must return 401:

- `GET /api/status`
- `GET /api/runtime/status`
- `POST /api/ask`

Do not deploy a public backend that depends only on remembering to set secrets. The code must enforce the default.

## Required Railway Variables

```bash
railway variables --set "WASENDER_API_KEY=<your_wasender_key>"
railway variables --set "WA_SIMPLE_OPENAI_ENDPOINT=https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4"
railway variables --set "AIOS_ALLOWED_ORIGIN=https://<your-frontend-domain>"
railway variables --set "AIOS_BASIC_AUTH_USER=<private_beta_user>"
railway variables --set "AIOS_BASIC_AUTH_PASSWORD=<private_beta_password>"
```

Set this when the WhatsApp provider can send the matching header or payload field:

```bash
railway variables --set "AIOS_WEBHOOK_SECRET=<provider_webhook_secret>"
```

Never set `PORT`; Railway injects it.

Use `AIOS_REQUIRE_AUTH=0` only for local development smoke tests.

## Deployment Steps

```bash
cd /Users/hassanka/Downloads/AIOS/deployment/hosted-backend

bash <(curl -fsSL https://railway.com/install.sh) -y
source "$HOME/.railway/env"
railway login
railway init

railway variables --set "WASENDER_API_KEY=<your_wasender_key>"
railway variables --set "WA_SIMPLE_OPENAI_ENDPOINT=https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4"
railway variables --set "AIOS_ALLOWED_ORIGIN=https://<your-frontend-domain>"
railway variables --set "AIOS_BASIC_AUTH_USER=<private_beta_user>"
railway variables --set "AIOS_BASIC_AUTH_PASSWORD=<private_beta_password>"
railway variables --set "AIOS_WEBHOOK_SECRET=<provider_webhook_secret>"

railway up
railway domain
```

## Post-Deploy Validation

Replace `<backend-domain>`, `<user>`, and `<password>`.

```bash
curl https://<backend-domain>/health
curl https://<backend-domain>/api/health
curl -i https://<backend-domain>/api/status
curl -u '<user>:<password>' https://<backend-domain>/api/status
curl -u '<user>:<password>' -X POST https://<backend-domain>/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"request":"Find me 2BR Yas Island under 2M"}'
```

Expected:

- `/health` returns 200.
- `/api/health` returns 200.
- `/api/status` without auth returns 401.
- `/api/status` with auth returns 200.
- `/api/ask` with auth returns 200.

## Integration Wiring

After the public domain is generated:

1. Set Wasender/provider webhook to `https://<backend-domain>/webhook/whatsapp/simple`.
2. Set the frontend `AIOS_API_BASE` to `https://<backend-domain>`.
3. Run the post-deploy validation above.
4. Store the validation result under `AIOS/proofs`.

## Proof Reference

Current local hardening proof:

`/Users/hassanka/Downloads/AIOS/proofs/secure_railway_backend_20260625/SECURE_RAILWAY_BACKEND_REPORT.md`
