# Reporting Systems


Evidence scope:
- Source chat: Home Sweet Home-Bitrix Support
- WhatsApp chat JID: 120363176580421967@g.us
- Local ChatStorage session PK: 1226
- Extracted local messages: 25
- Date range visible in local database: 2023-10-19 to 2026-06-24
- Accessible local attachments copied: 0
- Raw exports: raw/messages.md, raw/messages.csv, raw/messages.json, raw/chat_metadata.json


## Reporting dependencies identified

The 2026-06-24 action summary says historical leads and previous stage names must be mapped to new pipeline stages to preserve continuity and reporting accuracy.

## Reporting risks

- Changing pipeline stages without a mapping table will break historical reporting.
- Removing meeting stages could reduce sales-manager visibility if Meeting & Viewing reports are not adopted by the team.
- Missing campaign/ad-set/ad fields blocks marketing ROI reporting.

## AIOS reporting opportunity

AIOS should maintain a stage mapping layer and event timeline so reporting can survive pipeline changes without rewriting history.
