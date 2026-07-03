# Human Judgment Edge Case Library

Generated: 2026-06-22

Purpose: improve Human Judgment from 85% to 95%+ using real WhatsApp behavior.

Architecture status: frozen. This library is for refinement only.

## Edge Case 001 - Generic fallback reply

Example:
- User: `Hello`
- Bad reply observed: `Hello, how can I help you?`

Cause:
- OpenAI fallback path answered without Omar Personality / live context enforcement.

Correct behavior:
- If new contact: short natural welcome.
- If active/known contact: mirror context and avoid generic chatbot wording.

Status:
- Fixed by generic fallback blocker and live personality prompt enforcement.

## Edge Case 002 - Duplicate inbound events

Example:
- User: `Good morning Omar`
- Bad behavior observed: two identical inbound events and two outbound replies.

Cause:
- Provider emitted duplicate message events and early runtime had insufficient suppression.

Correct behavior:
- Suppress duplicate by provider message ID; use soft sender+text key if ID is missing.

Status:
- Fixed by message ID / soft-key dedupe.

## Edge Case 003 - Friendly Arabic greeting repeated as formal assistant loop

Example:
- User: `يسعد صباحك يا ملك`
- Bad reply observed: `... كيف أقدر أخدمك اليوم؟`

Cause:
- Greeting/banter was treated too much like a new-service opening.

Correct behavior:
- Friend/banter reply should be short and human:
  `صباح النور يا ملك 🌹`

Status:
- Improved by Social Context Engine and banter handling.

## Edge Case 004 - Correction mistaken as new greeting/task

Example:
- User: `this is Salwa`
- Bad reply observed: `Good morning Salwa — brochures, a shortlist...`

Cause:
- Correction phrase was read as identity + business continuation instead of a correction event.

Correct behavior:
- Acknowledge correction only:
  `Got it, corrected.`
- Continue from corrected identity on future turns.

Status:
- Fixed by correction detection and business judgment `acknowledge_correction`.

## Edge Case 005 - Emoji interpreted as request for help

Example:
- User: `😅`
- Weak reply observed: asked if anything needed checking.

Cause:
- Emoji-only message was not treated as emotional signal.

Correct behavior:
- Light acknowledgment:
  `😂 تمام`
  or `تمام.`

Status:
- Fixed by emoji meaning classification.

## Edge Case 006 - Over-qualification on property search

Example:
- User: `may i have one bedroom downtown for rent ?`
- Weak reply observed: asked for budget and move-in date before checking anything.

Cause:
- Business judgment asked qualifying questions instead of acting from enough initial signal.

Correct behavior:
- Action first:
  `Got it — I’ll check available 1BR in Downtown and send the best options.`
- Ask one missing detail only after giving action/next step.

Status:
- Improved by Business Judgment Engine; continue monitoring.

## Edge Case 007 - Staff command asked too many questions

Example:
- User: `please do sent me your offer`
- Weak reply observed: asked for monthly budget again.

Cause:
- System did not infer this was a continuation of the prior rental request.

Correct behavior:
- Continue from history:
  `On it — I’ll prepare the offer based on the Downtown 1BR request.`
- If required, ask only the single missing field.

Status:
- Monitor. Relationship memory now stores last expected action.

## Edge Case 008 - Arabic casual phrase misunderstood literally

Example:
- User: `ال AI يلعب`
- Weak reply observed: treated as literal game/play ambiguity.

Cause:
- Casual complaint/joke phrasing was not mapped to teasing/frustration.

Correct behavior:
- Human/light:
  `😂 لا خليني أظبطه`

Status:
- Added to social context library for teasing/frustration monitoring.

## Edge Case 009 - Simultaneous inbound messages caused relationship memory write error

Example:
- User sent two messages quickly:
  `Assalamalaikum Brother`
  `How are you`

Cause:
- Two request threads wrote the same temporary relationship-store file path.

Correct behavior:
- Relationship memory writes must be atomic and concurrency-safe.

Status:
- Fixed with locked save and unique temp file path.

## Edge Case 010 - MOU request treated too casually

Example:
- User: `Please make MOU and send it to me`

Cause:
- `MOU` was not classified as sensitive / document commitment.

Correct behavior:
- Safe business reply:
  `Send me the deal details and I’ll prepare the draft for review.`
- Do not commit legal terms without Omar review.

Status:
- Fixed by routing MOU as sensitive.

