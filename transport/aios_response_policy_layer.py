from __future__ import annotations

from dataclasses import dataclass, asdict
import os
import re


@dataclass
class ResponsePolicy:
    sender_type: str = "Unknown"
    relationship: str | None = None
    decision: str = "allow"
    allow: bool = True
    safety_notes: list[str] | None = None
    safe_reply: str | None = None
    retrieval_filter: dict | None = None


def _normalize_phone(value: object) -> str:
    return re.sub(r"\D+", "", str(value or "").split("@", 1)[0])


def _owner_phone_allowlist() -> set[str]:
    raw_values = [
        os.getenv("AIOS_OWNER_PHONE", ""),
        os.getenv("AIOS_OWNER_PHONES", ""),
    ]
    owners = set()
    for raw in raw_values:
        for item in str(raw or "").split(","):
            normalized = _normalize_phone(item)
            if normalized:
                owners.add(normalized)
    return owners


def evaluate_response_policy(event, message_text, context=None):
    """Fallback response policy evaluator used by the WhatsApp gateway.

    Returns a dataclass-compatible object because the gateway calls attribute
    access (sender_type/decision) and serializes it via asdict().
    """

    context = context or {}
    event = event or {}
    text = (message_text or "").lower()
    relationship = context.get("relationship") or context.get("relationship_tag")
    from_phone = _normalize_phone(event.get("from_phone", ""))
    is_owner = bool(from_phone and from_phone in _owner_phone_allowlist())

    if context.get("known_chat"):
        sender_type = "HSH Staff" if "staff" in str(relationship or "").lower() else "Known"
    elif is_owner:
        sender_type = "Omar"
    elif "friend" in str(relationship or "").lower():
        sender_type = "Friend"
    elif "staff" in str(relationship or "").lower():
        sender_type = "HSH Staff"
    elif "agent" in str(relationship or "").lower():
        sender_type = "Agent"
    else:
        sender_type = "Unknown"

    decision = "allow"
    safety_notes = []
    safe_reply = None
    retrieval_filter = {"exclude_owner_details": False}

    flagged_keywords = ["scam", "fraud", "hack", "threat", "extortion", "blackmail"]
    if any(token in text for token in flagged_keywords):
        decision = "refuse_safe"
        safe_reply = "I can only help with real estate and operations tasks. Send what you need and I’ll handle it."
        safety_notes.append("suspicious_text")

    if decision == "allow":
        allow = True
    else:
        allow = False
        retrieval_filter["exclude_owner_details"] = True

    return ResponsePolicy(
        sender_type=sender_type,
        relationship=relationship,
        decision=decision,
        allow=allow,
        safety_notes=safety_notes,
        safe_reply=safe_reply,
        retrieval_filter=retrieval_filter,
    )
