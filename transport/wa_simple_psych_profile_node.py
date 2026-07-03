#!/usr/bin/env python3
"""Lightweight psych/profile analyzer for the WhatsApp gateway.

Returns ONLY strict JSON with:
  {"urgency": "High|Medium|Low", "ego_style": "Direct-Blunt|Relationship-Oriented|Analytical", "reasoning": "Brief justification"}
"""

from __future__ import annotations

import json
import re

from typing import Any, Dict


_ALLOWED_URGENCY = {"High", "Medium", "Low"}
_ALLOWED_EGO = {"Direct-Blunt", "Relationship-Oriented", "Analytical"}


def _safe_lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _validate(profile: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        return _fallback("Malformed payload")

    urgency = str(profile.get("urgency", "Medium")).strip().title()
    if urgency not in _ALLOWED_URGENCY:
        urgency = "Medium"

    ego_style = str(profile.get("ego_style", "Relationship-Oriented")).strip()
    if ego_style not in _ALLOWED_EGO:
        ego_style = "Relationship-Oriented"

    reasoning = str(profile.get("reasoning", "") or "").strip()[:320]
    if not reasoning:
        reasoning = "Derived from keyword and context heuristics."

    return {
        "urgency": urgency,
        "ego_style": ego_style,
        "reasoning": reasoning,
    }


def _fallback(reason: str) -> Dict[str, Any]:
    return {
        "urgency": "Medium",
        "ego_style": "Relationship-Oriented",
        "reasoning": f"Fallback analysis: {reason}",
    }


def _heuristic_profile(message_text: str, sender: str = "") -> Dict[str, Any]:
    text = _safe_lower(message_text)
    sender = _safe_lower(sender)

    urgency = "Medium"
    if any(t in text for t in ("urgent", "asap", "immediately", "now", "critical", "now now", "very urgent", "عاجل", "ضروري", "اسرع")):
        urgency = "High"
    elif any(t in text for t in ("thanks", "thank", "مرحبا", "hello", "hi", "ya", "هلا", "صباح")):
        urgency = "Low"

    ego_style = "Relationship-Oriented"
    if any(t in text for t in ("roi", "numbers", "analysis", "compare", "calculate", "breakdown", "exact", "analytics")):
        ego_style = "Analytical"
    elif any(t in text for t in ("bro", "brother", "friend", "يا", "habibi", "😂", "😄", "يا زعيم", "يا كبير")):
        ego_style = "Relationship-Oriented"
    elif any(t in text for t in ("need", "show", "must", "now", "i want", "send me", "i need")):
        ego_style = "Direct-Blunt"

    if sender and "omar" in sender:
        ego_style = "Analytical"

    return {
        "urgency": urgency,
        "ego_style": ego_style,
        "reasoning": "Heuristic fallback based on urgency and action intent words.",
    }


def analyze_psych_profile_local(message_text: str, sender: str = "", history: str = "") -> Dict[str, Any]:
    try:
        profile = _heuristic_profile(message_text, sender)
        return _validate(profile)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return _fallback(str(exc))


def validate_psych_payload(payload: Dict[str, Any] | str | None) -> Dict[str, Any] | None:
    if payload is None:
        return None
    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return None
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    validated = _validate(payload)
    if validated == _fallback("Malformed payload"):
        return None
    return validated


def analyze_psych_profile_from_payload(payload: Dict[str, Any] | str | None) -> Dict[str, Any]:
    if isinstance(payload, str):
        parsed = validate_psych_payload(payload)
        if parsed:
            return parsed
        return _fallback("Could not parse payload")
    if isinstance(payload, dict):
        parsed = validate_psych_payload(payload)
        if parsed:
            return parsed
    return _fallback("Invalid payload")


def as_json(payload: Dict[str, Any] | None) -> str:
    return json.dumps(payload or _fallback("No payload"), ensure_ascii=False)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="", help="Message text")
    parser.add_argument("--sender", default="", help="Sender")
    args = parser.parse_args()
    result = analyze_psych_profile_local(args.text, sender=args.sender)
    print(as_json(result))
