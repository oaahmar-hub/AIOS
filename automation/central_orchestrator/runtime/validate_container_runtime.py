#!/usr/bin/env python3
"""Validate the AIOS container deployment contract.

This validator checks the Docker/Render runtime contract and runs a Docker
build/smoke test only when Docker is available locally. It does not publish,
deploy, write secrets, or call external providers.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "CONTAINER_RUNTIME_VALIDATION.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(rel: str) -> str:
    path = AIOS_ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _static_checks() -> list[dict[str, Any]]:
    dockerfile = _read("Dockerfile")
    live_server = _read("automation/central_orchestrator/runtime/aios_live_api_server.py")
    render = _read("render.yaml")
    dockerignore = _read(".dockerignore")
    env = _read(".env.production.example")
    checks = [
        {
            "name": "dockerfile_python_runtime",
            "passed": "FROM python:3.12-slim" in dockerfile,
            "evidence": "Dockerfile uses python:3.12-slim",
        },
        {
            "name": "dockerfile_runtime_command",
            "passed": "aios_live_api_server.py" in dockerfile and '"--host", "0.0.0.0"' in dockerfile,
            "evidence": "Dockerfile starts AIOS live API server on 0.0.0.0 without shell expansion",
        },
        {
            "name": "dockerfile_healthcheck",
            "passed": "HEALTHCHECK" in dockerfile and "/api/health" in dockerfile,
            "evidence": "Docker healthcheck probes /api/health",
        },
        {
            "name": "dockerfile_port",
            "passed": "EXPOSE 8765" in dockerfile and 'os.getenv("PORT")' in live_server,
            "evidence": "Dockerfile exposes 8765; AIOS runtime reads Railway/host PORT directly",
        },
        {
            "name": "render_docker_runtime",
            "passed": "runtime: docker" in render and "healthCheckPath: /api/health" in render,
            "evidence": "render.yaml uses Docker with /api/health",
        },
        {
            "name": "render_auth_secrets",
            "passed": "AIOS_BASIC_AUTH_USER" in render
            and "AIOS_BASIC_AUTH_PASSWORD" in render
            and "sync: false" in render,
            "evidence": "Render config keeps auth secrets external",
        },
        {
            "name": "render_whatsapp_hold_mode",
            "passed": "AIOS_WHATSAPP_REPLY_MODE" in render
            and "hold" in render
            and "AIOS_WHATSAPP_VERIFY_TOKEN" in render,
            "evidence": "Render config keeps WhatsApp in hold mode with external verify token",
        },
        {
            "name": "dockerignore_excludes_runtime_reports",
            "passed": "automation/central_orchestrator/reports" in dockerignore
            and "automation/whatsapp_provider_gateway/reports" in dockerignore,
            "evidence": ".dockerignore excludes local reports/state from hosted image",
        },
        {
            "name": "dockerignore_excludes_generated_build_outputs",
            "passed": "android/**" in dockerignore
            and "mobile-dist/**" in dockerignore
            and "evidence/**" in dockerignore
            and "automation/evidence/**" in dockerignore,
            "evidence": ".dockerignore excludes generated native/mobile/evidence outputs from hosted image",
        },
        {
            "name": "dockerignore_excludes_heavy_brand_binaries",
            "passed": "knowledge-base/branding/assets/**" in dockerignore,
            "evidence": ".dockerignore excludes large brand binary assets; runtime uses BRAND-ASSET-MANIFEST.json",
        },
        {
            "name": "runtime_command_center_data_api",
            "passed": 'path == "/api/command-center/data"' in live_server
            and "get_command_center_data()" in live_server,
            "evidence": "Hosted Command Center data is served by live API when static reports are excluded",
        },
        {
            "name": "runtime_gzip_json",
            "passed": "gzip.compress(body)" in live_server and "Content-Encoding" in live_server,
            "evidence": "AIOS live API compresses large JSON responses",
        },
        {
            "name": "production_env_template",
            "passed": "AIOS_ENV=production" in env
            and "AIOS_AUTH_MODE=basic" in env
            and "AIOS_WHATSAPP_REPLY_MODE=hold" in env,
            "evidence": ".env.production.example documents production runtime mode",
        },
    ]
    return checks


def _run(command: list[str], timeout: int = 120) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(AIOS_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "stdout_tail": completed.stdout[-1200:],
        "stderr_tail": completed.stderr[-1200:],
    }


def _docker_checks() -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker:
        return {
            "available": False,
            "passed": True,
            "skipped": True,
            "reason": "Docker CLI is not installed in this environment.",
        }
    version = _run([docker, "--version"], timeout=30)
    info = _run([docker, "info"], timeout=30)
    if not version["passed"] or not info["passed"]:
        return {
            "available": True,
            "passed": False,
            "skipped": False,
            "version": version,
            "info": info,
            "reason": "Docker CLI is present but the daemon is not usable.",
        }
    tag = "aios-runtime:local-validation"
    build = _run([docker, "build", "-t", tag, "."], timeout=600)
    return {
        "available": True,
        "passed": build["passed"],
        "skipped": False,
        "version": version,
        "info": {"passed": info["passed"], "elapsed_ms": info["elapsed_ms"]},
        "build": build,
        "image": tag,
    }


def validate() -> dict[str, Any]:
    static_checks = _static_checks()
    docker_checks = _docker_checks()
    static_passed = all(item["passed"] for item in static_checks)
    report = {
        "validated_at": _now(),
        "product": "AIOS",
        "feature": "Container Runtime Validation",
        "passed": static_passed and docker_checks.get("passed") is True,
        "container_contract_ready": static_passed,
        "docker_runtime_smoke": "pass"
        if docker_checks.get("available") and docker_checks.get("passed")
        else "skipped"
        if docker_checks.get("skipped")
        else "fail",
        "checks_passed": sum(1 for item in static_checks if item["passed"]),
        "checks_total": len(static_checks),
        "checks": static_checks,
        "docker": docker_checks,
        "blockers": [] if static_passed else [item["name"] for item in static_checks if not item["passed"]],
        "next_action": "Run this validator on a machine with Docker installed to add local container build proof."
        if docker_checks.get("skipped")
        else "Container runtime contract and Docker build proof are ready."
        if docker_checks.get("passed")
        else "Fix Docker runtime errors before permanent hosting.",
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
