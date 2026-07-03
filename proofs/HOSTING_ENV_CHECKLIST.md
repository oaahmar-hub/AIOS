# HOSTING ENV CHECKLIST

Classification: PARTIAL

No secret values are exposed in this file.

## Required

`WASENDER_API_KEY`

- type: secret
- status: MISSING FROM ENV
- purpose: outbound WhatsApp send from hosted runtime

`AIOS_BASIC_AUTH_USER`

- type: secret
- status: MISSING FROM ENV
- purpose: private beta protected API/status access

`AIOS_BASIC_AUTH_PASSWORD`

- type: secret
- status: MISSING FROM ENV
- purpose: private beta protected API/status access

## Recommended

`WA_SIMPLE_OPENAI_ENDPOINT`

- type: non-secret URL unless provider treats webhook as private
- status: MISSING FROM ENV
- default in backend: `https://hshglobaldubai.app.n8n.cloud/webhook/wa-simple-openai-reply-v4`

`AIOS_ALLOWED_ORIGIN`

- type: non-secret
- status: MISSING FROM ENV
- production target: frontend public URL

`AIOS_API_BASE` / `AIOS_API_BASE_URL`

- type: non-secret
- status: MISSING FROM ENV
- production target: hosted backend URL

`AIOS_DOMAIN`

- type: non-secret
- status: MISSING FROM ENV
- production target: `aios.hshglobaldubai.com`

## Optional / Contextual

`AIOS_WEBHOOK_SECRET`

- type: secret
- status: MISSING FROM ENV
- purpose: protect webhook if Wasender can send matching header or payload field

`AIOS_ROOT`

- type: non-secret
- status: MISSING FROM ENV
- Docker default: `/app/AIOS`

`AIRTABLE_API_KEY`

- type: secret
- status: MISSING FROM ENV
- purpose: hosted CRM write-back

`AIRTABLE_BASE_ID`

- type: non-secret identifier
- status: MISSING FROM ENV
- purpose: hosted CRM write-back

`AIRTABLE_TABLE_ID`

- type: non-secret identifier
- status: MISSING FROM ENV
- purpose: hosted CRM write-back

`AIRTABLE_LEADS_TABLE`

- type: non-secret identifier/name
- status: MISSING FROM ENV
- purpose: hosted CRM write-back

`AIRTABLE_CONTACTS_TABLE`

- type: non-secret identifier/name
- status: MISSING FROM ENV
- purpose: hosted CRM write-back

`OPENAI_API_KEY`

- type: secret
- status: MISSING FROM ENV
- purpose: only required if hosted runtime bypasses n8n and calls OpenAI directly

## Local Validation Env Used

Temporary local validation values were used for:

- `AIOS_BASIC_AUTH_USER`
- `AIOS_BASIC_AUTH_PASSWORD`
- `AIOS_WEBHOOK_SECRET`
- `AIOS_ALLOWED_ORIGIN`

These were not production credentials.

## CLI / Host Tool Availability

- `railway`: MISSING
- `vercel`: MISSING
- `fly`: MISSING
- `render`: MISSING
- `docker`: MISSING
- `node`: MISSING
- `npm`: MISSING

## Deployment Blocker

Production hosting cannot be marked LIVE until host login/OAuth, required secrets, public backend URL, public frontend URL, and provider webhook switch are completed.
