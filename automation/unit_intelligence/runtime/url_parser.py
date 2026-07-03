#!/usr/bin/env python3
"""Safe listing URL parser for Property Finder, Bayut, and Dubizzle.

This module parses public listing URLs and extracts structured metadata without
making any external network requests. It does not scrape portals or claim live
availability.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class ParsedListingUrl:
    portal: str
    listing_id: str | None
    url: str
    transaction: str | None  # sale, rent, plp (property listing page)
    property_type: str | None  # apartment, villa, townhouse, etc.
    area: str | None
    project: str | None
    building: str | None
    bedrooms: int | None
    slug: str | None
    confidence: str  # exact, partial, unknown
    parse_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "portal": self.portal,
            "listing_id": self.listing_id,
            "url": self.url,
            "transaction": self.transaction,
            "property_type": self.property_type,
            "area": self.area,
            "project": self.project,
            "building": self.building,
            "bedrooms": self.bedrooms,
            "slug": self.slug,
            "confidence": self.confidence,
            "parse_notes": self.parse_notes,
        }


_PROPERTY_TYPE_MAP: dict[str, str] = {
    "apartment": "apartment",
    "apartments": "apartment",
    "villa": "villa",
    "villas": "villa",
    "townhouse": "townhouse",
    "townhouses": "townhouse",
    "penthouse": "penthouse",
    "penthouses": "penthouse",
    "studio": "studio",
    "land": "land",
    "plot": "land",
    "office": "office",
    "shop": "retail",
    "warehouse": "warehouse",
    "commercial": "commercial",
}

_TRANSACTION_MAP: dict[str, str] = {
    "sale": "sale",
    "buy": "sale",
    "rent": "rent",
    "plp": "rent",  # property listing page; often rent by default on PF
    "property": "unknown",
}


_NUMBER_WORDS = {
    "studio": 0,
    "1-bedroom": 1,
    "1bed": 1,
    "2-bedroom": 2,
    "2bed": 2,
    "3-bedroom": 3,
    "3bed": 3,
    "4-bedroom": 4,
    "4bed": 4,
    "5-bedroom": 5,
    "5bed": 5,
}


def _extract_bedrooms_from_slug(slug: str) -> int | None:
    lowered = slug.lower().replace("-", " ")
    for token, value in _NUMBER_WORDS.items():
        if token in lowered or token.replace("-", "") in lowered:
            return value
    match = re.search(r"(\d+)-?\s*bed", lowered)
    if match:
        return int(match.group(1))
    return None


def _extract_property_type_from_slug(slug: str) -> str | None:
    """Extract property type using whole-word matching to avoid false positives."""
    lowered = slug.lower()
    # Sort longer keys first so "townhouse" beats "house" and we avoid matching "villa" inside "village".
    sorted_keys = sorted(_PROPERTY_TYPE_MAP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        pattern = r"\b" + re.escape(key) + r"\b"
        if re.search(pattern, lowered):
            return _PROPERTY_TYPE_MAP[key]
    return None


def _extract_area_from_slug(slug: str) -> str | None:
    """Extract area from PF-style slug: townhouse-for-rent-dubai-jvc-district-12-nakheel-..."""
    parts = slug.lower().split("-")
    area_parts: list[str] = []
    started = False
    skip_next = False
    stop_words = {
        "for",
        "rent",
        "sale",
        "buy",
        "dubai",
        "uae",
        "ref",
        "html",
    }
    for i, part in enumerate(parts):
        if skip_next:
            skip_next = False
            continue
        if part == "dubai":
            started = True
            continue
        if started:
            if part in stop_words:
                break
            # Keep district numbers with the area (e.g., district 12)
            if part == "district" and i + 1 < len(parts) and parts[i + 1].isdigit():
                area_parts.append(f"district {parts[i + 1]}")
                skip_next = True
                continue
            if part.isdigit() and part not in {"1", "2", "3", "4", "5"}:
                break
            area_parts.append(part)
    if area_parts:
        return " ".join(area_parts).title()
    return None


def _parse_propertyfinder(url: str, parsed: urlparse) -> ParsedListingUrl:
    notes: list[str] = []
    path = unquote(parsed.path).lower().strip("/")
    parts = [p for p in path.split("/") if p]

    transaction: str | None = None
    property_type: str | None = None
    area: str | None = None
    bedrooms: int | None = None
    listing_id: str | None = None
    slug: str | None = None
    confidence = "partial"

    if parts and parts[-1].endswith(".html"):
        slug = parts[-1][:-5]
    elif parts:
        slug = parts[-1]

    if slug:
        listing_match = re.search(r"-(\d{6,10})$", slug)
        if listing_match:
            listing_id = listing_match.group(1)
            notes.append("listing_id_extracted_from_slug")
        else:
            notes.append("listing_id_not_found_in_slug")

        # transaction from first path segment or slug
        if parts:
            if parts[0] in ("sale", "rent", "buy"):
                transaction = _TRANSACTION_MAP.get(parts[0])
            elif parts[0] == "plp":
                transaction = "rent"
                notes.append("transaction_inferred_from_plp")

        if transaction is None:
            if "for-sale" in slug or "buy" in slug:
                transaction = "sale"
            elif "for-rent" in slug or "rent" in slug:
                transaction = "rent"
            else:
                transaction = "unknown"
                notes.append("transaction_unknown")

        property_type = _extract_property_type_from_slug(slug)
        bedrooms = _extract_bedrooms_from_slug(slug)
        area = _extract_area_from_slug(slug)

    if listing_id and property_type and area:
        confidence = "exact"

    return ParsedListingUrl(
        portal="propertyfinder",
        listing_id=listing_id,
        url=url,
        transaction=transaction,
        property_type=property_type,
        area=area,
        project=None,
        building=None,
        bedrooms=bedrooms,
        slug=slug,
        confidence=confidence,
        parse_notes=notes,
    )


def _parse_bayut(url: str, parsed: urlparse) -> ParsedListingUrl:
    notes: list[str] = ["bayut_parser_stub"]
    path = unquote(parsed.path).lower().strip("/")
    parts = [p for p in path.split("/") if p]

    listing_id: str | None = None
    slug = parts[-1] if parts else None

    if slug:
        # Bayut URLs often end with a numeric ID or reference
        match = re.search(r"-(\d+)$", slug)
        if match:
            listing_id = match.group(1)
            notes.append("listing_id_extracted_from_slug")

    return ParsedListingUrl(
        portal="bayut",
        listing_id=listing_id,
        url=url,
        transaction=None,
        property_type=_extract_property_type_from_slug(slug or ""),
        area=None,
        project=None,
        building=None,
        bedrooms=_extract_bedrooms_from_slug(slug or ""),
        slug=slug,
        confidence="partial" if listing_id else "unknown",
        parse_notes=notes,
    )


def _parse_dubizzle(url: str, parsed: urlparse) -> ParsedListingUrl:
    notes: list[str] = ["dubizzle_parser_stub"]
    path = unquote(parsed.path).lower().strip("/")
    parts = [p for p in path.split("/") if p]

    listing_id: str | None = None
    slug = parts[-1] if parts else None

    if slug:
        match = re.search(r"-(\d+)$", slug)
        if match:
            listing_id = match.group(1)
            notes.append("listing_id_extracted_from_slug")

    return ParsedListingUrl(
        portal="dubizzle",
        listing_id=listing_id,
        url=url,
        transaction=None,
        property_type=_extract_property_type_from_slug(slug or ""),
        area=None,
        project=None,
        building=None,
        bedrooms=_extract_bedrooms_from_slug(slug or ""),
        slug=slug,
        confidence="partial" if listing_id else "unknown",
        parse_notes=notes,
    )


def parse_url(url: str) -> ParsedListingUrl:
    """Parse a listing URL and return structured metadata."""
    url = url.strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "propertyfinder" in host:
        return _parse_propertyfinder(url, parsed)
    if "bayut" in host:
        return _parse_bayut(url, parsed)
    if "dubizzle" in host:
        return _parse_dubizzle(url, parsed)

    return ParsedListingUrl(
        portal="unknown",
        listing_id=None,
        url=url,
        transaction=None,
        property_type=None,
        area=None,
        project=None,
        building=None,
        bedrooms=None,
        slug=None,
        confidence="unknown",
        parse_notes=["unsupported_portal"],
    )


def parse_urls(urls: list[str]) -> list[dict[str, Any]]:
    return [parse_url(url).to_dict() for url in urls]


if __name__ == "__main__":
    import json
    import sys

    sample = [
        "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78188849.html",
        "https://www.propertyfinder.ae/en/plp/rent/townhouse-for-rent-dubai-jumeirah-village-circle-district-12-nakheel-townhouses-78182876.html",
        "https://www.bayut.com/property/123456789",
        "https://www.dubizzle.com/property/123456789",
    ]
    if len(sys.argv) > 1:
        sample = sys.argv[1:]
    print(json.dumps(parse_urls(sample), indent=2, ensure_ascii=False))
