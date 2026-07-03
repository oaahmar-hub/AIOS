#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from realty_intelligence_agent_runtime import run_agent


RUNTIME_DIR = Path(__file__).resolve().parent
REPORT_PATH = RUNTIME_DIR.parent / "reports" / "REALTY_BRAIN_VALIDATION.json"


SCENARIOS = [
    {
        "name": "text_veterinary_clinic_dubai_south",
        "kwargs": {
            "request_text": "I want a veterinary clinic in Dubai South",
            "case_name": "validate-text-vet-dubai-south",
        },
        "expect": {
            "source_mode": "text",
            "area": "dubai south",
            "use_case": "veterinary_clinic",
            "requires_public_sources": True,
        },
    },
    {
        "name": "voice_apartment_dubai_marina",
        "kwargs": {
            "voice_transcript": "Need a 2 bedroom apartment in Dubai Marina under 2000000",
            "case_name": "validate-voice-marina-apartment",
        },
        "expect": {
            "source_mode": "voice",
            "area": "dubai marina",
            "use_case": "apartment",
            "requires_public_sources": True,
            "requires_roi": True,
            "bedroom_preference": "2",
            "max_price_aed": 2000000,
        },
    },
    {
        "name": "text_apartment_palm_jumeirah",
        "kwargs": {
            "request_text": "Need a 2 bedroom apartment in Palm Jumeirah",
            "case_name": "validate-text-palm-jumeirah-apartment",
        },
        "expect": {
            "source_mode": "text",
            "area": "palm jumeirah",
            "use_case": "apartment",
            "requires_public_sources": True,
            "requires_images": True,
            "bedroom_preference": "2",
        },
    },
    {
        "name": "url_bayut_dubai_south_office",
        "kwargs": {
            "source_url": "https://www.bayut.com/to-rent/offices/dubai/dubai-south/",
            "case_name": "validate-url-bayut-dubai-south-office",
        },
        "expect": {
            "source_mode": "url",
            "area": "dubai south",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
        },
    },
    {
        "name": "url_propertyfinder_direct_office",
        "kwargs": {
            "source_url": "https://www.propertyfinder.ae/en/plp/commercial-rent/office-space-for-rent-dubai-dubai-south-dubai-world-central-business-park-97364276.html",
            "case_name": "validate-url-propertyfinder-direct-office",
        },
        "expect": {
            "source_mode": "url",
            "area": "dubai south",
            "use_case": "office",
            "requires_public_sources": True,
        },
    },
    {
        "name": "url_propertyfinder_broker",
        "kwargs": {
            "source_url": "https://www.propertyfinder.ae/en/broker/home-sweet-home-real-estate-7889",
            "case_name": "validate-url-propertyfinder-broker",
        },
        "expect": {
            "source_mode": "url",
            "requires_public_sources": True,
        },
    },
    {
        "name": "text_warehouse_dubai_south",
        "kwargs": {
            "request_text": "I need a warehouse in Dubai South",
            "case_name": "validate-text-warehouse-dubai-south",
        },
        "expect": {
            "source_mode": "text",
            "area": "dubai south",
            "use_case": "warehouse",
            "requires_public_sources": True,
        },
    },
    {
        "name": "text_office_business_bay",
        "kwargs": {
            "request_text": "Need an office in Business Bay",
            "case_name": "validate-text-office-business-bay",
        },
        "expect": {
            "source_mode": "text",
            "area": "business bay",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
        },
    },
    {
        "name": "text_office_business_bay_budget",
        "kwargs": {
            "request_text": "Need an office in Business Bay under 180000",
            "case_name": "validate-text-office-business-bay-budget",
        },
        "expect": {
            "source_mode": "text",
            "area": "business bay",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
            "max_price_aed": 180000,
        },
    },
    {
        "name": "text_office_business_bay_budget_size",
        "kwargs": {
            "request_text": "Need an office in Business Bay around 900 sqft under 180000",
            "case_name": "validate-text-office-business-bay-budget-size",
        },
        "expect": {
            "source_mode": "text",
            "area": "business bay",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
            "max_price_aed": 180000,
            "target_size_sqft": 900,
            "top_candidate_max_size_delta": 175,
        },
    },
    {
        "name": "text_office_business_bay_with_parking",
        "kwargs": {
            "request_text": "Need an office in Business Bay with parking under 180000",
            "case_name": "validate-text-office-business-bay-with-parking",
        },
        "expect": {
            "source_mode": "text",
            "area": "business bay",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
            "parking_preference": "required",
            "max_price_aed": 180000,
            "top_candidate_title_includes": "Parking",
        },
    },
    {
        "name": "text_office_business_bay_furnished",
        "kwargs": {
            "request_text": "Need a furnished office in Business Bay under 180000",
            "case_name": "validate-text-office-business-bay-furnished",
        },
        "expect": {
            "source_mode": "text",
            "area": "business bay",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
            "max_price_aed": 180000,
            "furnishing_preference": "furnished",
            "top_candidate_title_includes": "Furnished",
        },
    },
    {
        "name": "text_office_business_bay_ready",
        "kwargs": {
            "request_text": "Need a ready office in Business Bay under 180000",
            "case_name": "validate-text-office-business-bay-ready",
        },
        "expect": {
            "source_mode": "text",
            "area": "business bay",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
            "readiness_preference": "ready",
            "max_price_aed": 180000,
            "top_candidate_title_includes": "Fitted",
        },
    },
    {
        "name": "voice_apartment_dubai_marina_3bath",
        "kwargs": {
            "voice_transcript": "Need a 2 bedroom 3 bathroom apartment in Dubai Marina under 3500000",
            "case_name": "validate-voice-marina-apartment-3bath",
        },
        "expect": {
            "source_mode": "voice",
            "area": "dubai marina",
            "use_case": "apartment",
            "requires_public_sources": True,
            "requires_roi": True,
            "bedroom_preference": "2",
            "bathroom_preference": "3",
            "max_price_aed": 3500000,
            "top_candidate_min_bathrooms": 3,
        },
    },
    {
        "name": "url_apartment_dubai_marina_upgraded",
        "kwargs": {
            "request_text": "Need an upgraded 2 bedroom 3 bathroom apartment in Dubai Marina under 3500000",
            "source_url": "https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-dubai-marina-ocean-heights-84894360.html",
            "case_name": "validate-url-marina-apartment-upgraded",
        },
        "expect": {
            "source_mode": "url",
            "area": "dubai marina",
            "use_case": "apartment",
            "requires_public_sources": True,
            "requires_images": True,
            "bedroom_preference": "2",
            "bathroom_preference": "3",
            "feature_preferences": ["upgraded"],
            "max_price_aed": 3500000,
            "top_candidate_title_includes": "Upgraded",
        },
    },
    {
        "name": "voice_apartment_dubai_marina_palm_view",
        "kwargs": {
            "voice_transcript": "Need a 2 bedroom apartment in Dubai Marina with Palm view under 3500000",
            "case_name": "validate-voice-marina-apartment-palm-view",
        },
        "expect": {
            "source_mode": "voice",
            "area": "dubai marina",
            "use_case": "apartment",
            "requires_public_sources": True,
            "requires_roi": True,
            "bedroom_preference": "2",
            "view_preference": "palm",
            "max_price_aed": 3500000,
            "top_candidate_title_includes": "Palm View",
        },
    },
    {
        "name": "text_office_business_bay_high_floor",
        "kwargs": {
            "request_text": "Need a high floor office in Business Bay under 180000",
            "case_name": "validate-text-office-business-bay-high-floor",
        },
        "expect": {
            "source_mode": "text",
            "area": "business bay",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
            "floor_preference": "high",
            "max_price_aed": 180000,
            "top_candidate_title_includes": "High Floor",
        },
    },
    {
        "name": "text_clinic_jvc",
        "kwargs": {
            "request_text": "Need a clinic in JVC",
            "case_name": "validate-text-clinic-jvc",
        },
        "expect": {
            "source_mode": "text",
            "area": "jvc",
            "use_case": "clinic",
            "requires_public_sources": True,
            "requires_images": True,
        },
    },
    {
        "name": "url_generic_dubai_south_office_page",
        "kwargs": {
            "source_url": "https://www.dubaisouth.ae/en/work/commercial-property/offices",
            "case_name": "validate-url-generic-dubai-south-office-page",
        },
        "expect": {
            "source_mode": "url",
            "area": "dubai south",
            "use_case": "office",
            "requires_public_sources": True,
            "requires_images": True,
        },
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _candidate_has_required_fields(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("title")
        and candidate.get("maps_url")
        and isinstance(candidate.get("why_this_property"), list)
        and len(candidate.get("why_this_property") or []) >= 1
        and isinstance(candidate.get("pros"), list)
        and isinstance(candidate.get("cons"), list)
        and "combined_score" in candidate
    )


def _saved_artifact_paths(case_name: str) -> dict[str, str]:
    base = RUNTIME_DIR.parent / "reports" / "client_property_proposals" / case_name
    return {
        "json": str(base.with_suffix(".json")),
        "html": str(base.with_suffix(".html")),
        "pdf": str(base.with_suffix(".pdf")),
        "screenshot": str(base.with_suffix(".png")),
    }


def _load_saved_result(case_name: str) -> dict[str, Any]:
    artifact_paths = _saved_artifact_paths(case_name)
    json_path = Path(artifact_paths["json"])
    result = json.loads(json_path.read_text(encoding="utf-8"))
    result["artifacts"] = result.get("artifacts") or artifact_paths
    if not result.get("export"):
        result["export"] = {
            "pdf_exported": Path(artifact_paths["pdf"]).exists(),
            "screenshot_exported": Path(artifact_paths["screenshot"]).exists(),
            "pdf_engine": "artifact_reuse",
        }
    return result


def validate_result(name: str, result: dict[str, Any], expect: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    request_profile = result.get("request_profile") or {}
    top_candidates = result.get("top_candidates") or []
    source_register = result.get("source_register") or []
    artifacts = result.get("artifacts") or {}
    export = result.get("export") or {}

    if request_profile.get("source_mode") != expect.get("source_mode"):
        errors.append(f"source_mode expected {expect.get('source_mode')} got {request_profile.get('source_mode')}")
    if expect.get("area") and request_profile.get("area") != expect.get("area"):
        errors.append(f"area expected {expect.get('area')} got {request_profile.get('area')}")
    if expect.get("use_case") and request_profile.get("use_case") != expect.get("use_case"):
        errors.append(f"use_case expected {expect.get('use_case')} got {request_profile.get('use_case')}")
    if expect.get("bedroom_preference") and str(request_profile.get("bedroom_preference") or "") != str(expect.get("bedroom_preference")):
        errors.append(
            f"bedroom_preference expected {expect.get('bedroom_preference')} got {request_profile.get('bedroom_preference')}"
        )
    if expect.get("bathroom_preference") and str(request_profile.get("bathroom_preference") or "") != str(expect.get("bathroom_preference")):
        errors.append(
            f"bathroom_preference expected {expect.get('bathroom_preference')} got {request_profile.get('bathroom_preference')}"
        )
    if expect.get("view_preference") and str(request_profile.get("view_preference") or "") != str(expect.get("view_preference")):
        errors.append(
            f"view_preference expected {expect.get('view_preference')} got {request_profile.get('view_preference')}"
        )
    if expect.get("floor_preference") and str(request_profile.get("floor_preference") or "") != str(expect.get("floor_preference")):
        errors.append(
            f"floor_preference expected {expect.get('floor_preference')} got {request_profile.get('floor_preference')}"
        )
    if expect.get("parking_preference") and str(request_profile.get("parking_preference") or "") != str(expect.get("parking_preference")):
        errors.append(
            f"parking_preference expected {expect.get('parking_preference')} got {request_profile.get('parking_preference')}"
        )
    if expect.get("feature_preferences"):
        actual_features = [str(item).strip().lower() for item in (request_profile.get("feature_preferences") or []) if str(item).strip()]
        expected_features = [str(item).strip().lower() for item in expect.get("feature_preferences") or []]
        for feature in expected_features:
            if feature not in actual_features:
                errors.append(f"feature_preferences missing expected value {feature}")
    if expect.get("furnishing_preference") and str(request_profile.get("furnishing_preference") or "") != str(expect.get("furnishing_preference")):
        errors.append(
            f"furnishing_preference expected {expect.get('furnishing_preference')} got {request_profile.get('furnishing_preference')}"
        )
    if expect.get("readiness_preference") and str(request_profile.get("readiness_preference") or "") != str(expect.get("readiness_preference")):
        errors.append(
            f"readiness_preference expected {expect.get('readiness_preference')} got {request_profile.get('readiness_preference')}"
        )
    if expect.get("max_price_aed") and int(request_profile.get("max_price_aed") or 0) != int(expect.get("max_price_aed")):
        errors.append(f"max_price_aed expected {int(expect.get('max_price_aed'))} got {int(request_profile.get('max_price_aed') or 0)}")
    if expect.get("target_size_sqft") and int(request_profile.get("target_size_sqft") or 0) != int(expect.get("target_size_sqft")):
        errors.append(
            f"target_size_sqft expected {int(expect.get('target_size_sqft'))} got {int(request_profile.get('target_size_sqft') or 0)}"
        )
    if len(top_candidates) < 3:
        errors.append(f"expected at least 3 top candidates, got {len(top_candidates)}")
    if not result.get("sales_pitch"):
        errors.append("sales_pitch missing")
    if not result.get("executive_pitch"):
        errors.append("executive_pitch missing")
    if not result.get("market_highlights"):
        errors.append("market_highlights missing")
    if not result.get("compliance_gates"):
        errors.append("compliance_gates missing")
    if not result.get("next_steps"):
        errors.append("next_steps missing")
    if not result.get("internal_evidence"):
        errors.append("internal_evidence missing")
    if not result.get("internal_inventory_matches"):
        errors.append("internal_inventory_matches missing")
    if not result.get("internal_market_snapshot"):
        errors.append("internal_market_snapshot missing")
    if expect.get("requires_public_sources") and not source_register:
        errors.append("source_register missing for public-source scenario")
    if expect.get("requires_public_sources") and not any(item.get("source_url") for item in top_candidates):
        errors.append("no top candidate has a public source_url")
    if expect.get("requires_roi") and not any(item.get("gross_yield_percent") is not None for item in top_candidates):
        errors.append("no top candidate has structured ROI or yield data")
    if expect.get("requires_images") and not any(item.get("hero_image_url") for item in top_candidates):
        errors.append("no top candidate has an image")
    if expect.get("bedroom_preference"):
        top_bedrooms = str(top_candidates[0].get("bedrooms") or "") if top_candidates else ""
        if top_bedrooms != str(expect.get("bedroom_preference")):
            errors.append(
                f"top-ranked candidate bedroom mismatch: expected {expect.get('bedroom_preference')} got {top_bedrooms or 'missing'}"
            )
    if expect.get("top_candidate_max_size_delta") and top_candidates:
        target_size = _float(request_profile.get("target_size_sqft"))
        top_size = _float(top_candidates[0].get("size_sqft"))
        if target_size <= 0 or top_size <= 0:
            errors.append("top-ranked candidate missing size data for target-size scenario")
        elif abs(top_size - target_size) > _float(expect.get("top_candidate_max_size_delta")):
            errors.append(
                f"top-ranked candidate size delta too large: |{int(top_size)} - {int(target_size)}| > {int(expect.get('top_candidate_max_size_delta'))}"
            )
    if expect.get("top_candidate_title_includes") and top_candidates:
        if str(expect.get("top_candidate_title_includes")).lower() not in str(top_candidates[0].get("title") or "").lower():
            errors.append(
                f"top-ranked candidate title does not include expected marker: {expect.get('top_candidate_title_includes')}"
            )
    if expect.get("top_candidate_min_bathrooms") and top_candidates:
        top_bathrooms = _float(top_candidates[0].get("bathrooms"))
        if top_bathrooms < _float(expect.get("top_candidate_min_bathrooms")):
            errors.append(
                f"top-ranked candidate bathrooms below expected minimum: {int(top_bathrooms)} < {int(_float(expect.get('top_candidate_min_bathrooms')))}"
            )
    if expect.get("max_price_aed"):
        priced_top = [item for item in top_candidates if item.get("price_aed")]
        within_budget = [item for item in priced_top if item.get("price_aed", 0) <= expect.get("max_price_aed")]
        if within_budget and top_candidates and _candidate_has_required_fields(top_candidates[0]):
            top_price = top_candidates[0].get("price_aed") or 0
            if top_price > expect.get("max_price_aed"):
                errors.append(
                    f"top-ranked candidate should stay within budget when qualifying options exist: {top_price} > {int(expect.get('max_price_aed'))}"
                )
        elif priced_top and top_candidates:
            top_risks = top_candidates[0].get("recommendation_risks") or top_candidates[0].get("cons") or []
            if not any("budget" in str(item).lower() or "exceeds the aed" in str(item).lower() for item in top_risks):
                errors.append("budget overrun is not surfaced in the top-ranked candidate risks")
    for index, candidate in enumerate(top_candidates[:3], start=1):
        if not _candidate_has_required_fields(candidate):
            errors.append(f"candidate {index} missing required fields")
    for key in ["json", "html", "pdf", "screenshot"]:
        artifact = artifacts.get(key)
        if not artifact:
            errors.append(f"artifact path missing for {key}")
            continue
        if not Path(artifact).exists():
            errors.append(f"artifact missing on disk for {key}: {artifact}")
    if export.get("pdf_exported") is not True:
        errors.append("pdf_exported not true")
    if export.get("screenshot_exported") is not True:
        errors.append("screenshot_exported not true")

    return {
        "name": name,
        "passed": not errors,
        "errors": errors,
        "request_profile": request_profile,
        "top_candidate_titles": [item.get("title") for item in top_candidates[:3]],
        "artifact_paths": artifacts,
        "source_count": len(source_register),
        "internal_match_count": len(result.get("internal_inventory_matches") or []),
        "internal_snapshot": result.get("internal_market_snapshot") or {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate current Realty Brain runtime outputs.")
    parser.add_argument(
        "--artifact-reuse",
        action="store_true",
        help="Validate current saved artifacts instead of regenerating every scenario.",
    )
    args = parser.parse_args()

    rows = []
    for scenario in SCENARIOS:
        if args.artifact_reuse:
            result = _load_saved_result(str(scenario["kwargs"]["case_name"]))
        else:
            result = run_agent(**scenario["kwargs"])
        rows.append(validate_result(scenario["name"], result, scenario["expect"]))

    report = {
        "generated_at": _now(),
        "validation_mode": "artifact_reuse" if args.artifact_reuse else "live_regeneration",
        "scenario_count": len(rows),
        "passed_count": sum(1 for row in rows if row["passed"]),
        "failed_count": sum(1 for row in rows if not row["passed"]),
        "all_passed": all(row["passed"] for row in rows),
        "scenarios": rows,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
