# Property Intelligence Schemas and Validation Rules

## Core entities

- Developer: developer_id, name, aliases, source, confidence.
- Project: project_id, developer_id, name, area, master_developer, handover, status.
- Building: building_id, project_id, name, aliases, location, permit_reference.
- Unit: unit_id, building_id, unit_number, type, beds, baths, floor, size, view, price, status.
- Owner: owner_id, name, contact_hash, source, consent_status.
- FloorPlan: floorplan_id, unit_type, project_id, file_path, page, area, bedrooms.
- Listing: listing_id, url, source_platform, text, price, unit_id_candidate, confidence.
- MatchEvidence: match_id, left_record, right_record, signals, confidence, reviewer_status.

## Validation rules

- A unit match is exact only when a stable identifier or building plus unit number agrees.
- URL-only matches cannot be marked exact unless the URL row contains a unit, permit, property, plot, or other bridge identifier.
- Floor plan recommendations must include project, unit type, bedroom count, size band, and source evidence.
- Owner data must be access-controlled and never used in public recommendations without permission.
