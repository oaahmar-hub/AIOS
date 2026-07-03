# CRM Structure


Evidence scope:
- Source chat: Home Sweet Home-Bitrix Support
- WhatsApp chat JID: 120363176580421967@g.us
- Local ChatStorage session PK: 1226
- Extracted local messages: 25
- Date range visible in local database: 2023-10-19 to 2026-06-24
- Accessible local attachments copied: 0
- Raw exports: raw/messages.md, raw/messages.csv, raw/messages.json, raw/chat_metadata.json


## Proven Bitrix CRM pipeline target

Message `2026-06-24T10:36:56Z` proposes replacing the existing pipeline stages with:

- New Lead
- Assigned
- No Answer
- Contacted / In Progress
- Contact in Future
- Meeting Confirmed
- Meeting Attended
- Options Sent
- Ready to Buy
- Deal Closed
- Not Interested
- Junk (Job Seekers, Brokers, Service Providers, etc.)
- Deal Lost

## Later vendor correction

Message `2026-06-24T11:39:01Z` says `Meeting Confirmed` and `Meeting Attended` should not remain as stages according to a previous meeting, because Bitrix's Meeting & Viewing module should track meetings per client.

## Business tension

Message `2026-06-24T14:48:36Z` pushes back: Home Sweet Home still needs meetings to remain stage names and will share old-stage vs new-stage mapping later.

## AIOS implication

AIOS should separate:

- Lead commercial stage
- Meeting/viewing event state
- Follow-up activity state
- Loss/junk reason

This avoids overloading a single pipeline stage field while still allowing Omar to see meeting status as a sales-control milestone.
