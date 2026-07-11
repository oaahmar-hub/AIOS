#!/usr/bin/env python3
"""Parse a WhatsApp agent-group message into a structured property request.

Returns a criteria dict when the message is a real request, else None (so the
Deal Agent ignores chatter, greetings, and listings). Handles the messy,
bilingual, shorthand way brokers actually post:

    "Need 2BR JVC for rent under 90k"
    "Looking for studio Marina rental budget 55k"
    "client wants 3 bed villa Palm for sale 12M"
    "مطلوب 1 غرفة الخليج التجاري للايجار 70 الف"

Pure stdlib, deterministic, never raises.
"""

from __future__ import annotations

import re
from typing import Optional

# Known Dubai areas (extend freely; matched case-insensitively as substrings/aliases)
AREAS = {
    "jvc": "JVC", "jumeirah village circle": "JVC",
    "jvt": "JVT", "jumeirah village triangle": "JVT",
    "marina": "Dubai Marina", "dubai marina": "Dubai Marina",
    "jbr": "JBR", "jumeirah beach residence": "JBR",
    "downtown": "Downtown", "burj khalifa": "Downtown",
    "business bay": "Business Bay", "bb": "Business Bay",
    "palm": "Palm Jumeirah", "palm jumeirah": "Palm Jumeirah",
    "dubai hills": "Dubai Hills", "hills": "Dubai Hills",
    "jlt": "JLT", "arjan": "Arjan", "furjan": "Furjan", "al furjan": "Furjan",
    "meydan": "Meydan", "mbr": "MBR City", "sports city": "Sports City",
    "silicon": "Silicon Oasis", "damac hills": "Damac Hills", "town square": "Town Square",
    "creek": "Dubai Creek", "expo": "Expo City", "zabeel": "Zabeel",
    # full Dubai coverage (matches the area files in the owner data)
    "damac hills 2": "Damac Hills 2", "town square": "Town Square",
    "tilal al ghaf": "Tilal Al Ghaf", "villa nova": "Villa Nova",
    "mudon": "Mudon", "motor city": "Motor City", "mjl": "MJL",
    "marsa": "Marsa", "jge": "Jumeirah Golf Estates", "jumeirah golf": "Jumeirah Golf Estates",
    "impz": "IMPZ", "greens": "Greens", "the greens": "Greens",
    "emaar beach front": "Emaar Beach Front", "beachfront": "Emaar Beach Front",
    "dubai south": "Dubai South", "district one": "District One",
    "burj khalifa": "Downtown", "jvc district": "JVC", "seasons": "JVC",
}
AREA_AR = {
    "الخليج التجاري": "Business Bay", "دبي مارينا": "Dubai Marina", "مارينا": "Dubai Marina",
    "وسط المدينة": "Downtown", "نخلة": "Palm Jumeirah", "النخلة": "Palm Jumeirah",
}

_REQUEST_HINTS = re.compile(
    r"\b(need|looking|require|want|wanted|client|budget|for rent|for sale|rental|searching|"
    r"anyone (have|has)|available)\b|مطلوب|ابغى|ابحث|للايجار|للبيع|عايز|محتاج",
    re.IGNORECASE,
)


def _intent(t: str) -> Optional[str]:
    t = t.lower()
    if re.search(r"\b(rent|rental|lease|monthly|yearly|per year|/yr|pa)\b|للايجار|ايجار", t):
        return "rent"
    if re.search(r"\b(sale|buy|purchase|freehold|resale|off[- ]?plan)\b|للبيع|شراء|بيع", t):
        return "sale"
    return None


def _beds(t: str) -> Optional[str]:
    t = t.lower()
    if re.search(r"\bstudio\b|ستوديو", t):
        return "studio"
    m = re.search(r"\b(\d)\s*(?:br|bhk|bed|beds|bedroom|bedrooms|b/r)\b", t)
    if m:
        return m.group(1) + "BR"
    m = re.search(r"(\d)\s*غرف", t)
    if m:
        return m.group(1) + "BR"
    return None


def _ptype(t: str) -> Optional[str]:
    t = t.lower()
    for kw, val in (("villa", "villa"), ("townhouse", "townhouse"), ("th", "townhouse"),
                    ("apartment", "apartment"), ("apt", "apartment"), ("flat", "apartment"),
                    ("penthouse", "penthouse"), ("plot", "plot"), ("office", "office")):
        if re.search(rf"\b{kw}\b", t):
            return val
    if "فيلا" in t:
        return "villa"
    if "شقة" in t:
        return "apartment"
    return None


def _budget(t: str) -> Optional[int]:
    t = t.lower()
    # e.g. "90k", "1.2m", "55,000", "70 الف", "12M"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([kmم])", t)
    if m:
        num = float(m.group(1).replace(",", ""))
        unit = m.group(2).lower()
        if unit == "k":
            return int(num * 1_000)
        if unit == "m":
            return int(num * 1_000_000)
        if unit == "م":  # arabic 'm' rare; treat as million
            return int(num * 1_000_000)
    if re.search(r"الف", t):  # "70 الف" = 70 thousand
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*الف", t)
        if m:
            return int(float(m.group(1).replace(",", "")) * 1_000)
    m = re.search(r"\b(\d{2,3}(?:[.,]\d{3})+)\b", t)  # 55,000 / 1.200.000
    if m:
        return int(m.group(1).replace(",", "").replace(".", ""))
    return None


def _area(t: str) -> Optional[str]:
    for kw, val in AREA_AR.items():
        if kw in t:
            return val
    low = t.lower()
    # longest alias first so "dubai marina" beats "marina" etc.
    for kw in sorted(AREAS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(kw)}\b", low):
            return AREAS[kw]
    return None


def parse_request(text: str) -> Optional[dict]:
    """Return criteria dict for a real request, else None."""
    try:
        t = str(text or "").strip()
        if len(t) < 4:
            return None
        area = _area(t)
        intent = _intent(t)
        beds = _beds(t)
        # A message is a "request" if it has a request hint AND at least an area
        # or (intent + beds). Otherwise it's chatter/a listing — ignore it.
        looks_request = bool(_REQUEST_HINTS.search(t))
        if not (looks_request and (area or (intent and beds))):
            return None
        crit = {
            "area": area,
            "intent": intent,
            "beds": beds,
            "type": _ptype(t),
            "budget": _budget(t),
            "raw": t[:200],
        }
        return {k: v for k, v in crit.items() if v is not None}
    except Exception:  # pragma: no cover
        return None
