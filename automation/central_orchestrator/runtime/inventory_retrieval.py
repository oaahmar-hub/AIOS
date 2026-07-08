#!/usr/bin/env python3
"""Inventory retrieval for the WhatsApp brain — the knowledge connection.

Turns a customer message into a search over the AIOS resolver inventory and
returns a compact, VERIFIED context block the LLM may quote from. The hard
rule stays intact: the brain may only state unit/price/size details that
appear in this block — everything else remains "I'll check and confirm."

Honesty guarantees:
- Only "quotable" rows are ever surfaced: area + (building or project) +
  unit + (price or size) must all be real values from the database.
- Junk areas (pure numbers from column-misaligned sources) are excluded.
- Every line in the context is a direct rendering of a database row —
  nothing is synthesized, rounded, or estimated.

Pure stdlib; loads the bundled resolver index once per process.
"""
from __future__ import annotations

import csv
import re
import threading
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
INDEX_CSV = AIOS_ROOT / "KnowledgeBase" / "resolver" / "unit_resolver_index.csv"
# Verified supplementary inventory ingested from the owner's Google Drive
# (Scorpion sale sheet + developer availability book). Loaded through the same
# quotable rule + junk filters as the main index; deduped by area/building/unit.
_SUPPLEMENTARY_CSVS = [
    AIOS_ROOT / "KnowledgeBase" / "TruthIngestion" / "drive_verified_inventory_2026-07-08.csv",
]

MAX_RESULTS = 5

# Arabic-Indic digits -> ASCII
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Common area spellings customers actually type (canonical -> aliases).
AREA_ALIASES: dict[str, list[str]] = {
    "JVC": ["jvc", "jumeirah village circle", "jumeirah village"],
    "JVT": ["jvt", "jumeirah village triangle"],
    "Beach Front": ["beachfront", "beach front", "emaar beachfront", "eb "],
    "Dubai Hills Estate": ["dubai hills", "hills estate", "dhe "],
    "Downtown": ["downtown", "burj khalifa area", "دبي وسط"],
    "Burj Khalifa": ["burj khalifa"],
    "Marsa Dubai": ["marsa dubai", "dubai marina", "marina"],
    "JBR": ["jbr", "jumeirah beach residence"],
    "Bluewaters": ["bluewaters", "blue waters"],
    "Creek Harbour": ["creek harbour", "creek harbor", "dubai creek"],
    "District One": ["district one", "district 1", "mbr city", "mohammed bin rashid"],
    "Palm Jumeirah": ["palm jumeirah", "the palm", "بالم", "النخلة"],
    "Marjan Island": ["marjan"],
    "Tilal Al Ghaf": ["tilal al ghaf", "tilal"],
    "The Oasis - Palmiera": ["oasis palmiera", "the oasis"],
    "Valley": ["the valley"],
    "Emirates Hills": ["emirates hills"],
    "Arjan": ["arjan"],
    "Business Bay": ["business bay"],
}

_BED_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"\bstudio\b|استوديو|ستوديو"), 0),
    (re.compile(r"\b(?:1\s*(?:br|bed|bedroom)s?|one\s*bed(?:room)?)\b|غرفة\s*وصالة|غرفه\s*وصاله"), 1),
    (re.compile(r"\b(?:2\s*(?:br|bed|bedroom)s?|two\s*bed(?:room)?s?)\b|غرفتين"), 2),
    (re.compile(r"\b(?:3\s*(?:br|bed|bedroom)s?|three\s*bed(?:room)?s?)\b|(?:3|٣)\s*غرف"), 3),
    (re.compile(r"\b(?:4\s*(?:br|bed|bedroom)s?|four\s*bed(?:room)?s?)\b|(?:4|٤)\s*غرف"), 4),
    (re.compile(r"\b(?:5\s*(?:br|bed|bedroom)s?|five\s*bed(?:room)?s?)\b|(?:5|٥)\s*غرف"), 5),
]

_BUDGET_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(k|m|thousand|million|mil|ألف|الف|مليون)?",
    re.IGNORECASE,
)

_lock = threading.Lock()
_ROWS: list[dict[str, str]] | None = None


def _norm(v: Any) -> str:
    return str(v or "").strip()


def _is_junk_area(area: str) -> bool:
    a = area.replace(".", "").replace(",", "").strip()
    return not a or a.replace(" ", "").isdigit()


def _is_junk_building(building: str) -> bool:
    """Column-misaligned junk like '31 803 681', '17 null 681 6716 building',
    '03 c 2701 681' — never quotable. A real name needs a real word."""
    tokens = building.lower().split()
    if not tokens:
        return True
    generic = {"null", "building", "tower", "bldg", "apt", "apartment", "unit", "retail", "shop"}
    if all(t in generic or t.isdigit() or re.fullmatch(r"[a-z]\d{0,4}", t) for t in tokens):
        return True
    # Packed leftovers carry embedded prices/ids ("00 525000 jumeirah village
    # circle tower") - a >=5-digit numeric token is never part of a real name.
    return any(t.isdigit() and len(t) >= 5 for t in tokens)


def _load_rows() -> list[dict[str, str]]:
    """Load quotable inventory once (thread-safe, lazy)."""
    global _ROWS
    if _ROWS is not None:
        return _ROWS
    with _lock:
        if _ROWS is not None:
            return _ROWS
        rows: list[dict[str, str]] = []
        try:
            with INDEX_CSV.open(newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    area = _norm(r.get("area"))
                    building = _norm(r.get("building")) or _norm(r.get("project"))
                    unit = _norm(r.get("unit"))
                    price = _norm(r.get("price"))
                    size = _norm(r.get("size"))
                    if _is_junk_area(area) or not building or not unit:
                        continue
                    if _is_junk_building(building):
                        continue
                    if not price and not size:
                        continue
                    rows.append(
                        {
                            "area": area,
                            "building": building,
                            "unit": unit,
                            "bedrooms": _norm(r.get("bedrooms")),
                            "price": price,
                            "size": size,
                            "developer": _norm(r.get("developer")),
                        }
                    )
        except Exception:
            rows = []
        # Supplementary verified sources (owner's Drive inventory). Same quotable
        # rule + junk filters; deduped against the index by area/building/unit.
        seen = {(r["area"].lower(), r["building"].lower(), str(r["unit"]).lower()) for r in rows}
        for extra in _SUPPLEMENTARY_CSVS:
            try:
                if not extra.exists():
                    continue
                with extra.open(newline="", encoding="utf-8", errors="replace") as fh:
                    for r in csv.DictReader(fh):
                        area = _norm(r.get("area"))
                        building = _norm(r.get("building")) or _norm(r.get("project"))
                        unit = _norm(r.get("unit"))
                        price = _norm(r.get("price"))
                        size = _norm(r.get("size"))
                        if _is_junk_area(area) or not building or not unit:
                            continue
                        if _is_junk_building(building) or (not price and not size):
                            continue
                        key = (area.lower(), building.lower(), unit.lower())
                        if key in seen:
                            continue
                        seen.add(key)
                        rows.append({
                            "area": area, "building": building, "unit": unit,
                            "bedrooms": _norm(r.get("bedrooms")), "price": price,
                            "size": size, "developer": _norm(r.get("developer")),
                        })
            except Exception:
                continue
        _ROWS = rows
        return _ROWS


def quotable_count() -> int:
    return len(_load_rows())


def parse_query(text: str) -> dict[str, Any]:
    """Extract area / building / bedrooms / budget from a customer message."""
    t = " " + _norm(text).translate(_AR_DIGITS).lower() + " "
    out: dict[str, Any] = {"area": None, "building": None, "bedrooms": None, "budget": None}

    for canon, aliases in AREA_ALIASES.items():
        if any(a in t for a in aliases):
            out["area"] = canon
            break

    for pat, beds in _BED_PATTERNS:
        if pat.search(t):
            out["bedrooms"] = beds
            break

    # Budget: the largest money-like number in the message.
    budget = 0.0
    for num, unit in _BUDGET_RE.findall(t):
        try:
            val = float(num.replace(",", ""))
        except ValueError:
            continue
        u = (unit or "").lower()
        if u in {"k", "thousand", "ألف", "الف"}:
            val *= 1_000
        elif u in {"m", "mil", "million", "مليون"}:
            val *= 1_000_000
        elif val < 10_000:
            continue  # bare small number: not a budget
        budget = max(budget, val)
    if budget >= 10_000:
        out["budget"] = int(budget)

    # Building: match known building names present in the message.
    buildings = {r["building"].lower() for r in _load_rows()}
    hit = ""
    for b in buildings:
        if len(b) >= 4 and b in t and len(b) > len(hit):
            hit = b
    if hit:
        out["building"] = hit
    else:
        # Project-brand match: many buildings are multi-word ("Verdana 6 TH",
        # "Reportage Hills", "Taormina Village 2"). A customer typing just the
        # brand ("Verdana") should still match the family, so match on the
        # distinctive leading token shared across a project's buildings.
        brands = {b.split()[0] for b in buildings if len(b.split()[0]) >= 5}
        for w in re.findall(r"[a-z]{5,}", t):
            if w in brands:
                out["building"] = w
                break

    return out


def _price_num(row: dict[str, str]) -> float:
    try:
        return float(row["price"].replace(",", ""))
    except Exception:
        return 0.0


def search(text: str, max_results: int = MAX_RESULTS) -> list[dict[str, str]]:
    """Return up to max_results real inventory rows matching the message."""
    q = parse_query(text)
    if not q["area"] and not q["building"]:
        return []  # nothing anchoring the search — do not spray random units
    rows = _load_rows()
    scored: list[tuple[float, dict[str, str]]] = []
    for r in rows:
        score = 0.0
        if q["building"]:
            if q["building"] in r["building"].lower():
                score += 4
            elif not q["area"]:
                continue
        if q["area"]:
            if r["area"].lower() == q["area"].lower():
                score += 2
            elif not q["building"] or q["building"] not in r["building"].lower():
                continue
        if q["bedrooms"] is not None and r["bedrooms"]:
            try:
                if int(float(r["bedrooms"])) == q["bedrooms"]:
                    score += 2
                else:
                    continue
            except ValueError:
                pass
        price = _price_num(r)
        if q["budget"]:
            if price and price > q["budget"] * 1.1:
                continue
            if price:
                score += 1
        if price:
            score += 0.5  # rows with a real price are more useful
        scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], _price_num(x[1]) or 9e18))
    # De-duplicate identical building+unit rows.
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for _, r in scored:
        key = (r["building"].lower(), r["unit"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= max_results:
            break
    return out


def _fmt_row(r: dict[str, str]) -> str:
    parts = [r["area"], r["building"], f"unit {r['unit']}"]
    if r["bedrooms"]:
        try:
            b = int(float(r["bedrooms"]))
            parts.append("studio" if b == 0 else f"{b}BR")
        except ValueError:
            pass
    if r["size"]:
        parts.append(f"size {r['size']}")
    if r["price"]:
        try:
            parts.append(f"AED {int(float(r['price'].replace(',', ''))):,}")
        except ValueError:
            parts.append(f"AED {r['price']}")
    if r["developer"]:
        parts.append(r["developer"])
    return " | ".join(parts)


def build_inventory_context(text: str) -> tuple[str, int]:
    """Return (context_block, match_count) for the LLM system prompt.

    Empty block when nothing matches — the no-fabrication rule then makes the
    brain answer "I'll check and confirm" instead of inventing.
    """
    matches = search(text)
    if not matches:
        return "", 0
    lines = "\n".join(f"- {_fmt_row(r)}" for r in matches)
    block = (
        "VERIFIED INVENTORY (AIOS database) — these are the ONLY listings you may "
        "quote, exactly as written; do not alter numbers, do not add units:\n"
        f"{lines}\n"
        "If the customer asks about anything not in this list, say you'll check "
        "and confirm. 'size' numbers are as recorded WITHOUT a unit - do not state "
        "sqft or sqm for them; if a field is missing, don't guess it."
    )
    return block, len(matches)


if __name__ == "__main__":
    import json as _json
    import sys as _sys

    msg = " ".join(_sys.argv[1:]) or "1br in JVC under 900k"
    print(_json.dumps({"query": parse_query(msg)}, ensure_ascii=False))
    for row in search(msg):
        print(_fmt_row(row))
