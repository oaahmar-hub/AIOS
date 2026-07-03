#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import sqlite3
from statistics import median
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from client_property_proposal_runtime import build as build_proposal
from client_property_proposal_runtime import export_visual_artifacts
from client_property_proposal_runtime import rank_candidates


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports" / "realty_agent_runs"
KB_ROOT = AIOS_ROOT / "KnowledgeBase"
ACQUISITION_INDEX = KB_ROOT / "acquisition_index.csv"
PROPERTY_DB = KB_ROOT / "Property_Master_Database.sqlite"
LISTING_IDENTITY_MAP = KB_ROOT / "resolver" / "listing_identity_map.csv"
DEFAULT_CASE_NAME = "realty-agent-run"
PROPERTYFINDER_SCRIPT = Path("/Users/hassanka/plugins/home-sweet-home-real-estate/scripts/fetch_propertyfinder_listings.py")
if str(KB_ROOT) not in sys.path:
    sys.path.insert(0, str(KB_ROOT))

from property_recommendation_agent import PropertyRecommendationAgent


URL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}

AREA_ALIASES = {
    "dubai south": ["dubai south", "emaar south", "residential district", "logistics city", "aviation city", "azizi venice"],
    "jvc": ["jvc", "jumeirah village circle", "jumeirah village circle jvc"],
    "jlt": ["jlt", "jumeirah lake towers", "jumeirah lakes towers"],
    "jvt": ["jvt", "jumeirah village triangle", "jumeirah village triangle jvt"],
    "dubai marina": ["dubai marina", "marina"],
    "business bay": ["business bay"],
    "dubai hills": ["dubai hills", "dubai hills estate"],
    "palm jumeirah": ["palm jumeirah", "the palm", "palm"],
    "downtown dubai": ["downtown dubai", "downtown"],
    "dubai creek harbour": ["dubai creek harbour", "creek harbour", "creek harbor"],
    "bluewaters": ["bluewaters", "bluewaters island"],
    "city walk": ["city walk"],
    "arabian ranches": ["arabian ranches"],
    "dubai harbour": ["dubai harbour", "emaar beachfront", "dubai harbour emaar beachfront"],
    "sobha hartland": ["sobha hartland", "hartland"],
    "al furjan": ["al furjan"],
    "arjan": ["arjan"],
    "dubai sports city": ["dubai sports city"],
    "dubailand": ["dubailand", "dubai land"],
    "dubai islands": ["dubai islands"],
    "meydan": ["meydan"],
    "damac hills": ["damac hills"],
}

AREA_BAYUT_SLUGS = {
    "dubai south": "dubai-south",
    "jvc": "jumeirah-village-circle-jvc",
    "jlt": "jumeirah-lake-towers-jlt",
    "jvt": "jumeirah-village-triangle-jvt",
    "dubai marina": "dubai-marina",
    "business bay": "business-bay",
    "dubai hills": "dubai-hills-estate",
    "palm jumeirah": "palm-jumeirah",
    "downtown dubai": "downtown-dubai",
    "dubai creek harbour": "dubai-creek-harbour",
    "bluewaters": "bluewaters-island",
    "city walk": "city-walk",
    "arabian ranches": "arabian-ranches",
    "dubai harbour": "dubai-harbour",
    "sobha hartland": "sobha-hartland",
    "al furjan": "al-furjan",
    "arjan": "arjan",
    "dubai sports city": "dubai-sports-city",
    "dubailand": "dubailand",
    "dubai islands": "dubai-islands",
    "meydan": "meydan-city",
    "damac hills": "damac-hills",
}

PROPERTYFINDER_AREA_SLUGS = {
    "dubai marina": "dubai-marina",
    "dubai hills": "dubai-hills-estate",
    "jvc": "jumeirah-village-circle",
    "jlt": "jumeirah-lake-towers",
    "jvt": "jumeirah-village-triangle",
    "business bay": "business-bay",
    "palm jumeirah": "palm-jumeirah",
    "downtown dubai": "downtown-dubai",
    "dubai creek harbour": "dubai-creek-harbour",
    "bluewaters": "bluewaters",
    "city walk": "city-walk",
    "arabian ranches": "arabian-ranches",
    "dubai harbour": "dubai-harbour",
    "sobha hartland": "sobha-hartland",
    "al furjan": "al-furjan",
    "arjan": "arjan",
    "dubai sports city": "dubai-sports-city",
    "dubailand": "dubailand",
    "dubai islands": "dubai-islands",
    "meydan": "meydan",
    "damac hills": "damac-hills",
}

CURATED_PROPERTYFINDER_LISTING_URLS = {
    ("business bay", "office", "rent"): [
        "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-business-bay-the-citadel-tower-105977060.html",
        "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-business-bay-xl-tower-105992828.html",
        "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-business-bay-the-burlington-106866048.html",
    ],
    ("business bay", "office", "buy"): [
        "https://www.propertyfinder.ae/en/plp/commercial-buy/office-space-for-sale-dubai-business-bay-the-opus-16295781.html",
        "https://www.propertyfinder.ae/en/plp/commercial-buy/office-space-for-sale-dubai-business-bay-77-shades-16063324.html",
    ],
}

USE_CASE_KEYWORDS = {
    "veterinary_clinic": ["veterinary", "vet clinic", "veterinary clinic", "pet clinic", "animal clinic"],
    "office": ["office", "workspace", "hq"],
    "retail": ["shop", "retail", "storefront", "showroom"],
    "warehouse": ["warehouse", "storage", "industrial"],
    "clinic": ["clinic", "medical", "healthcare", "dental"],
    "apartment": ["apartment", "flat", "1 bedroom", "2 bedroom", "3 bedroom", "studio"],
    "villa": ["villa", "standalone"],
    "townhouse": ["townhouse", "town house"],
}

INTERNAL_PROPERTY_TYPE_HINTS = {
    "veterinary_clinic": ["shop", "office"],
    "clinic": ["shop", "office"],
    "retail": ["shop"],
    "office": ["office"],
    "warehouse": ["warehouse"],
    "apartment": ["apartment"],
    "villa": ["villa"],
    "townhouse": ["townhouse"],
}

REQUEST_STRATEGIES = {
    ("dubai south", "veterinary_clinic"): {
        "proposal_title": "Dubai South Veterinary Clinic Proposal - Confidential Client",
        "market_highlights": [
            "Dubai South remains a strategic growth corridor tied to Al Maktoum International Airport, free zone business setup, and mixed-use expansion.",
            "Dubai South officially positions Business Park offices around airport, port, and free-zone access.",
            "Dubai South public communications confirm Residential District amenities that support recurring neighborhood demand."
        ],
        "compliance_gates": [
            "MOCCAE issues the veterinary establishment license through the official service directory.",
            "Ministerial Resolution No. 34 of 2026 requires the relevant business license before a veterinary establishment can be created.",
            "Ministerial Resolution No. 27 of 2026 sets health and technical requirements for veterinary establishments.",
            "Dubai Municipality Veterinary Services Section remains a practical local coordination touchpoint."
        ],
        "sales_pitch_template": "Lead with {primary} as the strongest clinic-fit launch option. Keep {secondary} as the lower-entry long-term alternative and {third} as the immediate operations fallback if the client prioritizes opening speed over frontage.",
        "next_steps": [
            "Confirm allowed veterinary-clinic use against the specific unit category before commercial commitment.",
            "Request floor plans, service-charge exposure, fit-out manual, and parking allocation for the top two options.",
            "Sequence approvals: business license, MOCCAE veterinary establishment path, municipality technical approvals, and Civil Defence fit-out scope.",
            "Prepare negotiation plan: reservation/payment-plan strategy for retail or lease strategy for the office fallback."
        ],
        "public_candidates": [
            {
                "title": "5% Discount | VAT Waiver | 30/70 Payment Plan | Direct From Developer",
                "commercial_mode": "sale",
                "price_aed": 5550000,
                "property_type": "shop",
                "size_sqft": 1502,
                "building": "Azizi Venice 14",
                "area": "Azizi Venice, Dubai South, Dubai",
                "developer": "Azizi Developments",
                "availability": "off-plan",
                "delivery_timeline": "Handover Q2 2026",
                "payment_plan": "30/70",
                "launch_mode": "near-term",
                "footfall_profile": "high",
                "parking_profile": "strong",
                "license_fit": "probable",
                "clinic_fit": "high",
                "summary": "Best flagship retail play for a branded veterinary clinic with visible frontage, customer access, and room for treatment flow.",
                "pros": [
                    "Retail frontage is the cleanest format for a client-facing veterinary clinic.",
                    "1,502 sqft can support reception, consult rooms, treatment, waiting, pharmacy, and grooming add-ons.",
                    "Near-term handover gives a credible launch path without waiting for 2027-2028 stock."
                ],
                "cons": [
                    "Higher capital commitment than the office fallback.",
                    "Still requires fit-out and approval lead time before trading."
                ],
                "source_url": "https://www.bayut.com/for-sale/shops/dubai/dubai-south/azizi-venice/",
                "source_links": [
                    "https://www.bayut.com/for-sale/shops/dubai/dubai-south/azizi-venice/",
                    "https://www.bayut.com/property-market-analysis/transactions/sale/shops/dubai/dubai-south/azizi-venice/azizi-venice-14/"
                ],
                "map_query": "Azizi Venice 14 Dubai South Dubai"
            },
            {
                "title": "Premium Retail Space | Great ROI | Flexible Plan | Dubai South",
                "commercial_mode": "sale",
                "price_aed": 4500000,
                "property_type": "shop",
                "size_sqft": 1237,
                "building": "Enre Residence by Imtiaz",
                "area": "Residential District, Dubai South, Dubai",
                "developer": "Imtiaz Developments",
                "availability": "off-plan",
                "delivery_timeline": "Handover Q1 2028",
                "payment_plan": "60/40",
                "launch_mode": "future",
                "footfall_profile": "high",
                "parking_profile": "strong",
                "license_fit": "probable",
                "clinic_fit": "high",
                "summary": "Balanced long-term retail option on size versus entry ticket, but with a slower revenue start because of later handover.",
                "pros": [
                    "1,237 sqft is efficient for a compact neighborhood clinic.",
                    "Lower capital outlay than the larger Azizi Venice flagship while staying in exact Dubai South catchment.",
                    "Residential District context aligns with repeat local pet-owner demand."
                ],
                "cons": [
                    "Later handover delays revenue compared with the top-ranked option.",
                    "Longer wait means more exposure to delivery timing."
                ],
                "source_url": "https://www.bayut.com/for-sale/shops/dubai/dubai-south/residential-district/",
                "source_links": [
                    "https://www.bayut.com/for-sale/shops/dubai/dubai-south/residential-district/",
                    "https://www.bayut.com/for-sale/off-plan/commercial/dubai/dubai-south/"
                ],
                "map_query": "Enre Residence by Imtiaz Residential District Dubai South"
            },
            {
                "title": "Bright | Fully Fitted Space | Partitioned",
                "commercial_mode": "rent",
                "price_aed": 350000,
                "price_term": "yearly",
                "property_type": "office",
                "size_sqft": 2490,
                "building": "Dubai South Business Park B3, The Avenue, Logistics City",
                "area": "Dubai South, Dubai",
                "developer": "Dubai South",
                "availability": "ready",
                "delivery_timeline": "Immediate occupancy",
                "payment_plan": "lease",
                "launch_mode": "immediate",
                "footfall_profile": "medium",
                "parking_profile": "strong",
                "license_fit": "needs_confirmation",
                "clinic_fit": "medium",
                "summary": "Best immediate operating option if the client wants to open in 2026 rather than wait for off-plan delivery.",
                "pros": [
                    "Fastest route to launch because the space is already fitted and partitioned.",
                    "Large floor plate can absorb reception, consultation rooms, treatment, staff, and storage.",
                    "Business Park positioning benefits from airport, port, and free-zone connectivity."
                ],
                "cons": [
                    "Office classification means clinical use needs stricter approval confirmation.",
                    "Stronger operationally than as a storefront brand play."
                ],
                "source_url": "https://www.bayut.com/to-rent/offices/dubai/dubai-south/",
                "source_links": [
                    "https://www.bayut.com/to-rent/offices/dubai/dubai-south/",
                    "https://www.dubaisouth.ae/en/work/commercial-property/offices"
                ],
                "map_query": "Dubai South Business Park B3 The Avenue Logistics City Dubai South"
            }
        ],
        "source_register": [
            {"label": "Bayut - Offices for Rent in Dubai South", "url": "https://www.bayut.com/to-rent/offices/dubai/dubai-south/", "date": "June 26, 2026"},
            {"label": "Bayut - Shops for Sale in Residential District, Dubai South", "url": "https://www.bayut.com/for-sale/shops/dubai/dubai-south/residential-district/", "date": "June 26, 2026"},
            {"label": "Bayut - Shops for Sale in Azizi Venice", "url": "https://www.bayut.com/for-sale/shops/dubai/dubai-south/azizi-venice/", "date": "June 26, 2026"},
            {"label": "Dubai South - Office Space in Dubai South | Free Zone Offices & Business Park", "url": "https://www.dubaisouth.ae/en/work/commercial-property/offices", "date": "June 26, 2026"},
            {"label": "Dubai South newsroom - residential district amenities and resident scale", "url": "https://www.dubaisouth.ae/en/newsroom/dubai-south-launches-south-square-sells-out-first-tower-within-three-hours", "date": "June 26, 2026"},
            {"label": "MOCCAE service directory - Issue a Veterinary Establishment License", "url": "https://site.moccae.gov.ae/en/our-services/service-directory.aspx?DisableResponsive=1&mainCategory=272%3FmainCategory%3D272&subCategory=284", "date": "June 26, 2026"},
            {"label": "MOCCAE - Ministerial Resolution No. 34 of 2026", "url": "https://moccae.gov.ae/assets/download/74f65cf7/Ministerial%20Resolution%20No.%2034%20of%202026%20.pdf.aspx", "date": "June 26, 2026"},
            {"label": "MOCCAE - Ministerial Resolution No. 27 of 2026", "url": "https://moccae.gov.ae/assets/download/561a85a6/Ministerial%20Resolution%20No.%2027%20of%202026%20Concerning%20the%20Health%20and%20Technical%20Requirements%20for%20Veterinary%20Establishments%20.pdf.aspx", "date": "June 26, 2026"}
        ],
    }
}

GENERIC_AREA_SOURCE_MAP = {
    "dubai south": {
        "office": [
            {"label": "Bayut - Offices for Rent in Dubai South", "url": "https://www.bayut.com/to-rent/offices/dubai/dubai-south/"},
            {"label": "Bayut - Offices for Rent in Logistics City", "url": "https://www.bayut.com/to-rent/offices/dubai/dubai-south/logistics-city/"},
            {"label": "Property Finder - Office Space for Rent in Dubai South Business Park", "url": "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-dubai-south-dubai-world-central-business-park-97364276.html"},
        ],
        "commercial": [
            {"label": "Bayut - Commercial Properties for Rent in Dubai South", "url": "https://www.bayut.com/to-rent/commercial/dubai/dubai-south/"},
            {"label": "Dubai South - Office Space in Dubai South | Free Zone Offices & Business Park", "url": "https://www.dubaisouth.ae/en/work/commercial-property/offices"},
        ],
        "shop": [
            {"label": "Bayut - Shops for Sale in Residential District, Dubai South", "url": "https://www.bayut.com/for-sale/shops/dubai/dubai-south/residential-district/"},
            {"label": "Bayut - Shops for Sale in Azizi Venice, Dubai South", "url": "https://www.bayut.com/for-sale/shops/dubai/dubai-south/azizi-venice/"},
        ],
        "warehouse": [
            {"label": "Bayut - Warehouses for Rent in Dubai South", "url": "https://www.bayut.com/to-rent/warehouses/dubai/dubai-south/"},
            {"label": "Bayut - Warehouses for Rent in Logistics City, Dubai South", "url": "https://www.bayut.com/to-rent/warehouses/dubai/dubai-south/logistics-city/"},
            {"label": "Bayut - Commercial Properties for Rent in Dubai South", "url": "https://www.bayut.com/to-rent/commercial/dubai/dubai-south/"},
        ],
    }
}


@dataclass
class RequestProfile:
    raw_request: str
    normalized_request: str
    source_mode: str
    area: str
    use_case: str
    property_preference: str
    bedroom_preference: str
    bathroom_preference: str
    view_preference: str
    floor_preference: str
    parking_preference: str
    feature_preferences: list[str]
    furnishing_preference: str
    readiness_preference: str
    intent: str
    source_url: str
    max_price_aed: float
    min_size_sqft: float
    max_size_sqft: float
    target_size_sqft: float


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "realty-agent-run"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _slugify_area(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalize(text)).strip("-")


def _clean_area_fragment(text: str) -> str:
    cleaned = _normalize(re.sub(r"[|/]+", ";", str(text or "")))
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"\buae\b", " ", cleaned)
    cleaned = re.sub(r"\bdubai,\s*dubai\b", "dubai", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;-")
    return cleaned


def _split_area_fragments(text: str) -> list[str]:
    cleaned = _clean_area_fragment(text)
    if not cleaned:
        return []
    parts = re.split(r"\s*;\s*|\s*,\s*", cleaned)
    out: list[str] = []
    for part in parts:
        item = part.strip()
        if not item or item in {"dubai", "unknown", "parking", "city view", "internal road", "garden & community", "community park & pool"}:
            continue
        out.append(item)
    return out


def _dynamic_area_aliases() -> dict[str, list[str]]:
    aliases: dict[str, set[str]] = {key: set(values) | {key} for key, values in AREA_ALIASES.items()}
    expansion_map = {
        "jumeirah village circle": "jvc",
        "jumeirah village triangle": "jvt",
        "jumeirah lake towers": "jlt",
        "jumeirah lakes towers": "jlt",
        "dubai creek harbour": "dubai creek harbour",
        "creek harbour": "dubai creek harbour",
        "creek harbor": "dubai creek harbour",
        "palm jumeirah": "palm jumeirah",
        "dubai hills estate": "dubai hills",
        "dubai hills": "dubai hills",
        "business bay": "business bay",
        "dubai marina": "dubai marina",
        "dubai harbour": "dubai harbour",
        "emaar beachfront": "dubai harbour",
        "arabian ranches": "arabian ranches",
        "city walk": "city walk",
        "sobha hartland": "sobha hartland",
        "al furjan": "al furjan",
        "arjan": "arjan",
        "dubai sports city": "dubai sports city",
        "dubai land": "dubailand",
        "dubailand": "dubailand",
        "dubai islands": "dubai islands",
        "meydan": "meydan",
        "damac hills": "damac hills",
    }

    if ACQUISITION_INDEX.exists():
        try:
            with ACQUISITION_INDEX.open(newline="", encoding="utf-8", errors="ignore") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    for fragment in _split_area_fragments(row.get("detected_area", "")):
                        canonical = expansion_map.get(fragment, fragment)
                        if len(canonical) < 3:
                            continue
                        aliases.setdefault(canonical, set()).add(fragment)
        except Exception:
            pass

    out: dict[str, list[str]] = {}
    for canonical, values in aliases.items():
        ordered = sorted({value.strip() for value in values if value and len(value.strip()) >= 3}, key=lambda item: (-len(item), item))
        if ordered:
            out[canonical] = ordered
    return out


_AREA_ALIAS_CACHE: dict[str, list[str]] | None = None


def _all_area_aliases() -> dict[str, list[str]]:
    global _AREA_ALIAS_CACHE
    if _AREA_ALIAS_CACHE is None:
        _AREA_ALIAS_CACHE = _dynamic_area_aliases()
    return _AREA_ALIAS_CACHE


def _infer_area(text: str) -> str:
    low = _normalize(text)
    matches: list[tuple[int, str]] = []
    for canonical, aliases in _all_area_aliases().items():
        for alias in aliases:
            if alias and alias in low:
                matches.append((len(alias), canonical))
                break
    if matches:
        matches.sort(reverse=True)
        return matches[0][1]
    return ""


def _infer_use_case(text: str) -> str:
    low = _normalize(text)
    for use_case, keywords in USE_CASE_KEYWORDS.items():
        if any(keyword in low for keyword in keywords):
            return use_case
    return "general_property"


def _infer_property_preference(text: str) -> str:
    low = _normalize(text)
    if any(word in low for word in ["shop", "retail", "storefront", "showroom"]):
        return "shop"
    if "office" in low:
        return "office"
    if "warehouse" in low:
        return "warehouse"
    if any(word in low for word in ["apartment", "flat", "studio"]):
        return "apartment"
    if "townhouse" in low or "town house" in low:
        return "townhouse"
    if "villa" in low:
        return "villa"
    if "clinic" in low:
        return "commercial"
    return "any"


def _infer_bedroom_preference(text: str) -> str:
    low = _normalize(text)
    match = re.search(r"\b(\d+)\s*bed(?:room)?\b", low)
    if match:
        return match.group(1)
    if "studio" in low:
        return "studio"
    return ""


def _infer_bathroom_preference(text: str) -> str:
    low = _normalize(text)
    match = re.search(r"\b(\d+)\s*bath(?:room)?s?\b", low)
    if match:
        return match.group(1)
    return ""


def _infer_view_preference(text: str) -> str:
    low = _normalize(text)
    if "palm view" in low:
        return "palm"
    if "sea view" in low or "ocean view" in low:
        return "sea"
    if "marina view" in low:
        return "marina"
    if "golf view" in low:
        return "golf"
    if "city view" in low:
        return "city"
    if "park view" in low:
        return "park"
    return ""


def _infer_floor_preference(text: str) -> str:
    low = _normalize(text)
    if "high floor" in low or "top floor" in low:
        return "high"
    if "low floor" in low or "lower floor" in low:
        return "low"
    if "mid floor" in low or "middle floor" in low:
        return "mid"
    return ""


def _infer_parking_preference(text: str) -> str:
    low = _normalize(text)
    if any(phrase in low for phrase in ["no parking", "without parking", "parking not required"]):
        return "not_required"
    if any(phrase in low for phrase in ["with parking", "parking included", "need parking", "needs parking", "require parking", "requires parking"]):
        return "required"
    return ""


def _infer_feature_preferences(text: str) -> list[str]:
    low = _normalize(text)
    feature_keywords = {
        "upgraded": ["upgraded", "fully upgraded", "renovated", "refurbished"],
        "corner": ["corner unit", "corner plot", "corner"],
        "balcony": ["balcony"],
        "terrace": ["terrace"],
        "duplex": ["duplex"],
        "brand_new": ["brand new"],
    }
    found: list[str] = []
    for canonical, keywords in feature_keywords.items():
        if any(keyword in low for keyword in keywords):
            found.append(canonical)
    return found


def _infer_furnishing_preference(text: str) -> str:
    low = _normalize(text)
    if "unfurnished" in low or "not furnished" in low:
        return "unfurnished"
    if "semi furnished" in low or "semi-furnished" in low:
        return "semi_furnished"
    if "fully furnished" in low or "furnished" in low:
        return "furnished"
    return ""


def _infer_readiness_preference(text: str) -> str:
    low = _normalize(text)
    if any(phrase in low for phrase in ["vacant", "ready now", "move in now", "move-in now", "immediate occupancy", "immediate move in"]):
        return "immediate"
    if any(phrase in low for phrase in ["ready", "fitted", "turnkey", "brand new"]):
        return "ready"
    if any(phrase in low for phrase in ["off plan", "off-plan", "handover", "launching soon"]):
        return "off_plan"
    return ""


def _infer_intent(text: str) -> str:
    low = _normalize(text)
    if any(word in low for word in ["rent", "lease", "yearly"]):
        return "rent"
    if any(word in low for word in ["buy", "purchase", "sale", "invest", "investment"]):
        return "buy"
    if any(word in low for word in ["under", "below", "budget", "max", "up to"]):
        if any(word in low for word in ["apartment", "flat", "studio", "villa", "townhouse", "town house"]):
            return "buy"
    if any(word in low for word in ["open", "launch", "start", "clinic", "business"]):
        return "business_setup"
    return "discovery"


def _parse_max_price_aed(text: str) -> float:
    low = _normalize(text)
    patterns = [
        r"(?:under|below|max|up to|budget(?: of)?|budget is)\s*(aed\s*)?(\d+(?:[\d,]*)(?:\.\d+)?)\s*([mk]|million|k)?",
        r"(?:under|below|max|up to|budget(?: of)?|budget is)\s*(\d+(?:[\d,]*)(?:\.\d+)?)\s*(aed|dirham|dirhams)?\s*([mk]|million|k)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, low)
        if not match:
            continue
        groups = [g for g in match.groups() if g]
        number_text = next((g for g in groups if re.search(r"\d", g)), "")
        unit_text = next((g for g in groups if g in {"m", "k", "million"}), "")
        if not number_text:
            continue
        value = float(number_text.replace(",", ""))
        if unit_text in {"m", "million"}:
            value *= 1_000_000
        elif unit_text == "k":
            value *= 1_000
        return value
    return 0.0


def _parse_size_preferences(text: str) -> tuple[float, float, float]:
    low = _normalize(text)

    def _to_float(value: str) -> float:
        return float(value.replace(",", "").strip())

    between = re.search(
        r"\bbetween\s+(\d[\d,]*(?:\.\d+)?)\s+(?:and|to)\s+(\d[\d,]*(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square\s*feet|sf)\b",
        low,
    )
    if between:
        first = _to_float(between.group(1))
        second = _to_float(between.group(2))
        return min(first, second), max(first, second), 0.0

    around = re.search(
        r"\b(?:around|about|approx(?:imately)?|near)\s+(\d[\d,]*(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square\s*feet|sf)\b",
        low,
    )
    if around:
        return 0.0, 0.0, _to_float(around.group(1))

    minimum = re.search(
        r"\b(?:at least|min(?:imum)?|from)\s+(\d[\d,]*(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square\s*feet|sf)\b",
        low,
    )
    if minimum:
        return _to_float(minimum.group(1)), 0.0, 0.0

    maximum = re.search(
        r"\b(?:under|below|max|up to)\s+(\d[\d,]*(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square\s*feet|sf)\b",
        low,
    )
    if maximum:
        return 0.0, _to_float(maximum.group(1)), 0.0

    exact = re.search(r"\b(\d[\d,]*(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square\s*feet|sf)\b", low)
    if exact:
        return 0.0, 0.0, _to_float(exact.group(1))

    return 0.0, 0.0, 0.0


def _parse_url_context(url: str) -> dict[str, str]:
    if not url:
        return {}
    parsed = urlparse(url)
    path = parsed.path.lower()
    bits = [bit for bit in re.split(r"[^a-z0-9]+", path) if bit]
    joined = " ".join(bits)
    area = _infer_area(joined)
    intent = "rent" if "rent" in bits else "buy" if ("sale" in bits or "buy" in bits) else ""
    property_preference = "shop" if "shop" in bits or "retail" in bits else "office" if "office" in bits else "commercial" if "commercial" in bits else ""
    return {
        "platform": parsed.netloc.lower(),
        "joined": joined,
        "area": area,
        "intent": intent,
        "property_preference": property_preference,
    }


def build_request_profile(request_text: str = "", source_url: str = "", voice_transcript: str = "") -> RequestProfile:
    text = request_text.strip() or voice_transcript.strip()
    url_context = _parse_url_context(source_url)
    if not text and source_url:
        text = url_context.get("joined", "")
    normalized = _normalize(text)
    area = _infer_area(text) or url_context.get("area", "")
    use_case = _infer_use_case(text)
    property_preference = _infer_property_preference(text) or url_context.get("property_preference", "") or "any"
    bedroom_preference = _infer_bedroom_preference(text)
    bathroom_preference = _infer_bathroom_preference(text)
    view_preference = _infer_view_preference(text)
    floor_preference = _infer_floor_preference(text)
    parking_preference = _infer_parking_preference(text)
    feature_preferences = _infer_feature_preferences(text)
    furnishing_preference = _infer_furnishing_preference(text)
    readiness_preference = _infer_readiness_preference(text)
    intent = _infer_intent(text) or url_context.get("intent", "") or "discovery"
    max_price_aed = _parse_max_price_aed(text)
    min_size_sqft, max_size_sqft, target_size_sqft = _parse_size_preferences(text)
    if intent == "discovery" and property_preference in {"apartment", "villa", "townhouse"}:
        intent = url_context.get("intent", "") or "buy"
    source_mode = "voice" if voice_transcript.strip() else "url" if source_url else "text"
    return RequestProfile(
        raw_request=text,
        normalized_request=normalized,
        source_mode=source_mode,
        area=area,
        use_case=use_case,
        property_preference=property_preference,
        bedroom_preference=bedroom_preference,
        bathroom_preference=bathroom_preference,
        view_preference=view_preference,
        floor_preference=floor_preference,
        parking_preference=parking_preference,
        feature_preferences=feature_preferences,
        furnishing_preference=furnishing_preference,
        readiness_preference=readiness_preference,
        intent=intent,
        source_url=source_url,
        max_price_aed=max_price_aed,
        min_size_sqft=min_size_sqft,
        max_size_sqft=max_size_sqft,
        target_size_sqft=target_size_sqft,
    )


def _load_propertyfinder_script():
    spec = importlib.util.spec_from_file_location("fetch_propertyfinder_listings", PROPERTYFINDER_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fetch_url_html(url: str) -> str:
    req = urllib.request.Request(url, headers=URL_HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", "ignore")


def _extract_next_data(html: str) -> dict[str, Any] | None:
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _extract_html_metadata(html: str) -> dict[str, str]:
    def match(pattern: str) -> str:
        found = re.search(pattern, html, re.I | re.S)
        return re.sub(r"\s+", " ", found.group(1)).strip() if found else ""

    return {
        "title": match(r"<title>(.*?)</title>"),
        "description": match(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)'),
        "og_title": match(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)'),
        "og_description": match(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)'),
        "og_image": match(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)'),
        "twitter_image": match(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'),
    }


def _propertyfinder_broker_url_tokens(url: str) -> set[str]:
    path = urlparse(url).path.lower()
    last = path.rsplit("/", 1)[-1]
    return {bit for bit in re.split(r"[^a-z0-9]+", last) if bit and bit not in {"en", "broker"}}


def _propertyfinder_broker_match_score(url_tokens: set[str], broker: dict[str, Any]) -> tuple[int, float]:
    broker_tokens = {
        bit
        for bit in re.split(
            r"[^a-z0-9]+",
            " ".join(
                [
                    str(broker.get("urlSlug") or ""),
                    str(broker.get("name") or ""),
                    str(broker.get("location") or ""),
                ]
            ).lower(),
        )
        if bit
    }
    shared = len(url_tokens & broker_tokens)
    ranking = float(broker.get("ranking") or 0)
    return shared, ranking


def _propertyfinder_broker_candidate_from_record(
    source_page_url: str,
    broker: dict[str, Any],
    schema_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    name = str(broker.get("name") or "Property Finder Broker").strip()
    location = str(broker.get("location") or "").strip()
    address = str(broker.get("address") or "").strip()
    total_properties = int(broker.get("totalProperties") or 0)
    residential_rent = int(broker.get("propertiesResidentialForRentCount") or 0)
    residential_sale = int(broker.get("propertiesResidentialForSaleCount") or 0)
    commercial_rent = int(broker.get("propertiesCommercialForRentCount") or 0)
    commercial_sale = int(broker.get("propertiesCommercialForSaleCount") or 0)
    total_residential = residential_rent + residential_sale
    total_commercial = commercial_rent + commercial_sale
    if total_commercial > total_residential:
        property_type = "commercial"
    elif residential_sale >= residential_rent:
        property_type = "apartment"
    else:
        property_type = "residential"
    if residential_rent and not residential_sale and not total_commercial:
        commercial_mode = "rent"
    elif residential_sale and not residential_rent and not total_commercial:
        commercial_mode = "sale"
    elif total_commercial and not total_residential:
        commercial_mode = "mixed"
    else:
        commercial_mode = "mixed"
    schema_item = schema_lookup.get(str(broker.get("urlSlug") or "").strip().lower()) or schema_lookup.get(name.lower()) or {}
    profile_url = str(schema_item.get("url") or "").strip()
    if not profile_url:
        slug = str(broker.get("urlSlug") or "").strip()
        client_id = broker.get("clientId") or broker.get("id") or ""
        profile_url = f"https://www.propertyfinder.ae/en/broker/{slug}-{client_id}".rstrip("-") if slug else source_page_url
    summary_bits = []
    if total_properties:
        summary_bits.append(f"{total_properties} live portfolio listings")
    if total_residential:
        summary_bits.append(f"{total_residential} residential")
    if total_commercial:
        summary_bits.append(f"{total_commercial} commercial")
    summary = ", ".join(summary_bits) if summary_bits else "Live broker portfolio discovered from Property Finder."
    return {
        "title": f"{name} Broker Portfolio",
        "area": location or address or "Dubai",
        "building": address or location or "Dubai",
        "developer": name,
        "source_url": profile_url,
        "source_links": [source_page_url, profile_url] if profile_url != source_page_url else [source_page_url],
        "commercial_mode": commercial_mode,
        "property_type": property_type,
        "price_aed": 0,
        "size_sqft": 0,
        "availability": "live_broker_portfolio",
        "delivery_timeline": "Current public broker profile",
        "launch_mode": "current",
        "footfall_profile": "medium" if total_commercial else "unknown",
        "parking_profile": "unknown",
        "license_fit": "needs_confirmation",
        "fit_label": "medium",
        "summary": summary,
        "pros": [
            "Live public broker profile sourced directly from Property Finder.",
            f"Portfolio mix shows {total_properties or 'multiple'} active listings linked to this broker.",
        ],
        "cons": [
            "Broker portfolio page is not a single property listing and still needs drill-down before client commitment.",
            "Live property-level pricing and unit fit must be confirmed from the chosen listing.",
        ],
        "map_query": address or location or name,
        "broker_name": name,
        "broker_location": location,
        "broker_address": address,
        "broker_portfolio_counts": {
            "total_properties": total_properties,
            "residential_rent": residential_rent,
            "residential_sale": residential_sale,
            "commercial_rent": commercial_rent,
            "commercial_sale": commercial_sale,
        },
    }


def _propertyfinder_broker_candidates_from_next_data(url: str, payload: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    page_props = payload.get("props", {}).get("pageProps", {})
    brokers = ((page_props.get("brokers") or {}).get("data")) or []
    if not brokers:
        return []
    schema_lookup: dict[str, dict[str, Any]] = {}
    for block in page_props.get("brokerSearchSchema") or []:
        for item in block.get("itemListElement") or []:
            name = str(item.get("name") or "").strip().lower()
            item_url = str(item.get("url") or "").strip()
            slug = item_url.rstrip("/").rsplit("/", 1)[-1].lower() if item_url else ""
            if name and name not in schema_lookup:
                schema_lookup[name] = item
            if slug and slug not in schema_lookup:
                schema_lookup[slug] = item
    url_tokens = _propertyfinder_broker_url_tokens(url)
    ordered = sorted(
        brokers,
        key=lambda broker: (
            -_propertyfinder_broker_match_score(url_tokens, broker)[0],
            -_propertyfinder_broker_match_score(url_tokens, broker)[1],
            str(broker.get("name") or ""),
        ),
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for broker in ordered:
        candidate = _propertyfinder_broker_candidate_from_record(url, broker, schema_lookup)
        source_url = str(candidate.get("source_url") or "")
        if not source_url or source_url in seen:
            continue
        out.append(candidate)
        seen.add(source_url)
        if len(out) >= limit:
            break
    return out


def _extract_bayut_runtime_payload(html: str) -> dict[str, Any] | None:
    marker = "window.state = "
    idx = html.find(marker)
    if idx == -1:
        return None
    text = html[idx + len(marker):]
    brace = 0
    in_str = False
    escaped = False
    end = None
    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                brace += 1
            elif ch == "}":
                brace -= 1
                if brace == 0:
                    end = i + 1
                    break
    if end is None:
        return None
    try:
        return json.loads(text[:end])
    except json.JSONDecodeError:
        return None


def gather_internal_evidence(profile: RequestProfile) -> tuple[list[str], list[dict[str, Any]]]:
    evidence: list[str] = []
    trail: list[dict[str, Any]] = []
    area_terms = _all_area_aliases().get(profile.area, [profile.area]) if profile.area else []
    matched_rows = 0
    matched_images: list[str] = []

    if ACQUISITION_INDEX.exists():
        with ACQUISITION_INDEX.open(newline="", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                haystack = " ".join(
                    [
                        row.get("filename", ""),
                        row.get("detected_area", ""),
                        row.get("detected_project", ""),
                        row.get("source_chat_group", ""),
                        row.get("focus_terms", ""),
                    ]
                ).lower()
                if area_terms and any(term in haystack for term in area_terms if term):
                    matched_rows += 1
                    copied = row.get("duplicate_of_or_copied_to", "")
                    if "/images/" in copied and len(matched_images) < 3:
                        matched_images.append(copied)
        if matched_rows:
            evidence.append(f"AIOS acquisition index contains {matched_rows} rows matching the area signal '{profile.area}'.")
            trail.append({"source": str(ACQUISITION_INDEX), "matched_rows": matched_rows, "sample_images": matched_images})
        if matched_images:
            evidence.append("Internal AIOS media evidence includes area-matched image records from broker/inventory channels.")

    if PROPERTY_DB.exists() and profile.area:
        con = sqlite3.connect(str(PROPERTY_DB))
        cur = con.cursor()
        query = """
            select count(*)
            from inventory_rows ir
            left join areas a on ir.area_id = a.area_id
            where lower(ifnull(a.name,'')) like ? or lower(ir.raw_json) like ?
        """
        like = f"%{profile.area}%"
        db_count = cur.execute(query, (like, like)).fetchone()[0]
        con.close()
        if db_count:
            evidence.append(f"Property master database contains {db_count} raw rows linked to {profile.area}.")
            trail.append({"source": str(PROPERTY_DB), "matched_rows": int(db_count)})

    return evidence, trail


def _profile_internal_property_types(profile: RequestProfile) -> list[str]:
    hinted = list(INTERNAL_PROPERTY_TYPE_HINTS.get(profile.use_case, []))
    if profile.property_preference and profile.property_preference not in {"any", "commercial"}:
        hinted.insert(0, profile.property_preference)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in hinted:
        if item and item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def _profile_bedrooms_int(profile: RequestProfile) -> int | None:
    if not profile.bedroom_preference:
        return None
    if profile.bedroom_preference == "studio":
        return 0
    try:
        return int(profile.bedroom_preference)
    except Exception:
        return None


def _internal_match_to_candidate(match: Any, profile: RequestProfile) -> dict[str, Any]:
    property_type = str(match.property_type or "unknown").lower()
    price_term = "yearly" if profile.intent == "rent" else ""
    score_tier = "high" if float(match.score or 0) >= 85 else "medium" if float(match.score or 0) >= 60 else "strategic"
    return {
        "title": match.project or "Internal Inventory Match",
        "commercial_mode": profile.intent,
        "price_aed": match.price or 0,
        "price_term": price_term,
        "property_type": property_type,
        "size_sqft": 0,
        "building": match.project or match.area or "Internal Match",
        "area": match.area or profile.area.title(),
        "developer": match.developer or "",
        "availability": match.status or match.inventory_type or "internal_inventory_match",
        "delivery_timeline": "Internal inventory database match",
        "launch_mode": "internal",
        "footfall_profile": "unknown",
        "parking_profile": "unknown",
        "license_fit": "needs_confirmation",
        "fit_label": score_tier,
        "summary": f"Internal AIOS inventory match from {match.source_group} with score {match.score:.1f}.",
        "pros": [
            "Directly retrieved from the AIOS internal property database.",
            f"Matched area: {match.area or 'unknown'}",
            f"Matched type: {match.property_type or 'unknown'}",
        ],
        "cons": [
            "Full media, map pin, and live commercial terms still need confirmation before client send."
        ],
        "source_url": "",
        "source_links": [],
        "map_query": match.area or match.project or profile.area or "Dubai",
        "internal_source_file": match.file_name,
        "internal_source_group": match.source_group,
        "internal_match_score": round(float(match.score or 0), 1),
    }


def _internal_match_is_low_quality(match: dict[str, Any]) -> bool:
    project = str(match.get("project") or "").strip().lower()
    area = str(match.get("area") or "").strip().lower()
    return project in {"", "unknown"} and area in {"", "unknown"}


def _internal_asset_match_to_candidate(asset: dict[str, Any], profile: RequestProfile) -> dict[str, Any]:
    file_type = str(asset.get("file_type") or "internal_asset").lower()
    title_base = asset.get("detected_project") or asset.get("detected_area") or asset.get("source_chat_group") or "Internal acquisition signal"
    source_file = asset.get("duplicate_of_or_copied_to") or asset.get("filename") or ""
    return {
        "title": f"Internal Signal - {title_base}",
        "commercial_mode": profile.intent,
        "price_aed": 0,
        "price_term": "",
        "property_type": profile.property_preference if profile.property_preference != "any" else "unknown",
        "size_sqft": 0,
        "building": asset.get("detected_project") or asset.get("detected_area") or "Internal Asset",
        "area": asset.get("detected_area") or profile.area.title(),
        "developer": asset.get("developer_signal") or "",
        "availability": f"internal_{file_type}_signal",
        "delivery_timeline": "Internal acquisition evidence",
        "launch_mode": "internal",
        "footfall_profile": "unknown",
        "parking_profile": "unknown",
        "license_fit": "needs_confirmation",
        "fit_label": "strategic" if file_type in {"jpg", "png"} else "medium",
        "summary": f"Internal {file_type.upper()} acquisition tagged to {asset.get('detected_area') or profile.area} from {asset.get('source_chat_group') or 'AIOS knowledge intake'}.",
        "pros": [
            "Recovered from AIOS internal acquisition index.",
            f"Source channel: {asset.get('source_chat_group') or 'AIOS intake'}",
            f"File type: {file_type.upper()}",
        ],
        "cons": [
            "This is an internal evidence signal, not a fully structured live listing."
        ],
        "source_url": "",
        "source_links": [],
        "map_query": asset.get("detected_area") or profile.area or "Dubai",
        "internal_source_file": source_file,
        "internal_source_group": asset.get("source_chat_group") or "",
        "internal_match_score": round(float(asset.get("signal_score") or 0), 1),
        "hero_image_url": source_file if file_type in {"jpg", "jpeg", "png", "webp"} else "",
    }


def gather_internal_asset_signals(profile: RequestProfile, limit: int = 8) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    if not ACQUISITION_INDEX.exists() or not profile.area:
        return [], {}, []

    area_aliases = AREA_ALIASES.get(profile.area, [profile.area])
    use_case = profile.use_case.replace("_", " ")
    rows: list[dict[str, Any]] = []
    with ACQUISITION_INDEX.open(newline="", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            haystack = " | ".join(str(row.get(k, "")) for k in reader.fieldnames).lower()
            if not any(alias in haystack for alias in area_aliases if alias):
                continue
            signal_score = 35.0
            file_type = str(row.get("file_type") or "").lower()
            if file_type in {"xlsx", "csv"}:
                signal_score += 35.0
            elif file_type in {"pdf"}:
                signal_score += 20.0
            elif file_type in {"jpg", "png", "jpeg"}:
                signal_score += 10.0
            if "inventory" in str(row.get("focus_terms") or "").lower():
                signal_score += 20.0
            if use_case and any(token in haystack for token in use_case.split()):
                signal_score += 10.0
            rows.append(
                {
                    "filename": row.get("filename") or "",
                    "file_type": row.get("file_type") or "",
                    "detected_area": row.get("detected_area") or profile.area.title(),
                    "detected_project": row.get("detected_project") or "",
                    "source_chat_group": row.get("source_chat_group") or "",
                    "focus_terms": row.get("focus_terms") or "",
                    "duplicate_of_or_copied_to": row.get("duplicate_of_or_copied_to") or "",
                    "developer_signal": next((item.strip() for item in str(row.get("detected_project") or "").split(";") if item.strip()), ""),
                    "signal_score": signal_score,
                }
            )

    rows.sort(key=lambda item: (-float(item["signal_score"]), item["file_type"], item["filename"]))
    deduped: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for row in rows:
        key = row.get("duplicate_of_or_copied_to") or row.get("filename") or ""
        if key in seen_paths:
            continue
        seen_paths.add(key)
        deduped.append(row)
        if len(deduped) >= limit:
            break

    file_type_counts: dict[str, int] = {}
    source_groups: list[str] = []
    projects: list[str] = []
    for row in rows:
        ft = str(row.get("file_type") or "").lower()
        file_type_counts[ft] = file_type_counts.get(ft, 0) + 1
        group = str(row.get("source_chat_group") or "").strip()
        if group and group not in source_groups and len(source_groups) < 4:
            source_groups.append(group)
        project = str(row.get("detected_project") or "").strip()
        if project and project not in projects and len(projects) < 6:
            projects.append(project)

    snapshot = {
        "match_count": len(rows),
        "asset_match_count": len(deduped),
        "file_type_counts": file_type_counts,
        "top_projects": projects,
        "source_groups": source_groups,
    }
    evidence = []
    if rows:
        evidence.append(f"AIOS acquisition index recovered {len(rows)} internal source assets tied to {profile.area}.")
    if file_type_counts:
        type_line = ", ".join(f"{count} {kind}" for kind, count in sorted(file_type_counts.items(), key=lambda item: (-item[1], item[0]))[:4])
        evidence.append(f"Internal source mix: {type_line}.")
    return deduped, snapshot, evidence


def _attach_internal_images(public_candidates: list[dict[str, Any]], image_assets: list[dict[str, Any]]) -> None:
    image_paths: list[str] = []
    for asset in image_assets:
        file_type = str(asset.get("file_type") or "").lower()
        if file_type not in {"jpg", "jpeg", "png", "webp"}:
            continue
        path = str(asset.get("duplicate_of_or_copied_to") or asset.get("filename") or "").strip()
        if not path or not Path(path).exists():
            continue
        if path not in image_paths:
            image_paths.append(path)
    if not image_paths:
        return

    image_index = 0
    for candidate in public_candidates:
        if candidate.get("hero_image_url"):
            continue
        if image_index >= len(image_paths):
            break
        candidate["hero_image_url"] = image_paths[image_index]
        image_index += 1


def gather_internal_inventory_matches(profile: RequestProfile, limit: int = 8) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    if not PROPERTY_DB.exists():
        return [], {}, ["AIOS internal property database is not available in this workspace."]

    agent = PropertyRecommendationAgent(PROPERTY_DB)
    property_types = _profile_internal_property_types(profile) or [""]
    bedrooms = _profile_bedrooms_int(profile)
    raw_matches: list[Any] = []
    seen: set[tuple[str, str, str, int]] = set()
    for property_type in property_types:
        matches = agent.search(
            area=profile.area.title() if profile.area else "",
            bedrooms=bedrooms,
            property_type=property_type,
            query_text=profile.raw_request,
            ready_only=profile.intent in {"rent", "business_setup"},
            limit=max(limit, 6),
        )
        for match in matches:
            key = (match.project, match.area, match.property_type, int(match.price or 0))
            if key in seen:
                continue
            seen.add(key)
            raw_matches.append(match)

    if not raw_matches:
        fallback_matches = agent.search(
            area=profile.area.title() if profile.area else "",
            bedrooms=bedrooms,
            property_type="",
            query_text=profile.raw_request,
            ready_only=profile.intent in {"rent", "business_setup"},
            limit=max(limit, 6),
        )
        for match in fallback_matches:
            key = (match.project, match.area, match.property_type, int(match.price or 0))
            if key in seen:
                continue
            seen.add(key)
            raw_matches.append(match)

    raw_matches.sort(key=lambda item: (-float(item.score or 0), float(item.price or 10**12), item.project))
    raw_matches = raw_matches[:limit]
    priced = [int(item.price) for item in raw_matches if item.price]
    snapshot = {
        "match_count": len(raw_matches),
        "priced_match_count": len(priced),
        "median_price_aed": int(median(priced)) if priced else 0,
        "min_price_aed": min(priced) if priced else 0,
        "max_price_aed": max(priced) if priced else 0,
        "top_projects": [item.project for item in raw_matches[:3] if item.project],
        "property_types": sorted({str(item.property_type or "").lower() for item in raw_matches if item.property_type}),
    }
    evidence: list[str] = []
    if raw_matches:
        evidence.append(f"AIOS property database returned {len(raw_matches)} scored internal matches for the brief.")
    if priced:
        evidence.append(
            f"Internal price band across matched records is AED {min(priced):,} to AED {max(priced):,}, with median AED {int(median(priced)):,}."
        )
    matches = [
        {
            "project": item.project,
            "area": item.area,
            "developer": item.developer,
            "bedrooms": item.bedrooms,
            "property_type": item.property_type,
            "inventory_type": item.inventory_type,
            "status": item.status,
            "price_aed": item.price or 0,
            "source_group": item.source_group,
            "file_name": item.file_name,
            "score": round(float(item.score or 0), 1),
        }
        for item in raw_matches
    ]
    asset_matches, asset_snapshot, asset_evidence = gather_internal_asset_signals(profile, limit=limit)
    if not matches and asset_matches:
        matches = [
            {
                "project": item.get("detected_project") or item.get("filename") or "Internal acquisition signal",
                "area": item.get("detected_area") or profile.area.title(),
                "developer": item.get("developer_signal") or "",
                "bedrooms": "",
                "property_type": item.get("file_type") or "asset",
                "inventory_type": "acquisition_index",
                "status": "internal_signal",
                "price_aed": 0,
                "source_group": item.get("source_chat_group") or "",
                "file_name": item.get("duplicate_of_or_copied_to") or item.get("filename") or "",
                "score": round(float(item.get("signal_score") or 0), 1),
                "signal_type": "internal_asset",
            }
            for item in asset_matches
        ]
    if asset_snapshot:
        if not snapshot.get("match_count"):
            snapshot = asset_snapshot
        else:
            snapshot["asset_match_count"] = asset_snapshot.get("asset_match_count", 0)
            snapshot["file_type_counts"] = asset_snapshot.get("file_type_counts", {})
            if not snapshot.get("top_projects"):
                snapshot["top_projects"] = asset_snapshot.get("top_projects", [])
            snapshot["source_groups"] = asset_snapshot.get("source_groups", [])
    for item in asset_evidence:
        if item not in evidence:
            evidence.append(item)
    return matches, snapshot, evidence


def provider_propertyfinder_broker(url: str) -> list[dict[str, Any]]:
    module = _load_propertyfinder_script()
    if module is not None:
        try:
            schema = module.load_schema(url)
            listings = module.extract_listings(schema, 6)
        except Exception:
            listings = []
        else:
            out = []
            for listing in listings:
                price_text = getattr(listing, "price", "")
                size_text = getattr(listing, "size", "")
                price_num = _first_number(price_text)
                size_num = _first_number(size_text)
                property_type = _infer_listing_property_type(f"{listing.title} {listing.url}")
                out.append(
                    {
                        "title": listing.title,
                        "area": listing.location,
                        "building": listing.location,
                        "source_url": listing.url,
                        "source_links": [url, listing.url],
                        "commercial_mode": "rent" if "year" in price_text.lower() or "month" in price_text.lower() else "sale",
                        "property_type": property_type,
                        "price_aed": price_num,
                        "size_sqft": size_num,
                        "availability": "live_broker_listing",
                        "delivery_timeline": "Current public broker listing",
                        "launch_mode": "current",
                        "footfall_profile": "unknown",
                        "parking_profile": "unknown",
                        "license_fit": "needs_confirmation",
                        "fit_label": "medium",
                        "summary": "Live Property Finder broker listing pulled directly from the broker-detail-schema.",
                        "pros": ["Live public listing extracted directly from Property Finder broker page."],
                        "cons": ["Specific use approval and exact suitability still need review."],
                        "map_query": listing.location or listing.title,
                    }
                )
            if out:
                return out
    try:
        html = _fetch_url_html(url)
    except Exception:
        return []
    payload = _extract_next_data(html)
    if not payload:
        return []
    return _propertyfinder_broker_candidates_from_next_data(url, payload, limit=6)


def provider_propertyfinder_search_page(url: str, limit: int = 6) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        html = _fetch_url_html(url)
    except Exception:
        return [], []
    payload = _extract_next_data(html)
    if not payload:
        return [], []
    page_props = payload.get("props", {}).get("pageProps", {})
    listings = page_props.get("searchResult", {}).get("listings", [])
    if not listings:
        property_result = (page_props.get("propertyResult") or {}).get("property") or {}
        if property_result:
            return provider_propertyfinder_listing_page_from_payload(property_result, url), []
    out: list[dict[str, Any]] = []
    for item in listings[:limit]:
        prop = item.get("property") or {}
        if not prop:
            continue
        location = prop.get("location") or {}
        price = prop.get("price") or {}
        size = prop.get("size") or {}
        share_url = prop.get("share_url") or ""
        title = str(prop.get("title") or "").strip()
        area = str(location.get("full_name") or location.get("path_name") or "").strip()
        property_type = _infer_listing_property_type(str(prop.get("property_type") or ""))
        price_value = prop.get("price", {}).get("value") or 0
        period = price.get("period") or ""
        size_value = size.get("value") or 0
        offering_type = str(prop.get("offering_type") or "").lower()
        share_url_lc = share_url.lower()
        if "sale" in offering_type or period == "sell" or "/buy/" in share_url_lc:
            commercial_mode = "sale"
        elif period in {"yearly", "monthly", "weekly", "daily"}:
            commercial_mode = "rent"
        else:
            commercial_mode = "discovery"
        image_medium = ""
        images = prop.get("images") or []
        if images and isinstance(images[0], dict):
            image_medium = images[0].get("medium") or images[0].get("small") or ""
        out.append(
            {
                "title": title or area or "Property Finder Result",
                "area": area,
                "building": area,
                "source_url": share_url or url,
                "source_links": [url, share_url] if share_url else [url],
                "commercial_mode": commercial_mode,
                "property_type": property_type,
                "price_aed": price_value,
                "price_term": period,
                "size_sqft": size_value,
                "availability": "live_search_result",
                "delivery_timeline": "Current public search result",
                "launch_mode": "current",
                "footfall_profile": "unknown",
                "parking_profile": "unknown",
                "license_fit": "needs_confirmation",
                "fit_label": "medium",
                "summary": "Live Property Finder search result extracted from page data.",
                "pros": ["Live public listing extracted from Property Finder search results."],
                "cons": ["Specific terms and fit should still be verified before client send."],
                "map_query": area or title,
                "hero_image_url": image_medium,
                "bedrooms": str(prop.get("bedrooms") or ""),
                "bathrooms": str(prop.get("bathrooms") or ""),
                "reference": str(prop.get("reference") or ""),
            }
        )
    market_notes: list[str] = []
    location_insights = ((page_props.get("serpWidgetData") or {}).get("location") or {}).get("priceInsights") or []
    price_range = next((x.get("value") for x in location_insights if x.get("type") == "priceRange"), "")
    avg_price = next((x for x in location_insights if x.get("type") == "avgPrice"), None)
    avg_psf = next((x for x in location_insights if x.get("type") == "avgPricePerSqft"), None)
    rental_yield = next((x.get("value") for x in location_insights if x.get("type") == "rentalYield"), "")
    rental_yield_value = _first_percent(rental_yield)
    if price_range:
        market_notes.append(f"Property Finder area range currently shows {price_range}.")
    if avg_price:
        avg_line = f"Property Finder average asking price is {avg_price.get('value')}"
        if avg_price.get("changePercent") is not None:
            avg_line += f", with change of {avg_price['changePercent']:.1f}%."
        market_notes.append(avg_line)
    if avg_psf:
        psf_line = f"Average asking price per sqft is {avg_psf.get('value')}"
        if avg_psf.get("changePercent") is not None:
            psf_line += f", with change of {avg_psf['changePercent']:.1f}%."
        market_notes.append(psf_line)
    if rental_yield:
        market_notes.append(f"Reported rental yield signal is {rental_yield}.")
    if rental_yield_value is not None:
        for row in out:
            if row.get("commercial_mode") == "sale":
                row["gross_yield_percent"] = rental_yield_value
    return out, market_notes


def _profile_propertyfinder_tokens(profile: RequestProfile) -> list[str]:
    property_label = profile.property_preference if profile.property_preference not in {"any", "commercial"} else profile.use_case
    mapping = {
        "office": ["office-space"],
        "retail": ["shop-for-rent", "shop-for-sale", "show-room"],
        "shop": ["shop-for-rent", "shop-for-sale", "show-room"],
        "warehouse": ["warehouse"],
        "clinic": ["office-space", "shop-for-rent", "shop-for-sale", "show-room"],
        "veterinary_clinic": ["office-space", "shop-for-rent", "shop-for-sale", "show-room"],
        "apartment": ["apartment-for-rent", "apartment-for-sale"],
        "villa": ["villa-for-rent", "villa-for-sale"],
        "townhouse": ["townhouse-for-rent", "townhouse-for-sale"],
    }
    return mapping.get(property_label, [])


def _profile_area_url_tokens(profile: RequestProfile) -> list[str]:
    tokens = []
    pf_slug = _propertyfinder_area_slug(profile.area) if profile.area else ""
    if pf_slug:
        tokens.append(pf_slug)
    if profile.area:
        tokens.append(_slugify_area(profile.area))
    return [token for token in tokens if token]


def _url_matches_market_intent(url: str, profile: RequestProfile) -> bool:
    market_intent = _effective_market_intent(profile)
    if market_intent == "rent":
        return "commercial-rent" in url or "/rent/" in url
    if market_intent == "buy":
        return "commercial-buy" in url or "/buy/" in url
    return True


def provider_propertyfinder_local_corpus(profile: RequestProfile, limit: int = 3) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    if not LISTING_IDENTITY_MAP.exists() or not profile.area:
        return [], [], []

    area_tokens = _profile_area_url_tokens(profile)
    property_tokens = _profile_propertyfinder_tokens(profile)
    if not area_tokens:
        return [], [], []

    def collect_urls(require_intent_match: bool) -> list[str]:
        found: list[str] = []
        seen_urls: set[str] = set()
        with LISTING_IDENTITY_MAP.open(encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                url = ((row.get("property_finder_url") or row.get("listing_url") or "")).strip().rstrip("*#")
                url_lc = url.lower()
                if not url or "propertyfinder.ae" not in url_lc:
                    continue
                if not any(token in url_lc for token in area_tokens):
                    continue
                if property_tokens and not any(token in url_lc for token in property_tokens):
                    continue
                if require_intent_match and not _url_matches_market_intent(url_lc, profile):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                found.append(url)
                if len(found) >= limit:
                    break
        return found

    matched_urls = collect_urls(require_intent_match=True)
    if not matched_urls:
        matched_urls = collect_urls(require_intent_match=False)

    candidates: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    notes: list[str] = []
    for url in matched_urls:
        rows, market_notes = provider_propertyfinder_search_page(url, limit=3)
        if not rows:
            continue
        for row in rows[:2]:
            if not any(existing.get("source_url") == row.get("source_url") for existing in candidates):
                candidates.append(row)
        sources.append(_source_row("Property Finder local corpus listing", url))
        for note in market_notes:
            if note not in notes:
                notes.append(note)
        if len(candidates) >= max(3, limit):
            break

    if candidates:
        notes.insert(0, "Structured Property Finder listing pages were recovered from the local public URL corpus when live area-search routing was unavailable.")
        if matched_urls and not any(_url_matches_market_intent(url.lower(), profile) for url in matched_urls):
            notes.append("Closest available Property Finder corpus matches were sale-side listings, so they are being used as market intelligence until a rent-side commercial match is available.")
    return candidates[: max(3, limit)], sources, notes


def provider_propertyfinder_curated_listing_fallback(profile: RequestProfile, limit: int = 3) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    market_intent = _effective_market_intent(profile)
    urls = CURATED_PROPERTYFINDER_LISTING_URLS.get((profile.area, profile.property_preference, market_intent), [])
    if not urls and profile.property_preference == "commercial":
        urls = CURATED_PROPERTYFINDER_LISTING_URLS.get((profile.area, profile.use_case, market_intent), [])
    if not urls:
        return [], [], []

    candidates: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    notes: list[str] = ["Curated direct Property Finder listing pages were used because area-level commercial search routing is incomplete for this market."]
    for url in urls:
        rows, market_notes = provider_propertyfinder_search_page(url, limit=2)
        if not rows:
            continue
        for row in rows[:2]:
            if not any(existing.get("source_url") == row.get("source_url") for existing in candidates):
                candidates.append(row)
        sources.append(_source_row("Property Finder curated direct listing", url))
        for note in market_notes:
            if note not in notes:
                notes.append(note)
        if len(candidates) >= limit:
            break
    return candidates[:limit], sources, notes


def provider_propertyfinder_listing_page_from_payload(prop: dict[str, Any], url: str) -> list[dict[str, Any]]:
    if not prop:
        return []
    location = prop.get("location") or {}
    price = prop.get("price") or {}
    size = prop.get("size") or {}
    share_url = prop.get("share_url") or url
    title = str(prop.get("title") or "").strip()
    area = str(location.get("full_name") or location.get("path_name") or "").strip()
    property_type = _infer_listing_property_type(str(prop.get("property_type") or ""))
    price_value = price.get("value") or 0
    period = price.get("period") or ""
    size_value = size.get("value") or 0
    offering_type = str(prop.get("offering_type") or "").lower()
    share_url_lc = str(share_url).lower()
    if "sale" in offering_type or period == "sell" or "/buy/" in share_url_lc:
        commercial_mode = "sale"
    elif period in {"yearly", "monthly", "weekly", "daily"} or "rent" in offering_type:
        commercial_mode = "rent"
    else:
        commercial_mode = "discovery"
    image_medium = ""
    images = prop.get("images") or {}
    if isinstance(images, dict):
        property_images = images.get("property") or []
        if property_images and isinstance(property_images[0], dict):
            image_medium = property_images[0].get("medium") or property_images[0].get("small") or ""
    return [
        {
            "title": title or area or "Property Finder Listing",
            "area": area,
            "building": area,
            "source_url": share_url or url,
            "source_links": [url, share_url] if share_url and share_url != url else [url],
            "commercial_mode": commercial_mode,
            "property_type": property_type,
            "price_aed": price_value,
            "price_term": period,
            "size_sqft": size_value,
            "availability": "live_listing_page",
            "delivery_timeline": "Current public listing page",
            "launch_mode": "current",
            "footfall_profile": "unknown",
            "parking_profile": "unknown",
            "license_fit": "needs_confirmation",
            "fit_label": "medium",
            "summary": "Live Property Finder listing extracted directly from a property page.",
            "pros": ["Live public listing extracted directly from Property Finder property page."],
            "cons": ["Specific terms and fit should still be verified before client send."],
            "map_query": area or title,
            "hero_image_url": image_medium,
            "bedrooms": str(prop.get("bedrooms") or ""),
            "bathrooms": str(prop.get("bathrooms") or ""),
            "reference": str(prop.get("reference") or ""),
            "developer": str(((prop.get("broker") or {}).get("name")) or ((prop.get("agent") or {}).get("name")) or ""),
        }
    ]


def build_propertyfinder_search_url(profile: RequestProfile) -> str:
    area_slug = _propertyfinder_area_slug(profile.area) if profile.area else ""
    if not area_slug:
        return ""
    if profile.property_preference == "apartment" and profile.intent == "rent":
        if profile.bedroom_preference and profile.bedroom_preference != "studio":
            return f"https://www.propertyfinder.ae/en/rent/dubai/{profile.bedroom_preference}-bedroom-apartments-for-rent-{area_slug}.html"
        if profile.bedroom_preference == "studio":
            return f"https://www.propertyfinder.ae/en/rent/dubai/studio-apartments-for-rent-{area_slug}.html"
        return f"https://www.propertyfinder.ae/en/rent/dubai/apartments-for-rent-{area_slug}.html"
    if profile.property_preference == "apartment" and profile.intent in {"buy", "investment"}:
        if profile.bedroom_preference and profile.bedroom_preference != "studio":
            return f"https://www.propertyfinder.ae/en/buy/dubai/{profile.bedroom_preference}-bedroom-apartments-for-sale-{area_slug}.html"
        if profile.bedroom_preference == "studio":
            return f"https://www.propertyfinder.ae/en/buy/dubai/studio-apartments-for-sale-{area_slug}.html"
        return f"https://www.propertyfinder.ae/en/buy/dubai/apartments-for-sale-{area_slug}.html"
    if profile.property_preference == "villa" and profile.intent == "rent":
        return f"https://www.propertyfinder.ae/en/rent/dubai/villas-for-rent-{area_slug}.html"
    if profile.property_preference == "villa" and profile.intent in {"buy", "investment"}:
        return f"https://www.propertyfinder.ae/en/buy/dubai/villas-for-sale-{area_slug}.html"
    if profile.property_preference == "townhouse" and profile.intent == "rent":
        return f"https://www.propertyfinder.ae/en/rent/dubai/townhouses-for-rent-{area_slug}.html"
    if profile.property_preference == "townhouse" and profile.intent in {"buy", "investment"}:
        return f"https://www.propertyfinder.ae/en/buy/dubai/townhouses-for-sale-{area_slug}.html"
    return ""


def provider_propertyfinder_profile_search(profile: RequestProfile) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    url = build_propertyfinder_search_url(profile)
    if url:
        candidates, market_notes = provider_propertyfinder_search_page(url)
        if candidates:
            bedroom_prefix = f"{profile.bedroom_preference} bedroom " if profile.bedroom_preference and profile.bedroom_preference != "studio" else ""
            if profile.bedroom_preference == "studio":
                bedroom_prefix = "studio "
            label = f"Property Finder - {bedroom_prefix}{profile.property_preference.title()} search in {profile.area.title()}"
            return candidates, [{"label": label, "url": url, "date": datetime.now(timezone.utc).strftime("%B %d, %Y")}], market_notes

    corpus_candidates, corpus_sources, corpus_notes = provider_propertyfinder_local_corpus(profile)
    if corpus_candidates:
        return corpus_candidates, corpus_sources, corpus_notes

    curated_candidates, curated_sources, curated_notes = provider_propertyfinder_curated_listing_fallback(profile)
    if curated_candidates:
        return curated_candidates, curated_sources, curated_notes

    fallback_urls = []
    for item in _area_source_options(profile):
        if "propertyfinder.ae" in item.get("url", ""):
            fallback_urls.append(item)
    seen = set()
    deduped_urls = []
    for item in fallback_urls:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped_urls.append(item)
    all_candidates: list[dict[str, Any]] = []
    source_rows: list[dict[str, str]] = []
    for item in deduped_urls[:4]:
        candidates, _notes = provider_propertyfinder_search_page(item["url"], limit=3)
        if candidates:
            all_candidates.extend(candidates[:3])
            source_rows.append({"label": item["label"], "url": item["url"], "date": datetime.now(timezone.utc).strftime("%B %d, %Y")})
    if not all_candidates:
        return [], [], []
    bedroom_prefix = f"{profile.bedroom_preference} bedroom " if profile.bedroom_preference and profile.bedroom_preference != "studio" else ""
    if profile.bedroom_preference == "studio":
        bedroom_prefix = "studio "
    if not source_rows:
        label = f"Property Finder - {bedroom_prefix}{profile.property_preference.title()} search in {profile.area.title()}"
        source_rows = [{"label": label, "url": url or "", "date": datetime.now(timezone.utc).strftime("%B %d, %Y")}]
    return all_candidates[:6], source_rows, []


def _extend_unique_candidates(
    target: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    max_candidates: int = 6,
) -> None:
    seen = {
        (
            str(item.get("source_url") or "").strip(),
            str(item.get("title") or "").strip(),
        )
        for item in target
    }
    for candidate in additions:
        key = (
            str(candidate.get("source_url") or "").strip(),
            str(candidate.get("title") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        target.append(candidate)
        if len(target) >= max_candidates:
            break


def provider_direct_url(profile: RequestProfile) -> list[dict[str, Any]]:
    if not profile.source_url:
        return []
    info = _parse_url_context(profile.source_url)
    title = " ".join(word.capitalize() for word in info.get("joined", "").split()[:12]) or "Public Listing URL"
    area = info.get("area") or profile.area or "Unknown"
    property_type = info.get("property_preference") or profile.property_preference or "unknown"
    return [
        {
            "title": title,
            "area": area.title() if area else "Unknown",
            "building": title,
            "source_url": profile.source_url,
            "source_links": [profile.source_url],
            "commercial_mode": info.get("intent") or profile.intent or "discovery",
            "property_type": property_type,
            "price_aed": 0,
            "size_sqft": 0,
            "availability": "url_supplied",
            "delivery_timeline": "Depends on live listing details",
            "launch_mode": "current",
            "footfall_profile": "unknown",
            "parking_profile": "unknown",
            "license_fit": "needs_confirmation",
            "fit_label": "medium" if property_type == profile.property_preference else "unknown",
            "summary": "Candidate generated from the supplied listing/search URL context when exact structured listing fields are not directly exposed.",
            "pros": ["Accepts direct Bayut/Property Finder style URLs as input."],
            "cons": ["Exact listing metrics may require a richer provider or authenticated browser session."],
            "map_query": area,
        }
    ]


def provider_generic_url_metadata(profile: RequestProfile) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    if not profile.source_url:
        return [], [], []
    try:
        html = _fetch_url_html(profile.source_url)
    except Exception:
        return [], [], []

    meta = _extract_html_metadata(html)
    title = meta.get("og_title") or meta.get("title") or ""
    description = meta.get("og_description") or meta.get("description") or ""
    hero_image = meta.get("og_image") or meta.get("twitter_image") or ""
    joined_text = " ".join([title, description, profile.raw_request, profile.source_url]).strip()
    if not joined_text:
        return [], [], []

    inferred_area = _infer_area(joined_text) or profile.area
    inferred_type = _infer_listing_property_type(joined_text)
    property_type = (
        profile.property_preference
        if profile.property_preference not in {"any", "commercial"}
        else inferred_type if inferred_type != "unknown" else "commercial"
    )
    candidate = {
        "title": title or "External Property Page",
        "area": inferred_area.title() if inferred_area else "Dubai",
        "building": title or inferred_area.title() if inferred_area else "Dubai",
        "source_url": profile.source_url,
        "source_links": [profile.source_url],
        "commercial_mode": _effective_market_intent(profile),
        "property_type": property_type,
        "price_aed": 0,
        "size_sqft": 0,
        "availability": "external_page_metadata",
        "delivery_timeline": "Current external page metadata",
        "launch_mode": "current",
        "footfall_profile": "unknown",
        "parking_profile": "unknown",
        "license_fit": "needs_confirmation",
        "fit_label": "medium",
        "summary": description or "Page metadata was extracted directly from the supplied external URL.",
        "pros": [
            "Direct metadata extracted from the supplied URL.",
            "Useful when the page is outside Bayut or Property Finder routing support.",
        ],
        "cons": [
            "This page may be a market or developer page rather than a single live listing.",
            "Exact pricing and unit-level details still need confirmation before client send.",
        ],
        "map_query": inferred_area.title() if inferred_area else title or "Dubai",
        "hero_image_url": hero_image,
    }
    notes = []
    if description:
        notes.append("External page metadata was used to enrich the supplied URL with title, description, and media signals.")
    return [candidate], [_source_row("User supplied external page", profile.source_url)], notes


def expand_public_candidates_from_profile(profile: RequestProfile, existing_candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    if not profile.area:
        return [], [], []

    existing_urls = {str(item.get("source_url") or "").strip() for item in existing_candidates if item.get("source_url")}
    candidates: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    notes: list[str] = []

    pf_candidates, pf_sources, pf_notes = provider_propertyfinder_profile_search(profile)
    for row in pf_candidates:
        source_url = str(row.get("source_url") or "").strip()
        if source_url and source_url in existing_urls:
            continue
        candidates.append(row)
    for source in pf_sources:
        if source.get("url") and source["url"] not in existing_urls:
            sources.append(source)
    notes.extend(pf_notes)

    if len(candidates) < 3:
        for item in _area_source_options(profile):
            source_url = str(item.get("url") or "").strip()
            if not source_url or source_url in existing_urls or any(existing.get("url") == source_url for existing in sources):
                continue
            sources.append(_source_row(item.get("label") or "Public market source", source_url))

    if candidates:
        notes.insert(0, "The supplied URL was expanded with matching live market routes so the shortlist is not limited to a single public page.")
    return candidates, sources, notes


def provider_bayut_url(profile: RequestProfile) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    if not profile.source_url or "bayut.com/" not in profile.source_url:
        return [], [], []
    try:
        html = _fetch_url_html(profile.source_url)
    except Exception:
        return [], [], []

    runtime_payload = _extract_bayut_runtime_payload(html) or {}
    rendering_page = ((runtime_payload.get("rendering") or {}).get("page") or "").lower()
    notes: list[str] = []
    sources = [{"label": "User supplied Bayut URL", "url": profile.source_url, "date": datetime.now(timezone.utc).strftime("%B %d, %Y")}]

    if "captcha" in html.lower() or rendering_page == "captchachallenge":
        notes.append("Bayut blocked direct live extraction with captcha on this request, so the agent used alternate live-search sources where possible.")
        pf_candidates, pf_sources, pf_notes = provider_propertyfinder_profile_search(profile)
        if not pf_candidates:
            generic_candidates, generic_sources, generic_notes = provider_generic_url_metadata(profile)
            pf_candidates = generic_candidates
            pf_sources.extend(generic_sources)
            pf_notes.extend(generic_notes)
        merged_sources = sources + [source for source in pf_sources if source["url"] != profile.source_url]
        return pf_candidates, merged_sources, notes + pf_notes

    direct_candidates = provider_direct_url(profile)
    notes.append("Bayut URL context was parsed, but direct structured Bayut search results were not exposed in the fetched page payload.")
    return direct_candidates, sources, notes


def _first_number(text: str) -> float:
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", str(text or ""))
    if not m:
        return 0
    return float(m.group(1).replace(",", ""))


def _first_percent(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(text or ""))
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)", str(text or ""))
    if m:
        return float(m.group(1))
    return None


def _infer_listing_property_type(text: str) -> str:
    low = _normalize(text)
    if "office" in low:
        return "office"
    if "shop" in low or "retail" in low or "showroom" in low:
        return "shop"
    if "warehouse" in low or "industrial" in low:
        return "warehouse"
    if "apartment" in low or "studio" in low:
        return "apartment"
    if "townhouse" in low or "town house" in low:
        return "townhouse"
    if "villa" in low:
        return "villa"
    return "unknown"


def _source_row(label: str, url: str) -> dict[str, str]:
    return {
        "label": label,
        "url": url,
        "date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
    }


def _bayut_area_slug(area: str) -> str:
    canonical = _normalize(area)
    return AREA_BAYUT_SLUGS.get(canonical, _slugify_area(canonical))


def _propertyfinder_area_slug(area: str) -> str:
    canonical = _normalize(area)
    return PROPERTYFINDER_AREA_SLUGS.get(canonical, _slugify_area(canonical))


def _broker_portfolio_market_notes(candidates: list[dict[str, Any]]) -> list[str]:
    broker_rows = [item for item in candidates if item.get("broker_portfolio_counts")]
    if not broker_rows:
        return []
    top = broker_rows[:3]
    total_inventory = sum(int((item.get("broker_portfolio_counts") or {}).get("total_properties") or 0) for item in top)
    total_commercial = sum(
        int((item.get("broker_portfolio_counts") or {}).get("commercial_rent") or 0)
        + int((item.get("broker_portfolio_counts") or {}).get("commercial_sale") or 0)
        for item in top
    )
    total_residential = sum(
        int((item.get("broker_portfolio_counts") or {}).get("residential_rent") or 0)
        + int((item.get("broker_portfolio_counts") or {}).get("residential_sale") or 0)
        for item in top
    )
    locations: list[str] = []
    for item in top:
        location = str(item.get("broker_location") or "").strip()
        if location and location not in locations:
            locations.append(location)
    notes: list[str] = []
    if total_inventory:
        notes.append(
            f"Current Property Finder broker-profile fallback surfaced {total_inventory} live portfolio listings across the top ranked broker candidates."
        )
    if total_residential or total_commercial:
        notes.append(
            f"Observed broker mix is {total_residential} residential listings versus {total_commercial} commercial listings across the shortlisted broker profiles."
        )
    if locations:
        notes.append(f"Shortlisted broker profiles currently cluster in {', '.join(locations[:3])}.")
    return notes


def _source_option_to_candidate(profile: RequestProfile, item: dict[str, str]) -> dict[str, Any]:
    label = str(item.get("label") or "Public market source").strip()
    url = str(item.get("url") or "").strip()
    inferred_type = _infer_listing_property_type(f"{label} {url}")
    property_type = profile.property_preference if profile.property_preference not in {"any", "commercial"} else inferred_type
    title = label.replace("Bayut - ", "").replace("Property Finder - ", "").replace("Dubai South - ", "").strip()
    fit_label = "high" if property_type == profile.property_preference and property_type not in {"unknown", "commercial"} else "medium"
    return {
        "title": title or f"{profile.area.title()} public market route",
        "area": profile.area.title() if profile.area else "Dubai",
        "building": profile.area.title() if profile.area else "Dubai",
        "source_url": url,
        "source_links": [url] if url else [],
        "commercial_mode": profile.intent or "discovery",
        "property_type": property_type if property_type and property_type != "unknown" else profile.property_preference or "commercial",
        "price_aed": 0,
        "size_sqft": 0,
        "availability": "public_source_route",
        "delivery_timeline": "Live public source route",
        "launch_mode": "current",
        "footfall_profile": "medium" if profile.property_preference in {"shop", "office"} else "unknown",
        "parking_profile": "unknown",
        "license_fit": "needs_confirmation",
        "fit_label": fit_label,
        "summary": "Public listing route identified, but structured listing extraction still needs browser-level or provider-level enrichment for exact property metrics.",
        "pros": [
            "Live public source route aligned to the request market.",
            "Usable for manual review and next-pass listing extraction.",
        ],
        "cons": [
            "Exact unit-level metrics are not yet extracted from this source route.",
            "Client-facing commitment still needs live listing-level confirmation.",
        ],
        "map_query": profile.area.title() if profile.area else "Dubai",
    }


def _effective_market_intent(profile: RequestProfile) -> str:
    if profile.intent in {"rent", "buy"}:
        return profile.intent
    if profile.property_preference in {"office", "shop", "warehouse", "commercial", "any"} or profile.use_case in {"clinic", "veterinary_clinic", "office", "retail", "warehouse"}:
        return "rent"
    return "buy"


def _dynamic_area_source_options(profile: RequestProfile) -> list[dict[str, str]]:
    area_slug = _bayut_area_slug(profile.area) if profile.area else ""
    if not area_slug:
        return []

    market_intent = _effective_market_intent(profile)
    prefix = "to-rent" if market_intent == "rent" else "for-sale"
    property_label = profile.property_preference if profile.property_preference not in {"any", "commercial"} else profile.use_case
    options: list[dict[str, str]] = []

    def add(label: str, url: str) -> None:
        options.append({"label": label, "url": url})

    if property_label == "office":
        add(f"Bayut - Offices {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/offices/dubai/{area_slug}/")
        add(f"Bayut - Commercial Properties {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/commercial/dubai/{area_slug}/")
    elif property_label in {"shop", "retail"}:
        add(f"Bayut - Shops {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/shops/dubai/{area_slug}/")
        add(f"Bayut - Commercial Properties {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/commercial/dubai/{area_slug}/")
    elif property_label == "warehouse":
        add(f"Bayut - Warehouses {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/warehouses/dubai/{area_slug}/")
        add(f"Bayut - Commercial Properties {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/commercial/dubai/{area_slug}/")
    elif property_label in {"clinic", "veterinary_clinic"}:
        add(f"Bayut - Shops {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/shops/dubai/{area_slug}/")
        add(f"Bayut - Offices {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/offices/dubai/{area_slug}/")
        add(f"Bayut - Commercial Properties {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/commercial/dubai/{area_slug}/")
    elif property_label == "apartment":
        add(f"Bayut - Apartments {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/apartments/dubai/{area_slug}/")
    elif property_label == "villa":
        add(f"Bayut - Villas {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/villas/dubai/{area_slug}/")
    elif property_label == "townhouse":
        add(f"Bayut - Townhouses {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/townhouses/dubai/{area_slug}/")
    else:
        add(f"Bayut - Properties {'for Rent' if market_intent == 'rent' else 'for Sale'} in {profile.area.title()}", f"https://www.bayut.com/{prefix}/property/dubai/{area_slug}/")
    return options


def _area_source_options(profile: RequestProfile) -> list[dict[str, str]]:
    static_map = GENERIC_AREA_SOURCE_MAP.get(profile.area, {})
    combined = (
        list(static_map.get(profile.property_preference, []))
        + list(static_map.get(profile.use_case, []))
        + list(static_map.get("commercial", []))
        + _dynamic_area_source_options(profile)
    )
    seen: set[str] = set()
    ordered: list[dict[str, str]] = []
    for item in combined:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        ordered.append(item)
    return ordered


def build_source_register(profile: RequestProfile, strategy: dict[str, Any] | None) -> list[dict[str, Any]]:
    sources = list(strategy.get("source_register") or []) if strategy else []
    for item in _area_source_options(profile):
        if not any(existing.get("url") == item["url"] for existing in sources):
            sources.append(_source_row(item["label"], item["url"]))
    if profile.source_url and not any(item["url"] == profile.source_url for item in sources if item.get("url")):
        sources.insert(0, _source_row("User supplied source URL", profile.source_url))
    return sources


def build_market_highlights(profile: RequestProfile, strategy: dict[str, Any] | None) -> list[str]:
    if strategy and strategy.get("market_highlights"):
        return list(strategy["market_highlights"])
    highlights = []
    if profile.area == "dubai south":
        highlights.append("Dubai South is being positioned around airport, free zone, logistics, and mixed-use residential growth.")
    if profile.intent in {"buy", "investment"}:
        highlights.append("Shortlist should compare capital entry, delivery timeline, and future demand ramp-up.")
    if profile.intent in {"rent", "business_setup"}:
        highlights.append("Immediate-launch value depends on occupancy readiness, fit-out burden, and permit certainty.")
    if profile.property_preference in {"apartment", "villa", "townhouse"}:
        highlights.append("Residential comparisons should weigh layout efficiency, building quality, and lifestyle access alongside entry price.")
    if profile.property_preference in {"office", "shop", "warehouse"}:
        highlights.append("Commercial comparisons should weigh use alignment, launch speed, and operational friction before brand polish.")
    return highlights or ["Market context has to be expanded with area-specific live sources before client send."]


def build_compliance_gates(profile: RequestProfile, strategy: dict[str, Any] | None) -> list[str]:
    if strategy and strategy.get("compliance_gates"):
        return list(strategy["compliance_gates"])
    gates = []
    if profile.use_case in {"veterinary_clinic", "clinic"}:
        gates.append("Business activity and authority use-class approval must be confirmed before commitment.")
        gates.append("Sector-specific technical and health requirements must be checked against the latest authority basis.")
    elif profile.property_preference in {"apartment", "villa", "townhouse"}:
        gates.append("Lease or purchase terms, building rules, and community restrictions must match the intended occupancy plan.")
        gates.append("Service charges, parking allocation, and handover condition should be verified before commitment.")
    else:
        gates.append("Usage, fit-out, and authority approvals must match the target business activity before deal commitment.")
    return gates


def build_sales_pitch(profile: RequestProfile, strategy: dict[str, Any] | None, candidates: list[dict[str, Any]]) -> str:
    ranked = rank_candidates(
        {
            "public_listings": candidates or [],
            "request_profile": {
                "area": profile.area,
                "use_case": profile.use_case,
                "property_preference": profile.property_preference,
                "bedroom_preference": profile.bedroom_preference,
                "bathroom_preference": profile.bathroom_preference,
                "view_preference": profile.view_preference,
                "floor_preference": profile.floor_preference,
                "parking_preference": profile.parking_preference,
                "feature_preferences": profile.feature_preferences,
                "furnishing_preference": profile.furnishing_preference,
                "readiness_preference": profile.readiness_preference,
                "intent": profile.intent,
                "max_price_aed": profile.max_price_aed,
                "min_size_sqft": profile.min_size_sqft,
                "max_size_sqft": profile.max_size_sqft,
                "target_size_sqft": profile.target_size_sqft,
            },
        }
    )
    primary = ranked[0]["title"] if len(ranked) > 0 else "the top option"
    secondary = ranked[1]["title"] if len(ranked) > 1 else "the secondary option"
    third = ranked[2]["title"] if len(ranked) > 2 else "the fallback option"
    if strategy and strategy.get("sales_pitch_template"):
        return strategy["sales_pitch_template"].format(primary=primary, secondary=secondary, third=third)
    return (
        f"Lead with {primary} as the strongest aligned option based on the current brief. "
        f"Keep {secondary} as the alternative and {third} as the fallback while approvals, pricing, and fit-out scope are verified."
    )


def build_next_steps(profile: RequestProfile, strategy: dict[str, Any] | None) -> list[str]:
    if strategy and strategy.get("next_steps"):
        return list(strategy["next_steps"])
    if profile.property_preference in {"apartment", "villa", "townhouse"}:
        return [
            "Confirm live availability, rent or sale terms, and current landlord or seller expectations before client send.",
            "Collect floor plan, exact built-up area, parking details, and building or community rules for the shortlisted options.",
            "Verify service charges, maintenance condition, and move-in timeline before presenting the lead recommendation as execution-ready.",
        ]
    return [
        "Confirm exact live availability and current commercial terms before client send.",
        "Collect floor plan, service-charge, fit-out, and authority-use information for the shortlisted options.",
        "Run final approval and risk review before presenting the recommendation as execution-ready."
    ]


def build_agent_review(profile: RequestProfile, ranked_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    top = ranked_candidates[:3]
    if not top:
        return {
            "approval_posture": "HOLD: no ranked candidates available yet.",
            "review_notes": [
                "Source extraction did not produce enough structured candidates for a client-ready recommendation.",
                "Expand listing retrieval and validate live pricing before client send.",
            ],
        }

    review_notes: list[str] = []
    lead = top[0]
    is_residential = profile.property_preference in {"apartment", "villa", "townhouse"}
    if lead.get("license_fit") == "needs_confirmation" and not is_residential:
        review_notes.append(f"Lead option {lead['title']} still requires written use and approval confirmation.")
    if not lead.get("price_aed"):
        review_notes.append(f"Lead option {lead['title']} still needs live pricing confirmation.")
    if any(not candidate.get("size_sqft") for candidate in top):
        review_notes.append("One or more shortlisted options still lack full area or layout detail.")
    if profile.source_mode == "url" and any(candidate.get("availability") == "url_supplied" for candidate in top):
        review_notes.append("URL-context fallback is present in the shortlist; enrich with direct listing extraction before client send.")
    if profile.use_case in {"veterinary_clinic", "clinic"}:
        review_notes.append("Sector-specific licensing and fit-out constraints remain a gating item before execution.")
    if is_residential:
        review_notes.append("Residential shortlist still needs building-rule, condition, and move-in verification before client send.")

    if not review_notes:
        review_notes.append("Shortlist is internally consistent, but live pricing and terms should still be rechecked before send.")

    unresolved = sum(1 for note in review_notes if "requires" in note or "lack" in note or "fallback" in note or "gating" in note)
    approval_posture = "READY FOR AGENT REVIEW BEFORE CLIENT SEND" if unresolved <= 1 else "CONDITIONAL: resolve review notes before client send"
    return {
        "approval_posture": approval_posture,
        "review_notes": review_notes,
    }


def strategy_candidates(profile: RequestProfile, strategy: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list(strategy.get("public_candidates") or []) if strategy else []


def select_strategy(profile: RequestProfile) -> dict[str, Any] | None:
    return REQUEST_STRATEGIES.get((profile.area, profile.use_case))


def generic_archetype_candidates(profile: RequestProfile) -> list[dict[str, Any]]:
    area_label = (profile.area or "target area").title()
    if profile.area == "dubai south" and profile.property_preference == "office":
        return [
            {
                "title": "Bright | Fully Fitted Space | Partitioned",
                "commercial_mode": "rent",
                "price_aed": 350000,
                "price_term": "yearly",
                "property_type": "office",
                "size_sqft": 2490,
                "building": "Dubai South Business Park B3, The Avenue, Logistics City",
                "area": "Dubai South, Dubai",
                "developer": "Dubai South",
                "availability": "ready",
                "delivery_timeline": "Current public rent listing",
                "payment_plan": "lease",
                "launch_mode": "immediate",
                "footfall_profile": "medium",
                "parking_profile": "strong",
                "license_fit": "needs_confirmation",
                "fit_label": "medium" if profile.use_case in {"clinic", "veterinary_clinic"} else "high",
                "summary": "Best immediate fitted office path based on the current Dubai South office market evidence.",
                "pros": [
                    "Fitted office stock reduces launch friction.",
                    "Business Park positioning supports airport, free-zone, and logistics connectivity."
                ],
                "cons": [
                    "Use approval still needs to match the final business activity."
                ],
                "source_url": "https://www.bayut.com/to-rent/offices/dubai/dubai-south/logistics-city/",
                "source_links": [
                    "https://www.bayut.com/to-rent/offices/dubai/dubai-south/logistics-city/",
                    "https://www.dubaisouth.ae/en/work/commercial-property/offices"
                ],
                "map_query": "Dubai South Business Park B3 Logistics City Dubai South"
            },
            {
                "title": "Modern Office in Dubai South Business Park",
                "commercial_mode": "rent",
                "price_aed": 0,
                "property_type": "office",
                "size_sqft": 1500,
                "building": "Dubai South Business Park",
                "area": "Dubai South, Dubai",
                "developer": "Dubai South",
                "availability": "live_public_listing",
                "delivery_timeline": "Current public rent listing",
                "payment_plan": "lease",
                "launch_mode": "current",
                "footfall_profile": "medium",
                "parking_profile": "strong",
                "license_fit": "needs_confirmation",
                "fit_label": "medium" if profile.use_case in {"clinic", "veterinary_clinic"} else "high",
                "summary": "Smaller business-park office route for clients who want a lower-entry Dubai South operational base.",
                "pros": [
                    "More compact entry size than large-floor office stock.",
                    "Business Park cluster has repeated public office supply."
                ],
                "cons": [
                    "Exact pricing and fit-out scope must be rechecked live."
                ],
                "source_url": "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-dubai-south-dubai-world-central-business-park-97364276.html",
                "source_links": [
                    "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-dubai-south-dubai-world-central-business-park-97364276.html",
                    "https://www.bayut.com/to-rent/offices/dubai/dubai-south/"
                ],
                "map_query": "Dubai South Business Park Dubai South"
            },
            {
                "title": "Large Networked Office Space in Dubai South Business Park",
                "commercial_mode": "rent",
                "price_aed": 0,
                "property_type": "office",
                "size_sqft": 10000,
                "building": "Dubai South Business Park",
                "area": "Dubai South, Dubai",
                "developer": "Dubai South",
                "availability": "live_public_listing",
                "delivery_timeline": "Current public rent listing",
                "payment_plan": "lease",
                "launch_mode": "current",
                "footfall_profile": "medium",
                "parking_profile": "strong",
                "license_fit": "needs_confirmation",
                "fit_label": "medium",
                "summary": "Scale-up office option for headquarters, call-center, or admin-heavy operating models in Dubai South.",
                "pros": [
                    "Supports larger staffing and multi-room operational setups.",
                    "Good fallback if the request is more corporate than customer-facing."
                ],
                "cons": [
                    "May be oversized for a lean startup requirement.",
                    "Exact price and current availability must be revalidated."
                ],
                "source_url": "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-dubai-south-dubai-world-central-business-park-97364284.html",
                "source_links": [
                    "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-dubai-south-dubai-world-central-business-park-97364284.html",
                    "https://www.dubaisouth.ae/en/work/commercial-property/offices"
                ],
                "map_query": "Dubai South Business Park Dubai South"
            },
        ]

    property_type = profile.property_preference if profile.property_preference != "any" else "commercial"
    return [
        {
            "title": f"Primary {property_type.title()} Option - {area_label}",
            "commercial_mode": profile.intent,
            "price_aed": 0,
            "property_type": property_type,
            "size_sqft": 0,
            "building": area_label,
            "area": area_label,
            "developer": "",
            "availability": "market_search_required",
            "delivery_timeline": "Pending live listing confirmation",
            "launch_mode": "current",
            "footfall_profile": "unknown",
            "parking_profile": "unknown",
            "license_fit": "needs_confirmation",
            "fit_label": "medium" if "clinic" in profile.use_case else "unknown",
            "summary": "Primary candidate archetype created from the request profile when direct listing extraction is incomplete.",
            "pros": ["Aligned to the request area and inferred property type."],
            "cons": ["Live listing specifics still need enrichment."],
            "source_url": profile.source_url or "",
            "source_links": [profile.source_url] if profile.source_url else [],
            "map_query": area_label,
        },
        {
            "title": f"Value-Oriented {property_type.title()} Alternative - {area_label}",
            "commercial_mode": profile.intent,
            "price_aed": 0,
            "property_type": property_type,
            "size_sqft": 0,
            "building": area_label,
            "area": area_label,
            "developer": "",
            "availability": "market_search_required",
            "delivery_timeline": "Pending live listing confirmation",
            "launch_mode": "current",
            "footfall_profile": "unknown",
            "parking_profile": "unknown",
            "license_fit": "needs_confirmation",
            "fit_label": "medium" if "clinic" in profile.use_case else "unknown",
            "summary": "Secondary archetype optimized for lower entry or lower risk.",
            "pros": ["Useful for comparing entry strategy against the primary option."],
            "cons": ["Needs live listing enrichment before client commitment."],
            "source_url": profile.source_url or "",
            "source_links": [profile.source_url] if profile.source_url else [],
            "map_query": area_label,
        },
        {
            "title": f"Scale-Up / Flagship {property_type.title()} Option - {area_label}",
            "commercial_mode": profile.intent,
            "price_aed": 0,
            "property_type": property_type,
            "size_sqft": 0,
            "building": area_label,
            "area": area_label,
            "developer": "",
            "availability": "market_search_required",
            "delivery_timeline": "Pending live listing confirmation",
            "launch_mode": "current",
            "footfall_profile": "unknown",
            "parking_profile": "unknown",
            "license_fit": "needs_confirmation",
            "fit_label": "medium" if "clinic" in profile.use_case else "unknown",
            "summary": "Third archetype intended for clients who want a flagship or future-scale position.",
            "pros": ["Lets the proposal compare short-term practicality against long-term ambition."],
            "cons": ["Needs live listing enrichment before client commitment."],
            "source_url": profile.source_url or "",
            "source_links": [profile.source_url] if profile.source_url else [],
            "map_query": area_label,
        },
    ]


def build_case_payload(profile: RequestProfile) -> dict[str, Any]:
    strategy = select_strategy(profile)
    internal_evidence, evidence_trail = gather_internal_evidence(profile)
    internal_image_assets, _internal_image_snapshot, _internal_image_evidence = gather_internal_asset_signals(profile, limit=64)
    internal_matches, internal_market_snapshot, internal_match_evidence = gather_internal_inventory_matches(profile)
    internal_evidence.extend([item for item in internal_match_evidence if item not in internal_evidence])
    public_candidates: list[dict[str, Any]] = []
    generated_sources: list[dict[str, str]] = []
    generated_market_notes: list[str] = []
    request_profile = {
        "raw_request": profile.raw_request,
        "source_mode": profile.source_mode,
        "area": profile.area,
        "use_case": profile.use_case,
        "property_preference": profile.property_preference,
        "bedroom_preference": profile.bedroom_preference,
        "bathroom_preference": profile.bathroom_preference,
        "view_preference": profile.view_preference,
        "floor_preference": profile.floor_preference,
        "parking_preference": profile.parking_preference,
        "feature_preferences": profile.feature_preferences,
        "furnishing_preference": profile.furnishing_preference,
        "readiness_preference": profile.readiness_preference,
        "intent": profile.intent,
        "source_url": profile.source_url,
        "max_price_aed": profile.max_price_aed,
        "min_size_sqft": profile.min_size_sqft,
        "max_size_sqft": profile.max_size_sqft,
        "target_size_sqft": profile.target_size_sqft,
    }

    if profile.source_url and "propertyfinder.ae/en/broker/" in profile.source_url:
        broker_candidates = provider_propertyfinder_broker(profile.source_url)
        public_candidates.extend(broker_candidates)
        generated_market_notes.extend(_broker_portfolio_market_notes(broker_candidates))
        for candidate in broker_candidates[:3]:
            source_url = str(candidate.get("source_url") or "").strip()
            if source_url:
                generated_sources.append(_source_row(candidate.get("title") or "Property Finder broker profile", source_url))
    elif profile.source_url and "propertyfinder.ae/" in profile.source_url:
        pf_candidates, pf_notes = provider_propertyfinder_search_page(profile.source_url)
        public_candidates.extend(pf_candidates)
        generated_market_notes.extend(pf_notes)
    elif profile.source_url and "bayut.com/" in profile.source_url:
        bayut_candidates, bayut_sources, bayut_notes = provider_bayut_url(profile)
        public_candidates.extend(bayut_candidates)
        generated_sources.extend(bayut_sources)
        generated_market_notes.extend(bayut_notes)
    elif profile.source_url:
        generic_candidates, generic_sources, generic_notes = provider_generic_url_metadata(profile)
        if generic_candidates:
            public_candidates.extend(generic_candidates)
            generated_sources.extend(generic_sources)
            generated_market_notes.extend(generic_notes)
        else:
            public_candidates.extend(provider_direct_url(profile))

    if profile.source_url and len(public_candidates) < 3:
        expanded_candidates, expanded_sources, expanded_notes = expand_public_candidates_from_profile(profile, public_candidates)
        _extend_unique_candidates(public_candidates, expanded_candidates, max_candidates=6)
        for source in expanded_sources:
            if not any(existing.get("url") == source.get("url") for existing in generated_sources):
                generated_sources.append(source)
        for note in expanded_notes:
            if note not in generated_market_notes:
                generated_market_notes.append(note)

    if strategy:
        public_candidates.extend(strategy_candidates(profile, strategy))

    if not profile.source_url and not strategy:
        pf_candidates, pf_sources, pf_notes = provider_propertyfinder_profile_search(profile)
        public_candidates.extend(pf_candidates)
        generated_sources.extend(pf_sources)
        generated_market_notes.extend(pf_notes)

    if not profile.area and public_candidates:
        derived_area = _infer_area(
            " ".join(
                str(item)
                for candidate in public_candidates[:3]
                for item in [candidate.get("title"), candidate.get("summary"), candidate.get("area"), candidate.get("building")]
                if item
            )
        )
        if derived_area:
            profile = RequestProfile(
                raw_request=profile.raw_request,
                normalized_request=profile.normalized_request,
                source_mode=profile.source_mode,
                area=derived_area,
                use_case=profile.use_case,
                property_preference=profile.property_preference,
                bedroom_preference=profile.bedroom_preference,
                bathroom_preference=profile.bathroom_preference,
                view_preference=profile.view_preference,
                floor_preference=profile.floor_preference,
                parking_preference=profile.parking_preference,
                feature_preferences=list(profile.feature_preferences),
                furnishing_preference=profile.furnishing_preference,
                readiness_preference=profile.readiness_preference,
                intent=profile.intent,
                source_url=profile.source_url,
                max_price_aed=profile.max_price_aed,
                min_size_sqft=profile.min_size_sqft,
                max_size_sqft=profile.max_size_sqft,
                target_size_sqft=profile.target_size_sqft,
            )
            request_profile["area"] = derived_area

    if len(public_candidates) < 3 and not profile.source_url:
        source_options = _area_source_options(profile)
        seen_source_urls = {str(item.get("source_url") or "").strip() for item in public_candidates if item.get("source_url")}
        for item in source_options:
            candidate = _source_option_to_candidate(profile, item)
            source_url = str(candidate.get("source_url") or "").strip()
            if not source_url or source_url in seen_source_urls:
                continue
            public_candidates.append(candidate)
            seen_source_urls.add(source_url)
            generated_sources.append(_source_row(item.get("label") or candidate.get("title") or "Public market source", source_url))
            if len(public_candidates) >= 3:
                break

    if len(public_candidates) < 3 and internal_matches:
        seen_internal = {(item.get("title"), item.get("source_url")) for item in public_candidates}
        for match in internal_matches:
            if _internal_match_is_low_quality(match):
                continue
            if match.get("signal_type") == "internal_asset":
                candidate = _internal_asset_match_to_candidate(
                    {
                        "filename": match["project"],
                        "file_type": match["property_type"],
                        "detected_area": match["area"],
                        "detected_project": match["project"],
                        "source_chat_group": match["source_group"],
                        "duplicate_of_or_copied_to": match["file_name"],
                        "signal_score": match["score"],
                        "developer_signal": match.get("developer", ""),
                    },
                    profile,
                )
            else:
                candidate = _internal_match_to_candidate(
                    type("InternalMatch", (), {
                        "project": match["project"],
                        "area": match["area"],
                        "developer": match["developer"],
                        "property_type": match["property_type"],
                        "inventory_type": match["inventory_type"],
                        "status": match["status"],
                        "price": match["price_aed"],
                        "source_group": match["source_group"],
                        "file_name": match["file_name"],
                        "score": match["score"],
                    })(),
                    profile,
                )
            key = (candidate.get("title"), candidate.get("source_url"))
            if key in seen_internal:
                continue
            public_candidates.append(candidate)
            seen_internal.add(key)
            if len(public_candidates) >= 3:
                break

    if len(public_candidates) < 3:
        seen = {(item.get("title"), item.get("source_url")) for item in public_candidates}
        for candidate in generic_archetype_candidates(profile):
            key = (candidate.get("title"), candidate.get("source_url"))
            if key in seen:
                continue
            public_candidates.append(candidate)
            seen.add(key)
            if len(public_candidates) >= 3:
                break

    _attach_internal_images(public_candidates, internal_image_assets)

    proposal_title = strategy.get("proposal_title") if strategy else f"AIOS Realty Proposal - {profile.raw_request[:72] or 'Client Request'}"
    sales_pitch = build_sales_pitch(profile, strategy, public_candidates)
    source_register = build_source_register(profile, strategy)
    for source in generated_sources:
        if not any(existing.get("url") == source["url"] for existing in source_register):
            source_register.insert(0, source)
    ranked_preview = rank_candidates({"public_listings": public_candidates, "request_profile": request_profile})
    agent_review = build_agent_review(profile, ranked_preview)
    hero_image = ""
    for entry in evidence_trail:
        sample_images = entry.get("sample_images") or []
        if sample_images:
            hero_image = sample_images[0]
            break

    if not hero_image:
        for candidate in ranked_preview:
            if candidate.get("hero_image_url"):
                hero_image = str(candidate["hero_image_url"])
                break

    if not hero_image:
        hero_image = str(AIOS_ROOT / "KnowledgeBase" / "raw_data" / "images" / "85dc25b10ca3__b7ad3954-58c6-4e00-9d1f-f6ae8ddd62b1.jpg")

    market_highlights = build_market_highlights(profile, strategy)
    for note in generated_market_notes:
        if note not in market_highlights:
            market_highlights.append(note)

    return {
        "case": {
            "case_id": _slug(profile.raw_request or profile.source_url or DEFAULT_CASE_NAME),
            "client_name": "Confidential Client",
            "client_request": profile.raw_request or profile.source_url,
            "hero_image_path": hero_image,
        },
        "proposal_title": proposal_title,
        "market_highlights": market_highlights,
        "compliance_gates": build_compliance_gates(profile, strategy),
        "sales_pitch": sales_pitch,
        "next_steps": build_next_steps(profile, strategy),
        "source_register": source_register,
        "public_listings": public_candidates,
        "internal_inventory_evidence": internal_evidence,
        "internal_inventory_matches": internal_matches,
        "internal_market_snapshot": internal_market_snapshot,
        "request_profile": request_profile,
        "agent_review": agent_review,
        "evidence_trail": evidence_trail,
    }


def run_agent(request_text: str = "", source_url: str = "", voice_transcript: str = "", case_name: str = "") -> dict[str, Any]:
    profile = build_request_profile(request_text=request_text, source_url=source_url, voice_transcript=voice_transcript)
    payload = build_case_payload(profile)
    final_case_name = case_name or payload["case"]["case_id"]
    result = build_proposal(payload, case_name=final_case_name)
    result["agent"] = {
        "name": "AIOS Realty Intelligence Agent",
        "generated_at": _now(),
        "request_profile": payload["request_profile"],
        "provider_summary": {
            "strategy_used": bool(select_strategy(profile)),
            "propertyfinder_broker_provider": "propertyfinder.ae/en/broker/" in source_url,
            "url_context_provider": bool(source_url),
            "internal_evidence_rows": len(payload.get("evidence_trail") or []),
        },
    }
    result["export"] = export_visual_artifacts(result)
    result_path = REPORTS_DIR / f"{case_name or payload['case']['case_id']}.json"
    result["agent"]["run_report"] = str(result_path)
    client_result_path = Path(result["artifacts"]["json"])
    client_result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generic AIOS realty intelligence agent runtime.")
    parser.add_argument("--request", default="", help="Client request text.")
    parser.add_argument("--url", default="", help="Source URL from Bayut, Property Finder, or another listing page.")
    parser.add_argument("--voice-transcript", default="", help="Voice transcript text.")
    parser.add_argument("--voice-transcript-file", default="", help="Path to a transcript file.")
    parser.add_argument("--case-name", default="", help="Optional output basename.")
    args = parser.parse_args()

    transcript = args.voice_transcript
    if args.voice_transcript_file:
        transcript = _read_text(args.voice_transcript_file)

    result = run_agent(
        request_text=args.request,
        source_url=args.url,
        voice_transcript=transcript,
        case_name=args.case_name,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
