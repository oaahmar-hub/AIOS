#!/usr/bin/env python3
"""Repair corrupted building/project/unit/area fields in the resolver corpus.

Several sources dumped whole title-deed lines into the ``building`` and
``area`` columns, e.g.::

    building = "t 5225 maria del carmen gamarra apartment 2205 beach tower"
    area     = "B.T 5225 Maria Del Carmen Gamarra Apartment 2205 Beach Tower 1 97.25 m2 508242463"

The real building name ("Beach Tower") and the unit ("2205") are present in
that string, but the owner name / plot / size / phone noise around them makes
the field unusable as a bridge anchor and fragments same-unit clustering
(every row looks unique).

This pass is deterministic and idempotent. For every record whose ``building``
matches the title-deed pattern it:

- extracts the real building name (the alpha tokens after ``apartment <unit>``)
  and rewrites ``building`` to it;
- backfills ``unit`` from the same pattern when ``unit`` is empty;
- backfills ``project`` from the recovered building name when ``project`` is
  empty;
- clears ``area`` when ``area`` is itself a title-deed line (contains
  ``apartment <digits>``), because a per-row junk area only adds noise.

It never invents values: everything written is a substring already present in
the record. It updates both ``unit_resolver_index.csv`` (what the property
graph builder reads) and the ``resolver_records`` table (the source of truth),
keeping timestamped backups.
"""

from __future__ import annotations

import csv
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

RESOLVER_DIR = Path(__file__).resolve().parent
INDEX_CSV = RESOLVER_DIR / "unit_resolver_index.csv"


def _resolve_resolver_db(resolver_dir: Path) -> Path:
    resolver_file = resolver_dir / "unit_resolver_database.resolver"
    if resolver_file.is_file():
        return resolver_file
    return resolver_dir / "unit_resolver_database.sqlite"


DB_PATH = _resolve_resolver_db(RESOLVER_DIR)

UNIT_RE = re.compile(r"\bapartment\s+([0-9]{1,6}[a-z]?)\b", re.IGNORECASE)
_STOP_TOKENS = {"m2", "sqft", "sq", "sqm"}


def _norm(value: object) -> str:
    return str(value or "").strip()


def extract_building_and_unit(building_raw: str) -> Optional[Tuple[str, str]]:
    """Return (unit, building_name) recovered from a title-deed building string."""
    text = _norm(building_raw)
    match = UNIT_RE.search(text)
    if not match:
        return None
    unit = match.group(1)
    tail = text[match.end():].strip()
    name_tokens = []
    for token in tail.split():
        if re.fullmatch(r"[0-9]+(\.[0-9]+)?", token):
            break
        if token.lower() in _STOP_TOKENS:
            break
        if re.fullmatch(r"[0-9]{6,}", token):
            break
        name_tokens.append(token)
        if len(name_tokens) >= 4:
            break
    building_name = " ".join(name_tokens).strip()
    return unit, building_name


def _title_case(value: str) -> str:
    return " ".join(word.capitalize() for word in value.split())


def repair_record(record: Dict[str, str]) -> Dict[str, str]:
    """Return the set of fields that changed for this record (may be empty)."""
    changes: Dict[str, str] = {}
    building_raw = _norm(record.get("building"))
    extracted = extract_building_and_unit(building_raw)
    if extracted:
        unit, building_name = extracted
        if building_name:
            clean_building = _title_case(building_name)
            if building_raw != clean_building:
                changes["building"] = clean_building
            if not _norm(record.get("unit")) and unit:
                changes["unit"] = unit
            if not _norm(record.get("project")):
                changes["project"] = clean_building
    area = _norm(record.get("area"))
    if area and UNIT_RE.search(area):
        changes["area"] = ""
    return changes


def repair_index_csv() -> Dict[str, int]:
    rows = list(csv.DictReader(INDEX_CSV.open(newline="", encoding="utf-8")))
    if not rows:
        return {"rows": 0}
    fieldnames = list(rows[0].keys())
    stats = {"rows": len(rows), "building": 0, "unit": 0, "project": 0, "area_cleared": 0, "records_changed": 0}
    for row in rows:
        changes = repair_record(row)
        if not changes:
            continue
        stats["records_changed"] += 1
        for field, value in changes.items():
            row[field] = value
            if field == "area":
                stats["area_cleared"] += 1
            else:
                stats[field] += 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(INDEX_CSV, INDEX_CSV.with_suffix(f".csv.bak-{stamp}"))
    with INDEX_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return stats


def repair_resolver_table() -> Dict[str, int]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(resolver_records)")}
        if not {"building", "project", "unit", "area"} <= cols:
            return {"updated": 0, "note": "resolver_records missing expected columns"}
        rows = [dict(r) for r in con.execute("select resolver_record_id, area, project, building, unit from resolver_records")]
        updated = 0
        for row in rows:
            changes = repair_record(row)
            if not changes:
                continue
            assignments = ", ".join(f"{field} = ?" for field in changes)
            con.execute(
                f"update resolver_records set {assignments} where resolver_record_id = ?",
                [*changes.values(), row["resolver_record_id"]],
            )
            updated += 1
        con.commit()
        return {"updated": updated}
    finally:
        con.close()


def main() -> None:
    csv_stats = repair_index_csv()
    db_stats = repair_resolver_table()
    print("unit_resolver_index.csv:", csv_stats)
    print("resolver_records table:", db_stats)


if __name__ == "__main__":
    main()
