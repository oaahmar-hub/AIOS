#!/usr/bin/env python3
"""Candidate inventory — verified-adjacent units the brain must NOT quote as fact.

The canonical property master holds units at confidence states below the
"quotable" bar (POSSIBLE / LIKELY): a real building + unit + an asking price
that has NOT been confirmed to the standard the brain uses when it states a
price to a customer. Feeding these into the quotable set would let the bot
present an unconfirmed price as fact — exactly what the no-fabrication rule
forbids.

Instead this module exposes them as a *verification worklist*: real leads Omar
can confirm, one click from becoming live inventory. Nothing here is ever
surfaced to a customer as a firm quote. Pure stdlib; never raises.
"""
from __future__ import annotations

import csv
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
CANONICAL_CSV = AIOS_ROOT / "KnowledgeBase" / "PropertyGraph" / "canonical_property_master.csv"

# States that are real-but-unconfirmed: worth verifying, never quotable.
_CANDIDATE_STATES = {"POSSIBLE", "LIKELY"}

_cache: list[dict] | None = None


def _load() -> list[dict]:
    global _cache
    if _cache is not None:
        return _cache
    import inventory_retrieval as inv  # reuse the same junk filters
    # Skip units already verified/live so the worklist is only *new* work.
    live = {(r["area"].lower().strip(), r["building"].lower().strip(), str(r["unit"]).lower().strip())
            for r in inv._load_rows()}
    out: list[dict] = []
    try:
        with CANONICAL_CSV.open(newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                state = (r.get("verification_state") or "").strip().upper()
                if state not in _CANDIDATE_STATES:
                    continue
                area = (r.get("canonical_area") or "").strip()
                building = (r.get("canonical_building") or "").strip()
                unit = (r.get("canonical_unit") or "").strip()
                price = (r.get("last_asking_price") or "").strip()
                if inv._is_junk_area(area) or not building or not unit:
                    continue
                if inv._is_junk_building(building) or not price:
                    continue
                if (area.lower(), building.lower(), unit.lower()) in live:
                    continue
                out.append({
                    "area": area,
                    "project": (r.get("canonical_project") or "").strip(),
                    "building": building,
                    "unit": unit,
                    "developer": (r.get("developer") or "").strip(),
                    "asking_price": price,
                    "confidence": state,
                    "reason": (r.get("verification_reason") or "").strip()[:160],
                    "sources": (r.get("source_count") or "").strip(),
                    "last_seen": (r.get("latest_seen_date") or "").strip(),
                    "permit_numbers": (r.get("permit_numbers") or "").strip()[:120],
                    "property_numbers": (r.get("property_numbers") or "").strip()[:120],
                    # explicit, machine + human readable: this is NOT a firm quote
                    "quotable": False,
                    "disclosure": "Unconfirmed candidate — verify before quoting.",
                })
    except Exception:
        out = []
    # Most sources + most recent first: the strongest leads to verify sit on top.
    def _key(c):
        try:
            s = int(c["sources"] or 0)
        except Exception:
            s = 0
        return (s, c["last_seen"])
    out.sort(key=_key, reverse=True)
    _cache = out
    return _cache


def worklist(limit: int = 100) -> list[dict]:
    return _load()[:max(0, int(limit))]


def stats() -> dict:
    try:
        rows = _load()
        by_area: dict[str, int] = {}
        by_conf: dict[str, int] = {}
        for r in rows:
            by_area[r["area"]] = by_area.get(r["area"], 0) + 1
            by_conf[r["confidence"]] = by_conf.get(r["confidence"], 0) + 1
        return {"ok": True, "candidates": len(rows),
                "by_confidence": by_conf,
                "top_areas": dict(sorted(by_area.items(), key=lambda x: -x[1])[:6])}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


def health() -> dict:
    s = stats()
    if not s.get("ok"):
        return {"ok": False, "detail": f"error:{s.get('error')}"}
    return {"ok": True, "detail": f"{s['candidates']} candidates to verify (never quoted)"}


if __name__ == "__main__":
    import json
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
    for c in worklist(4):
        print(f"  ~ {c['area']} | {c['building']} | u{c['unit']} | AED {c['asking_price']} | {c['confidence']} | {c['sources']} src")
