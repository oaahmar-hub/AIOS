#!/usr/bin/env python3
"""Re-clean the listing bridge master and recompute honest bridge statuses.

The listing/URL ingestion parser historically leaked search-slug text and URL
path fragments into the hard-identifier columns (e.g. ``property_number =
"listed"``, ``plot_number = "for sale dubai dubai land majan 1583088"``), set a
constant placeholder ``building = "Canal Bay"`` on portal listings, and kept
auth/login redirect links as listing URLs. Those junk values then merged
hundreds of unrelated listings under a single canonical id.

This pass rewrites ``listing_bridge_master.csv``/``.json`` in place using the
shared hygiene rules in :mod:`bridge_data_layer`:

* drop slug/URL-fragment/placeholder values from hard-identifier columns,
* drop non-listing (auth/redirect) URLs,
* drop the ``Canal Bay`` placeholder building,
* re-derive the canonical property id so junk-merged rows are split apart, and
* recompute ``bridge_status`` and ``missing_bridge_fields`` from the cleaned row.

It is read-only against source feeds and fully deterministic.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
RESOLVER_DIR = OUT_DIR.parent / "resolver"
sys.path.append(str(RESOLVER_DIR))

import bridge_data_layer as bridge  # noqa: E402

MASTER_CSV = OUT_DIR / "listing_bridge_master.csv"
MASTER_JSON = OUT_DIR / "listing_bridge_master.json"

FIELDS = [
    "source_platform",
    "listing_url",
    "listing_id",
    "broker_reference",
    "permit_number",
    "property_number",
    "plot_number",
    "building",
    "unit",
    "cpid",
    "source",
    "freshness",
    "confidence",
    "verified_by",
    "bridge_status",
    "missing_bridge_fields",
]

HARD_FIELDS = ("property_number", "permit_number", "plot_number", "unit")


def sanitize_row(row: dict[str, str]) -> dict[str, str]:
    out = {field: bridge.norm(row.get(field, "")) for field in FIELDS}

    # Drop auth/redirect links that were mistaken for listing URLs, and
    # JWT/auth-token fragments that were mistaken for listing ids.
    if out["listing_url"] and not bridge.is_listing_url(out["listing_url"]):
        out["listing_url"] = ""
    if out["listing_id"] and not bridge.is_valid_listing_id(out["listing_id"]):
        out["listing_id"] = ""

    # Strip slug text / URL fragments / placeholders from identifier columns.
    out["broker_reference"] = bridge.clean_identifier(out["broker_reference"])
    out["permit_number"] = bridge.clean_identifier(out["permit_number"])
    out["property_number"] = bridge.clean_identifier(out["property_number"])
    out["plot_number"] = bridge.clean_identifier(out["plot_number"])
    out["unit"] = bridge.clean_identifier(out["unit"])
    if bridge.is_placeholder_building(out["building"]):
        out["building"] = ""

    has_public_ref = (
        bridge.is_listing_url(out["listing_url"])
        or bridge.is_valid_listing_id(out["listing_id"])
        or bool(out["broker_reference"])
    )
    has_hard = any(bridge.is_strong_identifier(out[field], field) for field in HARD_FIELDS)
    has_location = bool(out["building"])

    # Re-derive the canonical id from the cleaned row so junk-merged groups
    # (e.g. the "CPID-LAND-77800826" mega-merge) are split back apart.
    cpid = bridge.canonical_property_id_from_row(
        {
            "property_number": out["property_number"],
            "permit_number": out["permit_number"],
            "plot_number": out["plot_number"],
            "unit_number": out["unit"],
            "source_platform": out["source_platform"],
            "listing_id": out["listing_id"],
            "broker_reference": out["broker_reference"],
            "building_name": out["building"],
        }
    )
    out["cpid"] = cpid

    missing: list[str] = []
    if has_public_ref and has_hard and cpid:
        status = "exact_bridge"
        confidence = "100"
    elif has_public_ref and (has_location or cpid):
        status = "partial_bridge"
        confidence = "80"
        if not has_hard:
            missing.append("hard_property_identifier")
    elif has_public_ref:
        status = "candidate_bridge"
        confidence = "65"
        missing.append("hard_property_identifier")
        missing.append("location_or_cpid")
    else:
        status = "invalid_bridge"
        confidence = "0"
        missing.append("public_bridge_reference")

    out["bridge_status"] = status
    out["confidence"] = confidence
    out["missing_bridge_fields"] = " | ".join(missing)
    return out


def main() -> None:
    with MASTER_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    before = Counter(bridge.norm(row.get("bridge_status", "")) for row in rows)
    cleaned = [sanitize_row(row) for row in rows]
    after = Counter(row["bridge_status"] for row in cleaned)

    with MASTER_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(cleaned)

    MASTER_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "total_rows": len(cleaned),
        "status_before": dict(before),
        "status_after": dict(after),
        "distinct_cpid_before": len({bridge.norm(row.get("cpid", "")) for row in rows}),
        "distinct_cpid_after": len({row["cpid"] for row in cleaned}),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
