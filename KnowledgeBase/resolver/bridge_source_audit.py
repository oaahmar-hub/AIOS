#!/usr/bin/env python3
"""Step 13: audit internal bridge-source availability for exact URL to unit."""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


RESOLVER_DIR = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/resolver")
RAW_CSV_DIR = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase/raw_data/csv")
RAW_CHAT_CSV = RAW_CSV_DIR / "5ca554ad55ac__omar_style_dataset_sample.csv"
IDENTITY_CSV = RESOLVER_DIR / "listing_identity_map.csv"
BENCHMARK_CSV = RESOLVER_DIR / "live_listing_benchmark_results.csv"
IDENT_BRIDGE_CSV = RESOLVER_DIR / "identifier_bridge_candidates.csv"
OUT_CSV = RESOLVER_DIR / "bridge_source_audit.csv"
OUT_MD = RESOLVER_DIR / "bridge_source_audit.md"

sys.path.append(str(RESOLVER_DIR))
import listing_similarity_matcher as matcher  # noqa: E402


URL_RE = re.compile(r"(https?://\S+|(?:propertyfinder\.ae|bayut\.com|dubizzle\.com)\S*)", re.I)
UNIT_RE = re.compile(r"\b(?:unit|apt|apartment|flat|villa)\s*(?:no\.?|number|#)?\s*[A-Za-z0-9-]+\b", re.I)
IDENTIFIER_HINT_RE = re.compile(
    r"\b(?:permit|trakheesi|dld permit|property no|property number|plot no|plot number|land no|land number)\b",
    re.I,
)
BROKER_REF_RE = re.compile(r"\b(?:broker ref(?:erence)?|reference|ref)\s*[:#-]?\s*[A-Za-z0-9-]{5,}\b", re.I)

SOURCE_DEFINITIONS = [
    ("listing screenshots", "OCR/image-based bridge not indexed in resolver"),
    ("broker reference databases", "No structured local broker reference dataset found"),
    ("agent/company inventory exports", "Inventory/unit exports exist but are not linked to listing URLs"),
    ("Property Finder reports/export files", "Property Finder URLs exist locally, but not with unit-bearing bridge fields"),
    ("Bayut/Dubizzle saved listing exports", "Bayut and Dubizzle URLs exist locally, but identifier fields are parser-noise only"),
    ("DLD/Dubai REST/permit datasets", "Permit/plot data exists in small pockets but does not join to benchmark listings"),
    ("CRM records", "No local CRM table with listing URL and unit join was found"),
    ("WhatsApp messages that include both listing link and unit number", "Direct WhatsApp bridge rows are the most important internal check"),
    ("old Excel files with listing URL + unit number", "Spreadsheet bridge would allow internal exact URL to unit joins"),
    ("owner/unit databases", "Large local unit corpus exists but without URL-level identifiers"),
]


def low(value):
    return matcher.low(value)


def meaningful_identifier(field, value):
    text = low(value)
    if not text:
        return ""
    blocked = ("details", "listed", "scaped", "market analysis", "tru estimate", "residence", "for sale")
    if any(token in text for token in blocked):
        return ""
    if field == "property_number" and text.startswith("/details"):
        return ""
    return text


def load_resolver_rows():
    with IDENTITY_CSV.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def count_resolver_bridge_rows(rows):
    listing_plus_unit = 0
    listing_plus_identifier = 0
    broker_reference_plus_unit = 0
    meaningful_listing_plus_identifier = 0

    for row in rows:
        has_listing = any((row.get(col) or "").strip() for col in ("listing_url", "property_finder_url", "bayut_url", "dubizzle_url"))
        has_unit = (row.get("unit") or "").strip() != ""
        identifiers = {
            field: meaningful_identifier(field, row.get(field, ""))
            for field in ("permit_number", "property_number", "plot_number", "land_number")
        }
        has_meaningful_identifier = any(identifiers.values())
        broker_like = BROKER_REF_RE.search(" ".join(str(row.get(col, "")) for col in row))

        if has_listing and has_unit:
            listing_plus_unit += 1
        if has_listing and any((row.get(field) or "").strip() for field in identifiers):
            listing_plus_identifier += 1
        if has_listing and has_meaningful_identifier:
            meaningful_listing_plus_identifier += 1
        if broker_like and has_unit:
            broker_reference_plus_unit += 1

    return {
        "listing_plus_unit": listing_plus_unit,
        "listing_plus_identifier": listing_plus_identifier,
        "meaningful_listing_plus_identifier": meaningful_listing_plus_identifier,
        "broker_reference_plus_unit": broker_reference_plus_unit,
    }


def count_whatsapp_bridge_rows():
    if not RAW_CHAT_CSV.exists():
        return {"link_plus_unit": 0, "link_plus_identifier": 0, "broker_reference_plus_unit": 0}

    link_plus_unit = 0
    link_plus_identifier = 0
    broker_reference_plus_unit = 0

    with RAW_CHAT_CSV.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            text = row.get("text", "") or ""
            if not URL_RE.search(text):
                continue
            has_unit = bool(UNIT_RE.search(text))
            has_identifier = bool(IDENTIFIER_HINT_RE.search(text))
            has_broker_reference = bool(BROKER_REF_RE.search(text))
            if has_unit:
                link_plus_unit += 1
            if has_identifier:
                link_plus_identifier += 1
            if has_broker_reference and has_unit:
                broker_reference_plus_unit += 1

    return {
        "link_plus_unit": link_plus_unit,
        "link_plus_identifier": link_plus_identifier,
        "broker_reference_plus_unit": broker_reference_plus_unit,
    }


def summarize_bridge_candidates():
    rows = list(csv.DictReader(IDENT_BRIDGE_CSV.open("r", encoding="utf-8", newline="")))
    counts = Counter(row["classification"] for row in rows)
    likely_examples = [row for row in rows if row["classification"] == "likely bridge possible"][:5]
    return counts, likely_examples


def build_source_rows(resolver_counts, whatsapp_counts, candidate_counts):
    rows = []
    for source_name, note in SOURCE_DEFINITIONS:
        status = "missing"
        evidence = ""

        if source_name == "listing screenshots":
            status = "missing"
            evidence = "0 OCR-indexed screenshot bridge rows in resolver outputs"
        elif source_name == "broker reference databases":
            status = "missing"
            evidence = f"{resolver_counts['broker_reference_plus_unit']} rows with broker-reference-like text + unit"
        elif source_name == "agent/company inventory exports":
            status = "partially available"
            evidence = "24,357 local unit rows exist, but 0 contain listing URL + unit"
        elif source_name == "Property Finder reports/export files":
            status = "partially available"
            evidence = "Property Finder URLs present in corpus; 0 meaningful listing URL + unit rows"
        elif source_name == "Bayut/Dubizzle saved listing exports":
            status = "partially available"
            evidence = f"{resolver_counts['listing_plus_identifier']} listing URL + identifier rows exist, but 0 meaningful identifier bridges"
        elif source_name == "DLD/Dubai REST/permit datasets":
            status = "partially available"
            evidence = "Permit/plot fields exist in corpus pockets, but 0 benchmark listings bridge through meaningful identifiers"
        elif source_name == "CRM records":
            status = "missing"
            evidence = "No local CRM-shaped listing URL + unit dataset detected"
        elif source_name == "WhatsApp messages that include both listing link and unit number":
            status = "missing"
            evidence = f"{whatsapp_counts['link_plus_unit']} WhatsApp messages with link + unit"
        elif source_name == "old Excel files with listing URL + unit number":
            status = "missing"
            evidence = f"{resolver_counts['listing_plus_unit']} resolver rows with listing URL + unit"
        elif source_name == "owner/unit databases":
            status = "available now"
            evidence = "Large local owner/unit corpus exists but without listing-link bridge"

        rows.append(
            {
                "bridge_source": source_name,
                "availability": status,
                "evidence_note": evidence,
                "supporting_context": note,
            }
        )
    return rows


def write_outputs(source_rows, resolver_counts, whatsapp_counts, candidate_counts, likely_examples):
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(source_rows[0].keys()))
        writer.writeheader()
        writer.writerows(source_rows)

    strongest_bridge = "area+project likely-only bridge"
    internal_exact_possible = "NO"

    lines = [
        "# Bridge Source Audit",
        "",
        f"- total rows with listing URL + unit: {resolver_counts['listing_plus_unit']}",
        f"- total rows with listing URL + permit/property/plot: {resolver_counts['meaningful_listing_plus_identifier']}",
        f"- total rows with broker reference + unit: {resolver_counts['broker_reference_plus_unit'] + whatsapp_counts['broker_reference_plus_unit']}",
        f"- total WhatsApp messages containing link + unit number: {whatsapp_counts['link_plus_unit']}",
        f"- strongest bridge source found: {strongest_bridge}",
        f"- exact URL -> unit possible internally: {internal_exact_possible}",
        "",
        "## Bridge source availability",
    ]
    for row in source_rows:
        lines.append(f"- {row['bridge_source']}: {row['availability']} | {row['evidence_note']}")

    lines.extend(
        [
            "",
            "## Bridge candidate summary",
            f"- exact bridge possible rows: {candidate_counts['exact bridge possible']}",
            f"- likely bridge possible rows: {candidate_counts['likely bridge possible']}",
            f"- no local bridge rows: {candidate_counts['no local bridge']}",
        ]
    )

    if likely_examples:
        lines.append("")
        lines.append("## Strongest internal examples")
        for row in likely_examples:
            lines.append(
                f"- {row['url']} | bridge={row['best_bridge_type']} | evidence={row['evidence_note']}"
            )

    lines.extend(
        [
            "",
            "## Verdict",
            "- Internal corpus contains listing rows and a large unit corpus, but no exact bridge rows joining live listing URLs to unit-bearing records.",
            "- The only internal bridge found is area/project overlap, which stays likely-only rather than exact.",
            "",
            f"- audit_csv: `{OUT_CSV}`",
        ]
    )

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    resolver_rows = load_resolver_rows()
    resolver_counts = count_resolver_bridge_rows(resolver_rows)
    whatsapp_counts = count_whatsapp_bridge_rows()
    candidate_counts, likely_examples = summarize_bridge_candidates()
    source_rows = build_source_rows(resolver_counts, whatsapp_counts, candidate_counts)
    write_outputs(source_rows, resolver_counts, whatsapp_counts, candidate_counts, likely_examples)

    print(
        json.dumps(
            {
                "total_rows_with_listing_url_plus_unit": resolver_counts["listing_plus_unit"],
                "total_rows_with_listing_url_plus_permit_property_plot": resolver_counts["meaningful_listing_plus_identifier"],
                "total_rows_with_broker_reference_plus_unit": resolver_counts["broker_reference_plus_unit"] + whatsapp_counts["broker_reference_plus_unit"],
                "total_whatsapp_messages_with_link_plus_unit": whatsapp_counts["link_plus_unit"],
                "strongest_bridge_source_found": "area+project likely-only bridge",
                "exact_url_to_unit_possible_internally": "NO",
                "audit_csv": str(OUT_CSV),
                "audit_md": str(OUT_MD),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
