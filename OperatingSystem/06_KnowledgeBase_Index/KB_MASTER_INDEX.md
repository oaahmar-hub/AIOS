# Knowledge Base — Master Index

The single map to the one brain. The OS reads from the existing `KnowledgeBase/` engine — this index tells every agent where to look. Maintained by [A10 Knowledge Librarian](../01_Agents/A10_Knowledge_Librarian.md).

## Structure of the engine (`/Users/hassanka/Downloads/AIOS/KnowledgeBase/`)

| Zone | Path | Contents | Used by |
|---|---|---|---|
| **Knowledge Vault** | `AIOS_Knowledge_Vault/` | Reusable knowledge, playbooks, case library, indexes | All agents |
| ↳ Category playbooks | `AIOS_Knowledge_Vault/category_playbooks/` | Property, Operations, Legal, Marketing, Sales, Case library, Omar intelligence | A04, A02, A03, A08, A09 |
| ↳ Case library | `AIOS_Knowledge_Vault/case_library/` | CASE-01…06 (real solved situations) | A10, A01, A05 |
| **Operations Corpus** | `Operations_Corpus/` | DLD / RERA / NOC / mortgage regulatory source files | A04, A05, A06 |
| **Property Master DB** | `organized_master/` + resolver DB | Inventory: areas, projects, inventory, owners, developers, documents | A02, A03, A08, A12 |
| **Resolver / Unit Finder** | `resolver/` | Listing↔unit matching, identity map, benchmark reports | A12 |
| **Vector DB** | `VectorDB/chroma/` | Embedding store for semantic retrieval | A10 |
| **Raw data** | `raw_data/`, `Raw/` | Source files by type + by developer/area (Nakheel, LEOS, Binghatti, Reportage, Deyaar, Zoya, Abu Dhabi…) | A10 (ingest) |

## Category playbooks (quick links)
- [Property Knowledge](../../KnowledgeBase/AIOS_Knowledge_Vault/category_playbooks/PROPERTY_KNOWLEDGE.md) — area normalization, search dimensions
- [Operations Knowledge](../../KnowledgeBase/AIOS_Knowledge_Vault/category_playbooks/OPERATIONS_KNOWLEDGE.md) — one-brain, WhatsApp, Risk-Hold, autopilot scope
- [Legal Knowledge](../../KnowledgeBase/AIOS_Knowledge_Vault/category_playbooks/LEGAL_KNOWLEDGE.md) — DLD/Ejari/RERA/AML fees + deadlines
- [Sales Knowledge](../../KnowledgeBase/AIOS_Knowledge_Vault/category_playbooks/SALES_KNOWLEDGE.md) — lead flow, qualification, follow-up
- [Marketing Knowledge](../../KnowledgeBase/AIOS_Knowledge_Vault/category_playbooks/MARKETING_KNOWLEDGE.md)
- [Omar Intelligence](../../KnowledgeBase/AIOS_Knowledge_Vault/category_playbooks/OMAR_INTELLIGENCE.md)

## Case library
- [CASE-01 WhatsApp Provider Blocker](../../KnowledgeBase/AIOS_Knowledge_Vault/case_library/CASE-01-WHATSAPP-PROVIDER-BLOCKER.md)
- [CASE-02 Palm Jumeirah Nakheel Package](../../KnowledgeBase/AIOS_Knowledge_Vault/case_library/CASE-02-PALM-JUMEIRAH-NAKHEEL-PACKAGE.md)
- [CASE-03 Dubai Brokers Contract B](../../KnowledgeBase/AIOS_Knowledge_Vault/case_library/CASE-03-DUBAI-BROKERS-CONTRACT-B.md)
- [CASE-04 Area Intelligence Rebuild](../../KnowledgeBase/AIOS_Knowledge_Vault/case_library/CASE-04-AREA-INTELLIGENCE-REBUILD.md)
- [CASE-05 Knowledge Corpus Build](../../KnowledgeBase/AIOS_Knowledge_Vault/case_library/CASE-05-KNOWLEDGE-CORPUS-BUILD.md)
- [CASE-06 Property Master Database](../../KnowledgeBase/AIOS_Knowledge_Vault/case_library/CASE-06-PROPERTY-MASTER-DATABASE.md)

## Retrieval rule (every agent)
Search the corpus/DB/Drive **before** answering from memory (`OPERATIONS_KNOWLEDGE.md` #12). Always return the source path.

## Filing rule (A10)
Store only durable, reusable knowledge — not raw chats (`AIOS_Knowledge_Vault/README.md`). Append to the right playbook or create a CASE. Update, don't duplicate.

## Known data gap
- **URL→unit bridge missing** in `resolver/` — see [BLOCKERS B4](../99_Meta/BLOCKERS.md). General resolution PASS; URL→unit FAIL until a bridge dataset is added.
