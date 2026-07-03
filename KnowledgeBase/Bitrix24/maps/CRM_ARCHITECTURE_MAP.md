# CRM Architecture Map


Evidence scope:
- Source chat: Home Sweet Home-Bitrix Support
- WhatsApp chat JID: 120363176580421967@g.us
- Local ChatStorage session PK: 1226
- Extracted local messages: 25
- Date range visible in local database: 2023-10-19 to 2026-06-24
- Accessible local attachments copied: 0
- Raw exports: raw/messages.md, raw/messages.csv, raw/messages.json, raw/chat_metadata.json


## Entities inferred/proven

- Lead
- Responsible user
- CRM activity
- Meeting / Viewing module
- Pipeline stage
- Project field
- Branch field
- Marketing campaign/ad/ad-set fields
- User/access permission records
- Organization structure
- Listing/property records

## Recommended AIOS architecture response

AIOS should model Bitrix-like CRM as separate objects:

- Contact
- Lead
- Lead event
- Activity
- Meeting/viewing
- Property/listing
- Campaign attribution touch
- Pipeline stage history
- Permission profile
- Branch/project dimension
