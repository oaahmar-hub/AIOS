#!/usr/bin/env python3
"""Enrich resolver_records from PropertyGraph listing_bridge_master.json.

Fills missing building, unit, permit_number, property_number, plot_number, and
URL fields where identifiers match. This is read-only enrichment against local data.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

KB = Path(__file__).resolve().parents[3] / "KnowledgeBase"
RESOLVER_DB = KB / "resolver" / "unit_resolver_database.sqlite"
BRIDGE_JSON = KB / "PropertyGraph" / "listing_bridge_master.json"


def load_bridge_records(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def index_bridges(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for rec in records:
        key = rec.get("listing_id") or rec.get("permit_number") or rec.get("property_number") or rec.get("plot_number")
        if not key:
            continue
        if key not in by_id:
            by_id[key] = rec
    return by_id


def url_column_for(platform: str) -> str | None:
    platform = (platform or "").lower()
    if "propertyfinder" in platform:
        return "property_finder_url"
    if "bayut" in platform:
        return "bayut_url"
    if "dubizzle" in platform:
        return "dubizzle_url"
    return None


def enrich_resolver(db_path: Path, bridge_records: list[dict[str, Any]]) -> dict[str, int]:
    by_id = index_bridges(bridge_records)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT resolver_record_id, listing_id, permit_number, property_number, plot_number FROM resolver_records")
    rows = cursor.fetchall()

    updated = 0
    matched = 0
    for resolver_record_id, listing_id, permit_number, property_number, plot_number in rows:
        bridge = None
        for key in (listing_id, permit_number, property_number, plot_number):
            if key and key in by_id:
                bridge = by_id[key]
                break
        if not bridge:
            continue
        matched += 1

        updates: dict[str, Any] = {}
        for src, dst in [
            ("building", "building"),
            ("unit", "unit"),
            ("permit_number", "permit_number"),
            ("property_number", "property_number"),
            ("plot_number", "plot_number"),
        ]:
            val = bridge.get(src)
            if val:
                updates[dst] = val

        url_col = url_column_for(bridge.get("source_platform", ""))
        if url_col:
            url = bridge.get("listing_url")
            if url:
                updates[url_col] = url
                updates["listing_url"] = url

        if not updates:
            continue

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [resolver_record_id]
        cursor.execute(
            f"UPDATE resolver_records SET {set_clause} WHERE resolver_record_id = ?",
            values,
        )
        updated += cursor.rowcount

    conn.commit()
    conn.close()
    return {"matched": matched, "updated": updated, "resolver_rows": len(rows), "bridge_records": len(bridge_records)}


def main() -> None:
    if not RESOLVER_DB.exists():
        raise FileNotFoundError(RESOLVER_DB)
    if not BRIDGE_JSON.exists():
        raise FileNotFoundError(BRIDGE_JSON)

    bridge_records = load_bridge_records(BRIDGE_JSON)
    stats = enrich_resolver(RESOLVER_DB, bridge_records)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
