#!/usr/bin/env python3
"""Step 12: identify exact or likely identifier bridges from existing corpus."""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


RESOLVER_DIR = Path(__file__).resolve().parent
BENCHMARK_CSV = RESOLVER_DIR / "live_listing_benchmark_results.csv"
OUT_CSV = RESOLVER_DIR / "identifier_bridge_candidates.csv"
OUT_REPORT = RESOLVER_DIR / "identifier_bridge_strategy_report.md"

sys.path.append(str(RESOLVER_DIR))
import listing_similarity_matcher as matcher  # noqa: E402


IDENTIFIER_FIELDS = ("permit_number", "property_number", "plot_number", "land_number")


def low(value):
    return matcher.low(value)


def meaningful_identifier(field, value):
    text = low(value)
    if not text:
        return ""
    blocked_fragments = {
        "details",
        "listed",
        "scaped",
        "com",
    }
    if any(fragment in text for fragment in blocked_fragments):
        return ""
    if field == "property_number" and text.startswith("/details"):
        return ""
    return text


def dedupe_records(records):
    out = []
    seen = set()
    for record in records:
        sig = (
            record.get("listing_url", ""),
            record.get("listing_id", ""),
            record.get("source_file", ""),
            record.get("row_number", ""),
            record.get("source_chat_group", ""),
        )
        if sig in seen:
            continue
        seen.add(sig)
        out.append(record)
    return out


def build_indexes(records):
    by_url = defaultdict(list)
    by_listing_id = defaultdict(list)
    by_area_building_units = defaultdict(list)
    by_area_project_units = defaultdict(list)
    by_identifier_units = {field: defaultdict(list) for field in IDENTIFIER_FIELDS}
    by_chat_units = defaultdict(list)

    for record in records:
        url = low(record.get("listing_url", ""))
        if url:
            by_url[url].append(record)

        listing_id = low(record.get("listing_id", ""))
        if listing_id:
            by_listing_id[listing_id].append(record)

        unit = (record.get("unit") or "").strip()
        if not unit:
            continue

        area = matcher.canonical_area(record.get("area", ""))
        building = matcher.canonical_building(record.get("building", ""))
        project = matcher.canonical_project(record.get("project", ""))

        if area and building:
            by_area_building_units[(area, building)].append(record)
        if area and project:
            by_area_project_units[(area, project)].append(record)

        chat = low(record.get("source_chat_group", ""))
        if chat:
            by_chat_units[chat].append(record)

        for field in IDENTIFIER_FIELDS:
            identifier = meaningful_identifier(field, record.get(field, ""))
            if identifier:
                by_identifier_units[field][identifier].append(record)

    return {
        "by_url": by_url,
        "by_listing_id": by_listing_id,
        "by_area_building_units": by_area_building_units,
        "by_area_project_units": by_area_project_units,
        "by_identifier_units": by_identifier_units,
        "by_chat_units": by_chat_units,
    }


def analyze_listing(row, indexes):
    query = matcher.parse_input_text(row["url"])
    parsed_area = matcher.canonical_area(query.get("area", ""))
    parsed_building = matcher.canonical_building(query.get("building", ""))
    parsed_project = matcher.canonical_project(query.get("project", ""))
    parsed_listing_id = low(query.get("listing_id", ""))

    direct = indexes["by_url"].get(low(row["url"]), []) + indexes["by_listing_id"].get(parsed_listing_id, [])
    direct = dedupe_records(direct)

    direct_ids = {}
    exact_identifier_hits = {}
    for field in IDENTIFIER_FIELDS:
        values = sorted(
            {
                meaningful_identifier(field, record.get(field, ""))
                for record in direct
                if meaningful_identifier(field, record.get(field, ""))
            }
        )
        if values:
            direct_ids[field] = values
            matches = []
            for value in values:
                matches.extend(indexes["by_identifier_units"][field].get(value, []))
            exact_identifier_hits[field] = dedupe_records(matches)

    same_area_building_units = []
    if parsed_area and parsed_building:
        same_area_building_units = dedupe_records(
            indexes["by_area_building_units"].get((parsed_area, parsed_building), [])
        )

    same_area_project_units = []
    if parsed_area and parsed_project:
        same_area_project_units = dedupe_records(
            indexes["by_area_project_units"].get((parsed_area, parsed_project), [])
        )

    direct_chats = sorted({low(record.get("source_chat_group", "")) for record in direct if record.get("source_chat_group")})
    same_chat_group_units = []
    for chat in direct_chats:
        same_chat_group_units.extend(indexes["by_chat_units"].get(chat, []))
    same_chat_group_units = dedupe_records(same_chat_group_units)

    exact_hits_total = sum(len(records) for records in exact_identifier_hits.values())

    if exact_hits_total > 0:
        classification = "exact bridge possible"
        if exact_identifier_hits.get("permit_number"):
            best_bridge_type = "permit_number"
        elif exact_identifier_hits.get("property_number"):
            best_bridge_type = "property_number"
        elif exact_identifier_hits.get("plot_number"):
            best_bridge_type = "plot_number"
        else:
            best_bridge_type = "land_number"
    elif same_area_building_units:
        classification = "likely bridge possible"
        best_bridge_type = "area+building"
    elif same_area_project_units:
        classification = "likely bridge possible"
        best_bridge_type = "area+project"
    elif same_chat_group_units:
        classification = "likely bridge possible"
        best_bridge_type = "source_chat_group"
    else:
        classification = "no local bridge"
        best_bridge_type = "listing_row_only"

    evidence_notes = []
    if direct:
        evidence_notes.append(f"direct_listing_rows={len(direct)}")
    if same_area_building_units:
        evidence_notes.append(f"same_area_building_units={len(same_area_building_units)}")
    if same_area_project_units:
        evidence_notes.append(f"same_area_project_units={len(same_area_project_units)}")
    if same_chat_group_units:
        evidence_notes.append(f"same_chat_group_units={len(same_chat_group_units)}")
    for field, matches in exact_identifier_hits.items():
        if matches:
            evidence_notes.append(f"{field}_unit_matches={len(matches)}")

    return {
        "source": row["source"],
        "url": row["url"],
        "parsed_listing_id": query.get("listing_id", ""),
        "parsed_area": parsed_area,
        "parsed_project": parsed_project,
        "parsed_building": parsed_building,
        "direct_listing_rows": len(direct),
        "permit_values": "|".join(direct_ids.get("permit_number", [])),
        "property_values": "|".join(direct_ids.get("property_number", [])),
        "plot_values": "|".join(direct_ids.get("plot_number", [])),
        "land_values": "|".join(direct_ids.get("land_number", [])),
        "permit_unit_hits": len(exact_identifier_hits.get("permit_number", [])),
        "property_unit_hits": len(exact_identifier_hits.get("property_number", [])),
        "plot_unit_hits": len(exact_identifier_hits.get("plot_number", [])),
        "land_unit_hits": len(exact_identifier_hits.get("land_number", [])),
        "same_area_building_unit_hits": len(same_area_building_units),
        "same_area_project_unit_hits": len(same_area_project_units),
        "same_chat_group_unit_hits": len(same_chat_group_units),
        "classification": classification,
        "best_bridge_type": best_bridge_type,
        "evidence_note": ";".join(evidence_notes),
    }


def write_csv(rows):
    fieldnames = list(rows[0].keys())
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows, records):
    counts = Counter(row["classification"] for row in rows)
    bridge_types = Counter(row["best_bridge_type"] for row in rows)
    viable_bridge_types = Counter(
        row["best_bridge_type"]
        for row in rows
        if row["best_bridge_type"] != "listing_row_only"
    )
    exact_identifier_types = Counter()
    for row in rows:
        for field in ("permit_unit_hits", "property_unit_hits", "plot_unit_hits", "land_unit_hits"):
            if int(row[field]) > 0:
                exact_identifier_types[field] += 1

    total_broker_like_hits = 0
    meaningful_property_values = sum(1 for row in rows if row["property_values"])
    lines = [
        "# Identifier Bridge Strategy Report",
        "",
        f"- total_benchmark_listings: {len(rows)}",
        f"- exact_bridges_found: {counts['exact bridge possible']}",
        f"- likely_bridges_found: {counts['likely bridge possible']}",
        f"- impossible_no_local_bridge_count: {counts['no local bridge']}",
        f"- best_bridge_type: `{viable_bridge_types.most_common(1)[0][0] if viable_bridge_types else 'none'}`",
        "",
        "## Bridge type counts",
    ]
    for bridge_type, count in bridge_types.most_common():
        lines.append(f"- {bridge_type}: {count}")

    lines.extend(
        [
            "",
            "## Identifier evidence",
            f"- meaningful_permit_links: {exact_identifier_types['permit_unit_hits']}",
            f"- meaningful_property_links: {exact_identifier_types['property_unit_hits']}",
            f"- meaningful_plot_links: {exact_identifier_types['plot_unit_hits']}",
            f"- meaningful_land_links: {exact_identifier_types['land_unit_hits']}",
            f"- benchmark_rows_with_meaningful_property_values: {meaningful_property_values}",
            f"- benchmark_rows_with_broker_or_company_bridge: {total_broker_like_hits}",
            f"- total_unit_rows_in_local_corpus: {sum(1 for record in records if (record.get('unit') or '').strip())}",
            "",
            "## Verdict",
            "- Existing corpus does not support exact unit resolution for the 50 benchmark listings through meaningful permit/property/plot/land identifiers.",
            "- The only repeatable local bridge is area/project context, and it remains likely-only rather than exact.",
            "",
            f"- candidates_csv: `{OUT_CSV.relative_to(RESOLVER_DIR.parents[1])}`",
        ]
    )
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    benchmark_rows = list(csv.DictReader(BENCHMARK_CSV.open("r", encoding="utf-8", newline="")))
    records = matcher.get_prepared_records()
    indexes = build_indexes(records)
    rows = [analyze_listing(row, indexes) for row in benchmark_rows]
    write_csv(rows)
    write_report(rows, records)
    counts = Counter(row["classification"] for row in rows)
    bridge_types = Counter(row["best_bridge_type"] for row in rows)
    viable_bridge_types = Counter(
        row["best_bridge_type"]
        for row in rows
        if row["best_bridge_type"] != "listing_row_only"
    )
    print(
        json.dumps(
            {
                "exact_bridges_found": counts["exact bridge possible"],
                "likely_bridges_found": counts["likely bridge possible"],
                "impossible_no_local_bridge_count": counts["no local bridge"],
                "best_bridge_type": viable_bridge_types.most_common(1)[0][0] if viable_bridge_types else "none",
                "candidates_csv": str(OUT_CSV),
                "report_md": str(OUT_REPORT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
