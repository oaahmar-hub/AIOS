#!/usr/bin/env python3
"""Run the AIOS production hosting pipeline after Railway login.

This is the one-command operator path. It runs the guarded Railway deploy
runner, then runs the public hosting finalizer. It does not bypass approval:
the underlying deploy runner still refuses to create/update public resources
unless Railway is authenticated and required environment is present.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUNTIME_DIR = Path(__file__).resolve().parent
AIOS_ROOT = RUNTIME_DIR.parents[2]
REPORTS_DIR = RUNTIME_DIR.parent / "reports"
REPORT_PATH = REPORTS_DIR / "PRODUCTION_HOSTING_PIPELINE_RUN.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, cwd=AIOS_ROOT, text=True, capture_output=True)
    return {
        "cmd": " ".join(args),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-5000:],
        "stderr": proc.stderr[-5000:],
    }


def _load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _deploy_cmd(args: argparse.Namespace, *, existing: bool = False, message: str = "") -> list[str]:
    deploy_cmd = [
        sys.executable,
        str(RUNTIME_DIR / "deploy_railway_production.py"),
        "--execute",
    ]
    if args.ensure_domain:
        deploy_cmd.append("--ensure-domain")
    if args.existing or existing:
        deploy_cmd.append("--existing")
    if args.service:
        deploy_cmd.extend(["--service", args.service])
    if args.name:
        deploy_cmd.extend(["--name", args.name])
    if message:
        deploy_cmd.extend(["--message", message])
    return deploy_cmd


def _env_sync_cmd(args: argparse.Namespace) -> list[str]:
    env_cmd = [
        sys.executable,
        str(RUNTIME_DIR / "sync_railway_environment.py"),
        "--execute",
    ]
    if args.service:
        env_cmd.extend(["--service", args.service])
    if args.environment:
        env_cmd.extend(["--environment", args.environment])
    return env_cmd


def run(args: argparse.Namespace) -> dict[str, Any]:
    deploy_initial = _run(_deploy_cmd(args, message="AIOS production hosting initial deploy"))
    env_sync = _run(_env_sync_cmd(args))
    env_sync_report_path = REPORTS_DIR / "RAILWAY_ENVIRONMENT_SYNC.json"
    env_sync_report = _load_report(env_sync_report_path)
    deploy_after_env = (
        _run(_deploy_cmd(args, existing=True, message="AIOS production hosting env redeploy"))
        if env_sync_report.get("status") == "synced"
        else {"cmd": "skipped", "returncode": 0, "stdout": "", "stderr": "Skipped because Railway environment sync did not complete."}
    )

    finalize_cmd = [sys.executable, str(RUNTIME_DIR / "finalize_production_hosting.py")]
    if args.base_url:
        finalize_cmd.extend(["--base-url", args.base_url])
    if args.whatsapp_hosted_pass:
        finalize_cmd.append("--whatsapp-hosted-pass")
    if args.skip_visual:
        finalize_cmd.append("--skip-visual")
    if args.skip_motion:
        finalize_cmd.append("--skip-motion")
    if args.skip_orchestrator:
        finalize_cmd.append("--skip-orchestrator")
    finalize = _run(finalize_cmd)

    deploy_report_path = REPORTS_DIR / "RAILWAY_PRODUCTION_DEPLOYMENT_RUN.json"
    finalization_report_path = REPORTS_DIR / "PRODUCTION_HOSTING_PUBLIC_FINALIZATION.json"
    deploy_report = _load_report(deploy_report_path)
    finalization_report = _load_report(finalization_report_path)
    report = {
        "generated_at": _now(),
        "mode": "deploy_then_finalize",
        "commands": {
            "deploy_initial": deploy_initial,
            "env_sync": env_sync,
            "deploy_after_env": deploy_after_env,
            "finalize": finalize,
        },
        "reports": {
            "railway_environment_sync": str(env_sync_report_path.relative_to(AIOS_ROOT)),
            "railway_deploy": str(deploy_report_path.relative_to(AIOS_ROOT)),
            "public_finalization": str(finalization_report_path.relative_to(AIOS_ROOT)),
        },
        "environment_sync_status": env_sync_report.get("status"),
        "railway_status": deploy_report.get("status"),
        "public_url_candidates": deploy_report.get("public_url_candidates", []),
        "finalization_status": finalization_report.get("status"),
        "finalization_classification": finalization_report.get("classification"),
        "blockers": list(dict.fromkeys((env_sync_report.get("environment", {}).get("missing_required", []) or []) + (deploy_report.get("environment", {}).get("missing_required", []) or []) + (finalization_report.get("blockers", []) or []))),
        "classification": "LIVE" if finalization_report.get("classification") == "LIVE" else "PARTIAL",
    }
    report["next_action"] = (
        "Production hosting is LIVE. Proceed only with controlled launch approval."
        if report["classification"] == "LIVE"
        else "Complete Railway login, hosted env secrets, and permanent public URL, then rerun this pipeline."
    )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deploy + public finalization for AIOS production hosting.")
    parser.add_argument("--base-url", default="", help="Optional permanent public AIOS URL.")
    parser.add_argument("--name", default="aios-runtime", help="Railway project name for new deploys.")
    parser.add_argument("--service", default="", help="Optional Railway service name.")
    parser.add_argument("--environment", default="", help="Optional Railway environment name.")
    parser.add_argument("--existing", action="store_true", help="Deploy to linked existing Railway project/service.")
    parser.add_argument("--ensure-domain", action="store_true", default=False, help="Ask Railway to generate a public domain after deploy.")
    parser.add_argument("--no-ensure-domain", dest="ensure_domain", action="store_false", help="Skip Railway domain generation.")
    parser.add_argument("--whatsapp-hosted-pass", action="store_true", help="Mark live hosted WhatsApp provider test as externally proven.")
    parser.add_argument("--skip-visual", action="store_true", help="Skip visual validation for diagnostics only.")
    parser.add_argument("--skip-motion", action="store_true", help="Skip Eye motion validation for diagnostics only.")
    parser.add_argument("--skip-orchestrator", action="store_true", help="Skip internal orchestrator validation for diagnostics only.")
    return parser.parse_args()


def main() -> int:
    report = run(parse_args())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["classification"] == "LIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
