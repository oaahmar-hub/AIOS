# Workflow Library

Numbered, repeatable flows. Invoke with `Run WF<nn> <subject>`. Each workflow names its trigger, steps, the agents it uses, the outputs, and what gets written to CRM/log (the live-path proof rule, `OPERATIONS_KNOWLEDGE.md` #6).

| WF | Workflow | Trigger | Lead agent |
|---|---|---|---|
| [WF01](WF01_Lead_Intake.md) | Lead Intake | New inquiry from any channel | A02 |
| [WF02](WF02_Property_Search_Shortlist.md) | Property Search & Shortlist | Client brief / buying intent | A12 + A02 |
| [WF03](WF03_PF_Listing_Publish.md) | Property Finder Listing Publish | New/updated listing | A03 |
| [WF04](WF04_Nakheel_NOC_Submission.md) | Nakheel NOC Submission | NOC needed | A05 |
| [WF05](WF05_DLD_Transfer.md) | DLD Transfer | Sale agreed → transfer | A04 |
| [WF06](WF06_Ejari_Registration.md) | Ejari Registration | Tenancy signed | A04 |
| [WF07](WF07_Contract_Renewal.md) | Contract Renewal | Lease/contract nearing expiry | A06 |
| [WF08](WF08_Unit_Handover.md) | Unit Handover | Unit ready to hand over | A07 |
| [WF09](WF09_Feasibility_Study.md) | Feasibility Study | Buy/hold/develop decision | A08 |
| [WF10](WF10_Daily_CEO_Briefing.md) | Daily CEO Briefing | Every morning | A01 |
| [WF11](WF11_WhatsApp_Reply.md) | WhatsApp Reply | Inbound WhatsApp | A02/A11 |

## Conventions
- Every workflow ends by **writing to CRM/log** and **setting a next action**. A workflow with no next action is not done.
- Risk-Hold steps are marked 🔒 — the OS pauses there for Omar.
- Workflows call agents; agents do the judgment. Keep workflows as the choreography.
