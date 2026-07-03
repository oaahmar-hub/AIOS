# Lead Management


Evidence scope:
- Source chat: Home Sweet Home-Bitrix Support
- WhatsApp chat JID: 120363176580421967@g.us
- Local ChatStorage session PK: 1226
- Extracted local messages: 25
- Date range visible in local database: 2023-10-19 to 2026-06-24
- Accessible local attachments copied: 0
- Raw exports: raw/messages.md, raw/messages.csv, raw/messages.json, raw/chat_metadata.json


## Lead management model visible from chat

- New form submissions create or update Bitrix leads.
- Duplicate submissions should not duplicate lead records.
- Duplicate submissions should still create notification and CRM activity.
- Lead progression is pipeline-stage driven.
- Historical leads require stage remapping.

## AIOS should copy

- Explicit lead stages from New Lead to Deal Closed/Deal Lost/Junk.
- Responsible-user ownership.
- CRM activity creation for important events.

## AIOS should improve

- Treat every form submission as a separate event against one canonical lead/contact.
- Show repeat intent and attribution changes across duplicate submissions.
- Avoid confusing meeting status with lead stage unless user chooses that view.
