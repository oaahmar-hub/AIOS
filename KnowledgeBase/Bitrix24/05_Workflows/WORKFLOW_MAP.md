# Workflow Map


Evidence scope:
- Source chat: Home Sweet Home-Bitrix Support
- WhatsApp chat JID: 120363176580421967@g.us
- Local ChatStorage session PK: 1226
- Extracted local messages: 25
- Date range visible in local database: 2023-10-19 to 2026-06-24
- Accessible local attachments copied: 0
- Raw exports: raw/messages.md, raw/messages.csv, raw/messages.json, raw/chat_metadata.json


## Lead intake workflow

1. Customer submits form.
2. Zapier sends lead data into Bitrix.
3. Bitrix checks duplicate status.
4. If new: create lead and assign responsible user.
5. If duplicate: do not create duplicate lead, notify responsible user, create CRM activity, record repeat submission event.
6. Sales user progresses lead through pipeline stages.
7. Meetings/viewings are tracked either as stages or in Meeting & Viewing module; this is unresolved.

## Pipeline implementation workflow

1. Confirm new stage list.
2. Confirm old-stage to new-stage mapping.
3. Apply pipeline configuration.
4. Map historical leads.
5. Train sales team for one hour.
6. Go live target: 29 June.
7. Test duplicate handling and Zapier attribution.

## Listing workflow

Vendor stated that CRM can be used to do listing to all portals: Property Finder, Bayut, Dubizzle, and website.
