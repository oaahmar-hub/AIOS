#!/usr/bin/env python3
"""AIOS production deployment preflight.

Runs local checks that should pass before connecting permanent hosting, domain,
auth secrets, and WhatsApp provider webhooks. This script does not publish,
deploy, call external providers, or write secrets to disk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import string
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "DEPLOYMENT_PREFLIGHT.json"
PACKAGE_REPORT_PATH = REPORTS_DIR / "DEPLOYMENT_PACKAGE_VALIDATION.json"

REQUIRED_ENV = [
    "AIOS_ENV",
    "AIOS_AUTH_MODE",
    "AIOS_BASIC_AUTH_USER",
    "AIOS_BASIC_AUTH_PASSWORD",
    "AIOS_WHATSAPP_REPLY_MODE",
    "AIOS_WHATSAPP_VERIFY_TOKEN",
]

RUNTIME_FILES = [
    "automation/central_orchestrator/runtime/aios_live_api_server.py",
    "automation/central_orchestrator/runtime/aios_runtime.py",
    "automation/central_orchestrator/runtime/validate_hosted_runtime.py",
    "automation/central_orchestrator/runtime/validate_public_beta.py",
    "automation/central_orchestrator/runtime/validate_eye_motion.py",
    "automation/central_orchestrator/runtime/validate_container_runtime.py",
    "automation/central_orchestrator/runtime/validate_host_environment.py",
    "automation/central_orchestrator/runtime/validate_deployment_package.py",
    "automation/central_orchestrator/runtime/validate_production_launch_readiness.py",
    "automation/central_orchestrator/runtime/deployment_preflight.py",
    "automation/central_orchestrator/runtime/build_deployment_bundle.py",
    "automation/central_orchestrator/runtime/prepare_production_release.py",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-3:]}"


def _secret(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(AIOS_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout_tail": completed.stdout[-1200:],
        "stderr_tail": completed.stderr[-1200:],
    }


def _compile_check() -> dict[str, Any]:
    return _run([sys.executable, "-m", "py_compile", *RUNTIME_FILES])


def _package_check() -> dict[str, Any]:
    result = _run([sys.executable, "automation/central_orchestrator/runtime/validate_deployment_package.py"])
    package_report: dict[str, Any] = {}
    if PACKAGE_REPORT_PATH.exists():
        try:
            package_report = json.loads(PACKAGE_REPORT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            package_report = {}
    result["package_passed"] = package_report.get("passed")
    result["checks_passed"] = package_report.get("checks_passed")
    result["checks_total"] = package_report.get("checks_total")
    return result


def _bundle_check() -> dict[str, Any]:
    result = _run([
        sys.executable,
        "automation/central_orchestrator/runtime/build_deployment_bundle.py",
        "--dry-run",
        "--summary",
    ])
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(result.get("stdout_tail") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    result["bundle_passed"] = parsed.get("passed")
    result["file_count"] = parsed.get("file_count")
    result["missing_required"] = parsed.get("missing_required")
    return result


def _env_check() -> dict[str, Any]:
    placeholders = {"", "change-in-host-secrets", "<set in host dashboard>", "your-aios-domain.example"}
    checks = []
    for key in REQUIRED_ENV:
        value = os.getenv(key, "")
        checks.append(
            {
                "name": key,
                "present": bool(value),
                "placeholder": value.strip() in placeholders,
                "masked": _mask(value),
                "fingerprint": _hash(value) if value else "",
            }
        )
    ready = all(item["present"] and not item["placeholder"] for item in checks)
    return {
        "passed": ready,
        "ready_for_host_secrets": ready,
        "checks": checks,
        "note": "Missing or placeholder values are expected before host secrets are set.",
    }


def _generated_secret_plan() -> dict[str, Any]:
    password = _secret(36)
    verify_token = _secret(40)
    return {
        "generated_at": _now(),
        "not_written_to_disk": True,
        "items": [
            {
                "key": "AIOS_BASIC_AUTH_PASSWORD",
                "length": len(password),
                "fingerprint": _hash(password),
                "masked": _mask(password),
            },
            {
                "key": "AIOS_WHATSAPP_VERIFY_TOKEN",
                "length": len(verify_token),
                "fingerprint": _hash(verify_token),
                "masked": _mask(verify_token),
            },
        ],
        "use": "Generate final values in host secret manager or rerun with a secure operator present. Do not commit secrets.",
    }


def validate() -> dict[str, Any]:
    compile_check = _compile_check()
    package_check = _package_check()
    bundle_check = _bundle_check()
    env_check = _env_check()
    secret_plan = _generated_secret_plan()
    passed = compile_check["passed"] and package_check["passed"] and bundle_check["passed"]
    report = {
        "validated_at": _now(),
        "passed": passed,
        "production_env_ready": env_check["passed"],
        "checks": {
            "compile": compile_check,
            "package": package_check,
            "bundle": bundle_check,
            "environment": env_check,
            "generated_secret_plan": secret_plan,
        },
        "deployment_status": "ready_for_host_secret_entry" if passed else "fix_preflight_failures",
        "external_blockers_remaining": [
            "Permanent backend/frontend host approval.",
            "Domain attachment.",
            "Production secret entry in host dashboard.",
            "WhatsApp provider login and live hosted test.",
        ],
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AIOS production deployment preflight.")
    parser.parse_args()
    report = validate()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
