#!/usr/bin/env python3
"""Step 15: same-unit clustering across listing, WhatsApp, and unit records."""

import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from difflib import SequenceMatcher


RESOLVER_DIR = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver")
OUT_CSV = RESOLVER_DIR / "same_unit_clusters.csv"
OUT_JSON = RESOLVER_DIR / "same_unit_clusters.json"
OUT_REPORT = RESOLVER_DIR / "same_unit_cluster_report.md"

sys.path.append(str(RESOLVER_DIR))
import listing_similarity_matcher as matcher  # noqa: E402


CLUSTER_CONFIDENCE = {
    "SAME_UNIT_EXACT": 95,
    "SAME_UNIT_LIKELY": 82,
    "SAME_UNIT_POSSIBLE": 68,
    "BUILDING_ONLY": 40,
}


def normalize_owner_flag(value):
    return "NO" if matcher.low(value) in {"", "no"} else "YES"


def parse_numeric(value):
    if value in ("", None):
        return ""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
    if not m:
        return ""
    try:
        return float(m.group(1))
    except Exception:
        return ""


def parse_size_sqm(record):
    if record.get("canonical_size_sqm") not in ("", None):
        try:
            return float(record["canonical_size_sqm"])
        except Exception:
            pass
    size = record.get("size", "")
    parsed = matcher.parse_size_value(size)
    if parsed not in ("", None):
        return float(parsed)
    numeric = parse_numeric(size)
    if numeric not in ("", None):
        if numeric > 1000:
            return round(float(numeric) * 0.092903, 2)
        return float(numeric)
    return ""


def parse_price_value(record):
    if record.get("canonical_price") not in ("", None):
        try:
            return float(record["canonical_price"])
        except Exception:
            pass
    price = record.get("price", "")
    parsed = matcher.parse_price_value(price)
    if parsed not in ("", None):
        return float(parsed)
    numeric = parse_numeric(price)
    return float(numeric) if numeric not in ("", None) else ""


def canonical_entity(record):
    building = matcher.canonical_building(record.get("building", ""))
    if building:
        return "building", building
    project = matcher.canonical_project(record.get("project", ""))
    if project:
        return "project", project
    return "", ""


def record_text(record):
    return matcher._clean_similarity_text(
        " ".join(
            filter(
                None,
                [
                    record.get("slug_title_tokens", ""),
                    record.get("project_building_tokens", ""),
                    record.get("area_tokens", ""),
                    record.get("area", ""),
                    record.get("project", ""),
                    record.get("building", ""),
                    record.get("status_tokens", ""),
                    record.get("source_file", ""),
                ],
            )
        )
    )


def text_similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def pct_diff(a, b):
    if a in ("", None) or b in ("", None):
        return None
    if float(a) == 0:
        return None
    return abs(float(a) - float(b)) / float(a)


def prepare_records():
    raw_records = matcher.get_prepared_records()
    prepared = []
    for idx, record in enumerate(raw_records):
        area = matcher.canonical_area(record.get("area", ""))
        entity_type, entity_value = canonical_entity(record)
        prepared.append(
            {
                "idx": idx,
                "resolver_record_id": record.get("resolver_record_id", ""),
                "source_platform": record.get("source_platform", ""),
                "source_file": record.get("source_file", ""),
                "source_path": record.get("source_path", ""),
                "source_chat_group": record.get("source_chat_group", ""),
                "source_sheet": record.get("source_sheet", ""),
                "row_number": record.get("row_number", ""),
                "listing_url": record.get("listing_url", ""),
                "listing_id": record.get("listing_id", ""),
                "area": area,
                "project": matcher.canonical_project(record.get("project", "")),
                "building": matcher.canonical_building(record.get("building", "")),
                "entity_type": entity_type,
                "entity_value": entity_value,
                "unit": matcher.normalize_unit(record.get("unit", "")),
                "bedrooms": matcher.canonical_bedrooms(record.get("bedrooms", "")),
                "bathrooms": matcher.canonical_bedrooms(record.get("bathrooms", "")),
                "size_sqm": parse_size_sqm(record),
                "price_value": parse_price_value(record),
                "status_tokens": sorted(set((record.get("status_tokens", "") or "").split())),
                "text": record_text(record),
                "owner_contact_available": normalize_owner_flag(record.get("owner_contact_available", "")),
                "restricted_ref": record.get("restricted_ref", ""),
            }
        )
    return prepared


def records_match_likely(a, b):
    if not (a["area"] and b["area"] and a["area"] == b["area"]):
        return False
    if not (a["entity_value"] and b["entity_value"] and a["entity_value"] == b["entity_value"]):
        return False
    if not (a["bedrooms"] and b["bedrooms"] and a["bedrooms"] == b["bedrooms"]):
        return False
    size_diff = pct_diff(a["size_sqm"], b["size_sqm"])
    price_diff = pct_diff(a["price_value"], b["price_value"])
    return size_diff is not None and price_diff is not None and size_diff <= 0.03 and price_diff <= 0.05


def records_match_possible(a, b):
    if not (a["area"] and b["area"] and a["area"] == b["area"]):
        return False
    if not (a["entity_value"] and b["entity_value"] and a["entity_value"] == b["entity_value"]):
        return False
    if not (a["bedrooms"] and b["bedrooms"] and a["bedrooms"] == b["bedrooms"]):
        return False
    size_diff = pct_diff(a["size_sqm"], b["size_sqm"])
    if size_diff is None or size_diff > 0.08:
        return False
    return text_similarity(a["text"], b["text"]) >= 0.45


def create_cluster(cluster_id, classification, members):
    source_platforms = sorted({m["source_platform"] for m in members if m["source_platform"]})
    source_files = sorted({m["source_file"] for m in members if m["source_file"]})
    units = sorted({m["unit"] for m in members if m["unit"]})
    bedrooms = sorted({m["bedrooms"] for m in members if m["bedrooms"]})
    sizes = [float(m["size_sqm"]) for m in members if m["size_sqm"] not in ("", None)]
    prices = [float(m["price_value"]) for m in members if m["price_value"] not in ("", None)]
    restricted_refs = sorted({m["restricted_ref"] for m in members if m["restricted_ref"]})
    owner_flag = "YES" if any(m["owner_contact_available"] == "YES" for m in members) else "NO"
    area = next((m["area"] for m in members if m["area"]), "")
    building = next((m["building"] for m in members if m["building"]), "")
    project = next((m["project"] for m in members if m["project"]), "")
    return {
        "cluster_id": cluster_id,
        "classification": classification,
        "canonical_area": area,
        "canonical_building_project": building or project,
        "possible_unit_number": units[0] if len(units) == 1 else ("|".join(units[:5]) if units else ""),
        "bedrooms": "|".join(bedrooms[:5]),
        "size_range_sqm": f"{min(sizes):.2f}-{max(sizes):.2f}" if sizes else "",
        "price_range": f"{min(prices):.0f}-{max(prices):.0f}" if prices else "",
        "source_platforms": "|".join(source_platforms),
        "source_files": "|".join(source_files[:10]),
        "record_count": len(members),
        "confidence": CLUSTER_CONFIDENCE[classification],
        "owner_contact_available": owner_flag,
        "restricted_owner_contact_link": "|".join(restricted_refs[:10]),
        "members": members,
    }


def build_clusters(records):
    assigned = set()
    clusters = []
    cluster_num = 1

    exact_groups = defaultdict(list)
    for record in records:
        if record["area"] and record["entity_value"] and record["unit"]:
            exact_groups[(record["area"], record["entity_value"], record["unit"])].append(record)

    for key, members in exact_groups.items():
        for member in members:
            assigned.add(member["idx"])
        clusters.append(create_cluster(f"cluster_{cluster_num:05d}", "SAME_UNIT_EXACT", members))
        cluster_num += 1

    residual = [r for r in records if r["idx"] not in assigned and r["area"] and r["entity_value"]]
    grouped = defaultdict(list)
    for record in residual:
        grouped[(record["area"], record["entity_value"], record["bedrooms"])].append(record)

    used = set()
    for group_records in grouped.values():
        for seed in group_records:
            if seed["idx"] in used or seed["size_sqm"] in ("", None) or seed["price_value"] in ("", None) or not seed["bedrooms"]:
                continue
            cluster = [seed]
            for other in group_records:
                if other["idx"] == seed["idx"] or other["idx"] in used:
                    continue
                if records_match_likely(seed, other):
                    cluster.append(other)
            if len(cluster) >= 2:
                for member in cluster:
                    used.add(member["idx"])
                    assigned.add(member["idx"])
                clusters.append(create_cluster(f"cluster_{cluster_num:05d}", "SAME_UNIT_LIKELY", cluster))
                cluster_num += 1

    residual = [r for r in records if r["idx"] not in assigned and r["area"] and r["entity_value"]]
    grouped = defaultdict(list)
    for record in residual:
        grouped[(record["area"], record["entity_value"], record["bedrooms"])].append(record)

    used = set()
    for group_records in grouped.values():
        for seed in group_records:
            if seed["idx"] in used or seed["size_sqm"] in ("", None) or not seed["bedrooms"]:
                continue
            cluster = [seed]
            for other in group_records:
                if other["idx"] == seed["idx"] or other["idx"] in used:
                    continue
                if records_match_possible(seed, other):
                    cluster.append(other)
            if len(cluster) >= 2:
                for member in cluster:
                    used.add(member["idx"])
                    assigned.add(member["idx"])
                clusters.append(create_cluster(f"cluster_{cluster_num:05d}", "SAME_UNIT_POSSIBLE", cluster))
                cluster_num += 1

    building_only_groups = defaultdict(list)
    for record in records:
        if record["idx"] in assigned or not (record["area"] and record["entity_value"]):
            continue
        building_only_groups[(record["area"], record["entity_value"])].append(record)

    for members in building_only_groups.values():
        for member in members:
            assigned.add(member["idx"])
        clusters.append(create_cluster(f"cluster_{cluster_num:05d}", "BUILDING_ONLY", members))
        cluster_num += 1

    return clusters


def index_clusters(clusters):
    by_area_entity = defaultdict(list)
    by_exact_unit = defaultdict(list)
    for cluster in clusters:
        area = matcher.canonical_area(cluster["canonical_area"])
        entity = matcher.canonical_building(cluster["canonical_building_project"]) or matcher.canonical_project(cluster["canonical_building_project"])
        by_area_entity[(area, entity)].append(cluster)
        if cluster["possible_unit_number"]:
            by_exact_unit[(area, entity, cluster["possible_unit_number"].split("|")[0])] .append(cluster)
    return by_area_entity, by_exact_unit


def query_to_record(input_text):
    query = matcher.parse_input_text(input_text)
    entity_type, entity_value = canonical_entity(query)
    return {
        "area": matcher.canonical_area(query.get("area", "")),
        "project": matcher.canonical_project(query.get("project", "")),
        "building": matcher.canonical_building(query.get("building", "")),
        "entity_type": entity_type,
        "entity_value": entity_value,
        "unit": matcher.normalize_unit(query.get("unit", "")),
        "bedrooms": matcher.canonical_bedrooms(query.get("bedrooms", "")),
        "size_sqm": matcher.parse_size_value(query.get("size", "")),
        "price_value": matcher.parse_price_value(query.get("price", "")),
        "status_tokens": sorted(set((query.get("status_tokens", "") or "").split())),
        "text": matcher._clean_similarity_text(input_text),
    }


def match_query_to_cluster(query_text, clusters):
    query = query_to_record(query_text)
    best = None
    best_score = -1
    for cluster in clusters:
        score = 0
        if query["area"] and matcher.canonical_area(cluster["canonical_area"]) == query["area"]:
            score += 20
        entity = matcher.canonical_building(cluster["canonical_building_project"]) or matcher.canonical_project(cluster["canonical_building_project"])
        if query["entity_value"] and entity == query["entity_value"]:
            score += 25
        if query["unit"] and cluster["possible_unit_number"] and query["unit"] in cluster["possible_unit_number"].split("|"):
            score += 45
        cluster_bedrooms = cluster["bedrooms"].split("|")[0] if cluster["bedrooms"] else ""
        if query["bedrooms"] and cluster_bedrooms and query["bedrooms"] == cluster_bedrooms:
            score += 10
        if query["size_sqm"] not in ("", None) and cluster["size_range_sqm"]:
            low_s, high_s = [float(x) for x in cluster["size_range_sqm"].split("-")]
            if low_s <= float(query["size_sqm"]) <= high_s:
                score += 15
            else:
                midpoint = (low_s + high_s) / 2
                diff = pct_diff(float(query["size_sqm"]), midpoint)
                if diff is not None and diff <= 0.05:
                    score += 8
        if query["price_value"] not in ("", None) and cluster["price_range"]:
            low_p, high_p = [float(x) for x in cluster["price_range"].split("-")]
            midpoint = (low_p + high_p) / 2
            diff = pct_diff(float(query["price_value"]), midpoint)
            if diff is not None and diff <= 0.05:
                score += 10
        sample_text = " ".join(member["text"] for member in cluster["members"][:3])
        if query["text"] and sample_text and text_similarity(query["text"], sample_text) >= 0.45:
            score += 6

        if score > best_score:
            best_score = score
            best = cluster

    classification = "UNRESOLVED"
    if best:
        if best["classification"] == "SAME_UNIT_EXACT" and best_score >= 70:
            classification = "SAME_UNIT_EXACT"
        elif best["classification"] == "SAME_UNIT_LIKELY" and best_score >= 55:
            classification = "SAME_UNIT_LIKELY"
        elif best["classification"] == "SAME_UNIT_POSSIBLE" and best_score >= 45:
            classification = "SAME_UNIT_POSSIBLE"
        elif best_score >= 35:
            classification = "BUILDING_ONLY"
    return {
        "query": query_text,
        "best_cluster": best["cluster_id"] if best else "",
        "cluster_classification": classification,
        "canonical_area": best["canonical_area"] if best else "",
        "canonical_building_project": best["canonical_building_project"] if best else "",
        "possible_unit_number": best["possible_unit_number"] if best else "",
        "confidence": best["confidence"] if best else 0,
        "record_count": best["record_count"] if best else 0,
        "owner_contact_available": best["owner_contact_available"] if best else "NO",
    }


def pick_random_records(records, predicate, count, seed):
    rng = random.Random(seed)
    pool = [record for record in records if predicate(record)]
    if len(pool) <= count:
        return pool
    return rng.sample(pool, count)


def build_test_queries(records):
    queries = [
        "Ocean Heights / Dubai Marina / 2BR / 1565 sqft / AED 2.2M / furnished / upgraded",
        "Ocean Heights / Dubai Marina / 2BR / 1600 sqft / AED 3M / refurbished / vacant",
    ]
    permit_row = next((r for r in records if r.get("permit_number")), None)
    property_row = next((r for r in records if r.get("property_number")), None)
    plot_row = next((r for r in records if r.get("plot_number") or r.get("land_number")), None)
    unit_row = next((r for r in records if r.get("unit") and (r.get("building") or r.get("project"))), None)
    project_row = next((r for r in records if r.get("area") and r.get("project")), None)
    noisy_row = next((r for r in records if r.get("text")), None)
    incomplete_row = next((r for r in records if r.get("area") and (r.get("building") or r.get("project"))), None)
    for row in [permit_row, property_row, plot_row]:
        if row:
            val = row.get("permit_number") or row.get("property_number") or row.get("plot_number") or row.get("land_number")
            queries.append(str(val))
    if unit_row:
        queries.append(f"{unit_row.get('unit')} {unit_row.get('building') or unit_row.get('project')}")
    if project_row:
        queries.append(f"{project_row.get('area')} {project_row.get('project')}")
    if noisy_row:
        queries.append(noisy_row.get("text", "")[:220])
    queries.append("broker reference 1038401677055")
    if incomplete_row:
        queries.append(f"{incomplete_row.get('area')} {incomplete_row.get('bedrooms')} bed")
    return queries[:10]


def write_outputs(clusters, tests, records):
    fieldnames = [
        "cluster_id",
        "classification",
        "canonical_area",
        "canonical_building_project",
        "possible_unit_number",
        "bedrooms",
        "size_range_sqm",
        "price_range",
        "source_platforms",
        "source_files",
        "record_count",
        "confidence",
        "owner_contact_available",
        "restricted_owner_contact_link",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for cluster in clusters:
            writer.writerow({key: cluster[key] for key in fieldnames})

    json_clusters = []
    for cluster in clusters:
        item = {key: cluster[key] for key in fieldnames}
        item["member_records"] = [
            {
                "resolver_record_id": member["resolver_record_id"],
                "source_platform": member["source_platform"],
                "source_file": member["source_file"],
                "source_chat_group": member["source_chat_group"],
                "area": member["area"],
                "project": member["project"],
                "building": member["building"],
                "unit": member["unit"],
                "bedrooms": member["bedrooms"],
                "size_sqm": member["size_sqm"],
                "price_value": member["price_value"],
                "owner_contact_available": member["owner_contact_available"],
                "restricted_ref": member["restricted_ref"],
            }
            for member in cluster["members"][:50]
        ]
        json_clusters.append(item)
    OUT_JSON.write_text(json.dumps(json_clusters, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = Counter(cluster["classification"] for cluster in clusters)
    url_joined = sum(
        1
        for cluster in clusters
        if cluster["classification"] in {"SAME_UNIT_EXACT", "SAME_UNIT_LIKELY", "SAME_UNIT_POSSIBLE"}
        for member in cluster["members"]
        if member["listing_url"]
    )
    restricted_clusters = sum(1 for cluster in clusters if cluster["owner_contact_available"] == "YES")
    ocean_test = tests[0]
    strongest_input = Counter(test["cluster_classification"] for test in tests).most_common(1)[0][0] if tests else ""
    weakest_input = "UNRESOLVED" if any(test["cluster_classification"] == "UNRESOLVED" for test in tests) else "BUILDING_ONLY"

    lines = [
        "# Same Unit Cluster Report",
        "",
        f"- total_clusters_created: {len(clusters)}",
        f"- SAME_UNIT_EXACT count: {counts['SAME_UNIT_EXACT']}",
        f"- SAME_UNIT_LIKELY count: {counts['SAME_UNIT_LIKELY']}",
        f"- SAME_UNIT_POSSIBLE count: {counts['SAME_UNIT_POSSIBLE']}",
        f"- BUILDING_ONLY count: {counts['BUILDING_ONLY']}",
        f"- url_records_joined_same_unit_cluster: {url_joined}",
        f"- clusters_with_restricted_owner_contact_available: {restricted_clusters}",
        "",
        "## Ocean Heights cluster result",
        f"- query: `{ocean_test['query']}`",
        f"- cluster_id: `{ocean_test['best_cluster']}`",
        f"- classification: `{ocean_test['cluster_classification']}`",
        f"- area: `{ocean_test['canonical_area']}`",
        f"- building/project: `{ocean_test['canonical_building_project']}`",
        f"- possible_unit_number: `{ocean_test['possible_unit_number'] or 'NOT FOUND'}`",
        f"- confidence: `{ocean_test['confidence']}`",
        "",
        "## Test summary",
        f"- strongest_successful_input_type: `{strongest_input}`",
        f"- weakest_input_type: `{weakest_input}`",
    ]

    for test in tests:
        lines.append(
            f"- `{test['query']}` -> {test['cluster_classification']} | cluster={test['best_cluster']} | area={test['canonical_area']} | building/project={test['canonical_building_project']} | unit={test['possible_unit_number'] or 'NOT FOUND'}"
        )

    lines.extend(
        [
            "",
            f"- clusters_csv: `{OUT_CSV}`",
            f"- clusters_json: `{OUT_JSON}`",
        ]
    )
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    records = prepare_records()
    clusters = build_clusters(records)
    test_queries = build_test_queries(records)
    tests = [match_query_to_cluster(query, clusters) for query in test_queries]
    write_outputs(clusters, tests, records)
    counts = Counter(cluster["classification"] for cluster in clusters)
    url_joined = sum(
        1
        for cluster in clusters
        if cluster["classification"] in {"SAME_UNIT_EXACT", "SAME_UNIT_LIKELY", "SAME_UNIT_POSSIBLE"}
        for member in cluster["members"]
        if member["listing_url"]
    )
    restricted_clusters = sum(1 for cluster in clusters if cluster["owner_contact_available"] == "YES")
    print(
        json.dumps(
            {
                "total_clusters_created": len(clusters),
                "SAME_UNIT_EXACT_count": counts["SAME_UNIT_EXACT"],
                "SAME_UNIT_LIKELY_count": counts["SAME_UNIT_LIKELY"],
                "SAME_UNIT_POSSIBLE_count": counts["SAME_UNIT_POSSIBLE"],
                "BUILDING_ONLY_count": counts["BUILDING_ONLY"],
                "ocean_heights_cluster_result": tests[0],
                "url_records_joined_same_unit_cluster": url_joined,
                "clusters_with_restricted_owner_contact_available": restricted_clusters,
                "csv": str(OUT_CSV),
                "json": str(OUT_JSON),
                "report": str(OUT_REPORT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
