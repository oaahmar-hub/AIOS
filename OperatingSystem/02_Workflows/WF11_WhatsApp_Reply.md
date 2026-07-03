# WF11 — WhatsApp Reply

**Flow:** Inbound → load history → classify → draft in voice → risk-gate → send/log
**Trigger:** An inbound WhatsApp message (manual or via the gateway).
**Lead agent:** [A02 Deal Closer](../01_Agents/A02_Deal_Closer.md) / [A11 PA](../01_Agents/A11_Personal_Assistant.md) · governed by `PersonalityEngine/OMAR_REPLY_POLICY.md`

## Steps
1. **Load context first** — prior contact, CRM record, and chat history before replying (`OPERATIONS_KNOWLEDGE.md` #3). Never reply blind.
2. **Classify** the message: inquiry / qualification / scheduling / negotiation / escalation-sensitive / general.
3. **Route**: inquiry/lead → A02 (also run [WF01](WF01_Lead_Intake.md)); scheduling → A11; sensitive → Risk-Hold.
4. **Draft in Omar's voice** — short, premium, mixed AR/EN where the contact does; end on a next action (`OMAR_PERSONALITY_PROFILE_V1.md`).
5. 🔒 **Risk gate** — legal, government, payment, banking, contracts, complaints, private documents, or uncertain commitments → acknowledge receipt + "Omar will review", hold the substantive reply (`OMAR_REPLY_POLICY.md`).
6. **Autopilot scope** — only low-risk inquiries, qualification, scheduling, follow-up, daily reports auto-proceed (`OPERATIONS_KNOWLEDGE.md` #9).
7. **Send/queue** and **log** to CRM/chat history; set any follow-up task.

## Outputs
- Context-aware reply (sent or held), CRM/history log, follow-up task if needed.

## Done when
- Replied or held per the risk gate, logged, next action set.

## Hard rules
- No reply without loaded history. No risky topic auto-sent. Voice matches Omar.
