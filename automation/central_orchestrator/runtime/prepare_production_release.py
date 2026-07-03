#!/usr/bin/env python3
"""Prepare an AIOS production release candidate.

This is a local packaging gate. It validates the deployable package, runs
preflight, refreshes launch readiness, builds the runtime bundle, and writes one
release-candidate report. It does not deploy, publish, write secrets, or call
external providers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import build_deployment_bundle
import deployment_preflight
import validate_container_runtime
import validate_deployment_package
import validate_host_environment
import validate_production_launch_readiness


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "PRODUCTION_RELEASE_CANDIDATE.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(path: str) -> str:
    return path


def prepare() -> dict[str, Any]:
    package = validate_deployment_package.validate()
    container = validate_container_runtime.validate()
    host_env = validate_host_environment.validate()
    preflight = deployment_preflight.validate()
    launch = validate_production_launch_readiness.validate()
    bundle = build_deployment_bundle.build(build_deployment_bundle.DEFAULT_OUTPUT_DIR)

    runtime_ready = launch.get("runtime_ready") is True
    public_beta_ready = launch.get("public_beta_ready") is True
    release_candidate_ready = (
        package.get("passed") is True
        and container.get("container_contract_ready") is True
        and preflight.get("passed") is True
        and bundle.get("passed") is True
        and runtime_ready
    )
    blockers = list(launch.get("blockers") or [])
    report = {
        "generated_at": _now(),
        "product": "AIOS",
        "feature": "Production Release Candidate",
        "release_candidate_ready": release_candidate_ready,
        "runtime_ready_percent": launch.get("runtime_ready_percent", 0),
        "runtime_ready": runtime_ready,
        "production_deployment": "ready" if public_beta_ready else "pending",
        "public_beta_ready": public_beta_ready,
        "status": "public_beta_ready" if public_beta_ready else "release_candidate_ready_pending_external_launch"
        if release_candidate_ready
        else "release_candidate_not_ready",
        "public_url": launch.get("public_url", ""),
        "artifact": {
            "bundle": _rel(bundle.get("bundle", "")),
            "manifest": _rel(bundle.get("manifest", "")),
            "bundle_sha256": bundle.get("bundle_sha256", ""),
            "bundle_bytes": bundle.get("bundle_bytes", 0),
            "file_count": bundle.get("file_count", 0),
            "missing_required": bundle.get("missing_required", []),
        },
        "checks": {
            "deployment_package": {
                "passed": package.get("passed") is True,
                "checks": f"{package.get('checks_passed', 0)}/{package.get('checks_total', 0)}",
                "report": "automation/central_orchestrator/reports/DEPLOYMENT_PACKAGE_VALIDATION.json",
            },
            "deployment_preflight": {
                "passed": preflight.get("passed") is True,
                "production_env_ready": preflight.get("production_env_ready") is True,
                "status": preflight.get("deployment_status", ""),
                "report": "automation/central_orchestrator/reports/DEPLOYMENT_PREFLIGHT.json",
            },
            "container_runtime": {
                "passed": container.get("passed") is True,
                "container_contract_ready": container.get("container_contract_ready") is True,
                "docker_runtime_smoke": container.get("docker_runtime_smoke", "not_validated"),
                "report": "automation/central_orchestrator/reports/CONTAINER_RUNTIME_VALIDATION.json",
            },
            "host_environment": {
                "passed": host_env.get("passed") is True,
                "production_env_ready": host_env.get("production_env_ready") is True,
                "required": f"{host_env.get('required_checks_passed', 0)}/{host_env.get('required_checks_total', 0)}",
                "report": "automation/central_orchestrator/reports/HOST_ENVIRONMENT_VALIDATION.json",
            },
            "launch_readiness": {
                "passed": runtime_ready,
                "status": launch.get("status", ""),
                "report": "automation/central_orchestrator/reports/PRODUCTION_LAUNCH_READINESS.json",
            },
            "bundle": {
                "passed": bundle.get("passed") is True,
                "report": bundle.get("manifest", ""),
            },
        },
        "blockers": blockers,
        "external_side_effects": {
            "published": False,
            "deployed": False,
            "secrets_written": False,
            "external_provider_called": False,
        },
        "next_action": "Upload the bundle to permanent hosting, set production secrets, attach domain, connect WhatsApp provider, then rerun public beta validation."
        if blockers
        else "Public beta is ready for controlled launch approval.",
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = prepare()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["release_candidate_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
