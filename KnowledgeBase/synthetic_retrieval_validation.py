#!/usr/bin/env python3
from __future__ import annotations

"""Offline synthetic retrieval validation for AIOS hybrid retriever.

Generates messy natural questions from real indexed records and verifies that
the hybrid retriever can recover the source/project/unit signal. This is a
deterministic baseline runner; an LLM paraphraser can be plugged in later.
"""

import argparse
import json
import random
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path

from hybrid_retriever import HybridRetriever


ROOT = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
SQLITE_DB = ROOT / "Property_Master_Database.sqlite"


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def sample_records(limit: int = 50, seed: int = 42) -> list[dict]:
    con = sqlite3.connect(SQLITE_DB)
    con.row_factory = sqlite3.Row
    rows = [dict(row) for row in con.execute(
        """
        SELECT
            IFNULL(p.name, '') AS project,
            IFNULL(a.name, '') AS area,
            IFNULL(d.name, '') AS developer,
            ir.unit_ref AS unit,
            ir.row_number,
            f.file_name AS source_file,
            f.source_group AS source_group
        FROM inventory_rows ir
        LEFT JOIN projects p ON ir.project_id = p.project_id
        LEFT JOIN areas a ON ir.area_id = a.area_id
        LEFT JOIN developers d ON ir.developer_id = d.developer_id
        LEFT JOIN inventory_files f ON ir.source_id = f.source_id
        WHERE (p.name IS NOT NULL OR ir.unit_ref IS NOT NULL)
          AND f.file_name IS NOT NULL
        ORDER BY abs(random())
        LIMIT ?
        """,
        (limit,),
    ).fetchall()]
    con.close()
    random.Random(seed).shuffle(rows)
    return rows


def make_question(record: dict) -> str:
    project = clean(record.get("project"))
    area = clean(record.get("area"))
    unit = clean(record.get("unit"))
    developer = clean(record.get("developer"))
    templates = [
        "bro check {project} unit {unit}",
        "Need details for {unit} in {project}",
        "What do we have in {project} {area}?",
        "find this one {project} {unit} pls",
        "Any record for {developer} {project}?",
        "شو عندنا عن {project} وحدة {unit}",
    ]
    template = random.choice(templates)
    question = template.format(project=project or "project", area=area or "", unit=unit or "", developer=developer or "")
    return re.sub(r"\s+", " ", question).strip()


def hit(record: dict, result: dict) -> bool:
    haystack = json.dumps(result.get("merged_data", []), ensure_ascii=False).lower()
    project = clean(record.get("project")).lower()
    source = clean(record.get("source_file")).lower()
    unit = clean(record.get("unit")).lower()
    checks = []
    if project:
        checks.append(project in haystack)
    if source:
        checks.append(source in haystack)
    if unit and len(unit) >= 3:
        checks.append(unit in haystack)
    return any(checks)


def run(limit: int = 50) -> dict:
    retriever = HybridRetriever()
    records = sample_records(limit=limit)
    cases = []
    for record in records:
        question = make_question(record)
        result = asdict(retriever.retrieve(question, limit=6))
        ok = hit(record, result)
        cases.append(
            {
                "question": question,
                "expected": record,
                "hit": ok,
                "confidence": result.get("system_confidence_score"),
                "sources": result.get("source_file_references", [])[:3],
            }
        )
    hits = sum(1 for case in cases if case["hit"])
    accuracy = round((hits / max(len(cases), 1)) * 100, 2)
    return {"total": len(cases), "hits": hits, "accuracy_percent": accuracy, "target_percent": 90, "pass": accuracy >= 90, "cases": cases}


def main():
    parser = argparse.ArgumentParser(description="Validate AIOS hybrid retrieval coverage")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    print(json.dumps(run(args.limit), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
