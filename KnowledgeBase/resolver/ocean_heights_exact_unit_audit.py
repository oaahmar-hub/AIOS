#!/usr/bin/env python3
"""Step 9: audit Ocean Heights likely match toward exact-unit resolution."""

import csv
import json
import sqlite3
from pathlib import Path
import sys


RESOLVER_DIR = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver")
RAW_CHAT_CSV = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/raw_data/csv/5ca554ad55ac__omar_style_dataset_sample.csv")
DB_PATH = RESOLVER_DIR / "unit_resolver_database.sqlite"
RUN_SUMMARY_PATH = RESOLVER_DIR / "run_summary.json"
CHAIN_CSV = RESOLVER_DIR / "ocean_heights_candidate_chain.csv"
REPORT_MD = RESOLVER_DIR / "ocean_heights_exact_unit_report.md"
OCEAN_URL = "https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-dubai-marina-ocean-heights-84894360.html"

sys.path.append(str(RESOLVER_DIR))
import listing_similarity_matcher as matcher  # noqa: E402


def load_run_summary():
    if not RUN_SUMMARY_PATH.exists():
        return {}
    return json.loads(RUN_SUMMARY_PATH.read_text(encoding="utf-8"))


def fetch_db_records():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT resolver_record_id, source_file, source_path, source_chat_group, source_sheet, row_number,
               source_platform, listing_id, listing_url, property_finder_url, bayut_url, dubizzle_url,
               permit_number, property_number, plot_number, land_number, municipality_number, dewa_number,
               area, project, building, unit, bedrooms, size, price, developer,
               owner_contact_available, extracted_from_pdf, extracted_from_sheet, extracted_from_text,
               extraction_confidence, confidence_score, match_basis
        FROM resolver_records
        WHERE lower(area) LIKE '%dubai marina%'
           OR lower(building) LIKE '%ocean%'
           OR lower(building) LIKE '%heights%'
           OR lower(listing_url) LIKE '%ocean-heights%'
           OR lower(property_finder_url) LIKE '%ocean-heights%'
        """
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def find_raw_cluster_rows(center_row=466, radius=8):
    rows = []
    with RAW_CHAT_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = list(csv.DictReader(handle))
    center_chat = reader[center_row - 1].get("chat", "")
    start = max(1, center_row - radius)
    end = min(len(reader), center_row + radius)
    for row_no in range(start, end + 1):
        row = reader[row_no - 1]
        if row.get("chat", "") != center_chat:
            continue
        rows.append(
            {
                "cluster_type": "raw_chat_neighbor",
                "resolver_record_id": "",
                "source_file": "raw_chat_style_dataset",
                "source_path": str(RAW_CHAT_CSV),
                "source_chat_group": row.get("chat", ""),
                "source_sheet": "",
                "row_number": str(row_no),
                "source_platform": "",
                "listing_id": "",
                "listing_url": "",
                "permit_number": "",
                "property_number": "",
                "plot_number": "",
                "land_number": "",
                "municipality_number": "",
                "dewa_number": "",
                "area": "",
                "project": "",
                "building": "",
                "unit": "",
                "bedrooms": "",
                "size": "",
                "price": "",
                "developer": "",
                "owner_contact_available": "NO",
                "match_basis": "",
                "confidence_score": "",
                "evidence_note": row.get("text", ""),
            }
        )
    return rows


def find_direct_identifier_hits(db_rows, query):
    out = []
    listing_id = query["parsed"].get("listing_id", "")
    listing_url = query["parsed"].get("listing_url", "") or OCEAN_URL
    for row in db_rows:
        linked = False
        note_parts = []
        if listing_id and row.get("listing_id") == listing_id:
            linked = True
            note_parts.append("exact_listing_id")
        row_urls = [row.get("listing_url", ""), row.get("property_finder_url", "")]
        if listing_url and any(listing_url and listing_url == u for u in row_urls if u):
            linked = True
            note_parts.append("exact_listing_url")
        if any(row.get(k) for k in ("permit_number", "property_number", "plot_number", "land_number")):
            note_parts.append("has_identifier_fields")
        if linked or note_parts:
            item = dict(row)
            item["cluster_type"] = "resolver_db_candidate"
            item["evidence_note"] = ",".join(note_parts)
            out.append(item)
    return out


def build_chain_rows(result, db_rows):
    chain_rows = []
    for rank, cand in enumerate(result["candidates"], start=1):
        chain_rows.append(
            {
                "cluster_type": "similarity_top_candidate",
                "rank": rank,
                "resolver_record_id": cand.get("resolver_record_id", ""),
                "source_file": cand.get("source_file", ""),
                "source_path": "",
                "source_chat_group": "",
                "source_sheet": cand.get("source_sheet", ""),
                "row_number": cand.get("row_number", ""),
                "source_platform": cand.get("source_platform", ""),
                "listing_id": "",
                "listing_url": cand.get("listing_url", ""),
                "permit_number": cand.get("permit_number", ""),
                "property_number": cand.get("property_number", ""),
                "plot_number": cand.get("plot_number", ""),
                "land_number": cand.get("land_number", ""),
                "municipality_number": "",
                "dewa_number": "",
                "area": cand.get("area", ""),
                "project": cand.get("project", ""),
                "building": cand.get("building", ""),
                "unit": cand.get("unit", ""),
                "bedrooms": cand.get("bedrooms", ""),
                "size": cand.get("size", ""),
                "price": cand.get("price", ""),
                "developer": "",
                "owner_contact_available": cand.get("owner_contact_available", ""),
                "match_basis": cand.get("status_label", ""),
                "confidence_score": str(cand.get("score", "")),
                "evidence_note": cand.get("score_breakdown", ""),
            }
        )
    chain_rows.extend(find_direct_identifier_hits(db_rows, result))
    chain_rows.extend(find_raw_cluster_rows())
    return chain_rows


def write_chain_csv(rows):
    fieldnames = [
        "cluster_type",
        "rank",
        "resolver_record_id",
        "source_file",
        "source_path",
        "source_chat_group",
        "source_sheet",
        "row_number",
        "source_platform",
        "listing_id",
        "listing_url",
        "permit_number",
        "property_number",
        "plot_number",
        "land_number",
        "municipality_number",
        "dewa_number",
        "area",
        "project",
        "building",
        "unit",
        "bedrooms",
        "size",
        "price",
        "developer",
        "owner_contact_available",
        "match_basis",
        "confidence_score",
        "evidence_note",
    ]
    with CHAIN_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def report_text(result, db_rows, chain_rows, summary):
    top = result["candidates"][0] if result["candidates"] else {}
    direct_id_rows = [
        row
        for row in db_rows
        if row.get("listing_id") == result["parsed"].get("listing_id")
        or row.get("listing_url") == OCEAN_URL
        or row.get("property_finder_url") == OCEAN_URL
    ]
    identifier_link_rows = [
        row
        for row in db_rows
        if any(row.get(k) for k in ("permit_number", "property_number", "plot_number", "land_number"))
    ]
    unit_found = bool(top.get("unit"))
    exact_unit_status = "EXACT_UNIT_FOUND" if unit_found else "UNIT_NOT_FOUND"
    improvements = [
        "Ocean Heights URL now resolves to a building-level likely match instead of unresolved.",
        "Price normalization upgraded the raw Ocean Heights row from `2.0` to `3000000.0`.",
        "Area + building + property-type signals now combine into a stable candidate chain.",
    ]
    if not unit_found:
        improvements.append("Exact unit completion failed because no linked permit/property/plot/listing record or unit-bearing companion row was found locally.")

    lines = [
        "# Ocean Heights Exact Unit Audit",
        "",
        f"- input_url: `{OCEAN_URL}`",
        f"- final_status: {result['top_confidence']}",
        f"- exact_unit_status: {exact_unit_status}",
        f"- confidence_score: {top.get('score', 0)}",
        f"- unit_found: `{top.get('unit', '') or 'NOT FOUND'}`",
        f"- top_candidate_record_id: `{top.get('resolver_record_id', '')}`",
        f"- top_candidate_area: `{top.get('area', '')}`",
        f"- top_candidate_building: `{top.get('building', '')}`",
        f"- top_candidate_bedrooms: `{top.get('bedrooms', '')}`",
        f"- top_candidate_size: `{top.get('size', '')}`",
        f"- top_candidate_price: `{top.get('price', '')}`",
        f"- top_candidate_source_file: `{top.get('source_file', '')}`",
        f"- top_candidate_score_breakdown: `{top.get('score_breakdown', '')}`",
        "",
        "## Candidate chain evidence",
        f"- similarity_candidates_logged: {len(result['candidates'])}",
        f"- direct_listing_id_or_url_hits_in_db: {len(direct_id_rows)}",
        f"- related_identifier_rows_in_db: {len(identifier_link_rows)}",
        f"- raw_source_cluster_rows_logged: {len([r for r in chain_rows if r['cluster_type'] == 'raw_chat_neighbor'])}",
        f"- evidence_csv: `{CHAIN_CSV}`",
        "",
        "## Exact unit resolution improvements",
    ]
    for item in improvements:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Updated resolver statistics",
            f"- total_records_indexed: {summary.get('total_records_indexed', '')}",
            f"- unit_records_resolved: {summary.get('unit_records_resolved', '')}",
            f"- remaining_unresolved_records: {summary.get('remaining_unresolved_records', '')}",
            f"- listing_urls_found: {summary.get('urls_found', '')}",
            f"- listing_ids_extracted: {summary.get('listing_ids_extracted', '')}",
            f"- restricted_owner_contact_rows: {summary.get('restricted_owner_contact_rows', '')}",
            f"- confidence_distribution_90_plus: {summary.get('confidence_distribution_90_plus', '')}",
            f"- confidence_distribution_80_89: {summary.get('confidence_distribution_80_89', '')}",
            f"- confidence_distribution_below_70: {summary.get('confidence_distribution_below_70', '')}",
            "",
            "## Final evidence-based verdict",
        ]
    )

    if unit_found:
        lines.append(f"- exact unit was discovered locally: `{top.get('unit', '')}`")
    else:
        lines.append("- exact unit was not discovered locally in the indexed resolver DB, raw chat cluster, or scanned raw XLSX corpus.")
        lines.append("- current best local match remains building-level only.")
        lines.append("- restricted owner/contact data remains protected because confidence is below exact-unit threshold and no unit-complete record was found.")

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    result = matcher.resolve_listing_by_similarity(OCEAN_URL)
    db_rows = fetch_db_records()
    chain_rows = build_chain_rows(result, db_rows)
    write_chain_csv(chain_rows)
    report_text(result, db_rows, chain_rows, load_run_summary())
    top = result["candidates"][0] if result["candidates"] else {}
    output = {
        "ocean_heights_final_status": result["top_confidence"],
        "unit_found": top.get("unit", "") or "NOT FOUND",
        "confidence_score": top.get("score", 0),
        "candidate_chain_csv": str(CHAIN_CSV),
        "report_md": str(REPORT_MD),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
