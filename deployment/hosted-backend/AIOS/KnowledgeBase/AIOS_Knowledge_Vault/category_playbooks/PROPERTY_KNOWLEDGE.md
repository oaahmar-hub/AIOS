# Property Knowledge Playbook

How to read market files, normalize areas, and search inventory reliably.

## Extracted Knowledge
1. **Canonical area-project hierarchy** — Use workbook names as market signals, but verify against inventory rows before assigning projects to areas. (Source: AIOS build logs + area intelligence chats)
2. **Area alias normalization** — Normalize aliases such as JVC -> Jumeirah Village Circle before search and dashboard use. (Source: Area intelligence chats)
3. **False-area removal** — Filter out false area names like Parking, Internal Road, Garden & Community, and similar utility labels. (Source: Area intelligence chats)
4. **Project-to-area mapping** — Treat communities like Yas Island, Saadiyat, Al Reem, Al Raha, and Al Reeman as true areas that contain multiple projects. (Source: Area intelligence chats)
5. **Search dimensions** — Property search must support area, project, developer, bedrooms, property type, and price range. (Source: Property intelligence build)
6. **Market structure first** — Many spreadsheets are community files, not standalone projects, so normalization must start from the community layer. (Source: Area coverage audit)
7. **Search query format** — Example queries: 2BR Yas Island under 2M; Villa Yas Acres under 5M; Ready properties in Abu Dhabi. (Source: Validation tests)
8. **Canonical area map** — Maintain a canonical area-project alias table so hidden project names become discoverable. (Source: Alias and canonical layer)
9. **Duplicate row handling** — Deduplicate inventory rows only after area and project mapping are stabilized. (Source: Normalization phase)
10. **Community clusters** — Some areas resolve into dense clusters such as Yas Island, Saadiyat Island, Al Reem Island, Al Raha, Al Reeman, and JVC. (Source: Inventory analysis)

## Reusable Pattern
- Keep this category as a living playbook and append new items when new chats add a durable rule, decision, or template.