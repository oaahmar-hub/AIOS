# AIOS Unit Finder Limitations

Status date: 2026-06-23

## Known Limitations

## 1. Missing URL Bridge Dataset

The biggest blocker is the missing bridge between public listing links and private unit identifiers.

Current evidence shows that Property Finder, Bayut, and Dubizzle links can often be parsed and matched by similarity, but they usually do not expose:

- Unit number
- Permit number
- Property number
- Plot number
- Land number

Without one of these fields, URL-only exact unit resolution should not be claimed.

## 2. Exact Match Requires Strong Keys

Exact resolution is reliable only when the input contains one of:

- Permit/property/plot/land/municipality/DEWA identifier present in the local index
- Building/project plus unit number

If neither exists, the resolver should return LIKELY, PARTIAL, or UNRESOLVED based on score.

## 3. Noisy Text Has Limited Reliability

Free-text descriptions work only when they include enough comparable fields:

- Area
- Building/project
- Bedrooms
- Size
- Price
- Status/furnishing

Descriptions like "send me options", "how much is this unit", or budget-only requests do not contain enough property identity.

## 4. Agent, Company, and Broker Reference Are Weak Alone

Agent/company or broker reference can help only if those fields also exist in the local corpus and connect to unit-bearing records.

Current local bridge evidence is not strong enough to treat these as exact keys.

## 5. Similarity Is Not Exact Identity

Similarity can produce useful candidate matches, but it cannot safely prove the exact unit without a hard identifier or unit number.

The resolver must not guess exact unit numbers from:

- Area plus building only
- Price plus size only
- URL slug only
- Agent/company only
- Description similarity only

## 6. Owner/Contact Data Restriction

Owner/contact data exists in local restricted data, but it must not be exposed in public resolver output.

Allowed public field:

- `owner_contact_available`: `YES` or `NO`

Restricted fields must remain internal only:

- Owner name
- Mobile number
- Email
- Direct contact details
- Restricted source references

## Required Future Bridge Data

Exact URL to unit resolution requires at least one of these bridge sources:

- Listing URL or listing ID plus unit number
- Listing URL or listing ID plus permit/property/plot/land number
- Broker reference plus unit number
- Broker reference plus permit/property/plot/land number
- CRM export linking live listing references to unit records
- Broker inventory export containing listing URL and unit details
- WhatsApp messages containing both listing link and unit number
- Portal/export files from Property Finder, Bayut, or Dubizzle that include broker references and unit identifiers
- DLD/Dubai REST/permit dataset that maps public permit/listing data to property identifiers

## Unsupported Claims

Do not claim:

- "Exact URL to unit is live"
- "Telegram-bot style exact unit finder is complete"
- "Owner/contact data is publicly retrievable"
- "Area/building-only search identifies the exact unit"
- "Similarity-only result is exact"

