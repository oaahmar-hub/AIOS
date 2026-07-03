# Implementation Roadmap

Build order for getting the OS to full daily power. Each phase is shippable on its own.

## Phase 0 — Activate (today, ~30 min) ✅ structure built
- [x] OS control plane created (`OperatingSystem/`).
- [ ] Confirm identity defaults in [AIOS_OS.md](../AIOS_OS.md).
- [ ] Run the first [daily briefing](../02_Workflows/WF10_Daily_CEO_Briefing.md) against live Calendar/Gmail (already live per proofs).
- [ ] Seed [pipeline_tracker.csv](../07_Dashboards/pipeline_tracker.csv) with current leads/listings.

## Phase 1 — Close the CRM loop (this week) → unblocks B1
- Supply Airtable config; switch lead/task creation from CSV mirror to live Airtable write-back.
- Verify with the live-path proof (inbound → CRM record written).
- Result: [WF01 Lead Intake](../02_Workflows/WF01_Lead_Intake.md) fully automated.

## Phase 2 — Sales engine live (week 2)
- Run real leads through WF01 → WF02 daily.
- Activate A02 + A12 on every inquiry; enforce "no cold leads".
- Stand up the [Weekly Review](../05_Systems/Weekly_Review/WEEKLY_REVIEW_SYSTEM.md) rhythm.

## Phase 3 — Compliance + deals backbone (weeks 3–4)
- Drive a real NOC package through [WF04](../02_Workflows/WF04_Nakheel_NOC_Submission.md) and a transfer through [WF05](../02_Workflows/WF05_DLD_Transfer.md).
- Load active tenancies into the renewal radar ([WF07](../02_Workflows/WF07_Contract_Renewal.md)).
- Re-verify all SOP fee/deadline figures against live DLD/RERA schedules.

## Phase 4 — Unit Finder bridge (frozen / brain backlog)
- This phase is removed from the active construction roadmap.
- Unit Finder is not Product Ready and remains frozen until website functional completion, WhatsApp priorities, app completion, and remaining approved construction work are complete.
- Reopen only when a stronger bridge dataset exists and the active construction stack is complete.

## Phase 5 — Marketing + content cadence (weeks 4–6)
- Stand up A09 content sets per listing/campaign; log to project register.
- Connect design tools (Canva/Adobe Express) for visual builds.

## Phase 6 — Engine hardening (parallel, engineering) → unblocks B5, B6
- Fix WhatsApp replay assertions (1/4 → 4/4).
- Restore DNA/context persistence (B2/B3).
- Prove production topology (B6); regenerate the scorecard.

## Phase 7 — Compounding second brain (ongoing)
- Every weekly review files ≥1 durable lesson via [A10](../01_Agents/A10_Knowledge_Librarian.md).
- Decisions reviewed against outcomes; winners → SOPs/playbooks.
- Quarterly: review this roadmap and the [verification table](VERIFICATION.md).

## Sequencing logic
Read → Sales loop → Compliance/deals → Marketing → Engine hardening → Compounding. Unit Finder bridge remains outside the active build order until the freeze is lifted. Revenue-touching capability first; deep engine fixes run in parallel on the engineering track.
