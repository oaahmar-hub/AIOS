# WF03 — Property Finder Listing Publish

**Flow:** Unit → verify → permit → copy → price → publish → log
**Trigger:** New listing to publish or an existing one to refresh.
**Lead agent:** [A03 Listings Manager](../01_Agents/A03_Listings_Manager.md) · **Supports:** A12, A04, A08

## Steps
1. **Verify the unit** via [A12](../01_Agents/A12_Unit_Finder_Operator.md). If only a URL is known and it won't resolve → confirm the unit manually before continuing.
2. 🔒 **Permit gate** — confirm a valid RERA/Trakheesi advertising permit ([SOP04](../03_SOPs/SOP04_RERA_Advertising_Permit.md)). No permit → route to A04, hold publish.
3. **Comparables** — A08 returns a defensible price band ([T10](../04_Templates/T10_Comparative_Market_Analysis.md)).
4. **Write copy** from [T01](../04_Templates/T01_Listing_Copy.md): title, highlights, location, terms; compliant claims only.
5. **Media** — confirm photos/floorplan from Drive; flag if missing.
6. **Publish/refresh** on Property Finder (and Bayut/Dubizzle if applicable).
7. **Log** to the pipeline tracker listing section: unit, permit no., price, publish date, portal.
8. **Maintenance hook** — set a 30-day refresh/stale-check reminder.

## Outputs
- Live/updated listing, permit number on file, comps, copy, publish log, refresh reminder.

## Done when
- Listing live with a valid permit, price defensible, logged, refresh reminder set.

## Hard rule
- No publish without a confirmed permit and a confirmed unit. 🔒
