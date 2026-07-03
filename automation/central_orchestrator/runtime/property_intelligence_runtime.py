#!/usr/bin/env python3
"""Build a local property-intelligence report for AIOS.

The runtime uses local AIOS knowledge and sample inventory only. It does not
call portals, send messages, write CRM rows, or claim live availability.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
OUTPUT_PATH = REPORTS_DIR / "PROPERTY_INTELLIGENCE_REPORT.json"
COMMUNITIES_PATH = AIOS_ROOT / "knowledge-base" / "market" / "DUBAI-COMMUNITIES.md"
BRAND_ASSET_MANIFEST_PATH = AIOS_ROOT / "knowledge-base" / "branding" / "BRAND-ASSET-MANIFEST.json"


DEFAULT_LEAD = {
    "intent": "buy",
    "area": "JVC",
    "budget": 1_000_000,
    "beds": 2,
    "purpose": "investment",
}

DEFAULT_INVENTORY = [
    {
        "reference": "JVC-204",
        "title": "Ready 2BR Apartment",
        "area": "JVC District 12",
        "price": 980_000,
        "beds": 2,
        "status": "Available",
        "size_sqft": 1080,
        "source": "local_sample_inventory",
    },
    {
        "reference": "MAR-881",
        "title": "Marina 2BR High Floor",
        "area": "Dubai Marina",
        "price": 1_450_000,
        "beds": 2,
        "status": "Available",
        "size_sqft": 1180,
        "source": "local_sample_inventory",
    },
    {
        "reference": "JVC-119",
        "title": "1BR Investor Deal",
        "area": "JVC",
        "price": 760_000,
        "beds": 1,
        "status": "Ready",
        "size_sqft": 740,
        "source": "local_sample_inventory",
    },
    {
        "reference": "DHE-330",
        "title": "Dubai Hills Park View 2BR",
        "area": "Dubai Hills Estate",
        "price": 1_820_000,
        "beds": 2,
        "status": "Available",
        "size_sqft": 1125,
        "source": "local_sample_inventory",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _money(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _area_key(value: Any) -> str:
    value = _normalize(value)
    aliases = {
        "jumeirah village circle": "jvc",
        "jvc": "jvc",
        "dubai marina": "dubai marina",
        "marina": "dubai marina",
        "dubai hills": "dubai hills",
        "dubai hills estate": "dubai hills",
        "palm": "palm jumeirah",
        "palm jumeirah": "palm jumeirah",
    }
    for needle, alias in aliases.items():
        if needle in value:
            return alias
    return value


def parse_community_context() -> dict[str, dict[str, Any]]:
    text = _safe_read(COMMUNITIES_PATH)
    contexts: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r"^## ([A-Z0-9 &()|,.\-]+)\n(?P<body>.*?)(?=^## |\Z)", text, flags=re.M | re.S):
        name = match.group(1).strip().title()
        body = match.group("body")
        key = _area_key(name)
        developer = re.search(r"\*\*Developer:\*\*\s*(.+)", body)
        community_type = re.search(r"\*\*Community type:\*\*\s*(.+)", body)
        property_types = re.search(r"\*\*Property types:\*\*\s*(.+)", body)
        noc = re.search(r"\*\*NOC:\*\*\s*(.+)", body)
        price_range = re.search(r"Price range(?: \(2024.+?\))?:\s*(.+)", body)
        avg_psf = re.search(r"Avg\. price/sq ft:\s*(.+)", body)
        rental_yield = re.search(r"Rental yield:\s*(.+)", body)
        contexts[key] = {
            "name": name,
            "developer": developer.group(1).strip() if developer else "",
            "community_type": community_type.group(1).strip() if community_type else "",
            "property_types": property_types.group(1).strip() if property_types else "",
            "noc": noc.group(1).strip() if noc else "",
            "price_range": price_range.group(1).strip() if price_range else "",
            "avg_price_per_sqft": avg_psf.group(1).strip() if avg_psf else "",
            "rental_yield": rental_yield.group(1).strip() if rental_yield else "",
            "source_path": COMMUNITIES_PATH.relative_to(AIOS_ROOT).as_posix(),
        }
    return contexts


def build_local_inventory(extra_inventory: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    inventory = [dict(item) for item in DEFAULT_INVENTORY]
    if extra_inventory:
        inventory.extend(dict(item) for item in extra_inventory)
    campaign_dir = AIOS_ROOT / "knowledge-base" / "branding" / "assets" / "property-campaigns"
    campaign_paths = [path for path in sorted(campaign_dir.glob("*")) if path.is_file()] if campaign_dir.exists() else []
    if not campaign_paths:
        try:
            manifest = json.loads(BRAND_ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
            campaign_paths = [Path(name) for name in manifest.get("categories", {}).get("property-campaigns", [])]
        except Exception:
            campaign_paths = []
    for path in campaign_paths[:12]:
        source_path = path.relative_to(AIOS_ROOT).as_posix() if path.is_absolute() and path.exists() else f"knowledge-base/branding/assets/property-campaigns/{path.name}"
        stem = path.stem
        if path.is_file():
            stem = path.stem
        inventory.append(
            {
                "reference": stem.upper()[:28],
                "title": stem.replace("-", " ").title(),
                "area": "Campaign Asset",
                "price": 0,
                "beds": "",
                "status": "Marketing Asset",
                "size_sqft": 0,
                "source": source_path,
                "asset_only": True,
            }
        )
    return inventory


def score_property(lead: dict[str, Any], prop: dict[str, Any], contexts: dict[str, dict[str, Any]]) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    lead_area = _area_key(lead.get("area"))
    prop_area = _area_key(prop.get("area"))
    budget = _money(lead.get("budget"))
    price = _money(prop.get("price"))
    beds = str(lead.get("beds") or "")
    prop_beds = str(prop.get("beds") or "")
    status = _normalize(prop.get("status"))
    if prop.get("asset_only"):
        return 8, ["marketing collateral available"], ["asset only, not inventory availability"]
    if lead_area and (lead_area in prop_area or prop_area in lead_area):
        score += 34
        reasons.append("area match")
    elif lead_area and prop_area in contexts:
        score += 8
        reasons.append("alternative market context available")
    if budget and price:
        if price <= budget:
            score += 28
            reasons.append("within budget")
        elif price <= budget * 1.10:
            score += 16
            reasons.append("near budget")
        else:
            risks.append("above stated budget")
    if beds and prop_beds and beds == prop_beds:
        score += 18
        reasons.append("bedroom match")
    elif beds and prop_beds:
        risks.append("bedroom mismatch")
    if status in {"available", "ready", "vacant"}:
        score += 14
        reasons.append("ready or available status")
    if _normalize(lead.get("purpose")) in {"investment", "investor"}:
        context = contexts.get(prop_area, {})
        if context.get("rental_yield"):
            score += 6
            reasons.append(f"yield benchmark available: {context['rental_yield']}")
    return min(score, 100), reasons or ["partial match"], risks


def compare_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparisons = []
    for item in matches[:4]:
        price = _money(item.get("price"))
        size = _money(item.get("size_sqft"))
        comparisons.append(
            {
                "property_ref": item.get("property_ref", ""),
                "price_per_sqft": round(price / size, 2) if price and size else None,
                "approval_position": "share_after_availability_check" if item.get("match_score", 0) >= 70 else "backup_only",
                "tradeoff": item.get("risk_notes", ["no major local risk flags"])[0],
            }
        )
    return comparisons


def build_draft_message(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return "I do not have a strong local match yet. I will keep checking inventory and update you."
    lines = ["I found a few options that may fit, pending availability confirmation:"]
    for match in matches[:3]:
        price = _money(match.get("price"))
        price_text = f"AED {price:,.0f}" if price else "price to confirm"
        lines.append(f"- {match.get('title')} in {match.get('area')} — {price_text} ({'; '.join(match.get('reasons', []))})")
    lines.append("Which option should I verify first?")
    return "\n".join(lines)


def build(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    lead = payload.get("lead") or DEFAULT_LEAD
    contexts = parse_community_context()
    inventory = build_local_inventory(payload.get("inventory") or payload.get("properties"))
    matches = []
    for prop in inventory:
        score, reasons, risks = score_property(lead, prop, contexts)
        matches.append(
            {
                "match_score": score,
                "property_ref": prop.get("reference", ""),
                "title": prop.get("title", ""),
                "area": prop.get("area", ""),
                "price": prop.get("price", 0),
                "beds": prop.get("beds", ""),
                "status": prop.get("status", ""),
                "size_sqft": prop.get("size_sqft", 0),
                "source": prop.get("source", ""),
                "reasons": reasons,
                "risk_notes": risks or ["availability and pricing must be confirmed before client commitment"],
                "next_action": "Verify availability, then share with client" if score >= 70 else "Keep as backup or research alternative",
            }
        )
    matches.sort(key=lambda item: item["match_score"], reverse=True)
    lead_area = _area_key(lead.get("area"))
    selected_contexts = {
        key: contexts[key]
        for key in sorted(contexts)
        if key == lead_area or key in {"jvc", "dubai marina", "dubai hills", "palm jumeirah"}
    }
    result = {
        "generated_at": _now(),
        "mode": "safe_local_property_intelligence_no_external_side_effects",
        "query": payload.get("query") or "recommend and compare local property options",
        "lead": lead,
        "inventory_count": len(inventory),
        "matched_count": len([item for item in matches if item["match_score"] >= 50]),
        "top_matches": matches[:6],
        "comparisons": compare_matches(matches),
        "community_context": selected_contexts,
        "market_structure": {
            "areas_loaded": len(contexts),
            "source_path": COMMUNITIES_PATH.relative_to(AIOS_ROOT).as_posix(),
            "current_pricing_requires_live_dld_check": True,
            "availability_requires_agent_confirmation": True,
        },
        "recommended_next_actions": [
            "Verify live availability and current price before sending client-facing options.",
            "For investment clients, compare rental yield and service-charge exposure before recommending.",
            "Use approved CRM writeback only after Omar confirms the selected recommendation.",
        ],
        "draft_client_message": build_draft_message(matches),
        "workflow_handoff": {
            "command": "@recommend",
            "source_agent": "automation/ai_agents_production/runtime/property_recommendation_agent.py",
            "approval_required_before_client_send": True,
        },
        "external_side_effects": {
            "portal_queries": False,
            "messages_sent": False,
            "crm_rows_written": False,
            "calendar_events_created": False,
            "drive_files_modified": False,
            "claims_live_availability": False,
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
