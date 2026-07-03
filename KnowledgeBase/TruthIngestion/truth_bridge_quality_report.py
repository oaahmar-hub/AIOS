#!/usr/bin/env python3
"""Measure AIOS Truth Bridge quality."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

KB = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
RESOLVER_DIR = KB / "resolver"
TRUTH_DIR = KB / "TruthIngestion" / "outputs"
DB = RESOLVER_DIR / "unit_resolver_database.sqlite"
OUT_CSV = TRUTH_DIR / "truth_bridge_quality_rows.csv"
OUT_REPORT = TRUTH_DIR / "TRUTH_BRIDGE_QUALITY_REPORT.md"
OUT_JSON = TRUTH_DIR / "truth_bridge_quality_summary.json"
SOURCE_STATUS_CSV = TRUTH_DIR / "truth_ingestion_source_status.csv"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def low(value: object) -> str:
    return norm(value).lower()


def has_value(row: Dict[str, str], *fields: str) -> bool:
    return any(norm(row.get(field, "")) for field in fields)


def digits(value: object) -> str:
    return re.sub(r"\D", "", norm(value))


def classify_quality(row: Dict[str, str]) -> Tuple[str, int, str]:
    has_url = has_value(row, "listing_url")
    has_listing_ref = has_value(row, "listing_id", "broker_reference")
    has_public_ref = has_url or has_listing_ref
    has_direct_id = has_value(row, "permit_number", "property_number", "plot_number")
    has_building_unit = has_value(row, "building_name") and has_value(row, "unit_number")
    has_location = has_value(row, "community", "project_name", "building_name")
    has_resolver_link = has_value(row, "resolver_record_id")
    has_value_support = has_value(row, "size_clues", "price_clues")

    if row.get("bridge_classification") == "exact_bridge":
        return "Exact", 100, "ingestion-marked exact bridge"
    if has_resolver_link and (has_public_ref and (has_direct_id or has_building_unit)):
        return "Exact", 100, "resolver_link + public reference + hard identifier/building-unit"
    if has_resolver_link and (has_direct_id or has_building_unit or (has_public_ref and has_location)):
        return "High-confidence", 80, "resolver_link + strong identifier/location evidence"
    if has_public_ref and (has_direct_id or has_location or has_value_support):
        return "Partial", 55, "public reference with supporting clues but no exact resolver bridge"
    if has_public_ref or has_direct_id or has_building_unit or has_location:
        return "Weak", 25, "single clue family without trusted bridge completion"
    return "Unusable", 0, "no meaningful bridge relationship"


def load_rows() -> List[Dict[str, str]]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute("select * from bridge_records")]
    finally:
        con.close()


def load_source_notes() -> Dict[str, Dict[str, str]]:
    if not SOURCE_STATUS_CSV.exists():
        return {}
    with SOURCE_STATUS_CSV.open("r", encoding="utf-8", newline="") as handle:
        return {row["source"]: row for row in csv.DictReader(handle)}


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = load_rows()
    source_notes = load_source_notes()
    quality_rows: List[Dict[str, str]] = []
    counts = Counter()
    source_counts = defaultdict(Counter)

    for row in rows:
        quality, score, reason = classify_quality(row)
        counts[quality] += 1
        source = norm(row.get("source_file", "")) or "UNKNOWN_SOURCE"
        source_counts[source][quality] += 1
        quality_rows.append(
            {
                "bridge_id": row.get("bridge_id", ""),
                "source_file": source,
                "source_sheet": row.get("source_sheet", ""),
                "listing_url": row.get("listing_url", ""),
                "listing_id": row.get("listing_id", ""),
                "broker_reference": row.get("broker_reference", ""),
                "permit_number": row.get("permit_number", ""),
                "property_number": row.get("property_number", ""),
                "plot_number": row.get("plot_number", ""),
                "building_name": row.get("building_name", ""),
                "unit_number": row.get("unit_number", ""),
                "community": row.get("community", ""),
                "project_name": row.get("project_name", ""),
                "resolver_record_id": row.get("resolver_record_id", ""),
                "bridge_classification": row.get("bridge_classification", ""),
                "quality_class": quality,
                "quality_score": str(score),
                "quality_reason": reason,
            }
        )

    total = len(rows) or 1
    exact_pct = round(counts["Exact"] * 100 / total, 2)
    high_pct = round(counts["High-confidence"] * 100 / total, 2)
    partial_pct = round(counts["Partial"] * 100 / total, 2)
    weak_pct = round(counts["Weak"] * 100 / total, 2)
    unusable_pct = round(counts["Unusable"] * 100 / total, 2)
    quality_score = round(
        (
            counts["Exact"] * 100
            + counts["High-confidence"] * 80
            + counts["Partial"] * 55
            + counts["Weak"] * 25
        )
        / total,
        2,
    )

    opportunities = []
    for source, counter in sorted(source_counts.items()):
        partial_like = counter["Partial"] + counter["Weak"]
        exact_like = counter["Exact"] + counter["High-confidence"]
        if partial_like <= 0:
            continue
        notes = source_notes.get(source, {})
        opportunities.append(
            {
                "source": source,
                "exact_like": exact_like,
                "partial_like": partial_like,
                "partial_pressure": partial_like - exact_like,
                "notes": notes.get("notes", ""),
            }
        )
    opportunities.sort(key=lambda item: (item["partial_pressure"], item["partial_like"]), reverse=True)

    remaining_gaps = [
        "Public listing rows still rarely carry same-row unit number, property number, or permit number.",
        "Broker reference rows exist, but most are not yet linked to exact unit-bearing inventory records.",
        "Active Listings and Dubai_brokers contribute unit/building truth but weak public-bridge linkage.",
        "Bitrix24/raw sample and Runtime Memory Ledger did not contribute bridge-usable rows in current import.",
        "Only one public listing CPID is currently visible in PropertyGraph despite the higher bridge row count.",
    ]

    recommended_sources = [
        "BAYUT OVER ALL LEAD.xlsx: highest volume of URL/listing-id/broker-reference rows; needs same-row or linked permit/property/unit enrichment.",
        "Listings (1).xlsx and files with the same schema: currently the strongest exact bridge source.",
        "Secondary Listings LINKS EXCEL.xlsx joined with inventory/unit sheets: already has URLs and listing IDs, but lacks exact unit linkage.",
        "Active Listings.xlsx combined with portal export fields: has unit/building truth, but needs listing reference or permit linkage.",
        "CRM / Bitrix structured exports with broker reference, permit, property number, and unit in one row: highest-value missing bridge source.",
    ]

    write_csv(OUT_CSV, quality_rows)

    report_lines = [
        "# Truth Bridge Quality Report",
        "",
        f"- generated_at: `{now_iso()}`",
        f"- truth_bridge_quality_score: `{quality_score}/100`",
        f"- total_bridge_rows: `{len(rows)}`",
        "",
        "## Quality Distribution",
        "",
        f"- Exact: `{counts['Exact']}` ({exact_pct}%)",
        f"- High-confidence: `{counts['High-confidence']}` ({high_pct}%)",
        f"- Partial: `{counts['Partial']}` ({partial_pct}%)",
        f"- Weak: `{counts['Weak']}` ({weak_pct}%)",
        f"- Unusable: `{counts['Unusable']}` ({unusable_pct}%)",
        "",
        "## Highest-Value Improvement Sources",
        "",
    ]
    for item in recommended_sources:
        report_lines.append(f"- {item}")
    report_lines.extend(["", "## Remaining Data Gaps", ""])
    for gap in remaining_gaps:
        report_lines.append(f"- {gap}")
    report_lines.extend(["", "## Source Pressure", ""])
    for item in opportunities[:10]:
        report_lines.append(
            f"- `{item['source']}`: partial_like=`{item['partial_like']}`, exact_like=`{item['exact_like']}`, notes=`{item['notes']}`"
        )
    report_lines.extend(["", "## Evidence", "", f"- rows_csv: `{OUT_CSV}`", f"- summary_json: `{OUT_JSON}`"])
    OUT_REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    summary = {
        "generated_at": now_iso(),
        "truth_bridge_quality_score": quality_score,
        "total_bridge_rows": len(rows),
        "distribution": {
            "Exact": counts["Exact"],
            "High-confidence": counts["High-confidence"],
            "Partial": counts["Partial"],
            "Weak": counts["Weak"],
            "Unusable": counts["Unusable"],
        },
        "percentages": {
            "Exact": exact_pct,
            "High-confidence": high_pct,
            "Partial": partial_pct,
            "Weak": weak_pct,
            "Unusable": unusable_pct,
        },
        "remaining_data_gaps": remaining_gaps,
        "recommended_high_value_sources": recommended_sources,
        "evidence": {
            "rows_csv": str(OUT_CSV),
            "report_md": str(OUT_REPORT),
            "summary_json": str(OUT_JSON),
        },
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
