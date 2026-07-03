#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports" / "client_property_proposals"
DEFAULT_CASE_PATH = RUNTIME_DIR / "sample_property_cases" / "dubai_south_veterinary_clinic.json"
DEFAULT_CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def _aed(value: Any) -> str:
    amount = _money(value)
    if amount <= 0:
        return "TBC"
    return f"AED {amount:,.0f}"


def _psf(price_aed: Any, size_sqft: Any) -> float | None:
    price = _money(price_aed)
    size = _money(size_sqft)
    if price <= 0 or size <= 0:
        return None
    return price / size


def _percent_value(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace("%", "").replace(",", "").strip())
    except Exception:
        return None


def _slug(text: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in text.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "proposal"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run_command(args: list[str]) -> bool:
    try:
        completed = subprocess.run(args, check=False, capture_output=True, text=True)
    except Exception:
        return False
    return completed.returncode == 0


def _google_maps_link(query: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def _image_uri(path_text: str) -> str:
    path = Path(path_text).expanduser()
    return path.resolve().as_uri() if path.exists() else ""


def _image_src(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://") or text.startswith("data:"):
        return text
    return _image_uri(text)


def _price_score(candidate: dict[str, Any], mode: str) -> float:
    price = _money(candidate.get("price_aed"))
    if price <= 0:
        return 0.0
    if mode == "rent":
        if price <= 250_000:
            return 18.0
        if price <= 400_000:
            return 14.0
        if price <= 600_000:
            return 9.0
        return 4.0
    if price <= 3_500_000:
        return 18.0
    if price <= 4_500_000:
        return 14.0
    if price <= 5_750_000:
        return 10.0
    return 5.0


def _bedrooms_int(value: Any) -> int | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text == "studio":
        return 0
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _bathrooms_int(value: Any) -> int | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _candidate_furnishing(candidate: dict[str, Any]) -> str:
    explicit = str(candidate.get("furnishing") or candidate.get("furnished") or "").strip().lower()
    if explicit in {"furnished", "unfurnished", "semi_furnished", "semi-furnished", "semi furnished"}:
        return explicit.replace("-", "_").replace(" ", "_")

    combined = " ".join(
        str(candidate.get(key) or "")
        for key in ["title", "summary", "availability", "building"]
    ).lower()
    if "unfurnished" in combined:
        return "unfurnished"
    if "semi furnished" in combined or "semi-furnished" in combined:
        return "semi_furnished"
    if "fully furnished" in combined or "furnished" in combined:
        return "furnished"
    return ""


def _candidate_readiness(candidate: dict[str, Any]) -> str:
    availability = str(candidate.get("availability") or "").strip().lower()
    delivery = str(candidate.get("delivery_timeline") or "").strip().lower()
    launch_mode = str(candidate.get("launch_mode") or "").strip().lower()
    combined = " ".join(str(candidate.get(key) or "") for key in ["title", "summary", "availability", "delivery_timeline"]).lower()

    if any(token in combined for token in ["vacant", "immediate occupancy", "ready now", "move in now", "move-in now"]) or launch_mode == "immediate":
        return "immediate"
    if availability in {"ready", "brand new", "fitted"} or "ready" in delivery or "fitted" in combined or "turnkey" in combined:
        return "ready"
    if availability == "off-plan" or "handover" in delivery or "off plan" in combined or "off-plan" in combined:
        return "off_plan"
    return ""


def _candidate_view_tokens(candidate: dict[str, Any]) -> set[str]:
    combined = " ".join(
        str(candidate.get(key) or "")
        for key in ["title", "summary", "building", "area"]
    ).lower()
    tokens: set[str] = set()
    for label in ["palm", "sea", "ocean", "marina", "golf", "city", "park", "canal"]:
        if label in combined:
            tokens.add("sea" if label == "ocean" else label)
    return tokens


def _candidate_floor_preference(candidate: dict[str, Any]) -> str:
    combined = " ".join(
        str(candidate.get(key) or "")
        for key in ["title", "summary", "building"]
    ).lower()
    if "high floor" in combined or "top floor" in combined:
        return "high"
    if "low floor" in combined or "lower floor" in combined:
        return "low"
    if "mid floor" in combined or "middle floor" in combined:
        return "mid"
    return ""


def _candidate_parking_profile(candidate: dict[str, Any]) -> str:
    explicit = str(candidate.get("parking_profile") or "").strip().lower()
    if explicit in {"strong", "limited", "none"}:
        return explicit

    combined = " ".join(
        str(candidate.get(key) or "")
        for key in ["title", "summary", "building", "pros", "cons"]
    ).lower()
    if any(token in combined for token in ["with parking", "parking included", "parking available", "dedicated parking", "parking supports"]):
        return "strong"
    if any(token in combined for token in ["limited parking", "parking may constrain", "shared parking only"]):
        return "limited"
    if any(token in combined for token in ["no parking", "without parking"]):
        return "none"
    return ""


def _candidate_feature_tokens(candidate: dict[str, Any]) -> set[str]:
    combined = " ".join(
        str(candidate.get(key) or "")
        for key in ["title", "summary", "building", "area", "pros", "cons"]
    ).lower()
    feature_keywords = {
        "upgraded": ["upgraded", "fully upgraded", "renovated", "refurbished"],
        "corner": ["corner unit", "corner plot", "corner"],
        "balcony": ["balcony"],
        "terrace": ["terrace"],
        "duplex": ["duplex"],
        "brand_new": ["brand new"],
    }
    found: set[str] = set()
    for canonical, keywords in feature_keywords.items():
        if any(keyword in combined for keyword in keywords):
            found.add(canonical)
    return found


def _budget_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    max_price = _money(request_profile.get("max_price_aed"))
    price = _money(candidate.get("price_aed"))
    if max_price <= 0:
        return 0.0, [], []
    if price <= 0:
        return -4.0, [], [f"price is still unconfirmed against the AED {max_price:,.0f} budget"]
    if price <= max_price:
        gap = max_price - price
        headroom_ratio = min(1.0, gap / max_price) if max_price else 0.0
        score = 10.0 + (6.0 * headroom_ratio)
        return score, [f"fits within the AED {max_price:,.0f} budget"], []
    overshoot = price - max_price
    overshoot_ratio = overshoot / max_price if max_price else 1.0
    penalty = min(24.0, 10.0 + overshoot_ratio * 18.0)
    return -penalty, [], [f"exceeds the AED {max_price:,.0f} budget by AED {overshoot:,.0f}"]


def _requested_size_range(request_profile: dict[str, Any]) -> tuple[float, float] | None:
    requested_min = _money(request_profile.get("min_size_sqft"))
    requested_max = _money(request_profile.get("max_size_sqft"))
    requested_target = _money(request_profile.get("target_size_sqft"))

    if requested_target > 0:
        tolerance = max(120.0, requested_target * 0.18)
        return max(0.0, requested_target - tolerance), requested_target + tolerance
    if requested_min > 0 and requested_max > 0:
        return min(requested_min, requested_max), max(requested_min, requested_max)
    if requested_min > 0:
        return requested_min, requested_min + max(250.0, requested_min * 0.35)
    if requested_max > 0:
        return max(0.0, requested_max - max(250.0, requested_max * 0.35)), requested_max

    property_preference = str(request_profile.get("property_preference") or "").lower()
    use_case = str(request_profile.get("use_case") or "").lower()
    bedrooms = _bedrooms_int(request_profile.get("bedroom_preference"))

    if property_preference == "apartment" or use_case == "apartment":
        apartment_ranges = {
            0: (350.0, 650.0),
            1: (650.0, 1100.0),
            2: (1000.0, 1600.0),
            3: (1500.0, 2300.0),
            4: (2200.0, 4000.0),
        }
        if bedrooms is not None:
            return apartment_ranges.get(min(bedrooms, 4), (2200.0, 4000.0))
        return (700.0, 1500.0)

    if property_preference in {"villa", "townhouse"} or use_case in {"villa", "townhouse"}:
        villa_ranges = {
            2: (1600.0, 2600.0),
            3: (2200.0, 3600.0),
            4: (3000.0, 5000.0),
            5: (3800.0, 6500.0),
        }
        if bedrooms is not None:
            return villa_ranges.get(min(max(bedrooms, 2), 5), (3800.0, 6500.0))
        return (2200.0, 4200.0)

    if property_preference == "office" or use_case == "office":
        return (700.0, 1800.0)
    if property_preference in {"shop", "retail", "commercial"} or use_case in {"clinic", "veterinary_clinic", "retail"}:
        return (900.0, 2200.0)
    if property_preference == "warehouse" or use_case == "warehouse":
        return (5000.0, 30000.0)
    return None


def _bedroom_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested = _bedrooms_int(request_profile.get("bedroom_preference"))
    if requested is None:
        return 0.0, [], []

    actual = _bedrooms_int(candidate.get("bedrooms"))
    if actual is None:
        return -4.0, [], ["bedroom count still needs confirmation against the request"]
    if actual == requested:
        label = "studio" if requested == 0 else f"{requested}-bedroom"
        return 14.0, [f"{label} layout matches the request"], []

    distance = abs(actual - requested)
    if distance == 1:
        return -7.0, [], [f"{actual}-bedroom layout is adjacent to the requested {requested}-bedroom brief"]
    return -16.0, [], [f"{actual}-bedroom layout conflicts with the requested {requested}-bedroom brief"]


def _bathroom_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested_text = str(request_profile.get("bathroom_preference") or "").strip()
    if not requested_text:
        return 0.0, [], []

    requested = _bathrooms_int(requested_text)
    if requested is None:
        return 0.0, [], []
    actual = _bathrooms_int(candidate.get("bathrooms"))
    if actual is None:
        return -2.0, [], ["bathroom count still needs confirmation against the request"]
    if actual == requested:
        return 7.0, [f"{requested}-bathroom layout matches the request"], []
    if actual > requested:
        return 3.0, [f"{actual}-bathroom layout exceeds the minimum bathroom count requested"], []
    return -7.0, [], [f"{actual}-bathroom layout is below the requested {requested}-bathroom brief"]


def _furnishing_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested = str(request_profile.get("furnishing_preference") or "").strip().lower()
    if not requested:
        return 0.0, [], []

    actual = _candidate_furnishing(candidate)
    if not actual:
        return -2.0, [], ["furnishing condition still needs confirmation against the request"]
    if actual == requested:
        label = requested.replace("_", " ")
        return 9.0, [f"{label} condition matches the request"], []
    if requested == "furnished" and actual == "semi_furnished":
        return 3.0, [], ["semi furnished rather than fully furnished"]
    return -9.0, [], [f"{actual.replace('_', ' ')} condition conflicts with the requested {requested.replace('_', ' ')} brief"]


def _readiness_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested = str(request_profile.get("readiness_preference") or "").strip().lower()
    if not requested:
        return 0.0, [], []

    actual = _candidate_readiness(candidate)
    if not actual:
        return -2.0, [], ["occupancy readiness still needs confirmation against the request"]
    if actual == requested:
        label = "vacant or immediate occupancy" if actual == "immediate" else actual.replace("_", " ")
        return 10.0, [f"{label} profile matches the request"], []
    if requested == "ready" and actual == "immediate":
        return 6.0, [f"{actual.replace('_', ' ')} profile exceeds the readiness requested"], []
    if requested == "immediate" and actual == "ready":
        return 2.0, [], ["space appears ready but vacancy or immediate occupancy still needs confirmation"]
    return -8.0, [], [f"{actual.replace('_', ' ')} profile conflicts with the requested {requested.replace('_', ' ')} brief"]


def _view_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested = str(request_profile.get("view_preference") or "").strip().lower()
    if not requested:
        return 0.0, [], []
    actual_tokens = _candidate_view_tokens(candidate)
    if not actual_tokens:
        return -4.0, [], ["view orientation still needs confirmation against the request"]
    if requested in actual_tokens:
        return 14.0, [f"{requested} view matches the request"], []
    return -12.0, [], [f"listing signals {', '.join(sorted(actual_tokens))} view rather than the requested {requested} view"]


def _floor_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested = str(request_profile.get("floor_preference") or "").strip().lower()
    if not requested:
        return 0.0, [], []
    actual = _candidate_floor_preference(candidate)
    if not actual:
        return -1.0, [], ["floor level still needs confirmation against the request"]
    if actual == requested:
        return 5.0, [f"{requested} floor profile matches the request"], []
    return -4.0, [], [f"{actual} floor profile conflicts with the requested {requested} floor brief"]


def _parking_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested = str(request_profile.get("parking_preference") or "").strip().lower()
    if not requested:
        return 0.0, [], []
    actual = _candidate_parking_profile(candidate)
    if not actual:
        return -2.0, [], ["parking availability still needs confirmation against the request"]
    if requested == "required":
        if actual == "strong":
            return 7.0, ["parking provision matches the request"], []
        if actual == "limited":
            return -3.0, [], ["parking exists but may be weaker than requested"]
        return -7.0, [], ["parking provision conflicts with the request"]
    if requested == "not_required":
        if actual == "none":
            return 3.0, ["listing aligns with the no-parking preference"], []
        return 0.0, [], []
    return 0.0, [], []


def _feature_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested = [str(item).strip().lower() for item in (request_profile.get("feature_preferences") or []) if str(item).strip()]
    if not requested:
        return 0.0, [], []
    actual = _candidate_feature_tokens(candidate)
    if not actual:
        return -2.0, [], ["requested listing features still need confirmation"]
    matched = [item for item in requested if item in actual]
    if matched:
        labels = ", ".join(item.replace("_", " ") for item in matched)
        score = 5.0 * len(matched)
        return score, [f"{labels} feature matches the request"], []
    labels = ", ".join(item.replace("_", " ") for item in requested)
    return -6.0, [], [f"listing does not clearly show the requested {labels} feature set"]


def _source_url_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    requested_url = str(request_profile.get("source_url") or "").strip().lower()
    if not requested_url:
        return 0.0, [], []
    candidate_url = str(candidate.get("source_url") or "").strip().lower()
    if not candidate_url:
        return 0.0, [], []
    if candidate_url == requested_url:
        return 18.0, ["direct match to the supplied listing URL"], []
    return 0.0, [], []


def _size_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    size = _money(candidate.get("size_sqft"))
    if not size:
        return 0.0, [], ["size and layout detail still need confirmation"]

    target_range = _requested_size_range(request_profile)
    if not target_range:
        ideal = 1250.0
        drift = abs(size - ideal)
        score = max(4.0, 18.0 - min(14.0, drift / 100.0))
        if size >= 950:
            return score, ["size supports flexible layout planning"], []
        return score, [], ["small footprint may compress layout flexibility"]

    target_min, target_max = target_range
    midpoint = (target_min + target_max) / 2.0
    tolerance = max(120.0, (target_max - target_min) * 0.15)

    if target_min <= size <= target_max:
        drift_ratio = abs(size - midpoint) / max(1.0, (target_max - target_min) / 2.0)
        score = 18.0 - min(8.0, drift_ratio * 8.0)
        return score, [f"size is aligned with the target brief range of {int(target_min):,}-{int(target_max):,} sqft"], []

    if size < target_min:
        shortfall = target_min - size
        if shortfall <= tolerance:
            return 8.0, [], [f"size is slightly below the target brief range of {int(target_min):,}-{int(target_max):,} sqft"]
        return -6.0, [], [f"size is materially below the target brief range of {int(target_min):,}-{int(target_max):,} sqft"]

    excess = size - target_max
    if excess <= tolerance:
        return 10.0, [f"size is above the target range but gives extra layout flexibility"], []
    return 4.0, [], [f"size is materially above the target brief range of {int(target_min):,}-{int(target_max):,} sqft"]


def _request_focus_label(request_profile: dict[str, Any]) -> str:
    use_case = str(request_profile.get("use_case") or "")
    property_preference = str(request_profile.get("property_preference") or "")
    mapping = {
        "veterinary_clinic": "veterinary clinic launch",
        "clinic": "clinic launch",
        "office": "office setup",
        "retail": "retail business setup",
        "warehouse": "warehouse operation",
        "apartment": "residential move",
        "villa": "residential move",
        "townhouse": "residential move",
        "general_property": "property brief",
    }
    if use_case in mapping:
        return mapping[use_case]
    if property_preference in {"office", "shop", "warehouse", "apartment", "villa", "townhouse"}:
        return f"{property_preference} brief"
    return "client brief"


def _target_property_types(request_profile: dict[str, Any]) -> set[str]:
    use_case = str(request_profile.get("use_case") or "")
    property_preference = str(request_profile.get("property_preference") or "")
    target_map = {
        "veterinary_clinic": {"shop", "retail", "office", "commercial"},
        "clinic": {"shop", "retail", "office", "commercial"},
        "office": {"office"},
        "retail": {"shop", "retail"},
        "warehouse": {"warehouse", "industrial"},
        "apartment": {"apartment"},
        "villa": {"villa"},
        "townhouse": {"townhouse", "villa"},
    }
    targets = set(target_map.get(use_case, set()))
    if property_preference:
        targets.add(property_preference)
    return {item for item in targets if item and item != "any"}


def _suitability_score(candidate: dict[str, Any], request_profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    score = 0.0
    strengths: list[str] = []
    risks: list[str] = []

    area = str(candidate.get("area") or "").lower()
    property_type = str(candidate.get("property_type") or "").lower()
    availability = str(candidate.get("availability") or "").lower()
    delivery = str(candidate.get("delivery_timeline") or "").lower()
    fit_label = str(candidate.get("fit_label") or candidate.get("clinic_fit") or "").lower()
    launch_mode = str(candidate.get("launch_mode") or "").lower()
    footfall = str(candidate.get("footfall_profile") or "").lower()
    parking = str(candidate.get("parking_profile") or "").lower()
    license_fit = str(candidate.get("license_fit") or "").lower()
    mode = str(candidate.get("commercial_mode") or "").lower()
    requested_area = str(request_profile.get("area") or "").lower()
    focus_label = _request_focus_label(request_profile)
    target_types = _target_property_types(request_profile)
    is_residential = str(request_profile.get("property_preference") or "") in {"apartment", "villa", "townhouse"}

    if requested_area and requested_area in area:
        score += 20
        strengths.append(f"exact {requested_area.title()} location")

    if target_types and property_type in target_types:
        score += 24
        strengths.append(f"{property_type} format matches the request profile")
    elif property_type:
        if property_type in {"shop", "retail"}:
            score += 14
            strengths.append("retail format supports customer-facing trading")
        elif property_type == "office":
            score += 12
            strengths.append("office format supports administrative or operational setup")
        elif property_type in {"warehouse", "industrial"}:
            score += 12
            strengths.append("warehouse format supports storage or logistics operations")
        elif property_type in {"apartment", "villa", "townhouse"}:
            score += 14
            strengths.append("residential format aligns with home-search requests")
        if target_types:
            risks.append("property type is adjacent to the request rather than an exact match")

    bedroom_delta, bedroom_strengths, bedroom_risks = _bedroom_score(candidate, request_profile)
    score += bedroom_delta
    strengths.extend(bedroom_strengths)
    risks.extend(bedroom_risks)

    bathroom_delta, bathroom_strengths, bathroom_risks = _bathroom_score(candidate, request_profile)
    score += bathroom_delta
    strengths.extend(bathroom_strengths)
    risks.extend(bathroom_risks)

    view_delta, view_strengths, view_risks = _view_score(candidate, request_profile)
    score += view_delta
    strengths.extend(view_strengths)
    risks.extend(view_risks)

    floor_delta, floor_strengths, floor_risks = _floor_score(candidate, request_profile)
    score += floor_delta
    strengths.extend(floor_strengths)
    risks.extend(floor_risks)

    parking_delta, parking_strengths, parking_risks = _parking_score(candidate, request_profile)
    score += parking_delta
    strengths.extend(parking_strengths)
    risks.extend(parking_risks)

    feature_delta, feature_strengths, feature_risks = _feature_score(candidate, request_profile)
    score += feature_delta
    strengths.extend(feature_strengths)
    risks.extend(feature_risks)

    source_url_delta, source_url_strengths, source_url_risks = _source_url_score(candidate, request_profile)
    score += source_url_delta
    strengths.extend(source_url_strengths)
    risks.extend(source_url_risks)

    furnishing_delta, furnishing_strengths, furnishing_risks = _furnishing_score(candidate, request_profile)
    score += furnishing_delta
    strengths.extend(furnishing_strengths)
    risks.extend(furnishing_risks)

    readiness_delta, readiness_strengths, readiness_risks = _readiness_score(candidate, request_profile)
    score += readiness_delta
    strengths.extend(readiness_strengths)
    risks.extend(readiness_risks)

    size_delta, size_strengths, size_risks = _size_score(candidate, request_profile)
    score += size_delta
    strengths.extend(size_strengths)
    risks.extend(size_risks)

    score += _price_score(candidate, mode)

    if availability in {"ready", "brand new", "fitted"} or "ready" in delivery or "immediate" in launch_mode:
        score += 16
        strengths.append("supports faster launch timeline")
    elif "2026" in delivery:
        score += 10
        strengths.append("near-term handover window")
    else:
        score += 4
        risks.append("handover delay pushes launch timeline")

    if fit_label == "high":
        score += 12
        strengths.append(f"layout and positioning align well with the {focus_label}")
    elif fit_label == "medium":
        score += 7
    else:
        risks.append("fit is strategic rather than direct")

    if footfall == "high":
        score += 10
        strengths.append("high catchment and customer-access potential")
    elif footfall == "medium":
        score += 6

    if parking == "strong":
        score += 6
        strengths.append("parking supports repeat visits and daily operations")
    elif parking == "limited":
        risks.append("parking may constrain peak-hour convenience")

    if license_fit == "probable":
        score += 8
    elif license_fit == "needs_confirmation" and not is_residential:
        score += 3
        risks.append("authority use approval still needs written confirmation")

    budget_delta, budget_strengths, budget_risks = _budget_score(candidate, request_profile)
    score += budget_delta
    strengths.extend(budget_strengths)
    risks.extend(budget_risks)

    return min(score, 100.0), strengths, risks


def _investment_score(candidate: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    notes: list[str] = []
    gross_yield = _percent_value(candidate.get("gross_yield_percent"))
    entry_psf = _psf(candidate.get("price_aed"), candidate.get("size_sqft"))
    if entry_psf is not None:
        if entry_psf <= 3200:
            score += 30
            notes.append(f"entry price around AED {entry_psf:,.0f}/sqft")
        elif entry_psf <= 4200:
            score += 22
            notes.append(f"entry price around AED {entry_psf:,.0f}/sqft")
        else:
            score += 14
            notes.append(f"premium entry around AED {entry_psf:,.0f}/sqft")

    delivery = str(candidate.get("delivery_timeline") or "")
    if "2026" in delivery:
        score += 16
        notes.append("earlier handover than most Dubai South off-plan retail stock")
    elif "2027" in delivery:
        score += 12
        notes.append("mid-cycle handover with neighborhood ramp-up upside")
    elif "2028" in delivery:
        score += 8
        notes.append("longer wait but deeper community build-out potential")

    if "payment_plan" in candidate and candidate["payment_plan"]:
        score += 12
        notes.append(f"payment plan {candidate['payment_plan']}")
    if str(candidate.get("developer") or "").strip():
        score += 8
        notes.append(f"developer: {candidate['developer']}")
    if gross_yield is not None:
        if gross_yield >= 7.0:
            score += 18
        elif gross_yield >= 5.0:
            score += 12
        else:
            score += 6
        notes.append(f"estimated gross yield around {gross_yield:.1f}%")
    return min(score, 100.0), notes


def _build_why_this_property(
    candidate: dict[str, Any],
    request_profile: dict[str, Any],
    recommendation_strengths: list[str],
    investment_notes: list[str],
) -> list[str]:
    reasons: list[str] = []
    requested_area = str(request_profile.get("area") or "").strip()
    if requested_area and requested_area.lower() in str(candidate.get("area") or "").lower():
        reasons.append(f"Direct match for the requested {requested_area.title()} location.")

    for item in recommendation_strengths:
        cleaned = str(item).strip()
        if cleaned and cleaned not in reasons:
            reasons.append(cleaned[0].upper() + cleaned[1:] + ("." if cleaned[-1] not in ".!?" else ""))
        if len(reasons) >= 3:
            break

    if len(reasons) < 3:
        for item in investment_notes:
            cleaned = str(item).strip()
            if cleaned and cleaned not in reasons:
                reasons.append(cleaned[0].upper() + cleaned[1:] + ("." if cleaned[-1] not in ".!?" else ""))
            if len(reasons) >= 3:
                break

    if len(reasons) < 3 and candidate.get("summary"):
        summary = str(candidate.get("summary") or "").strip()
        if summary:
            reasons.append(summary if summary[-1] in ".!?" else summary + ".")

    return reasons[:3]


def rank_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    request_profile = payload.get("request_profile") or {}
    for candidate in payload.get("public_listings") or []:
        suitability_score, recommendation_strengths, recommendation_risks = _suitability_score(candidate, request_profile)
        investment_score, investment_notes = _investment_score(candidate)
        combined = round(suitability_score * 0.72 + investment_score * 0.28, 1)
        row = dict(candidate)
        row.update(
            {
                "suitability_score": round(suitability_score, 1),
                "investment_score": round(investment_score, 1),
                "combined_score": combined,
                "constraint_fit": {
                    "bedroom_match": (
                        _bedrooms_int(candidate.get("bedrooms")) == _bedrooms_int(request_profile.get("bedroom_preference"))
                        if _bedrooms_int(request_profile.get("bedroom_preference")) is not None
                        else None
                    ),
                    "bathroom_match": (
                        _bathrooms_int(candidate.get("bathrooms")) == _bathrooms_int(request_profile.get("bathroom_preference"))
                        if _bathrooms_int(request_profile.get("bathroom_preference")) is not None
                        else None
                    ),
                    "view_match": (
                        str(request_profile.get("view_preference") or "").strip().lower() in _candidate_view_tokens(candidate)
                        if str(request_profile.get("view_preference") or "").strip()
                        else None
                    ),
                    "floor_match": (
                        _candidate_floor_preference(candidate) == str(request_profile.get("floor_preference") or "").strip().lower()
                        if str(request_profile.get("floor_preference") or "").strip()
                        else None
                    ),
                    "parking_match": (
                        _candidate_parking_profile(candidate) == "strong"
                        if str(request_profile.get("parking_preference") or "").strip().lower() == "required"
                        else (
                            _candidate_parking_profile(candidate) == "none"
                            if str(request_profile.get("parking_preference") or "").strip().lower() == "not_required"
                            else None
                        )
                    ),
                    "feature_matches": {
                        item: (item in _candidate_feature_tokens(candidate))
                        for item in [str(value).strip().lower() for value in (request_profile.get("feature_preferences") or []) if str(value).strip()]
                    },
                    "source_url_match": (
                        str(candidate.get("source_url") or "").strip().lower() == str(request_profile.get("source_url") or "").strip().lower()
                        if str(request_profile.get("source_url") or "").strip()
                        else None
                    ),
                    "furnishing_match": (
                        _candidate_furnishing(candidate) == str(request_profile.get("furnishing_preference") or "").strip().lower()
                        if str(request_profile.get("furnishing_preference") or "").strip()
                        else None
                    ),
                    "readiness_match": (
                        _candidate_readiness(candidate) == str(request_profile.get("readiness_preference") or "").strip().lower()
                        if str(request_profile.get("readiness_preference") or "").strip()
                        else None
                    ),
                    "within_budget": (
                        _money(candidate.get("price_aed")) <= _money(request_profile.get("max_price_aed"))
                        if _money(request_profile.get("max_price_aed")) > 0 and _money(candidate.get("price_aed")) > 0
                        else None
                    ),
                    "requested_size_sqft": {
                        "min": _money(request_profile.get("min_size_sqft")) or None,
                        "max": _money(request_profile.get("max_size_sqft")) or None,
                        "target": _money(request_profile.get("target_size_sqft")) or None,
                    },
                    "target_size_range_sqft": list(_requested_size_range(request_profile)) if _requested_size_range(request_profile) else [],
                },
                "constraint_match_priority": sum(
                    1
                    for flag in [
                        (
                            _bedrooms_int(candidate.get("bedrooms")) == _bedrooms_int(request_profile.get("bedroom_preference"))
                            if _bedrooms_int(request_profile.get("bedroom_preference")) is not None
                            else None
                        ),
                        (
                            _bathrooms_int(candidate.get("bathrooms")) == _bathrooms_int(request_profile.get("bathroom_preference"))
                            if _bathrooms_int(request_profile.get("bathroom_preference")) is not None
                            else None
                        ),
                        (
                            str(request_profile.get("view_preference") or "").strip().lower() in _candidate_view_tokens(candidate)
                            if str(request_profile.get("view_preference") or "").strip()
                            else None
                        ),
                        (
                            _candidate_floor_preference(candidate) == str(request_profile.get("floor_preference") or "").strip().lower()
                            if str(request_profile.get("floor_preference") or "").strip()
                            else None
                        ),
                        (
                            _candidate_parking_profile(candidate) == "strong"
                            if str(request_profile.get("parking_preference") or "").strip().lower() == "required"
                            else (
                                _candidate_parking_profile(candidate) == "none"
                                if str(request_profile.get("parking_preference") or "").strip().lower() == "not_required"
                                else None
                            )
                        ),
                        all(
                            item in _candidate_feature_tokens(candidate)
                            for item in [str(value).strip().lower() for value in (request_profile.get("feature_preferences") or []) if str(value).strip()]
                        ) if (request_profile.get("feature_preferences") or []) else None,
                        (
                            str(candidate.get("source_url") or "").strip().lower() == str(request_profile.get("source_url") or "").strip().lower()
                            if str(request_profile.get("source_url") or "").strip()
                            else None
                        ),
                        (
                            _candidate_furnishing(candidate) == str(request_profile.get("furnishing_preference") or "").strip().lower()
                            if str(request_profile.get("furnishing_preference") or "").strip()
                            else None
                        ),
                        (
                            _candidate_readiness(candidate) == str(request_profile.get("readiness_preference") or "").strip().lower()
                            if str(request_profile.get("readiness_preference") or "").strip()
                            else None
                        ),
                    ]
                    if flag is True
                ),
                "entry_psf_aed": round(_psf(candidate.get("price_aed"), candidate.get("size_sqft")) or 0, 2) or None,
                "gross_yield_percent": _percent_value(candidate.get("gross_yield_percent")),
                "recommendation_strengths": recommendation_strengths,
                "recommendation_risks": recommendation_risks,
                "clinic_fit_score": round(suitability_score, 1),
                "clinic_strengths": recommendation_strengths,
                "clinic_risks": recommendation_risks,
                "investment_notes": investment_notes,
                "why_this_property": _build_why_this_property(candidate, request_profile, recommendation_strengths, investment_notes),
                "maps_url": _google_maps_link(str(candidate.get("map_query") or candidate.get("building") or candidate.get("area") or "Dubai South")),
            }
        )
        ranked.append(row)
    ranked.sort(
        key=lambda item: (
            -item["combined_score"],
            -(item.get("constraint_match_priority") or 0),
            item.get("price_aed") or math.inf,
        )
    )
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked


def _proposal_pitch(top: list[dict[str, Any]], request_profile: dict[str, Any]) -> str:
    if not top:
        return "No ranked property options were available."
    first = top[0]
    second = top[1] if len(top) > 1 else None
    focus_label = _request_focus_label(request_profile)
    pitch = (
        f"The strongest option today is {first['title']} because it gives the best balance of location fit, "
        f"operational readiness, and alignment with the {focus_label}."
    )
    if second:
        pitch += (
            f" The secondary play is {second['title']}, which is stronger as a medium-term alternative than as the immediate lead recommendation."
        )
    return pitch


def _html_card(candidate: dict[str, Any]) -> str:
    price_line = _aed(candidate.get("price_aed"))
    if candidate.get("price_term"):
        price_line += f" {escape(str(candidate['price_term']))}"
    roi_line = "TBC"
    if candidate.get("gross_yield_percent") is not None:
        roi_line = _pct(float(candidate["gross_yield_percent"]))
    candidate_image_src = _image_src(str(candidate.get("hero_image_url") or ""))
    candidate_image_html = (
        f"<div class='candidate-image'><img src='{escape(candidate_image_src)}' alt='{escape(candidate.get('title') or 'Property image')}'></div>"
        if candidate_image_src
        else ""
    )
    investment_block = ""
    if candidate.get("investment_notes"):
        investment_block = "<div class='subblock'><h4>ROI / Investment Case</h4><ul>" + "".join(
            f"<li>{escape(note)}</li>" for note in candidate["investment_notes"]
        ) + "</ul></div>"
    why_this_property = candidate.get("why_this_property") or candidate.get("pros") or candidate.get("recommendation_strengths") or candidate.get("clinic_strengths") or []
    cons = candidate.get("cons") or candidate.get("recommendation_risks") or candidate.get("clinic_risks") or []
    source_links = candidate.get("source_links") or []
    return f"""
    <section class="candidate">
      {candidate_image_html}
      <div class="candidate-top">
        <div>
          <div class="eyebrow">Rank #{candidate['rank']}</div>
          <h3>{escape(candidate['title'])}</h3>
          <p class="meta">{escape(str(candidate.get('building') or ''))} · {escape(str(candidate.get('area') or ''))}</p>
        </div>
        <div class="score-pill">{candidate['combined_score']:.1f}</div>
      </div>
      <div class="stats">
        <div><span>Price</span><strong>{escape(price_line)}</strong></div>
        <div><span>Type</span><strong>{escape(str(candidate.get('property_type') or ''))}</strong></div>
        <div><span>Area</span><strong>{escape(str(candidate.get('size_sqft') or ''))} sqft</strong></div>
        <div><span>Handover</span><strong>{escape(str(candidate.get('delivery_timeline') or 'TBC'))}</strong></div>
        <div><span>ROI / Yield</span><strong>{escape(roi_line)}</strong></div>
      </div>
      <p class="summary">{escape(str(candidate.get('summary') or ''))}</p>
      <div class="split">
        <div class="subblock">
          <h4>Why This Property</h4>
          <ul>{''.join(f'<li>{escape(item)}</li>' for item in why_this_property)}</ul>
        </div>
        <div class="subblock">
          <h4>Risks / Watchouts</h4>
          <ul>{''.join(f'<li>{escape(item)}</li>' for item in cons)}</ul>
        </div>
      </div>
      {investment_block}
      <div class="subblock">
        <h4>Source Links</h4>
        <ul>{''.join(f"<li><a href='{escape(link)}'>{escape(link)}</a></li>" for link in source_links)}</ul>
      </div>
      <div class="actions">
        <a href="{escape(candidate['maps_url'])}">Open Map</a>
        <a href="{escape(str(candidate.get('source_url') or candidate['maps_url']))}">Open Listing</a>
      </div>
    </section>
    """


def render_html(result: dict[str, Any]) -> str:
    case = result["case"]
    request_profile = result.get("request_profile") or {}
    focus_label = _request_focus_label(request_profile)
    hero_uri = _image_src(case.get("hero_image_path") or "")
    hero_html = (
        f"<div class='hero-image'><img src='{escape(hero_uri)}' alt='Dubai South internal inventory context image'><p>Internal AIOS Dubai South image context.</p></div>"
        if hero_uri
        else ""
    )
    market_points = "".join(f"<li>{escape(item)}</li>" for item in result.get("market_highlights") or [])
    compliance_points = "".join(f"<li>{escape(item)}</li>" for item in result.get("compliance_gates") or [])
    source_points = "".join(
        f"<li><a href='{escape(item['url'])}'>{escape(item['label'])}</a> · {escape(item['date'])}</li>"
        for item in result.get("source_register") or []
    )
    candidate_cards = "".join(_html_card(candidate) for candidate in result.get("top_candidates") or [])
    next_steps = "".join(f"<li>{escape(step)}</li>" for step in result.get("next_steps") or [])
    review_notes = "".join(f"<li>{escape(item)}</li>" for item in result.get("agent_review", {}).get("review_notes", []))
    approval_posture = escape(str(result.get("agent_review", {}).get("approval_posture") or "Pending review"))
    internal_snapshot = result.get("internal_market_snapshot") or {}
    internal_matches = result.get("internal_inventory_matches") or []
    internal_match_lines = "".join(
        f"<li>{escape(item.get('project') or 'Unknown')} · {escape(item.get('area') or 'Unknown')} · "
        f"{escape(item.get('property_type') or 'Unknown')} · {_aed(item.get('price_aed'))} · score {escape(str(item.get('score') or '0'))}</li>"
        for item in internal_matches[:6]
    )
    market_snapshot_lines = []
    if internal_snapshot.get("match_count"):
        market_snapshot_lines.append(f"<li>Internal matches: {escape(str(internal_snapshot.get('match_count')))}</li>")
    if internal_snapshot.get("priced_match_count"):
        market_snapshot_lines.append(f"<li>Priced matches: {escape(str(internal_snapshot.get('priced_match_count')))}</li>")
    if internal_snapshot.get("median_price_aed"):
        market_snapshot_lines.append(f"<li>Median internal price: {escape(_aed(internal_snapshot.get('median_price_aed')))}</li>")
    if internal_snapshot.get("min_price_aed") and internal_snapshot.get("max_price_aed"):
        market_snapshot_lines.append(
            f"<li>Internal price band: {escape(_aed(internal_snapshot.get('min_price_aed')))} to {escape(_aed(internal_snapshot.get('max_price_aed')))}</li>"
        )
    if internal_snapshot.get("top_projects"):
        market_snapshot_lines.append(
            f"<li>Top internal projects: {escape(', '.join(internal_snapshot.get('top_projects') or []))}</li>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(result['proposal_title'])}</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --ink: #171411;
      --muted: #6d645a;
      --line: rgba(23,20,17,0.12);
      --paper: rgba(255,255,255,0.82);
      --accent: #8a5a2f;
      --accent-2: #24413d;
      --shadow: 0 22px 60px rgba(32, 24, 16, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top left, rgba(138,90,47,0.18), transparent 28%),
        linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
    }}
    .wrap {{ max-width: 1160px; margin: 0 auto; padding: 40px 24px 72px; }}
    .hero {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 28px;
      align-items: end;
      padding: 34px;
      background: linear-gradient(135deg, rgba(255,255,255,0.82), rgba(250,244,236,0.68));
      border: 1px solid var(--line);
      border-radius: 32px;
      box-shadow: var(--shadow);
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 12px;
      color: var(--accent);
      margin-bottom: 12px;
    }}
    h1 {{ margin: 0 0 10px; font-size: 54px; line-height: 0.95; }}
    .lede {{ color: var(--muted); font-size: 19px; line-height: 1.6; }}
    .hero-image img {{
      width: 100%;
      border-radius: 20px;
      display: block;
      aspect-ratio: 4 / 3;
      object-fit: cover;
    }}
    .hero-image p {{ margin: 10px 0 0; color: var(--muted); font-size: 13px; }}
    .candidate-image {{ margin: -24px -24px 18px; }}
    .candidate-image img {{
      width: calc(100% + 48px);
      margin-left: -24px;
      margin-right: -24px;
      border-radius: 24px 24px 0 0;
      display: block;
      aspect-ratio: 16 / 10;
      object-fit: cover;
      border-bottom: 1px solid var(--line);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
      margin-top: 24px;
    }}
    .panel, .candidate {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }}
    .panel {{ padding: 24px; }}
    .panel h3, .candidate h3 {{ margin: 0 0 10px; font-size: 28px; }}
    .panel ul, .candidate ul {{ margin: 0; padding-left: 18px; line-height: 1.6; }}
    .candidate {{
      padding: 28px;
      margin-top: 20px;
    }}
    .candidate-top {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
    }}
    .score-pill {{
      min-width: 74px;
      text-align: center;
      padding: 12px 14px;
      border-radius: 999px;
      background: var(--accent-2);
      color: #fff;
      font-weight: 700;
      font-size: 18px;
    }}
    .meta, .summary {{ color: var(--muted); }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin: 18px 0;
    }}
    .stats div {{
      padding: 14px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
    }}
    .stats span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 4px;
    }}
    .stats strong {{ font-size: 18px; }}
    .split {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-top: 16px;
    }}
    .subblock {{
      padding: 16px 18px;
      border-radius: 18px;
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
    }}
    .subblock h4 {{ margin: 0 0 10px; font-size: 16px; }}
    .actions {{
      display: flex;
      gap: 14px;
      margin-top: 18px;
      flex-wrap: wrap;
    }}
    .actions a {{
      text-decoration: none;
      color: var(--ink);
      border-bottom: 1px solid var(--ink);
      padding-bottom: 1px;
    }}
    .section-title {{
      margin: 34px 0 12px;
      font-size: 34px;
    }}
    @media (max-width: 900px) {{
      .hero, .grid, .split, .stats {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 40px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div>
        <div class="eyebrow">AIOS Premium Property Proposal</div>
        <h1>{escape(result['proposal_title'])}</h1>
        <p class="lede">{escape(result['executive_pitch'])}</p>
        <p class="lede">Client brief: {escape(case['client_request'])}</p>
        <p class="lede">Request focus: {escape(focus_label)}</p>
      </div>
      {hero_html}
    </section>

    <div class="grid">
      <section class="panel">
        <h3>Market Why</h3>
        <ul>{market_points}</ul>
      </section>
      <section class="panel">
        <h3>Compliance Gates</h3>
        <ul>{compliance_points}</ul>
      </section>
      <section class="panel">
        <h3>Source Register</h3>
        <ul>{source_points}</ul>
      </section>
    </div>

    <h2 class="section-title">Top Recommendations</h2>
    {candidate_cards}

    <div class="grid">
      <section class="panel">
        <h3>Sales Pitch</h3>
        <p class="lede">{escape(result['sales_pitch'])}</p>
      </section>
      <section class="panel">
        <h3>Next Steps</h3>
        <ul>{next_steps}</ul>
      </section>
      <section class="panel">
        <h3>Internal Evidence</h3>
        <ul>{''.join(f"<li>{escape(item)}</li>" for item in result.get('internal_evidence') or [])}</ul>
      </section>
      <section class="panel">
        <h3>Internal Market Snapshot</h3>
        <ul>{''.join(market_snapshot_lines) or '<li>No internal market snapshot available yet.</li>'}</ul>
      </section>
      <section class="panel">
        <h3>Internal Inventory Matches</h3>
        <ul>{internal_match_lines or '<li>No internal inventory matches surfaced for this brief.</li>'}</ul>
      </section>
      <section class="panel">
        <h3>Agent Review</h3>
        <p class="lede">{approval_posture}</p>
        <ul>{review_notes}</ul>
      </section>
    </div>
  </div>
</body>
</html>
"""


def export_pdf_with_reportlab(result: dict[str, Any], pdf_path: Path) -> bool:
    width, height = A4
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    margin = 18 * mm
    y = height - margin

    def line_gap(points: float = 14) -> None:
        nonlocal y
        y -= points

    def write(text: str, *, font: str = "Helvetica", size: int = 11, color=colors.black) -> None:
        nonlocal y
        if y < margin:
            c.showPage()
            y = height - margin
        c.setFont(font, size)
        c.setFillColor(color)
        for part in _wrap_text(text, width - (margin * 2), size):
            c.drawString(margin, y, part)
            line_gap(size + 3)

    c.setTitle(result["proposal_title"])
    c.setFillColor(colors.HexColor("#f3efe6"))
    c.rect(0, 0, width, height, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#8a5a2f"))
    c.rect(0, height - 52, width, 52, stroke=0, fill=1)
    y = height - 26
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin, y, result["proposal_title"])
    y = height - 74
    write(result["executive_pitch"], font="Helvetica-Bold", size=14, color=colors.HexColor("#171411"))
    line_gap(6)
    write(f"Client brief: {result['case']['client_request']}", size=11, color=colors.HexColor("#5b544c"))
    line_gap(8)
    write("Top Recommendations", font="Helvetica-Bold", size=15, color=colors.HexColor("#24413d"))
    for candidate in result.get("top_candidates") or []:
        line_gap(4)
        write(f"#{candidate['rank']} {candidate['title']}", font="Helvetica-Bold", size=13)
        write(
            f"{candidate.get('building', '')} | {candidate.get('area', '')} | {candidate.get('property_type', '').title()} | "
            f"{_aed(candidate.get('price_aed'))} {candidate.get('price_term', '')}".strip(),
            size=10,
            color=colors.HexColor("#5b544c"),
        )
        write(
            f"Suitability score {candidate['suitability_score']:.1f} | Investment score {candidate['investment_score']:.1f} | Combined score {candidate['combined_score']:.1f}",
            size=10,
            color=colors.HexColor("#5b544c"),
        )
        if candidate.get("gross_yield_percent") is not None:
            write(f"Estimated gross yield {candidate['gross_yield_percent']:.1f}%", size=10, color=colors.HexColor("#5b544c"))
        write("Why this property:", font="Helvetica-Bold", size=10)
        for item in candidate.get("why_this_property") or candidate.get("pros") or []:
            write(f"- {item}", size=10)
        write("Risks / watchouts:", font="Helvetica-Bold", size=10, color=colors.HexColor("#7a3f2f"))
        for item in candidate.get("cons") or []:
            write(f"- Risk: {item}", size=10, color=colors.HexColor("#7a3f2f"))
        if candidate.get("investment_notes"):
            write("ROI / investment case:", font="Helvetica-Bold", size=10)
            for item in candidate["investment_notes"]:
                write(f"- {item}", size=10)
        line_gap(6)
    write("Market Highlights", font="Helvetica-Bold", size=15, color=colors.HexColor("#24413d"))
    for item in result.get("market_highlights") or []:
        write(f"- {item}", size=10)
    line_gap(6)
    internal_snapshot = result.get("internal_market_snapshot") or {}
    internal_matches = result.get("internal_inventory_matches") or []
    write("Internal Market Snapshot", font="Helvetica-Bold", size=15, color=colors.HexColor("#24413d"))
    if internal_snapshot.get("match_count"):
        write(f"- Internal matches: {internal_snapshot.get('match_count')}", size=10)
    if internal_snapshot.get("priced_match_count"):
        write(f"- Priced matches: {internal_snapshot.get('priced_match_count')}", size=10)
    if internal_snapshot.get("median_price_aed"):
        write(f"- Median internal price: {_aed(internal_snapshot.get('median_price_aed'))}", size=10)
    if internal_snapshot.get("min_price_aed") and internal_snapshot.get("max_price_aed"):
        write(
            f"- Internal price band: {_aed(internal_snapshot.get('min_price_aed'))} to {_aed(internal_snapshot.get('max_price_aed'))}",
            size=10,
        )
    if internal_snapshot.get("top_projects"):
        write(f"- Top internal projects: {', '.join(internal_snapshot.get('top_projects') or [])}", size=10)
    if not internal_snapshot:
        write("- No internal market snapshot available.", size=10)
    line_gap(6)
    write("Internal Inventory Matches", font="Helvetica-Bold", size=15, color=colors.HexColor("#24413d"))
    if internal_matches:
        for item in internal_matches[:6]:
            write(
                f"- {item.get('project') or 'Unknown'} | {item.get('area') or 'Unknown'} | "
                f"{item.get('property_type') or 'Unknown'} | {_aed(item.get('price_aed'))} | score {item.get('score') or 0}",
                size=10,
            )
    else:
        write("- No internal inventory matches surfaced for this brief.", size=10)
    line_gap(6)
    write("Compliance Gates", font="Helvetica-Bold", size=15, color=colors.HexColor("#24413d"))
    for item in result.get("compliance_gates") or []:
        write(f"- {item}", size=10)
    line_gap(6)
    write("Next Steps", font="Helvetica-Bold", size=15, color=colors.HexColor("#24413d"))
    for item in result.get("next_steps") or []:
        write(f"- {item}", size=10)
    line_gap(6)
    write("Agent Review", font="Helvetica-Bold", size=15, color=colors.HexColor("#24413d"))
    if result.get("agent_review", {}).get("approval_posture"):
        write(str(result["agent_review"]["approval_posture"]), size=10)
    for item in result.get("agent_review", {}).get("review_notes") or []:
        write(f"- {item}", size=10)
    c.save()
    return pdf_path.exists()


def export_screenshot(result: dict[str, Any], *, chrome_path: Path = DEFAULT_CHROME_PATH) -> bool:
    html_path = Path(result["artifacts"]["html"])
    screenshot_path = Path(result["artifacts"]["screenshot"])
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    temp_screenshot_path = screenshot_path.with_name(f".{screenshot_path.stem}-tmp{screenshot_path.suffix}")
    if temp_screenshot_path.exists():
        temp_screenshot_path.unlink()

    html_uri = html_path.resolve().as_uri()
    if chrome_path.exists():
        chrome_args = [
            str(chrome_path),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--window-size=1600,2400",
            f"--screenshot={temp_screenshot_path}",
            html_uri,
        ]
        try:
            proc = subprocess.Popen(chrome_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception:
            proc = None
        if proc is not None:
            deadline = time.time() + 45
            while time.time() < deadline:
                if temp_screenshot_path.exists() and temp_screenshot_path.stat().st_size > 0:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        proc.kill()
                    temp_screenshot_path.replace(screenshot_path)
                    return True
                if proc.poll() is not None:
                    if proc.returncode == 0 and temp_screenshot_path.exists() and temp_screenshot_path.stat().st_size > 0:
                        temp_screenshot_path.replace(screenshot_path)
                        return True
                    return screenshot_path.exists() and screenshot_path.stat().st_size > 0
                time.sleep(0.5)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            if temp_screenshot_path.exists() and temp_screenshot_path.stat().st_size > 0:
                temp_screenshot_path.replace(screenshot_path)
                return True
            if temp_screenshot_path.exists():
                temp_screenshot_path.unlink()

    preview_name = f"{html_path.name}.png"
    preview_path = html_path.parent / preview_name
    if preview_path.exists():
        preview_path.unlink()
    qlmanage_args = [
        "qlmanage",
        "-t",
        "-s",
        "1600",
        "-o",
        str(html_path.parent),
        str(html_path),
    ]
    if _run_command(qlmanage_args) and preview_path.exists():
        preview_path.replace(screenshot_path)
        return screenshot_path.exists()
    return False


def _wrap_text(text: str, max_width: float, font_size: int) -> list[str]:
    rough_chars = max(40, int(max_width / (font_size * 0.48)))
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        tentative = word if not current else f"{current} {word}"
        if len(tentative) <= rough_chars:
            current = tentative
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def build(payload: dict[str, Any], *, case_name: str = "") -> dict[str, Any]:
    ranked = rank_candidates(payload)
    top_candidates = ranked[:3]
    case = payload["case"]
    top_title = top_candidates[0]["title"] if top_candidates else "No candidate selected"
    request_profile = payload.get("request_profile") or {}
    market_highlights = payload.get("market_highlights") or [
        "Dubai South remains a strategic growth corridor tied to Al Maktoum International Airport, free zone business setup, and large-scale mixed-use expansion.",
        "Dubai South confirmed the Residential District now includes retail shops, a 50,000 sq ft hypermarket, a mosque, a petrol station, and a bus route linking to Expo Metro.",
        "Dubai South Business Park is marketed with modern offices, turnkey solutions, and airport/port access, which supports immediate operational setups.",
    ]
    compliance_gates = payload.get("compliance_gates") or [
        "Usage, fit-out scope, and authority approvals must match the intended operating model before deal commitment.",
        "Commercial terms, service charges, and handover conditions must be checked against the latest live source documents.",
        "Licensing and use-class constraints must be confirmed in writing before the client commits capital or signs a lease.",
    ]
    sales_pitch = payload.get("sales_pitch") or (
        f"Lead with {top_title} as the strongest option for the current brief. "
        f"Keep the remaining shortlisted assets as fallback paths while pricing, approvals, and final fit are validated."
    )
    result = {
        "generated_at": _now(),
        "case": case,
        "proposal_title": payload.get("proposal_title") or f"AIOS Realty Proposal - {case.get('client_name', 'Client')}",
        "executive_pitch": payload.get("executive_pitch") or _proposal_pitch(top_candidates, request_profile),
        "sales_pitch": sales_pitch,
        "top_candidates": top_candidates,
        "market_highlights": market_highlights,
        "compliance_gates": compliance_gates,
        "internal_evidence": payload.get("internal_inventory_evidence") or [],
        "internal_inventory_matches": payload.get("internal_inventory_matches") or [],
        "internal_market_snapshot": payload.get("internal_market_snapshot") or {},
        "next_steps": payload.get("next_steps") or [
            "Confirm exact live availability and current commercial terms before client send.",
            "Request floor plans, service-charge schedule, and fit-out or handover rules for the top two properties.",
            "Validate use approval, licensing path, and technical constraints against the intended operating model.",
            "Prepare offer and negotiation strategy for the lead recommendation and backup options.",
        ],
        "source_register": payload.get("source_register") or [],
        "request_profile": request_profile,
        "evidence_trail": payload.get("evidence_trail") or [],
        "agent_review": payload.get("agent_review") or {},
    }
    report_name = _slug(case_name or case.get("case_id") or case.get("client_request") or "property-proposal")
    json_path = REPORTS_DIR / f"{report_name}.json"
    html_path = REPORTS_DIR / f"{report_name}.html"
    pdf_path = REPORTS_DIR / f"{report_name}.pdf"
    screenshot_path = REPORTS_DIR / f"{report_name}.png"
    result["artifacts"] = {
        "json": str(json_path),
        "html": str(html_path),
        "pdf": str(pdf_path),
        "screenshot": str(screenshot_path),
    }
    _write_text(html_path, render_html(result))
    _write_text(json_path, json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result


def export_visual_artifacts(result: dict[str, Any], *, chrome_path: Path = DEFAULT_CHROME_PATH) -> dict[str, Any]:
    pdf_path = Path(result["artifacts"]["pdf"])
    export = {
        "chrome_available": chrome_path.exists(),
        "pdf_exported": export_pdf_with_reportlab(result, pdf_path),
        "screenshot_exported": export_screenshot(result, chrome_path=chrome_path),
        "pdf_engine": "reportlab",
    }
    return export


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a premium AIOS client property proposal.")
    parser.add_argument("--case-json", default=str(DEFAULT_CASE_PATH), help="Path to case JSON input.")
    parser.add_argument("--case-name", default="", help="Optional output basename.")
    parser.add_argument("--skip-export", action="store_true", help="Skip PDF and screenshot export.")
    args = parser.parse_args()

    payload = _read_json(Path(args.case_json))
    result = build(payload, case_name=args.case_name)
    if not args.skip_export:
        result["export"] = export_visual_artifacts(result)
        _write_text(Path(result["artifacts"]["json"]), json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
