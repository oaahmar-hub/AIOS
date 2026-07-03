#!/usr/bin/env python3
"""Step 11: benchmark real-world usefulness on 50 live listing URLs."""

import csv
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys
from urllib.parse import urlparse


RESOLVER_DIR = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver")
IDENTITY_CSV = RESOLVER_DIR / "listing_identity_map.csv"
OUT_CSV = RESOLVER_DIR / "live_listing_benchmark_results.csv"
OUT_REPORT = RESOLVER_DIR / "live_listing_benchmark_report.md"

sys.path.append(str(RESOLVER_DIR))
import live_listing_enrichment as enrich  # noqa: E402
import listing_similarity_matcher as matcher  # noqa: E402

os.environ.setdefault("AIOS_RESOLVER_SKIP_HTTP_FETCH", "1")


TARGET_COUNTS = {
    "propertyfinder": 25,
    "bayut": 15,
    "dubizzle": 10,
}

FAST_RECORDS = None


def detect_source(url):
    host = (urlparse(url).netloc or "").lower()
    if "propertyfinder.ae" in host:
        return "propertyfinder"
    if "bayut.com" in host:
        return "bayut"
    if "dubizzle.com" in host:
        return "dubizzle"
    return ""


def is_listing_like(url):
    lower = url.lower().strip()
    source = detect_source(lower)
    if not source:
        return False
    if source == "propertyfinder":
        blocked = ("/new-projects/", "/agent/", "/leads/", "/preview")
        if any(token in lower for token in blocked):
            return False
        return "/plp/" in lower or "/go/" in lower
    if source == "bayut":
        return "property/details-" in lower or "/l/" in lower
    if source == "dubizzle":
        if "/blog/" in lower:
            return False
        return "/s/" in lower or "/property-for-" in lower
    return False


def collect_urls():
    by_source = defaultdict(list)
    seen = set()
    with IDENTITY_CSV.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for col in ("listing_url", "property_finder_url", "bayut_url", "dubizzle_url"):
                url = (row.get(col) or "").strip()
                if not url or url in seen or not is_listing_like(url):
                    continue
                source = detect_source(url)
                if not source:
                    continue
                by_source[source].append(url)
                seen.add(url)
                break
    selected = []
    for source, need in TARGET_COUNTS.items():
        selected.extend((source, url) for url in by_source[source][:need])
    if len(selected) < sum(TARGET_COUNTS.values()):
        already = {url for _, url in selected}
        for source in ("propertyfinder", "bayut", "dubizzle"):
            for url in by_source[source]:
                if url in already:
                    continue
                selected.append((source, url))
                already.add(url)
                if len(selected) >= sum(TARGET_COUNTS.values()):
                    break
            if len(selected) >= sum(TARGET_COUNTS.values()):
                break
    return selected


def extract_display_fields(enriched):
    area = enriched.get("area", "")
    building = enriched.get("building", "") or enriched.get("project", "")
    bedrooms = enriched.get("bedrooms", "")
    size = ""
    if enriched.get("size_sqm"):
        size = f"{enriched.get('size_sqm')} sqm"
    elif enriched.get("size_sqft"):
        size = f"{enriched.get('size_sqft')} sqft"
    price = enriched.get("price_aed", "")
    return area, building, bedrooms, size, price


def _url_fields(rec):
    return [
        rec.get("listing_url", ""),
        rec.get("property_finder_url", ""),
        rec.get("bayut_url", ""),
        rec.get("dubizzle_url", ""),
    ]


def _token_overlap(left, right):
    lt = set(matcher.tokenize(left))
    rt = set(matcher.tokenize(right))
    if not lt or not rt:
        return 0.0
    return len(lt & rt) / max(len(lt), 1)


def _candidate_from_record(rec, score, method):
    return {
        "score": score,
        "unit": rec.get("unit", ""),
        "resolver_record_id": rec.get("resolver_record_id", ""),
        "area": rec.get("area", ""),
        "project": rec.get("project", ""),
        "building": rec.get("building", ""),
        "bedrooms": rec.get("bedrooms", ""),
        "size": rec.get("size", ""),
        "price": rec.get("price", ""),
        "source_file": rec.get("source_file", ""),
        "source_sheet": rec.get("source_sheet", ""),
        "row_number": rec.get("row_number", ""),
        "listing_url": next((u for u in _url_fields(rec) if u), ""),
        "match_method": method,
    }


def _fast_records():
    global FAST_RECORDS
    if FAST_RECORDS is not None:
        return FAST_RECORDS
    prepared = []
    for rec in matcher.get_prepared_records():
        rec_urls = [matcher.low(u).rstrip("#") for u in _url_fields(rec) if u]
        rec_entity_raw = rec.get("building", "") or rec.get("project", "")
        prepared.append(
            {
                "rec": rec,
                "urls": rec_urls,
                "listing_id": matcher.low(rec.get("listing_id", "")),
                "area": matcher.canonical_area(rec.get("area", "")),
                "entity": matcher.canonical_building(rec_entity_raw),
                "entity_tokens": set(matcher.tokenize(rec_entity_raw)),
                "project": matcher.canonical_project(rec.get("project", "")),
                "bedrooms": matcher.canonical_bedrooms(rec.get("bedrooms", "")),
                "property_type": matcher.low(rec.get("property_type", "")),
                "has_unit": bool(rec.get("unit", "")),
            }
        )
    FAST_RECORDS = prepared
    return FAST_RECORDS


def fast_resolve_enriched(url, enriched):
    target_url = matcher.low(url).rstrip("#")
    listing_id = matcher.low(enriched.get("listing_id", ""))
    area = matcher.canonical_area(enriched.get("area", ""))
    building = matcher.canonical_building(enriched.get("building", "") or enriched.get("project", ""))
    building_tokens = set(matcher.tokenize(building))
    project = matcher.canonical_project(enriched.get("project", ""))
    bedrooms = matcher.canonical_bedrooms(enriched.get("bedrooms", ""))
    property_type = matcher.low(enriched.get("property_type", ""))

    found = {}

    def add(rec, score, method):
        key = "|".join(
            [
                rec.get("resolver_record_id", ""),
                rec.get("source_file", ""),
                rec.get("source_sheet", ""),
                rec.get("row_number", ""),
                rec.get("unit", ""),
                next((u for u in _url_fields(rec) if u), ""),
            ]
        )
        current = found.get(key)
        if not current or score > current["score"]:
            found[key] = _candidate_from_record(rec, score, method)

    for item in _fast_records():
        rec = item["rec"]
        if target_url and target_url in item["urls"]:
            add(rec, 99 if rec.get("unit") else 78, "exact_listing_url")
            continue
        if listing_id and listing_id == item["listing_id"]:
            add(rec, 96 if rec.get("unit") else 76, "exact_listing_id")

    for item in _fast_records():
        rec = item["rec"]
        score = 0
        reasons = []
        if area and item["area"] == area:
            score += 38
            reasons.append("area")
        if building:
            if building_tokens and item["entity_tokens"]:
                overlap = len(building_tokens & item["entity_tokens"]) / max(len(building_tokens), 1)
            else:
                overlap = 0.0
            if item["entity"] and (matcher.low(building) == matcher.low(item["entity"]) or overlap >= 0.55):
                score += 42
                reasons.append("building")
            elif overlap >= 0.35:
                score += 25
                reasons.append("building_partial")
        if project:
            if item["project"] and item["project"] == project:
                score += 18
                reasons.append("project")
        if bedrooms and bedrooms == item["bedrooms"]:
            score += 8
            reasons.append("bedrooms")
        if property_type and property_type in item["property_type"]:
            score += 4
            reasons.append("property_type")
        if item["has_unit"]:
            score += 4
            reasons.append("unit_available")
        if area and item["area"] == area and item["has_unit"] and score < 66:
            score = 66
            reasons.append("similar_area_unit")
        if score >= 58:
            add(rec, min(score, 94), "+".join(reasons))

    ranked = sorted(found.values(), key=lambda item: (item["score"] + (15 if item.get("unit") else 0), item["score"]), reverse=True)[:5]
    if not ranked:
        return {"candidates": [], "top_confidence": "UNRESOLVED"}
    top_score = ranked[0]["score"]
    status = "EXACT" if ranked[0].get("unit") and top_score >= 90 else "LIKELY_MATCH" if top_score >= 80 else "PARTIAL" if top_score >= 65 else "UNRESOLVED"
    return {"candidates": ranked, "top_confidence": status}


def classify_result(final_result):
    top = final_result["candidates"][0] if final_result.get("candidates") else {}
    score = int(top.get("score", 0) or 0)
    unit = (top.get("unit") or "").strip()
    if unit and score >= 90:
        return "EXACT", top
    if score >= 80:
        return "LIKELY", top
    return "UNRESOLVED", top


def failure_reasons(enriched, final_result, classification, top):
    reasons = []
    bridge = enriched.get("fetch_bridge", "")
    if bridge == "no_snapshot_available" and enriched.get("http_fetch_status", "").startswith(("http_403", "error:")):
        reasons.append("live_fetch_blocked")
    if not any(enriched.get(key) for key in ("permit_number", "property_number", "plot_number", "land_number")):
        reasons.append("no_public_identifier_bridge")
    if not any(enriched.get(key) for key in ("area", "building", "bedrooms", "size_sqm", "price_aed", "listing_id", "unit_reference")):
        reasons.append("no_public_fields_extracted")
    has_similar_unit = any(candidate.get("unit") for candidate in final_result.get("candidates", []))
    if classification != "EXACT" and not (top.get("unit") or "") and not has_similar_unit:
        reasons.append("no_unit_in_local_match")
    if classification == "UNRESOLVED":
        if not final_result.get("candidates"):
            reasons.append("no_candidate_match")
        else:
            reasons.append("insufficient_similarity_score")
    return ",".join(sorted(set(reasons)))


def run_benchmark():
    rows = []
    stats = Counter()
    source_stats = Counter()
    failures = Counter()

    for source, url in collect_urls():
        enriched = enrich.enrich_listing(url)
        final_result = fast_resolve_enriched(url, enriched)
        classification, top = classify_result(final_result)
        area, building, bedrooms, size, price = extract_display_fields(enriched)
        failure = failure_reasons(enriched, final_result, classification, top)

        row = {
            "source": source,
            "url": url,
            "listing_source": enriched.get("source_platform", source),
            "unit_reference": enriched.get("unit_reference", "") or enriched.get("listing_id", ""),
            "area": area,
            "building": building,
            "bedrooms": bedrooms,
            "size": size,
            "price": price,
            "confidence": top.get("score", 0),
            "exact_unit_found": "YES" if classification == "EXACT" else "NO",
            "likely_match": "YES" if classification == "LIKELY" else "NO",
            "unresolved": "YES" if classification == "UNRESOLVED" else "NO",
            "resolved_unit": top.get("unit", ""),
            "top_status": final_result.get("top_confidence", "UNRESOLVED"),
            "top_record_id": top.get("resolver_record_id", ""),
            "similar_units_count": sum(1 for c in final_result.get("candidates", []) if c.get("unit")),
            "match_method": top.get("match_method", ""),
            "fetch_status": enriched.get("http_fetch_status", ""),
            "fetch_bridge": enriched.get("fetch_bridge", ""),
            "failure_reasons": failure,
        }
        rows.append(row)
        stats[classification] += 1
        source_stats[f"{source}_{classification.lower()}"] += 1
        for item in filter(None, failure.split(",")):
            failures[item] += 1

    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    exact_rate = round((stats["EXACT"] / total) * 100, 2) if total else 0
    likely_rate = round((stats["LIKELY"] / total) * 100, 2) if total else 0
    unresolved_rate = round((stats["UNRESOLVED"] / total) * 100, 2) if total else 0

    lines = [
        "# Live Listing Benchmark Report",
        "",
        f"- total_tests: {total}",
        f"- exact_resolution_rate: {exact_rate}%",
        f"- likely_match_rate: {likely_rate}%",
        f"- unresolved_rate: {unresolved_rate}%",
        "",
        "## Source mix",
    ]
    for source in ("propertyfinder", "bayut", "dubizzle"):
        source_total = sum(1 for row in rows if row["source"] == source)
        lines.append(f"- {source}: {source_total}")

    lines.extend(
        [
            "",
            "## Outcome counts",
            f"- exact: {stats['EXACT']}",
            f"- likely: {stats['LIKELY']}",
            f"- unresolved: {stats['UNRESOLVED']}",
            "",
            "## Top failure reasons",
        ]
    )
    for reason, count in failures.most_common(8):
        lines.append(f"- {reason}: {count}")
    lines.append("")
    lines.append(f"- results_csv: `{OUT_CSV}`")
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "total_tests": total,
        "exact_rate": exact_rate,
        "likely_rate": likely_rate,
        "unresolved_rate": unresolved_rate,
        "counts": stats,
        "top_failure_reasons": failures.most_common(8),
        "results_csv": str(OUT_CSV),
        "report_md": str(OUT_REPORT),
    }


def main():
    result = run_benchmark()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
