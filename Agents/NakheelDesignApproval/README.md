# AIOS Nakheel Design Approval Agent

Golden Test Project: PJ-P-VP-018

STATUS: PASS

## Mission

Validate Nakheel/Palm Jumeirah design approval submissions before portal upload. The agent converts return comments into reusable validation rules and checks each package against portal slots, authority requirements, file size limits, drawing completeness, and risk indicators.

## Golden project evidence

- Indexed Nakheel files: 145
- PDF text index: `AIOS/KnowledgeBase/Canonical/AIOS_PDF_TEXT_INDEX.csv`
- Rules database: `NAKHEEL_RETURN_COMMENT_RULES.csv`
- Golden validation: `PJ-P-VP-018_GOLDEN_TEST_VALIDATION.csv`

## Core checks

| rule_id | severity | requirement |
| --- | --- | --- |
| NAK-001 | HIGH | Application type must match return path: Design Approval Re-submission Without Nonstandard unless nonstandard change is explicit. |
| NAK-002 | HIGH | Latest issued master developer return or rejection must be uploaded for resubmission. |
| NAK-003 | HIGH | Covering or reply letter must respond to returned comments and reference PJ-P-VP-018 and REC/PJ-VP-018/REV-01/2026. |
| NAK-004 | HIGH | Appointment letter must authorize the consultant/contractor and not be a draft/admin preview. |
| NAK-005 | HIGH | Drawings must be split by portal slots and not replaced by a general signing/admin pack. |
| NAK-006 | HIGH | Swimming pool undertaking and discharge-system drawing must exist where pool/discharge applies. |
| NAK-007 | HIGH | Gas connection undertaking must be uploaded when mandatory portal slot is marked with an asterisk. |
| NAK-008 | HIGH | Evaluation sheet must be filled, signed, and under 5 MB for the portal slot. |
| NAK-009 | HIGH | Portal file size limits must be respected: 5 MB and 20 MB slots. |
| NAK-010 | MEDIUM | No preview, draft, outbound email, signing coordination, or internal admin file should be uploaded as authority submission content. |
