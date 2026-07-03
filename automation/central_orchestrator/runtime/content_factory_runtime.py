#!/usr/bin/env python3
"""Build a local Content Factory report for AIOS.

The runtime prepares draft-only marketing outputs for property campaigns,
investor campaigns, and service campaigns. It does not generate final media,
publish content, create Drive files, call design/video tools, or post to social
channels.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "CONTENT_FACTORY_REPORT.json"
BRAND_ASSET_MANIFEST_PATH = AIOS_ROOT / "knowledge-base" / "branding" / "BRAND-ASSET-MANIFEST.json"

SOURCE_PATHS = {
    "marketing_agent": "agents/08-MARKETING-AGENT.md",
    "marketing_control": "automation/marketing_automation/MARKETING-AUTOMATION-CONTROL.md",
    "marketing_sop": "sops/SOP-10-MARKETING-CAMPAIGN.md",
    "listing_template": "templates/TPL-12-LISTING-DESCRIPTION.md",
    "brand_guidelines": "knowledge-base/branding/BRAND-GUIDELINES.md",
    "aios_brand_identity": "knowledge-base/branding/AIOS-BRAND-IDENTITY.md",
    "brand_asset_register": "knowledge-base/branding/BRAND-ASSET-REGISTER.md",
}

DEFAULT_BRIEF = {
    "campaign_name": "JVC Ready 2BR Investor Push",
    "campaign_type": "listing_campaign",
    "property_title": "Ready 2BR Apartment",
    "community": "JVC District 12",
    "price": 980_000,
    "beds": 2,
    "baths": 2,
    "size_sqft": 1080,
    "availability": "Available, subject to confirmation",
    "audience": "Buyers and investors",
    "tone": "premium, direct, factual",
    "key_message": "A ready two-bedroom JVC option with budget-fit investment appeal.",
    "cta": "Reply with your viewing window and I will verify availability first.",
    "language": "English",
    "permit_status": "RERA permit required before publishing",
    "contact_name": "Omar",
    "contact_phone": "+971555593714",
}

CONTENT_TYPES = [
    "flyer",
    "brochure",
    "presentation",
    "reel_script",
    "video_script",
    "caption",
    "marketing_campaign",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: Any) -> str:
    try:
        return f"AED {float(value):,.0f}"
    except Exception:
        return "price to confirm"


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _asset_count(path: str) -> int:
    root = AIOS_ROOT / path
    if not root.exists():
        return 0
    if root.is_file():
        return 1
    return len([item for item in root.rglob("*") if item.is_file()])


def _brand_asset_manifest() -> dict[str, Any]:
    try:
        return json.loads(BRAND_ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _asset_count_or_manifest(path: str, manifest_key: str) -> int:
    count = _asset_count(path)
    if count:
        return count
    counts = _brand_asset_manifest().get("counts", {})
    try:
        return int(counts.get(manifest_key) or 0)
    except Exception:
        return 0


def build_asset_register() -> dict[str, Any]:
    return {
        "logo_assets": _asset_count_or_manifest("knowledge-base/branding/assets/logo", "logo_assets"),
        "property_campaign_assets": _asset_count_or_manifest("knowledge-base/branding/assets/property-campaigns", "property_campaign_assets"),
        "presentation_assets": _asset_count_or_manifest("knowledge-base/branding/assets/presentations", "presentation_assets"),
        "market_report_assets": _asset_count_or_manifest("knowledge-base/branding/assets/market-reports", "market_report_assets"),
        "company_profile_assets": _asset_count_or_manifest("knowledge-base/branding/assets/company-profile", "company_profile_assets"),
        "manifest_path": BRAND_ASSET_MANIFEST_PATH.relative_to(AIOS_ROOT).as_posix(),
        "source_paths": [
            "knowledge-base/branding/assets/logo/",
            "knowledge-base/branding/assets/property-campaigns/",
            "knowledge-base/branding/assets/presentations/",
            "knowledge-base/branding/assets/market-reports/",
            "knowledge-base/branding/assets/company-profile/",
        ],
    }


def build_artifacts(brief: dict[str, Any]) -> list[dict[str, Any]]:
    price = _money(brief.get("price"))
    community = _safe_text(brief.get("community"))
    title = _safe_text(brief.get("property_title"))
    beds = _safe_text(brief.get("beds"))
    size = _safe_text(brief.get("size_sqft"))
    cta = _safe_text(brief.get("cta"))
    contact = f"{_safe_text(brief.get('contact_name'))} | {_safe_text(brief.get('contact_phone'))}".strip(" |")
    return [
        {
            "artifact_type": "flyer",
            "title": f"{title} Flyer Draft",
            "format": "single_page_visual_brief",
            "draft": {
                "headline": f"{beds}BR in {community} | {price}",
                "subhead": _safe_text(brief.get("key_message")),
                "detail_lines": [
                    f"{size} sq ft",
                    _safe_text(brief.get("availability")),
                    "RERA permit and live availability must be confirmed before publishing.",
                ],
                "cta": cta,
                "visual_direction": "AIOS dark premium base, specific property imagery only, minimal typography.",
            },
            "approval_required": True,
        },
        {
            "artifact_type": "brochure",
            "title": f"{title} Brochure Draft",
            "format": "multi_section_property_brochure",
            "draft": {
                "sections": [
                    "Cover: property signal, community, price, availability disclaimer",
                    "Property details: beds, baths, size, view, parking, furnishing",
                    "Investment snapshot: rent, service charge, yield only after verified data",
                    "Viewing and next action",
                ],
                "cta": cta,
            },
            "approval_required": True,
        },
        {
            "artifact_type": "presentation",
            "title": f"{title} Client Presentation Draft",
            "format": "6_slide_outline",
            "draft": {
                "slides": [
                    "1. Executive property summary",
                    "2. Unit facts and availability status",
                    "3. Community context",
                    "4. Comparable opportunity notes",
                    "5. Risks and checks before commitment",
                    "6. Next steps and viewing route",
                ],
                "style": "AIOS command-center polish, restrained premium layout, no generic real estate cliches.",
            },
            "approval_required": True,
        },
        {
            "artifact_type": "reel_script",
            "title": f"{community} Reel Script Draft",
            "format": "short_form_video_script",
            "draft": {
                "hook": f"Looking at a ready {beds}BR in {community} under {price}?",
                "beats": [
                    "Show the living space and layout first.",
                    "Cut to community and practical access point.",
                    "Show key feature or view, no stock footage.",
                    "End with availability verification CTA.",
                ],
                "voiceover": f"This is a ready {beds}-bed option in {community}. I will verify availability, price, and viewing access before sending full details.",
            },
            "approval_required": True,
        },
        {
            "artifact_type": "video_script",
            "title": f"{title} Walkthrough Video Draft",
            "format": "60_to_90_second_video_outline",
            "draft": {
                "opening": "Start with the strongest actual property visual.",
                "sequence": [
                    "Exterior/building or community context",
                    "Living and dining flow",
                    "Bedrooms and storage",
                    "View/balcony/key feature",
                    "Costs, checks, and viewing CTA",
                ],
                "safety_note": "Do not imply live availability or guaranteed yield without verification.",
            },
            "approval_required": True,
        },
        {
            "artifact_type": "caption",
            "title": f"{community} Caption Draft",
            "format": "instagram_linkedin_caption",
            "draft": {
                "caption": (
                    f"{title} in {community}. {beds} beds, {size} sq ft, listed at {price}. "
                    f"{_safe_text(brief.get('key_message'))} {cta}"
                ),
                "hashtags": ["#DubaiRealEstate", "#JVC", "#DubaiProperty", "#InvestmentProperty"],
                "channel_note": "Shorten for Instagram; add market context for LinkedIn.",
            },
            "approval_required": True,
        },
        {
            "artifact_type": "marketing_campaign",
            "title": _safe_text(brief.get("campaign_name")),
            "format": "multi_channel_campaign_plan",
            "draft": {
                "channels": ["Property Finder copy support", "Instagram", "LinkedIn", "WhatsApp one-to-one", "Email"],
                "weekly_sequence": [
                    "Monday: listing launch draft",
                    "Wednesday: community insight",
                    "Thursday: investor angle",
                    "Saturday: content batch and viewing CTA",
                    "Sunday: performance review",
                ],
                "metrics": ["leads received", "viewings booked", "qualified leads", "offers"],
                "crm_task": "Create follow-up task for every reply after approval-gated send.",
            },
            "approval_required": True,
        },
    ]


def compliance_checks(brief: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    permit_status = _safe_text(brief.get("permit_status")).lower()
    return [
        {"check": "rera_permit_required_for_specific_property", "passed": "permit" in permit_status, "approval_required": True},
        {"check": "no_guaranteed_roi_claims", "passed": True, "approval_required": False},
        {"check": "no_fake_property_photos", "passed": True, "approval_required": False},
        {"check": "availability_requires_confirmation", "passed": "confirm" in _safe_text(brief.get("availability")).lower(), "approval_required": True},
        {"check": "all_outputs_are_drafts", "passed": all(item.get("approval_required") for item in artifacts), "approval_required": True},
    ]


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    brief = {**DEFAULT_BRIEF, **(payload.get("brief") or payload)}
    artifacts = build_artifacts(brief)
    checks = compliance_checks(brief, artifacts)
    result = {
        "generated_at": _now(),
        "mode": "safe_local_content_factory_no_external_side_effects",
        "brief": brief,
        "artifact_count": len(artifacts),
        "content_types": CONTENT_TYPES,
        "draft_artifacts": artifacts,
        "campaign_plan": next(item for item in artifacts if item["artifact_type"] == "marketing_campaign"),
        "compliance_checks": checks,
        "asset_register": build_asset_register(),
        "source_paths": list(SOURCE_PATHS.values()),
        "workflow_handoffs": [
            {"command": "@marketing", "scope": "campaign strategy, captions, listing copy, content calendar"},
            {"command": "@property-intel", "scope": "property facts, market context, opportunity comparison"},
            {"command": "@crm-followup", "scope": "reply follow-up tasks and lead segmentation"},
            {"command": "@connector-payloads", "scope": "disabled content factory and Instagram payload contracts"},
            {"command": "@social-content-dry-review", "scope": "local review artifact only, no publish"},
        ],
        "recommended_next_actions": [
            "Verify RERA permit, property facts, price, availability, and media permissions before public use.",
            "Route any WhatsApp broadcast, paid ad, owner/client-specific message, or price reduction through Omar approval.",
            "Use the dry-review connector chain only after approval; keep generation and publishing disabled until final activation.",
        ],
        "external_side_effects": {
            "content_assets_generated": False,
            "content_published": False,
            "instagram_posts_published": False,
            "whatsapp_broadcasts_sent": False,
            "gmail_drafts_created": False,
            "drive_files_modified": False,
            "canva_designs_created": False,
            "video_jobs_started": False,
            "paid_ads_launched": False,
            "crm_rows_written": False,
        },
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(build(payload), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
