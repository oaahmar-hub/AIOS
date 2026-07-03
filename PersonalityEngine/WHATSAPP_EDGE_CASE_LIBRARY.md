# WHATSAPP_EDGE_CASE_LIBRARY

Purpose:
Capture real-world WhatsApp behavior failures without redesigning AIOS.

Architecture status:
Frozen. No new engines, no new layers, no routing redesign.

Learning mode rule:
Each real failure becomes one edge case with:
- Conversation
- Expected behavior
- Actual behavior
- Correct behavior
- Fix
- Status

Target:
Improve WhatsApp behavior from 96% to 99%+ through real usage refinement.

## Edge Case Format

```text
ID:
Date:
Contact:
Relationship:
Conversation objective:
Conversation:
Expected behavior:
Actual behavior:
Correct behavior:
Fix:
Status:
Validation:
```

---

## WA-EDGE-001 - Arabic "هاي" Misclassified As Correction

Date:
2026-06-22

Contact:
zaki Saleh Jawich / Trusted Partner

Relationship:
Trusted Partner, temporary full access

Conversation objective:
Casual greeting

Conversation:
```text
User: هاي
AIOS: تمام، صححتها.
```

Expected behavior:
Recognize "هاي" as Arabic/English-style casual greeting, not correction.

Actual behavior:
AIOS classified the message as correction and replied "تمام، صححتها."

Correct behavior:
```text
هاي يا زكي، هلا والله.
```
or
```text
هلا يا زكي، كيفك؟
```

Fix:
Removed "هاي" from correction patterns and added it to greeting detection.

Status:
Resolved

Validation:
WHATSAPP_EDGE_CASE_REGRESSION.py permanent regression passed.

---

## WA-EDGE-002 - Generic Property Shortlist Reply When Real Search Is Expected

Date:
2026-06-22

Contact:
zaki Saleh Jawich / Trusted Partner

Relationship:
Trusted Partner, temporary full access

Conversation objective:
Property inquiry

Conversation:
```text
User: Any one bedroom available for rent in downtown up to 100k ?
AIOS: Got it — I’ll check the best options and send you the shortlist.
```

Expected behavior:
Because this is a clear property request with area, bedroom count, rental objective, and budget, AIOS should search known inventory first. If rental inventory is not locally verified, say that directly and move to action.

Actual behavior:
AIOS gave a generic action-first reply without showing whether verified rental inventory exists.

Correct behavior:
```text
I’ll check Downtown 1BR rentals up to 100k now. If I don’t have a verified live option in inventory, I’ll confirm from the current listings/back office before sending.
```

Fix:
Added rental-specific verified-inventory response so rental requests do not use generic shortlist wording or sale inventory as proof.

Status:
Resolved

Validation:
WHATSAPP_EDGE_CASE_REGRESSION.py permanent regression passed.

---

## WA-EDGE-003 - Unit-Specific Request With No Verified Inventory

Date:
2026-06-22

Contact:
Test / Live proof

Relationship:
Unknown

Conversation objective:
Unit-specific request

Conversation:
```text
User: Tell me details of Unit 801 Anwa.
AIOS: I don’t see verified details for this unit in the current inventory. I’ll check the back-office/files and come back with the confirmed details.
```

Expected behavior:
Search unit inventory before asking. If verified data is unavailable, do not invent details.

Actual behavior:
Correct after latest fix.

Correct behavior:
Current behavior is acceptable. Next improvement is to connect the exact back-office/media file source so AIOS can return price, size, status, and photos when available.

Fix:
No behavior fix required now. Data-source enrichment needed later only if verified source exists.

Status:
Resolved behavior / Data gap remains

Validation:
Knowledge-first regression passed.

---

## WA-EDGE-004 - Old Contact Treated Too Much Like New Lead

Date:
2026-06-22

Contact:
H M Hasaan Noc Palm

Relationship:
Existing Client

Conversation objective:
Old NOC/Palm/Nakheel case

Conversation:
```text
User: هلا
User: كيفك شو اخبارك
User: عمر همام انا
AIOS earlier behavior: Asked property-style qualification.
```

Expected behavior:
Load old chat and subject first, then continue naturally.

Actual behavior:
Earlier behavior treated the contact like a new real estate lead.

Correct behavior:
```text
يا هلا عمر همام، نورت.
```
Then continue based on the previous NOC/Palm/Nakheel subject if he asks about the case.

Fix:
Manual alias and old-chat history merge already added.

Status:
Resolved

Validation:
OLD_CHAT_CONTEXT_REGRESSION.py passed 4/4.

---

## WA-EDGE-005 - Friend/Agent Casual Chat Over-Qualified As Lead

Date:
2026-06-22

Contact:
Markus Salut

Relationship:
Friend / contact

Conversation objective:
Casual check-in, later property buying context

Conversation:
```text
User: Hello Brother
User: Everything good What about you
AIOS earlier behavior: Hey brother — buying or renting?
```

Expected behavior:
Treat greeting/check-in as social until a property objective appears.

Actual behavior:
AIOS jumped to lead qualification.

Correct behavior:
```text
All good brother, thanks.
```
Only after:
```text
User: We buy now the propertys
```
should AIOS move into buyer/property mode.

Fix:
Conversation Objective Detection added before property mode.

Status:
Resolved

Validation:
MARKUS_CONVERSATION_REGRESSION.py passed 5/5.
