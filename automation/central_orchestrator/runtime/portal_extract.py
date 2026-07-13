#!/usr/bin/env python3
"""Extract structured unit info from a Bayut / Property Finder / Dubizzle URL.

The Deal Agent's SEARCH step and the owner lookup both need to turn a pasted
listing link into {area, building, unit?, listing_id} so it can be matched to
the DLD owner data. This parses the URL slug (no network needed) and returns
what's reliably encoded there; fields that aren't in the URL come back empty
(never guessed).

Pure stdlib, deterministic, never raises.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Optional

_AREA_HINTS = {
    "jumeirah-village-circle": "JVC", "jvc": "JVC",
    "jumeirah-village-triangle": "JVT", "jvt": "JVT",
    "dubai-marina": "Dubai Marina", "marina": "Dubai Marina",
    "jumeirah-beach-residence": "JBR", "jbr": "JBR",
    "downtown-dubai": "Downtown", "downtown": "Downtown", "burj-khalifa": "Downtown",
    "business-bay": "Business Bay",
    "palm-jumeirah": "Palm Jumeirah",
    "dubai-hills": "Dubai Hills", "dubai-hills-estate": "Dubai Hills",
    "jumeirah-lake-towers": "JLT", "jlt": "JLT",
    "arjan": "Arjan", "al-furjan": "Furjan", "furjan": "Furjan",
    "dubai-south": "Dubai South", "town-square": "Town Square",
    "damac-hills": "Damac Hills", "damac-hills-2": "Damac Hills 2",
    "mudon": "Mudon", "motor-city": "Motor City", "tilal-al-ghaf": "Tilal Al Ghaf",
    "emaar-beachfront": "Emaar Beach Front", "meydan": "Meydan",
}


def detect_portal(url: str) -> Optional[str]:
    u = (url or "").lower()
    if "bayut." in u:
        return "bayut"
    if "propertyfinder." in u:
        return "propertyfinder"
    if "dubizzle." in u:
        return "dubizzle"
    return None


def _slug_words(url: str) -> list:
    try:
        path = urlparse(url).path.lower()
        return [w for w in re.split(r"[/\-_.]+", path) if w]
    except Exception:
        return []


def _listing_id(url: str, portal: Optional[str]) -> str:
    # Bayut: /pm/<id>/<uuid> or ...-<digits>.html ; PF: ...-<digits>.html
    m = re.search(r"/pm/(\d+)/", url or "")
    if m:
        return m.group(1)
    m = re.search(r"-(\d{6,})\.html", url or "")
    if m:
        return m.group(1)
    m = re.search(r"/(\d{6,})(?:[/?#]|$)", url or "")
    return m.group(1) if m else ""


def _area(words: list):
    """Return (area_label, matched_key). matched_key is the hint slug that fired
    so the building parser can strip exactly those area tokens (and nothing
    else — 'towers' must survive for 'Bloom Towers')."""
    joined = " ".join(words)
    for key in sorted(_AREA_HINTS, key=len, reverse=True):
        if key.replace("-", " ") in joined or key in words:
            return _AREA_HINTS[key], key
    return "", ""


def _building(words: list, area: str, area_key: str = "") -> str:
    """Best-effort building phrase: the slug segment(s) after the area name and
    before the listing id / property-type words. Conservative — returns empty
    when it can't isolate a clean name."""
    stop = {"apartment", "apartments", "villa", "villas", "townhouse", "flat",
            "for", "rent", "sale", "buy", "dubai", "en", "ar", "plp", "property",
            "studio", "1", "2", "3", "4", "5", "bedroom", "bed", "html"}
    # strip exactly the tokens of the matched area phrase + the area label words +
    # common short area codes — but NOT generic building words like "towers".
    area_tokens = set(area.lower().split()) | set((area_key or "").split("-"))
    area_tokens |= {"jvc", "jvt", "jbr", "jlt", "dubai"}
    keep = [w for w in words
            if w not in stop and w not in area_tokens
            and not w.isdigit() and len(w) > 1]
    if not keep:
        return ""
    # building name is usually 1-4 tokens; take the last such run
    name = " ".join(keep[-4:]).title()
    return name if re.search(r"[a-z]{3,}", name.lower()) else ""


def extract(url: str) -> dict:
    """Return {ok, portal, area, building, listing_id, url}. ok is False for a
    non-listing / unrecognized URL."""
    try:
        portal = detect_portal(url)
        if not portal:
            return {"ok": False, "reason": "not a Bayut/PropertyFinder/Dubizzle URL"}
        words = _slug_words(url)
        area, area_key = _area(words)
        return {
            "ok": True,
            "portal": portal,
            "area": area,
            "building": _building(words, area, area_key),
            "listing_id": _listing_id(url, portal),
            "url": url,
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "reason": str(exc)}
