#!/usr/bin/env python3
"""AIOS WhatsApp Response Policy Layer.

Identity and permission checks for production WhatsApp replies.

This module is deliberately local and deterministic. It does not retrieve data,
call models, or send messages. Its job is to decide what AIOS is allowed to
retrieve or reveal before any knowledge/source lookup or response leaves the
system.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

CENTRAL_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "central_orchestrator" / "runtime"
if str(CENTRAL_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(CENTRAL_RUNTIME_DIR))

from aios_interaction_architecture_runtime import evaluate_permission_request


OMAR_DEFAULT_PHONES = {
    "971555593714",
    "0555593714",
}

TRUSTED_FULL_ACCESS_DEFAULT_PHONES = {
    # Hasan HSH Brother, CEO from Sueton. Omar approved Omar-level access.
    "971542227333",
}

TEMP_TRUSTED_FULL_ACCESS_DEFAULT_PHONES = {
    # Zaki Saleh Jawich. Omar approved temporary full access through 2026-06-24 23:59:59 Asia/Dubai.
    "971545112616": 1782331199,
}

PUBLIC_ALLOWED = {
    "property_information",
    "area_information",
    "community_information",
    "public_inventory",
    "project_details",
    "developer_information",
    "availability",
    "payment_plans",
    "market_information",
    "property_comparisons",
    "dld_procedures",
    "rera_procedures",
    "noc_procedures",
    "transfer_procedures",
    "mortgage_procedures",
    "residency_visa_information",
    "company_setup_information",
    "brochures",
    "public_project_documents",
}

AGENT_ALLOWED = PUBLIC_ALLOWED | {
    "inventory_information",
    "project_information",
}

OMAR_ALLOWED = {
    "property_information",
    "area_information",
    "public_inventory",
    "project_details",
    "brochures",
    "inventory_information",
    "project_information",
    "owner_details",
    "owner_contacts",
    "internal_notes",
    "internal_crm",
    "confidential_inventory",
    "private_documents",
    "private_ownership_records",
    "staff_personal_information",
    "internal_deal_notes",
    "internal_commissions",
    "internal_conversations",
}

PUBLIC_PATTERNS = {
    "property_information": [r"\b(property|unit|villa|apartment|plot|studio|bedroom|br|2br|3br)\b"],
    "area_information": [r"\b(area|location|jvc|yas|saadiyat|reem|marina|downtown|business bay)\b"],
    "community_information": [r"\b(community|amenities|facilities|nearby|schools|parks)\b"],
    "public_inventory": [r"\b(available|availability|inventory|stock|options|shortlist)\b"],
    "project_details": [r"\b(project|handover|amenities)\b"],
    "developer_information": [r"\b(developer|aldar|emaar|nakheel|damac|sobha|reportage)\b"],
    "availability": [r"\b(available|availability|vacant|ready|handover)\b"],
    "payment_plans": [r"\b(payment plan|installment|post handover|down payment)\b"],
    "market_information": [r"\b(market|roi|yield|price trend|capital appreciation|rental return)\b"],
    "property_comparisons": [r"\b(compare|comparison|better option|best option|versus|vs)\b"],
    "dld_procedures": [r"\b(dld|dubai land department)\b"],
    "rera_procedures": [r"\b(rera|rera form|rera permit)\b"],
    "noc_procedures": [r"\b(noc|no objection certificate)\b"],
    "transfer_procedures": [r"\b(transfer|ownership transfer|property transfer)\b"],
    "mortgage_procedures": [r"\b(mortgage|bank valuation|loan|pre approval)\b"],
    "residency_visa_information": [r"\b(residency|visa|golden visa|investor visa|gdrfa|icp)\b"],
    "company_setup_information": [r"\b(company setup|company formation|free zone|mainland|offshore|trade license)\b"],
    "brochures": [r"\b(brochure|floor plan|factsheet|presentation)\b"],
    "public_project_documents": [r"\b(public document|public documents|project document|project documents)\b"],
}

AGENT_PATTERNS = {
    "agent_identity": [
        r"\bagent\b",
        r"\bbroker\b",
        r"\bco[-\s]?broker\b",
        r"\bexternal\s+agent\b",
    ]
}

STAFF_PATTERNS = {
    "staff_identity": [
        r"\bhsh\b",
        r"\bstaff\b",
        r"\bteam\b",
        r"\bassistant\b",
        r"\boperation\b",
    ]
}


@dataclass
class PolicyDecision:
    sender_type: str
    access_level: str
    allowed_scopes: list[str]
    requested_scopes: list[str]
    forbidden_scopes: list[str]
    decision: str
    reason: str
    safe_reply: str
    retrieval_filter: dict[str, Any]
    response_rules: list[str]


def _digits(value: object) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _env_list(name: str) -> set[str]:
    raw = os.getenv(name, "")
    values: set[str] = set()
    for item in raw.replace(";", ",").split(","):
        digits = _digits(item)
        if digits:
            values.add(digits)
        elif item.strip():
            values.add(item.strip().lower())
    return values


def _env_json_dict(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _temp_trusted_full_access_phones() -> set[str]:
    now = int(__import__("time").time())
    active = {
        _digits(phone)
        for phone, expires_at in TEMP_TRUSTED_FULL_ACCESS_DEFAULT_PHONES.items()
        if _digits(phone) and int(expires_at or 0) >= now
    }
    configured = _env_json_dict("AIOS_TEMP_TRUSTED_FULL_ACCESS_PHONES")
    for phone, expires_at in configured.items():
        try:
            if int(expires_at) >= now:
                active.add(_digits(phone))
        except Exception:
            continue
    return active


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def _requested_scopes(text: str) -> list[str]:
    lowered = text or ""
    scopes: list[str] = []
    for scope, patterns in PUBLIC_PATTERNS.items():
        if _matches_any(lowered, patterns):
            scopes.append(scope)
    return sorted(set(scopes))


def _detect_sender_type(event: dict[str, Any], context: dict[str, Any] | None = None) -> tuple[str, str]:
    context = context or {}
    phone = _digits(event.get("from_phone"))
    name = str(event.get("profile_name") or context.get("known_contact_name") or "").lower()
    text_blob = json.dumps(context, ensure_ascii=False).lower()

    omar_phones = set(OMAR_DEFAULT_PHONES) | _env_list("AIOS_OMAR_PHONES")
    trusted_full_access_phones = (
        set(TRUSTED_FULL_ACCESS_DEFAULT_PHONES)
        | _env_list("AIOS_TRUSTED_FULL_ACCESS_PHONES")
        | _temp_trusted_full_access_phones()
    )
    staff_phones = _env_list("AIOS_HSH_STAFF_PHONES")
    agent_phones = _env_list("AIOS_AGENT_PHONES")
    role_map = _env_json_dict("AIOS_CONTACT_ROLE_MAP")

    if phone in omar_phones:
        return "Omar", "full"
    if phone in trusted_full_access_phones:
        return "Trusted Partner", "full"
    if phone in role_map:
        role = str(role_map.get(phone) or "").strip().lower()
        if role == "omar":
            return "Omar", "full"
        if role in {"trusted", "trusted partner", "full", "full_access", "partner_full"}:
            return "Trusted Partner", "full"
        if role in {"staff", "hsh staff", "internal"}:
            return "HSH Staff", "role_based"
        if role == "agent":
            return "Agent", "partner"
    if phone in staff_phones or _matches_any(name, STAFF_PATTERNS["staff_identity"]):
        return "HSH Staff", "role_based"
    if phone in agent_phones or _matches_any(name, AGENT_PATTERNS["agent_identity"]) or "agent" in text_blob or "broker" in text_blob:
        return "Agent", "partner"
    return "Customer", "public"


def _allowed_for(sender_type: str) -> set[str]:
    if sender_type in {"Omar", "Trusted Partner"}:
        return set(OMAR_ALLOWED)
    if sender_type == "Agent":
        return set(AGENT_ALLOWED)
    if sender_type == "HSH Staff":
        configured = _env_json_dict("AIOS_STAFF_ROLE_SCOPES")
        scopes = configured.get("default") if isinstance(configured, dict) else None
        if isinstance(scopes, list):
            return set(str(scope) for scope in scopes)
        return set(AGENT_ALLOWED)
    return set(PUBLIC_ALLOWED)


def _safe_refusal(sender_type: str, forbidden: list[str]) -> str:
    if sender_type == "Agent":
        return "I can share public property and inventory details, but private owner, internal, and commission details stay confidential."
    if sender_type == "HSH Staff":
        return "This needs Omar approval before sharing because it may include restricted internal or private information."
    return "I can help with public property, area, project, and process details, but private owner or internal information stays confidential."


def _has_full_access(sender_type: str) -> bool:
    return sender_type in {"Omar", "Trusted Partner"}


def evaluate_response_policy(
    *,
    event: dict[str, Any],
    message_text: str,
    context: dict[str, Any] | None = None,
) -> PolicyDecision:
    sender_type, access_level = _detect_sender_type(event, context)
    identity_type = "Agent / Broker" if sender_type == "Agent" else sender_type if sender_type in {"Omar", "Trusted Partner", "HSH Staff"} else "New Client"
    permission_decision = evaluate_permission_request(message_text, channel="whatsapp", identity_type=identity_type)
    allowed = _allowed_for(sender_type)
    requested = sorted(set(_requested_scopes(message_text) + permission_decision["hits"]))
    forbidden = permission_decision["hits"]

    if _has_full_access(sender_type):
        decision = "allow"
        reason = f"{sender_type} full-access sender approved by Omar."
        safe_reply = ""
    elif forbidden:
        if sender_type == "HSH Staff":
            decision = "hold_for_omar"
            reason = permission_decision["reason"]
        else:
            decision = "refuse_safe"
            reason = permission_decision["reason"]
        safe_reply = _safe_refusal(sender_type, forbidden)
    else:
        decision = "allow"
        reason = f"{sender_type} request is within the centralized AIOS permission runtime."
        safe_reply = ""

    return PolicyDecision(
        sender_type=sender_type,
        access_level=access_level,
        allowed_scopes=sorted(allowed),
        requested_scopes=requested,
        forbidden_scopes=forbidden,
        decision=decision,
        reason=reason,
        safe_reply=safe_reply,
        retrieval_filter={
            "public_only": sender_type in {"Customer", "Agent"},
            "exclude_owner_details": not _has_full_access(sender_type),
            "exclude_owner_contacts": not _has_full_access(sender_type),
            "exclude_internal_notes": not _has_full_access(sender_type),
            "exclude_internal_crm": not _has_full_access(sender_type),
            "exclude_confidential_inventory": not _has_full_access(sender_type),
            "exclude_private_documents": not _has_full_access(sender_type),
            "exclude_private_ownership_records": not _has_full_access(sender_type),
            "exclude_staff_personal_information": not _has_full_access(sender_type),
            "exclude_internal_commissions": not _has_full_access(sender_type),
            "exclude_internal_conversations": not _has_full_access(sender_type),
        },
        response_rules=[
            "Identify sender type before retrieval or reply.",
            "Use AIOS central permission runtime before retrieval or reply.",
            "Never expose data outside allowed_scopes.",
            "Apply retrieval_filter before querying knowledge sources.",
            "If forbidden_scopes is non-empty, do not retrieve or summarize those sources.",
            "When refusing, stay short, human, premium, and business-correct.",
        ],
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate AIOS WhatsApp response policy")
    parser.add_argument("message")
    parser.add_argument("--phone", default="+971500000001")
    parser.add_argument("--name", default="WhatsApp Contact")
    args = parser.parse_args()
    decision = evaluate_response_policy(
        event={"from_phone": args.phone, "profile_name": args.name},
        message_text=args.message,
        context={},
    )
    print(json.dumps(asdict(decision), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
