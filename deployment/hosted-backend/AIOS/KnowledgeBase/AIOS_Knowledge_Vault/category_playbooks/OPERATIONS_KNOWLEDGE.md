# Operations Knowledge Playbook

Canonical AIOS operating rules for WhatsApp, workflow proof, and escalation.

## Extracted Knowledge
1. **One brain policy** — Keep one central intelligence layer and avoid disconnected agents or siloed knowledge. (Source: AIOS master instructions)
2. **WhatsApp reply style** — Replies must stay mixed Arabic/English, short, premium, human, and business-correct. (Source: WhatsApp canon)
3. **History loading** — Always load prior contact, CRM, and chat history before replying to an inbound WhatsApp message. (Source: WhatsApp canon)
4. **Risk hold** — Send risky, legal, financial, government, or uncertain topics to Omar review hold. (Source: WhatsApp canon)
5. **Calendar handoff** — Scheduling requests should hand off to calendar/reminder workflows instead of long chat loops. (Source: AIOS handoff rules)
6. **Live-path proof** — For any automation claim, prove inbound received -> n8n execution -> response sent -> CRM/log written. (Source: WhatsApp production testing)
7. **Preserve working config** — When blocked by provider issues, freeze the current config instead of redesigning the architecture. (Source: WhatsApp blocker handling)
8. **Support package discipline** — When the provider fails, prepare a vendor support package with timestamps, session IDs, and logs. (Source: Wasender support prep)
9. **Autopilot scope** — Autopilot is allowed only for low-risk real estate inquiries, lead qualification, scheduling, follow-up, and daily reports. (Source: AIOS operating rules)
10. **One source of truth** — Keep one database, one knowledge base, one command center, and one workflow system. (Source: AIOS non-negotiables)
11. **Do not rebuild** — Patch the missing layer rather than replacing working workflows or providers. (Source: AIOS build guidance)
12. **Search-first behavior** — When a local answer is needed, search the filesystem and local corpus before guessing. (Source: Downloads and knowledge work)

## Reusable Pattern
- Keep this category as a living playbook and append new items when new chats add a durable rule, decision, or template.