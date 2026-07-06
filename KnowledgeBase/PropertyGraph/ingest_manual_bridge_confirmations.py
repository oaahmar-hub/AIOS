#!/usr/bin/env python3
"""Import manually confirmed bridge rows and rebuild the property graph."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import sys

KB = Path(__file__).resolve().parents[1]
GRAPH_DIR = KB / "PropertyGraph"
RESOLVER_DIR = KB / "resolver"


def _resolve_resolver_db(resolver_dir: Path) -> Path:
    resolver_file = resolver_dir / "unit_resolver_database.resolver"
    if resolver_file.is_file():
        return resolver_file
    return resolver_dir / "unit_resolver_database.sqlite"


DB_PATH = _resolve_resolver_db(RESOLVER_DIR)
INPUT_CSV = GRAPH_DIR / "manual_bridge_confirmations.csv"

sys.path.append(str(RESOLVER_DIR))
import bridge_data_layer as bridge_layer  # noqa: E402

sys.path.append(str(GRAPH_DIR))
import build_property_graph as graph_builder  # noqa: E402


def load_rows(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    rows = load_rows(INPUT_CSV)
    if not rows:
        print(json.dumps({"imported_rows": 0, "message": f"No rows found in {INPUT_CSV}"}))
        return
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(bridge_layer.SCHEMA_SQL)
    imported = 0
    for raw in rows:
        normalized = bridge_layer.normalize_bridge_row(raw)
        normalized["bridge_classification"] = "exact_bridge"
        normalized["confidence"] = "100"
        normalized["created_at"] = bridge_layer.now_iso()
        columns = list(normalized.keys())
        cur.execute(
            f"insert or replace into {bridge_layer.TABLE_NAME} ({','.join(columns)}) values ({','.join('?' for _ in columns)})",
            [normalized[col] for col in columns],
        )
        imported += 1
    con.commit()
    con.close()
    summary = graph_builder.build()
    summary["manual_bridge_rows_imported"] = imported
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
