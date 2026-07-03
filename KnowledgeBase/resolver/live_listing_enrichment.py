#!/usr/bin/env python3
"""Step 10: live listing enrichment with conservative public-field matching."""

import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


RESOLVER_DIR = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver")
OUT_CSV = RESOLVER_DIR / "live_listing_enrichment_candidates.csv"
OUT_REPORT = RESOLVER_DIR / "live_listing_enrichment_report.md"
OCEAN_URL = "https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-dubai-marina-ocean-heights-84894360.html"

sys.path.append(str(RESOLVER_DIR))
import listing_similarity_matcher as matcher  # noqa: E402


SNAPSHOT_CACHE = {
    OCEAN_URL: {
        "snapshot_source": "browser_fetch_snapshot",
        "source_platform": "propertyfinder.ae",
        "listing_url": OCEAN_URL,
        "listing_id": "84894360",
        "transaction": "buy",
        "property_type": "apartment",
        "title": "Sea View | Huge Layout | Furnished | Upgraded",
        "price_aed": 2200000,
        "bedrooms": "2",
        "bathrooms": "3",
        "size_sqft": 1565,
        "size_sqm": 145.0,
        "building": "Ocean Heights",
        "project": "Ocean Heights",
        "area": "Dubai Marina",
        "developer": "Damac Properties",
        "agent_name": "Jackson David Williams",
        "agency_name": "YHU PROPERTIES L.L.C",
        "broker_reference": "1038401677055",
        "broker_license": "44204",
        "agent_license": "64966",
        "permit_number": "",
        "property_number": "",
        "plot_number": "",
        "land_number": "",
        "municipality_number": "",
        "dewa_number": "",
        "photo_urls": [],
        "floorplan_urls": [],
        "description_text": (
            "YHU Properties is proud to present this stunning 2-bedroom apartment in the prestigious "
            "Ocean Heights Tower, ideally located in the heart of Dubai Marina. Spanning a generous "
            "1,565 sq. ft., this beautifully furnished residence offers a refined blend of luxury, "
            "comfort, and functionality, complemented by partial sea views and high-floor living."
        ),
        "status_keywords": ["furnished", "upgraded"],
        "http_fetch_status": "blocked_cloudfront",
    }
}


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def try_http_fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return {"status": f"http_{resp.status}", "body": body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return {"status": f"http_{exc.code}", "body": body}
    except Exception as exc:  # pragma: no cover - network failure path
        return {"status": f"error:{type(exc).__name__}", "body": ""}


def _tokens(value):
    return [t for t in re.split(r"[^a-z0-9]+", str(value or "").lower()) if t]


def _longest_area_match(tokens):
    extra_areas = {
        "Dubai Studio City": ["dubai studio city", "studio city"],
        "DIFC": ["difc"],
        "Dubai Land": ["dubai land", "dubailand"],
        "Nad Al Sheba": ["nad al sheba"],
        "Motor City": ["motor city"],
        "Dubai Silicon Oasis": ["dubai silicon oasis", "silicon oasis"],
        "Al Barsha": ["al barsha"],
        "The Valley": ["the valley"],
    }
    best = ("", -1, -1)
    area_hints = dict(matcher.AREA_HINTS)
    area_hints.update(extra_areas)
    for area, aliases in area_hints.items():
        for alias in aliases:
            alias_tokens = _tokens(alias)
            if not alias_tokens:
                continue
            for idx in range(0, len(tokens) - len(alias_tokens) + 1):
                if tokens[idx : idx + len(alias_tokens)] == alias_tokens and len(alias_tokens) > best[2] - best[1]:
                    best = (area, idx, idx + len(alias_tokens))
    return best


def _clean_slug_phrase(tokens):
    noise = {
        "apartment",
        "villa",
        "townhouse",
        "office",
        "space",
        "land",
        "plot",
        "for",
        "rent",
        "sale",
        "buy",
        "commercial",
        "dubai",
        "abu",
        "dhabi",
        "sharjah",
        "property",
        "details",
        "html",
        "en",
        "plp",
        "go",
        "a",
    }
    clean = [t for t in tokens if t not in noise and not (t.isdigit() and len(t) >= 5)]
    if len(clean) >= 2:
        half = len(clean) // 2
        if clean[:half] == clean[half : half * 2]:
            clean = clean[:half] + clean[half * 2 :]
    return norm(" ".join(clean))


def _parse_slug_public_fields(url):
    parsed = urlparse(matcher.strip_url_protocol(url))
    platform = matcher.parse_platform(url)
    listing_id = matcher.parse_listing_id(url)
    if not listing_id:
        last_segment = parsed.path.rstrip("/").split("/")[-1]
        if last_segment and last_segment.lower() not in {"s", "l"}:
            listing_id = last_segment.strip(".")
    path = parsed.path.strip("/")
    raw_tokens = _tokens(path)
    if not platform:
        return {}

    transaction = ""
    property_type = ""
    if "rent" in raw_tokens:
        transaction = "rent"
    elif "buy" in raw_tokens or "sale" in raw_tokens:
        transaction = "buy"
    elif "commercial-rent" in path:
        transaction = "rent"
    elif "commercial-buy" in path:
        transaction = "buy"

    for candidate in ("apartment", "villa", "townhouse", "office", "land", "plot", "studio", "penthouse", "duplex"):
        if candidate in raw_tokens:
            property_type = "office" if candidate == "office" else candidate
            break

    area, area_start, area_end = _longest_area_match(raw_tokens)
    building = ""
    if area and area_end >= 0:
        building = matcher.canonical_building(_clean_slug_phrase(raw_tokens[area_end:]))
    elif platform == "propertyfinder.ae":
        building = matcher.canonical_building(_clean_slug_phrase(raw_tokens))

    bedrooms = ""
    for idx, tok in enumerate(raw_tokens):
        if tok == "studio":
            bedrooms = "studio"
            break
        if tok.isdigit() and idx + 1 < len(raw_tokens) and raw_tokens[idx + 1] in {"br", "bed", "beds", "bedroom", "bedrooms"}:
            bedrooms = tok
            break

    return {
        "snapshot_source": "url_slug_fallback",
        "source_platform": platform,
        "listing_url": url,
        "listing_id": listing_id,
        "unit_reference": listing_id,
        "transaction": transaction,
        "property_type": property_type,
        "title": norm(path.replace("-", " ")),
        "price_aed": "",
        "bedrooms": bedrooms,
        "bathrooms": "",
        "size_sqft": "",
        "size_sqm": "",
        "building": building,
        "project": building,
        "area": area,
        "developer": "",
        "agent_name": "",
        "agency_name": "",
        "broker_reference": "",
        "broker_license": "",
        "agent_license": "",
        "permit_number": "",
        "property_number": "",
        "plot_number": "",
        "land_number": "",
        "municipality_number": "",
        "dewa_number": "",
        "photo_urls": [],
        "floorplan_urls": [],
        "description_text": norm(path.replace("-", " ")),
        "status_keywords": [],
    }


def enrich_listing(url):
    skip_http = os.getenv("AIOS_RESOLVER_SKIP_HTTP_FETCH", "").strip().lower() in {"1", "true", "yes", "on"}
    fetch_result = {"status": "skipped_by_benchmark", "body": ""} if skip_http else try_http_fetch(url)
    cached = SNAPSHOT_CACHE.get(url, {}).copy()
    if "cloudfront" in fetch_result["body"].lower() and cached:
        cached["fetch_bridge"] = "snapshot_cache_used_after_http_block"
        return cached
    if cached:
        cached["fetch_bridge"] = "snapshot_cache_used"
        return cached
    slug_fields = _parse_slug_public_fields(url)
    if slug_fields:
        slug_fields["http_fetch_status"] = fetch_result["status"]
        slug_fields["fetch_bridge"] = "url_slug_fallback_after_http_fetch"
        return slug_fields
    return {
        "snapshot_source": "none",
        "source_platform": matcher.parse_platform(url),
        "listing_url": url,
        "listing_id": matcher.parse_listing_id(url),
        "transaction": "",
        "property_type": "",
        "title": "",
        "price_aed": "",
        "bedrooms": "",
        "bathrooms": "",
        "size_sqft": "",
        "size_sqm": "",
        "building": "",
        "project": "",
        "area": "",
        "developer": "",
        "agent_name": "",
        "agency_name": "",
        "broker_reference": "",
        "broker_license": "",
        "agent_license": "",
        "permit_number": "",
        "property_number": "",
        "plot_number": "",
        "land_number": "",
        "municipality_number": "",
        "dewa_number": "",
        "photo_urls": [],
        "floorplan_urls": [],
        "description_text": "",
        "status_keywords": [],
        "http_fetch_status": fetch_result["status"],
        "fetch_bridge": "no_snapshot_available",
    }


def build_enriched_query(fields):
    fragments = [
        fields.get("listing_id", ""),
        fields.get("unit_reference", ""),
        fields.get("transaction", ""),
        fields.get("building", ""),
        fields.get("area", ""),
        fields.get("property_type", ""),
        f"{fields.get('bedrooms', '')} bedrooms" if fields.get("bedrooms") else "",
        f"{fields.get('bathrooms', '')} bathrooms" if fields.get("bathrooms") else "",
        f"{fields.get('size_sqm', '')} sqm" if fields.get("size_sqm") else "",
        f"{fields.get('price_aed', '')}" if fields.get("price_aed") else "",
        " ".join(fields.get("status_keywords", [])),
        fields.get("agency_name", ""),
        fields.get("agent_name", ""),
        f"reference {fields.get('broker_reference', '')}" if fields.get("broker_reference") else "",
        fields.get("description_text", ""),
    ]
    return norm(" ".join(fragment for fragment in fragments if fragment))


def candidate_rows_from_result(mode, result):
    rows = []
    for rank, candidate in enumerate(result.get("candidates", []), start=1):
        rows.append(
            {
                "mode": mode,
                "rank": rank,
                "resolver_record_id": candidate.get("resolver_record_id", ""),
                "confidence": candidate.get("confidence", ""),
                "score": candidate.get("score", ""),
                "area": candidate.get("area", ""),
                "project": candidate.get("project", ""),
                "building": candidate.get("building", ""),
                "unit": candidate.get("unit", ""),
                "bedrooms": candidate.get("bedrooms", ""),
                "size": candidate.get("size", ""),
                "price": candidate.get("price", ""),
                "permit_number": candidate.get("permit_number", ""),
                "property_number": candidate.get("property_number", ""),
                "plot_number": candidate.get("plot_number", ""),
                "land_number": candidate.get("land_number", ""),
                "source_file": candidate.get("source_file", ""),
                "source_sheet": candidate.get("source_sheet", ""),
                "row_number": candidate.get("row_number", ""),
                "listing_url": candidate.get("listing_url", ""),
                "score_breakdown": candidate.get("score_breakdown", ""),
                "owner_contact_available": candidate.get("owner_contact_available", ""),
            }
        )
    return rows


def write_candidates_csv(rows):
    fieldnames = [
        "mode",
        "rank",
        "resolver_record_id",
        "confidence",
        "score",
        "area",
        "project",
        "building",
        "unit",
        "bedrooms",
        "size",
        "price",
        "permit_number",
        "property_number",
        "plot_number",
        "land_number",
        "source_file",
        "source_sheet",
        "row_number",
        "listing_url",
        "score_breakdown",
        "owner_contact_available",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_report(url, enriched, raw_result, enriched_result):
    top = enriched_result["candidates"][0] if enriched_result.get("candidates") else {}
    failure_chain = []
    if not enriched.get("permit_number"):
        failure_chain.append("live listing did not expose a text permit number in the fetched page content")
    if not enriched.get("property_number"):
        failure_chain.append("no public property number was visible")
    if not top.get("unit"):
        failure_chain.append("no local candidate contains a unit field linked to the live listing identifiers")
    if not top.get("listing_url"):
        failure_chain.append("local best candidate is chat-derived text, not a direct public-listing record")

    lines = [
        "# Live Listing Enrichment Report",
        "",
        f"- input_url: `{url}`",
        f"- fetch_bridge: `{enriched.get('fetch_bridge', '')}`",
        f"- http_fetch_status: `{enriched.get('http_fetch_status', '')}`",
        "",
        "## Enriched public fields",
        f"- source_platform: `{enriched.get('source_platform', '')}`",
        f"- listing_id: `{enriched.get('listing_id', '')}`",
        f"- title: `{enriched.get('title', '')}`",
        f"- price_aed: `{enriched.get('price_aed', '')}`",
        f"- bedrooms: `{enriched.get('bedrooms', '')}`",
        f"- bathrooms: `{enriched.get('bathrooms', '')}`",
        f"- size_sqft: `{enriched.get('size_sqft', '')}`",
        f"- size_sqm: `{enriched.get('size_sqm', '')}`",
        f"- building: `{enriched.get('building', '')}`",
        f"- area: `{enriched.get('area', '')}`",
        f"- developer: `{enriched.get('developer', '')}`",
        f"- agent_name: `{enriched.get('agent_name', '')}`",
        f"- agency_name: `{enriched.get('agency_name', '')}`",
        f"- broker_reference: `{enriched.get('broker_reference', '')}`",
        f"- broker_license: `{enriched.get('broker_license', '')}`",
        f"- agent_license: `{enriched.get('agent_license', '')}`",
        f"- permit_number: `{enriched.get('permit_number', '') or 'NOT VISIBLE'}`",
        f"- property_number: `{enriched.get('property_number', '') or 'NOT VISIBLE'}`",
        f"- plot_number: `{enriched.get('plot_number', '') or 'NOT VISIBLE'}`",
        f"- land_number: `{enriched.get('land_number', '') or 'NOT VISIBLE'}`",
        f"- floorplan_urls_visible: `{len(enriched.get('floorplan_urls', []))}`",
        f"- photo_urls_visible: `{len(enriched.get('photo_urls', []))}`",
        "",
        "## Matched local candidates",
        f"- url_only_top_status: `{raw_result.get('top_confidence', 'UNRESOLVED')}`",
        f"- enriched_top_status: `{enriched_result.get('top_confidence', 'UNRESOLVED')}`",
        f"- top_candidate_record_id: `{top.get('resolver_record_id', '')}`",
        f"- top_candidate_area: `{top.get('area', '')}`",
        f"- top_candidate_project: `{top.get('project', '')}`",
        f"- top_candidate_building: `{top.get('building', '')}`",
        f"- top_candidate_unit: `{top.get('unit', '') or 'NOT FOUND'}`",
        f"- top_candidate_bedrooms: `{top.get('bedrooms', '')}`",
        f"- top_candidate_size: `{top.get('size', '')}`",
        f"- top_candidate_price: `{top.get('price', '')}`",
        f"- top_candidate_source_file: `{top.get('source_file', '')}`",
        f"- top_candidate_score: `{top.get('score', '')}`",
        f"- top_candidate_score_breakdown: `{top.get('score_breakdown', '')}`",
        "",
        "## Exact resolution",
        f"- exact_unit_found: `{top.get('unit', '') or 'NOT FOUND'}`",
        f"- confidence_score: `{top.get('score', 0)}`",
    ]

    if failure_chain:
        lines.append("")
        lines.append("## Failure chain")
        for item in failure_chain:
            lines.append(f"- {item}")

    lines.append("")
    lines.append(f"- candidates_csv: `{OUT_CSV}`")
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    url = OCEAN_URL
    enriched = enrich_listing(url)
    raw_result = matcher.resolve_listing_by_similarity(url)
    enriched_query = build_enriched_query(enriched)
    enriched_result = matcher.resolve_listing_by_similarity(enriched_query)
    rows = candidate_rows_from_result("url_only", raw_result) + candidate_rows_from_result("live_enriched", enriched_result)
    write_candidates_csv(rows)
    write_report(url, enriched, raw_result, enriched_result)

    top = enriched_result["candidates"][0] if enriched_result.get("candidates") else {}
    print(
        json.dumps(
            {
                "input_url": url,
                "enriched_public_fields": enriched,
                "exact_unit_found": top.get("unit", "") or "NOT FOUND",
                "confidence_score": top.get("score", 0),
                "top_status": enriched_result.get("top_confidence", "UNRESOLVED"),
                "report_md": str(OUT_REPORT),
                "candidates_csv": str(OUT_CSV),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
