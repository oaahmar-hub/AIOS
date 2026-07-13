#!/usr/bin/env python3
"""Measure AIOS Truth Bridge Quality from the latest bridge master export."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESOLVER_DIR = ROOT / "KnowledgeBase" / "resolver"
PROPERTY_GRAPH_DIR = ROOT / "KnowledgeBase" / "PropertyGraph"
MASTER_CSV = PROPERTY_GRAPH_DIR / "listing_bridge_master.csv"
FALLBACK_CSV = RESOLVER_DIR / "bridge_records_export.csv"
REPORT_MD = RESOLVER_DIR / "TRUTH_BRIDGE_QUALITY_REPORT.md"
REPORT_JSON = RESOLVER_DIR / "TRUTH_BRIDGE_QUALITY_REPORT.json"

QUALITY_WEIGHTS = {
    "Exact": 1.00,
    "High-confidence": 0.75,
    "Partial": 0.45,
    "Weak": 0.15,
    "Unusable": 0.00,
}


@dataclass
class BridgeRow:
    source: str
    source_platform: str
    listing_url: str
    listing_id: str
    broker_reference: str
    permit_number: str
    property_number: str
    plot_number: str
    building: str
    unit: str
    cpid: str
    status: str
    confidence: str


def norm(value: object) -> str:
    return str(value or "").strip()


def load_rows() -> tuple[str, list[BridgeRow]]:
    if MASTER_CSV.exists():
        with MASTER_CSV.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = [
                BridgeRow(
                    source=norm(row.get("source")),
                    source_platform=norm(row.get("source_platform")),
                    listing_url=norm(row.get("listing_url")),
                    listing_id=norm(row.get("listing_id")),
                    broker_reference=norm(row.get("broker_reference")),
                    permit_number=norm(row.get("permit_number")),
                    property_number=norm(row.get("property_number")),
                    plot_number=norm(row.get("plot_number")),
                    building=norm(row.get("building")),
                    unit=norm(row.get("unit")),
                    cpid=norm(row.get("cpid")),
                    status=norm(row.get("bridge_status")),
                    confidence=norm(row.get("confidence")),
                )
                for row in reader
            ]
        return str(MASTER_CSV), rows

    with FALLBACK_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [
            BridgeRow(
                source=norm(row.get("source_file")),
                source_platform=norm(row.get("source_platform")),
                listing_url=norm(row.get("listing_url")),
                listing_id=norm(row.get("listing_id")),
                broker_reference=norm(row.get("broker_reference")),
                permit_number=norm(row.get("permit_number")),
                property_number=norm(row.get("property_number")),
                plot_number=norm(row.get("plot_number")),
                building=norm(row.get("building_name")),
                unit=norm(row.get("unit_number")),
                cpid=norm(row.get("canonical_property_id")),
                status=norm(row.get("bridge_classification")),
                confidence=norm(row.get("confidence")),
            )
            for row in reader
        ]
    return str(FALLBACK_CSV), rows


def is_real_building(value: str) -> bool:
    return bool(value and value != "-")


def has_public_ref(row: BridgeRow) -> bool:
    return bool(row.listing_url or row.listing_id or row.broker_reference)


def classify_quality(row: BridgeRow) -> str:
    status = row.status
    if status == "exact_bridge":
        return "Exact"
    if status == "partial_bridge":
        if row.listing_id and row.broker_reference and is_real_building(row.building) and row.cpid:
            return "High-confidence"
        return "Partial"
    if status in {"waiting_for_data", "candidate_bridge"}:
        return "Weak"
    if has_public_ref(row):
        return "Weak"
    return "Unusable"


def pct(count: int, total: int) -> float:
    return round((count / total * 100.0), 1) if total else 0.0


def relative_source(source_path: str) -> str:
    try:
        return str(Path(source_path).resolve().relative_to(ROOT))
    except ValueError:
        return source_path


def main() -> None:
    source_path, rows = load_rows()
    source_path = relative_source(source_path)
    generated_on = date.today().isoformat()
    total_rows = len(rows)
    bucket_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    gap_counts: Counter[str] = Counter()
    source_breakdown: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        quality = classify_quality(row)
        bucket_counts[quality] += 1
        status_counts[row.status] += 1
        source_breakdown[row.source][quality] += 1

        if quality == "High-confidence":
            gap_counts["missing_hard_property_identifier"] += 1
        elif quality == "Partial":
            gap_counts["missing_broker_or_building_anchor"] += 1
        elif quality == "Weak":
            gap_counts["missing_cpid_link_or_hard_identifier"] += 1
        elif quality == "Unusable":
            gap_counts["no_public_bridge_reference"] += 1

        if quality in {"Exact", "High-confidence", "Partial"} and not row.unit:
            gap_counts["missing_unit_number"] += 1

    public_candidate_rows = sum(1 for row in rows if has_public_ref(row))
    trusted_exact_pct_all = pct(bucket_counts["Exact"], total_rows)
    trusted_exact_pct_candidates = pct(bucket_counts["Exact"], public_candidate_rows)
    high_conf_pct_all = pct(bucket_counts["High-confidence"], total_rows)
    quality_score = round(
        sum(bucket_counts[bucket] * QUALITY_WEIGHTS[bucket] for bucket in QUALITY_WEIGHTS) / total_rows * 100.0,
        1,
    ) if total_rows else 0.0

    ranked_sources = []
    for source, counts in source_breakdown.items():
        uplift_score = counts["High-confidence"] * 1.0 + counts["Partial"] * 0.5 + counts["Weak"] * 0.7
        ranked_sources.append(
            {
                "source": source,
                "exact": counts["Exact"],
                "high_confidence": counts["High-confidence"],
                "partial": counts["Partial"],
                "weak": counts["Weak"],
                "unusable": counts["Unusable"],
                "uplift_score": round(uplift_score, 1),
            }
        )
    ranked_sources.sort(key=lambda item: (item["uplift_score"], item["exact"]), reverse=True)

    result = {
        "generated_on": generated_on,
        "source_csv": source_path,
        "total_bridge_rows": total_rows,
        "public_reference_rows": public_candidate_rows,
        "quality_buckets": {
            bucket: {
                "count": bucket_counts[bucket],
                "percentage_of_all_rows": pct(bucket_counts[bucket], total_rows),
            }
            for bucket in ["Exact", "High-confidence", "Partial", "Weak", "Unusable"]
        },
        "status_counts": dict(status_counts),
        "truth_bridge_quality_score": quality_score,
        "exact_bridge_percentage": trusted_exact_pct_all,
        "exact_bridge_percentage_public_reference_rows": trusted_exact_pct_candidates,
        "high_confidence_percentage": high_conf_pct_all,
        "remaining_data_gaps": [
            {"gap": gap, "count": count}
            for gap, count in gap_counts.most_common()
        ],
        "recommended_highest_value_sources": ranked_sources[:5],
        "method": {
            "Exact": "exact_bridge rows with public reference and hard property identifier already attached.",
            "High-confidence": "partial_bridge rows with listing_id + broker_reference + building + CPID but still missing hard property identifier.",
            "Partial": "partial_bridge rows with public reference and some property context, but without enough anchors to trust exact closure.",
            "Weak": "waiting_for_data or candidate rows that have a public trace but do not yet have a trusted bridge.",
            "Unusable": "rows without a usable public bridge reference.",
        },
    }

    REPORT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    top_sources_lines = []
    for item in ranked_sources[:5]:
        top_sources_lines.append(
            f"- `{item['source']}`: uplift `{item['uplift_score']}`, "
            f"Exact `{item['exact']}`, High-confidence `{item['high_confidence']}`, "
            f"Partial `{item['partial']}`, Weak `{item['weak']}`, Unusable `{item['unusable']}`"
        )

    gap_lines = [
        f"- `{gap['gap']}`: `{gap['count']}`"
        for gap in result["remaining_data_gaps"]
    ]

    bucket_lines = [
        f"- `{bucket}`: `{result['quality_buckets'][bucket]['count']}` rows "
        f"({result['quality_buckets'][bucket]['percentage_of_all_rows']}%)"
        for bucket in ["Exact", "High-confidence", "Partial", "Weak", "Unusable"]
    ]

    md = "\n".join(
        [
            "# Truth Bridge Quality Report",
            "",
            f"Date: {generated_on}",
            f"Source CSV: `{source_path}`",
            "",
            "## Architecture Terminology",
            "",
            "1. Truth Acquisition",
            "2. Truth Ingestion",
            "3. Truth Bridge",
            "4. Resolver",
            "5. Unit Finder",
            "6. Property Intelligence",
            "",
            "## Summary",
            "",
            f"- Truth Bridge Quality score: `{quality_score}/100`",
            f"- Exact bridge percentage: `{trusted_exact_pct_all}%` of all bridge rows",
            f"- Exact bridge percentage on rows with a public reference: `{trusted_exact_pct_candidates}%`",
            f"- High-confidence percentage: `{high_conf_pct_all}%` of all bridge rows",
            f"- Total bridge rows audited: `{total_rows}`",
            f"- Public-reference bridge rows: `{public_candidate_rows}`",
            "",
            "## Quality Buckets",
            "",
            *bucket_lines,
            "",
            "## Remaining Data Gaps",
            "",
            *gap_lines,
            "",
            "## Highest-Value Source Uplift",
            "",
            *top_sources_lines,
            "",
            "## Reading",
            "",
            "- The bridge problem is now quality and completeness, not missing bridge infrastructure.",
            "- Exact closure remains small because hard property identifiers are sparse across the largest imported listing feeds.",
            "- The fastest exact-bridge gain is to enrich the strongest High-confidence rows with permit, property, or plot identifiers rather than adding more weak rows.",
        ]
    )
    REPORT_MD.write_text(md + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
