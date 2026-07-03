#!/usr/bin/env python3
"""Combined AIOS public beta readiness gate."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from validate_hosted_runtime import validate as validate_hosted_runtime
from validate_eye_motion import validate as validate_eye_motion
from validate_visual_presence import validate as validate_visual_presence


RUNTIME_DIR = Path(__file__).resolve().parent
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "PUBLIC_BETA_VALIDATION.json"
ORCHESTRATOR_REPORT_PATH = REPORTS_DIR / "CENTRAL_ORCHESTRATOR_VALIDATION.json"
HOSTED_RUNTIME_REPORT_PATH = REPORTS_DIR / "HOSTED_RUNTIME_VALIDATION.json"
EYE_MOTION_REPORT_PATH = REPORTS_DIR / "EYE_MOTION_VALIDATION.json"

TEMP_HOST_MARKERS = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "railway.app",
    ".lhr.life",
    "localhost.run",
    "ngrok",
    "trycloudflare",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _host(base_url: str) -> str:
    return urlparse(base_url).netloc.lower()


def _is_temporary_url(base_url: str) -> bool:
    host = _host(base_url)
    return not host or any(marker in host for marker in TEMP_HOST_MARKERS)


def _run_orchestrator_validation() -> dict[str, Any]:
    command = [sys.executable, str(RUNTIME_DIR / "run_central_orchestrator_validation.py")]
    completed = subprocess.run(
        command,
        cwd=str(RUNTIME_DIR.parents[2]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        if ORCHESTRATOR_REPORT_PATH.exists():
            parsed = json.loads(ORCHESTRATOR_REPORT_PATH.read_text(encoding="utf-8"))
    command_data = parsed.get("command_center_data", {})
    return {
        "passed": completed.returncode == 0 and parsed.get("passed") is True,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-1000:],
        "stderr_tail": completed.stderr[-1000:],
        "report": str(ORCHESTRATOR_REPORT_PATH.relative_to(RUNTIME_DIR.parents[1])),
        "scenario_count": parsed.get("scenario_count"),
        "passed_count": parsed.get("passed_count"),
        "failed_count": parsed.get("failed_count"),
        "website_ready": command_data.get("website_ready"),
        "mobile_app_ready": command_data.get("mobile_app_ready"),
        "permission_runtime_source": command_data.get("aios_permission_runtime_source"),
        "permission_same_result_everywhere": command_data.get("aios_permission_same_result_everywhere"),
    }


def _load_hosted_report(base_url: str) -> dict[str, Any]:
    if not HOSTED_RUNTIME_REPORT_PATH.exists():
        return {}
    try:
        report = json.loads(HOSTED_RUNTIME_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if str(report.get("base_url", "")).rstrip("/") != base_url.rstrip("/"):
        return {}
    return report


def _load_eye_motion_report(base_url: str) -> dict[str, Any]:
    if not EYE_MOTION_REPORT_PATH.exists():
        return {}
    try:
        report = json.loads(EYE_MOTION_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if str(report.get("base_url", "")).rstrip("/") != base_url.rstrip("/"):
        return {}
    return report


def _readiness_blockers(
    *,
    base_url: str,
    hosted: dict[str, Any],
    visual: dict[str, Any],
    motion: dict[str, Any],
    orchestrator: dict[str, Any],
    auth_required: bool,
    whatsapp_hosted_pass: bool,
) -> list[str]:
    blockers: list[str] = []
    if not hosted.get("passed"):
        blockers.append("Hosted runtime validation did not pass.")
    if visual.get("skipped"):
        blockers.append("Visual presence validation was skipped; screenshot proof is still required.")
    if not visual.get("passed"):
        blockers.append("Visual presence validation did not pass.")
    if motion.get("skipped"):
        blockers.append("10-second Eye motion validation was skipped; motion proof is still required.")
    if not motion.get("passed"):
        blockers.append("10-second Eye motion validation did not pass.")
    if orchestrator.get("skipped"):
        blockers.append("Internal AIOS orchestrator validation was skipped.")
    if not orchestrator.get("passed"):
        blockers.append("Internal AIOS orchestrator validation did not pass.")
    if _is_temporary_url(base_url):
        blockers.append("Public URL is temporary; attach permanent frontend/backend hosting and domain.")
    if auth_required and hosted.get("auth_mode") != "basic":
        blockers.append("Production authentication is not enabled or was not validated with Basic Auth credentials.")
    auth_checks = [check for check in hosted.get("checks", []) if str(check.get("name", "")).startswith("auth:")]
    if auth_required and (not auth_checks or any(check.get("passed") is not True for check in auth_checks)):
        blockers.append("Production authentication rejection checks did not pass.")
    whatsapp_checks = [
        check
        for check in hosted.get("checks", [])
        if check.get("name")
        in {"whatsapp_hosted_ingress_test", "whatsapp_webhook_verification", "whatsapp_provider_webhook_route"}
    ]
    if len(whatsapp_checks) < 3 or any(check.get("passed") is not True for check in whatsapp_checks):
        blockers.append("Hosted WhatsApp backend ingress, verification, and provider webhook checks did not pass.")
    if not whatsapp_hosted_pass:
        blockers.append("WhatsApp provider live connection is not approved, wired, and validated against the hosted runtime.")
    health = next((check for check in hosted.get("checks", []) if check.get("name") == "health"), {})
    if health.get("status") != 200 or health.get("runtime_status") != "ready":
        blockers.append("Public health endpoint is not ready.")
    return blockers


def validate(
    base_url: str,
    *,
    visual_base_url: str = "",
    user: str = "",
    password: str = "",
    auth_required: bool = True,
    whatsapp_hosted_pass: bool = False,
    skip_visual: bool = False,
    skip_motion: bool = False,
    skip_orchestrator: bool = False,
    reuse_hosted_report: bool = False,
    reuse_motion_report: bool = False,
) -> dict[str, Any]:
    visual_url = visual_base_url or base_url
    hosted = _load_hosted_report(base_url) if reuse_hosted_report else {}
    hosted_source = "existing_report" if hosted else "live_validation"
    if not hosted:
        hosted = validate_hosted_runtime(base_url, user=user, password=password)
    visual = (
        {"passed": True, "skipped": True, "base_url": visual_url, "checks_passed": 0, "checks_total": 0, "checks": []}
        if skip_visual
        else validate_visual_presence(visual_url)
    )
    motion = (
        {"passed": True, "skipped": True, "base_url": visual_url, "checks_passed": 0, "checks_total": 0, "checks": []}
        if skip_motion
        else (_load_eye_motion_report(visual_url) if reuse_motion_report else {}) or validate_eye_motion(visual_url)
    )
    orchestrator = (
        {"passed": True, "skipped": True}
        if skip_orchestrator
        else _run_orchestrator_validation()
    )
    whatsapp_checks = [
        check
        for check in hosted.get("checks", [])
        if check.get("name")
        in {"whatsapp_hosted_ingress_test", "whatsapp_webhook_verification", "whatsapp_provider_webhook_route"}
    ]
    blockers = _readiness_blockers(
        base_url=base_url,
        hosted=hosted,
        visual=visual,
        motion=motion,
        orchestrator=orchestrator,
        auth_required=auth_required,
        whatsapp_hosted_pass=whatsapp_hosted_pass,
    )
    runtime_ready = hosted.get("passed") is True and orchestrator.get("passed") is True and orchestrator.get("skipped") is not True
    auth_checks = [check for check in hosted.get("checks", []) if str(check.get("name", "")).startswith("auth:")]
    production_deployment_ready = not blockers
    health = next((check for check in hosted.get("checks", []) if check.get("name") == "health"), {})
    gate_checks = [
        {"name": "hosted_runtime", "passed": hosted.get("passed") is True},
        {"name": "visual_presence", "passed": visual.get("passed") is True and visual.get("skipped") is not True},
        {"name": "eye_motion", "passed": motion.get("passed") is True and motion.get("skipped") is not True},
        {"name": "orchestrator", "passed": orchestrator.get("passed") is True and orchestrator.get("skipped") is not True},
        {"name": "auth_protection", "passed": bool(auth_checks) and all(check.get("passed") is True for check in auth_checks)},
        {"name": "whatsapp_backend_ingress", "passed": len(whatsapp_checks) == 3 and all(check.get("passed") is True for check in whatsapp_checks)},
        {"name": "whatsapp_provider_live", "passed": whatsapp_hosted_pass is True},
        {"name": "public_health", "passed": health.get("status") == 200 and health.get("runtime_status") == "ready"},
        {"name": "permanent_domain", "passed": not _is_temporary_url(base_url)},
    ]
    checks_passed = sum(1 for check in gate_checks if check["passed"])
    checks_total = len(gate_checks)
    report = {
        "validated_at": _now(),
        "base_url": base_url.rstrip("/"),
        "visual_base_url": visual_url.rstrip("/"),
        "passed": production_deployment_ready,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "runtime_ready": runtime_ready,
        "runtime_ready_percent": 100 if runtime_ready else 0,
        "production_deployment": "ready" if production_deployment_ready else "pending",
        "public_beta_ready": production_deployment_ready,
        "temporary_preview": _is_temporary_url(base_url),
        "auth_required": auth_required,
        "auth_protection_pass": bool(auth_checks) and all(check.get("passed") is True for check in auth_checks),
        "whatsapp_hosted_pass": whatsapp_hosted_pass,
        "whatsapp_backend_ingress_pass": len(whatsapp_checks) == 3 and all(check.get("passed") is True for check in whatsapp_checks),
        "gate_checks": gate_checks,
        "checks": {
            "hosted_runtime": {
                "passed": hosted.get("passed"),
                "checks_passed": hosted.get("checks_passed"),
                "checks_total": hosted.get("checks_total"),
                "auth_mode": hosted.get("auth_mode"),
                "source": hosted_source,
                "report": "central_orchestrator/reports/HOSTED_RUNTIME_VALIDATION.json",
            },
            "visual_presence": {
                "passed": visual.get("passed"),
                "checks_passed": visual.get("checks_passed"),
                "checks_total": visual.get("checks_total"),
                "report": "central_orchestrator/reports/VISUAL_PRESENCE_VALIDATION.json",
                "skipped": visual.get("skipped", False),
            },
            "eye_motion": {
                "passed": motion.get("passed"),
                "checks_passed": motion.get("checks_passed"),
                "checks_total": motion.get("checks_total"),
                "report": "central_orchestrator/reports/EYE_MOTION_VALIDATION.json",
                "skipped": motion.get("skipped", False),
                "source": "existing_report" if reuse_motion_report and not skip_motion else "live_validation",
            },
            "orchestrator": orchestrator,
        },
        "blockers": blockers,
        "next_action": "Deploy to permanent host/domain, enable auth secrets, connect WhatsApp to hosted runtime, then rerun this gate."
        if blockers
        else "Public beta gate passed. Proceed with controlled launch approval.",
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the combined AIOS public beta readiness gate.")
    parser.add_argument("base_url", help="Hosted AIOS URL to validate.")
    parser.add_argument("--visual-base-url", default="", help="Optional URL for visual screenshots; defaults to base_url.")
    parser.add_argument("--user", default=os.getenv("AIOS_BASIC_AUTH_USER", ""))
    parser.add_argument("--password", default=os.getenv("AIOS_BASIC_AUTH_PASSWORD", ""))
    parser.add_argument("--auth-not-required", action="store_true")
    parser.add_argument("--whatsapp-hosted-pass", action="store_true")
    parser.add_argument("--skip-visual", action="store_true")
    parser.add_argument("--skip-motion", action="store_true")
    parser.add_argument("--skip-orchestrator", action="store_true")
    parser.add_argument("--reuse-hosted-report", action="store_true")
    parser.add_argument("--reuse-motion-report", action="store_true")
    args = parser.parse_args()
    report = validate(
        args.base_url,
        visual_base_url=args.visual_base_url,
        user=args.user,
        password=args.password,
        auth_required=not args.auth_not_required,
        whatsapp_hosted_pass=args.whatsapp_hosted_pass,
        skip_visual=args.skip_visual,
        skip_motion=args.skip_motion,
        skip_orchestrator=args.skip_orchestrator,
        reuse_hosted_report=args.reuse_hosted_report,
        reuse_motion_report=args.reuse_motion_report,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["public_beta_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
