#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path("/Users/hassanka/Downloads/AIOS/PersonalityEngine")
LIBRARY = ROOT / "WHATSAPP_EDGE_CASE_LIBRARY.jsonl"


def load_cases() -> list[dict]:
    cases = []
    with LIBRARY.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def is_resolved(status: str) -> bool:
    return str(status or "").lower().startswith("resolved")


def is_open(status: str) -> bool:
    return str(status or "").lower() == "open"


def main() -> None:
    cases = load_cases()
    total = len(cases)
    open_count = sum(1 for c in cases if is_open(c.get("status", "")))
    resolved_count = sum(1 for c in cases if is_resolved(c.get("status", "")))
    failure_keys = Counter(
        (c.get("actual_behavior", "").strip().lower(), c.get("correct_behavior", "").strip().lower())
        for c in cases
    )
    repeated = sum(count - 1 for count in failure_keys.values() if count > 1)
    # Learning-mode score: starts from 96 and earns the path to 99 as open cases are closed.
    quality_score = 99.0 if total and open_count == 0 else round(96.0 + (resolved_count / max(total, 1)) * 3.0, 2)
    report = {
        "TOTAL EDGE CASES": total,
        "OPEN": open_count,
        "RESOLVED": resolved_count,
        "REPEATED FAILURES": repeated,
        "WHATSAPP QUALITY SCORE": f"{quality_score}%",
        "OPEN CASE IDS": [c["id"] for c in cases if is_open(c.get("status", ""))],
        "RESOLVED CASE IDS": [c["id"] for c in cases if is_resolved(c.get("status", ""))],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
