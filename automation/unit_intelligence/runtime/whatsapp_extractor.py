#!/usr/bin/env python3
"""Extract listing URLs and property clues from WhatsApp message text.

This module is text-only. It does not connect to WhatsApp, send messages, or
read chat databases. It takes a message string and returns structured property
clues for the ingestion queue.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from url_parser import parse_url, ParsedListingUrl


@dataclass
class ExtractedClues:
    source: str = "whatsapp"
    urls: list[ParsedListingUrl] = field(default_factory=list)
    phone_numbers: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    prices: list[int] = field(default_factory=list)
    bedroom_counts: list[int] = field(default_factory=list)
    areas_mentioned: list[str] = field(default_factory=list)
    projects_mentioned: list[str] = field(default_factory=list)
    raw_text: str = ""
    confidence: str = "partial"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "urls": [u.to_dict() for u in self.urls],
            "phone_numbers": self.phone_numbers,
            "emails": self.emails,
            "prices": self.prices,
            "bedroom_counts": self.bedroom_counts,
            "areas_mentioned": self.areas_mentioned,
            "projects_mentioned": self.projects_mentioned,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "notes": self.notes,
        }


_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:propertyfinder\.ae|bayut\.com|dubizzle\.com)/[^\s\)\]\"]+",
    re.IGNORECASE,
)

_PHONE_RE = re.compile(
    r"(?:\+?971\s?5\d{8}|05\d{8}|\+?971\s?4\d{7}|04\d{7})",
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_PRICE_RE = re.compile(
    r"(?:AED\s?|aed\s?|dh\s?)?(?:(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(K|M|million)?",
    re.IGNORECASE,
)

_BED_RE = re.compile(r"(\d)\s*\b(bed|br|bedroom|bedrooms)\b", re.IGNORECASE)

# Simple area/project keyword lists. In production these should be driven by the area_aliases.json.
_KNOWN_AREAS = [
    "jvc", "jumeirah village circle", "jumeirah village triangle", "jvt",
    "dubai marina", "marina", "dubai hills", "dubai hills estate",
    "palm jumeirah", "palm", "downtown dubai", "business bay", "motor city",
    "damac hills", "arabian ranches", "al barsha", "tecom", "barsha heights",
    "dubai silicon oasis", "dso", "meydan", "city walk", "jbr",
    "jumeirah beach residence", "jumeirah lakes towers", "jlt",
    "emirates hills", "the springs", "the meadows", "the lakes",
]


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _extract_prices(text: str) -> list[int]:
    prices: list[int] = []
    for match in _PRICE_RE.finditer(text):
        number_str = match.group(1).replace(",", "")
        multiplier = match.group(2)
        try:
            value = float(number_str)
        except ValueError:
            continue
        if multiplier:
            mult_lower = multiplier.lower()
            if mult_lower == "k":
                value *= 1_000
            elif mult_lower in {"m", "million"}:
                value *= 1_000_000
        if value >= 10_000:  # Filter out small numbers that are not prices
            prices.append(int(value))
    return sorted(set(prices))


def _extract_bedrooms(text: str) -> list[int]:
    beds = []
    for match in _BED_RE.finditer(text):
        beds.append(int(match.group(1)))
    # Also catch "studio"
    if re.search(r"\bstudio\b", text, re.IGNORECASE):
        beds.append(0)
    return sorted(set(beds))


def _extract_areas(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for area in _KNOWN_AREAS:
        if area in text_lower:
            found.append(area.title())
    return sorted(set(found))


def _extract_projects(text: str) -> list[str]:
    # Placeholder: project extraction is highly domain-specific.
    # A real implementation would load the project_aliases.json from KnowledgeBase/resolver/.
    return []


def extract_from_message(text: str) -> ExtractedClues:
    text = _normalize_whitespace(text)
    result = ExtractedClues(raw_text=text)

    urls = _URL_RE.findall(text)
    result.urls = [parse_url(url) for url in urls]

    result.phone_numbers = sorted(set(_PHONE_RE.findall(text)))
    result.emails = sorted(set(_EMAIL_RE.findall(text)))
    result.prices = _extract_prices(text)
    result.bedroom_counts = _extract_bedrooms(text)
    result.areas_mentioned = _extract_areas(text)
    result.projects_mentioned = _extract_projects(text)

    notes = []
    if result.urls:
        notes.append(f"found {len(result.urls)} listing url(s)")
    if result.phone_numbers:
        notes.append(f"found {len(result.phone_numbers)} phone number(s)")
    if result.prices:
        notes.append(f"found {len(result.prices)} price(s)")
    if result.bedroom_counts:
        notes.append(f"found {len(result.bedroom_counts)} bedroom count(s)")
    if result.areas_mentioned:
        notes.append(f"found {len(result.areas_mentioned)} area(s)")
    result.notes = notes or ["no property clues detected"]

    if result.urls:
        result.confidence = "partial" if all(u.listing_id for u in result.urls) else "unknown"
    else:
        result.confidence = "unknown" if not result.areas_mentioned else "partial"

    return result


def extract_from_messages(messages: list[str]) -> list[dict[str, Any]]:
    return [extract_from_message(msg).to_dict() for msg in messages]


if __name__ == "__main__":
    import json
    import sys

    sample = [
        "Hi Omar, check this 2 bed in JVC AED 1.2M https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html call me 0551234567",
    ]
    if len(sys.argv) > 1:
        sample = sys.argv[1:]
    print(json.dumps(extract_from_messages(sample), indent=2, ensure_ascii=False))
