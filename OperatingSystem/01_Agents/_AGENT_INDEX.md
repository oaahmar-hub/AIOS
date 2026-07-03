# Agent Library

Twelve specialist agents. Each is an operating brief — a role Claude assumes on command. Invoke with:

```
Act as the <agent name> agent. <task>
```

Every agent inherits the [global operating principles](../AIOS_OS.md) and the Risk-Hold gate. Agents are grounded in HSH's real business (Nakheel/Palm, DLD, Ejari, RERA, Property Finder, Airtable CRM, Abu Dhabi + Dubai inventory).

| ID | Agent | Owns | Invoke for |
|---|---|---|---|
| A01 | [Chief of Staff](A01_Chief_Of_Staff.md) | Orchestration, prioritization, routing | Daily briefing, "what do I do next", delegating across agents |
| A02 | [Deal Closer](A02_Deal_Closer.md) | Sales, clients, pipeline | Lead qualification, follow-up, negotiation prep, closing |
| A03 | [Listings Manager](A03_Listings_Manager.md) | Property Finder, marketing inventory | Writing/publishing/refreshing listings, RERA permit check |
| A04 | [Compliance Officer](A04_Compliance_Officer.md) | DLD, Ejari, RERA, AML | Fees, deadlines, document checklists, regulatory answers |
| A05 | [Nakheel & NOC Specialist](A05_Nakheel_NOC_Specialist.md) | Nakheel approvals, NOC modifications | NOC packages, submission prep, Palm transactions |
| A06 | [Contracts & Renewals](A06_Contracts_Renewals.md) | Tenancy/sale contracts, renewals | Drafting, renewal notices, terms review, expiry tracking |
| A07 | [Handover Coordinator](A07_Handover_Coordinator.md) | Unit handovers, snagging | Handover checklists, snag lists, utility/key transfer |
| A08 | [Research & Feasibility Analyst](A08_Research_Feasibility_Analyst.md) | Market research, feasibility, CMA | Area studies, ROI/feasibility, comparative market analysis |
| A09 | [Marketing & Content Engine](A09_Marketing_Content_Engine.md) | Content, campaigns, social | Listing copy, posts, brochures, campaign plans |
| A10 | [Knowledge Librarian](A10_Knowledge_Librarian.md) | The knowledge engine | Lookups, filing new knowledge, keeping playbooks current |
| A11 | [Personal Assistant](A11_Personal_Assistant.md) | Calendar, inbox, errands, reminders | Scheduling, inbox triage, personal tasks, travel |
| A12 | [Unit Finder Operator](A12_Unit_Finder_Operator.md) | Resolver / Property Master DB | Resolving a listing/URL/address to an inventory unit |

## Routing rules (used by A01 Chief of Staff)

- Money in motion (lead, offer, negotiation, close) → **A02**
- A listing needs to go live or be fixed → **A03** (permit check first via **A04**)
- "Is this allowed / what's the fee / what's the deadline" → **A04**
- Anything Nakheel/Palm/NOC → **A05**
- A contract, renewal, or notice → **A06**
- Keys/snagging/handover → **A07**
- "Should I / is it worth it / what's the market" → **A08**
- Make something to publish → **A09**
- "Find / remember / where is" → **A10**
- Calendar/inbox/personal → **A11**
- "Which unit is this listing?" → **A12**

When a task spans agents, A01 sequences them and returns one consolidated output.

See [AGENT_TEMPLATE.md](AGENT_TEMPLATE.md) to add a new agent.
