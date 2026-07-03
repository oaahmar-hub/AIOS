#!/usr/bin/env python3
"""Create one AIOS production launch readiness report.

This script does not deploy, publish, write secrets, or call providers. It reads
the existing validation reports and turns them into one product-launch view:
what is ready, what is blocked, and what must happen before public beta.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "PRODUCTION_LAUNCH_READINESS.json"

SOURCE_REPORTS = {
    "hosted_runtime": REPORTS_DIR / "HOSTED_RUNTIME_VALIDATION.json",
    "auth_protection": REPORTS_DIR / "AUTH_PROTECTION_VALIDATION.json",
    "public_beta": REPORTS_DIR / "PUBLIC_BETA_VALIDATION.json",
    "eye_motion": REPORTS_DIR / "EYE_MOTION_VALIDATION.json",
    "visual_presence": REPORTS_DIR / "VISUAL_PRESENCE_VALIDATION.json",
    "deployment_package": REPORTS_DIR / "DEPLOYMENT_PACKAGE_VALIDATION.json",
    "deployment_preflight": REPORTS_DIR / "DEPLOYMENT_PREFLIGHT.json",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _check(report: dict[str, Any], name: str) -> dict[str, Any]:
    for item in report.get("checks", []):
        if item.get("name") == name:
            return item
    return {}


def _auth_checks_pass(auth: dict[str, Any]) -> bool:
    checks = [item for item in auth.get("checks", []) if str(item.get("name", "")).startswith("auth:")]
    return bool(checks) and all(item.get("passed") is True for item in checks)


def _gate(name: str, passed: bool, evidence: str, blocker: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "evidence": evidence,
        "blocker": "" if passed else blocker,
    }


def validate() -> dict[str, Any]:
    reports = {name: _read(path) for name, path in SOURCE_REPORTS.items()}
    hosted = reports["hosted_runtime"]
    auth = reports["auth_protection"]
    beta = reports["public_beta"]
    motion = reports["eye_motion"]
    visual = reports["visual_presence"]
    package = reports["deployment_package"]
    preflight = reports["deployment_preflight"]

    permission = _check(hosted, "permission_api_restricted_consistency")
    whatsapp_ingress = _check(hosted, "whatsapp_hosted_ingress_test")
    whatsapp_webhook = _check(hosted, "whatsapp_provider_webhook_route")
    hosted_base_url = beta.get("base_url") or hosted.get("base_url") or ""
    hosted_url_ready = hosted_base_url.startswith("https://")
    custom_domain_ready = hosted_url_ready and "railway.app" not in hosted_base_url.lower()
    webhook_ready = whatsapp_webhook.get("passed") is True

    gates = [
        _gate(
            "Hosted runtime surface",
            hosted.get("passed") is True,
            f"{hosted.get('checks_passed', 0)}/{hosted.get('checks_total', 0)} hosted checks",
            "Hosted runtime validation must pass against the public URL.",
        ),
        _gate(
            "Backend Permission API",
            permission.get("passed") is True,
            "Restricted owner-phone request returns one backend decision across WhatsApp, website, mobile, and voice.",
            "Permission API consistency must pass.",
        ),
        _gate(
            "Eye motion",
            motion.get("passed") is True,
            f"{motion.get('checks_passed', 0)}/{motion.get('checks_total', 0)} motion checks",
            "The 10-second Eye motion validation must pass.",
        ),
        _gate(
            "Visual presence",
            visual.get("passed") is True,
            f"{visual.get('checks_passed', 0)}/{visual.get('checks_total', 0)} visual checks",
            "Visual presence validation must pass.",
        ),
        _gate(
            "WhatsApp backend ingress",
            whatsapp_ingress.get("passed") is True and whatsapp_webhook.get("passed") is True,
            "Hosted ingress and provider webhook route receive WhatsApp-shaped payloads in hold mode.",
            "WhatsApp hosted ingress and provider webhook route must pass.",
        ),
        _gate(
            "Production auth behavior",
            auth.get("passed") is True and auth.get("auth_mode") == "basic" and _auth_checks_pass(auth),
            f"{auth.get('checks_passed', 0)}/{auth.get('checks_total', 0)} auth checks",
            "Basic Auth must reject protected routes and keep health public.",
        ),
        _gate(
            "Deployment package",
            package.get("passed") is True,
            f"{package.get('checks_passed', 0)}/{package.get('checks_total', 0)} package checks",
            "Deployment package validation must pass.",
        ),
        _gate(
            "Deployment preflight",
            preflight.get("passed") is True,
            preflight.get("deployment_status", "not_validated"),
            "Deployment preflight must pass.",
        ),
        _gate(
            "Public hosted URL",
            hosted_url_ready,
            hosted_base_url,
            "Public hosted URL must be available.",
        ),
        _gate(
            "Public production auth",
            hosted.get("auth_mode") == "basic",
            f"public auth mode: {hosted.get('auth_mode', 'not_validated')}",
            "Hosted public URL must be validated with production Basic Auth enabled.",
        ),
        _gate(
            "WhatsApp provider route",
            webhook_ready,
            "hosted provider webhook route validates token and accepts WhatsApp-shaped payloads in hold mode",
            "Connect WhatsApp provider to hosted runtime and run hosted provider route validation.",
        ),
        _gate(
            "Custom domain",
            custom_domain_ready,
            hosted_base_url,
            "Attach the final custom domain before public beta is marked ready.",
        ),
        _gate(
            "Public beta",
            beta.get("public_beta_ready") is True,
            beta.get("production_deployment", "pending"),
            "Public beta gate must pass after permanent host, domain, auth, and WhatsApp provider are live.",
        ),
    ]

    core_names = {
        "Hosted runtime surface",
        "Backend Permission API",
        "WhatsApp backend ingress",
        "Production auth behavior",
        "Deployment package",
        "Deployment preflight",
        "Public hosted URL",
        "WhatsApp provider route",
    }
    core_ready = all(item["passed"] for item in gates if item["name"] in core_names)
    public_ready = all(item["passed"] for item in gates)
    blockers = [item["blocker"] for item in gates if item["blocker"]]
    checks_passed = sum(1 for item in gates if item["passed"])
    checks_total = len(gates)
    report = {
        "validated_at": _now(),
        "product": "AIOS",
        "feature": "Production Launch Readiness",
        "passed": public_ready,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "runtime_ready_percent": 100 if core_ready else 0,
        "runtime_ready": core_ready,
        "production_deployment": "ready" if public_ready else "pending",
        "public_beta_ready": public_ready,
        "status": "public_beta_ready" if public_ready else "runtime_ready_pending_external_launch" if core_ready else "runtime_not_ready",
        "public_url": hosted_base_url,
        "auth_status": {
            "public_preview": hosted.get("auth_mode", "not_validated"),
            "production_proof": auth.get("auth_mode", "not_validated"),
            "production_proof_passed": auth.get("passed") is True,
        },
        "whatsapp_status": {
            "backend_ingress": "pass" if whatsapp_ingress.get("passed") is True else "pending_or_failed",
            "provider_route": "pass" if webhook_ready else "pending",
        },
        "eye_status": {
            "motion": "pass" if motion.get("passed") is True else "pending_or_failed",
            "motion_checks": f"{motion.get('checks_passed', 0)}/{motion.get('checks_total', 0)}",
            "visual_presence": "pass" if visual.get("passed") is True else "pending_or_failed",
        },
        "gates": gates,
        "blockers": blockers,
        "source_reports": {
            name: str(path.relative_to(AIOS_ROOT)) for name, path in SOURCE_REPORTS.items()
        },
        "next_action": "Resolve remaining production blockers, then rerun public beta gate."
        if blockers
        else "Public beta is ready for controlled launch approval.",
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = validate()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["runtime_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
