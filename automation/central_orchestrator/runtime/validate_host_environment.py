#!/usr/bin/env python3
"""Validate AIOS production host environment readiness.

This checks environment variables expected in the hosting provider. It masks and
fingerprints values for review, but never writes secrets or generates external
side effects.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "HOST_ENVIRONMENT_VALIDATION.json"

REQUIRED = {
    "AIOS_ENV": {"expected": "production", "secret": False},
    "AIOS_AUTH_MODE": {"expected": "basic", "secret": False},
    "AIOS_BASIC_AUTH_USER": {"expected": "", "secret": True},
    "AIOS_BASIC_AUTH_PASSWORD": {"expected": "", "secret": True, "min_length": 16},
    "AIOS_WHATSAPP_REPLY_MODE": {"expected": "hold", "secret": False},
    "AIOS_WHATSAPP_VERIFY_TOKEN": {"expected": "", "secret": True, "min_length": 24},
}

OPTIONAL = {
    "AIOS_PUBLIC_BASE_URL": {"placeholder": "https://your-aios-domain.example"},
    "AIOS_CUSTOM_DOMAIN": {"placeholder": "your-aios-domain.example"},
    "AIOS_WHATSAPP_HOSTED_TEST": {"allowed": {"pass", "fail"}},
}

PLACEHOLDERS = {
    "",
    "change-in-host-secrets",
    "<set in host dashboard>",
    "your-aios-domain.example",
    "https://your-aios-domain.example",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-3:]}"


def _required_check(key: str, rule: dict[str, Any]) -> dict[str, Any]:
    value = os.getenv(key, "")
    expected = str(rule.get("expected") or "")
    min_length = int(rule.get("min_length") or 1)
    present = bool(value)
    placeholder = value.strip() in PLACEHOLDERS
    expected_ok = value == expected if expected else present and len(value) >= min_length
    passed = present and not placeholder and expected_ok
    return {
        "name": key,
        "passed": passed,
        "present": present,
        "placeholder": placeholder,
        "secret": bool(rule.get("secret")),
        "expected": expected if not rule.get("secret") else "non-placeholder secret",
        "masked": _mask(value),
        "fingerprint": _hash(value),
        "min_length": min_length if rule.get("secret") else None,
    }


def _optional_check(key: str, rule: dict[str, Any]) -> dict[str, Any]:
    value = os.getenv(key, "")
    placeholder = value.strip() in PLACEHOLDERS or value == rule.get("placeholder")
    allowed = rule.get("allowed")
    passed = True
    if value and placeholder:
        passed = False
    if value and allowed and value not in allowed:
        passed = False
    return {
        "name": key,
        "passed": passed,
        "present": bool(value),
        "placeholder": placeholder,
        "masked": _mask(value),
        "fingerprint": _hash(value),
    }


def validate() -> dict[str, Any]:
    required_checks = [_required_check(key, rule) for key, rule in REQUIRED.items()]
    optional_checks = [_optional_check(key, rule) for key, rule in OPTIONAL.items()]
    required_ready = all(item["passed"] for item in required_checks)
    optional_ready = all(item["passed"] for item in optional_checks)
    blockers = [
        f"{item['name']} missing_or_placeholder"
        for item in required_checks
        if not item["passed"]
    ]
    blockers.extend(
        f"{item['name']} invalid_placeholder_or_value"
        for item in optional_checks
        if item["present"] and not item["passed"]
    )
    report = {
        "validated_at": _now(),
        "product": "AIOS",
        "feature": "Host Environment Validation",
        "passed": required_ready and optional_ready,
        "production_env_ready": required_ready and optional_ready,
        "required_checks_passed": sum(1 for item in required_checks if item["passed"]),
        "required_checks_total": len(required_checks),
        "optional_checks_passed": sum(1 for item in optional_checks if item["passed"]),
        "optional_checks_total": len(optional_checks),
        "required": required_checks,
        "optional": optional_checks,
        "blockers": blockers,
        "external_side_effects": {
            "secrets_written": False,
            "published": False,
            "deployed": False,
            "external_provider_called": False,
        },
        "next_action": "Enter production values in the host secret manager, then rerun this validator."
        if blockers
        else "Host environment is ready for public beta validation.",
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = validate()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
