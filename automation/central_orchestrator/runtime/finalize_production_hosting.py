#!/usr/bin/env python3
"""Finalize AIOS production hosting evidence after public deployment.

This runner does not deploy, publish, create accounts, or write secrets. It
collects the public URL from arguments/environment, runs the existing hosted
validation gates, and writes one evidence report for the production-hosting
track.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from validate_hosted_runtime import validate as validate_hosted_runtime
from validate_public_beta import validate as validate_public_beta
from validate_production_launch_readiness import validate as validate_launch_readiness


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "PRODUCTION_HOSTING_PUBLIC_FINALIZATION.json"
RAILWAY_RUN_REPORT_PATH = REPORTS_DIR / "RAILWAY_PRODUCTION_DEPLOYMENT_RUN.json"
TEMP_HOST_MARKERS = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    ".lhr.life",
    "localhost.run",
    "ngrok",
    "trycloudflare",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_cmd(args: list[str]) -> str:
    return " ".join(args)


def _run(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, cwd=AIOS_ROOT, text=True, capture_output=True)
    return {
        "cmd": _safe_cmd(args),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def _host(base_url: str) -> str:
    return urlparse(base_url).netloc.lower()


def _is_temporary_url(base_url: str) -> bool:
    host = _host(base_url)
    return not host or any(marker in host for marker in TEMP_HOST_MARKERS)


def _railway_state() -> dict[str, Any]:
    railway = shutil.which("railway")
    if not railway:
        local_railway = Path.home() / ".railway/bin/railway"
        if local_railway.exists():
            railway = str(local_railway)
    if not railway:
        return {"available": False, "authenticated": False, "whoami": {"error": "railway cli not found"}}
    whoami = _run([railway, "whoami"])
    state: dict[str, Any] = {
        "available": True,
        "authenticated": whoami["returncode"] == 0,
        "whoami": whoami,
    }
    if state["authenticated"]:
        state["status"] = _run([railway, "status", "--json"])
        state["domains"] = _run([railway, "domain", "--help"])
    return state


def _resolve_base_url(arg_url: str = "") -> str:
    railway_candidates: list[str] = []
    if RAILWAY_RUN_REPORT_PATH.exists():
        try:
            railway_report = json.loads(RAILWAY_RUN_REPORT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            railway_report = {}
        railway_candidates = [
            str(item)
            for item in railway_report.get("public_url_candidates", [])
            if str(item).strip()
        ]
    candidates = [
        arg_url,
        os.getenv("AIOS_PUBLIC_BASE_URL", ""),
        os.getenv("AIOS_PUBLIC_API_BASE_URL", ""),
        os.getenv("RAILWAY_PUBLIC_DOMAIN", ""),
    ] + railway_candidates
    for candidate in candidates:
        candidate = candidate.strip().rstrip("/")
        if not candidate:
            continue
        if not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        return candidate
    return ""


def _env_presence() -> dict[str, Any]:
    required = [
        "AIOS_ENV",
        "AIOS_AUTH_MODE",
        "AIOS_BASIC_AUTH_USER",
        "AIOS_BASIC_AUTH_PASSWORD",
        "AIOS_WHATSAPP_REPLY_MODE",
        "AIOS_WHATSAPP_VERIFY_TOKEN",
    ]
    optional = [
        "AIOS_PUBLIC_BASE_URL",
        "AIOS_PUBLIC_API_BASE_URL",
        "AIOS_CUSTOM_DOMAIN",
        "AIOS_WHATSAPP_HOSTED_TEST",
        "RAILWAY_PUBLIC_DOMAIN",
    ]
    return {
        "required": {
            key: {
                "present": bool(os.getenv(key)),
                "secret": key in {"AIOS_BASIC_AUTH_USER", "AIOS_BASIC_AUTH_PASSWORD", "AIOS_WHATSAPP_VERIFY_TOKEN"},
            }
            for key in required
        },
        "optional": {key: {"present": bool(os.getenv(key)), "secret": False} for key in optional},
        "missing_required": [key for key in required if not os.getenv(key)],
    }


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    base_url = _resolve_base_url(args.base_url)
    railway = _railway_state()
    environment = _env_presence()
    report: dict[str, Any] = {
        "validated_at": _now(),
        "mode": "public_finalization",
        "base_url": base_url,
        "railway": railway,
        "environment": environment,
        "temporary_preview": _is_temporary_url(base_url) if base_url else None,
        "checks": {},
        "status": "not_started",
        "classification": "PARTIAL",
        "blockers": [],
        "next_action": "",
    }
    if not railway.get("authenticated"):
        report["blockers"].append("Railway account authentication is incomplete.")
    if environment["missing_required"]:
        report["blockers"].append("Required production environment variables are missing locally for authenticated hosted validation.")
    if not base_url:
        report["status"] = "blocked_missing_public_url"
        report["blockers"].append("No AIOS_PUBLIC_BASE_URL, AIOS_PUBLIC_API_BASE_URL, RAILWAY_PUBLIC_DOMAIN, or --base-url was provided.")
    elif environment["missing_required"]:
        report["status"] = "blocked_missing_required_env"
    else:
        hosted = validate_hosted_runtime(
            base_url,
            user=os.getenv("AIOS_BASIC_AUTH_USER", ""),
            password=os.getenv("AIOS_BASIC_AUTH_PASSWORD", ""),
        )
        beta = validate_public_beta(
            base_url,
            user=os.getenv("AIOS_BASIC_AUTH_USER", ""),
            password=os.getenv("AIOS_BASIC_AUTH_PASSWORD", ""),
            whatsapp_hosted_pass=args.whatsapp_hosted_pass,
            skip_visual=args.skip_visual,
            skip_motion=args.skip_motion,
            skip_orchestrator=args.skip_orchestrator,
        )
        launch = validate_launch_readiness()
        report["checks"] = {
            "hosted_runtime": {
                "passed": hosted.get("passed"),
                "checks_passed": hosted.get("checks_passed"),
                "checks_total": hosted.get("checks_total"),
                "report": "automation/central_orchestrator/reports/HOSTED_RUNTIME_VALIDATION.json",
            },
            "public_beta": {
                "passed": beta.get("public_beta_ready"),
                "production_deployment": beta.get("production_deployment"),
                "report": "automation/central_orchestrator/reports/PUBLIC_BETA_VALIDATION.json",
            },
            "launch_readiness": {
                "passed": launch.get("public_beta_ready"),
                "runtime_ready": launch.get("runtime_ready"),
                "production_deployment": launch.get("production_deployment"),
                "report": "automation/central_orchestrator/reports/PRODUCTION_LAUNCH_READINESS.json",
            },
        }
        if hosted.get("passed") is not True:
            report["blockers"].append("Hosted runtime validation did not pass.")
        if beta.get("public_beta_ready") is not True:
            report["blockers"].append("Public beta validation did not pass.")
        if launch.get("public_beta_ready") is not True:
            report["blockers"].append("Production launch readiness did not pass.")
        if _is_temporary_url(base_url):
            report["blockers"].append("Public URL is temporary and cannot prove permanent production hosting.")
        report["status"] = "public_beta_ready" if not report["blockers"] else "public_finalization_incomplete"
        report["classification"] = "LIVE" if not report["blockers"] else "PARTIAL"
    if report["blockers"]:
        report["next_action"] = "Complete Railway login/deployment, set hosted env secrets, provide permanent public URL, then rerun finalization."
    else:
        report["next_action"] = "Production hosting evidence is complete. Proceed only with controlled launch approval."
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize AIOS public production-hosting evidence.")
    parser.add_argument("--base-url", default="", help="Permanent public AIOS URL. Falls back to AIOS_PUBLIC_BASE_URL.")
    parser.add_argument("--whatsapp-hosted-pass", action="store_true", help="Mark hosted WhatsApp provider live test as externally proven.")
    parser.add_argument("--skip-visual", action="store_true", help="Skip screenshot validation for emergency diagnostics only.")
    parser.add_argument("--skip-motion", action="store_true", help="Skip Eye motion validation for emergency diagnostics only.")
    parser.add_argument("--skip-orchestrator", action="store_true", help="Skip internal orchestrator validation for emergency diagnostics only.")
    return parser.parse_args()


def main() -> int:
    report = finalize(parse_args())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["classification"] == "LIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
