# User Complaints


Evidence scope:
- Source chat: Home Sweet Home-Bitrix Support
- WhatsApp chat JID: 120363176580421967@g.us
- Local ChatStorage session PK: 1226
- Extracted local messages: 25
- Date range visible in local database: 2023-10-19 to 2026-06-24
- Accessible local attachments copied: 0
- Raw exports: raw/messages.md, raw/messages.csv, raw/messages.json, raw/chat_metadata.json


## Duplicate lead notification gap

Message `2026-06-19T10:41:20Z` reports that when someone fills the form again as a duplicate lead, the team does not receive notifications.

Exact business requirement from the message:

- Do not duplicate the lead.
- Still notify responsible users that the same lead submitted again.

## Stage design disagreement

Messages `2026-06-24T11:39:01Z` and `2026-06-24T14:48:36Z` show disagreement or unresolved alignment around whether meeting statuses should be stages or tracked only in the Meeting & Viewing module.

## AIOS opportunity

AIOS should treat duplicate submissions as a first-class event stream, not as a CRM record duplication problem. It should preserve one lead/contact record but log each submission as a timeline event, activity, notification, and attribution touch.
